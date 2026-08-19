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

from config.management.commands.rename_skus_to_real import RENAMES

PRIMEIRO_ANTIGO, PRIMEIRO_REAL = RENAMES[0]


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
    Product.objects.create(sku=PRIMEIRO_REAL, name="Renomeado", base_price_q=100)

    call_command("ifood_retract_renamed_skus", stdout=StringIO())

    assert backend.retirados == [PRIMEIRO_ANTIGO]


@pytest.mark.django_db
def test_catalogo_intocado_nao_retira_nada(backend):
    # Nenhum código novo no catálogo: o rename não rodou, não há órfão.
    saida = StringIO()
    call_command("ifood_retract_renamed_skus", stdout=saida)

    assert "Nada a retirar" in saida.getvalue()
    assert backend.retirados is None


@pytest.mark.django_db
def test_ensaio_nao_chama_a_api(backend):
    Product.objects.create(sku=PRIMEIRO_REAL, name="Renomeado", base_price_q=100)

    saida = StringIO()
    call_command("ifood_retract_renamed_skus", "--dry-run", stdout=saida)

    assert PRIMEIRO_ANTIGO in saida.getvalue()
    assert backend.retirados is None
