"""
AuthService - OTP code verification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.contrib.auth import login
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..conf import doorman_settings, get_adapter
from ..error_codes import ErrorCode
from ..exceptions import GateError
from ..gates import Gates
from ..models import VerificationCode
from ..protocols.customer import AuthCustomerInfo
from ..signals import verification_code_sent, verification_code_verified

if TYPE_CHECKING:
    from django.http import HttpRequest

    from ..senders import MessageSenderProtocol

logger = logging.getLogger("shopman.doorman.verification")


@dataclass
class CodeRequestResult:
    """Result of code request."""

    success: bool
    code_id: str | None = None
    expires_at: str | None = None
    delivery_method: str | None = None
    debug_code: str | None = None
    error: str | None = None
    error_code: ErrorCode | None = None


@dataclass
class VerifyResult:
    """Result of code verification."""

    success: bool
    customer: AuthCustomerInfo | None = None
    created_customer: bool = False
    error: str | None = None
    error_code: ErrorCode | None = None
    attempts_remaining: int | None = None


class AuthService:
    """
    OTP code verification service.

    Handles code generation, sending, and verification
    for login and contact verification flows.
    """

    # ===========================================
    # Request Code
    # ===========================================

    @classmethod
    def request_code(
        cls,
        target_value: str,
        purpose: str = VerificationCode.Purpose.LOGIN,
        delivery_method: str = VerificationCode.DeliveryMethod.WHATSAPP,
        ip_address: str | None = None,
        sender: MessageSenderProtocol | None = None,
        customer_id=None,
    ) -> CodeRequestResult:
        """
        Request a verification code.

        Args:
            target_value: Phone (E.164) or email
            purpose: Code purpose (login, verify_contact)
            delivery_method: How to send (whatsapp, sms, email)
            ip_address: Client IP for rate limiting
            sender: Custom sender (default from settings)

        Returns:
            CodeRequestResult with code_id and expiration
        """
        adapter = get_adapter()
        target_value = adapter.normalize_login_target(target_value)
        if not target_value:
            return CodeRequestResult(
                success=False,
                error="Invalid login target.",
                error_code=ErrorCode.INVALID_TARGET,
            )
        if purpose not in VerificationCode.Purpose.values:
            return CodeRequestResult(
                success=False,
                error="Invalid verification purpose.",
                error_code=ErrorCode.INVALID_INPUT,
            )
        if delivery_method not in VerificationCode.DeliveryMethod.values:
            return CodeRequestResult(
                success=False,
                error="Invalid delivery method.",
                error_code=ErrorCode.INVALID_INPUT,
            )
        if not adapter.is_login_allowed(target_value, delivery_method):
            return CodeRequestResult(
                success=False,
                error="Login not allowed for this target.",
                error_code=ErrorCode.ACCOUNT_INACTIVE,
            )

        # Phase A is deliberately durable: provider resolution can itself use
        # a durable privacy intent.  Committing the OTP first keeps all network
        # I/O outside database transactions and makes nested callers fail
        # loudly instead of pretending an inner savepoint was a real commit.
        with transaction.atomic(durable=True):
            if purpose == VerificationCode.Purpose.LOGIN and customer_id is None:
                customer_hint = adapter.resolve_customer(target_value)
                if customer_hint is not None:
                    customer_id = customer_hint.uuid
            if customer_id is not None:
                locked_customer = adapter.lock_active_customer_by_uuid(customer_id)
                target_is_current = (
                    purpose != VerificationCode.Purpose.LOGIN
                    or (
                        locked_customer is not None
                        and adapter.login_target_belongs_to_customer(
                            locked_customer,
                            target_value,
                        )
                    )
                )
                if locked_customer is None or not target_is_current:
                    return CodeRequestResult(
                        success=False,
                        error="Account inactive.",
                        error_code=ErrorCode.ACCOUNT_INACTIVE,
                    )
                customer_id = locked_customer.uuid

            # G9: Rate limit by target
            try:
                Gates.rate_limit(
                    key=target_value,
                    max_requests=doorman_settings.ACCESS_CODE_RATE_LIMIT_MAX,
                    window_minutes=doorman_settings.ACCESS_CODE_RATE_LIMIT_WINDOW_MINUTES,
                )
            except GateError:
                return CodeRequestResult(
                    success=False,
                    error="Too many attempts. Please wait a few minutes.",
                    error_code=ErrorCode.RATE_LIMIT,
                )

            # G11: Cooldown between code sends
            try:
                Gates.code_cooldown(
                    target_value=target_value,
                    cooldown_seconds=doorman_settings.ACCESS_CODE_COOLDOWN_SECONDS,
                )
            except GateError:
                return CodeRequestResult(
                    success=False,
                    error="Please wait before requesting a new code.",
                    error_code=ErrorCode.COOLDOWN,
                )

            # G10: Rate limit by IP
            if ip_address:
                try:
                    Gates.ip_rate_limit(ip_address)
                except GateError:
                    return CodeRequestResult(
                        success=False,
                        error="Too many attempts from this location.",
                        error_code=ErrorCode.IP_RATE_LIMIT,
                    )

            previous_codes = VerificationCode.objects.filter(
                target_value=target_value,
                purpose=purpose,
            )
            if previous_codes.filter(
                status=VerificationCode.Status.PENDING,
                delivery_started_at__isnull=False,
            ).exists():
                return CodeRequestResult(
                    success=False,
                    error="A previous delivery still needs reconciliation.",
                    error_code=ErrorCode.SEND_FAILED,
                )
            previous_codes.filter(
                Q(status=VerificationCode.Status.SENT)
                | Q(
                    status=VerificationCode.Status.PENDING,
                    delivery_started_at__isnull=True,
                )
            ).update(status=VerificationCode.Status.EXPIRED)

            # Create code — store HMAC, send raw only after this commit.
            from ..models.verification_code import generate_raw_code

            raw_code, hmac_digest = generate_raw_code()
            code = VerificationCode.objects.create(
                code_hash=hmac_digest,
                target_value=target_value,
                purpose=purpose,
                delivery_method=delivery_method,
                ip_address=ip_address,
                customer_id=customer_id,
            )

        # Phase B fence: mark that provider I/O is about to start while holding
        # Customer -> VerificationCode.  Deletion treats this PENDING marker as
        # in-flight even after code expiry, so a late provider return cannot
        # cross an already-completed account deletion.
        with transaction.atomic():
            if customer_id is not None:
                locked_customer = adapter.lock_active_customer_by_uuid(customer_id)
                target_is_current = (
                    purpose != VerificationCode.Purpose.LOGIN
                    or (
                        locked_customer is not None
                        and adapter.login_target_belongs_to_customer(
                            locked_customer,
                            target_value,
                        )
                    )
                )
                if locked_customer is None or not target_is_current:
                    cls._fail_pending_code(code.pk)
                    return CodeRequestResult(
                        success=False,
                        error="Account inactive.",
                        error_code=ErrorCode.ACCOUNT_INACTIVE,
                    )
            code = VerificationCode.objects.select_for_update().filter(pk=code.pk).first()
            if (
                code is None
                or code.status != VerificationCode.Status.PENDING
                or code.is_expired
            ):
                cls._fail_pending_code(getattr(code, "pk", None))
                return CodeRequestResult(
                    success=False,
                    error="Failed to prepare code delivery.",
                    error_code=ErrorCode.SEND_FAILED,
                )
            code.delivery_started_at = timezone.now()
            code.save(update_fields=["delivery_started_at"])

        # Phase B: external I/O after both durable intents are visible.
        if sender:
            # Custom sender provided (e.g. tests) — bypass fallback chain
            try:
                sent = sender.send_code(target_value, raw_code, delivery_method)
                actual_method = delivery_method
                if not sent:
                    cls._fail_pending_code(code.pk)
                    return CodeRequestResult(
                        success=False, error="Failed to send code.",
                        error_code=ErrorCode.SEND_FAILED,
                    )
            except Exception:
                logger.exception("Send failed", extra={"target": target_value})
                cls._fail_pending_code(code.pk)
                return CodeRequestResult(
                    success=False, error="Error sending code.",
                    error_code=ErrorCode.SEND_FAILED,
                )
        else:
            # Use adapter's fallback chain
            sent, actual_method = adapter.send_code_with_fallback(
                target_value, raw_code, preferred_method=delivery_method,
            )
            if not sent:
                cls._fail_pending_code(code.pk)
                return CodeRequestResult(
                    success=False, error="Failed to send code.",
                    error_code=ErrorCode.SEND_FAILED,
                )

        # Phase C: Customer -> VerificationCode, the same canonical order used
        # by contact changes and account deletion.  If deletion/contact change
        # won while transport was running, the delivered code is failed closed.
        with transaction.atomic():
            if customer_id is not None:
                locked_customer = adapter.lock_active_customer_by_uuid(customer_id)
                target_is_current = (
                    purpose != VerificationCode.Purpose.LOGIN
                    or (
                        locked_customer is not None
                        and adapter.login_target_belongs_to_customer(
                            locked_customer,
                            target_value,
                        )
                    )
                )
                if locked_customer is None or not target_is_current:
                    cls._fail_pending_code(code.pk)
                    return CodeRequestResult(
                        success=False,
                        error="Account inactive.",
                        error_code=ErrorCode.ACCOUNT_INACTIVE,
                    )

            code = VerificationCode.objects.select_for_update().filter(pk=code.pk).first()
            if code is None or code.status != VerificationCode.Status.PENDING:
                return CodeRequestResult(
                    success=False,
                    error="Failed to finalize code delivery.",
                    error_code=ErrorCode.SEND_FAILED,
                )
            if actual_method != delivery_method:
                code.delivery_method = actual_method
            code.status = VerificationCode.Status.SENT
            code.sent_at = timezone.now()
            update_fields = ["status", "sent_at"]
            if actual_method != delivery_method:
                update_fields.append("delivery_method")
            code.save(update_fields=update_fields)

        # Signal
        verification_code_sent.send(
            sender=cls,
            code=code,
            target_value=target_value,
            delivery_method=actual_method,
        )

        logger.info("Code sent", extra={"target": target_value, "purpose": purpose})

        return CodeRequestResult(
            success=True,
            code_id=str(code.id),
            expires_at=code.expires_at.isoformat(),
            delivery_method=actual_method,
            debug_code=raw_code,
        )

    @staticmethod
    def _fail_pending_code(code_id) -> None:
        """Make a prepared code unusable without reviving terminal rows."""
        VerificationCode.objects.filter(
            pk=code_id,
            status=VerificationCode.Status.PENDING,
        ).update(status=VerificationCode.Status.FAILED)

    # ===========================================
    # Verify for Login
    # ===========================================

    @classmethod
    @transaction.atomic
    def verify_for_login(
        cls,
        target_value: str,
        code_input: str,
        request: HttpRequest | None = None,
    ) -> VerifyResult:
        """
        Verify code for login.

        Creates or retrieves Customer and marks code as verified.

        Args:
            target_value: Phone or email
            code_input: User-provided code
            request: Django request for audit

        Returns:
            VerifyResult with customer
        """
        adapter = get_adapter()
        target_value = adapter.normalize_login_target(target_value)
        if not target_value:
            return VerifyResult(
                success=False,
                error="Invalid login target.",
                error_code=ErrorCode.INVALID_TARGET,
            )

        # Leitura indicativa sem lock para descobrir o titular. A ordem de
        # bloqueio é sempre Customer -> VerificationCode, como na exclusão.
        code_hint = cls._get_valid_code(
            target_value,
            VerificationCode.Purpose.LOGIN,
            for_update=False,
        )
        if not code_hint:
            return VerifyResult(
                success=False,
                error="Code expired. Please request a new one.",
                error_code=ErrorCode.CODE_EXPIRED,
            )

        customer = None
        customer_hint = None
        if code_hint.customer_id:
            customer_hint = adapter.resolve_customer_by_uuid(code_hint.customer_id)
        if customer_hint is None:
            customer_hint = adapter.resolve_customer(target_value)
        if customer_hint is not None:
            customer = adapter.lock_active_customer_by_uuid(customer_hint.uuid)
            if customer is None:
                return VerifyResult(
                    success=False,
                    error="Account inactive.",
                    error_code=ErrorCode.ACCOUNT_INACTIVE,
                )
            if not adapter.login_target_belongs_to_customer(customer, target_value):
                return VerifyResult(
                    success=False,
                    error="Code expired. Please request a new one.",
                    error_code=ErrorCode.CODE_EXPIRED,
                )

        # A modern code is bound to the customer resolved when it was issued.
        # Never fall back to auto-creation when that owner was deleted or when
        # the target stopped belonging to it while this request waited.
        if code_hint.customer_id and (
            customer is None or str(code_hint.customer_id) != str(customer.uuid)
        ):
            return VerifyResult(
                success=False,
                error="Code expired. Please request a new one.",
                error_code=ErrorCode.CODE_EXPIRED,
            )

        code = (
            VerificationCode.objects.select_for_update()
            .filter(
                pk=code_hint.pk,
                target_value=target_value,
                purpose=VerificationCode.Purpose.LOGIN,
                status=VerificationCode.Status.SENT,
                expires_at__gt=timezone.now(),
            )
            .first()
        )
        if code is None:
            return VerifyResult(
                success=False,
                error="Code expired. Please request a new one.",
                error_code=ErrorCode.CODE_EXPIRED,
            )
        if code.customer_id and (
            customer is None or str(code.customer_id) != str(customer.uuid)
        ):
            return VerifyResult(
                success=False,
                error="Code expired. Please request a new one.",
                error_code=ErrorCode.CODE_EXPIRED,
            )

        # Verify code (checks is_valid + HMAC in one call)
        if not code.verify(code_input):
            code.record_attempt()
            adapter.on_login_failed(request, target_value, "incorrect_code")
            return VerifyResult(
                success=False,
                error="Incorrect code.",
                error_code=ErrorCode.CODE_INVALID,
                attempts_remaining=code.attempts_remaining,
            )

        # Get or create Customer via adapter
        created = False

        if not customer:
            if not adapter.should_auto_create_customer():
                adapter.on_login_failed(request, target_value, "account_not_found")
                return VerifyResult(
                    success=False,
                    error="Account not found. Please contact support.",
                    error_code=ErrorCode.ACCOUNT_NOT_FOUND,
                )

            customer = adapter.create_customer(target_value)
            created = True

        cls._link_verified_identifier(customer, target_value)

        # Mark code verified
        code.mark_verified(customer.uuid)

        # Django login if request provided
        if request is not None:
            from ._user_bridge import get_or_create_user_for_customer

            # Preserve session keys across login (login flushes session)
            preserved = {}
            preserve_keys = doorman_settings.PRESERVE_SESSION_KEYS
            if preserve_keys and hasattr(request, "session"):
                for key in preserve_keys:
                    if key in request.session:
                        preserved[key] = request.session[key]

            user, _ = get_or_create_user_for_customer(customer)
            login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")

            # Restore preserved keys
            for key, val in preserved.items():
                request.session[key] = val

        # Signal
        verification_code_verified.send(
            sender=cls,
            code=code,
            customer=customer,
            purpose=VerificationCode.Purpose.LOGIN,
        )

        logger.info(
            "Login verified",
            extra={
                "customer_id": str(customer.uuid),
                "created_customer": created,
            },
        )

        return VerifyResult(
            success=True,
            customer=customer,
            created_customer=created,
        )

    @classmethod
    def _link_verified_identifier(cls, customer: AuthCustomerInfo, target_value: str) -> None:
        """Best-effort linking of the verified login handle into Guestman's identifier table."""
        try:
            from shopman.guestman.contrib.identifiers import IdentifierService, IdentifierType
            from shopman.guestman.models import ContactPoint
            from shopman.guestman.models import Customer as GuestCustomer
            from shopman.guestman.services import identity as identity_service

            from ..conf import get_adapter

            guest_customer = GuestCustomer.objects.filter(uuid=customer.uuid, is_active=True).first()
            if not guest_customer:
                return
            adapter = get_adapter()
            if adapter.target_kind(target_value) == "email":
                identity_service.ensure_contact_point(
                    guest_customer,
                    type=ContactPoint.Type.EMAIL,
                    value_normalized=target_value,
                    is_primary=True,
                    is_verified=True,
                )
                IdentifierService.ensure_identifier(
                    customer_ref=guest_customer.ref,
                    identifier_type=IdentifierType.EMAIL,
                    identifier_value=target_value,
                    is_primary=True,
                    source_system="doorman",
                )
                return
            identity_service.ensure_contact_point(
                guest_customer,
                type=ContactPoint.Type.WHATSAPP,
                value_normalized=target_value,
                is_primary=True,
                is_verified=True,
            )
            IdentifierService.ensure_identifier(
                customer_ref=guest_customer.ref,
                identifier_type=IdentifierType.WHATSAPP,
                identifier_value=target_value,
                is_primary=True,
                source_system="doorman",
            )
        except Exception:
            logger.exception("verify_for_login: failed to link verified identifier")

    # ===========================================
    # Helpers
    # ===========================================

    @classmethod
    def _get_valid_code(
        cls,
        target_value: str,
        purpose: str,
        *,
        for_update: bool = False,
    ) -> VerificationCode | None:
        """Get the most recent valid code for target and purpose."""
        queryset = VerificationCode.objects
        if for_update:
            queryset = queryset.select_for_update()
        try:
            return queryset.filter(
                target_value=target_value,
                purpose=purpose,
                status=VerificationCode.Status.SENT,
                expires_at__gt=timezone.now(),
            ).latest("created_at")
        except VerificationCode.DoesNotExist:
            return None

    @classmethod
    def cleanup_expired_codes(cls, days: int = 7) -> int:
        """
        Delete expired codes older than N days.

        Args:
            days: Delete codes older than this many days

        Returns:
            Number of deleted codes
        """
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = (
            VerificationCode.objects.filter(expires_at__lt=cutoff)
            .exclude(
                status=VerificationCode.Status.PENDING,
                delivery_started_at__isnull=False,
            )
            .delete()
        )
        return deleted
