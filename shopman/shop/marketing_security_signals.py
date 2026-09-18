"""Invalidate open Marketing authorizations whenever Django RBAC changes.

Aqui mora também a invalidação da base de clientes cacheada: o limiar de cerimônia é uma
proporção dela, e um limiar calculado sobre uma base velha empurra a decisão "pede senha
ou não" para o lado errado sem ninguém ver.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import OperationalError, ProgrammingError, transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(
    m2m_changed,
    sender=User.user_permissions.through,
    dispatch_uid="shop.marketing_security.user_permissions",
)
@receiver(
    m2m_changed,
    sender=User.groups.through,
    dispatch_uid="shop.marketing_security.user_groups",
)
@receiver(
    m2m_changed,
    sender=Group.permissions.through,
    dispatch_uid="shop.marketing_security.group_permissions",
)
def invalidate_marketing_authorizations(sender, action, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    def bump() -> None:
        try:
            from shopman.shop.services.marketing_security import (
                bump_authority_generation,
            )

            bump_authority_generation()
        except (OperationalError, ProgrammingError):
            # The auth tables can be populated while this app's newest migration
            # is not present yet.  Runtime edits after migration remain covered.
            logger.debug("Marketing authorization generation table is not ready yet.")

    transaction.on_commit(bump)


@receiver(
    post_save,
    sender="guestman.Customer",
    dispatch_uid="shop.marketing_ceremony.customer_saved",
)
@receiver(
    post_delete,
    sender="guestman.Customer",
    dispatch_uid="shop.marketing_ceremony.customer_deleted",
)
def invalidate_marketing_customer_base(sender, **kwargs):
    """Cadastro mexeu, contagem cacheada morre.

    O cache da base dura 60 segundos só para que a projeção do cockpit — que resolve
    seis ações por anúncio — não faça um ``COUNT`` por ação. A invalidação verdadeira é
    esta: um cliente novo, uma anonimização ou uma exclusão refaz a conta no ato. Sem
    isso, o cache curto seria uma janela em que o limiar mente, e cache de regra que
    mente já custou caro nesta casa.
    """
    from shopman.shop.services.marketing_ceremony import invalidate_customer_base_size

    invalidate_customer_base_size()
