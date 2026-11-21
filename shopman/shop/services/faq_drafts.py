"""Rascunhos de pergunta frequente esperando publicação viram aviso no topo do Gestor.

A resposta que a equipe dá a um "vou verificar" pode virar rascunho de pergunta frequente
(WP-15). Sem aviso, o rascunho dormia no Admin para sempre (o dono: "o gestor é avisado?").
Um aviso só, com a contagem; some quando não sobra rascunho. Conta só o que nasceu de
conversa (``concierge_verification.origin_of``): o rascunho escrito no Admin já tem quem o
cuide.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

ALERT_TYPE = "faq_drafts_waiting"
DEDUPE_KEY = "faq:drafts"


def waiting() -> list:
    """Os rascunhos promovidos de conversa que ainda não foram publicados."""
    from shopman.shop.concierge_verification import origin_of
    from shopman.shop.models import FAQEntry

    return [
        entry for entry in FAQEntry.objects.filter(is_published=False).only("pk", "ref").order_by("pk")
        if origin_of(entry.ref)
    ]


def alert_message(count: int) -> str:
    if count == 1:
        return "1 pergunta frequente espera publicação."
    return f"{count} perguntas frequentes esperam publicação."


def sync_alert() -> None:
    """Abre, atualiza ou resolve o aviso pela contagem de agora. Nunca levanta."""
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services.observability import create_operator_alert

    try:
        count = len(waiting())
        open_pk = alert_adapter.open_pk(ALERT_TYPE)
        if count == 0:
            if open_pk is not None:
                alert_adapter.resolve_pk(open_pk, actor="faq")
            return
        message = alert_message(count)
        if open_pk is not None:
            alert_adapter.revise(open_pk, message=message)
            return
        create_operator_alert(
            type=ALERT_TYPE, severity="warning", message=message, dedupe_key=DEDUPE_KEY,
            debounce_minutes=0, stamp_dedupe=False,
        )
    except Exception:
        logger.warning("faq_drafts.alert_failed", exc_info=True)


def on_faq_changed(sender, **kwargs) -> None:
    sync_alert()


def connect() -> None:
    from django.db.models.signals import post_delete, post_save

    from shopman.shop.models import FAQEntry

    post_save.connect(on_faq_changed, sender=FAQEntry, weak=False, dispatch_uid="shopman.faq_drafts.saved")
    post_delete.connect(on_faq_changed, sender=FAQEntry, weak=False, dispatch_uid="shopman.faq_drafts.deleted")
