"""`apply_grocery_catalog`: a Mercearia real entra no catálogo — no PDV, e de longe só com foto.

A tabela mora em `config/` (é dado do Nelson). O seed chama a mesma função, então
um banco novo nasce com a Mercearia que o comando aplica num banco que já roda.
"""

from __future__ import annotations

from dataclasses import replace
from io import StringIO

import pytest
from django.core.management import call_command
from shopman.buyman.models import Material
from shopman.fiscalman.classification import from_metadata, resolve_fiscal_item
from shopman.offerman import get_social_attributes
from shopman.offerman.contrib.social.schema import gtin_is_valid
from shopman.offerman.models import Collection, Listing, ListingItem, Product

from config.management.commands import apply_grocery_catalog as command
from config.management.commands.apply_grocery_catalog import (
    GIFT_BOXES,
    GROCERY,
    LEFT_OUT,
    OWNER_PACKAGE,
    REAL_PLACEHOLDERS,
    WEB_UNCONFIRMED,
    apply_grocery,
)

DIJON = "MOSTARDA-DIJON-MAILLE-215"
VALE_DO_TESTO = "QUEIJO-VALEDOTESTO-POMERODE"


@pytest.fixture
def catalog(db):
    Collection.objects.create(ref="mercearia", name="Mercearia", is_active=True)
    for ref in ("pdv", "web", "whatsapp", "ifood"):
        Listing.objects.create(ref=ref, name=ref, is_active=True)


def _refs(sku: str) -> set[str]:
    return set(ListingItem.objects.filter(product__sku=sku).values_list("listing__ref", flat=True))


# ── A tabela ──────────────────────────────────────────────────────────────


def test_a_tabela_so_tem_item_vendavel_sem_mentir():
    skus = [item.sku for item in GROCERY]
    assert len(skus) == len(set(skus))
    assert not set(skus) & set(LEFT_OUT)
    for item in GROCERY:
        if item.unit == "kg":
            # A quilo: sem GTIN de embalagem (a balança imprime código interno).
            assert item.gtin == "" and item.weight_g is None, item.sku
        else:
            assert item.unit == "un", item.sku
            assert item.price_q > 0, item.sku
            assert gtin_is_valid(item.gtin), item.sku
        # Revenda: sem ST (102/5102) ou na ST do PR (500/5405), sempre com o CEST
        # do Anexo XVII quando o NCM tem um.
        assert item.profile in {"resale_common", "resale"}, item.sku
        fiscal = {"profile": item.profile, "ncm": item.ncm, "unit": item.unit.upper()}
        if item.cest:
            fiscal["cest"] = item.cest
        classification = from_metadata({"fiscal": fiscal})
        assert not classification.errors(), item.sku
        resolved = resolve_fiscal_item(classification)
        expected = ("5405", "500") if item.profile == "resale" else ("5102", "102")
        assert (resolved["cfop"], resolved["icms_situacao_tributaria"]) == expected, item.sku
        assert resolved.get("cest", "") == item.cest, item.sku


def test_a_tabela_nao_repete_sku_que_o_seed_ja_semeia():
    """Os placeholders da despensa são do seed; a revenda nova é só desta tabela."""
    import inspect

    from config.management.commands import seed

    source = inspect.getsource(seed.Command._seed_catalog)
    for item in (*GROCERY, *GIFT_BOXES):
        assert f'"{item.sku}"' not in source, item.sku


def test_gtin_repetido_nao_entra_em_dois_produtos():
    gtins = [item.gtin for item in GROCERY if item.gtin]
    assert len(gtins) == len(set(gtins))


# ── O comando ─────────────────────────────────────────────────────────────


