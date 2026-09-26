"""
Projeção dos canais de venda e exibição para o Gestor.

Um Feed exibe um recorte de coleções para fora (📺 menuboard / 🛰 Google/Meta) sem
transacionar. Esta projeção lista os feeds + a saída (URL para abrir/prever) +
as coleções disponíveis (para o operador escolher quais cada um mostra). A ordem de
exibição das coleções é global (``Collection.sort_order``), reordenável no catálogo.

Canais de venda mostram apenas configuração de envio e registros locais de sync.
Dataclasses imutáveis convertidas por ``backstage.api.projections``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Q

from shopman.shop.projections.types import Action

# O `kind` da tela deriva de `display.format`: formato VAZIO é quadro (rota nossa),
# formato preenchido é feed de plataforma (dialeto de terceiro).
_FORMAT_META = {
    "": {"kind": "menuboard", "label": "Menuboard (TV)", "icon": "tv", "capability": "display"},
    "google_merchant": {"kind": "google", "label": "Feed Google", "icon": "rss", "capability": "feed"},
    "meta_catalog": {"kind": "meta", "label": "Feed Meta", "icon": "rss", "capability": "feed"},
}


def _nonneg_int(value) -> int:
    """Config é JSONField editável: valor torto projeta como 0 (desligado)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _output_path(ref: str, fmt: str) -> str:
    """Caminho da saída (abrir/prever).

    O `?platform=` saiu: o formato é propriedade do CANAL, não parâmetro de query —
    dois jeitos de dizer a mesma coisa é um jeito a mais de discordarem.
    """
    if not fmt:
        return f"/menuboard/{ref}/"
    return f"/feed/{ref}.xml"


@dataclass(frozen=True)
class FeedCollectionRef:
    ref: str
    name: str
    exists: bool  # a coleção ainda existe?


@dataclass(frozen=True)
class ChannelPeriodOption:
    key: str
    label: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True)
class ChannelSwitchProjection:
    """O toggle "Ativo" de um card — o mesmo em canal de venda e de exibição.

    ``periods``/``reasons``/``title``/``consequence`` já são os do gesto que o
    toggle faria agora (desligar se está ligado; ligar se está desligado).
    """

    is_active: bool
    state_line: str  # quem, quando, por quê, até quando — vazio no estado normal
    closed_by_shop: str  # ligado, mas a loja está fechada: é o horário que fecha
    scheduled_line: str  # agendamento ainda por vir
    title: str
    consequence: str
    periods: tuple[ChannelPeriodOption, ...]
    reasons: tuple[str, ...]
    reason_required: bool
    enabled: bool
    disabled_reason: str
    base_revision: str
    expected_actor_id: int | None
    requires_manager_approval: bool


@dataclass(frozen=True)
class ManagerOptionProjection:
    username: str
    name: str


@dataclass(frozen=True)
class MenuboardAutomaticProjection:
    enabled: bool
    is_sleeping: bool
    idle_messages: tuple[str, ...]
    state_line: str
    lead_minutes: int
    lag_minutes: int


@dataclass(frozen=True)
class FeedProjection:
    ref: str
    name: str
    kind: str
    kind_label: str
    kind_icon: str
    capability: str  # display | feed
    is_active: bool
    output_path: str
    collections: tuple[FeedCollectionRef, ...]  # coleções que ele exibe (em ordem global)
    rotate_seconds: int  # menuboard: cadência da troca de páginas (0 = sem rotação)
    items_per_page: int  # menuboard: teto de itens por tela (0 = tudo numa página)
    automatic: MenuboardAutomaticProjection | None
    actions: tuple[Action, ...] = ()
    switch: ChannelSwitchProjection | None = None


@dataclass(frozen=True)
class CollectionOptionProjection:
    ref: str
    name: str
    product_count: int


@dataclass(frozen=True)
class CatalogChannelProjection:
    ref: str
    name: str
    projection_enabled: bool
    diagnostic: str
    synced: int
    pending: int
    errors: int
    retracted: int
    skipped: int
    observed: int
    catalog_path: str = "/catalog"
    is_active: bool = True
    switch: ChannelSwitchProjection | None = None


@dataclass(frozen=True)
class FeedBoardProjection:
    feeds: tuple[FeedProjection, ...]
    all_collections: tuple[CollectionOptionProjection, ...]  # opções p/ o picker (ordem global)
    catalog_channels: tuple[CatalogChannelProjection, ...] = ()
    # Quem pode autorizar ligar/desligar (a lista do PDV, sem quem está operando).
    # Vazia quando quem opera já é gerente — aí o toggle só pede confirmação.
    managers: tuple[ManagerOptionProjection, ...] = ()
    viewer_name: str = ""


