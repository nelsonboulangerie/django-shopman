"""A comanda virtual da edição de encomenda (``shop.services.pos_edit_session``).

A tela de venda do PDV vira o editor da encomenda (decisão do dono, 28/09). Estes
testes prendem o que faz dela uma comanda que NÃO é comanda: nasce do pedido
(itens com o ``line_id`` e o preço vendido, cliente, recebimento, data,
observação), não aparece no quadro, não vira ``POSTab``, não dispara cozinha,
não fecha venda nova — e o autosave de sempre funciona nela.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderItem, Session

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab, build_pos_tabs
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services import pos_edit_session
from shopman.shop.services.operator_orders import operational_revision
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def casa(db):
    Shop.objects.create(name="Loja", brand_name="Loja")
    Channel.objects.create(ref="web", name="Loja", config={"payment": {"timing": "external", "method": "cash"}})
    Channel.objects.create(
        ref="pdv", name="PDV", is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
    Product.objects.create(sku="PAO", name="Pão", base_price_q=1500, is_published=True, is_sellable=True)
    Customer.objects.create(ref="CLI-ANA", first_name="Ana", phone="+5543999990000")


@pytest.fixture
def operator():
    user = User.objects.create_user("marina", password="x", is_staff=True)
    for codename in ("operate_pos", "manage_orders"):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def _order(ref: str = "ENC-1", **data) -> Order:
    day = (timezone.localdate() + timedelta(days=3)).isoformat()
    order = Order.objects.create(
        ref=ref, channel_ref="web", status="accepted", total_q=2400,
        data={
            "customer": {"name": "Ana", "phone": "+5543999990000", "ref": "CLI-ANA"},
            "customer_ref": "CLI-ANA",
            "fulfillment_type": "pickup", "payment": {"method": "cash"},
            "delivery_date": day, "delivery_time_slot": "slot-09", "order_notes": "sem gergelim",
            **data,
        },
    )
    # Vendido a R$ 12,00 — o catálogo hoje diz R$ 15,00.
    OrderItem.objects.create(order=order, line_id="L1", sku="PAO", name="Pão", qty=2, unit_price_q=1200, line_total_q=2400)
    return order


def _open(order):
    return pos_edit_session.open_edit_session(order, channel_ref="pdv", actor="pos:marina", operator_username="marina")


def test_nasce_do_pedido_com_o_preco_vendido_e_fica_fora_do_quadro():
    order = _order()

    session = _open(order)

    tab = build_open_tab(session)
    assert tab["edit_of"] == "ENC-1" and tab["tab_display"] == "Encomenda ENC-1"
    (item,) = tab["items"]
    assert item["line_id"] == "L1" and item["qty"] == 2
    assert item["charged_price_q"] == 1200  # o VENDIDO, não o catálogo de hoje
    assert tab["sales_mode"] == "order" and tab["fulfillment_type"] == "pickup"
    assert tab["delivery_date"] == order.data["delivery_date"] and tab["delivery_time_slot"] == "slot-09"
    assert tab["order_notes"] == "sem gergelim" and tab["customer_name"] == "Ana"
    assert pos_edit_session.edit_info(session)["base_revision"] == operational_revision(order, field="edit")
    # Não é comanda do quadro.
    assert all(t.session_key != session.session_key for t in build_pos_tabs())
    assert not POSTab.objects.filter(ref="ENC-1").exists()


def test_retoma_quando_o_pedido_nao_mudou_e_refaz_quando_mudou():
    order = _order()
    first = _open(order)

    assert _open(order).pk == first.pk

    order.data = {**order.data, "order_notes": "mudou pelo Gestor"}
    order.save(update_fields=["data", "updated_at"])
    second = _open(order)

    assert second.pk != first.pk
    first.refresh_from_db()
    assert first.state == "abandoned"
    assert build_open_tab(second)["order_notes"] == "mudou pelo Gestor"


def test_autosave_funciona_sem_virar_comanda():
    order = _order()
    session = _open(order)
    tab = build_open_tab(session)

    pos_service.save_pos_tab(
        channel_ref="pdv",
        payload={
            "tab_session_key": session.session_key, "expected_revision": tab["revision"], "sales_mode": "order",
            "items": [{"line_id": "L1", "sku": "PAO", "name": "Pão", "qty": 3, "unit_price_q": 1200}],
            "fulfillment_type": "pickup", "delivery_date": tab["delivery_date"], "delivery_time_slot": "slot-09",
            "customer_name": "Ana", "customer_phone": "+5543999990000", "customer_ref": "CLI-ANA",
            "order_notes": "sem gergelim",
        },
        actor="pos:marina", operator_username="marina",
    )

    session.refresh_from_db()
    assert session.items[0]["qty"] in (3, "3")
    assert "tab_ref" not in session.data
    assert pos_edit_session.is_edit_session(session)
    assert not POSTab.objects.exists()


def test_nao_dispara_cozinha_nem_fecha_venda():
    session = _open(_order())

    with pytest.raises(PosIntentError) as fire:
        pos_service.fire_pos_tab(channel_ref="pdv", session_key=session.session_key, actor="pos:marina",
            operator_username="marina")
    assert fire.value.code == "edit_session_no_fire"

    with pytest.raises(PosIntentError) as close:
        pos_service.close_sale(
            channel_ref="pdv",
            payload={"tab_session_key": session.session_key, "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1500}],
                     "payment_method": "cash", "client_request_id": "x-1"},
            actor="pos:marina", operator_username="marina",
        )
    assert close.value.code == "edit_session_no_sale"
    assert Order.objects.count() == 1


def test_encomenda_que_nao_se_edita_nao_abre():
    order = _order(nfce_access_key="4126" + "0" * 40)

    with pytest.raises(PosIntentError) as refused:
        _open(order)
    assert refused.value.code == "fiscal_authorized"
    assert not Session.objects.filter(handle_type="pos_edit").exists()


def test_endpoint_abre_e_devolve_o_contexto_da_edicao(client, operator):
    order = _order()
    client.force_login(operator)

    response = client.post(reverse("api-backstage-pos-preorder-edit-session", args=[order.ref]), content_type="application/json")

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["tab"]["edit_of"] == order.ref
    assert body["edit"]["base_revision"] == operational_revision(order, field="edit")
    assert body["edit"]["actor_id"] == operator.pk
    assert body["edit"]["original"]["items"][0]["line_id"] == "L1"


# ── A peça pesada que já estava ──────────────────────────────────────────────


def _com_peca(ref: str = "ENC-KG") -> Order:
    from decimal import Decimal

    Product.objects.create(sku="QUEIJO", name="Queijo", unit="kg", base_price_q=8990, is_published=True, is_sellable=True)
    order = _order(ref)
    OrderItem.objects.create(
        order=order, line_id="L2", sku="QUEIJO", name="Queijo", qty=Decimal("0.312"), unit_price_q=8990,
        line_total_q=2805,
        meta={"weighed": {"entry": "label", "label_q": 2805, "weight_g": 312, "price_per_kg_q": 8990, "total_q": 2805}},
    )
    return order


def test_peca_pesada_abre_com_o_peso_vendido_e_o_autosave_nao_troca_a_peca():
    from decimal import Decimal

    order = _com_peca()
    session = _open(order)

    tab = build_open_tab(session)
    piece = next(item for item in tab["items"] if item["line_id"] == "L2")
    assert Decimal(str(piece["qty"])) == Decimal("0.312")
    assert piece["weighed"]["entry"] == "label" and piece["weighed"]["label_q"] == 2805

    # O quilo subiu e a tela manda de volta o que ela tem (a etiqueta, e até o
    # peso com a entrada por peso desligada): a peça continua a vendida.
    Product.objects.filter(sku="QUEIJO").update(base_price_q=9990)
    for weighed in ({"entry": "label", "label_q": 2805}, {"entry": "weight", "weight_g": 312}):
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={
                "tab_session_key": session.session_key, "expected_revision": tab["revision"], "sales_mode": "order",
                "items": [
                    {"line_id": "L1", "sku": "PAO", "name": "Pão", "qty": 2, "unit_price_q": 1200},
                    {"line_id": "L2", "sku": "QUEIJO", "name": "Queijo", "qty": 1, "unit_price_q": 9990, "weighed": weighed},
                ],
                "fulfillment_type": "pickup", "delivery_date": tab["delivery_date"], "delivery_time_slot": "slot-09",
                "customer_name": "Ana", "customer_phone": "+5543999990000", "customer_ref": "CLI-ANA",
                "order_notes": "sem gergelim",
            },
            actor="pos:marina", operator_username="marina",
        )
        session.refresh_from_db()
        saved = next(item for item in session.items if item["line_id"] == "L2")
        assert Decimal(str(saved["qty"])) == Decimal("0.312")
        assert int(saved["unit_price_q"]) == 8990


# ── Cancelar e refazer ───────────────────────────────────────────────────────


def _cancelled(ref: str = "ENC-X", **data) -> Order:
    order = _order(ref, **data)
    Order.objects.filter(pk=order.pk).update(status="cancelled")
    return Order.objects.get(pk=order.pk)


def _redo(order):
    return pos_edit_session.open_redo_tab(order, channel_ref="pdv", actor="pos:marina", operator_username="marina")


def test_refazer_abre_comanda_de_venda_com_a_encomenda_cancelada():
    order = _cancelled(fulfillment_type="pickup", fiscal={"tax_id": "52998224725"}, payment={"method": "pix"})

    redo = _redo(order)

    assert redo.resumed is False and redo.schedule_dropped == ""
    tab = build_open_tab(redo.session)
    assert tab["tab_ref"] == pos_service.normalize_tab_ref("Refazer ENC-X")
    assert tab["tab_display"] == "Refazer ENC-X"
    assert "edit_of" not in tab or not tab["edit_of"]
    (item,) = tab["items"]
    # Linha NOVA, pelo preço de hoje (o vendido era R$ 12,00).
    assert item["line_id"] != "L1" and item["sku"] == "PAO" and item["qty"] == 2
    assert item["charged_price_q"] == 1500
    assert tab["sales_mode"] == "order" and tab["fulfillment_type"] == "pickup"
    assert tab["delivery_date"] == order.data["delivery_date"] and tab["delivery_time_slot"] == "slot-09"
    assert tab["order_notes"] == "sem gergelim" and tab["customer_name"] == "Ana"
    # Pagamento e CPF na nota são do fechamento da venda nova.
    assert not tab.get("fiscal_tax_id") and tab.get("payment_method") != "pix"
    # Comanda do quadro, como qualquer outra.
    assert POSTab.objects.filter(ref=pos_service.normalize_tab_ref("Refazer ENC-X")).exists()
    assert any(t.session_key == redo.session.session_key for t in build_pos_tabs())
    assert not pos_edit_session.is_edit_session(redo.session)


def test_refazer_retoma_a_comanda_aberta_sem_remontar():
    order = _cancelled()
    first = _redo(order)
    tab = build_open_tab(first.session)
    pos_service.save_pos_tab(
        channel_ref="pdv",
        payload={
            "tab_session_key": first.session.session_key, "expected_revision": tab["revision"], "sales_mode": "order",
            "items": [{"sku": "PAO", "name": "Pão", "qty": 5, "unit_price_q": 1500}],
            "fulfillment_type": "pickup", "delivery_date": tab["delivery_date"], "delivery_time_slot": "slot-09",
            "customer_name": "Ana", "customer_phone": "+5543999990000", "customer_ref": "CLI-ANA",
        },
        actor="pos:marina", operator_username="marina",
    )

    again = _redo(order)

    assert again.resumed is True and again.session.pk == first.session.pk
    assert build_open_tab(again.session)["items"][0]["qty"] == 5


def test_refazer_so_depois_de_cancelar_e_uma_vez_so():
    with pytest.raises(PosIntentError) as alive:
        _redo(_order("ENC-VIVA"))
    assert alive.value.code == "order_not_cancelled"

    order = _cancelled("ENC-R")
    Order.objects.create(
        ref="PDV-NOVA", channel_ref="pdv", status="new", total_q=3000,
        data={"tab_ref": pos_service.normalize_tab_ref("Refazer ENC-R")},
    )
    with pytest.raises(PosIntentError) as twice:
        _redo(order)
    assert twice.value.code == "already_redone"
    assert "PDV-NOVA" in twice.value.message


def test_refazer_com_a_data_que_ja_passou_abre_sem_data_e_diz_por_que():
    order = _cancelled("ENC-P", delivery_date=(timezone.localdate() - timedelta(days=1)).isoformat())

    redo = _redo(order)

    hoje = timezone.localdate()
    assert redo.schedule_dropped == (
        "A data combinada já passou. Escolha hoje ou uma data futura. "
        f"A comanda veio para {hoje.strftime('%d/%m')}, sem horário: confirme a data com o cliente (F8)."
    )
    tab = build_open_tab(redo.session)
    assert tab["delivery_date"] == hoje.isoformat() and tab["delivery_time_slot"] == ""
    assert tab["items"][0]["sku"] == "PAO"


def test_endpoint_do_refazer(client, operator):
    order = _cancelled("ENC-E")
    client.force_login(operator)

    response = client.post(reverse("api-backstage-pos-preorder-redo-tab", args=[order.ref]), content_type="application/json")

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["redo"] == {"order_ref": "ENC-E", "resumed": False, "schedule_dropped": ""}
    assert body["tab"]["tab_display"] == "Refazer ENC-E"

    alive = _order("ENC-V")
    refused = client.post(reverse("api-backstage-pos-preorder-redo-tab", args=[alive.ref]), content_type="application/json")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "order_not_cancelled"
