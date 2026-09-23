"""`apply_fiscal_ncm`: o que a casa entrega no balcão é bebida, não pó nem pão.

O capítulo 22 da NCM é o das bebidas PRONTAS; o 21.01 e o 21.06 são das
preparações que servem para fazer bebida. O catálogo declarava café solúvel
onde servia uma xícara, e produto de padaria onde servia um Caffè Latte.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from shopman.offerman.models import Product

from config.management.commands.apply_fiscal_ncm import NCM_REVISADO, PERGUNTA_DO_CONTADOR

pytestmark = pytest.mark.django_db


def _product(sku: str, ncm: str = "") -> Product:
    fiscal = {"profile": "own_production", "unit": "UN"}
    if ncm:
        fiscal["ncm"] = ncm
    return Product.objects.create(
        sku=sku, name=sku, unit="un", base_price_q=1000, metadata={"fiscal": fiscal}
    )


def _ncm(sku: str) -> str:
    return Product.objects.get(sku=sku).metadata["fiscal"].get("ncm", "")


def test_a_tabela_so_propoe_bebida_pronta():
    """Tudo que ela toca vai para o capítulo 22, que é o das bebidas prontas."""
    assert all(ncm.startswith("22") for _sku, ncm, _porque in NCM_REVISADO)
    assert all(porque.strip() for _sku, _ncm, porque in NCM_REVISADO)
    codigos = [sku for sku, _n, _p in NCM_REVISADO]
    assert len(set(codigos)) == len(codigos)


def test_as_duas_sodas_ficam_de_fora_da_tabela():
    """A pergunta do Imposto Seletivo não se responde por comando."""
    revisados = {sku for sku, _n, _p in NCM_REVISADO}
    esperando = {sku for sku, _n, _p in PERGUNTA_DO_CONTADOR}
    assert not (revisados & esperando)
    assert esperando == {"SDLA", "CV"}


def test_ensaio_nao_grava():
    _product("CAFL", "19059090")

    out = StringIO()
    call_command("apply_fiscal_ncm", stdout=out)

    assert _ncm("CAFL") == "19059090"
    assert "PADARIA" in out.getvalue()
    assert "nada gravado" in out.getvalue()


def test_apply_troca_o_codigo_da_padaria_pelo_da_bebida():
    _product("CAFL", "19059090")
    _product("SP", "21011110")

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    assert _ncm("CAFL") == "22029900"
    assert _ncm("SP") == "22029900"


def test_preserva_o_resto_do_fiscal():
    """Trocar o NCM não pode apagar o perfil nem a unidade."""
    _product("SP", "21011110")

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    fiscal = Product.objects.get(sku="SP").metadata["fiscal"]
    assert fiscal == {"profile": "own_production", "unit": "UN", "ncm": "22029900"}


def test_nao_encosta_nas_sodas():
    _product("SDLA", "22021000")
    _product("CV", "22021000")

    out = StringIO()
    call_command("apply_fiscal_ncm", "--apply", stdout=out)

    assert _ncm("SDLA") == "22021000"
    assert _ncm("CV") == "22021000"
    assert "Imposto Seletivo" in out.getvalue()


def test_o_cest_vazio_sai_dito_toda_vez():
    """Decisão silenciosa vira esquecimento: o comando repete a razão."""
    _product("SP", "21011110")

    out = StringIO()
    call_command("apply_fiscal_ncm", "--apply", stdout=out)

    assert "CEST fica VAZIO" in out.getvalue()
    assert "substituição" in out.getvalue()


def test_rodar_de_novo_nao_faz_nada():
    _product("SP", "21011110")
    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    out = StringIO()
    call_command("apply_fiscal_ncm", "--apply", stdout=out)

    assert "Nada a revisar" in out.getvalue()


def test_sku_fora_deste_banco_e_dito_e_nao_quebra():
    out = StringIO()
    call_command("apply_fiscal_ncm", "--apply", stdout=out)

    assert "fora do catálogo deste banco" in out.getvalue()


def test_o_seed_nasce_com_o_mesmo_codigo():
    """Um banco novo não pode discordar de um banco que já roda."""
    import ast
    from pathlib import Path

    from django.conf import settings

    fonte = Path(settings.BASE_DIR, "config/management/commands/seed.py").read_text()
    tree = ast.parse(fonte)
    literais = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "22029900" in literais, "o seed não cria nenhuma bebida no NCM revisado"
    for antigo in ("21011110", "21011200", "09024000"):
        assert antigo not in literais, (
            f"o seed ainda cria bebida em {antigo}, que descreve preparação, não bebida pronta"
        )
