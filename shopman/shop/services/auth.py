"""Authentication mutation service for customer-facing entry points."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def customer_by_ref(customer_ref: str):
    from shopman.guestman.services import customer as customer_service

    return customer_service.get(customer_ref)


def customer_by_uuid(customer_uuid):
    from shopman.guestman.services import customer as customer_service

    return customer_service.get_by_uuid(customer_uuid)


IDENTITY_CONFLICT_DETAIL = (
    "Este número aparece em mais de um cadastro e, por segurança, não entramos "
    "por ele agora. Fale com a gente para resolver."
)


class TrustedDeviceIdentityConflict(Exception):
    """O número do dispositivo confiável não tem um dono só: a entrada é recusada."""

    detail = IDENTITY_CONFLICT_DETAIL


def identity_by_customer_ref(customer_ref: str):
    """Hydrate a session-safe Doorman identity through the configured resolver.

    O resolver é o da setting (``DOORMAN["IDENTITY_RESOLVER_CLASS"]``), o mesmo
    que o login usa: instanciar a classe do Guestman aqui ignorava a troca e
    abria uma segunda porta de identidade. Falha de leitura fecha (``None``,
    sem identidade) e grita no log, nunca em silêncio.
    """
    if not customer_ref:
        return None
    try:
        from shopman.doorman.conf import get_identity_resolver

        customer = customer_by_ref(customer_ref)
        if customer is None:
            return None
        identity = get_identity_resolver().get(customer.uuid, purpose="session")
        return identity if identity is not None and identity.is_active else None
    except Exception:
        logger.warning("auth.identity_by_customer_ref failed customer=%s", customer_ref, exc_info=True)
        return None


def identify_manychat_subject(subject: str):
    """Resolve/upsert a ManyChat subject through the opt-in Guestman bridge."""
    from shopman.guestman.adapters.auth import ManychatIdentityBridge

    return ManychatIdentityBridge().upsert_subscriber({"id": subject})


def _is_trusted_bff(request) -> bool:
    import hmac

    from django.conf import settings

    expected = str(getattr(settings, "SHOPMAN_BFF_PROXY_SECRET", "") or "")
    presented = str(request.META.get("HTTP_X_SHOPMAN_PROXY_SECRET", "") or "")
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


def _client_ip_behind_bff(request, depth: int) -> str | None:
    """IP do cliente final quando quem conectou foi um BFF Nuxt (loja ou operador).

    O navegador fala com o Nitro, e o Nitro abre conexão NOVA para o `api.` pela
    rede pública. A borda da plataforma trata o Nitro como um cliente qualquer e
    acrescenta, à direita, os mesmos ``depth`` saltos de sempre — o N-ésimo da
    direita é o IP de SAÍDA do Nitro (medido no alpha em 17/09: 147.182.186.185
    gravado como IP de consentimento). À esquerda deles está, intacto, o XFF que
    o Nitro recebeu da borda DELE, que é a mesma plataforma e portanto tem a
    mesma forma: contar ``depth`` da direita nesse trecho dá o cliente.

    Valor forjado pelo cliente entra na ponta esquerda e não desloca nenhuma das
    duas contagens. Sem trecho interno (dev local, BFF sem XFF) ou com lixo no
    lugar do IP, devolve ``None`` e vale a resolução direta.
    """
    import ipaddress

    xff = request.META.get("HTTP_X_FORWARDED_FOR") or ""
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if len(parts) <= depth:
        return None
    inner = parts[: len(parts) - depth]
    candidate = inner[max(0, len(inner) - depth)]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def client_ip(request) -> str:
    """IP real do cliente para rate-limit por IP e para evidência (LGPD).

    Atrás do load balancer, ``REMOTE_ADDR`` é o IP do proxy — todos os
    clientes compartilhariam um único bucket (falso bloqueio coletivo).
    Resolve via ``X-Forwarded-For`` com o mesmo ``TRUSTED_PROXY_DEPTH`` que os
    endpoints do doorman já usam.

    Quando a requisição traz o segredo dos BFFs Nuxt, lê um salto a mais: o
    N-ésimo da direita seria o IP de saída do Nitro, igual para todo visitante.
    Sem o segredo, o cabeçalho é ignorado — um cliente direto não consegue pedir
    a leitura mais funda para escolher o IP que quer ver gravado.
    """
    import os

    from shopman.doorman.conf import get_doorman_settings
    from shopman.doorman.utils import get_client_ip

    depth = get_doorman_settings().TRUSTED_PROXY_DEPTH
    resolved = get_client_ip(request, depth)
    via_bff = _is_trusted_bff(request)
    if via_bff:
        resolved = _client_ip_behind_bff(request, depth) or resolved
    # Diagnóstico controlado (inerte por padrão): quando SHOPMAN_LOG_CLIENT_IP
    # está ligado, registra a cadeia X-Forwarded-For crua e o IP resolvido, para
    # descobrir a forma real do XFF atrás do proxy (ex.: DO App Platform) e ajustar
    # DOORMAN_TRUSTED_PROXY_DEPTH. Ligar só por uma janela curta em staging: é 1
    # linha de log por request e o XFF pode conter IP de cliente (dado pessoal).
    if os.environ.get("SHOPMAN_LOG_CLIENT_IP", "").lower() in ("true", "1", "yes"):
        logger.info(
            "client_ip.diagnostic xff=%r remote_addr=%r depth=%s via_bff=%s resolved=%r",
            request.META.get("HTTP_X_FORWARDED_FOR"),
            request.META.get("REMOTE_ADDR"),
            depth,
            via_bff,
            resolved,
        )
    return resolved


# Volume global de códigos na última hora acima do qual o operador é avisado.
# Uma padaria não recebe 60 logins por hora: passar disso é ataque distribuído
# (muitos IPs, cada um abaixo do teto) ou defeito em loop. O aviso não bloqueia
# ninguém; ele chama alguém para olhar a conta do provedor.
LOGIN_CODES_GLOBAL_ALERT_PER_HOUR = 60
LOGIN_CODE_VOLUME_ALERT_TYPE = "login_code_volume"


def _watch_global_code_volume() -> None:
    """Avisa o operador quando o volume de códigos da última hora passa do limiar.

    Nunca levanta: observabilidade não derruba o login do cliente. O aviso tem
    texto estável, então o debounce do ``create_operator_alert`` segura um por
    janela em vez de um por envio.
    """
    try:
        from datetime import timedelta

        from django.utils import timezone
        from shopman.doorman.models import VerificationCode

        since = timezone.now() - timedelta(hours=1)
        count = VerificationCode.objects.filter(created_at__gte=since).count()
        if count <= LOGIN_CODES_GLOBAL_ALERT_PER_HOUR:
            return
        from shopman.shop.services.observability import create_operator_alert

        # Crítico: é a TI quem age (conta do provedor, bloqueio na borda), e o
        # crítico é o que chega por e-mail a ela. Um aviso por hora, no máximo.
        create_operator_alert(
            type=LOGIN_CODE_VOLUME_ALERT_TYPE,
            severity="critical",
            message=(
                f"Mais de {LOGIN_CODES_GLOBAL_ALERT_PER_HOUR} códigos de entrada pedidos "
                "na última hora. Confira na conta do provedor de SMS se é disparo "
                "automático (SMS pumping)."
            ),
            debounce_minutes=60,
            codes_last_hour=count,
        )
    except Exception:
        logger.exception("login_code.global_volume_watch_failed")


def _request_code_guarded(**kwargs):
    from shopman.doorman import get_auth_service

    from shopman.shop.policies.login_code_ceiling import ip_code_ceiling_refusal

    refusal = ip_code_ceiling_refusal(kwargs.get("ip_address"))
    if refusal is not None:
        return refusal
    result = get_auth_service().request_code(**kwargs)
    if getattr(result, "success", False):
        _watch_global_code_volume()
    return result


def request_code(*, phone: str, delivery_method: str, ip_address: str | None):
    return _request_code_guarded(
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


def request_contact_verification_code(
    *,
    phone: str,
    delivery_method: str,
    ip_address: str | None,
    customer_uuid,
):
    """Envia um OTP para provar posse de um número — sem logar, sem criar cliente.

    O caminho de login (`request_code` acima) resolve o cliente do número e, se
    não achar, CRIA um. Para "mudar meu número" isso seria um efeito colateral
    grave: pedir o código para o número novo nasceria um cadastro-fantasma nele,
    e o número que o cliente quer adotar já apareceria como sendo de outra conta.

    A finalidade `verify_contact` do Core não passa por `resolve_identity`: o
    `request_code` do doorman só normaliza, checa as portarias de rate limit e
    manda o código. Nenhum `Customer` é tocado. Foi medido.
    """
    return _request_code_guarded(
        target_value=phone,
        purpose=CONTACT_VERIFICATION_PURPOSE,
        delivery_method=delivery_method,
        ip_address=ip_address,
        customer_id=customer_uuid,
    )


class ContactVerifyResult:
    """Resultado de conferir um código de posse de contato."""

    def __init__(
        self,
        *,
        success: bool,
        error_code: str = "",
        attempts_remaining: int | None = None,
        delivery_method: str = "",
    ):
        self.success = success
        self.error_code = error_code
        self.attempts_remaining = attempts_remaining
        # O canal por onde o código SAIU de fato (o doorman regrava o
        # `delivery_method` do código quando a cadeia cai para o seguinte).
        # É a prova da posse, e é o que o contato carimba como origem.
        self.delivery_method = delivery_method


def verify_contact_code(*, phone: str, code_input: str, customer_uuid) -> ContactVerifyResult:
    """Confere um código de `verify_contact` — sem logar e sem resolver cliente.

    ⚠️ Não existe `AuthService.verify_contact()` no doorman, e isso NÃO é uma
    lacuna a preencher no Core. O único verify de serviço é o
    `verify_for_login`, que carrega justamente o que aqui faria estrago:
    `resolve_identity` + auto-create. O que ele tem de reaproveitável — achar o
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

    handle = get_adapter().login_handle(phone)
    if handle.kind != "phone" or not handle.value:
        return ContactVerifyResult(success=False, error_code="invalid_target")
    target = handle.value

    with transaction.atomic():
        code = (
            VerificationCode.objects.select_for_update()
            .filter(
                target_value=target,
                purpose=CONTACT_VERIFICATION_PURPOSE,
                status=VerificationCode.Status.SENT,
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
        delivery_method = code.delivery_method

    return ContactVerifyResult(success=True, delivery_method=delivery_method)


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


def code_resend_cooldown_seconds() -> int:
    """Segundos entre dois envios de código para o mesmo número (gate G11 do doorman).

    Fonte única para a tela: o botão "Reenviar" libera quando o servidor aceita.
    """
    from shopman.doorman.conf import doorman_settings

    return max(0, int(doorman_settings.ACCESS_CODE_COOLDOWN_SECONDS))


def device_trust_period_display() -> str:
    """O prazo da confiança do dispositivo, dito como o cliente fala ("6 meses").

    Fonte única: ``DEVICE_TRUST_TTL_DAYS`` do doorman, que conta do ÚLTIMO uso.
    A copy do login tinha "30 dias" escrito à mão e se descolou do prazo real
    (180 dias) sem ninguém notar (beta 06/11, SMS-09).
    """
    from shopman.doorman.conf import doorman_settings

    days = int(doorman_settings.DEVICE_TRUST_TTL_DAYS)
    if days % 365 == 0:
        years = days // 365
        return "1 ano" if years == 1 else f"{years} anos"
    if days >= 60 and days % 30 == 0:
        return f"{days // 30} meses"
    return "1 dia" if days == 1 else f"{days} dias"


def auth_error_code(auth_result) -> str | None:
    """O código público do erro, quando a tela precisa de mais que o texto.

    - Conflito de identidade: o código digitado estava CERTO, e o título
      "Código não confere" mentia sobre ele (beta 05/11, LOJA-03).
    - Código morto (venceu ou acabaram as tentativas): não há o que corrigir no
      que foi digitado; a tela esconde a validade, limpa o campo e libera o
      "Reenviar" (beta 06/11, SMS-07).
    - Espera entre envios (G11): a tela volta ao passo do código, se ele ainda
      vale, com o relógio do "Reenviar" no tempo do servidor (beta 06/11, SMS-08).
    """
    from shopman.doorman.error_codes import ErrorCode

    error_code = getattr(auth_result, "error_code", None)
    if error_code == ErrorCode.IDENTITY_CONFLICT:
        return "identity_conflict"
    if error_code in {ErrorCode.CODE_MAX_ATTEMPTS, ErrorCode.CODE_EXPIRED, ErrorCode.COOLDOWN}:
        return str(error_code)
    if (auth_result.error or "") in {
        "Identity ownership is conflicting.",
        "This handle belongs to another account.",
    }:
        return "identity_conflict"
    return None


def auth_error_body(detail: str, auth_result, *, field: str | None = None) -> dict:
    """Corpo de erro do auth no dialeto da casa ``{detail, field, errors}``.

    O conflito de identidade não aponta campo: o que foi digitado estava certo.
    """
    error_code = auth_error_code(auth_result)
    body: dict = {
        "detail": detail,
        "field": None if error_code == "identity_conflict" else field,
        "errors": {},
    }
    if error_code:
        body["error_code"] = error_code
    return body


def code_cooldown_body(detail: str, auth_result, *, phone: str) -> dict:
    """Recusa do G11 com o que a tela precisa para não deixar o cliente no escuro.

    Os segundos que faltam (``retry_after_seconds``) e, se o código enviado há
    pouco ainda vale, a validade e o canal dele: a tela volta ao passo do código
    para o cliente digitar o que já chegou (beta 06/11, SMS-08).
    """
    body = auth_error_body(detail, auth_result)
    body["phone"] = phone
    body["retry_after_seconds"] = getattr(auth_result, "retry_after_seconds", None) or 0
    body["code_expires_at"] = getattr(auth_result, "expires_at", None) or ""
    return body


def _seconds_phrase(seconds: int) -> str:
    return "1 segundo" if seconds == 1 else f"{seconds} segundos"


def request_code_error_message(auth_result) -> str:
    from shopman.doorman.error_codes import ErrorCode

    retry_after = getattr(auth_result, "retry_after_seconds", None)
    if auth_result.error_code == ErrorCode.COOLDOWN and retry_after:
        # Quanto falta, sempre: "aguarde" sem número deixava o cliente parado
        # sem saber até quando (beta 06/11, SMS-08).
        return (
            "Já enviamos um código para este número. "
            f"Você pode pedir outro em {_seconds_phrase(int(retry_after))}."
        )
    error_map = {
        ErrorCode.RATE_LIMIT: "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
        ErrorCode.COOLDOWN: "Aguarde antes de solicitar um novo código.",
        ErrorCode.IP_RATE_LIMIT: "Muitas tentativas deste local. Tente mais tarde.",
        ErrorCode.TOO_MANY_FAILURES: (
            "Muitos códigos incorretos para este número. Por segurança, "
            "novos códigos ficam suspensos por até 24 horas."
        ),
        # A falha foi NOSSA (ou do provedor), não do número: mandar o cliente
        # "verificar o número" era um rótulo que mente, e ele repetia o mesmo
        # número até desistir. A saída real é tentar de novo ou entrar pelo
        # WhatsApp, que não depende de SMS.
        ErrorCode.SEND_FAILED: (
            "Não conseguimos enviar o código agora. Tente de novo em instantes "
            "ou entre pelo WhatsApp."
        ),
        ErrorCode.IDENTITY_CONFLICT: IDENTITY_CONFLICT_DETAIL,
    }
    return error_map.get(
        auth_result.error_code,
        "Não foi possível enviar o código. Verifique o número e tente novamente.",
    )


def verify_for_login(*, phone: str, code_input: str, request):
    from shopman.doorman import get_auth_service

    from shopman.shop.services.customer_sign_in import mark_method

    AuthService = get_auth_service()
    mark_method(request, "otp")
    return AuthService.verify_for_login(
        target_value=phone,
        code_input=code_input,
        request=request,
    )


def verify_error_message(auth_result) -> str:
    from shopman.doorman.conf import doorman_settings
    from shopman.doorman.error_codes import ErrorCode

    if getattr(auth_result, "error_code", None) == ErrorCode.CODE_MAX_ATTEMPTS:
        # O código morreu pelas tentativas erradas. Dizer "incorreto" (e depois
        # "expirado") escondia a causa e não dizia o que fazer (beta 06/11, SMS-07).
        tentativas = int(doorman_settings.ACCESS_CODE_MAX_ATTEMPTS)
        return f"Você errou o código {tentativas} vezes, e ele deixou de valer. Peça um novo código."
    translations = {
        "Incorrect code.": "Código incorreto.",
        "Code expired. Please request a new one.": "Este código não vale mais. Peça um novo código.",
        "Account not found. Please contact support.": "Conta não encontrada.",
        "Identity ownership is conflicting.": IDENTITY_CONFLICT_DETAIL,
        "This handle belongs to another account.": IDENTITY_CONFLICT_DETAIL,
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
        customer = customer_by_uuid(auth_result.customer.subject_id)
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
    """Entrar pelo dispositivo confiável. Devolve o cliente, ou None.

    Quem diz de quem é o número é o porto de identidade do doorman
    (``resolve_identity``), o mesmo que o login por código consulta. Uma
    resolução paralela aqui seria a mesma decisão com dois donos: o
    ``get_by_phone`` escolhe um dono por ordenação quando o número aparece em
    dois cadastros, e o dispositivo confiável abriria a conta errada.

    Conflito de dono falha FECHADO: ``TrustedDeviceIdentityConflict``, que a
    superfície transforma em recusa com mensagem ao cliente. Nunca se escolhe
    um dos donos.
    """
    from django.contrib.auth import login
    from django.db import transaction
    from shopman.doorman.conf import get_adapter
    from shopman.doorman.protocols.identity import IdentityConflict
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer
    from shopman.doorman.services.device_trust import DeviceTrustService

    from shopman.shop.services import account as account_service
    from shopman.shop.services.customer_sign_in import mark_method

    adapter = get_adapter()
    handle = adapter.login_handle(phone)
    if handle.kind != "phone" or not handle.value:
        return None
    try:
        identity_hint = adapter.resolve_identity(handle.kind, handle.value, purpose="login")
    except IdentityConflict as exc:
        raise TrustedDeviceIdentityConflict from exc
    if identity_hint is None or not identity_hint.is_active:
        return None

    with transaction.atomic():
        try:
            customer = account_service.lock_active_customer(customer_uuid=identity_hint.subject_id)
        except account_service.AccountUnavailable:
            # A exclusão pode vencer depois da leitura indicativa por telefone.
            # Login por dispositivo confiável é uma conveniência: nesse caso ele
            # simplesmente deixa de autenticar, sem transformar a corrida em 500.
            return None
        # Com a linha travada, o número ainda é desta conta? A troca de número
        # pode ter vencido entre a leitura e o lock, e um conflito que surgiu
        # nesse meio também recusa.
        try:
            still_owner = adapter.login_target_belongs_to_customer(identity_hint, handle)
        except IdentityConflict as exc:
            raise TrustedDeviceIdentityConflict from exc
        if not still_owner:
            return None
        if not DeviceTrustService.check(request, "customer", customer.uuid):
            return None

        customer_info = get_adapter().identity(customer.uuid, purpose="session")
        if customer_info is None:
            return None
        user, _ = get_or_create_user_for_customer(customer_info)
        # login() dá flush na sessão quando OUTRO usuário estava logado — a sacola
        # anônima tem que sobreviver à troca, como nos fluxos do Doorman.
        preserved = preserved_session_values(request.session) if hasattr(request, "session") else {}
        mark_method(request, "trusted_device")
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
        rp_name=_store_brand(),
    )


def _store_brand() -> str:
    """A marca da loja, que o sistema mostra na passkey ("Passkey para …")."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    return ((shop.brand_name or shop.name) if shop else "").strip()


def passkey_register(request, *, customer, credential: dict, label: str = ""):
    from django.db import transaction
    from shopman.doorman.services import passkey as passkey_service

    from shopman.shop.services import account as account_service

    with transaction.atomic():
        locked_customer = account_service.lock_active_customer(customer_uuid=customer.uuid)
        return passkey_service.verify_registration(
            request,
            customer_id=locked_customer.uuid,
            credential=credential,
            label=label,
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
    from django.db import transaction
    from shopman.doorman.conf import get_adapter
    from shopman.doorman.models import Passkey
    from shopman.doorman.services import passkey as passkey_service
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    from shopman.shop.services import account as account_service
    from shopman.shop.services.customer_sign_in import mark_method

    credential_id = str(credential.get("id") or credential.get("rawId") or "")
    customer_id = Passkey.objects.filter(credential_id=credential_id).values_list(
        "customer_id", flat=True
    ).first()
    if customer_id is None:
        return passkey_service.verify_login(request, credential=credential)

    with transaction.atomic():
        try:
            customer = account_service.lock_active_customer(customer_uuid=customer_id)
        except account_service.AccountUnavailable as exc:
            from shopman.doorman.services.passkey import PasskeyError

            raise PasskeyError("Não reconhecemos esta chave. Entre pelo WhatsApp.") from exc
        if not Passkey.objects.select_for_update().filter(
            credential_id=credential_id,
            customer_id=customer.uuid,
        ).exists():
            from shopman.doorman.services.passkey import PasskeyError

            raise PasskeyError("Não reconhecemos esta chave. Entre pelo WhatsApp.")
        result = passkey_service.verify_login(request, credential=credential)
        if str(result.customer_id) != str(customer.uuid):
            from shopman.doorman.services.passkey import PasskeyError

            raise PasskeyError("Não reconhecemos esta chave. Entre pelo WhatsApp.")

        customer_info = get_adapter().identity(customer.uuid, purpose="session")
        if customer_info is None:
            from shopman.doorman.services.passkey import PasskeyError

            raise PasskeyError("Não reconhecemos esta identidade. Entre pelo WhatsApp.")
        user, _ = get_or_create_user_for_customer(customer_info)
        # A sacola anônima sobrevive à troca de sessão, como em todo login daqui.
        preserved = preserved_session_values(request.session) if hasattr(request, "session") else {}
        mark_method(request, "passkey")
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
    from django.db import transaction
    from shopman.doorman.services.device_trust import DeviceTrustService

    from shopman.shop.services import account as account_service

    with transaction.atomic():
        locked_customer = account_service.lock_active_customer(customer_uuid=customer_id)
        DeviceTrustService.trust(
            response=response,
            subject_type="customer",
            subject_id=locked_customer.uuid,
            request=request,
        )


def revoke_current_device(*, request, response) -> None:
    from shopman.doorman.services.device_trust import DeviceTrustService

    subject_id = getattr(getattr(request, "customer", None), "subject_id", None)
    if subject_id is not None:
        DeviceTrustService.revoke_device(
            request,
            response,
            subject_type="customer",
            subject_id=subject_id,
        )
