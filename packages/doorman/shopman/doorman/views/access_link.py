"""
Access link views.
"""

import json
import logging
import secrets as secrets_mod

from django.conf import settings as django_settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..conf import get_customer_resolver, get_doorman_settings
from ..models import AccessLink
from ..services.access_link import AccessLinkService
from ..utils import normalize_phone, safe_redirect_url

logger = logging.getLogger("shopman.doorman.views.access_link")


@method_decorator(csrf_exempt, name="dispatch")
class AccessLinkCreateView(View):
    """
    Create an access link.

    POST /api/auth/access/create/  (application API)
    POST /auth/access/create/      (package-level include, when not shadowed)

    Request body:
    {
        "customer_id": "uuid",
        "subscriber_id": "manychat-id",
        "manychat_id": "manychat-id",
        "subscriber": {"id": "manychat-id", "first_name": "Ana", "whatsapp_id": "5543..."},
        "whatsapp_id": "5543...",
        "email": "ana@example.com",
        "audience": "web_checkout|web_account|web_support|web_general",
        "source": "manychat|api|internal",
        "ttl_minutes": 5,
        "next": "/pedido/ORD-001/",
        "metadata": {}
    }

    Response:
    {
        "access_url": "https://.../a/?t=...&next=...",
        "has_context": true,
        "has_cart_context": true,
        "handoff_attempted": true,
        "handoff_expired": false,
        "access_flow": "cart_handoff",
        "token": "...",
        "expires_at": "..."
    }
    """

    def post(self, request):
        # Authenticate via API key (H05)
        settings = get_doorman_settings()
        api_key = settings.ACCESS_LINK_API_KEY
        if not api_key and not django_settings.DEBUG:
            logger.error("AccessLinkCreateView: ACCESS_LINK_API_KEY is not configured — rejecting request.")
            return JsonResponse({"error": "Access link API not configured"}, status=503)
        if api_key:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            x_api_key = request.META.get("HTTP_X_API_KEY", "")
            provided_key = ""
            if auth_header.startswith("Bearer "):
                provided_key = auth_header[7:]
            elif x_api_key:
                provided_key = x_api_key

            if not provided_key or not secrets_mod.compare_digest(provided_key, api_key):
                return JsonResponse({"error": "Unauthorized"}, status=401)

        # Parse JSON
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        unrendered = self._unrendered_variables(data)
        if unrendered:
            logger.warning(
                "access_link.unrendered_manychat_variables fields=%s", ",".join(unrendered)
            )
            return JsonResponse(
                {
                    "error": (
                        "O ManyChat mandou a variavel sem renderizar em: "
                        + ", ".join(unrendered)
                        + ". Insira a variavel pelo seletor do ManyChat em vez de digitar "
                        "o nome entre chaves — nome digitado a mao nao e substituido."
                    ),
                    "error_code": "unrendered_variable",
                    "fields": unrendered,
                },
                status=422,
            )

        resolver = get_customer_resolver()
        customer, error_response = self._resolve_customer(data, resolver)
        if error_response:
            return error_response
        if not customer:
            return JsonResponse({"error": "Customer not found"}, status=404)

        if not customer.is_active:
            return JsonResponse({"error": "Customer inactive"}, status=400)

        # Fold the post-login destination into the token metadata so the entry
        # link carries no `next` query param (the consuming surface derives the
        # destination server-side from the token → no open-redirect surface).
        metadata = dict(data.get("metadata") or {})
        next_url = self._next_url(data)
        if next_url:
            metadata["next"] = safe_redirect_url(next_url, request)

        # Contexto do site (fluxo do botão): um código NB-XxXx guarda a sacola e o
        # destino numa sessão web anônima. Se ``access_code`` contém um NB-XxXx (o próprio
        # código ou a mensagem inteira do WhatsApp), consome (uso único) e dobra na metadata.
        # ``#menu`` puro é login orgânico pelo WhatsApp: não tenta handoff e não dispara aviso
        # de sacola expirada. ``next`` passa por safe_redirect_url; o resto (ex.:
        # cart_session_key) viaja opaco.
        handoff_attempted = False
        access_code = self._access_code_from_payload(data)
        if not access_code or not self._contains_code(access_code):
            # O corpo não trouxe o código. Em vez de exigir que o fluxo saiba QUAL
            # variável carrega o texto da mensagem — nome que muda por canal e por
            # conta, e que já custou dias aqui —, perguntamos ao ManyChat. Assim o
            # request precisa carregar só o `subscriber_id`, que ninguém erra.
            from_api = self._last_input_text_from_manychat(data, resolver)
            if from_api and self._contains_code(from_api):
                logger.info("access_link.code_from_manychat_api")
                access_code = from_api
        if access_code:
            from ..services.link_state import contains_code, pop_state

            if contains_code(str(access_code)):
                handoff_attempted = True
                state = pop_state(str(access_code))
                if isinstance(state, dict):
                    for key, value in state.items():
                        if key == "next":
                            if value:
                                metadata["next"] = safe_redirect_url(str(value), request)
                        elif value is not None and key not in metadata:
                            metadata[key] = value
                else:
                    # Código veio mas não resolveu (expirou/já usado): um handoff do site foi
                    # TENTADO e falhou — distinto do login orgânico (sem access_code). Marcamos
                    # para o exchange avisar que a sacola não veio (omotenashi: nunca sumir com
                    # a sacola em silêncio). O login em si nunca falha por isso.
                    metadata["handoff_expired"] = True
            elif not self._looks_like_plain_keyword(access_code):
                # Veio ALGUMA COISA no lugar do código, e não é o "#menu" seco do login
                # orgânico. Tratar isso como orgânico faz a sacola sumir CALADA — o cliente
                # monta o pedido, entra, e o carrinho não está lá. Foi assim que um
                # `Last Text Input` devolvendo URL de mídia do Instagram passou dias sem
                # ninguém ver: identidade certa, login certo, sacola no chão.
                logger.warning(
                    "access_link.access_code_invalid len=%d inicio=%r — a variável do "
                    "ManyChat não está trazendo o texto da mensagem do WhatsApp",
                    len(str(access_code)), str(access_code)[:40],
                )
                metadata["handoff_expired"] = True

        has_cart_context = bool(metadata.get("cart_session_key"))

        # QUEM PEDE O LINK RECEBE O LINK. Só as entradas por este endpoint pedem
        # entrega — o `{tracking_url}` de uma notificação de pedido nasce pelo
        # mesmo serviço, com a mesma `source`, e não pode virar mensagem extra.
        # Por isso a intenção é declarada aqui, e não deduzida da origem.
        if data.get("source", AccessLink.Source.MANYCHAT) == AccessLink.Source.MANYCHAT:
            metadata.setdefault("deliver", "manychat")
            # ENTREGAR PARA QUEM FALOU. Sem isto o envio resolvia o destinatário
            # pelo TELEFONE — e o resolver, não achando contato com aquele número,
            # CRIA um assinante novo no ManyChat. Contato nascido há segundos não
            # tem interação, então o ManyChat recusa o envio com o código 3011
            # ("última interação há 19521h"). Mandávamos para um estranho enquanto
            # a pessoa que acabou de escrever esperava.
            sender_subscriber_id = self._subscriber_id_from_payload(data)
            if sender_subscriber_id:
                metadata.setdefault("deliver_to", sender_subscriber_id)

        result = AccessLinkService.create_token(
            customer=customer,
            audience=data.get("audience", AccessLink.Audience.WEB_GENERAL),
            source=data.get("source", AccessLink.Source.MANYCHAT),
            ttl_minutes=data.get("ttl_minutes"),
            metadata=metadata,
        )
        if not result.success:
            return JsonResponse(
                {"error": result.error, "error_code": result.error_code},
                status=400,
            )

        response_data = {
            "access_url": self._build_access_url(result.token),
            "has_context": has_cart_context,
            "has_cart_context": has_cart_context,
            "handoff_attempted": handoff_attempted,
            "handoff_expired": bool(metadata.get("handoff_expired")),
            "access_flow": "cart_handoff" if has_cart_context else "menu",
            "token": result.token,
            "expires_at": result.expires_at,
        }

        return JsonResponse(response_data)

    @staticmethod
    def _next_url(data: dict) -> str | None:
        return data.get("next")

    @staticmethod
    def _build_access_url(token: str | None) -> str:
        """Delega: a URL de entrada tem UM construtor.

        Eram dois, e discordavam — a resposta trazia `{loja}/a?t=`, a mensagem
        trazia `{domínio}/auth/access/?t=`. Quem clicou na segunda tomou 404.
        """
        return AccessLinkService._build_url(token or "")

    @staticmethod
    def _subscriber_id_from_payload(data: dict) -> str:
        """O `subscriber_id` do ManyChat, venha ele aninhado ou no topo."""
        subscriber = data.get("subscriber") or data.get("manychat_subscriber") or {}
        value = (
            (subscriber.get("id") if isinstance(subscriber, dict) else None)
            or data.get("manychat_id")
            or data.get("subscriber_id")
        )
        return str(value).strip() if value else ""

    @staticmethod
    def _contains_code(value: str) -> bool:
        from ..services.link_state import contains_code

        return bool(value) and contains_code(str(value))

    @staticmethod
    def _last_input_text_from_manychat(data: dict, resolver) -> str:
        """A última mensagem do assinante, pedida ao ManyChat pelo `subscriber_id`.

        Capacidade OPCIONAL do resolver (mesmo padrão de `upsert_manychat_subscriber`):
        sem ela, nada muda. Nunca derruba o login — o access link vale mesmo sem a
        sacola, e uma API lenta não pode virar porta fechada.
        """
        if data.get("source", AccessLink.Source.MANYCHAT) != AccessLink.Source.MANYCHAT:
            return ""
        subscriber = data.get("subscriber") or data.get("manychat_subscriber") or {}
        subscriber_id = (
            (subscriber.get("id") if isinstance(subscriber, dict) else None)
            or data.get("manychat_id")
            or data.get("subscriber_id")
        )
        if not subscriber_id or not hasattr(resolver, "manychat_last_input_text"):
            return ""
        try:
            return str(resolver.manychat_last_input_text(str(subscriber_id)) or "")
        except Exception:
            logger.warning(
                "access_link.manychat_last_input_failed subscriber=%s", subscriber_id, exc_info=True
            )
            return ""

    @staticmethod
    def _looks_like_plain_keyword(value: str) -> bool:
        """O ``#menu`` seco (com ou sem pontuação) é login orgânico legítimo, não defeito."""
        return len(str(value).strip()) <= 16

    @staticmethod
    def _unrendered_variables(data: dict, _prefix: str = "") -> list[str]:
        """Campos cujo value ainda é ``{{alguma_coisa}}`` — variável não substituída.

        No ManyChat, variável DIGITADA à mão no corpo do request não é substituída:
        chega a string literal. Ela some no `normalize_phone` (vira vazio) e o pedido
        morre com "faltou whatsapp_id", que manda procurar o campo errado — foi o que
        escondeu, por dias, um `{{phone}}` num lugar onde o ManyChat nunca teve campo
        `phone`. Dizer o nome do campo e o que fazer custa uma linha e devolve a tarde.
        """
        found: list[str] = []
        for key, value in (data or {}).items():
            path = f"{_prefix}{key}"
            if isinstance(value, dict):
                found.extend(AccessLinkCreateView._unrendered_variables(value, f"{path}."))
            elif isinstance(value, str):
                stripped = value.strip()
                if stripped.startswith("{{") and stripped.endswith("}}"):
                    found.append(path)
        return found

    @staticmethod
    def _access_code_from_payload(data: dict) -> str:
        fields = (
            "access_code",
            "state_code",
            "code",
            "last_input_text",
            "last_text_input",
            "message",
            "text",
        )
        for field in fields:
            value = data.get(field)
            if value:
                return str(value)

        for container_name in ("metadata", "custom_fields", "fields"):
            container = data.get(container_name)
            if not isinstance(container, dict):
                continue
            for field in fields:
                value = container.get(field)
                if value:
                    return str(value)
        return ""

    @classmethod
    def _resolve_customer(cls, data: dict, resolver):
        customer_id = data.get("customer_id")
        source = data.get("source", AccessLink.Source.MANYCHAT)
        manychat_id = data.get("manychat_id") or data.get("subscriber_id")

        if customer_id:
            payload, error_response = cls._access_identity_payload(data, manychat_id)
            if error_response:
                return None, error_response
            if payload:
                error_response = cls._manychat_whatsapp_id_guard(
                    source=source,
                    channel=cls._source_channel(data),
                    payload=payload,
                )
                if error_response:
                    return None, error_response
                if not hasattr(resolver, "upsert_access_link_customer"):
                    return None, JsonResponse({"error": "Access-link customer enrichment unsupported"}, status=400)
                try:
                    customer = resolver.upsert_access_link_customer(customer_id, payload)
                except ValueError as exc:
                    logger.warning("Access-link customer enrichment rejected: %s", exc)
                    return None, JsonResponse({"error": str(exc)}, status=409)
                return cls._guard_resolved_manychat_customer(data, source, customer)
            customer = resolver.get_by_uuid(customer_id)
            return cls._guard_resolved_manychat_customer(data, source, customer)

        subscriber = (
            data.get("subscriber")
            or data.get("manychat_subscriber")
            or cls._subscriber_from_top_level(data, manychat_id)
        )

        if source == AccessLink.Source.MANYCHAT and subscriber:
            if not isinstance(subscriber, dict):
                return None, JsonResponse({"error": "subscriber must be an object"}, status=400)
            subscriber = {**subscriber}
            if manychat_id and not subscriber.get("id"):
                subscriber["id"] = manychat_id
            if not subscriber.get("id"):
                return None, JsonResponse({"error": "subscriber.id required"}, status=400)
            if not hasattr(resolver, "upsert_manychat_subscriber"):
                return None, JsonResponse({"error": "ManyChat subscriber resolution unsupported"}, status=400)
            try:
                customer = resolver.upsert_manychat_subscriber(subscriber)
            except ValueError as exc:
                logger.warning("ManyChat subscriber resolution rejected: %s", exc)
                return None, JsonResponse({"error": str(exc)}, status=409)
            return cls._guard_resolved_manychat_customer(data, source, customer)

        if source == AccessLink.Source.MANYCHAT and manychat_id:
            if not hasattr(resolver, "get_by_identifier"):
                return None, JsonResponse({"error": "ManyChat identifier resolution unsupported"}, status=400)
            customer = resolver.get_by_identifier("manychat", manychat_id)
            return cls._guard_resolved_manychat_customer(data, source, customer)

        email = data.get("email")
        if email:
            return resolver.get_by_email(email), None

        return None, JsonResponse(
            {"error": "customer_id, subscriber_id, manychat_id, whatsapp_id or email required"},
            status=400,
        )

    @staticmethod
    def _access_identity_payload(data: dict, manychat_id: str | None):
        subscriber = data.get("subscriber") or data.get("manychat_subscriber")
        if subscriber is not None and not isinstance(subscriber, dict):
            return None, JsonResponse({"error": "subscriber must be an object"}, status=400)

        payload = {**subscriber} if isinstance(subscriber, dict) else {}
        if manychat_id and not payload.get("id"):
            payload["id"] = manychat_id

        fields = (
            "whatsapp_id",
            "first_name",
            "last_name",
            "email",
            "ig_id",
            "ig_username",
            "fb_id",
            "tg_id",
            "custom_fields",
        )
        for field in fields:
            if data.get(field) is not None:
                payload[field] = data[field]

        return (payload or None), None

    @classmethod
    def _manychat_whatsapp_id_guard(
        cls,
        *,
        source: str,
        channel: str,
        payload: dict | None,
    ):
        """Enriquecimento de um customer JÁ identificado (caminho ``customer_id``).

        Aqui o telefone é o dado que está sendo GRAVADO, então exigi-lo é o certo:
        enriquecer um cadastro com um whatsapp_id vazio só sujaria o registro.

        ⚠️ Este guard NÃO vale para o caminho do ``subscriber``. Ali ele rejeitava
        ANTES de saber de quem se tratava, e derrubava quem a casa já conhece: uma
        pessoa que chegou pelo Instagram tem ``subscriber_id`` e não tem
        ``whatsapp_id``, e levava 422 mesmo com cadastro e telefone no banco. Quem
        decide lá é o ``sync_subscriber`` — que já tem a regra certa (cliente
        conhecido com telefone passa; desconhecido sem telefone é recusado) — mais o
        ``_guard_resolved_manychat_customer``, que mantém a invariante de que todo
        access link do ManyChat cai num customer com telefone.
        """
        if source != AccessLink.Source.MANYCHAT:
            return None
        if channel == "instagram":
            return None
        if cls._payload_whatsapp_id(payload or {}):
            return None
        return JsonResponse(
            {"error": "ManyChat WhatsApp access link requires a valid whatsapp_id."},
            status=422,
        )

    @classmethod
    def _guard_resolved_manychat_customer(cls, data: dict, source: str, customer):
        if (
            source == AccessLink.Source.MANYCHAT
            and cls._source_channel(data) != "instagram"
            and customer
            and not customer.phone
        ):
            return None, JsonResponse(
                {"error": "ManyChat customer has no persisted phone."},
                status=422,
            )
        return customer, None

    @staticmethod
    def _source_channel(data: dict) -> str:
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            return ""
        return str(metadata.get("channel") or "").strip().lower()

    @staticmethod
    def _payload_whatsapp_id(payload: dict) -> str:
        return normalize_phone(str(payload.get("whatsapp_id") or ""))

    @staticmethod
    def _subscriber_from_top_level(data: dict, manychat_id: str | None) -> dict | None:
        if not manychat_id:
            return None
        fields = (
            "whatsapp_id",
            "first_name",
            "last_name",
            "email",
            "ig_id",
            "ig_username",
            "fb_id",
            "tg_id",
            "custom_fields",
        )
        subscriber = {"id": manychat_id}
        for field in fields:
            if data.get(field) is not None:
                subscriber[field] = data[field]
        return subscriber


class AccessLinkExchangeView(View):
    """
    Exchange an access link for a session.

    GET /auth/access/?t=TOKEN

    On success: Redirects to LOGIN_REDIRECT_URL
    On failure: Renders access_link_invalid.html
    """

    def get_template_name(self):
        """Get template name from settings."""
        settings = get_doorman_settings()
        return settings.TEMPLATE_ACCESS_LINK_INVALID

    def get(self, request):
        settings = get_doorman_settings()
        token = request.GET.get("t")
        if not token:
            return render(
                request,
                self.get_template_name(),
                {"error": str(_("Token não informado."))},
            )

        result = AccessLinkService.exchange(
            token,
            request,
            preserve_session_keys=settings.PRESERVE_SESSION_KEYS,
        )

        if result.success:
            next_url = safe_redirect_url(request.GET.get("next"), request)
            return redirect(next_url)
        else:
            return render(
                request,
                self.get_template_name(),
                {"error": result.error},
            )
