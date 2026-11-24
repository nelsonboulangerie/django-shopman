"""A sacola entre a loja e a conversa com a Nice (OC-16, C02; #3515; #3517).

Dois gestos, os dois pelo serviço de transferência (``shop.services.session_transfer``),
que decide autorização, revisão, reserva e diferenças. Aqui só se lê o
pedido, se chama o serviço e se aponta o navegador para a sacola do recibo.

- ``continue-in-conversation``: "Continuar pelo WhatsApp". OFERECE a sacola desta
  loja à conversa e guarda a oferta sob um código ``NB-`` (o mesmo mecanismo da
  entrada pelo WhatsApp). Não toca a sacola: quem aceita é a Nice, quando a
  mensagem chega pelo número verificado.
- ``bring``: "Trazer a sacola do WhatsApp". Oferece e aceita no mesmo gesto a sacola
  que a cliente tem aberta na conversa (``open_elsewhere``): os itens entram na
  sacola deste navegador (o mesmo item soma), sem pergunta.

Os dois só existem quando a projeção diz que são possíveis (X1); fora disso, o
servidor recusa com o motivo, e a tela não as mostra.
"""

from __future__ import annotations

import logging

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import session_transfer
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.identity import get_authenticated_customer, identity_strength, knows_only_the_number

logger = logging.getLogger(__name__)

#: O que a loja diz quando a passagem não aconteceu. Nada mudou em nenhuma das sacolas.
REFUSALS = {
    "no_cart": "Não há sacola com itens para levar.",
    "invalid_offer": "Não foi possível levar esta sacola. Sua sacola daqui continua como estava.",
    "not_authorized": "Esta sacola é de outra conta. Sua sacola daqui continua como estava.",
    "source_changed": "A outra sacola mudou. Toque de novo para trazer a versão nova.",
    "nothing_available": "Nenhum item da outra sacola está disponível aqui agora.",
    "transfer_unavailable": "A passagem da sacola entre a loja e o WhatsApp não está disponível agora.",
    "whatsapp_unavailable": "O WhatsApp da loja está indisponível agora. Sua sacola continua aqui.",
}


def _refused(code: str, *, http_status: int, request=None) -> Response:
    body = {"detail": REFUSALS.get(code, REFUSALS["invalid_offer"]), "error_code": code}
    if request is not None:
        from .surface import _cart_payload_after_mutation

        body["cart"] = _cart_payload_after_mutation(request)
    return Response(body, status=http_status)


def _bridge_channel() -> str:
    from shopman.storefront.concierge.service import transfer_bridge_channel

    bridge = transfer_bridge_channel()
    return bridge if bridge and bridge != STOREFRONT_CHANNEL_REF else ""


def _accept_here(request, offer) -> Response:
    """Aceita a oferta neste navegador: os itens entram na sacola dele, se ela já tem itens."""
    from .surface import _cart_payload_after_mutation

    customer = get_authenticated_customer(request)
    destination = session_transfer.TransferDestination(
        customer_ref=str(getattr(customer, "ref", "") or ""),
        identity_strength=identity_strength(request),
        session_key=str(request.session.get("cart_session_key") or ""),
        origin_channel=str(request.session.get("origin_channel") or ""),
    )
    try:
        receipt = session_transfer.accept(offer, dest_context=destination, actor="storefront")
    except session_transfer.TransferRefused as refused:
        logger.info("cart_transfer.refused code=%s", refused.code)
        return _refused(refused.code, http_status=status.HTTP_409_CONFLICT, request=request)
    request.session["cart_session_key"] = receipt.dest_session_key
    return Response(
        {"cart": _cart_payload_after_mutation(request),
         "cart_transfer": {"status": "accepted", "differences": receipt.differences}}
    )


@method_decorator(ratelimit(key="ip", rate="10/m", method="POST", block=False), name="dispatch")
class CartContinueInConversationView(APIView):
    """POST /api/v1/cart/continue-in-conversation/: "Continuar pelo WhatsApp".

    Oferece a sacola deste navegador à conversa com a Nice e devolve a mensagem
    pronta com o código ``NB-`` (``{code, message, deep_link, wa_number}``). A
    sacola daqui fica como está até a Nice aceitar.
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    throttle_classes = []

    @extend_schema(tags=["cart"], summary="Offer this cart to the conversation (WhatsApp)")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde um minuto.", "error_code": "rate_limited"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        bridge = _bridge_channel()
        from shopman.storefront.presentation.cart import nice_answers_this_customer

        if not bridge or knows_only_the_number(request) or not nice_answers_this_customer(request, bridge):
            return _refused("transfer_unavailable", http_status=status.HTTP_409_CONFLICT)
        customer = get_authenticated_customer(request)
        try:
            offer = session_transfer.offer(
                STOREFRONT_CHANNEL_REF,
                str(request.session.get("cart_session_key") or ""),
                bridge,
                customer_ref=str(getattr(customer, "ref", "") or ""),
                actor="storefront",
            )
            started = session_transfer.offer_to_conversation(offer)
        except session_transfer.TransferRefused as refused:
            if refused.code == "conversation_unavailable":
                return _refused("whatsapp_unavailable", http_status=status.HTTP_503_SERVICE_UNAVAILABLE)
            http_status = status.HTTP_403_FORBIDDEN if refused.code == "not_authorized" else status.HTTP_409_CONFLICT
            return _refused(refused.code, http_status=http_status)
        return Response(started)


class CartBringView(APIView):
    """POST /api/v1/cart/bring/ ``{channel}``: "Trazer a sacola do WhatsApp" (#3515).

    Só para a cliente que entrou com o próprio dispositivo e tem sacola aberta no
    canal pedido (a mesma régua de ``open_elsewhere``). Oferta e aceite no mesmo
    gesto; a sacola de lá continua intacta até o aceite, e o aceite repetido devolve
    o mesmo recibo (X4).
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    throttle_classes = []

    @extend_schema(tags=["cart"], summary="Bring the cart open in another channel to this browser")
    def post(self, request):
        from shopman.shop.projections import cart as cart_data

        channel = str((request.data or {}).get("channel") or "").strip()
        customer = get_authenticated_customer(request)
        if customer is None or knows_only_the_number(request) or not channel or channel != _bridge_channel():
            return _refused("transfer_unavailable", http_status=status.HTTP_409_CONFLICT)
        entry = next(
            (item for item in cart_data.open_elsewhere(customer.ref, STOREFRONT_CHANNEL_REF) if item.channel_ref == channel),
            None,
        )
        if entry is None:
            return _refused("no_cart", http_status=status.HTTP_409_CONFLICT, request=request)
        try:
            offer = session_transfer.offer(
                channel, entry.session_key, STOREFRONT_CHANNEL_REF, customer_ref=customer.ref, actor="storefront"
            )
        except session_transfer.TransferRefused as refused:
            return _refused(refused.code, http_status=status.HTTP_409_CONFLICT, request=request)
        return _accept_here(request, offer)
