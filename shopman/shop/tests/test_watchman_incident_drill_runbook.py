from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = ROOT / "docs/runbooks/watchman-ensaio-incidente-pool.md"


def test_pool_incident_drill_is_guarded_and_has_measurable_acceptance():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "ainda não executado" in text
    assert "pode executar o ensaio do pool" in text
    assert "T1 - T0 < 120 s" in text
    assert "três amostras consecutivas" in text
    assert "web-operator" in text
    assert "web-storefront" in text
    assert "liveness_pool_stuck_restart" in text
    assert "liveness_pool_stuck_but_database_down" in text
    assert "PoolTimeout" in text


def test_pool_incident_drill_has_no_live_mutation_or_retired_alpha_host():
    text = RUNBOOK.read_text(encoding="utf-8")

    forbidden = (
        "alpha.nelsonboulangerie.com.br",
        "doctl apps update",
        "doctl apps create-deployment",
        "UPDATE ",
        "DELETE FROM",
        "ALTER TABLE",
    )
    assert all(item not in text for item in forbidden)
    assert "não altera spec" in text.lower()
    assert "não grava dado" in text.lower()
