"""Excluir a conta: o que já recusaria a exclusão aparece ANTES do código.

Beta 06/11: o cliente pedia a exclusão, recebia o SMS, digitava o código e só então
lia "Ainda existe um pedido em andamento", sem saber qual pedido. O bloqueio era
conhecido de antemão; o SMS foi gasto à toa e a frase não levava a lugar nenhum.
"""

from __future__ import annotations

import uuid

import pytest
from django.test import Client
from shopman.doorman.models import VerificationCode
from shopman.guestman.models import Customer
from shopman.orderman.models import Directive, Order

from shopman.shop import directives

pytestmark = pytest.mark.django_db


def _customer() -> Customer:
    return Customer.objects.create(
        ref="CUS-EXCL-01", first_name="Ana", last_name="Silva", phone="+5543999990301",
    )


def _login(client: Client, customer: Customer, *, step_up: bool = False) -> None:
    from shopman.doorman import get_or_create_user_for_customer

    from shopman.storefront.tests.identity_fakes import grant_recent_step_up, make_identity_view

    info = make_identity_view(
        subject_id=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    if step_up:
        grant_recent_step_up(client, customer.uuid, "delete")


def _order(customer: Customer, *, ref: str, status: str) -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"sess-{ref}",
        handle_type="phone",
        handle_ref=customer.phone,
        status=status,
        data={"customer_ref": customer.ref},
    )


def _preflight(client: Client):
    return client.get("/api/v1/account/delete/")


def test_sem_bloqueio_a_conferencia_libera(client: Client):
    customer = _customer()
    _order(customer, ref="EXCL-DONE", status=Order.Status.COMPLETED)
    _login(client, customer)

    resposta = _preflight(client)

    assert resposta.status_code == 200
    assert resposta.json()["blocked"] is False


def test_pedido_em_andamento_aparece_antes_do_codigo_e_com_nome(client: Client):
    customer = _customer()
    _order(customer, ref="EXCL-ATIVO", status="preparing")
    _login(client, customer)

    resposta = _preflight(client)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["blocked"] is True
    assert corpo["error"] == {"code": "account_deletion_blocked", "reason": "active_order"}
    assert corpo["order_ref"] == "EXCL-ATIVO"
    assert "EXCL-ATIVO" in corpo["detail"]
    assert [a["href"] for a in corpo["actions"]] == ["/pedido/EXCL-ATIVO"]
    # Conferir não gasta código: nenhum SMS saiu para o cliente.
    assert not VerificationCode.objects.exists()
    # E não muda nada na conta.
    customer.refresh_from_db()
    assert customer.is_active is True


def test_etapa_em_aberto_diz_qual_e_o_que_esperar(client: Client):
    customer = _customer()
    _order(customer, ref="EXCL-NOTA", status=Order.Status.COMPLETED)
    Directive.objects.create(
        topic=directives.FISCAL_EMIT_NFCE,
        payload={"order_ref": "EXCL-NOTA"},
    )
    _login(client, customer)

    corpo = _preflight(client).json()

    assert corpo["blocked"] is True
    assert corpo["error"]["reason"] == "order_obligation_pending"
    assert corpo["order_ref"] == "EXCL-NOTA"
    assert "a nota fiscal" in corpo["detail"]
    assert "EXCL-NOTA" in corpo["detail"]
    assert "etapa obrigatória" not in corpo["detail"]
    assert "—" not in corpo["detail"]


def test_aviso_pessoal_na_fila_nao_bloqueia(client: Client):
    customer = _customer()
    _order(customer, ref="EXCL-AVISO", status=Order.Status.COMPLETED)
    Directive.objects.create(
        topic=directives.NOTIFICATION_SEND,
        payload={"order_ref": "EXCL-AVISO"},
    )
    _login(client, customer)

    assert _preflight(client).json()["blocked"] is False


def test_a_recusa_da_exclusao_tambem_nomeia_o_pedido(client: Client):
    customer = _customer()
    _order(customer, ref="EXCL-409", status="preparing")
    _login(client, customer, step_up=True)
    csrf = client.get("/api/v1/storefront/cart/").cookies["csrftoken"].value

    resposta = client.post(
        "/api/v1/account/delete/",
        data={"acknowledged": True},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["error"]["reason"] == "active_order"
    assert corpo["order_ref"] == "EXCL-409"
    assert corpo["actions"][0]["href"] == "/pedido/EXCL-409"


def test_anonimo_nao_confere_nada(client: Client):
    assert _preflight(client).status_code == 401
