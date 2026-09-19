"""A nota de uma venda por marketplace declara a venda DA CASA, e diz quem intermediou.

Auditoria de 19/09/2026. Três fatos externos sustentam cada asserção daqui:

- iFood, portal do desenvolvedor ("Detalhes de pedido"): a composição é
  ``orderAmount = subTotal + deliveryFee + additionalFees − benefits``, e as
  ``additionalFees`` "representam receita do iFood e não devem ser adicionadas
  à nota fiscal".
- iFood, blog de parceiros: entrega da LOJA ⇒ a taxa consta na nota; entrega do
  IFOOD ⇒ não consta.
- Ajuste SINIEF 22/20 (CONFAZ, efeitos desde abr/2021): a NFC-e identifica o
  intermediador da transação (``indIntermed`` + grupo ``infIntermed``).

Metade destes testes é sobre o pedido do canal próprio continuar **exatamente**
como era. É essa metade que impede a correção de vazar para o balcão.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings
from shopman.orderman.models import Order, OrderItem

from shopman.shop import fiscal_intermediary
from shopman.shop.models import Channel
from shopman.shop.services import fiscal, ifood_ingest, ifood_orders

pytestmark = pytest.mark.django_db

IFOOD_CNPJ = "14380200000121"

#: Configuração COMPLETA: com ela o grupo do intermediador sai na nota.
INTERMEDIARIES = {"ifood": {"cnpj": IFOOD_CNPJ, "id_cad_int_tran": "MERCHANT-42"}}
#: Sem o identificador do cadastro da loja — o estado de hoje, de propósito.
INTERMEDIARIES_SEM_ID = {"ifood": {"cnpj": IFOOD_CNPJ, "id_cad_int_tran": ""}}

FISCAL_OWN_PRODUCTION = {
    "ncm": "19059090",
    "cfop": "5102",
    "icms_origem": "0",
    "icms_situacao_tributaria": "102",
    "pis_situacao_tributaria": "99",
    "cofins_situacao_tributaria": "99",
}


def _focus_settings():
    return {
        "environment": "homologacao",
        "token": "focus-token",
        "cnpj_emitente": "12.345.678/0001-99",
        "serie_nfce": "1",
        "timeout": 10,
    }


def ingest_ifood(*, delivered_by="IFOOD", order_type="DELIVERY", subtotal=3000,
                 delivery_fee=799, additional_fees=150, benefits=0, sem_documento=False):
    """Pedido iFood real: um item de R$ 30,00 mais o que a plataforma cobrou.

    ``sem_documento`` é o caso COMUM na vida real, não a exceção: o iFood só
    repassa ``customer.documentNumber`` quando o cliente pede a nota.
    """
    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    order_amount = subtotal + delivery_fee + additional_fees - benefits
    documento = {} if sem_documento else {"documentNumber": "52998224725", "documentType": "CPF"}
    payload = ifood_orders.map_order({
        "id": f"ifood-{delivered_by}-{order_type}-{additional_fees}-{int(sem_documento)}",
        "orderType": order_type,
        "merchant": {"id": "merchant"},
        "customer": {"name": "Cliente iFood", **documento},
        # Na retirada o iFood não manda endereço nenhum — só a entrega tem.
        "delivery": {
            "deliveredBy": delivered_by,
            **({"deliveryAddress": {
                "formattedAddress": "Rua X, 123", "streetName": "Rua X", "streetNumber": "123",
                "neighborhood": "Centro", "city": "Londrina", "state": "PR", "postalCode": "86010000",
            }} if order_type == "DELIVERY" else {}),
        },
        "items": [{"id": "item-1", "externalCode": "PAO-001", "name": "Pão",
                   "quantity": 1, "unitPrice": subtotal / 100, "totalPrice": subtotal / 100}],
        "total": {
            "subTotal": subtotal / 100, "deliveryFee": delivery_fee / 100,
            "additionalFees": additional_fees / 100, "benefits": benefits / 100,
            "orderAmount": order_amount / 100,
        },
    })
    with patch.object(ifood_ingest.order_changed, "send"):
        return ifood_ingest.ingest(payload)


def counter_order(total_q=3000):
    """Pedido do canal próprio: o controle desta suíte."""
    Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV"})
    order = Order.objects.create(
        ref="ORD-PDV-INTERMEDIARY-1", channel_ref="pdv",
        status=Order.Status.COMPLETED, total_q=total_q,
        data={"payment": {"method": "cash", "amount_q": total_q}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO-001", name="Pão",
                             qty=1, unit_price_q=total_q, line_total_q=total_q)
    return order


# ── 0. O endereço que faltava para a nota de entrega sair ─────────────────


def test_the_ifood_delivery_address_reaches_the_note_as_components_not_only_as_text():
    """Sem logradouro/número/bairro/município/UF, a NFC-e de entrega nem sai.

    Medido em 19/09/2026 com a #886 já no ``main``: o destinatário da nota é
    montado de COMPONENTE, e o ingest só gravava complemento, referência e CEP
    — o resto morria dentro do ``formattedAddress``. A emissão era recusada
    antes do HTTP, então toda a correção de valor desta PR ficaria dormente.
    """
    order = ingest_ifood(order_type="DELIVERY")

    estruturado = order.data["delivery_address_structured"]

    assert estruturado["route"] == "Rua X"
    assert estruturado["street_number"] == "123"
    assert estruturado["neighborhood"] == "Centro"
    assert estruturado["city"] == "Londrina"
    assert estruturado["state_code"] == "PR"
    assert estruturado["postal_code"] == "86010000"
    # O texto formatado continua com um dono só: ``delivery_address``.
    assert "formatted_address" not in estruturado
    assert order.data["delivery_address"] == "Rua X, 123"


def test_a_pickup_order_gets_no_address_components_at_all():
    order = ingest_ifood(order_type="TAKEOUT", delivery_fee=0)

    assert order.data["fulfillment_type"] == "pickup"
    assert "route" not in (order.data.get("delivery_address_structured") or {})


# ── 1. A base da nota não carrega receita do iFood ────────────────────────


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_ifood_delivered_note_drops_platform_revenue_and_the_platform_freight():
    order = ingest_ifood(delivered_by="IFOOD", subtotal=3000, delivery_fee=799, additional_fees=150)

    # O TOTAL DO PEDIDO não muda de significado: é o que o cliente pagou ao iFood.
    assert order.total_q == 3949
    assert fiscal_intermediary.seller_amounts(order) == {"base_q": 3000, "freight_q": 0}
    assert fiscal.note_base_q(order) == 3000


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_merchant_delivered_note_keeps_the_freight_the_house_actually_charged():
    order = ingest_ifood(delivered_by="MERCHANT", subtotal=3000, delivery_fee=799, additional_fees=150)

    assert order.total_q == 3949
    # Só a receita da plataforma sai; o frete é da casa e fica.
    assert fiscal_intermediary.seller_amounts(order) == {"base_q": 3799, "freight_q": 799}


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_the_freight_rule_reads_delivered_by_instead_of_assuming_the_house_never_delivers():
    """Hoje a Nelson nunca entrega pedido do iFood — a regra ainda é lida do campo."""
    entregue_pelo_ifood = ingest_ifood(delivered_by="IFOOD", delivery_fee=799)
    entregue_pela_casa = ingest_ifood(delivered_by="MERCHANT", delivery_fee=799)

    assert fiscal_intermediary.seller_amounts(entregue_pelo_ifood)["freight_q"] == 0
    assert fiscal_intermediary.seller_amounts(entregue_pela_casa)["freight_q"] == 799


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_an_ifood_order_without_the_financial_breakdown_is_left_alone():
    """Simulação/payload antigo não manda ``totals`` — não é motivo para inventar número."""
    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest({
            "order_code": "sem-totais",
            "items": [{"sku": "PAO-001", "qty": 1, "unit_price_q": 1000}],
        })

    assert fiscal_intermediary.seller_amounts(order) is None
    assert fiscal.note_base_q(order) == order.total_q == 1000


# ── 2. O pedido do canal próprio não muda em NADA ─────────────────────────


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_counter_sale_has_no_intermediary_and_keeps_the_order_total_as_the_note_base():
    order = counter_order(total_q=3000)

    assert fiscal_intermediary.is_intermediated(order) is False
    assert fiscal_intermediary.seller_amounts(order) is None
    assert fiscal_intermediary.intermediary_for(order) is None
    assert fiscal_intermediary.missing_configuration(order) == ""
    assert fiscal.note_base_q(order) == 3000


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_counter_sale_payload_carries_no_intermediary_key_at_all():
    order = counter_order(total_q=3000)

    payload = fiscal.build_emission_payload(order)

    assert "intermediary" not in payload
    assert payload["payment"]["amount_q"] == 3000
    assert [item["sku"] for item in payload["items"]] == ["PAO-001"]


@override_settings(SHOPMAN_FOCUS_NFE=_focus_settings())
def test_a_counter_note_payload_has_none_of_the_intermediary_fields():
    """Sem intermediador, o documento sai idêntico ao que já saía."""
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(payload=payload)
        return {"status": "autorizado", "chave_nfe": "K" * 44}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        FocusNFeBackend().emit(
            reference="ORD-PDV-1",
            items=[{"sku": "PAO-001", "name": "Pão", "qty": "1", "unit": "un",
                    "unit_price_q": 3000, "total_q": 3000, "fiscal": FISCAL_OWN_PRODUCTION}],
            customer={}, payment={"method": "cash", "amount_q": 3000},
        )

    for field in ("indicador_intermediario", "cnpj_intermediario", "id_intermediario"):
        assert field not in captured["payload"]
    assert captured["payload"]["presenca_comprador"] == "1"


# ── 3. O grupo do intermediador (Ajuste SINIEF 22/20) ─────────────────────


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_the_intermediary_group_reaches_the_directive_payload():
    order = ingest_ifood()

    payload = fiscal.build_emission_payload(order)

    assert payload["intermediary"] == {"cnpj": IFOOD_CNPJ, "id_cad_int_tran": "MERCHANT-42"}


@override_settings(SHOPMAN_FOCUS_NFE=_focus_settings())
def test_the_intermediary_group_is_mapped_to_the_focus_field_names_flat_at_the_root():
    """``intermediario``, com "i" — e sem objeto ``infIntermed``, como a Focus documenta."""
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(payload=payload)
        return {"status": "autorizado", "chave_nfe": "K" * 44}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference="ORD-IFOOD-1",
            items=[{"sku": "PAO-001", "name": "Pão", "qty": "1", "unit": "un",
                    "unit_price_q": 3000, "total_q": 3000, "fiscal": FISCAL_OWN_PRODUCTION}],
            customer={}, payment={"method": "external", "amount_q": 3000},
            intermediary={"cnpj": IFOOD_CNPJ, "id_cad_int_tran": "MERCHANT-42"},
        )

    assert result.success is True
    assert captured["payload"]["indicador_intermediario"] == "1"
    assert captured["payload"]["cnpj_intermediario"] == IFOOD_CNPJ
    assert captured["payload"]["id_intermediario"] == "MERCHANT-42"
    # ⚠️ O grupo NÃO mexe no indPres. Ver test_nfce_only_accepts_indpres_1_or_4.
    assert captured["payload"]["presenca_comprador"] == "1"


@override_settings(SHOPMAN_FOCUS_NFE=_focus_settings())
def test_home_delivery_keeps_indpres_4_when_there_is_an_intermediary():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(payload=payload)
        return {"status": "autorizado", "chave_nfe": "K" * 44}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference="ORD-IFOOD-2",
            items=[{"sku": "PAO-001", "name": "Pão", "qty": "1", "unit": "un",
                    "unit_price_q": 3000, "total_q": 3000, "fiscal": FISCAL_OWN_PRODUCTION}],
            customer={"tax_id": "52998224725", "name": "Cliente"},
            payment={"method": "external", "amount_q": 3000},
            delivery={"address": {"route": "Rua X", "street_number": "123", "neighborhood": "Centro",
                                  "city": "Londrina", "state_code": "PR", "postal_code": "86010000"}},
            intermediary={"cnpj": IFOOD_CNPJ, "id_cad_int_tran": "MERCHANT-42"},
        )

    assert result.success is True
    assert captured["payload"]["presenca_comprador"] == "4"
    assert captured["payload"]["indicador_intermediario"] == "1"


@override_settings(SHOPMAN_FOCUS_NFE=_focus_settings())
def test_half_an_intermediary_group_is_refused_before_the_http_call():
    """A Focus exige CNPJ e identificador juntos: meio grupo é nota recusada."""
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    with patch("shopman.shop.adapters.fiscal_focusnfe._request") as request:
        result = FocusNFeBackend().emit(
            reference="ORD-IFOOD-3",
            items=[{"sku": "PAO-001", "name": "Pão", "qty": "1", "unit": "un",
                    "unit_price_q": 3000, "total_q": 3000, "fiscal": FISCAL_OWN_PRODUCTION}],
            customer={}, payment={"method": "external", "amount_q": 3000},
            intermediary={"cnpj": IFOOD_CNPJ, "id_cad_int_tran": ""},
        )

    request.assert_not_called()
    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES_SEM_ID)
def test_an_intermediated_sale_without_the_group_screams_instead_of_emitting_in_silence():
    """Nota válida e fora do Ajuste SINIEF 22/20 é o pior defeito: nada reclama."""
    order = ingest_ifood()

    with patch("shopman.shop.services.observability.create_operator_alert") as alert:
        payload = fiscal.build_emission_payload(order)

    assert "intermediary" not in payload
    alert.assert_called_once()
    assert alert.call_args.kwargs["type"] == "fiscal_intermediary_not_declared"
    assert "idCadIntTran" in alert.call_args.kwargs["message"]


# ── 3b. O indPres da NFC-e, travado por tipo de operação ──────────────────
#
# Esta seção existe por causa de um defeito MEU, pego em revisão antes do
# merge. Eu li na referência de campos da Focus que o grupo do intermediador
# "apenas pode ser informado se a operação for não-presencial (2, 3, 4 ou 9)",
# concluí que pedido de app não é balcão, e troquei o indPres de 1 para 2 na
# venda intermediada sem entrega.
#
# Está errado, e erra de um jeito que não aparece. Duas coisas que eu tinha
# trocado, verificadas depois na fonte (NT baixada do Portal da NF-e e MOC
# Online da SEFAZ-PR, não em blog):
#
# 1. A página de campos da Focus é COMPARTILHADA entre NF-e (modelo 55) e
#    NFC-e (modelo 65), e aquela régua é a do 55. Na NFC-e vale a B25b-20 →
#    Rejeição 717, que recusa todo indPres fora de {1, 4, 5}. O `2` é recusado
#    em TODAS as versões da regra — quebraria justamente a retirada, que é o
#    caso que hoje funciona.
# 2. A regra que eu supus ("o grupo exige operação não presencial") NÃO EXISTE.
#    A NT 2020.006 v1.31 diz o oposto na letra, e a B25c-20 só proíbe o
#    intermediador quando indPres está fora de {1,2,3,4,9} — o que na NFC-e
#    recorta apenas o 5.
#
# E não aparecia porque o defeito era LATENTE: com o `id_cad_int_tran` vazio
# (o default embarcado) o grupo não sai e o indPres fica em 1. Ele só
# detonaria no dia em que o dono respondesse a pergunta 1 e ligasse o grupo.
# Daí estes testes travarem o VALOR por tipo de operação, e não o caminho.


@pytest.mark.parametrize("indpres", ["0", "2", "3", "9"])
def test_nfce_refuses_an_indpres_outside_1_4_and_5_before_the_http_call(indpres):
    """B25b-20 / Rejeição 717. Recusar aqui é nominal; recusar na SEFAZ é nota morta."""
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    config = {**_focus_settings(), "presenca_comprador_nfce": indpres}
    with override_settings(SHOPMAN_FOCUS_NFE=config), \
            patch("shopman.shop.adapters.fiscal_focusnfe._request") as request:
        result = FocusNFeBackend().emit(
            reference=f"ORD-INDPRES-{indpres}",
            items=[{"sku": "PAO-001", "name": "Pão", "qty": "1", "unit": "un",
                    "unit_price_q": 3000, "total_q": 3000, "fiscal": FISCAL_OWN_PRODUCTION}],
            customer={}, payment={"method": "cash", "amount_q": 3000},
        )

    request.assert_not_called()
    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"
    assert "B25b-20" in result.error_message


def test_indpres_5_is_accepted_by_the_nfce_but_forbids_declaring_an_intermediary():
    """B25b-20 admite o 5 desde a NT 2025.002-RTC v1.51; a B25c-20 o proíbe com intermediador.

    O MOC 7.00 em PDF ainda traz a régua antiga (``<>1 e 4``) — programar por
    ele recusaria uma nota que a SEFAZ aceita.
    """
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    config = {**_focus_settings(), "presenca_comprador_nfce": "5"}
    item = {"sku": "PAO-001", "name": "Pão", "qty": "1", "unit": "un",
            "unit_price_q": 3000, "total_q": 3000, "fiscal": FISCAL_OWN_PRODUCTION}
    pagamento = {"method": "cash", "amount_q": 3000}

    with override_settings(SHOPMAN_FOCUS_NFE=config), \
            patch("shopman.shop.adapters.fiscal_focusnfe._request",
                  return_value={"status": "autorizado", "chave_nfe": "K" * 44}):
        sem_intermediador = FocusNFeBackend().emit(
            reference="ORD-INDPRES-5-OK", items=[item], customer={}, payment=pagamento,
        )

    assert sem_intermediador.success is True

    with override_settings(SHOPMAN_FOCUS_NFE=config), \
            patch("shopman.shop.adapters.fiscal_focusnfe._request") as request:
        com_intermediador = FocusNFeBackend().emit(
            reference="ORD-INDPRES-5-NAO", items=[item], customer={}, payment=pagamento,
            intermediary={"cnpj": IFOOD_CNPJ, "id_cad_int_tran": "MERCHANT-42"},
        )

    request.assert_not_called()
    assert com_intermediador.success is False
    assert "B25c-20" in com_intermediador.error_message


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
@pytest.mark.parametrize(("order_type", "esperado"), [("TAKEOUT", "1"), ("DELIVERY", "4")])
def test_the_marketplace_sale_keeps_the_indpres_of_its_operation_type(order_type, esperado):
    """Retirada é 1 mesmo vindo do app; entrega é 4. O intermediador não muda isso."""
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    order = ingest_ifood(order_type=order_type, delivery_fee=0 if order_type == "TAKEOUT" else 799)
    emission = fiscal.build_emission_payload(order)
    for item in emission["items"]:
        item["fiscal"] = FISCAL_OWN_PRODUCTION

    captured = {}

    def fake_request(method, path, payload_, config):
        captured.update(payload=payload_)
        return {"status": "autorizado", "chave_nfe": "K" * 44}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference=order.ref, items=emission["items"], customer=emission["customer"],
            payment=emission["payment"], delivery=emission["delivery"],
            intermediary=emission["intermediary"],
        )

    assert result.success is True
    assert captured["payload"]["presenca_comprador"] == esperado
    assert captured["payload"]["indicador_intermediario"] == "1"


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_an_ifood_delivery_without_a_tax_id_refuses_legibly_instead_of_emitting_wrong():
    """indPres=4 exige destinatário identificado (E01-20 → Rejeição 787).

    O iFood só repassa o documento quando o cliente pede a nota, então **a
    maioria** dos pedidos de entrega chega sem CPF. Não há saída inventável
    aqui: destinatário fictício é fraude e emitir sem ele é rejeição. A recusa
    tem que ser legível e chegar a gente — é pergunta aberta para o contador,
    registrada no corpo do PR.
    """
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    order = ingest_ifood(order_type="DELIVERY", sem_documento=True)
    emission = fiscal.build_emission_payload(order)
    for item in emission["items"]:
        item["fiscal"] = FISCAL_OWN_PRODUCTION

    assert emission["customer"].get("tax_id") is None

    with patch("shopman.shop.adapters.fiscal_focusnfe._request") as request:
        result = FocusNFeBackend().emit(
            reference=order.ref, items=emission["items"], customer=emission["customer"],
            payment=emission["payment"], delivery=emission["delivery"],
            intermediary=emission["intermediary"],
        )

    request.assert_not_called()
    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"
    assert "CPF/CNPJ solicitado para a nota" in result.error_message


# ── 4. A incoerência do desconto negativo ─────────────────────────────────


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_the_ifood_note_no_longer_derives_a_negative_discount_from_platform_money():
    """Regressão do defeito 4: ``produtos + frete − total`` dava NEGATIVO e era engolido.

    Com a base certa o total da nota bate com os produtos, ``valor_desconto``
    não existe, e nenhum ``valor_total > valor_produtos`` sem frete chega à SEFAZ.
    """
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    order = ingest_ifood(delivered_by="IFOOD", subtotal=3000, delivery_fee=799, additional_fees=150)
    payload = fiscal.build_emission_payload(order)
    for item in payload["items"]:
        item["fiscal"] = FISCAL_OWN_PRODUCTION

    captured = {}

    def fake_request(method, path, payload_, config):
        captured.update(payload=payload_)
        return {"status": "autorizado", "chave_nfe": "K" * 44}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference=order.ref, items=payload["items"], customer=payload["customer"],
            payment=payload["payment"], delivery=payload["delivery"],
            intermediary=payload["intermediary"],
        )

    assert result.success is True
    assert captured["payload"]["valor_produtos"] == "30.00"
    assert captured["payload"]["valor_total"] == "30.00"
    assert "valor_desconto" not in captured["payload"]
    assert captured["payload"]["valor_frete"] == "0.00"


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_when_the_house_delivers_the_freight_reaches_the_note_as_freight_not_as_merchandise():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    order = ingest_ifood(delivered_by="MERCHANT", subtotal=3000, delivery_fee=800, additional_fees=150)
    payload = fiscal.build_emission_payload(order)
    for item in payload["items"]:
        if item["sku"] != "__DELIVERY_FEE__":
            item["fiscal"] = FISCAL_OWN_PRODUCTION

    assert [item["sku"] for item in payload["items"]] == ["PAO-001", "__DELIVERY_FEE__"]

    captured = {}

    def fake_request(method, path, payload_, config):
        captured.update(payload=payload_)
        return {"status": "autorizado", "chave_nfe": "K" * 44}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference=order.ref, items=payload["items"], customer=payload["customer"],
            payment=payload["payment"], delivery=payload["delivery"],
            intermediary=payload["intermediary"],
        )

    assert result.success is True
    assert captured["payload"]["valor_produtos"] == "30.00"
    assert captured["payload"]["valor_frete"] == "8.00"
    assert captured["payload"]["valor_total"] == "38.00"
    assert "valor_desconto" not in captured["payload"]


# ── 5. O portão do pagamento não recusa a nota corrigida ──────────────────


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_the_payment_gate_measures_against_the_note_base_not_the_order_total():
    """A base corrigida é MENOR que ``Order.total_q`` — a régua velha recusaria sempre."""
    order = ingest_ifood(delivered_by="IFOOD", subtotal=3000, delivery_fee=799, additional_fees=150)

    payment = fiscal._fiscal_payment(order, order.data)

    assert payment["amount_q"] == 3000 < order.total_q
    assert fiscal._payment_below_total(payment, order) is False


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_stale_payment_below_the_note_base_still_refuses_on_a_counter_sale():
    """A guarda continua inteira onde ela nasceu."""
    order = counter_order(total_q=3000)
    order.data["payment"]["amount_q"] = 2000

    assert fiscal._payment_below_total(fiscal._fiscal_payment(order, order.data), order) is True


# ── 6. O contrato inteiro, do pedido ao adapter ───────────────────────────


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_the_handler_hands_the_intermediary_to_the_backend():
    from shopman.orderman.models import Directive

    from shopman.shop.handlers.fiscal import NFCeEmitHandler
    from shopman.shop.tests.test_fiscal_contract import AUTHORIZED, ContractOnlyBackend

    order = ingest_ifood()
    directive = Directive.objects.create(
        topic="fiscal.emit_nfce", payload=fiscal.build_emission_payload(order),
    )
    backend = ContractOnlyBackend()

    NFCeEmitHandler(backend).handle(message=directive, ctx={})

    assert backend.received["intermediary"] == {"cnpj": IFOOD_CNPJ, "id_cad_int_tran": "MERCHANT-42"}
    assert AUTHORIZED.access_key
