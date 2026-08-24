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


def test_sale_ops_gate_cpf_na_nota_pelo_toggle():
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
    sem_toggle = build_session_ops({**base, "issue_fiscal_document": False}, "op")
    com_toggle = build_session_ops({**base, "issue_fiscal_document": True}, "op")

    paths_sem = {op.get("path") for op in sem_toggle}
    paths_com = {op.get("path") for op in com_toggle}
    assert "customer.tax_id" in paths_sem      # identidade sempre (CRM)
    assert "fiscal.tax_id" not in paths_sem    # pedido NÃO — ninguém pediu
    assert "fiscal.tax_id" in paths_com        # pedido SIM — o toggle é o pedido


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
            "issue_fiscal_document": True,
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
    _persist_customer_from_payload({**base, "issue_fiscal_document": True}, operator_username="op")
    # "hoje não": venda seguinte sem o toggle
    _persist_customer_from_payload({**base, "issue_fiscal_document": False}, operator_username="op")

    customer = Customer.objects.get(phone="+5543999990002")
    assert customer.metadata["fiscal_prefs"]["cpf_na_nota"] is True
