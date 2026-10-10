"""Placar da memória (OBS0310-N) sobre os casos de contexto do golden set.

Para cada caso rotulado em ``golden_memory.json``: monta o estado que o caminho de
hoje teria gravado (``dialogue.next_state`` sobre as notas de ferramenta do caso),
aplica o vencimento (``dialogue.effective``) e resolve a fala (``dialogue.resolve``).
Compara com o rótulo: ``resolved``, ``ask``, ``handoff`` ou ``pass``.

**Antes** é o caminho sem memória: nenhuma fala é resolvida nem vira pergunta da
casa; tudo segue como veio para o modelo, que adivinha pelo histórico. Ali só os
casos ``pass`` (a fala se basta) estão certos. **Depois** é com a memória.

Medidas da v2 (seção 6.4): das falas de contexto, quantas foram resolvidas certo ou
viraram pergunta curta (nunca suposição); das que têm referente no estado, quantas
se resolveram sem pergunta; quantos "sim" foram aplicados à pergunta errada.
Sem rede, sem banco: tudo por argumento.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.utils import timezone

from . import dialogue

LABELS_PATH = pathlib.Path(__file__).with_name("golden_memory.json")
OUTCOMES = ("resolved", "handoff", "ask", "pass")
OUTCOME_LABELS = {
    "resolved": "resolvida pelo estado",
    "handoff": "'sim' que chama a equipe",
    "ask": "pergunta em vez de supor",
    "pass": "se basta (memória não mexe)",
}


def load_labels(path=None) -> dict:
    return json.loads(pathlib.Path(path or LABELS_PATH).read_text(encoding="utf-8"))["cases"]


def registry_copy(key: str) -> str:
    """A copy padrão do registro, sem banco (o placar não depende de override do Admin)."""
    from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS, WILDCARD

    entry = OMOTENASHI_DEFAULTS[key][WILDCARD][WILDCARD]
    return (entry.message or entry.title or "").strip()


def _now_for(case: dict) -> datetime:
    day = (case.get("alpha") or {}).get("at") or "2026-10-03"
    return timezone.make_aware(datetime.combine(datetime.fromisoformat(day).date(), time(12, 0)))


@dataclass
class MemoryResult:
    case: dict
    label: dict
    before: str
    after: str
    resolution: dialogue.Resolution

    @property
    def expected(self) -> str:
        return self.label["expect"]["outcome"]

    def ok(self, which: str) -> bool:
        got = self.before if which == "before" else self.after
        if got != self.expected:
            return False
        if which == "before":
            return True
        refs = self.label["expect"].get("refs")
        reason = self.label["expect"].get("reason")
        if refs and list(self.resolution.refs) != refs:
            return False
        return not (reason and self.resolution.reason != reason)


def run_case(case: dict, label: dict) -> MemoryResult:
    now = _now_for(case)
    facts = dialogue.Facts(now=now, quote_token=(label.get("facts") or {}).get("quote_token", ""))
    written = now - timedelta(minutes=2)
    state = dialogue.next_state({}, label.get("events") or [], now=written, fence=1, until=now + timedelta(days=1))
    memory = dialogue.effective(state, facts)
    resolution = dialogue.resolve(case["text"], memory, facts, copy=registry_copy)
    return MemoryResult(case=case, label=label, before="pass", after=resolution.outcome, resolution=resolution)


def run(cases: list[dict], labels: dict | None = None) -> list[MemoryResult]:
    labels = labels if labels is not None else load_labels()
    return [run_case(case, labels[case["ref"]]) for case in cases if case["ref"] in labels]


def render(results: list[MemoryResult], *, show_misses: int = 15) -> str:
    total = len(results)
    if not total:
        return "Nenhum caso de contexto rotulado."
    lines = [f"Memória da conversa: {total} mensagens que dependem do contexto (rótulos em golden_memory.json)."]
    lines.append("")
    lines.append(f"  {'esperado':<34} {'casos':>5} {'antes':>7} {'depois':>7}")
    for outcome in OUTCOMES:
        group = [r for r in results if r.expected == outcome]
        if not group:
            continue
        before = sum(r.ok("before") for r in group)
        after = sum(r.ok("after") for r in group)
        lines.append(f"  {OUTCOME_LABELS[outcome]:<34} {len(group):>5} {before:>7} {after:>7}")
    before = sum(r.ok("before") for r in results)
    after = sum(r.ok("after") for r in results)
    lines.append(f"  {'total certo':<34} {total:>5} {before:>7} {after:>7}")
    lines.append("")
    needs = [r for r in results if r.expected != "pass"]
    safe_after = sum(1 for r in needs if r.ok("after"))
    with_referent = [r for r in results if r.expected in {"resolved", "handoff"}]
    resolved_after = sum(1 for r in with_referent if r.ok("after"))
    wrong_yes = sum(
        1 for r in results
        if dialogue.answer_kind(dialogue.words(r.case["text"])) in {"yes", "weak_yes"}
        and r.after in {"resolved", "handoff"} and not r.ok("after")
    )
    guesses = sum(1 for r in results if r.expected == "ask" and r.after != "ask")
    lines.append(
        f"Precisam de memória ({len(needs)}): resolvidas certo ou com pergunta curta, antes 0, depois {safe_after}."
    )
    lines.append(
        f"Com referente no estado ({len(with_referent)}): resolvidas sem pergunta, antes 0, depois {resolved_after}."
    )
    lines.append(f"'Sim' aplicado à pergunta errada: {wrong_yes}. Suposição onde cabia pergunta: {guesses}.")
    misses = [r for r in results if not r.ok("after")]
    if misses and show_misses:
        lines.append("")
        lines.append(f"Erros depois ({len(misses)}):")
        for r in misses[:show_misses]:
            lines.append(
                f"  {r.case['ref']} \"{r.case['text'][:60]}\": esperado {r.expected}"
                f"/{r.label['expect'].get('reason', '')}, saiu {r.after}/{r.resolution.reason}"
            )
    return "\n".join(lines)
