"""O mapa que a loja usa para dar 301 numa URL de produto aposentada."""

from __future__ import annotations

import pytest
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db


def _product(sku: str) -> Product:
    return Product.objects.create(sku=sku, name=sku, unit="un", base_price_q=1000)


def test_lista_o_codigo_aposentado_e_o_de_hoje(client):
    """`CROISSANT` virou `CT` em agosto e `CT` virou `CRO` em setembro.

    Os dois endereços antigos apontam para o produto de hoje — o do meio
    inclusive, que é o que o Google tinha indexado.
    """
    _product("CRO")
    redirects = client.get("/api/v1/storefront/sku-redirects/").json()["redirects"]
    assert redirects["CT"] == "CRO"
    assert redirects["CROISSANT"] == "CRO"


def test_omite_o_codigo_que_nao_chega_a_produto_vivo(client):
    """Sem produto no destino não há 301 honesto: melhor o 404 do que outro 404."""
    redirects = client.get("/api/v1/storefront/sku-redirects/").json()["redirects"]
    assert "CT" not in redirects


def test_nao_devolve_o_codigo_que_voltou_a_ser_usado(client):
    """`FENDU` virou `FE` em agosto e `FE` voltou a `FENDU` hoje.

    Redirecionar `FENDU` mandaria a página boa para um 404.
    """
    _product("FENDU")
    redirects = client.get("/api/v1/storefront/sku-redirects/").json()["redirects"]
    assert "FENDU" not in redirects
    assert redirects.get("FE") == "FENDU"


def test_e_publico_e_pede_cache_curto(client):
    resp = client.get("/api/v1/storefront/sku-redirects/")
    assert resp.status_code == 200
    assert resp["Cache-Control"] == "public, max-age=300"


def test_nao_manda_para_produto_despublicado(client):
    """Despublicado continua no catálogo e some da loja: 301 para ele é 301 para 404.

    `MINI-BAGUETE` virou `MIB` em agosto, e o `MIB` saiu da vitrine em 23/09 —
    fica para a encomenda do restaurante, então pode voltar. Até lá não há
    destino: nem o código antigo nem ele mesmo entram no mapa.
    """
    produto = _product("MIB")
    produto.is_published = False
    produto.save()
    redirects = client.get("/api/v1/storefront/sku-redirects/").json()["redirects"]
    assert "MINI-BAGUETE" not in redirects
    assert "MIB" not in redirects


def test_manda_para_o_produto_publicado(client):
    """O mesmo código, publicado, é destino legítimo."""
    _product("MIB")
    redirects = client.get("/api/v1/storefront/sku-redirects/").json()["redirects"]
    assert redirects["MINI-BAGUETE"] == "MIB"
