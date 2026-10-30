"""Coleta GETs sem descartar erros de transporte ou respostas HTTP incompletas.

Não guarda corpos, cookies, credenciais ou endereços locais/remotos. Um processo
curl reutiliza conexões; cada transferência registra seu próprio exit code.
"""

import argparse
import json
import statistics
import subprocess
from datetime import UTC, datetime
from pathlib import Path

BASES = {"origin": "https://api.boulangerie.com.br", "bff": "https://www.nelsonboulangerie.com.br"}
FIELDS = (
    "url_effective", "http_code", "http_connect", "http_version", "exitcode", "errormsg",
    "num_connects", "time_namelookup", "time_connect", "time_appconnect",
    "time_pretransfer", "time_starttransfer", "time_total", "size_download", "proxy_used",
)
HEADERS = ("server-timing", "cf-cache-status", "age", "cf-ray", "date", "cache-control", "x-storefront-request-id")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", choices=BASES, default="bff")
    parser.add_argument("--pages", action="store_true")
    parser.add_argument("--samples", type=int, choices=range(1, 21), default=10)
    parser.add_argument("--protocol", choices=("auto", "http1.1", "http2"), default="auto")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    routes = {"catalog": "/menu", "pdp": "/produto/FENDU"} if args.pages else {
        "catalog": "/api/v1/storefront/catalog/", "pdp": "/api/v1/storefront/products/FENDU/",
    }
    command = ["curl", "--silent", "--show-error", "--fail", "--max-time", "15", "--rate", "1/s"]
    if args.protocol != "auto":
        command.append("--" + args.protocol)
    # Sem fail-early: a falha de uma transferência não apaga as seguintes.
    fmt = "%{json}" + "\t" + "\t".join("%header{" + h + "}" for h in HEADERS) + "\n"
    command.extend(["--write-out", fmt])
    for route in routes.values():
        for _ in range(args.samples):
            command.extend(["--url", BASES[args.surface] + route, "--output", "/dev/null"])
    captured = datetime.now(UTC).isoformat()
    result = subprocess.run(command, capture_output=True, text=True, check=False,
                            timeout=32 * args.samples + 30)
    rows = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != len(HEADERS) + 1:
            raise ValueError("Métricas curl incompletas; não interpretar como sucesso")
        raw = json.loads(parts[0])
        row = {key: raw.get(key) for key in FIELDS}
        row["headers"] = dict(zip(HEADERS, parts[1:], strict=True))
        rows.append(row)
    summary = {}
    for name, route in routes.items():
        sample = [r for r in rows if r["url_effective"] == BASES[args.surface] + route]
        success = [r for r in sample if r["exitcode"] == 0 and r["http_code"] == 200]
        summary[name] = {
            "n": len(sample), "successful": len(success), "failed": len(sample) - len(success),
            "p50_success_ms": round(statistics.median(r["time_total"] for r in success) * 1000, 2) if success else None,
            "maximum_observed_ms": round(max(r["time_total"] for r in sample) * 1000, 2) if sample else None,
        }
    output = {"label": args.label, "captured_utc": captured, "surface": args.surface,
              "pages": args.pages, "protocol": args.protocol, "curl_process_exitcode": result.returncode,
              "expected_samples": 2 * args.samples, "observed_samples": len(rows),
              "method": "Sequential GETs, connection reuse allowed, <=1 transfer/s; all exit codes retained; no bodies/cookies saved",
              "summary": summary, "samples": rows}
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary))
    if len(rows) != 2 * args.samples:
        raise RuntimeError("Coleta parcial persistida: quantidade de transferências divergente")


if __name__ == "__main__":
    main()
