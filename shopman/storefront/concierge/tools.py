"""As ferramentas do concierge: onde o dinheiro é decidido.

Cada função aqui é determinística e só chama services que já existem: o
catálogo da loja, a disponibilidade do Stockman, a sacola do Orderman, os
slots de retirada, o checkout, o pagamento, o acompanhamento e o access link.
O modelo escolhe QUAL ferramenta chamar e conversa sobre o resultado; nenhum
preço, saldo, prazo ou código Pix nasce no texto dele.

Três portões que não são do modelo:

- ``review_order`` fecha um ORÇAMENTO e devolve um ``quote_token`` que resume
  sacola + fulfillment + total. ``place_order`` só aceita esse token, e só se
  ele ainda bate com a sacola de agora. Mudou a sacola, mudou o token, e o
  pedido volta para a revisão. É a confirmação explícita, em código.
- ``place_order`` é idempotente pela chave ``concierge:<conversa>:<token>``:
  o modelo repetir a chamada não repete o pedido.
- O código Pix vai numa mensagem SEPARADA, montada pela casa (``extra_replies``),
  para o cliente copiar sem ruído. O modelo só avisa que ele chega em seguida.

Todo resultado é um ``dict`` serializável; erro de negócio vira ``{"ok": False,
"error": código, "message": frase}`` e nunca exceção, para o modelo poder
explicar ao cliente o que faltou.
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import date as date_type
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.models import Conversation

logger = logging.getLogger(__name__)

MAX_LINE_QTY = 99
MAX_MENU_ITEMS = 12
FULFILLMENT_TYPES = ("pickup", "delivery")
WEB_DESTINATIONS = {
    "menu": "/menu",
    "checkout": "/finalizar",
    "account": "/conta",
}
PAYMENT_LABELS = {
    "pix": "Pix",
    "card": "Cartão (link seguro)",
    "cash": "Dinheiro",
}


@dataclass
class ToolContext:
    """O que as ferramentas sabem sobre a conversa, e o que devolvem à casa."""

    conversation: Conversation
    channel_ref: str
    extra_replies: list[str] = field(default_factory=list)
    handoff: bool = False
    handoff_reason: str = ""
    order_ref: str = ""


# ── Helpers ───────────────────────────────────────────────────────────


def _money(value_q) -> str:
    return f"R$ {format_money(int(value_q or 0))}"


def _fold(text: str) -> str:
    """Minúsculas sem acento: "Pão" e "pao" são a mesma busca."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower().strip()


def _storefront_ref() -> str:
    return getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web") or "web"


def _storefront_base_url() -> str:
    return (getattr(settings, "SHOPMAN_STOREFRONT_BASE_URL", "") or "").rstrip("/")


def _catalog_channel_ref(channel_ref: str) -> str:
    """O canal cujo LISTING o concierge lê.

    O canal do concierge tem listing próprio (o seed e o ``bootstrap_whatsapp_channel``
    o criam espelhando a loja). Se ele ainda não existe neste banco, lê-se a loja
    online: o cliente do WhatsApp vê o que o site vende, nunca um cardápio vazio.
    """
    try:
        from shopman.offerman.models import Listing

        if Listing.objects.filter(ref=channel_ref, is_active=True).exists():
            return channel_ref
    except Exception:
        logger.debug("concierge.catalog_channel_ref degraded", exc_info=True)
    return _storefront_ref()


def _open_session(ctx: ToolContext):
    from shopman.shop.services import cart as cart_service

    key = ctx.conversation.session_key
    if not key:
        return None
    session = cart_service.get_open_session(session_key=key, channel_ref=ctx.channel_ref)
    if session is None:
        # Sacola fechada ou abandonada por fora (limpeza, commit): esquecer a chave.
        ctx.conversation.session_key = ""
        ctx.conversation.save(update_fields=["session_key", "updated_at"])
    return session


def _ensure_session(ctx: ToolContext):
    """A sacola aberta desta conversa, criando se preciso.

    A sessão nasce no canal do concierge, carimbada com a conversa e com o
    cliente (nome, telefone, ref), e presa ao telefone: uma sacola aberta por
    telefone no canal, como no site.
    """
    session = _open_session(ctx)
    if session is not None:
        return session

    from shopman.shop.services import cart as cart_service
    from shopman.shop.services import sessions

    conversation = ctx.conversation
    session, key = cart_service.get_or_create_session(
        session_key=None,
        channel_ref=ctx.channel_ref,
        origin_channel="whatsapp",
    )
    ops = [{"op": "set_data", "path": "concierge", "value": {"conversation_id": conversation.pk}}]
    customer = {
        k: v
        for k, v in {
            "name": conversation.customer_name,
            "phone": conversation.phone,
            "ref": conversation.customer_ref,
        }.items()
        if v
    }
    if customer:
        ops.append({"op": "set_data", "path": "customer", "value": customer})
    session = sessions.modify_session(session_key=key, channel_ref=ctx.channel_ref, ops=ops)
    if conversation.phone:
        sessions.assign_phone_handle(session_key=key, channel_ref=ctx.channel_ref, phone=conversation.phone)
    conversation.session_key = key
    conversation.save(update_fields=["session_key", "updated_at"])
    return session


def _set_session_data(ctx: ToolContext, session_key: str, values: dict):
    from shopman.shop.services import sessions

    ops = [{"op": "set_data", "path": path, "value": value} for path, value in values.items()]
    return sessions.modify_session(session_key=session_key, channel_ref=ctx.channel_ref, ops=ops)


