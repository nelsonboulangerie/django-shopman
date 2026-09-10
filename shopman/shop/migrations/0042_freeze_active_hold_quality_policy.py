"""Congela a política de QC nos holds ativos anteriores ao cutover.

Holds novos já carregam a versão e a allowlist do canal. Para os antigos, o
canal não mora no Stockman; esta migration só aceita as duas relações que o
identificam sem adivinhação: ``order:<ref>`` ou a chave de uma Session. Holds
de insumo de WorkOrder são locais e irrestritos. Qualquer outro dono ativo
interrompe o deploy para resolução explícita.
"""

from django.conf import settings
from django.db import migrations
from django.db.models import Q
from django.utils import timezone

VERSION_KEY = "_quality_grade_policy_version"
ALLOWLIST_KEY = "_allowed_quality_grade_refs"
BACKFILL_MARKER = "_quality_grade_policy_backfill"
POLICY_VERSION = 1
REMOTE_ALLOWLIST = ["excellent", "standard"]
ACTIVE_HOLD_STATUSES = ("pending", "confirmed")


def _live_holds(Hold):
    now = timezone.now()
    return Hold.objects.filter(status__in=ACTIVE_HOLD_STATUSES).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=now)
    )


def _channel_for_hold(hold, Order, Session) -> str:
    metadata = dict(hold.metadata or {})
    if metadata.get("purpose") == "workorder":
        return "__workorder__"

    reference = str(metadata.get("reference") or "")
    if reference.startswith("order:"):
        return str(
            Order.objects.filter(ref=reference.removeprefix("order:"))
            .values_list("channel_ref", flat=True)
            .first()
            or ""
        )
    if reference:
        return str(
            Session.objects.filter(session_key=reference)
            .values_list("channel_ref", flat=True)
            .first()
            or ""
        )
    return ""


def _allows_all_grades(channel_ref: str, Channel) -> bool:
    local_refs = {
        "pdv",
        "pos",
        str(getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv") or "pdv"),
    }
    if channel_ref not in local_refs:
        return False
    config = (
        Channel.objects.filter(ref=channel_ref)
        .values_list("config", flat=True)
        .first()
        or {}
    )
    stock = config.get("stock") if isinstance(config, dict) else {}
    return bool(isinstance(stock, dict) and stock.get("sells_nonconforming"))


def forwards(apps, schema_editor):
    Hold = apps.get_model("stockman", "Hold")
    Order = apps.get_model("orderman", "Order")
    Session = apps.get_model("orderman", "Session")
    Channel = apps.get_model("shop", "Channel")

    unresolved = []
    updates = []
    queryset = _live_holds(Hold).order_by("pk")
    for hold in queryset.iterator():
        metadata = dict(hold.metadata or {})
        if metadata.get(VERSION_KEY) == POLICY_VERSION:
            continue
        channel_ref = _channel_for_hold(hold, Order, Session)
        if not channel_ref:
            unresolved.append(hold.pk)
            continue

        metadata[VERSION_KEY] = POLICY_VERSION
        metadata[BACKFILL_MARKER] = "shop.0042"
        if channel_ref == "__workorder__" or _allows_all_grades(channel_ref, Channel):
            metadata.pop(ALLOWLIST_KEY, None)
        else:
            metadata[ALLOWLIST_KEY] = list(REMOTE_ALLOWLIST)
        hold.metadata = metadata
        updates.append(hold)

    if unresolved:
        sample = ", ".join(str(pk) for pk in unresolved[:10])
        raise RuntimeError(
            "Holds ativos sem canal identificável impedem o cutover da política "
            f"de QC (ids: {sample}). Resolva-os antes de publicar."
        )
    if updates:
        Hold.objects.bulk_update(updates, ["metadata"])


def backwards(apps, schema_editor):
    Hold = apps.get_model("stockman", "Hold")
    updates = []
    for hold in _live_holds(Hold).iterator():
        metadata = dict(hold.metadata or {})
        if metadata.get(BACKFILL_MARKER) != "shop.0042":
            continue
        metadata.pop(VERSION_KEY, None)
        metadata.pop(ALLOWLIST_KEY, None)
        metadata.pop(BACKFILL_MARKER, None)
        hold.metadata = metadata
        updates.append(hold)
    if updates:
        Hold.objects.bulk_update(updates, ["metadata"])


class Migration(migrations.Migration):
    dependencies = [
        ("orderman", "0004_alter_sessionitem_sku"),
        ("shop", "0041_enable_remote_waitlist_notifications"),
        ("stockman", "0003_batch_quality_grade_ref"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
