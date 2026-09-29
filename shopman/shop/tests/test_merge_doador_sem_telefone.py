"""Unificar um cadastro SEM telefone não leva pedido de outra pessoa.

O doador sem telefone é o caso mais comum de unificação: o cadastro do iFood
(``IF-*``) nasce com ``phone=""`` (o iFood manda o 0800 da central) e o
"fantasma" do balcão só tem CPF. O ``MergeService`` casava pedidos também por
``handle_type=phone`` + ``handle_ref == source.phone`` — e com o telefone vazio
isso é TODO pedido de telefone sem handle: pedidos de outras pessoas trocavam de
dono e ganhavam o telefone do sobrevivente.

Mora aqui, e não em ``packages/guestman``, porque a migração de pedidos é
integração opcional do Core: sem o orderman instalado o teste de lá pula.
"""

from __future__ import annotations

import pytest
from shopman.guestman.contrib.merge.service import MergeService
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

pytestmark = pytest.mark.django_db


@pytest.fixture
def ifood_donor():
    return Customer.objects.create(ref="IF-AAAA0001", first_name="Maria", last_name="Souza", phone="", source_system="ifood")


@pytest.fixture
def survivor():
    return Customer.objects.create(ref="CLI-MARIA", first_name="Maria", last_name="Souza", phone="+5543999990000")


def _order(ref: str, **extra) -> Order:
    return Order.objects.create(
        ref=ref, channel_ref=extra.pop("channel_ref", "web"), session_key=f"s-{ref}",
        status=Order.Status.ACCEPTED, total_q=1500, **extra,
    )


def test_donor_without_phone_takes_only_its_own_orders(ifood_donor, survivor):
    own = _order(
        "ORD-IF-OWN", channel_ref="ifood",
        data={"customer_ref": ifood_donor.ref, "customer": {"name": "Maria", "phone": ""}},
    )
    stranger = _order(
        "ORD-STRANGER", handle_type="phone", handle_ref="",
        data={"customer": {"name": "Outra pessoa", "phone": ""}},
    )

    result = MergeService.merge(ifood_donor, survivor, {"staff_override": True}, actor="test")

    assert result.migrated_orders == 1
    own.refresh_from_db()
    assert own.data["customer_ref"] == survivor.ref
    # O pedido próprio não ganha um telefone que nunca foi dele.
    assert own.data["customer"]["phone"] == ""
    stranger.refresh_from_db()
    assert stranger.handle_ref == ""
    assert stranger.data == {"customer": {"name": "Outra pessoa", "phone": ""}}


def test_donor_with_phone_still_takes_orders_by_phone_handle(survivor):
    donor = Customer.objects.create(ref="CLI-OLD", first_name="Maria", phone="+5543911110000")
    by_phone = _order("ORD-PHONE", handle_type="phone", handle_ref=donor.phone, data={})

    result = MergeService.merge(donor, survivor, {"staff_override": True}, actor="test")

    assert result.migrated_orders == 1
    by_phone.refresh_from_db()
    assert by_phone.handle_ref == survivor.phone
