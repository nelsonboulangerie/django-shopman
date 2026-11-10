#!/usr/bin/env python3
"""Guarda do próprio mapa de guardas (docs/reference/guard-map.md).

Sem importar Django. Reprova quando:

1. uma guarda citada em ``GUARDS`` não existe no repositório;
2. um ``scripts/check_*`` existe e não está em ``GUARDS`` (o mapa não é completo);
3. o documento e ``GUARDS`` divergem: guarda de ``GUARDS`` que o guard-map.md não cita, ou
   ``check_*.py`` citado no guard-map.md que não existe.

Imprime as áreas ainda sem guarda (seção 9 do documento).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = Path("docs/reference/guard-map.md")
CITED_CHECK = re.compile(r"\bcheck_[a-z0-9_]+\.(?:py|mjs)\b")

GUARDS: dict[str, list[str]] = {
    "fronteira-kernel": ["shopman/shop/tests/test_import_boundaries.py"],
    "orquestrador": ["scripts/check_orchestrator_units.py"],
    "superficie-headless": [
        "shopman/shop/tests/test_import_boundaries.py",
        "scripts/check_admin_surface_boundary.py",
        "scripts/check_unfold_canonical.py",
    ],
    "migracoes": ["scripts/check_migrations.py", "scripts/check_seed_reentrancy.py"],
    "adr015": ["scripts/check_adr015.py"],
    "governanca-docs": [
        "scripts/check_adr_governance.py",
        "scripts/check_docs_governance.py",
        "scripts/check_canonical_docs.py",
        "scripts/check_semantic_docs.py",
        "scripts/check_legal_archive.py",
        "scripts/check_marketing_docs.py",
    ],
    "superficies-nuxt": [
        "scripts/check_surface_registry.py",
        "scripts/check_surface_versions.py",
        "scripts/check_operator_component_ledger.py",
        "scripts/check_operator_layout_guardrails.py",
        "scripts/check_operator_shortcuts.py",
        "scripts/check_theme_baseline_contract.py",
        "scripts/check_npm_audit_gate.mjs",
    ],
    "vocabulario-copy": [
        "shopman/backstage/tests/test_vocabulario_de_tela.py",
        "surfaces/operator-kit/tests/guardrails.vocabulary.test.ts",
    ],
    "qualidade-codigo": [
        "scripts/check_silent_swallow.py",
        "scripts/check_constraints.py",
        "scripts/check_workflow_budgets.py",
        "scripts/check_menu_smoke.py",
    ],
    "deploy-runtime": [
        "scripts/check_do_spec_drift.py",
        "scripts/check_registry_drift.py",
        "scripts/check_production_contract.py",
        "scripts/check_runtime_gate.py",
        "scripts/check_release_readiness.py",
        "scripts/check_instance_descriptors.py",
        "scripts/check_tenant_config.py",
    ],
    "constituicao": [
        "scripts/check_money_integer.py",
        "scripts/check_cross_kernel_refs.py",
        "scripts/check_decision_authority.py",
        "scripts/check_order_lifecycle_owner.py",
        "scripts/check_lifecycle_functional.py",
        "scripts/check_read_side_immutability.py",
        "scripts/check_ledger_immutability.py",
        "scripts/check_signal_on_commit.py",
    ],
}

UNCOVERED = [
    "cadeia de custo write-only (ADR-023/024 sem leitor): F3 decide ligar (A) ou adiar (B)",
    "duplicação de autoridade de decisão GERAL: check_decision_authority cobre só as decisões registradas em CANONICAL/FORBIDDEN",
]


def problems(root: Path = ROOT, guards: dict[str, list[str]] | None = None) -> list[str]:
    guards = GUARDS if guards is None else guards
    found: list[str] = []
    for door, cited in guards.items():
        for g in cited:
            if not (root / g).exists():
                found.append(f"guarda citada mas inexistente: {door}: {g}")

    referenced = {g.split("/")[-1] for cited in guards.values() for g in cited}
    scripts = root / "scripts"
    for p in sorted([*scripts.glob("check_*.py"), *scripts.glob("check_*.mjs")]):
        if p.name not in referenced and p.name != "check_guard_map.py":
            found.append(f"check no repo que não está no mapa: scripts/{p.name}")

    doc_path = root / DOC
    if not doc_path.exists():
        return [*found, f"{DOC} não existe"]
    doc = doc_path.read_text()
    for name in sorted(referenced):
        if name not in doc:
            found.append(f"guarda do mapa que o {DOC.name} não cita: {name}")
    for name in sorted(set(CITED_CHECK.findall(doc))):
        if not (scripts / name).exists():
            found.append(f"{DOC.name} cita check inexistente: {name}")
    return found


def main() -> int:
    found = problems()
    if found:
        print("MAPA DE GUARDAS DIVERGENTE:")
        for f in found:
            print(f"  - {f}")
    else:
        print("MAPA DE GUARDAS COMPLETO.")

    print()
    print("AREAS AINDA NAO COBERTAS:")
    for u in UNCOVERED:
        print(f"  - {u}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
