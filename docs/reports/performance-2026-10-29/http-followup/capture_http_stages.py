"""HTTP real sequencial: conexão reutilizada, TTFB e Server-Timing separados.

Não grava corpos, cookies, credenciais ou cabeçalhos arbitrários. O primeiro
transfer pode abrir conexão; num_connects identifica o custo de transporte.
"""

import argparse
import json
import statistics
import subprocess
from datetime import UTC, datetime
from pathlib import Path

BASES = {
    "origin": "https://api.boulangerie.com.br",
    "bff": "https://www.nelsonboulangerie.com.br",
}
FIELDS = (
    "url_effective", "http_code", "time_namelookup", "time_connect", "time_appconnect",
    "time_pretransfer", "time_starttransfer", "time_total", "num_connects", "size_download",
)
HEADERS = ("server-timing", "cf-cache-status", "age", "cache-control")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--samples", type=int, default=5, choices=range(1, 11))
    parser.add_argument("--surface", choices=BASES, default="origin")
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    prefix = "/api/v1/storefront/" + ("public/" if args.public else "")
    routes = {"catalog": prefix + "catalog/", "pdp": prefix + "products/FENDU/"}
    fmt = "\t".join([*("%{" + field + "}" for field in FIELDS), *("%header{" + h + "}" for h in HEADERS)]) + "\n"
    command = [
        "curl", "--silent", "--show-error", "--fail", "--fail-early", "--max-time", "15",
        "--rate", "1/s", "--write-out", fmt,
    ]
    for route in routes.values():
        for _ in range(args.samples):
            command.extend(["--url", BASES[args.surface] + route, "--output", "/dev/null"])
    captured = datetime.now(UTC).isoformat()
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=args.samples * 32)
    rows = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != len(FIELDS) + len(HEADERS):
            raise ValueError("Formato de métricas HTTP inesperado")
        row = dict(zip(FIELDS, parts[:len(FIELDS)], strict=True))
        row["headers"] = dict(zip(HEADERS, parts[len(FIELDS):], strict=True))
        for field in FIELDS[2:8]:
            row[field] = float(row[field])
        for field in ("http_code", "num_connects", "size_download"):
            row[field] = int(row[field])
        rows.append(row)
    summary = {}
    for name, route in routes.items():
        sample = [r for r in rows if r["url_effective"] == BASES[args.surface] + route]
        summary[name] = {
            "n": len(sample),
            "p50_total_ms": round(statistics.median(r["time_total"] for r in sample) * 1000, 2),
            "p50_ttfb_ms": round(statistics.median(r["time_starttransfer"] for r in sample) * 1000, 2),
            "maximum_total_ms": round(max(r["time_total"] for r in sample) * 1000, 2),
        }
    output = {
        "label": args.label, "captured_utc": captured, "surface": args.surface,
        "public": args.public, "method": "Sequential curl, reuse allowed, 1 transfer/s maximum; no cookies or auth",
        "samples": rows, "summary": summary,
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
