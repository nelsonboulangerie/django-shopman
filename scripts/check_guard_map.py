"""Guarda do próprio mapa de guardas — a porta que faltava.

Sem importar Django. Confere: (1) toda guarda citada existe; (2) o mapa é completo (todo
scripts/check_* está citado); (3) imprime as áreas não cobertas (seção 9/10).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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
    "consolidacao-novas": [
        "scripts/check_decision_authority.py",
        "scripts/check_signal_on_commit.py",
        "scripts/check_money_integer.py",
        "scripts/check_read_side_immutability.py",
        "scripts/check_lifecycle_functional.py",
        "scripts/check_cross_kernel_refs.py",
        "scripts/check_order_lifecycle_owner.py",
        "scripts/check_ledger_immutability.py",
    ],
}

UNCOVERED = [
    "duplicacao-de-autoridade GERAL — o gate cobre os conhecidos; F2 fecha promise_for_sku",
]


def main() -> int:
    missing = []
    for door, guards in GUARDS.items():
        for g in guards:
            if not (ROOT / g).exists():
                missing.append(f"{door}: {g}")

    referenced = set()
    for guards in GUARDS.values():
        for g in guards:
            referenced.add(g.split("/")[-1])

    orphan_checks = sorted(
        p.name
        for p in list((ROOT / "scripts").glob("check_*.py"))
        + list((ROOT / "scripts").glob("check_*.mjs"))
        if p.name not in referenced and p.name != "check_guard_map.py"
    )

    ok = True
    if missing:
        ok = False
        print("GUARDA CITADA MAS INEXISTENTE (pode ser checkout defasado):")
        for m in missing:
            print(f"  - {m}")
    if orphan_checks:
        ok = False
        print("CHECK NO REPO QUE NAO ESTA NO MAPA:")
        for o in orphan_checks:
            print(f"  - scripts/{o}")
    if not missing and not orphan_checks:
        print("MAPA DE GUARDAS COMPLETO.")

    print()
    print("AREAS AINDA NAO COBERTAS:")
    for u in UNCOVERED:
        print(f"  - {u}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
