"""Checkout orchestration facade.

This is the single composed checkout path for external surfaces. It resolves
channel configuration, applies checkout/session operations, and commits through
Orderman via ``shopman.shop.services.sessions``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from types import SimpleNamespace

from django.db import transaction
from shopman.orderman.exceptions import ValidationError as OrderingValidationError
from shopman.orderman.services.commit import CommitService

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel
from shopman.shop.projections.order_tracking import convenience_pending
from shopman.shop.services import sessions

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckoutResult:
    order_ref: str
    status: str
    total_q: int
    items_count: int
    convenience_pending: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckoutDomainError:
    detail: str
    error_code: str
    context: dict
    http_status: int


@dataclass(frozen=True)
class _PreparedCheckout:
    session: object
    refusal: Exception | None = None


def process(
    session_key: str,
    channel_ref: str,
    data: dict,
    *,
    idempotency_key: str,
    expected_total_q: int,
    expected_revision: int,
    ctx: dict | None = None,
    expected_grand_total_q: int | None = None,
) -> CheckoutResult:
    """Convert checkout data to session operations and commit."""
    completed = CommitService.completed_response(session_key, channel_ref, idempotency_key)
    if completed is not None:
        result = _checkout_result(completed)
        pending = recover_post_commit_side_effects(result.order_ref)
        return replace(result, convenience_pending=tuple(pending or ()))

    result = process_ops(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=_build_ops_from_data(data),
        idempotency_key=idempotency_key,
        ctx=ctx,
        expected_total_q=expected_total_q,
        expected_grand_total_q=expected_grand_total_q,
        expected_revision=expected_revision,
    )
    pending = _apply_post_commit_side_effects(data, channel_ref, order_ref=result.order_ref)
    return replace(result, convenience_pending=tuple(pending or ()))


def process_ops(
    *,
    session_key: str,
    channel_ref: str,
    ops: list[dict],
    idempotency_key: str,
    expected_total_q: int,
    expected_revision: int,
    ctx: dict | None = None,
    expected_grand_total_q: int | None = None,
) -> CheckoutResult:
    """Reprice one reviewed revision, then seal that exact resulting revision."""
    completed = CommitService.completed_response(session_key, channel_ref, idempotency_key)
    if completed is not None:
        return _checkout_result(completed)

    ctx = dict(ctx or {})
    ctx["expected_total_q"] = int(expected_total_q)
    ctx["checkout_finalize"] = True
    channel = Channel.objects.get(ref=channel_ref)
    resolved_config = ChannelConfig.for_channel(channel).to_dict()

    prepared = _prepare_checkout_atomic(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=ops,
        ctx=ctx,
        channel_config=resolved_config,
        expected_revision=expected_revision,
        expected_total_q=expected_total_q,
        expected_grand_total_q=expected_grand_total_q,
    )
    if prepared.refusal is not None:
        raise prepared.refusal
    repriced = prepared.session

    ctx["expected_revision"] = repriced.rev
    commit = sessions.commit_session(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idempotency_key,
        ctx=ctx,
        channel_config=resolved_config,
    )

    logger.info("checkout.process: order %s committed for channel %s", commit.order_ref, channel_ref)
    return _checkout_result(commit)


@transaction.atomic
def _prepare_checkout_atomic(
    *,
    session_key: str,
    channel_ref: str,
    ops: list[dict],
    ctx: dict,
    channel_config: dict,
    expected_revision: int,
    expected_total_q: int,
    expected_grand_total_q: int | None,
) -> _PreparedCheckout:
    """Persist canonical repricing before the separate seal step."""
    repriced = sessions.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=ops,
        ctx=ctx,
        channel_config=channel_config,
        expected_revision=expected_revision,
    )

    try:
        # A decisão de total permanece canônica no Orderman. A exceção só sai
        # depois do commit deste bloco, preservando preço, revisão e identidade.
        CommitService.validate_expected_total(repriced, expected_total_q)

        from shopman.shop.projections.cart import build_cart

        cart = None
        if expected_grand_total_q is not None:
            from shopman.orderman.exceptions import ValidationError

            cart = build_cart(session_key, channel_ref)
            if cart.grand_total_q != expected_grand_total_q:
                raise ValidationError(
                    code="total_changed",
                    message="O total completo mudou. Confira uma nova revisão.",
                    context={
                        "old_total_q": expected_grand_total_q,
                        "new_total_q": cart.grand_total_q,
                    },
                )

        payment = (repriced.data or {}).get("payment") or {}
        if str(payment.get("method") or "").strip().lower() == "pix":
            from shopman.shop.services.pix_policy import (
                PixPaymentPolicyError,
                enforce_pix_test_amount_limit,
            )

            cart = cart or build_cart(session_key, channel_ref)
            try:
                enforce_pix_test_amount_limit(cart.grand_total_q)
            except PixPaymentPolicyError as exc:
                raise OrderingValidationError(
                    code=exc.code,
                    message=exc.message,
                    context=exc.context,
                ) from exc

    except OrderingValidationError as exc:
        return _PreparedCheckout(repriced, exc)

    return _PreparedCheckout(repriced)


def _checkout_result(commit) -> CheckoutResult:
    return CheckoutResult(
        order_ref=commit.order_ref,
        status=commit.status,
        total_q=commit.total_q,
        items_count=commit.items_count,
    )


def map_checkout_error(exc: Exception) -> dict[str, str] | None:
    """Map domain validation exceptions to checkout form errors."""
    from django.core.exceptions import ValidationError as DjangoValidationError
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    if isinstance(exc, OrderingValidationError):
        # ``total_changed`` carrega contexto estruturado (novo/antigo total) para a
        # tela reexibir old→new. Deixa passar para ``map_order_error``, que preserva
        # ``error_code`` + ``context`` — o mapeamento de form-field os descartaria.
        if exc.code in {"total_changed", "revision_changed", "pix_test_amount_limit"}:
            return None
        address_codes = {"delivery_zone_not_covered", "delivery_zone_unverified"}
        field = "delivery_address" if exc.code in address_codes else "checkout"
        # A trava da nota de entrega diz QUAL campo consertar (CPF ou endereço).
        from shopman.shop.services.delivery_fiscal_identity import REFUSAL_CODES

        if exc.code in REFUSAL_CODES:
            field = str((exc.context or {}).get("field") or field)
        return {field: exc.message}
    if isinstance(exc, DjangoValidationError):
        msgs = exc.messages if hasattr(exc, "messages") else [str(exc)]
        return {"checkout": msgs[0] if msgs else str(exc)}
    return None


def map_order_error(exc: Exception) -> CheckoutDomainError | None:
    """Map Orderman checkout errors without leaking Orderman imports to surfaces."""
    from shopman.orderman.exceptions import OrderError

    if not isinstance(exc, OrderError):
        return None

    code = getattr(exc, "code", "checkout_error")
    conflict_codes = {"revision_changed", "in_progress", "blocking_issues", "stale_checks", "hold_expired"}
    unprocessable_codes = {"pix_test_amount_limit"}
    http_status = 409 if code in conflict_codes else (422 if code in unprocessable_codes else 400)
    return CheckoutDomainError(
        detail=getattr(exc, "message", str(exc)),
        error_code=code,
        context=getattr(exc, "context", {}),
        http_status=http_status,
    )


def _fill_missing_first_name(customer_obj, name: str) -> None:
    if name and not customer_obj.first_name:
        customer_obj.first_name = name
        customer_obj.save(update_fields=["first_name"])


def _phone_owner_any_state(phone: str):
    """Quem é dono deste telefone, ATIVO OU NÃO.

    ``customer_service.get_by_phone`` só enxerga cadastro ativo; o UNIQUE global
    ``(type, value_normalized)`` do ContactPoint enxerga todos. É exatamente essa
    diferença que produz o ``IntegrityError`` daqui — e sem olhar para os
    inativos não há como saber por que a criação foi recusada.
    """
    from shopman.guestman.models import ContactPoint
    from shopman.utils.phone import normalize_phone

    normalized = normalize_phone(phone)
    if not normalized:
        return None

    contact = (
        ContactPoint.objects.select_related("customer")
        .filter(
            value_normalized=normalized,
            type__in=[ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP],
        )
        .order_by("-is_primary", "-is_verified", "-updated_at")
        .first()
    )
    return contact.customer if contact else None


def ensure_customer(intent, *, order_ref: str = "") -> None:
    """Ensure the checkout customer exists in Guestman.

    ⚠️ O ``except IntegrityError: pass`` que morava aqui era uma falha SILENCIOSA
    no ponto mais caro do fluxo: o pedido fechava sem vínculo com cadastro, e o
    cliente perdia histórico, fidelidade e rastreio sem que ninguém — nem ele,
    nem a padaria — soubesse. O pedido já foi commitado quando chegamos aqui, e é
    por isso que esta função não levanta para a superfície; mas ela não pode
    calar.

    A colisão tem duas causas, e só uma delas é problema:

    - **O telefone já é de um cadastro ATIVO** (corrida entre dois checkouts do
      mesmo número, ou o cadastro nasceu entre a busca e a escrita). O dono é o
      cadastro certo: adotamos, e o vínculo existe. Não há nada a alertar.
    - **O telefone está preso num cadastro DESATIVADO**, ou não há dono nenhum
      (a colisão foi de outra coluna). Aí o pedido fica mesmo sem cadastro, e
      isso vira alerta de operador — dado que não entrou é trabalho a fazer, não
      linha de log.
    """
    import uuid as uuid_lib

    from django.db import IntegrityError
    from shopman.guestman.services import customer as customer_service

    customer_obj = customer_service.get_by_phone(intent.customer_phone)
    if customer_obj:
        _fill_missing_first_name(customer_obj, intent.customer_name)
        return

    try:
        customer_service.create(
            ref=f"WEB-{str(uuid_lib.uuid4())[:8].upper()}",
            first_name=intent.customer_name,
            phone=intent.customer_phone,
        )
        return
    except IntegrityError:
        logger.info("checkout.ensure_customer_conflict order=%s", order_ref, exc_info=True)

    owner = _phone_owner_any_state(intent.customer_phone)
    if owner is not None and owner.is_active:
        # Vincular ao dono existente é melhor do que descartar: é o mesmo
        # telefone, que nesta loja É a identidade do cliente.
        _fill_missing_first_name(owner, intent.customer_name)
        return

    from shopman.shop.services.observability import create_operator_alert

    motivo = (
        "o telefone está preso num cadastro desativado"
        if owner is not None
        else "o cadastro não pôde ser criado"
    )
    create_operator_alert(
        type="checkout_customer_unlinked",
        severity="warning",
        message=(
            f"Pedido {order_ref or '(sem ref)'} fechou sem vínculo com cadastro: {motivo}. "
            "O cliente fica sem histórico, fidelidade e rastreio até alguém ligar os dois."
        ),
        order_ref=order_ref,
        dedupe_key=f"checkout_customer_unlinked:{order_ref}",
    )


@transaction.atomic
def persist_new_address(intent) -> None:
    """Persist a newly typed delivery address to the checkout customer."""
    if intent.fulfillment_type != "delivery":
        return
    if intent.saved_address_id:
        return
    if not intent.delivery_address:
        return

    from shopman.guestman.services import address as address_service
    from shopman.guestman.services import customer as customer_service

    customer_obj = customer_service.get_by_phone(intent.customer_phone)
    if not customer_obj:
        return

    from shopman.guestman.models import Customer
    Customer.objects.select_for_update().get(pk=customer_obj.pk)
    label = getattr(intent, "address_label", {}) or {}
    existing = next((a for a in address_service.addresses(customer_obj.ref) if a.formatted_address == intent.delivery_address), None)
    if existing is not None:
        if label:
            address_service.update_address(customer_obj.ref, existing.pk, label=label["key"], label_custom=label.get("custom", ""))
        return

    structured = intent.delivery_address_structured or {}

    lat = structured.get("latitude")
    lng = structured.get("longitude")
    coordinates = (float(lat), float(lng)) if lat and lng else None

    components = {
        "street_number": structured.get("street_number", ""),
        "route": structured.get("route", ""),
        "neighborhood": structured.get("neighborhood", ""),
        "city": structured.get("city", ""),
        "state_code": structured.get("state_code", ""),
        "postal_code": structured.get("postal_code", ""),
    }

    is_first = not address_service.has_any_address(customer_obj.ref)

    address_service.add_address(
        customer_ref=customer_obj.ref,
        label=label.get("key", "other"),
        label_custom=label.get("custom", "Entrega"),
        formatted_address=intent.delivery_address,
        place_id=structured.get("place_id") or None,
        components=components,
        coordinates=coordinates,
        complement=structured.get("complement", ""),
        delivery_instructions=structured.get("delivery_instructions", ""),
        is_default=is_first,
    )


def save_defaults(intent, *, order_ref: str, enabled: bool) -> None:
    """Persist explicit checkout defaults when the customer opts in."""
    if not enabled:
        return

    from shopman.guestman.services import customer as customer_service

    from shopman.shop.services.checkout_defaults import CheckoutDefaultsService

    customer_obj = customer_service.get_by_phone(intent.customer_phone)
    if not customer_obj:
        return

    defaults_data: dict = {
        "fulfillment_type": intent.fulfillment_type,
        "payment_method": intent.payment_method,
    }
    if intent.fulfillment_type == "delivery":
        if intent.saved_address_id:
            defaults_data["delivery_address_id"] = intent.saved_address_id
        elif intent.delivery_address:
            from shopman.guestman.services import address as address_service
            from shopman.orderman.exceptions import DirectiveTransientError

            saved = next((a for a in address_service.addresses(customer_obj.ref) if a.formatted_address == intent.delivery_address), None)
            if saved is None:
                raise DirectiveTransientError("Address persistence pending; dependent defaults deferred")
            defaults_data["delivery_address_id"] = str(saved.pk)
        if intent.delivery_time_slot:
            defaults_data["delivery_time_slot"] = intent.delivery_time_slot
    if intent.notes:
        defaults_data["order_notes"] = intent.notes

    CheckoutDefaultsService.save_defaults(
        customer_ref=customer_obj.ref,
        channel_ref=intent.channel_ref,
        data=defaults_data,
        source=f"order:{order_ref}",
    )


def _post_commit_intent(data: dict, channel_ref: str) -> SimpleNamespace:
    """Lightweight intent built from checkout data for the post-commit side effects.

    Shop never imports the storefront ``CheckoutIntent`` (dependency rule); the side
    effects only read attributes, so a namespace from ``data`` is enough.
    """
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    return SimpleNamespace(
        customer_phone=customer.get("phone") or "",
        customer_name=customer.get("name") or "",
        fulfillment_type=data.get("fulfillment_type", "pickup"),
        saved_address_id=data.get("saved_address_id"),
        address_label=data.get("address_label") or {},
        delivery_address=data.get("delivery_address"),
        delivery_address_structured=data.get("delivery_address_structured"),
        payment_method=payment.get("method") or "",
        delivery_time_slot=data.get("delivery_time_slot"),
        notes=data.get("order_notes"),
        channel_ref=channel_ref,
    )


def recover_convenience_effect(message) -> None:
    from shopman.orderman.models import Directive, Order

    from shopman.shop.services.remote_mutations import run_idempotent_mutation
    def execute():
        order = Order.objects.get(ref=message.payload["order_ref"])
        sealed_data = (order.snapshot or {}).get("data") or {}
        intent = _post_commit_intent(sealed_data, order.channel_ref)
        effect = message.payload["effect"]
        if intent.customer_phone:
            from shopman.guestman.services import customer as customers
            from shopman.orderman.exceptions import DirectiveTransientError
            if effect == "session_takeover":
                sessions.finalize_phone_handle(
                    session_key=order.session_key,
                    channel_ref=order.channel_ref,
                    phone=intent.customer_phone,
                    superseded_session_keys=tuple(message.payload.get("superseded_session_keys") or ()),
                    expected_customer_ref=str(message.payload.get("expected_customer_ref") or ""),
                )
            elif effect != "customer" and customers.get_by_phone(intent.customer_phone) is None:
                raise DirectiveTransientError("Customer linkage pending; dependent convenience effect deferred")
            elif effect == "customer":
                ensure_customer(intent, order_ref=order.ref)
                if customers.get_by_phone(intent.customer_phone) is None:
                    raise DirectiveTransientError("Customer linkage pending")
            elif effect == "address":
                persist_new_address(intent)
            elif effect == "defaults":
                save_defaults(intent, order_ref=order.ref, enabled=bool(sealed_data.get("save_as_default", True)))
            else:
                raise ValueError("Invalid convenience effect")
        Directive.objects.filter(pk=message.pk).update(status="done", last_error="", error_code="")
        return {"complete": True}, 200
    run_idempotent_mutation(scope="checkout:convenience", key=message.dedupe_key, execute=execute, local_atomic=True)


def _apply_post_commit_side_effects(data: dict, channel_ref: str, *, order_ref: str) -> list[str]:
    from shopman.orderman.models import Directive

    from shopman.shop import directives
    from shopman.shop.services.observability import create_operator_alert
    if not _post_commit_intent(data, channel_ref).customer_phone:
        return []
    pending = []
    for effect in ("session_takeover", "customer", "address", "defaults"):
        key = f"checkout:{order_ref}:{effect}:v1"
        message = Directive.objects.filter(topic=directives.CHECKOUT_CONVENIENCE, dedupe_key=key).first()
        if message is None and effect != "session_takeover":
            message = directives.create_persistently_deduped(
                directives.CHECKOUT_CONVENIENCE,
                payload={"order_ref": order_ref, "effect": effect},
                dedupe_key=key,
                receipt_scope="checkout:convenience:queued",
            )
            if message is None:
                message = Directive.objects.filter(
                    topic=directives.CHECKOUT_CONVENIENCE,
                    dedupe_key=key,
                ).first()
        if message is None or message.status == "done":
            continue
        try:
            recover_convenience_effect(message)
        except Exception:
            pending.append(effect)
            logger.warning("checkout.convenience_pending effect=%s", effect, exc_info=True)
            create_operator_alert(type="checkout_convenience_pending", severity="warning", message=(
                    f"O pedido {order_ref} entrou, mas o cadastro do cliente (vínculo, endereço ou "
                    "preferências que ele pediu para guardar) ainda não foi atualizado. O pedido segue "
                    "normal."
                ), order_ref=order_ref, dedupe_key=key)
    return pending


def recover_post_commit_side_effects(order_ref: str) -> list[str]:
    """Recreate missing convenience directives from the sealed order snapshot."""
    from shopman.orderman.models import Order

    order = Order.objects.get(ref=order_ref)
    sealed_data = (order.snapshot or {}).get("data") or {}
    return _apply_post_commit_side_effects(
        sealed_data,
        order.channel_ref,
        order_ref=order.ref,
    )


def queue_post_commit_effects(order) -> None:
    """Seal checkout effects and the exact prior-cart cut with the Order."""
    from django.db import models
    from shopman.orderman.models import Session

    data = (order.snapshot or {}).get("data") or {}
    intent = _post_commit_intent(data, order.channel_ref)
    if not intent.customer_phone:
        return
    from shopman.shop import directives

    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    customer_ref = str(data.get("customer_ref") or customer.get("ref") or "")
    target = Session.objects.filter(
        channel_ref=order.channel_ref,
        session_key=order.session_key,
    ).values("handle_ref").first()
    effects: list[tuple[str, dict]] = []
    if target is not None and not target["handle_ref"]:
        same_owner = models.Q(handle_type="phone", handle_ref=intent.customer_phone)
        if customer_ref:
            same_owner |= models.Q(data__customer__ref=customer_ref)
        superseded = list(
            Session.objects.filter(channel_ref=order.channel_ref, state="open")
            .filter(same_owner)
            .exclude(session_key=order.session_key)
            .order_by("pk")
            .values_list("session_key", flat=True)
        )
        effects.append(
            (
                "session_takeover",
                {
                    "superseded_session_keys": superseded,
                    "expected_customer_ref": customer_ref,
                },
            )
        )
    effects.extend((effect, {}) for effect in ("customer", "address", "defaults"))
    for effect, extra_payload in effects:
        directives.create_persistently_deduped(
            directives.CHECKOUT_CONVENIENCE,
            payload={"order_ref": order.ref, "effect": effect, **extra_payload},
            dedupe_key=f"checkout:{order.ref}:{effect}:v1",
            receipt_scope="checkout:convenience:queued",
        )


def recover_committed_checkout(
    *, session_key: str, channel_ref: str, idempotency_key: str
) -> CheckoutResult | None:
    """Recover the canonical inner receipt before a surface inspects the cart."""
    if not session_key:
        return None
    completed = CommitService.completed_response(session_key, channel_ref, idempotency_key)
    if completed is None:
        return None
    result = _checkout_result(completed)
    pending = recover_post_commit_side_effects(result.order_ref)
    return replace(result, convenience_pending=tuple(pending or ()))



def checkout_receipt_scope(*, browser_session: str, principal: str, cart_session: str, key: str) -> str:
    from shopman.orderman.models import IdempotencyKey

    from shopman.shop.services.remote_mutations import RemoteMutationConflict, fingerprint
    prefix = f"co:{fingerprint([browser_session, principal])[:32]}:"
    scope = prefix + fingerprint(cart_session)[:24]
    existing = IdempotencyKey.objects.filter(scope__startswith=prefix, key=key).first()
    if existing:
        if cart_session and existing.scope != scope:
            raise RemoteMutationConflict("Esta tentativa pertence a outra sacola. Confira o pedido já confirmado antes de continuar.")
        return existing.scope
    return scope


def recover_checkout_response(*, browser_session: str, principal: str, key: str = "") -> dict | None:
    from shopman.orderman.models import IdempotencyKey

    from shopman.shop.services.remote_mutations import fingerprint
    prefix = f"co:{fingerprint([browser_session, principal])[:32]}:"
    receipts = IdempotencyKey.objects.filter(scope__startswith=prefix, status="done", response_code=201)
    if key:
        receipts = receipts.filter(key=key)
    receipt = receipts.order_by("-created_at").first()
    if receipt and receipt.response_body:
        body = dict(receipt.response_body)
        body["convenience_pending"] = list(convenience_pending(body["order_ref"]))
        return body
    return None


def order_has_payment_error(order_ref: str) -> bool:
    from shopman.orderman.models import Order

    order = Order.objects.get(ref=order_ref)
    return bool((order.data or {}).get("payment", {}).get("error"))


def get_open_cart_session(*, session_key: str, channel_ref: str):
    from shopman.orderman.models import Session

    return Session.objects.get(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    )


def simulate_ifood_order(cart_session):
    from shopman.shop.services import ifood_ingest
    from shopman.shop.services.ifood_simulation import session_to_ifood_payload

    payload = session_to_ifood_payload(cart_session)
    return ifood_ingest.ingest(payload)


def close_cart_session(cart_session) -> None:
    cart_session.state = "closed"
    cart_session.save(update_fields=["state", "updated_at"])


def _build_ops_from_data(data: dict) -> list[dict]:
    """Convert checkout data dict into Orderman session operations."""
    ops = []
    data_fields = [
        "customer",
        "save_as_default",
        "address_label",
        "fulfillment_type",
        "delivery_address",
        "saved_address_id",
        "delivery_address_structured",
        "delivery_date",
        "delivery_time_slot",
        "order_notes",
        "payment",
        # CPF/CNPJ PEDIDO para a nota (``{tax_id}``) — a loja o manda na entrega.
        "fiscal",
        "loyalty",
        "manual_discount",
        "stock_check_unavailable",
        "is_gift",
        "recipient",
        "gift_message",
        "gift_hide_values",
        # Versão dos documentos legais vigente no checkout. Fica em `session.data`,
        # que o commit copia inteira para `Order.snapshot["data"]` (selado). Não
        # entra na lista de `order.data` do CommitService: evidência não se edita.
        "legal",
    ]
    for field in data_fields:
        if field in data:
            ops.append({"op": "set_data", "path": field, "value": data[field]})
    return ops
