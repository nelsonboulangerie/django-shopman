"""Estoque mínimo: a outra metade que faltava para existir uma solicitação.

`dailyUse` não é digitado nem calculado por job — sai das baixas de estoque que
a produção lança ao FINALIZAR uma ficha (`Move` negativo, `kind=MAKE`), lidas na
janela da política. Enquanto a fornada não roda no sistema, o consumo é zero.

E aí o cálculo fecha o círculo contra o operador: sem consumo, o `min_stock`
também cai para zero (`daily_use * replenish_at if daily_use > 0 else 0`), o
alvo de reposição vira zero, e `suggestedQty` é zero para SEMPRE. Cadastrar
custo e fornecedor não muda isso — o insumo continua invisível para o Compras.

O mínimo declarado é a saída: com ele, o alvo existe mesmo sem histórico, e o
insumo volta a poder virar pedido.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.apps import apps

from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services import purchase as purchase_service
from shopman.backstage.services.purchase import PurchaseError


@pytest.fixture
def material(db):
    Material = apps.get_model("buyman", "Material")
    return Material.objects.create(sku="ALECRIM", name="Alecrim", unit="g")


def _projected(sku: str):
    return next(row for row in build_purchase().materials if row.sku == sku)


@pytest.mark.django_db
def test_sem_consumo_e_sem_minimo_o_insumo_nunca_e_sugerido(material):
    """O estado de 56 dos 57 insumos: inerte por construção."""
    projected = _projected("ALECRIM")
    assert projected.dailyUse == 0
    assert projected.minStock == 0
    assert projected.suggestedQty == 0


@pytest.mark.django_db
def test_minimo_declarado_faz_o_insumo_virar_sugestao(material):
    purchase_service.set_min_stock({"minimums": [{"materialSku": "ALECRIM", "minStock": "500"}]})

    projected = _projected("ALECRIM")
    assert projected.minStock == 500
    # Sem estoque em mãos, a sugestão é o mínimo inteiro.
    assert projected.suggestedQty == 500


@pytest.mark.django_db
def test_grava_no_bloco_purchase_sem_pisar_no_resto_do_metadata(material):
    material.metadata = {"purchase": {"category": "Temperos"}, "outro": "fica"}
    material.save()

    purchase_service.set_min_stock({"minimums": [{"materialSku": "ALECRIM", "minStock": "500"}]})

    material.refresh_from_db()
    assert material.metadata["outro"] == "fica"
    assert material.metadata["purchase"]["category"] == "Temperos"
    assert Decimal(str(material.metadata["purchase"]["min_stock"])) == Decimal("500")


@pytest.mark.django_db
def test_aceita_o_teclado_da_casa(material):
    purchase_service.set_min_stock({"minimums": [{"materialSku": "ALECRIM", "minStock": "1.250,5"}]})
    assert _projected("ALECRIM").minStock == pytest.approx(1250.5)


@pytest.mark.django_db
def test_zero_apaga_o_minimo_declarado(material):
    purchase_service.set_min_stock({"minimums": [{"materialSku": "ALECRIM", "minStock": "500"}]})
    purchase_service.set_min_stock({"minimums": [{"materialSku": "ALECRIM", "minStock": "0"}]})

    material.refresh_from_db()
    # Apagar é remover a chave, não gravar zero: zero gravado e "sem mínimo"
    # levam ao mesmo alvo, mas só um deles volta a seguir o consumo quando a
    # produção começar a rodar.
    assert "min_stock" not in material.metadata.get("purchase", {})


@pytest.mark.django_db
def test_linha_em_branco_e_ignorada(material):
    result = purchase_service.set_min_stock(
        {"minimums": [{"materialSku": "ALECRIM", "minStock": "500"}, {"materialSku": "ALECRIM", "minStock": ""}]}
    )
    assert result["saved"] == 1


@pytest.mark.django_db
def test_insumo_desconhecido_derruba_o_lote_apontando_a_linha(material):
    with pytest.raises(PurchaseError) as excinfo:
        purchase_service.set_min_stock(
            {
                "minimums": [
                    {"materialSku": "ALECRIM", "minStock": "500"},
                    {"materialSku": "NAO-EXISTE", "minStock": "10"},
                ]
            }
        )

    assert excinfo.value.code == "min_stock_batch_invalid"
    assert excinfo.value.lines[0]["index"] == 1
    material.refresh_from_db()
    assert "min_stock" not in material.metadata.get("purchase", {})


@pytest.mark.django_db
def test_minimo_negativo_e_recusado(material):
    with pytest.raises(PurchaseError) as excinfo:
        purchase_service.set_min_stock({"minimums": [{"materialSku": "ALECRIM", "minStock": "-5"}]})
    assert excinfo.value.lines[0]["field"] == "minStock"
