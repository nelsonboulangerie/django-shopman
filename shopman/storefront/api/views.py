from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.utils.phone import normalize_phone

from shopman.shop.services import checkout as checkout_service
from shopman.shop.services import sessions as session_service
from shopman.storefront.api import clean_name
from shopman.storefront.cart import CHANNEL_REF
from shopman.storefront.identity import knows_only_the_number
from shopman.storefront.services import orders as order_service

from .serializers import (
    CheckoutResponseSerializer,
    CheckoutSerializer,
    DetailSerializer,
)

logger = logging.getLogger(__name__)


CHECKOUT_RATE_LIMIT_RETRY_SECONDS = 60


def _cart_data(request):
    """Resolve the cart DATA projection for the current visitor (checkout commit).

    Reads the orchestrator read-side (``shop.projections.cart.CartProjection``).
    """
    from shopman.shop.projections.cart import build_cart

    return build_cart(request.session.get("cart_session_key"), CHANNEL_REF)


# Chaves de IDENTIDADE do cliente que o commit precisa preservar:
# - ``ref``: elegibilidade de promoção por pessoa (aniversário, segmento RFM);
# - ``price_tier``: a faixa que decide o preço (staff, atacado).
#
# As duas já estavam na sessão (a loja as grava a cada mexida na sacola, em
# ``storefront/cart.py:_customer_link``) e o ``set_data`` de ``customer`` no
# commit substituía o bloco inteiro, derrubando ambas. Era isso que fazia a
# projeção e o commit discordarem: a tela mostrava o desconto e o envio cobrava
# cheio, com a guarda de preço recusando o pedido.
#
# O guarda do benefício de funcionário NÃO mora aqui — mora na regra
# (``EmployeeRule.pickup_only``), que é onde a política pertence e onde o dono
# pode mexer sem código.
#
# Nome e telefone não entram: o cliente os reescreve no formulário a cada envio,
# então vêm do payload.
_CUSTOMER_IDENTITY_KEYS = ("ref", "price_tier")


def _session_customer_identity(session_key: str) -> dict:
    """Devolve a identidade do cliente já gravada na sessão, para o commit não apagá-la.

    Ver o comentário no ``checkout_data`` do ``CheckoutView``: o ``set_data`` de
    ``customer`` substitui o bloco inteiro, então quem envia precisa recarregar o
    que já estava lá.
    """
    from shopman.shop.services.cart import get_open_session

    session = get_open_session(session_key=session_key, channel_ref=CHANNEL_REF)
    if session is None:
        return {}
    existing = (session.data or {}).get("customer") or {}
    return {k: existing[k] for k in _CUSTOMER_IDENTITY_KEYS if existing.get(k)}


