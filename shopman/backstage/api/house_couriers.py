"""Os entregadores da casa no Gestor: quem leva, enviar a corrida e a escala de hoje.

DEV-2026-030, frente M3 (#2526). A regra mora em ``shopman.backstage.services.house_couriers``;
aqui só a porta HTTP, com a mesma permissão e o mesmo protocolo de intenção da corrida da
TaOn (``OrderCourierRideView``).
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.operations import _actor, _intention_receipt, _intention_response, _ride_number_input
from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.services import house_couriers
from shopman.backstage.services.exceptions import OrderConflict
from shopman.shop.services.own_fleet import NOTE_MAX


def _refs(raw) -> list[str]:
    return list(dict.fromkeys(str(ref).strip()[:64] for ref in raw if str(ref).strip()))


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="House couriers for the call sheet and today's shift",
                      responses={200: OpenApiResponse(description="Couriers.")}),
)
class HouseCouriersView(APIView):
    """Quem da casa pode levar: a escala de hoje, quem está na rua e o valor da tabela.

    ``?refs=A&refs=B`` (opcional, na ordem da rota): o valor da tabela de cada entregador na
    escala para estes pedidos. Sem ``refs``, só a escala (os chips "Entregadores de hoje").
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request):
        from shopman.shop.services import courier

        refs = _refs(request.GET.getlist("refs"))
        if len(refs) > courier.MAX_RIDE_STOPS:
            return Response({"detail": f"Escolha até {courier.MAX_RIDE_STOPS} pedidos.", "field": "refs",
                             "errors": {"refs": [f"Escolha até {courier.MAX_RIDE_STOPS} pedidos."]}}, status=400)
        return Response(house_couriers.crew(refs))


