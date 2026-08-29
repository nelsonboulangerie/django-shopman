from __future__ import annotations

import logging
from decimal import Decimal

from django.http import HttpRequest
from shopman.orderman.models import Session
from shopman.utils.monetary import format_money

from shopman.shop.services import cart as cart_mutations
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF as CHANNEL_REF

logger = logging.getLogger(__name__)


class CartService:
    """Adapter between the Django visitor session and the Orderman cart session.

    Holds the session-key↔Orderman wiring (create, add, update, remove, coupon,
    clear) plus cheap summaries. Cart *data resolution* — availability,
    planned holds, discount transparency, totals — lives in the orchestrator
    read-side ``shop.projections.cart``; ``get_cart`` is the legacy-dict view
    over that projection, kept for the REST serializer / checkout / catalog
    until they consume the projection directly (WP6/D).
    """

    @staticmethod
    def _empty_cart(*, include_items: bool = True) -> dict:
        return {
            "items": [] if include_items else [],
            "subtotal_q": 0,
            "subtotal_display": "R$ 0,00",
            "count": 0,
            "discount_lines": [],
        }

    @staticmethod
    def summary_from_session(session: Session, *, include_items: bool = False) -> dict:
        """Return the lightweight cart summary from an already-loaded session."""
        items = [dict(item) for item in (session.items or [])]
        subtotal_q = sum(item.get("line_total_q", 0) for item in items)
        count = sum(int(Decimal(str(item.get("qty", 0)))) for item in items)
        return {
            "items": items if include_items else [],
            "subtotal_q": subtotal_q,
            "subtotal_display": f"R$ {format_money(subtotal_q)}",
            "count": count,
            "discount_lines": [],
        }

    @staticmethod
    def _get_session_key(request: HttpRequest) -> str | None:
        return request.session.get("cart_session_key")

    @staticmethod
    def _customer_link(request: HttpRequest) -> dict | None:
        """Return ``{"ref", "price_tier"}`` for the authenticated viewer, or ``None``.

        Used to persist the customer's identity onto the cart session so a
        promotion/coupon gated by customer tier/segment discounts on every
        reprice — the discount modifier resolves the tier/segment from the
        session, not from the request.
        """
        from shopman.storefront.identity import get_authenticated_customer

        try:
            customer = get_authenticated_customer(request)
        except Exception:
            # Best-effort pricing context — a resolution failure must never break
            # the cart mutation itself. Degrade to "not linked".
            logger.debug("cart customer link resolution failed", exc_info=True)
            return None
        if customer is None:
            return None
        return {
            "ref": getattr(customer, "ref", "") or "",
            "price_tier": (
                customer.price_tier.ref if getattr(customer, "price_tier_id", None) else ""
            ),
        }

    @staticmethod
    def _link_customer(request: HttpRequest, session_key: str) -> bool:
        """Idempotently persist the authenticated customer (ref + group) onto the
        cart session. Returns ``True`` when the session was actually updated.

        No-op for an anonymous viewer or when the session already carries the same
        identity, so it's cheap to call on every cart write.
        """
        payload = CartService._customer_link(request)
        if not payload:
            return False
        session = cart_mutations.get_open_session(
            session_key=session_key, channel_ref=CHANNEL_REF
        )
        if session is None:
            return False
        existing = (session.data or {}).get("customer") or {}
        merged = dict(existing)
        if payload["ref"]:
            merged["ref"] = payload["ref"]
        if payload["price_tier"]:
            merged["price_tier"] = payload["price_tier"]
        if merged == existing:
            return False
        data = dict(session.data or {})
        data["customer"] = merged
        session.data = data
        session.save(update_fields=["data"])
        return True

    @staticmethod
    def _get_or_create_session(request: HttpRequest) -> tuple[Session, str]:
        """Return (cart_session, session_key). Creates if needed."""
        cart_session, session_key = cart_mutations.get_or_create_session(
            session_key=request.session.get("cart_session_key"),
            channel_ref=CHANNEL_REF,
            origin_channel=request.session.get("origin_channel", "web"),
        )
        request.session["cart_session_key"] = session_key
        return cart_session, session_key

    @staticmethod
    def add_item(
        request: HttpRequest,
        sku: str,
        qty: int,
        unit_price_q: int,
        *,
        name: str = "",
    ) -> Session:
        """Add item to cart. Merges with existing line if same SKU.

        Delegates reservation and session mutation to the shop cart mutation
        facade. On shortage, raises CartUnavailableError with substitutes
        populated so the caller can render a "no stock" UI.

        For merges (existing line), checks availability for the *additional* qty only
        and adopts an additional hold tagged with the same session_key.
        """
        # Link the customer to an EXISTING cart before the add reprices, so a
        # segment/tier-gated promo already discounts this line. For a brand-new
        # cart (no key yet) the session doesn't exist to write to; we link right
        # after and reprice once below.
        existing_key = CartService._get_session_key(request)
        if existing_key:
            CartService._link_customer(request, existing_key)

        session, session_key = cart_mutations.add_item(
            session_key=existing_key,
            channel_ref=CHANNEL_REF,
            origin_channel=request.session.get("origin_channel", "web"),
            sku=sku,
            qty=qty,
            unit_price_q=unit_price_q,
            name=name,
        )
        request.session["cart_session_key"] = session_key
        if not existing_key and CartService._link_customer(request, session_key):
            session = (
                cart_mutations.reprice(session_key=session_key, channel_ref=CHANNEL_REF)
                or session
            )
        return session

    @staticmethod
    def update_qty(
        request: HttpRequest,
        line_id: str,
        qty: int,
        *,
        sku: str | None = None,
    ) -> Session:
        """Update quantity of a cart item.

        Reconciles holds to the new absolute quantity through the shop cart
        mutation facade. On shortage, raises `CartUnavailableError` and does
        not mutate the cart.
        """
        session_key = CartService._get_session_key(request)
        if not session_key:
            raise ValueError("No active cart")

        CartService._link_customer(request, session_key)
        return cart_mutations.update_qty(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            line_id=line_id,
            qty=qty,
            sku=sku,
        )

    @staticmethod
    def remove_item(
        request: HttpRequest,
        line_id: str,
        *,
        sku: str | None = None,
    ) -> Session:
        """Remove item from cart.

        Reconciles holds to qty=0 through the shop cart mutation facade, so the
        removed line doesn't bleed reservations until the next commit.
        """
        session_key = CartService._get_session_key(request)
        if not session_key:
            raise ValueError("No active cart")

        CartService._link_customer(request, session_key)
        return cart_mutations.remove_item(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            line_id=line_id,
            sku=sku,
        )

    @staticmethod
    def _get_line(session_key: str, line_id: str) -> dict | None:
        """Return the session line dict matching `line_id`, or None."""
        session = cart_mutations.get_open_session(session_key=session_key, channel_ref=CHANNEL_REF)
        if session is None:
            return None
        for item in session.items:
            if item.get("line_id") == line_id:
                return item
        return None

    @staticmethod
    def has_items(request: HttpRequest) -> bool:
        """Return whether the visitor has an open cart with positive-qty lines."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            return False

        if not CartService.session_has_items(session_key):
            if cart_mutations.get_open_session(
                session_key=session_key, channel_ref=CHANNEL_REF
            ) is None:
                request.session.pop("cart_session_key", None)
            return False
        return True

    @staticmethod
    def session_has_items(session_key: str) -> bool:
        """Uma REF de sacola tem linhas com quantidade? Sem tocar na sessão HTTP.

        Existe para quem só tem a ref na mão e nenhuma sessão do dono: a adoção da
        sacola que viaja no access link precisa saber se vale a troca, e a ref que
        ela avalia não é a da sessão que está pedindo.
        """
        if not session_key:
            return False
        session = cart_mutations.get_open_session(session_key=session_key, channel_ref=CHANNEL_REF)
        if session is None:
            return False
        for item in session.items:
            try:
                if Decimal(str(item.get("qty", 0))) > 0:
                    return True
            except Exception:
                logger.debug("cart.session_has_items degraded; using fallback", exc_info=True)
                continue
        return False

    @staticmethod
    def get_cart_summary(request: HttpRequest, *, include_items: bool = False) -> dict:
        """Return a cheap cart summary without stock/catalog enrichment.

        Used by global context and badge endpoints. Availability, planned holds,
        images, discounts transparency and upsells belong to the cart projection
        and should not be paid by every page render.
        """
        session_key = CartService._get_session_key(request)
        if not session_key:
            return CartService._empty_cart(include_items=include_items)

        session = cart_mutations.get_open_session(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
        )
        if session is None:
            request.session.pop("cart_session_key", None)
            return CartService._empty_cart(include_items=include_items)

        return CartService.summary_from_session(session, include_items=include_items)

    @staticmethod
    def apply_coupon(request: HttpRequest, code: str) -> dict:
        """Aplicar cupom: resolver quem está pedindo e traduzir a recusa.

        As cinco portas moram em ``shop.services.cart.validate_and_apply_coupon``
        (ADR-019) — aqui fica só o que é da superfície: achar a sessão, resolver o
        cliente autenticado do request, e devolver o código de erro que a view
        transforma em mensagem.
        """
        from shopman.shop.services import cart as cart_service
        from shopman.storefront.identity import get_authenticated_customer

        session_key = CartService._get_session_key(request)
        if not session_key:
            return {"ok": False, "error": "no_cart"}

        try:
            _session, promotion_name = cart_service.validate_and_apply_coupon(
                session_key=session_key,
                channel_ref=CHANNEL_REF,
                code=code,
                customer=get_authenticated_customer(request),
            )
        except cart_service.CouponRejected as exc:
            return {"ok": False, "error": exc.code}

        return {"ok": True, "code": (code or "").strip().upper(), "promotion": promotion_name}

    @staticmethod
    def remove_coupon(request: HttpRequest) -> dict:
        """Remove coupon from cart session."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            return {"ok": False, "error": "no_cart"}

        session = cart_mutations.remove_coupon_code(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
        )
        if session is None:
            return {"ok": False, "error": "no_cart"}

        return {"ok": True}

    @staticmethod
    def clear(request: HttpRequest) -> None:
        """Abandon the current session."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            return

        cart_mutations.clear_session(session_key=session_key, channel_ref=CHANNEL_REF)
        request.session.pop("cart_session_key", None)

