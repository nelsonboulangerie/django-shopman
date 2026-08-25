"""CPF na nota é um PEDIDO, não uma propriedade do cadastro.

Regressão do compulsório: cliente identificado com CPF no CRM saía com o
documento em TODA nota — o servidor preenchia ``customer.tax_id`` do cadastro,
o resolver disparava por ele e o adapter o punha na NFC-e. Ninguém pediu.

A separação: ``customer.*`` é identidade (CRM, loyalty, contato);
``fiscal.tax_id`` é o pedido desta venda. O resolver lê o pedido; o payload da
emissão recebe o documento do pedido e NUNCA o do cadastro. E quem optou uma
vez fica lembrado (``Customer.metadata.fiscal_prefs``) — pré-marca a próxima
venda, sem impor.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop import fiscal_resolvers
from shopman.shop.services.fiscal import _fiscal_customer

pytestmark = pytest.mark.django_db


def _order(data):
    return SimpleNamespace(data=data, total_q=1000, channel_ref="pdv")


def test_cadastro_com_cpf_nao_dispara_emissao_sem_pedido():
    order = _order({"customer": {"name": "Ana", "tax_id": "52998224725"}, "fiscal": {}})
    assert fiscal_resolvers.on_request_or_tax_id(order) is False


def test_pedido_de_cpf_na_nota_dispara():
    order = _order({"customer": {"name": "Ana"}, "fiscal": {"tax_id": "52998224725"}})
    assert fiscal_resolvers.on_request_or_tax_id(order) is True


def test_toggle_sem_cpf_dispara_nota_sem_documento():
    order = _order({"customer": {"name": "Ana", "tax_id": "52998224725"}, "fiscal": {"issue_document": True}})
    assert fiscal_resolvers.on_request_or_tax_id(order) is True
    # ...e o payload da emissão sai SEM o CPF do cadastro:
    assert "tax_id" not in _fiscal_customer(order.data)


def test_payload_da_emissao_usa_o_documento_do_pedido():
    data = {
        "customer": {"name": "Ana", "tax_id": "11111111111", "cpf": "11111111111"},
        "fiscal": {"issue_document": True, "tax_id": "52998224725"},
    }
    customer = _fiscal_customer(data)
    assert customer["tax_id"] == "52998224725"  # o PEDIDO
    assert customer.get("cpf") is None          # nada do cadastro vaza
    assert customer["name"] == "Ana"            # identidade continua


def test_o_cpf_digitado_e_o_pedido_o_do_cadastro_nao():
    from shopman.shop.models import Channel, Shop

    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})

    from shopman.shop.services.pos import build_session_ops

    base = {
        "items": [{"sku": "X", "name": "X", "qty": 1, "unit_price_q": 100}],
        "customer_name": "Ana",
        "customer_tax_id": "52998224725",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "receipt_channels": [],
    }
    # O toggle "Emitir nota fiscal" MORREU: emitir ou não é decisão da regra do
    # servidor, não de quem está no caixa. E ele era pior que ruído — com o
    # toggle desligado o CPF digitado não virava `fiscal.tax_id`, a nota saía
    # assim mesmo (o resolver emite por forma de pagamento) e saía como
    # CONSUMIDOR NÃO IDENTIFICADO. Agora digitar o documento É o pedido.
    com_cpf = build_session_ops(base, "op")
    paths_com = {op.get("path") for op in com_cpf}
    assert "customer.tax_id" in paths_com      # identidade (CRM)
    assert "fiscal.tax_id" in paths_com        # e o pedido desta venda

    sem_cpf = build_session_ops({**base, "customer_tax_id": ""}, "op")
    assert "fiscal.tax_id" not in {op.get("path") for op in sem_cpf}


def test_cpf_que_vem_so_do_cadastro_nao_entra_na_nota(db):
    """A invariante que o #306 estabeleceu, agora sem toggle para protegê-la.

    Cliente com CPF no CRM, venda em que ninguém pediu documento: o balcão manda
    só o telefone, o servidor completa a identidade pelo cadastro — e essa
    completação NÃO pode virar pedido. Sem esta separação, todo cliente
    identificado volta a sair com o documento em toda nota, compulsório.
    """
    from shopman.guestman.models import Customer

    from shopman.shop.models import Channel, Shop
    from shopman.shop.services.pos import build_session_ops

    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
    Customer.objects.create(
        ref=Customer.generate_ref(), first_name="Rita", last_name="CRM",
        phone="+5543999990009", document="52998224725",
    )

    ops = build_session_ops({
        "items": [{"sku": "X", "name": "X", "qty": 1, "unit_price_q": 100}],
        "customer_phone": "43999990009",   # só o telefone; ninguém pediu CPF
        "payment_method": "cash",
        "payment_collection": "terminal",
        "receipt_channels": [],
    }, "op")

    paths = {op.get("path") for op in ops}
    assert "customer.tax_id" in paths       # o CRM sabe quem é
    assert "fiscal.tax_id" not in paths     # a nota, não


def test_cliente_que_optou_fica_lembrado_e_pre_marca_a_proxima():
    from shopman.guestman.models import Customer

    from shopman.backstage.projections.pos import build_pos_customer_lookup
    from shopman.shop.models import Channel, Shop
    from shopman.shop.services.pos import _persist_customer_from_payload

    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})

    _persist_customer_from_payload(
        {
            "customer_name": "Ana Prefs",
            "customer_phone": "43999990001",
            "customer_tax_id": "52998224725",
            "receipt_channels": ["email"],
            "receipt_email": "ana@example.org",
        },
        operator_username="op",
    )
    customer = Customer.objects.get(phone="+5543999990001")
    assert customer.metadata["fiscal_prefs"] == {"cpf_na_nota": True, "email_receipt": True}

    lookup = build_pos_customer_lookup("43999990001")
    assert lookup.fiscal_prefs == {"cpf_na_nota": True, "email_receipt": True}


def test_consumidor_sem_documento_nao_gera_bloco_destinatario():
    """Schema da SEFAZ: ``dest``/``enderDest`` sem CPF/CNPJ é XML inválido — o
    telefone mora DENTRO do enderDest. Sem documento, NENHUM campo sai."""
    from shopman.shop.adapters.fiscal_focusnfe import _customer_fields

    fields = _customer_fields({"name": "Prova", "phone": "43999881234", "email": "p@x.org"})
    assert fields == {}

    com_doc = _customer_fields({"name": "Prova", "phone": "43999881234", "tax_id": "52998224725"})
    assert com_doc["cpf_destinatario"] == "52998224725"
    assert com_doc["telefone_destinatario"] == "43999881234"


def test_desmarcar_numa_venda_nao_apaga_a_preferencia():
    from shopman.guestman.models import Customer

    from shopman.shop.models import Channel, Shop
    from shopman.shop.services.pos import _persist_customer_from_payload

    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})

    base = {"customer_name": "Bia", "customer_phone": "43999990002"}
    _persist_customer_from_payload({**base, "customer_tax_id": "52998224725"}, operator_username="op")
    # "hoje não": venda seguinte sem pedir o documento
    _persist_customer_from_payload({**base, "customer_tax_id": ""}, operator_username="op")

    customer = Customer.objects.get(phone="+5543999990002")
    assert customer.metadata["fiscal_prefs"]["cpf_na_nota"] is True
