"""Uma pergunta só: *esta pessoa consegue abrir esta tela do Admin?*

O menu e os cards do dashboard existem para levar alguém a uma tela. Se a
resposta deles diverge da resposta da tela, o link vira porta trancada com placa
de aberto — e a divergência não avisa: ela aparece como um 403 na cara de quem
clicou, meses depois de alguém ter mexido só de um lado.

Então nem o menu nem o dashboard repetem a regra: os dois perguntam à própria
porta. Para uma changelist, a porta é o ``ModelAdmin`` (é o
``has_view_or_change_permission`` dele que levanta ``PermissionDenied``); para
uma tela custom, é o ``permission_required`` da própria view.
"""

from __future__ import annotations

import logging

from django.contrib import admin
from django.contrib.admin.exceptions import NotRegistered

logger = logging.getLogger(__name__)


def can_open_changelist(request, model) -> bool:
    """A changelist deste model abriria para este request?"""
    try:
        model_admin = admin.site.get_model_admin(model)
    except NotRegistered:
        logger.warning("admin_gate_model_nao_registrada", extra={"model": model._meta.label})
        return False
    return model_admin.has_view_or_change_permission(request)


def can_open_view(request, view) -> bool:
    """Idem para tela custom do Admin: a permissão é a que a view declara."""
    required = view.permission_required
    required = (required,) if isinstance(required, str) else tuple(required)
    return request.user.has_perms(required)
