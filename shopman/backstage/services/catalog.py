"""
Catalog mutation facade — pausa/publica/preço por superfície + bulk.

Estratégia de projeção (ponte da Frente 1):
- **Célula única** → ``ListingItem.save()``: emite ``availability_changed`` /
  ``price_changed``; o auto-trigger enfileira a projeção só para superfícies com
  backend na registry canônica (as demais são no-op). Preserva history.
- **Bulk** (scoped a coleção/superfície/seleção) → ``queryset.update()`` (rápido,
  consistente com as bulk actions do admin) **+ reconciliação única** via
  ``CatalogService.project_listing`` quando a superfície é alvo de projeção
  (retract-aware, um reconcile em vez de N directives).

Escreve direto nos models do offerman (como as projections do backstage já leem).
Superfície = Channel; célula = ListingItem da listing de mesmo ref.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from math import isfinite

from django.db import transaction

from shopman.backstage.services.exceptions import CatalogError
from shopman.shop.services import attributes

logger = logging.getLogger(__name__)


def _reconcile_if_projected(surface_ref: str) -> None:
    """Reconcilia a superfície (retract-aware) só se ela tem backend de projeção."""
    from shopman.offerman.conf import get_projection_backend

    if get_projection_backend(surface_ref) is None:
        return
    from shopman.offerman.exceptions import CatalogError as OffermanCatalogError
    from shopman.offerman.service import CatalogService

    try:
        CatalogService.project_listing(surface_ref)
    except OffermanCatalogError as exc:
        # Reconciliação é best-effort: a mutação no DB já valeu; a projeção externa
        # é retentada pelo auto-trigger/comando. Não derruba a operação do operador.
        raise CatalogError(f"Mudança aplicada, mas a sincronização falhou: {exc}") from exc


def _notify_surface(surface_ref: str) -> None:
    """Empurra o evento SSE da superfície (bulk não dispara post_save → menuboard)."""
    from shopman.shop.handlers._sse_emitters import emit_surface_changed

    emit_surface_changed(surface_ref)


# Sentinela "todos os canais" para as ações em lote (barra flutuante).
ALL_SURFACES = "*"


def _all_channel_refs() -> list[str]:
    from shopman.shop.models import Channel

    # O fan-out de "todos os canais" escreve preço e publicação — coisas que canal
    # `display` não tem. Seleção por política (ADR-018 §8). Canal cuja vitrine
    # espelha outra (``pricing.listing_from``) fica de fora: ele acompanha a fonte.
    from shopman.shop.services import listing_mirror

    return [
        ref
        for ref, config in Channel.objects.filter(
            is_active=True, commerce_policy=Channel.CommercePolicy.ORDER
        )
        .order_by("display_order", "id")
        .values_list("ref", "config")
        if not listing_mirror.source_ref_from_config(config)
    ]


def _refuse_mirror_surface(surface_ref: str) -> None:
    """Vitrine espelhada não tem edição própria: a mudança é feita na fonte."""
    from shopman.shop.models import Channel
    from shopman.shop.services import listing_mirror

    source = listing_mirror.source_ref(surface_ref)
    if not source:
        return
    names = dict(Channel.objects.filter(ref__in=[surface_ref, source]).values_list("ref", "name"))
    raise CatalogError(
        f"A vitrine de {names.get(surface_ref, surface_ref)} segue a de "
        f"{names.get(source, source)}. Altere o produto lá."
    )


def _realign_mirrors(refs) -> None:
    """Escrita em lote não dispara signal: o espelho da superfície acompanha aqui."""
    from shopman.shop.services import listing_mirror

    for ref in sorted(set(refs)):
        listing_mirror.realign(ref)


def _is_display_surface(surface_ref: str) -> bool:
    """A superfície EXIBE sem transacionar (TV, feed) e não vende?

    A pergunta é sobre POLÍTICA COMERCIAL, não sobre qual tabela guarda a linha —
    é o que a ADR-018 conseguiu ao absorver o `Feed`: a mesma tabela, e o que
    distingue é `commerce_policy`. Uma célula de exibição não tem preço para
    escrever, então pausar ali grava em `display.paused_skus`, não num ListingItem.
    """
    from shopman.shop.models import Channel

    return Channel.objects.filter(
        ref=surface_ref, commerce_policy=Channel.CommercePolicy.DISPLAY
    ).exists()


def cell_field_revisions(sku: str, surface_ref: str, *, item=None, display=None, missing=False, unit="") -> dict[str, str]:
    """A cell's relevant canonical target and independent field values."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    if display is not None:
        config = (display.config or {}).get("display") or {}
        context = {"display_id": display.pk, "collections": config.get("collections") or []}
        values = {"is_sellable": sku not in (config.get("paused_skus") or [])}
    elif item is not None:
        context = {"item_id": item.pk, "product_id": item.product_id, "listing_id": item.listing_id, "tier": str(item.min_qty), "unit": item.product.unit}
        values = {field: getattr(item, field) for field in ("is_published", "is_sellable", "price_q", "min_qty")}
    elif missing:
        context = {"membership": "absent", "unit": unit}
        values = dict.fromkeys(("is_published", "is_sellable", "price_q", "min_qty"))
    else:
        return {}
    return {field: mutation_fingerprint({"version": 1, "sku": sku, "surface": surface_ref, "target": context, "field": field, "value": str(value) if field == "min_qty" else value})
        for field, value in values.items()}


def _check_cell_revisions(patch: dict, current: dict, expected: dict | None, values: dict):
    from shopman.backstage.services.exceptions import CatalogConflict

    if expected is None:
        return
    changed = [field for field in patch if expected.get(field) != current.get(field)]
    if changed:
        error = CatalogConflict("A célula mudou nos campos editados. Confira os valores atuais; sua edição foi mantida.")
        error.current = values
        error.fields = changed
        raise error


@transaction.atomic
def set_cell(
    sku: str,
    surface_ref: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    price_q: int | None = None,
    min_qty: str | None = None,
    actor: str = "",
    expected_revisions: dict | None = None,
):
    """Merge one cell under Channel → Product → Listing → ListingItem locks."""
    from shopman.offerman.models import Collection, Listing, ListingItem, Product

    from shopman.shop.models import Channel

    patch = {}
    if is_published is not None:
        patch["is_published"] = _as_flag(is_published, "is_published")
    if is_sellable is not None:
        patch["is_sellable"] = _as_flag(is_sellable, "is_sellable")
    if price_q is not None:
        patch["price_q"] = _as_nullable_int(price_q, "price_q")
        if patch["price_q"] is None or patch["price_q"] < 0:
            raise CatalogError("Preço não pode ser negativo.")
    if min_qty is not None:
        from decimal import Decimal, InvalidOperation

        try:
            quantity = Decimal(str(min_qty))
            if not quantity.is_finite() or quantity <= 0 or quantity >= Decimal("10000000") or quantity.as_tuple().exponent < -3:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            raise CatalogError("A quantidade mínima deve ser positiva, com até três casas decimais.") from None
        patch["min_qty"] = quantity
    if not patch:
        raise CatalogError("Informe o campo que deseja alterar na célula.")
    channel = Channel.objects.select_for_update().filter(ref=surface_ref).first()
    groups = []
    if channel is not None and channel.commerce_policy == Channel.CommercePolicy.DISPLAY and expected_revisions is not None:
        refs = ((channel.config or {}).get("display") or {}).get("collections") or []
        groups = list(Collection.objects.select_for_update().filter(ref__in=refs).order_by("pk"))
    product = Product.objects.select_for_update().filter(sku=sku).first()
    if channel is None or product is None:
        raise CatalogError("O produto ou a superfície não foi encontrado.")
    if channel.commerce_policy == Channel.CommercePolicy.DISPLAY:
        from types import SimpleNamespace

        from shopman.backstage.services import feeds as display_service

        if set(patch) != {"is_sellable"}:
            raise CatalogError("Feed aceita apenas pausar/ativar (is_sellable).")
        if expected_revisions is not None and not any(group.product_queryset().filter(pk=product.pk).exists() for group in groups):
            from shopman.backstage.services.exceptions import CatalogConflict

            raise CatalogConflict("O produto não pertence mais ao recorte desta superfície. Atualize o catálogo.")
        _check_cell_revisions(patch, cell_field_revisions(sku, surface_ref, display=channel), expected_revisions,
            {"is_sellable": sku not in (((channel.config or {}).get("display") or {}).get("paused_skus") or [])})
        display_service.set_item_paused(surface_ref, sku, paused=not patch["is_sellable"])
        return SimpleNamespace(is_published=True, is_sellable=patch["is_sellable"], price_q=None)
    _refuse_mirror_surface(surface_ref)
    listing = Listing.objects.select_for_update().filter(ref=surface_ref).first()
    item = ListingItem.objects.select_for_update().filter(listing=listing, product=product).order_by("min_qty", "pk").first()
    creating = item is None
    if creating:
        if expected_revisions is None:
            raise CatalogError("Atualize o canal antes de incluir o produto.")
        _check_cell_revisions(patch, cell_field_revisions(sku, surface_ref, missing=True, unit=product.unit), expected_revisions, {})
        if listing is None:
            listing = Listing.objects.create(ref=surface_ref, name=channel.name)
        item = ListingItem(listing=listing, product=product, price_q=product.base_price_q,
            is_published=False, is_sellable=False)
    item.product, item.listing = product, listing
    _check_cell_revisions(patch, cell_field_revisions(sku, surface_ref, missing=True, unit=product.unit) if creating else cell_field_revisions(sku, surface_ref, item=item), expected_revisions,
        {field: str(getattr(item, field)) if field == "min_qty" else getattr(item, field) for field in ("price_q", "is_published", "is_sellable", "min_qty")})
    if "min_qty" in patch and ListingItem.objects.filter(listing=listing, product=product, min_qty=patch["min_qty"]).exclude(pk=item.pk).exists():
        raise CatalogError("Já existe um preço para esta quantidade mínima no canal.")
    old_min_qty = item.min_qty
    for field, value in patch.items():
        setattr(item, field, value)
    # Preserve the canonical save/history/signals, limiting the write to the patch.
    item.save(**({} if creating else {"update_fields": list(patch)}))
    if creating or item.min_qty != old_min_qty:
        from shopman.offerman.conf import get_projection_backend

        from shopman.shop.handlers.catalog_projection import enqueue_project

        _realign_mirrors([surface_ref])

        if get_projection_backend(surface_ref) is not None:
            enqueue_project(sku, surface_ref, trigger="manual_resync")
    return item


#: Teto de células por lote — o mesmo envelope das outras mutações em lote.
MAX_CATALOG_BATCH = 200


@transaction.atomic
def set_cells(cells: list[dict], *, actor: str = "") -> dict:
    """Aplica VÁRIAS células numa única ida, com conflito POR LINHA.

    Cada célula passa pelo MESMO ``set_cell`` (um ``save()`` por item, com sinais
    e histórico preservados), então a falha de uma linha não derruba as outras:
    quem colou a planilha recebe o recibo linha a linha. A intenção e o recibo
    da requisição são da camada HTTP.
    """
    from django.core.exceptions import ValidationError

    from shopman.backstage.services.exceptions import CatalogConflict

    if not isinstance(cells, list) or not cells:
        raise CatalogError("Informe as células do lote.")
    if len(cells) > MAX_CATALOG_BATCH:
        raise CatalogError(f"Envie no máximo {MAX_CATALOG_BATCH} células por lote.")
    applied, conflicts, errors = [], [], []
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            errors.append({"index": index, "detail": "Célula inválida."})
            continue
        sku = str(cell.get("sku") or "")
        surface_ref = str(cell.get("surface_ref") or "")
        patch = {field: cell[field] for field in ("is_published", "is_sellable", "price_q", "min_qty") if field in cell}
        revisions = cell.get("base_revisions") if isinstance(cell.get("base_revisions"), dict) else None
        try:
            item = set_cell(sku, surface_ref, actor=actor, expected_revisions=revisions, **patch)
        except CatalogConflict as exc:
            conflicts.append({"index": index, "sku": sku, "surface_ref": surface_ref,
                "detail": str(exc), "conflicting_fields": getattr(exc, "fields", [])})
        except (CatalogError, ValidationError) as exc:
            errors.append({"index": index, "sku": sku, "surface_ref": surface_ref, "detail": str(exc)})
        else:
            applied.append({"index": index, "sku": sku, "surface_ref": surface_ref,
                "is_published": item.is_published, "is_sellable": item.is_sellable, "price_q": item.price_q})
    if not applied and not conflicts:
        raise CatalogError(errors[0]["detail"] if errors else "Nenhuma célula foi aplicada.")
    return {"applied": applied, "conflicts": conflicts, "errors": errors}


@transaction.atomic
def set_products_active(products: list[dict], *, is_active: bool, actor) -> dict:
    """Arquiva/desarquiva produtos numa escrita, com recibo e auditoria por linha.

    ``base_is_active`` protege o gesto contra uma tela velha. O lote inteiro é
    travado e escrito em massa; falha ou conflito de uma linha aparece no recibo
    sem esconder o resultado das demais. A reconciliação continua no sinal
    canônico ``product_updated`` e só começa depois do commit local.
    """
    from datetime import timedelta

    from django.contrib.admin.models import CHANGE, LogEntry
    from django.utils import timezone
    from shopman.offerman.models import Product
    from shopman.offerman.signals import product_updated
    from simple_history.utils import bulk_update_with_history

    if not isinstance(products, list) or not products:
        raise CatalogError("Informe os produtos do lote.")
    if len(products) > MAX_CATALOG_BATCH:
        raise CatalogError(f"Envie no máximo {MAX_CATALOG_BATCH} produtos por lote.")
    if not isinstance(is_active, bool):
        raise CatalogError("Diga se os produtos ficam arquivados ou ativos.")

    requested: list[tuple[int, str, bool | None]] = []
    seen: set[str] = set()
    errors: list[dict] = []
    for index, row in enumerate(products):
        sku = str(row.get("sku") or "").strip() if isinstance(row, dict) else ""
        base = row.get("base_is_active") if isinstance(row, dict) else None
        if not sku or not isinstance(base, bool):
            errors.append({"index": index, "sku": sku, "detail": "Atualize a linha antes de confirmar."})
            continue
        if sku in seen:
            errors.append({"index": index, "sku": sku, "detail": "Produto repetido no lote."})
            continue
        seen.add(sku)
        requested.append((index, sku, base))

    locked = list(
        Product.objects.select_for_update()
        .filter(sku__in=[sku for _index, sku, _base in requested])
        .order_by("pk")
    )
    by_sku = {product.sku: product for product in locked}
    changed = []
    applied: list[dict] = []
    conflicts: list[dict] = []
    for index, sku, base in requested:
        product = by_sku.get(sku)
        if product is None:
            errors.append({"index": index, "sku": sku, "detail": "Produto não encontrado."})
            continue
        if product.is_active is not base:
            conflicts.append({
                "index": index,
                "sku": sku,
                "detail": "O estado do produto mudou. Atualize o catálogo antes de repetir.",
                "is_active": product.is_active,
            })
            continue
        before = product.is_active
        product.is_active = is_active
        did_change = before != is_active
        if did_change:
            changed.append(product)
        applied.append({
            "index": index,
            "sku": sku,
            "name": product.name,
            "before_is_active": before,
            "is_active": is_active,
            "changed": did_change,
        })

    if changed:
        verb = "unarchive" if is_active else "archive"
        reason = f"catalog.{verb}:{getattr(actor, 'username', '') or 'operator'}"[:100]
        bulk_update_with_history(
            changed,
            Product,
            ["is_active"],
            default_user=actor if getattr(actor, "pk", None) else None,
            default_change_reason=reason,
        )
        if getattr(actor, "pk", None):
            LogEntry.objects.log_actions(
                user_id=actor.pk,
                queryset=changed,
                action_flag=CHANGE,
                change_message=json.dumps({
                    "action": f"catalog.{verb}",
                    "skus": [product.sku for product in changed],
                }),
            )
        transaction.on_commit(
            lambda rows=tuple(changed): [
                product_updated.send(sender=Product, instance=product, sku=product.sku)
                for product in rows
            ]
        )

    now = timezone.now()
    return {
        "applied": sorted(applied, key=lambda row: row["index"]),
        "conflicts": sorted(conflicts, key=lambda row: row["index"]),
        "errors": sorted(errors, key=lambda row: row["index"]),
        "server_now": now.isoformat(),
        "undo_until": (now + timedelta(seconds=10)).isoformat(),
    }

