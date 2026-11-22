"""A verificação de saída: ``verify(conteúdo, evidência, regras) -> pass | repair | hold`` (v2 4.6).

Vale para TODA mensagem, inclusive a de molde e a redigida com marcadores.
*Repara* troca o trecho proibido e segue; *segura* não envia e leva a uma
pessoa; tudo vira achado no ``ReplyPlan``.

Regras genéricas do pacote (estruturais, sem língua nenhuma):

- ``claim_without_backing`` e companhia: afirmação cujo lastro não está na
  evidência, ou não vale (fato desconhecido ou vencido) → segura (N01, N02);
- ``backing_kind_not_accepted``: o lastro existe, mas não é o que o espaço
  aceita (o que se pode prometer não é unidade em mãos, K27) → segura;
- ``number_without_fact``: dígito no texto fora de um espaço preenchido por
  lastro → segura (preço, estado, prazo nunca vêm do texto, N03, K23);
- ``action_without_receipt``: parte de um movimento que muda o negócio sem
  afirmação lastreada em recibo de sucesso → segura (K24).

Regras da casa entram como dado (``PhraseRule``): o pacote traz o mecanismo,
nunca as palavras de uma casa.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from .evidence import Evidence

# Movimentos cuja parte afirma um efeito no negócio: exigem recibo de sucesso.
EFFECT_MOVES = frozenset({"change_cart", "commit_order", "cancel_order", "amend_order", "grant_discount"})
DIGIT = re.compile(r"\d")


@dataclass(frozen=True, slots=True)
class PhraseRule:
    """Regra da casa sobre o texto. ``unless_backing``: a regra não vale se a parte tem esse lastro."""

    code: str
    pattern: str
    action: Literal["repair", "hold"]
    replacement: str | None = None
    unless_backing: str | None = None

    def __post_init__(self) -> None:
        re.compile(self.pattern)
        if self.action == "repair" and self.replacement is None:
            raise ValueError(f"{self.code}: reparo diz pelo que trocar")
        if self.replacement is not None and DIGIT.search(self.replacement):
            raise ValueError(f"{self.code}: o reparo não introduz número")


@dataclass(frozen=True, slots=True)
class RenderedClaim:
    slot: str
    backing: str
    ref: str | None


@dataclass(frozen=True, slots=True)
class Segment:
    """Um trecho do texto. ``slot`` preenchido: bloco travado, valor vindo do lastro."""

    text: str
    slot: str | None = None


@dataclass(frozen=True, slots=True)
class RenderedPart:
    move: str
    segments: tuple[Segment, ...]
    claims: tuple[RenderedClaim, ...]
    # O molde que compôs a parte (``None`` no texto redigido fora de molde). Só registro: não
    # muda texto, lastro nem verificação; diz ao adaptador qual frase da casa saiu.
    template_id: str | None = None

    @property
    def text(self) -> str:
        return "".join(segment.text for segment in self.segments)

    @property
    def free_text(self) -> str:
        """Só o que NÃO veio de lastro (os trechos fixos ou redigidos)."""
        return " ".join(segment.text for segment in self.segments if segment.slot is None)


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    part: int | None
    slot: str | None = None
    action: Literal["repair", "hold"] = "hold"


@dataclass(frozen=True, slots=True)
class VerifyResult:
    result: Literal["pass", "repair", "hold"]
    findings: tuple[Finding, ...]
    parts: tuple[RenderedPart, ...]


def _part_kinds(part: RenderedPart, evidence: Evidence) -> set[str]:
    kinds: set[str] = set()
    for claim in part.claims:
        if claim.ref is not None:
            kinds.update(evidence.kinds_of(claim.backing, claim.ref))
    return kinds


def verify(parts: Iterable[RenderedPart], evidence: Evidence, rules: Iterable[PhraseRule] = (),
           accepted: dict[tuple[int, str], tuple[str, ...]] | None = None) -> VerifyResult:
    """Confere cada parte. ``accepted``: (parte, espaço) → lastros que o molde aceita."""
    parts = tuple(parts)
    findings: list[Finding] = []
    repaired: list[RenderedPart] = []
    for index, part in enumerate(parts):
        for claim in part.claims:
            problem = evidence.problem(claim.backing, claim.ref)
            if problem is not None:
                findings.append(Finding(problem, index, claim.slot))
                continue
            wanted = (accepted or {}).get((index, claim.slot))
            if wanted is not None and claim.ref is not None:
                if not set(evidence.kinds_of(claim.backing, claim.ref)) & set(wanted):
                    findings.append(Finding("backing_kind_not_accepted", index, claim.slot))
        if DIGIT.search(part.free_text):
            findings.append(Finding("number_without_fact", index))
        kinds = _part_kinds(part, evidence)
        if part.move in EFFECT_MOVES and "receipt:success" not in kinds:
            findings.append(Finding("action_without_receipt", index))
        segments = part.segments
        for rule in rules:
            if rule.unless_backing is not None and rule.unless_backing in kinds:
                continue
            if not any(seg.slot is None and re.search(rule.pattern, seg.text) for seg in segments):
                continue
            findings.append(Finding(rule.code, index, action=rule.action))
            if rule.action == "repair":
                # O reparo mexe só no texto livre; o bloco travado fica como veio do lastro.
                segments = tuple(seg if seg.slot is not None else
                                 Segment(re.sub(rule.pattern, rule.replacement or "", seg.text)) for seg in segments)
        repaired.append(RenderedPart(part.move, segments, part.claims, part.template_id))
    if any(f.action == "hold" for f in findings):
        result = "hold"
    elif findings:
        result = "repair"
    else:
        result = "pass"
    return VerifyResult(result, tuple(findings), tuple(repaired))
