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
  pedido volta para a revisão. O token identifica o resumo; compra exige também
  Message de revisão aceita pelo provider e uma nova entrada explícita do cliente.
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
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.conf import settings
from django.db import transaction
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
    "order": "",  # resolvido em runtime: o acompanhamento do pedido mais recente
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
    rendered_results: list[str] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────


def _quantity_value(value):
    quantity = Decimal(str(value))
    return int(quantity) if quantity == quantity.to_integral_value() else format(quantity.normalize(), "f")


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

    O listing comercial é explícito. Ausência não autoriza trocar preço/canal
    silenciosamente pelo catálogo da loja online.
    """
    return channel_ref


def _open_session(ctx: ToolContext):
    from shopman.shop.services import cart as cart_service

    key = ctx.conversation.session_key
    if not key:
        return None
    session = cart_service.get_open_session(session_key=key, channel_ref=ctx.channel_ref)
    if session is None:
        # Sacola fechada ou abandonada por fora (limpeza, commit): esquecer a chave.
        Conversation.objects.filter(pk=ctx.conversation.pk, session_key=key).update(session_key="")
        ctx.conversation.refresh_from_db(fields=["session_key"])
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
        "count": _quantity_value(cart.count),
        "lines": [
            {
                "sku": line.sku,
                "name": line.name,
                "qty": _quantity_value(line.qty),
                "unit_price": _money(line.unit_price_q),
                "line_total": _money(line.line_total_q),
                "is_available": line.is_available,
                "available_qty": _quantity_value(line.available_qty) if line.available_qty is not None else None,
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
        "order_notes": str(data.get("order_notes") or ""),
        "can_checkout": bool(cart.can_checkout),
        "checkout_block_reason": cart.checkout_block_reason or "",
    }
    if cart.minimum_order is not None:
        payload["minimum_order"] = _progress_payload(cart.minimum_order)
    suggestions_on = bool((getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}).get("suggest_add_ons"))
    if suggestions_on and cart.upsell is not None and not (ctx.conversation.flags or {}).get("suggestion_offered"):
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
        "session_key": session.session_key,
        "revision": session.rev,
        "customer": data.get("customer"),
        "coupon_code": data.get("coupon_code"),
        "order_notes": data.get("order_notes"),
        "payment": data.get("payment"),
        "lines": lines,
        "lines_total_q": _lines_total_q(session),
        "delivery_fee_q": data.get("delivery_fee_q"),
        "fulfillment_type": data.get("fulfillment_type"),
        "delivery_date": data.get("delivery_date"),
        "delivery_time_slot": data.get("delivery_time_slot"),
        "delivery_address": data.get("delivery_address"),
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode()).hexdigest()
    return digest


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
    return {"ok": False, "error": code, "code": code, "outcome": "not_applied", "message": message, **extra}


# ── Ferramentas ───────────────────────────────────────────────────────


def browse_menu(
    ctx: ToolContext, query: str = "", collection: str = "", available_only: bool = False
) -> dict:
    """O cardápio de agora: nome, preço e disponibilidade viva, do listing do canal.

    Sem ``query`` e sem ``collection`` devolve a VISÃO GERAL: cada coleção com
    quantos itens tem disponíveis agora e até três exemplos. Uma fatia dos
    primeiros doze itens do catálogo era o que fazia "o que tem hoje?" virar
    lista de cafés (a ordem do catálogo começa nas bebidas).

    ``collection`` aceita a ref ("paes") ou o rótulo ("Pães", "folhados"); o que não
    casa com nada é ignorado, com aviso no resultado. ``available_only`` tira do
    resultado o que não pode ser pedido agora. Itens disponíveis vêm primeiro.
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
    if not needle and not wanted:
        return _menu_overview(items, catalog, available_only=available_only)

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

    if available_only:
        items = [item for item in items if item.can_add_to_cart]
    items.sort(key=lambda item: (0 if item.can_add_to_cart else 1))

    payload = {
        "ok": True,
        "count": len(items),
        "available_count": sum(1 for item in items if item.can_add_to_cart),
        "items": [_item_payload(item) for item in items[:MAX_MENU_ITEMS]],
        "truncated": len(items) > MAX_MENU_ITEMS,
    }
    if collection_note:
        payload["note"] = collection_note
    if catalog.happy_hour is not None:
        label = getattr(catalog.happy_hour, "label", "") or getattr(catalog.happy_hour, "message", "")
        if label:
            payload["happy_hour"] = str(label)
    return payload