def set_product(sku: str, *, is_published: bool | None = None, is_sellable: bool | None = None, actor: str = ""):
    """Compatibility facade; global flags use the canonical partial product writer."""
    from shopman.offerman.models import Product

    patch = {field: value for field, value in {"is_published": is_published, "is_sellable": is_sellable}.items() if value is not None}
    if not patch:
        raise CatalogError("Nada a atualizar (informe is_published e/ou is_sellable).")
    update_product_detail(sku, patch, actor=actor)
    return Product.objects.get(sku=sku)


def bulk_set(
    skus: list[str],
    surface_ref: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    actor: str = "",
) -> int:
    """Aplica pausa/publicação em lote numa superfície e reconcilia uma vez.

    Retorna o número de células afetadas.
    """
    if is_published is not None:
        is_published = _as_flag(is_published, "is_published")
    if is_sellable is not None:
        is_sellable = _as_flag(is_sellable, "is_sellable")

    from shopman.offerman.models import Listing, ListingItem, Product

    from shopman.shop.models import Channel

    if not skus:
        return 0
    if _is_display_surface(surface_ref):
        # Feed: bulk só pausa/ativa (is_sellable). Sem preço/publicação.
        if is_sellable is None:
            raise CatalogError("Feed aceita apenas pausar/ativar (is_sellable).")
        from django.contrib.admin.models import CHANGE, LogEntry
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from shopman.backstage.services import feeds as display_service

        with transaction.atomic():
            channel = Channel.objects.select_for_update().get(ref=surface_ref)
            before = sorted(((channel.config or {}).get("display") or {}).get("paused_skus") or [])
            count = display_service.set_items_paused(surface_ref, skus, paused=not is_sellable)
            if count:
                channel.refresh_from_db()
                after = sorted(((channel.config or {}).get("display") or {}).get("paused_skus") or [])
                audit_user = get_user_model().objects.filter(username=actor).first() if actor else None
                if audit_user:
                    LogEntry.objects.log_actions(user_id=audit_user.pk, queryset=[channel], action_flag=CHANGE,
                        change_message=json.dumps({"action": "catalog.bulk_set", "surface_ref": surface_ref,
                            "skus": sorted(skus), "before": before, "after": after}))
                display = dict((channel.config or {}).get("display") or {})
                provenance = dict(display.get("pause_audit") or {})
                for sku in set(before) ^ set(after):
                    if sku in after:
                        provenance[sku] = f"Pausado por {actor or 'sistema'} em {timezone.localtime():%d/%m/%Y %H:%M}"
                    else:
                        provenance.pop(sku, None)
                display["pause_audit"] = provenance
                channel.config = {**(channel.config or {}), "display": display}
                channel.save(update_fields=["config"])
            return count
    updates: dict[str, bool] = {}
    if is_published is not None:
        updates["is_published"] = is_published
    if is_sellable is not None:
        updates["is_sellable"] = is_sellable
    if not updates:
        raise CatalogError("Nada a atualizar (informe is_published e/ou is_sellable).")

    from shopman.shop.services.fiscal_catalog import validate_listing_item_publication

    if surface_ref != ALL_SURFACES:
        _refuse_mirror_surface(surface_ref)
    refs = _all_channel_refs() if surface_ref == ALL_SURFACES else [surface_ref]
    with transaction.atomic():
        # Same lock order as the exact price preview. Every selected destination
        # validates before any update; provider sync is a separately queued effect.
        list(Channel.objects.select_for_update().filter(ref__in=refs).order_by("pk"))
        products = list(Product.objects.select_for_update().filter(sku__in=skus).order_by("pk"))
        listings = list(Listing.objects.select_for_update().filter(ref__in=refs).order_by("pk"))
        by_product = {product.pk: product for product in products}
        by_listing = {listing.pk: listing for listing in listings}
        items = list(ListingItem.objects.select_for_update().filter(
            listing_id__in=by_listing, product_id__in=by_product,
        ).order_by("listing_id", "product_id", "min_qty", "pk"))
        if len(items) > MAX_BULK_PRICE_CELLS:
            raise CatalogError(f"Selecione no máximo {MAX_BULK_PRICE_CELLS} células somando os canais e faixas.")
        from django.contrib.auth import get_user_model
        from simple_history.utils import bulk_update_with_history

        audit_user = get_user_model().objects.filter(username=actor).first() if actor else None
        # Capture the locked before-state even when a previous bulk update did
        # not produce history. Each row retains SKU, listing and quantity tier.
        audit_reason = f"catalog.bulk_set:{actor or 'system'}"[:90]
        bulk_update_with_history(items, ListingItem, [], default_user=audit_user,
                                 default_change_reason=f"{audit_reason}:before")
        for item in items:
            item.product = by_product[item.product_id]
            item.listing = by_listing[item.listing_id]
            for field, value in updates.items():
                setattr(item, field, value)
            validate_listing_item_publication(item)
        count = bulk_update_with_history(items, ListingItem, list(updates), default_user=audit_user,
                                         default_change_reason=f"{audit_reason}:after")
        _realign_mirrors(refs)
        from shopman.offerman.conf import get_projection_backend

        from shopman.shop.handlers.catalog_projection import enqueue_project
        from shopman.shop.services.catalog_sync import record_sync

        destinations = sorted({(item.product.sku, item.listing.ref) for item in items})
        for sku, ref in destinations:
            if get_projection_backend(ref) is not None:
                record_sync(sku, ref, status="pending")
                enqueue_project(sku, ref, trigger="operator_publication")
        for ref in sorted({ref for _sku, ref in destinations}):
            transaction.on_commit(lambda ref=ref: _notify_surface(ref))
    return count


def bulk_set_collection(
    collection_ref: str,
    surface_ref: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    actor: str = "",
) -> int:
    """Bulk scoped a uma COLEÇÃO (manual ou smart) numa superfície.

    Resolve os produtos da coleção (regra ou explícitos) e aplica em lote.
    """
    from shopman.offerman.models import Collection

    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise CatalogError(f"Coleção '{collection_ref}' não encontrada.")
    skus = list(coll.product_queryset().values_list("sku", flat=True))
    return bulk_set(
        skus, surface_ref, is_published=is_published, is_sellable=is_sellable, actor=actor
    )


_PRICE_OPS = ("set", "pct", "delta")


def _apply_price_op(old_q: int, op: str, value: int) -> int:
    """Aplica a operação de preço a um valor em centavos (nunca negativo)."""
    from decimal import ROUND_HALF_UP, Decimal

    if op == "set":
        new_q = int(value)
    elif op == "pct":
        factor = Decimal(1) + (Decimal(value) / Decimal(100))
        new_q = int((Decimal(old_q) * factor).to_integral_value(rounding=ROUND_HALF_UP))
    else:  # delta
        new_q = old_q + int(value)
    return max(new_q, 0)


def bulk_price(
    skus: list[str],
    surface_ref: str,
    *,
    op: str,
    value: int,
    actor: str = "",
) -> int:
    """Reprecifica em lote o tier base de cada produto numa superfície.

    ``op``: ``set`` (preço absoluto, centavos) · ``pct`` (ajuste percentual, pontos
    +/-) · ``delta`` (ajuste absoluto, centavos +/-). Calcula em Python (arredonda),
    grava num único ``bulk_update`` e reconcilia uma vez (padrão do bulk).

    Reprecificação é PERMANENTE (muda o cardápio). Para promoção temporária, use o
    motor de regras (Happy Hour), não isto.
    """
    from shopman.offerman.models import ListingItem

    if op not in _PRICE_OPS:
        raise CatalogError(f"Operação de preço inválida: {op!r}.")
    if op == "set" and value < 0:
        raise CatalogError("Preço não pode ser negativo.")
    if not skus:
        return 0
    if surface_ref == ALL_SURFACES:
        return sum(bulk_price(skus, ref, op=op, value=value, actor=actor) for ref in _all_channel_refs())
    _refuse_mirror_surface(surface_ref)

    # tier base (menor min_qty) por SKU — 1 célula por produto, como a matriz mostra.
    items = (
        ListingItem.objects.filter(listing__ref=surface_ref, product__sku__in=skus)
        .select_related("product")
        .order_by("product__sku", "min_qty")
    )
    seen: set[str] = set()
    changed: list = []
    for item in items:
        sku = item.product.sku
        if sku in seen:
            continue
        seen.add(sku)
        new_q = _apply_price_op(item.price_q, op, value)
        if new_q != item.price_q:
            item.price_q = new_q
            changed.append(item)

    if changed:
        ListingItem.objects.bulk_update(changed, ["price_q"])
        _realign_mirrors([surface_ref])
        _reconcile_if_projected(surface_ref)
        _notify_surface(surface_ref)
    return len(changed)


def bulk_price_collection(
    collection_ref: str,
    surface_ref: str,
    *,
    op: str,
    value: int,
    actor: str = "",
) -> int:
    """Reprecificação em lote scoped a uma COLEÇÃO (manual ou smart)."""
    from shopman.offerman.models import Collection

    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise CatalogError(f"Coleção '{collection_ref}' não encontrada.")
    skus = list(coll.product_queryset().values_list("sku", flat=True))
    return bulk_price(skus, surface_ref, op=op, value=value, actor=actor)


# ── detalhe do produto (edição completa no Gestor) ─────────────────────────────
# O painel de produto da matriz edita UM produto inteiro sem passar pelo Admin:
# campos escalares, tabela nutricional, rotulagem (alérgenos/restrições), atributos
# sociais e classificação fiscal. Escreve com ``save()`` (nunca ``update()``) para
# preservar o gatilho de re-projeção (``Product._PROJECTABLE_FIELDS``) e valida com
# ``full_clean()``. Coleções e listings têm editores no bloco Vínculos;
# componentes de combo são tratados pelo detalhe do produto.
#
# Os três blocos que moram em JSONField têm dono de schema próprio, e é o dono que
# valida e serializa (nunca escrevemos as sub-chaves na mão):
#   - nutrition_facts → offerman.nutrition.NutritionFacts (invariantes ANVISA)
#   - metadata['social'] → offerman.contrib.social.schema
#   - metadata['fiscal'] → fiscalman.classification

# Campos escalares editáveis, agrupados por tipo para o merge parcial.
_DETAIL_TEXT_FIELDS = (
    "name",
    "short_description",
    "long_description",
    "unit",
    "storage_tip",
    "ingredients_text",
    "image_url",
    "availability_policy",
)
_DETAIL_INT_FIELDS = ("base_price_q",)
_DETAIL_NULLABLE_INT_FIELDS = ("unit_weight_g", "shelf_life_days", "production_cycle_hours")
_DETAIL_BOOL_FIELDS = ("is_published", "is_sellable")

# Rotulagem de compra remota: o cliente não pega o produto na mão, então alérgenos,
# restrições, porção e medidas precisam estar escritos. Vivem em ``metadata``.
# ⚠️ ``allergens``, ``dietary_info`` e ``serves`` NÃO moram mais no metadata
# solto: são atributos do registro (``alergenos``, ``dieta``, ``porcoes``). Os
# nomes de CAMPO da API seguem em inglês — é a convenção da casa para contrato
# de projection —, mas a leitura e a escrita passam pelo service.
_DETAIL_ATTR_LIST_FIELDS = {"allergens": "alergenos", "dietary_info": "dieta"}
_DETAIL_ATTR_TEXT_FIELDS = {"serves": "porcoes"}
_DETAIL_META_LIST_FIELDS = ()
_DETAIL_META_TEXT_FIELDS = ("approx_dimensions",)

#: Campos que o formulário de criação aceita: os mesmos do painel de detalhe,
#: mais os blocos JSON que têm dono de schema. ``sku`` é identidade e entra
#: separado, validado por ``_new_product_sku``.
_DETAIL_EDITABLE_FIELDS = frozenset({
    *_DETAIL_TEXT_FIELDS,
    *_DETAIL_INT_FIELDS,
    *_DETAIL_NULLABLE_INT_FIELDS,
    *_DETAIL_BOOL_FIELDS,
    *_DETAIL_ATTR_LIST_FIELDS,
    *_DETAIL_ATTR_TEXT_FIELDS,
    *_DETAIL_META_TEXT_FIELDS,
    "keywords",
    "nutrition_facts",
    "social",
    "fiscal",
    "gtin_rejected",
    "allows_next_day_sale",
    "made_to_order",
    "ready_from",
    "vocation",
    "collections",
})


def _get_product(sku: str):
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku).first()
    if product is None:
        raise CatalogError(f"Produto '{sku}' não encontrado.")
    return product


def _nutrition_payload(product) -> dict:
    """Tabela nutricional como dict simples (chaves da dataclass, sem None)."""
    from dataclasses import asdict

    from shopman.offerman.nutrition import NutritionFacts

    facts = NutritionFacts.from_dict(product.nutrition_facts or {})
    return asdict(facts) if facts is not None else asdict(NutritionFacts())


def _fiscal_origin_choices() -> list[dict]:
    """Origens da mercadoria — a tabela do fiscalman é a fonte, não o Nuxt."""
    from shopman.fiscalman.classification import ORIGINS

    return [{"key": key, "name": name} for key, name in ORIGINS.items()]


def _fiscal_warnings(product) -> list[str]:
    from shopman.fiscalman.classification import from_metadata

    return from_metadata(product.metadata).warnings()


def _fiscal_payload(product) -> dict:
    from dataclasses import asdict

    from shopman.fiscalman.classification import from_metadata

    return asdict(from_metadata(product.metadata))


