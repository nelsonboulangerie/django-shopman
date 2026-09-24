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
        # Perfil de revenda comum: NCM de 8 dígitos e SEM CEST gravado.
        metadata = {"fiscal": {"profile": "own_production", "ncm": item.ncm, "unit": item.unit.upper()}}
        assert not from_metadata(metadata).errors(), item.sku
        assert resolve_fiscal_item(from_metadata(metadata))["cfop"] == "5102"


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


def test_cria_a_revenda_so_no_pdv(catalog):
    call_command("apply_grocery_catalog", "--apply", stdout=StringIO())

    dijon = Product.objects.get(sku=DIJON)
    assert (dijon.name, dijon.base_price_q, dijon.unit, dijon.unit_weight_g) == (
        "Mostarda Dijon Maille 215g", 3500, "un", 215,
    )
    assert dijon.is_sellable and not dijon.is_published
    assert dijon.metadata["fiscal"] == {"profile": "own_production", "ncm": "21033021", "unit": "UN"}
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


def test_queijo_a_quilo_nasce_sem_gtin_e_vendavel_sem_preco(catalog):
    """Falta de preço não trava: o PDV cobra o valor da etiqueta (dono, 24/09)."""
    report = apply_grocery(apply=True)

    queijo = Product.objects.get(sku=VALE_DO_TESTO)
    assert (queijo.unit, queijo.base_price_q, queijo.unit_weight_g) == ("kg", 0, None)
    assert queijo.is_sellable
    assert get_social_attributes(queijo).gtin == ""
    assert queijo.metadata["fiscal"]["unit"] == "KG"
    # Sem preço do quilo, o valor da etiqueta é o preço da linha (#1059).
    assert queijo.metadata["price_from_label"] is True
    item = ListingItem.objects.get(product=queijo)
    assert item.listing.ref == "pdv" and item.is_sellable
    assert [sku for sku, _ in report["no_price"]] == [VALE_DO_TESTO]


def test_item_a_quilo_com_gtin_e_recusado(catalog, monkeypatch):
    queijo = next(i for i in GROCERY if i.sku == VALE_DO_TESTO)
    monkeypatch.setattr(command, "GROCERY", (replace(queijo, gtin="2000000000008"),))

    report = apply_grocery(apply=True)

    assert report["refused"] == [(VALE_DO_TESTO, "item a quilo não leva GTIN de embalagem")]


def test_gtin_da_web_fica_marcado_como_a_conferir(catalog):
    apply_grocery(apply=True)

    ancienne = Product.objects.get(sku="MOSTARDA-ANCIENNE-MAILLE-210")
    assert ancienne.metadata["gtin_source"] == WEB_UNCONFIRMED
    assert "gtin_source" not in Product.objects.get(sku=DIJON).metadata


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


def test_item_com_preco_nao_leva_a_chave_da_etiqueta(catalog):
    apply_grocery(apply=True)

    assert "price_from_label" not in Product.objects.get(sku=DIJON).metadata
