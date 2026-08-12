"""Passkey: cadastrar e entrar sem código nenhum.

Dois fluxos, e os dois em dois passos porque WebAuthn é desafio-resposta:

1. **Cadastrar** (`registration_options` → `verify_registration`): a pessoa já está
   identificada e diz "quero entrar com o rosto na próxima vez".
2. **Entrar** (`login_options` → `verify_login`): sem digitar telefone, sem código. O
   navegador oferece as credenciais que ele tem para o nosso domínio.

⚠️ **O desafio vive na SESSÃO, não em variável nem em cache global.** Ele é de uso único e é
o que impede replay: a assinatura só vale para o desafio que nós acabamos de emitir, naquele
navegador. Guardar em cache por chave adivinhável ou aceitar desafio antigo transformaria a
proteção em enfeite.

⚠️ **A verificação criptográfica é da biblioteca.** `webauthn` (py_webauthn) faz CBOR, COSE,
contadores e formatos de attestation. Escrever isso na unha é como escrever o próprio TLS: dá
para fazer parecer funcionando e errar em silêncio no que importa.

O que este módulo NÃO faz, de propósito: não cria cliente, não mexe em sessão do Django, não
sabe o que é `request.user`. Ele valida assinatura e devolve a credencial; quem loga é a
camada de cima (`shopman/shop/services/auth.py`), como no resto do doorman.
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Chaves do desafio na sessão. Nomes distintos porque cadastrar e entrar podem acontecer no
#: mesmo navegador em sequência, e um desafio não pode servir para o outro fluxo.
REGISTRATION_CHALLENGE_KEY = "passkey_registration_challenge"
LOGIN_CHALLENGE_KEY = "passkey_login_challenge"
CHALLENGE_ISSUED_AT_KEY = "passkey_challenge_at"


class PasskeyError(Exception):
    """Falha de cadastro ou de login por passkey, com mensagem para a pessoa."""


@dataclass(frozen=True)
class PasskeyResult:
    """O resultado de uma verificação: qual credencial, de quem."""

    customer_id: str
    credential_id: str
    label: str = ""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def is_enabled() -> bool:
    from ..conf import doorman_settings

    return bool(doorman_settings.PASSKEY_ENABLED)


def _rp_id(request) -> str:
    """O domínio que a credencial reconhece.

    Configurado ganha; sem configuração, o host da requisição (sem porta) — que é o que faz
    dev funcionar sem ninguém configurar nada. É este valor que dá a imunidade a phishing:
    o sistema operacional só assina para ele.
    """
    from ..conf import doorman_settings

    configured = (doorman_settings.PASSKEY_RP_ID or "").strip()
    if configured:
        return configured
    host = (request.get_host() or "").split(":")[0]

    # ⚠️ WebAuthn exige DOMÍNIO REGISTRÁVEL: `localhost` é caso especial e passa, endereço IP
    # não (o Chrome recusa com `SecurityError: This is an invalid domain`). O dev deste projeto
    # roda em `127.0.0.1` por convenção, então passkey simplesmente não funciona local — e o
    # aviso no log é para ninguém perder uma hora procurando bug onde não tem.
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        logger.warning(
            "passkey.rp_id_is_an_ip host=%s — WebAuthn recusa endereço IP; use localhost ou "
            "configure PASSKEY_RP_ID com o domínio da loja.",
            host,
        )
    return host


def _issue_challenge(request, key: str, challenge: bytes) -> None:
    request.session[key] = _b64(challenge)
    request.session[CHALLENGE_ISSUED_AT_KEY] = timezone.now().isoformat()


def _consume_challenge(request, key: str) -> bytes:
    """Ler e APAGAR o desafio. Uso único é o que impede replay."""
    from ..conf import doorman_settings

    raw = request.session.pop(key, None)
    issued_raw = request.session.pop(CHALLENGE_ISSUED_AT_KEY, None)
    if not raw:
        raise PasskeyError("Este pedido expirou. Tente de novo.")

    if issued_raw:
        from datetime import datetime

        try:
            issued = datetime.fromisoformat(issued_raw)
        except ValueError:
            issued = None
        if issued is not None:
            limite = timedelta(minutes=doorman_settings.PASSKEY_CHALLENGE_TTL_MINUTES)
            if timezone.now() - issued > limite:
                raise PasskeyError("Este pedido expirou. Tente de novo.")

    return _unb64(str(raw))


# ── Cadastrar ────────────────────────────────────────────────────────


def registration_options(request, *, customer_id, display_name: str, user_name: str) -> dict:
    """As opções que o navegador precisa para criar a credencial."""
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    from ..models import Passkey

    ja_tem = list(
        Passkey.objects.filter(customer_id=customer_id).values_list("credential_id", flat=True)
    )

    options = generate_registration_options(
        rp_id=_rp_id(request),
        rp_name=_rp_name(),
        user_id=str(customer_id).encode(),
        user_name=user_name,
        user_display_name=display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            # `required` é o que faz a credencial ser DESCOBERÍVEL: o navegador a oferece sem
            # a pessoa digitar telefone nenhum. É a diferença entre "entre com o rosto" e
            # "digite quem você é e depois use o rosto".
            resident_key=ResidentKeyRequirement.REQUIRED,
            # Exigir verificação de usuário = rosto/digital/PIN, não só presença. Sem isto,
            # um aparelho destravado na mão de outra pessoa entraria.
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        # Impede cadastrar DUAS credenciais do mesmo aparelho: o navegador vê que já existe e
        # avisa, em vez de criar uma segunda que a pessoa não sabe distinguir na lista.
        exclude_credentials=[
            _descriptor(credential_id) for credential_id in ja_tem
        ],
    )
    _issue_challenge(request, REGISTRATION_CHALLENGE_KEY, options.challenge)

    import json

    return json.loads(options_to_json(options))


def verify_registration(request, *, customer_id, credential: dict, label: str = "") -> PasskeyResult:
    """Conferir o que o navegador criou e guardar a chave pública."""
    from webauthn import verify_registration_response

    from ..models import Passkey

    challenge = _consume_challenge(request, REGISTRATION_CHALLENGE_KEY)
    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_rp_id(request),
            expected_origin=_expected_origin(request),
            require_user_verification=True,
        )
    except Exception as err:
        logger.warning("passkey.registration_rejected", exc_info=True)
        raise PasskeyError("Não conseguimos ativar aqui. Tente de novo.") from err

    credential_id = _b64(verification.credential_id)
    passkey, _created = Passkey.objects.update_or_create(
        credential_id=credential_id,
        defaults={
            "customer_id": customer_id,
            "public_key": _b64(verification.credential_public_key),
            "sign_count": verification.sign_count or 0,
            "transports": list(credential.get("response", {}).get("transports") or []),
            "label": label[:100],
        },
    )
    logger.info("passkey.registered customer=%s", customer_id)
    return PasskeyResult(
        customer_id=str(customer_id), credential_id=passkey.credential_id, label=passkey.label,
    )


# ── Entrar ───────────────────────────────────────────────────────────


def login_options(request) -> dict:
    """Desafio de login. Sem `allowCredentials`: o navegador oferece o que ele tem.

    É isso que permite entrar sem digitar telefone — e é por isso que a credencial é criada
    como descobrível no cadastro.
    """
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement

    options = generate_authentication_options(
        rp_id=_rp_id(request),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _issue_challenge(request, LOGIN_CHALLENGE_KEY, options.challenge)

    import json

    return json.loads(options_to_json(options))


def verify_login(request, *, credential: dict) -> PasskeyResult:
    """Conferir a assinatura e dizer de quem é a credencial."""
    from webauthn import verify_authentication_response

    from ..models import Passkey

    challenge = _consume_challenge(request, LOGIN_CHALLENGE_KEY)
    credential_id = str(credential.get("id") or credential.get("rawId") or "")
    passkey = Passkey.objects.filter(credential_id=credential_id).first()
    if passkey is None:
        # Mensagem única para "não existe" e "não confere": distinguir as duas contaria a
        # quem tenta se aquela credencial existe na nossa base.
        raise PasskeyError("Não reconhecemos esta chave. Entre pelo WhatsApp.")

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_rp_id(request),
            expected_origin=_expected_origin(request),
            credential_public_key=_unb64(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except Exception as err:
        logger.warning("passkey.login_rejected credential=%s", credential_id[:12], exc_info=True)
        raise PasskeyError("Não reconhecemos esta chave. Entre pelo WhatsApp.") from err

    passkey.touch(sign_count=verification.new_sign_count)
    logger.info("passkey.login customer=%s", passkey.customer_id)
    return PasskeyResult(
        customer_id=str(passkey.customer_id),
        credential_id=passkey.credential_id,
        label=passkey.label,
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _rp_name() -> str:
    from ..conf import doorman_settings

    return doorman_settings.PASSKEY_RP_NAME


def _expected_origin(request) -> str:
    """A origem que o navegador declara, montada do jeito que ele monta.

    ⚠️ Origem inclui ESQUEMA e PORTA (`https://loja.com`, `http://127.0.0.1:3000`), e a
    verificação compara byte a byte. Montar isso errado faz tudo falhar com "não reconhecemos
    esta chave", que é a mensagem menos útil possível para depurar.
    """
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{request.get_host()}"


def _descriptor(credential_id: str):
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor

    return PublicKeyCredentialDescriptor(id=_unb64(credential_id))


def list_for_customer(customer_id) -> list:
    """As passkeys da pessoa, para ela ver e revogar. Sem chave pública na resposta."""
    from ..models import Passkey

    return list(Passkey.objects.filter(customer_id=customer_id))


def revoke(customer_id, credential_id: str) -> bool:
    """Apagar uma credencial. Escopado ao cliente — ninguém revoga a de outro."""
    from ..models import Passkey

    deleted, _ = Passkey.objects.filter(
        customer_id=customer_id, credential_id=credential_id,
    ).delete()
    return bool(deleted)