def _fiscal_profile_choices() -> list[dict]:
    """Perfis fiscais disponíveis — a dataclass é a fonte, não uma lista no Nuxt."""
    from shopman.fiscalman.classification import FISCAL_PROFILES

    return [
        {"key": p.key, "name": p.name, "requires_cest": p.requires_cest}
        for p in FISCAL_PROFILES.values()
    ]


def _social_attrs_payload(product) -> dict:
    from dataclasses import asdict

    from shopman.offerman import get_social_attributes

    return asdict(get_social_attributes(product))


def _gtin_rejected_payload(metadata: dict) -> dict | None:
    from shopman.shop.services.fiscal import GTIN_NF_REJECTED_KEY

    mark = metadata.get(GTIN_NF_REJECTED_KEY)
    if not isinstance(mark, dict):
        return None
    return {
        "gtin": str(mark.get("gtin") or ""),
        "code": str(mark.get("code") or ""),
        "reason": str(mark.get("reason") or ""),
        "at": str(mark.get("at") or ""),
        "order_ref": str(mark.get("order_ref") or ""),
        "confirmed": bool(mark.get("confirmed_at")),
        "confirmed_by": str(mark.get("confirmed_by") or ""),
        "confirmed_at": str(mark.get("confirmed_at") or ""),
    }


def _detail_payload(product) -> dict:
    """Projection do detalhe: campos editáveis + contexto somente-leitura."""
    from shopman.offerman.models import Collection

    memberships = list(product.collection_items.select_related("collection").order_by("sort_order", "pk"))
    primary = next((ci for ci in memberships if ci.is_primary), None)
    metadata = product.metadata or {}
    return {
        "sku": product.sku,
        "name": product.name,
        "short_description": product.short_description,
        "long_description": product.long_description,
        "keywords": sorted(product.keywords.names()),
        "base_price_q": product.base_price_q,
        "unit": product.unit,
        "unit_weight_g": product.unit_weight_g,
        "availability_policy": product.availability_policy,
        "shelf_life_days": product.shelf_life_days,
        "storage_tip": product.storage_tip,
        "production_cycle_hours": product.production_cycle_hours,
        "is_active": product.is_active,
        "is_published": product.is_published,
        "is_sellable": product.is_sellable,
        "ingredients_text": product.ingredients_text,
        "image_url": product.image_url,
        # rotulagem de compra remota (registro de atributos)
        "allergens": list(attributes.get(product, "alergenos") or []),
        "dietary_info": list(attributes.get(product, "dieta") or []),
        "serves": str(attributes.get(product, "porcoes") or ""),
        "approx_dimensions": str(metadata.get("approx_dimensions") or ""),
        "allows_next_day_sale": bool(metadata.get("allows_next_day_sale", False)),
        # Promessa da casa sobre o produto ("Preparado na hora"), não política de
        # estoque. Ver docs/reference/data-schemas.md → Product.metadata.
        "made_to_order": bool(metadata.get("made_to_order", False)),
        # Somente leitura (ADR-040): o modo de produção da ficha vigente do SKU
        # ("Em lote" ou "Na hora") e, no feito na hora, a estação de preparo que o
        # recebe. A fonte é a FICHA, na Produção; ``None`` sem ficha (revenda).
        "production": _production_payload(product.sku),
        # Hora declarada de prontidão ("HH:MM", "" = deduzir do histórico). É o
        # que impede prometer a baguete de tradição para as 9h.
        "ready_from": str(metadata.get("ready_from") or ""),
        "nutrition_facts": _nutrition_payload(product),
        "social": _social_attrs_payload(product),
        "fiscal": _fiscal_payload(product),
        # A SEFAZ recusou o GTIN deste produto numa NFC-e; ``None`` quando não.
        # Só ``confirmed`` é editável (o gesto "Manter sem GTIN na nota"); o
        # resto é o registro da recusa. Corrigir ``social.gtin`` apaga a marca.
        "gtin_rejected": _gtin_rejected_payload(metadata),
        "components": [{"sku": row.component.sku, "name": row.component.name,
            "unit": row.component.unit, "qty": str(row.qty)}
            for row in product.components.select_related("component").order_by("component__name", "component__sku")],
        "collections": [{"ref": ci.collection.ref, "is_primary": ci.is_primary, "sort_order": ci.sort_order} for ci in memberships],
        "collection_choices": list(Collection.objects.filter(rule={}).order_by("sort_order", "name").values("ref", "name", "is_active")),
        "primary_collection": primary.collection.ref if primary else "",
        "primary_collection_name": primary.collection.name if primary else "",
        # somente-leitura: o painel avisa que o dado veio da FICHA e que editar
        # à mão congela a derivação (ver ``dietary_from_recipe``). Vem da
        # proveniência do valor, não mais de um sentinela à parte.
        "field_sources": {
            **{field: attributes.source(product, ref) or "" for field, ref in {**_DETAIL_ATTR_LIST_FIELDS, **_DETAIL_ATTR_TEXT_FIELDS}.items()},
            "nutrition_facts": "recipe" if (product.nutrition_facts or {}).get("auto_filled", False) else "manual",
        },
        "dietary_from_recipe": _from_recipe(product),
        "nutrition_auto_filled": bool((product.nutrition_facts or {}).get("auto_filled", False)),
        "fiscal_profiles": _fiscal_profile_choices(),
        "fiscal_origins": _fiscal_origin_choices(),
        # Avisos (não bloqueiam): o CEST conferido contra o NCM pela tabela do
        # Anexo do Conv. ICMS 142/2018 (``fiscalman.cest_table``).
        "fiscal_warnings": _fiscal_warnings(product),
        # Selos derivados do SKU (Comprável · Vendável · Produzido · Usado em
        # receita) — somente leitura; o gesto de compra é ``set_purchasable``.
        "roles": _roles_payload(product.sku),
        # Vocação do SKU (``ProductConsumptionTag``): o ref do papel, "" = sem
        # vocação. Serve só ao B.I.; não muda a venda. As escolhas vêm do
        # catálogo de papéis, editável no Admin — não de uma lista no Nuxt.
        **_vocation_payload(product.sku),
        # Disponibilidade nos canais (V4-G4, prévia ``catalogo-produto4.html``):
        # somente leitura, do registro de faltas (``ShelfOutage``). Pausar segue
        # no interruptor do canal, na tabela.
        "channel_availability": _channel_availability_payload(product.sku),
        # "Volta ~10:40: lote de 42 no forno" (G23): o próximo lote do SKU hoje, pela
        # previsão da Produção (início real + duração medida). Vazio sem lote aberto.
        **_back_payload(product.sku),
        # O histórico de alterações do produto (⋯ do painel, v4): o do Admin.
        "admin_history_path": _admin_history_path(product),
    }


#: Canais que recebem a indisponibilidade sozinhos (o iFood pelo catálogo
#: projetado; os de exibição pelo estoque do canal de origem, #1404).
_AUTOMATIC_CHANNELS = frozenset({"ifood"})


def _next_batch(sku: str) -> dict | None:
    """O próximo lote do SKU hoje na previsão da Produção: hora e quantidade.

    Mesma leitura do painel de fornadas (``build_production_forecast``): o lote
    em produção volta no início real mais a duração medida; o planejado, na hora
    típica de término. Lote já atrasado ou sem previsão não promete hora.
    """
    from shopman.backstage.projections.production import build_production_forecast

    try:
        rows = build_production_forecast().rows
    except Exception:
        logger.warning("catalog.next_batch_failed sku=%s", sku, exc_info=True)
        return None
    for row in rows:
        if row.output_sku != sku or row.status not in ("in_progress", "scheduled") or row.eta_display in ("", "—"):
            continue
        qty = row.qty.rstrip("0").rstrip(".").rstrip(",") if any(c in row.qty for c in ".,") else row.qty
        where = "no forno" if row.status == "in_progress" else "programado"
        return {"at": row.eta_display, "reason": f"lote de {qty} {where}", "in_oven": row.status == "in_progress"}
    return None


def _back_payload(sku: str) -> dict:
    batch = _next_batch(sku)
    return {"back_at": batch["at"] if batch else "", "back_reason": batch["reason"] if batch else ""}


def _admin_history_path(product) -> str:
    from django.urls import NoReverseMatch, reverse

    try:
        return reverse(f"admin:{product._meta.app_label}_{product._meta.model_name}_history", args=[product.pk])
    except NoReverseMatch:
        return ""


def _channel_note(channel, *, state: str, sale: bool, waiting: int) -> str:
    """A segunda linha do canal indisponível (v4): o que o cliente vê ali agora."""
    if state == "available":
        return ""
    ref = channel.ref
    if ref == "web":
        return f'"Me avise" ligado, {waiting} esperando' if waiting else '"Me avise" ligado'
    if ref in ("pdv", "pos", "balcao"):
        return "selo no botão, venda desativada"
    # A TV (menuboard) é o canal de exibição sem formato de feed (``feeds._switch_kind``).
    display = (channel.config or {}).get("display") or {}
    if not sale and not display.get("format"):
        return 'letreiro mostra "esgotado"'
    return ""


def _channel_availability_payload(sku: str) -> list[dict]:
    """Em que canal dá para comprar o produto agora, e desde quando não dá.

    ``state``: ``available`` · ``sold_out`` · ``paused``. Canal de exibição
    (Meta, Google) não vende: segue o estoque do canal para onde manda o
    cliente (``external_availability.stock_channel_ref``) e é ``automatic``.
    Leitura que falha some (lista vazia): ausência de resposta não é resposta.
    """
    from django.utils import timezone

    from shopman.backstage.models import ShelfOutage
    from shopman.shop.models import Channel
    from shopman.shop.services import external_availability

    try:
        from shopman.shop.services.fomo import demand_count

        open_rows = {row.channel_ref: row for row in ShelfOutage.objects.filter(sku=sku, ended_at__isnull=True)}
        waiting = demand_count(sku) if open_rows else 0
        batch = _next_batch(sku) if open_rows else None
        rows = []
        for channel in Channel.objects.filter(is_active=True).order_by("display_order", "name"):
            sale = channel.commerce_policy == Channel.CommercePolicy.ORDER
            source = channel.ref if sale else external_availability.stock_channel_ref(channel.ref)
            outage = open_rows.get(source)
            state = outage.reason if outage else "available"
            rows.append({
                "ref": channel.ref,
                "name": channel.name or channel.ref,
                "kind": "sale" if sale else "display",
                "state": state,
                "since": timezone.localtime(outage.started_at).strftime("%H:%M") if outage else "",
                "automatic": (not sale) or channel.ref in _AUTOMATIC_CHANNELS,
                # "volta ~10:40 (lote no forno)": só o esgotado volta com o lote; a
                # pausa é decisão de alguém e não volta sozinha.
                "back_at": batch["at"] if batch and state == "sold_out" else "",
                "back_hint": ("lote no forno" if batch["in_oven"] else "lote programado") if batch and state == "sold_out" else "",
                "note": _channel_note(channel, state=state, sale=sale, waiting=waiting),
            })
        return rows
    except Exception:
        logger.warning("catalog.channel_availability_failed sku=%s", sku, exc_info=True)
        return []


def _vocation_payload(sku: str) -> dict:
    """A vocação gravada e as escolhas ativas.

    Um papel desativado no Admin continua aparecendo para o SKU que ainda o
    usa: esconder a escolha atual faria a tela mentir "sem vocação".
    """
    from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag

    tag = ProductConsumptionTag.objects.filter(sku=sku).select_related("role").first()
    roles = list(ConsumptionRole.objects.filter(is_active=True))
    if tag is not None and all(role.pk != tag.role_id for role in roles):
        roles.append(tag.role)
    return {
        "vocation": tag.role.ref if tag is not None else "",
        "vocation_choices": [{"ref": role.ref, "label": role.label, "hint": role.hint} for role in roles],
    }


def _apply_vocation(sku: str, raw) -> None:
    """Grava, troca ou remove a vocação do SKU. "" remove.

    Escolher pelo Gestor é curadoria de gente: a etiqueta sai ``reviewed``. Ao
    TROCAR o papel, o peso próprio do SKU volta a herdar o do papel novo — o
    peso medido para um "híbrido" não vale para um "leva".
    """
    from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag

    if not isinstance(raw, str):
        error = CatalogError("Vocação: escolha uma das opções.")
        error.field = "vocation"
        raise error
    ref = raw.strip()
    tag = ProductConsumptionTag.objects.select_for_update().filter(sku=sku).first()
    if not ref:
        if tag is not None:
            tag.delete()
        return
    if tag is not None and tag.role.ref == ref:
        return
    role = ConsumptionRole.objects.filter(ref=ref, is_active=True).first()
    if role is None:
        error = CatalogError("Vocação: esta opção não existe mais. Atualize o produto e escolha de novo.")
        error.field = "vocation"
        raise error
    if tag is None:
        ProductConsumptionTag.objects.create(sku=sku, role=role, reviewed=True)
        return
    tag.role = role
    tag.eat_in_weight = None
    tag.reviewed = True
    tag.save(update_fields=["role", "eat_in_weight", "reviewed", "updated_at"])


def _production_payload(sku: str) -> dict | None:
    """O modo de produção do SKU, a estação dele e o endereço da ficha na Produção."""
    from urllib.parse import quote

    from shopman.craftsman.models import ProductionMode, Recipe

    from shopman.backstage.projections.hub import surface_link

    recipe = Recipe.objects.filter(output_sku=sku, is_active=True).values("ref", "name", "production_mode").first()
    if recipe is None:
        return None
    mode = recipe["production_mode"]
    station = ""
    if mode == ProductionMode.MADE_TO_ORDER:
        from shopman.shop.services.kds import kitchen_routes_for_skus

        station = str((kitchen_routes_for_skus([sku]).get(sku) or {}).get("station") or "")
        if station:
            summary = f"Feito na hora na estação {station}: os insumos baixam a cada venda."
        else:
            summary = (
                "Feito na hora, mas nenhuma estação de preparo recebe a coleção dele: "
                "a cozinha não vê este item."
            )
    else:
        summary = "Produzido em lote: planejado e estocado pela Produção."
    return {
        "mode": str(mode),
        "mode_label": str(ProductionMode(mode).label),
        "station": station,
        "summary": summary,
        "recipe_ref": recipe["ref"],
        "recipe_name": recipe["name"],
        "url": surface_link("production", f"recipes/sheets?open={quote(recipe['ref'], safe='')}"),
    }


def _roles_payload(sku: str) -> dict[str, bool]:
    from shopman.shop.services.sku_records import sku_roles

    roles = sku_roles(sku)
    return {
        "purchasable": roles.purchasable,
        "sellable": roles.sellable,
        "produced": roles.produced,
        "used_in_recipe": roles.used_in_recipe,
    }


@transaction.atomic
def set_purchasable(sku: str, enabled: bool) -> dict:
    """"Permitir compra": liga/desliga o cadastro de compra do mesmo SKU.

    Ligar cria (ou reativa) o ``Material`` do SKU, na mesma unidade — e recusa
    o que tem ficha ativa, porque o que é produzido aqui entra pela Produção.
    Desligar inativa o cadastro de compra, sem apagar custo nem histórico.
    """
    from django.core.exceptions import ValidationError
    from shopman.offerman.models import Product

    from shopman.shop.services.sku_records import ensure_purchase_record, stop_buying

    product = Product.objects.filter(sku=sku).first()
    if product is None:
        raise CatalogError(f"Produto '{sku}' não encontrado.")
    if not enabled:
        stop_buying(sku)
    else:
        try:
            ensure_purchase_record(product)
        except ValidationError as exc:
            raise CatalogError(exc.messages[0]) from exc
    return _detail_payload(product)



