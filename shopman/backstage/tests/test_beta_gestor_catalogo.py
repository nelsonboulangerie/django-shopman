"""Beta de 05/11/2026, frente Gestor/Catálogo/Clientes: um teste por achado.

O id do achado (``GES-01``, ``CMP-08``…) está no nome de cada teste. Cada um
trava a CAUSA que o beta achou, não o sintoma da tela.
"""

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.guestman.models import Customer, PriceTier
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

from shopman.backstage.services import catalog as catalog_service
from shopman.backstage.services.exceptions import CatalogError
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

CUSTOMERS_URL = "/api/v1/backstage/customers/"


def _perm(codename: str) -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename=codename,
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def manager(shop):
    user = User.objects.create_user("gerente-beta", password="pw", is_staff=True)
    user.user_permissions.add(_perm("manage_customers"), _perm("manage_catalog"))
    return user


@pytest.fixture
def channels(shop):
    """PDV, Loja online, iFood e WhatsApp, cada um com a listagem do mesmo ref."""
    for order, (ref, name) in enumerate(
        (("pdv", "PDV"), ("web", "Loja online"), ("ifood", "iFood"), ("whatsapp", "WhatsApp")), start=1
    ):
        Channel.objects.create(ref=ref, name=name, is_active=True, display_order=order)
        Listing.objects.create(ref=ref, name=name, is_active=True)
    return {listing.ref: listing for listing in Listing.objects.all()}


def _post(client, url: str, body: dict):
    return client.post(
        url, json.dumps(body), content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )


# ── GES-01 (P0): o cadastro novo não nasce num grupo com desconto ───────────


def test_ges01_form_options_dizem_qual_e_o_grupo_padrao(shop):
    from shopman.backstage.projections.customers import build_customer_form_options

    PriceTier.objects.create(ref="alianca-francesa", name="Aliança Francesa")
    PriceTier.objects.create(ref="varejo", name="Varejo")

    sem_padrao = build_customer_form_options()
    # A lista continua inteira, mas nenhum é "padrão": o formulário nasce sem grupo.
    assert [tier.value for tier in sem_padrao.price_tiers][0] == "alianca-francesa"
    assert sem_padrao.default_price_tier_refs == ()

    PriceTier.objects.filter(ref="varejo").update(is_default=True)
    assert build_customer_form_options().default_price_tier_refs == ("varejo",)


# ── GES-02: Vendido por peso pausa e devolve, nunca apaga ─────────────────


def test_ges02_vendido_por_peso_pausa_os_remotos_e_desmarcar_traz_de_volta(channels):
    cha = Product.objects.create(
        sku="CHCAM", name="Chá Camille", unit="un", base_price_q=1500,
        image_url="https://cdn.example.com/cha.jpg", is_published=True, is_sellable=True,
    )
    for ref, price in (("pdv", 1500), ("web", 1600), ("ifood", 1800), ("whatsapp", 1600)):
        ListingItem.objects.create(listing=channels[ref], product=cha, price_q=price)
    # Pausado à mão antes: continua pausado na volta.
    ListingItem.objects.filter(product=cha, listing__ref="whatsapp").update(is_sellable=False)

    catalog_service.update_product_detail("CHCAM", {"unit": "kg"})

    items = {item.listing.ref: item for item in ListingItem.objects.filter(product=cha).select_related("listing")}
    assert set(items) == {"pdv", "web", "ifood", "whatsapp"}, "nenhuma listagem pode sumir"
    assert (items["web"].is_published, items["web"].is_sellable, items["web"].price_q) == (False, False, 1600)
    assert (items["ifood"].is_published, items["ifood"].is_sellable, items["ifood"].price_q) == (False, False, 1800)
    assert items["pdv"].is_sellable is True

    catalog_service.update_product_detail("CHCAM", {"unit": "un"})

    items = {item.listing.ref: item for item in ListingItem.objects.filter(product=cha).select_related("listing")}
    assert (items["web"].is_published, items["web"].is_sellable) == (True, True)
    assert (items["ifood"].is_published, items["ifood"].is_sellable) == (True, True)
    assert items["whatsapp"].is_sellable is False, "a pausa à mão não é da regra: fica"
    cha.refresh_from_db()
    assert "remote_paused_by_rule" not in (cha.metadata or {})


