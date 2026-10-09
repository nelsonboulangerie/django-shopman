"""A revisão da venda do PDV não pode custar uma ida ao banco por linha.

O ``review_sale`` roda a cada mudança do carrinho no balcão (o operador vê o
total, os avisos e as janelas antes de cobrar). Medido em 09/10/2026: ~15
consultas POR LINHA, quase todas do aviso de disponibilidade, que perguntava ao
``availability.decide`` item por item (canal, listagem, item da listagem,
bundle, recorte do canal, leitura do estoque, fila de espera…). Uma sacola de
dez linhas pagava ~150 consultas para mostrar o mesmo aviso.

Este arquivo trava duas coisas:

1. **O custo não cresce com o número de linhas** — a diferença entre dez linhas
   e uma é uma constante pequena, não dez vezes o custo de uma linha.
2. **O resultado é o mesmo** — o aviso de falta sai para quem falta, com a mesma
   frase, e não sai para quem tem saldo ou não é rastreado.
"""

from __future__ import annotations

import time
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind

from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service

pytestmark = pytest.mark.django_db

ABERTO_TODO_DIA = {
    day: {"open": "00:00", "close": "23:59"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}

LINHAS = 10


@pytest.fixture
def balcao():
    Shop.objects.create(name="Nelson", brand_name="Nelson", opening_hours=ABERTO_TODO_DIA)
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False},
        },
    )
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    position = Position.objects.create(
        ref="loja", name="Loja", kind=PositionKind.PHYSICAL, is_saleable=True,
    )
    for i in range(LINHAS):
        product = Product.objects.create(
            sku=f"P{i:02d}", name=f"Produto {i}", base_price_q=900,
            is_published=True, is_sellable=True,
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=900)
        # Um terço com saldo de sobra, um terço com saldo curto (gera aviso) e
        # um terço sem estoque rastreado (aprovado sem limite).
        if i % 3 == 0:
            stock.receive(
                quantity=Decimal("50"), sku=product.sku, position=position,
                target_date=date.today(), reason="entrada",
            )
        elif i % 3 == 1:
            stock.receive(
                quantity=Decimal("1"), sku=product.sku, position=position,
                target_date=date.today(), reason="entrada",
            )
    # Fora da listagem do canal: recusa pelo portão da listagem.
    Product.objects.create(
        sku="FORA", name="Fora da vitrine", base_price_q=900, is_published=True, is_sellable=True,
    )


def _payload(skus: list[str]) -> dict:
    return {
        "items": [
            {"sku": sku, "name": sku, "qty": 2, "unit_price_q": 900} for sku in skus
        ],
        "fulfillment_type": "pickup",
        "payment_method": "cash",
    }


def _review(skus: list[str]):
    return pos_service.review_sale(
        channel_ref="pdv", payload=_payload(skus), operator_username="marina",
    )


def _measure(skus: list[str]) -> tuple[int, float, object]:
    _review(skus)  # aquece caches de processo (adapters, registro de regras)
    with CaptureQueriesContext(connection) as ctx:
        review = _review(skus)
    melhor_ms = float("inf")
    for _ in range(5):
        started = time.perf_counter()
        _review(skus)
        melhor_ms = min(melhor_ms, (time.perf_counter() - started) * 1000)
    return len(ctx.captured_queries), melhor_ms, review


def _skus(n: int) -> list[str]:
    return [f"P{i:02d}" for i in range(n)]


def test_custo_da_revisao_nao_cresce_com_as_linhas(balcao):
    medidas = {n: _measure(_skus(n)) for n in (1, 5, LINHAS)}
    for n, (queries, ms, _) in medidas.items():
        print(f"review_sale {n:>2} linha(s): {queries} consultas, {ms:.1f} ms")

    uma = medidas[1][0]
    dez = medidas[LINHAS][0]
    assert medidas[5][0] == uma
    assert dez == uma, (
        f"review_sale com {LINHAS} linhas fez {dez} consultas contra {uma} com 1: "
        "a revisão voltou a ir ao banco por linha"
    )


