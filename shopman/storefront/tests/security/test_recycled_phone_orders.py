"""OC-02 / X7: pedido com dono declarado não abre por coincidência de telefone.

Operadora recicla número. Quem herda o número (B) não pode ver os pedidos de
quem o tinha antes (A): pedido com ``customer_ref`` (ou ``customer.ref``) só casa
pelo ref. Telefone continua casando pedido SEM dono declarado (convidado).

A matriz cobre os três consumidores da mesma regra
(``customer_orders.customer_identity_filter``): o casamento individual (acesso
ao pedido, API e SSE), o histórico/contagens do serviço e a projeção do cliente,
mais a Concierge, que pergunta pela mesma função.
"""
from __future__ import annotations

import pytest
from django.test import Client

from shopman.shop.projections import customer as customer_projection
from shopman.shop.services import customer_orders

from .conftest import login_as_customer

pytestmark = pytest.mark.django_db

PREVIOUS_REF = "CUST-ANTERIOR"


@pytest.fixture
def previous_owner(db):
    """A: tinha o número, trocou de chip. O cadastro dele segue vivo, sem o número."""
    from shopman.guestman.models import Customer

    return Customer.objects.create(ref=PREVIOUS_REF, first_name="Ana", last_name="Antes", phone="")


@pytest.fixture
def matrix(customer, previous_owner, channel):
    """Pedidos no MESMO telefone: de A (dono declarado), de B e de convidado."""
    from shopman.orderman.models import Order

    phone = customer.phone

    def make(ref, *, data, status="new", handle_type="phone", handle_ref=phone):
        return Order.objects.create(
            ref=ref,
            channel_ref=channel.ref,
            status=status,
            total_q=1000,
            handle_type=handle_type,
            handle_ref=handle_ref,
            data=data,
        )

    return {
        "a_top": make("ORD-A-TOP", data={"customer_ref": PREVIOUS_REF, "customer": {"ref": PREVIOUS_REF, "phone": phone}}),
        "a_nested": make("ORD-A-NESTED", data={"customer": {"ref": PREVIOUS_REF, "phone": phone}}),
        "a_done": make("ORD-A-DONE", status="completed", data={"customer_ref": PREVIOUS_REF}),
        "b_own": make("ORD-B-OWN", data={"customer_ref": customer.ref}),
        "guest_handle": make("ORD-GUEST-HANDLE", data={}),
        "guest_digits": make("ORD-GUEST-DIGITS", data={}, handle_ref=phone.lstrip("+")),
        "guest_snapshot": make(
            "ORD-GUEST-SNAPSHOT",
            handle_type="ifood",
            handle_ref="IFOOD-123",
            data={"customer_ref": "", "customer": {"phone": phone}},
        ),
    }


A_ORDERS = ("a_top", "a_nested", "a_done")
GUEST_ORDERS = ("guest_handle", "guest_digits", "guest_snapshot")


# ── Casamento individual ─────────────────────────────────────────────


@pytest.mark.parametrize("key", A_ORDERS)
def test_ref_igual_casa(matrix, key):
    assert customer_orders.order_matches_customer_identity(matrix[key], customer_ref=PREVIOUS_REF)


@pytest.mark.parametrize("key", A_ORDERS)
def test_ref_diferente_com_mesmo_telefone_nao_casa(matrix, customer, key):
    order = matrix[key]
    assert not customer_orders.order_matches_customer_identity(
        order, customer_ref=customer.ref, phone=customer.phone
    )
    assert not customer_orders.order_matches_customer_identity(order, phone=customer.phone)


@pytest.mark.parametrize("key", GUEST_ORDERS)
def test_convidado_sem_ref_continua_casando_por_telefone(matrix, customer, key):
    order = matrix[key]
    assert customer_orders.order_matches_customer_identity(order, phone=customer.phone)
    assert customer_orders.order_matches_customer_identity(
        order, customer_ref=customer.ref, phone=customer.phone
    )
    assert customer_orders.order_matches_customer_identity(order, phone="(43) 99999-0001")


def test_pedido_nao_salvo_nunca_casa(customer):
    from shopman.orderman.models import Order

    order = Order(ref="ORD-UNSAVED", handle_type="phone", handle_ref=customer.phone, data={})
    assert not customer_orders.order_matches_customer_identity(order, phone=customer.phone)


