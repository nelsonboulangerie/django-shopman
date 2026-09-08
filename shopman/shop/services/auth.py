"""Authentication mutation service for customer-facing entry points."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def customer_by_uuid(customer_uuid):
    from shopman.guestman.services import customer as customer_service

    return customer_service.get_by_uuid(customer_uuid)


def customer_by_phone(phone: str):
    from shopman.guestman.services import customer as customer_service

    return customer_service.get_by_phone(phone)


def set_missing_first_name(*, phone: str, name: str) -> None:
    customer = customer_by_phone(phone)
    if customer and not customer.first_name:
        customer.first_name = name
        customer.save(update_fields=["first_name"])


def update_customer_name(customer_ref: str, *, first_name: str, last_name: str):
    from shopman.guestman.services import customer as customer_service

    return customer_service.update(customer_ref, first_name=first_name, last_name=last_name)


def trusted_device_prefill(request) -> tuple[str, str]:
    """Return (phone, first_name) from a trusted device cookie when valid."""
    try:
        from shopman.doorman import TrustedDevice
        from shopman.doorman.conf import doorman_settings

        raw_token = request.COOKIES.get(doorman_settings.DEVICE_TRUST_COOKIE_NAME)
        if not raw_token:
            return "", ""
        device = TrustedDevice.verify_token(raw_token)
        if not device:
            return "", ""
        customer = customer_by_uuid(device.customer_id)
        if not customer:
            return "", ""
        return customer.phone or "", customer.first_name or ""
    except Exception:
        logger.debug("auth.trusted_device_prefill degraded; using fallback", exc_info=True)
        return "", ""


def client_ip(request) -> str:
    """IP real do cliente para os gates de rate-limit por IP do doorman.

    Atrás do load balancer, ``REMOTE_ADDR`` é o IP do proxy — todos os
    clientes compartilhariam um único bucket (falso bloqueio coletivo).
    Resolve via ``X-Forwarded-For`` com o mesmo ``TRUSTED_PROXY_DEPTH`` que os
    endpoints do doorman já usam.
    """
    import os

    from shopman.doorman.conf import get_doorman_settings
    from shopman.doorman.utils import get_client_ip

    depth = get_doorman_settings().TRUSTED_PROXY_DEPTH
    resolved = get_client_ip(request, depth)
    # Diagnóstico controlado (inerte por padrão): quando SHOPMAN_LOG_CLIENT_IP
    # está ligado, registra a cadeia X-Forwarded-For crua e o IP resolvido, para
    # descobrir a forma real do XFF atrás do proxy (ex.: DO App Platform) e ajustar
    # DOORMAN_TRUSTED_PROXY_DEPTH. Ligar só por uma janela curta em staging: é 1
    # linha de log por request e o XFF pode conter IP de cliente (dado pessoal).
    if os.environ.get("SHOPMAN_LOG_CLIENT_IP", "").lower() in ("true", "1", "yes"):
        logger.info(
            "client_ip.diagnostic xff=%r remote_addr=%r depth=%s resolved=%r",
            request.META.get("HTTP_X_FORWARDED_FOR"),
            request.META.get("REMOTE_ADDR"),
            depth,
            resolved,
        )
    return resolved


def request_code(*, phone: str, delivery_method: str, ip_address: str | None):
    from shopman.doorman import get_auth_service

    AuthService = get_auth_service()
    return AuthService.request_code(
        target_value=phone,
        purpose="login",
        delivery_method=delivery_method,
        ip_address=ip_address,
    )


# O OTP que prova POSSE de um contato, e não identidade de quem entra.
#
# O `purpose` não é decoração: ele separa dois cofres. Um código pedido para
# provar um número novo não serve para entrar em conta nenhuma, porque
# `verify_for_login` só procura código de `login` — e vice-versa. Sem essa
# separação, pedir "confirme seu número novo" geraria um código que abre a
# sessão de quem atender o telefone.
CONTACT_VERIFICATION_PURPOSE = "verify_contact"


def request_contact_verification_code(*, phone: str, delivery_method: str, ip_address: str | None):
    """Envia um OTP para provar posse de um número — sem logar, sem criar cliente.

    O caminho de login (`request_code` acima) resolve o cliente do número e, se
    não achar, CRIA um. Para "mudar meu número" isso seria um efeito colateral
    grave: pedir o código para o número novo nasceria um cadastro-fantasma nele,
    e o número que o cliente quer adotar já apareceria como sendo de outra conta.

    A finalidade `verify_contact` do Core não passa por `resolve_customer`: o
    `request_code` do doorman só normaliza, checa as portarias de rate limit e
    manda o código. Nenhum `Customer` é tocado. Foi medido.
    """
    from shopman.doorman import get_auth_service

    AuthService = get_auth_service()
    return AuthService.request_code(
        target_value=phone,
        purpose=CONTACT_VERIFICATION_PURPOSE,
        delivery_method=delivery_method,
        ip_address=ip_address,
    )


class ContactVerifyResult:
    """Resultado de conferir um código de posse de contato."""

    def __init__(
        self,
        *,
        success: bool,
        error_code: str = "",
        attempts_remaining: int | None = None,
    ):
        self.success = success
        self.error_code = error_code
        self.attempts_remaining = attempts_remaining


def verify_contact_code(*, phone: str, code_input: str, customer_uuid) -> ContactVerifyResult:
    """Confere um código de `verify_contact` — sem logar e sem resolver cliente.

    ⚠️ Não existe `AuthService.verify_contact()` no doorman, e isso NÃO é uma
    lacuna a preencher no Core. O único verify de serviço é o
    `verify_for_login`, que carrega justamente o que aqui faria estrago:
    `resolve_customer` + auto-create. O que ele tem de reaproveitável — achar o
    código válido, conferir o HMAC, contar a tentativa, carimbar — já é API
    pública do MODELO (`VerificationCode.verify()` se descreve como "the
    canonical entry point for code verification"). Compor sobre ela é usar o
    Core como ele é, não contorná-lo.

    O `select_for_update` é o mesmo do Core: duas conferências simultâneas do
    mesmo código não podem cada uma achar que gastou a última tentativa.
    """
    from django.db import transaction
    from django.utils import timezone
    from shopman.doorman.conf import get_adapter
    from shopman.doorman.models import VerificationCode

    target = get_adapter().normalize_login_target(phone)
    if not target:
        return ContactVerifyResult(success=False, error_code="invalid_target")

    with transaction.atomic():
        code = (
            VerificationCode.objects.select_for_update()
            .filter(
                target_value=target,
                purpose=CONTACT_VERIFICATION_PURPOSE,
                status__in=[
                    VerificationCode.Status.PENDING,
                    VerificationCode.Status.SENT,
                ],
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if code is None:
            return ContactVerifyResult(success=False, error_code="code_expired")

        if not code.verify(code_input):
            code.record_attempt()
            return ContactVerifyResult(
                success=False,
                error_code="code_invalid",
                attempts_remaining=code.attempts_remaining,
            )

        # Gastar o código aqui, e não depois da troca, é deliberado: um código
        # conferido não pode sobreviver para uma segunda tentativa, mesmo que a
        # troca seja recusada logo adiante por conflito.
        code.mark_verified(customer_uuid)

    return ContactVerifyResult(success=True)


def contact_verify_error_message(result: ContactVerifyResult) -> str:
    mensagens = {
        "invalid_target": "Confira o número e tente de novo.",
        "code_expired": "Esse código expirou. Peça um novo.",
        "code_invalid": "Código incorreto.",
    }
    mensagem = mensagens.get(result.error_code, "Não foi possível confirmar o código.")
    restantes = result.attempts_remaining
    if restantes is not None and restantes > 0:
        plural = "tentativa restante" if restantes == 1 else "tentativas restantes"
        mensagem += f" ({restantes} {plural})"
    return mensagem


def request_code_error_message(auth_result) -> str:
    from shopman.doorman.error_codes import ErrorCode

    error_map = {
        ErrorCode.RATE_LIMIT: "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
        ErrorCode.COOLDOWN: "Aguarde antes de solicitar um novo código.",
        ErrorCode.IP_RATE_LIMIT: "Muitas tentativas deste local. Tente mais tarde.",
    }
    return error_map.get(
        auth_result.error_code,
        "Não foi possível enviar o código. Verifique o número e tente novamente.",
    )


def request_code_partial_error_message(auth_result) -> str:
    translations = {
        "Too many attempts. Please wait a few minutes.": "Muitas tentativas. Aguarde alguns minutos.",
        "Please wait before requesting a new code.": "Aguarde antes de solicitar um novo código.",
        "Too many attempts from this location.": "Muitas tentativas deste local.",
        "Failed to send code.": "Falha ao enviar código.",
        "Error sending code.": "Erro ao enviar código.",
    }
    raw = auth_result.error or ""
    return translations.get(raw, raw) or "Erro ao enviar código."


def verify_for_login(*, phone: str, code_input: str, request):
    from shopman.doorman import get_auth_service

    AuthService = get_auth_service()
    return AuthService.verify_for_login(
        target_value=phone,
        code_input=code_input,
        request=request,
    )


def verify_error_message(auth_result) -> str:
    translations = {
        "Incorrect code.": "Código incorreto.",
        "Code expired. Please request a new one.": "Código expirado. Solicite um novo.",
        "Account not found. Please contact support.": "Conta não encontrada.",
    }
    raw_error = auth_result.error or ""
    error_msg = translations.get(raw_error, raw_error) or "Código inválido."
    if auth_result.attempts_remaining is not None and auth_result.attempts_remaining > 0:
        count = auth_result.attempts_remaining
        suffix = "tentativa restante" if count == 1 else "tentativas restantes"
        error_msg += f" ({count} {suffix})"
    return error_msg


def confirmed_customer_name(auth_result) -> str:
    try:
        customer = customer_by_uuid(auth_result.customer.uuid)
        return customer.first_name if customer else ""
    except Exception:
        logger.debug("auth.confirmed_customer_name degraded; using fallback", exc_info=True)
        return ""


def preserved_session_values(session) -> dict:
    from shopman.doorman.conf import doorman_settings

    return {
        key: session[key]
        for key in doorman_settings.PRESERVE_SESSION_KEYS
        if key in session
    }


def safe_redirect_url(next_url: str | None, request) -> str:
    from shopman.doorman.utils import safe_redirect_url as _safe_redirect_url

    return _safe_redirect_url(next_url, request)


def trusted_device_login(request, *, phone: str):
    """Authenticate request through trusted-device flow. Returns customer or None."""
    customer = customer_by_phone(phone)
    if not customer:
        return None

    from django.contrib.auth import login
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer
    from shopman.doorman.services.device_trust import DeviceTrustService

    if not DeviceTrustService.check(request, "customer", customer.uuid):
        return None

    customer_info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(customer_info)
    # login() dá flush na sessão quando OUTRO usuário estava logado — a sacola
    # anônima tem que sobreviver à troca, como nos fluxos do Doorman.
    preserved = preserved_session_values(request.session) if hasattr(request, "session") else {}
    login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")
    for key, value in preserved.items():
        request.session[key] = value
    return customer


# ── Passkey ──────────────────────────────────────────────────────────
#
# A ponte, pelo mesmo motivo de `device_is_trusted`: a superfície não fala com o kernel direto
# (`test_import_boundaries`). Aqui só passamos recado e, no login, criamos a sessão — a
# criptografia é toda do doorman.


def passkey_error():
    """A classe de exceção do passkey, para a superfície capturar sem importar o kernel.

    ⚠️ Parece cerimônia, mas é a mesma fronteira que o `test_import_boundaries` guarda: a loja
    fala com `shop.services`, não com o doorman. Deixar só a exceção passar por cima seria
    abrir um furo por conveniência — e furo de fronteira nunca fica sozinho.
    """
    from shopman.doorman.services.passkey import PasskeyError

    return PasskeyError


def passkey_enabled() -> bool:
    from shopman.doorman.services import passkey as passkey_service

    return passkey_service.is_enabled()


def passkey_registration_options(request, *, customer) -> dict:
    from shopman.doorman.services import passkey as passkey_service

    return passkey_service.registration_options(
        request,
        customer_id=customer.uuid,
        display_name=(getattr(customer, "name", "") or "").strip() or "Cliente",
        # O `user_name` aparece no seletor do sistema operacional ("Passkey para …"), então
        # telefone é melhor que ref interna: é o que a pessoa reconhece como sendo ela.
        user_name=(getattr(customer, "phone", "") or getattr(customer, "ref", "")),
    )


def passkey_register(request, *, customer, credential: dict, label: str = ""):
    from shopman.doorman.services import passkey as passkey_service

    return passkey_service.verify_registration(
        request, customer_id=customer.uuid, credential=credential, label=label,
    )


def passkey_login_options(request) -> dict:
    from shopman.doorman.services import passkey as passkey_service

    return passkey_service.login_options(request)


def passkey_login(request, *, credential: dict):
    """Verificar a assinatura e ABRIR a sessão. Devolve o cliente, ou levanta `PasskeyError`.

    Login por passkey é pelo menos tão forte quanto o OTP: a credencial só assina para o nosso
    domínio (imune a phishing) e exigimos verificação de usuário (rosto/digital/PIN). Então a
    sessão nasce com identidade FORTE — nada reduzido, nada a confirmar.
    """
    from django.contrib.auth import login
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services import passkey as passkey_service
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    result = passkey_service.verify_login(request, credential=credential)
    customer = customer_by_uuid(result.customer_id)
    if customer is None:
        from shopman.doorman.services.passkey import PasskeyError

        # Credencial órfã: o cliente foi apagado/anonimizado e a chave sobrou. Recusar com a
        # mesma mensagem de sempre (não contar o que existe na base) e deixar rastro no log.
        logger.warning("passkey_login_orphan_credential customer=%s", result.customer_id)
        raise PasskeyError("Não reconhecemos esta chave. Entre pelo WhatsApp.")

    customer_info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(customer_info)
    # A sacola anônima sobrevive à troca de sessão, como em todo login daqui.
    preserved = preserved_session_values(request.session) if hasattr(request, "session") else {}
    login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")
    for key, value in preserved.items():
        request.session[key] = value
    return customer


def passkey_list(customer) -> list:
    from shopman.doorman.services import passkey as passkey_service

    return passkey_service.list_for_customer(customer.uuid)


def passkey_revoke(customer, credential_id: str) -> bool:
    from shopman.doorman.services import passkey as passkey_service

    return passkey_service.revoke(customer.uuid, credential_id)


def device_is_trusted(request, *, customer_uuid) -> bool:
    """Este navegador já provou identidade por OTP algum dia e ganhou o cookie?

    É a pergunta que decide o quanto sabemos de quem está do outro lado: com o cookie,
    sabemos que é a PESSOA; sem ele, um link de campanha só nos diz o NÚMERO. Vive aqui, e
    não na API da loja, porque a superfície não fala com o kernel direto
    (`test_import_boundaries`) — e porque `trusted_device_login`/`trust_device`, os dois
    outros usos da mesma confiança, já moram neste módulo.
    """
    from shopman.doorman.services.device_trust import DeviceTrustService

    if not customer_uuid:
        return False
    return DeviceTrustService.check(request, "customer", customer_uuid)


def trust_device(*, response, customer_id, request) -> None:
    from shopman.doorman.services.device_trust import DeviceTrustService

    DeviceTrustService.trust(
        response=response,
        subject_type="customer",
        subject_id=customer_id,
        request=request,
    )


def revoke_current_device(*, request, response) -> None:
    from shopman.doorman.services.device_trust import DeviceTrustService

    DeviceTrustService.revoke_device(request, response)
