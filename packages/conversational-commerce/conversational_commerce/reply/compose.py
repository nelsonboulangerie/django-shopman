"""Compor a resposta: plano de partes → molde preenchido pelo lastro → verificação.

O molde é a base sempre gerada (redação por modelo não entra, corte do plano).
Cada espaço do molde é preenchido SÓ a partir da evidência apontada; espaço sem
lastro é erro de programação, nunca texto vazio que passa. O resultado é um
``ReplyPlan`` (F1) com a verificação gravada e o texto, que só existe quando a
verificação não segurou a mensagem.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from conversational_commerce.contracts import Producer, ReplyPlan

from .evidence import Evidence
from .templates import SLOT, Template
from .verify import PhraseRule, RenderedClaim, RenderedPart, Segment, VerifyResult, verify

Formatter = Callable[[Any], str]


class UnresolvedReference(Exception):
    """O formatador de REFERÊNCIA (spec 06) não resolveu o valor: o espaço fica vazio e a verificação segura.

    É o mecanismo de quem diz em texto o que o lastro carrega só como referência opaca (o endereço da
    entrega, P17): o lastro guarda a referência, o texto existe só no envio, e a falha nunca vira frase
    sem o valor nem o valor de outro sujeito.
    """


def plain(value: Any) -> str:
    """Formatação neutra. Dinheiro, data e quantidade na voz da casa são do adaptador."""
    if isinstance(value, bool):
        raise TypeError("booleano não vira texto de resposta; o molde decide a frase")
    return str(value)


@dataclass(frozen=True, slots=True)
class PartSpec:
    """Uma parte: o movimento, o molde e, para cada espaço, o lastro (``backing``, ``ref``)."""

    move: str
    template_id: str
    bindings: Mapping[str, tuple[str, str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Composed:
    plan: ReplyPlan
    verification: VerifyResult
    text: str | None

    @property
    def template_ids(self) -> tuple[str | None, ...]:
        """Os moldes que compuseram a resposta, na ordem das partes."""
        return tuple(part.template_id for part in self.verification.parts)


def render_part(spec: PartSpec, template: Template, evidence: Evidence,
                formatters: Mapping[str, Formatter]) -> RenderedPart:
    if template.move != spec.move:
        raise ValueError(f"o molde {template.template_id} é de {template.move}, não de {spec.move}")
    missing = sorted(set(template.slots) - set(spec.bindings))
    if missing:
        raise ValueError(f"espaço sem lastro no molde {template.template_id}: {missing}")
    segments: list[Segment] = []
    claims: list[RenderedClaim] = []
    cursor = 0
    for match in SLOT.finditer(template.text):
        if match.start() > cursor:
            segments.append(Segment(template.text[cursor:match.start()]))
        slot = match.group(1)
        backing, ref = spec.bindings[slot]
        accepted = set(evidence.kinds_of(backing, ref)) & set(template.slots[slot].accepts)
        if evidence.problem(backing, ref) is None and accepted:
            value = evidence.value(backing, ref, template.slots[slot].field)
            try:
                segments.append(Segment(formatters.get(slot, plain)(value), slot))
            except UnresolvedReference:
                segments.append(Segment("", slot))
                claims.append(RenderedClaim(slot, backing, ref, unresolved=True))  # a verificação segura
                cursor = match.end()
                continue
        else:
            segments.append(Segment("", slot))  # lastro que não vale ou não serve: a verificação segura
        claims.append(RenderedClaim(slot, backing, ref))
        cursor = match.end()
    if cursor < len(template.text):
        segments.append(Segment(template.text[cursor:]))
    if not claims:
        claims.append(RenderedClaim("courtesy", "courtesy", None))
    return RenderedPart(spec.move, tuple(segments), tuple(claims), template.template_id)


def compose(*, specs: Iterable[PartSpec], templates: Mapping[str, Template], evidence: Evidence,
            rules: Iterable[PhraseRule] = (), formatters: Mapping[str, Formatter] | None = None,
            decision_id: str, record: Mapping[str, Any], voice: frozenset[str] | None = None) -> Composed:
    """Compõe e verifica. ``record``: o envelope do ``ReplyPlan`` (id, tenant, environment...).

    ``voice``: os moldes que a casa assina (``verify``); fora deles, a mensagem segura."""
    specs = tuple(specs)
    if not specs:
        raise ValueError("resposta sem parte")
    rendered, accepted = [], {}
    for index, spec in enumerate(specs):
        template = templates[spec.template_id]
        rendered.append(render_part(spec, template, evidence, formatters or {}))
        for slot, slot_spec in template.slots.items():
            accepted[(index, slot)] = slot_spec.accepts
    result = verify(rendered, evidence, rules, accepted, voice)
    plan = ReplyPlan(
        **{"producer": Producer(name="conversational-commerce", version="reply-1"), **record},
        decision_id=decision_id,
        parts=[{"move": part.move, "claims": [{"slot": c.slot, "backing": c.backing, "ref": c.ref}
                                              for c in part.claims]} for part in result.parts],
        locked_blocks=[f"part{index}.{claim.slot}" for index, part in enumerate(result.parts)
                       for claim in part.claims if claim.backing != "courtesy"],
        verification={"result": result.result,
                      "findings": [{"code": f.code, "part": f.part, "slot": f.slot} for f in result.findings]},
    )
    text = None if result.result == "hold" else "\n\n".join(part.text for part in result.parts)
    return Composed(plan, result, text)
