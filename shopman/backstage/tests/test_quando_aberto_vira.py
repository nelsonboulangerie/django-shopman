"""'Quando aberto, vira': a embalagem declara em que insumo se abre, no painel do item.

Sem tela nova e sem botão de abrir: o operador diz o que vem dentro (insumo
aberto, quanto por embalagem, validade depois de aberto) e a produção abre
sozinha no fechamento da fornada (``shop/services/package_opening.py``).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe
from shopman.offerman.models import Product

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services import purchase as purchase_service
from shopman.shop.services.package_opening import opened_name_for, packages_opening_into

pytestmark = pytest.mark.django_db

TABLETE = "MANTEIGA-SAL-PRESIDENT-200"


@pytest.fixture
def tablete(db):
    Product.objects.create(sku=TABLETE, name="Manteiga Extra com Sal Président 200g", unit="un",
                           base_price_q=1500, unit_weight_g=200)
    return Material.objects.create(sku=TABLETE, name="Manteiga Extra com Sal Président 200g", unit="un")


def _item(sku):
    return next(m for m in build_purchase().materials if m.sku == sku)


def test_o_painel_pre_preenche_o_conteudo_pelo_peso_declarado(tablete):
    item = _item(TABLETE)
    assert item.netContentKg == "0.2"
    assert item.opensInto is None


def test_criar_o_aberto_a_partir_da_embalagem(tablete):
    _projection, message = purchase_service.set_opening(
        TABLETE, {"enabled": True, "createOpened": True, "quantity": "0,200", "shelfLifeDays": "30"},
    )

    aberto = Material.objects.get(sku=f"{TABLETE}-ABERTO")
    assert (aberto.name, aberto.unit) == ("Manteiga Extra com Sal Président (aberta)", "kg")
    assert Material.objects.get(sku=TABLETE).metadata["opens_into"] == {
        "sku": aberto.sku, "quantity": "0.200", "shelf_life_days": 30,
    }
    assert [p.sku for p in packages_opening_into(aberto.sku)] == [TABLETE]
    assert "vira Manteiga Extra com Sal Président (aberta)" in message
    vista = _item(TABLETE).opensInto
    assert (vista.name, vista.unit, vista.quantity, vista.shelfLifeDays) == (aberto.name, "kg", "0.200", 30)


def test_escolher_um_insumo_ja_existente(tablete):
    Material.objects.create(sku="MANTEIGA-COM-SAL", name="Manteiga com sal", unit="kg")

    purchase_service.set_opening(TABLETE, {"enabled": True, "openedSku": "MANTEIGA-COM-SAL", "quantity": "0.2"})

    assert Material.objects.get(sku=TABLETE).metadata["opens_into"] == {"sku": "MANTEIGA-COM-SAL", "quantity": "0.2"}


def test_desligar_tira_a_declaracao_e_guarda_o_aberto(tablete):
    purchase_service.set_opening(TABLETE, {"enabled": True, "createOpened": True, "quantity": "0.2"})
    purchase_service.set_opening(TABLETE, {"enabled": False})

    assert "opens_into" not in Material.objects.get(sku=TABLETE).metadata
    assert Material.objects.filter(sku=f"{TABLETE}-ABERTO").exists()


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"createOpened": True, "quantity": ""}, "quantity"),
        ({"createOpened": True, "quantity": "0.2", "shelfLifeDays": "-3"}, "shelfLifeDays"),
        ({"openedSku": "NAO-EXISTE", "quantity": "0.2"}, "openedSku"),
    ],
)
def test_declaracao_torta_volta_com_o_campo_certo(tablete, payload, field):
    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.set_opening(TABLETE, {"enabled": True, **payload})
    assert erro.value.field == field


def test_o_aberto_precisa_ser_pesado_ou_medido_e_a_embalagem_contada(tablete):
    Material.objects.create(sku="OUTRO-UN", name="Outro", unit="un")
    with pytest.raises(purchase_service.PurchaseError):
        purchase_service.set_opening(TABLETE, {"enabled": True, "openedSku": "OUTRO-UN", "quantity": "1"})

    farinha = Material.objects.create(sku="FARINHA", name="Farinha", unit="kg")
    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.set_opening(farinha.sku, {"enabled": True, "createOpened": True, "quantity": "1"})
    assert "só embalagem por unidade se abre" in str(erro.value)


def test_produzido_aqui_nao_e_embalagem(db):
    Material.objects.create(sku="LEVAIN", name="Levain", unit="un")
    Recipe.objects.create(ref="REC-LEVAIN", name="Levain", output_sku="LEVAIN", is_active=True)
    with pytest.raises(purchase_service.PurchaseError):
        purchase_service.set_opening("LEVAIN", {"enabled": True, "createOpened": True, "quantity": "1"})


def test_o_nome_do_aberto_perde_o_tamanho_da_embalagem():
    assert opened_name_for("Geleia Figo St. Dalfour 284g") == "Geleia Figo St. Dalfour (aberta)"
    assert opened_name_for("Azeite Defumado Mirante 250ml") == "Azeite Defumado Mirante (aberta)"
    assert opened_name_for("Manteiga") == "Manteiga (aberta)"


def test_a_api_do_painel(client, tablete):
    user = User.objects.create_user("compras-abre", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing), codename="operate_purchase",
    ))
    client.force_login(user)

    response = client.post(
        reverse("api-backstage-purchase-opening", args=[TABLETE]),
        {"enabled": True, "createOpened": True, "quantity": "0.200", "shelfLifeDays": 30},
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    item = next(m for m in response.json()["purchase"]["materials"] if m["sku"] == TABLETE)
    assert item["opensInto"]["sku"] == f"{TABLETE}-ABERTO"
