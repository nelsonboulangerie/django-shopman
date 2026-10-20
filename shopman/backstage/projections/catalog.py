"""
Catalog matrix projection — produto × superfície para o Gestor.

Cada superfície é um Channel (capacidade + fonte de conteúdo resolvidas do
ChannelConfig); cada célula (produto × superfície) reflete o ListingItem daquela
listing (convenção listing.ref == channel.ref). Estado por célula = produto-level
AND listing-level (ambos precisam concordar para o item estar disponível).

Read-only. Frozen dataclasses convertidos por ``backstage.api.projections.projection_data``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from shopman.utils.monetary import format_money

from shopman.shop.projections.types import Action


def product_detail_action(sku: str, detail: dict, user):
    from shopman.backstage.services.catalog import product_field_revisions
    from shopman.shop.projections.types import Action
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    revisions = product_field_revisions(detail)
    allowed = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_catalog"))
    return Action(ref="edit-product", kind="mutation", label="Salvar produto", enabled=allowed,
        reason="" if allowed else "Identifique uma pessoa com permissão para editar o catálogo.",
        method="PATCH", idempotency="required", payload_schema={"expected_actor_id": getattr(user, "pk", None),
            "base_revision": mutation_fingerprint({"sku": sku, "revisions": revisions}), "base_revisions": revisions})


def product_create_action(user):
    """A intenção de criar um produto novo, com a revisão que a superfície carrega."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    actor_id = getattr(user, "pk", None)
    allowed = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_catalog"))
    return Action(ref="create-product", kind="mutation", label="Novo produto", enabled=allowed,
        reason="" if allowed else "Sem permissão para editar o catálogo.",
        method="POST", idempotency="required",
        payload_schema={"expected_actor_id": actor_id,
            "base_revision": mutation_fingerprint({"operation": "catalog.product-create", "actor": actor_id})})


def product_duplicate_action(sku: str, user):
    """A intenção de duplicar UM produto, com a revisão do conteúdo copiável."""
    from shopman.backstage.services.catalog import product_duplicate_revision

    actor_id = getattr(user, "pk", None)
    allowed = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_catalog"))
    revision = product_duplicate_revision(sku) if allowed else ""
    return Action(ref="duplicate-product", kind="mutation", label="Duplicar produto",
        enabled=allowed, reason="" if allowed else "Sem permissão para editar o catálogo.",
        method="POST", idempotency="required",
        payload_schema={"expected_actor_id": actor_id, "base_revision": revision, "ref": sku})

def product_switch_action(product, user):
    # Same field tokens and writer as the full editor, without loading long fields.
    action = product_detail_action(product.sku, {"sku": product.sku,
        "is_published": product.is_published, "is_sellable": product.is_sellable}, user)
    return replace(action, ref="toggle-product", label="Disponibilidade em todas as superfícies", method="POST",
        payload_schema={**action.payload_schema, "ref": product.sku})


def resync_action(product, targets: list[str], user):
    from shopman.backstage.services.catalog import resync_revision

    allowed = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_catalog"))
    enabled = allowed and bool(targets)
    return Action(ref="resync", kind="mutation", label="Reenviar às plataformas", enabled=enabled,
        reason="" if enabled else "Nenhum destino ativo e configurado." if allowed else "Sem permissão para editar o catálogo.",
        method="POST", idempotency="required", payload_schema={"ref": product.sku,
            "expected_actor_id": getattr(user, "pk", None), "base_revision": resync_revision(product, targets), "targets": sorted(targets)})


def cell_action(sku: str, surface_ref: str, user, *, item=None, display=None, available=True):
    from shopman.backstage.services.catalog import cell_field_revisions
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    revisions = cell_field_revisions(sku, surface_ref, item=item, display=display)
    allowed = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_catalog"))
    reason = "" if allowed and available else "O produto não pertence a esta superfície." if not available else "Sem permissão para editar o catálogo."
    return Action(ref="edit-cell", kind="mutation", label="Alterar célula", enabled=allowed and available,
        reason=reason, method="POST", idempotency="required", payload_schema={
            "base_revision": mutation_fingerprint({"sku": sku, "surface": surface_ref, "revisions": revisions}),
            "base_revisions": revisions, "expected_actor_id": getattr(user, "pk", None), "sku": sku, "surface_ref": surface_ref,
            "ref": mutation_fingerprint({"sku": sku, "surface": surface_ref}),
        })


def curation_actions(collection_ref: str, user):
    from shopman.backstage.services.catalog import curation_revision
    from shopman.backstage.services.exceptions import CatalogError
    from shopman.shop.projections.types import Action

    allowed = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_catalog"))
    actions = []
    scopes = [("reorder-collections", "", "Ordenar coleções")]
    if collection_ref:
        scopes.append(("reorder-items", collection_ref, "Ordenar produtos"))
    for operation, ref, label in scopes:
        try:
            revision = curation_revision(ref)
            reason = "" if allowed else "Sem permissão para editar o catálogo."
        except CatalogError as exc:
            revision, reason = "", str(exc)
        actions.append(Action(ref=operation, kind="mutation", label=label, enabled=allowed and not reason,
            reason=reason, method="POST", idempotency="required", payload_schema={
                "base_revision": revision, "expected_actor_id": getattr(user, "pk", None), "ref": ref,
            }))
    return tuple(actions)


