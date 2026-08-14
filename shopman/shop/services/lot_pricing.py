"""Preço por LOTE — o desconto sai do lote reservado, não da posição.

Este módulo é o primeiro consumidor do modelo de lote/validade (ADR-017) e o que
começa a aposentar o D-1 (ver `docs/plans/D1-RETIREMENT-PLAN.md`): o desconto de
uma linha passa a vir do ``Batch`` que ela reservou — percentual resolvido na
inspeção da fornada e **congelado** no lote — em vez de um percentual linear
amarrado à posição ``"ontem"``.

Por que isso resolve o caso do queijo: a posição é um proxy binário de "está no
último dia", que só funciona para pão de um dia. A validade do lote vale para
qualquer prazo, e o percentual acompanha a razão real (grau da inspeção).

O elo que torna isto possível: cada ``Hold`` ancora em UM ``Quant``
(``holds.py``, "1:1 hold:quant by design") e ``Quant.batch`` guarda a
``Batch.ref`` — então a linha sabe de qual lote saiu.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def percent_for_lot(batch_ref: str, *, declared_percent: int = 0) -> int:
    """Desconto (0–100) do lote, arbitrando ``max(automatic, declared)``.

    ``automatic`` é o ``Batch.nonconformity_percent`` gravado no fechamento da
    fornada; ``declared`` é um desconto que o operador aprofundou à mão. O
    operador pode dar MAIS desconto, nunca menos do que a inspeção determinou —
    quem inspecionou viu o pão (ADR-017 §7).

    Lote desconhecido ou leitura degradada devolve o declarado: fail-safe para
    preço CHEIO quando não há motivo conhecido para descontar.
    """
    declared = _clamp(declared_percent)
    if not batch_ref:
        return declared
    try:
        from shopman.stockman.models import Batch

        automatic = (
            Batch.objects.filter(ref=batch_ref)
            .values_list("nonconformity_percent", flat=True)
            .first()
        )
    except Exception:
        logger.debug("lot_pricing.lookup_failed batch=%s", batch_ref, exc_info=True)
        return declared
    return max(declared, _clamp(automatic or 0))


def batch_ref_for_hold(hold_id) -> str:
    """A ``Batch.ref`` do lote que este hold reservou; "" quando não há lote.

    Hold flutuante (``quant=None``, venda antecipada/demanda) não tem lote — e
    não pode ter: o lote ainda não existe.
    """
    if not hold_id:
        return ""
    try:
        from shopman.stockman.models import Hold

        return (
            Hold.objects.filter(pk=hold_id)
            .values_list("quant__batch", flat=True)
            .first()
            or ""
        )
    except Exception:
        logger.debug("lot_pricing.hold_lookup_failed hold=%s", hold_id, exc_info=True)
        return ""


def lot_context(batch_ref: str) -> dict:
    """Rótulo e validade do lote, para transparência na linha e na vitrine."""
    if not batch_ref:
        return {}
    try:
        from shopman.stockman.models import Batch

        row = (
            Batch.objects.filter(ref=batch_ref)
            .values("nonconformity_percent", "nonconformity_reason", "expiry_date")
            .first()
        )
    except Exception:
        logger.debug("lot_pricing.context_failed batch=%s", batch_ref, exc_info=True)
        return {}
    if not row:
        return {}
    return {
        "batch_ref": batch_ref,
        "percent": _clamp(row["nonconformity_percent"] or 0),
        "reason": row["nonconformity_reason"] or "",
        "expiry_date": row["expiry_date"].isoformat() if row["expiry_date"] else "",
    }


def _clamp(value) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0
