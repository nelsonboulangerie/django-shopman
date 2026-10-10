"""Cadastrar e usar a digital do dispositivo do operador (WebAuthn).

Dois fluxos, os dois desafio-resposta:

1. **Cadastrar** (``registration_options`` → ``verify_registration``): a pessoa já está
   na sessão de operador e diz "quero confirmar com a digital neste dispositivo".
2. **Confirmar** (``assertion_options`` → ``verify_assertion``): o selo do Marketing
   pede a assinatura do dispositivo PARA UMA confirmação exata. O desafio fica na
   sessão junto com a ``ref`` dessa confirmação, e a assinatura só vale para ela.

⚠️ O desafio vive na SESSÃO e é de uso único: é o que impede replay. A verificação
criptográfica é da biblioteca (``webauthn``), como no ``doorman`` do cliente.

⚠️ Origem: as superfícies de operador chegam pelo BFF (Nuxt), em outro host que o do
Django. A origem esperada é a que o navegador declarou (o cabeçalho ``Origin`` que o
BFF repassa), desde que esteja entre as origens confiáveis (``CSRF_TRUSTED_ORIGINS``);
o domínio da credencial (RP ID) é ``SHOPMAN_OPERATOR_PASSKEY_RP_ID`` quando
configurado (a zona do cookie de operador em produção), senão o host dessa origem.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

REGISTRATION_KEY = "operator_passkey_registration"
ASSERTION_KEY = "operator_passkey_assertion"
CHALLENGE_TTL = timedelta(minutes=5)


class OperatorPasskeyError(Exception):
    """Falha de cadastro ou de confirmação, com a frase para a pessoa."""


@dataclass(frozen=True)
class AssertionResult:
    credential_id: str
    confirmation_ref: str


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _origin(request) -> str:
    """A origem que o navegador declarou, se for uma das confiáveis."""
    declared = str(request.headers.get("Origin") or "").strip().rstrip("/")
    trusted = {str(value).rstrip("/") for value in getattr(settings, "CSRF_TRUSTED_ORIGINS", [])}
    own = f"{'https' if request.is_secure() else 'http'}://{request.get_host()}"
    trusted.add(own)
    if declared and declared in trusted:
        return declared
    return own


def _rp_id(request) -> str:
    configured = str(getattr(settings, "SHOPMAN_OPERATOR_PASSKEY_RP_ID", "") or "").strip()
    if configured:
        return configured
    return urlsplit(_origin(request)).hostname or ""


def _issue(request, key: str, challenge: bytes, **extra) -> None:
    request.session[key] = {"challenge": _b64(challenge), "issued_at": timezone.now().isoformat(), **extra}
    request.session.modified = True


def _consume(request, key: str) -> dict:
    raw = request.session.pop(key, None)
    request.session.modified = True
    if not isinstance(raw, dict) or not raw.get("challenge"):
        raise OperatorPasskeyError("Este pedido expirou. Tente de novo.")
    try:
        issued = datetime.fromisoformat(str(raw.get("issued_at") or ""))
    except ValueError:
        issued = None
    if issued is None or timezone.now() - issued > CHALLENGE_TTL:
        raise OperatorPasskeyError("Este pedido expirou. Tente de novo.")
    return raw


def has_passkey(user) -> bool:
    from shopman.shop.models import OperatorPasskey

    return OperatorPasskey.objects.filter(user=user).exists()


def registration_options(request, *, user) -> dict:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorAttachment,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    from shopman.shop.models import OperatorPasskey

    existing = OperatorPasskey.objects.filter(user=user).values_list("credential_id", flat=True)
    options = generate_registration_options(
        rp_id=_rp_id(request),
        rp_name=str(getattr(settings, "SHOPMAN_OPERATOR_PASSKEY_RP_NAME", "") or "Shopman"),
        user_id=f"operator:{user.pk}".encode(),
        user_name=user.get_username(),
        user_display_name=(user.get_full_name() or user.get_username()),
        authenticator_selection=AuthenticatorSelectionCriteria(
            # A digital é a do PRÓPRIO dispositivo (não uma chave USB nem o celular de outro).
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            # Verificação de usuário obrigatória: dispositivo destravado na mão de outra
            # pessoa não confirma nada.
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=_unb64(value)) for value in existing],
    )
    _issue(request, REGISTRATION_KEY, options.challenge, user_id=user.pk)
    return json.loads(options_to_json(options))


def verify_registration(request, *, user, credential: dict, label: str = ""):
    from webauthn import verify_registration_response

    from shopman.shop.models import OperatorPasskey

    issued = _consume(request, REGISTRATION_KEY)
    if issued.get("user_id") != user.pk:
        raise OperatorPasskeyError("A pessoa da sessão mudou. Comece de novo.")
    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=_unb64(issued["challenge"]),
            expected_rp_id=_rp_id(request),
            expected_origin=_origin(request),
            require_user_verification=True,
        )
    except Exception as exc:
        logger.warning("operator_passkey.registration_rejected user=%s", user.pk, exc_info=True)
        raise OperatorPasskeyError("Não deu para cadastrar a digital deste dispositivo. Tente de novo.") from exc
    credential_id = _b64(verification.credential_id)
    passkey, _created = OperatorPasskey.objects.update_or_create(
        credential_id=credential_id,
        defaults={
            "user": user,
            "public_key": _b64(verification.credential_public_key),
            "sign_count": verification.sign_count or 0,
            "transports": list((credential.get("response") or {}).get("transports") or []),
            "label": str(label or "")[:100],
        },
    )
    logger.info("operator_passkey.registered user=%s", user.pk)
    return passkey


def assertion_options(request, *, user, confirmation_ref: str) -> dict:
    """O desafio que o selo pede ao dispositivo, preso a UMA confirmação."""
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

    from shopman.shop.models import OperatorPasskey

    credentials = list(OperatorPasskey.objects.filter(user=user).values_list("credential_id", flat=True))
    if not credentials:
        raise OperatorPasskeyError("Este dispositivo ainda não tem a sua digital cadastrada.")
    options = generate_authentication_options(
        rp_id=_rp_id(request),
        allow_credentials=[PublicKeyCredentialDescriptor(id=_unb64(value)) for value in credentials],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _issue(request, ASSERTION_KEY, options.challenge, user_id=user.pk, confirmation_ref=str(confirmation_ref))
    return json.loads(options_to_json(options))


def verify_assertion(request, *, user, credential: dict) -> AssertionResult:
    from webauthn import verify_authentication_response

    from shopman.shop.models import OperatorPasskey

    issued = _consume(request, ASSERTION_KEY)
    if issued.get("user_id") != user.pk:
        raise OperatorPasskeyError("A pessoa da sessão mudou. Comece de novo.")
    credential_id = str(credential.get("id") or credential.get("rawId") or "")
    passkey = OperatorPasskey.objects.filter(credential_id=credential_id, user=user).first()
    if passkey is None:
        raise OperatorPasskeyError("A digital não conferiu. Use o seu código.")
    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=_unb64(issued["challenge"]),
            expected_rp_id=_rp_id(request),
            expected_origin=_origin(request),
            credential_public_key=_unb64(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:
        logger.warning("operator_passkey.assertion_rejected user=%s", user.pk, exc_info=True)
        raise OperatorPasskeyError("A digital não conferiu. Use o seu código.") from exc
    passkey.touch(sign_count=verification.new_sign_count)
    return AssertionResult(credential_id=passkey.credential_id, confirmation_ref=str(issued.get("confirmation_ref") or ""))
