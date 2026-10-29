"""Amostra curta anônima, sequencial, sem cookies; não é teste de carga nem p95 histórico."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

URLS = (
    "https://www.nelsonboulangerie.com.br/produto/FENDU",
    "https://api.boulangerie.com.br/api/v1/storefront/products/FENDU/",
    "https://api.boulangerie.com.br/api/v1/storefront/products/FENDU/recommendations/",
    "https://api.boulangerie.com.br/api/v1/storefront/public/products/FENDU/recommendations/",
    "https://api.boulangerie.com.br/api/v1/storefront/public/catalog/",
    "https://central.boulangerie.com.br/",
    "https://mkt.boulangerie.com.br/",
)
HEADERS = ("Cache-Control", "CF-Cache-Status", "Age", "Server-Timing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "method": "GET anônimo, sem cookies, sequencial, intervalo de 1 s; total HTTP, não TTFB",
        "rows": [],
    }
    aborted = False
    for url in URLS:
        for sample in range(args.samples):
            request = urllib.request.Request(url, headers={"User-Agent": "Shopman-performance-readonly/1.0"})
            started = time.perf_counter()
            try:
                response = urllib.request.urlopen(request, timeout=15)
            except urllib.error.HTTPError as error:
                response = error
            except urllib.error.URLError as error:
                result["error"] = type(error.reason).__name__
                aborted = True
                break
            with response:
                body = response.read()
                row = {
                    "url": url,
                    "sample": sample + 1,
                    "status": response.status,
                    "total_ms": round((time.perf_counter() - started) * 1000, 2),
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "headers": {name: response.headers.get(name) for name in HEADERS},
                }
            result["rows"].append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if row["status"] >= 500:
                aborted = True
                break
            time.sleep(1)
        if aborted:
            break
    result["aborted"] = aborted
    result["summary"] = []
    for url in URLS:
        rows = [row for row in result["rows"] if row["url"] == url]
        if rows:
            result["summary"].append(
                {
                    "url": url,
                    "n": len(rows),
                    "median_total_ms": statistics.median(row["total_ms"] for row in rows),
                    "maximum_total_ms": max(row["total_ms"] for row in rows),
                    "statuses": [row["status"] for row in rows],
                }
            )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return int(aborted)


if __name__ == "__main__":
    raise SystemExit(main())
