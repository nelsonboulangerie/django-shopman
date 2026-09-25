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
from shopman.shop.models import Channel, Shop
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


def cupom(sponsor, value_q, *, target="CART", sem_patrocinio=False):
    """Um ``benefits[]`` como o iFood manda: valor, alvo e quem pagou.

    ``sponsor`` é a palavra da tabela "Sponsorship" deles (``MERCHANT``,
    ``IFOOD``, ``EXTERNAL``, ``CHAIN``); ``sem_patrocinio`` monta o cupom
    **sem** ``sponsorshipValues``, que é o caso em que não dá para saber de
    quem saiu o dinheiro.
    """
    benefit = {"value": value_q / 100, "target": target}
    if not sem_patrocinio:
        benefit["sponsorshipValues"] = [
            {"name": sponsor, "value": value_q / 100, "description": f"Incentivo {sponsor}"},
        ]
    return benefit


def ingest_ifood(*, delivered_by="IFOOD", order_type="DELIVERY", subtotal=3000,
                 delivery_fee=799, additional_fees=150, benefits=(), sem_documento=False,
                 suffix=""):
    """Pedido iFood real: um item de R$ 30,00 mais o que a plataforma cobrou.

    ``sem_documento`` é o caso COMUM na vida real, não a exceção: o iFood só
    repassa ``customer.documentNumber`` quando o cliente pede a nota.

    ``benefits`` é a lista de cupons (use :func:`cupom`), como o iFood manda:
    o total deles vira ``total.benefits`` e a lista vira ``benefits[]``, que é
    onde mora o patrocinador.
    """
    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    benefits = list(benefits)
    benefits_q = sum(int(round(b["value"] * 100)) for b in benefits)
    order_amount = subtotal + delivery_fee + additional_fees - benefits_q
    documento = {} if sem_documento else {"documentNumber": "52998224725", "documentType": "CPF"}
    payload = ifood_orders.map_order({
        "id": f"ifood-{delivered_by}-{order_type}-{additional_fees}-{int(sem_documento)}{suffix}",
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
        "benefits": benefits,
        "total": {
            "subTotal": subtotal / 100, "deliveryFee": delivery_fee / 100,
            "additionalFees": additional_fees / 100, "benefits": benefits_q / 100,
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
def test_an_ifood_order_without_the_financial_breakdown_is_left_alone_AND_stays_silent():
    """Simulação/payload antigo não manda ``totals`` — e aqui o silêncio é MERECIDO.

    Sem ``totals``, o ``ifood_ingest`` monta ``total_q`` da soma dos itens
    (``total_q = order_amount_q or items_subtotal_q``). Não há receita de
    plataforma dentro dele, então a base já está certa e não há o que gritar.
    """
    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest({
            "order_code": "sem-totais",
            "items": [{"sku": "PAO-001", "qty": 1, "unit_price_q": 1000}],
        })

    assert fiscal_intermediary.seller_amounts(order) is None
    assert fiscal_intermediary.unreadable_breakdown(order) == ""
    assert fiscal.note_base_q(order) == order.total_q == 1000


# ── 1a. O cupom cai de um lado ou do outro, conforme quem o patrocinou ────
#
# Decisão do dono: cupom da LOJA é desconto e derruba a base; cupom do iFood
# compõe a base, porque a plataforma repassa aquele valor e a loja recebe
# cheio. Quem define as palavras é a tabela "Sponsorship" do portal do iFood,
# que para cada patrocinador prescreve "trate como desconto" (só MERCHANT) ou
# "trate como pagamento" (IFOOD, EXTERNAL, CHAIN).
#
# Metade desta seção é o lado que NÃO muda: cupom da loja continua reduzindo a
# base exatamente como antes.


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_coupon_the_house_paid_for_is_a_discount_and_lowers_the_base():
    order = ingest_ifood(delivered_by="IFOOD", subtotal=3000, delivery_fee=799,
                         additional_fees=150, benefits=[cupom("MERCHANT", 500)])

    # O cliente pagou 34,49 ao iFood; a loja abriu mão de 5,00 do próprio bolso.
    assert order.total_q == 3449
    assert fiscal_intermediary.seller_amounts(order) == {"base_q": 2500, "freight_q": 0}
    assert fiscal_intermediary.unattributable_benefits(order) == ""


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_coupon_the_platform_paid_for_composes_the_base_instead_of_lowering_it():
    """O iFood repassa o valor: a loja recebe cheio, e a nota declara cheio."""
    order = ingest_ifood(delivered_by="IFOOD", subtotal=3000, delivery_fee=799,
                         additional_fees=150, benefits=[cupom("IFOOD", 500)])

    # Mesmo total de pedido do teste anterior, base DIFERENTE — é exatamente
    # esta diferença que o patrocinador decide.
    assert order.total_q == 3449
    assert fiscal_intermediary.seller_amounts(order) == {"base_q": 3000, "freight_q": 0}
    assert fiscal_intermediary.unattributable_benefits(order) == ""


@pytest.mark.parametrize("sponsor", ["EXTERNAL", "CHAIN"])
@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_the_other_two_sponsors_the_ifood_documents_are_repasse_too(sponsor):
    """``EXTERNAL`` (parceiro) e ``CHAIN`` (rede) também são "trate como pagamento"."""
    order = ingest_ifood(benefits=[cupom(sponsor, 500)], suffix=sponsor)

    assert fiscal_intermediary.seller_amounts(order)["base_q"] == 3000


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_coupon_split_between_the_house_and_the_platform_splits_the_base_too():
    """``sponsorshipValues`` é LISTA: a divisão é por parcela, não pelo cupom."""
    order = ingest_ifood(benefits=[{
        "value": 5.00, "target": "CART",
        "sponsorshipValues": [
            {"name": "MERCHANT", "value": 2.00, "description": "Incentivo da Loja"},
            {"name": "IFOOD", "value": 3.00, "description": "Incentivo do iFood"},
        ],
    }])

    # Só os 2,00 da loja saem da base; os 3,00 do iFood são repasse.
    assert fiscal_intermediary.seller_amounts(order)["base_q"] == 2800
    assert fiscal_intermediary.house_discounts(order) == {
        "goods_q": 200, "freight_q": 0, "unreadable": "",
    }


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_delivery_coupon_only_lands_where_the_freight_actually_is():
    """Cupom de frete não abate de uma base que não tem frete dentro.

    A loja patrocinou o frete grátis, mas quem entregou foi o iFood: o frete
    nem está na base, e descontar dele tiraria duas vezes.
    """
    ifood_entregou = ingest_ifood(
        delivered_by="IFOOD", subtotal=3000, delivery_fee=800, additional_fees=150,
        benefits=[cupom("MERCHANT", 800, target="DELIVERY_FEE")],
    )
    casa_entregou = ingest_ifood(
        delivered_by="MERCHANT", subtotal=3000, delivery_fee=800, additional_fees=150,
        benefits=[cupom("MERCHANT", 800, target="DELIVERY_FEE")],
    )

    # Entrega da plataforma: a mercadoria segue cheia, o frete não entra.
    assert fiscal_intermediary.seller_amounts(ifood_entregou) == {"base_q": 3000, "freight_q": 0}
    # Entrega da casa: o frete entra na nota (8,00) e o cupom da loja o zera.
    assert fiscal_intermediary.seller_amounts(casa_entregou) == {"base_q": 3000, "freight_q": 800}


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_delivery_coupon_the_platform_paid_keeps_the_freight_the_house_earned():
    """Frete grátis bancado pelo iFood, entrega da casa: a casa recebe o frete."""
    order = ingest_ifood(delivered_by="MERCHANT", subtotal=3000, delivery_fee=800,
                         additional_fees=150,
                         benefits=[cupom("IFOOD", 800, target="DELIVERY_FEE")])

    assert fiscal_intermediary.seller_amounts(order) == {"base_q": 3800, "freight_q": 800}


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_coupon_with_no_sponsor_at_all_declares_MORE_and_screams():
    """Não saber quem pagou não vira desconto — vira nota cheia e alerta crítico.

    Desconto que não houve é subdeclaração, que é infração. Declarar a mais é
    caro e não é crime. O erro escolhe esse lado, e não escolhe calado.
    """
    order = ingest_ifood(benefits=[cupom("MERCHANT", 500, sem_patrocinio=True)])

    assert fiscal_intermediary.seller_amounts(order)["base_q"] == 3000
    assert "sem patrocinador declarado" in fiscal_intermediary.unattributable_benefits(order)

    with patch("shopman.shop.services.observability.create_operator_alert") as alert:
        fiscal.build_emission_payload(order)

    tipos = [call.kwargs["type"] for call in alert.call_args_list]
    assert "fiscal_intermediary_benefit_unattributed" in tipos


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_an_unknown_sponsor_name_is_not_quietly_read_as_one_of_the_four():
    """Palavra nova do iFood não pode cair no balde errado em silêncio."""
    order = ingest_ifood(benefits=[cupom("FRANCHISE", 500)])

    assert fiscal_intermediary.seller_amounts(order)["base_q"] == 3000
    assert "patrocinador desconhecido (FRANCHISE)" in (
        fiscal_intermediary.unattributable_benefits(order)
    )


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_an_unknown_coupon_target_is_not_guessed_between_goods_and_freight():
    """Alvo novo: os dois destinos caem em lugares diferentes da nota."""
    order = ingest_ifood(benefits=[cupom("MERCHANT", 500, target="TIP")])

    assert fiscal_intermediary.seller_amounts(order)["base_q"] == 3000
    assert "alvo de cupom desconhecido (TIP)" in (
        fiscal_intermediary.unattributable_benefits(order)
    )


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_a_coupon_total_that_does_not_close_with_the_detail_screams():
    """``total.benefits`` de 5,00 com 2,00 detalhados: falta cupom, e isso se diz."""
    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    payload = ifood_orders.map_order({
        "id": "ifood-cupom-que-nao-fecha",
        "orderType": "TAKEOUT", "merchant": {"id": "merchant"},
        "customer": {"name": "Cliente iFood"},
        "items": [{"id": "i1", "externalCode": "PAO-001", "name": "Pão",
                   "quantity": 1, "unitPrice": 30.0, "totalPrice": 30.0}],
        "benefits": [cupom("MERCHANT", 200)],
        "total": {"subTotal": 30.0, "deliveryFee": 0.0, "additionalFees": 0.0,
                  "benefits": 5.00, "orderAmount": 25.00},
    })
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest(payload)

    assert "não fecha com o cupom do total" in (
        fiscal_intermediary.unattributable_benefits(order)
    )


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_an_order_with_no_coupon_at_all_says_nothing():
    """O silêncio do caso comum: sem cupom não há atribuição a fazer."""
    order = ingest_ifood(benefits=[])

    assert fiscal_intermediary.house_discounts(order) == {
        "goods_q": 0, "freight_q": 0, "unreadable": "",
    }
    assert fiscal_intermediary.unattributable_benefits(order) == ""


def test_a_counter_order_with_no_ifood_data_never_enters_the_coupon_split():
    """O controle: o pedido do canal próprio não tem cupom de plataforma."""
    order = counter_order()

    assert fiscal_intermediary.unattributable_benefits(order) == ""
    assert fiscal_intermediary.seller_amounts(order) is None


# ── 1b. As duas omissões da mesma família falham do MESMO jeito ───────────
#
# Correção de desenho apontada em revisão: faltar a CONFIGURAÇÃO do grupo
# gritava, mas faltar o DETALHAMENTO financeiro saía calado pelo total cheio —
# com a receita da plataforma dentro da base, que é o defeito que esta PR
# existe para consertar. O `None` de `seller_amounts` cobria duas coisas
# opostas: "não há o que corrigir" e "deveria haver e eu não sei ler".
#
# A segunda é o que acontece no dia em que alguém declarar um segundo
# marketplace: o defeito volta inteiro, para o canal novo, em silêncio.


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES={
    "rappi": {"cnpj": "33014556000196", "id_cad_int_tran": "LOJA-9"},
})
def test_an_intermediated_channel_we_cannot_read_screams_instead_of_billing_the_full_total():
    """O caso do SEGUNDO marketplace: declarado intermediado, sem leitor."""
    Channel.objects.get_or_create(ref="rappi", defaults={"name": "Rappi"})
    order = Order.objects.create(
        ref="ORD-RAPPI-1", channel_ref="rappi", status=Order.Status.COMPLETED,
        total_q=3949, data={"payment": {"method": "external", "amount_q": 3949}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO-001", name="Pão",
                             qty=1, unit_price_q=3000, line_total_q=3000)

    assert fiscal_intermediary.is_intermediated(order) is True
    assert fiscal_intermediary.seller_amounts(order) is None
    assert "rappi" in fiscal_intermediary.unreadable_breakdown(order)

    with patch("shopman.shop.services.observability.create_operator_alert") as alert:
        fiscal.build_emission_payload(order)

    tipos = [c.kwargs["type"] for c in alert.call_args_list]
    assert "fiscal_intermediary_base_unknown" in tipos
    corpo = next(c.kwargs["message"] for c in alert.call_args_list
                 if c.kwargs["type"] == "fiscal_intermediary_base_unknown")
    assert "total CHEIO" in corpo
    assert "rappi" in corpo


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_the_readable_channel_and_the_direct_sale_never_raise_the_base_alarm():
    """As duas metades que precisam continuar caladas."""
    ifood = ingest_ifood()
    balcao = counter_order()

    assert fiscal_intermediary.unreadable_breakdown(ifood) == ""
    assert fiscal_intermediary.unreadable_breakdown(balcao) == ""

    for order in (ifood, balcao):
        with patch("shopman.shop.services.observability.create_operator_alert") as alert:
            fiscal.build_emission_payload(order)
        tipos = [c.kwargs["type"] for c in alert.call_args_list]
        assert "fiscal_intermediary_base_unknown" not in tipos


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_house_delivered_asks_the_generic_question_the_platform_answers_in_its_own_word():
    assert fiscal_intermediary.house_delivered(ingest_ifood(delivered_by="MERCHANT")) is True
    assert fiscal_intermediary.house_delivered(ingest_ifood(delivered_by="IFOOD")) is False
    # Venda direta é SEMPRE transporte da casa: não há plataforma para entregar.
    # Antes isto devolvia False, porque a função lia a chave do iFood num pedido
    # que não tem chave do iFood — ausência lida como negativa. Não incomodava
    # enquanto o único leitor era a base (que já filtra por venda intermediada);
    # passou a incomodar quando o grupo do transportador virou leitor, porque aí
    # a resposta errada tiraria a padaria de transportadora da entrega DELA.
    assert fiscal_intermediary.house_delivered(counter_order()) is True


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_a_delivery_by_the_platform_does_not_name_the_bakery_as_the_carrier():
    """Quem entregou foi o iFood: a padaria não se declara transportadora.

    ``modFrete=2`` ("Contratação do Frete por conta de Terceiros"), porque o
    transporte HOUVE — ``9`` diria que não houve — e quem o contratou não foi
    nem o remetente nem o destinatário. O subgrupo X03 ``transporta`` fica
    fora: nomear a padaria ali declararia um transporte que ela não prestou.
    """
    order = ingest_ifood(delivered_by="IFOOD", subtotal=3000, delivery_fee=800,
                         additional_fees=150)
    _result, sent = _emit_captured(_classify(fiscal.build_emission_payload(order)))

    assert sent["presenca_comprador"] == "4"
    assert sent["modalidade_frete"] == "2"
    assert "cnpj_transportador" not in sent
    assert "nome_transportador" not in sent
    # O terceiro que transportou tem nome e CNPJ, e sai na MESMA nota — no
    # grupo do intermediador, que é onde ele cabe.
    assert sent["cnpj_intermediario"] == IFOOD_CNPJ
    # A taxa do iFood segue fora da nota: quem a recebeu não foi a casa.
    assert "valor_frete" not in sent or sent["valor_frete"] == "0.00"


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_a_delivery_by_the_house_still_declares_the_bakery_as_the_carrier():
    """O outro lado: entrega da casa não muda em nada.

    ``modFrete=3`` ("Transporte Próprio por conta do Remetente") e o
    transportador é o emitente — que é o que a regra X04-30 espera de um
    ``modFrete=3`` (CNPJ do transportador igual ao do remetente).
    """
    Shop.objects.create(name="Nelson Boulangerie")
    order = ingest_ifood(delivered_by="MERCHANT", subtotal=3000, delivery_fee=800,
                         additional_fees=150)
    _result, sent = _emit_captured(_classify(fiscal.build_emission_payload(order)))

    assert sent["modalidade_frete"] == "3"
    assert sent["cnpj_transportador"]
    assert sent["nome_transportador"] == "Nelson Boulangerie"
    assert sent["valor_frete"] == "8.00"


@override_settings(SHOPMAN_FOCUS_NFE=_focus_settings())
def test_a_counter_delivery_keeps_the_bakery_as_the_carrier():
    """O controle: a entrega do canal PRÓPRIO nunca passou por plataforma nenhuma.

    Sem ``by_house`` no ``delivery``, o adapter assume a casa — entrega própria
    é a regra, e é o comportamento que já existia.
    """
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    Shop.objects.create(name="Nelson Boulangerie")
    captured = {}

    def fake_request(method, path, payload_, config):
        captured.update(payload=payload_)
        return {"status": "autorizado", "chave_nfe": "K" * 44}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference="ORD-PDV-DELIVERY-1",
            items=[{"sku": "PAO-001", "name": "Pão", "qty": "1", "unit": "un",
                    "unit_price_q": 3000, "total_q": 3000, "fiscal": FISCAL_OWN_PRODUCTION}],
            customer={"tax_id": "52998224725", "name": "Cliente"},
            payment={"method": "cash", "amount_q": 3000},
            delivery={"address": {
                "route": "Rua X", "street_number": "123", "neighborhood": "Centro",
                "city": "Londrina", "state_code": "PR", "postal_code": "86010000",
            }},
        )

    assert result.success is True
    assert captured["payload"]["modalidade_frete"] == "3"
    assert captured["payload"]["nome_transportador"] == "Nelson Boulangerie"


def test_the_seam_for_a_second_marketplace_is_named_in_one_place():
    """Onde um segundo marketplace entra não pode ser descoberto por arqueologia."""
    assert fiscal_intermediary.READABLE_BREAKDOWN_CHANNELS == frozenset({"ifood"})


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
    """Nota válida e fora do Ajuste SINIEF 22/20 é o pior defeito: nada reclama.

    Sem env var E sem loja cadastrada não sobra de onde tirar o identificador —
    o grupo não sai, e a ausência grita. É o único caminho que continua levando
    ao silêncio recusado.
    """
    order = ingest_ifood()

    with patch("shopman.shop.services.observability.create_operator_alert") as alert:
        payload = fiscal.build_emission_payload(order)

    assert "intermediary" not in payload
    alert.assert_called_once()
    assert alert.call_args.kwargs["type"] == "fiscal_intermediary_not_declared"
    assert "idCadIntTran" in alert.call_args.kwargs["message"]


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES_SEM_ID)
def test_the_store_name_fills_the_idCadIntTran_when_the_deployment_did_not():
    """O identificador do YB03 é o NOME DA LOJA, e ele já está no sistema.

    A NT 2020.006 define o campo como "nome do usuário ou identificação do
    perfil do vendedor no site do intermediador", de 2 a 60 caracteres, e a
    SEFAZ não valida o conteúdo. O nome fantasia da loja é exatamente isso, é o
    mesmo com que ela aparece no iFood, e cada deployment já tem o seu — ou
    seja, o valor certo chega sem ninguém precisar lembrar.
    """
    Shop.objects.create(name="Nelson Boulangerie")
    order = ingest_ifood()

    with patch("shopman.shop.services.observability.create_operator_alert") as alert:
        payload = fiscal.build_emission_payload(order)

    assert payload["intermediary"] == {
        "cnpj": IFOOD_CNPJ, "id_cad_int_tran": "Nelson Boulangerie",
    }
    assert fiscal_intermediary.missing_configuration(order) == ""
    alert.assert_not_called()


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES)
def test_the_deployment_env_var_still_wins_over_the_store_name():
    """A loja cujo perfil na plataforma tem outro nome continua podendo fixá-lo."""
    Shop.objects.create(name="Nelson Boulangerie")
    order = ingest_ifood()

    assert fiscal_intermediary.intermediary_for(order)["id_cad_int_tran"] == "MERCHANT-42"


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES_SEM_ID)
def test_a_store_name_longer_than_the_field_is_cut_at_sixty_characters():
    """String[2-60] no YB03: nome maior é cortado, não recusado."""
    Shop.objects.create(name="B" * 80)
    order = ingest_ifood()

    assert fiscal_intermediary.intermediary_for(order)["id_cad_int_tran"] == "B" * 60


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


