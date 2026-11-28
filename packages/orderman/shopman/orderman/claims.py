"""Ficha de execução compartilhada pelos consumidores de diretivas."""
from __future__ import annotations

import logging
from datetime import datetime

from django.db import transaction
from shopman.orderman.models import Directive

logger = logging.getLogger(__name__)


def save_if_claimed(
    directive: Directive,
    attempts: int,
    started_at: datetime,
    fields: dict,
    *,
    only_if_running: bool = False,
) -> bool:
    """Grava o desfecho só se o claim ainda for deste worker (compare-and-set).

    Lê a linha sob ``select_for_update`` e confere a ficha ``(attempts,
    started_at)``: o reaper zera ``started_at`` e um novo claim incrementa
    ``attempts``, então qualquer um dos dois faz a ficha divergir. Divergiu, não
    escreve nada e devolve ``False``. Usa ``save()`` (não ``update()``) para manter
    os signals do modelo.
    """
    with transaction.atomic():
        current = Directive.objects.select_for_update().filter(pk=directive.pk).first()
        if current is None or (current.attempts != attempts or current.started_at != started_at):
            logger.warning(
                "Directive %s #%s: claim perdido (reaper ou outro worker); "
                "desfecho deste worker descartado",
                directive.topic, directive.pk,
            )
            return False
        if only_if_running and current.status != "running":
            fields = {k: v for k, v in fields.items() if k != "status"}
        for name, value in fields.items():
            setattr(current, name, value)
        current.save(update_fields=[*fields, "updated_at"])
    for name in ("status", "error_code", "last_error", "available_at", "attempts", "started_at"):
        setattr(directive, name, getattr(current, name))
    return True