def _menu_overview(items: list, catalog, *, available_only: bool) -> dict:
    """Coleções com contagem de disponíveis e exemplos, no lugar de uma fatia cega."""
    by_collection: dict[str, list] = {}
    for item in items:
        by_collection.setdefault(_fold(item.category or ""), []).append(item)
    collections = []
    for cat in catalog.categories:
        ref = getattr(cat, "ref", "") or ""
        label = getattr(cat, "label", "") or getattr(cat, "name", "") or ref
        members = by_collection.get(_fold(label)) or by_collection.get(_fold(ref)) or []
        available = [item for item in members if item.can_add_to_cart]
        if available_only and not available:
            continue
        collections.append(
            {
                "ref": ref,
                "label": label,
                "available_count": len(available),
                "total_count": len(members),
                "examples": [
                    {"sku": item.sku, "name": item.name, "price": item.price_display}
                    for item in (available or members)[:3]
                ],
            }
        )
    return {
        "ok": True,
        "overview": True,
        "available_count": sum(1 for item in items if item.can_add_to_cart),
        "total_count": len(items),
        "collections": collections,
        "hint": "Para listar itens, chame de novo com `collection` (ref ou rótulo) ou `query`.",
    }


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
    from shopman.offerman.models import Product
    from shopman.utils import units
    product = Product.objects.filter(sku__iexact=sku).first()
    if product is None:
        return _error("unknown_sku", "Não encontrei esse produto no cardápio. Escolha um produto disponível.")
    try:
        if isinstance(qty, bool) or not isinstance(qty, (int, float, str, Decimal)):
            raise ValueError
        parsed = units.convert(qty, product.unit, product.unit)
        from shopman.orderman.models import SessionItem
        precision = Decimal(1).scaleb(-SessionItem._meta.get_field("qty").decimal_places)
        if not parsed.is_finite() or parsed < 0 or parsed > MAX_LINE_QTY or parsed != parsed.quantize(precision):
            raise ValueError
        if units.dimension(product.unit) == units.COUNT:
            units_count = units.convert(parsed, product.unit, "un")
            if units_count != units_count.to_integral_value():
                raise ValueError
        qty = parsed
    except (ValueError, InvalidOperation, units.UnitError):
        return _error("invalid_qty", "Informe uma quantidade válida na unidade do produto, entre 0 e 99; zero remove o item.")
    item = _catalog_item(ctx, product.sku)
    if item is None:
        return _error("unknown_sku", "Esse produto não está disponível neste cardápio.")
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
        held_qty = Decimal(str(existing.get("qty") or 0)) if existing is not None else Decimal(0)
        available_total = Decimal(str(exc.available_qty)) + held_qty
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
            requested_qty=_quantity_value(qty),
            available_qty=_quantity_value(available_total),
            is_paused=bool(exc.is_paused),
            planned_for_date=str(getattr(exc, "planned_target_date", "") or ""),
            substitutes=substitutes,
        )
    except Exception:
        logger.exception("concierge.set_item failed sku=%s", sku)
        return _error("cart_error", "Não consegui atualizar a sacola. Suas escolhas foram preservadas; tente consultar a sacola.")

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

    session = _open_session(ctx)
    if session is None:
        return _error("no_cart", "Escolha os itens antes da entrega ou retirada.")
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

    values: dict = {"fulfillment_type": fulfillment_type, "delivery_date": when, "delivery_time_slot": ""}
    structured = None
    base_revision = session.rev
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

    from shopman.orderman.models import Session
    with transaction.atomic():
        locked = Session.objects.select_for_update().get(pk=session.pk)
        if locked.rev != base_revision or locked.state != "open":
            return _error("revision_conflict", "A sacola mudou. Confira as escolhas atuais antes de alterar a entrega.")
        _assert_authority(ctx)
        cart_service.set_delivery_draft(
            session_key=session.session_key, channel_ref=ctx.channel_ref,
            fulfillment_type=fulfillment_type, delivery_address_structured=structured,
        )
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


def review_order(ctx: ToolContext, payment_method: str = "", order_notes: str | None = None) -> dict:
    """O orçamento: recap completo, o que falta e o token que autoriza o pedido."""
    from shopman.shop.config import ChannelConfig
    from shopman.storefront.intents.checkout import _validate_preorder

    session = _open_session(ctx)
    if session is None or not (session.items or []):
        return {"ok": True, "ready": False, "missing": ["items"], "message": "A sacola está vazia."}

    from shopman.shop.services import cart as cart_service
    if order_notes is not None:
        if not isinstance(order_notes, str) or len(order_notes) > 300:
            return _error("invalid_input", "A observação deve ter até 300 caracteres.")
        session = _set_session_data(ctx, session.session_key, {"order_notes": " ".join(order_notes.split())})
    methods = ChannelConfig.for_channel(ctx.channel_ref).payment.available_methods
    selected = payment_method or (session.data or {}).get("payment", {}).get("method") or (methods[0] if len(methods) == 1 else "")
    if selected and selected not in methods:
        return _error("invalid_payment_method", "Escolha uma forma de pagamento disponível.")
    if selected:
        session = _set_session_data(ctx, session.session_key, {"payment": {"method": selected}})
    else:
        session = cart_service.reprice(session_key=session.session_key, channel_ref=ctx.channel_ref)
    payload = _cart_payload(ctx, session)
    data = session.data or {}
    missing: list[str] = []
    if not selected:
        missing.append("payment_method")
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
        "payment_method": selected,
    }
    if payload.get("suggestion"):
        # Uma sugestão por CONVERSA. Medido em 04/09: Pain Grillé num recap, Água no
        # seguinte; a regra do prompt ("uma vez, nunca de novo") precisa do código.
        flags = dict(ctx.conversation.flags or {})
        flags["suggestion_offered"] = True
        ctx.conversation.flags = flags
        ctx.conversation.save(update_fields=["flags", "updated_at"])
    if not missing:
        token = _quote_token(session)
        ctx.conversation.quote = {
            "token": token,
            "session_key": session.session_key,
            "customer_ref": ctx.conversation.customer_ref,
            "phone": ctx.conversation.phone,
            "snapshot": payload,
            "revision": session.rev,
            "payment_method": selected,
            "total_q": int(payload["total_q"]),
            "lines_total_q": _lines_total_q(session),
            "issued_at": timezone.now().isoformat(),
            "validity": "session_open_and_current_policy",
        }
        ctx.conversation.save(update_fields=["quote", "updated_at"])
        result["quote_token"] = token
    return result


def _assert_authority(ctx: ToolContext, *, for_mutation=True):
    from shopman.storefront.concierge import service
    current = service.assert_turn_authority(ctx.conversation, for_mutation=for_mutation)
    if (current.customer_ref, current.phone, current.channel_ref) != (ctx.conversation.customer_ref, ctx.conversation.phone, ctx.channel_ref):
        raise service.TurnRevoked("identity_changed")
    return current


def _occurred_after_offer(message, offered) -> bool:
    from django.utils.dateparse import parse_datetime
    raw = (message.envelope or {}).get("provider_timestamp")
    if not raw:
        return True
    try:
        occurred_at = parse_datetime(str(raw))
    except (TypeError, ValueError):
        return False
    return bool(occurred_at is not None and timezone.is_aware(occurred_at) and occurred_at > offered.created_at)


