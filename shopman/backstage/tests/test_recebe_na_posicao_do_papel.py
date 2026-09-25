"""O Compras recebe pelo papel do SKU: revenda onde se vende, insumo no depósito.

Achado do kit/caixa presente (#1099): tudo entrava na posição PADRÃO do
Stockman, que no Nelson é ``massa`` (WIP da Produção). A geleia recebida
contava como "em produção" e nunca ficava à venda.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone
from shopman.buyman.models import Material, Supplier
from shopman.craftsman.contrib.stockman.handlers import _consume_materials
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderItem
from shopman.offerman.models import Product
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind, Quant
from shopman.stockman.services.availability import availability_for_sku

from shopman.backstage.services import purchase as purchase_service
from shopman.shop.models import Shop
from shopman.shop.services.receiving_position import receiving_position

pytestmark = pytest.mark.django_db

CHAVE = "41260812345678000190550010000012341000123459"
GELEIA = "GELEIA-FIGO-STDALFOUR-284"


@pytest.fixture
def casa(db):
    """As posições do Nelson, com a ``massa`` (WIP) como padrão do Stockman."""
    positions = {}
    for ref, kind, saleable, default in (
        ("deposito", PositionKind.PHYSICAL, False, False),
        ("vitrine", PositionKind.PHYSICAL, True, False),
        ("producao", PositionKind.PHYSICAL, False, False),
        ("massa", PositionKind.PROCESS, False, True),
    ):
        positions[ref] = Position.objects.create(ref=ref, name=ref, kind=kind, is_saleable=saleable, is_default=default)
    Product.objects.create(sku=GELEIA, name="Geleia Figo St. Dalfour 284g", unit="un", base_price_q=4200)
    Material.objects.create(sku=GELEIA, name="Geleia Figo St. Dalfour 284g", unit="un")
    Material.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg")
    fornecedor = Supplier.objects.create(ref="dalfour", name="Importadora", document="12.345.678/0001-90")
    return positions, fornecedor


def _receber(fornecedor, sku, qty):
    purchase_service.confirm_receipt(
        {
            "mode": "invoice", "supplierRef": fornecedor.ref, "invoiceAccessKey": CHAVE, "note": "",
            "lines": [{"id": "l1", "materialSku": sku, "purchaseQty": qty, "costInput": "", "checked": True}],
        },
        user=User.objects.create_user(f"compras-{sku}", password="pw", is_staff=True),
    )


def _saldo(sku, position):
    return sum((q.quantity for q in Quant.objects.filter(sku=sku, position=position)), Decimal("0"))


def test_geleia_recebida_fica_a_venda_na_loja_e_no_pdv(casa):
    positions, fornecedor = casa

    _receber(fornecedor, GELEIA, "6")

    assert _saldo(GELEIA, positions["vitrine"]) == Decimal("6")
    assert _saldo(GELEIA, positions["massa"]) == Decimal("0")
    disponivel = availability_for_sku(GELEIA)
    assert disponivel["available"] == Decimal("6")
    assert disponivel["breakdown"]["in_production"] == Decimal("0")


def test_farinha_recebida_vai_para_o_deposito_nao_vende_e_a_producao_consome(casa):
    positions, fornecedor = casa

    _receber(fornecedor, "FARINHA-T65", "25")

    assert _saldo("FARINHA-T65", positions["deposito"]) == Decimal("25")
    assert availability_for_sku("FARINHA-T65")["available"] == Decimal("0")

    recipe = Recipe.objects.create(ref="pao", name="Pão", output_sku="PAO", batch_size=Decimal("1"))
    work_order = WorkOrder.objects.create(recipe=recipe, output_sku="PAO", quantity=1)
    WorkOrderItem.objects.create(
        work_order=work_order, kind=WorkOrderItem.Kind.CONSUMPTION, item_ref="FARINHA-T65",
        quantity=Decimal("5"), unit="kg", recorded_at=timezone.now(),
    )
    assert _consume_materials(work_order, fail_closed=True) == []
    assert _saldo("FARINHA-T65", positions["deposito"]) == Decimal("20")


def test_a_posicao_e_configuravel_por_papel_e_a_que_contradiz_o_papel_e_ignorada(casa):
    positions, _fornecedor = casa
    Position.objects.create(ref="prateleira", name="Prateleira", kind=PositionKind.PHYSICAL, is_saleable=True)
    Shop.objects.create(name="Loja", defaults={"purchase": {
        "receive_position_resale": "prateleira",
        "receive_position_material": "vitrine",  # vende: não serve para insumo
    }})

    assert receiving_position(GELEIA).ref == "prateleira"
    assert receiving_position("FARINHA-T65").ref == "deposito"


def test_sobra_de_contagem_sem_quant_nasce_onde_o_recebimento_poria(casa):
    from shopman.backstage.services.purchase_count import ResolvedCountLine, _apply_count

    positions, _fornecedor = casa
    _apply_count(
        ResolvedCountLine(material=Material.objects.get(sku=GELEIA), counted=Decimal("3"), reason="achado"),
        user=None,
    )

    assert _saldo(GELEIA, positions["vitrine"]) == Decimal("3")


def test_relocate_leva_a_revenda_guardada_fora_da_venda_para_a_loja(casa):
    positions, _fornecedor = casa
    stock.receive(quantity=Decimal("5"), sku=GELEIA, position=positions["deposito"], reason="seed antigo")
    stock.receive(quantity=Decimal("2"), sku=GELEIA, position=positions["massa"], reason="compra antiga")
    stock.receive(quantity=Decimal("25"), sku="FARINHA-T65", position=positions["deposito"], reason="compra")

    ensaio = StringIO()
    call_command("relocate_resale_stock", stdout=ensaio)
    assert "seriam transferidos" in ensaio.getvalue()
    assert _saldo(GELEIA, positions["vitrine"]) == Decimal("0")

    call_command("relocate_resale_stock", "--apply", stdout=StringIO())

    assert _saldo(GELEIA, positions["vitrine"]) == Decimal("7")
    assert _saldo(GELEIA, positions["deposito"]) + _saldo(GELEIA, positions["massa"]) == Decimal("0")
    assert _saldo("FARINHA-T65", positions["deposito"]) == Decimal("25")  # insumo fica
    assert availability_for_sku(GELEIA)["available"] == Decimal("7")

    segunda = StringIO()
    call_command("relocate_resale_stock", "--apply", stdout=segunda)
    assert "0 saldo(s)" in segunda.getvalue()
