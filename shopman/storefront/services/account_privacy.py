"""Orquestra direitos de dados com recibo durável, lock e idempotência."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.shop.models import (
    PrivacyRequestOperation,
    PrivacyRequestReceipt,
    PrivacyRequestState,
)

_CONTRACT_VERSION = "account-privacy.v1"
_FAILED_RETENTION = timedelta(days=90)
_COMPLETED_RETENTION = timedelta(days=365 * 5)
_STALE_IN_PROGRESS = timedelta(minutes=10)


class PrivacyRequestError(Exception):
    code = "privacy_request_failed"


class InvalidIdempotencyKey(PrivacyRequestError):
    code = "invalid_idempotency_key"


class PrivacyRequestConflict(PrivacyRequestError):
    code = "idempotency_conflict"


class PrivacyRequestInProgress(PrivacyRequestError):
    code = "privacy_request_in_progress"


class PrivacyReceiptKeyUnavailable(PrivacyRequestError):
    code = "privacy_receipt_key_unavailable"


class AccountDeletionBlocked(PrivacyRequestError):
    code = "account_deletion_blocked"

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class DeletionOutcome:
    receipt_ref: str
    replayed: bool


def delete_account(*, customer, idempotency_key: str, authorized_at) -> DeletionOutcome:
    """Anonimiza uma conta uma única vez ou reproduz seu recibo concluído.

    O recibo nasce em transação própria para sobreviver a qualquer rollback da
    exclusão. A mutação inteira, inclusive o estado concluído do recibo, fecha
    em uma segunda transação atômica.
    """

    normalized_key = _validate_idempotency_key(idempotency_key)
    request_material = json.dumps(
        {"acknowledged": True, "contract": _CONTRACT_VERSION, "operation": "deletion"},
        sort_keys=True,
        separators=(",", ":"),
    )
    key_version, key = _key_for_idempotency(
        PrivacyRequestOperation.DELETION,
        normalized_key,
    )
    subject_digest = _digest(
        "subject",
        str(customer.uuid),
        key_version=key_version,
        key=key,
    )
    idempotency_digest = _digest(
        "idempotency",
        normalized_key,
        key_version=key_version,
        key=key,
    )
    request_digest = _digest(
        "request",
        request_material,
        key_version=key_version,
        key=key,
    )
    receipt, replayed = _acquire_receipt(
        operation=PrivacyRequestOperation.DELETION,
        subject_digest=subject_digest,
        idempotency_digest=idempotency_digest,
        request_digest=request_digest,
        authorized_at=authorized_at,
        key_version=key_version,
    )
    if replayed:
        return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=True)

    try:
        with transaction.atomic():
            receipt = PrivacyRequestReceipt.objects.select_for_update().get(pk=receipt.pk)
            if receipt.state == PrivacyRequestState.COMPLETED:
                return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=True)

            from shopman.shop.services import account as account_service

            locked_customer = account_service.lock_customer_for_privacy(customer.pk)
            if not locked_customer.is_active:
                previous = (
                    PrivacyRequestReceipt.objects.filter(
                        operation=PrivacyRequestOperation.DELETION,
                        subject_digest__in=_all_digests("subject", str(customer.uuid)),
                        state=PrivacyRequestState.COMPLETED,
                    )
                    .exclude(pk=receipt.pk)
                    .first()
                )
                if previous is None:
                    raise AccountDeletionBlocked("account_already_inactive")
                now = timezone.now()
                receipt.state = PrivacyRequestState.COMPLETED
                receipt.completed_at = now
                receipt.failure_stage = ""
                receipt.failure_code = ""
                receipt.outcome_counts = {"accounts": 0, "already_deleted": 1}
                receipt.retention_until = now + _COMPLETED_RETENTION
                receipt.save(
                    update_fields=[
                        "state",
                        "completed_at",
                        "failure_stage",
                        "failure_code",
                        "outcome_counts",
                        "retention_until",
                        "updated_at",
                    ]
                )
                return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=True)
            blocker = _deletion_blocker(locked_customer)
            if blocker:
                raise AccountDeletionBlocked(blocker)

            _settle_storefront_records(locked_customer)
            account_service.anonymize_customer(locked_customer)
            now = timezone.now()
            receipt.state = PrivacyRequestState.COMPLETED
            receipt.completed_at = now
            receipt.failure_stage = ""
            receipt.failure_code = ""
            receipt.outcome_counts = {"accounts": 1}
            receipt.retention_until = now + _COMPLETED_RETENTION
            receipt.save(
                update_fields=[
                    "state",
                    "completed_at",
                    "failure_stage",
                    "failure_code",
                    "outcome_counts",
                    "retention_until",
                    "updated_at",
                ]
            )
    except AccountDeletionBlocked:
        _mark_failed(receipt.pk, stage="precondition", code="account_deletion_blocked")
        raise
    except Exception:
        _mark_failed(receipt.pk, stage="anonymization", code="account_deletion_incomplete")
        _alert_failed_receipt(receipt.ref)
        raise

    return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=False)


def begin_export(
    *,
    customer_uuid,
    authorized_at,
) -> PrivacyRequestReceipt:
    """Abre evidência durável antes de qualquer leitura/serialização do artefato."""

    now = timezone.now()
    nonce = str(uuid.uuid4())
    key_version, key = _current_privacy_key()
    return PrivacyRequestReceipt.objects.create(
        operation=PrivacyRequestOperation.EXPORT,
        state=PrivacyRequestState.IN_PROGRESS,
        key_version=key_version,
        subject_digest=_digest(
            "subject",
            str(customer_uuid),
            key_version=key_version,
            key=key,
        ),
        idempotency_digest=_digest(
            "idempotency",
            nonce,
            key_version=key_version,
            key=key,
        ),
        request_digest=_digest(
            "request",
            _CONTRACT_VERSION + ":export",
            key_version=key_version,
            key=key,
        ),
        authorization_method="otp_step_up",
        authorized_at=authorized_at,
        retention_until=now + _FAILED_RETENTION,
    )


def complete_export(receipt_pk: int, *, counts: dict[str, int]) -> PrivacyRequestReceipt:
    now = timezone.now()
    with transaction.atomic():
        receipt = PrivacyRequestReceipt.objects.select_for_update().get(pk=receipt_pk)
        receipt.state = PrivacyRequestState.COMPLETED
        receipt.completed_at = now
        receipt.failure_stage = ""
        receipt.failure_code = ""
        receipt.outcome_counts = _safe_counts(counts)
        receipt.retention_until = now + _COMPLETED_RETENTION
        receipt.save(
            update_fields=[
                "state",
                "completed_at",
                "failure_stage",
                "failure_code",
                "outcome_counts",
                "retention_until",
                "updated_at",
            ]
        )
    return receipt


def fail_export(receipt_pk: int, *, stage: str = "artifact") -> None:
    _mark_failed(receipt_pk, stage=stage, code="account_export_incomplete")


def _acquire_receipt(
    *,
    operation: str,
    subject_digest: str,
    idempotency_digest: str,
    request_digest: str,
    authorized_at,
    key_version: int,
) -> tuple[PrivacyRequestReceipt, bool]:
    now = timezone.now()
    defaults = {
        "request_digest": request_digest,
        "key_version": key_version,
        "authorization_method": "otp_step_up",
        "authorized_at": authorized_at,
        "retention_until": now + _FAILED_RETENTION,
    }
    try:
        with transaction.atomic():
            receipt, created = PrivacyRequestReceipt.objects.get_or_create(
                operation=operation,
                subject_digest=subject_digest,
                idempotency_digest=idempotency_digest,
                defaults=defaults,
            )
    except IntegrityError:
        receipt = PrivacyRequestReceipt.objects.get(
            operation=operation,
            idempotency_digest=idempotency_digest,
        )
        if not hmac.compare_digest(receipt.subject_digest, subject_digest):
            raise PrivacyRequestConflict("idempotency_key_owned_by_another_subject") from None
        created = False

    if created:
        return receipt, False
    if not hmac.compare_digest(receipt.request_digest, request_digest):
        raise PrivacyRequestConflict("request_digest_mismatch")
    if receipt.state == PrivacyRequestState.COMPLETED:
        return receipt, True

    with transaction.atomic():
        receipt = PrivacyRequestReceipt.objects.select_for_update().get(pk=receipt.pk)
        if receipt.state == PrivacyRequestState.COMPLETED:
            return receipt, True
        if receipt.state == PrivacyRequestState.IN_PROGRESS and receipt.updated_at >= now - _STALE_IN_PROGRESS:
            raise PrivacyRequestInProgress("request_already_running")
        receipt.state = PrivacyRequestState.IN_PROGRESS
        receipt.completed_at = None
        receipt.failure_stage = ""
        receipt.failure_code = ""
        receipt.attempt_count += 1
        receipt.started_at = now
        receipt.save(
            update_fields=[
                "state",
                "completed_at",
                "failure_stage",
                "failure_code",
                "attempt_count",
                "started_at",
                "updated_at",
            ]
        )
    return receipt, False


def replay_completed_deletion(idempotency_key: str) -> DeletionOutcome | None:
    """Consulta somente um recibo concluído; nunca inicia ou retoma exclusão."""

    normalized_key = _validate_idempotency_key(idempotency_key)
    digests = _all_digests("idempotency", normalized_key)
    receipt = (
        PrivacyRequestReceipt.objects.filter(
            operation=PrivacyRequestOperation.DELETION,
            idempotency_digest__in=digests,
            state=PrivacyRequestState.COMPLETED,
        )
        .order_by("-started_at", "-pk")
        .first()
    )
    if receipt is None:
        return None
    return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=True)


def _mark_failed(receipt_pk: int, *, stage: str, code: str) -> None:
    now = timezone.now()
    with transaction.atomic():
        receipt = PrivacyRequestReceipt.objects.select_for_update().get(pk=receipt_pk)
        if receipt.state == PrivacyRequestState.COMPLETED:
            return
        receipt.state = PrivacyRequestState.FAILED
        receipt.completed_at = now
        receipt.failure_stage = stage
        receipt.failure_code = code
        receipt.outcome_counts = {}
        receipt.retention_until = now + _FAILED_RETENTION
        receipt.save(
            update_fields=[
                "state",
                "completed_at",
                "failure_stage",
                "failure_code",
                "outcome_counts",
                "retention_until",
                "updated_at",
            ]
        )


def _settle_storefront_records(customer) -> None:
    """Revoga filas futuras e retém somente prova técnica não identificável."""

    from django.db.models import Q

    from shopman.storefront.models import (
        CustomerFavorite,
        StockAlertDelivery,
        StockAlertSubscription,
    )
    from shopman.storefront.services.stock_alerts import _revocation_hash

    phone = customer.phone or ""
    query = Q(customer_ref=customer.ref)
    if phone:
        query |= Q(customer_ref="", contact_phone=phone)
    subscriptions = list(StockAlertSubscription.objects.select_for_update().filter(query).order_by("pk"))
    subscription_ids = [subscription.pk for subscription in subscriptions]
    if (
        subscription_ids
        and StockAlertDelivery.objects.filter(
            subscription_id__in=subscription_ids,
            status=StockAlertDelivery.Status.CLAIMED,
        ).exists()
    ):
        raise AccountDeletionBlocked("stock_alert_delivery_in_flight")

    now = timezone.now()
    if subscription_ids:
        StockAlertDelivery.objects.filter(
            subscription_id__in=subscription_ids,
            status__in=(
                StockAlertDelivery.Status.QUEUED,
                StockAlertDelivery.Status.RETRYABLE,
            ),
        ).update(
            status=StockAlertDelivery.Status.SUPPRESSED,
            claimed_at=None,
            last_error_code="subject_deleted",
            updated_at=now,
        )
        for subscription in subscriptions:
            reason = "subject_deleted"
            revoked_at = subscription.revoked_at or now
            revocation_hash = subscription.revocation_evidence_hash or _revocation_hash(
                subscription.ref,
                revoked_at,
                reason,
            )
            StockAlertSubscription.objects.filter(pk=subscription.pk).update(
                customer_ref="",
                contact_phone="",
                target_key=_digest("stock-alert-target", str(subscription.ref)),
                disclosure_text="",
                revoked_at=revoked_at,
                revoke_reason=reason,
                revocation_evidence_hash=revocation_hash,
                dispatch_claimed_at=None,
            )

    CustomerFavorite.objects.filter(customer_ref=customer.ref).delete()


def _deletion_blocker(customer) -> str:
    from shopman.shop.models import ConversationMessage, DeliveryTarget, OutboundAttempt
    from shopman.shop.services import account as account_service

    order_blocker = account_service.privacy_order_deletion_blocker(
        customer.ref,
        customer.phone or "",
    )
    if order_blocker:
        return order_blocker
    conversations = account_service._customer_conversations(  # noqa: SLF001
        customer.ref,
        customer.phone or "",
    )
    messages = ConversationMessage.objects.filter(conversation__in=conversations)
    if OutboundAttempt.objects.filter(
        message__in=messages,
        state=OutboundAttempt.State.EXECUTING,
    ).exists():
        return "conversation_delivery_in_flight"
    if DeliveryTarget.objects.filter(
        member__customer=customer,
        state=DeliveryTarget.State.SENDING,
    ).exists():
        return "marketing_delivery_in_flight"
    return ""


def _alert_failed_receipt(receipt_ref) -> None:
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type="account_deletion_incomplete",
        severity="critical",
        message=f"Exclusão de conta incompleta. Recibo: {receipt_ref}.",
        dedupe_key=f"privacy-deletion:{receipt_ref}",
    )


def _validate_idempotency_key(value: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = uuid.UUID(raw)
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidIdempotencyKey("uuid_v4_required") from exc
    if parsed.version != 4 or str(parsed) != raw.lower():
        raise InvalidIdempotencyKey("uuid_v4_required")
    return str(parsed)


def _key_for_idempotency(operation: str, idempotency_key: str) -> tuple[int, bytes]:
    keys = _privacy_hmac_keys()
    digests = [
        _digest(
            "idempotency",
            idempotency_key,
            key_version=version,
            key=key,
        )
        for version, key in keys.items()
    ]
    existing = (
        PrivacyRequestReceipt.objects.filter(
            operation=operation,
            idempotency_digest__in=digests,
        )
        .order_by("-started_at", "-pk")
        .first()
    )
    if existing is None:
        return _current_privacy_key(keys)
    key = keys.get(existing.key_version)
    if key is None:
        raise PrivacyReceiptKeyUnavailable("receipt_key_version_not_configured")
    return existing.key_version, key


def _all_digests(purpose: str, value: str) -> list[str]:
    return [_digest(purpose, value, key_version=version, key=key) for version, key in _privacy_hmac_keys().items()]


def _current_privacy_key(keys: dict[int, bytes] | None = None) -> tuple[int, bytes]:
    resolved = keys or _privacy_hmac_keys()
    version = int(getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION", 1))
    key = resolved.get(version)
    if key is None:
        raise PrivacyReceiptKeyUnavailable("current_receipt_key_not_configured")
    return version, key


def _privacy_hmac_keys() -> dict[int, bytes]:
    raw_previous = getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_PREVIOUS_KEYS", {})
    if isinstance(raw_previous, str):
        try:
            raw_previous = json.loads(raw_previous or "{}")
        except (TypeError, ValueError) as exc:
            raise PrivacyReceiptKeyUnavailable("receipt_keyring_invalid") from exc
    if not isinstance(raw_previous, Mapping):
        raise PrivacyReceiptKeyUnavailable("receipt_keyring_invalid")

    keys: dict[int, bytes] = {}
    for raw_version, raw_key in raw_previous.items():
        try:
            version = int(raw_version)
        except (TypeError, ValueError) as exc:
            raise PrivacyReceiptKeyUnavailable("receipt_key_version_invalid") from exc
        key = str(raw_key or "").encode("utf-8")
        if version < 1 or len(key) < 32:
            raise PrivacyReceiptKeyUnavailable("receipt_key_invalid")
        keys[version] = key

    current_version = int(getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION", 1))
    current_key = str(getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY", "") or "").encode("utf-8")
    if current_version < 1 or len(current_key) < 32:
        raise PrivacyReceiptKeyUnavailable("current_receipt_key_invalid")
    previous_current = keys.get(current_version)
    if previous_current is not None and not hmac.compare_digest(
        previous_current,
        current_key,
    ):
        raise PrivacyReceiptKeyUnavailable("receipt_key_version_conflict")
    keys[current_version] = current_key
    return keys


def _digest(
    purpose: str,
    value: str,
    *,
    key_version: int | None = None,
    key: bytes | None = None,
) -> str:
    if key_version is None or key is None:
        key_version, key = _current_privacy_key()
    material = f"{_CONTRACT_VERSION}\0key:{key_version}\0{purpose}\0{value}".encode()
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def _safe_counts(values: dict[str, int]) -> dict[str, int]:
    return {
        str(key)[:48]: max(0, int(value))
        for key, value in values.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