def _confirmation(ctx: ToolContext, token: str):
    from shopman.shop.models import ConversationMessage as Message
    offered = Message.objects.filter(
        conversation=ctx.conversation, kind=Message.Kind.REPLY,
        transport_state="accepted", envelope__quote_token=token,
    ).order_by("-pk").first()
    if offered is None:
        return None
    inbound = Message.objects.filter(
        conversation=ctx.conversation, kind=Message.Kind.INBOUND, pk__gt=offered.pk,
    )
    limit = getattr(ctx.conversation, "_inbound_max_id", None)
    if limit is not None:
        inbound = inbound.filter(pk__lte=limit)
    messages = list(inbound.order_by("pk"))
    if not messages:
        return None
    # Correção no mesmo envio ou outra intenção intermediária invalida o aceite.
    for message in messages:
        if (message.envelope or {}).get("version") != 2 or not (message.envelope or {}).get("event_id") or not _occurred_after_offer(message, offered):
            return None
        if _fold(message.text).rstrip(".! ") not in {"sim", "confirmo", "pode confirmar", "confirmar pedido", "sim, confirmo"}:
            return None
    return messages[-1]


def place_order(ctx: ToolContext, quote_token: str, payment_method: str, order_notes: str = "") -> dict:
    """Compra autorizada por revisão oferecida; recibo e efeito local compartilham commit."""
    from shopman.orderman.models import Order, Session

    from shopman.shop.config import ChannelConfig
    from shopman.shop.services import checkout as checkout_service
    from shopman.shop.services import remote_mutations
    from shopman.shop.services.customer_orders import customer_identity_filter

    _assert_authority(ctx)
    conversation = ctx.conversation
    current = Conversation.objects.get(pk=conversation.pk)
    if current.customer_ref != conversation.customer_ref or current.phone != conversation.phone or current.channel_ref != ctx.channel_ref:
        return _error("identity_required", "Confirme seu acesso para continuar este pedido.")
    if not conversation.phone:
        return _error("identity_required", "O pedido precisa de identificação pelo acesso seguro do site.")
    if not isinstance(quote_token, str) or not quote_token or not isinstance(payment_method, str) or not isinstance(order_notes, str):
        return _error("invalid_input", "Confira a revisão e a forma de pagamento.")
    payment_method = payment_method.strip().lower()
    methods = ChannelConfig.for_channel(ctx.channel_ref).payment.available_methods
    if payment_method not in methods:
        return _error("invalid_payment_method", "Forma de pagamento indisponível neste canal.")
    if len(order_notes) > 300:
        return _error("invalid_input", "A observação deve ter até 300 caracteres.")
    notes = " ".join(order_notes.split()) or str(((current.quote or {}).get("snapshot") or {}).get("order_notes") or "")
    scope = "concierge.purchase:" + hashlib.sha256(f"{conversation.pk}:{ctx.channel_ref}".encode()).hexdigest()[:40]
    fingerprint = remote_mutations.mutation_fingerprint({
        "customer_ref": conversation.customer_ref, "phone": conversation.phone,
        "channel_ref": ctx.channel_ref, "revision": quote_token, "payment_method": payment_method, "notes": notes,
    })
    try:
        receipt = remote_mutations.lookup_local_mutation(scope=scope, key=quote_token, fingerprint=fingerprint)
        if receipt:
            body = dict(receipt.response_body)
            if not body.get("ok"):
                return body
            identity = customer_identity_filter(customer_ref=conversation.customer_ref or None, phone=conversation.phone)
            if identity is None or not Order.objects.filter(identity, ref=body.get("order_ref")).exists():
                return _error("identity_required", "Confirme seu acesso para consultar este pedido.")
            return _placed_result(ctx, body["order_ref"], payment_method, replayed=True)
    except remote_mutations.RemoteMutationConflict:
        return _error("intent_conflict", "Esta confirmação já foi usada com outras escolhas. Consulte o pedido registrado.")
    except remote_mutations.RemoteMutationInProgress:
        return _error("in_progress", "Sua confirmação está em processamento. Consulte o resultado sem fazer outro pedido.")
    quote = current.quote or {}
    if quote_token != quote.get("token"):
        return _error("quote_stale", "A revisão mudou. Confira a sacola antes de confirmar.")
    if payment_method != quote.get("payment_method"):
        return _error("revision_conflict", "A forma de pagamento mudou. Confira uma nova revisão.")
    confirmation = _confirmation(ctx, quote_token)
    if confirmation is None:
        return _error("confirmation_required", "Confira o resumo enviado e confirme o pedido em uma nova mensagem.")
    if quote.get("phone") != current.phone or quote.get("customer_ref") != current.customer_ref:
        return _error("identity_required", "Sua identificação mudou. Confira uma nova revisão.")
    session = _open_session(ctx)
    if session is None or not session.items:
        recovered = remote_mutations.lookup_local_mutation(scope=scope, key=quote_token, fingerprint=fingerprint)
        if recovered:
            if not recovered.response_body.get("ok"):
                return recovered.response_body
            return _placed_result(ctx, recovered.response_body["order_ref"], payment_method, replayed=True)
        return _error("no_cart", "Não há sacola aberta. Consulte seus pedidos para recuperar um pedido já registrado.")
    # O conteúdo completo que os defaults e o endereço recebem é o da Session.
    data = {key: value for key, value in (session.data or {}).items() if key in {
        "fulfillment_type", "delivery_address", "delivery_address_structured", "delivery_date",
        "delivery_time_slot", "saved_address_id", "order_notes", "is_gift", "recipient", "gift_message", "gift_hide_values",
    }}
    data.update(customer={k: v for k, v in {"name": current.customer_name, "phone": current.phone, "ref": current.customer_ref}.items() if v}, payment={"method": payment_method})
    if notes:
        # Uma observação nova pode mudar produção/entrega; deve constar no resumo.
        if notes != str((session.data or {}).get("order_notes") or ""):
            return _error("revision_conflict", "Inclua a observação na sacola e confira o novo resumo antes de confirmar.")
        data["order_notes"] = notes

    def commit_local():
        latest = Conversation.objects.select_for_update().get(pk=conversation.pk)
        if (latest.quote or {}).get("token") != quote_token:
            return _error("revision_conflict", "A revisão mudou. Confira o resumo atual."), 409
        locked = Session.objects.select_for_update().get(pk=session.pk)
        _assert_authority(ctx)
        if locked.state != "open" or quote_token != _quote_token(locked):
            return _error("revision_conflict", "A sacola mudou. Suas escolhas estão preservadas; confira o novo resumo."), 409
        fresh = _cart_payload(ctx, locked)
        if fresh["total_q"] != quote["total_q"]:
            return _error("revision_conflict", "O total mudou; confira a diferença antes de confirmar.", previous_total_q=quote["total_q"], current_total_q=fresh["total_q"]), 409
        from shopman.storefront.intents.checkout import _validate_preorder
        errors = _validate_preorder(str(locked.data.get("delivery_date") or ""), cart_lines=locked.items,
            channel_ref=ctx.channel_ref, session_key=locked.session_key)
        if locked.data.get("fulfillment_type") == "pickup":
            from shopman.storefront.services.pickup_slots import validate_pickup_slot_selection
            slot_error = validate_pickup_slot_selection(locked.data.get("delivery_time_slot", ""),
                delivery_date=locked.data.get("delivery_date", ""), cart_skus=[str(i.get("sku")) for i in locked.items],
                now=timezone.localtime().time().replace(second=0, microsecond=0))
            if slot_error:
                errors["delivery_time_slot"] = slot_error
        elif locked.data.get("fulfillment_type") == "delivery" and locked.data.get("delivery_time_slot"):
            from shopman.shop.services.business_calendar import delivery_slots_for
            slots = delivery_slots_for(_parse_date(locked.data.get("delivery_date", "")))
            if locked.data["delivery_time_slot"] not in {slot.get("ref") for slot in slots}:
                errors["delivery_time_slot"] = "O horário não está mais disponível para entrega."
        if errors:
            return _error("revision_conflict", "A data mudou de disponibilidade. Escolha um horário válido.", errors=errors), 409
        result = checkout_service.process(
            locked.session_key, ctx.channel_ref, data,
            idempotency_key=hashlib.sha256(f"concierge:{conversation.pk}:{quote_token}".encode()).hexdigest(),
            ctx={"actor": "concierge", "conversation_id": conversation.pk},
            expected_total_q=int(quote["lines_total_q"]), expected_grand_total_q=int(quote["total_q"]),
        )
        Conversation.objects.filter(pk=conversation.pk).update(session_key="", last_order_ref=result.order_ref)
        return {"ok": True, "code": "order_registered", "outcome": "applied", "order_ref": result.order_ref,
            "intent_ref": quote_token, "revision": quote_token, "confirmation_message_id": confirmation.pk}, 200
    try:
        receipt = remote_mutations.run_idempotent_mutation(scope=scope, key=quote_token, fingerprint=fingerprint, execute=commit_local)
    except remote_mutations.RemoteMutationConflict:
        return _error("intent_conflict", "Esta confirmação já tem outras escolhas. Consulte o pedido registrado.")
    except Exception as exc:
        logger.exception("concierge.place_order refused conversation=%s", conversation.pk)
        recovered = remote_mutations.lookup_local_mutation(scope=scope, key=quote_token, fingerprint=fingerprint)
        if recovered and recovered.response_body.get("order_ref"):
            return _placed_result(ctx, recovered.response_body["order_ref"], payment_method, replayed=True)
        if getattr(exc, "code", "") == "total_changed":
            return _error("revision_conflict", "O total mudou. Confira a diferença antes de confirmar.", facts=getattr(exc, "context", {}))
        return _error("checkout_unavailable", "Não consegui concluir a confirmação. Consulte o resultado usando esta mesma confirmação.")
    if not receipt.response_body.get("ok"):
        return receipt.response_body
    conversation.session_key = ""
    return _placed_result(ctx, receipt.response_body["order_ref"], payment_method, replayed=receipt.replayed)