def _line_for_sku(session, sku: str) -> dict | None:
    wanted = _fold(sku)
    for item in session.items or []:
        if _fold(item.get("sku", "")) == wanted:
            return item
    return None


def _item_payload(item) -> dict:
    return {
        "sku": item.sku,
        "name": item.name,
        "price": item.price_display,
        "price_q": int(item.base_price_q),
        "availability": str(item.availability),
        "availability_label": item.availability_label,
        "available_qty": item.available_qty,
        "can_order": bool(item.can_add_to_cart),
        "description": item.short_description or "",
        "promotion": item.promotion_label or "",
        "unit": item.unit_weight_label or "",
        "collection": item.category or "",
    }


def _catalog_item(ctx: ToolContext, sku: str):
    from shopman.storefront.presentation.catalog import build_catalog_items_for_skus

    ref = _catalog_channel_ref(ctx.channel_ref)
    items = build_catalog_items_for_skus([sku], channel_ref=ref)
    if items:
        return items[0]
    # Tolerância a caixa: o cliente digita "cr", o SKU é "CR".
    try:
        from shopman.offerman.models import Product

        product = Product.objects.filter(sku__iexact=sku).first()
    except Exception:
        logger.debug("concierge.catalog_item: busca por sku degradada", exc_info=True)
        product = None
    if product is None:
        return None
    items = build_catalog_items_for_skus([product.sku], channel_ref=ref)
    return items[0] if items else None


def _cart_payload(ctx: ToolContext, session) -> dict:
    from shopman.shop.projections.cart import build_cart

    cart = build_cart(session.session_key, ctx.channel_ref)
    data = session.data or {}
    fulfillment = _fulfillment_payload(data)
    payload = {
        "empty": cart.is_empty,
        "count": cart.count,
        "lines": [
            {
                "sku": line.sku,
                "name": line.name,
                "qty": line.qty,
                "unit_price": _money(line.unit_price_q),
                "line_total": _money(line.line_total_q),
                "is_available": line.is_available,
                "available_qty": line.available_qty,
                "planned_for_date": line.planned_for_date,
                "discount": line.discount_name or "",
            }
            for line in cart.lines
        ],
        "subtotal": _money(cart.subtotal_q),
        "discount_total": _money(cart.discount_total_q) if cart.discount_total_q else "",
        "delivery_fee": (
            ("grátis" if cart.delivery_is_free else _money(cart.delivery_fee_q))
            if cart.delivery_fee_q is not None
            else ""
        ),
        "delivery_out_of_zone": bool(cart.delivery_zone_error),
        "total": _money(cart.grand_total_q),
        "total_q": int(cart.grand_total_q),
        "fulfillment": fulfillment,
        "can_checkout": bool(cart.can_checkout),
        "checkout_block_reason": cart.checkout_block_reason or "",
    }
    if cart.minimum_order is not None:
        payload["minimum_order"] = _progress_payload(cart.minimum_order)
    if cart.upsell is not None:
        payload["suggestion"] = _upsell_payload(cart.upsell)
    return payload


def _progress_payload(progress) -> dict:
    out = {}
    for name in ("threshold_q", "remaining_q", "reached", "label", "message"):
        value = getattr(progress, name, None)
        if value is None:
            continue
        out[name.replace("_q", "")] = _money(value) if name.endswith("_q") else value
    return out


def _upsell_payload(upsell) -> dict:
    out = {}
    for name in ("sku", "name", "price_display", "message", "label"):
        value = getattr(upsell, name, None)
        if value:
            out["price" if name == "price_display" else name] = value
    return out


def _fulfillment_payload(data: dict) -> dict:
    fulfillment_type = str(data.get("fulfillment_type") or "")
    slot_ref = str(data.get("delivery_time_slot") or "")
    return {
        "type": fulfillment_type,
        "date": str(data.get("delivery_date") or ""),
        "slot_ref": slot_ref,
        "slot_label": _slot_label(fulfillment_type, slot_ref),
        "address": str(data.get("delivery_address") or ""),
    }


def _slot_label(fulfillment_type: str, slot_ref: str) -> str:
    if not slot_ref:
        return ""
    if fulfillment_type == "delivery" and "-" in slot_ref:
        start, _, end = slot_ref.partition("-")
        return f"{start} às {end}"
    from shopman.storefront.services.pickup_slots import slot_label

    try:
        return slot_label(slot_ref) or slot_ref
    except Exception:
        logger.debug("concierge.slot_label degraded slot=%s", slot_ref, exc_info=True)
        return slot_ref


def _quote_token(session) -> str:
    """Resumo estável de sacola + fulfillment + total. Mudou algo, muda o token."""
    data = session.data or {}
    lines = sorted(
        (
            str(item.get("sku") or ""),
            str(item.get("qty") or ""),
            int(item.get("line_total_q") or 0),
        )
        for item in (session.items or [])
    )
    seed = {
        "lines": lines,
        "lines_total_q": _lines_total_q(session),
        "delivery_fee_q": data.get("delivery_fee_q"),
        "fulfillment_type": data.get("fulfillment_type"),
        "delivery_date": data.get("delivery_date"),
        "delivery_time_slot": data.get("delivery_time_slot"),
        "delivery_address": data.get("delivery_address"),
    }
    digest = hashlib.sha1(json.dumps(seed, sort_keys=True, default=str).encode()).hexdigest()
    return digest[:12]


