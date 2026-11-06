"""Pedido sem forma de pagamento não existe (decisão do dono, 06/11/2026, GES-03).

A única forma "sem receber agora" é **em conta**, e só para o cliente cadastrado
com essa permissão (``Customer.metadata.house_account``). A regra mora no commit
(``policies.order_payment.PaymentMethodRule``), por onde passam a loja, o PDV e a
Concierge do WhatsApp; o seed, que cria pedido sem commit, se confere no fim.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.guestman.models import Customer
from shopman.orderman.exceptions import ValidationError
from shopman.orderman.models import Order, Session
from shopman.orderman.tests.commit_support import seal_for

from shopman.shop.models import Channel, Shop
from shopman.shop.policies.order_payment import PaymentMethodRule, payment_refusal
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db


class _Session:
    def __init__(self, data):
        self.data = data
        self.items = []


def _validate(data):
    PaymentMethodRule().validate(channel=None, session=_Session(data), ctx={})


def _customer(ref, *, house_account):
    return Customer.objects.create(
        ref=ref, first_name="Cliente", metadata={"house_account": True} if house_account else {},
    )


@pytest.mark.parametrize("payment", [None, {}, {"amount_q": 5000}, {"method": ""}, {"method": "fiado"}])
def test_sem_forma_de_pagamento_o_commit_recusa_com_o_campo(payment):
    data = {} if payment is None else {"payment": payment}
    assert payment_refusal(data) == (
        "payment_method_missing", "Escolha a forma de pagamento antes de fechar o pedido.",
    )
    with pytest.raises(ValidationError) as refused:
        _validate(data)
    assert refused.value.code == "payment_method_missing"
    assert refused.value.context == {"field": "payment_method"}
    assert refused.value.message == "Escolha a forma de pagamento antes de fechar o pedido."


def test_mista_sem_linhas_tambem_e_sem_forma():
    with pytest.raises(ValidationError) as refused:
        _validate({"payment": {"method": "mixed"}})
    assert refused.value.code == "payment_method_missing"


@pytest.mark.parametrize("method", ["cash", "pix", "card", "credit", "debit", "link", "external"])
def test_toda_forma_conhecida_passa(method):
    assert payment_refusal({"payment": {"method": method}}) is None
    PaymentMethodRule().validate(channel=None, session=_Session({"payment": {"method": method}}), ctx={})


def test_a_regra_do_commit_diz_a_recusa_da_politica_no_campo_da_forma():
    with pytest.raises(ValidationError) as refused:
        PaymentMethodRule().validate(channel=None, session=_Session({"payment": {}}), ctx={})
    assert refused.value.code == "payment_method_missing"
    assert refused.value.context == {"field": "payment_method"}


def test_em_conta_passa_para_cliente_com_conta_na_casa():
    _customer("CLI-CONTA", house_account=True)
    assert payment_refusal({"payment": {"method": "account"}, "customer": {"ref": "CLI-CONTA"}}) is None
    _validate({"payment": {"method": "account"}, "customer": {"ref": "CLI-CONTA"}})
    _validate({"payment": {"method": "account"}, "customer_ref": "CLI-CONTA"})


@pytest.mark.parametrize(
    "data, message",
    [
        ({"payment": {"method": "account"}}, "Venda em conta exige o cliente identificado."),
        (
            {"payment": {"method": "account"}, "customer": {"ref": "CLI-SEM"}},
            "Este cliente não tem conta na casa.",
        ),
        (
            {
                "payment": {
                    "method": "mixed",
                    "tenders": [{"method": "cash", "amount_q": 1000}, {"method": "account", "amount_q": 4000}],
                },
                "customer": {"ref": "CLI-SEM"},
            },
            "Este cliente não tem conta na casa.",
        ),
    ],
)
def test_em_conta_e_recusado_para_quem_nao_tem_a_permissao(data, message):
    _customer("CLI-SEM", house_account=False)
    assert payment_refusal(data) == ("house_account_not_allowed", message)
    with pytest.raises(ValidationError) as refused:
        _validate(data)
    assert refused.value.code == "house_account_not_allowed"
    assert refused.value.context == {"field": "payment_method"}
    assert refused.value.message == message


# ── A porta de verdade: o commit não cria o pedido ─────────────────────────────


@pytest.fixture
def web():
    Shop.objects.get_or_create(name="Nelson")
    return Channel.objects.create(ref="web", name="Loja online")


def _open_session(key, data):
    return Session.objects.create(
        session_key=key, channel_ref="web", state="open", rev=1,
        items=[{"line_id": f"L-{key}", "sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1000}],
        data=data,
    )


def test_commit_sem_forma_de_pagamento_nao_cria_pedido(web):
    from shopman.orderman import registry

    # Porteiro de toda porta: registrado sempre, fora do RuleConfig.
    assert any(isinstance(v, PaymentMethodRule) for v in registry.get_validators(stage="commit"))
    _open_session("sem-forma", {"fulfillment_type": "pickup"})

    with pytest.raises(ValidationError) as refused:
        sessions.commit_session(
            session_key="sem-forma", channel_ref="web", idempotency_key="k-sem-forma",
            seal=seal_for("sem-forma", "web"),
        )

    assert refused.value.code == "payment_method_missing"
    assert not Order.objects.exists()
    assert Session.objects.get(session_key="sem-forma").state == "open"


def test_commit_em_conta_de_quem_nao_tem_conta_nao_cria_pedido(web):
    assert PaymentMethodRule.code == "shop.payment_method"
    _customer("CLI-SEM", house_account=False)
    _open_session("conta-sem", {"fulfillment_type": "pickup", "payment": {"method": "account"},
                                "customer": {"ref": "CLI-SEM"}})

    with pytest.raises(ValidationError) as refused:
        sessions.commit_session(
            session_key="conta-sem", channel_ref="web", idempotency_key="k-conta-sem",
            seal=seal_for("conta-sem", "web"),
        )

    assert refused.value.code == "house_account_not_allowed"
    assert not Order.objects.exists()


def test_a_recusa_chega_a_tela_no_dialeto_de_erro_com_o_campo_da_forma():
    from shopman.shop.services.checkout import map_checkout_error

    refused = ValidationError(
        code="payment_method_missing", message="Escolha a forma de pagamento antes de fechar o pedido.",
        context={"field": "payment_method"},
    )
    assert map_checkout_error(refused) == {
        "payment_method": "Escolha a forma de pagamento antes de fechar o pedido.",
    }


# ── O seed não cria pedido sem forma ──────────────────────────────────────────


def test_seed_falha_gritando_se_criar_pedido_sem_forma_de_pagamento():
    from django.core.management.base import CommandError

    from config.management.commands.seed import Command

    Order.objects.create(ref="SEED-OK", channel_ref="pdv", session_key="s-ok", total_q=1000,
                         data={"payment": {"method": "cash"}})
    Command()._assert_every_order_has_payment()  # tudo certo, nada a dizer

    Order.objects.create(ref="SEED-C02", channel_ref="whatsapp", session_key="s-c02", total_q=5000, data={})
    _customer("CLI-SEM", house_account=False)
    Order.objects.create(ref="SEED-X52", channel_ref="pdv", session_key="s-x52", total_q=1000,
                         data={"payment": {"method": "account"}, "customer_ref": "CLI-SEM"})

    with pytest.raises(CommandError) as failed:
        Command()._assert_every_order_has_payment()
    assert "SEED-C02 (sem forma de pagamento)" in str(failed.value)
    assert "SEED-X52 (em conta para cliente sem conta na casa)" in str(failed.value)
    assert "SEED-OK" not in str(failed.value)


# ── O Gestor não tem mais o estado "Pagamento não informado" ─────────────────


def test_o_gestor_nao_maquia_pedido_sem_forma_grita_no_log():
    from shopman.backstage.projections import order_queue

    order = Order(ref="WEB-SEM-FORMA", channel_ref="web", total_q=5000, data={})
    with patch.object(order_queue.logger, "error") as error:
        label = order_queue._payment_method_label("", {}, order=order)

    assert label == ""
    error.assert_called_once_with("order_queue.order_without_payment order=%s", "WEB-SEM-FORMA")