def _placed_result(ctx, order_ref, payment_method, *, replayed=False):
    from shopman.orderman.models import Order
    order = Order.objects.get(ref=order_ref)
    payment = (order.data or {}).get("payment") or {}
    pix_code = str(payment.get("copy_paste") or "").strip()
    if pix_code:
        ctx.extra_replies.append(pix_code)
    ctx.order_ref = order.ref
    pending = payment_method in {"pix", "card"} and not (pix_code or payment.get("checkout_url"))
    return {
        "ok": True, "code": "payment_pending" if pending else "order_registered",
        "outcome": "already_applied" if replayed else ("partial" if pending else "applied"),
        "order_ref": order.ref, "resource_ref": order.ref, "status": order.status,
        "total": _money(order.total_q), "items_count": order.items.count(),
        "tracking_url": f"{_storefront_base_url()}/pedido/{order.ref}/",
        "pending_effects": ["payment_setup"] if pending else [],
        "payment": {"method": payment_method, "pix_code_prepared_separately": bool(pix_code),
            "checkout_url": str(payment.get("checkout_url") or ""),
            "expires_at": str(payment.get("expires_at") or ""), "pending_setup": pending},
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
            from shopman.storefront.services.orders import resolve_timeouts_if_due
            resolve_timeouts_if_due(order)
            order.refresh_from_db()
            projection = build_order_conversation(order, channel_ref=ctx.channel_ref)
        except Exception:
            logger.exception("concierge.order_status projection failed order=%s", order.ref)
            return _error("projection_unavailable", "O pedido está registrado, mas não consegui atualizar a consulta. Tente consultar novamente.", resource_ref=order.ref)
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
                "actions": [asdict(action) for action in projection.actions],
                "source_projection": projection.source_projection,
                "payment_url": projection.payment_url,
                "requires_payment_gate": projection.requires_payment_gate,
                "supports_access_link": projection.supports_access_link,
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
            {"sku": item.get("sku", ""), "name": item.get("name", ""), "qty": str(Decimal(str(item.get("qty") or 0)))}
            for item in items
        ],
    }


