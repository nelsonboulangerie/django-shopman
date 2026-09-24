"""Builder do payload fiscal: catálogo ilegível ≠ produto sem NCM.

Regressão do audit do Fiscalman (F2): ``_products_by_sku`` capturava
``except Exception`` e devolvia ``{}``. Um soluço de banco fazia todos os itens
perderem o metadado fiscal, o adapter recusava por "produto sem NCM" e o handler
classificava a recusa como TERMINAL — nota morta na fila, sem retry, com um
diagnóstico que mentia sobre a causa.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db.utils import OperationalError
from django.test import override_settings
from shopman.fiscalman.contracts import FiscalDocumentResult
from shopman.offerman.models import Product
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.fiscal import NFCeEmitHandler
from shopman.shop.models import Channel
from shopman.shop.services import fiscal as fiscal_service

pytestmark = pytest.mark.django_db

EMIT_ALWAYS = override_settings(
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.tests.test_fiscal_items_builder.StubFiscalBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER="shopman.shop.fiscal_resolvers.always",
)


class StubFiscalBackend:
    """Backend fiscal só para o pool não estar vazio (``fiscal.emit`` é no-op sem backend)."""

    def emit(self, **kwargs):
        return FiscalDocumentResult(success=True, access_key="x", status="authorized")

    def query_status(self, *, reference):
        return FiscalDocumentResult(success=False)

    def cancel(self, *, reference, reason):
        raise NotImplementedError


@pytest.fixture
def order_with_item(db):
    from shopman.shop.fiscal import fiscal_pool

    fiscal_pool.reset()
    Channel.objects.create(ref="pdv", name="PDV")
    Product.objects.create(
        sku="PAO-1",
        name="Pão",
        metadata={"fiscal": {"profile": "standard", "ncm": "19059010"}},
    )
    order = Order.objects.create(
        ref="ORD-FISCAL-BUILD-1", channel_ref="pdv", status=Order.Status.COMPLETED, total_q=1000
    )
    order.items.create(sku="PAO-1", name="Pão", qty=1, unit_price_q=1000, line_total_q=1000)
    yield order
    fiscal_pool.reset()


@EMIT_ALWAYS
def test_unreadable_catalog_raises_instead_of_queueing_a_note_without_ncm(order_with_item):
    with patch.object(
        Product.objects.__class__, "filter", side_effect=OperationalError("conexão caiu")
    ):
        with pytest.raises(OperationalError):
            fiscal_service.emit(order_with_item)

    # E, principalmente: nenhuma directive nasceu com um retrato falso do catálogo.
    assert not Directive.objects.filter(topic="fiscal.emit_nfce").exists()


@EMIT_ALWAYS
def test_readable_catalog_queues_items_with_their_fiscal_codes(order_with_item):
    fiscal_service.emit(order_with_item)

    directive = Directive.objects.get(topic="fiscal.emit_nfce")
    item = directive.payload["items"][0]
    assert item["fiscal"]["ncm"] == "19059010"
    assert item["fiscal"]["cfop"] == "5102"


@EMIT_ALWAYS
def test_product_without_ncm_is_terminal_in_the_handler_and_that_is_the_truth(order_with_item):
    Product.objects.filter(sku="PAO-1").update(metadata={})
    fiscal_service.emit(order_with_item)
    directive = Directive.objects.get(topic="fiscal.emit_nfce")

    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    backend = FocusNFeBackend()
    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(backend).handle(message=directive, ctx={})


# ── invariante de canal: quem escreve `payment` escreve o valor final ────────
#
# Audit do Fiscalman (F7): o adapter deriva `valor_desconto = produtos + frete −
# pagamento`. Um `payment` defasado não vira erro — vira um desconto que não
# houve dentro de um XML válido, subdeclarando a venda.


@EMIT_ALWAYS
def test_stale_payment_below_total_does_not_become_a_phantom_discount(order_with_item):
    from shopman.backstage.models import OperatorAlert

    order_with_item.data = {"payment": {"method": "cash", "amount_q": 700}}
    order_with_item.save(update_fields=["data"])

    fiscal_service.emit(order_with_item)

    assert not Directive.objects.filter(topic="fiscal.emit_nfce").exists()
    alert = OperatorAlert.objects.filter(type="fiscal_payment_mismatch").first()
    assert alert is not None
    assert order_with_item.ref in alert.message


@EMIT_ALWAYS
def test_mixed_payment_is_measured_by_the_sum_of_its_tenders(order_with_item):
    order_with_item.data = {
        "payment": {
            "method": "mixed",
            "amount_q": 1000,
            "tenders": [
                {"method": "cash", "amount_q": 400},
                {"method": "pix", "amount_q": 600},
            ],
        }
    }
    order_with_item.save(update_fields=["data"])

    fiscal_service.emit(order_with_item)

    assert Directive.objects.filter(topic="fiscal.emit_nfce").exists()


@EMIT_ALWAYS
def test_payment_matching_the_total_emits_normally(order_with_item):
    order_with_item.data = {"payment": {"method": "cash", "amount_q": 1000}}
    order_with_item.save(update_fields=["data"])

    fiscal_service.emit(order_with_item)

    directive = Directive.objects.get(topic="fiscal.emit_nfce")
    assert directive.payload["payment"]["amount_q"] == 1000


# ── GTIN da NFC-e: só de fonte que decide ────────────────────────────────────
#
# A SEFAZ confere cEAN/cEANTrib contra o Cadastro Centralizado de GTIN: GTIN
# errado é nota rejeitada. Vai para a nota o GTIN com dígito válido e origem
# confiável (NF-e de compra ou embalagem); palpite da web sai "SEM GTIN".

VALID_GTIN = "3006670000187"


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({"social": {"gtin": VALID_GTIN}}, VALID_GTIN),
        ({"social": {"gtin": VALID_GTIN}, "gtin_source": "embalagem, dono, 24/09"}, VALID_GTIN),
        ({}, ""),
        ({"social": {"gtin": VALID_GTIN}, "gtin_source": "web, a confirmar na embalagem"}, ""),
        ({"social": {"gtin": VALID_GTIN[:-1] + "0"}}, ""),
    ],
    ids=["nfe-de-compra", "embalagem", "produto-da-casa", "web-a-confirmar", "digito-invalido"],
)
def test_fiscal_item_carries_only_a_trusted_gtin(order_with_item, extra, expected):
    Product.objects.filter(sku="PAO-1").update(
        metadata={"fiscal": {"profile": "standard", "ncm": "19059010"}, **extra}
    )

    items = fiscal_service._build_fiscal_items(order_with_item)

    assert items[0]["gtin"] == expected


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({"social": {"gtin": VALID_GTIN}}, VALID_GTIN),
        ({}, "SEM GTIN"),
        ({"social": {"gtin": VALID_GTIN}, "gtin_source": "web, a confirmar na embalagem"}, "SEM GTIN"),
        ({"social": {"gtin": VALID_GTIN[:-1] + "0"}}, "SEM GTIN"),
    ],
    ids=["gtin-confiavel", "sem-gtin", "web-a-confirmar", "digito-invalido"],
)
def test_nfce_item_barcode_fields_follow_the_trust_rule(order_with_item, extra, expected):
    """Ponta a ponta: catálogo → payload fiscal → item da Focus (cEAN e cEANTrib)."""
    from shopman.shop.adapters.fiscal_focusnfe import _map_item

    Product.objects.filter(sku="PAO-1").update(
        metadata={"fiscal": {"profile": "standard", "ncm": "19059010"}, **extra}
    )

    item = fiscal_service._build_fiscal_items(order_with_item)[0]
    mapped = _map_item(1, item, {})

    assert mapped["codigo_barras_comercial"] == expected
    assert mapped["codigo_barras_tributavel"] == expected


# ── kit sai aberto na nota (decisão do dono, 24/09/2026) ────────────────────
#
# Linha cujo produto tem componentes vira uma linha fiscal POR componente, com
# a tributação do componente e o preço da linha rateado pelo que cada um vale
# avulso. A soma fecha centavo a centavo.


def _kit_order(ref: str, *lines) -> Order:
    Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV"})
    order = Order.objects.create(ref=ref, channel_ref="pdv", status=Order.Status.COMPLETED, total_q=0)
    for sku, name, qty, unit_price_q, line_total_q in lines:
        order.items.create(sku=sku, name=name, qty=qty, unit_price_q=unit_price_q, line_total_q=line_total_q)
    return order


@pytest.fixture
def gift_box(db):
    """Caixa com pão (sem ST, 102/5102) e mostarda (ST, 500/5405), preços diferentes."""
    from shopman.offerman.models import ProductComponent

    bread = Product.objects.create(
        sku="PAO-KIT", name="Pão de Campagne", base_price_q=2000,
        metadata={"fiscal": {"profile": "standard", "ncm": "19059090"}},
    )
    mustard = Product.objects.create(
        sku="MOSTARDA-KIT", name="Mostarda Dijon", base_price_q=3000,
        metadata={"fiscal": {"profile": "tax_substitution", "ncm": "21033021", "cest": "1703800"}},
    )
    box = Product.objects.create(
        sku="CAIXA-KIT", name="Caixa Presente", base_price_q=4999,
        metadata={"kit": True, "fiscal": {"profile": "standard", "ncm": "19059090"}},
    )
    ProductComponent.objects.create(parent=box, component=bread, qty=1)
    ProductComponent.objects.create(parent=box, component=mustard, qty=1)
    return box


def test_kit_abre_uma_linha_por_componente_com_o_fiscal_de_cada_um(gift_box):
    order = _kit_order("ORD-KIT-1", ("CAIXA-KIT", "Caixa Presente", 1, 4999, 4999))

    items = fiscal_service._build_fiscal_items(order)

    assert [i["sku"] for i in items] == ["PAO-KIT", "MOSTARDA-KIT"]
    bread, mustard = items
    assert (bread["fiscal"]["cfop"], bread["fiscal"]["icms_situacao_tributaria"]) == ("5102", "102")
    assert (mustard["fiscal"]["cfop"], mustard["fiscal"]["icms_situacao_tributaria"]) == ("5405", "500")
    assert mustard["fiscal"]["ncm"] == "21033021" and mustard["fiscal"]["cest"] == "1703800"
    assert bread["name"] == "Pão de Campagne"
    assert bread["meta"]["kit"] == {"sku": "CAIXA-KIT", "name": "Caixa Presente", "qty": "1"}


def test_rateio_proporcional_ao_preco_avulso_e_a_soma_fecha_no_centavo(gift_box):
    # 4999 × 2000/5000 = 1999,6 → 1999; o resto (3000) vai na última linha.
    order = _kit_order("ORD-KIT-2", ("CAIXA-KIT", "Caixa Presente", 1, 4999, 4999))

    bread, mustard = fiscal_service._build_fiscal_items(order)

    assert (bread["total_q"], mustard["total_q"]) == (1999, 3000)
    assert bread["total_q"] + mustard["total_q"] == 4999


def test_desconto_da_linha_vai_junto_no_rateio_e_a_quantidade_multiplica(gift_box):
    from shopman.offerman.models import ProductComponent

    ProductComponent.objects.filter(component__sku="PAO-KIT").update(qty=3)
    # 2 caixas, com desconto: o total cobrado da linha (9001) é o que se rateia.
    order = _kit_order("ORD-KIT-3", ("CAIXA-KIT", "Caixa Presente", 2, 4999, 9001))

    bread, mustard = fiscal_service._build_fiscal_items(order)

    assert (bread["qty"], mustard["qty"]) == ("6", "2")
    # pesos: pão 2000 × 3 = 6000; mostarda 3000 × 1 = 3000 → 2/3 e 1/3.
    assert bread["total_q"] == 6000  # floor(9001 × 6000 / 9000) = 6000
    assert mustard["total_q"] == 3001
    assert bread["total_q"] + mustard["total_q"] == 9001
    assert bread["unit_price_q"] == 1000


def test_componentes_sem_preco_rateiam_igual(gift_box):
    Product.objects.filter(sku__in=["PAO-KIT", "MOSTARDA-KIT"]).update(base_price_q=0)
    order = _kit_order("ORD-KIT-4", ("CAIXA-KIT", "Caixa Presente", 1, 1001, 1001))

    bread, mustard = fiscal_service._build_fiscal_items(order)

    assert (bread["total_q"], mustard["total_q"]) == (500, 501)


def test_pacote_de_n_unidades_sai_como_n_do_mesmo_pao_pelo_preco_do_pacote(db):
    from shopman.offerman.models import ProductComponent

    bun = Product.objects.create(
        sku="BRBB", name="Brioche Burger Bun", base_price_q=900,
        metadata={"fiscal": {"profile": "standard", "ncm": "19059090"}},
    )
    pack = Product.objects.create(
        sku="BRBB2", name="Brioche Burger Bun (pc. 2un.)", base_price_q=1600,
        metadata={"fiscal": {"profile": "standard", "ncm": "19059090"}},
    )
    ProductComponent.objects.create(parent=pack, component=bun, qty=2)
    order = _kit_order("ORD-KIT-5", ("BRBB2", "Brioche Burger Bun (pc. 2un.)", 1, 1600, 1600))

    (line,) = fiscal_service._build_fiscal_items(order)

    assert (line["sku"], line["name"], line["qty"]) == ("BRBB", "Brioche Burger Bun", "2")
    assert (line["total_q"], line["unit_price_q"]) == (1600, 800)
    assert line["fiscal"]["ncm"] == "19059090"


def test_linha_de_produto_comum_nao_muda(order_with_item):
    (line,) = fiscal_service._build_fiscal_items(order_with_item)

    assert line["sku"] == "PAO-1" and line["name"] == "Pão"
    assert (line["qty"], line["unit_price_q"], line["total_q"]) == ("1", 1000, 1000)
    assert "kit" not in line["meta"]
    assert line["fiscal"]["ncm"] == "19059010"


def test_kit_aberto_passa_pelo_adapter_e_a_nota_fecha(gift_box):
    from shopman.shop.adapters.fiscal_focusnfe import _map_item

    order = _kit_order("ORD-KIT-6", ("CAIXA-KIT", "Caixa Presente", 1, 4999, 4999))
    mapped = [_map_item(i, item, {}) for i, item in enumerate(fiscal_service._build_fiscal_items(order), 1)]

    assert [m["codigo_ncm"] for m in mapped] == ["19059090", "21033021"]
    assert [m["cfop"] for m in mapped] == ["5102", "5405"]
    assert sum(int(round(float(m["valor_bruto"]) * 100)) for m in mapped) == 4999


def test_cada_linha_do_kit_leva_o_gtin_do_seu_componente(gift_box):
    Product.objects.filter(sku="MOSTARDA-KIT").update(metadata={
        "fiscal": {"profile": "tax_substitution", "ncm": "21033021", "cest": "1703800"},
        "social": {"gtin": VALID_GTIN},
    })
    order = _kit_order("ORD-KIT-7", ("CAIXA-KIT", "Caixa Presente", 1, 4999, 4999))

    bread, mustard = fiscal_service._build_fiscal_items(order)

    assert (bread["gtin"], mustard["gtin"]) == ("", VALID_GTIN)


# ── caixa presente com preço próprio: o ágio sai na embalagem ───────────────
#
# Os itens saem pelo preço avulso; a diferença (preço do kit − soma avulsa) sai
# na linha da caixa física. Kit com desconto (soma avulsa ≥ preço do kit) não
# tem linha de caixa: o preço é rateado entre os itens.


@pytest.fixture
def gift_box_with_packaging(gift_box):
    from shopman.offerman.models import ProductComponent

    packaging = Product.objects.create(
        sku="CAIXA-KIT-EMB", name="Caixa Presente (embalagem)", base_price_q=0, is_sellable=False,
        metadata={"kit_packaging": True, "fiscal": {"profile": "standard", "ncm": "48192000"}},
    )
    ProductComponent.objects.create(parent=gift_box, component=packaging, qty=1)
    return gift_box


def test_agio_itens_pelo_preco_avulso_e_a_diferenca_na_embalagem(gift_box_with_packaging):
    # Kit a R$ 60,00; pão 20,00 + mostarda 30,00 = 50,00 avulsos → caixa 10,00.
    order = _kit_order("ORD-KIT-AGIO-1", ("CAIXA-KIT", "Caixa Presente", 1, 6000, 6000))

    items = fiscal_service._build_fiscal_items(order)

    assert [(i["sku"], i["total_q"]) for i in items] == [
        ("PAO-KIT", 2000), ("MOSTARDA-KIT", 3000), ("CAIXA-KIT-EMB", 1000),
    ]
    packaging = items[-1]
    assert packaging["name"] == "Caixa Presente (embalagem)"
    assert packaging["fiscal"]["ncm"] == "48192000"
    assert (packaging["fiscal"]["cfop"], packaging["fiscal"]["icms_situacao_tributaria"]) == ("5102", "102")
    assert packaging["gtin"] == ""
    assert sum(i["total_q"] for i in items) == 6000


def test_agio_com_desconto_da_venda_rateia_entre_todas_as_linhas_inclusive_a_caixa(gift_box_with_packaging):
    # Lista 60,00, vendido com 10% (54,00): 20/30/10 viram 18/27/9.
    Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV"})
    order = Order.objects.create(ref="ORD-KIT-AGIO-2", channel_ref="pdv", status=Order.Status.COMPLETED, total_q=0)
    order.items.create(
        sku="CAIXA-KIT", name="Caixa Presente", qty=1, unit_price_q=5400, line_total_q=5400,
        meta={"_list_q": 6000, "_disc": {"type": "manual", "amount_q": 600, "label": "10%"}},
    )

    items = fiscal_service._build_fiscal_items(order)

    assert [i["total_q"] for i in items] == [1800, 2700, 900]


def test_agio_com_desconto_que_nao_divide_redondo_fecha_no_centavo(gift_box_with_packaging):
    Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV"})
    order = Order.objects.create(ref="ORD-KIT-AGIO-3", channel_ref="pdv", status=Order.Status.COMPLETED, total_q=0)
    order.items.create(
        sku="CAIXA-KIT", name="Caixa Presente", qty=3, unit_price_q=5333, line_total_q=15999,
        meta={"_list_q": 6000},
    )

    items = fiscal_service._build_fiscal_items(order)

    # pesos 6000/9000/3000 de 18000; 15999 → 5333, 7999, e o resto 2667 na caixa.
    assert [i["total_q"] for i in items] == [5333, 7999, 2667]
    assert sum(i["total_q"] for i in items) == 15999
    assert [i["qty"] for i in items] == ["3", "3", "3"]


def test_kit_com_desconto_nao_tem_linha_de_caixa(gift_box_with_packaging):
    # Kit a R$ 45,00 < 50,00 avulsos: sem caixa, 45,00 rateado 2:3 entre os itens.
    order = _kit_order("ORD-KIT-DESC-1", ("CAIXA-KIT", "Caixa Presente", 1, 4500, 4500))

    items = fiscal_service._build_fiscal_items(order)

    assert [(i["sku"], i["total_q"]) for i in items] == [("PAO-KIT", 1800), ("MOSTARDA-KIT", 2700)]


def test_kit_com_preco_igual_a_soma_avulsa_nao_tem_linha_de_caixa(gift_box_with_packaging):
    order = _kit_order("ORD-KIT-DESC-2", ("CAIXA-KIT", "Caixa Presente", 1, 5000, 5000))

    items = fiscal_service._build_fiscal_items(order)

    assert [(i["sku"], i["total_q"]) for i in items] == [("PAO-KIT", 2000), ("MOSTARDA-KIT", 3000)]


def test_kit_com_agio_passa_pelo_adapter_focus_e_a_nota_fecha(gift_box_with_packaging):
    from shopman.shop.adapters.fiscal_focusnfe import _map_item

    order = _kit_order("ORD-KIT-AGIO-4", ("CAIXA-KIT", "Caixa Presente", 1, 6000, 6000))
    mapped = [_map_item(i, item, {}) for i, item in enumerate(fiscal_service._build_fiscal_items(order), 1)]

    assert [m["codigo_ncm"] for m in mapped] == ["19059090", "21033021", "48192000"]
    assert [m["cfop"] for m in mapped] == ["5102", "5405", "5102"]
    assert mapped[-1]["codigo_barras_comercial"] == "SEM GTIN"
    assert [m["valor_unitario_comercial"] for m in mapped] == ["20.00", "30.00", "10.00"]
    assert sum(int(round(float(m["valor_bruto"]) * 100)) for m in mapped) == 6000


def test_a_embalagem_nao_entra_na_expansao_de_disponibilidade_e_reserva(gift_box_with_packaging):
    from shopman.shop.adapters.catalog import expand_bundle

    assert [c["sku"] for c in expand_bundle("CAIXA-KIT", 1)] == ["PAO-KIT", "MOSTARDA-KIT"]