def _lines_total_q(session) -> int:
    return sum(int(item.get("line_total_q") or 0) for item in (session.items or []))


def _today_iso() -> str:
    return timezone.localdate().isoformat()


def _parse_date(value: str) -> date_type | None:
    try:
        return date_type.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def _error(code: str, message: str, **extra) -> dict:
    return {"ok": False, "error": code, "message": message, **extra}


# ── Ferramentas ───────────────────────────────────────────────────────


def browse_menu(ctx: ToolContext, query: str = "", collection: str = "") -> dict:
    """O cardápio de agora: nome, preço e disponibilidade viva, do listing do canal.

    ``collection`` aceita a ref ("paes") ou o rótulo ("Pães", "folhados"); o que não
    casa com nada é ignorado, com aviso no resultado. Melhor o cardápio inteiro
    filtrado pela busca do que uma lista vazia por causa de um nome chutado.
    """
    from shopman.storefront.presentation.catalog import build_catalog

    ref = _catalog_channel_ref(ctx.channel_ref)
    try:
        catalog = build_catalog(channel_ref=ref)
    except Exception:
        logger.exception("concierge.browse_menu failed")
        return _error("catalog_unavailable", "Não consegui ler o cardápio agora.")

    items = list(catalog.items)
    collection_note = ""
    wanted = _fold(collection)
    if wanted:
        match = next(
            (
                cat
                for cat in catalog.categories
                if _fold(getattr(cat, "ref", "")) == wanted or _fold(getattr(cat, "label", "") or getattr(cat, "name", "")) == wanted
            ),
            None,
        )
        if match is not None:
            match_ref = getattr(match, "ref", "")
            items = [item for item in items if _fold(item.category or "") in (wanted, _fold(match_ref), _fold(getattr(match, "label", "") or ""))]
        else:
            collection_note = f"Coleção '{collection}' não existe; mostrando sem esse filtro."
    needle = _fold(query)
    if needle:
        terms = [t for t in needle.split() if t]

        def matches(item) -> bool:
            haystack = _fold(
                " ".join(
                    [item.name, item.short_description or "", item.category or "", " ".join(item.search_terms or ())]
                )
            )
            return all(term in haystack for term in terms)

        items = [item for item in items if matches(item)]

    payload = {
        "ok": True,
        "count": len(items),
        "items": [_item_payload(item) for item in items[:MAX_MENU_ITEMS]],
        "truncated": len(items) > MAX_MENU_ITEMS,
    }
    if collection_note:
        payload["note"] = collection_note
    if not needle:
        payload["collections"] = [
            {
                "ref": getattr(cat, "ref", "") or "",
                "label": getattr(cat, "label", "") or getattr(cat, "name", "") or "",
            }
            for cat in catalog.categories
        ]
    if catalog.happy_hour is not None:
        label = getattr(catalog.happy_hour, "label", "") or getattr(catalog.happy_hour, "message", "")
        if label:
            payload["happy_hour"] = str(label)
    return payload


def view_cart(ctx: ToolContext) -> dict:
    """A sacola desta conversa, com totais e o que falta para fechar."""
    session = _open_session(ctx)
    if session is None:
        return {"ok": True, "empty": True, "count": 0, "lines": [], "total": _money(0), "fulfillment": _fulfillment_payload({})}
    return {"ok": True, **_cart_payload(ctx, session)}


def set_item(ctx: ToolContext, sku: str, qty: int) -> dict:
    """Define a quantidade ABSOLUTA de um produto na sacola (0 remove).

    Reserva estoque pelo caminho da loja; quando não há, devolve o saldo real e
    os substitutos que o Stockman sugere. Preço vem do listing, nunca do texto.
    """
    from shopman.shop.services import cart as cart_service
    from shopman.shop.services.cart import CartUnavailableError

    sku = str(sku or "").strip()
    if not sku:
        return _error("missing_sku", "Diga qual produto.")
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        return _error("invalid_qty", "Quantidade inválida.")
    qty = max(0, min(qty, MAX_LINE_QTY))

    item = _catalog_item(ctx, sku)
    if item is None:
        return _error("unknown_sku", f"Não encontrei o produto {sku} no cardápio. Use browse_menu para achar o SKU certo.")
    sku = item.sku

    session = _ensure_session(ctx)
    existing = _line_for_sku(session, sku)

    if qty == 0:
        if existing is not None:
            cart_service.remove_item(
                session_key=session.session_key, channel_ref=ctx.channel_ref, line_id=existing["line_id"], sku=sku
            )
        session = _open_session(ctx)
        return {"ok": True, "removed": sku, **(_cart_payload(ctx, session) if session else {"empty": True})}

    if not item.can_add_to_cart:
        return _error(
            "unavailable",
            f"{item.name}: {item.availability_label}.",
            sku=sku,
            availability=str(item.availability),
            available_qty=item.available_qty,
            is_paused=bool(item.is_paused),
        )

    try:
        if existing is not None:
            cart_service.update_qty(
                session_key=session.session_key,
                channel_ref=ctx.channel_ref,
                line_id=existing["line_id"],
                qty=qty,
                sku=sku,
            )
        else:
            cart_service.add_item(
                session_key=session.session_key,
                channel_ref=ctx.channel_ref,
                origin_channel="whatsapp",
                sku=sku,
                qty=qty,
                unit_price_q=int(item.base_price_q),
                name=item.name,
            )
    except CartUnavailableError as exc:
        # Ao AJUSTAR uma linha, a reserva confere só o acréscimo: o saldo que volta
        # exclui o que esta sacola já segura. Para o cliente, o que existe é a soma.
        held_qty = int(Decimal(str(existing.get("qty") or 0))) if existing is not None else 0
        available_total = int(exc.available_qty) + held_qty
        substitutes = []
        for sub in exc.substitutes or []:
            if isinstance(sub, dict):
                substitutes.append({"sku": sub.get("sku", ""), "name": sub.get("name", sub.get("sku", ""))})
        return _error(
            "insufficient_stock" if not exc.is_paused else "paused",
            (
                f"{item.name}: só há {available_total} agora."
                if available_total
                else f"{item.name}: indisponível no momento."
            ),
            sku=sku,
            requested_qty=qty,
            available_qty=available_total,
            is_paused=bool(exc.is_paused),
            planned_for_date=str(getattr(exc, "planned_target_date", "") or ""),
            substitutes=substitutes,
        )
    except Exception as exc:
        logger.exception("concierge.set_item failed sku=%s", sku)
        return _error("cart_error", f"Não consegui atualizar a sacola: {getattr(exc, 'message', exc)}")

    session = _open_session(ctx)
    return {"ok": True, **_cart_payload(ctx, session)}


