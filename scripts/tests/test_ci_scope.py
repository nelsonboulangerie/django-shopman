"""O escopo da CI erra para o lado de rodar, nunca para o de pular."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "ci_scope", Path(__file__).resolve().parents[1] / "ci_scope.py"
)
ci_scope = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ci_scope)
classify = ci_scope.classify


def test_fila_e_push_rodam_tudo():
    for event in ("merge_group", "push", "workflow_dispatch", "schedule"):
        scope = classify(event, ["docs/x.md"])
        assert scope["heavy"] == "true"
        assert scope["full"] == "true"
        assert scope["python"] == "true"
        assert scope["surfaces"] == "all"


def test_pr_so_de_docs_nao_liga_codigo():
    scope = classify("pull_request", ["docs/reference/ci.md", "CLAUDE.md", "surfaces/pos-nuxt/README.md"])
    assert scope == {"full": "false", "heavy": "false", "code": "false", "python": "false", "surfaces": "[]"}


def test_pr_de_um_app_liga_o_app_e_o_kit():
    scope = classify("pull_request", ["surfaces/orders-nuxt/app/pages/index.vue"])
    assert scope["python"] == "false"
    assert scope["code"] == "true"
    assert json.loads(scope["surfaces"]) == ["operator-kit", "orders-nuxt"]


def test_pr_python_nao_liga_superficie():
    scope = classify("pull_request", ["shopman/shop/services/x.py", "packages/orderman/y.py"])
    assert scope["python"] == "true"
    assert scope["surfaces"] == "[]"


def test_infraestrutura_e_pasta_desconhecida_ligam_tudo():
    for path in (
        ".github/workflows/runtime-gate.yml",
        "scripts/surface_contract.mjs",
        "Makefile",
        "surfaces/registry.json",
        "Dockerfile",
        "pasta-nova/arquivo.txt",
    ):
        scope = classify("pull_request", [path])
        assert scope["full"] == "true", path
        assert scope["python"] == "true", path
        assert scope["surfaces"] == "all", path


def test_lista_vazia_roda_tudo():
    assert classify("pull_request", [])["full"] == "true"
