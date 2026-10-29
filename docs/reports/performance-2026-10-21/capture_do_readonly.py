"""Lê spec resumido e observações de catálogo via contexto existente do doctl.

Não grava spec completo, credenciais nem linhas arbitrárias dos logs. Não altera
contexto, serviços, políticas ou permissões. A coleta de logs não é uma série de 7 dias.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from datetime import UTC, datetime
from pathlib import Path

APP_ID = "40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f"
FIELDS = (
    "timestamp",
    "path",
    "mode",
    "cache_status",
    "status",
    "query_count",
    "projection_ms",
    "availability_ms",
    "personalization_ms",
    "db_ms",
    "cache_ms",
    "cache_calls",
    "response_bytes",
    "connect_ms",
    "connect_count",
    "gc_ms",
    "gc_count",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = ["doctl", "--context", args.context, "apps"]
    app = json.loads(
        subprocess.run(
            base + ["get", APP_ID, "--output", "json"], capture_output=True, text=True, check=True, timeout=30
        ).stdout
    )
    app = app[0] if isinstance(app, list) else app
    deployment = app.get("active_deployment", {})
    out = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "app_id": APP_ID,
        "region": app.get("region", {}).get("slug"),
        "services": [
            {key: service.get(key) for key in ("name", "instance_size_slug", "instance_count")}
            for service in app.get("spec", {}).get("services", [])
        ],
        "deployment": {key: deployment.get(key) for key in ("id", "phase", "created_at")},
        "observations": [],
    }
    logs = subprocess.run(
        base + ["logs", APP_ID, "web-storefront", "--type", "run", "--tail", "2000", "--no-prefix"],
        capture_output=True,
        text=True,
        timeout=45,
    )
    out["log_command_exit_code"] = logs.returncode
    for line in logs.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not str(event.get("message", "")).startswith("storefront_catalog_observation"):
            continue
        if event.get("logger") != "shopman.storefront.continuum":
            continue
        record = {key: event[key] for key in FIELDS if key in event}
        # Nenhum identificador, query string ou corpo é preservado como caminho.
        if "path" in record and record["path"] not in (
            "storefront_catalog",
            "storefront_menu",
            "continuum_catalog_structure",
            "/api/v1/storefront/catalog/",
            "/api/v1/storefront/menu/",
            "/api/v1/storefront/public/catalog/",
            "/api/v1/storefront/public/menu/",
        ):
            record.pop("path")
        out["observations"].append(record)
    out["observations_count"] = len(out["observations"])
    out["projection_sample_summary"] = {}
    for path in sorted({row.get("path", "not_exported") for row in out["observations"]}):
        values = sorted(
            float(row["projection_ms"])
            for row in out["observations"]
            if row.get("path", "not_exported") == path and isinstance(row.get("projection_ms"), int | float)
        )
        if values:
            out["projection_sample_summary"][path] = {
                "n": len(values),
                "p50_ms": statistics.median(values),
                "maximum_ms": max(values),
            }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in out.items() if key != "observations"}, indent=2))


if __name__ == "__main__":
    main()