_CONSEQUENCE = {
    # (tipo, ligar?) → o que acontece. Tipo: web | whatsapp | ifood | pdv | order | menuboard | feed
    ("web", False): "A loja online para de aceitar pedidos. O cardápio continua no site para consulta.",
    ("web", True): "A loja online volta a aceitar pedidos, dentro do horário da loja.",
    ("whatsapp", False): "O WhatsApp continua respondendo, mas para de oferecer e de fechar pedido.",
    ("whatsapp", True): "O WhatsApp volta a fechar pedido, dentro do horário da loja.",
    ("ifood", False): "A loja fecha no iFood. Os pedidos do iFood já aceitos seguem normalmente.",
    ("ifood", True): "A loja volta a abrir no iFood, dentro do horário da loja.",
    ("order", False): "O canal para de aceitar pedidos.",
    ("order", True): "O canal volta a aceitar pedidos, dentro do horário da loja.",
    ("menuboard", False): "A TV apaga o cardápio e mostra só: \u201cConsulte o cardápio no balcão.\u201d",
    ("menuboard", True): "A TV volta a mostrar o cardápio.",
    ("feed", False): "O feed marca todos os produtos como fora de estoque, e a plataforma para de anunciá-los.",
    ("feed", True): "O feed volta a anunciar os produtos disponíveis.",
}


def _switch_kind(channel, *, display_format: str | None) -> str:
    from shopman.shop.services.channel_switch import IFOOD_CHANNEL_REF

    if display_format is not None:
        return "menuboard" if not display_format else "feed"
    if channel.ref == IFOOD_CHANNEL_REF:
        return "ifood"
    if channel.ref in {"web", "whatsapp"}:
        return channel.ref
    return "order"


def _build_switch(channel, *, user, authorized: bool, is_manager: bool, state, now,
                  display_format: str | None = None) -> ChannelSwitchProjection:
    from shopman.shop.services import channel_switch as switches

    active = switches.effective_active(channel, now=now)
    target = not active
    name = channel.name or channel.ref
    governed = switches.governed_by_calendar(channel)
    periods = switches.period_options(channel, target=target, now=now, state=state if governed else None)
    return ChannelSwitchProjection(
        is_active=active,
        state_line=switches.state_line(channel, now=now),
        closed_by_shop=switches.closed_by_shop(channel, state=state, now=now) if governed else "",
        scheduled_line=switches.scheduled_line(channel, now=now),
        title=f"{'Ligar' if target else 'Desligar'} {name}",
        consequence=_CONSEQUENCE[(_switch_kind(channel, display_format=display_format), target)],
        periods=tuple(ChannelPeriodOption(key=p.key, label=p.label, enabled=p.enabled, reason=p.reason) for p in periods),
        reasons=switches.reason_presets(channel, target=target),
        reason_required=not target,
        enabled=authorized,
        disabled_reason="" if authorized else "Identifique uma pessoa com permissão para editar o catálogo.",
        base_revision=switches.revision(channel),
        expected_actor_id=getattr(user, "pk", None),
        requires_manager_approval=not is_manager,
    )