def send_web_link(ctx: ToolContext, destination: str = "menu", order_ref: str = "") -> dict:
    """Acesso ao alvo exato; navegar não implica transferir uma sacola."""
    if destination not in WEB_DESTINATIONS:
        return _error("invalid_input", "Escolha cardápio, conta, sacola ou pedido.")
    path = WEB_DESTINATIONS[destination]
    if destination == "order":
        if not order_ref:
            available = order_status(ctx)
            if not available.get("ok"):
                return available
            return _error("target_required", "Escolha qual pedido quer abrir.", orders=available.get("orders", []))
        selected = order_status(ctx, order_ref)
        if not selected.get("ok"):
            return selected
        if not selected.get("orders"):
            return _error("not_found", "Não encontrei esse pedido para este acesso.")
        path = f"/pedido/{selected['orders'][0]['order_ref']}/"
    public_url = f"{_storefront_base_url()}{path}"
    info = _auth_customer_info(ctx)
    if info is None:
        return {"ok": True, "url": public_url, "logged_in": False, "cart_carried": False,
            "message": "Continue pelo site; confirme seu acesso para abrir dados pessoais."}
    if destination == "checkout" and not (getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}).get("transfer_enabled", False):
        return _error("transfer_disabled", "Sua sacola está preservada aqui. A continuação desta sacola no site ainda não está disponível.")
    try:
        from shopman.doorman.models import AccessLink
        from shopman.doorman.services.access_link import AccessLinkService

        from shopman.shop.services import remote_mutations
        current = Conversation.objects.get(pk=ctx.conversation.pk)
        source_key = current.session_key or (current.flags or {}).get("web_transfer_key", "")
        def prepare_access():
            # Mint é local. Qualquer falha reverte transferência e holds.
            with transaction.atomic():
                current = Conversation.objects.select_for_update().get(pk=ctx.conversation.pk)
                _assert_authority(ctx)
                web_key = _copy_cart_to_web(ctx) if destination == "checkout" else ""
                metadata = {"next": path, "conversation_id": ctx.conversation.pk}
                if web_key:
                    metadata["cart_session_key"] = web_key
                result = AccessLinkService.create_token(info, audience=AccessLink.Audience.WEB_GENERAL,
                    source=AccessLink.Source.MANYCHAT, metadata=metadata)
                if result is None or not result.success or not result.url:
                    raise ValueError("access_link_unavailable")
                if destination == "checkout":
                    flags = dict(current.flags or {})
                    flags["web_transfer_key"] = source_key
                    Conversation.objects.filter(pk=current.pk).update(flags=flags)
                return {"ok": True, "url": result.url, "logged_in": True, "cart_carried": bool(web_key),
                    "order_ref": order_ref, "resource_ref": web_key or order_ref,
                    "expires_at": str(getattr(result, "expires_at", "") or "")}, 200
        if destination == "checkout":
            if not source_key:
                return _error("no_cart", "Não há sacola para transferir. Consulte seus pedidos para continuar uma compra registrada.")
            fingerprint = remote_mutations.mutation_fingerprint({"customer_ref": current.customer_ref,
                "phone": current.phone, "source_key": source_key, "destination": _storefront_ref()})
            receipt = remote_mutations.run_idempotent_mutation(scope=f"concierge.transfer:{current.pk}",
                key=source_key, fingerprint=fingerprint, execute=prepare_access)
            return receipt.response_body
        return prepare_access()[0]

    except Exception:
        ctx.conversation.refresh_from_db()
        logger.exception("concierge.send_web_link failed")
        return _error("access_unavailable", "Não consegui preparar o acesso. Sua sacola foi preservada; podemos continuar aqui.")


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
    """Transferência conservadora: qualquer conflito reverte origem, destino e reservas."""
    from shopman.orderman.models import Session

    from shopman.shop.services import cart as cart_service
    from shopman.shop.services import sessions
    if not (getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}).get("transfer_enabled", False):
        raise ValueError("transfer_disabled")
    source = _open_session(ctx)
    if source is None or not source.items:
        raise ValueError("no_cart")
    base_revision = source.rev
    with transaction.atomic():
        Conversation.objects.select_for_update().get(pk=ctx.conversation.pk)
        source = Session.objects.select_for_update().get(pk=source.pk)
        _assert_authority(ctx)
        if source.rev != base_revision or source.state != "open":
            raise ValueError("revision_conflict")
        web_ref = _storefront_ref()
        # G05 precisa decidir conflito de carrinhos: jamais abandonar o existente.
        if ctx.conversation.phone and Session.objects.filter(channel_ref=web_ref, state="open", handle_type="phone", handle_ref=ctx.conversation.phone).exists():
            raise ValueError("destination_conflict")
        from shopman.shop.projections.cart import build_cart
        source_total_q = build_cart(source.session_key, ctx.channel_ref).grand_total_q
        # Liberação e nova reserva acontecem na mesma transação: ninguém observa
        # estoque liberado entre elas, e toda recusa restaura os holds originais.
        sessions.abandon_session(session_key=source.session_key, channel_ref=ctx.channel_ref)
        web_key = None
        for item in source.items:
            if item.get("sku") == "__DELIVERY_FEE__":
                continue
            qty = Decimal(str(item.get("qty") or 0))
            from shopman.orderman.models import SessionItem
            precision = Decimal(1).scaleb(-SessionItem._meta.get_field("qty").decimal_places)
            if not qty.is_finite() or qty <= 0 or qty != qty.quantize(precision):
                raise ValueError("unsupported_quantity")
            _, web_key = cart_service.add_item(session_key=web_key, channel_ref=web_ref,
                origin_channel=ctx.conversation.channel_ref, sku=str(item["sku"]), qty=qty,
                unit_price_q=int(item.get("unit_price_q") or 0), name=str(item.get("name") or ""))
        values = {key: value for key, value in source.data.items() if key in {
            "customer", "fulfillment_type", "delivery_address", "delivery_address_structured", "delivery_date",
            "delivery_time_slot", "order_notes", "coupon_code", "is_gift", "recipient", "gift_message", "gift_hide_values",
        }}
        target = sessions.modify_session(session_key=web_key, channel_ref=web_ref,
            ops=[{"op": "set_data", "path": key, "value": value} for key, value in values.items()])
        from shopman.shop.projections.cart import build_cart
        if source_total_q != build_cart(web_key, web_ref).grand_total_q:
            raise ValueError("commercial_revision_conflict")
        if len(target.items) != len(source.items):
            raise ValueError("incomplete_transfer")
        # Sem assign_phone_handle: essa função abandona carrinho concorrente.
        Conversation.objects.filter(pk=ctx.conversation.pk).update(session_key="")
        ctx.conversation.session_key = ""
        return web_key


