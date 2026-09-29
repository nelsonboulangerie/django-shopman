"""A identidade do cliente do iFood é o ``customer.id``, não o id do pedido.

Até 19/09/2026 ``services/customer._handle_ifood`` buscava o cliente pelo
``order.external_ref`` — o id do PEDIDO. Como ele é único por compra, a busca
nunca casava: cada pedido do iFood criava um ``Customer`` ``IF-*`` novo.
Recorrência ficava impossível de apurar e o B.I. do canal contava um cliente
por venda.

Os testes aqui passam pelo ``customer.ensure`` de verdade, com o adapter real
do guestman e banco, porque o defeito era exatamente na ponte entre o que a
ingestão guardava e o que a estratégia procurava.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.shop.models import Channel
from shopman.shop.services import customer as customer_service
from shopman.shop.services import ifood_ingest

CUSTOMER_A = "dace8b15-e2be-408e-9b98-91b4e72e029f"
CUSTOMER_B = "0f1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9"


def _ingest(order_code: str, *, ifood_customer_id: str, name: str = "Ana") -> Order:
    payload = {
        "order_code": order_code,
        "merchant_id": "merchant-abc",
        "customer": {
            "name": name,
            "ifood_customer_id": ifood_customer_id,
            # O número que o iFood manda é a central deles, não o da pessoa.
            "phone": "0800 705 3040",
            "phone_localizer": "89338721",
        },
        "items": [{"sku": "PAO-001", "name": "Pão", "qty": 1, "unit_price_q": 500}],
    }
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest(payload)
    order.refresh_from_db()
    return order


@pytest.fixture
def ifood_channel(db):
    return Channel.objects.create(ref="ifood", name="iFood")


@pytest.mark.django_db
def test_dois_pedidos_do_mesmo_cliente_resolvem_para_um_customer(ifood_channel):
    primeiro = _ingest("IFOOD-260919-V76", ifood_customer_id=CUSTOMER_A)
    segundo = _ingest("IFOOD-260920-A11", ifood_customer_id=CUSTOMER_A)

    customer_service.ensure(primeiro)
    customer_service.ensure(segundo)
    primeiro.refresh_from_db()
    segundo.refresh_from_db()

    assert primeiro.data["customer_ref"] == segundo.data["customer_ref"]
    assert Customer.objects.filter(ref__startswith="IF-").count() == 1


@pytest.mark.django_db
def test_clientes_diferentes_nao_colidem(ifood_channel):
    de_ana = _ingest("IFOOD-260919-V76", ifood_customer_id=CUSTOMER_A, name="Ana")
    de_bruno = _ingest("IFOOD-260919-V77", ifood_customer_id=CUSTOMER_B, name="Bruno")

    customer_service.ensure(de_ana)
    customer_service.ensure(de_bruno)
    de_ana.refresh_from_db()
    de_bruno.refresh_from_db()

    assert de_ana.data["customer_ref"] != de_bruno.data["customer_ref"]
    assert Customer.objects.filter(ref__startswith="IF-").count() == 2


@pytest.mark.django_db
def test_o_telefone_da_central_nao_entra_no_cadastro(ifood_channel):
    """O ``phone`` do pedido do iFood é o 0800 deles — número de um terceiro."""
    order = _ingest("IFOOD-260919-V76", ifood_customer_id=CUSTOMER_A)
    customer_service.ensure(order)
    order.refresh_from_db()

    cadastrado = Customer.objects.get(ref=order.data["customer_ref"])
    assert cadastrado.phone == ""


@pytest.mark.django_db
def test_chave_antiga_ainda_e_encontrada_e_nada_e_migrado(ifood_channel):
    """Cliente criado pela chave velha (id do PEDIDO) continua alcançável.

    A segunda tentativa é só leitura e não pode casar pessoa errada: o id do
    pedido pertence a uma compra só. Ela cobre a janela em que o pedido criou
    o ``Customer`` mas perdeu o ``customer_ref`` antes de gravá-lo.
    """
    from shopman.shop.adapters import get_adapter

    order = _ingest("IFOOD-260919-V76", ifood_customer_id=CUSTOMER_A)
    adapter = get_adapter("customer")
    antigo = adapter.create_customer(
        ref="IF-LEGADO01", first_name="iFood", last_name="#IFOOD-26",
        phone="", customer_type="individual", source_system="ifood",
    )
    adapter.create_identifier(antigo["ref"], "ifood", "IFOOD-260919-V76", is_primary=True)

    customer_service.ensure(order)
    order.refresh_from_db()

    assert order.data["customer_ref"] == "IF-LEGADO01"
    # Nada de migração: o registro antigo segue com a chave que sempre teve, e
    # nenhum ``Customer`` novo nasceu para este pedido.
    assert Customer.objects.filter(ref__startswith="IF-").count() == 1


@pytest.mark.django_db
def test_pedido_sem_customer_id_cai_na_chave_do_pedido(ifood_channel):
    """Pedido antigo, ingerido antes do mapeamento novo, continua resolvendo."""
    order = _ingest("IFOOD-260101-OLD", ifood_customer_id="")
    customer_service.ensure(order)
    order.refresh_from_db()

    assert order.data["customer_ref"].startswith("IF-")
    identificadores = Customer.objects.get(ref=order.data["customer_ref"]).identifiers.all()
    assert [i.identifier_value for i in identificadores] == ["IFOOD-260101-OLD"]


@pytest.mark.django_db
def test_customer_id_fora_da_forma_de_uuid_nao_funde_pessoas(ifood_channel):
    """Sentinela repetida no lugar do UUID separaria, nunca fundiria.

    A documentação do iFood não garante durabilidade do ``customer.id``; o
    único estrago irreversível seria um valor repetido entre pessoas
    diferentes virar cadastro único. Fora da forma de UUID, a chave usada é a
    do pedido — que separa a mais.
    """
    uma = _ingest("IFOOD-260919-V80", ifood_customer_id="anonymous", name="Ana")
    outra = _ingest("IFOOD-260919-V81", ifood_customer_id="anonymous", name="Bruno")

    customer_service.ensure(uma)
    customer_service.ensure(outra)
    uma.refresh_from_db()
    outra.refresh_from_db()

    assert uma.data["customer_ref"] != outra.data["customer_ref"]
