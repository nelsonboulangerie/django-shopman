"""A via impressa da rota do entregador da casa, com o QR do link (#2406, DEV-2026-030).

Decisão 2 do dono (16/11/2026): o entregador da casa recebe a rota pelo link no WhatsApp
E por uma via impressa com o QR do MESMO link. O papel diz o que a página do link diz
no balcão (plano §4.2): a letra da rota, quem leva, as paradas na ordem do percurso com o
primeiro nome, o endereço, o complemento e as instruções, o que cobrar em cada uma, as
sacolas, a maquininha e o recado da loja. Telefone do cliente não sai (§4.4: só como
botão no link, enquanto a parada está aberta). CPF nunca.

Quem compõe é o servidor, pelas mesmas peças do ESC/POS do balcão (``receipt_escpos``);
o agente da estação só entrega os bytes. A primeira impressão fica carimbada em cada
pedido da rota (``courier.slip_printed_at``), e a segunda sai marcada "2a VIA".
"""

from __future__ import annotations

from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.services import receipt_escpos as escpos
from shopman.shop.models.delivery_service import CourierLink

#: A chave do carimbo da primeira via, no bloco ``courier`` de cada pedido da rota.
STAMP = "slip_printed_at"


def _money(value_q: int) -> str:
    from shopman.utils.monetary import format_money

    return f"R$ {format_money(int(value_q or 0))}"


def _stop_lines(stop: dict) -> bytes:
    out = bytearray()
    bags = int(stop.get("bags") or 0)
    head = f"{stop['code']} · {stop['name']}" if stop.get("name") else stop["code"]
    out += escpos._pair(head, f"{bags} {'sacola' if bags == 1 else 'sacolas'}" if bags else "")
    for text in (stop.get("street"), stop.get("complement"), stop.get("neighborhood")):
        for line in escpos._wrap(text, escpos.COLUMNS) if text else []:
            out += escpos._line(line)
    if stop.get("instructions"):
        for line in escpos._wrap(f"Obs.: {stop['instructions']}", escpos.COLUMNS):
            out += escpos._line(line)
    receive = stop.get("receive") or {}
    cash_q, card_q = int(receive.get("cash_q") or 0), int(receive.get("card_q") or 0)
    if cash_q:
        out += escpos._pair("Receber em dinheiro", _money(cash_q))
        if receive.get("pays_with_q"):
            out += escpos._pair("Paga com", _money(receive["pays_with_q"]))
            out += escpos._pair("Troco para o cliente", _money(receive.get("change_back_q") or 0))
    if card_q:
        out += escpos._pair("Receber na maquininha", _money(card_q))
    if not cash_q and not card_q:
        out += escpos._line("Pago. Não cobre nada.")
    return bytes(out)


def slip_bytes(link: CourierLink, *, link_url: str, reprint: bool = False, shop_name: str = "") -> bytes:
    """Os bytes da via da rota, com o QR do link no fim."""
    from shopman.shop.services import courier, own_fleet

    orders = own_fleet._ride_orders(link)
    live = [order for order in orders if own_fleet._live(order, link)]
    first = courier.get_block(orders[0]) if orders else {}
    number = first.get("ride_number")
    many = len(orders) > 1
    title = f"ROTA {courier.ride_letter(number)}" if many and number else (
        f"PEDIDO {own_fleet._order_label(orders[0])}" if orders else "ROTA")
    value_q = (first.get("estimate") or {}).get("value_q")

    out = bytearray()
    out += bytes([escpos.ESC, ord("@")])
    out += bytes([escpos.ESC, ord("t"), escpos.CODE_PAGE])
    out += escpos._store_heading(shop_name)
    out += escpos._centered("Via do entregador da casa")
    if reprint:
        out += escpos._centered("*** 2a VIA ***")
    out += escpos._rule()
    out += escpos._double(title)
    leva = f"{link.courier.name} leva"
    out += escpos._pair(leva, _money(value_q) if isinstance(value_q, int) and value_q > 0 else "")
    out += escpos._line(f"{len(live)} {'parada' if len(live) == 1 else 'paradas'}, nesta ordem")
    out += escpos._rule()
    for order in live:
        out += _stop_lines(own_fleet._stop_view(order, link, on_route=False))
        out += escpos._rule()
    machine = next((((o.data or {}).get("dispatch") or {}).get("device_label") for o in live
                    if ((o.data or {}).get("dispatch") or {}).get("device_label")), "")
    if machine:
        out += escpos._line(f"Leva a {own_fleet_machine_text(machine)}")
    note = str(first.get("note") or "").strip()
    if note:
        for line in escpos._wrap(f"Recado da loja: {note}", escpos.COLUMNS):
            out += escpos._line(line)
    if machine or note:
        out += escpos._rule()
    out += escpos._centered("Aponte a câmera do celular")
    out += escpos._centered("para abrir a rota")
    out += escpos._qr(link_url)
    # A mesma moldura da via do entregador: documento não fiscal, destacado (Ajuste
    # SINIEF 19/16, cláusula décima, § 4º), porque o papel sai da casa com a sacola.
    out += escpos._line("")
    out += escpos._double("NÃO É DOCUMENTO FISCAL")
    out += escpos._line("")
    out += bytes([escpos.ESC, ord("d"), 4])
    out += bytes([escpos.GS, ord("V"), 1])  # corte parcial
    return bytes(out)


def own_fleet_machine_text(label: str) -> str:
    """ "maquininha Azul": o nome da maquininha como a casa fala, sem repetir a palavra."""
    text = label.strip()
    return text[0].lower() + text[1:] if text.lower().startswith("maquininha") else f"maquininha {text}"


def stamp_first_print(link: CourierLink) -> bool:
    """Carimba a primeira via em cada pedido da rota. Devolve se esta é uma 2ª via."""
    from django.db import transaction

    from shopman.shop.services import courier

    with transaction.atomic():
        orders = list(Order.objects.select_for_update().filter(ref__in=link.order_refs or []))
        reprint = any(courier.get_block(order).get(STAMP) for order in orders)
        if not reprint:
            now = timezone.now().isoformat()
            for order in orders:
                data = dict(order.data or {})
                block = dict(data.get("courier") or {})
                if block.get("ride_ref") != link.ride_ref:
                    continue
                block[STAMP] = now
                data["courier"] = block
                Order.objects.filter(pk=order.pk).update(data=data)
    return reprint
