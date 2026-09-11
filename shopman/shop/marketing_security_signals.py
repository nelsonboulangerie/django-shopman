"""Invalidate open Marketing authorizations whenever Django RBAC changes."""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import OperationalError, ProgrammingError, transaction
from django.db.models.signals import m2m_changed
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
