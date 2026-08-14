"""Drift guard for the generated B.I. contract mirror.

O bi-nuxt importa as shapes de um módulo TypeScript gerado cuja fonte única
são os dataclasses de ``shopman.backstage.projections.bi_*``. Dataclass mudou
sem regenerar → este teste falha com o comando do conserto.
"""

from __future__ import annotations

from shopman.backstage.management.commands.export_bi_schema import (
    output_path,
    render_bi_contract_ts,
)


def test_generated_bi_contract_is_not_stale() -> None:
    path = output_path()
    assert path.exists(), f"{path} missing — run: python manage.py export_bi_schema"
    assert path.read_text(encoding="utf-8") == render_bi_contract_ts(), (
        "B.I. contract mirror is stale — run: python manage.py export_bi_schema"
    )


def test_render_is_deterministic() -> None:
    assert render_bi_contract_ts() == render_bi_contract_ts()


def test_render_reflects_contract_source() -> None:
    from dataclasses import fields

    from shopman.backstage.projections.bi_production import BIProductionReport

    rendered = render_bi_contract_ts()
    assert "export interface BIProductionReport {" in rendered
    for field in fields(BIProductionReport):
        assert f"  {field.name}:" in rendered
