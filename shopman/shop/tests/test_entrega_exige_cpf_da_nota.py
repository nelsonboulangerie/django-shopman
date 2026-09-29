"""Entrega com NFC-e não entra sem CPF/CNPJ e endereço completo (decisão do dono, 24/09/2026).

A SEFAZ recusa a nota de entrega a domicílio sem a identificação do consumidor
e sem o endereço completo (787/788). Antes, o pedido entrava e a recusa só
aparecia na emissão, com o entregador na rua. Estes testes provam:

- a régua da porta é a MESMA da emissão (o adapter Focus monta a recusa dela);
- "vai ter nota?" é a pergunta do resolver fiscal, não uma cópia;
- a trava do commit recusa com o campo certo, e deixa passar retirada e
  entrega sem nota;
- o PDV recusa no fechamento com o campo "CPF na nota" e publica a exigência
  na review.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from shopman.orderman.exceptions import ValidationError as OrderValidationError

from shopman.shop.services import delivery_fiscal_identity as identity
from shopman.shop.services import fiscal

CPF = "52998224725"
ADDRESS = {
    "formatted_address": "Rua Pará, 86 - Centro, Londrina - PR",
    "route": "Rua Pará",
    "street_number": "86",
    "neighborhood": "Centro",
    "city": "Londrina",
    "state_code": "PR",
    "postal_code": "86010-000",
}
ELECTRONIC_OR_ON_DELIVERY = (
    "shopman.shop.fiscal_resolvers.on_request_or_tax_id,"
    "shopman.shop.fiscal_resolvers.eletronic_payment,"
    "shopman.shop.fiscal_resolvers.deferred_settlement"
)


@pytest.fixture
def emits(monkeypatch, settings):
    """Backend fiscal ligado e a regra do alpha: pagamento eletrônico ou na entrega emite."""
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = ELECTRONIC_OR_ON_DELIVERY


def _order(**data):
    return identity.order_view(data=data, channel_ref="web")


# ── A régua ───────────────────────────────────────────────────────────────


def test_endereco_completo_e_cpf_valido_nao_tem_lacuna():
    assert identity.recipient_gaps(tax_id=CPF, address=ADDRESS) == []


def test_sem_cpf_e_cpf_errado_sao_lacunas_diferentes():
    missing = identity.recipient_gaps(tax_id="", address=ADDRESS)
    wrong = identity.recipient_gaps(tax_id="52998224700", address=ADDRESS)
    assert [g.code for g in missing] == ["delivery_tax_id_required"]
    assert [g.code for g in wrong] == ["delivery_tax_id_invalid"]
    assert missing[0].field == wrong[0].field == "fiscal_tax_id"


def test_endereco_so_texto_lista_cada_parte_que_falta():
    gaps = identity.recipient_gaps(tax_id=CPF, address={"formatted_address": "Rua Pará, 86"})
    assert {g.field for g in gaps} == {"delivery_address"}
    assert [g.label for g in gaps] == [
        "logradouro", "número (ou S/N explicitamente informado)", "bairro", "município",
        "UF válida", "CEP de 8 dígitos",
    ]
    message = identity.address_gap_message(gaps)
    assert message == (
        "Para a nota fiscal da entrega, falta no endereço: a rua, o número (ou S/N), o bairro, "
        "a cidade, o estado e o CEP."
    )
    assert "—" not in message


@pytest.mark.django_db
def test_o_adapter_da_emissao_recusa_com_a_mesma_regua():
    """A emissão e a porta leem a mesma função: o que a porta deixa passar, a nota aceita."""
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFePayloadError, _home_delivery_fields

    with pytest.raises(FocusNFePayloadError) as exc:
        _home_delivery_fields({}, {"tax_id": ""}, {"address": {**ADDRESS, "postal_code": ""}})
    assert str(exc.value) == "Entrega a domicílio: confira CPF/CNPJ solicitado para a nota, CEP de 8 dígitos."

    fields = _home_delivery_fields({"cnpj_emitente": "11222333000181"}, {"tax_id": CPF}, {"address": ADDRESS})
    assert fields["cep_destinatario"] == "86010000"
    assert fields["uf_destinatario"] == "PR"


# ── "Vai ter nota?" é a pergunta da emissão ───────────────────────────────


def test_sem_backend_fiscal_nada_e_exigido(monkeypatch, settings):
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: None)
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.always"
    assert identity.delivery_fiscal_gaps(_order(fulfillment_type="delivery")) == []


def test_retirada_nunca_exige(emits):
    assert identity.delivery_fiscal_gaps(_order(fulfillment_type="pickup", payment={"method": "pix"})) == []


def test_entrega_com_pix_exige_cpf(emits):
    gaps = identity.delivery_fiscal_gaps(
        _order(fulfillment_type="delivery", payment={"method": "pix"}, delivery_address_structured=ADDRESS)
    )
    assert [g.code for g in gaps] == ["delivery_tax_id_required"]


def test_entrega_que_a_regra_nao_emite_passa_sem_cpf(monkeypatch, settings):
    """Dinheiro pago no balcão e regra só "a pedido": não há nota, não há exigência."""
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
    order = _order(fulfillment_type="delivery", payment={"method": "cash"})
    assert identity.delivery_fiscal_gaps(order) == []


def test_cpf_errado_e_recusado_mesmo_onde_a_regra_nao_emitiria(monkeypatch, settings):
    """CPF informado JÁ é pedido de nota (``on_request_or_tax_id``)."""
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
    order = _order(
        fulfillment_type="delivery", payment={"method": "cash"},
        fiscal={"tax_id": "11111111111"}, delivery_address_structured=ADDRESS,
    )
    assert identity.refusal(identity.delivery_fiscal_gaps(order))[0] == "delivery_tax_id_invalid"


# ── A trava do commit ─────────────────────────────────────────────────────


def _session(data, items=None):
    return SimpleNamespace(data=data, items=items or [{"sku": "PAO", "line_total_q": 1200}])


def _validate(data):
    from shopman.shop.rules.validation import DeliveryFiscalIdentityRule

    DeliveryFiscalIdentityRule().validate(channel=SimpleNamespace(ref="web"), session=_session(data), ctx={})


def test_commit_recusa_entrega_sem_cpf_apontando_o_campo(emits):
    with pytest.raises(OrderValidationError) as exc:
        _validate({"fulfillment_type": "delivery", "payment": {"method": "pix"}, "delivery_address_structured": ADDRESS})
    assert exc.value.code == "delivery_tax_id_required"
    assert exc.value.context == {"field": "fiscal_tax_id"}
    assert exc.value.message == "Para entregar, precisamos do CPF ou CNPJ para a nota fiscal."


def test_commit_recusa_endereco_incompleto_depois_do_cpf(emits):
    with pytest.raises(OrderValidationError) as exc:
        _validate({
            "fulfillment_type": "delivery", "payment": {"method": "card"},
            "fiscal": {"tax_id": CPF}, "delivery_address_structured": {**ADDRESS, "neighborhood": ""},
        })
    assert exc.value.code == "delivery_address_incomplete"
    assert exc.value.context == {"field": "delivery_address"}
    assert "o bairro" in exc.value.message


def test_commit_deixa_passar_entrega_completa_e_retirada(emits):
    _validate({
        "fulfillment_type": "delivery", "payment": {"method": "pix"},
        "fiscal": {"tax_id": CPF}, "delivery_address_structured": ADDRESS,
    })
    _validate({"fulfillment_type": "pickup", "payment": {"method": "pix"}})


def test_a_trava_esta_registrada_no_commit():
    from shopman.orderman import registry

    codes = {getattr(v, "code", "") for v in registry.get_validators(stage="commit")}
    assert "shop.delivery_fiscal_identity" in codes


def test_erro_do_checkout_chega_no_campo_do_cpf():
    from shopman.shop.services.checkout import map_checkout_error

    exc = OrderValidationError(
        code="delivery_tax_id_required", message="m", context={"field": "fiscal_tax_id"},
    )
    assert map_checkout_error(exc) == {"fiscal_tax_id": "m"}


# ── Pré-preenchimento da próxima entrega: lê, nunca grava ─────────────────


@pytest.mark.django_db
def test_pre_preenche_com_a_ultima_entrega_da_propria_pessoa():
    from shopman.guestman.models import Customer
    from shopman.orderman.models import Order

    from shopman.shop.projections.delivery_fiscal import FROM_LAST_DELIVERY, delivery_tax_id_prefill

    ana = Customer.objects.create(ref="ANA", first_name="Ana", phone="+5543999990001")
    assert delivery_tax_id_prefill(ana.uuid).tax_id == ""

    def pedido(ref, *, customer_ref, fulfillment_type, tax_id):
        Order.objects.create(ref=ref, channel_ref="web", status="new", total_q=100, data={
            "customer_ref": customer_ref, "fulfillment_type": fulfillment_type, "fiscal": {"tax_id": tax_id},
        })

    pedido("E-1", customer_ref="ANA", fulfillment_type="delivery", tax_id="11144477735")
    pedido("E-2", customer_ref="ANA", fulfillment_type="delivery", tax_id=CPF)
    pedido("R-1", customer_ref="ANA", fulfillment_type="pickup", tax_id="11222333000181")
    pedido("J-1", customer_ref="JOAO", fulfillment_type="delivery", tax_id="11222333000181")

    prefill = delivery_tax_id_prefill(ana.uuid)
    assert (prefill.tax_id, prefill.source) == (CPF, FROM_LAST_DELIVERY)
    ana.refresh_from_db()
    assert ana.document == ""


@pytest.mark.django_db
def test_documento_do_cadastro_vem_antes_da_ultima_entrega():
    from shopman.guestman.models import Customer

    from shopman.shop.projections.delivery_fiscal import FROM_DOCUMENT, delivery_tax_id_prefill

    ana = Customer.objects.create(ref="ANA", first_name="Ana", phone="+5543999990001", document=CPF)
    prefill = delivery_tax_id_prefill(ana.uuid)
    assert (prefill.tax_id, prefill.source) == (CPF, FROM_DOCUMENT)
