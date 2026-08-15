"""O comprovante de sangria: papel que aponta para a verdade.

O comprovante existe porque a política de PIN nasceu de "sangria sem
testemunha". Papel sem vínculo com o registro seria só papel.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from shopman.backstage.models import CashMovement, CashShift, POSTerminal
from shopman.backstage.services.receipt_escpos import COLUMNS, ENCODING, cash_movement_receipt
from shopman.backstage.services.receipt_verify import (
    InvalidReceiptCode,
    code_for,
    movement_id_from,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def movimento():
    user = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    shift = CashShift.objects.create(
        terminal=POSTerminal.default(), operator=user, opening_amount_q=10000
    )
    return CashMovement.objects.create(
        shift=shift,
        movement_type="sangria",
        amount_q=15000,
        reason="Retirada para o cofre",
        created_by="marina",
        approved_by="admin",
        created_at=timezone.now(),
    )


# ── O registro do que aconteceu com o papel ───────────────────────────────


def test_o_movimento_nasce_SEM_confirmacao_de_impressao(movimento):
    """⚠️ Assumir 'impresso' sem confirmação transforma papel que faltou em
    papel que alguém escondeu — o oposto do que o comprovante existe para fazer.

    Quem imprime é o navegador do balcão, e ele pode fechar antes de confirmar.
    """
    assert movimento.receipt_status == CashMovement.ReceiptStatus.PENDING
    assert movimento.receipt_at is None


def test_os_quatro_estados_do_papel_existem():
    valores = set(CashMovement.ReceiptStatus.values)
    assert valores == {"pending", "printed", "failed", "skipped"}


# ── O código de conferência ───────────────────────────────────────────────


def test_o_codigo_resolve_para_o_movimento(movimento):
    assert movement_id_from(code_for(movimento.pk)) == movimento.pk


def test_codigo_inventado_NAO_resolve():
    """Sem assinatura, bastaria escrever 'SG-999' num papel qualquer."""
    with pytest.raises(InvalidReceiptCode):
        movement_id_from("SG-999-AAAAAAAA")


def test_codigo_de_outro_movimento_nao_serve_para_este(movimento):
    """Trocar o número no papel tem que quebrar a assinatura."""
    codigo = code_for(movimento.pk)
    adulterado = codigo.replace(f"-{movimento.pk}-", f"-{movimento.pk + 1}-")
    with pytest.raises(InvalidReceiptCode):
        movement_id_from(adulterado)


@pytest.mark.parametrize("lixo", ["", "SG", "SG-1", "XX-1-AAAAAAAA", "SG-abc-AAAAAAAA", None])
def test_codigo_malformado_nao_explode_feio(lixo):
    with pytest.raises(InvalidReceiptCode):
        movement_id_from(lixo)


def test_o_codigo_evita_caracteres_que_se_confundem(movimento):
    """Quem digita o código quando o QR não lê não deve tropeçar em I × 1."""
    assinatura = code_for(movimento.pk).split("-")[2]
    assert not set(assinatura) & set("IO")


# ── O papel ───────────────────────────────────────────────────────────────


def _texto(bytes_do_papel: bytes) -> str:
    return bytes_do_papel.decode(ENCODING, "replace")


def test_o_papel_traz_valor_operador_e_quem_autorizou(movimento):
    papel = _texto(cash_movement_receipt(movimento, verify_code="SG-1-XXXXXXXX", verify_url="https://x/y"))

    assert "150,00" in papel
    assert "marina" in papel
    # Retirada tem DUAS assinaturas; o papel mostra as duas.
    assert "admin" in papel
    assert "Retirada para o cofre" in papel


def test_o_papel_traz_o_codigo_e_o_QR(movimento):
    papel = cash_movement_receipt(movimento, verify_code="SG-1-XXXXXXXX", verify_url="https://x/verificar")

    assert "SG-1-XXXXXXXX".encode(ENCODING) in papel
    assert b"https://x/verificar" in papel
    assert bytes([0x1D, 0x28, 0x6B]) in papel, "faltou o comando de QR"


def test_o_papel_impoe_a_tabela_de_acento(movimento):
    """CP860 é IMPOSTA, não descoberta — o balcão provou que a impressora obedece.

    Sem impor, o acento depende do que veio de fábrica ou de quem mexeu antes.
    """
    papel = cash_movement_receipt(movimento, verify_code="X", verify_url="u")
    assert bytes([0x1B, ord("t"), 3]) in papel
    assert papel.startswith(bytes([0x1B, ord("@")])), "sem reset, herda estado do job anterior"


def test_a_segunda_via_sai_MARCADA(movimento):
    """Sem a marca, dois papéis idênticos circulam e a 2ª via passa por original."""
    original = _texto(cash_movement_receipt(movimento, verify_code="X", verify_url="u"))
    segunda = _texto(cash_movement_receipt(movimento, verify_code="X", verify_url="u", reprint=True))

    assert "2a VIA" not in original
    assert "2a VIA" in segunda


def test_nenhuma_linha_passa_da_largura_do_papel(movimento):
    movimento.reason = "Retirada " * 30  # motivo gigante, digitado sem dó
    papel = _texto(cash_movement_receipt(movimento, verify_code="SG-1-XXXXXXXX", verify_url="https://x/y"))

    for linha in papel.splitlines():
        limpa = "".join(c for c in linha if c.isprintable())
        assert len(limpa) <= COLUMNS, f"linha estourou {COLUMNS} colunas: {limpa!r}"


def test_motivo_vazio_nao_deixa_o_papel_mudo(movimento):
    movimento.reason = ""
    papel = _texto(cash_movement_receipt(movimento, verify_code="X", verify_url="u"))
    assert "Motivo:" in papel


def test_o_que_a_tabela_nao_tem_vira_equivalente_e_nao_lixo(movimento):
    """Travessão, aspas curvas e reticências viram "?" na CP860.

    O operador digita (ou o celular põe sozinho) e o motivo da sangria sairia
    corrompido, parecendo defeito da impressora.
    """
    movimento.reason = "Cofre — “fim de turno” … valor à parte"
    papel = _texto(cash_movement_receipt(movimento, verify_code="X", verify_url="u"))

    assert "?" not in papel, "algum caractere não foi traduzido e virou lixo"
    assert "Cofre - " in papel
    assert '"fim de turno"' in papel
    assert "..." in papel
    # Acento de verdade CONTINUA saindo — a tradução não pode achatar português.
    assert "à parte" in papel
