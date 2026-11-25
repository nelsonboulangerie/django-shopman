#!/usr/bin/env python
"""Baseline da CI medido na API do GitHub, reproduzível (só leitura).

Responde, com número e janela declarada, o que o plano de CI/DX precisa saber
antes de mexer em qualquer coisa:

* **fila** (``merge_group``): por grupo, do primeiro workflow criado ao último
  terminado (o relógio que o PR espera), qual workflow fechou por último
  (o caminho crítico) e como o grupo terminou;
* **PR** (``pull_request``): duração por workflow;
* **PR pronto → merge**: entrada na fila → merge, e quantas vezes o PR saiu da
  fila e por quê (``REMOVED_FROM_MERGE_QUEUE_EVENT.reason``);
* **jobs** (amostra): espera por runner (``started - created``) e execução,
  por job do Runtime Gate e do Surfaces Gate;
* **minutos e dinheiro** do mês, por SKU de runner (``settings/billing/usage``).

Sem dependência fora da stdlib; fala com o GitHub pelo ``gh`` já autenticado.
As respostas brutas ficam em ``--cache`` (padrão ``.ci-baseline/``, fora do
git) e uma segunda rodada não refaz chamada já feita para dia fechado.

    python scripts/ci_baseline.py --since 2026-10-26 --until 2026-11-25
    python scripts/ci_baseline.py --since 2026-11-18 --jobs-days 2 --json out.json

Regime: ``--split 2026-11-17`` (padrão) separa antes/depois da decisão
"leve no PR, pesado na fila" (docs/reference/ci-escopo.md).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = "nelsonboulangerie/django-shopman"
OWNER, NAME = REPO.split("/")

#: Workflows cujo fim decide o grupo da fila (produzem check obrigatório).
#: Os outros (Ficou de fora, Omotenashi, cache) terminam em segundos ou não
#: bloqueiam; ficam no relatório por workflow mas não no relógio do grupo.
GATE_WORKFLOWS = {
    "Runtime Gate",
    "Surfaces Gate",
    "Security Gate",
    "Production Contract",
    "Operator Groups Gate",
    "Ficou de fora",
    "Omotenashi Gate",
}
JOB_SAMPLE_WORKFLOWS = {"Runtime Gate", "Surfaces Gate"}


def ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def gh_json(path: str, attempts: int = 4) -> dict:
    """``gh api`` com retentativa: 502/timeout da API não derrubam a medição."""
    for attempt in range(attempts):
        proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        if attempt == attempts - 1:
            raise subprocess.CalledProcessError(proc.returncode, ["gh", "api", path], proc.stdout, proc.stderr)
        print(f"  ↻ {path[:80]}… ({proc.stderr.strip()[:80]})", file=sys.stderr)
        time.sleep(2 ** (attempt + 1))
    raise AssertionError("inalcançável")


def gh_graphql(query: str, attempts: int = 4) -> dict:
    for attempt in range(attempts):
        proc = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"], capture_output=True, text=True)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        if attempt == attempts - 1:
            raise subprocess.CalledProcessError(proc.returncode, "gh api graphql", proc.stdout, proc.stderr)
        print(f"  ↻ graphql ({proc.stderr.strip()[:80]})", file=sys.stderr)
        time.sleep(2 ** (attempt + 1))
    raise AssertionError("inalcançável")


class Cache:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, fetch, *, reusable: bool):
        path = self.root / (key.replace("/", "_") + ".json")
        if reusable and path.exists():
            return json.loads(path.read_text())
        data = fetch()
        path.write_text(json.dumps(data))
        return data


RUN_FIELDS = (
    "id", "name", "head_branch", "head_sha", "status", "conclusion",
    "created_at", "run_started_at", "updated_at", "run_attempt",
)


def runs_in_window(event: str, window: str) -> tuple[list[dict], int]:
    """Runs de uma janela ``created=`` (até 1.000: limite da busca da API)."""
    runs: list[dict] = []
    total = 0
    for page in range(1, 11):
        data = gh_json(f"repos/{REPO}/actions/runs?event={event}&created={window}&per_page=100&page={page}")
        total = data.get("total_count", 0)
        batch = data.get("workflow_runs", [])
        runs.extend({k: r.get(k) for k in RUN_FIELDS} for r in batch)
        if len(batch) < 100:
            break
    return runs, total


def runs_for_day(cache: Cache, event: str, day: dt.date, today: dt.date) -> list[dict]:
    """Um dia inteiro. A busca da API para em 1.000 resultados; dia mais cheio
    que isso (a fila de 18 e 19/11 passou) é lido de hora em hora."""

    def fetch():
        runs, total = runs_in_window(event, day.isoformat())
        if total <= len(runs):
            return runs
        runs = []
        for hour in range(24):
            window = f"{day}T{hour:02d}:00:00Z..{day}T{hour:02d}:59:59Z"
            chunk, total = runs_in_window(event, window)
            if total > len(chunk):
                print(f"⚠️ {event} {window}: {total} runs, lidos {len(chunk)}", file=sys.stderr)
            runs.extend(chunk)
        return runs

    return cache.get(f"runs-v2-{event}-{day}", fetch, reusable=day < today)


def jobs_for_run(cache: Cache, run_id: int) -> list[dict]:
    def fetch():
        data = gh_json(f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100&filter=latest")
        return [
            {
                k: j.get(k)
                for k in ("name", "conclusion", "created_at", "started_at", "completed_at", "labels")
            }
            for j in data.get("jobs", [])
        ]

    return cache.get(f"jobs-{run_id}", fetch, reusable=True)


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[idx]


def fmt_min(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return f"{seconds / 60:.1f}"


def summary(values: list[float]) -> dict:
    return {
        "n": len(values),
        "p50_min": round(pct(values, 0.5) / 60, 1) if values else None,
        "p95_min": round(pct(values, 0.95) / 60, 1) if values else None,
        "mean_min": round(statistics.fmean(values) / 60, 1) if values else None,
    }


def group_key(run: dict) -> str:
    return run["head_branch"] or run["head_sha"]


def analyse_queue(runs: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        if r["status"] != "completed":
            continue
        groups[group_key(r)].append(r)

    wall: list[float] = []
    critical = Counter()
    outcome = Counter()
    per_workflow: dict[str, list[float]] = defaultdict(list)
    for runs_of_group in groups.values():
        gate = [r for r in runs_of_group if r["name"] in GATE_WORKFLOWS]
        if not gate:
            continue
        start = min(ts(r["created_at"]) for r in gate)
        last = max(gate, key=lambda r: ts(r["updated_at"]))
        conclusions = {r["conclusion"] for r in gate}
        if conclusions <= {"success", "skipped"}:
            outcome["success"] += 1
            wall.append((ts(last["updated_at"]) - start).total_seconds())
            critical[last["name"]] += 1
        elif "failure" in conclusions:
            outcome["failure"] += 1
        else:
            outcome["cancelled/other"] += 1
        for r in runs_of_group:
            if r["conclusion"] == "success":
                per_workflow[r["name"]].append(
                    (ts(r["updated_at"]) - ts(r["created_at"])).total_seconds()
                )
    return {
        "groups": len(groups),
        "outcome": dict(outcome),
        "success_wall": summary(wall),
        "critical_path_last_to_finish": dict(critical.most_common()),
        "per_workflow_success": {k: summary(v) for k, v in sorted(per_workflow.items())},
    }


def analyse_pr(runs: list[dict]) -> dict:
    per_workflow: dict[str, list[float]] = defaultdict(list)
    outcome: dict[str, Counter] = defaultdict(Counter)
    for r in runs:
        if r["status"] != "completed":
            continue
        outcome[r["name"]][r["conclusion"]] += 1
        if r["conclusion"] == "success":
            per_workflow[r["name"]].append(
                (ts(r["updated_at"]) - ts(r["created_at"])).total_seconds()
            )
    return {
        "per_workflow_success": {k: summary(v) for k, v in sorted(per_workflow.items())},
        "outcome": {k: dict(v) for k, v in sorted(outcome.items())},
    }


def analyse_jobs(cache: Cache, runs: list[dict]) -> dict:
    wait: dict[str, list[float]] = defaultdict(list)
    run_s: dict[str, list[float]] = defaultdict(list)
    labels: Counter = Counter()
    for r in runs:
        if r["name"] not in JOB_SAMPLE_WORKFLOWS or r["status"] != "completed":
            continue
        for j in jobs_for_run(cache, r["id"]):
            if j["conclusion"] != "success" or not j["started_at"]:
                continue
            name = f'{r["name"]} › {j["name"]}'
            wait[name].append((ts(j["started_at"]) - ts(j["created_at"])).total_seconds())
            run_s[name].append((ts(j["completed_at"]) - ts(j["started_at"])).total_seconds())
            labels[",".join(j.get("labels") or [])] += 1
    rows = {
        name: {"wait": summary(wait[name]), "run": summary(run_s[name])}
        for name in sorted(run_s, key=lambda n: -(pct(run_s[n], 0.5) or 0))
    }
    return {"jobs": rows, "runner_labels": dict(labels.most_common())}


def analyse_merges(since: dt.date, until: dt.date) -> dict:
    """PR pronto→merge e saídas da fila, por GraphQL (50 PRs por chamada)."""
    entered_to_merge: list[float] = []
    removals = Counter()
    prs_with_reentry = 0
    total = 0
    cursor = ""
    while True:
        after = f', after: "{cursor}"' if cursor else ""
        search = f"repo:{REPO} is:pr is:merged merged:{since.isoformat()}..{until.isoformat()}"
        q = (
            '{ search(query: "' + search + '", type: ISSUE, first: 20' + after + ") {"
            " pageInfo { hasNextPage endCursor } nodes { ... on PullRequest { number mergedAt"
            " timelineItems(first: 30, itemTypes: [ADDED_TO_MERGE_QUEUE_EVENT, REMOVED_FROM_MERGE_QUEUE_EVENT]) {"
            " nodes { __typename ... on AddedToMergeQueueEvent { createdAt }"
            " ... on RemovedFromMergeQueueEvent { createdAt reason } } } } } } }"
        )
        data = gh_graphql(q)["data"]["search"]
        for pr in data["nodes"]:
            if not pr:
                continue
            events = pr["timelineItems"]["nodes"]
            adds = [ts(e["createdAt"]) for e in events if e["__typename"] == "AddedToMergeQueueEvent"]
            rems = [e for e in events if e["__typename"] == "RemovedFromMergeQueueEvent"]
            if not adds:
                continue
            total += 1
            entered_to_merge.append((ts(pr["mergedAt"]) - min(adds)).total_seconds())
            if rems:
                prs_with_reentry += 1
            for e in rems:
                removals[e.get("reason") or "?"] += 1
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]
    return {
        "merged_via_queue": total,
        "first_enqueue_to_merge": summary(entered_to_merge),
        "prs_removed_at_least_once": prs_with_reentry,
        "removal_reasons": dict(removals.most_common()),
    }


def billing(month: dt.date) -> list[dict]:
    try:
        data = gh_json(
            f"/orgs/{OWNER}/settings/billing/usage?year={month.year}&month={month.month}"
        )
    except subprocess.CalledProcessError as exc:  # sem permissão de billing
        return [{"error": exc.stderr.strip()[:200]}]
    rows = defaultdict(lambda: {"minutes": 0.0, "gross": 0.0, "net": 0.0})
    for item in data.get("usageItems", []):
        if item.get("product") != "actions" or item.get("repositoryName") != NAME:
            continue
        row = rows[item["sku"]]
        row["minutes"] += item["quantity"]
        row["gross"] += item["grossAmount"]
        row["net"] += item["netAmount"]
    return [
        {"sku": sku, **{k: round(v, 2) for k, v in row.items()}} for sku, row in sorted(rows.items())
    ]


def days(since: dt.date, until: dt.date):
    d = since
    while d <= until:
        yield d
        d += dt.timedelta(days=1)


def print_report(rep: dict) -> None:
    print(f"# Baseline da CI · {rep['window']}  (gerado {rep['generated_at']})\n")
    for regime, block in rep["regimes"].items():
        q = block["queue"]
        print(f"## {regime}\n")
        print(
            f"Fila: {q['groups']} grupos · desfecho {q['outcome']} · "
            f"relógio do grupo verde p50 {q['success_wall']['p50_min']} min, "
            f"p95 {q['success_wall']['p95_min']} min (n={q['success_wall']['n']})"
        )
        print(f"Último a terminar (caminho crítico): {q['critical_path_last_to_finish']}\n")
        print("| workflow (fila, sucesso) | n | p50 min | p95 min |\n|---|---:|---:|---:|")
        for name, s in q["per_workflow_success"].items():
            print(f"| {name} | {s['n']} | {s['p50_min']} | {s['p95_min']} |")
        print("\n| workflow (PR, sucesso) | n | p50 min | p95 min |\n|---|---:|---:|---:|")
        for name, s in block["pr"]["per_workflow_success"].items():
            print(f"| {name} | {s['n']} | {s['p50_min']} | {s['p95_min']} |")
        print()
    m = rep.get("merges")
    if m:
        print("## Fila → merge\n")
        print(
            f"{m['merged_via_queue']} PRs mergeados pela fila · 1ª entrada→merge "
            f"p50 {m['first_enqueue_to_merge']['p50_min']} min, p95 {m['first_enqueue_to_merge']['p95_min']} min · "
            f"{m['prs_removed_at_least_once']} saíram da fila ao menos 1x · motivos {m['removal_reasons']}\n"
        )
    j = rep.get("jobs")
    if j:
        print(f"## Jobs (amostra: {rep['jobs_window']})\n")
        print("| job | n | espera p50 | espera p95 | execução p50 | execução p95 |\n|---|---:|---:|---:|---:|---:|")
        for name, s in list(j["jobs"].items())[:25]:
            print(
                f"| {name} | {s['run']['n']} | {s['wait']['p50_min']} | {s['wait']['p95_min']} | "
                f"{s['run']['p50_min']} | {s['run']['p95_min']} |"
            )
        print(f"\nRótulos de runner: {j['runner_labels']}\n")
    print("## Minutos e dinheiro (mês, este repo)\n")
    for row in rep["billing"]:
        print(f"- {row}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    today = dt.datetime.now(dt.UTC).date()
    parser.add_argument("--since", type=dt.date.fromisoformat, default=today - dt.timedelta(days=30))
    parser.add_argument("--until", type=dt.date.fromisoformat, default=today)
    parser.add_argument("--split", type=dt.date.fromisoformat, default=dt.date(2026, 11, 17))
    parser.add_argument("--jobs-days", type=int, default=2, help="dias finais com amostra de jobs (0 desliga)")
    parser.add_argument("--no-merges", action="store_true")
    parser.add_argument("--cache", type=Path, default=Path(".ci-baseline"))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    cache = Cache(args.cache)
    by_regime: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    job_runs: list[dict] = []
    jobs_from = args.until - dt.timedelta(days=max(args.jobs_days - 1, 0))
    for day in days(args.since, args.until):
        regime = (
            f"antes de {args.split} (tudo no PR e na fila)"
            if day < args.split
            else f"desde {args.split} (leve no PR, pesado na fila)"
        )
        for event, label in (("merge_group", "queue"), ("pull_request", "pr")):
            runs = runs_for_day(cache, event, day, today)
            by_regime[regime][label].extend(runs)
            if event == "merge_group" and args.jobs_days and day >= jobs_from:
                job_runs.extend(runs)
        print(f"· {day}", file=sys.stderr)

    rep: dict = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "window": f"{args.since}..{args.until}",
        "regimes": {
            regime: {"queue": analyse_queue(d["queue"]), "pr": analyse_pr(d["pr"])}
            for regime, d in sorted(by_regime.items())
        },
        "billing": billing(args.until),
    }
    if not args.no_merges:
        rep["merges"] = analyse_merges(max(args.split, args.since), args.until)
    if job_runs:
        rep["jobs_window"] = f"{jobs_from}..{args.until} (merge_group)"
        rep["jobs"] = analyse_jobs(cache, job_runs)
    if args.json:
        args.json.write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    print_report(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