@dataclass(frozen=True)
class CatalogPricePreviewCell:
    id: int
    sku: str
    surface_ref: str
    tier: str
    before_q: int
    after_q: int


@dataclass(frozen=True)
class CatalogPricePreview:
    base_revision: str
    expected_actor_id: int
    cells: tuple[CatalogPricePreviewCell, ...]
    limit: int


@dataclass(frozen=True)
class CatalogPublicationCell:
    sku: str
    surface_ref: str
    tier: str
    before: dict[str, bool]
    after: dict[str, bool]


@dataclass(frozen=True)
class CatalogPublicationSkip:
    sku: str
    surface_ref: str
    reason: str


@dataclass(frozen=True)
class CatalogPublicationPreview:
    base_revision: str
    expected_actor_id: int
    cells: tuple[CatalogPublicationCell, ...]
    skipped: tuple[CatalogPublicationSkip, ...]
    limit: int


def _money(value_q: int) -> str:
    return f"R$ {format_money(int(value_q))}"


def _edit_url(product) -> str:
    """Deep-link canônico p/ a edição do produto no Admin/Unfold."""
    from django.urls import NoReverseMatch, reverse

    try:
        return reverse(
            f"admin:{product._meta.app_label}_{product._meta.model_name}_change",
            args=[product.pk],
        )
    except NoReverseMatch:
        return ""


@dataclass(frozen=True)
class SurfaceProjection:
    """Uma superfície — coluna da matriz. Canal (transaciona) ou Feed (só exibe)."""

    ref: str
    name: str
    # Rótulo curto do cabeçalho da coluna (a matriz é estreita). Nunca vazio: cai
    # para `name` quando não há um curto configurado. O `name` completo segue no
    # tooltip da coluna e em toda lista onde há espaço.
    short_name: str
    is_projection_target: bool  # tem backend na registry canônica (Frente 1) — ex.: iFood
    sync_status: str  # ok | error | never | na
    kind: str = "channel"  # channel (transacional) | display (menuboard) | feed (Google/Meta)
    transactional: bool = True  # canal vende (preço/publicação); feed só exibe (pausa)
    icon: str = ""  # dica de ícone p/ feeds (tv/rss)
    output_path: str = ""  # saída pública do feed (abrir/prever); vazio p/ canal
    sync_key: str = ""  # ref do canal — a MESMA chave para transacional e exibição


@dataclass(frozen=True)
class SurfaceCellProjection:
    """Célula produto × superfície."""

    surface_ref: str
    in_listing: bool  # o produto está nesta listing?
    is_published: bool  # listing-level
    is_sellable: bool  # listing-level
    available: bool  # produto-level AND listing-level
    price_q: int | None
    price_display: str
    # Estado de sync por (produto × plataforma) — CatalogSyncState (Arc C). Só faz
    # sentido em superfície que é alvo de projeção (canal com backend na registry);
    # vazio quando nunca houve push ou a superfície não projeta (feed de pull).
    valid_from: str = ""
    valid_until: str = ""
    sync_status: str = ""  # synced | pending | error | retracted | skipped | "" (nunca)
    sync_error: str = ""  # última mensagem de erro (quando status=error)
    synced_at: str = ""  # ISO do último push OK (synced/retracted)
    pause_audit: str = ""
    action: Action | None = None


@dataclass(frozen=True)
class CatalogRowProjection:
    """Uma linha da matriz — um produto e suas células por superfície."""

    sku: str
    name: str
    image_url: str
    primary_collection: str  # ref
    primary_collection_name: str
    is_active: bool  # cadastro presente na operação; falso = arquivado
    is_published: bool  # produto-level
    is_sellable: bool  # produto-level
    base_price_q: int
    base_price_display: str
    edit_url: str  # deep-link p/ a página de edição do produto (Admin/Unfold)
    # estoque (produto-level, do loop produção→estoque→disponibilidade). Esgotado é
    # ortogonal a Pausado: não mexe no switch; a próxima fornada repõe sozinho.
    stock_tracked: bool  # há controle de estoque para este SKU?
    stock_qty: int | None  # promissível agora (None = sem controle)
    sold_out: bool  # rastreado e sem estoque para vender
    low_stock: bool  # rastreado, pouco estoque (≤ threshold do canal)
    replenish_qty: int  # vindo por produção (planejado + em produção) — "fornada"
    keywords: tuple[str, ...]
    cells: tuple[SurfaceCellProjection, ...]  # alinhado à ordem de ``surfaces``
    # PIM social (Arc A) — atributos de catálogo social em Product.metadata['social'],
    # lidos por get_social_attributes. Alimentam o painel PIM e sinalizam prontidão de
    # feed (Google/Meta/TikTok exigem brand + categoria). Ver ``_social_view``.
    social: dict
    pim_complete: bool  # tem o essencial p/ publicar em feed (brand + categoria Google)
    # O produto passa por todos os portões do cardápio (publicado, na vitrine, com
    # preço) e mesmo assim não aparece em grupo nenhum: o único vínculo de coleção
    # dele é com uma coleção DESATIVADA, e o balde "sem categoria" só recolhe quem
    # não tem vínculo algum. Não é pausa nem ocultação — é efeito colateral, e por
    # isso não cabe nos estados existentes da linha. Ver
    # ``shop.services.catalog_visibility``.
    hidden_by_inactive_collection: bool = False
    # Tem vocação (``ProductConsumptionTag``)? Só o B.I. lê a vocação; aqui ela
    # serve ao filtro "Sem vocação" e ao aviso discreto da lista.
    has_vocation: bool = False
    product_action: Action | None = None
    resync_action: Action | None = None


