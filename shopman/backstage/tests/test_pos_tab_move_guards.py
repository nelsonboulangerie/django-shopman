"""Mover itens entre comandas: o que a API recusa, e com que voz.

Duas portas que a tela fecha e o servidor precisa fechar também:

- a referência nova com barra ou caractere de URL ("77/2") é recusa de
  formato (422 ``invalid_tab_ref``, "Use um hífen"), nunca 500;
- a comanda virtual da edição de encomenda (``pos_edit_session``) não é origem
  nem destino de transferência: tirar ou pôr item ali mexeria numa encomenda já
  vendida por fora do "Salvar alterações".
"""

from __future__ import annotations

import json
from datetime import timedelta
from urllib.parse import quote

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.models import Terminal
from shopman.guestman.models import Customer
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order, OrderItem, Session

from shopman.backstage.models import POSTab
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services import pos_edit_session
from shopman.shop.services.pos_intent import PosIntentError, pos_session_revision

pytestmark = pytest.mark.django_db

MOVE_URL = "/api/v1/backstage/pos/tabs/move-lines/"


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(ref="web", name="Loja", config={"payment": {"timing": "external", "method": "cash"}})
    Channel.objects.create(
        ref="pdv", name="PDV", is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
    POSTab.objects.create(ref="00000077", label="77")
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    product = Product.objects.create(sku="PAO", name="Pão", base_price_q=1500, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=listing, product=product, price_q=1500)
    Customer.objects.create(ref="CLI-ANA", first_name="Ana", phone="+5543999990000")
    op = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    for codename in ("operate_pos", "manage_orders"):
        op.user_permissions.add(Permission.objects.get(codename=codename))
    client.force_login(op)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=op, terminal=terminal, float_q=0)
    return client


def _tab(tab_ref: str, payload: dict) -> Session:
    session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref=tab_ref, actor="t", operator_username="marina")
    pos_service.save_pos_tab(
        channel_ref="pdv", actor="t", operator_username="marina",
        payload={**payload, "tab_ref": tab_ref, "tab_session_key": session.session_key},
    )
    return Session.objects.get(pk=session.pk)


