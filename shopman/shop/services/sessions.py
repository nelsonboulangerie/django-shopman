"""Order session orchestration facade.

Surfaces should use this module instead of calling Orderman write services
directly. Read projections may still query kernel models when that is the
clearest representation boundary.
"""

from __future__ import annotations

from django.db import models, transaction
from shopman.orderman.exceptions import SessionError
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Session
from shopman.orderman.services.commit import CommitResult, CommitService
from shopman.orderman.services.modify import ModifyService
from shopman.utils.phone import normalize_phone

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel


def new_session_key() -> str:
    """Return a canonical Orderman session key."""
    return generate_session_key()


def new_idempotency_key() -> str:
    """Return a canonical Orderman idempotency key."""
    return generate_idempotency_key()


def create_session(
    channel_ref: str,
    *,
    handle_type: str | None = None,
    handle_ref: str | None = None,
    data: dict | None = None,
    state: str = "open",
) -> Session:
    """Create an open Orderman session with resolved channel policies."""
    channel = Channel.objects.get(ref=channel_ref)
    config = ChannelConfig.for_channel(channel)
    return Session.objects.create(
        session_key=new_session_key(),
        channel_ref=channel.ref,
        state=state,
        pricing_policy=config.pricing.policy,
        edit_policy=config.editing.policy,
        handle_type=handle_type,
        handle_ref=handle_ref,
        data=data or {},
    )


def modify_session(
    *,
    session_key: str,
    channel_ref: str,
    ops: list[dict],
    ctx: dict | None = None,
    channel_config: dict | None = None,
) -> Session:
    """Apply canonical session operations through Orderman."""
    return ModifyService.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=ops,
        ctx=ctx,
        channel_config=channel_config,
    )


def move_session_lines(
    *,
    from_session_key: str,
    to_session_key: str,
    channel_ref: str,
    line_ids: list[str],
) -> tuple[Session, Session]:
    """Move lines verbatim between two open sessions (freezes price).

    Thin facade over the kernel integrity op used for comanda
    transfer/split/merge.
    """
    return ModifyService.move_lines(
        from_session_key=from_session_key,
        to_session_key=to_session_key,
        channel_ref=channel_ref,
        line_ids=line_ids,
    )


def commit_session(
    *,
    session_key: str,
    channel_ref: str,
    idempotency_key: str,
    ctx: dict | None = None,
    channel_config: dict | None = None,
) -> CommitResult:
    """Commit a session through the canonical Orderman service."""
    return CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idempotency_key,
        ctx=ctx,
        channel_config=channel_config,
    )


@transaction.atomic
def assign_phone_handle(
    *,
    session_key: str,
    channel_ref: str,
    phone: str,
    abandon_existing: bool = True,
) -> None:
    """Attach an open session to a phone handle.

    When ``abandon_existing`` is true, older open sessions for the same phone
    and channel are abandoned so the phone has a single active cart/session.
    """
    if not phone:
        return
    phone = normalize_phone(phone) or phone

    # Resolution is only a hint.  Account deletion may win after this read, so
    # acquire the canonical Customer fence and re-resolve the phone before any
    # Session lock (global order: Customer -> Session).
    from shopman.guestman.services import customer as customer_service

    from shopman.shop.services import account as account_service

    customer_hint = customer_service.get_by_phone(phone)
    if customer_hint is not None:
        try:
            locked_customer = account_service.lock_active_customer(customer_uuid=customer_hint.uuid)
        except account_service.AccountUnavailable as exc:
            raise SessionError(
                code="customer_inactive",
                message="O titular desta sessão não está mais ativo.",
            ) from exc
        current = customer_service.get_by_phone(phone)
        if current is None or current.pk != locked_customer.pk:
            raise SessionError(
                code="customer_identity_changed",
                message="A identidade do titular mudou; confirme novamente.",
            )

    sessions = list(
        Session.objects.select_for_update()
        .filter(channel_ref=channel_ref, state="open")
        .filter(
            models.Q(session_key=session_key)
            | models.Q(handle_type="phone", handle_ref=phone)
        )
        .order_by("pk")
    )
    session = next((candidate for candidate in sessions if candidate.session_key == session_key), None)
    if session is None:
        return
    if session.is_anonymized:
        raise SessionError(
            code="session_anonymized",
            message="Uma sessão anonimizada não pode recuperar sua identidade.",
        )
    if abandon_existing:
        older = [
            candidate
            for candidate in sessions
            if candidate.pk != session.pk
            and candidate.handle_type == "phone"
            and candidate.handle_ref == phone
        ]
        older_keys = [candidate.session_key for candidate in older]
        if older:
            Session.objects.filter(pk__in=[candidate.pk for candidate in older]).update(
                state="abandoned"
            )
        # Sessão abandonada devolve as reservas — sem isso, os holds planejados
        # (eternos) da sacola antiga seguram a fornada do dia contra o próprio
        # cliente (WP-A/WP-B do AVAILABILITY-SALE-PRODUCTION-PLAN).
        from shopman.shop.services.availability import release_session_holds

        for key in older_keys:
            release_session_holds(key)
    session.handle_type = "phone"
    session.handle_ref = phone
    session.save(update_fields=["handle_type", "handle_ref"])


