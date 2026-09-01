"""Compras surface contract (GET/POST api/v1/backstage/purchase/*).

The Nuxt app consumes a Backstage projection. Writes compose Buyman and
Stockman without adding domain rules to Core.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest
from django.apps import apps
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


def _nfe_reader_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
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
        ref="moinho-sp",
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
    assert purchase["suppliers"][0]["ref"] == "moinho-sp"
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
    (tmp_path / f"{VALID_ACCESS_KEY}.xml").write_text(_nfe_reader_xml(), encoding="utf-8")

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
    assert receipt["lines"][0]["invoiceProductCode"] == "FAR-25"
    assert receipt["lines"][0]["invoiceEan"] == ""


@pytest.mark.django_db
def test_scan_invoice_registers_unknown_supplier_from_issuer(tmp_path, client, purchase_operator):
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{VALID_ACCESS_KEY}" versao="4.00">
      <ide><serie>1</serie><nNF>2271</nNF><dhEmi>2026-08-11T09:00:00-03:00</dhEmi></ide>
      <emit>
        <CNPJ>84290690000228</CNPJ>
        <xNome>INDUSTRIA E COMERCIO DE PRODUTOS ALIMENTICIOS TAMURA LTDA</xNome>
        <enderEmit><fone>4333221100</fone></enderEmit>
      </emit>
      <dest><CNPJ>99999999000191</CNPJ><xNome>Nelson Boulangerie</xNome></dest>
      <det nItem="1">
        <prod>
          <cProd>PRD00015</cProd>
          <xProd>B2B Cafe Tamura Chocomelo Torra Media 500g</xProd>
          <NCM>09012100</NCM>
          <CFOP>5101</CFOP>
          <uCom>1UN</uCom>
          <qCom>10.0000</qCom>
          <vUnCom>59.2500000000</vUnCom>
          <vProd>592.50</vProd>
        </prod>
      </det>
      <total><ICMSTot><vNF>614.58</vNF></ICMSTot></total>
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
    body = response.json()
    assert "fornecedor cadastrado" in body["message"].lower()
    receipt = body["purchase"]["activeReceipt"]
    assert receipt["supplierRef"] == "tamura"
    assert "fornecedor nao cadastrado" not in receipt["note"]
    assert receipt["lines"][0]["materialSku"] == ""

    Supplier = apps.get_model("buyman", "Supplier")
    created = Supplier.objects.get(ref="tamura")
    assert created.document == "84.290.690/0002-28"
    assert created.name.startswith("INDUSTRIA E COMERCIO")
    assert created.phone == "4333221100"
    assert created.is_active is True
    supplier_refs = [supplier["ref"] for supplier in body["purchase"]["suppliers"]]
    assert "tamura" in supplier_refs


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
    # Fase 5: a ponte que a quantidade atravessou fica carimbada no proprio
    # lancamento — as tres chaves juntas, para a conta poder ser refeita depois.
    assert move.metadata["converted_via"] == {
        "label": "saco 25 kg",
        "factor": "25.000000",
        "approximate": False,
    }
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
def test_confirm_receipt_learns_invoice_product_map_for_the_next_scan(
    tmp_path,
    client,
    purchase_operator,
    material,
    supplier,
    conversion,
    position,
):
    (tmp_path / f"{VALID_ACCESS_KEY}.xml").write_text(_nfe_reader_xml(), encoding="utf-8")
    client.force_login(purchase_operator)
    nfe_settings = {
        "SHOPMAN_PURCHASE_INVOICE_READER": "shopman.shop.adapters.purchase_invoice_nfe.read_invoice",
        "SHOPMAN_PURCHASE_NFE": {"xml_dir": str(tmp_path)},
    }

    with override_settings(**nfe_settings):
        first_scan = client.post(
            reverse("api-backstage-purchase-scan-invoice"),
            data={"qrPayload": VALID_ACCESS_KEY},
            content_type="application/json",
        )
    first_line = first_scan.json()["purchase"]["activeReceipt"]["lines"][0]
    assert first_line["materialSku"] == ""
    assert first_line["invoiceProductCode"] == "FAR-25"

    confirm = client.post(
        reverse("api-backstage-purchase-confirm-receipt"),
        data={
            "mode": "invoice",
            "supplierRef": supplier.ref,
            "invoiceAccessKey": VALID_ACCESS_KEY,
            "note": "NF conferida",
            "lines": [
                {
                    "id": first_line["id"],
                    "materialSku": material.sku,
                    "conversionId": str(conversion.pk),
                    "purchaseQty": 2,
                    "costInput": "360,00",
                    "expiryDate": "2027-02-25",
                    "lineNote": first_line["lineNote"],
                    "invoiceProductCode": first_line["invoiceProductCode"],
                    "invoiceEan": first_line["invoiceEan"],
                    "checked": True,
                }
            ],
        },
        content_type="application/json",
    )

    assert confirm.status_code == 200
    supplier.refresh_from_db()
    assert supplier.metadata["purchase"]["invoice_product_map"] == {
        "FAR-25": {"materialSku": material.sku, "conversionLabel": conversion.label}
    }
    assert supplier.metadata["purchase"]["lead_time_days"] == 2

    with override_settings(**nfe_settings):
        second_scan = client.post(
            reverse("api-backstage-purchase-scan-invoice"),
            data={"qrPayload": VALID_ACCESS_KEY},
            content_type="application/json",
        )
    line = second_scan.json()["purchase"]["activeReceipt"]["lines"][0]
    assert line["materialSku"] == material.sku
    assert line["conversionId"] == str(conversion.pk)
    assert line["requiresConversion"] is False


@pytest.mark.django_db
def test_confirm_receipt_replaces_divergent_map_entry_and_logs(
    caplog,
    client,
    purchase_operator,
    material,
    supplier,
    conversion,
    position,
):
    supplier.metadata = {
        "purchase": {
            "lead_time_days": 2,
            "invoice_product_map": {
                "FAR-25": {"materialSku": "MANTEIGA-TOURAGE", "conversionLabel": "caixa 10 kg"},
                "ACU-01": "ACUCAR-CRISTAL",
            },
        }
    }
    supplier.save(update_fields=["metadata", "updated_at"])
    client.force_login(purchase_operator)

    # O logger "shopman" tem propagate=False (config/settings.py): o handler do
    # caplog fica na raiz e nunca veria o warning. Anexar direto no logger do
    # service captura independente de propagação.
    service_logger = logging.getLogger("shopman.backstage.services.purchase")
    service_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="shopman.backstage.services.purchase"):
            response = client.post(
                reverse("api-backstage-purchase-confirm-receipt"),
                data={
                    "mode": "invoice",
                    "supplierRef": supplier.ref,
                    "invoiceAccessKey": VALID_ACCESS_KEY,
                    "note": "Operador corrigiu o insumo da linha",
                    "lines": [
                        {
                            "id": "nfe-1",
                            "materialSku": material.sku,
                            "conversionId": str(conversion.pk),
                            "purchaseQty": 2,
                            "costInput": "360,00",
                            "expiryDate": "2027-02-25",
                            "lineNote": "",
                            "invoiceProductCode": "FAR-25",
                            "checked": True,
                        }
                    ],
                },
                content_type="application/json",
            )
    finally:
        service_logger.removeHandler(caplog.handler)

    assert response.status_code == 200
    supplier.refresh_from_db()
    mapping = supplier.metadata["purchase"]["invoice_product_map"]
    assert mapping["FAR-25"] == {"materialSku": material.sku, "conversionLabel": conversion.label}
    assert mapping["ACU-01"] == "ACUCAR-CRISTAL"
    assert supplier.metadata["purchase"]["lead_time_days"] == 2
    assert "purchase.invoice_product_map_overwrite" in caplog.text


@pytest.mark.django_db
def test_confirm_receipt_without_invoice_context_learns_nothing(
    client,
    purchase_operator,
    material,
    supplier,
    conversion,
    position,
):
    client.force_login(purchase_operator)

    manual = client.post(
        reverse("api-backstage-purchase-confirm-receipt"),
        data={
            "mode": "manual",
            "supplierRef": supplier.ref,
            "invoiceAccessKey": None,
            "note": "Romaneio em papel conferido na entrega",
            "lines": [
                {
                    "id": "manual-1",
                    "materialSku": material.sku,
                    "conversionId": str(conversion.pk),
                    "purchaseQty": 1,
                    "costInput": "180,00",
                    "expiryDate": "2027-02-25",
                    "lineNote": "",
                    "invoiceProductCode": "FAR-25",
                    "checked": True,
                }
            ],
        },
        content_type="application/json",
    )
    assert manual.status_code == 200

    invoice_without_code = client.post(
        reverse("api-backstage-purchase-confirm-receipt"),
        data={
            "mode": "invoice",
            "supplierRef": supplier.ref,
            "invoiceAccessKey": VALID_ACCESS_KEY,
            "note": "Linha adicionada à mão na conferência",
            "lines": [
                {
                    "id": "extra-1",
                    "materialSku": material.sku,
                    "conversionId": str(conversion.pk),
                    "purchaseQty": 1,
                    "costInput": "180,00",
                    "expiryDate": "2027-02-25",
                    "lineNote": "",
                    "checked": True,
                }
            ],
        },
        content_type="application/json",
    )
    assert invoice_without_code.status_code == 200

    supplier.refresh_from_db()
    assert "invoice_product_map" not in supplier.metadata.get("purchase", {})


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


def _nfe_issuer_xml(cnpj: str, nome: str) -> str:
    """NF mínima de um emitente qualquer, para exercitar o cadastro de fornecedor."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{VALID_ACCESS_KEY}" versao="4.00">
      <ide><serie>1</serie><nNF>3310</nNF><dhEmi>2026-08-27T09:00:00-03:00</dhEmi></ide>
      <emit>
        <CNPJ>{cnpj}</CNPJ>
        <xNome>{nome}</xNome>
        <enderEmit><fone>4333445566</fone></enderEmit>
      </emit>
      <dest><CNPJ>99999999000191</CNPJ><xNome>Nelson Boulangerie</xNome></dest>
      <det nItem="1">
        <prod>
          <cProd>PRD00099</cProd>
          <xProd>Farinha de trigo tipo 1 saco 25kg</xProd>
          <NCM>11010010</NCM>
          <CFOP>5101</CFOP>
          <uCom>SC</uCom>
          <qCom>4.0000</qCom>
          <vUnCom>150.0000000000</vUnCom>
          <vProd>600.00</vProd>
        </prod>
      </det>
      <total><ICMSTot><vNF>600.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe versao="4.00"><infProt><chNFe>{VALID_ACCESS_KEY}</chNFe><cStat>100</cStat></infProt></protNFe>