def list_pickup_slots(ctx: ToolContext, delivery_date: str = "", fulfillment_type: str = "pickup") -> dict:
    """Dias e horários em que a casa consegue entregar/servir esta sacola."""
    from shopman.shop.services.business_calendar import available_dates, delivery_slots_for
    from shopman.storefront.services.pickup_slots import annotate_slots_for_checkout

    session = _open_session(ctx)
    skus = [str(item.get("sku")) for item in (session.items or [])] if session else []
    when = delivery_date or _today_iso()
    day = _parse_date(when)
    if day is None:
        return _error("invalid_date", "Data inválida. Use AAAA-MM-DD.")

    try:
        dates = [d.isoformat() for d in available_dates(max_count=5)]
    except Exception:
        logger.debug("concierge.available_dates degraded", exc_info=True)
        dates = []

    payload: dict = {"ok": True, "date": when, "available_dates": dates}
    if fulfillment_type == "delivery":
        try:
            slots = delivery_slots_for(day)
        except Exception:
            logger.debug("concierge.delivery_slots degraded", exc_info=True)
            slots = []
        payload["delivery_slots"] = [{"ref": s.get("ref"), "label": s.get("label")} for s in slots]
        return payload

    annotated = annotate_slots_for_checkout(skus, delivery_date=when)
    payload["pickup_slots"] = [
        {
            "ref": slot.get("ref"),
            "label": slot.get("label"),
            "available": bool(slot.get("enabled")),
            "reason": slot.get("reason") or "",
            "is_earliest": bool(slot.get("is_earliest")),
        }
        for slot in annotated.get("pickup_slots", [])
    ]
    payload["earliest_slot_ref"] = annotated.get("earliest_slot_ref") or ""
    return payload


def set_fulfillment(
    ctx: ToolContext,
    fulfillment_type: str,
    delivery_date: str = "",
    slot_ref: str = "",
    address: str = "",
) -> dict:
    """Retirada ou entrega, quando, e (na entrega) onde. Valida como o checkout do site."""
    from shopman.shop.services import cart as cart_service
    from shopman.storefront.intents.checkout import _validate_preorder
    from shopman.storefront.services.pickup_slots import validate_pickup_slot_selection

    fulfillment_type = str(fulfillment_type or "").strip().lower()
    if fulfillment_type not in FULFILLMENT_TYPES:
        return _error("invalid_fulfillment", "Escolha retirada (pickup) ou entrega (delivery).")

    session = _ensure_session(ctx)
    when = str(delivery_date or "").strip() or _today_iso()
    day = _parse_date(when)
    if day is None:
        return _error("invalid_date", "Data inválida. Use AAAA-MM-DD.")

    errors: dict[str, str] = {}
    errors.update(
        _validate_preorder(
            when,
            cart_lines=list(session.items or []),
            channel_ref=ctx.channel_ref,
            session_key=session.session_key,
        )
    )

    values: dict = {"fulfillment_type": fulfillment_type, "delivery_date": when}
    slot_ref = str(slot_ref or "").strip()

    if fulfillment_type == "pickup":
        if slot_ref:
            skus = [str(item.get("sku")) for item in (session.items or [])]
            now_time = timezone.localtime().time().replace(second=0, microsecond=0)
            error = validate_pickup_slot_selection(slot_ref, delivery_date=when, cart_skus=skus, now=now_time)
            if error:
                errors["delivery_time_slot"] = error
            else:
                values["delivery_time_slot"] = slot_ref
        cart_service.set_delivery_draft(
            session_key=session.session_key, channel_ref=ctx.channel_ref, fulfillment_type="pickup"
        )
        values["delivery_address"] = ""
    else:
        address = " ".join(str(address or "").split()).strip()
        if not address:
            errors["delivery_address"] = "Preciso do endereço completo, com número."
        else:
            structured = _structured_address(address)
            if "latitude" not in structured:
                # Sem coordenada não há taxa honesta: o motor de faixas precisa da
                # distância, e cobrar "taxa padrão" por um endereço que não se sabe
                # onde fica é chute com dinheiro. Falha fechado e aponta o site,
                # onde o endereço é escolhido no mapa.
                return _error(
                    "address_not_located",
                    "Não consegui localizar esse endereço para calcular a entrega. Peça para conferir o "
                    "endereço com número e bairro, ou ofereça o site (send_web_link) ou a retirada.",
                    address=address,
                )
            cart_service.set_delivery_draft(
                session_key=session.session_key,
                channel_ref=ctx.channel_ref,
                fulfillment_type="delivery",
                delivery_address_structured=structured,
            )
            values["delivery_address"] = address
        if slot_ref:
            from shopman.shop.services.business_calendar import delivery_slots_for

            refs = {s.get("ref") for s in delivery_slots_for(day)}
            if slot_ref not in refs:
                errors["delivery_time_slot"] = "Esse horário não está disponível para entrega nesse dia."
            else:
                values["delivery_time_slot"] = slot_ref

    if errors:
        return {"ok": False, "error": "validation", "errors": errors, "message": " ".join(errors.values())}

    session = _set_session_data(ctx, session.session_key, values)
    payload = _cart_payload(ctx, session)
    result = {"ok": True, **payload}
    if fulfillment_type == "pickup" and not values.get("delivery_time_slot"):
        result["pickup_slots"] = list_pickup_slots(ctx, when).get("pickup_slots", [])
    if fulfillment_type == "delivery" and payload.get("delivery_out_of_zone"):
        result["message"] = "Esse endereço está fora da nossa área de entrega."
    return result


