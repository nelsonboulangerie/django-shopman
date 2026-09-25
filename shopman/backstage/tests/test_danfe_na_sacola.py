"""A DANFE que vai na sacola da entrega (decisão do dono, 25/09/2026).

O que esta suíte prende:

- o papel é o do balcão (``danfe_nfce``), com o carimbo do balcão
  (``danfe_printed_at``) e "REIMPRESSÃO" na segunda;
- a impressão automática sai UMA vez, só na entrega despachada há pouco, e vale
  para as duas ordens do tempo: nota autorizada antes do despacho e depois;
- o despacho nunca espera a nota (a regra dura: expedição sem NFC-e só avisa);
- retirada oferece reimprimir e não imprime sozinha; iFood fica de fora.
"""

from __future__ import annotations

import base64
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections.order_queue import build_order_card
from shopman.backstage.services import order_danfe
from shopman.backstage.services.receipt_escpos import ENCODING
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

NOTA = {
    "nfce_access_key": "41260800000000000000650010000001521151375188",
    "nfce_status": "authorized",
    "nfce_number": 152,
    "nfce_series": 1,
    "nfce_protocol": "123",
    "nfce_qrcode_url": "http://www.fazenda.pr.gov.br/nfce/qrcode/?p=x",
}


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Nelson Boulangerie")


@pytest.fixture
def gestor(db, shop):
    user = User.objects.create_user("gestor-danfe", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    return user


@pytest.fixture
def logado(client, gestor):
    client.force_login(gestor)
    return client


def _order(
    ref: str,
    *,
    status: str = Order.Status.DISPATCHED,
    fulfillment: str = "delivery",
    channel_ref: str = "web",
    authorized: bool = True,
    dispatched_ago: timedelta | None = timedelta(seconds=20),
) -> Order:
    data = {"customer": {"name": "Ana"}, "payment": {"method": "pix"}, "fulfillment_type": fulfillment}
    if authorized:
        data.update(NOTA)
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, status=status, total_q=3600, data=data)
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO", name="Pão de fermentação natural", qty=2,
        unit_price_q=1800, line_total_q=3600,
    )
    if dispatched_ago is not None:
        Order.objects.filter(pk=order.pk).update(dispatched_at=timezone.now() - dispatched_ago)
        order.refresh_from_db()
    return order


def _post(client, ref: str, *, auto: bool):
    return client.post(
        reverse("api-backstage-order-danfe-escpos", args=[ref]),
        data={"auto": auto},
        content_type="application/json",
    )


def _texto(corpo: dict) -> str:
    return base64.b64decode(corpo["payload_b64"]).decode(ENCODING, "replace")


# ── O estado que o card recebe ────────────────────────────────────────────


def test_entrega_despachada_com_nota_autorizada_imprime_sozinha():
    estado = order_danfe.danfe_state(_order("DLV-1"))

    assert estado == order_danfe.DanfeState(printable=True, printed=False, auto_print=True)


def test_nota_autorizada_ANTES_do_despacho_espera_o_despacho():
    """Pronta e autorizada: a DANFE sai no gesto de despachar, não antes."""
    pronto = _order("DLV-2", status=Order.Status.READY, dispatched_ago=None)

    assert order_danfe.danfe_state(pronto).auto_print is False

    Order.objects.filter(pk=pronto.pk).update(status=Order.Status.DISPATCHED, dispatched_at=timezone.now())
    pronto.refresh_from_db()
    assert order_danfe.danfe_state(pronto).auto_print is True


def test_nota_autorizada_DEPOIS_do_despacho_imprime_quando_chega():
    """O despacho não espera a nota; a DANFE sai quando a autorização chega."""
    despachado = _order("DLV-3", authorized=False)

    assert order_danfe.danfe_state(despachado) == order_danfe.DanfeState()

    despachado.data.update(NOTA)
    despachado.save(update_fields=["data"])
    assert order_danfe.danfe_state(despachado).auto_print is True


def test_fora_da_janela_a_sacola_ja_foi_e_nada_sai_sozinho():
    atrasado = _order("DLV-4", dispatched_ago=order_danfe.AUTO_PRINT_WINDOW + timedelta(seconds=1))

    estado = order_danfe.danfe_state(atrasado)
    assert estado.printable is True
    assert estado.auto_print is False