</nfeProc>
"""


def _scan(client, tmp_path, xml):
    (tmp_path / f"{VALID_ACCESS_KEY}.xml").write_text(xml, encoding="utf-8")
    with override_settings(
        SHOPMAN_PURCHASE_INVOICE_READER="shopman.shop.adapters.purchase_invoice_nfe.read_invoice",
        SHOPMAN_PURCHASE_NFE={"xml_dir": str(tmp_path)},
    ):
        return client.post(
            reverse("api-backstage-purchase-scan-invoice"),
            data={"qrPayload": VALID_ACCESS_KEY},
            content_type="application/json",
        )


@pytest.mark.django_db
def test_scan_invoice_adopts_supplier_the_owner_already_registered_by_name(
    tmp_path, client, purchase_operator
):
    """A NF traz a razão social; o dono cadastrou o nome de boca. É a MESMA casa.

    Sem isto, a primeira nota de um fornecedor já cadastrado cria um segundo
    cadastro e o histórico de custo nasce partido em dois.
    """
    Supplier = apps.get_model("buyman", "Supplier")
    existente = Supplier.objects.create(
        ref="france-panificacao", name="France Panificação", is_active=True
    )
    assert existente.document == ""

    client.force_login(purchase_operator)
    response = _scan(
        client, tmp_path, _nfe_issuer_xml("11222333000181", "FRANCE PANIFICACAO LTDA")
    )

    assert response.status_code == 200
    receipt = response.json()["purchase"]["activeReceipt"]
    assert receipt["supplierRef"] == "france-panificacao"

    existente.refresh_from_db()
    assert existente.document == "11.222.333/0001-81"
    assert existente.phone == "4333445566"
    assert existente.metadata["purchase"]["document_learned_from"] == "nfe_scan"
    # o que importa: UM fornecedor para a empresa, não dois
    assert Supplier.objects.filter(name__icontains="FRANCE").count() == 1


@pytest.mark.django_db
def test_scan_invoice_never_overwrites_a_supplier_that_already_has_another_cnpj(
    tmp_path, client, purchase_operator
):
    """Nome parecido não vence CNPJ conhecido — senão a nota de uma filial
    sequestraria o cadastro da outra."""
    Supplier = apps.get_model("buyman", "Supplier")
    outro = Supplier.objects.create(
        ref="france-panificacao",
        name="France Panificação",
        document="99.888.777/0001-66",
        is_active=True,
    )

    client.force_login(purchase_operator)
    response = _scan(
        client, tmp_path, _nfe_issuer_xml("11222333000181", "FRANCE PANIFICACAO LTDA")
    )

    assert response.status_code == 200
    outro.refresh_from_db()
    assert outro.document == "99.888.777/0001-66"
    assert Supplier.objects.filter(document="11.222.333/0001-81").exclude(pk=outro.pk).exists()


@pytest.mark.django_db
def test_scan_invoice_registers_new_supplier_when_the_name_is_ambiguous(
    tmp_path, client, purchase_operator
):
    """Dois candidatos com a mesma chave de nome = ambiguidade. Cadastra novo em
    vez de adivinhar qual dos dois é o emitente."""
    Supplier = apps.get_model("buyman", "Supplier")
    Supplier.objects.create(ref="france-panificacao-a", name="France Panificação", is_active=True)
    Supplier.objects.create(
        ref="france-panificacao-b", name="FRANCE PANIFICACAO ME", is_active=True
    )

    client.force_login(purchase_operator)
    response = _scan(
        client, tmp_path, _nfe_issuer_xml("11222333000181", "FRANCE PANIFICACAO LTDA")
    )

    assert response.status_code == 200
    for ref in ("france-panificacao-a", "france-panificacao-b"):
        assert Supplier.objects.get(ref=ref).document == ""
    assert Supplier.objects.filter(document="11.222.333/0001-81").count() == 1


@pytest.mark.django_db
def test_declare_conversion_requires_operate_purchase(client, material):
    bare = User.objects.create_user("bare-conversion", password="pw", is_staff=True)
    client.force_login(bare)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {"materialSku": material.sku, "label": "pacote 500 g", "factor": "0.5"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert MaterialConversion.objects.count() == 0


@pytest.mark.django_db
def test_declare_conversion_creates_the_row_with_its_author(client, purchase_operator, material, supplier):
    """O gesto que faltava: a embalagem nova nasce no recebimento, assinada."""
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {
            "materialSku": material.sku,
            "supplierRef": supplier.ref,
            "label": "pacote 500 g",
            "factor": "0.5",
            "kind": "conventional",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    conversion = MaterialConversion.objects.get()
    assert body["conversionId"] == str(conversion.pk)
    assert body["message"] == "Conversão salva: 1 pacote 500 g = 0,5 kg."
    assert conversion.material == material
    assert conversion.supplier == supplier
    assert conversion.to_base_factor == Decimal("0.500000")
    assert conversion.created_by == purchase_operator
    # A projection já volta com a conversão, para a linha poder selecioná-la.
    assert body["purchase"]["conversions"][0]["id"] == str(conversion.pk)


@pytest.mark.django_db
def test_declare_conversion_without_supplier_serves_every_supplier(client, purchase_operator, material):
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {"materialSku": material.sku, "label": "cartela", "factor": "1.5", "kind": "approximate"},
        content_type="application/json",
    )

    assert response.status_code == 200
    conversion = MaterialConversion.objects.get()
    assert conversion.supplier is None
    assert conversion.is_approximate is True
    assert response.json()["message"].endswith("(aproximada).")


@pytest.mark.django_db
@pytest.mark.parametrize("factor", ["0", "-2", "", "abc"])
def test_declare_conversion_refuses_a_factor_that_is_not_positive(client, purchase_operator, material, factor):
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {"materialSku": material.sku, "label": "saco", "factor": factor},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "conversion_factor_invalid"
    assert response.json()["field"] == "factor"
    assert MaterialConversion.objects.count() == 0


@pytest.mark.django_db
def test_declare_conversion_refuses_a_duplicate_label(client, purchase_operator, material, supplier, conversion):
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {
            "materialSku": material.sku,
            "supplierRef": supplier.ref,
            "label": conversion.label,
            "factor": "20",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "conversion_validation_failed"
    assert "Edite a existente" in response.json()["detail"]
    assert MaterialConversion.objects.count() == 1
    conversion.refresh_from_db()
    assert conversion.to_base_factor == Decimal("25.000000")


@pytest.mark.django_db
def test_declaring_the_same_conversion_twice_returns_the_one_that_exists(
    client, purchase_operator, material, supplier, conversion,
):
    """Segundo clique — ou segundo operador lendo a mesma nota — não vira erro."""
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {
            "materialSku": material.sku,
            "supplierRef": supplier.ref,
            "label": conversion.label,
            "factor": "25",
            "kind": "conventional",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["conversionId"] == str(conversion.pk)
    assert response.json()["message"] == "Conversão já cadastrada: saco 25 kg."
    assert MaterialConversion.objects.count() == 1


@pytest.mark.django_db
def test_declare_conversion_points_a_factor_error_at_the_factor_field(client, purchase_operator, material):
    """Fator com casas demais é erro DO FATOR — a tela precisa destacar o campo certo."""
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {"materialSku": material.sku, "label": "saco", "factor": "0.12345678901"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["field"] == "factor"
    assert MaterialConversion.objects.count() == 0


@pytest.mark.django_db
def test_declare_conversion_refuses_a_blank_label(client, purchase_operator, material):
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {"materialSku": material.sku, "label": "   ", "factor": "0.5"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "conversion_label_required"


@pytest.mark.django_db
def test_scan_invoice_carries_the_conversion_the_note_suggests(tmp_path, client, purchase_operator, supplier):
    """Ponta a ponta: o caso do fermento chega na tela como sugestão, não como erro mudo."""
    Material.objects.create(
        sku="FERMENTO-BIO",
        name="Fermento biologico",
        unit="kg",
        metadata={"purchase": {"invoice_codes": ["FERM-500"]}},
    )
    client.force_login(purchase_operator)

    xml = _nfe_reader_xml().replace(
        """          <cProd>FAR-25</cProd>
          <xProd>FARINHA T65 25KG</xProd>
          <NCM>11010010</NCM>
          <CFOP>5102</CFOP>
          <uCom>SC</uCom>
          <qCom>2.0000</qCom>
          <vUnCom>180.0000000000</vUnCom>
          <vProd>360.00</vProd>""",
        """          <cProd>FERM-500</cProd>
          <xProd>FERM BIOL FRESCO MAURI 500G</xProd>
          <NCM>21021000</NCM>
          <CFOP>5102</CFOP>
          <uCom>UN</uCom>
          <qCom>10.0000</qCom>
          <vUnCom>6.0000000000</vUnCom>
          <uTrib>KG</uTrib>
          <qTrib>5.0000</qTrib>
          <vUnTrib>12.0000000000</vUnTrib>
          <vProd>60.00</vProd>""",
    )

    (tmp_path / f"{VALID_ACCESS_KEY}.xml").write_text(xml, encoding="utf-8")
    with override_settings(
        SHOPMAN_PURCHASE_INVOICE_READER="shopman.shop.adapters.purchase_invoice_nfe.read_invoice",
        SHOPMAN_PURCHASE_NFE={"xml_dir": str(tmp_path)},
    ):
        response = client.post(
            reverse("api-backstage-purchase-scan-invoice"),
            {"qrPayload": VALID_ACCESS_KEY},
            content_type="application/json",
        )

    assert response.status_code == 200
    line = response.json()["purchase"]["activeReceipt"]["lines"][0]
    assert line["materialSku"] == "FERMENTO-BIO"
    assert line["purchaseQty"] == 10.0
    assert line["invoiceUnit"] == "UN"
    assert line["requiresConversion"] is True
    assert line["conversionSuggestion"] == {
        "label": "Un 500 g",
        "factor": "0.5",
        "kind": "conventional",
        "source": "invoice-tax-pair",
        "note": "A NF diz 10 UN = 5 KG (12,00 por KG), então 1 UN = 0,5 kg.",
    }


@pytest.mark.django_db
def test_receipt_in_the_base_unit_stamps_no_bridge(client, purchase_operator, supplier, position):
    """Sem conversao no meio nao ha ponte a registrar — e uma chave `null` fingiria que ha."""
    sal = Material.objects.create(sku="SAL", name="Sal marinho", unit="kg")
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-confirm-receipt"),
        data={
            "mode": "manual",
            "supplierRef": supplier.ref,
            "note": "Romaneio",
            "lines": [
                {
                    "id": "line-sal",
                    "materialSku": sal.sku,
                    "conversionId": None,
                    "purchaseQty": 3,
                    "costInput": "9,00",
                    "checked": True,
                }
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    move = Move.objects.get(quant__sku=sal.sku)
    assert "converted_via" not in move.metadata


@pytest.mark.django_db
def test_stock_that_crossed_an_approximate_bridge_carries_the_tilde(
    client, purchase_operator, material, supplier, position,
):
    """R3 da ADR-024: a incerteza acompanha o numero ate a tela."""
    ovos = Material.objects.create(sku="OVOS", name="Ovos", unit="kg", shelf_life_days=21)
    cartela = MaterialConversion.objects.create(
        material=ovos,
        supplier=supplier,
        label="cartela",
        to_base_factor=Decimal("1.5"),
        kind=MaterialConversion.Kind.APPROXIMATE,
    )
    client.force_login(purchase_operator)

    confirm = client.post(
        reverse("api-backstage-purchase-confirm-receipt"),
        data={
            "mode": "manual",
            "supplierRef": supplier.ref,
            "note": "Romaneio",
            "lines": [
                {
                    "id": "line-ovos",
                    "materialSku": ovos.sku,
                    "conversionId": str(cartela.pk),
                    "purchaseQty": 2,
                    "costInput": "48,00",
                    "expiryDate": "2026-09-30",
                    "checked": True,
                }
            ],
        },
        content_type="application/json",
    )
    assert confirm.status_code == 200

    move = Move.objects.get(quant__sku=ovos.sku)
    assert move.metadata["converted_via"] == {
        "label": "cartela",
        "factor": "1.500000",
        "approximate": True,
    }

    board = client.get(reverse("api-backstage-purchase"))
    rows = {row["sku"]: row for row in board.json()["purchase"]["materials"]}
    assert rows["OVOS"]["stockIsApproximate"] is True
    # O insumo que entrou na propria base nao ganha enfeite: numero exato e exato.
    assert rows["FARINHA-T65"]["stockIsApproximate"] is False


@pytest.mark.django_db
def test_declare_conversion_derives_the_factor_from_the_invoice_axes(client, purchase_operator, supplier):
    """O caminho da nota real: o insumo so e escolhido DEPOIS do scan.

    "MANTEIGA S/SAL CX 5 KG PRESIDENT TEU" nao casa com "Manteiga francesa" do
    cadastro, entao o scan nao pode calcular a conversao — sem insumo nao ha
    unidade-base para converter PARA. Escolhido o insumo, o par da nota volta e
    o servidor deriva, com a mesma fisica do adapter.
    """
    manteiga = Material.objects.create(sku="MANTEIGA-FR", name="Manteiga francesa", unit="kg")
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {
            "materialSku": manteiga.sku,
            "supplierRef": supplier.ref,
            "invoiceQty": "7",
            "invoiceUnit": "CX",
            "invoiceTaxQty": "35",
            "invoiceTaxUnit": "KG",
            "invoiceDescription": "MANTEIGA S/SAL CX 5 KG PRESIDENT TEU",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    conversion = MaterialConversion.objects.get()
    assert conversion.label == "Caixa 5 kg"
    assert conversion.to_base_factor == Decimal("5.000000")
    assert conversion.kind == MaterialConversion.Kind.CONVENTIONAL
    assert conversion.created_by == purchase_operator
    assert response.json()["conversionId"] == str(conversion.pk)


@pytest.mark.django_db
def test_invoice_axes_that_cannot_reach_the_base_still_refuse(client, purchase_operator, supplier):
    """R4 intacta: entre massa e contagem nao existe caminho, e o gesto para."""
    contados = Material.objects.create(sku="GUARDANAPO", name="Guardanapo", unit="un")
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-conversions"),
        {
            "materialSku": contados.sku,
            "supplierRef": supplier.ref,
            "invoiceQty": "7",
            "invoiceUnit": "CX",
            "invoiceTaxQty": "35",
            "invoiceTaxUnit": "KG",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "conversion_label_required"
    assert MaterialConversion.objects.count() == 0


@pytest.mark.django_db
def test_supplier_lot_from_the_note_becomes_the_stock_batch(
    client, purchase_operator, material, supplier, conversion, position,
):
    """Num recall, quem chama o lote e o fornecedor: "lote L2408A", nao o
    codigo que a nossa entrada inventou. Guardar o numero da nota e o que torna
    "esse lote entrou aqui?" uma pergunta respondivel em segundos.
    """
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-confirm-receipt"),
        data={
            "mode": "invoice",
            "supplierRef": supplier.ref,
            "invoiceAccessKey": VALID_ACCESS_KEY,
            "note": "",
            "lines": [
                {
                    "id": "line-farinha",
                    "materialSku": material.sku,
                    "conversionId": str(conversion.pk),
                    "purchaseQty": 2,
                    "costInput": "360,00",
                    "expiryDate": "2027-02-25",
                    "invoiceLot": "L2408A",
                    "checked": True,
                }
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    batch = Batch.objects.get(sku=material.sku)
    assert batch.ref == "FARINHAT65-LL2408A"
    assert str(batch.expiry_date) == "2027-02-25"
    assert batch.supplier == supplier.name


@pytest.mark.django_db
def test_receipt_without_a_supplier_lot_keeps_the_derived_batch_ref(
    client, purchase_operator, material, supplier, conversion, position,
):
    """`rastro` e opcional: sem lote na nota, vale o codigo derivado de sempre."""
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-confirm-receipt"),
        data={
            "mode": "invoice",
            "supplierRef": supplier.ref,
            "invoiceAccessKey": VALID_ACCESS_KEY,
            "note": "",
            "lines": [
                {
                    "id": "line-farinha",
                    "materialSku": material.sku,
                    "conversionId": str(conversion.pk),
                    "purchaseQty": 2,
                    "costInput": "360,00",
                    "expiryDate": "2027-02-25",
                    "checked": True,
                }
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    batch = Batch.objects.get(sku=material.sku)
    assert batch.ref.startswith("BUY-")


@pytest.mark.django_db
def test_cost_batch_requires_operate_purchase(client, material, supplier):
    bare = User.objects.create_user("bare-cost-batch", password="pw", is_staff=True)
    client.force_login(bare)
    response = client.post(
        reverse("api-backstage-purchase-costs-batch"),
        data={"supplierRef": supplier.ref, "costs": []},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_cost_batch_saves_many_and_returns_projection(client, purchase_operator, material, supplier):
    outro = Material.objects.create(sku="SAL", name="Sal", unit="kg")
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-costs-batch"),
        data={
            "supplierRef": supplier.ref,
            "makePreferred": True,
            "costs": [
                {"materialSku": material.sku, "costInput": "180,00"},
                {"materialSku": outro.sku, "costInput": "2,90"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    # A tela recebe a projeção junto: um gesto, um round-trip.
    assert {row["sku"] for row in body["purchase"]["materials"]} >= {material.sku, outro.sku}
    assert SupplierMaterialCost.objects.filter(is_preferred=True).count() == 2


@pytest.mark.django_db
def test_cost_batch_reports_the_offending_line(client, purchase_operator, material, supplier):
    client.force_login(purchase_operator)

    response = client.post(
        reverse("api-backstage-purchase-costs-batch"),
        data={
            "supplierRef": supplier.ref,
            "costs": [
                {"materialSku": material.sku, "costInput": "180,00"},
                {"materialSku": "NAO-EXISTE", "costInput": "1,00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "cost_batch_invalid"
    assert body["error"]["lines"][0]["index"] == 1
    assert body["error"]["lines"][0]["materialSku"] == "NAO-EXISTE"
    # Tudo-ou-nada: a linha boa também não entrou.
    assert not SupplierMaterialCost.objects.exists()