@transaction.atomic
def assign_customer(
    *,
    session_key: str,
    channel_ref: str,
    customer_uuid,
) -> bool:
    """Persist canonical customer pricing identity under Customer -> Session locks."""
    from shopman.shop.services import account as account_service

    try:
        customer = account_service.lock_active_customer(customer_uuid=customer_uuid)
    except account_service.AccountUnavailable:
        return False

    session = (
        Session.objects.select_for_update()
        .filter(session_key=session_key, channel_ref=channel_ref, state="open")
        .first()
    )
    if session is None:
        return False
    session.assert_accepts_personal_data("customer")

    existing = (session.data or {}).get("customer") or {}
    merged = dict(existing)
    merged["ref"] = customer.ref
    if customer.price_tier_id:
        merged["price_tier"] = customer.price_tier.ref
    else:
        merged.pop("price_tier", None)
    if merged == existing:
        return False
    data = dict(session.data or {})
    data["customer"] = merged
    session.data = data
    session.save(update_fields=["data"])
    return True


@transaction.atomic
def assign_handle(
    *,
    session_key: str,
    channel_ref: str,
    handle_type: str,
    handle_ref: str,
) -> None:
    """Attach a generic handle to an open session."""
    if handle_type in {"customer", "phone", "whatsapp"} and handle_ref:
        from shopman.guestman.models import Customer
        from shopman.guestman.services import customer as customer_service

        from shopman.shop.services import account as account_service

        customer_hint = None
        if handle_type == "customer":
            customer_hint = Customer.objects.filter(ref=handle_ref).only("uuid").first()
        else:
            customer_hint = customer_service.get_by_phone(handle_ref)
        if customer_hint is not None:
            try:
                locked_customer = account_service.lock_active_customer(
                    customer_uuid=customer_hint.uuid
                )
            except account_service.AccountUnavailable as exc:
                raise SessionError(
                    code="customer_inactive",
                    message="O titular desta sessão não está mais ativo.",
                ) from exc
            if handle_type == "customer" and locked_customer.ref != handle_ref:
                raise SessionError(
                    code="customer_identity_changed",
                    message="A identidade do titular mudou; confirme novamente.",
                )
            if handle_type in {"phone", "whatsapp"}:
                current = customer_service.get_by_phone(handle_ref)
                if current is None or current.pk != locked_customer.pk:
                    raise SessionError(
                        code="customer_identity_changed",
                        message="A identidade do titular mudou; confirme novamente.",
                    )

    session = Session.objects.select_for_update().filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).first()
    if session is None:
        return
    if session.is_anonymized:
        raise SessionError(
            code="session_anonymized",
            message="Uma sessão anonimizada não pode recuperar sua identidade.",
        )
    session.handle_type = handle_type
    session.handle_ref = handle_ref
    session.save(update_fields=["handle_type", "handle_ref"])


def abandon_session(*, session_key: str, channel_ref: str) -> bool:
    """Mark an open session as abandoned and release its stock holds."""
    updated = Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).update(state="abandoned")
    if updated:
        from shopman.shop.services.availability import release_session_holds

        release_session_holds(session_key)
    return bool(updated)
