"""A escada de conferência: gerar, conferir e, se reprovado, regerar com o motivo, subindo de modelo.

A primeira tentativa é a resposta da casa, por molde sobre o lastro: correta por construção,
grátis e instantânea. Se a conferência (``conference.confer``) a reprova, cada degrau da
escada (``Drafter``) recebe **só os fatos** que a tentativa reprovada já trazia, a fala do
cliente, os **passos permitidos** (o que a casa pode oferecer como próximo passo) e o
**motivo** da reprovação, e devolve uma reescrita. A reescrita é conferida de novo, agora
sem o benefício da construção: precisa da palavra do juiz e não pode trazer número que não
esteja nos fatos.

Os degraus vão do barato ao capaz; com mais tentativas que degraus, o último se repete.
A subida para quando:

- uma tentativa passa (``chosen`` é ela);
- as tentativas acabam (``max_attempts``, contando a da casa);
- o custo do turno chegaria ao teto, ou o custo de um degrau é **desconhecido** (não se sobe
  às cegas: desconhecido não é zero);

e então sai a **alternativa segura** do adaptador, que nunca compromete nada (o texto literal
das fontes, ou o "vou verificar" com dono e prazo). Degrau que cai conta como tentativa
reprovada e a escada segue.

Cada reprovação fica registrada com o motivo: é a pauta do que falta (pergunta frequente,
regra, passo permitido), medida no placar.

**Papéis separados, configurados um a um, nunca intercambiáveis** (decisão do dono, 21/11/2026):

- o **conferente** (``ReplyJudge``) é um decisor tipado: escolhe entre opções fechadas e devolve
  confiança (no primeiro adaptador, o Jev). Ele não redige;
- o **redator** (``Drafter``) é um modelo de linguagem: escreve a reescrita. Ele não se confere;
- a **escalada** é só do redator, degrau a degrau, e só quando o degrau de baixo foi
  reprovado, com teto de custo por turno (aqui) e por dia (no freio do adaptador). O
  conferente não sobe de degrau.

Um não substitui o outro: a configuração é por papel, nunca "este ou aquele" no mesmo lugar.

``mode="shadow"`` sobe a escada e registra tudo, mas o que sai é a resposta da casa: é como a
escada se mede antes de valer.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from .conference import Conference, ReplyJudge, confer

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass(frozen=True, slots=True)
class Draft:
    text: str
    #: Custo da chamada em US$; ``None`` é desconhecido (e para a subida).
    cost_usd: float | None


class Drafter(Protocol):
    """Um degrau: reescreve a resposta reprovada sem acrescentar fato. Levanta exceção quando cai."""

    name: str

    def draft(self, *, customer: str, facts: str, allowed_steps: Sequence[str], rejection: Sequence[str],
              previous: str = "") -> Draft: ...


@dataclass(frozen=True, slots=True)
class LadderPolicy:
    max_attempts: int = 3
    #: Teto de custo do turno, em US$ (o teto do dia é do freio do adaptador, por cima).
    turn_budget_usd: float = 0.01
    mode: Literal["shadow", "enforce"] = "shadow"

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts >= 1: a resposta da casa é a primeira tentativa")
        if self.turn_budget_usd < 0:
            raise ValueError("turn_budget_usd >= 0")


@dataclass(frozen=True, slots=True)
class Attempt:
    source: str
    text: str
    conference: Conference | None
    cost_usd: float | None = 0.0
    ms: int = 0
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.conference is not None and self.conference.decision == "send"

    def as_record(self) -> dict:
        return {
            "source": self.source,
            "text": self.text,
            "cost_usd": self.cost_usd,
            "ms": self.ms,
            **({"error": self.error} if self.error else {}),
            **({"conference": self.conference.as_record()} if self.conference else {}),
        }


@dataclass(frozen=True, slots=True)
class LadderResult:
    #: O que sai para o cliente (em sombra, sempre a resposta da casa).
    text: str
    #: Quem a escada escolheria: ``house``, o nome de um degrau, ou ``safe``.
    chosen: str
    attempts: tuple[Attempt, ...]
    stopped: str = ""
    safe_text: str = ""

    @property
    def cost_usd(self) -> float | None:
        costs = [a.cost_usd for a in self.attempts]
        return None if any(c is None for c in costs) else round(sum(costs), 6)

    @property
    def rejections(self) -> tuple[str, ...]:
        return tuple(reason for a in self.attempts if a.conference for reason in a.conference.failed)

    def as_record(self) -> dict:
        return {
            "chosen": self.chosen,
            "stopped": self.stopped,
            "cost_usd": self.cost_usd,
            "attempts": [a.as_record() for a in self.attempts],
            **({"safe_text": self.safe_text} if self.chosen == "safe" else {}),
        }


def numbers_outside(text: str, facts: str) -> tuple[str, ...]:
    """Os números da reescrita que não estão nos fatos (preço, quantidade e prazo só vêm do lastro)."""
    known = {n.replace(",", ".") for n in NUMBER.findall(facts or "")}
    return tuple(n for n in NUMBER.findall(text or "") if n.replace(",", ".") not in known)


def climb(
    *,
    customer: str,
    house_text: str,
    house_conference: Conference,
    drafters: Sequence[Drafter],
    judge: ReplyJudge | None,
    policy: LadderPolicy,
    allowed_steps: Sequence[str],
    safe: Callable[[tuple[Attempt, ...]], str],
    has_next_step: Callable[[str], bool],
    acceptable: Callable[[str], bool] = lambda text: True,
    previous: str = "",
    next_step_needed: bool = True,
    estimate_usd: Callable[[Drafter], float | None] = lambda drafter: None,
) -> LadderResult:
    """Sobe a escada a partir da resposta da casa já conferida. Nunca levanta."""
    attempts: list[Attempt] = [Attempt("house", house_text, house_conference)]
    spent = 0.0
    stopped = ""
    chosen = "house" if house_conference.decision == "send" else ""
    if not chosen and not drafters:
        stopped = "no_drafter"
    while not chosen and not stopped:
        if len(attempts) >= policy.max_attempts:
            stopped = "max_attempts"
            break
        drafter = drafters[min(len(attempts) - 1, len(drafters) - 1)]
        estimate = estimate_usd(drafter)
        if estimate is None:
            stopped = f"cost_unknown:{drafter.name}"
            break
        if spent + estimate > policy.turn_budget_usd:
            stopped = "turn_budget"
            break
        rejection = attempts[-1].conference.failed if attempts[-1].conference else ("error",)
        started = time.perf_counter()
        try:
            draft = drafter.draft(customer=customer, facts=house_text, allowed_steps=tuple(allowed_steps),
                                  rejection=rejection, previous=previous)
        except Exception as exc:  # noqa: BLE001 — degrau que cai é tentativa reprovada
            attempts.append(Attempt(drafter.name, "", None, estimate, round((time.perf_counter() - started) * 1000),
                                    error=type(exc).__name__))
            spent += estimate
            continue
        ms = round((time.perf_counter() - started) * 1000)
        if draft.cost_usd is None:
            attempts.append(Attempt(drafter.name, draft.text, None, None, ms, error="cost_unknown"))
            stopped = f"cost_unknown:{drafter.name}"
            break
        spent += draft.cost_usd
        outside = numbers_outside(draft.text, house_text)
        conference = confer(
            customer=customer, reply=draft.text, held=bool(outside) or not acceptable(draft.text),
            by_construction=False, has_next_step=has_next_step(draft.text), judge=judge, previous=previous,
            next_step_needed=next_step_needed,
        )
        attempts.append(Attempt(drafter.name, draft.text, conference, draft.cost_usd, ms,
                                error=("number_outside_facts:" + ",".join(outside)) if outside else ""))
        if conference.decision == "send" and draft.text.strip():
            chosen = drafter.name
    safe_text = ""
    if not chosen:
        chosen = "safe"
        try:
            safe_text = safe(tuple(attempts))
        except Exception:  # noqa: BLE001 — sem alternativa montável, a casa fica com a própria resposta
            safe_text = house_text
    final = {"house": house_text, "safe": safe_text}.get(chosen) or next(
        a.text for a in reversed(attempts) if a.source == chosen and a.passed)
    return LadderResult(
        text=house_text if policy.mode == "shadow" else final,
        chosen=chosen,
        attempts=tuple(attempts),
        stopped=stopped,
        safe_text=safe_text,
    )


__all__ = ["Attempt", "Draft", "Drafter", "LadderPolicy", "LadderResult", "climb", "numbers_outside"]