def _structured_address(address: str) -> dict:
    from shopman.shop.services.geocoding import forward_geocode

    structured = {"formatted_address": address, "is_verified": False}
    try:
        coords = forward_geocode(address)
    except Exception:
        logger.debug("concierge.forward_geocode degraded", exc_info=True)
        coords = None
    if coords:
        structured["latitude"], structured["longitude"] = coords
    return structured


def review_order(ctx: ToolContext) -> dict:
    """O orçamento: recap completo, o que falta e o token que autoriza o pedido."""
    from shopman.shop.config import ChannelConfig
    from shopman.storefront.intents.checkout import _validate_preorder

    session = _open_session(ctx)
    if session is None or not (session.items or []):
        return {"ok": True, "ready": False, "missing": ["items"], "message": "A sacola está vazia."}

    payload = _cart_payload(ctx, session)
    data = session.data or {}
    missing: list[str] = []
    if not payload["can_checkout"]:
        missing.append(payload["checkout_block_reason"] or "cart")
    fulfillment_type = str(data.get("fulfillment_type") or "")
    if fulfillment_type not in FULFILLMENT_TYPES:
        missing.append("fulfillment_type")
    elif fulfillment_type == "pickup" and not data.get("delivery_time_slot"):
        missing.append("delivery_time_slot")
    elif fulfillment_type == "delivery":
        if not data.get("delivery_address"):
            missing.append("delivery_address")
        if data.get("delivery_zone_error"):
            missing.append("delivery_out_of_zone")
    if not ctx.conversation.phone:
        missing.append("customer_phone")
    if data.get("delivery_date"):
        date_errors = _validate_preorder(
            str(data["delivery_date"]),
            cart_lines=list(session.items or []),
            channel_ref=ctx.channel_ref,
            session_key=session.session_key,
        )
        if date_errors:
            missing.append("delivery_date")
            payload["date_error"] = " ".join(date_errors.values())

    methods = ChannelConfig.for_channel(ctx.channel_ref).payment.available_methods
    result = {
        "ok": True,
        "ready": not missing,
        "missing": missing,
        **payload,
        "payment_methods": [{"ref": m, "label": PAYMENT_LABELS.get(m, m)} for m in methods],
    }
    if not missing:
        token = _quote_token(session)
        ctx.conversation.quote = {
            "token": token,
            "total_q": int(payload["total_q"]),
            "lines_total_q": _lines_total_q(session),
            "issued_at": timezone.now().isoformat(),
        }
        ctx.conversation.save(update_fields=["quote", "updated_at"])
        result["quote_token"] = token
    return result


