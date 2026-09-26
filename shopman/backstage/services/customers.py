"""Unificar e desfazer cadastros a partir do Gestor.

O trabalho inteiro é do ``MergeService`` do Guestman — prévia, ida e volta.
Aqui só se traduz o pedido do Gestor (dois ``ref``) e a recusa do Core, que é
de engenharia e em inglês, para a frase que o gestor lê.

A evidência do gate G6 é ``staff_override``: quem unifica é um gestor
autenticado, com ``shop.manage_customers``, que viu a prévia lado a lado e
confirmou. A evidência viaja assinada com quem disse e de onde.
"""

from __future__ import annotations

import logging

from django.db import transaction

from shopman.backstage.services.exceptions import CustomerMergeError, CustomerNotFound

logger = logging.getLogger(__name__)

_EVIDENCE = {
    "staff_override": True,
    "operator_confirmed": True,
    "source_surface": "gestor",
}


def _pair(source_ref: str, target_ref: str, *, lock: bool = False):
    from shopman.guestman.models import Customer

    source_ref = (source_ref or "").strip()
    target_ref = (target_ref or "").strip()
    if not source_ref or not target_ref:
        raise CustomerMergeError("Escolha os dois cadastros: o que sai e o que fica.")
    if source_ref == target_ref:
        raise CustomerMergeError("Os dois lados são o mesmo cadastro.")

    qs = Customer.objects.filter(ref__in=(source_ref, target_ref))
    if lock:
        # Linhas de Customer antes de qualquer filho que o merge mova, em ordem
        # estável — duas unificações invertidas não se travam.
        qs = qs.select_for_update().order_by("pk")
    by_ref = {customer.ref: customer for customer in qs}
    source, target = by_ref.get(source_ref), by_ref.get(target_ref)
    if source is None or target is None:
        missing = source_ref if source is None else target_ref
        raise CustomerNotFound(f"O cadastro {missing} não existe mais. Recarregue a lista.")
    if not source.is_active:
        raise CustomerMergeError(
            f"{source.ref} já foi unificado a outro cadastro. Abra a ficha dele para ver para onde foi."
        )
    if not target.is_active:
        raise CustomerMergeError(
            f"{target.ref} já foi unificado a outro cadastro e não pode receber este. "
            "Escolha o cadastro que ficou."
        )
    return source, target


def _translate(exc: Exception) -> CustomerMergeError:
    logger.warning("gestor_customer_merge_denied error=%s", exc, exc_info=True)
    return CustomerMergeError("Não foi possível unificar os cadastros. Recarregue e tente de novo.")


def preview_merge(*, source_ref: str, target_ref: str):
    """``(source, target, MergePreview)`` — nada é gravado."""
    from shopman.guestman.contrib.merge.service import MergeService
    from shopman.guestman.exceptions import CustomerError
    from shopman.guestman.gates import GateError

    source, target = _pair(source_ref, target_ref)
    try:
        preview = MergeService.preview(source, target, evidence=_EVIDENCE)
    except (GateError, CustomerError) as exc:
        raise _translate(exc) from exc
    return source, target, preview


def merge_customers(*, source_ref: str, target_ref: str, actor: str):
    """Unifica: ``source`` sai (fica desativado), ``target`` fica com tudo."""
    from shopman.guestman.contrib.merge.service import MergeService
    from shopman.guestman.exceptions import CustomerError
    from shopman.guestman.gates import GateError

    try:
        with transaction.atomic():
            source, target = _pair(source_ref, target_ref, lock=True)
            result = MergeService.merge(source, target, evidence=_EVIDENCE, actor=actor or "gestor")
    except (GateError, CustomerError) as exc:
        raise _translate(exc) from exc

    logger.info(
        "gestor_customer_merged source=%s target=%s actor=%s audit=%s",
        result.source_ref,
        result.target_ref,
        actor,
        result.audit_id,
    )
    return result


def undo_merge(*, audit_id: str, actor: str) -> None:
    """Desfaz dentro da janela. A recusa diz qual dos três casos aconteceu."""
    from django.core.exceptions import ValidationError
    from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus
    from shopman.guestman.contrib.merge.service import MergeService
    from shopman.guestman.exceptions import CustomerError

    try:
        audit = MergeAudit.objects.filter(pk=audit_id).first()
    except (ValueError, ValidationError):
        audit = None
    if audit is None:
        raise CustomerNotFound("Esta unificação não está mais no sistema. Recarregue a lista.")
    if audit.status != MergeStatus.COMPLETED:
        who = f" por {audit.reverted_by}" if audit.reverted_by else ""
        raise CustomerMergeError(f"Esta unificação já foi desfeita{who}.")
    if not audit.can_undo:
        raise CustomerMergeError(
            f"O prazo de {MergeAudit.UNDO_WINDOW_HOURS} horas para desfazer terminou. "
            f"Daqui em diante a separação é manual: cadastre {audit.source_ref} de novo e mova o que for dele."
        )
    try:
        MergeService.undo(str(audit.pk), actor=actor or "gestor")
    except CustomerError as exc:
        logger.warning("gestor_customer_undo_denied audit=%s error=%s", audit.pk, exc, exc_info=True)
        raise CustomerMergeError(
            "Não foi possível desfazer: um dos dois cadastros mudou desde a unificação. "
            "Confira as fichas antes de tentar de novo."
        ) from exc
    logger.info("gestor_customer_merge_undone audit=%s actor=%s", audit.pk, actor)