# ── GES-03 / GES-26: a aba Geral lê a mesma fonte que Vínculos e Tabelão ─────


def test_ges03_canal_sem_vinculo_e_not_listed_e_vinculo_pausado_e_paused(channels):
    from shopman.backstage.services.catalog import _channel_availability_payload

    agua = Product.objects.create(sku="AGUA", name="Água", base_price_q=500, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=channels["pdv"], product=agua, price_q=500)
    ListingItem.objects.create(listing=channels["web"], product=agua, price_q=500, is_sellable=False)

    states = {row["ref"]: row["state"] for row in _channel_availability_payload("AGUA")}

    assert states == {"pdv": "available", "web": "paused", "ifood": "not_listed", "whatsapp": "not_listed"}


def test_ges03_canal_de_exibicao_fora_das_colecoes_e_not_listed(channels):
    from shopman.backstage.services.catalog import _channel_availability_payload

    Channel.objects.create(
        ref="meta", name="Catálogo Meta", is_active=True, display_order=9,
        commerce_policy=Channel.CommercePolicy.DISPLAY,
        config={"display": {"format": "meta_catalog", "collections": ["vitrine"]}},
    )
    vitrine = Collection.objects.create(ref="vitrine", name="Vitrine", is_active=True)
    dentro = Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    fora = Product.objects.create(sku="AGUA", name="Água", base_price_q=500, is_published=True, is_sellable=True)
    CollectionItem.objects.create(collection=vitrine, product=dentro, is_primary=True)
    for product in (dentro, fora):
        ListingItem.objects.create(listing=channels["web"], product=product, price_q=500)

    meta = lambda sku: next(row for row in _channel_availability_payload(sku) if row["ref"] == "meta")  # noqa: E731
    assert meta("PAO")["state"] == "available"
    assert meta("AGUA")["state"] == "not_listed"


# ── GES-04: o produto sem canal aparece no recorte de vigência ─────────────


def test_ges04_produto_sem_vinculo_passa_pela_vigencia(channels):
    from shopman.backstage.projections.catalog import build_catalog_matrix

    vendido = Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=channels["pdv"], product=vendido, price_q=500)
    Product.objects.create(sku="PAO-COPIA", name="Pão (cópia)", base_price_q=500, is_published=False, is_sellable=False)

    today = date.today()
    matrix = build_catalog_matrix(date_from=today, date_to=today)

    assert {row.sku for row in matrix.rows} == {"PAO", "PAO-COPIA"}


# ── GES-05: preço zero não passa calado ────────────────────────────────────


def test_ges05_preco_zero_no_canal_e_recusado_no_campo(channels):
    pao = Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=channels["pdv"], product=pao, price_q=500)

    with pytest.raises(CatalogError) as refused:
        catalog_service.set_cell("PAO", "pdv", price_q=0)

    assert str(refused.value) == "O preço precisa ser maior que zero."
    assert refused.value.field == "price_q"
    assert ListingItem.objects.get(product=pao, listing__ref="pdv").price_q == 500


def test_ges05_ajuste_em_lote_que_zera_preco_e_recusado(channels):
    pao = Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=channels["pdv"], product=pao, price_q=500)

    with pytest.raises(CatalogError, match="deixaria 1 preço em zero"):
        catalog_service.bulk_price(["PAO"], "pdv", op="delta", value=-1000)

    assert ListingItem.objects.get(product=pao, listing__ref="pdv").price_q == 500


# ── GES-08: contadores que não mentem ──────────────────────────────────────


def test_ges08_todas_conta_o_catalogo_e_nao_a_pagina(channels):
    from shopman.backstage.projections.catalog import build_catalog_matrix

    for index in range(5):
        Product.objects.create(sku=f"P{index}", name=f"P{index}", base_price_q=100, is_published=True, is_sellable=True)

    matrix = build_catalog_matrix(page_size=2)

    assert len(matrix.rows) == 2
    assert matrix.all_product_count == 5