def place_order(ctx: ToolContext, quote_token: str, payment_method: str, order_notes: str = "") -> dict:
    """Fecha o pedido do orçamento vigente. Recusa token velho; idempotente por token."""
    from shopman.shop.config import ChannelConfig
    from shopman.shop.services import checkout as checkout_service

    conversation = ctx.conversation
    session = _open_session(ctx)
    if session is None or not (session.items or []):
        return _error("no_cart", "Não há sacola para fechar.")

    quote = conversation.quote or {}
    quote_token = str(quote_token or "").strip()
    if not quote_token or quote_token != str(quote.get("token") or "") or quote_token != _quote_token(session):
        return _error(
            "quote_stale",
            "A sacola mudou desde o último orçamento. Chame review_order de novo e confirme com o cliente.",
        )

    payment_method = str(payment_method or "").strip().lower()
    methods = ChannelConfig.for_channel(ctx.channel_ref).payment.available_methods
    if payment_method not in methods:
        return _error(
            "invalid_payment_method",
            "Forma de pagamento indisponível neste canal.",
            payment_methods=[{"ref": m, "label": PAYMENT_LABELS.get(m, m)} for m in methods],
        )
    if not conversation.phone:
        return _error("no_phone", "Este contato não tem telefone; o pedido precisa ser feito pelo site.")

    customer = {
        k: v
        for k, v in {
            "name": conversation.customer_name,
            "phone": conversation.phone,
            "ref": conversation.customer_ref,
        }.items()
        if v
    }
    data: dict = {"customer": customer, "payment": {"method": payment_method}}
    notes = " ".join(str(order_notes or "").split()).strip()
    if notes:
        data["order_notes"] = notes[:300]

    idempotency_key = f"concierge:{conversation.pk}:{quote_token}"
    try:
        result = checkout_service.process(
            session.session_key,
            ctx.channel_ref,
            data,
            idempotency_key=idempotency_key,
            ctx={"actor": "concierge", "conversation_id": conversation.pk},
            expected_total_q=int(quote.get("lines_total_q") or _lines_total_q(session)),
        )
    except Exception as exc:
        logger.warning("concierge.place_order refused conversation=%s: %s", conversation.pk, exc, exc_info=True)
        code = str(getattr(exc, "code", "") or type(exc).__name__)
        message = str(getattr(exc, "message", "") or exc)
        return _error(code, message)

    from shopman.shop.services.customer_orders import find_order

    order = find_order(result.order_ref)
    payment = ((order.data or {}).get("payment") or {}) if order is not None else {}
    if order is not None and not (payment.get("copy_paste") or payment.get("checkout_url")):
        # O intent nasce no `on_commit` do lifecycle (timing at_commit), que já rodou
        # quando o checkout devolveu. Se por algum motivo não rodou (transação
        # externa, falha adiada), pedimos aqui: `initiate` é idempotente pelo
        # `intent_ref`, e o cliente não pode ficar sem o Pix na mão.
        from shopman.shop.services import payment as payment_service

        try:
            payment_service.initiate(order)
            order.refresh_from_db()
            payment = (order.data or {}).get("payment") or {}
        except Exception:
            logger.exception("concierge.place_order payment.initiate failed order=%s", order.ref)

    pix_code = str(payment.get("copy_paste") or "").strip()
    if pix_code:
        ctx.extra_replies.append(pix_code)
    ctx.order_ref = result.order_ref

    conversation.session_key = ""
    conversation.quote = {}
    conversation.save(update_fields=["session_key", "quote", "updated_at"])

    tracking_url = f"{_storefront_base_url()}/pedido/{result.order_ref}/"
    return {
        "ok": True,
        "order_ref": result.order_ref,
        "status": result.status,
        "total": _money(order.total_q if order is not None else result.total_q),
        "items_count": result.items_count,
        "tracking_url": tracking_url,
        "payment": {
            "method": payment_method,
            "pix_code_sent_separately": bool(pix_code),
            "checkout_url": str(payment.get("checkout_url") or ""),
            "expires_at": str(payment.get("expires_at") or ""),
            "pending_setup": payment_method in {"pix", "card"} and not (pix_code or payment.get("checkout_url")),
        },
    }


def order_status(ctx: ToolContext, order_ref: str = "") -> dict:
    """Onde estão os pedidos deste cliente (o último, ou um ref específico)."""
    from shopman.orderman.models import Order

    from shopman.shop.services.conversation import build_order_conversation
    from shopman.shop.services.customer_orders import customer_identity_filter

    conversation = ctx.conversation
    identity = customer_identity_filter(
        customer_ref=conversation.customer_ref or None, phone=conversation.phone or None
    )
    if identity is None:
        return {"ok": True, "orders": [], "message": "Ainda não sei quem é o cliente."}

    qs = Order.objects.filter(identity).distinct().order_by("-created_at")
    order_ref = str(order_ref or "").strip()
    if order_ref:
        qs = qs.filter(ref__iexact=order_ref)
    orders = []
    for order in qs[:3]:
        try:
            projection = build_order_conversation(order, channel_ref=ctx.channel_ref)
        except Exception:
            logger.exception("concierge.order_status projection failed order=%s", order.ref)
            continue
        orders.append(
            {
                "order_ref": projection.order_ref,
                "status": projection.order_status,
                "state": projection.state,
                "title": projection.title,
                "message": projection.message,
                "items": list(projection.items_summary),
                "total": projection.total_display,
                "deadline_at": projection.deadline_at,
                "tracking_url": f"{_storefront_base_url()}{projection.tracking_url}",
                "needs_payment": projection.source_projection == "payment",
                "created_at": timezone.localtime(order.created_at).strftime("%d/%m %H:%M"),
            }
        )
    if order_ref and not orders:
        return {"ok": True, "orders": [], "message": f"Não achei o pedido {order_ref} para este cliente."}
    return {"ok": True, "orders": orders}


def last_order(ctx: ToolContext) -> dict:
    """O último pedido do cliente, para o "o de sempre"."""
    from shopman.guestman.services import customer as customer_service

    from shopman.shop.services.customer_orders import last_reorder_context

    ref = ctx.conversation.customer_ref
    customer = customer_service.get(ref) if ref else None
    if customer is None:
        return {"ok": True, "order_ref": "", "items": [], "message": "Sem histórico para este cliente."}
    order_ref, items = last_reorder_context(customer_uuid=customer.uuid, min_days=0)
    if not order_ref:
        return {"ok": True, "order_ref": "", "items": [], "message": "Sem pedido anterior."}
    return {
        "ok": True,
        "order_ref": order_ref,
        "items": [
            {"sku": item.get("sku", ""), "name": item.get("name", ""), "qty": int(Decimal(str(item.get("qty") or 0)))}
            for item in items
        ],
    }