def test_retirada_oferece_a_danfe_e_nao_imprime_sozinha():
    retirada = _order("PCK-1", status=Order.Status.READY, fulfillment="pickup", dispatched_ago=None)

    assert order_danfe.danfe_state(retirada) == order_danfe.DanfeState(printable=True, printed=False, auto_print=False)


def test_ifood_fica_de_fora():
    ifood = _order("IFOOD-1", channel_ref="ifood")

    assert order_danfe.danfe_state(ifood) == order_danfe.DanfeState()


def test_o_card_do_gestor_carrega_o_estado_da_danfe(shop, gestor):
    card = build_order_card(_order("DLV-5"), user=gestor)

    assert (card.danfe_printable, card.danfe_printed, card.danfe_auto_print) == (True, False, True)


# ── O papel e o carimbo ───────────────────────────────────────────────────


def test_a_automatica_compoe_a_danfe_do_balcao_e_carimba(logado):
    order = _order("DLV-6")

    resposta = _post(logado, order.ref, auto=True)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["title"] == "danfe:DLV-6"
    assert corpo["reprint"] is False
    texto = _texto(corpo)
    assert "DANFE NFC-e" in texto
    assert "Pedido DLV-6" in texto
    assert "REIMPRESSÃO" not in texto
    order.refresh_from_db()
    assert order.data.get("danfe_printed_at")
    assert order_danfe.danfe_state(order).auto_print is False


def test_a_automatica_sai_UMA_vez_mesmo_com_duas_estacoes(logado):
    """A segunda estação recebe recusa, não uma REIMPRESSÃO que ninguém pediu."""
    order = _order("DLV-7")

    assert _post(logado, order.ref, auto=True).status_code == 200
    segunda = _post(logado, order.ref, auto=True)

    assert segunda.status_code == 409
    assert segunda.json()["code"] == "danfe_auto_not_due"


def test_reimprimir_a_mao_sai_carimbada_REIMPRESSAO(logado):
    order = _order("DLV-8")

    primeira = _post(logado, order.ref, auto=True).json()
    segunda = _post(logado, order.ref, auto=False).json()

    assert primeira["reprint"] is False
    assert segunda["reprint"] is True
    assert "REIMPRESSÃO" in _texto(segunda)


def test_retirada_imprime_a_mao_e_recusa_a_automatica(logado):
    order = _order("PCK-2", status=Order.Status.READY, fulfillment="pickup", dispatched_ago=None)

    assert _post(logado, order.ref, auto=True).status_code == 409
    manual = _post(logado, order.ref, auto=False)
    assert manual.status_code == 200
    assert manual.json()["reprint"] is False


def test_sem_nota_autorizada_nao_ha_danfe(logado):
    order = _order("DLV-9", authorized=False)

    resposta = _post(logado, order.ref, auto=False)

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "danfe_not_authorized"
    order.refresh_from_db()
    assert "danfe_printed_at" not in order.data


def test_ifood_recusa_ate_a_mao(logado):
    order = _order("IFOOD-2", channel_ref="ifood")

    resposta = _post(logado, order.ref, auto=False)

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "danfe_ifood"


def test_pedido_inexistente_e_404(logado):
    assert _post(logado, "NAO-EXISTE", auto=False).status_code == 404


def test_sem_manage_orders_nao_imprime(client, shop):
    User.objects.create_user("sem-permissao", password="pw", is_staff=True)
    client.login(username="sem-permissao", password="pw")

    assert _post(client, _order("DLV-10").ref, auto=False).status_code in (401, 403)


# ── O quadro sabe da nota na hora ─────────────────────────────────────────


def test_a_autorizacao_empurra_o_quadro_do_gestor(shop):
    """Sem o empurrão, a DANFE só sairia no poll de 30 s — com a sacola na rua."""
    from shopman.shop.handlers.fiscal import NFCeEmitHandler

    order = _order("DLV-11", authorized=False)
    resultado = mock.Mock(
        access_key=NOTA["nfce_access_key"], document_number=152, document_series=1,
        protocol_number="123", xml_url="", danfe_url="", qrcode_url="", status="authorized",
    )
    with mock.patch("shopman.shop.handlers._sse_emitters._emit_backstage") as emit:
        NFCeEmitHandler._record(order, resultado)

    emit.assert_called_once()
    args, kwargs = emit.call_args
    assert args[0] == "orders"
    assert args[2]["kind"] == "fiscal_changed"
    assert args[2]["ref"] == "DLV-11"
