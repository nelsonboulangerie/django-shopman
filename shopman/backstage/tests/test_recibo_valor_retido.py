"""O recibo do valor retido de uma encomenda não retirada (#3538).

Contador (24/11/2026, #2695): o valor que a loja retém de uma encomenda paga e não
retirada é multa, com RECIBO e sem NFC-e. Decisão do dono (24/11/2026): recibo
próprio, gerado no gesto do "Não retirado", impresso pelo agente da estação e com
link no aviso ao cliente.

Uma leitura só (``no_show.retention_receipt``) alimenta o papel do balcão, a página
do pedido na loja e a frase do aviso. Recibo é de dinheiro RECEBIDO: sem dinheiro
retido (tudo voltou, nada pago, compra na conta da casa) não há recibo.
"""

from __future__ import annotations

import base64

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.projections.order_queue import build_operator_order
from shopman.backstage.services.receipt_escpos import ENCODING, retention_receipt
from shopman.shop.policies import no_show_reason
from shopman.shop.services import cancel_reasons, no_show
from shopman.shop.tests import _no_show as world

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

CNPJ = "12345678000195"


@pytest.fixture(autouse=True)
def mundo(monkeypatch):
    world.make_shop(legal_name="Padaria de Teste Ltda", document=CNPJ)
    world.product("CROIS", price_q=935)
    world.product("BOLO", price_q=3000)
    world.lot("CROIS")
    world.lot("BOLO")
    moment = world.at(19, 5)
    monkeypatch.setattr(timezone, "now", lambda: moment)


