"""Arquivamento de fornecedores em lote, com revisão, recibo e auditoria."""

from datetime import timedelta

from django.apps import apps
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.db import transaction
from django.utils import timezone

from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services.purchase import PurchaseError

SALT = "purchase.supplier-bulk.v1"


@transaction.atomic
def set_supplier_archive(data, *, user):
    Supplier = apps.get_model("buyman", "Supplier")
    undo = bool(data.get("undo"))
    if undo:
        try:
            receipt = signing.loads(data["undo"], salt=SALT, max_age=15)
            if receipt["actor"] != user.pk:
                raise signing.BadSignature()
            entries = receipt["rows"]
        except (signing.BadSignature, KeyError, TypeError):
            raise PurchaseError(
                "O prazo para desfazer terminou. Atualize a lista.", code="undo_expired", status_code=409
            ) from None
    else:
        entries = data.get("rows")
        if not isinstance(data.get("isActive"), bool):
            raise PurchaseError("Escolha Arquivar ou Desarquivar.", code="active_invalid", field="isActive")
    if not isinstance(entries, list) or not entries or len(entries) > 100:
        raise PurchaseError("Marque de 1 a 100 fornecedores.", code="selection_invalid", field="rows")
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("ref"), str)
        or not row.get("ref")
        or not isinstance(row.get("revision"), str)
        or not row.get("revision")
        for row in entries
    ):
        raise PurchaseError(
            "Atualize a lista antes de alterar os fornecedores.", code="revision_required", field="rows"
        )
    refs = [row["ref"] for row in entries]
    if len(set(refs)) != len(refs):
        raise PurchaseError("Cada fornecedor entra uma vez no lote.", code="selection_invalid", field="rows")
    suppliers = list(Supplier.objects.select_for_update().filter(ref__in=refs).order_by("pk"))
    expected = {row["ref"]: row for row in entries}
    if len(suppliers) != len(entries) or any(
        row.updated_at.isoformat() != expected[row.ref]["revision"] for row in suppliers
    ):
        raise PurchaseError(
            "Alguém mudou os fornecedores enquanto você escolhia. Atualize e confira o lote.",
            code="catalog_changed",
            status_code=409,
        )
    now = timezone.now()
    previous = []
    audit = []
    content_type = ContentType.objects.get_for_model(Supplier)
    for row in suppliers:
        previous.append({"ref": row.ref, "revision": now.isoformat(), "isActive": row.is_active})
        active = expected[row.ref]["isActive"] if undo else data["isActive"]
        audit.append(
            LogEntry(
                user_id=user.pk,
                content_type_id=content_type.pk,
                object_id=str(row.pk),
                object_repr=str(row)[:200],
                action_flag=CHANGE,
                change_message=f"{'Desfazer: ' if undo else ''}{'Desarquivar' if active else 'Arquivar'} fornecedor (lote)",
            )
        )
        row.is_active = active
        row.updated_at = now
    Supplier.objects.bulk_update(suppliers, ["is_active", "updated_at"])
    LogEntry.objects.bulk_create(audit)
    resource = {"kind": "supplier-bulk", "count": len(suppliers)}
    if not undo:
        resource.update(
            undo=signing.dumps({"actor": user.pk, "rows": previous}, salt=SALT),
            until=(now + timedelta(seconds=15)).isoformat(),
            serverNow=now.isoformat(),
        )
    noun = "fornecedor" if len(suppliers) == 1 else "fornecedores"
    status = ("desarquivado" if data.get("isActive") else "arquivado") + ("" if len(suppliers) == 1 else "s")
    return (
        build_purchase(),
        "Alteração desfeita." if undo else f"{len(suppliers)} {noun} {status}.",
        resource,
    )
