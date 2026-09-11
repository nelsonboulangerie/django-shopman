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

from dataclasses import asdict
from math import isfinite

from django.db import transaction

from shopman.backstage.services.exceptions import CatalogError
from shopman.shop.services import attributes


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
    # `display` não tem. Seleção por política (ADR-018 §8).
    return list(
        Channel.objects.filter(
            is_active=True, commerce_policy=Channel.CommercePolicy.ORDER
        )
        .order_by("display_order", "id")
        .values_list("ref", flat=True)
    )


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


def cell_field_revisions(sku: str, surface_ref: str, *, item=None, display=None) -> dict[str, str]:
    """A cell's relevant canonical target and independent field values."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    if display is not None:
        config = (display.config or {}).get("display") or {}
        context = {"display_id": display.pk, "collections": config.get("collections") or []}
        values = {"is_sellable": sku not in (config.get("paused_skus") or [])}
    elif item is not None:
        context = {"item_id": item.pk, "product_id": item.product_id, "listing_id": item.listing_id, "tier": str(item.min_qty)}
        values = {field: getattr(item, field) for field in ("is_published", "is_sellable", "price_q")}
    else:
        return {}
    return {field: mutation_fingerprint({"version": 1, "sku": sku, "surface": surface_ref, "target": context, "field": field, "value": value})
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
    listing = Listing.objects.select_for_update().filter(ref=surface_ref).first()
    item = ListingItem.objects.select_for_update().filter(listing=listing, product=product).order_by("min_qty", "pk").first()
    if item is None:
        raise CatalogError(f"Produto '{sku}' não está na superfície '{surface_ref}'.")
    item.product, item.listing = product, listing
    _check_cell_revisions(patch, cell_field_revisions(sku, surface_ref, item=item), expected_revisions,
        {field: getattr(item, field) for field in ("price_q", "is_published", "is_sellable")})
    for field, value in patch.items():
        setattr(item, field, value)
    # Preserve the canonical save/history/signals, limiting the write to the patch.
    item.save(update_fields=list(patch))
    return item


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
        from shopman.backstage.services import feeds as display_service

        return display_service.set_items_paused(surface_ref, skus, paused=not is_sellable)
    updates: dict[str, bool] = {}
    if is_published is not None:
        updates["is_published"] = is_published
    if is_sellable is not None:
        updates["is_sellable"] = is_sellable
    if not updates:
        raise CatalogError("Nada a atualizar (informe is_published e/ou is_sellable).")

    from shopman.shop.services.fiscal_catalog import validate_listing_item_publication

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
        for item in items:
            item.product = by_product[item.product_id]
            item.listing = by_listing[item.listing_id]
            for field, value in updates.items():
                setattr(item, field, value)
            validate_listing_item_publication(item)
        count = ListingItem.objects.filter(pk__in=[item.pk for item in items]).update(**updates)
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
# ``full_clean()``. Fora do escopo: componentes de bundle, pertencimento a coleções
# e listings — seguem no Admin.
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
_DETAIL_BOOL_FIELDS = ("is_published", "is_sellable", "is_batch_produced")

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


def _detail_payload(product) -> dict:
    """Projection do detalhe: campos editáveis + contexto somente-leitura."""
    primary = next((ci for ci in product.collection_items.all() if ci.is_primary), None)
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
        "is_batch_produced": product.is_batch_produced,
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
        # Hora declarada de prontidão ("HH:MM", "" = deduzir do histórico). É o
        # que impede prometer a baguete de tradição para as 9h.
        "ready_from": str(metadata.get("ready_from") or ""),
        "nutrition_facts": _nutrition_payload(product),
        "social": _social_attrs_payload(product),
        "fiscal": _fiscal_payload(product),
        "primary_collection": primary.collection.ref if primary else "",
        "primary_collection_name": primary.collection.name if primary else "",
        # somente-leitura: o painel avisa que o dado veio da FICHA e que editar
        # à mão congela a derivação (ver ``dietary_from_recipe``). Vem da
        # proveniência do valor, não mais de um sentinela à parte.
        "dietary_from_recipe": _from_recipe(product),
        "nutrition_auto_filled": bool((product.nutrition_facts or {}).get("auto_filled", False)),
        "fiscal_profiles": _fiscal_profile_choices(),
    }



def product_field_revisions(detail: dict) -> dict[str, str]:
    """Tokens for editable leaf fields, derived from the canonical read payload."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    readonly = {"sku", "primary_collection", "primary_collection_name", "dietary_from_recipe", "nutrition_auto_filled", "fiscal_profiles"}
    values = _patch_leaves({key: value for key, value in detail.items() if key not in readonly})
    return {path: mutation_fingerprint({"version": 1, "sku": detail["sku"], "field": path, "value": value})
        for path, value in values.items() if path not in {"nutrition_facts.auto_filled", "social.has_data"}}


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

    product = Product.objects.select_for_update().filter(sku=sku).first()
    if product is None:
        raise CatalogError(f"Produto '{sku}' não encontrado.")
    if expected_revisions is not None:
        _check_product_revisions(product, data, expected_revisions)
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
    if "social" in data:
        _apply_social(product, data.get("social"))
    if "fiscal" in data:
        _apply_fiscal(product, data.get("fiscal"))

    # Global availability already had strict flag parsing and save's fiscal gate.
    # Do not turn a pause into a mandatory review of untouched legacy label data.
    if not set(data).issubset({"is_published", "is_sellable"}):
        try:
            product.full_clean()
        except ValidationError as exc:
            raise CatalogError(_first_validation_message(exc)) from exc

    product.save()

    if keywords is not None:
        product.keywords.set(keywords)

    product.refresh_from_db()
    return _detail_payload(product)


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
        f"Tarefa — campo \"{spec['label']}\":",
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
    return len(changed)


# 100 destination cells is the measured provisional lab envelope, not a field SLA.
MAX_BULK_PRICE_CELLS = 100


def _bulk_selection(data: dict, *, lock: bool, allow_display: bool = False):
    from shopman.offerman.models import Collection, Listing, ListingItem, Product

    from shopman.shop.models import Channel
    surface = data.get("surface_ref")
    if not isinstance(surface, str) or not surface:
        raise CatalogError("surface_ref é obrigatório.")
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
        bulk_set(skus, ref, **patch)
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
