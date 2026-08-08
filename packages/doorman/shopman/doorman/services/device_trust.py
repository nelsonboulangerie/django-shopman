"""
DeviceTrustService — Manage device trust for skip-OTP logins.

After OTP verification, a user can trust their device via a secure
HttpOnly cookie. On subsequent visits, the device token is checked
and if valid, the user can login without OTP.

Security:
- Cookie is HttpOnly, Secure (in production), SameSite=Lax.
- Token in DB stored as HMAC digest (never plaintext).
- TTL-based expiration.
- Can be revoked per-customer.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from ..conf import doorman_settings
from ..models.device_trust import SubjectType, TrustedDevice
from ..signals import device_trusted

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("shopman.doorman.device_trust")

# Cookie name for device trust token
COOKIE_NAME_ATTR = "DEVICE_TRUST_COOKIE_NAME"


class DeviceTrustService:
    """Service for device trust operations."""

    @classmethod
    def cookie_name_for(cls, subject_type: str) -> str:
        """Cookie de cada tipo de sujeito. Um cookie guarda um token só."""
        if subject_type == SubjectType.DISPLAY:
            return doorman_settings.DEVICE_TRUST_DISPLAY_COOKIE_NAME
        return doorman_settings.DEVICE_TRUST_COOKIE_NAME

    @classmethod
    def check(cls, request: HttpRequest, subject_type: str, subject_id) -> bool:
        """O request vem de um dispositivo confiável DESTE sujeito?

        Token válido de outro sujeito não serve: a checagem confere o par
        (tipo, id), então cookie de um quadro não abre outro.
        """
        if not doorman_settings.DEVICE_TRUST_ENABLED:
            return False

        raw_token = request.COOKIES.get(cls.cookie_name_for(subject_type))
        if not raw_token:
            return False

        device = TrustedDevice.verify_token(raw_token)
        if device is None:
            return False

        if device.subject_type != subject_type or device.subject_id != str(subject_id):
            return False

        logger.info(
            "Device trust verified",
            extra={
                "subject_type": subject_type,
                "subject_id": str(subject_id),
                "device_id": str(device.id),
            },
        )
        return True

    @classmethod
    def trust(
        cls,
        response: HttpResponse,
        subject_type: str,
        subject_id,
        request: HttpRequest,
    ) -> TrustedDevice | None:
        """
        Create a trusted device and set the cookie on the response.

        Call this after successful OTP verification.

        Returns the TrustedDevice or None if device trust is disabled.
        """
        if not doorman_settings.DEVICE_TRUST_ENABLED:
            return None

        user_agent = request.META.get("HTTP_USER_AGENT", "")
        from ..utils import get_client_ip

        ip = get_client_ip(request, doorman_settings.TRUSTED_PROXY_DEPTH)

        device, raw_token = TrustedDevice.create_for(
            subject_type=subject_type,
            subject_id=subject_id,
            user_agent=user_agent,
            ip_address=ip,
        )

        # Set cookie
        cookie_name = cls.cookie_name_for(subject_type)
        max_age = doorman_settings.DEVICE_TRUST_TTL_DAYS * 86400
        response.set_cookie(
            cookie_name,
            raw_token,
            max_age=max_age,
            httponly=True,
            secure=doorman_settings.USE_HTTPS,
            samesite="Lax",
        )

        # Signal
        device_trusted.send(
            sender=cls,
            device=device,
            subject_type=subject_type,
            subject_id=str(subject_id),
            request=request,
        )

        logger.info(
            "Device trusted",
            extra={
                "subject_type": subject_type,
                "subject_id": str(subject_id),
                "device_id": str(device.id),
                "label": device.label,
            },
        )

        return device

    @classmethod
    def revoke_device(cls, request: HttpRequest, response: HttpResponse) -> None:
        """Revoke the trusted device from the current request and clear cookie."""
        cookie_name = doorman_settings.DEVICE_TRUST_COOKIE_NAME
        raw_token = request.COOKIES.get(cookie_name)
        if raw_token:
            device = TrustedDevice.verify_token(raw_token)
            if device:
                device.revoke()
                logger.info(
                    "Device trust revoked",
                    extra={"device_id": str(device.id)},
                )
        response.delete_cookie(cookie_name)

    @classmethod
    def revoke_all(cls, customer_id: uuid.UUID) -> int:
        """Revoke all trusted devices for a customer."""
        count = TrustedDevice.revoke_all_for(SubjectType.CUSTOMER, customer_id)
        if count:
            logger.info(
                "All devices revoked",
                extra={"customer_id": str(customer_id), "count": count},
            )
        return count

    @classmethod
    def cleanup(cls, days: int = 7) -> int:
        """Delete expired device trust records older than N days."""
        return TrustedDevice.cleanup_expired(days)
