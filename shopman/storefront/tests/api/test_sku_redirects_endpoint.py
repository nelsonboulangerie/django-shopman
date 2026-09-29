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


# ── Lápides: o produto apagado e a prateleira de onde ele saiu ───────────────


def _lapide(sku: str, *collection_refs: str):
    from shopman.shop.services.retired_urls import record

    record(sku=sku, collection_refs=collection_refs)


def _colecao_com_produto(ref: str, nome: str, sku: str):
    from shopman.offerman.models import Collection, CollectionItem

    colecao = Collection.objects.create(ref=ref, name=nome, is_active=True)
    CollectionItem.objects.create(collection=colecao, product=_product(sku))
    return colecao


def test_produto_apagado_sai_com_a_colecao_de_onde_veio(client):
    _colecao_com_produto("doces", "Doces", "MDLN")
    _lapide("PU", "doces")
    gone = client.get("/api/v1/storefront/sku-redirects/").json()["gone"]
    assert gone["PU"] == {"collection": "doces", "collection_name": "Doces"}


def test_oferece_a_primeira_colecao_que_ainda_tem_produto(client):
    """Produto morava em duas vitrines; a que esvaziou não serve de destino."""
    from shopman.offerman.models import Collection

    Collection.objects.create(ref="combos", name="Combos", is_active=True)
    _colecao_com_produto("salgados", "Salgados", "QJQT")
    _lapide("TABUA", "combos", "salgados")
    gone = client.get("/api/v1/storefront/sku-redirects/").json()["gone"]
    assert gone["TABUA"] == {"collection": "salgados", "collection_name": "Salgados"}


def test_colecao_vazia_nao_vira_destino(client):
    """O `COMBO-PETIT-DEJ` era o único de "Combos": a prateleira ficou vazia."""
    from shopman.offerman.models import Collection

    Collection.objects.create(ref="combos", name="Combos", is_active=True)
    _lapide("COMBO-PETIT-DEJ", "combos")
    gone = client.get("/api/v1/storefront/sku-redirects/").json()["gone"]
    assert gone["COMBO-PETIT-DEJ"] == {"collection": "", "collection_name": ""}


def test_produto_que_voltou_a_existir_perde_a_lapide(client):
    """Lápide de quem está vivo mentiria: a página dele responde."""
    _product("PU")
    _lapide("PU", "doces")
    gone = client.get("/api/v1/storefront/sku-redirects/").json()["gone"]
    assert "PU" not in gone


def test_codigo_que_renasceu_fora_da_vitrine_nao_diz_que_nao_existe(client):
    """Renascer despublicado é existir: 410 diria "não volta" sobre algo que voltou.

    O `GL` sai hoje e volta como duas geleias; se alguém reaproveitar o código,
    a resposta certa volta a ser o 404, que é reversível.
    """
    produto = _product("GL")
    produto.is_published = False
    produto.save()
    _lapide("GL", "mercearia")
    gone = client.get("/api/v1/storefront/sku-redirects/").json()["gone"]
    assert "GL" not in gone
