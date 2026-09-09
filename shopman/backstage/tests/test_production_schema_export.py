"""Drift guard for the generated production contract mirror.

The Produção surface (production-nuxt) imports the projection shapes from a
generated TypeScript module whose single source of truth is
``shopman.backstage.projections.production``. If a dataclass changes without
regenerating, this test fails with the fix command — so the hand-sync the
schema was meant to kill cannot creep back via staleness.
"""

from __future__ import annotations

from shopman.backstage.management.commands.export_production_schema import (
    output_path,
    render_production_contract_ts,
)


def test_generated_production_contract_is_not_stale() -> None:
    path = output_path()
    assert path.exists(), f"{path} missing — run: python manage.py export_production_schema"
    assert path.read_text(encoding="utf-8") == render_production_contract_ts(), (
        "Production contract mirror is stale — run: python manage.py export_production_schema"
    )


def test_render_is_deterministic() -> None:
    assert render_production_contract_ts() == render_production_contract_ts()


def test_render_reflects_contract_source() -> None:
    from dataclasses import fields

    from shopman.backstage.projections.production import ProductionBoardProjection

    rendered = render_production_contract_ts()
    assert "export interface ProductionBoardProjection {" in rendered
    for field in fields(ProductionBoardProjection):
        assert f"  {field.name}:" in rendered


def test_render_includes_closed_mutation_requests_and_generated_client() -> None:
    rendered = render_production_contract_ts()

    assert "export interface ProductionFinishMutationRequest {" in rendered
    assert "  idempotency_key: string;" in rendered
    assert "  expected_rev: number;" in rendered
    assert "export interface ProductionConflictErrorEnvelope {" in rendered
    assert "export function finishProductionWorkOrder(" in rendered
    assert 'method: "POST"' in rendered


def test_render_includes_operator_alert_projection_and_ack_request() -> None:
    rendered = render_production_contract_ts()

    assert "export interface OperatorAlertsProjection {" in rendered
    assert "export interface OperatorAlertProjection {" in rendered
    assert "export interface AlertAckMutationRequest {" in rendered


def test_mutation_endpoints_live_only_in_generated_client() -> None:
    root = output_path().parents[4]
    handwritten = root / "surfaces" / "production-nuxt" / "app" / "composables"
    mutation_fragments = (
        "/production/plan/",
        "/start/",
        "/finish/",
        "/advance-step/",
        "/quick-finish/",
        "/void/",
        "/oven/arm/",
        "/oven/conclude/",
        "/ack/",
    )

    offenders = [
        path
        for path in handwritten.glob("*.ts")
        if any(fragment in path.read_text(encoding="utf-8") for fragment in mutation_fragments)
    ]

    assert offenders == []
