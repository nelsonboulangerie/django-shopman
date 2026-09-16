"""Importação de evidência e decisão humana local; nenhum envio de catálogo."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.db import IntegrityError, transaction
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.models import CatalogBinding, CatalogSnapshot, Channel
from shopman.shop.services.ifood_catalog_review import build_ifood_catalog_review, validate_review_snapshot
from shopman.shop.services.remote_mutations import mutation_fingerprint

MAX_SNAPSHOT_BYTES = 20 * 1024 * 1024


class CatalogBindingError(ValueError):
    """Entrada inválida para revisão ou vínculo local."""


class CatalogBindingConflict(CatalogBindingError):
    """A evidência ou decisão atual difere da revisão apresentada."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Chave repetida.")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Número não finito.")


def parse_snapshot(raw_json):
    """Conserva o texto original e números decimais sem coerção de códigos."""
    if not isinstance(raw_json, str):
        raise CatalogBindingError("Informe raw_json como texto JSON original.")
    try:
        raw = raw_json.encode("utf-8")
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise ValueError
        snapshot = json.loads(raw_json, parse_float=Decimal, parse_constant=_constant, object_pairs_hook=_pairs)
        validate_review_snapshot(snapshot)
        for key in ("merchant_id", "catalog_id", "context"):
            if len(snapshot[key]) > 128:
                raise ValueError
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CatalogBindingError("Snapshot inválido, incompleto ou acima de 20 MiB.") from None
    return snapshot, hashlib.sha256(raw).hexdigest()


def _authorized(actor):
    if not actor or not actor.is_active or not actor.is_staff or not actor.has_perm("shop.manage_catalog"):
        raise CatalogBindingError("Identifique uma pessoa com permissão para editar o catálogo.")


def _channel(ref, *, lock=False):
    query = Channel.objects.select_for_update() if lock else Channel.objects
    channel = query.filter(ref=ref).first()
    if channel is None:
        raise CatalogBindingError("Canal não encontrado.")
    return channel


def import_revision(channel, actor):
    return mutation_fingerprint({"version": 1, "operation": "catalog.snapshot.import",
                                 "channel_id": channel.pk, "channel_ref": channel.ref, "actor_id": actor.pk})


def scope(snapshot):
    return {"provider": snapshot.provider, "account_ref": snapshot.account_ref,
            "catalog_ref": snapshot.catalog_ref, "context": snapshot.context}


def binding_revision(snapshot, item_id, binding):
    return mutation_fingerprint({"version": 1, "snapshot_id": snapshot.pk, "sha256": snapshot.sha256,
        "channel_id": snapshot.channel_id, "scope": scope(snapshot), "item_id": item_id,
        "binding": None if binding is None else {"id": binding.pk, "revision": binding.revision,
            "channel_id": binding.channel_id, "product_id": binding.product_id,
            "snapshot_id": binding.snapshot_id}})


def review_rows(snapshot, products):
    parsed, digest = parse_snapshot(snapshot.raw_json)
    if digest != snapshot.sha256 or any(parsed[key] != getattr(snapshot, field)
        for key, field in (("merchant_id", "account_ref"), ("catalog_id", "catalog_ref"), ("context", "context"))):
        raise CatalogBindingError("A evidência armazenada diverge do escopo ou do hash.")
    result = build_ifood_catalog_review(snapshot=parsed, products=products,
        local_details={product.sku: {"sku": product.sku, "name": product.name} for product in products})
    return result["items"]


def item_context_ref(row):
    effective = row["remote"]["effective_context"] or {}
    value = effective.get("itemContextId")
    return "" if value is None else value


def binding_block(row):
    identity = row["identity"]
    if identity["status"] in {"invalid_identity", "invalid_context", "duplicate_identity"}:
        return "Identidade ou contexto remoto inválido; importe uma evidência consistente."
    refs = [identity["item_id"], identity["product_id"], identity["category_id"]]
    if any(not isinstance(value, str) or not value.strip() or len(value) > 256 for value in refs):
        return "Identidade remota fora do formato aceito."
    context_ref = item_context_ref(row)
    if not isinstance(context_ref, str) or len(context_ref) > 256:
        return "Identificador do contexto remoto inválido."
    return ""