@dataclass(frozen=True)
class CollectionProjection:
    """Coleção — alça do eixo coleção (filtro/agrupamento/bulk)."""

    ref: str
    name: str
    is_smart: bool
    product_count: int


@dataclass(frozen=True)
class VocationPendingProjection:
    """Produto à venda sem vocação — o aviso "Classificar" da lista."""

    sku: str
    name: str


@dataclass(frozen=True)
class CatalogFacetsProjection:
    """Contagens por opção das facetas de multi-escolha, do RECORTE ATUAL.

    Cada dimensão conta sobre o recorte inteiro (coleção, busca, superfície e
    os outros filtros ativos), nunca só a página: era a mentira que tirou as
    facetas do painel quando a lista virou paginada. A seleção da PRÓPRIA
    dimensão não entra na conta — a opção diz quantos itens casariam se fosse
    marcada, com o resto do recorte como está.

    As chaves são os valores das opções:
    - ``stock``: ``ok`` | ``low`` | ``out``;
    - ``sync_status``: ``synced`` | ``pending`` | ``error`` | ``never``.

    PIM é boolean (Sim/Não), sem contagem por opção; canal/feed já carrega o
    total do recorte. ``retracted`` e ``skipped`` aparecem no selo da célula,
    mas não são opções de recorte: quem os separa no painel não teria o que
    fazer com a distinção.
    """

    stock: dict[str, int] = field(default_factory=dict)
    sync_status: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogMatrixProjection:
    surfaces: tuple[SurfaceProjection, ...]
    rows: tuple[CatalogRowProjection, ...]
    collections: tuple[CollectionProjection, ...]
    # Contagens por opção das facetas de multi-escolha, do recorte atual.
    facets: CatalogFacetsProjection = field(default_factory=CatalogFacetsProjection)
    # Da loja inteira, não do recorte de coleção: o aviso diz quantos faltam
    # classificar, esteja a lista filtrada ou não.
    vocation_pending: tuple[VocationPendingProjection, ...] = ()
    # Paginação/filtro/ordenação no SERVIDOR: a matriz não vem mais inteira, e o
    # navegador não monta uma linha por produto do catálogo.
    total: int = 0
    page: int = 1
    page_size: int = 0
    has_next: bool = False
    order: str = "name"
    query: str = ""
    date_from: str = ""
    date_to: str = ""


# ── builders ────────────────────────────────────────────────────────────────


_EMPTY_STOCK = {
    "stock_tracked": False,
    "stock_qty": None,
    "sold_out": False,
    "low_stock": False,
    "replenish_qty": 0,
}


def _stock_view(info: dict | None, low_stock_threshold: int, replenish_qty: int) -> dict:
    """Deriva o estado de estoque da linha a partir do dict canônico de availability.

    Esgotado = rastreado e sem promissível AGORA. ``replenish_qty`` vem de uma consulta
    SEPARADA (fornadas futuras) — não do promissível-agora — pra não mascarar o esgotado.
    """
    if not info or not info.get("is_tracked", True):
        return {**_EMPTY_STOCK, "replenish_qty": max(int(replenish_qty or 0), 0)}
    promisable = int(info.get("total_promisable") or 0)
    sold_out = promisable <= 0
    return {
        "stock_tracked": True,
        "stock_qty": promisable,
        "sold_out": sold_out,
        "low_stock": (not sold_out) and promisable <= max(int(low_stock_threshold or 0), 0),
        "replenish_qty": max(int(replenish_qty or 0), 0),
    }


#: Baldes de estoque da faceta, na ordem em que o painel os mostra.
_STOCK_BUCKETS = ("ok", "low", "out")


def _stock_bucket(info: dict | None, low_stock_threshold: int) -> str:
    """Balde de UMA linha: esgotado vence estoque baixo; sem rastro, ``ok``."""
    view = _stock_view(info, low_stock_threshold, 0)
    if view["sold_out"]:
        return "out"
    if view["low_stock"]:
        return "low"
    return "ok"


def _stock_for(skus: list[str]) -> tuple[dict[str, dict | None], int, dict[str, int]]:
    """Availability-agora (canal representante) + threshold + suprimento planejado.

    Estoque é físico/produto-level; usa o scope de UM canal representante (o de menor
    ``display_order``). ``planned`` é uma consulta separada (fornadas futuras próximas).
    Degrada em silêncio (sem Stockman → vazio → tudo untracked → como hoje).
    """
    from shopman.shop.config import ChannelConfig
    from shopman.shop.models import Channel

    # Canal `display` não vende, logo não representa escopo de estoque.
    rep = (
        Channel.objects.filter(
            is_active=True, commerce_policy=Channel.CommercePolicy.ORDER
        )
        .order_by("display_order", "id")
        .first()
    )
    if rep is None or not skus:
        return {}, 0, {}
    threshold = int(getattr(ChannelConfig.for_channel(rep).stock, "low_stock_threshold", 0) or 0)

    from shopman.shop.projections import catalog_context

    availability = catalog_context.availability_for_skus(skus, channel_ref=rep.ref)
    planned = catalog_context.planned_supply_for_skus(skus)
    return availability, threshold, planned


