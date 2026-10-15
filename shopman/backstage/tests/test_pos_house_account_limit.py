"""Limite opcional da conta na casa (decisão do dono, 14/10/2026, P2-23).

- O limite mora no cadastro do cliente (``Customer.metadata.house_account_limit_q``),
  escrito pelo Admin em reais; em branco, sem limite.
- Sem limite, nada muda: a venda em conta fecha sem gerente, de qualquer valor.
- Com limite, a venda em conta que levaria o saldo acima dele NÃO é recusada:
  pede o PIN do gerente, e a review diz saldo atual, limite e quanto passa.
- Exatamente no limite ainda cabe. No misto, só a parte em conta conta.
- O pedido guarda o que o gerente assinou.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman import services as cash
from shopman.cashman.models import Shift
from shopman.doorman.models import PinCredential
from shopman.guestman.contrib.admin_unfold.admin import CustomerForm
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import Order

from shopman.backstage.api.operations import _pos_sale_review_payload
from shopman.shop.models import Channel, Shop
from shopman.shop.services import house_account
from shopman.shop.services import pos as shop_pos
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@pytest.fixture
def counter():
    Shop.objects.create(name="Loja", brand_name="Loja")
    Channel.objects.create(
        ref="pdv", name="PDV", is_active=True,
        config={"confirmation": {"mode": "immediate"}, "payment": {"method": "cash", "timing": "external"},
                "stock": {"check_on_commit": False}},
    )
    Product.objects.create(sku="PAO", name="Pão", base_price_q=1000, is_published=True, is_sellable=True)
    User = get_user_model()
    operator = User.objects.create_user(username="marina", password="x", is_staff=True)
    _grant(operator, "operate_pos")
    manager = User.objects.create_user(username="gerente", password="x", is_staff=True)
    _grant(manager, "adjust_shift")
    PinCredential.set_for(manager, "4321")
    shift = cash.open_shift(operator=operator, float_q=10000)
    ana = Customer.objects.create(ref="CLI-ANA", first_name="Ana", phone="+5543999990001", metadata={"house_account": True})
    return {"operator": operator, "manager": manager, "shift": shift, "ana": ana}


def _set_limit(customer: Customer, limit_q: int | None) -> None:
    metadata = dict(customer.metadata or {})
    if limit_q is None:
        metadata.pop("house_account_limit_q", None)
    else:
        metadata["house_account_limit_q"] = limit_q
    customer.metadata = metadata
    customer.save(update_fields=["metadata"])


def _payload(counter, *, ref: str, qty: int = 1, **over) -> dict:
    payload = {
        "items": [{"sku": "PAO", "name": "Pão", "qty": qty, "unit_price_q": 1000}],
        "customer_ref": "CLI-ANA",
        "payment_method": "account",
        "client_request_id": ref,
        "cash_shift_id": counter["shift"].pk,
    }
    payload.update(over)
    return payload


def _close(counter, **kw):
    return shop_pos.close_sale(
        channel_ref="pdv", payload=_payload(counter, **kw), actor="pos:marina", operator_username="marina",
    )


def _review(counter, **kw):
    return shop_pos.review_sale(channel_ref="pdv", payload=_payload(counter, **kw), operator_username="marina")


def test_sem_limite_nada_muda(counter):
    review = _review(counter, ref="r-1", qty=50)
    assert not review.requires_manager_approval
    assert review.house_account_limit is None

    _close(counter, ref="c-1", qty=50)
    assert house_account.balance_q("CLI-ANA") == 50000


def test_exatamente_no_limite_ainda_cabe(counter):
    _set_limit(counter["ana"], 3000)
    _close(counter, ref="c-1", qty=1)  # deve 10

    review = _review(counter, ref="r-2", qty=2)  # 10 + 20 = 30 = limite
    assert not review.requires_manager_approval
    _close(counter, ref="c-2", qty=2)
    assert house_account.balance_q("CLI-ANA") == 3000


def test_acima_do_limite_pede_o_gerente_e_a_review_diz_os_numeros(counter):
    _set_limit(counter["ana"], 3000)
    _close(counter, ref="c-1", qty=2)  # deve 20

    review = _review(counter, ref="r-2", qty=2)  # 20 + 20 = 40: passa 10
    assert review.requires_manager_approval
    assert review.approval_reasons == ("house_account_over_limit",)
    assert review.house_account_limit == {"balance_q": 2000, "limit_q": 3000, "charge_q": 2000, "over_q": 1000}
    assert _pos_sale_review_payload(review)["house_account_limit"] == review.house_account_limit

    with pytest.raises(PosIntentError) as exc:
        _close(counter, ref="c-2", qty=2)
    assert exc.value.code == "manager_approval_required"
    assert house_account.balance_q("CLI-ANA") == 2000

    with pytest.raises(PosIntentError) as exc:
        _close(counter, ref="c-3", qty=2, manager_approval={"username": "gerente", "pin": "0000"})
    assert exc.value.code == "manager_approval_invalid"
    assert "outro meio de pagamento" in exc.value.recovery

    result = _close(counter, ref="c-4", qty=2, manager_approval={"username": "gerente", "pin": "4321"})
    assert house_account.balance_q("CLI-ANA") == 4000
    order = Order.objects.get(ref=result.order_ref)
    assert order.data["payment"]["house_account_over_limit"] == {
        "balance_q": 2000, "limit_q": 3000, "charge_q": 2000, "over_q": 1000, "approved_by": "gerente",
    }


def test_o_operador_nao_assina_o_proprio_limite(counter):
    _set_limit(counter["ana"], 500)
    _grant(counter["operator"], "adjust_shift")
    PinCredential.set_for(counter["operator"], "1111")
    with pytest.raises(PosIntentError) as exc:
        _close(counter, ref="c-1", qty=1, manager_approval={"username": "marina", "pin": "1111"})
    assert exc.value.code == "manager_approval_invalid"


def test_no_misto_so_a_parte_em_conta_conta(counter):
    _set_limit(counter["ana"], 1500)
    tenders = [{"method": "cash", "amount_q": 2000}, {"method": "account", "amount_q": 1000}]
    review = _review(counter, ref="r-1", qty=3, payment_method="mixed", payment_tenders=tenders)
    assert not review.requires_manager_approval

    tenders = [{"method": "cash", "amount_q": 1000}, {"method": "account", "amount_q": 2000}]
    review = _review(counter, ref="r-2", qty=3, payment_method="mixed", payment_tenders=tenders)
    assert review.house_account_limit == {"balance_q": 0, "limit_q": 1500, "charge_q": 2000, "over_q": 500}


def test_venda_que_nao_e_em_conta_ignora_o_limite(counter):
    _set_limit(counter["ana"], 100)
    review = _review(counter, ref="r-1", qty=5, payment_method="cash")
    assert not review.requires_manager_approval
    assert review.house_account_limit is None


@pytest.mark.parametrize("raw", [True, 0, -100, "abc", None, "2000"])
def test_limite_so_vale_inteiro_positivo(counter, raw):
    counter["ana"].metadata = {"house_account": True, "house_account_limit_q": raw}
    counter["ana"].save(update_fields=["metadata"])
    expected = 2000 if raw == "2000" else None
    assert house_account.limit_q("CLI-ANA") == expected


def _form_data(customer: Customer, **over) -> dict:
    data = {
        "ref": customer.ref,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "customer_type": customer.customer_type,
        "document": customer.document or "",
        "email": customer.email or "",
        "phone": customer.phone or "",
        "price_tier": customer.primary_price_tier_id or "",
        "tags": "",
        "notes": customer.notes or "",
        "is_active": "on" if customer.is_active else "",
        "metadata": '{"house_account": true}',
        "created_by": customer.created_by or "",
        "source_system": customer.source_system or "",
        "house_account": "on",
    }
    data.update(over)
    return data


def test_o_admin_grava_o_limite_em_centavos_e_em_branco_apaga(counter):
    customer = counter["ana"]
    form = CustomerForm(data=_form_data(customer, house_account_limit="250.50"), instance=customer)
    assert form.is_valid(), form.errors
    form.save()
    customer.refresh_from_db()
    assert customer.metadata == {"house_account": True, "house_account_limit_q": 25050}
    assert CustomerForm(instance=customer).fields["house_account_limit"].initial == Decimal("250.50")

    form = CustomerForm(data=_form_data(customer, house_account_limit=""), instance=customer)
    assert form.is_valid(), form.errors
    form.save()
    customer.refresh_from_db()
    assert customer.metadata == {"house_account": True}
    assert house_account.limit_q("CLI-ANA") is None
