"""O comando das palavras-chave só lê sem --write, e com --write grava a proposta."""

from __future__ import annotations

import io
import json

import pytest
from django.core.management import call_command
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db


@pytest.fixture
def proposal(tmp_path):
    path = tmp_path / "proposta.json"
    path.write_text(json.dumps({"products": {
        "CN": {"add": ["folhado de maçã", "folhado"]},
        "CI": {"add": ["chapata"], "remove": ["italiano"]},
        "FORA": {"add": ["nada"]},
    }}), encoding="utf-8")
    return str(path)


@pytest.fixture
def products():
    chausson = Product.objects.create(sku="CN", name="Chausson aux Pommes", base_price_q=1200, is_published=True)
    chausson.keywords.add("folhado")
    ciabatta = Product.objects.create(sku="CI", name="Ciabatta", base_price_q=1200, is_published=True)
    ciabatta.keywords.add("italiano", "pao")
    Product.objects.create(sku="MDLN", name="Madeleine", base_price_q=1200, is_published=True)
    return chausson, ciabatta


def _run(*args):
    out = io.StringIO()
    call_command("concierge_keywords", *args, stdout=out)
    return out.getvalue()


def test_without_write_it_only_reports(products, proposal):
    report = _run("--proposal", proposal)
    chausson, ciabatta = products
    assert "3 produto(s) publicado(s): 2 com palavras-chave, 1 sem." in report
    assert "sem palavras-chave: MDLN | Madeleine" in report
    assert "CN | Chausson aux Pommes: + folhado de maçã  |  - -" in report
    assert "CI | Ciabatta: + chapata  |  - italiano" in report
    assert "FORA: não está publicado aqui" in report
    assert "2 produto(s) mudaria(m); nada gravado" in report
    assert sorted(chausson.keywords.names()) == ["folhado"]
    assert sorted(ciabatta.keywords.names()) == ["italiano", "pao"]


def test_with_write_it_records_the_proposal(products, proposal):
    report = _run("--proposal", proposal, "--write")
    chausson, ciabatta = products
    assert "2 produto(s) gravado(s)." in report
    assert sorted(chausson.keywords.names()) == ["folhado", "folhado de maçã"]
    assert sorted(ciabatta.keywords.names()) == ["chapata", "pao"]
    assert "0 produto(s) mudaria(m)" in _run("--proposal", proposal)


def test_the_shipped_proposal_is_valid():
    from shopman.storefront.management.commands.concierge_keywords import PROPOSAL

    products = json.loads(PROPOSAL.read_text(encoding="utf-8"))["products"]
    assert products["CN"]["add"][0] == "folhado de maçã"
    for sku, entry in products.items():
        assert entry.get("add") or entry.get("remove"), sku
        assert entry.get("why"), sku
        assert not any("—" in word for word in entry.get("add", ())), sku
