"""Conferência de volumes no despacho (P1-13 dos cenários de pedido).

Cada Via Pedido leva um QR assinado com o pedido e o volume ("k de N"). O leitor
do posto Saída bipa a sacola e o Gestor diz quantas foram conferidas. Sacola de
outro pedido bipada enquanto um pedido é conferido é aviso FORTE e não conta.
Nada disso segura a saída: despacho com a conferência pela metade só avisa.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.orderman.models import Order, OrderEvent, OrderItem

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import order_ticket as tickets
from shopman.shop.models import Channel, Shop
from shopman.shop.services import volume_check

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja(db):
    Shop.objects.create(name="Nelson Boulangerie")
    Channel.objects.create(ref="web", name="Loja online", config={})


def _order(ref: str, *, volumes: int | None = None, status=Order.Status.READY, delivery: bool = True) -> Order:
    data = {"customer": {"name": "Ana"}, "fulfillment_type": "delivery" if delivery else "pickup",
            "payment": {"method": "cash"}}
    if volumes:
        data["volumes"] = volumes
    order = Order.objects.create(ref=ref, channel_ref="web", status=status, total_q=1500, data=data)
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


# ── O código ──────────────────────────────────────────────────────────────


def test_o_codigo_e_assinado_e_nao_se_forja_trocando_o_pedido(loja):
    code = volume_check.volume_code("NB-1042", 2, 3)
    parsed = volume_check.parse_volume_code(code)
    assert (parsed.order_ref, parsed.k, parsed.n) == ("NB-1042", 2, 3)
    # Leitor com Caps Lock trocado e espaço nas pontas.
    assert volume_check.parse_volume_code(f"  {code.lower()} ") == parsed

    forjado = code.replace("NB-1042", "NB-1043")
    assert volume_check.parse_volume_code(forjado) is None
    assert volume_check.parse_volume_code("https://nelson.com.br/pedido/NB-1042") is None
    assert volume_check.parse_volume_code(volume_check.volume_code("NB-1", 4, 3)) is None


def test_cada_via_do_pedido_leva_o_QR_da_sua_sacola(loja):
    order = _order("VOL-PAPEL", volumes=3)

    papel = tickets.ticket_bytes(order)

    for k in (1, 2, 3):
        assert volume_check.volume_code(order.ref, k, 3).encode() in papel
    assert papel.count(b"leitor da Sa") == 3


# ── A bipada ──────────────────────────────────────────────────────────────


def test_bipar_as_sacolas_conta_de_uma_em_uma_e_repetida_nao_conta_duas_vezes(loja):
    order = _order("VOL-1", volumes=3)

    first = volume_check.check_volume(volume_check.volume_code(order.ref, 1, 3), actor="marina")
    again = volume_check.check_volume(volume_check.volume_code(order.ref, 1, 3), actor="marina")
    second = volume_check.check_volume(volume_check.volume_code(order.ref, 3, 3), actor="marina")

    assert (first.outcome, first.checked, first.total) == ("checked", 1, 3)
    assert again.outcome == "repeated" and again.checked == 1
    assert (second.checked, second.complete) == (2, False)
    assert second.message == "Pedido VOL-1: 2 de 3 sacolas conferidas."
    order.refresh_from_db()
    assert volume_check.progress_label(order) == "2 de 3 sacolas conferidas"
    assert volume_check.missing_volumes(order) == (2,)
    assert order.data["volume_check"]["checked"]["1"]["by"] == "marina"
    assert OrderEvent.objects.filter(order=order, type="volume_checked").count() == 2

    last = volume_check.check_volume(volume_check.volume_code(order.ref, 2, 3), actor="marina")
    assert last.complete is True
    assert last.message == "Pedido VOL-1: todas as 3 sacolas conferidas."


def test_sacola_de_OUTRO_pedido_e_aviso_forte_e_nao_conta(loja):
    """O caso clássico: conferindo o pedido A, aparece a sacola do B."""
    a = _order("VOL-A", volumes=2)
    b = _order("VOL-B", volumes=2)

    result = volume_check.check_volume(volume_check.volume_code(b.ref, 1, 2), actor="marina", expected_ref=a.ref)

    assert result.outcome == "other_order"
    assert result.order_ref == "VOL-B" and result.expected_ref == "VOL-A"
    assert result.message.startswith("Esta sacola é do pedido VOL-B, não do pedido VOL-A.")
    a.refresh_from_db()
    b.refresh_from_db()
    assert volume_check.checked_volumes(b) == ()  # a sacola errada não conta para ninguém
    assert a.data["volume_check"]["wrong"][0]["order_ref"] == "VOL-B"
    assert OrderEvent.objects.filter(order=a, type="volume_check_wrong_bag").exists()


def test_via_impressa_antes_de_mudar_os_volumes_pede_reimpressao(loja):
    order = _order("VOL-VELHA")  # sem volumes declarados: a via diz 1 de 1
    old_code = volume_check.volume_code(order.ref, 1, 1)
    order.data["volumes"] = 2
    order.save(update_fields=["data"])

    result = volume_check.check_volume(old_code, actor="marina")

    assert result.outcome == "stale"
    assert "Reimprima as vias" in result.message


def test_codigo_que_nao_e_da_casa(loja):
    result = volume_check.check_volume("ABC-123", actor="marina")
    assert result.outcome == "unknown"
    assert result.message == "Este código não é de uma Via Pedido desta loja."


# ── A saída só avisa ──────────────────────────────────────────────────────


def test_sair_com_a_conferencia_pela_metade_avisa_e_nao_segura(loja):
    from shopman.shop.services import operator_orders

    order = _order("VOL-SAI", volumes=3, delivery=False)
    volume_check.check_volume(volume_check.volume_code(order.ref, 1, 3), actor="marina")

    operator_orders.advance_order(order, actor="marina")

    order.refresh_from_db()
    assert order.status == "completed"
    alert = OperatorAlert.objects.get(type="dispatch_unchecked_volumes", order_ref=order.ref)
    assert "2 de 3 sacolas sem conferir" in alert.message


def test_quem_nao_confere_nao_recebe_alerta_a_cada_saida(loja):
    from shopman.shop.services import operator_orders

    order = _order("VOL-NADA", volumes=3, delivery=False)

    operator_orders.advance_order(order, actor="marina")

    assert not OperatorAlert.objects.filter(type="dispatch_unchecked_volumes").exists()


# ── A porta HTTP e o cartão ───────────────────────────────────────────────


@pytest.fixture
def gestor(loja):
    user = User.objects.create_user("gestor-conferencia", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders",
    ))
    return user


def test_a_porta_responde_o_resultado_e_o_cartao_mostra_o_progresso(gestor, client):
    from shopman.backstage.projections.order_queue import build_order_card

    order = _order("VOL-API", volumes=2)
    other = _order("VOL-OUTRO", volumes=1)
    client.force_login(gestor)

    ok = client.post(
        "/api/v1/backstage/orders/volume-check/",
        {"code": volume_check.volume_code(order.ref, 2, 2)}, content_type="application/json",
    )
    wrong = client.post(
        "/api/v1/backstage/orders/volume-check/",
        {"code": volume_check.volume_code(other.ref, 1, 1), "expected_ref": order.ref}, content_type="application/json",
    )
    empty = client.post("/api/v1/backstage/orders/volume-check/", {"code": ""}, content_type="application/json")

    assert ok.status_code == 200, ok.content
    assert ok.json()["outcome"] == "checked"
    assert (ok.json()["checked"], ok.json()["total"]) == (1, 2)
    assert wrong.json()["outcome"] == "other_order"
    assert empty.status_code == 400
    card = build_order_card(Order.objects.get(ref=order.ref))
    assert (card.volumes_checked, card.volumes_to_check) == (1, 2)
    assert card.volume_check_label == "1 de 2 sacolas conferidas"


def test_sem_acesso_ao_quadro_nao_confere(loja, client):
    user = User.objects.create_user("sem-quadro", password="pw", is_staff=True)
    client.force_login(user)
    response = client.post(
        "/api/v1/backstage/orders/volume-check/", {"code": "VP-X-1-1-AAAAAAAA"}, content_type="application/json",
    )
    assert response.status_code == 403
