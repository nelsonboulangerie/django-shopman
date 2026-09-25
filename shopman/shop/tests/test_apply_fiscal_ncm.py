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

from config.management.commands.apply_fiscal_ncm import AVISOS, NCM_REVISADO

pytestmark = pytest.mark.django_db


def _product(sku: str, ncm: str = "") -> Product:
    fiscal = {"profile": "standard", "unit": "UN"}
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


def test_a_soda_da_casa_entra_como_bebida_preparada():
    """Decisão dele em 23/09, com o argumento da embalagem por trás.

    O Imposto Seletivo sobre bebida açucarada só alcança o que está em
    embalagem primária destinada ao consumidor final. Soda servida no copo não
    tem — então o IS não pesa na escolha, e sobra a classificação pura.
    """
    revisados = {sku for sku, _n, _p in NCM_REVISADO}
    assert "SDLA" in revisados


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
    assert fiscal == {"profile": "standard", "unit": "UN", "ncm": "22029900"}


def test_o_aviso_do_engarrafamento_sai_toda_vez():
    """O que muda a conta é a EMBALAGEM, e isso tem de ficar dito.

    Servida no copo, a soda não é alcançada pelo Imposto Seletivo. Engarrafada
    para vender, passa a ser — e a casa vira contribuinte.
    """
    _product("SDLA", "22021000")

    out = StringIO()
    call_command("apply_fiscal_ncm", "--apply", stdout=out)

    assert _ncm("SDLA") == "22029900"
    texto = out.getvalue()
    assert "ENGARRAFAR" in texto and "Imposto Seletivo" in texto


def test_o_cest_vazio_sai_dito_toda_vez():
    """Decisão silenciosa vira esquecimento: o comando repete a razão."""
    _product("SP", "21011110")

    out = StringIO()
    call_command("apply_fiscal_ncm", "--apply", stdout=out)

    assert "CEST vazio" in out.getvalue()
    assert "substituição" in out.getvalue()


def test_todo_aviso_tem_texto():
    assert AVISOS and all(a.strip() for a in AVISOS)


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


# ── CEST de quem a casa faz ────────────────────────────────────────────────


def test_o_cest_da_casa_sai_do_ncm():
    """Pão de 1905.90.90 leva 17.062.00 — identificação, não tributação."""
    _product("CRO", "19059090")
    _product("FORMA", "19059010")
    _product("RTAT", "20059900")

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    cests = {sku: Product.objects.get(sku=sku).metadata["fiscal"].get("cest") for sku in ("CRO", "FORMA", "RTAT")}
    assert cests == {"CRO": "1706200", "FORMA": "1706000", "RTAT": "1709200"}
    assert Product.objects.get(sku="CRO").metadata["fiscal"]["profile"] == "standard"


def test_cest_ja_escrito_fica():
    produto = _product("CRO", "19059090")
    produto.metadata = {"fiscal": {**produto.metadata["fiscal"], "cest": "1705300"}}
    produto.save()

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    assert Product.objects.get(sku="CRO").metadata["fiscal"]["cest"] == "1705300"


def test_bebida_preparada_segue_sem_cest():
    _product("SP", "22029900")

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    assert "cest" not in Product.objects.get(sku="SP").metadata["fiscal"]


def test_todo_cest_da_casa_bate_com_o_ncm_no_anexo():
    from shopman.fiscalman.cest_table import cest_ncm_warnings

    from config.management.commands.apply_fiscal_ncm import HOUSE_CEST_BY_NCM

    for ncm, cest in HOUSE_CEST_BY_NCM.items():
        assert cest_ncm_warnings(ncm, cest) == [], (ncm, cest)


# ── Pão de forma é 1905.90.10; o resto dos pães, 1905.90.90 ────────────────


def test_baguete_sai_do_ncm_de_pao_de_forma_e_o_cest_acompanha():
    produto = _product("TRADI", "19059010")
    produto.metadata = {"fiscal": {**produto.metadata["fiscal"], "cest": "1706000"}}
    produto.save()

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    fiscal = Product.objects.get(sku="TRADI").metadata["fiscal"]
    assert (fiscal["ncm"], fiscal["cest"]) == ("19059090", "1706200")