def _emit_captured(emission):
    """Emite pelo adapter Focus com o HTTP trocado por captura. Devolve (result, payload|None)."""
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload_, config):
        captured.update(payload=payload_)
        return {"status": "autorizado", "chave_nfe": "K" * 44}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request) as request:
        result = FocusNFeBackend().emit(
            reference=emission["order_ref"], items=emission["items"], customer=emission["customer"],
            payment=emission["payment"], delivery=emission["delivery"],
            intermediary=emission.get("intermediary"),
        )
    if not result.success:
        request.assert_not_called()
    return result, captured.get("payload")


def _classify(emission):
    for item in emission["items"]:
        if not str(item["sku"]).startswith("__"):
            item["fiscal"] = FISCAL_OWN_PRODUCTION
    return emission


def _cents(value) -> int:
    from shopman.shop.adapters.fiscal_focusnfe import _money_to_q

    return _money_to_q(value or "0")


_DELIVERY_ONLY_FIELDS = (
    "cpf_destinatario", "cnpj_destinatario", "nome_destinatario",
    "logradouro_destinatario", "numero_destinatario", "bairro_destinatario",
    "municipio_destinatario", "uf_destinatario", "cep_destinatario",
    "cnpj_transportador", "nome_transportador", "valor_frete",
)


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_an_ifood_delivery_by_ifood_without_a_tax_id_is_a_presential_note_without_the_fee():
    """Decisão do dono (24/09/2026): sem CPF, a entrega intermediada sai PRESENCIAL.

    Consumidor não identificado, sem endereço, sem frete (``modalidade_frete``
    9), sem transportador. Entregou o iFood: a taxa não é da casa e fica fora
    — o total da nota é só a mercadoria, e o pagamento declara o mesmo valor.
    Praxe do mercado; a confirmação do contador é pendência registrada no PR.
    """
    order = ingest_ifood(delivered_by="IFOOD", subtotal=3000, delivery_fee=799,
                         additional_fees=150, sem_documento=True)
    emission = _classify(fiscal.build_emission_payload(order))

    assert emission["delivery"] is None
    assert emission["customer"].get("tax_id") is None
    assert [item["sku"] for item in emission["items"]] == ["PAO-001"]

    result, sent = _emit_captured(emission)

    assert result.success is True
    assert sent["presenca_comprador"] == "1"
    assert sent["modalidade_frete"] == "9"
    for field in _DELIVERY_ONLY_FIELDS:
        assert field not in sent, field
    assert "valor_outras_despesas" not in sent
    assert sent["valor_produtos"] == "30.00"
    assert sent["valor_total"] == "30.00"
    assert "valor_desconto" not in sent
    assert [f["valor_pagamento"] for f in sent["formas_pagamento"]] == ["30.00"]
    # O intermediador continua declarado: a regra B25c-20 aceita indPres=1.
    assert sent["indicador_intermediario"] == "1"


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_an_ifood_delivery_by_the_house_without_a_tax_id_carries_the_fee_as_other_expenses():
    """Entregou a CASA: a taxa é receita dela e entra em outras despesas (vOutro).

    Produtos + outras despesas = total = pagamento. A nota presencial não pode
    mentir no valor: o cliente pagou 38,00 à casa (30,00 de pão + 8,00 de
    entrega), e a receita do iFood (1,50) segue fora.
    """
    order = ingest_ifood(delivered_by="MERCHANT", subtotal=3000, delivery_fee=800,
                         additional_fees=150, sem_documento=True)
    emission = _classify(fiscal.build_emission_payload(order))

    assert emission["delivery"] is None
    assert [item["sku"] for item in emission["items"]] == ["PAO-001", "__OTHER_EXPENSE__"]

    result, sent = _emit_captured(emission)

    assert result.success is True
    assert sent["presenca_comprador"] == "1"
    assert sent["modalidade_frete"] == "9"
    for field in _DELIVERY_ONLY_FIELDS:
        assert field not in sent, field
    assert sent["valor_produtos"] == "30.00"
    assert sent["valor_outras_despesas"] == "8.00"
    assert sent["valor_total"] == "38.00"
    assert "valor_desconto" not in sent
    assert [f["valor_pagamento"] for f in sent["formas_pagamento"]] == ["38.00"]
    # W15-10: o vOutro do total é a soma dos itens; a taxa nunca vira produto.
    assert [item["codigo_produto"] for item in sent["items"]] == ["PAO-001"]
    assert sum(_cents(item.get("valor_outras_despesas")) for item in sent["items"]) == 800


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_other_expenses_and_a_discount_close_to_the_cent():
    """Com cupom (benefits), taxa ímpar e receita do iFood, tudo fecha no centavo."""
    order = ingest_ifood(delivered_by="MERCHANT", subtotal=3000, delivery_fee=701,
                         additional_fees=99, benefits=[cupom("MERCHANT", 500)],
                         sem_documento=True)
    emission = _classify(fiscal.build_emission_payload(order))

    result, sent = _emit_captured(emission)

    assert result.success is True
    # base = 3000 + 701 + 99 − 500 − 99 = 3201: produtos 30,00 + outras 7,01 − desconto 5,00.
    assert sent["valor_total"] == "32.01"
    assert sent["valor_outras_despesas"] == "7.01"
    assert sent["valor_desconto"] == "5.00"
    assert [f["valor_pagamento"] for f in sent["formas_pagamento"]] == ["32.01"]
    produtos = sum(_cents(i["valor_bruto"]) for i in sent["items"])
    outras = sum(_cents(i.get("valor_outras_despesas")) for i in sent["items"])
    desconto = sum(_cents(i.get("valor_desconto")) for i in sent["items"])
    assert produtos + outras - desconto == 3201


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_an_ifood_delivery_with_a_tax_id_keeps_the_full_home_delivery_note():
    """Com CPF, segue a nota de entrega completa: indPres=4, destinatário, endereço, transportador."""
    order = ingest_ifood(delivered_by="MERCHANT", subtotal=3000, delivery_fee=800, additional_fees=150)
    emission = _classify(fiscal.build_emission_payload(order))

    assert emission["delivery"] is not None
    assert [item["sku"] for item in emission["items"]] == ["PAO-001", "__DELIVERY_FEE__"]

    result, sent = _emit_captured(emission)

    assert result.success is True
    assert sent["presenca_comprador"] == "4"
    assert sent["cpf_destinatario"] == "52998224725"
    assert sent["logradouro_destinatario"] == "Rua X"
    assert sent["cnpj_transportador"]
    assert sent["valor_frete"] == "8.00"
    assert "valor_outras_despesas" not in sent
    assert sent["valor_total"] == "38.00"


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_an_invalid_document_from_the_platform_is_not_treated_as_no_document():
    """Documento informado e inválido é pedido de nota com dado errado: recusa ruidosa."""
    order = ingest_ifood(order_type="DELIVERY")
    order.data["fiscal"] = {"tax_id": "11111111112"}
    emission = _classify(fiscal.build_emission_payload(order))

    assert emission["delivery"] is not None

    result, sent = _emit_captured(emission)

    assert sent is None
    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"


