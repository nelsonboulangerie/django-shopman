"""Storefront auth session API for API-first storefront clients."""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import access as access_service
from shopman.shop.services import auth as auth_service
from shopman.shop.services import storefront_links
from shopman.storefront.constants import HAS_AUTH
from shopman.storefront.identity import (
    IDENTITY_DEVICE,
    IDENTITY_NUMBER,
    IDENTITY_SESSION_KEY,
    get_authenticated_customer,
    identity_strength,
    knows_only_the_number,
)
from shopman.storefront.intents._phone import normalize_phone_input
from shopman.storefront.intents.auth import clean_display_name, needs_confirmation

logger = logging.getLogger(__name__)


SessionSerializer = inline_serializer(
    name="StorefrontAuthSession",
    fields={
        "is_authenticated": serializers.BooleanField(),
        "customer_ref": serializers.CharField(allow_blank=True),
        "customer_name": serializers.CharField(allow_blank=True),
        "customer_phone": serializers.CharField(allow_blank=True),
        "customer_email": serializers.CharField(allow_blank=True),
        "requires_welcome": serializers.BooleanField(),
        "welcome_suggested_name": serializers.CharField(allow_blank=True),
    },
)


def _session_payload(customer) -> dict:
    if not customer:
        return {
            "is_authenticated": False,
            "customer_ref": "",
            "customer_name": "",
            "customer_phone": "",
            "customer_email": "",
            "requires_welcome": False,
            "welcome_suggested_name": "",
        }

    customer_name = getattr(customer, "name", "") or ""
    return {
        "is_authenticated": True,
        "customer_ref": getattr(customer, "ref", "") or "",
        "customer_name": customer_name,
        "customer_phone": getattr(customer, "phone", "") or "",
        "customer_email": getattr(customer, "email", "") or "",
        "requires_welcome": needs_confirmation(customer_name),
        "welcome_suggested_name": clean_display_name(customer_name),
    }


