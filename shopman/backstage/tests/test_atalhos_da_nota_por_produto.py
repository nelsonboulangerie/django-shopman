"""Os atalhos da nota da cozinha valem para os produtos do pedido (decisão do dono, 21/11/2026).

Cada atalho diz a que categorias e produtos se aplica; sem nenhum, vale para todos. O
detalhe do pedido no Gestor mostra só os que valem para algum item dele: "Sem cebola"
num pedido de pão não aparece.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from shopman.offerman.models import Collection, CollectionItem, Product
from shopman.orderman.models import Order

from shopman.backstage.projections.order_queue import _kitchen_note_tags
from shopman.shop.models import KitchenNoteTag, Shop

pytestmark = pytest.mark.django_db


def _product(sku: str, collection: Collection) -> Product:
    product = Product.objects.create(sku=sku, name=sku.title(), base_price_q=1000)
    CollectionItem.objects.create(collection=collection, product=product)
    return product


def _order(ref: str, *skus: str) -> Order:
    order = Order.objects.create(ref=ref, channel_ref="web", session_key=f"s-{ref}", status="accepted", total_q=1000)
    for i, sku in enumerate(skus, start=1):
        order.items.create(line_id=f"L{i}", sku=sku, name=sku, qty=Decimal("1"), unit_price_q=1000, line_total_q=1000)
    return order


@pytest.fixture
def casa():
    paes = Collection.objects.create(ref="rusticos", name="Rústicos")
    lanches = Collection.objects.create(ref="salgados", name="Salgados")
    _product("BAGUETE", paes)
    _product("HOTDOG", lanches)
    _product("CHA", Collection.objects.create(ref="bebidas", name="Bebidas"))
    bem_assado = KitchenNoteTag.objects.create(label="Bem assado", position=0)
    bem_assado.collections.add(paes)
    sem_cebola = KitchenNoteTag.objects.create(label="Sem cebola", position=1)
    sem_cebola.collections.add(lanches)
    KitchenNoteTag.objects.create(label="Embalar para presente", position=2)
    so_cha = KitchenNoteTag.objects.create(label="Sem açúcar", position=3)
    so_cha.products.add(Product.objects.get(sku="CHA"))


def test_pedido_de_pao_nao_oferece_sem_cebola(casa):
    assert _kitchen_note_tags(_order("P-PAO", "BAGUETE")) == ("Bem assado", "Embalar para presente")


def test_pedido_misto_oferece_o_que_vale_para_algum_item(casa):
    assert _kitchen_note_tags(_order("P-MISTO", "BAGUETE", "HOTDOG", "CHA")) == (
        "Bem assado",
        "Sem cebola",
        "Embalar para presente",
        "Sem açúcar",
    )


def test_atalho_sem_categoria_nem_produto_vale_para_todo_pedido(casa):
    assert _kitchen_note_tags(_order("P-CHA", "CHA")) == ("Embalar para presente", "Sem açúcar")


def test_o_admin_dos_atalhos_abre_e_diz_para_que_vale(casa, client):
    Shop.objects.create(name="Casa")
    admin = get_user_model().objects.create_superuser("dona", password="x", email="dona@example.com")
    client.force_login(admin)

    lista = client.get("/admin/shop/kitchennotetag/")
    assert lista.status_code == 200
    assert "Rústicos" in lista.content.decode()
    assert "Todos os pedidos" in lista.content.decode()
    tag = KitchenNoteTag.objects.get(label="Sem cebola")
    assert client.get(f"/admin/shop/kitchennotetag/{tag.pk}/change/").status_code == 200
