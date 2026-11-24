"""CartProjection — immutable UI projection for the storefront cart (drawer + page).

Pure presentation: consumes the cart data projection
(``shop.projections.cart.build_cart`` — lines with own-hold-aware
availability, planned-hold state, discount transparency, coupon, totals,
minimum-order progress, upsell and the checkout-eligibility decision) and
shapes it into the frozen dataclass the template renders. Formats ``R$``,
composes "Cupom X"/"Faltam X" copy and the cart actions; resolves nothing
itself.

Never imports from ``shopman.storefront.views.*`` or ``shop.services``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from django.utils import timezone
from shopman.utils.formatting import format_clock, format_local
from shopman.utils.monetary import format_money

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.projections import cart as cart_data
from shopman.shop.projections import catalog_context
from shopman.shop.projections.ready_promise import PromiseFacts, read_promise_facts
from shopman.shop.projections.types import Action, Availability
from shopman.storefront.presentation.catalog import notify_subscribed_skus
from shopman.storefront.presentation.promise import PromiseProjection, promise_for

if TYPE_CHECKING:
    from django.http import HttpRequest  # noqa: F401

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DiscountLineProjection:
    """One aggregated discount row for the cart breakdown.

    ``amount_q`` is the positive cents the customer saved — templates
    prepend the ``-`` sign themselves.
    """

    label: str
    amount_q: int
    amount_display: str
    # A promoção vencedora é restrita à retirada: o checkout avisa antes de o
    # cliente trocar para entrega.
    requires_pickup: bool = False


@dataclass(frozen=True)
class CartItemProjection:
    """A single cart line as rendered on the drawer/page."""

    line_id: str
    sku: str
    name: str
    qty: int
    unit_price_q: int
    total_price_q: int
    price_display: str           # preço CHEIO por unidade, e.g. "R$ 0,90"
    image_url: str | None

    # Pricing transparency — populated when a promo/coupon reduced the line.
    discount_label: str | None
    # Preço por unidade da PROMOÇÃO da linha, o mesmo que o cardápio mostra.
    # A linha exibe ``price_display`` riscado e este ao lado; ``None`` quando
    # não há promoção na linha. Cupom não entra: é do pedido e mora no resumo.
    promo_price_display: str | None
    # O total da linha como a cliente paga, e o cheio para riscar ao lado
    # (decisão do dono 1, 16/11/2026): com promoção do produto, a linha mostra
    # o total com desconto e o cheio riscado; sem promoção, ``line_total_display``
    # é o total cheio e ``line_total_struck_display`` é ``None``. Cupom não
    # abate aqui: é do pedido e mora no resumo.
    line_total_display: str
    line_total_struck_display: str | None
    # Preço de lista por unidade, em centavos: a tela refaz o total da linha
    # enquanto a resposta da troca de quantidade não chega, sem ler número de
    # dentro de ``price_display``.
    list_price_q: int

    # Availability snapshot at render-time.
    is_available: bool
    availability_warning: str | None  # short message when qty > stock
    available_qty: int | None         # how many are actually available (None = demand-based, no ceiling)
    # Esgotado honesto: dá para assinar o retorno daqui mesmo, sem voltar ao
    # cardápio. Pausado não entra — o cliente vê o mesmo "Indisponível", mas não
    # ganha promessa de volta sobre uma decisão do operador.
    is_notifiable: bool
    is_notify_subscribed: bool

    # Planned-hold lifecycle state (AVAILABILITY-PLAN §8): the line is
    # either awaiting confirmation of planned production
    # (``is_awaiting_confirmation``) or the planned stock has materialized
    # and the shopper must confirm before the TTL runs out
    # (``is_ready_for_confirmation``). Both are False on a vanilla
    # ready-stock line.
    is_awaiting_confirmation: bool
    is_ready_for_confirmation: bool
    confirmation_deadline_iso: str | None       # ISO 8601 UTC, fuels the countdown na loja Nuxt
    confirmation_deadline_display: str | None   # pre-formatted HH:MM for badge copy / toast
    planned_for_date: str | None                # ISO date da fornada que a linha espera
    planned_for_notice: str | None              # "Previsto para amanhã" (copy omotenashi + data)
    earlier_available_date: str | None          # ISO date anterior à fornada em que a linha já tem saldo

    # Preparado na hora: promessa declarada da casa
    # (``Product.metadata["made_to_order"]``) — café, Jambon-Beurre, croque,
    # finalizados no momento de servir. O selo diz o que o item É, não o que
    # falta. PODE aparecer junto de ``is_awaiting_confirmation``, e isso é
    # correto: são perguntas diferentes (o que é × quando vem), e a resposta de
    # uma não cala a outra.
    is_made_to_order: bool = False
    made_to_order_label: str = ""

    # Observação do item para a cozinha, escrita pelo cliente ("" = nenhuma).
    notes: str = ""

    # Escolhas no produto: resumo ("+ Ovo frito · Salada"; o nome da linha já o
    # traz) e se a linha tem escolha. Linha com escolha muda pela ``line_id``.
    options_summary: str = ""
    has_options: bool = False

    # Quando fica pronto: a mesma promessa do card e do produto
    # (``presentation/promise``). Na linha que espera uma fornada, o dia é o da
    # reserva. ``None`` = nada a prometer (linha indisponível ou sem dado).
    promise: PromiseProjection | None = None


@dataclass(frozen=True)
class MinimumOrderProgressProjection:
    """Progress bar data for a minimum-order policy (general or delivery-only)."""

    minimum_q: int
    remaining_q: int
    percent: int
    minimum_display: str
    remaining_display: str
    # Copy do aviso, do registro omotenashi (admin-configurável). O Vue monta
    # "{warning_prefix} {remaining_display} {warning_middle} {minimum_display}"
    # + o CTA acionável.
    warning_prefix: str = ""
    warning_middle: str = ""
    add_more_cta: str = ""


@dataclass(frozen=True)
class FreeDeliveryProgressProjection:
    """Progress bar data for the free-delivery upsell."""

    threshold_q: int
    remaining_q: int
    percent: int
    threshold_display: str
    remaining_display: str


@dataclass(frozen=True)
class UpsellSuggestionProjection:
    """Um item oferecido junto do que está na sacola.

    Sem ``reasons`` de propósito: o porquê da sugestão é do Admin e do B.I.,
    não da tela do cliente. Para quem compra, é só um convite.
    """

    sku: str
    name: str
    unit_price_q: int
    price_display: str
    image_url: str | None


@dataclass(frozen=True)
class OpenElsewhereProjection:
    """A sacola aberta da mesma cliente em outro canal (OC-17, C06).

    A loja AVISA que ela existe; não sincroniza nem mescla. Sai só para quem
    entrou com o próprio dispositivo (força ``device``): link encaminhado não
    entrega a conta (S1), nem o que está na sacola de outro canal. Sem chave de
    sessão: a sacola do outro canal é identificada pelo canal.

    ``bring`` é a ação de trazer a sacola para cá. Nasce DESLIGADA: quem a liga é
    a passagem entre canais (``session_transfer``, OC-15/OC-16/OC-18). Enquanto
    ``enabled`` é falso, a tela não oferece o gesto (X1).
    """

    channel: str
    channel_label: str
    items_count: int
    items_phrase: str
    subtotal_q: int
    subtotal_display: str
    bring: Action


@dataclass(frozen=True)
class CartProjection:
    """Full projection for the storefront cart."""

    items: tuple[CartItemProjection, ...]
    items_count: int              # sum of units across lines
    is_empty: bool
    # Copy do estado vazio (registro omotenashi, admin-configurável). Sensível a
    # momento e audiência: a sacola vazia de madrugada não fala como a da manhã,
    # e quem já pediu antes ouve "quer repetir o de sempre?". Vazio quando a
    # sacola tem itens — o Vue só renderiza o bloco sob ``is_empty``.
    empty_title: str
    empty_message: str

    # Totals (dual)
    subtotal_q: int
    subtotal_display: str
    original_subtotal_q: int
    discount_total_q: int
    discount_total_display: str
    has_discount: bool
    # Todo desconto do pedido, um por origem (promoção de produto, cupom,
    # pontos). É o dado; o que a tela SUBTRAI no resumo é
    # ``order_discount_lines``.
    discount_lines: tuple[DiscountLineProjection, ...]

    # O resumo como a cliente lê (decisão do dono 1, 16/11/2026). A promoção
    # do produto já abateu na linha, então:
    # - ``lines_subtotal_*`` é o Subtotal: a soma das linhas como a tela as
    #   mostra (com a promoção do produto, sem cupom nem pontos);
    # - ``promo_savings_*`` diz quanto as promoções de produto já abateram
    #   (informa, não subtrai de novo; ``None`` sem promoção);
    # - ``order_discount_lines`` são as linhas que o resumo subtrai: cupom,
    #   pontos e desconto de pedido. Subtotal menos elas, mais a entrega, é o
    #   Total.
    lines_subtotal_q: int
    lines_subtotal_display: str
    promo_savings_q: int
    promo_savings_display: str | None
    order_discount_lines: tuple[DiscountLineProjection, ...]

    delivery_fee_q: int | None
    delivery_fee_display: str | None
    delivery_is_free: bool
    delivery_zone_error: bool
    # Distância loja→endereço, p/ justificar a taxa no checkout ("a 2 km · R$ 5,00").
    delivery_distance_km: float | None
    delivery_distance_display: str | None
    grand_total_q: int
    grand_total_display: str
    loyalty_applied: bool

    # Coupon
    coupon_code: str | None
    coupon_discount_q: int | None
    coupon_discount_display: str | None
    # Cupom na sacola com desconto zero: o motivo vem do servidor (beta 06/11).
    # "" quando há desconto ou não há cupom. Ver ``CartCouponProjection``.
    coupon_zero_reason: str
    coupon_missing_q: int
    coupon_missing_display: str | None
    coupon_fulfillment_types: tuple[str, ...]

    # Warnings
    has_unavailable_items: bool
    has_awaiting_confirmation_items: bool    # ≥1 line still pre-materialization
    has_ready_for_confirmation_items: bool   # ≥1 line materialized, awaiting shopper confirmation
    # Copy do banner de estoque alterado (registro omotenashi, admin-configurável);
    # o Vue mostra quando ``has_unavailable_items`` — acima do tratamento por-item.
    unavailable_banner: str
    # Aviso sob o badge "Aguardando confirmação" por item (registro omotenashi,
    # admin-configurável); o Vue mostra na linha em espera de materialização.
    awaiting_confirmation_notice: str

    # Minimum order + upsell context
    minimum_order_progress: MinimumOrderProgressProjection | None
    # Delivery-only minimum, shown in the delivery step ("Pedido mínimo para
    # entrega R$X · faltam R$Y"). Pickup never carries one.
    delivery_minimum_progress: MinimumOrderProgressProjection | None
    # Free-delivery upsell ("faltam R$Y para frete grátis"), reuses the bar.
    free_delivery_progress: FreeDeliveryProgressProjection | None
    upsell: UpsellSuggestionProjection | None

    # Canonical cart-level actions. Surfaces render these instead of deriving
    # checkout eligibility from local cart flags.
    actions: tuple[Action, ...]
    revision: int = 0
    draft_context: str = ""
    # Economia do grupo (texto por grupo, Admin). Vazia quando não houve.
    group_savings_message: str = ""
    # Reserva com prazo à vista (WP-L11, decisão do dono 4 de 16/11/2026): até
    # quando a sacola guarda os itens. É o menor prazo das reservas vivas da
    # sessão; cada gesto na sacola renova, e a resposta já traz a hora nova.
    # ``None`` quando nada tem prazo correndo (sacola vazia, só item de fornada
    # futura): a tela não promete hora nenhuma. ``reserved_until_display`` é a
    # hora no formato da casa ("19h18"). O relógio do servidor NÃO mora aqui: a
    # projeção é o estado da sacola e sai igual em toda resposta do mesmo
    # estado (o replay de uma oferta e o gêmeo público dependem disso). Ele vai
    # no envelope da leitura da sacola (``GET /api/v1/storefront/cart/``).
    reserved_until_iso: str | None = None
    reserved_until_display: str | None = None
    # A reserva que venceu e não foi renovada (#2767): a hora até quando ela valia,
    # para quem abre a sacola depois do prazo ler o que houve ("A reserva valia até
    # 19h18 e já venceu"). Prazo de outro dia leva a data ("18/11 às 19h18").
    # ``None`` com reserva viva (a sacola diz até quando guarda) ou sem reserva
    # vencida de item que está na sacola.
    reservation_lapsed_display: str | None = None
    # Sacolas abertas da mesma cliente em outros canais (OC-17, C06): aviso, nunca
    # sincronização. Vazio para visitante, para link encaminhado e sem outra sacola.
    open_elsewhere: tuple[OpenElsewhereProjection, ...] = ()


# ──────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────


def build_cart(
    *,
    request: HttpRequest,
    channel_ref: str,
) -> CartProjection:
    """Build a ``CartProjection`` for the current visitor.

    Always returns a projection — an empty cart becomes
    ``CartProjection(items=(), is_empty=True, ...)``. Never raises for
    business conditions; stock shortfalls surface as per-line warnings.
    """
    session_key = request.session.get("cart_session_key")
    data = cart_data.build_cart(session_key, channel_ref)

    image_by_sku = _image_by_sku(line.sku for line in data.lines)
    planned_notice_template = (
        resolve_copy("CART_WAITLIST_PLANNED_DATE", moment="*", audience="*").message or ""
    ).strip()
    # Selo do item preparado na hora. Configurável no Admin como todo o resto da voz
    # da casa — o padrão diz o que É, não o que falta.
    made_to_order_label = (
        resolve_copy("PRODUCT_MADE_TO_ORDER", moment="*", audience="*").title or ""
    ).strip()
    # Quem já pediu o aviso vê "Anotado" também na sacola — mesmo dono da
    # pergunta que o card e a PDP usam.
    subscribed_skus = notify_subscribed_skus(request)
    promise_facts = read_promise_facts(
        [line.sku for line in data.lines], channel_ref=channel_ref, day_known=True
    )
    items = tuple(
        _present_line(
            line, image_by_sku, planned_notice_template, made_to_order_label,
            subscribed_skus=subscribed_skus,
            promise_facts=promise_facts,
        )
        for line in data.lines
    )

    summary = _summary(data)
    min_order = present_minimum_order(data.minimum_order)
    delivery_minimum = present_minimum_order(data.delivery_minimum)
    free_delivery = present_free_delivery(data.free_delivery)
    upsell = present_upsell(data.upsell)
    actions = _cart_actions(data, min_order)
    empty_title, empty_message = _empty_copy(request, is_empty=data.is_empty)

    from shopman.storefront.identity import checkout_draft_context
    context = checkout_draft_context(request, session_key)
    reserved_until = None if data.is_empty else cart_data.reserved_until(session_key)
    lapsed_at = (
        None if data.is_empty or reserved_until
        else cart_data.reservation_lapsed_at(session_key, [line.sku for line in data.lines])
    )
    return CartProjection(
        reserved_until_iso=_iso(reserved_until),
        reserved_until_display=(format_clock(reserved_until) or None) if reserved_until else None,
        reservation_lapsed_display=_lapsed_display(lapsed_at),
        open_elsewhere=_open_elsewhere(request, channel_ref),
        revision=data.revision,
        draft_context=context,
        items=items,
        items_count=data.count,
        is_empty=data.is_empty,
        empty_title=empty_title,
        empty_message=empty_message,
        subtotal_q=data.subtotal_q,
        subtotal_display=_money(data.subtotal_q),
        original_subtotal_q=data.original_subtotal_q,
        discount_total_q=data.discount_total_q,
        discount_total_display=_money(data.discount_total_q),
        has_discount=data.discount_total_q > 0,
        discount_lines=tuple(_present_discount_line(dl) for dl in data.discount_lines),
        lines_subtotal_q=summary.lines_subtotal_q,
        lines_subtotal_display=_money(summary.lines_subtotal_q),
        promo_savings_q=summary.promo_savings_q,
        promo_savings_display=(
            _money(summary.promo_savings_q) if summary.promo_savings_q else None
        ),
        order_discount_lines=tuple(
            _present_discount_line(dl) for dl in summary.order_discount_lines
        ),
        delivery_fee_q=data.delivery_fee_q,
        delivery_fee_display=_delivery_fee_display(data),
        delivery_is_free=data.delivery_is_free,
        delivery_zone_error=data.delivery_zone_error,
        delivery_distance_km=data.delivery_distance_km,
        delivery_distance_display=_delivery_distance_display(data),
        loyalty_applied=data.loyalty_applied,
        grand_total_q=data.grand_total_q,
        grand_total_display=_money(data.grand_total_q),
        coupon_code=data.coupon.code if data.coupon else None,
        coupon_discount_q=data.coupon.discount_q if data.coupon else None,
        coupon_discount_display=(
            _money(data.coupon.discount_q)
            if data.coupon and data.coupon.discount_q
            else None
        ),
        coupon_zero_reason=data.coupon.zero_reason if data.coupon else "",
        coupon_missing_q=data.coupon.missing_q if data.coupon else 0,
        coupon_missing_display=(
            _money(data.coupon.missing_q) if data.coupon and data.coupon.missing_q else None
        ),
        coupon_fulfillment_types=data.coupon.fulfillment_types if data.coupon else (),
        has_unavailable_items=data.has_unavailable,
        has_awaiting_confirmation_items=data.has_awaiting_confirmation,
        has_ready_for_confirmation_items=data.has_ready_for_confirmation,
        unavailable_banner=(
            resolve_copy("CART_UNAVAILABLE_BANNER", moment="*", audience="*").message or ""
        ).strip(),
        awaiting_confirmation_notice=(
            resolve_copy("CART_WAITLIST_NOTICE", moment="*", audience="*").message or ""
        ).strip(),
        minimum_order_progress=min_order,
        delivery_minimum_progress=delivery_minimum,
        free_delivery_progress=free_delivery,
        upsell=upsell,
        actions=actions,
        group_savings_message=data.group_savings_message,
    )


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _present_line(
    line: cart_data.CartLineProjection,
    image_by_sku: dict[str, str | None],
    planned_notice_template: str = "",
    made_to_order_label: str = "",
    subscribed_skus: frozenset[str] | set[str] = frozenset(),
    promise_facts: PromiseFacts | None = None,
) -> CartItemProjection:
    # ``is_available`` already reflects the own-hold correction. When false,
    # the stock really fell behind what this session reserved — surface the
    # exact delta.
    warning: str | None = None
    if not line.is_available:
        if line.available_qty is not None and line.available_qty > 0:
            unit_word = "unidade disponível" if line.available_qty == 1 else "unidades disponíveis"
            warning = f"Apenas {line.available_qty} {unit_word}"
        else:
            warning = "Indisponível"

    discount_label: str | None = None
    if line.discount_name:
        discount_label = (
            f"Cupom {line.discount_name}" if line.discount_is_coupon else line.discount_name
        )

    # O cardápio mostrou "antes R$ 6,00, R$ 5,10"; a linha da sacola repete a
    # mesma dupla para o preço não mudar no caminho (beta 06/11). Decisão do
    # dono 1 (16/11/2026): com promoção do produto, o unitário E o total da
    # linha falam o preço com desconto, cada um com o cheio riscado ao lado.
    # Sem promoção (inclusive com cupom ou oferta de valor fixo, que são do
    # pedido), a linha fala o cheio e o desconto mora no resumo.
    promo_price_display: str | None = None
    line_total_display = _money(line.list_total_q)
    line_total_struck_display: str | None = None
    if _has_product_promo(line):
        promo_price_display = _money(line.unit_price_q)
        line_total_display = _money(line.line_total_q)
        line_total_struck_display = _money(line.list_total_q)

    return CartItemProjection(
        line_id=line.line_id,
        sku=line.sku,
        name=line.name,
        qty=line.qty,
        unit_price_q=line.unit_price_q,
        total_price_q=line.line_total_q,
        # O unitário cheio. Desconto de PEDIDO rateado na linha nunca vira preço
        # exibido: "2 × R$ 8,00" num croissant de R$ 13 fazia as linhas somarem
        # 16 sob um Subtotal de 26 (beta 05/11, MKT-05).
        price_display=_money(line.list_price_q),
        image_url=image_by_sku.get(line.sku),
        discount_label=discount_label,
        promo_price_display=promo_price_display,
        line_total_display=line_total_display,
        line_total_struck_display=line_total_struck_display,
        list_price_q=line.list_price_q,
        is_available=line.is_available,
        availability_warning=warning,
        available_qty=line.available_qty,
        is_notifiable=line.is_notifiable,
        is_notify_subscribed=line.is_notifiable and line.sku in subscribed_skus,
        is_made_to_order=line.is_made_to_order,
        made_to_order_label=(
            made_to_order_label if line.is_made_to_order else ""
        ),
        is_awaiting_confirmation=line.is_awaiting_confirmation,
        is_ready_for_confirmation=line.is_ready_for_confirmation,
        confirmation_deadline_iso=line.confirmation_deadline_iso,
        confirmation_deadline_display=_deadline_display(line.confirmation_deadline_iso),
        planned_for_date=line.planned_for_date,
        earlier_available_date=line.earlier_available_date,
        planned_for_notice=_planned_for_notice(line, planned_notice_template),
        notes=line.notes,
        options_summary=line.options_summary,
        has_options=line.has_options,
        promise=_line_promise(line, promise_facts),
    )


def _has_product_promo(line: cart_data.CartLineProjection) -> bool:
    """A linha tem promoção do PRODUTO: o desconto abate nela, não no resumo.

    Cupom e oferta de valor fixo são do pedido: o motor rateia o valor no preço
    cobrado, mas a linha segue falando o cheio.
    """
    return bool(
        line.discount_name
        and not line.discount_is_coupon
        and line.unit_price_q < line.list_price_q
    )


@dataclass(frozen=True)
class _CartSummary:
    lines_subtotal_q: int
    promo_savings_q: int
    order_discount_lines: tuple[cart_data.CartDiscountLineProjection, ...]


def _summary(data: cart_data.CartProjection) -> _CartSummary:
    """O resumo que fecha com as linhas (decisão do dono 1, 16/11/2026).

    O Subtotal é a soma das linhas como a tela as mostra: com promoção do
    produto, o total com desconto; sem ela, o cheio. As linhas de desconto do
    resumo são o que sobra depois de tirar o que já abateu nas linhas: cupom,
    pontos e desconto de pedido. Subtotal menos elas é o que a cliente paga
    pelos itens (``subtotal_q``).
    """
    lines_subtotal_q = 0
    promo_savings_q = 0
    saved_by_promo: dict[str, int] = {}
    for line in data.lines:
        if _has_product_promo(line):
            saved_q = max(line.list_total_q - line.line_total_q, 0)
            promo_savings_q += saved_q
            name = line.discount_name or ""
            saved_by_promo[name] = saved_by_promo.get(name, 0) + saved_q
            lines_subtotal_q += line.line_total_q
        else:
            lines_subtotal_q += line.list_total_q

    order_rows: list[cart_data.CartDiscountLineProjection] = []
    for row in data.discount_lines:
        on_lines_q = 0 if row.is_coupon else saved_by_promo.get(row.name, 0)
        amount_q = row.amount_q - on_lines_q
        if amount_q > 0:
            order_rows.append(replace(row, amount_q=amount_q))

    closes_q = lines_subtotal_q - sum(row.amount_q for row in order_rows)
    if closes_q != data.subtotal_q:
        # A tela mostraria um resumo que não soma. Não há como consertar aqui
        # sem inventar número: o aviso é para quem mantém o motor de preço.
        logger.warning(
            "cart.summary_does_not_close shown_q=%s charged_q=%s",
            closes_q, data.subtotal_q,
        )
    return _CartSummary(
        lines_subtotal_q=lines_subtotal_q,
        promo_savings_q=promo_savings_q,
        order_discount_lines=tuple(order_rows),
    )


def _line_promise(
    line: cart_data.CartLineProjection, facts: PromiseFacts | None,
) -> PromiseProjection | None:
    """A promessa da linha, pela mesma função do card e do produto.

    A linha já tem dia: a da fornada que ela reservou (``planned_for_date``), ou
    hoje, quando a reserva é do pronto de hoje (ou o item não tem estoque
    controlado). A grade do checkout decide o resto: casa fechada ou corte do
    dia levam a promessa para o próximo dia com horário.
    """
    if facts is None:
        return None
    from datetime import date

    planned_for = facts.today
    if line.planned_for_date:
        try:
            planned_for = date.fromisoformat(line.planned_for_date)
        except ValueError:
            return None
    return promise_for(
        line.sku,
        facts,
        orderable=line.is_available,
        planned_for=planned_for,
        made_to_order=line.is_made_to_order,
    )


def _present_discount_line(dl: cart_data.CartDiscountLineProjection) -> DiscountLineProjection:
    return DiscountLineProjection(
        label=f"Cupom {dl.name}" if dl.is_coupon else dl.name,
        amount_q=dl.amount_q,
        amount_display=_money(dl.amount_q),
        requires_pickup=dl.requires_pickup,
    )


def _delivery_fee_display(data: cart_data.CartProjection) -> str | None:
    if data.delivery_fee_q is None:
        return None
    return "Grátis" if data.delivery_is_free else _money(data.delivery_fee_q)


def _delivery_distance_display(data: cart_data.CartProjection) -> str | None:
    km = data.delivery_distance_km
    if km is None:
        return None
    if km == int(km):
        return f"{int(km)} km"
    return f"{km:.1f}".replace(".", ",") + " km"


def _planned_for_notice(
    line: cart_data.CartLineProjection, template: str,
) -> str | None:
    """Compose the waitlist line's expected-batch notice ("Previsto para amanhã").

    Only meaningful while the line still awaits materialization — a ready
    line already shows the confirmation deadline instead.
    """
    if not line.is_awaiting_confirmation or not template:
        return None
    display = _planned_for_display(line.planned_for_date)
    if not display:
        return None
    return template.replace("{date}", display)


def _planned_for_display(planned_iso: str | None) -> str | None:
    # A data já chega TRUTHFUL do read-side (``shop.projections.cart`` fixa o piso
    # fulfillável: nunca "hoje" com a loja fechada). Aqui é só formatação.
    if not planned_iso:
        return None
    try:
        from datetime import date, timedelta

        from django.utils import formats
        from django.utils import timezone as _tz

        planned = date.fromisoformat(planned_iso)
        today = _tz.localdate()
        if planned <= today:
            return "hoje"
        if planned == today + timedelta(days=1):
            return "amanhã"
        return f"{formats.date_format(planned, 'l')}, {formats.date_format(planned, 'd/m')}"
    except Exception:
        logger.debug("cart._planned_for_display degraded", exc_info=True)
        return None


def present_cart_date_mismatch(*, name: str, cart_date, item_date) -> dict[str, str]:
    """A recusa do item de OUTRA data, na voz da loja: é outro pedido.

    Não é "indisponível" (o item existe) nem "ajuste a quantidade" (nenhuma
    quantidade resolve): na loja online cada pedido tem uma data só.
    """
    item_day = _planned_for_display(_iso(item_date)) or "outra data"
    cart_day = _planned_for_display(_iso(cart_date)) or "outra data"
    return {
        "title": "Isso fica para outro pedido",
        "detail": (
            f"{name} é para {item_day}, e sua sacola é para {cart_day}. "
            f"Cada pedido tem uma data só: envie este e monte outro pedido para {item_day}."
        ),
        "item_day_display": item_day,
        "cart_day_display": cart_day,
    }


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _lapsed_display(lapsed_at) -> str | None:
    """A hora da reserva vencida; de outro dia, com a data ("18/11 às 19h18")."""
    if lapsed_at is None:
        return None
    if timezone.localtime(lapsed_at).date() == timezone.localdate():
        return format_clock(lapsed_at) or None
    return format_local(lapsed_at, "%d/%m às {clock}", empty="") or None


def _deadline_display(deadline_iso: str | None) -> str | None:
    if not deadline_iso:
        return None
    try:
        from datetime import datetime


        return format_clock(datetime.fromisoformat(deadline_iso))
    except Exception:
        logger.debug("cart._deadline_display degraded", exc_info=True)
        return None


def present_minimum_order(
    data: cart_data.MinimumOrderProgressProjection | None,
) -> MinimumOrderProgressProjection | None:
    """Format the minimum-order progress data into the cart presentation DTO.

    Shared by the cart and the checkout order-summary partial so the ``R$``
    strings come from one place.
    """
    if data is None:
        return None

    def _msg(key: str) -> str:
        return (resolve_copy(key, moment="*", audience="*").message or "").strip()

    return MinimumOrderProgressProjection(
        minimum_q=data.minimum_q,
        remaining_q=data.remaining_q,
        percent=data.percent,
        minimum_display=_money(data.minimum_q),
        remaining_display=_money(data.remaining_q),
        warning_prefix=_msg("MIN_ORDER_WARNING_PREFIX"),
        warning_middle=_msg("MIN_ORDER_WARNING_MIDDLE"),
        add_more_cta=_msg("MIN_ORDER_WARNING"),
    )


def present_free_delivery(
    data: cart_data.FreeDeliveryProgressProjection | None,
) -> FreeDeliveryProgressProjection | None:
    """Format the free-delivery progress data into the cart presentation DTO."""
    if data is None:
        return None
    return FreeDeliveryProgressProjection(
        threshold_q=data.threshold_q,
        remaining_q=data.remaining_q,
        percent=data.percent,
        threshold_display=_money(data.threshold_q),
        remaining_display=_money(data.remaining_q),
    )


def present_upsell(
    data: cart_data.UpsellSuggestionProjection | None,
) -> UpsellSuggestionProjection | None:
    """Format the upsell suggestion data into the cart presentation DTO."""
    if data is None:
        return None
    return UpsellSuggestionProjection(
        sku=data.sku,
        name=data.name,
        unit_price_q=data.unit_price_q,
        price_display=_money(data.unit_price_q) if data.unit_price_q else "",
        image_url=data.image_url,
    )


def _image_by_sku(skus) -> dict[str, str | None]:
    """Resolve image URLs in a single query for rendering thumbnails."""
    return catalog_context.image_urls_by_sku(skus)


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


def _open_elsewhere(request: HttpRequest, channel_ref: str) -> tuple[OpenElsewhereProjection, ...]:
    """As outras sacolas abertas da cliente que entrou com o próprio dispositivo."""
    from shopman.storefront.identity import get_authenticated_customer, knows_only_the_number

    if getattr(request, "customer", None) is None or knows_only_the_number(request):
        return ()
    customer = get_authenticated_customer(request)
    if customer is None:
        return ()
    return tuple(
        OpenElsewhereProjection(
            channel=entry.channel_ref,
            channel_label=entry.channel_name,
            items_count=entry.items_count if isinstance(entry.items_count, int) else entry.lines_count,
            items_phrase=cart_data.items_phrase(entry),
            subtotal_q=entry.subtotal_q,
            subtotal_display=_money(entry.subtotal_q),
            bring=Action(
                ref="bring_cart",
                kind="mutation",
                label="Trazer esta sacola para cá",
                priority="secondary",
                enabled=False,
                reason="A passagem da sacola entre canais ainda não está ligada.",
            ),
        )
        for entry in cart_data.open_elsewhere(customer.ref, channel_ref)
    )


def _empty_copy(request: HttpRequest, *, is_empty: bool) -> tuple[str, str]:
    """Título e mensagem do estado vazio, por momento e audiência.

    Só resolve quando a sacola está vazia: montar o contexto omotenashi custa
    uma leitura do estado do negócio, e a sacola com itens nunca renderiza o
    bloco.
    """
    if not is_empty:
        return "", ""
    from shopman.shop.omotenashi import OmotenashiContext

    omo = OmotenashiContext.from_request(request)
    entry = resolve_copy("CART_EMPTY", moment=omo.moment, audience=omo.audience)
    return (entry.title or "").strip(), (entry.message or "").strip()


def _cart_actions(
    data: cart_data.CartProjection,
    minimum_order_progress: MinimumOrderProgressProjection | None,
) -> tuple[Action, ...]:
    """Map the data projection's checkout-eligibility decision to actions.

    The orchestrator decided ``can_checkout`` + ``checkout_block_reason``; the
    presentation only renders the matching label/reason copy.
    """
    checkout_enabled = data.can_checkout
    checkout_reason = ""
    checkout_label = "Finalizar pedido"

    def _reason(key: str, fallback: str) -> str:
        return resolve_copy(key, moment="*", audience="*").message or fallback

    if data.checkout_block_reason == "empty":
        checkout_reason = _reason("CART_CHECKOUT_BLOCK_EMPTY", "Sacola vazia.")
    elif data.checkout_block_reason == "unavailable":
        checkout_reason = _reason(
            "CART_CHECKOUT_BLOCK_UNAVAILABLE", "Revise itens indisponíveis antes de finalizar."
        )
    elif data.checkout_block_reason == "below_minimum":
        checkout_reason = (
            f"Faltam {minimum_order_progress.remaining_display} para o pedido mínimo."
            if minimum_order_progress is not None
            else _reason("CART_CHECKOUT_BLOCK_MIN_ORDER", "Pedido mínimo não atingido.")
        )
    elif data.has_ready_for_confirmation:
        checkout_label = "Confirmar agora"

    return (
        Action(
            ref="checkout",
            kind="link",
            label=checkout_label,
            priority="primary",
            enabled=checkout_enabled,
            reason=checkout_reason,
            href="/finalizar",
            idempotency="none",
        ),
        Action(
            ref="continue_shopping",
            kind="link",
            label="Continuar comprando",
            priority="secondary",
            enabled=True,
            href="/menu",
            idempotency="none",
        ),
    )


# Re-export for convenience so ``from shopman.shop.projections import Availability``
# remains the single import the cart template needs alongside ``build_cart``.
__all__ = [
    "Availability",
    "CartItemProjection",
    "CartProjection",
    "DiscountLineProjection",
    "FreeDeliveryProgressProjection",
    "MinimumOrderProgressProjection",
    "OpenElsewhereProjection",
    "UpsellSuggestionProjection",
    "build_cart",
    "present_cart_date_mismatch",
]
