"""O saldo à vista só quando o item está ACABANDO (DEV-2026-077).

Decisão do dono (23/11/2026, opção C da prévia): o tile do PDV mostra "Restam 3"
à vista só quando o item está acabando, e "acabando" é uma porcentagem por SKU,
mostrada em unidades e arredondada para cima, porque há pães de que a casa faz
poucas unidades. A mesma régua diz o "Últimas N un." do card da Cozinha, que antes
lia o ``StockAlert.min_quantity`` (agora só reposição).

Estes testes usam o estoque de verdade (Stockman), não um dublê: a referência do
dia sai do ledger.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.stockman.models import Move, Position, Quant, StockAlert
from shopman.stockman.services.movements import StockMovements

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.projections.kds import _add_stock_warnings
from shopman.backstage.services import catalog
from shopman.backstage.services.exceptions import CatalogError
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import running_low

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/pos/"


# ── a régua, sem banco ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("percent", "reference", "expected"),
    [
        (20, 6, 2),  # 1,2 vira 2: o pão de poucas unidades avisa
        (20, 4, 1),  # 0,8 vira 1: para baixo, nunca avisaria
        (20, 30, 6),
        (20, 5, 1),
        (0, 30, 0),  # 0 desliga
        (100, 7, 7),
        (20, 0, 0),
    ],
)
def test_o_limiar_em_unidades_arredonda_para_cima(percent, reference, expected):
    assert running_low.threshold_units(percent, reference) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(20, 20), ("35", 35), (" 5 ", 5), (0, 0), (100, 100), (20.0, 20),
     (101, None), (-1, None), ("vinte", None), (12.5, None), (True, None), (None, None), ("", None)],
)
def test_a_porcentagem_e_inteira_de_0_a_100(raw, expected):
    assert running_low.coerce_percent(raw) == expected


def test_esgotado_nao_e_acabando():
    assert running_low.is_running_low(0, percent=20, reference=6) is False
    assert running_low.is_running_low(2, percent=0, reference=6) is False
    assert running_low.is_running_low(2, percent=20, reference=6) is True


# ── o PDV, com o estoque de verdade ─────────────────────────────────────────


@pytest.fixture
def vitrine():
    return Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)


@pytest.fixture
def balcao(client, vitrine):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref=POS_CHANNEL_REF, name="PDV", is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
    listing = Listing.objects.create(ref=POS_CHANNEL_REF, name="PDV", is_active=True)
    for sku in ("POUCO", "MUITO"):
        product = Product.objects.create(sku=sku, name=sku.title(), base_price_q=1000, is_published=True, is_sellable=True)
        ListingItem.objects.create(listing=listing, product=product, price_q=1000)
    operator = get_user_model().objects.create_user(username="fran", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos")
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    return client


def _receive(sku: str, qty: int, position, *, target_date: date | None = None) -> Quant:
    StockMovements.receive(qty, sku, position=position, target_date=target_date, reason="teste", kind=Move.Kind.MAKE)
    return Quant.objects.filter(sku=sku, position=position, target_date=target_date).order_by("pk").last()


def _sell(quant: Quant, qty: int) -> None:
    StockMovements.issue(qty, quant, reason="venda de teste", kind=Move.Kind.SELL)


def _shop_defaults(defaults: dict) -> None:
    # Pelo ``save``: o ``Shop.load`` lê do cache, e o ``update`` não o invalida.
    shop = Shop.objects.get()
    shop.defaults = defaults
    shop.save()


def _tiles(client) -> dict[str, dict]:
    response = client.get(URL)
    assert response.status_code == 200, response.content
    return {p["sku"]: p for p in response.json()["pos"]["products"]}


def _rows(client) -> dict[str, dict]:
    response = client.get(URL + "?only=availability")
    assert response.status_code == 200, response.content
    return {row["sku"]: row for row in response.json()["availability"]}


def test_pao_de_seis_avisa_com_dois_e_pao_de_trinta_com_seis(balcao, vitrine):
    pouco = _receive("POUCO", 6, vitrine)
    muito = _receive("MUITO", 30, vitrine)

    tiles = _tiles(balcao)
    assert (tiles["POUCO"]["units_left"], tiles["POUCO"]["running_low"]) == (6, False)
    assert (tiles["MUITO"]["units_left"], tiles["MUITO"]["running_low"]) == (30, False)

    _sell(pouco, 3)  # restam 3 de 6: ainda não (20% de 6 = 2)
    _sell(muito, 23)  # restam 7 de 30: ainda não (20% de 30 = 6)
    tiles = _tiles(balcao)
    assert (tiles["POUCO"]["units_left"], tiles["POUCO"]["running_low"]) == (3, False)
    assert (tiles["MUITO"]["units_left"], tiles["MUITO"]["running_low"]) == (7, False)

    _sell(pouco, 1)  # restam 2 de 6
    _sell(muito, 1)  # restam 6 de 30
    tiles = _tiles(balcao)
    assert (tiles["POUCO"]["units_left"], tiles["POUCO"]["running_low"]) == (2, True)
    assert (tiles["MUITO"]["units_left"], tiles["MUITO"]["running_low"]) == (6, True)
    # O aviso de estoque relê só os selos: o mesmo número e o mesmo "acabando".
    rows = _rows(balcao)
    assert (rows["POUCO"]["units_left"], rows["POUCO"]["running_low"]) == (2, True)
    assert (rows["MUITO"]["units_left"], rows["MUITO"]["running_low"]) == (6, True)


def test_a_fornada_de_hoje_ainda_nao_finalizada_conta_dos_dois_lados(balcao, vitrine):
    """O risco do quant datado de hoje: o ``units_left`` o conta como pronto.

    Saíram 6 da primeira fornada e há 18 planejados para hoje (quant com
    ``target_date`` de hoje). O ``shelf_history`` sozinho diria que o dia teve 6,
    e com 5 vendidos o pão estaria "acabando" (1 de 6) enquanto o tile mostra 19.
    A referência sai do MESMO número do tile: 19 restam + 5 vendidos = 24.
    """
    from shopman.stockman.services.queries import StockQueries

    today = timezone.localdate()
    prateleira = _receive("POUCO", 6, vitrine)
    _receive("POUCO", 18, vitrine, target_date=today)
    _sell(prateleira, 5)

    tile = _tiles(balcao)["POUCO"]
    shelf = StockQueries.shelf_history(["POUCO"], since=today, until=today)["POUCO"][today]
    assert shelf.opening + shelf.received == 6  # o que o shelf_history vê
    assert tile["units_left"] == 19  # o que o tile mostra: prateleira + fornada de hoje
    # Medido sobre o próprio número (19 + 5 = 24), o pão não está acabando.
    assert tile["running_low"] is False
    gone = running_low.left_today(["POUCO"])["POUCO"]
    assert tile["units_left"] + gone == 24
    # A régua, chamada direto sobre o número do tile, dá o mesmo veredito.
    assert running_low.running_low_skus({"POUCO": tile["units_left"]}) == set()


def test_a_porcentagem_propria_do_produto_vence_o_padrao_da_loja(balcao, vitrine):
    Product.objects.filter(sku="POUCO").update(metadata={"running_low_percent": 50})
    quant = _receive("POUCO", 6, vitrine)

    _sell(quant, 2)  # restam 4 de 6: 50% de 6 = 3, ainda não
    assert _tiles(balcao)["POUCO"]["running_low"] is False
    _sell(quant, 1)  # restam 3
    assert _tiles(balcao)["POUCO"]["running_low"] is True


def test_o_padrao_da_loja_zero_desliga_o_aviso(balcao, vitrine):
    _shop_defaults({"running_low": {"percent": 0}})
    quant = _receive("POUCO", 6, vitrine)
    _sell(quant, 5)
    tile = _tiles(balcao)["POUCO"]
    assert (tile["units_left"], tile["running_low"]) == (1, False)


def test_padrao_ilegivel_cai_nos_vinte_por_cento(balcao, vitrine):
    _shop_defaults({"running_low": {"percent": "muito"}})
    assert running_low.shop_default_percent() == running_low.DEFAULT_PERCENT == 20


def test_a_devolucao_volta_ao_saldo_e_sai_das_saidas(balcao, vitrine):
    quant = _receive("POUCO", 6, vitrine)
    _sell(quant, 5)
    StockMovements.receive_into(1, quant, reason="devolução de teste", kind=Move.Kind.RETURN)
    # 2 restam, saíram 4 (5 vendidos, 1 devolvido): a referência continua 6.
    assert running_low.left_today(["POUCO"]) == {"POUCO": 4}
    assert _tiles(balcao)["POUCO"]["running_low"] is True


# ── a Cozinha lê a mesma régua, e o StockAlert virou só reposição ───────────


def test_a_cozinha_diz_ultimas_pela_mesma_regua_e_nao_pelo_alerta_de_reposicao(vitrine):
    Shop.objects.create(name="Nelson")
    for sku in ("POUCO", "MUITO"):
        Product.objects.create(sku=sku, name=sku.title(), base_price_q=1000)
    # O alerta de reposição pede 20 de cada: antes, os dois diriam "Últimas".
    for sku in ("POUCO", "MUITO"):
        StockAlert.objects.create(sku=sku, position=vitrine, min_quantity=20)
    _sell(_receive("POUCO", 6, vitrine), 4)  # restam 2 de 6: acabando
    _sell(_receive("MUITO", 30, vitrine), 15)  # restam 15 de 30: não

    warnings = {item["sku"]: item.get("stock_warning", "") for item in _add_stock_warnings([{"sku": "POUCO"}, {"sku": "MUITO"}])}
    assert warnings == {"POUCO": "Últimas 2 un.", "MUITO": ""}


# ── o painel do produto no Catálogo do Gestor ───────────────────────────────


@pytest.fixture
def pao():
    Shop.objects.create(name="Loja", defaults={"running_low": {"percent": 25}})
    return Product.objects.create(sku="PAO", name="Pão", base_price_q=1200)


def test_o_detalhe_mostra_a_porcentagem_propria_e_o_padrao_da_loja(pao):
    detail = catalog.get_product_detail("PAO")
    assert detail["running_low_percent"] is None
    assert detail["running_low_default_percent"] == 25


def test_gravar_e_apagar_a_porcentagem_propria(pao):
    assert catalog.update_product_detail("PAO", {"running_low_percent": 40})["running_low_percent"] == 40
    assert Product.objects.get(sku="PAO").metadata["running_low_percent"] == 40
    assert running_low.percents_for(["PAO"]) == {"PAO": 40}

    assert catalog.update_product_detail("PAO", {"running_low_percent": None})["running_low_percent"] is None
    assert "running_low_percent" not in Product.objects.get(sku="PAO").metadata
    assert running_low.percents_for(["PAO"]) == {"PAO": 25}


@pytest.mark.parametrize("raw", [150, -5, "muito", 12.5])
def test_porcentagem_fora_da_faixa_e_recusada_e_nao_guardada(pao, raw):
    with pytest.raises(CatalogError) as exc:
        catalog.update_product_detail("PAO", {"running_low_percent": raw})
    assert "0 a 100%" in str(exc.value)
    assert "running_low_percent" not in Product.objects.get(sku="PAO").metadata


# ── a faceta "Estoque baixo" do Catálogo do Gestor lê a mesma régua ─────────


def test_a_faceta_do_catalogo_marca_acabando_pela_porcentagem_do_sku(vitrine, monkeypatch):
    """O operador vê UMA régua: o pão de 6 com 2 está acabando; o de 30 com 15, não.

    Antes, a faceta comparava com o número fixo do canal (5): o pão de 30 com 5
    ficaria "baixo" junto com o de 6 com 5, que é quase cheio.
    """
    from shopman.backstage.projections import catalog as projection

    Shop.objects.create(name="Nelson")
    Channel.objects.create(
        ref="balcao", name="Balcão", is_active=True, commerce_policy=Channel.CommercePolicy.ORDER,
    )
    for sku in ("POUCO", "MUITO"):
        Product.objects.create(sku=sku, name=sku.title(), base_price_q=1000)
    _sell(_receive("POUCO", 6, vitrine), 4)
    _sell(_receive("MUITO", 30, vitrine), 15)
    shown = {"POUCO": 2, "MUITO": 15}
    monkeypatch.setattr(
        "shopman.shop.projections.catalog_context.availability_for_skus",
        lambda skus, *, channel_ref: {sku: {"is_tracked": True, "total_promisable": shown[sku]} for sku in skus},
    )

    _, low, _ = projection._stock_for(["POUCO", "MUITO"])
    assert low == {"POUCO"}
    assert projection._stock_bucket({"is_tracked": True, "total_promisable": 2}, "POUCO" in low) == "low"
    assert projection._stock_bucket({"is_tracked": True, "total_promisable": 15}, "MUITO" in low) == "ok"
