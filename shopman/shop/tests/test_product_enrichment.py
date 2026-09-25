"""A sugestão de catálogo por GTIN — e, sobretudo, o que ela NÃO faz.

O que estes testes guardam:

- **nada vira dado do produto sozinho**: a sugestão é rascunho por campo, e só
  o campo aceito entra — com fonte e data guardadas;
- **valor preenchido à mão não é sobrescrito** sem ``replace`` explícito;
- **alérgeno vazio na fonte é "não curado"**: nunca vira campo aceitável;
- **alérgeno fora da lista da casa não some**: vai para `allergens_unmapped`;
- **foto de terceiro nunca vai para a vitrine**: fica como referência, com
  licença e atribuição;
- **a NF-e é a primeira fonte**: ganha da Cosmos no NCM, e a divergência fica
  visível em vez de sumir;
- **a ausência fala da busca**: "só a embalagem confirma", com o escopo;
- **fornecedor fora do ar não derruba nada**.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from shopman.offerman.models import Product

from shopman.shop.services import product_enrichment as pe


@pytest.fixture(autouse=True)
def _nao_inerte(settings, monkeypatch):
    """A trava de DEBUG é testada em `test_inerte_em_debug`; aqui ela sai da frente."""
    settings.DEBUG = False
    settings.SHOPMAN_COSMOS_TOKEN = "token-de-teste"
    monkeypatch.setattr(pe, "_suppressed_reason", None, raising=False)


def _sem_rede(monkeypatch, *, cosmos=None, off=None):
    monkeypatch.setattr(pe, "fetch_cosmos", lambda gtin: cosmos)
    monkeypatch.setattr(pe, "fetch_off", lambda gtin: off)


COSMOS_OK = {
    "description": "GELEIA ST DALFOUR FRAMBOESA 284G",
    "brand": {"name": "ST DALFOUR"},
    "thumbnail": "https://cdn-cosmos.bluesoft.com.br/products/5014271390420",
    "ncm": {"code": "2007.99.90", "description": "Outras"},
    "net_weight": 284,
}

OFF_OK = {
    "product_name": "Geleia de framboesa",
    "allergens_tags": ["en:gluten", "en:milk"],
    "ingredients_text": "AÇÚCAR, FRAMBOESA, PECTINA",
    "image_front_url": "https://images.openfoodfacts.org/x.jpg",
    "serving_quantity": 20,
    "nutriments": {"energy-kcal_100g": 250, "sugars_100g": 60, "sodium_100g": 0.05},
}


def _valor(s, campo):
    return s.fields[campo]["value"]


# ── A consulta ──────────────────────────────────────────────────────────


def test_cosmos_da_nome_marca_ncm_e_peso_campo_a_campo(monkeypatch):
    _sem_rede(monkeypatch, cosmos=COSMOS_OK)
    s = pe.build_suggestion("5014271390420")
    assert _valor(s, "name") == "GELEIA ST DALFOUR FRAMBOESA 284G"
    assert _valor(s, "brand") == "ST DALFOUR"
    assert _valor(s, "ncm") == "20079990"
    assert _valor(s, "net_weight_g") == 284
    assert {e["source"] for e in s.fields.values()} == {"cosmos"}
    assert all(e["fetched_at"] for e in s.fields.values())


def test_foto_de_terceiro_e_so_referencia_com_licenca(monkeypatch):
    _sem_rede(monkeypatch, off=OFF_OK)
    s = pe.build_suggestion("1")
    assert "image_url" not in s.fields
    assert s.reference_photo["source"] == "openfoodfacts"
    assert s.reference_photo["license"] == "CC BY-SA 3.0"
    assert "Open Food Facts contributors" in s.reference_photo["attribution"]


def test_foto_da_cosmos_tambem_nao_vai_para_a_vitrine(monkeypatch):
    _sem_rede(monkeypatch, cosmos=COSMOS_OK, off=OFF_OK)
    s = pe.build_suggestion("1")
    assert s.reference_photo["source"] == "cosmos"
    assert s.reference_photo["license"] == pe.COSMOS_PHOTO_LICENSE
    assert "image_url" not in s.fields


def test_off_traduz_alergeno_e_converte_a_tabela_para_a_porcao(monkeypatch):
    _sem_rede(monkeypatch, off=OFF_OK)
    s = pe.build_suggestion("1")
    assert _valor(s, "allergens") == ["glúten", "leite"]
    nutricao = _valor(s, "nutrition")
    assert nutricao["serving_size_g"] == 20
    assert nutricao["energy_kcal"] == 50.0
    assert nutricao["sodium_mg"] == 10.0


def test_sem_porcao_declarada_nao_ha_tabela(monkeypatch):
    _sem_rede(monkeypatch, off={**OFF_OK, "serving_quantity": None})
    assert "nutrition" not in pe.build_suggestion("1").fields


def test_alergeno_fora_da_lista_da_casa_NAO_some(monkeypatch):
    _sem_rede(monkeypatch, off={"allergens_tags": ["en:milk", "en:celery", "en:molluscs"]})
    s = pe.build_suggestion("1")
    assert _valor(s, "allergens") == ["leite"]
    assert s.allergens_unmapped == ["en:celery", "en:molluscs"]
    assert any("fora da lista da casa" in n for n in s.notes)


def test_alergeno_vazio_e_nao_curado_nunca_nao_contem(monkeypatch):
    """93% dos sem-alérgeno tinham ingredientes: o vazio é falta de curadoria."""
    _sem_rede(monkeypatch, off={"allergens_tags": [], "ingredients_text": "AÇÚCAR, ÁGUA"})
    s = pe.build_suggestion("1")
    assert "allergens" not in s.fields  # [] aceito seria lido como "não contém"
    assert pe.ALLERGENS_NOT_CURATED in s.notes


def test_nada_encontrado_fala_da_busca_com_escopo(monkeypatch, settings):
    settings.SHOPMAN_COSMOS_TOKEN = ""
    _sem_rede(monkeypatch, cosmos=None, off=None)
    s = pe.build_suggestion("7898708850309")
    assert s.is_empty()
    assert s.notes[0].startswith(pe.NOTHING_FOUND)
    assert "Cosmos (Bluesoft) ficou de fora (sem SHOPMAN_COSMOS_TOKEN)" in s.notes[0]
    assert "consultadas: Open Food Facts" in s.notes[0]


def test_fornecedor_fora_do_ar_nao_derruba(monkeypatch):
    _sem_rede(monkeypatch, cosmos=None, off=None)
    s = pe.build_suggestion("1")
    assert s.is_empty()
    assert s.sources == []


def test_gtin_vazio_nao_consulta_ninguem(monkeypatch):
    def _explode(gtin):  # pragma: no cover - não deve ser chamado
        raise AssertionError("não devia consultar sem GTIN")

    monkeypatch.setattr(pe, "fetch_cosmos", _explode)
    monkeypatch.setattr(pe, "fetch_off", _explode)
    assert pe.build_suggestion("").is_empty()


def test_inerte_em_debug(settings, monkeypatch):
    """Dev não gasta a cota de 25/dia do plano grátis sem pedir."""
    settings.DEBUG = True
    settings.SHOPMAN_ENRICHMENT_ALLOW_IN_DEBUG = False
    settings.SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG = False

    def _explode(gtin):  # pragma: no cover - não deve ser chamado
        raise AssertionError("não devia consultar em DEBUG sem opt-in")

    monkeypatch.setattr(pe, "fetch_cosmos", _explode)
    monkeypatch.setattr(pe, "fetch_off", _explode)
    s = pe.build_suggestion("789")
    assert s.is_empty()
    assert any("inerte" in n.lower() for n in s.notes)


def test_cosmos_sem_token_nao_estoura(settings, monkeypatch):
    settings.SHOPMAN_COSMOS_TOKEN = ""
    chamou = []
    monkeypatch.setattr(pe, "_get_json", lambda *a, **k: chamou.append(1))
    assert pe.fetch_cosmos("789") is None
    assert not chamou


def test_o_setting_do_token_existe_e_nasce_vazio():
    from django.conf import settings as django_settings

    assert hasattr(django_settings, "SHOPMAN_COSMOS_TOKEN")


# ── NF-e como primeira fonte ────────────────────────────────────────────


def test_nfe_ganha_da_cosmos_e_a_divergencia_fica_visivel(monkeypatch):
    _sem_rede(monkeypatch, cosmos=COSMOS_OK)
    meta = pe.merge_into_metadata({}, pe.build_suggestion("5014271390420"))
    nota = pe.suggestion_from_invoice(
        gtin="5014271390420", ncm="20079100", cest="1704600", unit="un", access_key="4126"
    )
    meta = pe.merge_into_metadata(meta, nota)

    ncm = meta["enrichment"]["fields"]["ncm"]
    assert (ncm["value"], ncm["source"]) == ("20079100", "nfe")
    assert ncm["alternatives"] == [
        {"value": "20079990", "source": "cosmos", "fetched_at": ncm["alternatives"][0]["fetched_at"]}
    ]
    assert meta["enrichment"]["fields"]["cest"]["source_ref"] == "4126"
    assert meta["enrichment"]["fields"]["fiscal_unit"]["value"] == "UN"
    assert meta["enrichment"]["sources"] == ["nfe", "cosmos"]


def test_nfe_com_gtin_invalido_nao_sugere_gtin():
    s = pe.suggestion_from_invoice(gtin="7898708850300", ncm="21011200")
    assert "gtin" not in s.fields
    assert "ncm" in s.fields


def test_nfe_com_dois_gtins_avisa_qual_conferir():
    s = pe.suggestion_from_invoice(gtin="7898708850309", other_gtin="17898708850306")
    assert "17898708850306" in s.fields["gtin"]["detail"]


# ── O aceite, campo a campo ─────────────────────────────────────────────


@pytest.fixture
def geleia(db):
    return Product.objects.create(
        sku="GELEIA",
        name="Geleia de framboesa",
        base_price_q=3900,
        image_url="",
        metadata={"fiscal": {"profile": "resale_tax_substitution", "ncm": "", "unit": "UN"}},
    )


@pytest.fixture
def gestor(db):
    return User.objects.create_user("gestor-catalogo", password="pw", is_staff=True)


def _com_rascunho(produto, monkeypatch, *, cosmos=COSMOS_OK, off=OFF_OK):
    _sem_rede(monkeypatch, cosmos=cosmos, off=off)
    produto.metadata = pe.merge_into_metadata(produto.metadata, pe.build_suggestion("5014271390420"))
    produto.save()
    produto.refresh_from_db()
    return produto


def test_aceita_so_os_campos_marcados(geleia, gestor, monkeypatch):
    _com_rascunho(geleia, monkeypatch)

    result = pe.accept_fields(geleia, ["ncm", "allergens"], user=gestor)

    geleia.refresh_from_db()
    assert result.applied == ["ncm", "allergens"]
    assert geleia.metadata["fiscal"]["ncm"] == "20079990"
    assert geleia.metadata["allergens"] == ["glúten", "leite"]
    assert geleia.metadata["dietary_auto_filled"] is False
    # o resto continua rascunho
    assert geleia.ingredients_text == ""
    assert "brand" not in (geleia.metadata.get("social") or {})
    pendentes = pe.pending_fields(geleia)
    assert "ncm" not in pendentes and "brand" in pendentes
    aceito = geleia.metadata["enrichment"]["accepted"]["ncm"]
    assert aceito["source"] == "cosmos"
    assert aceito["accepted_by"] == "gestor-catalogo"
    assert aceito["fetched_at"] and aceito["accepted_at"]


def test_nome_preenchido_a_mao_so_muda_com_substituir(geleia, gestor, monkeypatch):
    _com_rascunho(geleia, monkeypatch)

    sem = pe.accept_fields(geleia, ["name"], user=gestor)
    geleia.refresh_from_db()
    assert sem.conflicts == {"name": "Geleia de framboesa"}
    assert geleia.name == "Geleia de framboesa"
    assert "name" in pe.pending_fields(geleia)

    com = pe.accept_fields(geleia, ["name"], replace=["name"], user=gestor)
    geleia.refresh_from_db()
    assert com.applied == ["name"]
    assert geleia.name == "GELEIA ST DALFOUR FRAMBOESA 284G"
    assert geleia.metadata["enrichment"]["accepted"]["name"]["replaced"] == "Geleia de framboesa"


def test_alergeno_a_mao_nao_e_sobrescrito_sem_confirmacao(geleia, gestor, monkeypatch):
    geleia.metadata = {**geleia.metadata, "allergens": ["leite"]}
    geleia.save()
    _com_rascunho(geleia, monkeypatch)

    result = pe.accept_fields(geleia, ["allergens"], user=gestor)

    geleia.refresh_from_db()
    assert result.conflicts == {"allergens": ["leite"]}
    assert geleia.metadata["allergens"] == ["leite"]


def test_aceitar_nunca_promove_foto_para_a_vitrine(geleia, gestor, monkeypatch):
    _com_rascunho(geleia, monkeypatch)

    pe.accept_fields(geleia, list(pe.pending_fields(geleia)), replace=["name"], user=gestor)

    geleia.refresh_from_db()
    assert geleia.image_url == ""
    assert geleia.metadata["enrichment"]["reference_photo"]["license"] == pe.COSMOS_PHOTO_LICENSE


def test_cest_da_nota_entra_em_qualquer_perfil(geleia, gestor):
    """O CEST identifica a mercadoria; sem ST ele também vai (Conv. ICMS 142/2018)."""
    geleia.metadata = pe.merge_into_metadata(
        {**geleia.metadata, "fiscal": {"profile": "resale", "ncm": "20079990"}},
        pe.suggestion_from_invoice(cest="1709400"),
    )
    geleia.save()

    result = pe.accept_fields(geleia, ["cest"], user=gestor)

    geleia.refresh_from_db()
    assert "cest" not in result.refused
    assert geleia.metadata["fiscal"]["cest"] == "1709400"
    assert geleia.metadata["fiscal"]["profile"] == "resale"


def test_gtin_da_nota_entra_no_cadastro_social(geleia, gestor):
    geleia.metadata = pe.merge_into_metadata(
        geleia.metadata, pe.suggestion_from_invoice(gtin="7898708850309", access_key="4126")
    )
    geleia.save()

    pe.accept_fields(geleia, ["gtin"], user=gestor)

    geleia.refresh_from_db()
    assert geleia.metadata["social"]["gtin"] == "7898708850309"
    assert geleia.metadata["enrichment"]["accepted"]["gtin"]["source_ref"] == "4126"


def test_tabela_nutricional_aceita_vira_manual(geleia, gestor, monkeypatch):
    _com_rascunho(geleia, monkeypatch)

    pe.accept_fields(geleia, ["nutrition"], user=gestor)

    geleia.refresh_from_db()
    assert geleia.nutrition_facts["serving_size_g"] == 20
    assert geleia.nutrition_facts["auto_filled"] is False


def test_nova_consulta_nao_desfaz_o_aceite(geleia, gestor, monkeypatch):
    _com_rascunho(geleia, monkeypatch)
    pe.accept_fields(geleia, ["ncm"], user=gestor)
    geleia.refresh_from_db()

    _com_rascunho(geleia, monkeypatch)

    assert "ncm" not in pe.pending_fields(geleia)
    assert geleia.metadata["enrichment"]["accepted"]["ncm"]["value"] == "20079990"
