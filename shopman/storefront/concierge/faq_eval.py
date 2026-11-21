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
import logging
import pathlib
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from .faq_answer import (  # noqa: E402,F401  (o motor mora em faq_answer; o placar o reexporta)
    MAX_TOKENS,
    Answer,
    _fold,
    answer_with_model,
    build_request,
    held_by_jev,
    inventions,
)

GOLDEN_FAQ_PATH = pathlib.Path(__file__).with_name("golden_faq.json")
ARMS = ("faq", "model")
READ_TIMEOUT_S = 20.0




def load_golden(path=None) -> list[dict]:
    return list(json.loads(pathlib.Path(path or GOLDEN_FAQ_PATH).read_text(encoding="utf-8"))["cases"])


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
    drafts: bool = False
    live_refs: list[str] = field(default_factory=list)
    rows: list[Scored] = field(default_factory=list)
    stopped: str = ""
    #: Com ``jev_check``: os casos em que o Jev reprovou a resposta da IA (e valeu a FAQ direta).
    jev_held: list[str] | None = None

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
            f"{total} perguntas · FAQs na rodada: {len(self.live_refs)}"
            + (" (públicas + rascunhos, só no teste)" if self.drafts else " (só as públicas)")
            + f": {', '.join(self.live_refs)}",
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
        if self.jev_held is not None:
            lines.append(f"  Conferência do Jev: reprovou {len(self.jev_held)} (valeu a FAQ direta)"
                         + (f": {', '.join(self.jev_held)}" if self.jev_held else ""))
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


def live_faq(channel_ref: str, *, include_drafts: bool = False) -> list:
    """As perguntas que valem na rodada: as públicas e, com ``include_drafts``, os rascunhos.

    Os rascunhos entram SÓ no placar (dono, 20/11/2026: "ok, pode fazer assim"); nada é
    publicado nem chega ao cliente. Publicar continua sendo dele, no Admin.
    """
    from shopman.shop.models import FAQEntry, Shop
    from shopman.storefront.presentation.public_information import FAQItemProjection, build_public_faq

    shop = Shop.load()
    items = list(build_public_faq(channel_ref=channel_ref, shop=shop)) if shop else []
    if include_drafts:
        items += [
            FAQItemProjection(ref=f"curated-{entry.ref}", question=entry.question.strip(), answer=entry.answer.strip())
            for entry in FAQEntry.objects.filter(is_published=False).order_by("position", "id")
            if entry.question.strip() and entry.answer.strip()
        ]
    return items


def answer_direct(text: str, *, channel_ref: str, faqs: list) -> Answer:
    """Braço A: a pergunta frequente que melhor casa, servida como está (a busca de hoje)."""
    from shopman.shop.models import Shop
    from shopman.storefront.presentation.public_information import search_public_faq

    from .tools import _public_search_terms

    started = time.perf_counter()
    query = " ".join(_public_search_terms(text))
    found = search_public_faq(query, channel_ref=channel_ref, shop=Shop.load(), limit=1, items=faqs) if query else ()
    elapsed = (time.perf_counter() - started) * 1000
    if not found:
        return Answer(refs=[], ms=elapsed)
    return Answer(refs=[found[0].ref], text=found[0].answer, ms=elapsed)


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


def run(
    cases: list[dict], *, arm: str, channel_ref: str, client=None, model: str = "", budget=None,
    include_drafts: bool = False, jev_check: bool = False,
) -> Report:
    from . import metrics

    faqs = live_faq(channel_ref, include_drafts=include_drafts)
    live = {f.ref for f in faqs}
    report = Report(arm=arm, model=model, live_refs=sorted(live), drafts=include_drafts,
                    jev_held=[] if jev_check and arm == "model" else None)
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
            if report.jev_held is not None and not answer.error and held_by_jev(answer, faqs):
                # O caminho vivo (``intents._faq_by_model``): reprovada, vale a FAQ direta.
                report.jev_held.append(case["ref"])
                answer = answer_direct(case["text"], channel_ref=channel_ref, faqs=faqs)
        report.rows.append(score(case, answer, live=live, faqs=faqs, check_invention=arm == "model"))
    return report