def test_pao_de_forma_fica_no_1905_90_10():
    _product("FORMA", "19059010")

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    fiscal = Product.objects.get(sku="FORMA").metadata["fiscal"]
    assert (fiscal["ncm"], fiscal["cest"]) == ("19059010", "1706000")


def test_cest_escrito_a_mao_nao_acompanha_a_troca_de_ncm():
    produto = _product("CI", "19059010")
    produto.metadata = {"fiscal": {**produto.metadata["fiscal"], "cest": "1705000"}}
    produto.save()

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    assert Product.objects.get(sku="CI").metadata["fiscal"]["cest"] == "1705000"


def test_nenhum_pao_da_tabela_vai_para_o_1905_90_20():
    from config.management.commands.apply_fiscal_ncm import BREAD_NCM

    assert {ncm for _sku, ncm, _porque in BREAD_NCM} == {"19059090"}
    assert "FORMA" not in {sku for sku, _ncm, _porque in BREAD_NCM}



def test_ncm_corrigido_da_revenda_e_da_despensa_mantem_o_cest():
    camembert = _product("QUEIJO-CAMEMBERT-ILEDEFRANCE-125", "04069020")
    camembert.metadata = {"fiscal": {**camembert.metadata["fiscal"], "cest": "1702400"}}
    camembert.save()
    tapenade = _product("TPND", "20059900")
    tapenade.metadata = {"fiscal": {**tapenade.metadata["fiscal"], "cest": "1709200"}}
    tapenade.save()

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    queijo = Product.objects.get(sku="QUEIJO-CAMEMBERT-ILEDEFRANCE-125").metadata["fiscal"]
    assert (queijo["ncm"], queijo["cest"]) == ("04069030", "1702400")
    pasta = Product.objects.get(sku="TPND").metadata["fiscal"]
    assert (pasta["ncm"], pasta["cest"]) == ("20057000", "1709200")



# ── Sanduíches, salsicha e a ficha do croque ───────────────────────────────


def test_sanduiche_com_embutido_predominante_vai_ao_capitulo_16_e_o_cest_acompanha():
    for sku in ("HOD", "JB"):
        produto = _product(sku, "19059090")
        produto.metadata = {"fiscal": {**produto.metadata["fiscal"], "cest": "1706200"}}
        produto.save()
    _product("CQCOM", "19059090")

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    hot_dog = Product.objects.get(sku="HOD").metadata["fiscal"]
    assert (hot_dog["ncm"], hot_dog["cest"]) == ("16010000", "1707600")
    jambon = Product.objects.get(sku="JB").metadata["fiscal"]
    assert (jambon["ncm"], jambon["cest"]) == ("16024100", "1707904")
    assert _ncm("CQCOM") == "19059090"


def test_a_salsicha_comprada_guarda_o_ncm_da_nota_do_fornecedor():
    from shopman.buyman.models import Material

    Material.objects.create(sku="SALSICHA-VIENNA", name="Salsicha vienna artesanal", unit="g")

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    assert Material.objects.get(sku="SALSICHA-VIENNA").metadata["ncm"] == "16024100"


def test_a_ficha_do_croque_carrega_o_limite_de_20_por_cento_de_presunto():
    from shopman.craftsman.models import Recipe

    from config.management.commands.apply_fiscal_ncm import CROQUE_FISCAL_NOTE

    _product("CQCOM", "19059090")
    Recipe.objects.create(ref="croque-complet", name="Croque Complet", output_sku="CQCOM", batch_size=1)

    call_command("apply_fiscal_ncm", "--apply", stdout=StringIO())

    assert Recipe.objects.get(ref="croque-complet").meta["fiscal_note"] == CROQUE_FISCAL_NOTE
    assert "20%" in CROQUE_FISCAL_NOTE
