"""Venda por peso no balcão: a etiqueta (ou o peso) vira QUANTIDADE, nunca preço.

Caso real: o Queijo Vale do Testo, fracionado, pesado e etiquetado à mão. A
etiqueta tem peso e valor; o operador digita o que tem em mãos e o PDV deriva o
outro pelo preço do quilo do catálogo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import services as cash
from shopman.orderman.models import Order, Session
from shopman.utils.monetary import monetary_mult

from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services import weighed_sale
from shopman.shop.services.pos_intent import PosIntentError

QUEIJO = "QUEIJO-VALEDOTESTO-POMERODE"
PRECO_KG = 8990  # R$ 89,90/kg


# ── A conta, sem banco ─────────────────────────────────────────────────────


def test_etiqueta_feita_com_o_mesmo_preco_do_quilo_devolve_o_peso_e_o_valor_exatos():
    # 312 g a R$ 89,90/kg = R$ 28,0488 → a balança imprime R$ 28,05.
    assert weighed_sale.grams_for_label(2805, PRECO_KG) == 312
    assert weighed_sale.total_for_grams(312, PRECO_KG) == 2805


@pytest.mark.parametrize("price", [150, 999, 1000, 1001, 4590, 8990, 12990, 23900])
def test_qualquer_etiqueta_da_mesma_balanca_bate_no_centavo(price):
    """A promessa do "total bate com a etiqueta": para toda peça de 1 g a 3 kg,
    pesada com o preço do catálogo, o valor impresso volta idêntico."""
    for grams in range(1, 3001):
        label_q = weighed_sale.total_for_grams(grams, price)
        if label_q <= 0:
            continue
        line = weighed_sale.resolve(name="Queijo", entry="label", price_per_kg_q=price, label_q=label_q)
        assert line.total_q == label_q, (price, grams)
        assert line.label_gap_q == 0


@pytest.mark.parametrize("price", [999, 4590, 8990, 23900])
def test_etiqueta_de_outro_preco_nunca_cobra_acima_do_impresso(price):
    """Quando o valor não tem grama exata (a balança usou outro preço do quilo),
    a linha fica no MAIOR peso que não passa da etiqueta — e diz a diferença."""
    for label_q in range(50, 6000, 7):
        grams = weighed_sale.grams_for_label(label_q, price)
        if grams <= 0:
            continue
        assert weighed_sale.total_for_grams(grams, price) <= label_q
        assert weighed_sale.total_for_grams(grams + 1, price) > label_q


def test_diferenca_de_arredondamento_fica_visivel_e_a_favor_do_cliente():
    # R$ 28,00 não é múltiplo de grama a R$ 89,90/kg: 311 g = R$ 27,96, 312 g = R$ 28,05.
    line = weighed_sale.resolve(name="Queijo", entry="label", price_per_kg_q=PRECO_KG, label_q=2800)
    assert line.weight_g == 311
    assert line.total_q == 2796
    assert line.label_gap_q == 4


def test_peso_digitado_vira_o_valor_pela_conta_do_kernel():
    line = weighed_sale.resolve(name="Queijo", entry="weight", price_per_kg_q=PRECO_KG, weight_g=312)
    assert line.qty == Decimal("0.312")
    assert line.total_q == monetary_mult(Decimal("0.312"), PRECO_KG) == 2805
    assert line.label_gap_q == 0


def test_sem_preco_do_quilo_nao_ha_venda_por_peso():
    with pytest.raises(weighed_sale.WeighedEntryError) as exc:
        weighed_sale.resolve(name="Queijo", entry="label", price_per_kg_q=0, label_q=2805)
    assert exc.value.code == "price_missing"


def test_valor_menor_que_uma_grama_e_recusado():
    with pytest.raises(weighed_sale.WeighedEntryError) as exc:
        weighed_sale.resolve(name="Queijo", entry="label", price_per_kg_q=PRECO_KG, label_q=4)
    assert exc.value.code == "weight_label_below_one_gram"


def test_peso_absurdo_e_recusado():
    with pytest.raises(weighed_sale.WeighedEntryError) as exc:
        weighed_sale.resolve(name="Queijo", entry="weight", price_per_kg_q=PRECO_KG, weight_g=31200)
    assert exc.value.code == "weight_too_large"
    assert "31,200 kg" in exc.value.message


# ── O balcão de ponta a ponta ──────────────────────────────────────────────


class _Counter:
    def __init__(self, *, price_q: int = PRECO_KG):
        from shopman.offerman.models import Product

        Shop.objects.create(name="Test Shop", brand_name="Test")
        self.channel = Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={
                "confirmation": {"mode": "immediate"},
                "payment": {"method": "cash", "timing": "external"},
                "stock": {"check_on_commit": False},
            },
        )
        self.queijo = Product.objects.create(
            sku=QUEIJO, name="Queijo Vale do Testo", unit="kg", base_price_q=price_q,
            is_published=True, is_sellable=True,
            metadata={"fiscal": {"profile": "tax_substitution", "ncm": "04069090", "unit": "UN"}},
        )
        Product.objects.create(sku="PAO", name="Pão", base_price_q=1200, is_published=True, is_sellable=True)
        self.operator = get_user_model().objects.create_user(username="marina", password="x")
        self.shift = cash.open_shift(operator=self.operator, float_q=10000)

    def payload(self, *items, **overrides):
        payload = {
            "items": list(items),
            "customer_name": "Cliente",
            "payment_method": "cash",
            "cash_shift_id": self.shift.pk,
        }
        payload.update(overrides)
        return payload

    def close(self, *items, client_request_id: str = "c1", **overrides):
        return pos_service.close_sale(
            channel_ref="pdv",
            payload=self.payload(*items, client_request_id=client_request_id, **overrides),
            actor="pos:marina",
            operator_username="marina",
        )

    def review(self, *items, **overrides):
        return pos_service.review_sale(
            channel_ref="pdv", payload=self.payload(*items, **overrides), operator_username="marina",
        )


def _queijo(**weighed):
    # ``qty`` e ``unit_price_q`` do navegador são IGNORADOS na linha pesada.
    return {"sku": QUEIJO, "name": "Queijo Vale do Testo", "qty": 7, "unit_price_q": 1, "weighed": weighed}


@pytest.fixture
def counter(db):
    return _Counter()


def test_venda_pela_etiqueta_fecha_com_o_peso_em_kg_e_o_valor_da_etiqueta(counter):
    result = counter.close(_queijo(entry="label", label_q=2805))

    order = Order.objects.get(ref=result.order_ref)
    (item,) = list(order.items.all())
    assert item.qty == Decimal("0.312")
    assert item.unit_price_q == PRECO_KG
    assert item.line_total_q == 2805
    assert order.total_q == 2805
    assert item.meta["weighed"] == {
        "entry": "label",
        "label_q": 2805,
        "weight_g": 312,
        "price_per_kg_q": PRECO_KG,
        "total_q": 2805,
        "by": "marina",
    }


def test_venda_pelo_peso_fecha_com_o_valor_que_o_peso_vale(counter):
    _liga_entrada_por_peso()
    result = counter.close(_queijo(entry="weight", weight_g=1250), {"sku": "PAO", "name": "Pão", "qty": 2, "unit_price_q": 1200})

    order = Order.objects.get(ref=result.order_ref)
    queijo = order.items.get(sku=QUEIJO)
    assert queijo.qty == Decimal("1.250")
    assert queijo.line_total_q == monetary_mult(Decimal("1.25"), PRECO_KG) == 11238
    assert order.total_q == 11238 + 2400


def test_review_promete_o_mesmo_total_que_o_fechamento_cobra(counter):
    review = counter.review(_queijo(entry="label", label_q=2805))
    assert review.subtotal_q == 2805
    assert review.total_q == 2805
    assert review.requires_manager_approval is False


def test_desconto_de_linha_na_peca_pesada_a_review_mede_o_centavo_do_kernel(counter):
    """A régua do desconto vale para a linha pesada como para qualquer outra:
    10% de cortesia no queijo passa pelo "maior desconto ganha" do kernel, e a
    review não pode prometer um centavo diferente do que o pedido sela."""
    line = _queijo(entry="label", label_q=2805)
    line["discount"] = {"type": "percent", "value": 10, "reason": "cortesia"}

    review = counter.review(line)
    result = counter.close(line)

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == review.total_q
    assert review.line_discount_q > 0


def test_o_valor_digitado_nao_vira_preco_mesmo_quando_o_quilo_e_mais_barato(counter):
    """Etiqueta de R$ 30,00 para um queijo de R$ 89,90/kg: cobra-se o peso que
    R$ 30,00 compra (333 g = R$ 29,94), nunca os R$ 30,00 como preço à mão."""
    result = counter.close(_queijo(entry="label", label_q=3000))
    item = Order.objects.get(ref=result.order_ref).items.get()
    assert item.unit_price_q == PRECO_KG
    assert item.qty == Decimal("0.333")
    assert item.line_total_q == 2994


def test_produto_por_peso_sem_valor_da_etiqueta_e_recusado(counter):
    with pytest.raises(PosIntentError) as exc:
        counter.close({"sku": QUEIJO, "name": "Queijo Vale do Testo", "qty": 1, "unit_price_q": PRECO_KG})
    assert exc.value.code == "weight_entry_required"
    assert exc.value.field == "items.0.weighed"


def test_peso_informado_para_produto_por_unidade_e_recusado(counter):
    with pytest.raises(PosIntentError) as exc:
        counter.close({"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200, "weighed": {"entry": "weight", "weight_g": 300}})
    assert exc.value.code == "not_sold_by_weight"


# ── Preço zero não vende; peso só com a balança ligada ──────────────────────


def _liga_entrada_por_peso():
    shop = Shop.objects.get()
    shop.defaults = {**(shop.defaults or {}), "pos": {"weighed_weight_entry": True}}
    shop.save(update_fields=["defaults"])


@pytest.mark.django_db
def test_produto_por_peso_sem_preco_do_quilo_nunca_sai_a_zero():
    """O Yooga vendeu 34 queijos a R$ 0,00. Aqui, sem preço do quilo, recusa."""
    counter = _Counter(price_q=0)
    _liga_entrada_por_peso()
    for weighed in ({"entry": "label", "label_q": 2805}, {"entry": "weight", "weight_g": 312}):
        with pytest.raises(PosIntentError) as exc:
            counter.review(_queijo(**weighed))
        assert exc.value.code == "price_missing"


def test_entrada_pelo_peso_vem_desligada(counter):
    """Sem balança no balcão, o PDV só aceita o valor da etiqueta."""
    with pytest.raises(PosIntentError) as exc:
        counter.close(_queijo(entry="weight", weight_g=312))
    assert exc.value.code == "weight_entry_disabled"


def test_item_sem_preco_no_catalogo_nao_vende_no_balcao(counter):
    from shopman.offerman.models import Product

    Product.objects.create(sku="CORTESIA", name="Biscoito", base_price_q=0, is_published=True, is_sellable=True)
    with pytest.raises(PosIntentError) as exc:
        counter.review({"sku": "CORTESIA", "name": "Biscoito", "qty": 1, "unit_price_q": 0})
    assert exc.value.code == "price_missing"
    assert exc.value.field == "items.0"


def test_desconto_de_100_por_cento_zera_o_item_pela_regua(counter):
    """Dar o item é desconto de 100%: o cobrado vai a zero, o preço de lista fica."""
    line = {
        "sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200,
        "discount": {"type": "percent", "value": 100, "reason": "cortesia"},
    }
    result = counter.close(line, {"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200, "line_id": "L-pago0001"})
    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1200


@pytest.mark.django_db
def test_nenhum_canal_commita_item_sem_preco():
    """O validador de commit vale para qualquer canal — a loja online inclusive."""
    from shopman.orderman.exceptions import ValidationError

    from shopman.shop.rules.validation import PricedItemsRule

    class _Session:
        items = [
            {"sku": "PAO", "name": "Pão", "unit_price_q": 0, "meta": {"_list_q": 1200}},
            {"sku": "__DELIVERY_FEE__", "name": "Taxa", "unit_price_q": 0, "meta": {"type": "delivery_fee"}},
        ]

    PricedItemsRule().validate(channel=None, session=_Session(), ctx={})  # 100% de desconto passa

    _Session.items = [{"sku": "QUEIJO", "name": "Queijo", "unit_price_q": 0, "meta": {"_list_q": 0}}]
    with pytest.raises(ValidationError) as exc:
        PricedItemsRule().validate(channel=None, session=_Session(), ctx={})
    assert exc.value.code == "price_missing"


def test_preco_do_listing_do_canal_e_o_preco_do_quilo(counter):
    """O listing do canal vence o base — e a faixa ``min_qty=1`` vale para
    0,3 kg. Com ``int(qty)`` o kernel pulava o listing e cobrava o base."""
    from shopman.offerman.models import Listing, ListingItem

    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    ListingItem.objects.create(listing=listing, product=counter.queijo, price_q=7990, is_published=True, is_sellable=True)

    result = counter.close(_queijo(entry="label", label_q=2493))
    item = Order.objects.get(ref=result.order_ref).items.get()
    assert item.unit_price_q == 7990
    assert item.qty == Decimal("0.312")
    assert item.line_total_q == 2493


def test_nfce_sai_em_quilo_com_o_preco_do_quilo(counter):
    from shopman.shop.adapters.fiscal_focusnfe import _map_item
    from shopman.shop.services.fiscal import _build_fiscal_items

    result = counter.close(_queijo(entry="label", label_q=2805))
    (fiscal_item,) = _build_fiscal_items(Order.objects.get(ref=result.order_ref))
    assert fiscal_item["qty"] == "0.312"
    assert fiscal_item["fiscal"]["unit"] == "KG"

    mapped = _map_item(1, fiscal_item, {})
    assert mapped["unidade_comercial"] == "KG"
    assert mapped["unidade_tributavel"] == "KG"
    assert mapped["quantidade_comercial"] == "0.312"
    assert mapped["valor_unitario_comercial"] == "89.90"
    assert mapped["valor_bruto"] == "28.05"


def test_comanda_guarda_e_devolve_a_peca_pesada(counter):
    from shopman.backstage.projections.pos import build_open_tab

    session_key = pos_service.open_pos_tab(
        channel_ref="pdv", tab_ref="7", actor="pos:marina", operator_username="marina",
    ).session_key
    pos_service.save_pos_tab(
        channel_ref="pdv",
        payload={"tab_session_key": session_key, "items": [_queijo(entry="label", label_q=2805)]},
        actor="pos:marina",
        operator_username="marina",
    )

    tab = build_open_tab(Session.objects.get(session_key=session_key))
    (line,) = tab["items"]
    assert line["qty"] == 0.312
    assert line["price_q"] == PRECO_KG
    assert line["weighed"] == {"entry": "label", "label_q": 2805, "weight_g": 312}


def test_grade_do_pdv_diz_que_o_preco_e_do_quilo(counter):
    from shopman.backstage.projections.pos import _product_projection

    tile = _product_projection(counter.queijo, PRECO_KG)
    assert tile.sold_by_weight is True
    assert tile.price_display == "R$ 89,90/kg"


def test_a_chave_da_balanca_e_da_loja_e_nasce_desligada(counter):
    assert weighed_sale.weight_entry_enabled() is False
    _liga_entrada_por_peso()
    assert weighed_sale.weight_entry_enabled() is True


_POS_TRANSITIONS = {
    "new": ["accepted", "cancelled"],
    "accepted": ["preparing", "ready", "completed", "cancelled"],
    "preparing": ["ready", "cancelled"],
    "ready": ["preparing", "dispatched", "completed"],
    "dispatched": ["delivered", "returned"],
    "delivered": ["completed", "returned"],
    "completed": ["returned", "cancelled"],
    "cancelled": [],
    "returned": [],
}


@pytest.mark.django_db(transaction=True)
def test_estoque_baixa_em_quilo():
    """2 kg de queijo na vitrine; vendida a peça de 312 g, sobram 1,688 kg.

    ``transaction=True`` de propósito: a reserva/baixa sai do lifecycle, que roda
    no ``on_commit`` do fechamento — como em produção.
    """
    from shopman.stockman import PositionKind
    from shopman.stockman.models import Position, Quant
    from shopman.stockman.services import StockQueries

    counter = _Counter()
    counter.channel.config = {
        **counter.channel.config,
        "stock": {"check_on_commit": False, "allow_untracked": False, "sells_nonconforming": True},
        "lifecycle": {"transitions": _POS_TRANSITIONS},
    }
    counter.channel.save(update_fields=["config"])
    vitrine = Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
    Quant.objects.create(sku=QUEIJO, position=vitrine, _quantity=Decimal("2.000"))

    counter.close(_queijo(entry="label", label_q=2805))

    assert StockQueries.available(QUEIJO) == Decimal("1.688")


@pytest.mark.django_db
def test_produto_a_quilo_fica_so_no_balcao():
    """Canal remoto vende unidade inteira: a peça a quilo só vende no PDV."""
    from shopman.offerman.models import Listing, ListingItem, Product

    from shopman.shop.services.sku_records import sync_sale_listings

    for ref in ("pdv", "web", "whatsapp", "ifood"):
        Listing.objects.create(ref=ref, name=ref, is_active=True)
    queijo = Product.objects.create(
        sku=QUEIJO, name="Queijo", unit="kg", base_price_q=PRECO_KG, image_url="https://img/queijo.jpg",
        is_published=True, is_sellable=True,
    )
    ListingItem.objects.create(listing=Listing.objects.get(ref="web"), product=queijo, price_q=PRECO_KG)

    listed, unlisted = sync_sale_listings(queijo, PRECO_KG)

    assert listed == ["pdv"]
    assert unlisted == ["web"]
    assert list(ListingItem.objects.filter(product=queijo).values_list("listing__ref", flat=True)) == ["pdv"]


def test_vendido_por_peso_tem_uma_definicao_so():
    """O PDV, a NF-e e o cadastro de venda perguntam à MESMA função."""
    from shopman.shop.services import sku_records

    assert not hasattr(sku_records, "is_sold_by_weight")
    assert weighed_sale.is_sold_by_weight("Kg") is True
    assert weighed_sale.is_sold_by_weight("un") is False
    assert weighed_sale.is_sold_by_weight("") is False