def _social_view(product) -> tuple[dict, bool]:
    """Atributos PIM sociais da linha + prontidão de feed.

    ``pim_complete`` = tem o mínimo p/ um feed comercial (Google/Meta/TikTok): marca
    e categoria Google. GTIN/condição são refinamentos, não bloqueiam o sinal verde.
    """
    from shopman.offerman import get_social_attributes

    attrs = get_social_attributes(product)
    view = {
        "brand": attrs.brand,
        "gtin": attrs.gtin,
        "mpn": attrs.mpn,
        "condition": attrs.condition,
        "google_product_category": attrs.google_product_category,
        "tiktok_category_id": attrs.tiktok_category_id,
        "hashtags": list(attrs.hashtags),
        "social_caption": attrs.social_caption,
        "has_data": attrs.has_data,
    }
    complete = bool(attrs.brand and attrs.google_product_category)
    return view, complete


def _cell_sync(sync_map: dict, sku: str, surface_ref: str) -> tuple[str, str, str]:
    """(status, error, synced_at) do CatalogSyncState p/ (sku, surface_ref) — ou vazios."""
    rec = sync_map.get(sku, {}).get(surface_ref)
    if not rec:
        return "", "", ""
    return rec.get("status") or "", rec.get("error") or "", rec.get("last_synced_at") or ""


#: Baldes de envio da faceta. ``retracted``/``skipped`` têm selo na célula, mas não
#: viram opção de recorte — ver ``CatalogFacetsProjection``.
_SYNC_BUCKETS = ("synced", "pending", "error", "never")


def _sync_buckets(members_by_target: dict[str, set[str]], sync_map: dict) -> dict[str, set[str]]:
    """Baldes de envio por SKU, das células das superfícies-alvo.

    Um SKU casa um balde quando ALGUMA superfície-alvo o oferta e o último envio
    (``CatalogSyncState``) está naquele estado; sem registro nenhum, o balde é
    ``never``. A lista de alvos importa: só conta superfície com backend de
    projeção (canal ou feed que projeta); as demais não têm envio para filtrar.
    """
    buckets: dict[str, set[str]] = {}
    for surface_key, members in members_by_target.items():
        for sku in members:
            status = sync_map.get(sku, {}).get(surface_key, {}).get("status") or ""
            buckets.setdefault(sku, set()).add(status or "never")
    return buckets


def _surface_sync_status(listing, is_projection_target: bool) -> str:
    if not is_projection_target:
        return "na"
    meta = listing.projection_metadata if listing else {}
    if meta.get("last_error"):
        return "error"
    if meta.get("last_projected_skus"):
        return "ok"
    return "never"


def _build_surfaces() -> tuple[list[SurfaceProjection], dict[str, dict]]:
    """Retorna as superfícies + um índice {surface_ref: {sku: ListingItem}}."""
    from shopman.offerman.conf import get_projection_backend
    from shopman.offerman.models import Listing, ListingItem

    from shopman.shop.models import Channel

    # Canal `display` não é coluna de canal: ele é superfície de exibição, montada
    # pelo caminho de feed. Sem este filtro a matriz duplicaria cada feed/TV — uma
    # vez como canal, outra como feed (ADR-018 §8: seleção por política, nunca por ref).
    from shopman.shop.services.channel_switch import effective_active

    # Desligado no toggle da aba Canais = fora das colunas (só a aba Canais o
    # mostra, para religar). O período vale pelo relógio, não pelo carimbo.
    channels = [
        channel
        for channel in Channel.objects.filter(
            commerce_policy=Channel.CommercePolicy.ORDER
        ).order_by("display_order", "id")
        if effective_active(channel)
    ]
    listings = {lst.ref: lst for lst in Listing.objects.all()}

    # índice de células: surface_ref → sku → ListingItem (tier base = menor min_qty)
    cells_index: dict[str, dict] = {}
    items = (
        ListingItem.objects.filter(listing__ref__in=[c.ref for c in channels])
        .select_related("product", "listing")
        .order_by("product__sku", "min_qty")
    )
    for item in items:
        bucket = cells_index.setdefault(item.listing.ref, {})
        bucket.setdefault(item.product.sku, item)  # primeiro = menor min_qty

    surfaces: list[SurfaceProjection] = []
    for ch in channels:
        is_target = get_projection_backend(ch.ref) is not None
        # `short_name` é chave de ChannelConfig, lida direto do override do canal:
        # é presentação POR canal (não há default de loja que faça sentido), e assim
        # evitamos um Shop.load() por canal só para resolver a cascata.
        short = str((ch.config or {}).get("short_name", "")).strip()
        surfaces.append(
            SurfaceProjection(
                ref=ch.ref,
                name=ch.name or ch.ref,
                short_name=short or ch.name or ch.ref,
                is_projection_target=is_target,
                sync_status=_surface_sync_status(listings.get(ch.ref), is_target),
                kind="channel",
                transactional=True,
                sync_key=ch.ref,
            )
        )
    return surfaces, cells_index