@transaction.atomic
def import_snapshot(*, channel_ref, raw_json, actor, expected_revision=None):
    _authorized(actor)
    parsed, digest = parse_snapshot(raw_json)
    channel = _channel(channel_ref, lock=True)
    if expected_revision is not None and expected_revision != import_revision(channel, actor):
        raise CatalogBindingConflict("O canal ou a identificação mudou. Atualize antes de importar.")
    snapshot = CatalogSnapshot.objects.create(channel=channel, provider="ifood",
        account_ref=parsed["merchant_id"], catalog_ref=parsed["catalog_id"], context=parsed["context"],
        captured_at=datetime.fromisoformat(parsed["captured_at"].replace("Z", "+00:00")),
        imported_by=actor, sha256=digest, raw_json=raw_json, source=parsed["source"],
        item_count=sum(len(category["items"]) for category in parsed["categories"]))
    LogEntry.objects.log_actions(user_id=actor.pk, queryset=[snapshot], action_flag=ADDITION,
        change_message=json.dumps({"action": "catalog.snapshot.import", "channel_ref": channel_ref,
                                   "snapshot_id": snapshot.pk, "sha256": digest}))
    return snapshot


@transaction.atomic
def bind_item(*, channel_ref, snapshot_id, item_id, sku, base_revision, actor):
    _authorized(actor)
    if any(not isinstance(value, str) or not value.strip() for value in (item_id, sku, base_revision)):
        raise CatalogBindingError("Item, SKU e revisão são obrigatórios.")
    if type(snapshot_id) is not int or snapshot_id < 1:
        raise CatalogBindingError("Snapshot inválido.")
    channel = _channel(channel_ref, lock=True)
    product = Product.objects.select_for_update().filter(sku=sku).first()
    if product is None:
        raise CatalogBindingError("Produto canônico não encontrado.")
    snapshot = CatalogSnapshot.objects.select_for_update().filter(pk=snapshot_id, channel=channel).first()
    if snapshot is None:
        raise CatalogBindingError("Snapshot não pertence ao canal selecionado.")
    if snapshot.provider != "ifood":
        raise CatalogBindingError("Não há parser de revisão para este provedor.")
    rows = review_rows(snapshot, [product])
    row = next((row for row in rows if row["identity"]["item_id"] == item_id), None)
    if row is None:
        raise CatalogBindingError("Item não pertence ao snapshot selecionado.")
    reason = binding_block(row)
    if reason:
        raise CatalogBindingError(reason)
    binding = CatalogBinding.objects.select_for_update().filter(**scope(snapshot), resource_id=item_id).first()
    if binding is not None and binding.channel_id != channel.pk:
        raise CatalogBindingConflict("Este recurso já está vinculado em outro canal; confira o escopo.")
    if not isinstance(base_revision, str) or binding_revision(snapshot, item_id, binding) != base_revision:
        raise CatalogBindingConflict("O vínculo mudou. Atualize a revisão antes de confirmar sua escolha.")
    before = None if binding is None else {"sku": binding.product.sku, "revision": binding.revision,
                                          "snapshot_id": binding.snapshot_id}
    if binding is None:
        binding = CatalogBinding(channel=channel, **scope(snapshot), resource_id=item_id)
    else:
        binding.revision += 1
    binding.product = product
    binding.external_product_ref = row["identity"]["product_id"]
    binding.category_ref = row["identity"]["category_id"]
    binding.item_context_ref = item_context_ref(row)
    binding.snapshot = snapshot
    binding.confirmed_by = actor
    binding.confirmed_at = timezone.now()
    try:
        with transaction.atomic():
            binding.save()
    except IntegrityError:
        raise CatalogBindingConflict("Outro operador confirmou este recurso. Atualize a revisão.") from None
    LogEntry.objects.log_actions(user_id=actor.pk, queryset=[binding], action_flag=CHANGE if before else ADDITION,
        change_message=json.dumps({"action": "catalog.binding.confirm", "channel_ref": channel_ref,
            "resource_id": item_id, "before": before, "after": {"sku": sku, "revision": binding.revision,
                                                                  "snapshot_id": snapshot.pk}}))
    return binding, binding_revision(snapshot, item_id, binding)
