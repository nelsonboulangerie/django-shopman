"""Comprável e vendável: um gesto em cada sentido.

Decisão do dono (24/09/2026): comprável é ter cadastro no Compras; vendável é
decisão explícita. Um item comprado pode ser insumo E revenda, e tornar
vendável tem de ser um gesto só:

- no Compras, "Permitir revenda" pede SÓ o preço e cria o cadastro de venda do
  mesmo SKU, que entra no PDV (canal remoto só com foto);
- no Catálogo, "Permitir compra" cria o cadastro de compra do mesmo SKU —
  e recusa o que tem ficha ativa ("é produzido aqui").

Desligar nunca apaga: pausa e deslista a venda, inativa a compra.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman import get_social_attributes
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.models import DayClosing
from shopman.backstage.services import purchase as purchase_service
from shopman.shop.services.sku_records import sku_roles

pytestmark = pytest.mark.django_db


def _perm(model, codename):
    return Permission.objects.get(content_type=ContentType.objects.get_for_model(model), codename=codename)


@pytest.fixture
def listings(db):
    return {ref: Listing.objects.create(ref=ref, name=ref.upper()) for ref in ("pdv", "web", "ifood")}


@pytest.fixture
def geleia(db):
    return Material.objects.create(
        sku="GELEIA-FIGO-STDALFOUR-284", name="Geleia Figo St. Dalfour 284g", unit="un",
        shelf_life_days=365, metadata={"brand": "St. Dalfour", "gtin": "084380959042", "ncm": "20079910"},
    )


@pytest.fixture
def gestor(db):
    from shopman.shop.models import Shop

    user = User.objects.create_user("gestor-compras", password="pw", is_staff=True)
    user.user_permissions.add(
        _perm(DayClosing, "operate_purchase"),
        Permission.objects.get(content_type__app_label="shop", content_type__model="shop", codename="manage_catalog"),
    )
    Shop.objects.get_or_create(name="Loja")
    return user


def _listed(product):
    return set(
        ListingItem.objects.filter(product=product, is_published=True, is_sellable=True)
        .values_list("listing__ref", flat=True)
    )


class TestVenderTambem:
    def test_ligar_cria_o_cadastro_de_venda_do_mesmo_sku_e_so_no_pdv(self, listings, geleia):
        purchase_service.set_sale(geleia.sku, {"enabled": True, "priceInput": "42,00"})

        product = Product.objects.get(sku=geleia.sku)
        assert (product.name, product.unit, product.shelf_life_days) == (geleia.name, "un", 365)
        assert product.base_price_q == 4200
        assert product.is_sellable and not product.is_published
        social = get_social_attributes(product)
        assert (social.brand, social.gtin) == ("St. Dalfour", "084380959042")
        assert product.metadata["fiscal"]["ncm"] == "20079910"
        # Sem foto não entra em canal onde o cliente decide pela imagem.
        assert _listed(product) == {"pdv"}
        assert ListingItem.objects.get(product=product).price_q == 4200
        roles = sku_roles(geleia.sku)
        assert roles.purchasable and roles.sellable and not roles.produced

    def test_com_foto_vai_tambem_para_os_canais_remotos(self, listings, geleia):
        geleia.metadata = {**geleia.metadata, "image_url": "https://img.example.com/geleia.jpg"}
        geleia.save()

        purchase_service.set_sale(geleia.sku, {"enabled": True, "priceInput": "42"})

        assert _listed(Product.objects.get(sku=geleia.sku)) == {"pdv", "web", "ifood"}

    def test_ligar_sem_preco_e_recusado(self, listings, geleia):
        with pytest.raises(purchase_service.PurchaseError) as erro:
            purchase_service.set_sale(geleia.sku, {"enabled": True, "priceInput": ""})

        assert erro.value.field == "priceInput"
        assert not Product.objects.filter(sku=geleia.sku).exists()

    def test_desligar_pausa_e_deslista_sem_apagar(self, listings, geleia):
        purchase_service.set_sale(geleia.sku, {"enabled": True, "priceInput": "42"})
        purchase_service.set_sale(geleia.sku, {"enabled": False})

        product = Product.objects.get(sku=geleia.sku)
        assert not product.is_sellable
        assert ListingItem.objects.filter(product=product).exists()
        assert _listed(product) == set()
        assert not sku_roles(geleia.sku).sellable
        assert Material.objects.get(sku=geleia.sku).is_active  # compra continua

    def test_religar_volta_ao_pdv_com_o_preco_novo(self, listings, geleia):
        purchase_service.set_sale(geleia.sku, {"enabled": True, "priceInput": "42"})
        purchase_service.set_sale(geleia.sku, {"enabled": False})
        purchase_service.set_sale(geleia.sku, {"enabled": True, "priceInput": "45,00"})

        product = Product.objects.get(sku=geleia.sku)
        assert product.is_sellable and product.base_price_q == 4500
        assert _listed(product) == {"pdv"}
        assert ListingItem.objects.get(product=product).price_q == 4500

    def test_produzido_aqui_nao_nasce_do_compras(self, listings):
        levain = Material.objects.create(sku="LEVAIN-LIQUIDO", name="Levain", unit="kg")
        Recipe.objects.create(ref="REC-LEVAIN", name="Levain", output_sku=levain.sku, is_active=True)

        with pytest.raises(purchase_service.PurchaseError) as erro:
            purchase_service.set_sale(levain.sku, {"enabled": True, "priceInput": "10"})

        assert "produzido aqui" in str(erro.value)

    def test_a_projecao_do_compras_mostra_os_selos_e_o_preco(self, listings, geleia):
        purchase_service.set_sale(geleia.sku, {"enabled": True, "priceInput": "42"})

        from shopman.backstage.projections.purchase import build_purchase

        item = next(m for m in build_purchase().materials if m.sku == geleia.sku)
        assert item.roles.purchasable and item.roles.sellable
        assert item.salePriceQ == 4200
        assert item.category == "Revenda"

    def test_api_exige_operar_compras_e_gerir_catalogo(self, client, listings, geleia, gestor):
        so_compras = User.objects.create_user("so-compras", password="pw", is_staff=True)
        so_compras.user_permissions.add(_perm(DayClosing, "operate_purchase"))
        url = reverse("api-backstage-purchase-sale", args=[geleia.sku])

        client.force_login(so_compras)
        assert client.post(url, {"enabled": True, "priceInput": "42"}, content_type="application/json").status_code == 403

        client.force_login(gestor)
        response = client.post(url, {"enabled": True, "priceInput": "42"}, content_type="application/json")
        assert response.status_code == 200, response.json()
        item = next(m for m in response.json()["purchase"]["materials"] if m["sku"] == geleia.sku)
        assert item["roles"]["sellable"] is True
        assert item["salePriceQ"] == 4200


class TestCompradoPronto:
    def test_ligar_cria_o_cadastro_de_compra_na_mesma_unidade(self, client, gestor):
        queijo = Product.objects.create(sku="QUEIJO-GRUYERE-KG", name="Gruyère", unit="kg", base_price_q=24900)
        client.force_login(gestor)

        response = client.post(
            reverse("api-backstage-catalog-product-purchase", args=[queijo.sku]),
            {"enabled": True}, content_type="application/json",
        )

        assert response.status_code == 200, response.json()
        assert response.json()["product"]["roles"]["purchasable"] is True
        material = Material.objects.get(sku=queijo.sku)
        assert (material.name, material.unit, material.is_active) == ("Gruyère", "kg", True)

    def test_produzido_aqui_e_recusado_com_mensagem_clara(self, client, gestor):
        croissant = Product.objects.create(sku="CRO", name="Croissant", unit="un", base_price_q=1300)
        Recipe.objects.create(ref="REC-CRO", name="Croissant", output_sku="CRO", is_active=True)
        client.force_login(gestor)

        response = client.post(
            reverse("api-backstage-catalog-product-purchase", args=[croissant.sku]),
            {"enabled": True}, content_type="application/json",
        )

        assert response.status_code == 400
        assert "é produzido aqui" in response.json()["detail"]
        assert not Material.objects.filter(sku="CRO").exists()

    def test_desligar_inativa_sem_apagar(self, client, gestor):
        cha = Product.objects.create(sku="CHA-MAMA-KANFA-P50", name="Chá Mamã", unit="un", base_price_q=7300)
        Material.objects.create(sku=cha.sku, name=cha.name, unit="un")
        client.force_login(gestor)

        response = client.post(
            reverse("api-backstage-catalog-product-purchase", args=[cha.sku]),
            {"enabled": False}, content_type="application/json",
        )

        assert response.status_code == 200
        assert Material.objects.get(sku=cha.sku).is_active is False
        assert response.json()["product"]["roles"]["purchasable"] is False

    def test_os_selos_de_usado_em_receita_e_produzido(self, gestor):
        Material.objects.create(sku="MANTEIGA-SAL-PRESIDENT-200", name="Manteiga", unit="un")
        Product.objects.create(sku="MANTEIGA-SAL-PRESIDENT-200", name="Manteiga", unit="un", base_price_q=1500)
        receita = Recipe.objects.create(ref="REC-CRO2", name="Croissant", output_sku="CRO2", is_active=True)
        RecipeItem.objects.create(recipe=receita, input_sku="MANTEIGA-SAL-PRESIDENT-200", quantity=1, unit="un")

        manteiga = sku_roles("MANTEIGA-SAL-PRESIDENT-200")
        assert manteiga.purchasable and manteiga.sellable and manteiga.used_in_recipe
        assert not manteiga.produced
        assert sku_roles("CRO2").produced


def _patch_detail(client, sku, payload):
    from uuid import uuid4

    url = f"/api/v1/backstage/catalog/product/{sku}/"
    action = client.get(url).json()["action"]
    return client.patch(url, {**action["payload_schema"], "patch": payload},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))


class TestVendidoPorPeso:
    """Vendido por peso (unidade kg) é só no balcão: o preço final sai da balança."""

    def test_permitir_revenda_de_item_por_quilo_fica_so_no_pdv_mesmo_com_foto(self, listings):
        queijo = Material.objects.create(
            sku="QUEIJO-GRUYERE-KG", name="Gruyère", unit="kg",
            metadata={"image_url": "https://img.example.com/gruyere.jpg"},
        )

        _projection, message = purchase_service.set_sale(queijo.sku, {"enabled": True, "priceInput": "149,90"})

        product = Product.objects.get(sku=queijo.sku)
        assert product.unit == "kg" and product.base_price_q == 14990
        assert _listed(product) == {"pdv"}
        assert "só no balcão" in message

    def test_virar_vendido_por_peso_no_catalogo_tira_dos_canais_remotos(self, client, listings, gestor):
        queijo = Product.objects.create(
            sku="QUEIJO-BRIE", name="Brie", unit="un", base_price_q=4000, image_url="https://img.example.com/brie.jpg",
        )
        for listing in listings.values():
            ListingItem.objects.create(listing=listing, product=queijo, price_q=4000)
        client.force_login(gestor)

        response = _patch_detail(client, queijo.sku, {"unit": "kg", "base_price_q": 16000})

        assert response.status_code == 200, response.json()
        assert set(ListingItem.objects.filter(product=queijo).values_list("listing__ref", flat=True)) == {"pdv"}

    def test_unidade_que_desmente_o_cadastro_de_compra_volta_com_a_mensagem_do_porteiro(self, client, gestor):
        manteiga = Product.objects.create(sku="MANTEIGA-200", name="Manteiga 200g", unit="un", base_price_q=1500)
        Material.objects.create(sku=manteiga.sku, name=manteiga.name, unit="un")
        client.force_login(gestor)

        response = _patch_detail(client, manteiga.sku, {"unit": "kg"})

        assert response.status_code == 400
        assert "cadastro de compra" in response.json()["detail"]
        assert Product.objects.get(sku=manteiga.sku).unit == "un"
