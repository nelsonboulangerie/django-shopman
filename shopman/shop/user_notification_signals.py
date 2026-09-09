"""Reconcilia representações pessoais quando a condição canônica muda."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from shopman.shop.models import Announcement
from shopman.shop.services.user_notifications import reconcile_announcement_review


@receiver(
    post_save,
    sender=Announcement,
    dispatch_uid="shopman.shop.user_notifications.reconcile_announcement",
)
def reconcile_announcement_notifications(sender, instance, created, update_fields=None, **kwargs):
    if created:
        return
    relevant = {"status", "expires_at", "version", "content", "platforms"}
    if update_fields is not None and relevant.isdisjoint(update_fields):
        return
    reconcile_announcement_review(instance)
