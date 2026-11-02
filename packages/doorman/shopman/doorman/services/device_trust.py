"""
DeviceTrustService — Manage device trust for skip-OTP logins.

After OTP verification, a user can trust their device via a secure
HttpOnly cookie. On subsequent visits, the device token is checked
and if valid, the user can login without OTP.

Security:
- Cookie is HttpOnly, Secure (in production), SameSite=Lax.
- Token in DB stored as HMAC digest (never plaintext).
- Vence depois de ``DEVICE_TRUST_TTL_DAYS`` SEM USO: cada uso renova o registro e o
  cookie (``renew_cookies``, chamado pelo ``DeviceTrustRenewalMiddleware``).
- Can be revoked per-customer.
"""

from __future__ import annotations

import logging
import re
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

#: Onde o request guarda os cookies a reemitir: ``{nome do cookie: token}``.
RENEWALS_ATTR = "_doorman_trust_renewals"


class DeviceTrustService:
    """Service for device trust operations."""

    @classmethod
    def cookie_name_for(cls, subject_type: str, subject_id=None) -> str:
        """Cookie de cada sujeito. Um cookie guarda um token só.

        ⚠️ Para DISPLAY o nome carrega o ``subject_id``, e isso não é detalhe: um
        computador pode tocar duas TVs. Com um nome só, autorizar o segundo
        quadro sobrescrevia o token do primeiro, e o primeiro voltava a dar 403 —
        as duas telas se derrubavam em revezamento. Cliente segue com nome único
        de propósito: um navegador é de uma pessoa.
        """
        # Quadro e ESTAÇÃO carregam o ``subject_id`` no nome, pela mesma razão: um
        # computador pode tocar duas TVs, e pode ser provisionado como balcão E
        # como totem. Com um nome só, autorizar o segundo sobrescrevia o token do
        # primeiro e os dois se derrubavam em revezamento. Cliente segue com nome
        # único de propósito: um navegador é de uma pessoa.
        base_por_sujeito = {
            SubjectType.DISPLAY: doorman_settings.DEVICE_TRUST_DISPLAY_COOKIE_NAME,
            SubjectType.STATION: doorman_settings.DEVICE_TRUST_STATION_COOKIE_NAME,
        }
        base = base_por_sujeito.get(subject_type)
        if base is None:
            return doorman_settings.DEVICE_TRUST_COOKIE_NAME
        if subject_id is None:
            return base
        seguro = re.sub(r"[^A-Za-z0-9_-]", "_", str(subject_id))
        return f"{base}_{seguro}"

    @classmethod
    def check(cls, request: HttpRequest, subject_type: str, subject_id) -> bool:
        """O request vem de um dispositivo confiável DESTE sujeito?

        Token válido de outro sujeito não serve: a checagem confere o par
        (tipo, id), então cookie de um quadro não abre outro.
        """
        if not doorman_settings.DEVICE_TRUST_ENABLED:
            return False

        raw_token = request.COOKIES.get(cls.cookie_name_for(subject_type, subject_id))
        if not raw_token:
            return False

        device = TrustedDevice.find_valid_token(raw_token)
        if device is None:
            return False

        if device.subject_type != subject_type or device.subject_id != str(subject_id):
            return False

        device.touch()
        cls.mark_renewal(request, cls.cookie_name_for(subject_type, subject_id), raw_token)

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

        cls._set_cookie(response, cls.cookie_name_for(subject_type, subject_id), raw_token)

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
    def _set_cookie(cls, response: HttpResponse, cookie_name: str, raw_token: str) -> None:
        response.set_cookie(
            cookie_name,
            raw_token,
            max_age=doorman_settings.DEVICE_TRUST_TTL_DAYS * 86400,
            httponly=True,
            secure=doorman_settings.USE_HTTPS,
            samesite="Lax",
        )

    @classmethod
    def mark_renewal(cls, request: HttpRequest, cookie_name: str, raw_token: str) -> None:
        """Pede que a resposta deste request reemita o cookie com o prazo cheio.

        Quem confere a confiança (``check``, ou quem chama ``TrustedDevice.verify_token``
        com o cookie na mão) quase nunca tem a resposta: ela nasce depois, na view. O
        registro já foi renovado no ``touch``; sem isto, o NAVEGADOR apagaria o cookie no
        prazo da emissão, e a renovação do banco seria de um token que ninguém mais tem.
        """
        renewals = getattr(request, RENEWALS_ATTR, None)
        if renewals is None:
            renewals = {}
            setattr(request, RENEWALS_ATTR, renewals)
        renewals[cookie_name] = raw_token

    @classmethod
    def renew_cookies(cls, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Reemite os cookies de confiança usados neste request, com o prazo cheio.

        Não toca num cookie que a própria resposta já escreveu: ``trust`` acabou de
        emitir um token novo, ou ``revoke_device``/``delete_cookie`` acabou de apagá-lo,
        e a decisão da view vale mais que a renovação.

        A resposta passa a ``Cache-Control: private``: ela carrega um token de
        dispositivo, e um cache compartilhado que a guardasse entregaria esse token a
        outro navegador.
        """
        renewals = getattr(request, RENEWALS_ATTR, None)
        if not renewals or not doorman_settings.DEVICE_TRUST_ENABLED:
            return response
        renewed = False
        for cookie_name, raw_token in renewals.items():
            if cookie_name in response.cookies:
                continue
            cls._set_cookie(response, cookie_name, raw_token)
            renewed = True
        if renewed:
            from django.utils.cache import patch_cache_control

            patch_cache_control(response, private=True)
        return response

    @classmethod
    def revoke_device(
        cls,
        request: HttpRequest,
        response: HttpResponse,
        *,
        subject_type: str,
        subject_id,
    ) -> None:
        """Revoke only the request token belonging to the named subject."""
        cookie_name = cls.cookie_name_for(subject_type, subject_id)
        raw_token = request.COOKIES.get(cookie_name)
        if raw_token:
            device = TrustedDevice.find_valid_token(raw_token)
            if (
                device
                and device.subject_type == subject_type
                and device.subject_id == str(subject_id)
            ):
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


def describe_user_agent(user_agent: str) -> str:
    """"Safari / iPhone": o mesmo rótulo que a lista de dispositivos mostra."""
    from ..models.device_trust import _derive_label

    return _derive_label(user_agent or "")