def product_field_revisions(detail: dict) -> dict[str, str]:
    """Tokens for editable leaf fields, derived from the canonical read payload."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    readonly = {"collection_choices", "listing_links", "sku", "production", "primary_collection", "primary_collection_name", "dietary_from_recipe", "nutrition_auto_filled", "fiscal_profiles", "fiscal_origins", "fiscal_warnings", "field_sources", "roles", "vocation_choices", "channel_availability", "back_at", "back_reason", "admin_history_path"}
    values = _patch_leaves({key: value for key, value in detail.items() if key not in readonly})
    revisions = {}
    for path, value in values.items():
        if path in {"nutrition_facts.auto_filled", "social.has_data"}:
            continue
        if path.startswith("gtin_rejected.") and path != "gtin_rejected.confirmed":
            continue
        if path == "components":
            # O rótulo vem do componente; a unidade faz parte da quantidade.
            value = sorted(({"sku": row["sku"], "qty": row["qty"], "unit": row["unit"]} for row in value), key=lambda row: row["sku"])
        state = {"version": 1, "sku": detail["sku"], "field": path, "value": value}
        if path == "components":
            state["parent_unit"] = detail["unit"]
        root = path.split(".", 1)[0]
        if root in {"nutrition_facts", *_DETAIL_ATTR_LIST_FIELDS, *_DETAIL_ATTR_TEXT_FIELDS}:
            state["source"] = (detail.get("field_sources") or {}).get(root, "")
        revisions[path] = mutation_fingerprint(state)
    return revisions


def _patch_leaves(data: dict, prefix: str = "") -> dict:
    leaves = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            leaves.update(_patch_leaves(value, path))
        else:
            leaves[path] = value
    return leaves


def _check_product_revisions(product, patch: dict, expected: dict) -> None:
    from shopman.backstage.services.exceptions import CatalogConflict

    current = product_field_revisions(_detail_payload(product))
    paths = _patch_leaves(patch)
    unknown = set(paths) - set(current)
    if unknown:
        raise CatalogError("O patch contém campos que não são editáveis neste produto.")
    changed = [path for path in paths if expected.get(path) != current[path]]
    if changed:
        error = CatalogConflict("O produto mudou nos campos editados. Confira os valores atuais; seu rascunho foi preservado.")
        error.fields = changed
        raise error

@transaction.atomic
def _apply_product_collections(product, rows, *, expected_revision=None):
    """Curadoria manual com revisão do conjunto, sem publicar em nenhum canal."""
    from shopman.offerman.models import Collection, CollectionItem

    if not isinstance(rows, list) or len(rows) > 200 or any(not isinstance(row, dict) for row in rows):
        raise CatalogError("Informe até 200 coleções.")
    refs = [row.get("ref") for row in rows]
    if any(not isinstance(ref, str) or not ref for ref in refs) or len(set(refs)) != len(refs):
        raise CatalogError("Escolha cada coleção uma única vez.")
    from django.db.models import Q

    previous_groups = CollectionItem.objects.filter(product=product).values("collection_id")
    groups = {group.ref: group for group in Collection.objects.select_for_update().filter(
        Q(ref__in=refs) | Q(pk__in=previous_groups)).order_by("pk")}
    if not set(refs).issubset(groups) or any(groups[ref].is_smart for ref in refs):
        raise CatalogError("Escolha coleções manuais existentes. Coleções automáticas seguem suas regras.")
    flags = [_as_flag(row.get("is_primary", False), "Coleção primária") for row in rows]
    if sum(flags) > 1:
        raise CatalogError("Escolha uma única coleção primária.")
    orders = [_as_nullable_int(row.get("sort_order", index), "Ordem") for index, row in enumerate(rows)]
    if any(value is None or value < 0 or value > 2147483647 for value in orders):
        raise CatalogError("A ordem deve ser um inteiro a partir de zero.")
    current = {item.collection.ref: item for item in CollectionItem.objects.select_for_update(of=("self",)).filter(product=product).select_related("collection").order_by("sort_order", "pk")}
    if expected_revision is not None:
        observed = [{"ref": item.collection.ref, "is_primary": item.is_primary, "sort_order": item.sort_order} for item in current.values()]
        revision = product_field_revisions({"sku": product.sku, "collections": observed})["collections"]
        if expected_revision != revision:
            from shopman.backstage.services.exceptions import CatalogConflict

            error = CatalogConflict("As coleções mudaram durante a edição. Confira os valores atuais.")
            error.fields = ["collections"]
            raise error
    # Limpa a primária antes da troca para respeitar a constraint condicional.
    CollectionItem.objects.filter(product=product, is_primary=True).update(is_primary=False)
    CollectionItem.objects.filter(product=product).exclude(collection__ref__in=refs).delete()
    for row, primary, order in zip(rows, flags, orders, strict=True):
        item = current.get(row["ref"]) or CollectionItem(product=product, collection=groups[row["ref"]])
        item.is_primary, item.sort_order = primary, order
        item.save()



def _apply_product_components(product, rows):
    """Composição atômica; a validação de ciclo e profundidade é do Core."""
    from decimal import Decimal, InvalidOperation

    from django.core.exceptions import ValidationError
    from shopman.offerman.models import Product, ProductComponent
    from shopman.offerman.signals import product_updated

    if not isinstance(rows, list) or len(rows) > 200 or any(not isinstance(row, dict) for row in rows):
        raise CatalogError("Informe até 200 componentes.")
    skus = [row.get("sku") for row in rows]
    if any(not isinstance(sku, str) or not sku for sku in skus) or len(set(skus)) != len(skus):
        raise CatalogError("Escolha cada produto componente uma única vez.")
    products = {p.sku: p for p in Product.objects.filter(sku__in=skus)}
    if set(products) != set(skus):
        raise CatalogError("Um dos produtos componentes não existe mais. Escolha outro produto.")
    parsed = []
    for row in rows:
        raw = row.get("qty")
        try:
            if isinstance(raw, bool) or not isinstance(raw, (str, int)):
                raise ValueError
            qty = Decimal(raw)
            if not qty.is_finite() or qty <= 0 or qty > Decimal("9999999.999") or qty != qty.quantize(Decimal("0.001")):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise CatalogError("Informe uma quantidade positiva com até três casas decimais por componente.") from exc
        parsed.append((products[row["sku"]], qty))
    ProductComponent.objects.filter(parent=product).delete()
    for component, qty in parsed:
        try:
            ProductComponent.objects.create(parent=product, component=component, qty=qty)
        except ValidationError as exc:
            messages = " ".join(exc.messages)
            if component.pk == product.pk:
                detail = "O produto não pode compor a si mesmo."
            elif "Circular" in messages:
                detail = "A composição criaria um ciclo entre produtos. Escolha outro componente."
            elif "Max bundle depth" in messages:
                detail = "A composição ultrapassa o limite de níveis de combos. Escolha um produto com menos níveis."
            else:
                detail = "Não foi possível incluir o componente. Confira o produto e a quantidade."
            raise CatalogError(detail) from exc
    from shopman.shop.handlers._sse_emitters import emit_catalog_changed

    # O sinal grava a outbox na mesma transação; o emissor SSE agenda o push
    # para depois do commit. Falha de outbox não pode confirmar a composição.
    product_updated.send(sender=Product, instance=product, sku=product.sku)
    emit_catalog_changed()


def get_product_detail(sku: str) -> dict:
    """Todos os campos editáveis de um produto (para o painel do Gestor)."""
    return _detail_payload(_get_product(sku))


def _as_nullable_int(value, label: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise CatalogError(f"{label} deve ser um número inteiro.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CatalogError(f"{label} deve ser um número inteiro.") from exc


def _as_flag(value, label: str) -> bool:
    """Booleano estrito de entrada de operador, no dialeto desta camada.

    ``bool()`` cru mente: ``bool("false")`` é ``True``, então quem manda o texto
    ``"false"`` LIGA a opção em vez de desligar, e nada avisa. Não é explorável
    pela UI de hoje, que manda JSON de verdade; é explorável por quem fala com a
    API direto, e vira bug no dia em que alguém trocar um ``fetch`` por
    ``URLSearchParams``.

    Mesma tabela de tokens do parser canônico (``backstage/parsing.py``), mas
    levantando ``CatalogError`` — esta camada tem dialeto próprio de entrada, e
    ``services/exceptions.py`` documenta que a camada HTTP mapeia por TIPO.
    Importar o parser do DRF aqui quebraria esse mapeamento para consertar um
    ``bool()``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "1", "yes", "on"}:
            return True
        if token in {"false", "0", "no", "off"}:
            return False
    elif isinstance(value, int) and value in (0, 1):
        # `isinstance(True, int)` é verdade em Python — por isso o bool vem antes.
        return bool(value)
    elif value is None:
        return False
    raise CatalogError(f"{label} aceita apenas sim ou não.")