def _counter_tab(tab_ref: str = "77") -> Session:
    return _tab(tab_ref, {
        "items": [{"line_id": "L1", "sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1500}],
        "payment_method": "cash",
    })


def _paid_preorder() -> Order:
    day = (timezone.localdate() + timedelta(days=3)).isoformat()
    order = Order.objects.create(
        ref="ENC-1", channel_ref="web", status="accepted", total_q=2400,
        data={
            "customer": {"name": "Ana", "phone": "+5543999990000", "ref": "CLI-ANA"},
            "customer_ref": "CLI-ANA",
            "fulfillment_type": "pickup",
            "payment": {"method": "pix", "status": "captured"},
            "delivery_date": day, "delivery_time_slot": "slot-09",
        },
    )
    OrderItem.objects.create(order=order, line_id="E1", sku="PAO", name="Pão", qty=2, unit_price_q=1200, line_total_q=2400)
    return order


def _move(client, *, source: Session, line_ids: list[str], **target):
    return client.post(MOVE_URL, content_type="application/json", data=json.dumps({
        "from_session_key": source.session_key,
        "expected_revision": pos_session_revision(source),
        "line_ids": line_ids,
        **target,
    }))


# ── Referência nova inválida ─────────────────────────────────────────────────


@pytest.mark.parametrize("bad_ref", ["77/2", "77?2", "77#2", "77%2"])
def test_move_lines_invalid_new_tab_ref_is_a_422_not_a_500(balcao, bad_ref):
    client = balcao
    client.raise_request_exception = False
    source = _counter_tab()

    response = _move(client, source=source, line_ids=[source.items[0]["line_id"]], to_tab_ref=bad_ref)

    assert response.status_code == 422, response.status_code
    body = response.json()
    assert body["error"]["code"] == "invalid_tab_ref"
    assert "Use um hífen, por exemplo 77-2." in body["detail"]
    assert "—" not in body["detail"]
    # Nada se moveu e nenhuma comanda nova nasceu.
    assert Session.objects.get(pk=source.pk).items == source.items
    assert Session.objects.filter(channel_ref="pdv", state="open").count() == 1


def test_open_tab_read_with_invalid_ref_is_a_422_not_a_500(balcao):
    client = balcao
    client.raise_request_exception = False

    response = client.get(f"/api/v1/backstage/pos/tabs/{quote('77?2', safe='')}/open/")

    assert response.status_code == 422, response.status_code
    body = response.json()
    assert body["error"]["code"] == "invalid_tab_ref"
    assert "Use um hífen" in body["detail"]


# ── A comanda virtual da edição de encomenda ─────────────────────────────────


@pytest.fixture
def edicao(balcao):
    order = _paid_preorder()
    edit = pos_edit_session.open_edit_session(order, channel_ref="pdv", actor="pos:marina", operator_username="marina")
    # Uma comanda comum no MESMO modo (Encomenda, mesmo cliente e data): o
    # porteiro de modo não recusa, então quem recusa tem de ser a edição.
    regular = _tab("88", {**pos_edit_session.cart_payload(order), "items": [
        {"line_id": "N1", "sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1500},
    ]})
    return {"client": balcao, "order": order, "edit": edit, "regular": regular}


def _untouched(edicao) -> None:
    edit = Session.objects.get(pk=edicao["edit"].pk)
    regular = Session.objects.get(pk=edicao["regular"].pk)
    assert [i["line_id"] for i in edit.items] == [i["line_id"] for i in edicao["edit"].items]
    assert [i["line_id"] for i in regular.items] == [i["line_id"] for i in edicao["regular"].items]


def test_edit_session_is_not_a_move_source(edicao):
    edit, regular = edicao["edit"], edicao["regular"]
    assert pos_edit_session.is_edit_session(edit)

    with pytest.raises(PosIntentError) as exc:
        pos_service.move_pos_tab_lines(
            channel_ref="pdv", from_session_key=edit.session_key, to_session_key=regular.session_key,
            line_ids=[edit.items[0]["line_id"]], actor="t", operator_username="marina",
        )

    assert exc.value.code == "edit_session_no_move"
    assert exc.value.status == 409
    assert "—" not in exc.value.message
    _untouched(edicao)


def test_edit_session_is_not_a_split_source(edicao):
    edit = edicao["edit"]

    with pytest.raises(PosIntentError) as exc:
        pos_service.move_pos_tab_lines(
            channel_ref="pdv", from_session_key=edit.session_key, to_tab_ref="99",
            line_ids=[edit.items[0]["line_id"]], actor="t", operator_username="marina",
        )

    assert exc.value.code == "edit_session_no_move"
    assert not Session.objects.filter(channel_ref="pdv", handle_ref="00000099").exists()
    _untouched(edicao)


def test_edit_session_is_not_a_move_target(edicao):
    edit, regular = edicao["edit"], edicao["regular"]

    with pytest.raises(PosIntentError) as exc:
        pos_service.move_pos_tab_lines(
            channel_ref="pdv", from_session_key=regular.session_key, to_session_key=edit.session_key,
            line_ids=[regular.items[0]["line_id"]], actor="t", operator_username="marina",
        )

    assert exc.value.code == "edit_session_no_move"
    _untouched(edicao)


def test_edit_session_move_over_http_is_a_409(edicao):
    client, edit, regular = edicao["client"], edicao["edit"], edicao["regular"]

    response = _move(
        client, source=regular, line_ids=[regular.items[0]["line_id"]],
        to_session_key=edit.session_key, target_revision=pos_session_revision(edit),
    )

    assert response.status_code == 409, response.content
    body = response.json()
    assert body["error"]["code"] == "edit_session_no_move"
    assert body["detail"] == "Itens de uma encomenda em edição não se transferem. Termine a edição primeiro."
    _untouched(edicao)
