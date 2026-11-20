"""Placar da resposta às perguntas frequentes: a FAQ direta contra a IA a partir das FAQs (WP-18).

Pedido do dono (20/11/2026): "podemos inclusive dar uma chance à IA para responder mesmo as
perguntas frequentes, diretamente baseada nas nossas FAQs ... Vale o teste e comparar".

- **Braço A (``faq``)**: a resposta de hoje, a pergunta frequente que melhor casa com a fala
  (a mesma busca da Concierge), servida como está.
- **Braço B (``model``)**: a IA compõe a resposta usando SÓ as perguntas frequentes
  publicadas, citando quais usou. Sem pergunta frequente que cubra, ela diz que vai
  verificar e não inventa (a Concierge nunca afirma falso).

O verificador é sem modelo: toda referência citada existe; todo número, hora, data e valor
da resposta aparece nas respostas citadas; responder sem citar é invenção. Uma invenção
reprova o braço. Ninguém julga o tom por código: o placar imprime as respostas para leitura.
"""

from __future__ import annotations

import json
import pathlib
import re
import time
import unicodedata
from dataclasses import dataclass, field

GOLDEN_FAQ_PATH = pathlib.Path(__file__).with_name("golden_faq.json")
ARMS = ("faq", "model")
MAX_TOKENS = 700
READ_TIMEOUT_S = 20.0

_NUMBER = re.compile(r"\d+(?:[.,:h]\d+)?")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def load_golden(path=None) -> list[dict]:
    return list(json.loads(pathlib.Path(path or GOLDEN_FAQ_PATH).read_text(encoding="utf-8"))["cases"])


@dataclass
class Answer:
    refs: list[str]
    text: str = ""
    uncovered: str = ""
    error: str = ""
    cost_usd: float | None = 0.0
    ms: float = 0.0


@dataclass
class Scored:
    case: dict
    answer: Answer
    expected: list[set]
    exact: bool
    covered: bool
    extra: list[str]
    invented: list[str]


@dataclass
class Report:
    arm: str
    model: str = ""
    live_refs: list[str] = field(default_factory=list)
    rows: list[Scored] = field(default_factory=list)
    stopped: str = ""

    def render(self, *, show: int = 30) -> str:
        total = len(self.rows)
        exact = sum(r.exact for r in self.rows)
        covered = sum(r.covered for r in self.rows)
        extra = sum(bool(r.extra) for r in self.rows)
        invented = [r for r in self.rows if r.invented]
        none_cases = [r for r in self.rows if not any(r.expected)]
        verified = sum(not r.answer.refs for r in none_cases)
        lines = [
            f"Braço: {self.arm}" + (f" ({self.model})" if self.model else ""),
            f"{total} perguntas · FAQs vivas: {len(self.live_refs)} ({', '.join(self.live_refs)})",
            f"  Resposta certa (as FAQs certas, nem mais nem menos)   {exact}/{total}",
            f"  Pergunta coberta por inteiro                           {covered}/{total}",
            f"  Texto vizinho (FAQ que não responde a pergunta)        {extra}",
            f"  Sem FAQ que cubra: disse que vai verificar             {verified}/{len(none_cases)}",
            f"  INVENÇÃO (reprova o braço)                             {len(invented)}",
        ]
        timed = sorted(r.answer.ms for r in self.rows if r.answer.ms)
        if timed:
            p95 = timed[min(len(timed) - 1, int(round(0.95 * (len(timed) - 1))))]
            lines.append(f"  Tempo da resposta: p50 {timed[len(timed) // 2]:.0f} ms, p95 {p95:.0f} ms")
        errors = [r for r in self.rows if r.answer.error]
        if errors:
            lines.append("  Falhas (a resposta caiu na FAQ direta): " + ", ".join(sorted({r.answer.error for r in errors})))
        if self.stopped:
            lines.append(f"  ⚠ {self.stopped}")
        if invented:
            lines.append("Invenções:")
            lines += [f"  {r.case['ref']}: {', '.join(r.invented)}" for r in invented]
        misses = [r for r in self.rows if not r.exact]
        if misses:
            lines.append(f"Erros ({len(misses)}):")
            for r in misses[:show]:
                expected = " + ".join("/".join(sorted(p)) or "nenhuma" for p in r.expected)
                lines.append(f"  {r.case['ref']} \"{r.case['text'][:60]}\": esperado {expected}, saiu {', '.join(r.answer.refs) or 'nenhuma'}")
        lines.append("Respostas (para ler o tom):")
        for r in self.rows[:show]:
            text = " ".join((r.answer.text or "(vou verificar)").split())
            lines.append(f"  {r.case['ref']}: {text[:220]}")
        return "\n".join(lines)


def live_faq(channel_ref: str) -> list:
    from shopman.shop.models import Shop
    from shopman.storefront.presentation.public_information import build_public_faq

    shop = Shop.load()
    return list(build_public_faq(channel_ref=channel_ref, shop=shop)) if shop else []


def answer_direct(text: str, *, channel_ref: str, faqs: list) -> Answer:
    """Braço A: a pergunta frequente que melhor casa, servida como está (a busca de hoje)."""
    from shopman.shop.models import Shop
    from shopman.storefront.presentation.public_information import search_public_faq

    from .tools import _public_search_terms

    started = time.perf_counter()
    query = " ".join(_public_search_terms(text))
    found = search_public_faq(query, channel_ref=channel_ref, shop=Shop.load(), limit=1) if query else ()
    elapsed = (time.perf_counter() - started) * 1000
    if not found:
        return Answer(refs=[], ms=elapsed)
    return Answer(refs=[found[0].ref], text=found[0].answer, ms=elapsed)


