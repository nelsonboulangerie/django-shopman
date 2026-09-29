"""A equivalência aproximada passa a dizer de onde veio, e a casa pode calibrá-la.

Pedido dele em 24/09/2026, sobre o peso da folha de louro fresca — que nenhuma
fonte sabe dizer: *"alguma anotação para calibrar o peso seria bom"*. Ao procurar
onde a anotação cabia, apareceu que o buraco era maior que o louro: o ovo a 50 g
e o limão a 100 g estavam no banco exatamente como estaria um número pesado na
casa, e ninguém sabia qual dos três calibrar primeiro.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from shopman.buyman.models import Material, MaterialConversion

pytestmark = pytest.mark.django_db


def _conversao(sku="OVOS", label="ovos", fator="0.050", **kwargs) -> MaterialConversion:
    material, _ = Material.objects.get_or_create(sku=sku, defaults={"name": sku, "unit": "kg"})
    return MaterialConversion.objects.create(
        material=material, label=label, to_base_factor=Decimal(fator),
        kind=kwargs.pop("kind", MaterialConversion.Kind.APPROXIMATE), **kwargs,
    )


def _rodar(**kwargs) -> str:
    saida = StringIO()
    call_command("calibrate_conversions", stdout=saida, stderr=saida, **kwargs)
    return saida.getvalue()


# ------------------------------------------------------ o que falta calibrar


def test_sem_procedencia_conta_como_por_calibrar():
    """O silêncio de hoje é de fator que ninguém sabe de onde veio.

    Tratá-lo como declarado esconderia exatamente o que este campo mostra.
    """
    conversao = _conversao()
    assert conversao.source == ""
    assert conversao.needs_calibration is True
    assert "OVOS" in _rodar()


def test_pesada_na_casa_sai_da_lista():
    _conversao(source=MaterialConversion.Source.HOUSE_SCALE)
    assert "OVOS" not in _rodar()


def test_declarada_pelo_dono_sai_da_lista():
    """A palavra dele vale a pesagem: ele conhece a salsicha que compra."""
    _conversao(sku="SALSICHA-VIENNA", label="salsichas", source=MaterialConversion.Source.OWNER)
    assert "SALSICHA" not in _rodar()


def test_convencionada_nunca_entra_na_lista():
    """"1 saco = 25 kg" é contrato do fornecedor, não equivalência física.

    Calibrar ali seria duvidar da nota — e o conserto de uma embalagem que mudou
    é corrigir a embalagem, não pesar o saco.
    """
    _conversao(sku="FARINHA", label="saco 25 kg", fator="25",
               kind=MaterialConversion.Kind.CONVENTIONAL)
    assert "FARINHA" not in _rodar()


def test_sem_nada_pendente_o_relatorio_diz_isso():
    _conversao(source=MaterialConversion.Source.HOUSE_SCALE)
    assert "Nenhuma equivalência por calibrar" in _rodar()


# --------------------------------------------------------------- a pesagem


def test_o_ensaio_nao_grava():
    conversao = _conversao()
    saida = _rodar(weigh=["OVOS:ovos=0.058"])
    conversao.refresh_from_db()
    assert conversao.to_base_factor == Decimal("0.050000")
    assert "pesaria" in saida


def test_a_pesagem_grava_o_fator_E_o_carimbo():
    """O número sem o carimbo é o mesmo problema de novo, um passo adiante."""
    conversao = _conversao()
    _rodar(weigh=["OVOS:ovos=0.058"], apply=True)

    conversao.refresh_from_db()
    assert conversao.to_base_factor == Decimal("0.058000")
    assert conversao.source == MaterialConversion.Source.HOUSE_SCALE
    assert conversao.needs_calibration is False


def test_o_relatorio_mostra_o_quanto_o_chute_errava():
    """16% de erro no ovo muda a lista de compras; sem o número ninguém percebe."""
    _conversao()
    assert "+16.0%" in _rodar(weigh=["OVOS:ovos=0.058"])


# ---------------------------------------------------------------- as recusas


@pytest.mark.parametrize("texto", ["OVOS", "OVOS:ovos", "OVOS=0.058", "OVOS:ovos=abc"])
def test_forma_errada_recusa_dizendo_a_forma_certa(texto):
    _conversao()
    with pytest.raises(CommandError, match="SKU:rótulo=fator"):
        _rodar(weigh=[texto])


@pytest.mark.parametrize("fator", ["0", "-0.058"])
def test_fator_que_nao_e_positivo_recusa(fator):
    _conversao()
    with pytest.raises(CommandError, match="maior que zero"):
        _rodar(weigh=[f"OVOS:ovos={fator}"])


def test_calibrar_o_que_nao_existe_recusa_em_vez_de_criar():
    """Criar equivalência é outro gesto: ele declara o rótulo que a bancada usa."""
    with pytest.raises(CommandError, match="não existe"):
        _rodar(weigh=["LOURO:folhas=0.0007"], apply=True)


def test_calibrar_uma_CONVENCIONADA_recusa_nomeando_a_razao():
    _conversao(sku="FARINHA", label="saco 25 kg", fator="25",
               kind=MaterialConversion.Kind.CONVENTIONAL)
    with pytest.raises(CommandError, match="duvidar da nota"):
        _rodar(weigh=["FARINHA:saco 25 kg=24"], apply=True)


def test_uma_recusa_no_meio_nao_grava_a_que_veio_antes():
    """A pesagem é um gesto só: meia calibragem é pior que nenhuma."""
    conversao = _conversao()
    with pytest.raises(CommandError):
        _rodar(weigh=["OVOS:ovos=0.058", "NAO-EXISTE:x=1"], apply=True)
    conversao.refresh_from_db()
    assert conversao.to_base_factor == Decimal("0.050000")