def test_a_manteiga_president_abre_em_insumo_pesado_e_quem_declarou_manda(catalog):
    call_command("apply_grocery_catalog", "--apply", stdout=StringIO())

    tablete = Material.objects.get(sku="MANTEIGA-SAL-PRESIDENT-200")
    # Abre no insumo que as fichas já usam: nenhuma ficha precisa mudar.
    assert tablete.metadata["opens_into"] == {
        "sku": "MANTEIGA-PRESIDENT-COM-SAL", "quantity": "0.200", "shelf_life_days": 30,
    }
    assert Material.objects.get(sku="MANTEIGA-PRESIDENT-COM-SAL").unit == "kg"

    # O que o operador mudar no Compras não é desfeito por rodar de novo.
    tablete.metadata = {**tablete.metadata, "opens_into": {"sku": "OUTRO", "quantity": "0.2"}}
    tablete.save()
    call_command("apply_grocery_catalog", "--apply", stdout=StringIO())
    assert Material.objects.get(sku="MANTEIGA-SAL-PRESIDENT-200").metadata["opens_into"]["sku"] == "OUTRO"


def test_cria_a_revenda_so_no_pdv(catalog):
    call_command("apply_grocery_catalog", "--apply", stdout=StringIO())

    dijon = Product.objects.get(sku=DIJON)
    assert (dijon.name, dijon.base_price_q, dijon.unit, dijon.unit_weight_g) == (
        "Mostarda Dijon Maille 215g", 3500, "un", 215,
    )
    assert dijon.is_sellable and not dijon.is_published
    # Mostarda preparada está na ST do PR (17.038.00): revenda com ST.
    assert dijon.metadata["fiscal"] == {"profile": "resale", "ncm": "21033021", "unit": "UN", "cest": "1703800"}
    assert "purchase" not in dijon.metadata
    # Comprável: o cadastro de compra do MESMO SKU, na mesma unidade.
    compra = Material.objects.get(sku=DIJON)
    assert (compra.name, compra.unit, compra.is_active) == (dijon.name, "un", True)
    social = get_social_attributes(dijon)
    assert (social.brand, social.gtin) == ("Maille", "3036810201280")
    assert dijon.collection_items.get().collection.ref == "mercearia"
    assert _refs(DIJON) == {"pdv"}
    assert ListingItem.objects.get(product=dijon).price_q == 3500
    assert Product.objects.filter(sku__in=[i.sku for i in GROCERY]).count() == len(GROCERY)
    assert not Product.objects.filter(sku__in=LEFT_OUT).exists()


def test_ensaio_nao_grava(catalog):
    out = StringIO()
    call_command("apply_grocery_catalog", stdout=out)

    assert DIJON in out.getvalue()
    assert "QUEIJO-VALEDOTESTO-POMERODE" in out.getvalue()
    assert not Product.objects.filter(sku=DIJON).exists()


def test_idempotente(catalog):
    apply_grocery(apply=True)
    report = apply_grocery(apply=True)

    assert report["created"] == []
    assert report["updated"] == []
    assert report["listed"] == []
    assert report["conflicts"] == []
    assert ListingItem.objects.filter(product__sku=DIJON).count() == 1
    assert Product.objects.get(sku=DIJON).collection_items.count() == 1


def test_gtin_invalido_e_recusado(catalog, monkeypatch):
    torto = replace(GROCERY[0], gtin="7898655520011")  # dígito verificador errado
    monkeypatch.setattr(command, "GROCERY", (torto,))

    report = apply_grocery(apply=True)

    assert report["refused"] == [(torto.sku, "GTIN inválido")]
    assert not Product.objects.filter(sku=torto.sku).exists()


def test_sem_foto_nao_entra_na_loja_online_e_sai_se_estiver(catalog):
    apply_grocery(apply=True)
    dijon = Product.objects.get(sku=DIJON)
    ListingItem.objects.create(listing=Listing.objects.get(ref="web"), product=dijon, price_q=3500)

    report = apply_grocery(apply=True)

    assert _refs(DIJON) == {"pdv"}
    assert (DIJON, "web") in report["unlisted"]