_SYSTEM = """Você é a Concierge da padaria, no WhatsApp. Responda à cliente usando SÓ as \
perguntas frequentes abaixo. Nunca afirme nada que elas não digam: nada de preço, horário, \
prazo, endereço, ingrediente ou política que não esteja escrito nelas.

Regras:
- cite as referências (ref) das perguntas frequentes que usou;
- se uma parte da pergunta não é coberta por nenhuma, escreva essa parte em "uncovered" e não \
a responda (a casa vai verificar);
- se nenhuma parte é coberta, devolva refs vazio e answer vazio;
- voz feminina, cordial e curta; sem travessão.

Responda só com JSON: {"refs": ["..."], "answer": "...", "uncovered": "..."}"""


def build_request(text: str, faqs: list, *, model: str) -> dict:
    catalog = "\n\n".join(f"ref: {f.ref}\npergunta: {f.question}\nresposta: {f.answer}" for f in faqs)
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        # Resposta curta, sem raciocínio (o mesmo aprendizado do #2909).
        "thinking": {"type": "disabled"},
        "system": [{"type": "text", "text": _SYSTEM + "\n\nPerguntas frequentes:\n\n" + catalog}],
        "messages": [{"role": "user", "content": f"Mensagem da cliente:\n<<<\n{text}\n>>>"}],
    }


def answer_with_model(text: str, *, faqs: list, client, model: str) -> Answer:
    """Braço B: a IA compõe a resposta a partir das FAQs, citando quais usou."""
    from .observation_privacy import redact_observation_text

    redacted = redact_observation_text(text).text
    started = time.perf_counter()
    try:
        response = client.messages.create(**build_request(redacted, faqs, model=model))
    except Exception as exc:  # fora do ar, tempo, freio: vale a FAQ direta
        return Answer(refs=[], error=type(exc).__name__, ms=(time.perf_counter() - started) * 1000)
    elapsed = (time.perf_counter() - started) * 1000
    if getattr(response, "stop_reason", "") in {"max_tokens", "refusal"}:
        return Answer(refs=[], error=str(response.stop_reason), ms=elapsed)
    raw = "".join(getattr(b, "text", "") for b in getattr(response, "content", []) if getattr(b, "type", "") == "text")
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return Answer(refs=[], error="fora_do_esquema", ms=elapsed)
    refs = [str(r) for r in (data.get("refs") or []) if isinstance(r, str)]
    return Answer(refs=refs, text=str(data.get("answer") or ""), uncovered=str(data.get("uncovered") or ""), ms=elapsed)


def inventions(answer: Answer, faqs: list) -> list[str]:
    """O que a resposta afirma sem estar nas FAQs citadas. Vazio = nada inventado."""
    by_ref = {f.ref: f for f in faqs}
    out = [f"referência inexistente: {ref}" for ref in answer.refs if ref not in by_ref]
    if answer.text.strip() and not answer.refs:
        out.append("respondeu sem citar pergunta frequente")
    cited = _fold(" ".join(by_ref[r].answer + " " + by_ref[r].question for r in answer.refs if r in by_ref))
    cited_numbers = {n.replace(",", ".") for n in _NUMBER.findall(cited)}
    for number in _NUMBER.findall(_fold(answer.text)):
        if number.replace(",", ".") not in cited_numbers:
            out.append(f"número fora das FAQs: {number}")
    if "—" in answer.text:
        out.append("travessão")
    return out


def score(case: dict, answer: Answer, *, live: set, faqs: list, check_invention: bool) -> Scored:
    # A FAQ que não está publicada agora não responde nada: o certo é verificar.
    expected = [set(part) & live for part in case["parts"]]
    got = set(answer.refs)
    needed = [part for part in expected if part]
    covered = all(part & got for part in needed)
    allowed = set().union(*expected) if expected else set()
    extra = sorted(got - allowed)
    exact = covered and not extra and (bool(needed) or not got)
    # Por inteiro: a parte que nenhuma FAQ cobre também foi tratada (dita como "vou
    # verificar"), e não silenciada. Pergunta toda sem FAQ: não respondeu nada.
    has_uncovered_part = any(not part for part in expected)
    covered = covered and (not has_uncovered_part or (not needed and not got) or bool(answer.uncovered.strip()))
    return Scored(
        case=case, answer=answer, expected=expected, exact=exact, covered=covered, extra=extra,
        invented=inventions(answer, faqs) if check_invention else [],
    )


def run(cases: list[dict], *, arm: str, channel_ref: str, client=None, model: str = "", budget=None) -> Report:
    from . import metrics

    faqs = live_faq(channel_ref)
    live = {f.ref for f in faqs}
    report = Report(arm=arm, model=model, live_refs=sorted(live))
    for index, case in enumerate(cases):
        if budget is not None and (reason := budget.stop_reason(measured=index, total=len(cases))):
            report.stopped = reason
            break
        if arm == "faq":
            answer = answer_direct(case["text"], channel_ref=channel_ref, faqs=faqs)
        else:
            meter = metrics.TurnMeter()
            answer = answer_with_model(case["text"], faqs=faqs, client=meter.wrap(client, "faq"), model=model)
            usage = meter.as_usage()
            answer.cost_usd = usage.get("cost_usd")
            if budget is not None:
                budget.charge(usage.get("cost_usd"))
        report.rows.append(score(case, answer, live=live, faqs=faqs, check_invention=arm == "model"))
    return report
