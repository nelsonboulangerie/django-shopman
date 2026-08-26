"""Compras surface contract (GET/POST api/v1/backstage/purchase/*).

The Nuxt app consumes a Backstage projection. Writes compose Buyman and
Stockman without adding domain rules to Core.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse
from shopman.buyman.models import Material, MaterialConversion, Supplier, SupplierMaterialCost
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.orderman.models import Directive
from shopman.stockman import stock
from shopman.stockman.models import Batch, Move, Position, Quant
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.models import DayClosing
from shopman.shop.directives import NOTIFICATION_SEND

VALID_ACCESS_KEY = "41260812345678000190550010000012341000123459"


def _operate_purchase_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_purchase",
    )


@pytest.fixture
def purchase_operator(db):
    user = User.objects.create_user("purchase-api", password="pw", is_staff=True)
    user.user_permissions.add(_operate_purchase_perm())
    return user


@pytest.fixture
def position(db):
    return Position.objects.create(ref="deposito", name="Depósito", kind=PositionKind.PHYSICAL, is_default=True)


@pytest.fixture
def material(db):
    return Material.objects.create(
        sku="FARINHA-T65",
        name="Farinha T65",
        unit="kg",
        shelf_life_days=180,
        metadata={"purchase": {"category": "Farinhas", "min_stock": "30"}},
    )


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(
        ref="SUP-MOINHO-SP",
        name="Moinho São Paulo",
        document="12.345.678/0001-90",
        email="compras@moinho.example",
        metadata={"purchase": {"lead_time_days": 2, "payment_term": "14 dias"}},
    )


@pytest.fixture
def conversion(material, supplier):
    return MaterialConversion.objects.create(
        material=material,
        supplier=supplier,
        label="saco 25 kg",
        to_base_factor=Decimal("25"),
    )


@pytest.mark.django_db
def test_purchase_board_requires_operate_purchase(client, material):
    bare = User.objects.create_user("bare-purchase", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse("api-backstage-purchase")).status_code == 403


@pytest.mark.django_db
def test_purchase_board_returns_composed_projection(client, purchase_operator, material, supplier, conversion, position):
    Recipe.objects.create(ref="baguete", name="Baguete", output_sku="BAGUETE", batch_size=Decimal("10"))
    recipe = Recipe.objects.get(ref="baguete")
    RecipeItem.objects.create(recipe=recipe, input_sku=material.sku, quantity=Decimal("6"), unit="kg")
    stock.receive(Decimal("12"), material.sku, position=position, reason="seed")
    SupplierMaterialCost.objects.create(
        supplier=supplier,
        material=material,
        conversion=conversion,
        cost_q=18000,
        is_preferred=True,
    )

    client.force_login(purchase_operator)
    response = client.get(reverse("api-backstage-purchase"))

    assert response.status_code == 200
    purchase = response.json()["purchase"]
    assert purchase["materials"][0]["sku"] == "FARINHA-T65"
    assert purchase["materials"][0]["stockOnHand"] == 12.0
    assert purchase["materials"][0]["recipes"] == ["Baguete"]
    assert purchase["suppliers"][0]["ref"] == "SUP-MOINHO-SP"
    assert purchase["conversions"][0]["label"] == "saco 25 kg"
    assert purchase["costs"][0]["costQ"] == 18000


@pytest.mark.django_db
def test_scan_invoice_validates_key_and_resolves_supplier(client, purchase_operator, supplier):
    client.force_login(purchase_operator)
    response = client.post(
        reverse("api-backstage-purchase-scan-invoice"),
        data={"qrPayload": f"https://fazenda.example/qrcode?p={VALID_ACCESS_KEY}|2|1"},
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    receipt = body["purchase"]["activeReceipt"]
    assert receipt["mode"] == "invoice"
    assert receipt["supplierRef"] == supplier.ref
    assert VALID_ACCESS_KEY in receipt["invoiceInput"]


@pytest.mark.django_db
def test_scan_invoice_uses_configured_nfe_reader(
    tmp_path,
    client,
    purchase_operator,
    material,
    supplier,
    conversion,
):
    supplier.metadata = {
        "purchase": {
            "invoice_product_map": {
                "FAR-25": {
                    "materialSku": material.sku,
                    "conversionLabel": conversion.label,
                }
            }
        }
    }
    supplier.save(update_fields=["metadata"])
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{VALID_ACCESS_KEY}" versao="4.00">
      <ide><serie>1</serie><nNF>1234</nNF><dhEmi>2026-08-25T09:00:00-03:00</dhEmi></ide>
      <emit><CNPJ>12345678000190</CNPJ><xNome>Moinho Sao Paulo</xNome></emit>
      <dest><CNPJ>99999999000191</CNPJ><xNome>Nelson Boulangerie</xNome></dest>
      <det nItem="1">
        <prod>
          <cProd>FAR-25</cProd>
          <xProd>FARINHA T65 25KG</xProd>
          <NCM>11010010</NCM>
          <CFOP>5102</CFOP>
          <uCom>SC</uCom>
          <qCom>2.0000</qCom>
          <vUnCom>180.0000000000</vUnCom>
          <vProd>360.00</vProd>
        </prod>
      </det>
      <total><ICMSTot><vNF>360.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe versao="4.00"><infProt><chNFe>{VALID_ACCESS_KEY}</chNFe><cStat>100</cStat></infProt></protNFe>
</nfeProc>
"""
    (tmp_path / f"{VALID_ACCESS_KEY}.xml").write_text(xml, encoding="utf-8")

    client.force_login(purchase_operator)
    with override_settings(
        SHOPMAN_PURCHASE_INVOICE_READER="shopman.shop.adapters.purchase_invoice_nfe.read_invoice",
        SHOPMAN_PURCHASE_NFE={"xml_dir": str(tmp_path)},
    ):
        response = client.post(
            reverse("api-backstage-purchase-scan-invoice"),
            data={"qrPayload": VALID_ACCESS_KEY},
            content_type="application/json",
        )

    assert response.status_code == 200
    receipt = response.json()["purchase"]["activeReceipt"]
    assert receipt["supplierRef"] == supplier.ref
    assert receipt["lines"][0]["materialSku"] == material.sku
    assert receipt["lines"][0]["conversionId"] == str(conversion.pk)
    assert receipt["lines"][0]["requiresConversion"] is False