def notify_when_available(ctx: ToolContext, sku: str) -> dict:
    """Disclosure oferecido e aceite posterior são a prova da inscrição canônica."""
    from shopman.shop.models import ConversationMessage as Message
    from shopman.storefront.services import stock_alerts
    item = _catalog_item(ctx, sku)
    if item is None:
        return _error("unknown_sku", "Não encontrei esse produto no cardápio.")
    text = stock_alerts.STOCK_ALERT_DISCLOSURE
    version = stock_alerts.STOCK_ALERT_DISCLOSURE_VERSION
    token = hashlib.sha256(f"{ctx.conversation.pk}:{item.sku}:{version}:{text}".encode()).hexdigest()
    offered = Message.objects.filter(conversation=ctx.conversation, kind=Message.Kind.REPLY,
        transport_state="accepted", envelope__disclosure__token=token).order_by("-pk").first()
    accepted = None
    if offered:
        messages = Message.objects.filter(conversation=ctx.conversation, kind=Message.Kind.INBOUND, pk__gt=offered.pk)
        limit = getattr(ctx.conversation, "_inbound_max_id", None)
        if limit is not None:
            messages = messages.filter(pk__lte=limit)
        messages = list(messages.order_by("pk"))
        if messages and all((m.envelope or {}).get("version") == 2 and (m.envelope or {}).get("event_id") and _occurred_after_offer(m, offered) and
            _fold(m.text).rstrip(".! ") in {"sim", "aceito", "quero o aviso", "sim, aceito"} for m in messages):
            accepted = messages[-1]
    if accepted is None:
        return {"ok": True, "code": "consent_required", "message": f"Aviso para {item.name}: {text} Deseja receber este aviso?",
            "disclosure": {"sku": item.sku, "text": text, "version": version, "token": token}}
    if not ctx.conversation.phone:
        return _error("identity_required", "Confirme seu contato no site para receber o aviso.")
    from shopman.guestman.services import customer as customer_service
    customer = customer_service.get(ctx.conversation.customer_ref) if ctx.conversation.customer_ref else None
    with transaction.atomic():
        Conversation.objects.select_for_update().get(pk=ctx.conversation.pk)
        _assert_authority(ctx)
        subscription = stock_alerts.subscribe(item.sku, channel_ref=ctx.channel_ref, customer=customer,
            phone=ctx.conversation.phone, disclosure_text=offered.envelope["disclosure"]["text"],
            disclosure_version=offered.envelope["disclosure"]["version"])
        if subscription is None:
            return _error("subscribe_failed", "Não consegui registrar o aviso. Suas escolhas estão preservadas.")
        # A inscrição é a fonte de consentimento; Message só liga a prova que o originou.
        envelope = dict(accepted.envelope or {})
        envelope["subscription_ref"] = str(subscription.ref)
        envelope["disclosure_message_id"] = offered.pk
        accepted.envelope = envelope
        accepted.save(update_fields=["envelope"])
    return {"ok": True, "code": "subscribed", "message": f"Aviso de disponibilidade registrado para {item.name}.",
        "resource_ref": str(subscription.ref)}


def handoff_to_human(ctx: ToolContext, reason: str = "") -> dict:
    """Passa a conversa para a equipe. A casa cuida do alerta e do campo no ManyChat."""
    ctx.handoff = True
    ctx.handoff_reason = " ".join(str(reason or "").split()).strip()[:200] or "pedido do cliente"
    return {"ok": True, "message": "Solicitação de atendimento registrada. A equipe continuará por aqui conforme a disponibilidade."}


def _guard(handler):
    @wraps(handler)
    def guarded(ctx, *args, **kwargs):
        try:
            _assert_authority(ctx, for_mutation=handler.__name__ not in {"browse_menu", "view_cart", "last_order", "order_status", "list_pickup_slots"})
            if handler.__name__ in {"set_item", "review_order"}:
                from shopman.orderman.models import Session
                with transaction.atomic():
                    current = Conversation.objects.select_for_update().get(pk=ctx.conversation.pk)
                    _assert_authority(ctx)
                    ctx.conversation.session_key = current.session_key
                    if current.session_key:
                        Session.objects.select_for_update().filter(session_key=current.session_key, channel_ref=ctx.channel_ref).first()
                    result = handler(ctx, *args, **kwargs)
                    if not result.get("ok"):
                        transaction.set_rollback(True)
                    return result
            return handler(ctx, *args, **kwargs)
        except Exception:
            logger.exception("concierge.command_blocked tool=%s", handler.__name__)
            return _error("authority_unavailable", "O atendimento automático está pausado. Suas escolhas foram preservadas.")
    return guarded


