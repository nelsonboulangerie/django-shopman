"""O pedido de compra fecha na entrega: enviar → receber → poder pedir de novo.

Achado da auditoria de UX de 03/10/2026: depois do primeiro "Enviar pedido" o
botão ficava "Enviado" para sempre. `purchase.request_status = "sent"` era
escrito e nada o apagava — nem o recebimento — e o insumo nunca mais podia ser
pedido pela tela.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from shopman.buyman.models import Material, MaterialConversion, Supplier, SupplierMaterialCost
from shopman.orderman.models import Directive
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services.purchase import (
    PurchaseError,
    cancel_purchase_request,
    confirm_receipt,
    send_purchase_request,
)
from shopman.shop.directives import NOTIFICATION_SEND


@pytest.fixture
def operador(db):
    return User.objects.create_user("compras-op", password="pw", is_staff=True)


@pytest.fixture
def cenario(db):
    # A sugestão de reposição só existe com posição padrão; o pedido depende dela.
    Position.objects.get_or_create(
        ref="deposito",
        defaults={"name": "Depósito", "kind": PositionKind.PHYSICAL, "is_default": True},
    )
    fornecedor = Supplier.objects.create(
        ref="moinho-sp", name="Moinho São Paulo", email="pedidos@moinho.example"
    )
    material = Material.objects.create(
        sku="FAR-T65",
        name="Farinha T65",
        unit="kg",
        metadata={"purchase": {"min_stock": "100", "category": "Farinhas"}},
    )
    conversao = MaterialConversion.objects.create(
        material=material, supplier=fornecedor, label="saco 25 kg", to_base_factor=Decimal("25")
    )
    SupplierMaterialCost.objects.create(
        material=material, supplier=fornecedor, conversion=conversao, cost_q=18000, is_preferred=True
    )
    return material, fornecedor, conversao


def _recebe(cenario, operador, *, sacos=1, note="entrega da manhã"):
    material, fornecedor, conversao = cenario
    confirm_receipt(
        {
            "mode": "manual",
            "supplierRef": fornecedor.ref,
            "note": note,
            "lines": [
                {
                    "id": "l1",
                    "materialSku": material.sku,
                    "conversionId": str(conversao.pk),
                    "purchaseQty": sacos,
                    "costInput": "180,00",
                    "checked": True,
                }
            ],
        },
        user=operador,
    )


def _status(material) -> str:
    return build_purchase().purchaseRequestStatuses.get(material.sku, "review")


def _pedidos() -> int:
    return Directive.objects.filter(topic=NOTIFICATION_SEND, payload__event="purchase_request").count()


@pytest.mark.django_db
def test_enviar_receber_e_poder_pedir_de_novo(cenario, operador):
    material, _f, _c = cenario

    send_purchase_request(material.sku, user=operador)
    assert _status(material) == "sent"

    # Chegou só um saco: o insumo ainda está abaixo do mínimo e volta a pedir.
    _recebe(cenario, operador, sacos=1)

    material.refresh_from_db()
    assert _status(material) == "review"
    assert not [key for key in material.metadata["purchase"] if key.startswith("request_")], (
        "pedido encerrado deixou resto no metadata"
    )
    # O que não é do pedido fica onde estava.
    assert material.metadata["purchase"]["min_stock"] == "100"
    assert material.metadata["purchase"]["category"] == "Farinhas"

    Directive.objects.filter(topic=NOTIFICATION_SEND).update(status="done")
    send_purchase_request(material.sku, user=operador)

    assert _status(material) == "sent"
    assert _pedidos() == 2


@pytest.mark.django_db
def test_pedido_em_aberto_nao_sai_duas_vezes(cenario, operador):
    material, _f, _c = cenario
    send_purchase_request(material.sku, user=operador)

    with pytest.raises(PurchaseError) as recusa:
        send_purchase_request(material.sku, user=operador)

    assert recusa.value.code == "purchase_request_open"
    assert recusa.value.status_code == 409
    assert _pedidos() == 1


@pytest.mark.django_db
def test_cancelar_libera_o_insumo_para_pedir_de_novo(cenario, operador):
    material, _f, _c = cenario
    send_purchase_request(material.sku, user=operador)

    cancel_purchase_request(material.sku)

    material.refresh_from_db()
    assert _status(material) == "review"
    assert not [key for key in material.metadata["purchase"] if key.startswith("request_")]

    Directive.objects.filter(topic=NOTIFICATION_SEND).update(status="done")
    send_purchase_request(material.sku, user=operador)
    assert _status(material) == "sent"


@pytest.mark.django_db
def test_cancelar_sem_pedido_em_aberto_nao_mexe_em_nada(cenario):
    material, _f, _c = cenario
    antes = material.updated_at

    cancel_purchase_request(material.sku)

    material.refresh_from_db()
    assert material.updated_at == antes
    assert _status(material) == "review"