def test_com_foto_entra_nos_canais_remotos(catalog):
    apply_grocery(apply=True)
    Product.objects.filter(sku=DIJON).update(image_url="https://img.example.com/dijon.webp")

    apply_grocery(apply=True)

    assert _refs(DIJON) == {"pdv", "web", "whatsapp", "ifood"}


def test_curadoria_do_gestor_vence(catalog):
    apply_grocery(apply=True)
    Product.objects.filter(sku=DIJON).update(name="Dijon Maille", base_price_q=3900)

    report = apply_grocery(apply=True)

    dijon = Product.objects.get(sku=DIJON)
    assert (dijon.name, dijon.base_price_q) == ("Dijon Maille", 3900)
    assert {(sku, field) for sku, field, *_ in report["conflicts"]} == {
        (DIJON, "name"), (DIJON, "base_price_q"),
    }


# ── Placeholders que viram o produto real ──────────────────────────────────


def test_placeholder_vira_o_produto_real_e_a_listagem_acompanha(catalog):
    rtat = Product.objects.create(
        sku="RTAT", name="Patê de Ratatouille", unit="un", base_price_q=2400, unit_weight_g=170,
        metadata={"price_tbd": True},
    )
    ListingItem.objects.create(listing=Listing.objects.get(ref="pdv"), product=rtat, price_q=2400)

    call_command("apply_grocery_catalog", "--apply", stdout=StringIO())

    rtat.refresh_from_db()
    assert (rtat.name, rtat.base_price_q, rtat.unit_weight_g) == ("Ratatouille 90g", 1800, 90)
    assert "price_tbd" not in rtat.metadata
    assert ListingItem.objects.get(product=rtat).price_q == 1800


def test_placeholder_que_o_gestor_ja_mexeu_fica(catalog):
    Product.objects.create(sku="TPND", name="Tapenade da Casa", unit="un", base_price_q=2400)

    report = apply_grocery(apply=True)

    tapenade = Product.objects.get(sku="TPND")
    assert tapenade.name == "Tapenade da Casa"
    assert tapenade.base_price_q == 2900
    assert ("TPND", "name", "Tapenade da Casa", "Tapenade Azeitonas Pretas 100g") in report["conflicts"]


def test_os_placeholders_reais_batem_com_o_seed():
    """O seed já nasce com o nome/preço real; o comando só troca num banco vivo."""
    import inspect

    from config.management.commands import seed

    source = inspect.getsource(seed.Command._seed_catalog)
    for real in REAL_PLACEHOLDERS:
        assert f'("{real.sku}", "{real.name}"' in source, real.sku


# ── A quilo, caixas presente e GTIN da web ────────────────────────────────


def test_queijo_a_quilo_nasce_cadastrado_sem_gtin_e_fora_da_venda_sem_preco(catalog):
    """Preço zero não vende (dono, 24/09): cadastrado, sim; vendável, não."""
    report = apply_grocery(apply=True)

    queijo = Product.objects.get(sku=VALE_DO_TESTO)
    assert (queijo.unit, queijo.base_price_q, queijo.unit_weight_g) == ("kg", 0, None)
    assert not queijo.is_sellable
    assert get_social_attributes(queijo).gtin == ""
    assert queijo.metadata["fiscal"]["unit"] == "KG"
    item = ListingItem.objects.get(product=queijo)
    assert item.listing.ref == "pdv" and not item.is_sellable
    assert [sku for sku, _ in report["no_price"]] == [VALE_DO_TESTO]


def test_item_sem_preco_que_estava_a_venda_sai_da_venda(catalog):
    apply_grocery(apply=True)
    Product.objects.filter(sku=VALE_DO_TESTO).update(is_sellable=True)
    ListingItem.objects.filter(product__sku=VALE_DO_TESTO).update(is_sellable=True)

    report = apply_grocery(apply=True)

    assert not Product.objects.get(sku=VALE_DO_TESTO).is_sellable
    assert not ListingItem.objects.get(product__sku=VALE_DO_TESTO).is_sellable
    assert (VALE_DO_TESTO, ["venda: desligada até ter preço"]) in report["updated"]