for _name in ("browse_menu", "view_cart", "last_order", "order_status", "list_pickup_slots", "set_item", "set_fulfillment", "review_order", "place_order", "send_web_link", "notify_when_available"):
    globals()[_name] = _guard(globals()[_name])


def _display_text(value) -> str:
    """Dado exibido não cria linhas factuais nem links fora de campos de Action.

    Não interpreta frases nem preços: normaliza controles/espaçamento e neutraliza
    URLs em texto livre. Links autorizados usam campos estruturados intactos.
    """
    text = str(value or "")
    text = re.sub(r"(?i)\b(?:[a-z][a-z0-9+.-]*://|www\.)\S+", "[link omitido]", text)
    text = "".join(" " if unicodedata.category(char).startswith("C") else char for char in text)
    return " ".join(text.split())


def _display_name(value) -> str:
    """Nome de catálogo explicitamente citado, distinto da prosa factual."""
    text = _display_text(value).replace("“", "'").replace("”", "'")
    return f"“{text}”"


def render_result(name: str, result: dict) -> str:
    """Somente fatos do servidor; texto livre do modelo nunca entra na resposta."""
    if not result.get("ok"):
        return _display_text(result.get("message") or "Não consegui concluir. Suas escolhas estão preservadas.")
    if result.get("message") and (
        name in {"notify_when_available", "handoff_to_human"}
        or not any(result.get(key) for key in ("lines", "orders", "items", "collections", "payment", "url", "pickup_slots", "delivery_slots"))
    ):
        return _display_text(result["message"])
    if name == "browse_menu":
        if result.get("overview"):
            rows = [f"{_display_name(c['label'])}: {c['available_count']} disponíveis. " + "; ".join(f"{_display_name(i['name'])} — {i['price']}" for i in c['examples']) for c in result.get("collections", [])]
        else:
            rows = [f"{_display_name(i['name'])} — {i['price']}. {_display_text(i['availability_label'])}" for i in result.get("items", [])]
        return "\n".join(rows) or "Não encontrei produtos para essa busca."
    if name in {"view_cart", "set_item", "set_fulfillment", "review_order"}:
        rows = [f"{i['qty']} × {_display_name(i['name'])} — {i['line_total']}" for i in result.get("lines", [])]
        if not rows:
            return "Sua sacola está vazia. Escolha um produto para começar."
        rows.append(f"Total: {result.get('total', '')}")
        fulfillment = result.get("fulfillment") or {}
        if fulfillment.get("type"):
            rows.append(f"{'Retirada' if fulfillment['type'] == 'pickup' else 'Entrega'}: {fulfillment.get('date', '')} {_display_text(fulfillment.get('slot_label', ''))}")
        if fulfillment.get("address"):
            rows.append(_display_text(fulfillment['address']))
        if result.get("order_notes"):
            rows.append(f"Observação: {_display_text(result['order_notes'])}")
        if result.get("delivery_fee"):
            rows.append(f"Entrega: {result['delivery_fee']}")
        if name == "review_order":
            methods = ", ".join(p["label"] for p in result.get("payment_methods", []))
            rows.append(f"Pagamento: {PAYMENT_LABELS.get(result.get('payment_method'), '') or methods}.")
            if result.get("ready"):
                rows.append("Confira o resumo. Ao confirmar, seu pedido será registrado; pagamento é uma etapa separada. Responda ‘confirmo’ para registrar.")
            else:
                labels = {"items": "escolher os produtos", "payment_method": "escolher como pagar", "customer_phone": "confirmar seu contato", "fulfillment_type": "escolher entrega ou retirada", "delivery_time_slot": "escolher o horário", "delivery_date": "escolher uma data disponível", "delivery_address": "informar o endereço", "delivery_out_of_zone": "escolher um endereço atendido ou retirada", "cart": "conferir a sacola"}
                rows.append("Ainda falta: " + ", ".join(labels.get(field, "conferir a disponibilidade da sacola") for field in result.get("missing", [])))
        return "\n".join(rows)
    if name == "place_order":
        payment = result.get("payment") or {}
        text = f"Pedido {result['order_ref']} registrado. Total: {result['total']}."
        if payment.get("pending_setup"):
            text += " O pagamento ainda não está disponível; consulte o mesmo pedido para acompanhar."
        elif payment.get("pix_code_prepared_separately"):
            text += " O pagamento está pendente; o código Pix é apresentado em um bloco separado."
        text += f"\nAcompanhar: {result['tracking_url']}"
        return text
    if name == "order_status":
        rows = []
        for order in result.get("orders", []):
            rows.append(f"Pedido {order['order_ref']} — {order['title']}. {order['message']} Total: {order['total']}.")
            for action in order.get("actions", []):
                if action.get("enabled"):
                    href = action.get("href") or order["tracking_url"]
                    if href.startswith("/") and not href.startswith("//"):
                        href = _storefront_base_url() + href
                    rows.append(f"{action['label']}: {href}")
            rows.append(f"Acompanhar: {order['tracking_url']}")
        return "\n".join(rows) or "Não encontrei pedidos para este acesso."
    if name == "send_web_link":
        return f"Continue no site: {result['url']}"
    if name == "last_order":
        return "\n".join(f"{i['qty']} × {_display_name(i['name'])}" for i in result.get("items", [])) or "Sem pedido anterior."
    if name == "list_pickup_slots":
        slots = result.get("pickup_slots", result.get("delivery_slots", []))
        return "\n".join(_display_text(i['label']) for i in slots if i.get("available", True)) or "Nenhum horário disponível nessa data."
    return _display_text(result.get("message") or "Suas escolhas foram preservadas. Podemos continuar.")


