"""Compras: o que a conformidade V6 com a v4 pôs no servidor (ids C*).

- C23: a contagem de volumes ("Contei N volumes") mora no servidor, por NF:
  abrir a mesma nota em outro dispositivo não pede para contar de novo.
- C22: "Devolver só este item" registra a devolução de UMA linha, com a
  referência própria, sem tocar no estoque.
- C11: o EAN lido na embalagem (ou o da nota) vira EAN do cadastro de compra
  ao confirmar, e o próximo "Ler EAN" acha o item por ele.
- C13: as entradas de hoje vêm marcadas, com a hora.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from shopman.buyman.models import Material, MaterialConversion, Supplier
from shopman.stockman.models import Move, Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.models import ReceiptVolumeCount
from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services import purchase as purchase_service
from shopman.backstage.services.purchase import PurchaseError

CHAVE = "41260812345678000190550010000012341000123459"
EAN_CAIXA = "7891000315507"


@pytest.fixture
def operador(db):
    return User.objects.create_user("doca-v6", password="pw", is_staff=True)


@pytest.fixture
def cenario(db):
    fornecedor = Supplier.objects.create(ref="moinho-v6", name="Moinho V6", document="12.345.678/0001-90")
    manteiga = Material.objects.create(sku="MANT-V6", name="Manteiga sem sal", unit="kg", shelf_life_days=30)
    caixa = MaterialConversion.objects.create(
        material=manteiga, supplier=fornecedor, label="caixa 5 kg", to_base_factor=Decimal("5")
    )
    Position.objects.get_or_create(
        ref="estoque", defaults={"name": "Estoque", "kind": PositionKind.PHYSICAL, "is_saleable": False}
    )
    return {"fornecedor": fornecedor, "manteiga": manteiga, "caixa": caixa}


def _linha(c, **over):
    linha = {
        "id": "l1",
        "materialSku": c["manteiga"].sku,
        "conversionId": str(c["caixa"].pk),
        "purchaseQty": 4,
        "invoicePurchaseQty": "4",
        "invoiceUnit": "CX",
        "costInput": "880,00",
        "invoiceTotal": "880,00",
        "expiryDate": (timezone.localdate() + timedelta(days=20)).isoformat(),
        "lineNote": "",
        "checked": True,
    }
    linha.update(over)
    return linha


class TestVolumesNoServidor:
    def test_contar_grava_por_nf_e_outro_dispositivo_le(self, cenario, operador):
        purchase_service.save_receipt_volumes({"invoiceAccessKey": CHAVE, "counted": 9}, user=operador)
        row = ReceiptVolumeCount.objects.get(invoice_key=CHAVE)
        assert (row.counted, row.counted_by) == (9, "doca-v6")
        assert purchase_service.counted_receipt_volumes(CHAVE) == 9

    def test_recontar_substitui_e_nulo_desfaz(self, cenario, operador):
        purchase_service.save_receipt_volumes({"invoiceAccessKey": CHAVE, "counted": 9}, user=operador)
        purchase_service.save_receipt_volumes({"invoiceAccessKey": CHAVE, "counted": 8}, user=operador)
        assert purchase_service.counted_receipt_volumes(CHAVE) == 8
        purchase_service.save_receipt_volumes({"invoiceAccessKey": CHAVE, "counted": None}, user=operador)
        assert purchase_service.counted_receipt_volumes(CHAVE) is None

    def test_contagem_invalida_e_sem_nf_recusam(self, cenario, operador):
        with pytest.raises(PurchaseError):
            purchase_service.save_receipt_volumes({"invoiceAccessKey": CHAVE, "counted": 0}, user=operador)
        with pytest.raises(PurchaseError):
            purchase_service.save_receipt_volumes({"invoiceAccessKey": "123", "counted": 3}, user=operador)

    def test_a_projecao_devolve_a_contagem(self, cenario, operador):
        projection = build_purchase(active_receipt={"mode": "invoice", "volumesCounted": 7})
        assert projection.activeReceipt.volumesCounted == 7
        assert build_purchase().activeReceipt.volumesCounted is None

    def test_entrada_registrada_apaga_a_contagem(self, cenario, operador):
        purchase_service.save_receipt_volumes({"invoiceAccessKey": CHAVE, "counted": 4}, user=operador)
        purchase_service.confirm_receipt(
            {
                "mode": "invoice",
                "supplierRef": cenario["fornecedor"].ref,
                "invoiceAccessKey": CHAVE,
                "note": "",
                "lines": [_linha(cenario)],
            },
            user=operador,
        )
        assert purchase_service.counted_receipt_volumes(CHAVE) is None


class TestDevolverSoEsteItem:
    def test_devolucao_parcial_tem_referencia_propria_e_nao_mexe_no_estoque(self, cenario, operador):
        antes = Move.objects.count()
        _, mensagem = purchase_service.reject_receipt(
            {
                "mode": "invoice",
                "supplierRef": cenario["fornecedor"].ref,
                "invoiceAccessKey": CHAVE,
                "note": "Avariado",
                "lines": [_linha(cenario, lineNote="Avariado")],
                "partial": True,
            },
            user=operador,
        )
        assert "Devolução do item registrada" in mensagem
        assert "mant-v6" in mensagem
        assert Move.objects.count() == antes

    def test_devolucao_parcial_e_de_um_item_so(self, cenario, operador):
        with pytest.raises(PurchaseError):
            purchase_service.reject_receipt(
                {
                    "mode": "invoice",
                    "supplierRef": cenario["fornecedor"].ref,
                    "invoiceAccessKey": CHAVE,
                    "note": "Avariado",
                    "lines": [_linha(cenario), _linha(cenario, id="l2")],
                    "partial": True,
                },
                user=operador,
            )


class TestEanNoCadastro:
    def test_ean_lido_vira_ean_do_insumo_e_aparece_na_projecao(self, cenario, operador):
        purchase_service.confirm_receipt(
            {
                "mode": "invoice",
                "supplierRef": cenario["fornecedor"].ref,
                "invoiceAccessKey": CHAVE,
                "note": "",
                "lines": [_linha(cenario, scannedEan=EAN_CAIXA)],
            },
            user=operador,
        )
        cenario["manteiga"].refresh_from_db()
        assert cenario["manteiga"].metadata["purchase"]["eans"] == [EAN_CAIXA]
        material = next(m for m in build_purchase().materials if m.sku == "MANT-V6")
        assert material.eans == (EAN_CAIXA,)

    def test_codigo_que_nao_e_gtin_nao_entra(self, cenario, operador):
        purchase_service.confirm_receipt(
            {
                "mode": "invoice",
                "supplierRef": cenario["fornecedor"].ref,
                "invoiceAccessKey": CHAVE,
                "note": "",
                "lines": [_linha(cenario, scannedEan="7891000315508")],  # dígito errado
            },
            user=operador,
        )
        cenario["manteiga"].refresh_from_db()
        assert "eans" not in (cenario["manteiga"].metadata or {}).get("purchase", {})


class TestEntradasDeHoje:
    def test_entrada_de_hoje_vem_marcada_com_a_hora(self, cenario, operador):
        purchase_service.confirm_receipt(
            {
                "mode": "invoice",
                "supplierRef": cenario["fornecedor"].ref,
                "invoiceAccessKey": CHAVE,
                "note": "",
                "lines": [_linha(cenario)],
            },
            user=operador,
        )
        [entrada] = build_purchase().receiptHistory
        assert entrada.receivedToday is True
        assert len(entrada.receivedAtTime) == 5