@extend_schema_view(
    post=extend_schema(tags=["backstage"], summary="Toggle a house courier on today's shift",
                       responses={200: OpenApiResponse(description="Couriers.")}),
)
class HouseCourierShiftView(APIView):
    """Liga e desliga a escala de hoje de um entregador da casa (``{"on_shift": true}``)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def post(self, request, ref: str):
        from shopman.backstage.services.exceptions import OrderError

        on_shift = request.data.get("on_shift")
        if not isinstance(on_shift, bool):
            return Response({"detail": "Diga se está na escala.", "field": "on_shift",
                             "errors": {"on_shift": ["Diga se está na escala."]}}, status=400)
        try:
            house_couriers.set_shift(ref, on_shift)
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=404)
        return Response(house_couriers.crew())


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="Read the committed result of a house courier ride intention",
                      responses={200: OpenApiResponse(description="Committed result."),
                                 202: OpenApiResponse(description="No committed result yet.")}),
)
class HouseCourierRideView(APIView):
    """A corrida vai para um entregador da casa: o link dele e o WhatsApp pronto.

    O mesmo protocolo de intenção da corrida da TaOn: ``expected_actor_id`` (quem a tela
    leu), uma ``Idempotency-Key`` por corrida e ``base_revisions`` (``{ref:
    courier.dispatch_revision}``, a revisão que a tela leu de CADA pedido, a da ação
    ``courier-dispatch`` da projeção). Corpo: ``refs`` (1 a ``courier.MAX_RIDE_STOPS``, na
    ordem da rota), ``courier`` (o ``ref`` do entregador), ``change_out`` (``{ref:
    "20,00"}``), ``machine`` (a maquininha da rota) e ``ride_number`` (o número que a tela
    mostrava) e ``note`` (a observação para o entregador, até 200 caracteres, mostrada na
    página do link).

    Responde ``ride_ref``, ``link_url`` (a página do entregador), ``whatsapp_url`` (abre o
    WhatsApp do dispositivo com o texto pronto) e ``detail`` ("Rota A enviada para Diego.").
    ``GET ?idempotency_key=`` lê o resultado sem executar nada.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"
    intention_operation = "house-courier-ride"

    def get(self, request):
        return _intention_receipt(request, operation=self.intention_operation, resource="")

    def post(self, request):
        from shopman.orderman.models import Order

        from shopman.shop.services import courier

        refs = request.data.get("refs")
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in refs) or not (
            1 <= len(set(refs)) <= courier.MAX_RIDE_STOPS
        ):
            message = f"Escolha de 1 a {courier.MAX_RIDE_STOPS} pedidos."
            return Response({"detail": message, "field": "refs", "errors": {"refs": [message]}}, status=400)
        who = request.data.get("courier")
        if not isinstance(who, str) or not who.strip():
            return Response({"detail": "Escolha quem leva.", "field": "courier",
                             "errors": {"courier": ["Escolha quem leva."]}}, status=400)
        change_out = request.data.get("change_out") or {}
        if not isinstance(change_out, dict) or any(
            not isinstance(value, str | int | float) for value in change_out.values()
        ):
            return Response({"detail": "Troco inválido.", "field": "change_out",
                             "errors": {"change_out": ["Troco inválido."]}}, status=400)
        machine = request.data.get("machine") or ""
        if not isinstance(machine, str):
            return Response({"detail": "Maquininha inválida.", "field": "machine",
                             "errors": {"machine": ["Maquininha inválida."]}}, status=400)
        ride_number, valid = _ride_number_input(request.data)
        if not valid:
            return Response({"detail": "Número de corrida inválido.", "field": "ride_number",
                             "errors": {"ride_number": ["Número de corrida inválido."]}}, status=400)
        note = request.data.get("note") or ""
        if not isinstance(note, str) or len(note.strip()) > NOTE_MAX:
            message = f"A observação cabe em até {NOTE_MAX} caracteres."
            return Response({"detail": message, "field": "note", "errors": {"note": [message]}}, status=400)
        note = note.strip()
        refs = _refs(refs)
        revisions = request.data.get("base_revisions")
        if not isinstance(revisions, dict):
            revisions = {}
        base = {ref: revisions[ref] for ref in refs if isinstance(revisions.get(ref), str) and revisions[ref]}
        if len(base) != len(refs):
            base = None
        change_out = {str(ref): str(value) for ref, value in change_out.items()}
        machine, who = machine.strip(), who.strip()
        found: dict[str, Order] = {}

        def prepare():
            found.update({order.ref: order for order in Order.objects.filter(ref__in=refs)})
            if len(found) != len(refs):
                return Response({"detail": "Algum pedido não existe mais. Atualize a fila."}, status=409)
            return None

        def send(expected):
            if not found and prepare() is not None:
                raise OrderConflict("Algum pedido não existe mais. Atualize a fila.")
            sent = house_couriers.send_ride(
                [found[ref] for ref in refs], who, actor=_actor(request), operator=request.user,
                change_out_raw=change_out, machine=machine, expected_revisions=expected, ride_number=ride_number,
                note=note,
            )
            return {"refs": refs, "ride_ref": sent.ride_ref, "link_url": sent.link_url,
                    "whatsapp_url": sent.whatsapp_url, "detail": sent.detail, "ride_number": sent.ride_number,
                    "ride_letter": courier.ride_letter(sent.ride_number)}

        return _intention_response(
            request, operation=self.intention_operation, resource="", base=base or "",
            inputs={"refs": refs, "courier": who, "change_out": change_out, "machine": machine,
                    "ride_number": ride_number, "note": note},
            execute=send, prepare=prepare, where="a fila",
        )


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="Read the committed result of a house ride gesture",
                      responses={200: OpenApiResponse(description="Committed result."),
                                 202: OpenApiResponse(description="No committed result yet.")}),
    post=extend_schema(tags=["backstage"], summary="House ride gesture from the counter",
                       responses={200: OpenApiResponse(description="Applied.")}),
)
class HouseRideGestureView(APIView):
    """Os gestos do balcão na corrida da casa (M3b, #2898): ``depart``, ``deliver``,
    ``resend`` e ``release``.

    Para quando o entregador está sem celular ou sem sinal: "Saiu" e "A47 entregue" pelo
    mesmo funil do link (fonte ``operator:<nome>``); "Reenviar o link" devolve o MESMO
    link e o WhatsApp pronto (``whatsapp_url``); "Soltar o link" solta o celular preso.
    Protocolo de intenção: ``expected_actor_id``, ``Idempotency-Key`` e ``base_revision``
    (a revisão da rota, da ação da projeção ``house``). ``deliver`` leva ``ref``.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"
    GESTURES = ("depart", "deliver", "resend", "release")

    def get(self, request, ride: str, gesture: str):
        if gesture not in self.GESTURES:
            return Response({"detail": "Gesto desconhecido."}, status=404)
        return _intention_receipt(request, operation=f"house-{gesture}", resource=ride)

    def post(self, request, ride: str, gesture: str):
        if gesture not in self.GESTURES:
            return Response({"detail": "Gesto desconhecido."}, status=404)
        ride = ride.strip()[:64]
        order_ref = request.data.get("ref") or ""
        if gesture == "deliver" and (not isinstance(order_ref, str) or not order_ref.strip()):
            return Response({"detail": "Diga qual pedido foi entregue.", "field": "ref",
                             "errors": {"ref": ["Diga qual pedido foi entregue."]}}, status=400)
        order_ref = order_ref.strip()[:64] if isinstance(order_ref, str) else ""

        def run(expected):
            actor = _actor(request)
            if gesture == "depart":
                return {"detail": house_couriers.depart(ride, actor=actor, expected=expected)}
            if gesture == "deliver":
                return {"detail": house_couriers.deliver(ride, order_ref, actor=actor, expected=expected)}
            house_couriers.check_revision(house_couriers.live_link(ride), expected)
            if gesture == "release":
                return {"detail": house_couriers.release(ride)}
            sent = house_couriers.resend(ride)
            return {"detail": sent.detail, "link_url": sent.link_url, "whatsapp_url": sent.whatsapp_url}

        return _intention_response(
            request, operation=f"house-{gesture}", resource=ride,
            inputs={"ref": order_ref} if gesture == "deliver" else {}, execute=run, where="a corrida",
        )


@extend_schema_view(
    post=extend_schema(tags=["backstage"], summary="House route slip bytes (ESC/POS, base64) with the link QR",
                       responses={200: OpenApiResponse(description="Slip payload."),
                                  409: OpenApiResponse(description="This station does not print.")}),
)
class HouseRideSlipView(APIView):
    """A via impressa da rota da casa, com o QR do link (#2406; decisão 2 do dono).

    O servidor compõe (``house_route_slip``) e a página relaia ao agente desta estação,
    como a Via Pedido. Sem impressora nesta estação, recusa ANTES de compor (409, com o
    motivo e o agente), para não carimbar uma primeira via que não saiu. A resposta diz se
    é 2ª via (``reprint``) e traz o agente da estação (``agent``) para a página imprimir.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def post(self, request, ride: str):
        import base64

        from shopman.backstage.api.operations import _station_device_agent
        from shopman.backstage.services import house_route_slip
        from shopman.backstage.services.exceptions import OrderError

        agent = _station_device_agent(request)
        if not (agent.get("can_print") and agent.get("agent_url")):
            reason = str(agent.get("reason") or "Este dispositivo não tem impressora.").strip()
            return Response({"detail": f"{reason} A via sai no dispositivo que tem impressora.", "agent": agent},
                            status=409)
        try:
            link = house_couriers.live_link(ride.strip()[:64])
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=409)
        reprint = house_route_slip.stamp_first_print(link)
        payload = house_route_slip.slip_bytes(link, link_url=house_couriers.link_url(link), reprint=reprint)
        return Response({
            "ok": True, "payload_b64": base64.b64encode(payload).decode("ascii"),
            "title": f"via-da-rota:{link.ride_ref}", "reprint": reprint, "agent": agent,
        })