def _as_str_list(value, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CatalogError(f"{label} deve ser uma lista de textos.")
    return [item.strip() for item in value if item.strip()]


def _apply_nutrition(product, raw) -> None:
    """Grava a tabela nutricional. As invariantes ANVISA são do ``Product.clean()``."""
    from dataclasses import fields as dataclass_fields

    from shopman.offerman.nutrition import NutritionFacts

    if not isinstance(raw, dict):
        raise CatalogError("nutrition_facts deve ser um objeto.")

    # A dataclass é a fonte dos nutrientes aceitos; ``auto_filled`` é sentinel
    # interno e nunca vem do operador.
    accepted = {f.name: f.type for f in dataclass_fields(NutritionFacts) if f.name != "auto_filled"}

    collected: dict = dict(product.nutrition_facts or {})
    changed = False
    for key in accepted:
        if key not in raw:
            continue
        value = raw.get(key)
        if value in (None, ""):
            continue
        try:
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise CatalogError(f"{key} deve ser um número.")
            parsed = _as_nullable_int(value, key) if "int" in str(accepted[key]) else float(value)
            if parsed is None or not isfinite(parsed):
                raise CatalogError(f"{key} deve ser um número finito.")
            changed = changed or collected.get(key) != parsed
            collected[key] = parsed
        except (TypeError, ValueError, OverflowError) as exc:
            raise CatalogError(f"{key} deve ser um número.") from exc

    # Editar à mão desliga a derivação a partir da receita — senão o próximo save
    # da Recipe sobrescreveria em silêncio o que o operador acabou de digitar.
    if changed:
        collected["auto_filled"] = False
    product.nutrition_facts = collected


def _apply_labelling(product, data: dict) -> None:
    """Alérgenos, restrições, porção e medidas — tudo em ``metadata``."""
    metadata = dict(product.metadata or {})

    for field in _DETAIL_META_LIST_FIELDS:
        if field in data:
            values = _as_str_list(data.get(field), field)
            if values:
                metadata[field] = values
            else:
                metadata.pop(field, None)
    for field in _DETAIL_META_TEXT_FIELDS:
        if field in data:
            value = str(data.get(field) or "").strip()
            if value:
                metadata[field] = value
            else:
                metadata.pop(field, None)
    if "allows_next_day_sale" in data:
        metadata["allows_next_day_sale"] = _as_flag(data.get("allows_next_day_sale"), "allows_next_day_sale")
    if "made_to_order" in data:
        metadata["made_to_order"] = _as_flag(data.get("made_to_order"), "made_to_order")
    if "ready_from" in data:
        # Vazio APAGA a declaração; hora ilegível é recusada em vez de virar
        # ausência silenciosa (o cadastro diria que a casa respondeu, e o sistema
        # agiria como se ninguém tivesse respondido).
        raw = str(data.get("ready_from") or "").strip()
        if raw:
            from shopman.shop.services.product_readiness import format_clock, parse_clock

            parsed = parse_clock(raw)
            if parsed is None:
                raise CatalogError("Pronto a partir de: use o formato HH:MM. Ex.: 12:00.")
            metadata["ready_from"] = format_clock(parsed)
        else:
            metadata.pop("ready_from", None)

    product.metadata = metadata

    # A rotulagem dietética vai para o registro. Só marca como escrita pelo
    # gestor quando ela REALMENTE mudou: um save qualquer não pode travar a
    # derivação pela ficha técnica.
    for field, ref in _DETAIL_ATTR_LIST_FIELDS.items():
        if field not in data:
            continue
        novo = _as_str_list(data.get(field), field)
        if novo == (attributes.get(product, ref) or []):
            continue
        attributes.set(product, ref, novo or None, source="manual", save=False)

    for field, ref in _DETAIL_ATTR_TEXT_FIELDS.items():
        if field not in data:
            continue
        novo = str(data.get(field) or "").strip()
        if novo != (attributes.get(product, ref) or ""):
            attributes.set(product, ref, novo or None, source="manual", save=False)


def _from_recipe(product) -> bool:
    """Se a rotulagem dietética veio da ficha técnica (e é recalculável)."""
    return any(
        attributes.get(product, ref) is not None
        and attributes.source(product, ref) == "recipe"
        for ref in ("alergenos", "dieta")
    )


def _apply_social(product, raw) -> None:
    from shopman.offerman import (
        ProductSocialAttributes,
        get_social_attributes,
        set_social_attributes,
    )

    if not isinstance(raw, dict):
        raise CatalogError("social deve ser um objeto.")

    current = get_social_attributes(product)
    merged = {**asdict(current), **raw}
    attrs = ProductSocialAttributes(
        brand=str(merged.get("brand") or "").strip(),
        gtin=str(merged.get("gtin") or "").strip(),
        mpn=str(merged.get("mpn") or "").strip(),
        condition=str(merged.get("condition") or "new"),
        google_product_category=str(merged.get("google_product_category") or "").strip(),
        tiktok_category_id=str(merged.get("tiktok_category_id") or "").strip(),
        hashtags=merged.get("hashtags") or [],
        social_caption=str(merged.get("social_caption") or "").strip(),
    )
    problems = attrs.errors()
    if problems:
        raise CatalogError(problems[0])
    product.metadata = set_social_attributes(product.metadata, attrs)


def _apply_fiscal(product, raw) -> None:
    from shopman.fiscalman.classification import (
        ProductFiscalClassification,
        from_metadata,
        to_metadata_fiscal,
    )

    if not isinstance(raw, dict):
        raise CatalogError("fiscal deve ser um objeto.")

    current = from_metadata(product.metadata)
    merged = {**asdict(current), **raw}
    classification = ProductFiscalClassification(
        profile=str(merged.get("profile") or "").strip(),
        ncm=str(merged.get("ncm") or "").strip(),
        cest=str(merged.get("cest") or "").strip(),
        unit=str(merged.get("unit") or "UN").strip() or "UN",
        origin=str(merged.get("origin") or "0").strip() or "0",
    )

    metadata = dict(product.metadata or {})
    # Classificação vazia = produto ainda não fiscalizado; só validamos quando há
    # algo preenchido (mesma regra do form do Admin — o NFC-e é que cobra depois).
    if not classification.ncm and not classification.cest:
        metadata.pop("fiscal", None)
        product.metadata = metadata
        return

    problems = classification.errors()
    if problems:
        raise CatalogError(problems[0])
    metadata["fiscal"] = to_metadata_fiscal(classification)
    product.metadata = metadata


@transaction.atomic
def update_product_detail(sku: str, data: dict, *, actor: str = "", expected_revisions: dict | None = None) -> dict:
    """Merge parcial dos campos do produto (chave ausente = sem mudança).

    Edição de conteúdo valida com ``full_clean()``; switches globais preservam a
    validação de flags e o gate fiscal de save, sem rever rotulagem não editada.
    Persiste com ``save()``, que emite ``product_updated`` quando um campo projetável
    muda — o auto-trigger re-projeta nas plataformas alvo. Os blocos em JSONField
    (nutricional, social, fiscal) são validados pelo dono do schema antes disso.
    """
    from django.core.exceptions import ValidationError
    from shopman.offerman.models import Product

    if "components" in data:
        # Serializa alterações cruzadas do grafo antes do lock do produto atual.
        # Ordem única evita A→B e B→A bloquearem uma à outra em ordem inversa.
        list(Product.objects.select_for_update().order_by("pk").values_list("pk", flat=True))
    product = Product.objects.select_for_update().filter(sku=sku).first()
    if product is None:
        raise CatalogError(f"Produto '{sku}' não encontrado.")
    if expected_revisions is not None:
        _check_product_revisions(product, data, expected_revisions)
    if "components" in data:
        _apply_product_components(product, data["components"])
        data = {key: value for key, value in data.items() if key != "components"}
        if not data:
            return _detail_payload(product)
    if "collections" in data:
        _apply_product_collections(product, data["collections"], expected_revision=(expected_revisions or {}).get("collections"))
        data = {key: value for key, value in data.items() if key != "collections"}
        if not data:
            return _detail_payload(product)
    # A vocação mora fora do produto (``ProductConsumptionTag``): grava à parte,
    # na mesma transação, e sozinha não regrava nem revalida o produto.
    if "vocation" in data:
        _apply_vocation(product.sku, data["vocation"])
        data = {key: value for key, value in data.items() if key != "vocation"}
        if not data:
            return _detail_payload(product)
    keywords = None
    if "keywords" in data:
        raw = data["keywords"]
        if not isinstance(raw, list) or any(not isinstance(value, str) for value in raw):
            raise CatalogError("keywords deve ser uma lista de textos.")
        keywords = [value.strip() for value in raw if value.strip()]

    for field in _DETAIL_TEXT_FIELDS:
        if field in data:
            setattr(product, field, str(data.get(field) or "").strip())
    for field in _DETAIL_INT_FIELDS:
        if field in data:
            value = _as_nullable_int(data.get(field), field)
            if value is None:
                raise CatalogError(f"{field} é obrigatório.")
            setattr(product, field, value)
    for field in _DETAIL_NULLABLE_INT_FIELDS:
        if field in data:
            setattr(product, field, _as_nullable_int(data.get(field), field))
    for field in _DETAIL_BOOL_FIELDS:
        if field in data:
            setattr(product, field, _as_flag(data.get(field), field))

    if "nutrition_facts" in data:
        _apply_nutrition(product, data.get("nutrition_facts"))
    # Rotulagem e blocos de metadata em sequência: cada um lê o metadata já
    # atualizado pelo anterior, então não há escrita perdida.
    try:
        _apply_labelling(product, data)
    except attributes.AttributeError_ as exc:
        raise CatalogError(str(exc)) from exc
    gtin_settled = False
    if "social" in data:
        _apply_social(product, data.get("social"))
        gtin_settled = _settle_rejected_gtin(product, actor=actor)
    if "gtin_rejected" in data:
        gtin_settled = _confirm_rejected_gtin(product, data.get("gtin_rejected"), actor=actor) or gtin_settled
    if "fiscal" in data:
        _apply_fiscal(product, data.get("fiscal"))

    # Availability and social-only edits already had their own strict validators
    # plus save's fiscal gate. Do not require review of untouched legacy labels.
    if not (set(data).issubset({"is_published", "is_sellable"}) or set(data) <= {"social", "gtin_rejected"}):
        try:
            product.full_clean()
        except ValidationError as exc:
            raise CatalogError(_first_validation_message(exc)) from exc

    try:
        product.save()
    except ValidationError as exc:
        # O porteiro de coerência do SKU (unidade de venda × de compra) fala
        # em ``pre_save``: a mensagem dele vai inteira para a tela.
        raise CatalogError(" ".join(exc.messages)) from exc

    if "unit" in data:
        # Vendido por peso é só no balcão: o preço final nasce na balança, e o
        # cliente de longe não vê a peça (``sku_records.sells_remotely``).
        from shopman.shop.services.sku_records import withdraw_from_remote_channels
        from shopman.shop.services.weighed_sale import is_sold_by_weight

        if is_sold_by_weight(product.unit):
            withdraw_from_remote_channels(product)

    if keywords is not None:
        product.keywords.set(keywords)

    if gtin_settled:
        _close_gtin_rejected_alerts(product.sku, actor=actor)

    product.refresh_from_db()
    return _detail_payload(product)


# ── criar e duplicar produto ─────────────────────────────────────────────────
# A criação do Gestor reusa o MESMO escritor do painel de detalhe: o produto novo
# nasce com o mínimo (SKU e nome) e o resto entra pelo merge validado, com
# ``save()``. Nunca um ``update()`` em massa: o ``save()`` é o gatilho de
# ``product_created``/``product_updated`` que re-projeta iFood/Meta.
#
# A duplicação copia o CONTEÚDO do produto (campos, palavras-chave, rótulos e a
# composição do combo) e nunca a decisão comercial: listing, publicação em canal
# e curadoria de coleção são do dia, e copiá-los empurraria um SKU novo para
# iFood/Meta sem ninguém revisar. A cópia nasce oculta e fora de venda.
#
# O GTIN identifica a EMBALAGEM, não o produto: dois SKUs com o mesmo código de
# barras viram recusa na SEFAZ e no Google, então a cópia nasce sem ele (e sem a
# marca de recusa do original, que é história daquele SKU).


def _new_product_sku(raw) -> str:
    if not isinstance(raw, str):
        raise CatalogError("Informe o SKU do produto.")
    sku = raw.strip()
    if not sku:
        raise CatalogError("Informe o SKU do produto.")
    if len(sku) > 100:
        raise CatalogError("O SKU deve ter no máximo 100 caracteres.")
    if "/" in sku:
        raise CatalogError("O SKU não pode ter barra (/).")
    return sku


def _new_product_name(raw, *, fallback: str = "") -> str:
    name = str(raw or "").strip() or fallback
    if not name:
        raise CatalogError("Informe o nome do produto.")
    if len(name) > 200:
        raise CatalogError("O nome do produto deve ter no máximo 200 caracteres.")
    return name


def _duplicate_metadata(source) -> dict:
    from shopman.shop.services.fiscal import GTIN_NF_REJECTED_KEY

    metadata = json.loads(json.dumps(source.metadata or {}))
    metadata.pop("gtin_source", None)
    metadata.pop(GTIN_NF_REJECTED_KEY, None)
    social = metadata.get("social")
    if isinstance(social, dict):
        metadata["social"] = {**social, "gtin": ""}
    return metadata


def product_duplicate_revision(sku: str) -> str:
    """Impressão do conteúdo copiável: qualquer campo que mude invalida a cópia."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    detail = get_product_detail(sku)
    return mutation_fingerprint({"operation": "catalog.product-duplicate", "sku": sku,
        "revisions": product_field_revisions(detail)})


def suggested_duplicate_sku(sku: str) -> str:
    from shopman.offerman.models import Product

    base = f"{sku}-COPIA"[:100]
    candidate, suffix = base, 2
    while Product.objects.filter(sku__iexact=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[: 100 - len(tail)]}{tail}"
        suffix += 1
    return candidate


def suggested_duplicate_name(name: str) -> str:
    suffix = " (cópia)"
    return f"{name[: 200 - len(suffix)]}{suffix}"


@transaction.atomic
def create_product(data: dict, *, actor: str = "") -> tuple[dict, dict | None]:
    """Cria um produto novo e devolve (detalhe canônico, resultado do GTIN).

    O segundo item é None sem rascunho de GTIN; com rascunho, o resumo do
    aceite campo a campo (aplicados, conflitos, recusados).
    """
    from django.core.exceptions import ValidationError
    from shopman.offerman.models import Product

    if not isinstance(data, dict):
        raise CatalogError("Informe os campos do produto.")
    sku = _new_product_sku(data.get("sku"))
    name = _new_product_name(data.get("name"))
    if Product.objects.filter(sku__iexact=sku).exists():
        error = CatalogError(f"Já existe um produto com o SKU '{sku}'.")
        error.field = "sku"
        raise error
    payload = {key: value for key, value in data.items()
        if key not in {"sku", "name", "base_revision", "expected_actor_id", "idempotency_key", "enrichment", "purchase", "intent"}}
    unknown = set(payload) - _DETAIL_EDITABLE_FIELDS
    if unknown:
        raise CatalogError(f"Campos não editáveis neste produto: {', '.join(sorted(unknown))}.")
    try:
        product = Product.objects.create(sku=sku, name=name)
        detail = update_product_detail(sku, payload, actor=actor) if payload else _detail_payload(product)
        enrichment = _apply_gtin_draft(sku, data.get("enrichment"), actor=actor)
        if data.get("purchase"):
            # "Compro e revendo": o vendável nasce e o comprável do MESMO SKU é
            # ligado no mesmo fluxo (custo e fornecedor são do Compras).
            set_purchasable(sku, True)
            detail = _detail_payload(_get_product(sku))
        elif enrichment is not None:
            detail = _detail_payload(_get_product(sku))
        return detail, enrichment
    except ValidationError as exc:
        raise CatalogError(_first_validation_message(exc)) from exc


@transaction.atomic
def duplicate_product(sku: str, data: dict, *, actor: str = "", expected_revision: str | None = None) -> dict:
    """Duplica o conteúdo de um produto num SKU novo (oculto e fora de venda)."""
    from django.core.exceptions import ValidationError
    from shopman.offerman.models import Product, ProductComponent

    from shopman.backstage.services.exceptions import CatalogConflict

    if not isinstance(data, dict):
        raise CatalogError("Informe os campos da cópia.")
    source = Product.objects.select_for_update().filter(sku=sku).first()
    if source is None:
        raise CatalogError(f"Produto '{sku}' não encontrado.")
    if expected_revision is not None and expected_revision != product_duplicate_revision(sku):
        raise CatalogConflict("O produto mudou desde que você abriu a cópia. Confira antes de duplicar.")
    new_sku = _new_product_sku(data.get("sku"))
    if new_sku == source.sku:
        raise CatalogError("O SKU da cópia precisa ser diferente do original.")
    if Product.objects.filter(sku__iexact=new_sku).exists():
        error = CatalogError(f"Já existe um produto com o SKU '{new_sku}'.")
        error.field = "sku"
        raise error
    name = _new_product_name(data.get("name"), fallback=suggested_duplicate_name(source.name))
    try:
        copy = Product.objects.create(
            sku=new_sku,
            name=name,
            short_description=source.short_description,
            long_description=source.long_description,
            unit=source.unit,
            unit_weight_g=source.unit_weight_g,
            storage_tip=source.storage_tip,
            ingredients_text=source.ingredients_text,
            nutrition_facts=source.nutrition_facts or {},
            base_price_q=source.base_price_q,
            availability_policy=source.availability_policy,
            shelf_life_days=source.shelf_life_days,
            production_cycle_hours=source.production_cycle_hours,
            image_url=source.image_url,
            metadata=_duplicate_metadata(source),
            is_published=False,
            is_sellable=False,
        )
        copy.keywords.set(list(source.keywords.names()))
        # Os rótulos derivados da ficha congelam como escrita à mão na cópia: ela
        # não herda a ficha técnica do original, e dizer "veio da ficha" ali
        # congelaria uma derivação que não existe neste SKU.
        for _field, ref in {**_DETAIL_ATTR_LIST_FIELDS, **_DETAIL_ATTR_TEXT_FIELDS}.items():
            value = attributes.get(source, ref)
            if value in (None, [], ""):
                continue
            attributes.set(copy, ref, value, source="manual", save=False)
        copy.save()
        # A composição do combo é do produto: a cópia nasce com os mesmos
        # componentes. Listing, coleção e publicação NÃO vêm: são decisões do dia.
        for component in ProductComponent.objects.filter(parent=source).order_by("pk"):
            ProductComponent.objects.create(parent=copy, component=component.component, qty=component.qty)
    except ValidationError as exc:
        raise CatalogError(_first_validation_message(exc)) from exc
    return _detail_payload(copy)

# ── GTIN: rascunho, correlação e foto ────────────────────────────────────────
# O rascunho NÃO escreve: consulta as fontes que já existem
# (``shop.services.product_enrichment``: NF-e de compra -> Cosmos -> Open Food
# Facts) e devolve campo a campo com a ORIGEM e a alternativa. Quem aplica é o
# aceite campo a campo (``product_enrichment.accept_fields``), o MESMO caminho do
# Admin; esta camada não reimplementa prioridade, fusão nem licença de foto.

_CORRELATE_CONFIG_FIELDS = ("unit", "availability_policy", "shelf_life_days")
_PHOTO_MAX_BYTES = 8 * 1024 * 1024


def product_draft(gtin: str) -> dict:
    """Rascunho por GTIN para a tela de criar. Leitura pura: nada é gravado."""
    from shopman.offerman import gtin_is_valid

    from shopman.shop.services import product_enrichment as enrichment

    code = str(gtin or "").strip()
    if not code:
        raise CatalogError("Leia ou digite o código de barras.")
    if not gtin_is_valid(code):
        raise CatalogError("O código de barras tem dígito verificador inválido. Confira a leitura.")
    suggestion = enrichment.build_suggestion(code)
    fields = {}
    for name, entry in suggestion.fields.items():
        fields[name] = {
            **entry,
            "label": enrichment.FIELD_LABELS.get(name, name),
            "source_label": enrichment.SOURCE_LABELS.get(entry.get("source", ""), entry.get("source", "")),
            "display": enrichment.format_value(name, entry.get("value")),
        }
    draft = {
        "gtin": suggestion.gtin,
        "fields": fields,
        "sources": list(suggestion.sources),
        "consulted": list(suggestion.consulted),
        "skipped": dict(suggestion.skipped),
        "allergens_unmapped": list(suggestion.allergens_unmapped),
        "notes": list(suggestion.notes),
        "reference_photo": suggestion.reference_photo,
    }
    draft["correlate"] = correlate_suggestions(draft)
    return draft


def _draft_hints(draft: dict) -> tuple[str, str, list[str]]:
    import re

    fields = (draft or {}).get("fields") or {}
    value = lambda name: (fields.get(name) or {}).get("value")  # noqa: E731
    ncm = str(value("ncm") or "")
    brand = str(value("brand") or "")
    name = str(value("name") or "")
    words = [word for word in re.split(r"\W+", name.lower()) if len(word) >= 4][:4]
    return ncm, brand, words


def correlate_suggestions(draft: dict, *, limit: int = 5) -> dict:
    """O que reaproveitar de produtos parecidos (NCM, marca, nome).

    A sugestão é a CONFIGURAÇÃO do cadastro (unidade, disponibilidade,
    validade) e o PERFIL fiscal da casa. CFOP/CSOSN não se
    inventam por produto: saem do perfil. Nada aqui escreve.
    """
    from collections import Counter

    from shopman.offerman.models import Product

    ncm, brand, words = _draft_hints(draft or {})
    scored = []
    products = Product.objects.only(
        "id", "sku", "name", "unit", "availability_policy", "shelf_life_days", "metadata",
    ).order_by("name")
    for product in products:
        meta = product.metadata or {}
        reasons = []
        if ncm and str((meta.get("fiscal") or {}).get("ncm") or "") == ncm:
            reasons.append(f"mesmo NCM {ncm}")
        if brand and str((meta.get("social") or {}).get("brand") or "").strip().lower() == brand.lower():
            reasons.append(f"mesma marca {brand}")
        matches = [word for word in words if word in product.name.lower()]
        if matches:
            reasons.append("nome parecido: " + ", ".join(matches))
        if reasons:
            scored.append((len(reasons), product, reasons))
    scored.sort(key=lambda item: (-item[0], item[1].name))
    chosen = scored[:limit]
    suggestions = []
    for field in _CORRELATE_CONFIG_FIELDS:
        counter = Counter()
        for _score, product, _reasons in chosen:
            value = getattr(product, field)
            if value not in (None, ""):
                counter[value] += 1
        if not counter:
            continue
        value, count = counter.most_common(1)[0]
        who = [product.sku for _s, product, _r in chosen if getattr(product, field) == value][:3]
        suggestions.append({
            "field": field, "value": value,
            "reason": f"{count} de {len(chosen)} produtos parecidos usam {value}",
            "sources": who,
        })
    profiles = Counter()
    for _score, product, _reasons in chosen:
        profile = str(((product.metadata or {}).get("fiscal") or {}).get("profile") or "")
        if profile:
            profiles[profile] += 1
    if profiles:
        value, count = profiles.most_common(1)[0]
        extra = {"field": "fiscal_profile", "value": value,
            "reason": f"{count} de {len(chosen)} produtos parecidos usam este perfil fiscal",
            "sources": [product.sku for _s, product, _r in chosen
                if str(((product.metadata or {}).get("fiscal") or {}).get("profile") or "") == value][:3]}
        suggestions.append(extra)
    notes = [] if chosen else ["Ainda não há produto parecido no catálogo para comparar."]
    return {
        "correlates": [{"sku": product.sku, "name": product.name, "reasons": reasons}
            for _score, product, reasons in chosen],
        "suggestions": suggestions,
        "notes": notes,
    }


def photo_enhance_status() -> tuple[bool, str]:
    """A melhoria de foto está ligada neste ambiente? (provider vazio = não)."""
    from django.conf import settings

    provider = str(getattr(settings, "SHOPMAN_PRODUCT_IMAGE_ENHANCE_PROVIDER", "") or "").strip().lower()
    if not provider:
        return False, "A melhoria de foto não está configurada neste ambiente."
    if provider == "deterministic":
        return True, ""
    if provider == "generative":
        # Foto generativa pode INVENTAR o produto. Só entra opt-in, com chave e
        # revisão humana; nesta onda não há provedor ligado.
        return False, "A melhoria generativa de foto ainda não está ligada. Use o ajuste determinístico."
    return False, f"Provedor de melhoria de foto desconhecido: {provider}."


def _decode_photo(raw) -> tuple[object, bytes]:
    """Valida a foto e devolve ``(imagem PIL, bytes originais)``."""
    import base64
    import binascii
    from io import BytesIO

    from PIL import Image, UnidentifiedImageError

    text = str(raw or "")
    if text.startswith("data:"):
        _, _, text = text.partition(",")
    try:
        payload = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CatalogError("Envie a foto como imagem.") from exc
    if len(payload) > _PHOTO_MAX_BYTES:
        raise CatalogError("A foto é grande demais (máximo 8 MB).")
    try:
        image = Image.open(BytesIO(payload))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise CatalogError("Não consegui ler esta foto. Envie JPEG, PNG ou WebP.") from exc
    return image, payload


_PHOTO_EXTENSIONS = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}


def store_product_photo(raw, *, filename: str = "") -> dict:
    """Grava a foto no storage DEFAULT e devolve a URL. Não padroniza nem inventa.

    O nome é único (arquivo imutável: o host serve com cache de um ano). Sem
    storage gravável o serviço é DEGRADÁVEL: levanta ``AiAssistNotConfigured`` e a
    camada HTTP responde 503, como o assist sem chave.
    """
    import os
    import uuid

    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from shopman.backstage.services.exceptions import AiAssistNotConfigured

    image, payload = _decode_photo(raw)
    fmt = str(getattr(image, "format", "") or "").strip().lower()
    extension = _PHOTO_EXTENSIONS.get(fmt, "jpg")
    base = os.path.splitext(os.path.basename(str(filename or "")))[0].strip() or "produto"
    name = f"products/{base}-{uuid.uuid4().hex}.{extension}"
    try:
        saved = default_storage.save(name, ContentFile(payload))
        url = default_storage.url(saved)
    except Exception as exc:
        raise AiAssistNotConfigured(
            "O storage de fotos não está disponível neste ambiente. Avise o responsável."
        ) from exc
    return {"name": saved, "url": url, "size": len(payload), "media_type": f"image/{fmt or 'jpeg'}"}


def _trim_uniform_border(image):
    from PIL import Image, ImageChops

    rgb = image.convert("RGB")
    width, height = rgb.size
    if width < 8 or height < 8:
        return rgb
    corner = rgb.getpixel((0, 0))
    background = Image.new("RGB", rgb.size, corner)
    diff = ImageChops.difference(rgb, background).convert("L")
    box = diff.point(lambda value: 255 if value > 18 else 0).getbbox()
    return rgb.crop(box) if box else rgb


def enhance_product_photo(raw) -> dict:
    """Padronização DETERMINÍSTICA: recorta a borda, enquadra, dimensiona e afia.

    Não inventa conteúdo: troca/limpa a borda uniforme, enquadra no quadrado,
    redimensiona e ajusta nitidez. É a padronização permitida por padrão.
    """
    from io import BytesIO

    from django.conf import settings
    from PIL import Image, ImageEnhance, ImageOps

    from shopman.backstage.services.exceptions import AiAssistNotConfigured

    available, reason = photo_enhance_status()
    provider = str(getattr(settings, "SHOPMAN_PRODUCT_IMAGE_ENHANCE_PROVIDER", "") or "").strip().lower()
    if not available or provider != "deterministic":
        raise AiAssistNotConfigured(reason or "A melhoria de foto não está ligada.")
    image, _payload = _decode_photo(raw)
    image = _trim_uniform_border(image)
    square = ImageOps.pad(image, (1200, 1200), color=(255, 255, 255), method=Image.Resampling.LANCZOS)
    square = ImageEnhance.Sharpness(square).enhance(1.15)
    square = ImageEnhance.Contrast(square).enhance(1.02)
    output = BytesIO()
    square.save(output, format="JPEG", quality=90, optimize=True)
    import base64

    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return {"provider": "deterministic", "media_type": "image/jpeg",
        "image": f"data:image/jpeg;base64,{encoded}",
        "steps": ["recorte da borda uniforme", "quadrado 1200x1200", "nitidez", "contraste"]}


def _apply_gtin_draft(sku: str, spec, *, actor: str) -> dict | None:
    from dataclasses import replace as dc_replace
    from types import SimpleNamespace

    from shopman.offerman import get_social_attributes, gtin_is_valid, set_social_attributes

    from shopman.shop.services import product_enrichment as enrichment

    if not isinstance(spec, dict):
        return None
    gtin = str(spec.get("gtin") or "").strip()
    accept = [str(name) for name in (spec.get("accept") or []) if isinstance(name, str)]
    replace = [str(name) for name in (spec.get("replace") or []) if isinstance(name, str)]
    if not gtin or not accept:
        return None
    if not gtin_is_valid(gtin):
        raise CatalogError("O código de barras tem dígito verificador inválido.")
    product = _get_product(sku)
    # O código lido é a identidade do item: vai para o social, não para o rascunho.
    product.metadata = set_social_attributes(
        product.metadata, dc_replace(get_social_attributes(product.metadata), gtin=gtin))
    suggestion = enrichment.build_suggestion(gtin)
    product.metadata = enrichment.merge_into_metadata(product.metadata, suggestion)
    product.save(update_fields=["metadata", "updated_at"])
    names = [name for name in accept if name in enrichment.FIELD_LABELS]
    who = SimpleNamespace(get_username=lambda: actor or "catalogo")
    result = enrichment.accept_fields(product, names, replace=replace, user=who)
    return {
        "applied": list(result.applied),
        "conflicts": dict(result.conflicts),
        "refused": dict(result.refused),
        "sources": list(suggestion.sources),
        "notes": list(suggestion.notes),
    }

# ── GTIN recusado pela SEFAZ ──────────────────────────────────────────────────
# A nota que tomou a recusa já saiu de novo "SEM GTIN" (``shop.handlers.fiscal``)
# e o produto ficou marcado; a venda nunca esperou. O que sobra é gente com a
# embalagem na mão, e são dois desfechos:
#   - o código da embalagem é OUTRO: corrige o GTIN e salva. A marca sai, e a
#     próxima nota leva o código novo (a fonte passa a ser a embalagem);
#   - é o mesmo, ou o produto não tem código de barras: "Manter sem GTIN na
#     nota". A marca fica, com quem conferiu e quando, e o aviso se acalma.
# Nos dois casos o alerta daquele produto fecha.


def _settle_rejected_gtin(product, *, actor: str) -> bool:
    """GTIN corrigido depois da recusa: apaga a marca; ``True`` quando apagou.

    Salvar o MESMO código que a SEFAZ recusou não apaga nada: a nota seguinte
    seria recusada de novo. Um GTIN novo digitado aqui foi lido na embalagem
    (é o que o aviso pede), e por isso vira a fonte que decide a nota.
    """
    from django.utils import timezone
    from shopman.offerman import get_social_attributes

    from shopman.shop.services.fiscal import GTIN_NF_REJECTED_KEY

    metadata = dict(product.metadata or {})
    mark = metadata.get(GTIN_NF_REJECTED_KEY)
    if not isinstance(mark, dict):
        return False
    gtin = get_social_attributes(metadata).gtin.strip()
    if gtin == str(mark.get("gtin") or "").strip():
        return False
    metadata.pop(GTIN_NF_REJECTED_KEY)
    if gtin:
        metadata["gtin_source"] = f"embalagem, {actor or 'gestor'}, {timezone.localdate().isoformat()}"
    product.metadata = metadata
    return True


def _confirm_rejected_gtin(product, raw, *, actor: str) -> bool:
    """O gesto "Manter sem GTIN na nota": registra quem conferiu; a marca fica."""
    from django.utils import timezone

    from shopman.shop.services.fiscal import GTIN_NF_REJECTED_KEY

    if not isinstance(raw, dict) or set(raw) != {"confirmed"}:
        raise CatalogError("gtin_rejected aceita apenas a confirmação.")
    if not _as_flag(raw.get("confirmed"), "Manter sem GTIN na nota"):
        raise CatalogError("A confirmação do GTIN recusado não se desfaz: corrija o GTIN para voltar a mandá-lo.")
    metadata = dict(product.metadata or {})
    mark = metadata.get(GTIN_NF_REJECTED_KEY)
    if not isinstance(mark, dict):
        # Outra tela já corrigiu o GTIN: nada a confirmar, e não é erro.
        return False
    if mark.get("confirmed_at"):
        return False
    metadata[GTIN_NF_REJECTED_KEY] = {
        **mark,
        "confirmed_at": timezone.now().isoformat(),
        "confirmed_by": str(actor or "")[:100],
    }
    product.metadata = metadata
    return True


def _close_gtin_rejected_alerts(sku: str, *, actor: str) -> int:
    from shopman.backstage.services.alerts import resolve_alerts_ending_with
    from shopman.shop.services.fiscal import GTIN_REJECTED_ALERT_TYPE, gtin_rejected_alert_suffix

    return resolve_alerts_ending_with(
        GTIN_REJECTED_ALERT_TYPE,
        suffix=gtin_rejected_alert_suffix(sku),
        actor=actor or "catalogo",
    )


def _first_validation_message(exc) -> str:
    """Primeira mensagem legível de um ValidationError de campo (para o toast)."""
    messages = getattr(exc, "message_dict", None)
    if messages:
        for field, msgs in messages.items():
            if msgs:
                return f"{field}: {msgs[0]}"
    return "; ".join(exc.messages) if exc.messages else "Dados inválidos."


# ── assist de IA (sugestão POR CAMPO) ─────────────────────────────────────────
# O operador pede uma sugestão para UM campo e aceita ou descarta ela sozinha —
# não existe "gerar tudo". Por isso cada campo tem seu próprio prompt: pedir
# "descreva o produto" devolve o mesmo texto para a descrição curta, a longa e a
# legenda social, que são peças diferentes. O contexto do produto (nome, coleção,
# palavras-chave, campos já preenchidos) vai junto para a sugestão nascer coerente
# com o que já existe, em vez de genérica.

# A VOZ não vive mais aqui: era literal, invisível para quem opera e não editável — e a
# campanha não tinha voz nenhuma, então catálogo e anúncio soavam como duas lojas. Agora ela
# é `Shop.brand_voice`, lida por `shop/services/copy_assist.py`. Este módulo segue dono do
# que é DELE: o que pedir por campo.

# Um spec por campo assistível: o que pedir e quanto texto cabe na resposta.
_AI_ASSIST_FIELDS: dict[str, dict] = {
    "short_description": {
        "label": "descrição curta",
        "instruction": (
            "Escreva a descrição CURTA do produto: 1 a 2 frases, no máximo 200 caracteres, "
            "para listagens e vitrine. Destaque o que o cliente percebe (sabor, textura, "
            "método) em vez de repetir o nome do produto."
        ),
        "max_tokens": 300,
    },
    "long_description": {
        "label": "descrição longa",
        "instruction": (
            "Escreva a descrição COMPLETA da página do produto: 2 a 4 frases envolventes. "
            "Conte o método, os ingredientes que importam e quando esse produto cai bem. "
            "Não invente prêmios, origens, certificações nem prazos que não estejam no contexto."
        ),
        "max_tokens": 600,
    },
    "ingredients_text": {
        "label": "lista de ingredientes",
        "instruction": (
            "Escreva a lista de ingredientes em ordem decrescente de peso, como manda a "
            "ANVISA: nomes separados por vírgula, terminando em ponto final, sem quantidades "
            "e sem cabeçalho. Use apenas ingredientes plausíveis para este produto; se o "
            "contexto não permitir inferir com segurança, devolva a lista mais enxuta possível."
        ),
        "max_tokens": 300,
    },
    "social_caption": {
        "label": "legenda social",
        "instruction": (
            "Escreva a legenda para um post de Instagram/TikTok: 1 a 3 frases curtas, "
            "convidativas, que funcionem embaixo de uma foto do produto. Sem hashtags "
            "(elas têm campo próprio) e sem chamada para link na bio."
        ),
        "max_tokens": 400,
    },
    "hashtags": {
        "label": "hashtags",
        "instruction": (
            "Sugira de 5 a 8 hashtags relevantes para este produto em redes sociais, "
            "separadas por espaço, SEM o caractere '#' e sem vírgulas. Misture termos do "
            "produto, do método e da categoria. Exemplo de formato: paoartesanal fermentacaonatural padaria"
        ),
        "max_tokens": 200,
    },
}

ASSISTABLE_FIELDS: tuple[str, ...] = tuple(_AI_ASSIST_FIELDS)


def _ai_assist_context(product) -> str:
    """Contexto do produto para o prompt — só o que já está preenchido."""
    from shopman.offerman import get_social_attributes

    social = get_social_attributes(product)
    primary = next((ci for ci in product.collection_items.all() if ci.is_primary), None)
    lines = [
        f"Nome do produto: {product.name}",
        f"SKU: {product.sku}",
    ]
    optional = (
        ("Coleção", primary.collection.name if primary else ""),
        ("Palavras-chave", ", ".join(sorted(product.keywords.names()))),
        ("Unidade de venda", product.unit),
        ("Peso por unidade (g)", product.unit_weight_g),
        ("Descrição curta atual", product.short_description),
        ("Descrição longa atual", product.long_description),
        ("Ingredientes atuais", product.ingredients_text),
        ("Dica de conservação", product.storage_tip),
        ("Marca", social.brand),
        ("Categoria Google", social.google_product_category),
        ("Legenda social atual", social.social_caption),
        ("Hashtags atuais", " ".join(social.hashtags)),
    )
    lines.extend(f"{label}: {value}" for label, value in optional if value)
    return "\n".join(lines)


def _ai_assist_prompt(product, field: str, current_value: str) -> str:
    """Prompt do campo: contexto do produto + a tarefa específica daquele campo."""
    spec = _AI_ASSIST_FIELDS[field]
    parts = [
        "Contexto do produto:",
        _ai_assist_context(product),
        "",
        f"Tarefa (campo \"{spec['label']}\"):",
        spec["instruction"],
    ]
    if current_value.strip():
        parts += [
            "",
            "O campo já tem este texto. Proponha uma versão melhor, mantendo os fatos:",
            current_value.strip(),
        ]
    return "\n".join(parts)


def ai_assist_field(sku: str, field: str, current_value: str = "") -> str:
    """Sugestão de IA para UM campo de UM produto. Devolve o texto limpo.

    Levanta ``CatalogError`` (campo inválido / produto inexistente),
    ``AiAssistNotConfigured`` (sem ``AI_ASSIST_API_KEY`` → 503 na camada HTTP) ou
    ``AiAssistError`` (falha do provedor). ``hashtags`` volta como string separada
    por espaço — a superfície já normaliza texto livre em lista.
    """
    from shopman.backstage.services.exceptions import AiAssistError, AiAssistNotConfigured
    from shopman.shop.services import copy_assist

    if field not in _AI_ASSIST_FIELDS:
        raise CatalogError(
            f"Campo '{field}' não aceita sugestão de IA. Assistíveis: {', '.join(ASSISTABLE_FIELDS)}."
        )

    product = _get_product(sku)
    prompt = _ai_assist_prompt(product, field, current_value or "")

    # O transporte e a voz são do `copy_assist`; o que pedir por campo é daqui. As
    # exceções são traduzidas para as do backstage porque a camada HTTP já mapeia estas
    # (503 para "não configurado"), e um segundo dialeto de erro não ajudaria ninguém.
    try:
        return copy_assist.suggest(prompt, max_tokens=_AI_ASSIST_FIELDS[field]["max_tokens"])
    except copy_assist.CopyAssistNotConfigured as exc:
        raise AiAssistNotConfigured(str(exc)) from exc
    except copy_assist.CopyAssistError as exc:
        raise AiAssistError(str(exc)) from exc


# ── reordenação (curadoria da vitrine) ─────────────────────────────────────────
# A ordem do cardápio vive em Collection.sort_order (seções) e CollectionItem.sort_order
# (produtos dentro da coleção). Storefront, menuboard e feeds usam essa ordem.


def _curation_snapshot(collection_ref: str = "", *, lock: bool = False):
    """Read the canonical ordering and membership; locking callers are atomic."""
    from shopman.offerman.models import Collection, CollectionItem

    from shopman.shop.services.remote_mutations import mutation_fingerprint

    groups = Collection.objects.all()
    if lock:
        groups = groups.select_for_update()
    if collection_ref:
        group = groups.filter(ref=collection_ref).first()
        if group is None:
            raise CatalogError("A coleção não foi encontrada.")
        if group.is_smart:
            raise CatalogError("Coleção por regra não tem ordem manual.")
        items = CollectionItem.objects.filter(collection=group).select_related("product").order_by("pk")
        if lock:
            items = items.select_for_update(of=("self",))
        records = list(items)
        rows = [(item.pk, item.product.sku, item.sort_order) for item in records]
        context = {"ref": group.ref, "active": group.is_active, "rule": group.rule}
    else:
        records = list(groups.filter(is_active=True).order_by("pk"))
        rows = [(group.pk, group.ref, group.sort_order) for group in records]
        context = {"scope": "active-collections"}
    revision = mutation_fingerprint({"version": 1, "context": context, "rows": rows})
    return revision, records, [row[1] for row in rows]


def curation_revision(collection_ref: str = "") -> str:
    return _curation_snapshot(collection_ref)[0]


def _validate_curated_order(ordered, members, observed, expected):
    from shopman.backstage.services.exceptions import CatalogConflict

    if not isinstance(ordered, list) or any(not isinstance(value, str) for value in ordered):
        raise CatalogError("A ordem deve ser uma lista de referências.")
    if expected is not None and expected != observed:
        raise CatalogConflict("A ordem mudou durante a edição. Confira a ordem atual antes de aplicar seu arraste.")
    if len(ordered) != len(set(ordered)) or set(ordered) != set(members):
        raise CatalogError("A lista mudou ou está incompleta. Atualize e reordene o conjunto completo.")


@transaction.atomic
def reorder_collections(ordered_refs: list[str], *, actor: str = "", expected_revision: str | None = None) -> int:
    """Reorder exactly the observed active collections; preserve inactive groups."""
    from shopman.offerman.models import Collection

    revision, records, members = _curation_snapshot(lock=True)
    _validate_curated_order(ordered_refs, members, revision, expected_revision)
    positions = {ref: index for index, ref in enumerate(ordered_refs)}
    changed = []
    for group in records:
        if group.sort_order != positions[group.ref]:
            group.sort_order = positions[group.ref]
            changed.append(group)
    if changed:
        Collection.objects.bulk_update(changed, ["sort_order"])
        from shopman.shop.handlers._sse_emitters import emit_catalog_changed

        emit_catalog_changed()
    return len(changed)


@transaction.atomic
def reorder_collection_items(collection_ref: str, ordered_skus: list[str], *, actor: str = "", expected_revision: str | None = None) -> int:
    """Reorder exact manual membership under the collection and item locks."""
    from shopman.offerman.models import CollectionItem

    revision, records, members = _curation_snapshot(collection_ref, lock=True)
    _validate_curated_order(ordered_skus, members, revision, expected_revision)
    positions = {sku: index for index, sku in enumerate(ordered_skus)}
    changed = []
    for item in records:
        if item.sort_order != positions[item.product.sku]:
            item.sort_order = positions[item.product.sku]
            changed.append(item)
    if changed:
        CollectionItem.objects.bulk_update(changed, ["sort_order"])
        from shopman.shop.handlers._sse_emitters import emit_catalog_changed

        emit_catalog_changed()
    return len(changed)


# 100 destination cells is the measured provisional lab envelope, not a field SLA.
MAX_BULK_PRICE_CELLS = 100


def _bulk_selection(data: dict, *, lock: bool, allow_display: bool = False):
    from shopman.offerman.models import Collection, Listing, ListingItem, Product

    from shopman.shop.models import Channel
    surface = data.get("surface_ref")
    if not isinstance(surface, str) or not surface:
        raise CatalogError("surface_ref é obrigatório.")
    if surface != ALL_SURFACES:
        _refuse_mirror_surface(surface)
    refs = _all_channel_refs() if surface == ALL_SURFACES else [surface]
    channels = Channel.objects.filter(ref__in=refs).order_by("pk")
    if lock:
        channels = channels.select_for_update()
    channels = list(channels)
    if len(channels) != len(refs) or any(channel.commerce_policy != Channel.CommercePolicy.ORDER for channel in channels) and not (allow_display and len(channels) == 1 and channels[0].commerce_policy == Channel.CommercePolicy.DISPLAY):
        raise CatalogError("Selecione uma superfície existente compatível com a operação.")
    collection = None
    if data.get("collection_ref"):
        collections = Collection.objects.filter(ref=data["collection_ref"])
        collection = (collections.select_for_update() if lock else collections).first()
        if collection is None:
            raise CatalogError("Coleção não encontrada.")
        skus = list(collection.product_queryset().order_by("sku").values_list("sku", flat=True))
    else:
        skus = data.get("skus")
        if not isinstance(skus, list) or not skus or any(not isinstance(sku, str) or not sku.strip() for sku in skus):
            raise CatalogError("Informe collection_ref ou uma lista skus.")
        skus = sorted(set(skus))
    group_refs = [ref for channel in channels if channel.commerce_policy == Channel.CommercePolicy.DISPLAY
        for ref in ((channel.config or {}).get("display") or {}).get("collections", [])]
    groups = Collection.objects.filter(ref__in=group_refs).order_by("pk")
    groups = list(groups.select_for_update() if lock else groups)
    products = Product.objects.filter(sku__in=skus).order_by("pk")
    listings = Listing.objects.filter(ref__in=refs).order_by("pk")
    if lock:
        products, listings = products.select_for_update(), listings.select_for_update()
    products, listings = list(products), list(listings)
    if len(products) != len(skus):
        raise CatalogError("A seleção contém produto que não existe mais.")
    queryset = ListingItem.objects.filter(listing__ref__in=refs, product__sku__in=skus).order_by("listing_id", "product_id", "min_qty", "pk")
    if lock:
        queryset = queryset.select_for_update()
    all_items = list(queryset)
    return refs, channels, collection, skus, products, listings, all_items, groups


def _price_snapshot(data: dict, *, actor_id: int, lock: bool = False) -> tuple[dict, list]:
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    op, value = data.get("op"), data.get("value")
    if op not in _PRICE_OPS or not isinstance(value, int) or isinstance(value, bool):
        raise CatalogError("Informe operação de preço e valor inteiro válidos.")
    if op == "set" and value < 0:
        raise CatalogError("Preço não pode ser negativo.")
    refs, channels, collection, skus, products, listings, all_items, _groups = _bulk_selection(data, lock=lock)
    by_product = {product.pk: product for product in products}
    by_listing = {listing.pk: listing for listing in listings}
    seen = set()
    items, cells = [], []
    for item in all_items:
        identity = (item.listing_id, item.product_id)
        if identity in seen:
            continue
        seen.add(identity)
        product, listing = by_product[item.product_id], by_listing[item.listing_id]
        cells.append({"id": item.pk, "sku": product.sku, "surface_ref": listing.ref,
                      "tier": str(item.min_qty), "before_q": item.price_q,
                      "after_q": _apply_price_op(item.price_q, op, value)})
        items.append(item)
    if len(cells) > MAX_BULK_PRICE_CELLS:
        raise CatalogError(f"Selecione no máximo {MAX_BULK_PRICE_CELLS} células somando os canais.")
    state = {
        "actor": actor_id, "operation": "bulk-price", "op": op, "value": value,
        "skus": skus, "refs": refs, "cells": cells,
        "tiers": [(item.pk, str(item.min_qty), item.price_q, item.is_published, item.is_sellable) for item in all_items],
        "products": [(product.pk, product.base_price_q, product.is_published, product.is_sellable, product.metadata) for product in products],
        "listings": [(listing.pk, listing.is_active) for listing in listings],
        "channels": [(channel.pk, channel.is_active, channel.commerce_policy, channel.config) for channel in channels],
        "collection": (collection.ref, collection.rule) if collection else None,
    }
    from shopman.backstage.projections.catalog import CatalogPricePreview, CatalogPricePreviewCell

    preview = CatalogPricePreview(
        base_revision=mutation_fingerprint(state), expected_actor_id=actor_id,
        cells=tuple(CatalogPricePreviewCell(**cell) for cell in cells), limit=MAX_BULK_PRICE_CELLS,
    )
    return asdict(preview), items


def preview_bulk_price(data: dict, *, actor_id: int) -> dict:
    preview, _items = _price_snapshot(data, actor_id=actor_id)
    return preview


@transaction.atomic
def apply_bulk_price_intention(data: dict, *, actor_id: int) -> dict:
    from shopman.offerman.conf import get_projection_backend
    from shopman.offerman.models import ListingItem

    from shopman.backstage.services.exceptions import CatalogConflict
    from shopman.shop.handlers.catalog_projection import enqueue_project
    from shopman.shop.services.catalog_sync import record_sync

    preview, items = _price_snapshot(data, actor_id=actor_id, lock=True)
    if data.get("expected_actor_id") != actor_id or data.get("base_revision") != preview["base_revision"]:
        raise CatalogConflict("O catálogo ou a identificação mudou. Revise a prévia; nenhum preço foi alterado.")
    changed, pending = [], []
    surfaces = set()
    for item, cell in zip(items, preview["cells"], strict=True):
        if item.price_q == cell["after_q"]:
            continue
        item.price_q = cell["after_q"]
        changed.append(item)
        surfaces.add(cell["surface_ref"])
    ListingItem.objects.bulk_update(changed, ["price_q"])
    _realign_mirrors(surfaces)
    for cell in preview["cells"]:
        if cell["before_q"] == cell["after_q"] or get_projection_backend(cell["surface_ref"]) is None:
            continue
        record_sync(cell["sku"], cell["surface_ref"], status="pending")
        enqueue_project(cell["sku"], cell["surface_ref"], trigger="operator_price_intention")
        pending.append({"sku": cell["sku"], "surface_ref": cell["surface_ref"]})
    for surface in surfaces:
        transaction.on_commit(lambda ref=surface: _notify_surface(ref))
    return {"ok": True, "outcome": "applied", "count": len(changed), "cells": preview["cells"], "sync_pending": pending}


def _publication_snapshot(data: dict, *, actor_id: int, lock: bool = False) -> dict:
    from shopman.backstage.projections.catalog import (
        CatalogPublicationCell,
        CatalogPublicationPreview,
        CatalogPublicationSkip,
    )
    from shopman.shop.models import Channel
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    patch = {field: _as_flag(data[field], field) for field in ("is_published", "is_sellable") if field in data}
    if not patch:
        raise CatalogError("Informe is_published e/ou is_sellable.")
    refs, channels, collection, skus, products, listings, items, groups = _bulk_selection(data, lock=lock, allow_display=True)
    display = channels[0] if len(channels) == 1 and channels[0].commerce_policy == Channel.CommercePolicy.DISPLAY else None
    cells, skipped = [], []
    if display is not None:
        if set(patch) != {"is_sellable"}:
            raise CatalogError("Feed aceita apenas pausar/ativar (is_sellable).")
        membership = {sku for group in groups for sku in group.product_queryset().filter(sku__in=skus).values_list("sku", flat=True)}
        paused = ((display.config or {}).get("display") or {}).get("paused_skus") or []
        for sku in skus:
            if sku not in membership:
                skipped.append({"sku": sku, "surface_ref": display.ref, "reason": "Produto fora do recorte do feed."})
                continue
            before = {"is_sellable": sku not in paused}
            cells.append(CatalogPublicationCell(sku=sku, surface_ref=display.ref, tier="", before=before, after={**before, **patch}))
    else:
        by_product = {product.pk: product for product in products}
        by_listing = {listing.pk: listing for listing in listings}
        from shopman.shop.services.fiscal_catalog import validate_listing_item_publication

        for item in items:
            item.product, item.listing = by_product[item.product_id], by_listing[item.listing_id]
            before = {field: getattr(item, field) for field in ("is_published", "is_sellable")}
            after = {**before, **patch}
            for field, value in patch.items():
                setattr(item, field, value)
            validate_listing_item_publication(item)
            cells.append(CatalogPublicationCell(sku=item.product.sku, surface_ref=item.listing.ref,
                tier=str(item.min_qty), before=before, after=after))
        present = {(cell.sku, cell.surface_ref) for cell in cells}
        skipped = [{"sku": sku, "surface_ref": ref, "reason": "Produto sem célula neste canal."}
            for sku in skus for ref in refs if (sku, ref) not in present]
    if not cells:
        raise CatalogError("Nenhuma célula da seleção pertence ao destino.")
    if len(cells) > MAX_BULK_PRICE_CELLS:
        raise CatalogError(f"Selecione no máximo {MAX_BULK_PRICE_CELLS} células somando os canais e faixas.")
    state = {"version": 1, "actor": actor_id, "operation": "catalog.publication", "patch": patch,
        "skus": skus, "refs": refs, "cells": [asdict(cell) for cell in cells], "skipped": skipped,
        "items": [(item.pk, item.price_q) for item in items],
        "products": [(product.pk, product.base_price_q, product.is_published, product.is_sellable, product.metadata) for product in products],
        "listings": [(listing.pk, listing.is_active) for listing in listings],
        "channels": [(channel.pk, channel.is_active, channel.commerce_policy, channel.config) for channel in channels],
        "collection": (collection.ref, collection.rule) if collection else None,
        "groups": [(group.pk, group.rule) for group in groups]}
    return asdict(CatalogPublicationPreview(base_revision=mutation_fingerprint(state), expected_actor_id=actor_id,
        cells=tuple(cells), skipped=tuple(CatalogPublicationSkip(**cell) for cell in skipped), limit=MAX_BULK_PRICE_CELLS))


def preview_bulk_publication(data: dict, *, actor_id: int) -> dict:
    return _publication_snapshot(data, actor_id=actor_id)


@transaction.atomic
def apply_bulk_publication_intention(data: dict, *, actor_id: int) -> dict:
    from shopman.backstage.services.exceptions import CatalogConflict

    preview = _publication_snapshot(data, actor_id=actor_id, lock=True)
    if data.get("expected_actor_id") != actor_id or data.get("base_revision") != preview["base_revision"]:
        raise CatalogConflict("O catálogo ou a seleção mudou. Revise a prévia; nada foi alterado.")
    patch = {field: _as_flag(data[field], field) for field in ("is_published", "is_sellable") if field in data}
    # Frozen destinations from the validated snapshot; a newly created channel
    # cannot silently join the operator's intention between validation and commit.
    targets = sorted({cell["surface_ref"] for cell in preview["cells"]})
    for ref in targets:
        skus = sorted({cell["sku"] for cell in preview["cells"] if cell["surface_ref"] == ref})
        from django.contrib.auth import get_user_model
        actor = get_user_model().objects.get(pk=actor_id).get_username()
        bulk_set(skus, ref, actor=actor, **patch)
    changed = sum(cell["before"] != cell["after"] for cell in preview["cells"])
    return {"ok": True, "outcome": "applied", "count": changed, "cells": preview["cells"], "skipped": preview["skipped"]}


def resync_revision(product, targets: list[str]) -> str:
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    return mutation_fingerprint({"version": 1, "product_id": product.pk, "sku": product.sku, "targets": sorted(targets)})


def resync_snapshot(sku: str, *, lock: bool = False):
    from shopman.offerman.conf import get_projection_backend_channels
    from shopman.offerman.models import Product

    from shopman.shop.models import Channel

    channels = Channel.objects.filter(ref__in=get_projection_backend_channels(), is_active=True).order_by("pk")
    channels = list(channels.select_for_update() if lock else channels)
    products = Product.objects.filter(sku=sku)
    product = (products.select_for_update() if lock else products).first()
    if product is None:
        raise CatalogError("Produto não encontrado.")
    return product, sorted(channel.ref for channel in channels)


@transaction.atomic
def apply_resync_intention(data: dict) -> dict:
    from shopman.backstage.services.exceptions import CatalogConflict
    from shopman.shop.handlers.catalog_projection import enqueue_project
    from shopman.shop.services.catalog_sync import record_sync

    product, targets = resync_snapshot(data["sku"], lock=True)
    if data.get("base_revision") != resync_revision(product, targets):
        raise CatalogConflict("Os destinos de sincronização mudaram. Atualize antes de reenviar.")
    chosen = [data["channel_ref"]] if data.get("channel_ref") else targets
    if not chosen or any(ref not in targets for ref in chosen):
        raise CatalogError("Não há destino ativo e configurado para este reenvio.")
    tasks = []
    for ref in chosen:
        directive = enqueue_project(product.sku, ref, trigger="manual_resync")
        if directive is None or directive.status not in {"queued", "running"}:
            raise CatalogError("O enfileiramento não foi confirmado. Consulte novamente o resultado.")
        record_sync(product.sku, ref, status="pending")
        tasks.append({"channel_ref": ref, "directive_id": directive.pk, "status": directive.status})
    return {"ok": True, "outcome": "applied", "sku": product.sku, "channels": chosen, "tasks": tasks}


# ── import CSV de produto (pt-BR) ────────────────────────────────────────────
# Reusa o MESMO recurso do Admin (``ProductResource``, upsert por sku): o CSV
# tem as colunas do export, com separador ``;`` (vírgula é decimal) e a prévia
# roda em ``dry_run`` — o erro é POR LINHA e nada é gravado antes de confirmar.

_IMPORT_FLAGS = ("is_published", "is_sellable")
_PRODUCT_IMPORT_SALT = "catalog.product-import.v1"
_IMPORT_HEADERS = {
    "SKU": "sku", "Produto": "name", "Preço (R$)": "base_price_q",
    "Publicado": "is_published", "À venda": "is_sellable",
}
_IMPORT_INFORMATIONAL_HEADERS = {"Coleção (informativa)"}
_IMPORT_BOOL_TOKENS = {
    "sim": "1", "s": "1", "verdadeiro": "1", "true": "1",
    "não": "0", "nao": "0", "n": "0", "falso": "0", "false": "0",
}


def _import_price_q(value) -> str:
    """Preço do CSV em centavos. "5,00" e "5.00" viram 500; "500" já é centavo."""
    raw = str(value if value is not None else "").replace("R$", "").strip()
    if not raw:
        return ""
    if "," in raw:
        normalized = raw.replace(".", "").replace(",", ".")
    else:
        normalized = raw
    try:
        if "." in normalized:
            return str(int(round(float(normalized) * 100)))
        return str(int(normalized))
    except ValueError:
        # Valor torto fica como veio: quem recusa a linha é o recurso, com o erro.
        return raw


def _run_product_import(csv_text, *, dry_run: bool) -> dict:
    import csv
    import io

    import tablib
    from shopman.offerman import ProductResource

    text = str(csv_text or "").strip()
    if not text:
        raise CatalogError("Envie o arquivo CSV.")
    first = text.splitlines()[0]
    delimiter = ";" if first.count(";") >= first.count(",") and ";" in first else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    source_headers = [str(field).strip() for field in (reader.fieldnames or [])]
    if len(source_headers) != len(set(source_headers)):
        raise CatalogError("O cabeçalho do CSV tem colunas repetidas.")
    unknown = [header for header in source_headers if header not in _IMPORT_HEADERS
               and header not in _IMPORT_INFORMATIONAL_HEADERS and not header.startswith("Canal: ")]
    if unknown:
        raise CatalogError(f"O CSV tem colunas desconhecidas: {', '.join(unknown)}. Use o arquivo exportado pelo Catálogo.")
    if "SKU" not in source_headers:
        raise CatalogError("O CSV precisa da coluna SKU. Use o arquivo exportado pelo Catálogo.")
    headers = [_IMPORT_HEADERS[header] for header in source_headers if header in _IMPORT_HEADERS]
    dataset = tablib.Dataset()
    dataset.headers = headers
    parsed = []
    for raw in reader:
        source_row = {str(key).strip(): (value if value is not None else "") for key, value in raw.items() if key}
        if not any(str(value).strip() for value in source_row.values()):
            continue
        row = {_IMPORT_HEADERS[source]: source_row.get(source, "") for source in source_headers if source in _IMPORT_HEADERS}
        if "base_price_q" in row:
            row["base_price_q"] = _import_price_q(row["base_price_q"])
        for flag in _IMPORT_FLAGS:
            token = str(row.get(flag, "")).strip().lower()
            if token in _IMPORT_BOOL_TOKENS:
                row[flag] = _IMPORT_BOOL_TOKENS[token]
        dataset.append([row.get(header, "") for header in headers])
        parsed.append(row)
    if not parsed:
        raise CatalogError("O CSV não tem nenhuma linha para importar.")

    result = ProductResource().import_data(
        dataset, dry_run=dry_run, raise_errors=False, use_transactions=True,
    )
    errors = []
    for invalid in result.invalid_rows:
        messages = getattr(getattr(invalid, "error", None), "messages", None)
        errors.append({"row": invalid.number, "detail": "; ".join(str(item) for item in messages) if messages else str(invalid.error)})
    for error in result.error_rows:
        errors.append({"row": error.number, "detail": str(error.errors)})
    for index, row in enumerate(result.rows, start=1):
        if row.errors:
            errors.append({"row": index, "detail": "; ".join(str(item) for item in row.errors)})
    for base in result.base_errors:
        errors.append({"row": 0, "detail": str(getattr(base, "error", base))})
    payload = {
        "dry_run": dry_run,
        "rows": len(parsed),
        "totals": {key: int(value) for key, value in result.totals.items()},
        "errors": errors,
    }
    if dry_run:
        payload["changes"] = _import_changes(parsed)
    return payload


def _product_import_state(csv_text, *, lock: bool = False) -> list[list]:
    """Estado importável dos produtos-alvo, incluindo a ausência do SKU."""
    from shopman.offerman.models import Product

    preview = _run_product_import(csv_text, dry_run=True)
    skus = sorted({change["sku"] for change in preview["changes"] if change["sku"]})
    queryset = Product.objects.filter(sku__in=skus).order_by("sku")
    if lock:
        queryset = queryset.select_for_update()
    existing = {product.sku: product for product in queryset}
    fields = ("name", "base_price_q", "unit", "availability_policy", "is_published", "is_sellable", "shelf_life_days")
    return [[sku, *([getattr(existing[sku], field) for field in fields] if sku in existing else [None])] for sku in skus]


def _import_changes(parsed: list[dict]) -> list[dict]:
    from shopman.offerman.models import Product

    skus = [str(row.get("sku") or "").strip() for row in parsed]
    existing = {product.sku: product for product in Product.objects.filter(sku__in=skus)}
    changes = []
    for row in parsed:
        sku = str(row.get("sku") or "").strip()
        before = existing.get(sku)
        changes.append({
            "sku": sku,
            "action": "update" if before else "new",
            "name": str(row.get("name") or (before.name if before else "")),
            "before": {
                "name": before.name,
                "base_price_q": before.base_price_q,
                "is_published": before.is_published,
                "is_sellable": before.is_sellable,
            } if before else None,
        })
    return changes


def preview_product_import(data: dict, *, actor_id: int) -> dict:
    """Prévia do CSV: valida linha a linha e mostra o que muda. Não grava nada."""
    from django.core import signing

    from shopman.shop.services.remote_mutations import mutation_fingerprint

    csv_text = data.get("csv") if isinstance(data, dict) else None
    result = _run_product_import(csv_text, dry_run=True)
    result["base_revision"] = signing.dumps(
        {"actor": actor_id, "csv": mutation_fingerprint(str(csv_text or "")), "state": _product_import_state(csv_text)},
        salt=_PRODUCT_IMPORT_SALT,
        compress=True,
    )
    return result


@transaction.atomic
def apply_product_import(data: dict, *, actor_id: int) -> dict:
    """Aplica o CSV validado sem sobrescrever uma prévia obsoleta."""
    from django.core import signing

    from shopman.backstage.services.exceptions import CatalogConflict
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    csv_text = data.get("csv") if isinstance(data, dict) else None
    try:
        receipt = signing.loads(data.get("base_revision", ""), salt=_PRODUCT_IMPORT_SALT, max_age=1800)
    except (signing.BadSignature, TypeError):
        raise CatalogConflict("Refaça a prévia antes de importar.") from None
    expected = {"actor": actor_id, "csv": mutation_fingerprint(str(csv_text or "")), "state": _product_import_state(csv_text, lock=True)}
    if receipt != expected:
        raise CatalogConflict("O catálogo mudou desde a prévia. Refaça a prévia antes de importar.")
    validation = _run_product_import(csv_text, dry_run=True)
    if validation["errors"]:
        first = validation["errors"][0]
        detail = f"Nenhum produto foi importado. Confira a linha {first['row']}: {first['detail']}"
        return {"ok": False, "outcome": "not_applied", "detail": detail, **validation}
    result = _run_product_import(csv_text, dry_run=False)
    if result["errors"]:
        first = result["errors"][0]
        detail = f"Nenhum produto foi importado. Confira a linha {first['row']}: {first['detail']}"
        return {"ok": False, "outcome": "not_applied", "detail": detail, **result}
    return {"ok": True, "outcome": "applied", **result}
