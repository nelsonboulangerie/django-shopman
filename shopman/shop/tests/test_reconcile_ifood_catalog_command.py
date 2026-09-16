"""Comando de inventário não grava catálogo, diretivas nem acessa HTTP."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Listing, Product
from shopman.orderman.models import Directive

FIXTURE = Path(__file__).parent / "fixtures/ifood_catalog_inventory.json"


def run(inventory=FIXTURE, **overrides):
    output = StringIO()
    options = {"inventory": str(inventory), "merchant_id": "merchant-a", "catalog_id": "catalog-a", "context": "DEFAULT"}
    options.update(overrides)
    call_command("reconcile_ifood_catalog", stdout=output, **options)
    return json.loads(output.getvalue())


@pytest.mark.django_db
def test_command_reads_canonical_products_without_mutations_or_http():
    Product.objects.create(sku="BG-1", name="Baguete", base_price_q=100)
    models = (Product, Listing, Directive)
    before = [list(model.objects.values()) for model in models]
    with patch("requests.sessions.Session.request", side_effect=AssertionError("HTTP proibido")), \
            CaptureQueriesContext(connection) as queries:
        result = run()
    assert [list(model.objects.values()) for model in models] == before
    assert all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries)
    assert result["items"][0]["candidate_skus"] == ["BG-1"]
    assert result["summary"]["pending"] == 5
    assert result["items"][0]["merchant_id"] == "merchant-a"


@pytest.mark.parametrize("body", ["not-json-secret", "{}", '[{"id":"category"}]'])
def test_bad_file_format_does_not_expose_contents(tmp_path, body):
    path = tmp_path / "inventory.json"
    path.write_text(body)
    with pytest.raises(CommandError) as error:
        run(path)
    assert "not-json-secret" not in str(error.value)


def test_missing_file_and_directory_are_command_errors(tmp_path):
    for path in [tmp_path, tmp_path / "secret-name.json"]:
        with pytest.raises(CommandError) as error:
            run(path)
        assert "secret-name" not in str(error.value)


@pytest.mark.parametrize("scope", [{"merchant_id": ""}, {"catalog_id": " "}, {"context": ""}])
def test_invalid_scope_errors_before_database_access(scope):
    with pytest.raises(CommandError, match="loja, catálogo e contexto"):
        run(**scope)


def test_bad_utf8_is_safe_command_error(tmp_path):
    path = tmp_path / "inventory.json"
    path.write_bytes(b"\xff")
    with pytest.raises(CommandError, match="JSON UTF-8"):
        run(path)


def test_database_error_does_not_expose_connection_details():
    from django.db import DatabaseError

    with patch.object(Product.objects, "only", side_effect=DatabaseError("secret-connection-details")):
        with pytest.raises(CommandError) as error:
            run()
    assert "secret-connection-details" not in str(error.value)
    assert "produtos canônicos" in str(error.value)
