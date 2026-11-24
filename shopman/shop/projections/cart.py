"""Cart read-side projection — semantic data, surface-agnostic.

The orchestrator resolves the cart once, for any surface: lines (with
own-hold-aware availability and planned-hold state), discount transparency,
coupon, delivery fee, totals, minimum-order progress, upsell and the
checkout-eligibility decision (``can_checkout`` + ``checkout_block_reason``).
Everything is semantic — cents (``_q``), enums, ISO timestamps, booleans,
refs. Presentation (``R$`` formatting, "Cupom X"/"Faltam X" copy, the
``Action`` labels) lives in ``<surface>/presentation/``.

This is the single source of cart-data resolution: ``CartService.get_cart``
(the legacy dict) and ``storefront/presentation/cart`` both build from
``build_cart`` — no surface re-derives availability, discount or totals.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.utils import timezone

from shopman.shop import product_options
from shopman.shop.discount_spread import merged_for_display

logger = logging.getLogger(__name__)

DEFAULT_STOREFRONT_CHANNEL_REF = "web"

# Pricing-modifier discount keys aggregated into the cart breakdown.
_PRICING_MODIFIER_KEYS = (
    "happy_hour",
    "lot_discount",
    "loyalty_redeem",
    "manual_discount",
)


@dataclass(frozen=True)
class MinimumOrderProgressProjection:
    """Progress toward the channel's minimum-order amount — cents only.

    ``percent`` is the integer share of the minimum already reached (0–100).
    The presentation derives the ``R$`` strings and the "Faltam X" copy.
    """

    minimum_q: int
    remaining_q: int
    percent: int


@dataclass(frozen=True)
class FreeDeliveryProgressProjection:
    """Progress toward the free-delivery threshold — cents only.

    Emitted only while the order is below the threshold; the presentation
    derives the ``R$`` strings and the "faltam X para frete grátis" copy.
    """

    threshold_q: int
    remaining_q: int
    percent: int


@dataclass(frozen=True)
class UpsellSuggestionProjection:
    """Um SKU oferecido junto do que já está na sacola.

    Escolhido pelo motor de sugestão (``projections.suggestions``) — não mais
    "o mais popular que falta", que foi a regra que ofereceu Água a quem levava
    pão. Carrega o preço listado que o checkout cobraria (``unit_price_q``) e o
    nome/imagem que a superfície renderiza: sem instância de model, sem preço
    formatado.
    """

    sku: str
    name: str
    unit_price_q: int
    image_url: str | None
    #: Por que ESTE item foi oferecido — os códigos que o motor de sugestão
    #: produziu ("affinity:BAG", "pairing:natureza=comida→bebida"). Não vai
    #: para a tela do cliente; existe para o Admin explicar e o B.I. medir.
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CartLineProjection:
    """A single cart line — semantic, own-hold-aware availability included."""

    line_id: str
    sku: str
    name: str
    qty: Decimal | int
    unit_price_q: int
    line_total_q: int

    # Availability at render-time (own-hold corrected: a session holding all
    # of its own stock is NOT flagged unavailable).
    is_available: bool
    available_qty: Decimal | int | None  # None = demand-based / no ceiling

    # Planned-hold lifecycle (AVAILABILITY-PLAN §8).
    is_awaiting_confirmation: bool
    is_ready_for_confirmation: bool
    confirmation_deadline_iso: str | None
    # Batch date the waitlisted line is planned against (None = no plan yet).
    planned_for_date: str | None
    # Data ANTERIOR à fornada prevista em que a linha inteira já tem saldo
    # (fornada extra planejada depois, pão pronto). None = não há; o pedido
    # começa na fornada prevista. O fechamento move a reserva para a data
    # escolhida (``policies.order_date_before_batch``).
    earlier_available_date: str | None

    # Preço de LISTA da linha (``meta._list_q``, carimbado pelo ItemPricingModifier
    # antes de qualquer desconto) e o total a esse preço. A sacola mostra a linha
    # cheia e o desconto só no resumo: Subtotal = soma das linhas, Subtotal menos
    # descontos = Total (beta 05/11, MKT-05). O preço cobrado continua em
    # ``unit_price_q``/``line_total_q``.
    list_price_q: int
    list_total_q: int
    discount_name: str | None  # raw promo/coupon name (presentation prefixes "Cupom")
    discount_is_coupon: bool

    # Preparado na hora: promessa DECLARADA da casa
    # (``Product.metadata["made_to_order"]``) — finalizado no momento de servir.
    # Eixo próprio, independente da fila: o croque que espera a fornada de amanhã
    # carrega os dois (o selo diz o que É, a fila diz quando vem).
    is_made_to_order: bool = False

    # Esgotado honesto: a linha caiu por FALTA — não por pausa (decisão do
    # operador) nem por disponibilidade parcial, que tem o "Usar N" como saída.
    # Mesma régua do card e da PDP; sem ela a sacola dizia "Indisponível" e a
    # única saída era a lixeira.
    is_notifiable: bool = False

    # Observação do item para a cozinha (``meta["notes"]``); "" = sem observação.
    notes: str = ""

    # Escolhas no produto (``meta["options"]``): o resumo legível ("+ Ovo frito")
    # e se a linha tem escolha (aí ela só muda pela ``line_id``).
    options_summary: str = ""
    has_options: bool = False


@dataclass(frozen=True)
class CartDiscountLineProjection:
    """One aggregated discount row — positive cents saved, one per origin."""

    name: str
    is_coupon: bool
    amount_q: int
    # A promoção vencedora é restrita à retirada (fulfillment_types): o checkout
    # avisa antes de o cliente trocar para entrega.
    requires_pickup: bool = False


@dataclass(frozen=True)
class CartCouponProjection:
    """Applied coupon — code + cents saved.

    Com ``discount_q == 0``, ``zero_reason`` diz por quê (``pricing.coupon.reason``,
    ``DiscountModifier._coupon_zero_reason``); ``missing_q`` é o que falta para o
    pedido mínimo e ``fulfillment_types`` onde o cupom vale.
    """

    code: str
    discount_q: int
    zero_reason: str = ""
    missing_q: int = 0
    fulfillment_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class CartProjection:
    """Full cart data projection — surface-agnostic, policy-laden."""

    session_key: str
    lines: tuple[CartLineProjection, ...]
    count: int
    is_empty: bool

    subtotal_q: int
    original_subtotal_q: int
    discount_total_q: int
    discount_lines: tuple[CartDiscountLineProjection, ...]
    coupon: CartCouponProjection | None

    delivery_fee_q: int | None
    delivery_is_free: bool
    delivery_zone_error: bool
    # Distância loja→endereço em km (1 casa), quando calculável. Justifica a taxa
    # ao cliente ("a X km · R$ Y"). None quando não há coordenada.
    delivery_distance_km: float | None
    grand_total_q: int

    loyalty_applied: bool

    has_unavailable: bool
    has_awaiting_confirmation: bool
    has_ready_for_confirmation: bool

    minimum_order: MinimumOrderProgressProjection | None
    # Delivery-only minimum (``shop.defaults.rules.delivery_minimum_q``): set
    # while a delivery order is below it. Pickup never carries a minimum, but the
    # projection stays fulfillment-agnostic — the surface shows it in the
    # delivery step. ``delivery_minimum`` blocks the commit (DeliveryZoneRule).
    delivery_minimum: MinimumOrderProgressProjection | None
    # Free-delivery upsell (``shop.defaults.rules.free_delivery_above_q``): set
    # while below the threshold so any surface can reuse the progress bar.
    free_delivery: FreeDeliveryProgressProjection | None
    upsell: UpsellSuggestionProjection | None

    can_checkout: bool
    revision: int = 0
    checkout_block_reason: str = ""  # "" | "empty" | "unavailable" | "below_minimum"
    # Mensagem de economia do grupo (texto por grupo, editável no Admin). Vazia
    # quando não houve desconto de grupo.
    group_savings_message: str = ""
    # De onde a sacola veio quando outro canal a passou para cá (OC-15/OC-16):
    # ``Session.data["transferred_from"]``, lido na mesma consulta da sacola, para
    # o recibo da passagem só custar consulta quando existe.
    transferred_from: dict | None = None


def _empty_cart(session_key: str = "") -> CartProjection:
    return CartProjection(
        session_key=session_key,
        lines=(),
        count=0,
        is_empty=True,
        subtotal_q=0,
        original_subtotal_q=0,
        discount_total_q=0,
        discount_lines=(),
        coupon=None,
        delivery_fee_q=None,
        delivery_is_free=False,
        delivery_zone_error=False,
        delivery_distance_km=None,
        grand_total_q=0,
        loyalty_applied=False,
        has_unavailable=False,
        has_awaiting_confirmation=False,
        has_ready_for_confirmation=False,
        minimum_order=None,
        delivery_minimum=None,
        free_delivery=None,
        upsell=None,
        can_checkout=False,
        checkout_block_reason="empty",
    )


def reserved_until(session_key: str | None):
    """Até quando a sacola guarda os itens: o menor prazo das reservas vivas da sessão.

    Leitura pura, para a superfície dizer a hora ao cliente ("Guardamos seus
    itens até 19h18"). Conta só reserva ATIVA e COM prazo: a de fornada futura e
    a de demanda nascem sem ``expires_at`` e não entram, e a que já venceu deixou
    de contar no saldo no instante em que venceu (mesma régua de
    ``availability.bump_session_hold_expiry``, que é quem renova o prazo a cada
    gesto na sacola). Sem reserva com prazo, ``None``: nada é prometido.
    """
    if not session_key:
        return None
    try:
        from django.db.models import Min
        from shopman.stockman import Hold, HoldStatus
    except Exception:
        logger.debug("cart.reserved_until degraded; returning None", exc_info=True)
        return None
    return Hold.objects.filter(
        metadata__reference=session_key,
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        expires_at__gt=timezone.now(),
    ).aggregate(until=Min("expires_at"))["until"]


def reservation_lapsed_at(session_key: str | None, skus):
    """Até quando valia a reserva que venceu, para a sacola dizer o que houve (#2767).

    Leitura pura, irmã de :func:`reserved_until`. Quem abre a sacola depois do
    prazo (voltou no dia seguinte, recarregou a página) vê as linhas normais; sem
    esta leitura, nada diria que a reserva acabou. Conta a reserva com prazo de um
    item que ainda está na sacola (``skus``) e que venceu pelo relógio: a ainda
    viva com o prazo já passado e a que o ``release_expired`` soltou depois do
    prazo (``resolved_at`` no prazo ou depois). A que a cliente soltou tirando o
    item sai antes do prazo e não conta. Item que já tem reserva viva (renovada
    por um gesto, ou de fornada futura, sem relógio) também não conta: está
    guardado. Devolve o prazo mais tarde entre as vencidas, ou ``None``.
    """
    skus = [sku for sku in (skus or ()) if sku]
    if not session_key or not skus:
        return None
    from django.db.models import F, Max, Q
    from shopman.stockman import Hold, HoldStatus

    now = timezone.now()
    live = [HoldStatus.PENDING, HoldStatus.CONFIRMED]
    mine = Hold.objects.filter(metadata__reference=session_key, sku__in=skus)
    held = mine.filter(status__in=live).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    return (
        mine.exclude(sku__in=held.values("sku"))
        .filter(expires_at__lte=now)
        .filter(Q(status__in=live) | Q(status=HoldStatus.RELEASED, resolved_at__gte=F("expires_at")))
        .aggregate(at=Max("expires_at"))["at"]
    )


def open_elsewhere(customer_ref: str, channel_ref: str):
    """As sacolas abertas deste cliente nos outros canais (OC-17, C06).

    Leitura pura sobre ``sessions.open_sessions_for_customer``: o canal que
    pergunta avisa, nunca sincroniza. Vazio sem cliente.
    """
    if not customer_ref:
        return ()
    from shopman.shop.services.sessions import open_sessions_for_customer

    return open_sessions_for_customer(customer_ref, exclude_channel=channel_ref)


def offered_cart(channel_ref: str, session_key: str):
    """A sacola de outro canal que uma passagem aponta (``transferred_to``), contada; ``None`` se fechou."""
    from shopman.shop.services.sessions import open_session_summary

    return open_session_summary(channel_ref, session_key)


def conversation_number_available() -> bool:
    """A loja tem WhatsApp para a mensagem pronta de "Continuar pelo WhatsApp" (X1)."""
    from shopman.shop.services.session_transfer import conversation_number

    return bool(conversation_number())


@dataclass(frozen=True)
class TransferArrival:
    """A sacola deste canal que chegou de outro, com o recibo da passagem (OC-15/OC-16).

    Só existe na sacola em que ``session_transfer.accept`` pôs os itens (nova, ou a
    que o destino já tinha): a adoção no mesmo canal não grava recibo. As diferenças são as do recibo gravado na origem.
    """

    source_channel: str
    source_channel_name: str
    differences: tuple[dict, ...]
    source_total_q: int
    dest_total_q: int
    #: O que entrou: linhas e unidades ("3"; "1.5" com item de peso).
    carried_lines: int = 0
    carried_units: str = ""


def transfer_arrival(session_key: str | None, came_from: dict | None) -> TransferArrival | None:
    """O recibo da passagem que trouxe esta sacola, ou ``None``. Leitura pura.

    ``came_from`` é o ``transferred_from`` que ``build_cart`` já leu da sacola: sem
    ele, nenhuma consulta.
    """
    if not session_key:
        return None
    from shopman.orderman.models import Session

    from shopman.shop.models import Channel

    if not isinstance(came_from, dict) or not came_from.get("channel_ref") or "tab_ref" in came_from:
        return None
    source_data = (
        Session.objects.filter(channel_ref=came_from["channel_ref"], session_key=came_from.get("session_key") or "")
        .values_list("data", flat=True)
        .first()
    )
    receipt = (source_data or {}).get("transfer_receipt") if isinstance(source_data, dict) else None
    if not isinstance(receipt, dict) or receipt.get("dest_session_key") != session_key:
        return None
    name = Channel.objects.filter(ref=came_from["channel_ref"]).values_list("name", flat=True).first()
    return TransferArrival(
        source_channel=str(came_from["channel_ref"]),
        source_channel_name=str(name or came_from["channel_ref"]),
        differences=tuple(diff for diff in receipt.get("differences") or () if isinstance(diff, dict)),
        source_total_q=int(receipt.get("source_total_q") or 0),
        dest_total_q=int(receipt.get("dest_total_q") or 0),
        carried_lines=int(receipt.get("carried_lines") or 0),
        carried_units=str(receipt.get("carried_units") or ""),
    )


def items_phrase(entry) -> str:
    """Quanto há na outra sacola, como a cliente conta: "3 itens", "1 item".

    Com item de peso (quantidade quebrada) a soma de unidades não diz nada, e a
    frase conta os produtos: "2 produtos".
    """
    count = entry.items_count
    if isinstance(count, int):
        return f"{count} {'item' if count == 1 else 'itens'}"
    lines = entry.lines_count
    return f"{lines} {'produto' if lines == 1 else 'produtos'}"


def build_cart(
    session_key: str | None,
    channel_ref: str = DEFAULT_STOREFRONT_CHANNEL_REF,
) -> CartProjection:
    """Resolve the full cart data for ``session_key`` on ``channel_ref``.

    Always returns a projection — an empty/expired cart becomes the empty
    projection. Never raises for business conditions; stock shortfalls surface
    as per-line ``is_available`` flags.
    """
    if not session_key:
        return _empty_cart()

    from shopman.orderman.models import Session

    session = Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).first()
    if session is None:
        return _empty_cart()

    # A linha __DELIVERY_FEE__ é cobrança (entra em Order.total_q), não item do
    # carrinho: fica fora de lines/subtotal — a taxa aparece via delivery_fee_q.
    # A linha que o rateio do desconto partiu (#3240) aparece inteira: a cliente
    # comprou 3 Croissants, e o cupom de pedido já tem linha própria na sacola.
    raw_items = merged_for_display([
        dict(item)
        for item in (session.items or [])
        if item.get("sku") != "__DELIVERY_FEE__"
        and (item.get("meta") or {}).get("type") != "delivery_fee"
    ])
    if not raw_items:
        return _empty_cart(session_key)

    skus = [item.get("sku", "") for item in raw_items]
    names_by_sku, made_to_order, sellable = _product_facts(skus)
    # O trilho de sugestão vem ANTES das linhas: ele conhece os candidatos e a
    # sacola, e lê os dois de uma vez para o memo do request (GET); a leitura
    # das linhas, logo abaixo, sai do memo. A resposta é a mesma: o trilho só
    # depende do conjunto de SKUs da sacola, que já está decidido aqui.
    upsell = _upsell(set(skus), channel_ref=channel_ref)
    avail_map, own_holds = _availability(skus, session_key, channel_ref, _future_cart_date(session))
    planned_by_sku = _planned_holds(session_key, skus)
    earlier_by_sku = _earlier_available_dates(raw_items, planned_by_sku, channel_ref)

    pricing = session.pricing or {}
    discount_data = pricing.get("discount", {})
    discount_items = {d["sku"]: d for d in discount_data.get("items", [])}

    lines = tuple(
        _build_line(
            item, names_by_sku, avail_map, own_holds, discount_items,
            planned_by_sku=planned_by_sku,
            earlier_by_sku=earlier_by_sku,
            made_to_order_skus=made_to_order,
            sellable_skus=sellable,
        )
        for item in raw_items
    )

    count = sum(line.qty for line in lines)
    subtotal_q = sum(line.line_total_q for line in lines)
    # Linha em planned-hold ("aguardando confirmação"/"confirme até HH:MM") NÃO é
    # indisponível: a falta de pronta-entrega é exatamente o que o selo da linha já
    # explica, e o commit adota o hold planejado da sessão (stock.hold; com data
    # futura, re-reserva contra o target_date). Contá-la aqui disparava o banner
    # "estoque mudou" + checkout bloqueado JUNTO do selo acolhedor — beco sem
    # saída na sacola (AVAILABILITY-PLAN §5 bloqueia checkout só por Indisponível).
    has_unavailable = any(
        not line.is_available
        and not line.is_awaiting_confirmation
        and not line.is_ready_for_confirmation
        for line in lines
    )
    has_awaiting = any(line.is_awaiting_confirmation for line in lines)
    has_ready = any(line.is_ready_for_confirmation for line in lines)

    discount_total_q = int(discount_data.get("total_discount_q", 0) or 0)
    discount_total_q += sum(
        int((pricing.get(key) or {}).get("total_discount_q", 0))
        for key in _PRICING_MODIFIER_KEYS
    )
    original_subtotal_q = subtotal_q + discount_total_q
    discount_lines = _discount_lines(discount_data, pricing)
    coupon = _coupon(session.data or {}, pricing)

    delivery_fee_q = (session.data or {}).get("delivery_fee_q")
    delivery_fee_q = int(delivery_fee_q) if delivery_fee_q is not None else None
    delivery_zone_error = bool((session.data or {}).get("delivery_zone_error"))
    delivery_distance_km = (session.data or {}).get("delivery_distance_km")
    delivery_distance_km = float(delivery_distance_km) if delivery_distance_km is not None else None
    grand_total_q = subtotal_q + (delivery_fee_q or 0)

    # Cupom promocional NÃO conta pros thresholds (mínimo de pedido/entrega, frete
    # grátis): aplicar uma cortesia não pode tirar a elegibilidade do cliente. O
    # preço por lote continua contando — é o preço real de venda, não cortesia.
    coupon_discount_q = coupon.discount_q if coupon else 0
    threshold_base_q = subtotal_q + coupon_discount_q
    minimum_order = build_minimum_order_progress(threshold_base_q, channel_ref)
    delivery_minimum = build_delivery_minimum_progress(threshold_base_q, channel_ref)
    free_delivery = build_free_delivery_progress(
        threshold_base_q, channel_ref,
        price_tier_refs=((session.data or {}).get("customer") or {}).get("price_tiers") or (),
    )

    can_checkout, block_reason = _checkout_eligibility(
        is_empty=False,
        has_unavailable=has_unavailable,
        minimum_order=minimum_order,
    )

    came_from = (session.data or {}).get("transferred_from")
    return CartProjection(
        session_key=session_key,
        transferred_from=came_from if isinstance(came_from, dict) else None,
        revision=session.rev,
        lines=lines,
        count=count,
        is_empty=False,
        subtotal_q=subtotal_q,
        original_subtotal_q=original_subtotal_q,
        discount_total_q=discount_total_q,
        discount_lines=discount_lines,
        coupon=coupon,
        delivery_fee_q=delivery_fee_q,
        delivery_is_free=(delivery_fee_q is not None and delivery_fee_q == 0),
        delivery_zone_error=delivery_zone_error,
        delivery_distance_km=delivery_distance_km,
        grand_total_q=grand_total_q,
        loyalty_applied="loyalty_redeem" in pricing,
        has_unavailable=has_unavailable,
        has_awaiting_confirmation=has_awaiting,
        has_ready_for_confirmation=has_ready,
        minimum_order=minimum_order,
        delivery_minimum=delivery_minimum,
        free_delivery=free_delivery,
        upsell=upsell,
        can_checkout=can_checkout,
        checkout_block_reason=block_reason,
        group_savings_message=str((discount_data.get("savings") or {}).get("message") or ""),
    )


# ──────────────────────────────────────────────────────────────────────
# Internals — line + availability resolution (ported from CartService.get_cart)
# ──────────────────────────────────────────────────────────────────────


def _product_facts(
    skus: list[str],
) -> tuple[dict[str, str], frozenset[str], frozenset[str]]:
    """Nome, "preparado na hora" e "ainda vendável" dos SKUs da sacola.

    Uma leitura de ``Product`` para as três perguntas (eram três, para os
    mesmos SKUs). A degradação de cada uma continua a dela: a leitura que falha
    sobe, como subia a do nome; uma derivação que falha esvazia só a própria
    resposta (``_made_to_order_skus``, ``_sellable_skus``).
    """
    from shopman.offerman.models import Product

    products = list(
        Product.objects.filter(sku__in=skus).only("sku", "name", "metadata", "is_sellable")
    )
    names_by_sku = {p.sku: p.name for p in products}
    return names_by_sku, _made_to_order_skus(products, skus), _sellable_skus(products, skus)


def _sellable_skus(products: list, skus: list[str]) -> frozenset[str]:
    """Quais destes SKUs a casa ainda vende (``Product.is_sellable``).

    O mapa de disponibilidade vem do Stockman e só conhece pausa de ESTOQUE; a
    pausa comercial mora no produto. Sem esta leitura, um item despublicado pela
    operação ganharia o sino "Me avise" — e o cliente sairia esperando a volta de
    algo que foi decisão, não falta.
    """
    if not skus:
        return frozenset()
    try:
        return frozenset(p.sku for p in products if p.is_sellable)
    except Exception:
        logger.warning("cart.sellable lookup failed skus=%s", skus, exc_info=True)
        return frozenset()


def _made_to_order_skus(products: list, skus: list[str]) -> frozenset[str]:
    """Quais destes SKUs a casa declara como "Preparado na hora".

    Lido da mesma leitura da sacola inteira (``_product_facts``): perguntar por
    linha faria N+1 numa leitura que roda a cada mexida na sacola. Degrada para
    vazio — selo é promessa, e promessa que não se pode confirmar não se faz.
    """
    if not skus:
        return frozenset()
    try:
        return frozenset(
            p.sku
            for p in products
            if (p.metadata or {}).get("made_to_order")
        )
    except Exception:
        logger.warning("cart.made_to_order lookup failed skus=%s", skus, exc_info=True)
        return frozenset()


def _future_cart_date(session) -> date | None:
    """A data da sacola quando ela é de outro dia; ``None`` para hoje ou sem data.

    A fonte é a mesma da reserva (``cart._cart_date``): o teto da linha
    lê a data em que a sacola reserva. Sacola de hoje (ou sem data) segue na
    leitura canônica do cardápio, sem data explícita.
    """
    from shopman.shop.services.cart import _cart_date

    day = _cart_date(session)
    if day is None or day <= timezone.localdate():
        return None
    return day


def _availability(
    skus: list[str], session_key: str, channel_ref: str, target_date: date | None = None,
) -> tuple[dict[str, dict | None], dict[str, Decimal]]:
    """Canonical catalog availability + own-hold lookup.

    The catalog resolver deliberately reads ready stock for today and, when
    enabled, the first reservable future batch as a separate promise. Passing
    the waitlist horizon directly to Stockman made a zero-day product's fresh
    stock look expired in the cart even while the menu correctly offered it.

    A sacola com data futura (``target_date``) lê ESSA data, a mesma em que a
    reserva sai: o teto da linha não pode ser o pronto de hoje.
    """
    try:
        from shopman.shop.projections import catalog_context
        from shopman.shop.services import availability as availability_service

        avail_map = catalog_context.availability_for_skus(
            skus, channel_ref=channel_ref, target_date=target_date,
        )
        own_holds = availability_service.own_holds_by_sku(session_key, skus)
        return avail_map, own_holds
    except Exception:
        logger.warning("cart.availability check failed skus=%s", skus, exc_info=True)
        return {}, {}


def _build_line(
    item: dict,
    names_by_sku: dict[str, str],
    avail_map: dict[str, dict | None],
    own_holds: dict[str, Decimal],
    discount_items: dict[str, dict],
    *,
    planned_by_sku: dict[str, tuple[bool, bool, str | None, str | None]],
    earlier_by_sku: dict[str, str] | None = None,
    made_to_order_skus: frozenset[str] = frozenset(),
    sellable_skus: frozenset[str] = frozenset(),
) -> CartLineProjection:
    sku = item.get("sku", "")
    qty = Decimal(str(item.get("qty", 0) or 0))
    if qty == qty.to_integral_value():
        qty = int(qty)
    name = item.get("name") or names_by_sku.get(sku) or sku

    raw_avail = avail_map.get(sku)
    # ── Dois eixos, duas fontes. Eles não competem mais. ──
    #
    # "Preparado na hora" é PROMESSA DA CASA sobre o produto (finalizado no
    # momento de servir: gratinado, montado, extraído). Quem declara é o
    # catálogo — ``Product.metadata["made_to_order"]``.
    #
    # "Fila de espera" é ESTADO DA RESERVA desta linha (o hold espera uma
    # fornada que ainda não saiu). Quem responde é o hold.
    #
    # ⚠️ Isto saiu de cima de ``availability_policy == "demand_ok"``, e a troca
    # não é cosmética. ``demand_ok`` é política de CONFERÊNCIA DE ESTOQUE
    # ("aprova a venda mesmo sem saldo"). No catálogo da casa ela cai sobre
    # café e salgados de vitrine, que de fato são finalizados na hora — mas a
    # coincidência não é contrato, e o acoplamento quebrava nos dois sentidos:
    # marcar um PÃO como ``demand_ok`` por razão de estoque dava a ele o selo,
    # e apertar o croque para ``stock_only`` (o natural quando se passa a
    # controlar o estoque dele) tirava o selo, calado.
    #
    # Separados, some a regra de "quem ganha": um croque que espera a fornada
    # de amanhã é as duas coisas ao mesmo tempo, e a sacola pode dizer as duas
    # — o que ele É, e quando ele vem.
    is_made_to_order = sku in made_to_order_skus
    is_awaiting, is_ready, deadline_iso, planned_for_date = planned_by_sku.get(
        sku, _NO_PLANNED_HOLD,
    )
    is_available, available_qty = _line_availability(
        sku, qty, raw_avail, own_holds,
    )
    # "Me avise" só para escassez de verdade: pausa é decisão (e nem o hold
    # próprio reabre a linha), e sobra parcial já tem o "Usar N" como avanço.
    is_notifiable = (
        not is_available
        and not (raw_avail or {}).get("is_paused", False)
        and not available_qty
        and sku in sellable_skus
    )

    disc = discount_items.get(sku)
    unit_price_q = int(item.get("unit_price_q", 0) or 0)
    line_total_q = int(item.get("line_total_q", 0) or 0)
    listed = (item.get("meta") or {}).get("_list_q")
    if listed is None and disc and int(disc.get("original_price_q") or 0) > 0:
        listed = disc["original_price_q"]
    list_price_q = max(unit_price_q, int(listed)) if listed is not None else unit_price_q
    list_total_q = (
        # Mesma conta do ``monetary_mult`` (meio para cima), sem importar o
        # formatador: projection de dados não carrega aparência (regra R-B).
        int((Decimal(str(qty)) * list_price_q).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if list_price_q != unit_price_q
        else line_total_q
    )
    discount_name = (disc.get("name") or "") if disc else None
    discount_is_coupon = bool(disc and disc.get("type") == "coupon")

    return CartLineProjection(
        line_id=str(item.get("line_id") or ""),
        sku=sku,
        name=name,
        qty=qty,
        unit_price_q=unit_price_q,
        line_total_q=line_total_q,
        is_available=is_available,
        available_qty=available_qty,
        is_made_to_order=is_made_to_order,
        is_notifiable=is_notifiable,
        notes=str((item.get("meta") or {}).get("notes") or ""),
        options_summary=product_options.summary(product_options.line_options(item)),
        has_options=bool(product_options.own_options(product_options.line_options(item))),
        is_awaiting_confirmation=is_awaiting,
        is_ready_for_confirmation=is_ready,
        confirmation_deadline_iso=deadline_iso,
        planned_for_date=planned_for_date,
        earlier_available_date=(earlier_by_sku or {}).get(sku),
        list_price_q=list_price_q,
        list_total_q=list_total_q,
        discount_name=discount_name or None,
        discount_is_coupon=discount_is_coupon,
    )


#: Linha sem reserva planejada: nem aguardando, nem pronta, sem prazo, sem data.
_NO_PLANNED_HOLD: tuple[bool, bool, str | None, str | None] = (False, False, None, None)


def _planned_holds(
    session_key: str, skus: list[str],
) -> dict[str, tuple[bool, bool, str | None, str | None]]:
    """Estado da reserva planejada de cada SKU da sacola, numa leitura só.

    ``(aguardando, pronta, prazo ISO, data prevista ISO)`` por SKU; SKU fora do
    mapa não tem reserva planejada (``_NO_PLANNED_HOLD``). Era uma consulta de
    ``Hold`` por linha.
    """
    from shopman.shop.services import availability as availability_service

    planned_by_sku = availability_service.classify_planned_holds_for_session(session_key, skus)
    # O piso é o mesmo para a sacola inteira: calculado uma vez, e só se alguma
    # linha tiver data prevista.
    floor = None
    if any(p.get("planned_for") is not None for p in planned_by_sku.values()):
        floor = _earliest_fulfillable_date()

    out: dict[str, tuple[bool, bool, str | None, str | None]] = {}
    for sku, planned in planned_by_sku.items():
        deadline = planned.get("deadline")
        planned_for = planned.get("planned_for")
        if planned_for is not None:
            # Piso fulfillável: a fornada pode estar datada para HOJE, mas se a loja já
            # fechou (ou hoje é dia fechado) não há retirada hoje. A promessa ao cliente
            # nunca fica abaixo do próximo dia operante — senão a sacola diz "Previsto
            # pra hoje" enquanto o acompanhamento (correto) diz "Estamos fechados".
            planned_for = max(planned_for, floor)
        out[sku] = (
            planned["is_awaiting_confirmation"],
            planned["is_ready_for_confirmation"],
            deadline.isoformat() if deadline is not None else None,
            planned_for.isoformat() if planned_for is not None else None,
        )
    return out


def _earlier_available_dates(
    raw_items: list[dict],
    planned_by_sku: dict[str, tuple[bool, bool, str | None, str | None]],
    channel_ref: str,
) -> dict[str, str]:
    """Por SKU que espera fornada futura, a data anterior em que a linha já tem saldo.

    Só olha linha com data prevista depois do primeiro dia em que a casa
    atende: sacola sem fila não paga leitura nenhuma. Degrada para vazio (a
    data prevista segue sendo o piso).
    """
    from datetime import date as date_type

    waiting = {
        sku: date_type.fromisoformat(state[3])
        for sku, state in planned_by_sku.items()
        if state[3]
    }
    if not waiting or not channel_ref:
        return {}
    first_day = _earliest_fulfillable_date()
    out: dict[str, str] = {}
    try:
        from shopman.shop.policies.order_date_before_batch import earliest_day_with_room

        qty_by_sku: dict[str, Decimal] = {}
        for item in raw_items:
            sku = item.get("sku", "")
            if sku in waiting:
                qty_by_sku[sku] = qty_by_sku.get(sku, Decimal("0")) + Decimal(str(item.get("qty", 0) or 0))
        for sku, qty in qty_by_sku.items():
            if waiting[sku] <= first_day or qty <= 0:
                continue
            day = earliest_day_with_room(
                sku, qty, waiting[sku], channel_ref=channel_ref, first_day=first_day,
            )
            if day is not None:
                out[sku] = day.isoformat()
    except Exception:
        logger.debug("cart._earlier_available_dates degraded", exc_info=True)
        return {}
    return out


def _earliest_fulfillable_date():
    """Próxima data em que a loja realmente opera (hoje só se ainda aberta).

    Fonte da verdade é o ``business_calendar`` (pula dia fechado/feriado e descarta
    hoje após o fechamento). Degrada para ``localdate()`` se sem agenda."""
    from django.utils import timezone

    try:
        from shopman.shop.services import business_calendar

        dates = business_calendar.available_dates(max_count=1)
        return dates[0] if dates else timezone.localdate()
    except Exception:
        logger.debug("cart._earliest_fulfillable_date degraded", exc_info=True)
        return timezone.localdate()


def _line_availability(
    sku: str, qty, avail: dict | None, own_holds: dict[str, Decimal],
) -> tuple[bool, int | Decimal | None]:
    """Decisão do Stockman para a linha, com a reserva da própria sessão como dela.

    Uma linha só fica indisponível quando a falta é real (de fora), nunca porque
    o hold da própria sessão drenou ``total_promisable``; e o SKU sem ledger
    (nenhum ``Quant``) não tem teto, como o Stockman e o commit decidem. A regra
    mora em ``catalog_context.session_line_promise``. Returns
    ``(is_available, available_qty)``; ``None`` = sem teto finito.
    """
    if avail is None:
        return True, None
    from shopman.shop.projections import catalog_context

    approved, ceiling = catalog_context.session_line_promise(
        sku, qty, avail, own_holds.get(sku, Decimal("0")),
    )
    if ceiling is not None and ceiling == ceiling.to_integral_value():
        ceiling = int(ceiling)
    return approved, ceiling


def _discount_lines(discount_data: dict, pricing: dict) -> tuple[CartDiscountLineProjection, ...]:
    """One row per discount origin, aggregated. Coupon/promo carry the raw
    name + ``is_coupon``; the presentation composes the label.
    ``requires_pickup`` acende quando a promoção vencedora é restrita à retirada
    (o ``fulfillment_types`` carimbado pelo motor no registro do desconto).
    """
    agg: dict[tuple[bool, str], dict[str, Any]] = defaultdict(
        lambda: {"amount_q": 0, "requires_pickup": False}
    )
    for d in discount_data.get("items") or []:
        amt = int(d.get("discount_q", 0)) * int(d.get("qty", 0))
        if amt <= 0:
            continue
        name = (d.get("name") or "").strip() or "Promoção"
        entry = agg[(d.get("type") == "coupon", name)]
        entry["amount_q"] += amt
        fulfillment = d.get("fulfillment_types") or []
        if "pickup" in fulfillment and "delivery" not in fulfillment:
            entry["requires_pickup"] = True
    for key in _PRICING_MODIFIER_KEYS:
        mod_data = pricing.get(key) or {}
        amt = int(mod_data.get("total_discount_q", 0))
        if amt > 0:
            agg[(False, mod_data.get("label", key))]["amount_q"] += amt
    return tuple(
        CartDiscountLineProjection(
            name=name,
            is_coupon=is_coupon,
            amount_q=entry["amount_q"],
            requires_pickup=entry["requires_pickup"],
        )
        for (is_coupon, name), entry in sorted(agg.items(), key=lambda kv: -kv[1]["amount_q"])
    )


def _coupon(data: dict, pricing: dict) -> CartCouponProjection | None:
    code = data.get("coupon_code")
    coupon_data = pricing.get("coupon")
    if not (code and coupon_data):
        return None
    discount_q = int(coupon_data.get("discount_q", 0) or 0)
    if discount_q > 0:
        return CartCouponProjection(code=code, discount_q=discount_q)
    return CartCouponProjection(
        code=code,
        discount_q=discount_q,
        zero_reason=str(coupon_data.get("reason") or ""),
        missing_q=int(coupon_data.get("missing_q") or 0),
        fulfillment_types=tuple(coupon_data.get("fulfillment_types") or ()),
    )


def _checkout_eligibility(
    *,
    is_empty: bool,
    has_unavailable: bool,
    minimum_order: MinimumOrderProgressProjection | None,
) -> tuple[bool, str]:
    if is_empty:
        return False, "empty"
    if has_unavailable:
        return False, "unavailable"
    if minimum_order is not None:
        return False, "below_minimum"
    return True, ""


# ──────────────────────────────────────────────────────────────────────
# Minimum-order + upsell (consumed by build_cart and the live mutation payload)
# ──────────────────────────────────────────────────────────────────────


def shop_rule_q(key: str) -> int:
    """Read a cents-valued policy from ``shop.defaults["rules"][key]``.

    ``0``/empty means the policy is off — there is no magic fallback. This is
    the single source for the configurable order/delivery thresholds, so the
    cart, checkout and commit validators all read identical numbers.
    """
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        rules = (shop.defaults.get("rules") or {}) if shop and shop.defaults else {}
        raw = rules.get(key)
        return max(0, int(raw)) if raw else 0
    except Exception as e:
        logger.warning("shop_rule_q_failed key=%s: %s", key, e, exc_info=True)
        return 0


def _threshold_progress(subtotal_q: int, threshold_q: int) -> tuple[int, int] | None:
    """Return ``(remaining_q, percent)`` toward ``threshold_q``, or ``None`` when
    the threshold is off (``0``) or already met."""
    if not threshold_q or subtotal_q >= threshold_q:
        return None
    remaining_q = threshold_q - subtotal_q
    percent = int(min(subtotal_q * 100 / threshold_q, 100))
    return remaining_q, percent


def build_minimum_order_progress(
    subtotal_q: int,
    channel_ref: str = DEFAULT_STOREFRONT_CHANNEL_REF,
) -> MinimumOrderProgressProjection | None:
    """Progress toward the general minimum order (``shop.defaults.rules.minimum_order_q``).

    Applies to every fulfillment type. Returns ``None`` when the policy is off
    (``0``/empty) or the subtotal already meets the minimum. Keeps the rule
    lookup out of every surface so the cart, checkout and live cart-mutation
    payloads consume identical guidance.
    """
    minimum_q = shop_rule_q("minimum_order_q")
    progress = _threshold_progress(subtotal_q, minimum_q)
    if progress is None:
        return None
    remaining_q, percent = progress
    return MinimumOrderProgressProjection(
        minimum_q=minimum_q,
        remaining_q=remaining_q,
        percent=percent,
    )


def build_delivery_minimum_progress(
    subtotal_q: int,
    channel_ref: str = DEFAULT_STOREFRONT_CHANNEL_REF,
) -> MinimumOrderProgressProjection | None:
    """Progress toward the delivery-only minimum (``shop.defaults.rules.delivery_minimum_q``).

    Returns ``None`` when the policy is off or the subtotal already meets it.
    The same value gates the commit in ``DeliveryZoneRule`` — single source.
    Pickup orders carry no minimum, so the surface only shows this in the
    delivery flow.
    """
    minimum_q = shop_rule_q("delivery_minimum_q")
    progress = _threshold_progress(subtotal_q, minimum_q)
    if progress is None:
        return None
    remaining_q, percent = progress
    return MinimumOrderProgressProjection(
        minimum_q=minimum_q,
        remaining_q=remaining_q,
        percent=percent,
    )


def build_free_delivery_progress(
    subtotal_q: int,
    channel_ref: str = DEFAULT_STOREFRONT_CHANNEL_REF,
    *,
    price_tier_refs=(),
) -> FreeDeliveryProgressProjection | None:
    """Progress toward free delivery (``shop.defaults.rules.free_delivery_above_q``).

    Returns ``None`` when the policy is off or the subtotal already qualifies.
    The same value zeroes the fee in ``DeliveryFeeModifier`` — single source.

    Cliente de grupo com frete grátis (``PriceTierAdvantage`` ``free_shipping``)
    mede contra o MENOR dos dois mínimos: o do grupo e o da loja. É o mesmo que o
    ``resolve_delivery_fee_waiver`` usa para zerar a taxa, senão a barra diria
    "faltam R$ 40" a quem já tem frete grátis por ser do grupo.
    """
    threshold_q = shop_rule_q("free_delivery_above_q")
    if price_tier_refs:
        from shopman.shop.policies.group_advantage import free_shipping_minimum_q
        from shopman.shop.services import promotions as promotion_service

        group = promotion_service.best_group_advantage(price_tier_refs, "free_shipping")
        if group is not None:
            group_q = free_shipping_minimum_q(group.value.config)
            threshold_q = group_q if not threshold_q else min(threshold_q, group_q)
            if threshold_q <= 0:
                return None
    progress = _threshold_progress(subtotal_q, threshold_q)
    if progress is None:
        return None
    remaining_q, percent = progress
    return FreeDeliveryProgressProjection(
        threshold_q=threshold_q,
        remaining_q=remaining_q,
        percent=percent,
    )


def _upsell(
    cart_skus: set[str],
    *,
    channel_ref: str = DEFAULT_STOREFRONT_CHANNEL_REF,
) -> UpsellSuggestionProjection | None:
    """Uma sugestão de adicional para esta sacola, ou ``None``.

    Quem escolhe é o motor de sugestão (``projections.suggestions``): a mesma
    regra que o concierge usa, e não mais uma por superfície. A regra anterior
    daqui era "o item mais popular que não está na sacola", e foi ela que
    ofereceu Água a quem levava pão — popularidade não é afinidade.

    Os portões (visível no canal, vendável, disponível agora, fora da sacola)
    são do motor. Degrada para ``None``: sacola sem sugestão é uma sacola sem
    trilho, não uma sacola quebrada.
    """
    from shopman.shop.projections.suggestions import COMPLEMENT, suggest

    try:
        found = suggest(
            COMPLEMENT, cart_skus=cart_skus, channel_ref=channel_ref, surface="web",
        )
    except Exception:
        logger.warning("cart: motor de sugestão falhou; sacola segue sem trilho.", exc_info=True)
        return None

    if not found:
        return None
    top = found[0]
    return UpsellSuggestionProjection(
        sku=top.sku,
        name=top.name,
        unit_price_q=top.unit_price_q,
        image_url=top.image_url,
        reasons=top.reasons,
    )


__all__ = [
    "CartCouponProjection",
    "CartDiscountLineProjection",
    "CartLineProjection",
    "CartProjection",
    "FreeDeliveryProgressProjection",
    "MinimumOrderProgressProjection",
    "UpsellSuggestionProjection",
    "build_cart",
    "build_delivery_minimum_progress",
    "build_free_delivery_progress",
    "build_minimum_order_progress",
    "shop_rule_q",
]