@override_settings(SHOPMAN_FISCAL_INTERMEDIARIES=INTERMEDIARIES, SHOPMAN_FOCUS_NFE=_focus_settings())
def test_an_own_channel_delivery_without_a_tax_id_still_refuses_and_screams():
    """A regra presencial é SÓ do canal intermediado.

    Nos canais próprios o dono decidiu o contrário (CPF exigido na entrada do
    pedido de entrega). Se uma entrega sem CPF chegar à emissão mesmo assim,
    ela continua recusada antes do HTTP, com a razão legível.
    """
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja"})
    order = Order.objects.create(
        ref="ORD-WEB-DELIVERY-SEM-CPF", channel_ref="web",
        status=Order.Status.COMPLETED, total_q=3800,
        data={
            "fulfillment_type": "delivery",
            "payment": {"method": "pix", "amount_q": 3800},
            "delivery_address_structured": {
                "route": "Rua X", "street_number": "123", "neighborhood": "Centro",
                "city": "Londrina", "state_code": "PR", "postal_code": "86010000",
            },
        },
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO-001", name="Pão",
                             qty=1, unit_price_q=3000, line_total_q=3000)
    OrderItem.objects.create(order=order, line_id="2", sku="__DELIVERY_FEE__", name="Taxa de entrega",
                             qty=1, unit_price_q=800, line_total_q=800)

    assert fiscal_intermediary.issues_as_presential(order, requested_tax_id="") is False
    emission = _classify(fiscal.build_emission_payload(order))
    assert emission["delivery"] is not None

    result, sent = _emit_captured(emission)

    assert sent is None
    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"
    assert "CPF/CNPJ solicitado para a nota" in result.error_message


def test_the_adapter_refuses_other_expenses_on_a_home_delivery_note():
    """vOutro é a taxa da nota presencial; junto com entrega, contaria duas vezes."""
    with override_settings(SHOPMAN_FOCUS_NFE=_focus_settings()):
        result, sent = _emit_captured({
            "order_ref": "ORD-DOUBLE-FEE",
            "items": [
                {"sku": "PAO-001", "name": "Pão", "qty": "1", "unit_price_q": 3000, "total_q": 3000,
                 "fiscal": FISCAL_OWN_PRODUCTION},
                {"sku": "__OTHER_EXPENSE__", "name": "Taxa de entrega", "qty": "1",
                 "unit_price_q": 800, "total_q": 800, "meta": {"type": "other_expense"}, "fiscal": {}},
            ],
            "customer": {"tax_id": "52998224725"},
            "payment": {"method": "pix", "amount_q": 3800},
            "delivery": {"address": {"route": "Rua X", "street_number": "1", "neighborhood": "C",
                                     "city": "Londrina", "state_code": "PR", "postal_code": "86010000"}},
        })

    assert sent is None
    assert result.success is False
    assert "outras despesas" in result.error_message


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