def build_feed_board(*, user=None, now=None) -> FeedBoardProjection:
    from django.utils import timezone
    from shopman.offerman.models import Collection

    from shopman.backstage.projections.pos import _manager_cards
    from shopman.backstage.services import feeds as feed_service
    from shopman.backstage.services.operator import ADJUST_SHIFT
    from shopman.shop.models import Channel
    from shopman.shop.services import business_calendar
    from shopman.shop.services import channel_switch as switches
    from shopman.shop.services.channel_switch import effective_active

    now = now or timezone.now()
    state = business_calendar.current_business_state(now=now)
    collections = list(Collection.objects.filter(is_active=True).order_by("sort_order", "name"))
    coll_by_ref = {c.ref: c for c in collections}
    order_index = {c.ref: i for i, c in enumerate(collections)}

    authorized = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_catalog"))
    # Gerente é quem autoriza exceção no PDV (``cashman.adjust_shift``): ele só
    # confirma; quem não é, chama um gerente (crachá ou PIN) no mesmo diálogo.
    is_manager = bool(authorized and user.has_perm(ADJUST_SHIFT))
    feeds: list[FeedProjection] = []
    channels = Channel.objects.filter(
        commerce_policy=Channel.CommercePolicy.DISPLAY
    ).order_by("name")
    for sc in channels:
        display = (sc.config or {}).get("display") or {}
        fmt = display.get("format") or ""
        meta = _FORMAT_META.get(fmt, {"kind": fmt, "label": fmt, "icon": "monitor", "capability": "display"})
        channel_active = effective_active(sc, now=now)
        automatic = None
        if not fmt:
            from shopman.shop.services.menuboard_schedule import (
                AUTOMATIC_LAG_MINUTES,
                AUTOMATIC_LEAD_MINUTES,
                resolve_menuboard_automatic_state,
            )

            automatic_state = resolve_menuboard_automatic_state(sc, now=now)
            automatic = MenuboardAutomaticProjection(
                enabled=automatic_state.enabled,
                is_sleeping=automatic_state.is_sleeping,
                idle_messages=automatic_state.idle_messages,
                state_line=("Automático ligado; aguarda o canal Ativo."
                            if automatic_state.enabled and not channel_active else automatic_state.state_line),
                lead_minutes=AUTOMATIC_LEAD_MINUTES,
                lag_minutes=AUTOMATIC_LAG_MINUTES,
            )
        # resolve + ordena as coleções do canal pela ordem global (sort_order)
        refs = list(display.get("collections") or [])
        resolved = [
            FeedCollectionRef(
                ref=r,
                name=coll_by_ref[r].name if r in coll_by_ref else r,
                exists=r in coll_by_ref,
            )
            for r in refs
        ]
        resolved.sort(key=lambda c: order_index.get(c.ref, 10_000))
        feeds.append(
            FeedProjection(
                actions=tuple(Action(
                    ref=field, kind="mutation", label=label,
                    enabled=authorized and (field not in {"rotation", "automatic"} or not fmt),
                    reason=("Identifique uma pessoa com permissão para editar o catálogo." if not authorized else
                            "Feed de plataforma não tem páginas para rotacionar." if field == "rotation" and fmt else
                            "Modo automático existe apenas no menuboard." if field == "automatic" and fmt else ""),
                    method="POST", idempotency="required",
                    payload_schema={"base_revision": feed_service.revision(sc, field), "expected_actor_id": getattr(user, "pk", None)},
                ) for field, label in (("collections", "Salvar coleções"), ("rotation", "Salvar rotação"),
                                        ("automatic", "Salvar modo automático"))),
                switch=_build_switch(sc, user=user, authorized=authorized, is_manager=is_manager,
                                     state=state, now=now, display_format=fmt),
                ref=sc.ref,
                name=sc.name or sc.ref,
                kind=meta["kind"],
                kind_label=meta["label"],
                kind_icon=meta["icon"],
                capability=meta["capability"],
                is_active=channel_active,
                output_path=_output_path(sc.ref, fmt),
                collections=tuple(resolved),
                rotate_seconds=_nonneg_int(display.get("rotate_seconds")),
                items_per_page=_nonneg_int(display.get("items_per_page")),
                automatic=automatic,
            )
        )

    options = tuple(
        CollectionOptionProjection(ref=c.ref, name=c.name, product_count=c.product_queryset().count())
        for c in collections
    )
    from shopman.offerman.conf import get_projection_backend_channels

    from shopman.shop.models.catalog_sync import CatalogSyncState

    configured = set(get_projection_backend_channels())
    # Não instanciamos adapters nem consultamos a API para montar esta leitura.
    external = list(Channel.objects.filter(
        commerce_policy=Channel.CommercePolicy.ORDER,
    ).order_by("name", "ref"))
    counts = {row["channel_ref"]: row for row in CatalogSyncState.objects.filter(
        channel_ref__in=[channel.ref for channel in external],
    ).values("channel_ref").annotate(
        observed=Count("pk"), synced=Count("pk", filter=Q(status="synced")),
        pending=Count("pk", filter=Q(status="pending")),
        errors=Count("pk", filter=Q(status="error")),
        retracted=Count("pk", filter=Q(status="retracted")),
        skipped=Count("pk", filter=Q(status="skipped")),
    )}
    catalog_channels = []
    for channel in external:
        enabled = channel.ref in configured
        count = counts.get(channel.ref, {})
        diagnostic = ("Sem envio externo de catálogo configurado." if not enabled else
                      "Canal desligado: o envio de produtos fica parado até religar." if not effective_active(channel, now=now) else
                      "Envio configurado. Consulte o resultado por produto no Catálogo.")
        catalog_channels.append(CatalogChannelProjection(
            ref=channel.ref, name=channel.name or channel.ref, projection_enabled=enabled,
            diagnostic=diagnostic, synced=count.get("synced", 0), pending=count.get("pending", 0),
            errors=count.get("errors", 0), retracted=count.get("retracted", 0),
            skipped=count.get("skipped", 0), observed=count.get("observed", 0),
            is_active=effective_active(channel, now=now),
            # PDV sem toggle (o balcão fecha pelo caixa, não pelo canal): card informativo.
            switch=_build_switch(channel, user=user, authorized=authorized, is_manager=is_manager,
                                 state=state, now=now) if switches.is_switchable(channel) else None,
        ))
    managers = () if is_manager or not authorized else tuple(
        ManagerOptionProjection(username=card["username"], name=card["name"]) for card in _manager_cards(user)
    )
    viewer = (user.get_full_name() or user.get_username()).strip() if authorized else ""
    return FeedBoardProjection(feeds=tuple(feeds), all_collections=options,
                              catalog_channels=tuple(catalog_channels), managers=managers, viewer_name=viewer)
