"""Receber com preço diferente não troca o custo preferencial em silêncio.

Beta test 05/11/2026, achado CMP-06; decisão do dono em 06/11: o recebimento
gravava o preço pago no custo do fornecedor, e quando esse custo era o
preferencial do insumo, o custo que alimenta custeio, sugestão de preço e pedido
de compra mudava sem ninguém ter escolhido. Agora a entrada pergunta: troca ou
mantém. Sem resposta, o servidor recusa (a tela pergunta antes).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from shopman.buyman.models import Material, MaterialConversion, Supplier, SupplierMaterialCost
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.services.purchase import PurchaseError, confirm_receipt


@pytest.fixture
def operador(db):
    return User.objects.create_user("recebe-op", password="pw", is_staff=True)


@pytest.fixture
def cenario(db):
    Position.objects.get_or_create(
        ref="deposito",
        defaults={"name": "Depósito", "kind": PositionKind.PHYSICAL, "is_default": True},
    )
    fornecedor = Supplier.objects.create(ref="moinho-sp", name="Moinho São Paulo")
    material = Material.objects.create(sku="FAR-T65", name="Farinha T65", unit="kg")
    saco = MaterialConversion.objects.create(
        material=material, supplier=fornecedor, label="saco 25 kg", to_base_factor=Decimal("25")
    )
    custo = SupplierMaterialCost.objects.create(
        material=material, supplier=fornecedor, conversion=saco, cost_q=18000, is_preferred=True
    )
    return material, fornecedor, saco, custo


def _recebe(cenario, operador, *, custo: str, sacos: int = 1, conversion=None, **linha):
    material, fornecedor, saco, _ = cenario
    conversion = conversion or saco
    confirm_receipt(
        {
            "mode": "manual",
            "supplierRef": fornecedor.ref,
            "note": f"entrega {custo} {sacos} {linha}",
            "lines": [
                {
                    "id": "l1",
                    "materialSku": material.sku,
                    "conversionId": str(conversion.pk),
                    "purchaseQty": sacos,
                    "costInput": custo,
                    "checked": True,
                    **linha,
                }
            ],
        },
        user=operador,
    )


@pytest.mark.django_db
def test_preco_diferente_sem_resposta_e_recusado(cenario, operador):
    _material, _f, _s, custo = cenario

    with pytest.raises(PurchaseError) as exc:
        _recebe(cenario, operador, custo="198,00")

    assert exc.value.code == "preferred_cost_decision_required"
    assert exc.value.field == "lines.0.preferredCost"
    custo.refresh_from_db()
    assert custo.cost_q == 18000


@pytest.mark.django_db
def test_manter_deixa_o_custo_preferencial_como_estava(cenario, operador):
    _material, _f, _s, custo = cenario

    _recebe(cenario, operador, custo="198,00", preferredCost="keep")

    custo.refresh_from_db()
    assert custo.cost_q == 18000
    assert custo.is_preferred is True


@pytest.mark.django_db
def test_atualizar_troca_o_custo_preferencial(cenario, operador):
    _material, _f, _s, custo = cenario

    _recebe(cenario, operador, custo="198,00", preferredCost="update")

    custo.refresh_from_db()
    assert custo.cost_q == 19800
    assert custo.is_preferred is True


@pytest.mark.django_db
def test_mesmo_preco_nao_pergunta(cenario, operador):
    _material, _f, _s, custo = cenario

    # Dois sacos a R$ 360,00 é o mesmo R$ 180,00 por saco.
    _recebe(cenario, operador, custo="360,00", sacos=2)

    custo.refresh_from_db()
    assert custo.cost_q == 18000


@pytest.mark.django_db
def test_mesmo_preco_em_outra_embalagem_nao_pergunta(cenario, operador):
    material, fornecedor, _s, custo = cenario
    quilo = MaterialConversion.objects.create(
        material=material, supplier=fornecedor, label="pacote 1 kg", to_base_factor=Decimal("1")
    )

    # 25 pacotes de 1 kg por R$ 180,00 é o saco de 25 kg pelo mesmo preço.
    _recebe(cenario, operador, custo="180,00", sacos=25, conversion=quilo)

    # Nada muda no custo preferencial: nem o valor, nem a embalagem em que o
    # pedido de compra é feito.
    custo.refresh_from_db()
    assert custo.cost_q == 18000
    assert custo.conversion_id == _s.pk
    assert custo.is_preferred is True


@pytest.mark.django_db
def test_atualizar_em_outra_embalagem_grava_o_valor_que_a_pergunta_mostrou(cenario, operador):
    material, fornecedor, saco, custo = cenario
    quilo = MaterialConversion.objects.create(
        material=material, supplier=fornecedor, label="pacote 1 kg", to_base_factor=Decimal("1")
    )

    # 25 pacotes de 1 kg por R$ 198,00: a pergunta diz "Atualizar para R$ 198,00"
    # no saco de 25 kg, e é isso que fica gravado.
    _recebe(cenario, operador, custo="198,00", sacos=25, conversion=quilo, preferredCost="update")

    custo.refresh_from_db()
    assert custo.cost_q == 19800
    assert custo.conversion_id == saco.pk
    assert custo.is_preferred is True


@pytest.mark.django_db
def test_outra_embalagem_com_preco_diferente_sem_resposta_e_recusada(cenario, operador):
    material, fornecedor, _s, custo = cenario
    quilo = MaterialConversion.objects.create(
        material=material, supplier=fornecedor, label="pacote 1 kg", to_base_factor=Decimal("1")
    )

    with pytest.raises(PurchaseError) as exc:
        _recebe(cenario, operador, custo="198,00", sacos=25, conversion=quilo)

    assert exc.value.code == "preferred_cost_decision_required"
    custo.refresh_from_db()
    assert (custo.cost_q, custo.conversion_id) == (18000, _s.pk)


@pytest.mark.django_db
def test_primeiro_custo_do_insumo_nao_pergunta(operador, db):
    Position.objects.get_or_create(
        ref="deposito",
        defaults={"name": "Depósito", "kind": PositionKind.PHYSICAL, "is_default": True},
    )
    fornecedor = Supplier.objects.create(ref="laticinio", name="Laticínio")
    material = Material.objects.create(sku="MANT", name="Manteiga", unit="kg")

    confirm_receipt(
        {
            "mode": "manual",
            "supplierRef": fornecedor.ref,
            "note": "primeira entrega",
            "lines": [{"id": "l1", "materialSku": material.sku, "purchaseQty": 2, "costInput": "90,00", "checked": True}],
        },
        user=operador,
    )

    custo = SupplierMaterialCost.objects.get(material=material, supplier=fornecedor)
    assert custo.cost_q == 4500
    assert custo.is_preferred is True


@pytest.mark.django_db
def test_resposta_invalida_e_recusada(cenario, operador):
    with pytest.raises(PurchaseError) as exc:
        _recebe(cenario, operador, custo="198,00", preferredCost="talvez")

    assert exc.value.code == "preferred_cost_decision_invalid"
