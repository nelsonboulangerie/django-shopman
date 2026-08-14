"""Cart mutation facade.

A superfície cuida de HTTP, sessão e apresentação; este módulo cuida das escritas
contra as sessions do Orderman e os holds do Stockman — e, desde a ADR-019, também
das **portas de validação do cupom**, que moravam na superfície da loja e por isso
deixavam o PDV sem cupom.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.orderman.models import Session

from shopman.shop.services import availability, lot_pricing
from shopman.shop.services import sessions as session_service

logger = logging.getLogger(__name__)


class CartUnavailableError(Exception):
    """Raised when a cart mutation cannot reserve the requested stock."""

    def __init__(
        self,
        sku: str,
        requested_qty: int,
        available_qty: int,
        is_paused: bool,
        substitutes: list[dict],
        error_code: str,
        is_planned: bool = False,
        planned_target_date=None,
    ):
        super().__init__(f"unavailable: sku={sku} qty={requested_qty} avail={available_qty}")
        self.sku = sku
        self.requested_qty = requested_qty
        self.available_qty = available_qty
        self.is_paused = is_paused
        self.substitutes = substitutes
        self.error_code = error_code
        self.is_planned = is_planned
        self.planned_target_date = planned_target_date


def get_open_session(*, session_key: str, channel_ref: str) -> Session | None:
    """Return an open cart session, if it still exists."""
    return Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).first()


def reprice(*, session_key: str, channel_ref: str) -> Session | None:
    """Re-run session modifiers without mutating lines.

    Used after a non-line change to ``session.data`` (e.g. linking the customer)
    so the pricing reflects it — the discount modifier reads customer tier/segment
    from the session. Returns ``None`` if the session is gone.
    """
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None
    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )


def get_or_create_session(
    *,
    session_key: str | None,
    channel_ref: str,
    origin_channel: str,
) -> tuple[Session, str]:
    """Return an open session key for cart mutations."""
    if session_key:
        session = get_open_session(session_key=session_key, channel_ref=channel_ref)
        if session is not None:
            return session, session.session_key

    session = session_service.create_session(
        channel_ref,
        data={"origin_channel": origin_channel},
    )
    return session, session.session_key


def add_item(
    *,
    session_key: str | None,
    channel_ref: str,
    origin_channel: str,
    sku: str,
    qty: int,
    unit_price_q: int,
    name: str = "",
) -> tuple[Session, str]:
    """Reserve stock and add or merge a cart line."""
    session, resolved_key = get_or_create_session(
        session_key=session_key,
        channel_ref=channel_ref,
        origin_channel=origin_channel,
    )

    existing = next((item for item in session.items if item.get("sku") == sku), None)
    hold_id = _reserve_or_raise(
        sku=sku,
        qty=qty,
        session_key=resolved_key,
        channel_ref=channel_ref,
    )
    availability.bump_session_hold_expiry(resolved_key)

    if existing:
        new_qty = int(Decimal(str(existing["qty"]))) + qty
        return (
            session_service.modify_session(
                session_key=resolved_key,
                channel_ref=channel_ref,
                ops=[{"op": "set_qty", "line_id": existing["line_id"], "qty": new_qty}],
            ),
            resolved_key,
        )

    op: dict = {"op": "add_line", "sku": sku, "qty": qty, "unit_price_q": unit_price_q}
    if name:
        op["name"] = name
    # O lote que a reserva ancorou vira flag durável de linha (``meta``, único
    # lugar que sobrevive ao ``_normalize_items``). É daqui que o
    # LotDiscountModifier lê o desconto congelado no lote — ADR-017 §7.
    batch_ref = lot_pricing.batch_ref_for_hold(hold_id)
    if batch_ref:
        op["meta"] = {"batch_ref": batch_ref}
    return (
        session_service.modify_session(
            session_key=resolved_key,
            channel_ref=channel_ref,
            ops=[op],
        ),
        resolved_key,
    )


def update_qty(
    *,
    session_key: str,
    channel_ref: str,
    line_id: str,
    qty: int,
    sku: str | None = None,
) -> Session:
    """Reconcile holds and update a cart line quantity."""
    line_sku = sku
    if line_sku is None:
        line = get_line(session_key=session_key, channel_ref=channel_ref, line_id=line_id)
        line_sku = line["sku"] if line is not None else None
    if line_sku is not None:
        result = availability.reconcile(
            sku=line_sku,
            new_qty=Decimal(str(qty)),
            session_key=session_key,
            channel_ref=channel_ref,
        )
        if not result["ok"]:
            raise CartUnavailableError(
                sku=line_sku,
                requested_qty=qty,
                available_qty=int(result["available_qty"]),
                is_paused=result["is_paused"],
                substitutes=result["substitutes"],
                error_code=result["error_code"],
                is_planned=result.get("is_planned", False),
            )

    availability.bump_session_hold_expiry(session_key)
    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[{"op": "set_qty", "line_id": line_id, "qty": qty}],
    )


def remove_item(
    *,
    session_key: str,
    channel_ref: str,
    line_id: str,
    sku: str | None = None,
) -> Session:
    """Reconcile holds and remove a cart line."""
    line_sku = sku
    if line_sku is None:
        line = get_line(session_key=session_key, channel_ref=channel_ref, line_id=line_id)
        line_sku = line["sku"] if line is not None else None
    if line_sku is not None:
        availability.reconcile(
            sku=line_sku,
            new_qty=Decimal("0"),
            session_key=session_key,
            channel_ref=channel_ref,
        )

    availability.bump_session_hold_expiry(session_key)
    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[{"op": "remove_line", "line_id": line_id}],
    )


def get_line(*, session_key: str, channel_ref: str, line_id: str) -> dict | None:
    """Return the session line dict matching ``line_id``."""
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None
    for item in session.items:
        if item.get("line_id") == line_id:
            return item
    return None


class CouponRejected(Exception):
    """Cupom recusado numa das portas. ``code`` é a razão, em vocabulário estável.

    A superfície traduz ``code`` para mensagem no idioma do público e devolve no
    dialeto ``{detail, field, errors}``. O motivo vem daqui porque quem decide é o
    orquestrador; a superfície só interpreta request e formata resposta.
    """

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def customer_eligible_for_promotion(customer, promotion) -> bool:
    """``customer`` satisfaz o alvo POR CLIENTE da promoção?

    Só valida o que depende de QUEM é o cliente — ``customer_segments`` (grupo/RFM) e
    ``birthday_only`` —, porque se não batem o desconto seria sempre 0. Restrição por
    item ou contexto (``skus``, ``collections``, ``fulfillment_types``) NÃO entra: ela
    decide QUAIS itens recebem desconto, não se o cliente pode usar o cupom. Espelha
    ``DiscountModifier._matches`` nesses dois eixos.

    ``customer`` é o cliente já resolvido (ou ``None`` para visitante anônimo).
    """
    from django.core.exceptions import ObjectDoesNotExist
    from django.utils import timezone as tz

    segments = list(getattr(promotion, "customer_segments", None) or [])
    birthday_only = bool(getattr(promotion, "birthday_only", False))
    if not segments and not birthday_only:
        return True  # cupom aberto a todos

    if customer is None:
        return False  # alvo exige identidade; visitante anônimo não qualifica

    if segments:
        tier_ref = customer.price_tier.ref if getattr(customer, "price_tier_id", None) else ""
        try:
            rfm_segment = customer.insight.rfm_segment or ""
        except ObjectDoesNotExist:
            # Sem insight calculado (OneToOne ausente) o cliente só casa por faixa;
            # segmento RFM fica vazio. Degrada sem bloquear o cupom.
            logger.debug("coupon_eligibility_insight_missing")
            rfm_segment = ""
        if tier_ref not in segments and rfm_segment not in segments:
            return False

    if birthday_only:
        birthday = getattr(customer, "birthday", None)
        if not birthday:
            return False
        today = tz.localdate()
        if not (birthday.month == today.month and birthday.day == today.day):
            return False

    return True


def validate_and_apply_coupon(
    *,
    session_key: str,
    channel_ref: str,
    code: str,
    customer=None,
) -> tuple[Session, str]:
    """As portas do cupom + a aplicação. Devolve ``(session, nome da promoção)``.

    Estas validações moravam em ``storefront/cart.py``, e por isso **o PDV não tinha
    cupom**: para ganhá-lo teria de reimplementar as mesmas cinco portas, e duas
    implementações da mesma pergunta divergem por construção. Agora a superfície só
    interpreta request e formata erro; quem decide é o orquestrador (ADR-019).

    Levanta ``CouponRejected`` com um destes códigos:

    · ``invalid_coupon`` — não existe, ou está inativo
    · ``coupon_exhausted`` — passou de ``max_uses``
    · ``coupon_expired`` — promoção inativa ou fora da janela
    · ``coupon_wrong_channel`` — a promoção não vale neste canal (ADR-019 §4).
      Porta nova: antes ``Promotion.channels`` não existia, então um cupom da web
      era aceito no balcão e descontava mesmo assim.
    · ``coupon_not_eligible`` — o alvo por cliente não bate. Recusar aqui em vez de
      gravar um cupom MUDO (desconto 0) sem avisar — ex.: FUNCIONARIO
      (``customer_segments=["staff"]``) na mão de quem não é staff.
    """
    from django.utils import timezone as tz

    from shopman.shop.models import Coupon

    code = (code or "").strip().upper()

    try:
        coupon = (
            Coupon.objects.select_related("promotion")
            .prefetch_related("promotion__channels")
            .get(code=code, is_active=True)
        )
    except Coupon.DoesNotExist:
        raise CouponRejected("invalid_coupon") from None

    if not coupon.is_available:
        raise CouponRejected("coupon_exhausted")

    promotion = coupon.promotion
    now = tz.now()
    if not promotion.is_active or now < promotion.valid_from or now > promotion.valid_until:
        raise CouponRejected("coupon_expired")

    if not promotion.applies_to_channel(channel_ref):
        raise CouponRejected("coupon_wrong_channel")

    if not customer_eligible_for_promotion(customer, promotion):
        raise CouponRejected("coupon_not_eligible")

    # A identidade (ref + grupo) vai para a sessão junto do cupom: um cupom segmentado
    # só desconta se o modifier souber grupo/segmento, e ele resolve isso da sessão a
    # cada reprice. Sem isto o cupom é aceito e desconta zero.
    payload = None
    if customer is not None:
        payload = {
            "ref": getattr(customer, "ref", "") or "",
            "price_tier": (
                customer.price_tier.ref if getattr(customer, "price_tier_id", None) else ""
            ),
        }

    session = apply_coupon_code(
        session_key=session_key, channel_ref=channel_ref, code=code, customer=payload
    )
    if session is None:
        raise CouponRejected("no_cart")
    return session, promotion.name


def apply_coupon_code(
    *,
    session_key: str,
    channel_ref: str,
    code: str,
    customer: dict | None = None,
) -> Session | None:
    """Attach a validated coupon code and re-run session modifiers.

    When ``customer`` (``{"ref", "price_tier"}``) is given, its identity is merged into
    ``session.data["customer"]`` so a coupon gated by customer tier/segment
    computes its discount — the discount modifier resolves the customer's tier
    and RFM segment from the session, and does so on every later reprice too.
    Open (non-segmented) coupons pass ``None``.
    """
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None

    data = session.data or {}
    data["coupon_code"] = code
    if customer:
        merged = dict(data.get("customer") or {})
        if customer.get("ref"):
            merged["ref"] = customer["ref"]
        if customer.get("price_tier"):
            merged["price_tier"] = customer["price_tier"]
        if merged:
            data["customer"] = merged
    session.data = data
    session.save(update_fields=["data"])

    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )


def remove_coupon_code(*, session_key: str, channel_ref: str) -> Session | None:
    """Remove coupon code and re-run session modifiers."""
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None

    data = session.data or {}
    data.pop("coupon_code", None)
    session.data = data
    session.save(update_fields=["data"])

    session = session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )
    if session.pricing and "coupon" in session.pricing:
        pricing = session.pricing
        pricing.pop("coupon", None)
        session.pricing = pricing
        session.save(update_fields=["pricing"])
    return session


def set_delivery_draft(
    *,
    session_key: str,
    channel_ref: str,
    fulfillment_type: str,
    delivery_address_structured: dict | None = None,
) -> Session | None:
    """Persist the chosen fulfillment + delivery address to the session and
    re-run modifiers so the cart reflects the delivery fee (and zone coverage)
    *before* the final commit.

    Read-side preview only — no order is created. The ``DeliveryZoneRule``
    remains the authoritative gate at commit. Clearing ``delivery_fee_q`` and
    ``delivery_zone_error`` forces ``DeliveryFeeModifier`` to recompute against
    the (possibly new) address; on pickup the delivery keys are dropped so the
    fee disappears from the total.
    """
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None

    data = dict(session.data or {})
    data["fulfillment_type"] = fulfillment_type
    data.pop("delivery_fee_q", None)
    data.pop("delivery_zone_error", None)
    if fulfillment_type == "delivery":
        if delivery_address_structured:
            data["delivery_address_structured"] = delivery_address_structured
    else:
        data.pop("delivery_address_structured", None)
        data.pop("delivery_address", None)
    session.data = data
    session.save(update_fields=["data"])

    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )


def set_loyalty_redeem(
    *,
    session_key: str,
    channel_ref: str,
    redeem_q: int,
) -> Session | None:
    """Apply (``redeem_q > 0``) or clear loyalty redemption on the session and
    re-run modifiers.

    The session is the single source of truth for loyalty redemption: both the
    cart and the checkout read ``session.data["loyalty"]`` (via the
    ``loyalty_redeem`` pricing key). Toggling here keeps them in sync instead of
    a UI-only flag that diverges from the discount actually applied.
    """
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None

    data = dict(session.data or {})
    if redeem_q > 0:
        data["loyalty"] = {"redeem_points_q": int(redeem_q)}
    else:
        data.pop("loyalty", None)
    session.data = data
    session.save(update_fields=["data"])

    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )


def clear_session(*, session_key: str, channel_ref: str) -> None:
    """Abandon the cart session."""
    session_service.abandon_session(session_key=session_key, channel_ref=channel_ref)


def _reserve_or_raise(*, sku: str, qty: int, session_key: str, channel_ref: str):
    """Reserva e devolve o ``hold_id`` — o elo até o LOTE (ADR-017/D1-RETIREMENT).

    O hold ancora em um Quant, e o Quant carrega a ``Batch.ref``; é por aqui que
    a linha descobre de qual lote saiu, e portanto qual desconto de lote vale.
    """
    result = availability.reserve(
        sku,
        Decimal(str(qty)),
        session_key=session_key,
        channel_ref=channel_ref,
    )
    if result["ok"]:
        return result.get("hold_id")
    raise CartUnavailableError(
        sku=sku,
        requested_qty=qty,
        available_qty=int(result["available_qty"]),
        is_paused=result["is_paused"],
        substitutes=result["substitutes"],
        error_code=result["error_code"],
        is_planned=result.get("is_planned", False),
    )