def test_ges08_fora_do_ar_nao_conta_insumo(shop):
    from shopman.backstage.models import OutageReason, ShelfOutage
    from shopman.backstage.projections.order_attention import menu_outages

    Product.objects.create(sku="PAO", name="Pão", base_price_q=500)
    now = timezone.now()
    ShelfOutage.objects.create(sku="PAO", channel_ref="web", reason=OutageReason.SOLD_OUT, started_at=now)
    ShelfOutage.objects.create(sku="TOMATE", channel_ref="web", reason=OutageReason.SOLD_OUT, started_at=now)

    items, more = menu_outages(channel_names={"web": "Loja online"})

    assert [item.sku for item in items] == ["PAO"]
    assert more == 0


# ── GES-09: revisar vínculos de canal que não existe é 404 ─────────────────


def test_ges09_canal_inexistente_e_404_e_o_catalogo_abre_recortado(client, manager, channels):
    from shopman.backstage.projections.feeds import build_feed_board

    client.force_login(manager)
    response = client.get("/api/v1/backstage/catalog/channels/naoexiste/review/")
    assert response.status_code == 404

    board = build_feed_board(user=manager)
    paths = {channel.ref: channel.catalog_path for channel in board.catalog_channels}
    assert paths["web"] == "/catalog?surface=web"


# ── GES-11: SKU com letras, números e hífen ────────────────────────────────


@pytest.mark.parametrize("sku", ["mg teste 🥐", "PÃO", "A/B", "-INICIO"])
def test_ges11_sku_fora_do_padrao_e_recusado_no_campo(shop, sku):
    with pytest.raises(CatalogError) as refused:
        catalog_service.create_product({"sku": sku, "name": "Teste"})
    assert refused.value.field == "sku"
    assert not Product.objects.filter(name="Teste").exists()


def test_ges11_sku_vira_maiusculo(shop):
    detail, _ = catalog_service.create_product({"sku": "pao-novo", "name": "Pão novo"})
    assert detail["sku"] == "PAO-NOVO"


# ── GES-12: busca sem acento ───────────────────────────────────────────────


def test_ges12_busca_de_cliente_ignora_acento(shop):
    from shopman.backstage.projections.customers import build_customer_list

    Customer.objects.create(ref="CLI-003", first_name="João", last_name="Oliveira", phone="+5543993333333")
    Customer.objects.create(ref="CLI-004", first_name="Conceição", last_name="Araújo", phone="")

    assert [item.ref for item in build_customer_list(query="joao").items] == ["CLI-003"]
    assert [item.ref for item in build_customer_list(query="conceicao araujo").items] == ["CLI-004"]
    assert [item.ref for item in build_customer_list(query="João").items] == ["CLI-003"]


def test_ges12_a_dobra_do_postgres_e_a_mesma_do_python():
    """O ``TRANSLATE`` do Postgres e a ``shopman_fold`` do SQLite dobram igual.

    Sem isso, a busca passava no teste (SQLite) e falhava no alpha (Postgres).
    """
    from django.db import connection
    from django.db.models import Value

    from shopman.backstage.projections import customers

    assert len(customers._ACCENTED) == len(customers._PLAIN)
    for accented, plain in zip(customers._ACCENTED, customers._PLAIN, strict=True):
        assert customers._fold_text(accented) == plain
        assert customers._fold_text(accented.upper()) == plain

    class _Compiler:
        def compile(self, node):
            return node.as_sql(self, connection)

    sql, _ = customers.FoldedText(Value("x")).as_postgresql(_Compiler(), connection)
    assert sql.startswith("TRANSLATE(LOWER(")
    assert f"'{customers._ACCENTED}', '{customers._PLAIN}')" in sql


# ── GES-13: o telefone repetido diz de quem é ──────────────────────────────


def test_ges13_telefone_repetido_diz_de_quem_e(client, manager):
    Customer.objects.create(ref="CLI-003", first_name="João", last_name="Oliveira", phone="+5543993333333")
    client.force_login(manager)

    response = _post(client, CUSTOMERS_URL, {"firstName": "Rui", "phone": "43 99333-3333"})

    assert response.status_code == 409
    body = response.json()
    assert body["field"] == "phone"
    assert body["detail"] == "Este telefone é de João Oliveira (CLI-003). Abra o cadastro para conferir ou unificar."
    assert body["error"]["owner"] == {"ref": "CLI-003", "name": "João Oliveira"}


# ── GES-14: a marca técnica da unificação não aparece ao operador ──────────