class SessionView(APIView):
    """GET /api/v1/auth/session/ — current customer identity as JSON."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Current storefront session", responses={200: SessionSerializer})
    def get(self, request):
        customer = get_authenticated_customer(request)
        return Response(_session_payload(customer))


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — end Django auth session as JSON."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Logout storefront session", responses={200: SessionSerializer})
    def post(self, request):
        preserved = {}
        if hasattr(request, "session"):
            preserved = auth_service.preserved_session_values(request.session)

        django_logout(request)

        if hasattr(request, "session"):
            for key, value in preserved.items():
                request.session[key] = value

        response = Response(_session_payload(None))
        auth_service.revoke_current_device(request=request, response=response)
        return response


def _carried_strength(metadata) -> str:
    """A força que o token CARREGA, quando ele é uma travessia de navegador.

    ⚠️ Carrega, nunca promove. A travessia existe para levar a sessão de dentro do
    navegador embutido do WhatsApp para o navegador de verdade da pessoa (potes de cookie
    são separados — o do WKWebView não é o do Safari). Se ela chegou sabendo só o número, do
    outro lado continua sabendo só o número.

    Promover aqui seria transformar "trocar de navegador" em prova de identidade, o que é
    absurdo: é a mesma pessoa no mesmo aparelho, com a mesma dúvida.
    """
    if not isinstance(metadata, dict) or metadata.get("login_source") != "handoff":
        return ""
    carried = str(metadata.get("identity_strength") or "")
    return carried if carried in (IDENTITY_DEVICE, IDENTITY_NUMBER) else IDENTITY_NUMBER


def _record_identity_strength(request, metadata, *, customer) -> None:
    """Marcar a sessão quando ela nasceu de um link de campanha.

    ⚠️ E consultar o APARELHO antes de marcar como fraca: se este navegador já carrega o
    cookie de confiança da pessoa (`DeviceTrustService.check`), nós sabemos que é ela —
    o link foi só conveniência, e não há nada a reduzir. É o celular dela, que é o caso da
    esmagadora maioria de quem volta.
    """
    carried = _carried_strength(metadata)
    if carried:
        request.session[IDENTITY_SESSION_KEY] = carried
        return

    if not isinstance(metadata, dict) or metadata.get("login_source") != "campaign":
        return

    trusted = False
    try:
        if customer is not None:
            trusted = auth_service.device_is_trusted(request, customer_uuid=customer.uuid)
    except Exception:
        # Na dúvida, a identidade é a FRACA: reduzir o que aparece é degradação segura;
        # assumir confiança que não se verificou não é.
        logger.debug("access_link: device trust check degraded", exc_info=True)

    request.session[IDENTITY_SESSION_KEY] = (
        IDENTITY_DEVICE if trusted else IDENTITY_NUMBER
    )


def _access_link_redirect(metadata: dict | None) -> str:
    """Derive the Nuxt store destination from AccessLink metadata.

    The destination is owned by the backend (no client-supplied ``next``), so a
    magic link can only ever land on a safe in-store path.
    """
    from shopman.shop.services import storefront_links

    meta = metadata if isinstance(metadata, dict) else {}
    order_ref = str(meta.get("order_ref") or "")
    action = str(meta.get("action") or "")
    if order_ref:
        # PAYMENT-TRACKING-MERGE: pagamento é um degrau do acompanhamento, não uma
        # tela. Um magic link de pagamento aterrissa no próprio acompanhamento.
        if action == "reorder":
            return storefront_links.path_order_history()
        return storefront_links.path_order_tracking(order_ref)
    # A destination folded into the token at creation (e.g. ManyChat → /checkout).
    # It was validated as a safe relative path when minted; re-check defensively.
    next_path = str(meta.get("next") or "")
    if next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return storefront_links.path_account()


def _access_link_metadata_for_customer(metadata: dict | None, customer) -> dict | None:
    if not isinstance(metadata, dict):
        return metadata
    order_ref = str(metadata.get("order_ref") or "").strip()
    if not order_ref:
        return metadata

    from shopman.storefront.services import orders as order_service

    order = order_service.find_order(order_ref)
    if order is not None and order_service.customer_can_access_order(customer, order):
        return metadata

    logger.warning(
        "access_link_order_grant_denied order=%s customer_uuid=%s",
        order_ref,
        getattr(customer, "uuid", None),
    )
    return {**metadata, "order_ref": ""}


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch")
class AccessLinkExchangeView(APIView):
    """POST /api/v1/auth/access/ — exchange a magic-link token for a session.

    The customer clicks ``…/a?t=<token>`` on the store; the Nuxt page posts the
    token here (through the BFF), so the session cookie is established on the
    store host. Returns the session payload plus the backend-derived ``redirect``
    destination (from the token metadata).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Exchange a magic-link token for a session")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        payload = request.data if hasattr(request, "data") else {}
        token = str(payload.get("token") or payload.get("t") or "").strip()
        if not token:
            return Response({"detail": "Link inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if not HAS_AUTH:
            return Response({"ok": True, "redirect": storefront_links.path_account(), **_session_payload(None)})

        metadata = access_service.token_metadata(token)
        # Antes do resgate: depois dele o token está gasto e a origem já não se lê.
        source = access_service.token_source(token)
        result = access_service.exchange_token(token, request)
        if not result.success:
            # ⚠️ Token gasto NÃO significa porta fechada. É o segundo toque na mesma
            # mensagem — e o uso único é justamente o que o torna comum: a pessoa clica,
            # compra, volta na conversa e clica outra vez. Se ela JÁ tem sessão, dizer
            # "este link expirou" é uma parede falsa, a informação mais desanimadora
            # possível para quem já está dentro.
            #
            # Quem sabe as duas coisas (token inválido E sessão existente) é o servidor. A
            # página não tem como responder isso numa carga nova: o estado do cliente
            # nasce vazio, e só o cookie sabe.
            already = get_authenticated_customer(request)
            if already is not None:
                logger.info("access_link_exchange_spent_but_session_alive")
                redirect_metadata = _access_link_metadata_for_customer(metadata, already)
                return Response({
                    "ok": True,
                    "already_authenticated": True,
                    "redirect": _access_link_redirect(redirect_metadata),
                    "identity_strength": identity_strength(request),
                    **_session_payload(already),
                })
            logger.warning("access_link_exchange_failed error=%s", getattr(result, "error", "?"))
            return Response(
                {"detail": "Este link expirou ou já foi usado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hasattr(request, "session"):
            request.session["origin_channel"] = access_service.resolve_origin(result)
            _record_identity_strength(request, metadata, customer=result.customer)

        # Access link vindo do site: o código NB carregou a sacola anônima na metadata.
        # A in-app browser que abre o link é sessão nova (sem sacola), então adotamos a
        # ref — mas só se a sessão atual estiver vazia (não sobrescreve uma sacola local).
        cart_ref = str(metadata.get("cart_session_key") or "") if isinstance(metadata, dict) else ""
        if cart_ref and hasattr(request, "session") and not request.session.get("cart_session_key"):
            request.session["cart_session_key"] = cart_ref

        redirect_metadata = _access_link_metadata_for_customer(metadata, result.customer)
        order_ref = str(metadata.get("order_ref") or "") if isinstance(metadata, dict) else ""
        if order_ref and isinstance(redirect_metadata, dict) and redirect_metadata.get("order_ref") == order_ref:
            from shopman.storefront.services import orders as order_service

            order_service.grant_order_access(request, order_ref)

        customer = None
        try:
            if result.customer:
                customer = auth_service.customer_by_uuid(result.customer.uuid)
        except Exception:
            logger.debug("access_link_exchange: customer lookup degraded", exc_info=True)

        payload = {
            "ok": True,
            "redirect": _access_link_redirect(redirect_metadata),
            "identity_strength": identity_strength(request),
            **_session_payload(customer),
        }
        response = Response(payload)

        # ⚠️ Link nascido de uma MENSAGEM que a pessoa enviou (`source=manychat`) prova posse
        # do número — a mesma prova do OTP, que já confia no aparelho. Então este caminho
        # também confia: é o que faz a confirmação valer para sempre naquele celular, em vez
        # de virar pedágio semanal. Link que NÓS empurramos (`internal`, campanha) não
        # confia: mensagem se encaminha.
        if source == "manychat" and result.customer is not None:
            request.session[IDENTITY_SESSION_KEY] = IDENTITY_DEVICE
            try:
                auth_service.trust_device(
                    response=response, customer_id=result.customer.uuid, request=request,
                )
                payload["device_trusted"] = True
            except Exception:
                logger.warning("access_link_trust_failed", exc_info=True)
        # Handoff do site que expirou: entrou logado, mas a sacola não veio. Avisamos com
        # gentileza (copy configurável), sem bloquear a entrada. Ver ACCESS-LINK-UNIFICATION.
        if isinstance(metadata, dict) and metadata.get("handoff_expired"):
            from shopman.shop.omotenashi import resolve_copy

            payload["handoff_expired"] = True
            payload["notice"] = resolve_copy("LOGIN_HANDOFF_EXPIRED", moment="*").message
        response.data = payload
        return response


def _normalize_payload_phone(payload: dict) -> str:
    raw = (
        payload.get("phone_normalized")
        or payload.get("phone")
        or payload.get("target")
        or ""
    )
    raw = str(raw).strip()
    phone_region = str(payload.get("phone_region") or "BR")
    international = phone_region == "INTL" or (raw.startswith("+") and not raw.startswith("+55"))
    return normalize_phone_input(raw, international=international) or ""


# Como cada canal se chama na frase que o cliente lê. Mapa explícito: o que não
# está aqui NÃO tem nome de canal, e a tela omite o canal em vez de inventar um.
_DELIVERY_LABELS = {
    "whatsapp": "WhatsApp",
    "sms": "SMS",
    "email": "e-mail",
}


def _delivery_response(delivery_method: str) -> dict:
    # Era `"SMS" if delivery_method == "sms" else "WhatsApp"`: QUALQUER método
    # que não fosse exatamente `sms` virava "WhatsApp" — console, e-mail,
    # fallback. Quem clicava em "Receber por SMS" e caía no fallback lia "Código
    # enviado por WhatsApp" e ia esperar numa caixa de entrada que nunca ia
    # tocar. Um `else` que chuta um canal é pior que não dizer canal nenhum:
    # label vazio manda a tela omitir a frase do canal, o que é verdade.
    label = _DELIVERY_LABELS.get(str(delivery_method or "").strip().lower(), "")
    doorman = getattr(settings, "DOORMAN", {}) or {}
    chain = doorman.get("DELIVERY_CHAIN", [])
    sender_class = str(doorman.get("MESSAGE_SENDER_CLASS") or "")
    return {
        "delivery_method": delivery_method,
        "delivery_label": label,
        "dev_console_hint": bool(
            getattr(settings, "DEBUG", False)
            and ("console" in chain or "ConsoleSender" in sender_class)
        ),
    }


def _debug_otp_allowed() -> bool:
    if getattr(settings, "DEBUG", False):
        return True
    environment = str(getattr(settings, "SHOPMAN_ENVIRONMENT", "production")).strip().lower()
    return bool(
        getattr(settings, "SHOPMAN_EXPOSE_DEBUG_OTP", False)
        and environment in {"development", "dev", "local", "staging"}
    )


def _debug_otp_response(auth_result=None) -> dict:
    if not _debug_otp_allowed():
        return {}
    code = str(getattr(auth_result, "debug_code", "") or "")
    if not code:
        return {}
    return {
        "debug_otp_code": code,
        "debug_otp_expires_at": getattr(auth_result, "expires_at", None) or "",
    }


@method_decorator(ratelimit(key="user_or_ip", rate="5/m", method="POST", block=False), name="dispatch")
class RequestCodeView(APIView):
    """POST /api/v1/auth/request-code/ — request OTP as JSON."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Request storefront OTP")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        payload = request.data if hasattr(request, "data") else {}
        phone = _normalize_payload_phone(payload)
        if not phone:
            return Response(
                {"detail": "Telefone inválido.", "field": "phone"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery_method = str(payload.get("delivery_method") or "whatsapp").strip().lower()
        if delivery_method not in {"whatsapp", "sms"}:
            delivery_method = "whatsapp"

        if not HAS_AUTH:
            return Response({"ok": True, "phone": phone, **_delivery_response(delivery_method)})

        auth_result = auth_service.request_code(
            phone=phone,
            delivery_method=delivery_method,
            # IP real (XFF rightmost, TRUSTED_PROXY_DEPTH): atrás do LB,
            # REMOTE_ADDR é o proxy e o gate de IP bloquearia todo mundo junto.
            ip_address=auth_service.client_ip(request),
        )
        if not auth_result.success:
            return Response(
                {"detail": auth_service.request_code_error_message(auth_result)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actual_method = getattr(auth_result, "delivery_method", None) or delivery_method
        return Response({
            "ok": True,
            "phone": phone,
            # Timeout transparente: a validade do código é pública (o código não).
            "code_expires_at": getattr(auth_result, "expires_at", None) or "",
            **_delivery_response(actual_method),
            **_debug_otp_response(auth_result),
        })


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch")
class DeviceCheckView(APIView):
    """POST /api/v1/auth/device-check/ — skip OTP when trusted-device cookie is valid."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Check trusted device for passwordless login")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        payload = request.data if hasattr(request, "data") else {}
        phone = _normalize_payload_phone(payload)
        if not phone:
            return Response(
                {"detail": "Telefone inválido.", "field": "phone"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not HAS_AUTH:
            return Response({"ok": True, "trusted": False, "phone": phone, **_session_payload(None)})

        customer = auth_service.trusted_device_login(request, phone=phone)
        if not customer:
            return Response({"ok": True, "trusted": False, "phone": phone, **_session_payload(None)})

        return Response({"ok": True, "trusted": True, "phone": phone, **_session_payload(customer)})


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch")
class VerifyCodeView(APIView):
    """POST /api/v1/auth/verify-code/ — verify OTP and create session as JSON."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Verify storefront OTP")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        payload = request.data if hasattr(request, "data") else {}
        phone = _normalize_payload_phone(payload)
        code_input = str(payload.get("code") or "").strip()
        code_digits = "".join(ch for ch in code_input if ch.isdigit())
        if not phone:
            return Response(
                {"detail": "Telefone inválido.", "field": "phone"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(code_digits) != 6:
            return Response(
                {"detail": "Informe os 6 números do código.", "field": "code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not HAS_AUTH:
            return Response({"ok": True, "phone": phone, "customer_name": ""})

        auth_result = auth_service.verify_for_login(
            phone=phone,
            code_input=code_digits,
            request=request,
        )
        if not auth_result.success:
            return Response(
                {"detail": auth_service.verify_error_message(auth_result)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = None
        try:
            customer = auth_service.customer_by_uuid(auth_result.customer.uuid)
        except Exception:
            logger.debug("auth.post degraded; using fallback", exc_info=True)
            customer = None

        session = _session_payload(customer)
        session["customer_name"] = auth_service.confirmed_customer_name(auth_result) or session["customer_name"]
        return Response({"ok": True, "phone": phone, **session})


class TrustDeviceView(APIView):
    """POST /api/v1/auth/trust-device/ — persist trusted-device cookie after OTP consent."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Trust current device for future storefront logins")
    def post(self, request):
        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return Response({"detail": "Entre na sua conta para continuar."}, status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data if hasattr(request, "data") else {}
        trust_value = payload.get("trust", False)
        trust = trust_value is True or str(trust_value).strip().lower() in {"1", "true", "yes"}

        response = Response({"ok": True, "trusted": False})
        if trust:
            auth_service.trust_device(
                response=response,
                customer_id=customer_info.uuid,
                request=request,
            )
            response.data["trusted"] = True
        return response

class BrowserHandoffView(APIView):
    """POST /api/v1/auth/handoff/ → um link de uso único para o navegador DE VERDADE dela.

    ⚠️ Existe por um fato de plataforma, não por capricho: o navegador embutido do WhatsApp é
    um WKWebView com **pote de cookie próprio**. Tudo o que ela conquistar ali — sessão,
    aparelho confiado — não existe no Safari que ela usa no resto do dia. "Confirmado para
    sempre neste aparelho" era, na prática, "neste webview".

    Em vez de sofrer isso, atravessamos de propósito: no momento em que já sabemos quem ela
    é, oferecemos o pulo, e a identidade nasce no pote que ela vai usar de verdade. O link é
    curto, de uso único, e **carrega a força que a sessão já tinha** — nunca mais que isso,
    porque trocar de navegador não é prova de identidade.

    É também a porta de entrada da passkey: cadastrar credencial dentro do webview do
    WhatsApp é irregular; no navegador de verdade, não é.
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    #: Curto porque o pulo é imediato — ela toca e o navegador abre. Não é link para guardar,
    #: é um trilho entre dois navegadores do mesmo aparelho.
    HANDOFF_TTL_MINUTES = 3

    @extend_schema(tags=["auth"], summary="Mint a one-time link to the system browser")
    def post(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response(
                {"detail": "Entre na sua conta para continuar."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        payload = request.data if hasattr(request, "data") else {}
        raw_next = str((payload or {}).get("next") or "").strip()
        # Só caminho interno: o destino é a tela onde ela está, e aceitar URL de fora aqui
        # seria abrir redirect com sessão na mão.
        next_path = raw_next if raw_next.startswith("/") and not raw_next.startswith("//") else "/"

        try:
            url = access_service.mint_handoff_link(
                customer_uuid=customer.uuid,
                next_path=next_path,
                identity_strength=identity_strength(request),
                cart_session_key=str(request.session.get("cart_session_key") or ""),
                ttl_minutes=self.HANDOFF_TTL_MINUTES,
            )
        except Exception:
            logger.warning("browser_handoff_mint_failed", exc_info=True)
            url = ""

        if not url:
            return Response(
                {"detail": "Não foi possível abrir seu navegador agora."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"url": url, "expires_in_minutes": self.HANDOFF_TTL_MINUTES})

# ── Passkey: entrar com o rosto, sem código nenhum ───────────────────
#
# ⚠️ A regra de segurança que decide o desenho: **cadastrar passkey exige identidade FORTE**.
# Uma sessão que só conhece o número (chegou por link de campanha, e mensagem se encaminha)
# não pode gravar uma credencial na conta de alguém — seria alguém cadastrando o PRÓPRIO rosto
# no acesso de outra pessoa, e para sempre. Então cadastro pede confirmação antes; entrar, não.


def _passkey_credential(request) -> dict:
    payload = request.data if hasattr(request, "data") else {}
    credential = (payload or {}).get("credential")
    return credential if isinstance(credential, dict) else {}


class PasskeyRegisterOptionsView(APIView):
    """POST /api/v1/auth/passkey/register/options/ — o desafio para criar a credencial."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    @extend_schema(tags=["auth"], summary="Options to enroll a passkey")
    def post(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Entre na sua conta para continuar."}, status=401)
        if not auth_service.passkey_enabled():
            return Response({"detail": "Recurso indisponível."}, status=503)
        if knows_only_the_number(request):
            # Cadastrar credencial é o ato mais consequente da conta: vale para sempre. Quem
            # só provou o número confirma antes — e a tela já sabe oferecer esse toque.
            return Response(
                {
                    "detail": "Confirme que é você para ativar o acesso rápido.",
                    "error_code": "identity_confirmation_required",
                },
                status=403,
            )
        try:
            return Response(auth_service.passkey_registration_options(request, customer=customer))
        except Exception:
            logger.warning("passkey_register_options_failed", exc_info=True)
            return Response({"detail": "Não foi possível preparar agora."}, status=503)


class PasskeyRegisterView(APIView):
    """POST /api/v1/auth/passkey/register/ — guarda a chave pública que o aparelho criou."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    @extend_schema(tags=["auth"], summary="Finish enrolling a passkey")
    def post(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Entre na sua conta para continuar."}, status=401)
        if knows_only_the_number(request):
            return Response(
                {
                    "detail": "Confirme que é você para ativar o acesso rápido.",
                    "error_code": "identity_confirmation_required",
                },
                status=403,
            )

        credential = _passkey_credential(request)
        if not credential:
            return Response({"detail": "Pedido incompleto.", "field": "credential"}, status=400)

        label = str((request.data or {}).get("label") or "").strip()
        try:
            result = auth_service.passkey_register(
                request, customer=customer, credential=credential, label=label,
            )
        except auth_service.passkey_error() as err:
            return Response({"detail": str(err)}, status=400)
        return Response({"ok": True, "credential_id": result.credential_id, "label": result.label})


class PasskeyLoginOptionsView(APIView):
    """POST /api/v1/auth/passkey/login/options/ — desafio de login, sem pedir telefone.

    Sem `allowCredentials`: o navegador oferece as credenciais que ELE tem para o nosso
    domínio. É isso que faz "entrar com o rosto" não precisar de identificação antes.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Options to sign in with a passkey")
    def post(self, request):
        if not auth_service.passkey_enabled():
            return Response({"detail": "Recurso indisponível."}, status=503)
        try:
            return Response(auth_service.passkey_login_options(request))
        except Exception:
            logger.warning("passkey_login_options_failed", exc_info=True)
            return Response({"detail": "Não foi possível preparar agora."}, status=503)


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch")
class PasskeyLoginView(APIView):
    """POST /api/v1/auth/passkey/login/ — verifica a assinatura e abre a sessão.

    A sessão nasce com identidade FORTE: a credencial só assina para o nosso domínio (imune a
    phishing) e exigimos rosto/digital/PIN. Não há nada a reduzir nem a confirmar depois.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Sign in with a passkey")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."}, status=429,
            )
        credential = _passkey_credential(request)
        if not credential:
            return Response({"detail": "Pedido incompleto.", "field": "credential"}, status=400)

        try:
            customer = auth_service.passkey_login(request, credential=credential)
        except auth_service.passkey_error() as err:
            return Response({"detail": str(err)}, status=400)

        request.session[IDENTITY_SESSION_KEY] = IDENTITY_DEVICE
        return Response({"ok": True, **_session_payload(customer)})
