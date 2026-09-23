"""O rename de SKU deixa órfão no cardápio do iFood, e alguém tem de varrer (F5).

O id do item lá é `uuid5(merchant, "item:" + sku)`. Trocar o SKU muda o uuid: o
sync cria um item novo e o antigo fica no cardápio deles, disponível, apontando
para produto que não existe mais aqui.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from shopman.offerman.models import Product

from shopman.shop.management.commands.ifood_retract_renamed_skus import (
    _mapa_de_renames,
    _orfaos_no_ifood,
)

# A cadeia inteira: `BAGUETE` virou `BF`, que virou `TRADI`.
PRIMEIRO_ANTIGO = "BAGUETE"
CODIGO_DE_HOJE = "TRADI"


class BackendFalso:
    def __init__(self):
        self.retirados = None

    def retract(self, skus, *, channel):
        from shopman.offerman.protocols.projection import ProjectionResult

        self.retirados = list(skus)
        return ProjectionResult(success=True, projected=len(skus), channel=channel)


@pytest.fixture
def backend(monkeypatch):
    falso = BackendFalso()
    monkeypatch.setattr(
        "shopman.offerman.conf.get_projection_backend", lambda channel: falso
    )
    return falso


@pytest.mark.django_db
def test_recusa_enquanto_o_sku_antigo_for_o_produto_vivo(backend):
    # Antes do rename, retirar o antigo derrubaria o cardápio que está vendendo.
    Product.objects.create(sku=PRIMEIRO_ANTIGO, name="Vivo", base_price_q=100)

    with pytest.raises(CommandError, match="ainda existem no catálogo"):
        call_command("ifood_retract_renamed_skus", stdout=StringIO())

    assert backend.retirados is None


@pytest.mark.django_db
def test_retira_so_os_pares_que_o_rename_de_fato_trocou(backend):
    Product.objects.create(sku=CODIGO_DE_HOJE, name="Renomeado", base_price_q=100)

    call_command("ifood_retract_renamed_skus", stdout=StringIO())

    # Os DOIS códigos que esse produto já teve, não só o último: cada um deixou
    # um item no cardápio do iFood.
    assert sorted(backend.retirados) == ["BAGUETE", "BF"]


@pytest.mark.django_db
def test_catalogo_intocado_nao_retira_nada(backend):
    # Nenhum código novo no catálogo: o rename não rodou, não há órfão.
    saida = StringIO()
    call_command("ifood_retract_renamed_skus", stdout=saida)

    assert "Nada a retirar" in saida.getvalue()
    assert backend.retirados is None


@pytest.mark.django_db
def test_ensaio_nao_chama_a_api(backend):
    Product.objects.create(sku=CODIGO_DE_HOJE, name="Renomeado", base_price_q=100)

    saida = StringIO()
    call_command("ifood_retract_renamed_skus", "--dry-run", stdout=saida)

    assert PRIMEIRO_ANTIGO in saida.getvalue()
    assert backend.retirados is None


def test_le_os_dois_mapas_de_rename():
    """A leva nova deixa o mesmo tipo de órfão que a antiga, e sem erro nenhum."""
    from config.management.commands.apply_product_skus import RENAMES as CURADOS
    from config.management.commands.rename_skus_to_real import RENAMES as REAIS

    mapa = _mapa_de_renames()
    assert {a for a, _n in REAIS} <= set(mapa)
    assert {a for a, _n in CURADOS} <= set(mapa)


def test_o_codigo_que_voltou_nao_e_retirado():
    """`FENDU` virou `FE` em agosto, e a curadoria de setembro o devolve a `FENDU`.

    Resolver a cadeia no papel daria um ciclo. Quem desempata é o catálogo: o
    código que EXISTE hoje fica, o outro sai.
    """
    mapa = _mapa_de_renames()
    assert mapa["FENDU"] == "FE" and mapa["FE"] == "FENDU"  # o ciclo é real

    orfaos = _orfaos_no_ifood({"FENDU"})

    assert "FE" in orfaos
    assert "FENDU" not in orfaos


@pytest.mark.django_db
def test_o_codigo_que_voltou_nao_trava_o_comando(backend):
    """Medido no alpha em 23/09, depois do rename dar certo.

    `FENDU` é chave do mapa (virou `FE` em agosto) e alvo dele (`FE` voltou a
    `FENDU` agora). Vivo, ele parecia um rename pela metade e travava o comando
    inteiro — depois de um rename que tinha funcionado.
    """
    Product.objects.create(sku="FENDU", name="Fendu", base_price_q=600)

    call_command("ifood_retract_renamed_skus", stdout=StringIO())

    assert backend.retirados is not None
    assert "FE" in backend.retirados       # o código de agosto ficou órfão
    assert "FENDU" not in backend.retirados  # o de hoje é o produto vivo