# ── Histórico, contagens e projeção do cliente ───────────────────────


def _b_visible_refs(matrix):
    return {matrix["b_own"].ref, *(matrix[key].ref for key in GUEST_ORDERS)}


def test_projecao_do_historico_nao_mostra_pedido_de_a_para_b(matrix, customer):
    summaries = customer_projection.history_summaries_for_customer(
        customer_ref=customer.ref, phone=customer.phone
    )
    assert {summary.ref for summary in summaries} == _b_visible_refs(matrix)


def test_historico_so_por_telefone_mostra_apenas_convidado(matrix, customer):
    summaries = customer_projection.history_summaries_for_phone(customer.phone)
    assert {summary.ref for summary in summaries} == {matrix[key].ref for key in GUEST_ORDERS}


def test_historico_de_a_pelo_ref_continua_inteiro(matrix):
    summaries = customer_projection.history_summaries_for_customer_ref(PREVIOUS_REF)
    assert {summary.ref for summary in summaries} == {matrix[key].ref for key in A_ORDERS}


def test_contagens_de_b_nao_somam_pedidos_de_a(matrix, customer):
    active = customer_orders.active_order_count_for_customer(customer_ref=customer.ref, phone=customer.phone)
    total = customer_orders.order_count_for_customer(customer_ref=customer.ref, phone=customer.phone)
    assert total == len(_b_visible_refs(matrix))
    assert active == len(_b_visible_refs(matrix))  # todos os de B estão em "new"


def test_repetir_pedido_de_b_nunca_parte_do_pedido_de_a(matrix, customer):
    from datetime import timedelta

    from django.utils import timezone
    from shopman.orderman.models import Order

    # A recompra só oferece pedido concluído (#3560): o de A, concluído, é o mais
    # recente de todos no número, e o de B também está concluído.
    Order.objects.filter(pk=matrix["a_top"].pk).update(
        status="completed", created_at=timezone.now() + timedelta(minutes=5)
    )
    Order.objects.filter(pk=matrix["b_own"].pk).update(status="completed")
    order_ref, _items = customer_orders.last_reorder_context(customer_uuid=customer.uuid, min_days=0)
    assert order_ref == matrix["b_own"].ref


# ── API: o novo titular do número recebe 404, como pedido inexistente ─


@pytest.mark.parametrize("key", A_ORDERS)
def test_novo_titular_do_numero_recebe_404_no_pedido_de_a(matrix, customer, key):
    client = Client()
    login_as_customer(client, customer)
    foreign = client.get(f"/api/v1/tracking/{matrix[key].ref}/")
    missing = client.get("/api/v1/tracking/ORD-NAO-EXISTE/")
    assert foreign.status_code == missing.status_code == 404


def test_titular_abre_o_proprio_pedido_pela_api(matrix, customer):
    client = Client()
    login_as_customer(client, customer)
    response = client.get(f"/api/v1/tracking/{matrix['b_own'].ref}/")
    assert response.status_code == 200


# ── SSE: a permissão do canal do pedido (usuário logado, ref + telefone) ─


def test_canal_do_pedido_obedece_a_mesma_regra(matrix, customer):
    from shopman.doorman.models import CustomerUser

    client = Client()
    user = login_as_customer(client, customer)
    assert CustomerUser.objects.filter(user=user, customer_id=customer.uuid).exists()
    for key in A_ORDERS:
        assert not customer_orders.user_can_access_order(user, matrix[key])
    assert customer_orders.user_can_access_order(user, matrix["b_own"])
    for key in GUEST_ORDERS:
        assert customer_orders.user_can_access_order(user, matrix[key])


# ── Concierge: a conversa de B não acha o pedido de A ────────────────


def test_conversa_de_b_nao_acha_pedido_de_a(matrix, customer):
    from shopman.shop.models import Conversation
    from shopman.storefront.concierge.cancellation import target_order

    conversation = Conversation.objects.create(phone=customer.phone, customer_ref=customer.ref)
    for key in A_ORDERS:
        assert target_order(conversation, order_ref=matrix[key].ref) is None
    assert target_order(conversation, order_ref=matrix["b_own"].ref) == matrix["b_own"]
    assert target_order(conversation, order_ref=matrix["guest_handle"].ref) == matrix["guest_handle"]