# Rate-limit MANUAL (is_ratelimited): só a tentativa que chega ao commit
# incrementa o contador — cliente corrigindo erro de formulário não pode
# tomar 429 no momento mais crítico do pedido.
class CheckoutView(APIView):
    """
    POST /api/v1/checkout/

    Commit the cart as an order.
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    serializer_class = CheckoutSerializer

    @extend_schema(
        tags=["checkout"],
        summary="Commit cart as order",
        request=CheckoutSerializer,
        responses={
            201: CheckoutResponseSerializer,
            400: DetailSerializer,
            429: DetailSerializer,
        },
    )
    def post(self, request):
        if self._rate_limited(request, increment=False):
            return self._rate_limited_response()

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check cart has items
        cart = _cart_data(request)
        if cart.is_empty:
            return Response(
                {"detail": "Sua sacola está vazia."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_key = cart.session_key
        # O nome impresso no ticket do KDS: sanitiza controle/bidi (a serializer
        # ja limita o comprimento em 120) antes de gravar no pedido.
        name = clean_name(serializer.validated_data["name"], max_length=120)
        phone_raw = serializer.validated_data["phone"]
        notes = serializer.validated_data.get("notes", "")
        fulfillment_type = serializer.validated_data.get("fulfillment_type", "pickup")
        delivery_address = serializer.validated_data.get("delivery_address", "")
        saved_address_id = serializer.validated_data.get("saved_address_id")
        delivery_address_structured = serializer.validated_data.get("delivery_address_structured") or {}
        delivery_complement = serializer.validated_data.get("delivery_complement", "")
        delivery_instructions = serializer.validated_data.get("delivery_instructions", "")
        delivery_date = serializer.validated_data.get("delivery_date", "")
        delivery_time_slot = serializer.validated_data.get("delivery_time_slot", "")
        payment_method = serializer.validated_data.get("payment_method", "")
        use_loyalty = serializer.validated_data.get("use_loyalty", False)
        idempotency_key = serializer.validated_data.get("idempotency_key") or session_service.new_idempotency_key()

        if fulfillment_type != "delivery":
            saved_address_id = None
            delivery_address = ""
            delivery_address_structured = {}
            delivery_complement = ""
            delivery_instructions = ""

        if not delivery_date and (fulfillment_type == "delivery" or delivery_time_slot):
            return Response(
                {"detail": "Escolha a data.", "field": "delivery_date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard autoritativo: nunca confirmar pedido para um dia fechado
        # (fim de semana fora do expediente, feriado, férias coletivas). A UI
        # já evita oferecer, mas o commit não bloqueia data futura — então o
        # servidor é a última linha. Prometer dia fechado seria gravíssimo.
        if delivery_date:
            from datetime import date as _date

            from shopman.shop.services import business_calendar

            try:
                _parsed_date = _date.fromisoformat(delivery_date)
            except ValueError:
                _parsed_date = None
            if _parsed_date is not None:
                # Bordas de data: encomenda no passado nunca é pedido válido, e a
                # janela de encomenda tem teto (max_preorder_days). is_open_on é
                # cego a ambos, então esta é a guarda autoritativa (o caminho
                # HTMX que validava isso está morto).
                _today_local = timezone.localdate()
                if _parsed_date < _today_local:
                    message = "Não é possível encomendar para uma data passada."
                    return Response(
                        {"detail": message, "field": "delivery_date", "errors": {"delivery_date": message}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                from datetime import timedelta as _timedelta

                from shopman.shop.projections import checkout_context

                _max_preorder_days, _ = checkout_context.preorder_config()
                _max_date = _today_local + _timedelta(days=_max_preorder_days)
                if _parsed_date > _max_date:
                    message = f"Data máxima permitida: {_max_date.strftime('%d/%m/%Y')}."
                    return Response(
                        {"detail": message, "field": "delivery_date", "errors": {"delivery_date": message}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not business_calendar.is_open_on(_parsed_date):
                    message = "Estamos fechados nesse dia. Escolha outra data."
                    return Response(
                        {
                            "detail": message,
                            "field": "delivery_date",
                            "errors": {"delivery_date": message},
                            **_closed_shop_hint(),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Eixo de HORA: dia operante mas já encerrado hoje (entrega e
                # retirada). is_open_on é cego à hora — esta é a última linha.
                _state = business_calendar.current_business_state()
                _today = _state.resolved_at.date() if _state.resolved_at else None
                if _parsed_date == _today and _state.closure_source == "after_close":
                    message = "Já encerramos o atendimento de hoje. Escolha outra data."
                    return Response(
                        {
                            "detail": message,
                            "field": "delivery_date",
                            "errors": {"delivery_date": message},
                            **_closed_shop_hint(),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        if fulfillment_type == "delivery" and delivery_time_slot and delivery_date:
            # Aba antiga do checkout: slot de entrega de HOJE que já passou
            # não vira pedido impossível para a operação.
            slot_error = _delivery_slot_in_past_error(delivery_time_slot, delivery_date)
            if slot_error:
                return Response(
                    {
                        "detail": slot_error,
                        "field": "delivery_time_slot",
                        "errors": {"delivery_time_slot": slot_error},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if fulfillment_type == "pickup":
            from shopman.storefront.services.pickup_slots import validate_pickup_slot_selection

            try:
                now_local = timezone.localtime().time().replace(second=0, microsecond=0)
            except (ValueError, KeyError):
                now_local = None
            slot_error = validate_pickup_slot_selection(
                delivery_time_slot,
                delivery_date=delivery_date,
                cart_skus=[str(line.sku) for line in cart.lines if line.sku],
                now=now_local,
            )
            if slot_error:
                return Response(
                    {
                        "detail": slot_error,
                        "field": "delivery_time_slot",
                        "errors": {"delivery_time_slot": slot_error},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if fulfillment_type == "delivery" and saved_address_id:
            saved_payload, saved_error = _saved_address_payload(request, saved_address_id)
            if saved_error:
                return Response(saved_error, status=status.HTTP_400_BAD_REQUEST)
            if saved_payload:
                # ⚠️ O endereço SALVO manda, não o texto que veio do cliente. A precedência
                # era a inversa (`delivery_address or salvo`), e isso é errado por dois
                # motivos: (1) escolher um endereço por `id` e mandar outro texto junto
                # entregaria em lugar diferente do escolhido; (2) com o endereço reduzido em
                # sessão que só conhece o número, o texto que a tela tem é "Centro ·
                # Londrina" — e o entregador receberia isso como endereço.
                #
                # O `id` é a escolha; o texto é só desenho. Quem escolhe salvo, entrega no
                # salvo.
                delivery_address = saved_payload["formatted_address"]
                delivery_address_structured = {
                    **_clean_structured_address(delivery_address_structured),
                    **saved_payload["structured"],
                }

        if fulfillment_type == "delivery":
            structured = _clean_structured_address(delivery_address_structured)
            delivery_address = delivery_address or str(structured.get("formatted_address") or "")
            if not delivery_address.strip():
                return Response(
                    {
                        "detail": "Informe o endereço de entrega.",
                        "field": "delivery_address",
                        "errors": {"delivery_address": "Informe o endereço de entrega."},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            delivery_address_structured = structured

        # ⚠️ A única rota de perda MATERIAL que uma sessão de link abria: gastar os pontos
        # da pessoa num pedido entregue num endereço digitado na hora. Pontos valem onde ela
        # já vai — endereço salvo ou balcão. Custo para quem é dona de verdade: nenhum, e o
        # aparelho dela é conhecido de qualquer forma. Ver `storefront/identity.py`.
        if use_loyalty and knows_only_the_number(request):
            if fulfillment_type == "delivery" and not saved_address_id:
                message = (
                    "Para usar seus pontos numa entrega em endereço novo, confirme que é "
                    "você. Em endereço já salvo ou retirando no balcão, pode usar agora."
                )
                return Response(
                    {
                        "detail": message,
                        "field": "use_loyalty",
                        # `error_code`, não `code`: é o nome que o dialeto de erro da casa
                        # usa para o código que ROTEIA a UI (docs/reference/errors.md), e o
                        # que a tela de checkout já lê. Dois nomes para a mesma pergunta e a
                        # tela reage a um só.
                        "error_code": "identity_confirmation_required",
                        "errors": {"use_loyalty": message},
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        phone = normalize_phone(phone_raw) or phone_raw

        # A identidade (``ref``/``price_tier``) que já está na sessão PRECISA
        # sobreviver ao envio. ``_build_ops_from_data`` vira um ``set_data`` em
        # ``customer``, que SUBSTITUI o bloco inteiro — mandar só nome+telefone
        # apagava o ``ref``, e sem ``ref`` o ``_resolve_customer_ctx`` do
        # discount modifier retorna cedo e nunca avalia ``is_birthday``. Efeito
        # observado no staging: o desconto de aniversário aparecia no checkout e
        # sumia no "Enviar pedido", o total subia e a guarda de integridade
        # recusava o pedido. O ``price_tier`` caía junto (atacado virava varejo).
        # Mesmo idioma de merge de `shop/services/cart.py` e `storefront/cart.py`.
        checkout_data = {
            "customer": {**_session_customer_identity(session_key), "name": name, "phone": phone},
            "fulfillment_type": fulfillment_type,
            # Omotenashi: lembrar escolhas é o default; toggle desmarcado → False.
            # (Endereço novo é salvo sempre, independente disto.)
            "save_as_default": serializer.validated_data.get("save_as_default", True),
        }
        if notes:
            checkout_data["order_notes"] = notes
        if delivery_address:
            checkout_data["delivery_address"] = delivery_address
        if saved_address_id:
            checkout_data["saved_address_id"] = saved_address_id
        if fulfillment_type == "delivery":
            structured = _clean_structured_address(delivery_address_structured)
            if delivery_complement:
                structured["complement"] = delivery_complement
            if delivery_instructions:
                structured["delivery_instructions"] = delivery_instructions
            if structured:
                checkout_data["delivery_address_structured"] = structured
        if delivery_date:
            checkout_data["delivery_date"] = delivery_date
        if delivery_time_slot:
            checkout_data["delivery_time_slot"] = delivery_time_slot
        if payment_method in {"pix", "card"}:
            checkout_data["payment"] = {"method": payment_method}
        elif payment_method == "cash":
            # Dinheiro também é método de pagamento: sem isso o operador não
            # sabe como cobrar — e o troco pedido pelo cliente se perdia.
            from shopman.storefront.intents.checkout import parse_change_for

            payment_data = {"method": "cash"}
            change_for_q = parse_change_for(serializer.validated_data.get("change_for", ""))
            if fulfillment_type == "delivery" and change_for_q:
                payment_data["change_for_q"] = change_for_q
            checkout_data["payment"] = payment_data

        # Presente (entrega para terceiro) — integridade antes do commit.
        from shopman.storefront.intents.gift import build_gift_data

        gift_data, gift_errors = build_gift_data(
            is_gift=serializer.validated_data.get("is_gift", False),
            fulfillment_type=fulfillment_type,
            recipient_name=clean_name(serializer.validated_data.get("recipient_name", ""), max_length=120),
            recipient_phone=serializer.validated_data.get("recipient_phone", ""),
            gift_message=serializer.validated_data.get("gift_message", ""),
            hide_values=serializer.validated_data.get("gift_hide_values", False),
        )
        if gift_errors:
            field, message = next(iter(gift_errors.items()))
            return Response(
                {"detail": message, "field": field, "errors": gift_errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if gift_data:
            checkout_data.update(gift_data)

        # Sempre gravar a chave: desmarcar o toggle precisa LIMPAR um resgate
        # aplicado numa tentativa anterior da mesma sessão (senão o desconto
        # stale sobrevive ao commit).
        checkout_data["loyalty"] = {}
        if use_loyalty:
            try:
                from shopman.shop.projections import checkout_context

                customer_info = getattr(request, "customer", None)
                loyalty_balance_q = checkout_context.loyalty_balance(
                    customer_info.uuid if customer_info else None
                )
                if loyalty_balance_q > 0:
                    checkout_data["loyalty"] = {"redeem_points_q": loyalty_balance_q}
            except Exception:
                logger.debug("views.post degraded; using fallback", exc_info=True)
                pass

        # Passou por todas as validações: agora sim a tentativa CONTA.
        if self._rate_limited(request, increment=True):
            return self._rate_limited_response()

        try:
            result = checkout_service.process(
                session_key=session_key,
                channel_ref=CHANNEL_REF,
                data=checkout_data,
                idempotency_key=idempotency_key,
                expected_total_q=serializer.validated_data.get("expected_total_q"),
            )
        except Exception as exc:
            logger.debug("views.post degraded; using fallback", exc_info=True)
            mapped = checkout_service.map_checkout_error(exc)
            if mapped:
                field, message = next(iter(mapped.items()))
                return Response(
                    {"detail": message, "field": field, "errors": mapped},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order_error = checkout_service.map_order_error(exc)
            if order_error is not None:
                return Response(
                    {
                        "detail": order_error.detail,
                        "error_code": order_error.error_code,
                        "context": order_error.context,
                    },
                    status=order_error.http_status,
                )
            raise

        # Clear cart
        order_service.grant_order_access(request, result.order_ref)
        order_service.mark_just_placed(request, result.order_ref)
        request.session.pop("cart_session_key", None)
        # PAYMENT-TRACKING-MERGE: pix/card não vão mais para uma tela de pagamento
        # à parte — o Pix/cartão aparecem inline no próprio acompanhamento.
        #
        # ⚠️ Rota do CLIENTE (Nuxt: `pages/pedido/[ref]/index.vue`), não a da API.
        # `/tracking/{ref}` é o endpoint (`/api/v1/tracking/{ref}/`); como URL de
        # navegação ela dá 404 — e o `finalizar.vue` faz `navigateTo(next_url)`
        # com fallback que nunca dispara, porque este campo vem sempre preenchido.
        # Resultado observado no staging: pedido criado e cliente na tela de 404.
        next_url = f"/pedido/{result.order_ref}"

        data = CheckoutResponseSerializer(
            {
                "order_ref": result.order_ref,
                "status": result.status,
                "next_url": next_url,
            }
        ).data
        return Response(data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _rate_limited(request, *, increment: bool) -> bool:
        from django_ratelimit.core import is_ratelimited

        return is_ratelimited(
            request,
            group="storefront.checkout",
            key="user_or_ip",
            rate="3/m",
            method="POST",
            increment=increment,
        )

    @staticmethod
    def _rate_limited_response() -> Response:
        return Response(
            {
                "detail": "Muitas tentativas. Aguarde alguns minutos.",
                "error_code": "rate_limited",
                "retry_after_seconds": CHECKOUT_RATE_LIMIT_RETRY_SECONDS,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(CHECKOUT_RATE_LIMIT_RETRY_SECONDS)},
        )


def _closed_shop_hint() -> dict:
    """Enriquece o erro de dia/horário fechado com o caminho adiante (omotenashi):
    quando reabrimos e a próxima data em que dá para encomendar. Aditivo — um
    front que só lê ``detail`` ignora sem quebrar; degrada silencioso se o cálculo
    de calendário falhar (nunca deixa o checkout 500 por causa de uma dica)."""
    from shopman.shop.omotenashi import resolve_copy
    from shopman.shop.services import business_calendar

    hint: dict = {}
    try:
        state = business_calendar.current_business_state()
        if state.next_open_at is not None:
            hint["next_open_at"] = state.next_open_at.isoformat()
        upcoming = business_calendar.available_dates(max_count=1)
        if upcoming:
            hint["earliest_available_date"] = upcoming[0].isoformat()
    except Exception:
        logger.debug("closed_shop_hint degraded", exc_info=True)
        return hint
    if hint:
        hint["preorder_hint"] = (
            resolve_copy("CHECKOUT_CLOSED_PREORDER_HINT", moment="*", audience="*").message
            or "Você pode encomendar para o próximo dia disponível."
        )
    return hint


def _delivery_slot_in_past_error(slot: str, delivery_date: str) -> str | None:
    """Slot "HH:MM-HH:MM" de HOJE cujo fim já passou → erro acionável."""
    import re
    from datetime import date as _date

    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})\s*$", slot or "")
    if not match:
        return None  # formato livre (ex.: "manhã") — sem eixo de hora para validar
    try:
        if _date.fromisoformat(delivery_date) != timezone.localdate():
            return None
    except ValueError:
        return None
    start = (int(match.group(1)), int(match.group(2)))
    end = (int(match.group(3)), int(match.group(4)))
    if end <= start:
        # Slot cruza a meia-noite (ex.: 22:00-02:00): o fim é amanhã, então
        # nunca "já passou" hoje. Sem eixo confiável — não bloquear.
        return None
    now_local = timezone.localtime()
    if (now_local.hour, now_local.minute) >= end:
        return "Esse horário já passou. Escolha outro horário de entrega."
    return None


_STRUCTURED_ADDRESS_FIELDS = (
    "formatted_address",
    "route",
    "street_number",
    "neighborhood",
    "city",
    "state_code",
    "postal_code",
    "country",
    "country_code",
    "latitude",
    "longitude",
    "place_id",
    "complement",
    "delivery_instructions",
)


def _clean_structured_address(value: dict | None) -> dict:
    """Os campos conhecidos do endereço, sem vazios e em tipo que o JSON aceita.

    ⚠️ O `Decimal` era o furo. Este dicionário vai para `Session.data`, que é JSONField, e
    `json.dumps` não serializa `Decimal` — então um endereço SALVO com coordenada (as do
    seed têm) derrubava o checkout com 500:

        TypeError: Object of type Decimal is not JSON serializable
        (modifiers.py:844 → session.save)

    Ficava escondido porque o app sempre manda o `delivery_address_structured` junto, com
    lat/lng em float, e o merge deixava o float por cima. Bastava um cliente escolher endereço
    salvo sem mandar os componentes para cair — e foi o que apareceu quando a precedência
    passou a ser "o salvo manda".

    Normalizar aqui, e não em quem chama, é o que garante que as DUAS fontes (o que a tela
    manda e o que o endereço salvo tem) saiam do mesmo jeito.
    """
    if not isinstance(value, dict):
        return {}
    cleaned: dict = {}
    for field in _STRUCTURED_ADDRESS_FIELDS:
        raw = value.get(field)
        if raw is None or raw == "":
            continue
        cleaned[field] = float(raw) if isinstance(raw, Decimal) else raw
    return cleaned


def _saved_address_payload(request, address_id: int | None) -> tuple[dict | None, dict | None]:
    if not address_id:
        return None, None
    from shopman.shop.services import account as account_service
    from shopman.storefront.identity import get_authenticated_customer

    customer = get_authenticated_customer(request)
    if not customer:
        return None, {"detail": "Entre novamente para usar este endereço.", "field": "saved_address_id"}
    # get_address já é escopado ao cliente: devolve None tanto para PK inexistente
    # quanto para PK de outro cliente. Um único 404 uniforme fecha o oráculo de
    # enumeração (403 vs 404 distinguível revelaria PKs válidos de terceiros).
    address = account_service.get_address(customer.ref, address_id)
    if not address:
        return None, {"detail": "Endereço não encontrado.", "field": "saved_address_id"}
    structured = _clean_structured_address({
        "formatted_address": address.formatted_address,
        "route": getattr(address, "route", "") or "",
        "street_number": getattr(address, "street_number", "") or "",
        "neighborhood": getattr(address, "neighborhood", "") or "",
        "city": getattr(address, "city", "") or "",
        "state_code": getattr(address, "state_code", "") or "",
        "postal_code": getattr(address, "postal_code", "") or "",
        "latitude": getattr(address, "latitude", None),
        "longitude": getattr(address, "longitude", None),
        "place_id": getattr(address, "place_id", "") or "",
        "complement": getattr(address, "complement", "") or "",
        "delivery_instructions": getattr(address, "delivery_instructions", "") or "",
    })
    return {
        "formatted_address": address.formatted_address,
        "structured": structured,
    }, None