# ── Registro ──────────────────────────────────────────────────────────


def _schema(properties: dict, required: list[str]) -> dict:
    """Esquema de ferramenta SEM ``strict``, e só o obrigatório em ``required``.

    Medido em 04/09/2026: com ``strict`` e todo parâmetro obrigatório, o modelo,
    querendo omitir um filtro, era obrigado pela gramática a preencher a string e
    preenchia com a própria sintaxe interna de chamada (tags), turno após turno.
    Parâmetro opcional fica opcional; a função tem default.
    """
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
            "qualquer produto, preço ou saldo. Sem argumentos devolve a visão geral por coleção "
            "(quantos disponíveis e exemplos). `query` busca por nome/descrição; `collection` "
            "filtra por uma coleção, pela ref ou pelo rótulo; `available_only` mostra só o que "
            "pode ser pedido agora."
        ),
        "input_schema": _schema(
            {
                "query": {"type": "string", "description": "Termo de busca por nome ou descrição."},
                "collection": {"type": "string", "description": "Ref ou rótulo da coleção."},
                "available_only": {"type": "boolean", "description": "Só o que pode ser pedido agora."},
            },
            [],
        ),
    },
    {
        "name": "view_cart",
        "description": "Mostra a sacola atual: itens, totais, entrega/retirada escolhida e o que falta para fechar.",
        "input_schema": _schema({}, []),
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
                "qty": {"type": "number", "description": "Quantidade final na unidade do produto (0 remove); decimal exato para peso ou volume."},
            },
            ["sku", "qty"],
        ),
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
                "delivery_date": {"type": "string", "description": "AAAA-MM-DD; omita para hoje."},
                "fulfillment_type": {"type": "string", "enum": ["pickup", "delivery"]},
            },
            [],
        ),
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
            ["fulfillment_type"],
        ),
    },
    {
        "name": "review_order",
        "description": (
            "Fecha o orçamento: recap de itens, entrega/retirada, total e formas de pagamento. Devolve "
            "`ready` e, quando pronto, o `quote_token`. Apresente o recap ao cliente e peça a confirmação "
            "explícita ANTES de place_order."
        ),
        "input_schema": _schema({"payment_method": {"type": "string"}, "order_notes": {"type": "string", "description": "Observação para incluir no resumo antes da confirmação; até 300 caracteres."}}, []),
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
            ["quote_token", "payment_method"],
        ),
    },
    {
        "name": "order_status",
        "description": (
            "Situação dos pedidos do cliente (os 3 últimos, ou um ref específico): estado, mensagem "
            "oficial, prazo e link de acompanhamento."
        ),
        "input_schema": _schema(
            {"order_ref": {"type": "string", "description": "Ref do pedido; omita para os últimos."}},
            [],
        ),
    },
    {
        "name": "last_order",
        "description": "Itens do último pedido do cliente, para repetir (\"o de sempre\").",
        "input_schema": _schema({}, []),
    },
    {
        "name": "send_web_link",
        "description": (
            "Gera um link do site já logado (leva a sacola junto quando há). Use quando algo é melhor "
            "no site: cardápio completo com fotos, entrega fora do fluxo, conta, ou cliente sem telefone. "
            "Para PAGAR um pedido que já foi feito, use `order`: o pagamento de um pedido vive no "
            "acompanhamento dele, não no checkout."
        ),
        "input_schema": _schema(
            {"destination": {"type": "string", "enum": ["menu", "checkout", "account", "order"]}, "order_ref": {"type": "string"}},
            [],
        ),
    },
    {
        "name": "notify_when_available",
        "description": (
            "Registra o aviso \"me avise quando tiver\" para um produto indisponível, o mesmo sino do "
            "site: o cliente recebe uma mensagem quando o produto voltar ou quando sair a fornada. "
            "Ofereça quando um item pedido estiver indisponível."
        ),
        "input_schema": _schema({"sku": {"type": "string", "description": "SKU do produto."}}, ["sku"]),
    },
    {
        "name": "handoff_to_human",
        "description": (
            "Passa a conversa para a equipe da casa. Use quando o cliente pedir uma pessoa, reclamar, "
            "ou quando você não consegue resolver com as outras ferramentas."
        ),
        "input_schema": _schema({"reason": {"type": "string", "description": "Motivo, em uma frase."}}, []),
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
    "notify_when_available": notify_when_available,
    "handoff_to_human": handoff_to_human,
}

TOOL_NAMES = tuple(_HANDLERS)


def execute(name: str, arguments: dict, ctx: ToolContext) -> dict:
    """Roda a ferramenta ``name``. Nunca levanta: erro vira resultado explicável."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return _error("unknown_tool", f"Ferramenta desconhecida: {name}")
    schema = next(spec["input_schema"] for spec in TOOL_SPECS if spec["name"] == name)
    if not isinstance(arguments, dict) or set(arguments) - set(schema["properties"]) or any(key not in arguments for key in schema["required"]):
        return _error("invalid_input", "Confira os dados necessários para esta ação.")
    for key, value in arguments.items():
        prop = schema["properties"][key]
        kind = prop["type"]
        valid = ((kind == "string" and isinstance(value, str) and len(value) <= 2000)
            or (kind == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
            or (kind == "boolean" and isinstance(value, bool)))
        if not valid or ("enum" in prop and value not in prop["enum"]):
            return _error("invalid_input", "Confira o campo informado.", field=key)
    try:
        return handler(ctx, **arguments)
    except Exception:
        logger.exception("concierge.tool_failed tool=%s", name)
        return _error("tool_failed", "Não consegui concluir esta ação. Suas escolhas foram preservadas.")