@pytest.mark.django_db
def test_confirm_receipt_writes_buy_move_batch_and_cost(
    client,
    purchase_operator,
    material,
    supplier,
    conversion,
    position,
):
    client.force_login(purchase_operator)
    response = client.post(
        reverse("api-backstage-purchase-confirm-receipt"),
        data={
            "mode": "invoice",
            "supplierRef": supplier.ref,
            "invoiceAccessKey": VALID_ACCESS_KEY,
            "note": "Conferido no recebimento",
            "lines": [
                {
                    "id": "line-farinha",
                    "materialSku": material.sku,
                    "conversionId": str(conversion.pk),
                    "purchaseQty": 2,
                    "costInput": "360,00",
                    "expiryDate": "2027-02-25",
                    "lineNote": "Recebimento parcial; 1 saco avariado devolvido.",
                    "checked": True,
                }
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    quant = Quant.objects.get(sku=material.sku, position=position)
    assert quant.quantity == Decimal("50.000")
    move = Move.objects.get(quant=quant)
    assert move.kind == Move.Kind.BUY
    assert move.metadata["purchase_supplier_ref"] == supplier.ref
    assert move.metadata["purchase_line_note"] == "Recebimento parcial; 1 saco avariado devolvido."
    assert move.metadata["purchase_unit_cost_q"] == 18000
    batch = Batch.objects.get(sku=material.sku, expiry_date="2027-02-25")
    assert "Recebimento parcial" in batch.notes

    cost = SupplierMaterialCost.objects.get(material=material, supplier=supplier)
    assert cost.cost_q == 18000
    assert cost.is_preferred is True
    assert cost.cost_per_base_unit_q == 720


@pytest.mark.django_db
def test_confirm_receipt_blocks_imported_line_that_requires_conversion(
    client,
    purchase_operator,
    material,
    supplier,
):
    client.force_login(purchase_operator)
    response = client.post(
        reverse("api-backstage-purchase-confirm-receipt"),
        data={
            "mode": "invoice",
            "supplierRef": supplier.ref,
            "invoiceAccessKey": VALID_ACCESS_KEY,
            "note": "NF lida",
            "lines": [
                {
                    "id": "line-farinha",
                    "materialSku": material.sku,
                    "conversionId": None,
                    "requiresConversion": True,
                    "purchaseQty": 2,
                    "costInput": "360,00",
                    "expiryDate": "2027-02-25",
                    "lineNote": "Definir conversao antes de confirmar.",
                    "checked": True,
                }
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "conversion_required"
    assert Move.objects.count() == 0


@pytest.mark.django_db
def test_reject_receipt_records_notification_without_stock_move(client, purchase_operator, material, supplier, conversion):
    client.force_login(purchase_operator)
    response = client.post(
        reverse("api-backstage-purchase-reject-receipt"),
        data={
            "mode": "invoice",
            "supplierRef": supplier.ref,
            "invoiceAccessKey": VALID_ACCESS_KEY,
            "note": "Fornecedor não permite recebimento parcial; remessa devolvida.",
            "lines": [
                {
                    "id": "line-farinha",
                    "materialSku": material.sku,
                    "conversionId": str(conversion.pk),
                    "purchaseQty": 1,
                    "costInput": "180,00",
                    "expiryDate": "2027-02-25",
                    "lineNote": "Saco rasgado e molhado.",
                    "checked": False,
                }
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert Move.objects.count() == 0
    directive = Directive.objects.get(topic=NOTIFICATION_SEND)
    assert directive.payload["event"] == "purchase_receipt_rejected"
    assert directive.payload["backends"] == ["console"]
    assert directive.payload["context"]["supplier_ref"] == supplier.ref
    assert directive.payload["context"]["document_ref"] == VALID_ACCESS_KEY
    assert "recebimento parcial" in directive.payload["context"]["reason"]
    assert "Saco rasgado" in directive.payload["context"]["lines_text"]


@pytest.mark.django_db
def test_upsert_cost_and_request_status_actions(client, purchase_operator, material, supplier, conversion):
    client.force_login(purchase_operator)
    supplier.email = ""
    supplier.metadata = {"purchase": {"contact": "pedidos@moinho.example", "lead_time_days": 2}}
    supplier.save(update_fields=["email", "metadata", "updated_at"])

    cost_response = client.post(
        reverse("api-backstage-purchase-costs"),
        data={
            "materialSku": material.sku,
            "supplierRef": supplier.ref,
            "conversionId": str(conversion.pk),
            "costInput": "180,00",
            "makePreferred": True,
        },
        content_type="application/json",
    )
    assert cost_response.status_code == 200
    assert SupplierMaterialCost.objects.get(material=material, supplier=supplier).is_preferred is True

    approve = client.post(reverse("api-backstage-purchase-request-approve", args=[material.sku]))
    assert approve.status_code == 200
    assert approve.json()["purchase"]["purchaseRequestStatuses"][material.sku] == "approved"

    sent = client.post(reverse("api-backstage-purchase-request-send", args=[material.sku]))
    assert sent.status_code == 200
    material.refresh_from_db()
    assert material.metadata["purchase"]["request_status"] == "sent"
    assert material.metadata["purchase"]["request_supplier_ref"] == supplier.ref
    directive = Directive.objects.get(topic=NOTIFICATION_SEND, payload__event="purchase_request")
    assert directive.payload["recipient"] == "pedidos@moinho.example"
    assert directive.payload["backends"] == ["email", "console"]
    assert directive.payload["context"]["material_sku"] == material.sku
    assert directive.payload["context"]["supplier_ref"] == supplier.ref
    assert directive.payload["context"]["operator_username"] == purchase_operator.username


@pytest.mark.django_db
def test_send_purchase_request_requires_supplier_contact(client, purchase_operator, material, supplier, conversion):
    client.force_login(purchase_operator)
    supplier.email = ""
    supplier.phone = ""
    supplier.save(update_fields=["email", "phone", "updated_at"])
    SupplierMaterialCost.objects.create(
        material=material,
        supplier=supplier,
        conversion=conversion,
        cost_q=18000,
        is_preferred=True,
    )

    response = client.post(reverse("api-backstage-purchase-request-send", args=[material.sku]))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "supplier_contact_missing"
    material.refresh_from_db()
    assert material.metadata["purchase"].get("request_status") != "sent"
    assert not Directive.objects.filter(topic=NOTIFICATION_SEND, payload__event="purchase_request").exists()