def test_frutas_vermelhas_se_acham_por_4_frutas(catalog):
    """"4 fruits" é o nome francês do que o brasileiro chama de frutas vermelhas."""
    apply_grocery(apply=True)

    for sku in ("GELEIA-FRUTASVERM-STDALFOUR-284", "GELEIA-FRUTASVERM-STDALFOUR-28"):
        assert "4 frutas" in set(Product.objects.get(sku=sku).keywords.names()), sku
    assert "GELEIA-4FRUTAS-STDALFOUR-284" not in LEFT_OUT


def test_item_a_quilo_com_gtin_e_recusado(catalog, monkeypatch):
    queijo = next(i for i in GROCERY if i.sku == VALE_DO_TESTO)
    monkeypatch.setattr(command, "GROCERY", (replace(queijo, gtin="2000000000008"),))

    report = apply_grocery(apply=True)

    assert report["refused"] == [(VALE_DO_TESTO, "item a quilo não leva GTIN de embalagem")]


def test_a_origem_do_gtin_fica_marcada(catalog):
    apply_grocery(apply=True)

    brie = Product.objects.get(sku="CREME-BRIE-POMERODE-90")
    assert brie.metadata["gtin_source"] == WEB_UNCONFIRMED
    ancienne = Product.objects.get(sku="MOSTARDA-ANCIENNE-MAILLE-210")
    assert ancienne.metadata["gtin_source"] == OWNER_PACKAGE
    assert "gtin_source" not in Product.objects.get(sku=DIJON).metadata


def test_a_embalagem_troca_a_origem_da_web(catalog):
    """O GTIN já estava certo; só a origem muda quando o dono lê o pote."""
    apply_grocery(apply=True)
    ancienne = Product.objects.get(sku="MOSTARDA-ANCIENNE-MAILLE-210")
    ancienne.metadata = {**ancienne.metadata, "gtin_source": WEB_UNCONFIRMED}
    ancienne.save()

    report = apply_grocery(apply=True)

    assert Product.objects.get(sku="MOSTARDA-ANCIENNE-MAILLE-210").metadata["gtin_source"] == OWNER_PACKAGE
    assert ("MOSTARDA-ANCIENNE-MAILLE-210", [f"origem do GTIN: {OWNER_PACKAGE}"]) in report["updated"]


def test_caixa_presente_e_produto_da_casa_so_no_pdv(catalog):
    apply_grocery(apply=True)

    for box in GIFT_BOXES:
        caixa = Product.objects.get(sku=box.sku)
        assert (caixa.name, caixa.base_price_q) == (box.name, box.price_q)
        assert caixa.is_sellable and not caixa.is_published
        assert "purchase" not in caixa.metadata
        assert get_social_attributes(caixa).gtin == ""
        assert _refs(box.sku) == {"pdv"}


# ── A venda antiga do Yooga volta ao produto ──────────────────────────────


def test_os_nomes_do_yooga_apontam_para_skus_da_tabela():
    known = {item.sku for item in GROCERY} | {box.sku for box in GIFT_BOXES}
    assert set(command.YOOGA_NAMES.values()) <= known