# capability/ícone por formato de exibição. Formato VAZIO é quadro (rota nossa);
# formato preenchido é feed de plataforma (dialeto de terceiro).
_DISPLAY_META = {
    "": {"capability": "display", "icon": "tv", "path": "/menuboard/{ref}/"},
    "google_merchant": {"capability": "feed", "icon": "rss", "path": "/feed/{ref}.xml"},
    "meta_catalog": {"capability": "feed", "icon": "rss", "path": "/feed/{ref}.xml"},
}


def _build_display_surfaces() -> tuple[list[SurfaceProjection], dict[str, dict]]:
    """Canais de EXIBIÇÃO como colunas + índice {ref: {"members", "paused"}}.

    ``members`` = SKUs que o canal exibe (união dos produtos das suas coleções).
    ``paused`` = pausa LOCAL do item neste canal (a global é do produto, gate por cima).

    Eram um model próprio (``Feed``) até a ADR-018. Duas consequências aparecem
    aqui: o ``sync_key`` passa a ser o **ref** (era o ``kind``, então canal chaveava
    por ref e feed por kind — duas chaves para a mesma pergunta), e o ``?channel_ref=``
    saiu do ``output_path``, porque o formato é propriedade do canal e não parâmetro
    de query.

    ⚠️ Este enumerador e o ``_build_surfaces`` **se excluem por política**:
    ``ORDER`` lá, ``DISPLAY`` aqui. Sem isso a matriz duplica cada TV/feed — uma vez
    como canal, outra como exibição. Foi o erro que a linha de base pegou (11
    superfícies, 4 duplicadas) quando a absorção entrou sem o filtro.
    """
    from shopman.offerman.conf import get_projection_backend
    from shopman.offerman.models import Collection

    from shopman.shop.models import Channel
    from shopman.shop.services.channel_switch import effective_active

    # Feed/TV desligado sai das colunas, igual ao canal de venda desligado.
    channels = [
        channel
        for channel in Channel.objects.filter(
            commerce_policy=Channel.CommercePolicy.DISPLAY
        ).order_by("name")
        if effective_active(channel)
    ]
    if not channels:
        return [], {}

    def _display(ch) -> dict:
        return (ch.config or {}).get("display") or {}

    # resolve os SKUs de cada coleção uma única vez (reuso entre canais)
    needed_refs = {r for ch in channels for r in (_display(ch).get("collections") or [])}
    members_by_coll: dict[str, set[str]] = {}
    for coll in Collection.objects.filter(ref__in=needed_refs):
        members_by_coll[coll.ref] = set(coll.product_queryset().values_list("sku", flat=True))

    surfaces: list[SurfaceProjection] = []
    index: dict[str, dict] = {}
    for ch in channels:
        display = _display(ch)
        fmt = display.get("format") or ""
        meta = _DISPLAY_META.get(fmt, {"capability": "display", "icon": "monitor", "path": ""})
        members: set[str] = set()
        for r in display.get("collections") or []:
            members |= members_by_coll.get(r, set())
        index[ch.ref] = {
            "members": members,
            "paused": {str(s) for s in (display.get("paused_skus") or [])},
            "pause_audit": display.get("pause_audit") or {},
            "channel": ch,
        }
        is_target = get_projection_backend(ch.ref) is not None
        short = str((ch.config or {}).get("short_name", "")).strip()
        surfaces.append(
            SurfaceProjection(
                ref=ch.ref,
                name=ch.name or ch.ref,
                short_name=short or ch.name or ch.ref,
                is_projection_target=is_target,
                sync_status=_surface_sync_status(None, is_target),
                sync_key=ch.ref,
                kind=meta["capability"],
                transactional=False,
                icon=meta["icon"],
                output_path=meta["path"].format(ref=ch.ref),
            )
        )
    return surfaces, index


#: Ordenações que o servidor aceita (colunas reais; nunca uma ordem inventada).
_CATALOG_ORDERS: dict[str, tuple[str, ...]] = {
    "name": ("name", "sku"),
    "-name": ("-name", "sku"),
    "sku": ("sku",),
    "-sku": ("-sku",),
    "price": ("base_price_q", "name"),
    "-price": ("-base_price_q", "name"),
    "updated": ("-updated_at",),
    "validity": ("_valid_from", "name", "sku"),
}

#: Teto de linhas por página. Acima disto a matriz volta a ser o que era.
MAX_CATALOG_PAGE_SIZE = 200