def test_ges14_observacao_nao_mostra_a_marca_da_unificacao(shop):
    from shopman.backstage.projections.customers import build_customer_detail

    Customer.objects.create(
        ref="CUST-A", first_name="Ana", last_name="Silva", is_active=False,
        notes="Prefere retirada.\n[MERGED] → CUST-B by joyce",
    )

    assert build_customer_detail("CUST-A").notes == "Prefere retirada."


# ── GES-23: a evidência que falta nomeia o campo ───────────────────────────


def test_ges23_evidencia_textual_vazia_nomeia_o_campo():
    from shopman.backstage.models import OperationEvidence
    from shopman.backstage.services.operations import OperationChecklistError, _validate_evidence

    with pytest.raises(OperationChecklistError) as refused:
        _validate_evidence(required=OperationEvidence.TEXT, evidence_text="", evidence_number=None, evidence_data={})

    assert refused.value.field == "evidence_text"
    assert str(refused.value) == "Escreva a evidência para concluir esta tarefa."


# ── CMP-08: "Permitir revenda" conta a mesma história que o Catálogo ───────


def test_cmp08_revenda_vende_no_balcao_com_os_remotos_pausados(channels):
    from shopman.buyman.models import Material

    from shopman.backstage.projections.pos import _load_products
    from shopman.backstage.services.purchase import set_sale

    Material.objects.create(
        sku="TONICA-ANTARCTICA", name="Água tônica", unit="un",
        metadata={"image_url": "https://cdn.example.com/tonica.jpg"},
    )

    _board, message = set_sale("TONICA-ANTARCTICA", {"enabled": True, "priceInput": "6,00"})

    assert message == (
        "Água tônica está à venda no PDV. Loja online, iFood e WhatsApp ficam pausados até você ligar no Catálogo."
    )
    # A mesma história nas duas telas: publicado, vendendo no PDV, remotos pausados.
    assert [entry.sku for entry in _load_products()] == ["TONICA-ANTARCTICA"]
    remote = ListingItem.objects.filter(product__sku="TONICA-ANTARCTICA").exclude(listing__ref="pdv")
    assert remote.exists() and not remote.filter(is_published=True).exists()


# ── GES-10: "Ocultar no catálogo" tira o item do PDV também ────────────────


def test_ges10_produto_oculto_ou_pausado_nao_entra_na_grade_do_pdv(channels):
    from shopman.backstage.projections.pos import _load_products

    def produto(sku, **flags):
        product = Product.objects.create(sku=sku, name=sku.title(), base_price_q=500, **flags)
        ListingItem.objects.create(listing=channels["pdv"], product=product, price_q=500)
        return product

    produto("VISIVEL", is_published=True, is_sellable=True)
    produto("OCULTO", is_published=False, is_sellable=True)
    produto("PAUSADO", is_published=True, is_sellable=False)

    assert [entry.sku for entry in _load_products()] == ["VISIVEL"]


# ── GES-21: o dispositivo do posto ganha nome ──────────────────────────────


def test_ges21_dar_nome_ao_dispositivo_do_posto(client, shop):
    from shopman.doorman.models import SubjectType, TrustedDevice

    from shopman.backstage import station_trust
    from shopman.backstage.models import Workstation

    app_label, codename = station_trust.PROVISION_PERM.split(".")
    gestor = User.objects.create_user("gestor-postos", password="pw", is_staff=True)
    gestor.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
    Workstation.objects.create(ref="pdv-principal", label="PDV principal", kind="service")
    device, _token = TrustedDevice.create_for(SubjectType.STATION, "pdv-principal", user_agent="", ip_address="127.0.0.1")
    client.force_login(gestor)
    url = f"/api/v1/backstage/workstations/pdv-principal/devices/{device.pk}/"

    vazio = client.patch(url, json.dumps({"label": "  "}), content_type="application/json")
    assert vazio.status_code == 400
    assert vazio.json()["errors"] == {"label": ["Dê um nome ao dispositivo."]}

    ok = client.patch(url, json.dumps({"label": "Tablet do  balcão"}), content_type="application/json")
    assert ok.status_code == 200, ok.json()
    device.refresh_from_db()
    assert device.label == "Tablet do balcão"
    row = next(w for w in ok.json()["workstations"] if w["ref"] == "pdv-principal")
    assert row["devices"][0]["label"] == "Tablet do balcão"