def test_de_para_do_yooga_volta_ao_produto_real(catalog):
    from shopman.backstage.models import ProductAlias

    qp = Product.objects.create(sku="QP", name="Queijo Pomerode", unit="un", base_price_q=3200)
    outro = Product.objects.create(sku="CRO", name="Croissant", unit="un", base_price_q=1000)
    solto = ProductAlias.objects.create(source="yooga", external_name="Mostarda Dijon Maille 215g", status="confirmed")
    no_placeholder = ProductAlias.objects.create(
        source="yooga", external_name="Queijo Vale do Testo Pomerode  3m", status="confirmed", product=qp,
    )
    curado = ProductAlias.objects.create(
        source="yooga", external_name="Caixa Presente Nice", status="confirmed", product=outro,
    )

    report = apply_grocery(apply=True)

    solto.refresh_from_db()
    no_placeholder.refresh_from_db()
    curado.refresh_from_db()
    assert solto.product.sku == DIJON
    assert no_placeholder.product.sku == VALE_DO_TESTO
    assert curado.product == outro  # curadoria de alguém: fica
    assert len(report["aliases"]) == 2
    assert apply_grocery(apply=True)["aliases"] == []


def test_item_a_quilo_nao_vai_para_canal_remoto_nem_com_foto(catalog):
    """O carrinho online só aceita unidade inteira: quem pesa é o balcão."""
    apply_grocery(apply=True)
    queijo = Product.objects.get(sku=VALE_DO_TESTO)
    Product.objects.filter(pk=queijo.pk).update(image_url="https://img.example.com/queijo.webp")
    ListingItem.objects.create(listing=Listing.objects.get(ref="web"), product=queijo, price_q=0)

    report = apply_grocery(apply=True)

    assert _refs(VALE_DO_TESTO) == {"pdv"}
    assert (VALE_DO_TESTO, "web") in report["unlisted"]



# ── CEST e perfil fiscal ──────────────────────────────────────────────────


def test_mercearia_no_perfil_antigo_e_reclassificada(catalog):
    """Quem nasceu `own_production` sem CEST (a Mercearia de antes) ganha o da tabela."""
    queijo = Product.objects.create(
        sku="QUEIJO-BRIE-ILEDEFRANCE-25", name="Queijo Mini Brie Ile de France 25g", unit="un",
        base_price_q=1000, metadata={"fiscal": {"profile": "own_production", "ncm": "04069030", "unit": "UN"}},
    )

    report = apply_grocery(apply=True)

    queijo.refresh_from_db()
    assert queijo.metadata["fiscal"] == {
        "profile": "resale_common", "ncm": "04069030", "unit": "UN", "cest": "1702400",
    }
    assert any(sku == queijo.sku and "fiscal: perfil resale_common" in lines[0]
               for sku, lines in report["updated"])


def test_classificacao_curada_fica_e_sai_como_divergencia(catalog):
    Product.objects.create(
        sku="MANTEIGA-SAL-PRESIDENT-200", name="Manteiga Extra com Sal Président 200g", unit="un",
        base_price_q=1500,
        metadata={"fiscal": {"profile": "resale", "ncm": "04051000", "unit": "UN", "cest": "1702500"}},
    )

    report = apply_grocery(apply=True)

    manteiga = Product.objects.get(sku="MANTEIGA-SAL-PRESIDENT-200")
    assert manteiga.metadata["fiscal"]["profile"] == "resale"
    assert ("MANTEIGA-SAL-PRESIDENT-200", "profile", "resale", "resale_common") in report["conflicts"]


def test_chas_kanfa_do_seed_ganham_ncm_da_nota_e_cest(catalog):
    cha = Product.objects.create(
        sku="CHA-MAMA-KANFA-P50", name="Mama Chai Kãnfa — Pouch 50g", unit="un", base_price_q=6000,
        metadata={"fiscal": {"profile": "own_production", "ncm": "09022000", "unit": "UN"}},
    )

    apply_grocery(apply=True)

    cha.refresh_from_db()
    assert cha.metadata["fiscal"] == {"profile": "resale_common", "ncm": "09021000", "unit": "UN", "cest": "1709700"}


def test_cada_perfil_fiscal_tem_nota_com_fonte():
    assert {"obrigacao", "st_no_pr", "csosn_500"} <= set(command.FISCAL_NOTES)
    assert "CV142_18" in command.FISCAL_NOTES["obrigacao"]