def test_aviso_de_falta_sai_para_quem_falta_e_so_para_quem_falta(balcao):
    review = _review([*_skus(LINHAS), "FORA"])
    avisos = [w["message"] for w in review.warnings if w["code"] == "item_low_stock"]
    com_falta = {f"P{i:02d}" for i in range(LINHAS) if i % 3 == 1} | {"FORA"}
    assert {msg.split(":", 1)[0] for msg in avisos} == com_falta


# ── O lote responde o MESMO que a pergunta linha a linha ─────────────────────


@pytest.fixture
def vitrine_variada(balcao):
    """Um caso de cada resposta do ``decide``, mais o que muda com a data."""
    from datetime import timedelta

    from shopman.offerman.models import ProductComponent
    from shopman.stockman.models import Hold, HoldStatus

    listing = Listing.objects.get(ref="pdv")
    position = Position.objects.get(ref="loja")
    hoje = date.today()

    def produto(sku, *, listed=True, sellable_in_listing=True, **extra):
        product = Product.objects.create(
            sku=sku, name=sku, base_price_q=900, is_published=True,
            is_sellable=extra.pop("is_sellable", True), **extra,
        )
        if listed:
            ListingItem.objects.create(
                listing=listing, product=product, price_q=900, is_sellable=sellable_in_listing,
            )
        return product

    produto("PAUSADO_NA_VITRINE", sellable_in_listing=False)
    stock.receive(quantity=Decimal("9"), sku="PAUSADO_NA_VITRINE", position=position,
                  target_date=hoje, reason="entrada")
    produto("PAUSADO_NO_CATALOGO", is_sellable=False)
    stock.receive(quantity=Decimal("9"), sku="PAUSADO_NO_CATALOGO", position=position,
                  target_date=hoje, reason="entrada")
    produto("AMANHA")  # só fornada de amanhã
    stock.receive(quantity=Decimal("5"), sku="AMANHA", position=position,
                  target_date=hoje + timedelta(days=1), reason="fornada")
    produto("SEGURADO")  # saldo 4, hold de 3
    quant = stock.receive(quantity=Decimal("4"), sku="SEGURADO", position=position,
                          target_date=hoje, reason="entrada")
    Hold.objects.create(sku="SEGURADO", quant=quant, quantity=Decimal("3"),
                        status=HoldStatus.PENDING, target_date=hoje)
    # Duas faixas de preço do mesmo produto na vitrine.
    faixa = produto("FAIXAS")
    ListingItem.objects.create(listing=listing, product=faixa, price_q=800, min_qty=Decimal("10"))
    stock.receive(quantity=Decimal("2"), sku="FAIXAS", position=position,
                  target_date=hoje, reason="entrada")
    kit = produto("KIT")
    ProductComponent.objects.create(parent=kit, component=Product.objects.get(sku="P00"), qty=Decimal("2"))
    ProductComponent.objects.create(parent=kit, component=Product.objects.get(sku="P01"), qty=Decimal("1"))


CASOS = [
    "P00", "P01", "P02", "FORA", "PAUSADO_NA_VITRINE", "PAUSADO_NO_CATALOGO",
    "AMANHA", "SEGURADO", "FAIXAS", "KIT", "NAO_EXISTE", "P00",
]


@pytest.mark.parametrize("dias", [0, 1])
@pytest.mark.parametrize("qty", ["1", "2", "0.5"])
def test_decide_many_responde_o_mesmo_que_decide(vitrine_variada, dias, qty):
    from datetime import timedelta

    from shopman.shop.services import availability

    alvo = date.today() + timedelta(days=dias)
    linhas = [(sku, Decimal(qty)) for sku in CASOS]
    um_a_um = [availability.decide(sku, q, channel_ref="pdv", target_date=alvo) for sku, q in linhas]
    em_lote = availability.decide_many(linhas, channel_ref="pdv", target_date=alvo)
    assert em_lote == um_a_um


def test_get_prices_responde_o_mesmo_que_get_price(vitrine_variada):
    from shopman.shop.handlers.pricing import OffermanPricingBackend

    backend = OffermanPricingBackend()
    canal = Channel.objects.get(ref="pdv")
    skus = [*CASOS, ""]
    for qty in (Decimal(1), Decimal(10)):
        um_a_um = {sku: backend.get_price(sku, canal, qty=qty) for sku in skus}
        assert backend.get_prices(skus, canal, qty=qty) == um_a_um
