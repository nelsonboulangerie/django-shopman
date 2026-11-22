"""A API pública da página do entregador da casa (DEV-2026-030, frente M2).

Sem login: a chave é o token do link (``CourierLink``) e o celular que confirmou ser do
entregador (cabeçalho ``X-Courier-Device``, a chave que a página gera e guarda). Plano
``docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md`` §4.2, §4.4 e §4.5.2.

- ``GET  rides/<token>/``          o momento da rota (ou a confirmação, se ninguém confirmou)
- ``POST rides/<token>/claim/``    "Sou o Diego, abrir": prende o link a este celular
- ``POST rides/<token>/events/``   os toques: ``depart``, ``deliver``, ``problem`` e ``theme``
  (o tema escolhido na página vai para o cadastro do entregador, #2648) e ``position``
  (a posição do celular com a rota na rua, a cada 15 s, #2509)
"""

from __future__ import annotations

from rest_framework import status as http
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import courier_links, own_fleet

DEVICE_HEADER = "HTTP_X_COURIER_DEVICE"

_REFUSALS = {
    courier_links.UNKNOWN: (http.HTTP_404_NOT_FOUND, "Este link não existe."),
    courier_links.BAD_DEVICE: (http.HTTP_400_BAD_REQUEST, "Abra o link pelo navegador do celular."),
    courier_links.OTHER_DEVICE: (http.HTTP_403_FORBIDDEN, "Esta rota está aberta em outro celular."),
}


def _private(response: Response) -> Response:
    # Endereço e telefone de cliente: nada de cache nem de indexação.
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


class _LinkView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def _access(self, request, token: str, *, claim: bool = False):
        device = request.META.get(DEVICE_HEADER, "")
        access = (courier_links.claim if claim else courier_links.resolve)(token, device)
        return access

    def _answer(self, access) -> Response:
        if access.state in _REFUSALS:
            code, detail = _REFUSALS[access.state]
            return _private(Response({"detail": detail, "moment": access.state}, status=code))
        if access.state == courier_links.UNCLAIMED:
            link = access.link
            return _private(Response({"moment": "confirm", "courier": link.courier.name,
                                      "theme": own_fleet.page_theme(link.courier)}))
        return _private(Response(own_fleet.ride_view(access.link)))


class CourierRideView(_LinkView):
    def get(self, request, token: str):
        return self._answer(self._access(request, token))


class CourierRideClaimView(_LinkView):
    def post(self, request, token: str):
        return self._answer(self._access(request, token, claim=True))


class CourierRideEventView(_LinkView):
    def post(self, request, token: str):
        access = self._access(request, token)
        if access.state != courier_links.OK:
            if access.state == courier_links.UNCLAIMED:
                return _private(Response({"detail": "Confirme que a rota é sua antes.", "moment": "confirm"},
                                         status=http.HTTP_409_CONFLICT))
            return self._answer(access)
        data = request.data if isinstance(request.data, dict) else {}
        action = str(data.get("action") or "")
        order_ref = str(data.get("order_ref") or "")
        try:
            if action == "depart":
                own_fleet.depart(access.link)
            elif action == "deliver":
                own_fleet.deliver(access.link, order_ref)
            elif action == "problem":
                own_fleet.report_problem(access.link, order_ref, str(data.get("kind") or ""),
                                         payment=str(data.get("payment") or ""))
            elif action == "position":
                own_fleet.report_position(access.link, data.get("lat"), data.get("lng"),
                                          accuracy=data.get("accuracy"), at=data.get("at"))
            elif action == "theme":
                own_fleet.remember_theme(access.link, str(data.get("theme") or ""))
            else:
                return _private(Response({"detail": "Ação desconhecida.", "field": "action"},
                                         status=http.HTTP_400_BAD_REQUEST))
        except own_fleet.OwnFleetRefused as refused:
            return _private(Response({"detail": str(refused)}, status=http.HTTP_409_CONFLICT))
        return _private(Response(own_fleet.ride_view(access.link)))
