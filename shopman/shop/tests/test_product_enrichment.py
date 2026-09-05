"""A sugestão de catálogo por GTIN — e, sobretudo, o que ela NÃO faz.

O que estes testes guardam:

- **nada vira rótulo sozinho**: a sugestão nasce `pending` e não toca o produto;
- **alérgeno fora da lista da casa não some**: vai para `allergens_unmapped` e
  aparece para quem aceita — descartar em silêncio é o pior defeito aqui;
- **silêncio do OFF não é ausência**: veio ingrediente e não veio alérgeno, o
  rascunho DIZ isso em vez de deixar a lista vazia parecer "não contém";
- **fornecedor fora do ar não derruba nada**: falha de rede vira sugestão vazia.
"""

from __future__ import annotations

import pytest

from shopman.shop.services import product_enrichment as pe


@pytest.fixture(autouse=True)
def _nao_inerte(settings, monkeypatch):
    """A trava de DEBUG é testada em `test_inerte_em_debug`; aqui ela sai da frente."""
    settings.DEBUG = False
    monkeypatch.setattr(pe, "_suppressed_reason", None, raising=False)


def _sem_rede(monkeypatch, *, cosmos=None, off=None):
    monkeypatch.setattr(pe, "fetch_cosmos", lambda gtin: cosmos)
    monkeypatch.setattr(pe, "fetch_off", lambda gtin: off)


COSMOS_OK = {
    "description": "GELEIA ST DALFOUR FRAMBOESA 284G",
    "brand": {"name": "ST DALFOUR"},
    "thumbnail": "https://cdn-cosmos.bluesoft.com.br/products/5014271390420",
    "ncm": {"code": "20079990", "description": "Outras"},
    "gpc": {"description": "Geleias / Conservas de Frutas"},
    "net_weight": 284,
}


def test_cosmos_da_foto_nome_marca_e_ncm(monkeypatch):
    _sem_rede(monkeypatch, cosmos=COSMOS_OK)
    s = pe.build_suggestion("5014271390420")
    assert s.name == "GELEIA ST DALFOUR FRAMBOESA 284G"
    assert s.brand == "ST DALFOUR"
    assert s.ncm == "20079990"
    assert s.net_weight_g == 284
    assert s.image_url.startswith("https://cdn-cosmos")
    assert s.sources == ["cosmos"]


def test_off_traduz_alergeno_para_o_vocabulario_da_casa(monkeypatch):
    _sem_rede(monkeypatch, off={"allergens_tags": ["en:gluten", "en:milk", "en:soybeans"]})
    s = pe.build_suggestion("7891000412855")
    assert s.allergens == ["glúten", "leite", "soja"]
    assert s.allergens_unmapped == []


def test_alergeno_fora_da_lista_da_casa_NAO_some(monkeypatch):
    """Aipo é obrigatório na UE e não está na RDC 26/2015.

    Um `dict.get()` devolveria None e a informação sumiria — que é exatamente o
    defeito que esta superfície não pode ter.
    """
    _sem_rede(monkeypatch, off={"allergens_tags": ["en:milk", "en:celery", "en:molluscs"]})
    s = pe.build_suggestion("1")
    assert s.allergens == ["leite"]
    assert s.allergens_unmapped == ["en:celery", "en:molluscs"]
    assert any("fora da lista da casa" in n for n in s.notes)


def test_silencio_do_off_nao_e_declaracao_de_ausencia(monkeypatch):
    """93% dos sem-alérgeno tinham ingredientes: o vazio é falta de curadoria."""
    _sem_rede(monkeypatch, off={"allergens_tags": [], "ingredients_text": "AÇÚCAR, ÁGUA, FRAMBOESA"})
    s = pe.build_suggestion("1")
    assert s.allergens == []
    assert any("NÃO marcou alérgeno" in n for n in s.notes)


def test_a_sugestao_nasce_pending_e_nao_e_rotulo(monkeypatch):
    _sem_rede(monkeypatch, cosmos=COSMOS_OK, off={"allergens_tags": ["en:gluten"]})
    meta = pe.build_suggestion("1").to_metadata()
    assert meta["status"] == "pending"
    # o bloco é um rascunho ao lado; não escreve nas chaves que a loja lê
    assert set(meta) <= {"status", "fetched_at", "sources", "suggested", "notes"}
    assert "allergens" not in meta
    assert meta["suggested"]["allergens"] == ["glúten"]


def test_foto_do_off_avisa_a_licenca(monkeypatch):
    _sem_rede(monkeypatch, off={"image_front_url": "https://images.openfoodfacts.org/x.jpg"})
    s = pe.build_suggestion("1")
    assert any("CC-BY-SA" in n for n in s.notes)


def test_cosmos_tem_prioridade_na_foto(monkeypatch):
    """A do fabricante ganha da colaborativa — e sem aviso de licença."""
    _sem_rede(monkeypatch, cosmos=COSMOS_OK, off={"image_front_url": "https://images.openfoodfacts.org/x.jpg"})
    s = pe.build_suggestion("1")
    assert s.image_url.startswith("https://cdn-cosmos")
    assert not any("CC-BY-SA" in n for n in s.notes)


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
