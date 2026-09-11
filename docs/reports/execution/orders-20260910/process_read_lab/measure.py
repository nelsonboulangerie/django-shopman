"""Compare one/four localhost Daphne readers; fixed rich synthetic 500-order DB."""
import json
import math
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil
import requests

ROOT = Path(__file__).resolve().parents[5]
assert ROOT.name == "django-shopman-orders-execution-20260910"
cookies = json.loads((ROOT / ".orders-lab/http-lab-auth.json").read_text())["cookies"]


def once(port):
    start = time.perf_counter()
    response = requests.get(f"http://127.0.0.1:{port}/api/v1/backstage/orders/", cookies=cookies, timeout=60)
    elapsed = (time.perf_counter() - start) * 1000
    assert response.status_code == 200, response.status_code
    assert response.json()["queue"]["total_count"] == 500
    return {"port": port, "http_ms": elapsed, "backend_ms": float(response.headers["X-Lab-Backend-Ms"]),
            "queries": int(response.headers["X-Lab-Queries"]), "hold_queries": int(response.headers["X-Lab-Hold-Queries"]),
            "process_rss_bytes": int(response.headers["X-Lab-Rss-Bytes"]), "bytes": len(response.content)}


def distribution(samples, key):
    ordered = sorted(s[key] for s in samples)
    return {"p50": ordered[math.ceil(len(ordered) * .5) - 1], "p95": ordered[math.ceil(len(ordered) * .95) - 1], "max": ordered[-1]}


first = [once(port) for port in (8016, 8017, 8018, 8019)]
results = []
for processes in (1, 4):
    for clients in (1, 2, 10):
        with ThreadPoolExecutor(max_workers=clients) as pool:
            samples = list(pool.map(lambda index, processes=processes: once(8016 + index % processes), range(20)))
        results.append({"processes": processes, "clients": clients, "samples": samples,
                        "http_ms": distribution(samples, "http_ms"), "backend_ms": distribution(samples, "backend_ms")})
result = {"platform": platform.platform(), "logical_cpus": psutil.cpu_count(), "memory_bytes": psutil.virtual_memory().total,
          "first_request_each_process": first, "results": results,
          "scope": "One/four Daphne reader processes; client-side round robin, no BFF/load balancer, localhost, same rich 500 fixture. Not production topology or pilot approval."}
(ROOT / ".orders-lab/process-read-result.json").write_text(json.dumps(result, indent=2))
print(json.dumps([{k: v for k, v in row.items() if k != "samples"} for row in results]))