def send_web_link(ctx: ToolContext, destination: str = "menu") -> dict:
    """Um link de acesso ao site, já logado, levando a sacola junto quando há."""
    destination = str(destination or "menu").strip().lower()
    path = WEB_DESTINATIONS.get(destination, WEB_DESTINATIONS["menu"])
    public_url = f"{_storefront_base_url()}{path}"

    info = _auth_customer_info(ctx)
    if info is None:
        return {"ok": True, "url": public_url, "logged_in": False, "cart_carried": False}

    web_key = _copy_cart_to_web(ctx)
    metadata: dict = {"next": path, "conversation_id": ctx.conversation.pk}
    if web_key:
        metadata["cart_session_key"] = web_key

    try:
        from shopman.doorman.models import AccessLink
        from shopman.doorman.services.access_link import AccessLinkService

        result = AccessLinkService.create_token(
            info,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.MANYCHAT,
            metadata=metadata,
        )
    except Exception:
        logger.exception("concierge.send_web_link failed")
        result = None
    if result is None or not getattr(result, "success", False) or not getattr(result, "url", ""):
        return {"ok": True, "url": public_url, "logged_in": False, "cart_carried": bool(web_key)}
    return {
        "ok": True,
        "url": result.url,
        "logged_in": True,
        "cart_carried": bool(web_key),
        "expires_at": str(getattr(result, "expires_at", "") or ""),
    }


def _auth_customer_info(ctx: ToolContext):
    ref = ctx.conversation.customer_ref
    if not ref:
        return None
    try:
        from shopman.guestman.adapters.auth import CustomerResolver
        from shopman.guestman.services import customer as customer_service

        customer = customer_service.get(ref)
        if customer is None:
            return None
        return CustomerResolver().get_by_uuid(customer.uuid)
    except Exception:
        logger.debug("concierge.auth_customer_info degraded", exc_info=True)
        return None


def _copy_cart_to_web(ctx: ToolContext) -> str:
    """Leva a sacola do chat para uma sacola da LOJA (canal web) e abandona a do chat.

    A sacola do site é lida no canal da loja; uma sessão do canal do concierge
    não seria encontrada por lá. Copiar (reservando de novo) e abandonar a antiga
    (liberando os holds) mantém uma única reserva viva.
    """
    from shopman.shop.services import cart as cart_service
    from shopman.shop.services import sessions
    from shopman.shop.services.cart import CartUnavailableError

    session = _open_session(ctx)
    if session is None or not (session.items or []):
        return ""

    web_ref = _storefront_ref()
    web_key: str | None = None
    for item in session.items:
        try:
            _, web_key = cart_service.add_item(
                session_key=web_key,
                channel_ref=web_ref,
                origin_channel="whatsapp",
                sku=str(item.get("sku")),
                qty=int(Decimal(str(item.get("qty") or 0))),
                unit_price_q=int(item.get("unit_price_q") or 0),
                name=str(item.get("name") or ""),
            )
        except CartUnavailableError:
            logger.info("concierge.copy_cart_to_web skipped sku=%s", item.get("sku"))
        except Exception:
            logger.exception("concierge.copy_cart_to_web failed sku=%s", item.get("sku"))
    if not web_key:
        return ""
    if ctx.conversation.phone:
        sessions.assign_phone_handle(session_key=web_key, channel_ref=web_ref, phone=ctx.conversation.phone)
    sessions.abandon_session(session_key=session.session_key, channel_ref=ctx.channel_ref)
    ctx.conversation.session_key = ""
    ctx.conversation.save(update_fields=["session_key", "updated_at"])
    return web_key


def handoff_to_human(ctx: ToolContext, reason: str = "") -> dict:
    """Passa a conversa para a equipe. A casa cuida do alerta e do campo no ManyChat."""
    ctx.handoff = True
    ctx.handoff_reason = " ".join(str(reason or "").split()).strip()[:200] or "pedido do cliente"
    return {"ok": True, "message": "A equipe foi avisada e continua a conversa por aqui."}


# ── Registro ──────────────────────────────────────────────────────────