def build_catalog_matrix(collection_ref: str = "", *, user=None, query: str = "",
    order: str = "name", page: int = 1, page_size: int = 50,
    filters: dict | None = None, date_from: date | None = None, date_to: date | None = None) -> CatalogMatrixProjection:
    """Monta a matriz produto × superfície com o eixo coleção, PAGINADA.

    ``collection_ref`` (opcional) recorta os produtos daquela coleção, inclusive
    os arquivados quando esse é o filtro explícito. ``query`` busca em nome e SKU;
    ``filters`` aceita ``archived``/``is_published``/``is_sellable``/``has_vocation``/
    ``surface``/``stock``/``pim_complete``/``sync_status``; ``order`` é uma das
    chaves de ``_CATALOG_ORDERS``; a página é do BANCO — só as linhas dela viram
    projection. As coleções e a vocação pendente continuam da casa inteira.

    Semântica das facetas novas (envio, estoque e PIM), todas EM LOTE:

    - ``stock`` é por produto: balde ``ok``/``low``/``out`` (esgotado vence
      estoque baixo; produto sem rastro cai em ``ok``), o mesmo da coluna da linha.
    - ``pim_complete`` é por produto: tem marca e categoria Google? É o mesmo sinal
      de prontidão para feed que a linha mostra.
    - ``sync_status`` é por célula (produto × superfície): o produto casa o balde
      quando ALGUMA superfície-alvo o oferta e o último envio está naquele estado
      (``synced``/``pending``/``error``; sem registro nenhum, ``never``). Só conta
      superfície com backend de projeção — a lista de alvos importa. Com recorte de
      superfície ativo, o envio olha só as superfícies escolhidas.

    ``facets`` devolve a contagem por opção do RECORTE ATUAL, nunca só da página.
    A seleção da própria dimensão não entra na conta: a opção diz quantos itens
    casariam se fosse marcada, com o resto do recorte como está.
    """
    from shopman.offerman.models import Collection, Product

    surfaces, cells_index = _build_surfaces()
    from django.db.models import Max, Min, Q, Subquery
    from django.utils import timezone
    from shopman.offerman.models import ListingItem
    from shopman.offerman.smart_collection import resolve_products

    def collection_products(collection):
        if collection.is_smart:
            return resolve_products(collection.rule)
        return Product.objects.filter(collection_items__collection=collection).distinct()

    item_ids = [item.pk for cells in cells_index.values() for item in cells.values()]
    latest = ListingItem.history.filter(id__in=item_ids).values("id").annotate(last=Max("history_id")).values("last")
    pause_audit = {}
    for entry in ListingItem.history.filter(history_id__in=Subquery(latest), is_sellable=False,
            history_change_reason__endswith=":after").select_related("history_user"):
        actor = entry.history_user.get_username() if entry.history_user else "sistema"
        pause_audit[entry.id] = f"Pausado por {actor} em {timezone.localtime(entry.history_date):%d/%m/%Y %H:%M}"
    display_surfaces, display_index = _build_display_surfaces()
    surfaces = surfaces + display_surfaces

    # A consulta é do BANCO: busca, filtros simples e ordenação acontecem antes
    # de materializar. A página é o único recorte que vira linha na resposta.
    filters = filters or {}
    archived = bool(filters.get("archived"))
    products = Product.objects.all()
    collection_smart = False
    if collection_ref:
        coll = Collection.objects.filter(ref=collection_ref).first()
        if coll is None:
            products = products.none()
        else:
            collection_smart = coll.is_smart
            products = collection_products(coll)
    term = (query or "").strip()
    if term:
        products = products.filter(Q(name__icontains=term) | Q(sku__icontains=term))
    products = products.filter(is_active=not archived)
    if filters.get("is_published") is not None:
        products = products.filter(is_published=bool(filters["is_published"]))
    if filters.get("is_sellable") is not None:
        products = products.filter(is_sellable=bool(filters["is_sellable"]))
    if filters.get("has_vocation") is not None:
        # Vocação mora fora do produto (``ProductConsumptionTag``): o recorte é
        # por SKU, no banco, para o total e o has_next contarem o conjunto.
        from shopman.backstage.models import ProductConsumptionTag

        tagged = ProductConsumptionTag.objects.values_list("sku", flat=True)
        products = products.filter(sku__in=tagged) if filters["has_vocation"] else products.exclude(sku__in=tagged)
    surface_refs = [str(ref) for ref in (filters.get("surface") or []) if ref]
    if surface_refs:
        # Canal transaciona = tem ListingItem; feed = pertence às coleções do
        # recorte. As duas condições vão para a MESMA query, com distinct.
        feed_members: set[str] = set()
        clauses = Q()
        for ref in surface_refs:
            if ref in display_index:
                feed_members |= set(display_index[ref]["members"])
            else:
                clauses |= Q(listing_items__listing__ref=ref)
        if feed_members:
            clauses |= Q(sku__in=feed_members)
        products = products.filter(clauses).distinct()
    # A janela casa com ALGUM canal selecionado, com limites inclusivos. As
    # duas pontas devem pertencer à MESMA listing, não a canais diferentes.
    validity_items = ListingItem.objects.filter(listing__ref__in=[
        surface.ref for surface in surfaces if surface.transactional
        and (not surface_refs or surface.ref in surface_refs)
    ])
    if date_from is not None or date_to is not None:
        if date_from is not None:
            validity_items = validity_items.filter(
                Q(listing__valid_until__isnull=True) | Q(listing__valid_until__gte=date_from))
        if date_to is not None:
            validity_items = validity_items.filter(
                Q(listing__valid_from__isnull=True) | Q(listing__valid_from__lte=date_to))
        # Feed não tem preço próprio: seu recorte de curadoria continua válido
        # quando o operador o seleciona, inclusive junto de um canal de venda.
        selected_feed_skus = set().union(*(
            display_index[ref]["members"] for ref in surface_refs if ref in display_index
        ))
        products = products.filter(Q(pk__in=validity_items.values("product_id")) | Q(sku__in=selected_feed_skus))
    if order == "validity":
        products = products.annotate(_valid_from=Min("listing_items__listing__valid_from",
            filter=Q(listing_items__pk__in=validity_items.values("pk"))))
    # ── facetas de envio/estoque/PIM, EM LOTE ──────────────────────────────
    # Os candidatos são quem passou por coleção, busca, filtros simples e
    # superfície. Sobre eles, a leitura de cada faceta sai de uma vez (estoque,
    # sync e PIM) e o recorte final é um filtro por SKU: o número de consultas
    # não cresce com o tamanho do catálogo.
    stock_values = {str(value) for value in (filters.get("stock") or []) if str(value) in _STOCK_BUCKETS}
    sync_values = {str(value) for value in (filters.get("sync_status") or []) if str(value) in _SYNC_BUCKETS}
    pim_filter = filters.get("pim_complete")
    pim_filter = bool(pim_filter) if pim_filter is not None else None

    candidate_skus = list(dict.fromkeys(products.order_by().values_list("sku", flat=True)))
    stock_info, low_stock_threshold, planned_by_sku = _stock_for(candidate_skus)
    stock_buckets = {
        sku: _stock_bucket(stock_info.get(sku), low_stock_threshold) for sku in candidate_skus
    }

    # Estado de sync por (produto × plataforma) — uma consulta p/ todos os
    # candidatos. O envio olha só superfície-alvo; se a tela estreitou a
    # superfície, ele segue o mesmo estreitamento (o checklist "recusados pelo
    # iFood" não pode devolver erro de outra plataforma).
    from shopman.shop.services.catalog_sync import sync_status_map

    sync_map = sync_status_map(candidate_skus)
    members_by_surface = {
        surface.ref: (
            set(display_index[surface.ref]["members"])
            if surface.ref in display_index
            else set(cells_index.get(surface.ref, {}))
        )
        for surface in surfaces
    }
    target_members = {
        (surface.sync_key or surface.ref): members_by_surface[surface.ref]
        for surface in surfaces
        if surface.is_projection_target and (not surface_refs or surface.ref in surface_refs)
    }
    sync_buckets = _sync_buckets(target_members, sync_map)

    pim_skus: set[str] = set()
    if pim_filter is not None:
        from shopman.offerman import get_social_attributes

        # Só quando a faceta está ativa: o PIM é boolean, sem contagem por opção.
        for sku, metadata in products.order_by().values_list("sku", "metadata"):
            attrs = get_social_attributes(metadata)
            if attrs.brand and attrs.google_product_category:
                pim_skus.add(sku)

    def _passes_stock(sku: str) -> bool:
        return not stock_values or stock_buckets.get(sku, "ok") in stock_values

    def _passes_pim(sku: str) -> bool:
        return pim_filter is None or (sku in pim_skus) == pim_filter

    def _passes_sync(sku: str) -> bool:
        return not sync_values or bool(sync_buckets.get(sku, set()) & sync_values)

    final_skus = [
        sku for sku in candidate_skus
        if _passes_stock(sku) and _passes_pim(sku) and _passes_sync(sku)
    ]
    products = products.filter(sku__in=final_skus)

    order_key = order if order in _CATALOG_ORDERS else "name"
    if collection_ref and not collection_smart and not term and order_key == "name":
        # Coleção manual mantém a ordem curada (arraste), salvo busca/ordenação explícita.
        products = products.order_by("collection_items__sort_order", "sku")
    else:
        products = products.order_by(*_CATALOG_ORDERS[order_key])
    total = len(final_skus)
    size = max(1, min(int(page_size or 50), MAX_CATALOG_PAGE_SIZE))
    current = max(1, int(page or 1))
    start = (current - 1) * size
    products = list(products.prefetch_related("keywords", "collection_items__collection")[start:start + size])

    # Uma consulta para a matriz inteira: quem passa pelo filtro do cardápio mas
    # não é alcançado por nenhuma coleção ativa (regra em catalog_visibility).
    from shopman.shop.services import catalog_visibility

    hidden_skus = catalog_visibility.hidden_by_inactive_collection_skus()

    from shopman.backstage.models import ProductConsumptionTag

    tagged_skus = set(ProductConsumptionTag.objects.values_list("sku", flat=True))

    rows: list[CatalogRowProjection] = []
    for product in products:
        primary_ref = ""
        primary_name = ""
        primary = next((ci for ci in product.collection_items.all() if ci.is_primary), None)
        if primary:
            primary_ref = primary.collection.ref
            primary_name = primary.collection.name

        cells: list[SurfaceCellProjection] = []
        for surface in surfaces:
            # Feed (menuboard/plataforma): célula = pertence ao feed (via coleções) e
            # pausa local; sem preço/publicação. A pausa global do produto gateia por cima.
            sync_status, sync_error, synced_at = _cell_sync(sync_map, product.sku, surface.sync_key or surface.ref)
            if surface.ref in display_index:
                sc = display_index[surface.ref]
                in_feed = product.sku in sc["members"]
                paused_here = product.sku in sc["paused"]
                cells.append(
                    SurfaceCellProjection(
                        surface_ref=surface.ref,
                        in_listing=in_feed,
                        is_published=in_feed,
                        is_sellable=in_feed and not paused_here,
                        pause_audit=sc["pause_audit"].get(product.sku, "") if paused_here else "",
                        available=(
                            in_feed
                            and not paused_here
                            and product.is_active
                            and product.is_published
                            and product.is_sellable
                        ),
                        price_q=None,
                        price_display="",
                        action=cell_action(product.sku, surface.ref, user, display=sc["channel"], available=in_feed),
                        sync_status=sync_status,
                        sync_error=sync_error,
                        synced_at=synced_at,
                    )
                )
                continue

            item = cells_index.get(surface.ref, {}).get(product.sku)
            if item is None:
                cells.append(
                    SurfaceCellProjection(
                        surface_ref=surface.ref,
                        in_listing=False,
                        is_published=False,
                        is_sellable=False,
                        available=False,
                        price_q=None,
                        price_display="",
                        sync_status=sync_status,
                        sync_error=sync_error,
                        synced_at=synced_at,
                    )
                )
                continue
            available = (
                product.is_active
                and product.is_published
                and product.is_sellable
                and item.is_published
                and item.is_sellable
            )
            cells.append(
                SurfaceCellProjection(
                    surface_ref=surface.ref,
                    in_listing=True,
                    is_published=item.is_published,
                    is_sellable=item.is_sellable,
                    available=available,
                    price_q=item.price_q,
                    price_display=_money(item.price_q),
                    valid_from=item.listing.valid_from.isoformat() if item.listing.valid_from else "",
                    valid_until=item.listing.valid_until.isoformat() if item.listing.valid_until else "",
                    pause_audit=pause_audit.get(item.pk, "") if not item.is_sellable else "",
                    action=cell_action(product.sku, surface.ref, user, item=item),
                    sync_status=sync_status,
                    sync_error=sync_error,
                    synced_at=synced_at,
                )
            )

        stock = _stock_view(
            stock_info.get(product.sku), low_stock_threshold, planned_by_sku.get(product.sku, 0)
        )
        social_view, pim_complete = _social_view(product)
        rows.append(
            CatalogRowProjection(
                sku=product.sku,
                name=product.name,
                image_url=product.image_url or "",
                primary_collection=primary_ref,
                primary_collection_name=primary_name,
                is_active=product.is_active,
                is_published=product.is_published,
                is_sellable=product.is_sellable,
                base_price_q=product.base_price_q,
                base_price_display=_money(product.base_price_q),
                edit_url=_edit_url(product),
                stock_tracked=stock["stock_tracked"],
                stock_qty=stock["stock_qty"],
                sold_out=stock["sold_out"],
                low_stock=stock["low_stock"],
                replenish_qty=stock["replenish_qty"],
                # `.names()` consulta o banco por produto e ignora o prefetch; a
                # lista do cache do prefetch é a mesma e não faz N+1.
                keywords=tuple(sorted(tag.name for tag in product.keywords.all())),
                cells=tuple(cells),
                social=social_view,
                pim_complete=pim_complete,
                hidden_by_inactive_collection=product.sku in hidden_skus,
                has_vocation=product.sku in tagged_skus,
                product_action=product_switch_action(product, user),
                resync_action=resync_action(product, [surface.ref for surface in surfaces if surface.is_projection_target], user),
            )
        )

    collections = tuple(
        CollectionProjection(
            ref=c.ref,
            name=c.name,
            is_smart=c.is_smart,
            product_count=collection_products(c).filter(is_active=not archived).count(),
        )
        for c in Collection.objects.filter(is_active=True).order_by("sort_order", "name")
    )

    # "Sem vocação" = produto à venda (``is_sellable``) sem etiqueta. Produto
    # fora de venda não entra: classificar o que não se vende não informa o B.I.
    vocation_pending = tuple(
        VocationPendingProjection(sku=sku, name=name)
        for sku, name in Product.objects.active().filter(is_sellable=True)
        .exclude(sku__in=tagged_skus)
        .order_by("name", "sku")
        .values_list("sku", "name")
    )

    # A opção conta o que casaria COM o resto do recorte; a seleção da própria
    # dimensão fica fora da conta (senão marcar "esgotado" zeraria os outros).
    stock_count_skus = [sku for sku in candidate_skus if _passes_pim(sku) and _passes_sync(sku)]
    sync_count_skus = [sku for sku in candidate_skus if _passes_stock(sku) and _passes_pim(sku)]

    facets = CatalogFacetsProjection(
        stock={
            bucket: sum(1 for sku in stock_count_skus if stock_buckets.get(sku, "ok") == bucket)
            for bucket in _STOCK_BUCKETS
        },
        sync_status={
            bucket: sum(1 for sku in sync_count_skus if bucket in sync_buckets.get(sku, set()))
            for bucket in _SYNC_BUCKETS
        },
    )

    return CatalogMatrixProjection(
        surfaces=tuple(surfaces), rows=tuple(rows), collections=collections, facets=facets,
        vocation_pending=vocation_pending,
        total=total, page=current, page_size=size, has_next=start + len(products) < total,
        order=order_key, query=term,
        date_from=date_from.isoformat() if date_from else "",
        date_to=date_to.isoformat() if date_to else "",
    )