@pytest.fixture
def gestor(client, django_user_model):
    user = django_user_model.objects.create_user(username="gestor-recibo", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    return user


def _encomenda(ref: str, *, back: bool = True, pay: str | None = "pix") -> Order:
    """Croissant com estoque baixado (volta à venda) e bolo sem estoque baixado (perda)."""
    lines = ([("CROIS", 2, 935)] if back else []) + [("BOLO", 1, 3000)]
    order = world.ready_order(ref, lines, held=False, ready_at=world.at(14), data={"customer": {"name": "Ana"}})
    if back:
        order.data["hold_ids"] = [world.fulfilled_hold("CROIS", 2, order_ref=ref)]
        order.save(update_fields=["data", "updated_at"])
    if pay:
        world.pay(order, pay)
    order.refresh_from_db()
    return order


def _nao_retirado(order: Order) -> Order:
    no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")
    order.refresh_from_db()
    return order


# ── A leitura ────────────────────────────────────────────────────────────────


def test_o_recibo_le_o_que_o_gesto_gravou():
    order = _nao_retirado(_encomenda("RET-1"))

    receipt = no_show.retention_receipt(order)

    assert receipt is not None
    assert receipt.order_ref == "RET-1"
    assert receipt.legal_name == "Padaria de Teste Ltda"
    assert receipt.tax_id == "12.345.678/0001-95"
    assert receipt.customer_name == "Ana"
    assert (receipt.paid_q, receipt.refund_q, receipt.retained_q) == (4870, 1870, 3000)
    assert [(line.name, line.value_q) for line in receipt.lines] == [("Bolo", 3000)]
    assert receipt.closed_at is not None
    assert receipt.nature.endswith("não há venda.")


def test_sem_dinheiro_retido_nao_ha_recibo():
    tudo_volta = world.ready_order("RET-TUDO", [("CROIS", 2, 935)], held=False, ready_at=world.at(14))
    tudo_volta.data["hold_ids"] = [world.fulfilled_hold("CROIS", 2, order_ref="RET-TUDO")]
    tudo_volta.save(update_fields=["data", "updated_at"])
    world.pay(tudo_volta, "pix")
    tudo_volta.refresh_from_db()
    nada_pago = _encomenda("RET-NADA", pay=None)

    assert no_show.retention_receipt(_nao_retirado(tudo_volta)) is None
    assert no_show.retention_receipt(_nao_retirado(nada_pago)) is None


def test_pedido_que_nao_foi_encerrado_como_nao_retirado_nao_tem_recibo():
    assert no_show.retention_receipt(_encomenda("RET-PRONTO")) is None


def test_compra_na_conta_da_casa_nao_tem_recibo_porque_nada_foi_recebido():
    block = {"paid_q": 3000, "refund_q": 0, "retained_q": 3000, "on_account": True, "lines": []}

    assert no_show_reason.kept_money_q(block) == 0
    assert no_show_reason.RECEIPT_HINT not in no_show_reason.customer_text(block)


def test_na_venda_mista_o_recibo_e_so_do_que_a_loja_recebeu():
    block = {
        "paid_q": 5000, "refund_q": 2000, "retained_q": 3000, "on_account": False,
        "from_account_q": 1500, "money_q": 500, "debt_left_q": 1000, "kept_q": 2000, "lines": [],
    }

    assert no_show_reason.kept_money_q(block) == 2000


# ── O aviso e a página ───────────────────────────────────────────────────────


def test_o_aviso_diz_onde_esta_o_recibo_e_a_pagina_nao_repete():
    order = _nao_retirado(_encomenda("RET-AVISO"))

    aviso = cancel_reasons.customer_text(order.data)
    pagina = cancel_reasons.customer_text(order.data, receipt_hint=False)

    assert aviso.endswith(no_show_reason.RECEIPT_HINT)
    assert no_show_reason.RECEIPT_HINT not in pagina
    assert "—" not in aviso


def test_a_pagina_do_pedido_mostra_o_recibo():
    from shopman.shop.projections.order_tracking import build_tracking
    from shopman.storefront.presentation.order_tracking import _present_retention_receipt

    order = _nao_retirado(_encomenda("RET-PAGINA"))

    shown = _present_retention_receipt(build_tracking(order).retention_receipt)

    assert shown is not None
    assert shown.title == no_show.RECEIPT_TITLE
    assert shown.issuer_lines == ("Padaria de Teste Ltda", "CNPJ 12.345.678/0001-95")
    assert shown.retained_display == "R$ 30,00"
    assert [(row.label, row.value_display) for row in shown.money_rows] == [
        ("Pago", "R$ 48,70"), ("Devolvido a você", "R$ 18,70"),
    ]
    assert shown.not_fiscal == "Não é documento fiscal."


# ── O papel ──────────────────────────────────────────────────────────────────


def test_o_papel_diz_quem_emite_o_valor_e_que_nao_e_nota():
    order = _nao_retirado(_encomenda("RET-PAPEL"))
    receipt = no_show.retention_receipt(order)

    text = retention_receipt(receipt, verify_url="https://loja.test/pedido/RET-PAPEL").decode(ENCODING)

    assert "PADARIA DE TESTE" in text
    assert "CNPJ 12.345.678/0001-95" in text
    assert "Recibo de valor retido" in text
    assert "Pedido RET-PAPEL" in text
    assert "RETIDO R$ 30,00" in text
    assert "Devolvido ao cliente" in text
    assert "Não é documento fiscal." in text
    assert "2a VIA" not in text
    assert "2a VIA" in retention_receipt(receipt, reprint=True).decode(ENCODING)


# ── A rota e o detalhe do Gestor ─────────────────────────────────────────────


def _imprimir(client, ref: str):
    return client.post(reverse("api-backstage-order-retention-receipt-escpos", args=[ref]))


def test_a_rota_compoe_o_recibo_e_a_segunda_impressao_e_segunda_via(client, gestor):
    order = _nao_retirado(_encomenda("RET-ROTA"))

    first = _imprimir(client, order.ref)
    second = _imprimir(client, order.ref)

    assert first.status_code == 200, first.content
    assert first.json()["reprint"] is False
    assert "RETIDO R$ 30,00" in base64.b64decode(first.json()["payload_b64"]).decode(ENCODING)
    assert second.json()["reprint"] is True


def test_a_rota_recusa_pedido_sem_valor_retido(client, gestor):
    order = _encomenda("RET-SEM")

    response = _imprimir(client, order.ref)

    assert response.status_code == 404
    assert response.json()["detail"] == "Este pedido não tem valor retido pela loja."


def test_a_rota_pede_a_permissao_do_gestor(client, django_user_model):
    order = _nao_retirado(_encomenda("RET-PERM"))
    client.force_login(django_user_model.objects.create_user(username="sem-permissao", is_staff=True))

    assert _imprimir(client, order.ref).status_code == 403


def test_o_detalhe_do_gestor_oferece_o_recibo_e_sabe_se_ja_saiu(client, gestor):
    order = _nao_retirado(_encomenda("RET-DETALHE"))

    before = build_operator_order(order, user=gestor)
    _imprimir(client, order.ref)
    order.refresh_from_db()
    after = build_operator_order(order, user=gestor)

    assert (before.retention_receipt_printable, before.retention_receipt_printed) == (True, False)
    assert (after.retention_receipt_printable, after.retention_receipt_printed) == (True, True)
    assert build_operator_order(_encomenda("RET-ABERTO"), user=gestor).retention_receipt_printable is False
