"""Cinco GETs sequenciais por leitura privada, sem cookies ou corpos persistidos."""

import argparse
import hashlib
import json
import statistics
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

URLS = {
    "catalog": "https://api.boulangerie.com.br/api/v1/storefront/catalog/",
    "pdp": "https://api.boulangerie.com.br/api/v1/storefront/products/FENDU/",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = {"captured_utc": datetime.now(UTC).isoformat(), "reads": {}}
    for name, url in URLS.items():
        rows = []
        for _ in range(5):
            start = time.perf_counter()
            with urllib.request.urlopen(url, timeout=15) as response:
                body = response.read()
                rows.append({
                    "status": response.status, "ms": round((time.perf_counter() - start) * 1000, 2),
                    "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                    "headers": {key: response.headers.get(key) for key in (
                        "CF-Cache-Status", "Cache-Control", "Age", "Server-Timing", "X-API-Version",
                    )},
                })
            time.sleep(1)
        output["reads"][name] = {
            "url": url, "samples": rows, "p50_ms": statistics.median(x["ms"] for x in rows),
            "maximum_ms": max(x["ms"] for x in rows),
        }
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({key: {k: v for k, v in value.items() if k != "samples"} for key, value in output["reads"].items()}))


if __name__ == "__main__":
    main()
