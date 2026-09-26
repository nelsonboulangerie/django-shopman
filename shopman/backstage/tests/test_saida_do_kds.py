"""A Saída do KDS em duas colunas, e o "Pronto" da estação sem tela.

Decisões do dono (26/09/2026):

- a Saída vê, além dos prontos para sair, os pedidos que ainda esperam alguma
  estação ("Em preparo"), com um chip por estação;
- a estação de tela dá baixa sozinha — o chip só mostra o estado;
- a estação SEM tela recebe o papel (Via Cozinha) e imprimir não dá baixa:
  quem conclui é a Saída ("Pronto" no chip), o PDV (card do ticket) ou o
  leitor de código;
- a ação tem critério: só estação sem tela, só os tickets daquela estação
  naquele pedido.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from shopman.cashman.models import Terminal
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket, PrintAgentCredential, PrintJob
from shopman.backstage.projections.kds import build_kds_board
from shopman.backstage.services import kitchen_ticket_print
from shopman.shop.models import Channel

pytestmark = pytest.mark.django_db


def _perm(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


@pytest.fixture
def saida(db):
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja"})
    return KDSInstance.objects.create(ref="saida", name="Saída", type="expedition")


@pytest.fixture
def lanches(db):
    terminal = Terminal.objects.create(ref="lanches-printer", label="Impressora Lanches")
    PrintAgentCredential.issue(terminal=terminal)
    return KDSInstance.objects.create(ref="lanches", name="Lanches", type="prep", print_terminal=terminal)


@pytest.fixture
def cafes(db):
    return KDSInstance.objects.create(ref="cafes", name="Cafés", type="prep")


def _order(ref: str, *, status=Order.Status.PREPARING, name: str = "Ana") -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"sk-{ref}",
        status=status,
        total_q=1500,
        data={"customer": {"name": name}, "fulfillment_type": "pickup"},
    )


def _ticket(order: Order, station: KDSInstance, *, status: str = "pending", line: str = "L1") -> KDSTicket:
    return KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=station,
        status=status,
        items=[{"sku": "X", "name": "Item", "qty": 1, "line_id": line}],
    )


def _operator(username: str, *perms: tuple[str, str]) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for app_label, codename in perms:
        user.user_permissions.add(_perm(app_label, codename))
    return user


# ── A coluna "Em preparo" ──────────────────────────────────────────────────


def test_pedido_que_espera_estacao_aparece_em_preparo_com_um_chip_por_estacao(saida, lanches, cafes):
    order = _order("WEB-20260926-1234")
    _ticket(order, cafes, status="in_progress")
    _ticket(order, lanches)

    board = build_kds_board(saida.ref)

    assert board.tickets == ()  # nenhum pronto para sair
    assert board.counts["preparing"] == 1
    card = board.preparing[0]
    assert card.order_ref == order.ref
    assert card.customer_name == "Ana"
    chips = {chip.station_name: chip for chip in card.stations}
    assert chips["Cafés"].prints is False
    assert chips["Cafés"].state_label == "em preparo"
    assert chips["Cafés"].can_mark_ready is False  # a estação de tela dá baixa sozinha
    assert chips["Lanches"].prints is True
    assert chips["Lanches"].state_label == "na fila"
    assert chips["Lanches"].can_mark_ready is True


def test_estacao_de_tela_que_terminou_fica_no_card_como_pronta(saida, lanches, cafes):
    order = _order("WEB-20260926-1235")
    _ticket(order, cafes, status="done")
    _ticket(order, lanches)

    card = build_kds_board(saida.ref).preparing[0]

    chips = {chip.station_name: chip for chip in card.stations}
    assert chips["Cafés"].state == "done"
    assert chips["Cafés"].state_label == "pronto"
    # Quem ainda falta vem primeiro.
    assert card.stations[0].station_name == "Lanches"


def test_o_chip_da_estacao_sem_tela_diz_quando_o_papel_saiu(saida, lanches, django_capture_on_commit_callbacks):
    order = _order("WEB-20260926-1236")
    with django_capture_on_commit_callbacks(execute=True):
        ticket = _ticket(order, lanches)
    job = PrintJob.objects.get(kind=PrintJob.Kind.KITCHEN_TICKET)

    chip = build_kds_board(saida.ref).preparing[0].stations[0]
    assert chip.paper_label == "na fila da impressora"

    PrintJob.objects.filter(pk=job.pk).update(status=PrintJob.Status.SPOOLED)
    chip = build_kds_board(saida.ref).preparing[0].stations[0]
    assert chip.paper_label.startswith("impresso às ")
    assert chip.paper_failed is False

    PrintJob.objects.filter(pk=job.pk).update(status=PrintJob.Status.EXPIRED)
    chip = build_kds_board(saida.ref).preparing[0].stations[0]
    assert (chip.paper_label, chip.paper_failed) == ("não imprimiu", True)
    assert kitchen_ticket_print.paper_states([ticket.pk])[ticket.pk].failed is True


def test_pedido_sem_ticket_aberto_e_pedido_pronto_nao_estao_em_preparo(saida, lanches):
    todo_pronto = _order("WEB-20260926-1237")
    _ticket(todo_pronto, lanches, status="done")
    pronto = _order("WEB-20260926-1238", status=Order.Status.READY)
    _ticket(pronto, lanches)  # ticket órfão de pedido que já saiu da cozinha

    board = build_kds_board(saida.ref)

    assert board.preparing == ()
    assert [card.order_ref for card in board.tickets] == [pronto.ref]


def test_estacao_so_com_item_retirado_nao_vira_chip(saida, lanches, cafes):
    order = _order("WEB-20260926-1239")
    _ticket(order, cafes)
    _ticket(order, lanches, status="cancelled")

    card = build_kds_board(saida.ref).preparing[0]

    assert [chip.station_name for chip in card.stations] == ["Cafés"]


# ── O "Pronto" da Saída ────────────────────────────────────────────────────


def _exit_done(client, order: Order, station: KDSInstance):
    return client.post(
        reverse("api-backstage-kds-exit-printed-station-done", args=[order.pk, station.ref]),
        content_type="application/json",
    )


def test_pronto_da_saida_conclui_a_estacao_e_o_pedido_passa_para_prontos(client, saida, lanches, cafes):
    order = _order("WEB-20260926-1240")
    _ticket(order, cafes, status="done")
    ticket = _ticket(order, lanches)
    client.force_login(_operator("saida-op", ("backstage", "operate_kds")))

    response = _exit_done(client, order, lanches)

    assert response.status_code == 200, response.json()
    assert response.json()["completed"] == 1
    ticket.refresh_from_db()
    assert (ticket.status, ticket.completed_by, ticket.completed_via) == ("done", "saida-op", "exit")
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    board = build_kds_board(saida.ref)
    assert board.preparing == ()
    assert [card.order_ref for card in board.tickets] == [order.ref]


def test_pronto_da_saida_so_toca_a_estacao_e_o_pedido_do_card(client, saida, lanches):
    order = _order("WEB-20260926-1241")
    outro = _order("WEB-20260926-1242")
    deste = _ticket(order, lanches)
    do_outro = _ticket(outro, lanches)
    client.force_login(_operator("saida-op2", ("backstage", "operate_kds")))

    assert _exit_done(client, order, lanches).status_code == 200

    deste.refresh_from_db()
    do_outro.refresh_from_db()
    assert deste.status == "done"
    assert do_outro.status == "pending"


def test_pronto_da_saida_recusa_estacao_de_tela(client, saida, cafes):
    order = _order("WEB-20260926-1243")
    ticket = _ticket(order, cafes)
    client.force_login(_operator("saida-op3", ("backstage", "operate_kds")))

    response = _exit_done(client, order, cafes)

    assert response.status_code == 400
    assert response.json()["detail"] == "Cafés tem tela: o pronto é dado lá."
    ticket.refresh_from_db()
    assert ticket.status == "pending"


def test_pronto_da_saida_repetido_e_sucesso_sem_efeito(client, saida, lanches):
    order = _order("WEB-20260926-1244")
    _ticket(order, lanches)
    client.force_login(_operator("saida-op4", ("backstage", "operate_kds")))

    assert _exit_done(client, order, lanches).json()["completed"] == 1
    replay = _exit_done(client, order, lanches)
    assert replay.status_code == 200
    assert replay.json()["completed"] == 0


def test_pedido_ou_estacao_inexistente_e_404(client, saida, lanches):
    order = _order("WEB-20260926-1245")
    client.force_login(_operator("saida-op5", ("backstage", "operate_kds")))

    missing_order = client.post(
        reverse("api-backstage-kds-exit-printed-station-done", args=[999999, lanches.ref]),
        content_type="application/json",
    )
    missing_station = client.post(
        reverse("api-backstage-kds-exit-printed-station-done", args=[order.pk, "nao-existe"]),
        content_type="application/json",
    )
    assert missing_order.status_code == 404
    assert missing_station.status_code == 404


def test_o_papel_cancelado_e_a_ciencia_da_estacao_sem_tela(client, saida, lanches):
    """Sem tela não há "Recebi o cancelamento": o papel CANCELADO é o aviso.
    O item retirado não pode travar o Pronto da Saída para sempre."""
    order = _order("WEB-20260926-1246")
    vivo = _ticket(order, lanches, line="L1")
    retirado = _ticket(order, lanches, status="cancelled", line="L2")
    client.force_login(_operator("saida-op6", ("backstage", "operate_kds")))

    assert _exit_done(client, order, lanches).status_code == 200

    vivo.refresh_from_db()
    retirado.refresh_from_db()
    assert vivo.status == "done"
    assert retirado.acknowledged_at is not None


def test_o_caixa_tambem_da_o_pronto_e_quem_nao_opera_nenhum_dos_dois_nao(client, saida, lanches):
    order = _order("WEB-20260926-1247")
    _ticket(order, lanches)

    client.force_login(_operator("so-staff"))
    assert _exit_done(client, order, lanches).status_code == 403

    client.force_login(_operator("caixa", ("cashman", "operate_pos")))
    assert _exit_done(client, order, lanches).status_code == 200


# ── O "Pronto" do PDV no card do ticket ────────────────────────────────────


def _pos_done(client, ticket: KDSTicket):
    return client.post(
        reverse("api-backstage-kds-printed-ticket-done", args=[ticket.pk]),
        content_type="application/json",
    )


def test_pronto_do_pdv_conclui_o_ticket_e_devolve_o_aviso(client, lanches):
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja"})
    order = _order("WEB-20260926-1250", name="Ana")
    ticket = _ticket(order, lanches)
    client.force_login(_operator("caixa-2", ("cashman", "operate_pos")))

    response = _pos_done(client, ticket)

    assert response.status_code == 200, response.json()
    receipt = response.json()["ticket"]
    assert receipt["message"] == "Lanches pronto · Ana · #1250"
    assert receipt["completed_now"] is True
    ticket.refresh_from_db()
    assert (ticket.status, ticket.completed_via) == ("done", "pos")

    replay = _pos_done(client, ticket)
    assert replay.status_code == 200
    assert replay.json()["ticket"]["message"] == "Lanches já estava pronto · Ana · #1250"


def test_pronto_do_pdv_recusa_ticket_de_estacao_de_tela_e_ticket_cancelado(client, lanches, cafes):
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja"})
    order = _order("WEB-20260926-1251")
    de_tela = _ticket(order, cafes)
    cancelado = _ticket(order, lanches, status="cancelled")
    client.force_login(_operator("caixa-3", ("cashman", "operate_pos")))

    tela = _pos_done(client, de_tela)
    assert tela.status_code == 400
    assert tela.json()["detail"] == "Cafés tem tela: o pronto é dado lá."

    cancel = _pos_done(client, cancelado)
    assert cancel.status_code == 400
    assert "cancelado" in cancel.json()["detail"]


def test_a_linha_da_comanda_traz_o_card_do_ticket_para_o_pdv(lanches, cafes):
    from shopman.backstage.projections.pos import _kitchen_tickets_by_line

    order = _order("WEB-20260926-1252")
    _ticket(order, lanches, line="L1")
    _ticket(order, cafes, status="in_progress", line="L2")
    _ticket(order, lanches, status="cancelled", line="L3")

    by_line = _kitchen_tickets_by_line(order.session_key)

    assert set(by_line) == {"L1", "L2"}  # o cancelado não vira card
    lanche = by_line["L1"][0]
    assert (lanche["station_name"], lanche["prints"], lanche["can_mark_ready"]) == ("Lanches", True, True)
    assert lanche["status_label"] == "Na fila"
    assert lanche["items"] == [{"name": "Item", "qty": 1, "notes": ""}]
    cafe = by_line["L2"][0]
    assert (cafe["prints"], cafe["can_mark_ready"], cafe["status_label"]) == (False, False, "Em preparo")


# ── O QR da Via Cozinha e o leitor de código ───────────────────────────────


def _scan(client, code: str):
    return client.post(
        reverse("api-backstage-kds-printed-ticket-scan"), {"code": code}, content_type="application/json"
    )


def test_o_codigo_do_ticket_e_assinado_e_nao_se_adivinha():
    code = kitchen_ticket_print.ticket_code(1234)
    assert code.startswith("KT-1234-")
    assert kitchen_ticket_print.ticket_pk_from_code(code) == 1234
    assert kitchen_ticket_print.ticket_pk_from_code(code.lower()) == 1234  # Caps Lock trocado
    assert kitchen_ticket_print.ticket_pk_from_code(f"  {code}\n") == 1234
    # O pk do vizinho com a assinatura deste não passa.
    assert kitchen_ticket_print.ticket_pk_from_code(code.replace("KT-1234-", "KT-1235-")) is None
    assert kitchen_ticket_print.ticket_pk_from_code("KT-1234") is None
    assert kitchen_ticket_print.ticket_pk_from_code("7891234567895") is None  # código de barras de produto


def test_o_papel_vivo_leva_o_qr_e_o_cancelado_nao(lanches):
    from shopman.backstage.services.receipt_escpos import ENCODING, kitchen_ticket

    order = _order("WEB-20260926-1260")
    vivo = _ticket(order, lanches)
    cancelado = _ticket(order, lanches, status="cancelled", line="L2")

    papel_vivo = kitchen_ticket(vivo).decode(ENCODING, "replace")
    papel_cancelado = kitchen_ticket(cancelado).decode(ENCODING, "replace")

    assert kitchen_ticket_print.ticket_code(vivo.pk) in papel_vivo
    assert "Leia o código no PDV" in papel_vivo
    assert "KT-" not in papel_cancelado


def test_o_leitor_conclui_o_ticket_e_devolve_o_aviso(client, lanches):
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja"})
    order = _order("WEB-20260926-1261", name="Ana")
    ticket = _ticket(order, lanches)
    client.force_login(_operator("caixa-leitor", ("cashman", "operate_pos")))

    response = _scan(client, kitchen_ticket_print.ticket_code(ticket.pk))

    assert response.status_code == 200, response.json()
    assert response.json()["ticket"]["message"] == "Lanches pronto · Ana · #1261"
    ticket.refresh_from_db()
    assert (ticket.status, ticket.completed_by, ticket.completed_via) == ("done", "caixa-leitor", "scanner")

    again = _scan(client, kitchen_ticket_print.ticket_code(ticket.pk))
    assert again.status_code == 200
    assert again.json()["ticket"]["completed_now"] is False
    assert again.json()["ticket"]["message"] == "Lanches já estava pronto · Ana · #1261"


def test_codigo_estranho_e_404_com_o_que_houve(client, lanches):
    client.force_login(_operator("caixa-leitor2", ("cashman", "operate_pos")))

    response = _scan(client, "KT-99-AAAAAAAAAA")

    assert response.status_code == 404
    assert response.json()["detail"] == "Código não reconhecido: não é de uma Via Cozinha desta loja."


def test_leitor_em_ticket_cancelado_diz_para_nao_preparar(client, lanches):
    order = _order("WEB-20260926-1262")
    cancelado = _ticket(order, lanches, status="cancelled")
    client.force_login(_operator("caixa-leitor3", ("cashman", "operate_pos")))

    response = _scan(client, kitchen_ticket_print.ticket_code(cancelado.pk))

    assert response.status_code == 400
    assert response.json()["detail"] == "Este pedido foi cancelado em Lanches: não prepare."


def test_leitor_exige_operador_do_pdv_ou_do_kds(client, lanches):
    order = _order("WEB-20260926-1263")
    ticket = _ticket(order, lanches)
    client.force_login(_operator("so-staff-2"))

    assert _scan(client, kitchen_ticket_print.ticket_code(ticket.pk)).status_code == 403
