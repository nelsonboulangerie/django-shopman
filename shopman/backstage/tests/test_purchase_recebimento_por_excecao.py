"""Compras: recebimento por exceção, com a validade incontornável (UX-C1).

Decisão do dono (03/10/2026): a linha que BATE com a nota entra sem o "ok" linha
a linha, mediante um ato físico (contar os volumes); perecível continua pedindo
validade; toda diferença entre a nota e o que chegou pede motivo; a linha que não
bate continua pedindo o ok dela. Nada além disso se afrouxa.

Chamamos o SERVIÇO direto: o portão de permissão é da view, e tem teste próprio.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from shopman.buyman.models import Material, MaterialConversion, Supplier
from shopman.stockman.models import Batch, Move, Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services import purchase as purchase_service
from shopman.backstage.services.purchase import PurchaseError

#: Emitente = `chave[6:20]` = 12345678000190, o mesmo CNPJ do fornecedor abaixo.
CHAVE = "41260812345678000190550010000012341000123459"


@pytest.fixture
def operador(db):
    return User.objects.create_user("doca-op", password="pw", is_staff=True)


@pytest.fixture
def cenario(db):
    fornecedor = Supplier.objects.create(ref="moinho-sp", name="Moinho São Paulo", document="12.345.678/0001-90")
    farinha = Material.objects.create(sku="FAR-T65", name="Farinha T65", unit="kg")
    manteiga = Material.objects.create(sku="MANT-SS", name="Manteiga sem sal", unit="kg", shelf_life_days=30)
    saco = MaterialConversion.objects.create(
        material=farinha, supplier=fornecedor, label="saco 25 kg", to_base_factor=Decimal("25")
    )
    caixa = MaterialConversion.objects.create(
        material=manteiga, supplier=fornecedor, label="caixa 5 kg", to_base_factor=Decimal("5")
    )
    Position.objects.get_or_create(
        ref="estoque", defaults={"name": "Estoque", "kind": PositionKind.PHYSICAL, "is_saleable": False}
    )
    return {"fornecedor": fornecedor, "farinha": farinha, "manteiga": manteiga, "saco": saco, "caixa": caixa}


def _validade() -> str:
    return (timezone.localdate() + timedelta(days=20)).isoformat()


def _linhas(c):
    """Uma nota de 2 sacos de farinha + 4 caixas de manteiga: 6 volumes."""
    return [
        {
            "id": "l1",
            "materialSku": c["farinha"].sku,
            "conversionId": str(c["saco"].pk),
            "purchaseQty": 2,
            "invoicePurchaseQty": "2",
            "invoiceUnit": "SC",
            "costInput": "360,00",
            "invoiceTotal": "360,00",
            "lineNote": "",
            "checked": False,
        },
        {
            "id": "l2",
            "materialSku": c["manteiga"].sku,
            "conversionId": str(c["caixa"].pk),
            "purchaseQty": 4,
            "invoicePurchaseQty": "4",
            "invoiceUnit": "CX",
            "costInput": "880,00",
            "invoiceTotal": "880,00",
            "expiryDate": _validade(),
            "lineNote": "",
            "checked": False,
        },
    ]


def _payload(c, *, lines=None, counted=6, invoice_volumes=0, mode="invoice"):
    payload = {
        "mode": mode,
        "supplierRef": c["fornecedor"].ref,
        "invoiceAccessKey": CHAVE if mode == "invoice" else "",
        "note": "",
        "invoiceVolumes": invoice_volumes,
        "lines": lines if lines is not None else _linhas(c),
    }
    if counted is not None:
        payload["volumes"] = {"counted": counted}
    return payload


def _erro(payload, user) -> PurchaseError:
    with pytest.raises(PurchaseError) as exc:
        purchase_service.confirm_receipt(payload, user=user)
    return exc.value


@pytest.mark.django_db
def test_tudo_bate_e_volumes_contados_entra_sem_ok_por_linha(cenario, operador):
    purchase_service.confirm_receipt(_payload(cenario), user=operador)

    moves = list(Move.objects.filter(kind="buy").order_by("id"))
    assert [m.metadata["purchase_material_sku"] for m in moves] == ["FAR-T65", "MANT-SS"]
    assert sum(m.delta for m in moves) == Decimal("70")  # 2 × 25 kg + 4 × 5 kg
    for move in moves:
        # Fica escrito COMO a linha foi assinada, quantos volumes, e por quem.
        assert move.metadata["purchase_line_attested_by"] == "volume_count"
        assert move.metadata["purchase_volumes_counted"] == 6
        assert move.metadata["purchase_volumes_expected"] == 6
        assert move.user == operador


@pytest.mark.django_db
def test_volumes_errados_bloqueia_com_motivo(cenario, operador):
    erro = _erro(_payload(cenario, counted=5), operador)

    assert erro.code == "receipt_volumes_mismatch"
    assert erro.field == "volumes.counted"
    assert "contou 5" in str(erro) and "6" in str(erro)
    assert not Move.objects.filter(kind="buy").exists()


@pytest.mark.django_db
def test_sem_contagem_nao_entra(cenario, operador):
    erro = _erro(_payload(cenario, counted=None), operador)

    assert erro.code == "receipt_volumes_required"
    assert not Move.objects.filter(kind="buy").exists()


@pytest.mark.django_db
def test_perecivel_sem_validade_bloqueia_mesmo_com_volumes(cenario, operador):
    linhas = _linhas(cenario)
    linhas[1]["expiryDate"] = ""

    erro = _erro(_payload(cenario, lines=linhas), operador)

    assert erro.code == "expiry_required"
    assert erro.field == "lines.1.expiryDate"
    assert not Move.objects.filter(kind="buy").exists()


@pytest.mark.django_db
def test_divergencia_sem_motivo_bloqueia_mesmo_conferida(cenario, operador):
    """A nota diz 4 caixas, chegaram 3: não entra em silêncio, nem com o ok."""
    linhas = _linhas(cenario)
    linhas[1].update({"purchaseQty": 3, "costInput": "660,00", "checked": True})

    erro = _erro(_payload(cenario, lines=linhas, counted=5), operador)

    assert erro.code == "receipt_difference_reason_required"
    assert erro.field == "lines.1.lineNote"
    assert not Move.objects.filter(kind="buy").exists()


@pytest.mark.django_db
def test_divergencia_com_motivo_e_ok_entra_e_a_contagem_desconta_a_falta(cenario, operador):
    linhas = _linhas(cenario)
    linhas[1].update({"purchaseQty": 3, "costInput": "660,00", "lineNote": "Faltou", "checked": True})

    # 6 da nota, menos a caixa que faltou: 5 volumes na doca.
    purchase_service.confirm_receipt(_payload(cenario, lines=linhas, counted=5), user=operador)

    farinha = Move.objects.get(kind="buy", metadata__purchase_material_sku="FAR-T65")
    manteiga = Move.objects.get(kind="buy", metadata__purchase_material_sku="MANT-SS")
    assert farinha.metadata["purchase_line_attested_by"] == "volume_count"
    assert manteiga.metadata["purchase_line_attested_by"] == "line_check"
    assert manteiga.metadata["purchase_line_note"] == "Faltou"
    assert manteiga.delta == Decimal("15")


@pytest.mark.django_db
def test_linha_que_nao_bate_ainda_pede_o_ok(cenario, operador):
    """Valor diferente do da nota: não é exceção silenciosa, é item para conferir."""
    linhas = _linhas(cenario)
    linhas[0]["costInput"] = "300,00"

    erro = _erro(_payload(cenario, lines=linhas), operador)

    assert erro.code == "receipt_line_unchecked"
    assert erro.field == "lines.0.checked"


@pytest.mark.django_db
def test_embalagem_que_diverge_da_nota_pede_o_ok(cenario, operador):
    linhas = _linhas(cenario)
    linhas[0]["conversionSuggestion"] = {"label": "saco 20 kg", "factor": "20"}

    erro = _erro(_payload(cenario, lines=linhas), operador)

    assert erro.code == "receipt_line_unchecked"


@pytest.mark.django_db
def test_entrada_sem_nota_continua_pedindo_ok_por_linha(cenario, operador):
    erro = _erro(_payload(cenario, mode="manual"), operador)

    assert erro.code == "receipt_line_unchecked"


@pytest.mark.django_db
def test_linha_a_granel_usa_os_volumes_declarados_na_nota(cenario, operador):
    """Manteiga vendida em KG, sem embalagem cadastrada: só o qVol da nota diz os volumes."""
    linhas = _linhas(cenario)
    linhas[1].update({"conversionId": None, "purchaseQty": 20, "invoicePurchaseQty": "20", "invoiceUnit": "KG"})

    sem_qvol = _erro(_payload(cenario, lines=linhas, counted=6), operador)
    assert sem_qvol.code == "receipt_line_unchecked"

    purchase_service.confirm_receipt(_payload(cenario, lines=linhas, counted=6, invoice_volumes=6), user=operador)
    assert Move.objects.filter(kind="buy").count() == 2


@pytest.mark.django_db
def test_ok_em_todas_as_linhas_dispensa_a_contagem(cenario, operador):
    """O caminho de antes continua valendo: quem conferiu item a item não conta volumes."""
    linhas = _linhas(cenario)
    for linha in linhas:
        linha["checked"] = True

    purchase_service.confirm_receipt(_payload(cenario, lines=linhas, counted=None), user=operador)

    assert {m.metadata["purchase_line_attested_by"] for m in Move.objects.filter(kind="buy")} == {"line_check"}


@pytest.mark.django_db
def test_validade_da_ultima_entrega_vira_atalho_so_enquanto_vale(cenario, operador):
    purchase_service.confirm_receipt(_payload(cenario), user=operador)

    manteiga = next(m for m in build_purchase().materials if m.sku == "MANT-SS")
    assert manteiga.lastDeliveryExpiry == _validade()

    Batch.objects.filter(sku="MANT-SS").update(expiry_date=timezone.localdate() - timedelta(days=1))
    manteiga = next(m for m in build_purchase().materials if m.sku == "MANT-SS")
    assert manteiga.lastDeliveryExpiry == ""
