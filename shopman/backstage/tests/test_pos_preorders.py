"""Encomendas do PDV — o corte, o saldo, a situação, a busca e a rota.

A seção Encomendas (``docs/plans/ENCOMENDAS-PDV-PLAN.md``) lê o que a casa
prometeu: todo pedido com recebimento, de qualquer canal, hoje ou depois, pela
data combinada. Estes testes prendem o que a tela não pode errar — quem entra,
quanto falta receber, e que o detalhe não vira porta para qualquer pedido.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem
from shopman.payman import PaymentService

from shopman.backstage.projections import preorders

pytestmark = pytest.mark.django_db


def _order(ref: str, *, status: str = "accepted", channel_ref: str = "web", total_q: int = 3600,
           items=(("Pão de fermentação natural", 2, 1800),), **data_extra) -> Order:
    data = {"customer": {"name": "Ana Souza", "phone": "+5543999887766"}, "fulfillment_type": "pickup"}
    data.update(data_extra)
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, status=status, total_q=total_q, data=data)
    for seq, (name, qty, price) in enumerate(items, start=1):
        OrderItem.objects.create(
            order=order, line_id=str(seq), sku=f"SKU-{seq}", name=name, qty=qty,
            unit_price_q=price, line_total_q=qty * price,
        )
    return order


def _pay(order: Order, amount_q: int, *, method: str = "cash") -> str:
    intent = PaymentService.settle(order.ref, amount_q, method, idempotency_key=f"test:{order.ref}:{method}")
    payment = dict(order.data.get("payment") or {})
    payment.update({"method": method, "intent_ref": intent.ref})
    order.data["payment"] = payment
    order.save(update_fields=["data"])
    return intent.ref


def _list(date_from=None, date_to=None, query=""):
    today = timezone.localdate()
    return preorders.build_preorder_list(
        date_from=date_from or today, date_to=date_to or today + timedelta(days=6), query=query,
    )


def _refs(projection) -> list[str]:
    return [card.ref for day in projection.days for card in day.orders]


def _card(projection, ref: str):
    return next(card for day in projection.days for card in day.orders if card.ref == ref)


# ── O corte ───────────────────────────────────────────────────────────────


def test_encomenda_e_todo_pedido_com_recebimento_de_qualquer_canal_hoje_ou_depois():
    today = timezone.localdate()
    _order("WEB-HOJE", delivery_date=today.isoformat())
    _order("IFOOD-SAB", channel_ref="ifood", delivery_date=(today + timedelta(days=3)).isoformat())
    _order("PDV-ENC", channel_ref="pdv", origin_channel="pos", pos={"sales_mode": "order"},
           delivery_date=(today + timedelta(days=1)).isoformat())

    assert set(_refs(_list())) == {"WEB-HOJE", "IFOOD-SAB", "PDV-ENC"}


def test_balcao_cancelado_e_devolvido_ficam_de_fora():
    today = timezone.localdate()
    _order("BALCAO", channel_ref="pdv", origin_channel="pos", pos={"sales_mode": "counter"})
    _order("MORTO", status="cancelled", delivery_date=today.isoformat())
    _order("DEVOLVIDO", status="returned", delivery_date=today.isoformat())
    _order("VIVO", delivery_date=today.isoformat())

    assert _refs(_list()) == ["VIVO"]


def test_vai_pela_data_COMBINADA_e_nao_pela_data_da_venda():
    today = timezone.localdate()
    _order("SABADO", delivery_date=(today + timedelta(days=10)).isoformat())

    assert _refs(_list()) == []
    assert _refs(_list(today + timedelta(days=10), today + timedelta(days=10))) == ["SABADO"]


# ── A grade ───────────────────────────────────────────────────────────────


def test_a_grade_tem_TODOS_os_dias_do_intervalo_com_contagem_e_total_do_dia():
    today = timezone.localdate()
    _order("A", delivery_date=today.isoformat(), total_q=1000)
    _order("B", delivery_date=today.isoformat(), total_q=2500)
    _order("C", delivery_date=(today + timedelta(days=2)).isoformat(), total_q=4000)

    projection = _list()

    assert len(projection.days) == 7
    assert [(d.orders_count, d.total_q) for d in projection.days[:3]] == [(2, 3500), (0, 0), (1, 4000)]
    assert projection.days[0].is_today and projection.days[0].date_display == "hoje"
    assert projection.days[1].date_display == "amanhã"
    assert projection.days[0].total_display == "R$ 35,00"
    assert projection.count == 3 and projection.total_q == 7500


def test_dentro_do_dia_a_ordem_e_a_da_janela():
    today = timezone.localdate().isoformat()
    _order("TARDE", delivery_date=today, delivery_time_slot="slot-15")
    _order("CEDO", delivery_date=today, delivery_time_slot="slot-09")

    projection = _list()

    assert [c.ref for c in projection.days[0].orders] == ["CEDO", "TARDE"]
    assert projection.days[0].orders[0].window_start == "09:00"
    assert projection.days[0].orders[0].window_label


def test_o_intervalo_tem_teto():
    date_from, date_to = preorders.parse_range("2026-01-01", "2026-12-31")

    assert (date_to - date_from).days + 1 == preorders.MAX_SPAN_DAYS
    assert date_from.isoformat() == "2026-01-01"


# ── Saldo e situação ──────────────────────────────────────────────────────


def test_sem_pagamento_o_saldo_e_o_total_e_a_situacao_e_a_pagar():
    _order("DEVE", delivery_date=timezone.localdate().isoformat())

    card = _card(_list(), "DEVE")

    assert (card.balance_q, card.situation, card.situation_label) == (3600, "to_pay", "A pagar")
    assert card.balance_display == "R$ 36,00"


def test_pago_pelo_payman_zera_o_saldo():
    order = _order("PAGO", delivery_date=timezone.localdate().isoformat())
    _pay(order, 3600)

    card = _card(_list(), "PAGO")

    assert (card.balance_q, card.situation) == (0, "paid")


def test_pagamento_a_MAIS_nunca_vira_saldo_negativo():
    order = _order("A-MAIS", delivery_date=timezone.localdate().isoformat())
    _pay(order, 5000)

    assert _card(_list(), "A-MAIS").balance_q == 0


def test_venda_mista_soma_os_intents_de_CADA_tender():
    """Venda mista grava o intent em cada tender e não em ``payment.intent_ref``."""
    order = _order("MISTA", delivery_date=timezone.localdate().isoformat())
    cash = PaymentService.settle(order.ref, 1000, "cash", idempotency_key="t:mista:cash")
    pix = PaymentService.settle(order.ref, 1500, "pix", idempotency_key="t:mista:pix", asserted_at_terminal=True)
    order.data["payment"] = {"method": "mixed", "tenders": [
        {"method": "cash", "amount_q": 1000, "intent_ref": cash.ref},
        {"method": "pix", "amount_q": 1500, "intent_ref": pix.ref},
    ]}
    order.save(update_fields=["data"])

    assert _card(_list(), "MISTA").balance_q == 1100


def test_o_saldo_usa_o_total_EFETIVO_do_pedido_ajustado():
    _order("AJUSTADO", delivery_date=timezone.localdate().isoformat(),
           adjustment={"items": [{"line_id": "1", "sku": "SKU-1", "name": "Pão", "qty": "1",
                                  "unit_price_q": 1800, "line_total_q": 1800}], "total_q": 1800})

    card = _card(_list(), "AJUSTADO")

    assert (card.total_q, card.balance_q, card.items_count) == (1800, 1800, 1)


def test_intent_que_o_payman_nao_conhece_vira_CONFERIR_e_nunca_zero():
    _order("SEM-LEITURA", delivery_date=timezone.localdate().isoformat(),
           payment={"method": "pix", "intent_ref": "PI-QUE-NAO-EXISTE"})

    card = _card(_list(), "SEM-LEITURA")

    assert card.balance_q is None
    assert card.situation == "check_payment"


def test_na_conta_da_casa_nao_e_saldo_a_cobrar_no_balcao():
    _order("CONTA", delivery_date=timezone.localdate().isoformat(), payment={"method": "account"})

    card = _card(_list(), "CONTA")

    assert (card.balance_q, card.situation) == (0, "on_account")


def test_ifood_pre_pago_tem_saldo_zero():
    _order("IFOOD-PAGO", channel_ref="ifood", delivery_date=timezone.localdate().isoformat(),
           ifood={"payments": {"prepaid_q": 3600, "pending_q": 0, "methods": []}})

    assert _card(_list(), "IFOOD-PAGO").balance_q == 0


@pytest.mark.parametrize(("status", "situation"), [
    ("ready", "ready"), ("dispatched", "out_for_delivery"), ("completed", "delivered"), ("delivered", "delivered"),
])
def test_a_mercadoria_vence_o_dinheiro_na_situacao(status, situation):
    _order(f"S-{status}", status=status, delivery_date=timezone.localdate().isoformat())

    card = _card(_list(), f"S-{status}")

    assert card.situation == situation
    assert card.balance_q == 3600  # o saldo continua no card, com campo próprio


# ── Busca ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("query", ["ana", "ANA SOUZA", "SOUZA", "9988", "(43) 99988-7766", "busca-1"])
def test_busca_por_nome_telefone_ou_numero(query):
    today = timezone.localdate().isoformat()
    _order("BUSCA-1", delivery_date=today)
    _order("OUTRO", delivery_date=today, customer={"name": "Carlos", "phone": "+5543911112222"})

    assert _refs(_list(query=query)) == ["BUSCA-1"]


def test_busca_ignora_acento():
    _order("JOSE", delivery_date=timezone.localdate().isoformat(), customer={"name": "José Álvares"})

    assert _refs(_list(query="jose alvares")) == ["JOSE"]


def test_busca_pelo_numero_do_ifood():
    _order("IFOOD-260926-1", channel_ref="ifood", delivery_date=timezone.localdate().isoformat(),
           ifood={"display_id": "4994"})

    assert _refs(_list(query="4994")) == ["IFOOD-260926-1"]


def test_poucos_digitos_nao_buscam_telefone():
    _order("CURTO", delivery_date=timezone.localdate().isoformat())

    assert _refs(_list(query="99")) == []


# ── As rotas ──────────────────────────────────────────────────────────────


def _operator(*codenames: str) -> User:
    user = User.objects.create_user(f"op-{'-'.join(codenames) or 'none'}", password="pw", is_staff=True)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


@pytest.fixture
def caixa(client):
    client.force_login(_operator("operate_pos", "manage_orders"))
    return client


def test_a_rota_lista_com_os_params_canonicos(caixa):
    today = timezone.localdate()
    _order("ROTA-1", delivery_date=today.isoformat())

    response = caixa.get("/api/v1/backstage/pos/preorders/", {
        "date_from": today.isoformat(), "date_to": today.isoformat(), "q": "ana",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["date_from"] == body["date_to"] == today.isoformat()
    assert body["count"] == 1
    assert body["days"][0]["orders"][0]["ref"] == "ROTA-1"
    assert body["days"][0]["orders"][0]["situation_label"] == "A pagar"


def test_sem_manage_orders_a_rota_recusa(client):
    client.force_login(_operator("operate_pos"))

    response = client.get("/api/v1/backstage/pos/preorders/")

    assert response.status_code == 403
    assert "detail" in response.json()


def test_o_detalhe_traz_itens_saldo_e_contato(caixa):
    _order("DET-1", delivery_date=timezone.localdate().isoformat(), order_notes="Sem açúcar por cima")

    body = caixa.get("/api/v1/backstage/pos/preorders/DET-1/").json()

    assert body["card"]["ref"] == "DET-1"
    assert body["card"]["balance_q"] == 3600
    assert body["items"] == [{"name": "Pão de fermentação natural", "qty_display": "2", "line_total_display": "R$ 36,00"}]
    assert body["customer_note"] == "Sem açúcar por cima"
    assert body["customer_phone"] == "(43) 99988-7766"
    assert body["ticket_printed"] is False


def test_o_detalhe_nao_e_porta_para_venda_de_balcao(caixa):
    _order("BALCAO-DET", channel_ref="pdv", origin_channel="pos", pos={"sales_mode": "counter"})

    response = caixa.get("/api/v1/backstage/pos/preorders/BALCAO-DET/")

    assert response.status_code == 404
    assert response.json()["detail"] == "Encomenda não encontrada."


def test_o_detalhe_do_ifood_nao_mostra_o_rele_como_telefone(caixa):
    _order("IFOOD-DET", channel_ref="ifood", delivery_date=timezone.localdate().isoformat(),
           customer={"name": "Marina A.", "phone": "08007050000", "phone_localizer": "12345678"})

    body = caixa.get("/api/v1/backstage/pos/preorders/IFOOD-DET/").json()

    assert body["customer_phone"] == ""
