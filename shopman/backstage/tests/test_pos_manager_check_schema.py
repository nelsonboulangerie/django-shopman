"""Cada view do PDV leva a PRÓPRIA descrição no schema OpenAPI.

A conferência do PIN do gerente (PDV-05) nasceu entre o decorador e a view do
"Resolve or create a customer": o decorador passou a descrever a conferência, e o
resolve do cliente ficou sem descrição nenhuma. O mapa da API mentia nas duas.
"""

from __future__ import annotations

from django.urls import path
from drf_spectacular.generators import SchemaGenerator

from shopman.backstage.api.operations import POSCustomerResolveView, POSManagerApprovalCheckView


def _summaries() -> dict[str, str]:
    # Só as duas rotas: o schema inteiro leva mais de um minuto para gerar.
    patterns = [
        path("resolve/", POSCustomerResolveView.as_view()),
        path("check/", POSManagerApprovalCheckView.as_view()),
    ]
    schema = SchemaGenerator(patterns=patterns).get_schema(request=None, public=True)
    return {route: ops["post"].get("summary", "") for route, ops in schema["paths"].items()}


def test_cada_view_tem_a_propria_descricao():
    summaries = _summaries()
    assert summaries["/resolve/"].startswith("Resolve or create a customer")
    assert "manager approval" in summaries["/check/"]
