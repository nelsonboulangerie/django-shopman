"""Os comandos de insumo são read-only por padrão e validam antes da rede."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from shopman.buyman.models import Material

from shopman.shop.management.commands import fetch_material_enrichment as command_module
from shopman.shop.services import product_enrichment as pe

pytestmark = pytest.mark.django_db


def test_fetch_defaults_to_dry_run(monkeypatch):
    material = Material.objects.create(
        sku="GELEIA", name="Geleia", unit="un", metadata={"gtin": "7898708850309"}
    )
    suggestion = pe.EnrichmentSuggestion(gtin="7898708850309")
    suggestion.add("brand", "Marca", pe.SOURCE_COSMOS)
    monkeypatch.setattr(command_module, "build_suggestion", lambda gtin: suggestion)
    output = StringIO()

    call_command("fetch_material_enrichment", stdout=output)

    material.refresh_from_db()
    assert "enrichment" not in material.metadata
    assert "dry-run, nada gravado" in output.getvalue()


def test_fetch_stage_writes_only_pending_draft(monkeypatch):
    material = Material.objects.create(
        sku="GELEIA", name="Geleia", unit="un", metadata={"gtin": "7898708850309"}
    )
    suggestion = pe.EnrichmentSuggestion(gtin="7898708850309")
    suggestion.add("brand", "Marca", pe.SOURCE_COSMOS)
    monkeypatch.setattr(command_module, "build_suggestion", lambda gtin: suggestion)

    call_command("fetch_material_enrichment", "--stage")

    material.refresh_from_db()
    assert "brand" not in material.metadata
    assert material.metadata["enrichment"]["fields"]["brand"]["value"] == "Marca"


def test_invalid_gtin_never_calls_external_source(monkeypatch):
    Material.objects.create(sku="ERRO", name="Erro", unit="un", metadata={"gtin": "123"})
    monkeypatch.setattr(
        command_module,
        "build_suggestion",
        lambda gtin: (_ for _ in ()).throw(AssertionError("não deveria consultar")),
    )
    errors = StringIO()

    call_command("fetch_material_enrichment", stderr=errors)

    assert "GTIN inválido, não consultado" in errors.getvalue()


def test_audit_json_exposes_numeric_coverage():
    Material.objects.create(
        sku="FARINHA", name="Farinha", unit="kg", metadata={"diet": "vegan", "allergens": []}
    )
    output = StringIO()

    call_command("audit_material_enrichment", "--json", stdout=output)

    payload = json.loads(output.getvalue())
    assert payload["active_materials"] == 1
    assert payload["declared_materials"] == 0  # não é usado por ficha neste cenário
    assert payload["invalid"] == []
