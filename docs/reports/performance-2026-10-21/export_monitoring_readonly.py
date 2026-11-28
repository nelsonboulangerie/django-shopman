"""Exporta somente métricas documentadas com um token de leitura já existente."""

from __future__ import annotations

import json
import math
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

APP_ID = "40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f"
COMPONENTS = ("web-storefront", "storefront-nuxt", "operator-floor", "operator-office")
METRICS = ("cpu_percentage", "memory_percentage", "restart_count")


def main() -> None:
    token = os.environ["DO_READ_TOKEN"]
    end = int(time.time())
    result = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "start": end - 7 * 86400,
        "end": end,
        "app_id": APP_ID,
        "metrics": [],
        "errors": [],
    }
    for component in COMPONENTS:
        for metric in METRICS:
            query = urllib.parse.urlencode(
                {"app_id": APP_ID, "app_component": component, "start": result["start"], "end": end}
            )
            url = "https://api.digitalocean.com/v2/monitoring/metrics/apps/" + metric + "?" + query
            request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = json.load(response)
            except urllib.error.HTTPError as error:
                result["errors"].append({"component": component, "metric": metric, "status": error.code})
                continue
            summaries = []
            for series in data.get("data", {}).get("result", []):
                values = sorted(float(point[1]) for point in series.get("values", []) if math.isfinite(float(point[1])))
                summaries.append(
                    {
                        "labels": series.get("metric", {}),
                        "n": len(values),
                        "p50": statistics.median(values) if values else None,
                        "p95_nearest_rank": values[math.ceil(len(values) * 0.95) - 1] if values else None,
                        "maximum": max(values) if values else None,
                    }
                )
            result["metrics"].append(
                {"component": component, "metric": metric, "response": data, "summary_by_series": summaries}
            )
    Path("phase-a-monitoring.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"exported": len(result["metrics"]), "errors": result["errors"]}))


if __name__ == "__main__":
    main()