def _schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOL_SPECS: list[dict] = [
    {
        "name": "browse_menu",
        "description": (
            "Lista o cardápio de agora com preço e disponibilidade reais. Use antes de falar de "
            "qualquer produto, preço ou saldo. `query` filtra por nome/descrição (\"\" para tudo); "
            "`collection` filtra por uma coleção do cardápio, pela ref ou pelo rótulo que a própria "
            "resposta lista em `collections` (\"\" para todas)."
        ),
        "input_schema": _schema(
            {
                "query": {"type": "string", "description": "Termo de busca, ou \"\"."},
                "collection": {"type": "string", "description": "Ref ou rótulo da coleção, ou \"\"."},
            },
            ["query", "collection"],
        ),
        "strict": True,
    },
    {
        "name": "view_cart",
        "description": "Mostra a sacola atual: itens, totais, entrega/retirada escolhida e o que falta para fechar.",
        "input_schema": _schema({}, []),
        "strict": True,
    },
    {
        "name": "set_item",
        "description": (
            "Define a quantidade ABSOLUTA de um produto na sacola (0 remove). Reserva o estoque; se não "
            "houver, devolve o saldo real e substitutos. Use o SKU exato de browse_menu."
        ),
        "input_schema": _schema(
            {
                "sku": {"type": "string", "description": "SKU do produto."},
                "qty": {"type": "integer", "description": "Quantidade final desejada (0 remove)."},
            },
            ["sku", "qty"],
        ),
        "strict": True,
    },
    {
        "name": "list_pickup_slots",
        "description": (
            "Dias e horários possíveis. Para retirada devolve os slots (com os que a produção "
            "ainda não alcança). Para entrega devolve as janelas do dia. `delivery_date` em AAAA-MM-DD "
            "ou \"\" para hoje."
        ),
        "input_schema": _schema(
            {
                "delivery_date": {"type": "string", "description": "AAAA-MM-DD ou \"\"."},
                "fulfillment_type": {"type": "string", "enum": ["pickup", "delivery"]},
            },
            ["delivery_date", "fulfillment_type"],
        ),
        "strict": True,
    },
    {
        "name": "set_fulfillment",
        "description": (
            "Grava retirada (pickup) ou entrega (delivery), a data (AAAA-MM-DD, \"\" = hoje), o "
            "horário (slot_ref de list_pickup_slots, \"\" se ainda não escolhido) e, na entrega, o "
            "endereço completo com número. Valida como o site e devolve a taxa de entrega."
        ),
        "input_schema": _schema(
            {
                "fulfillment_type": {"type": "string", "enum": ["pickup", "delivery"]},
                "delivery_date": {"type": "string", "description": "AAAA-MM-DD ou \"\"."},
                "slot_ref": {"type": "string", "description": "Ref do horário, ou \"\"."},
                "address": {"type": "string", "description": "Endereço completo (entrega), ou \"\"."},
            },
            ["fulfillment_type", "delivery_date", "slot_ref", "address"],
        ),
        "strict": True,
    },
    {
        "name": "review_order",
        "description": (
            "Fecha o orçamento: recap de itens, entrega/retirada, total e formas de pagamento. Devolve "
            "`ready` e, quando pronto, o `quote_token`. Apresente o recap ao cliente e peça a confirmação "
            "explícita ANTES de place_order."
        ),
        "input_schema": _schema({}, []),
        "strict": True,
    },
    {
        "name": "place_order",
        "description": (
            "Cria o pedido do orçamento confirmado. Só depois do cliente dizer que confirma. Passe o "
            "`quote_token` de review_order e a forma de pagamento escolhida. O código Pix, quando "
            "houver, é enviado pela casa numa mensagem separada logo após a sua."
        ),
        "input_schema": _schema(
            {
                "quote_token": {"type": "string"},
                "payment_method": {"type": "string", "description": "Ref de payment_methods (ex.: pix, card)."},
                "order_notes": {"type": "string", "description": "Observação do cliente para a cozinha, ou \"\"."},
            },
            ["quote_token", "payment_method", "order_notes"],
        ),
        "strict": True,
    },
    {
        "name": "order_status",
        "description": (
            "Situação dos pedidos do cliente (os 3 últimos, ou um ref específico): estado, mensagem "
            "oficial, prazo e link de acompanhamento."
        ),
        "input_schema": _schema(
            {"order_ref": {"type": "string", "description": "Ref do pedido, ou \"\" para os últimos."}},
            ["order_ref"],
        ),
        "strict": True,
    },
    {
        "name": "last_order",
        "description": "Itens do último pedido do cliente, para repetir (\"o de sempre\").",
        "input_schema": _schema({}, []),
        "strict": True,
    },
    {
        "name": "send_web_link",
        "description": (
            "Gera um link do site já logado (leva a sacola junto quando há). Use quando algo é melhor "
            "no site: cardápio completo com fotos, entrega fora do fluxo, conta, ou cliente sem telefone."
        ),
        "input_schema": _schema(
            {"destination": {"type": "string", "enum": ["menu", "checkout", "account"]}},
            ["destination"],
        ),
        "strict": True,
    },
    {
        "name": "handoff_to_human",
        "description": (
            "Passa a conversa para a equipe da casa. Use quando o cliente pedir uma pessoa, reclamar, "
            "ou quando você não consegue resolver com as outras ferramentas."
        ),
        "input_schema": _schema({"reason": {"type": "string", "description": "Motivo, em uma frase."}}, ["reason"]),
        "strict": True,
    },
]

_HANDLERS = {
    "browse_menu": browse_menu,
    "view_cart": view_cart,
    "set_item": set_item,
    "list_pickup_slots": list_pickup_slots,
    "set_fulfillment": set_fulfillment,
    "review_order": review_order,
    "place_order": place_order,
    "order_status": order_status,
    "last_order": last_order,
    "send_web_link": send_web_link,
    "handoff_to_human": handoff_to_human,
}

TOOL_NAMES = tuple(_HANDLERS)


def execute(name: str, arguments: dict, ctx: ToolContext) -> dict:
    """Roda a ferramenta ``name``. Nunca levanta: erro vira resultado explicável."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return _error("unknown_tool", f"Ferramenta desconhecida: {name}")
    try:
        return handler(ctx, **(arguments or {}))
    except TypeError as exc:
        logger.warning("concierge.tool_bad_arguments tool=%s: %s", name, exc)
        return _error("bad_arguments", f"Argumentos inválidos para {name}.")
    except Exception as exc:
        logger.exception("concierge.tool_failed tool=%s", name)
        return _error("tool_failed", f"{name} falhou: {getattr(exc, 'message', exc)}")
