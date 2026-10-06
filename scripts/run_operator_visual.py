#!/usr/bin/env python3
"""Seleciona e executa a matriz visual canônica por app, rota e cenário."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs/reference/operator-component-ledger.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True)
    parser.add_argument("--route")
    parser.add_argument("--scenario")
    parser.add_argument("--viewports")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--update-snapshots", action="store_true")
    args = parser.parse_args()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    if args.app == "operator-kit":
        if args.route and args.route != "/__operator_kit_catalog":
            parser.error("operator-kit só declara /__operator_kit_catalog")
        if args.scenario and args.scenario != "canonical-layouts":
            parser.error("operator-kit só declara o cenário canonical-layouts")
        selection = {
            "app": "operator-kit",
            "route": "/__operator_kit_catalog",
            "scenario": "canonical-layouts",
            "status": "infrastructure-fixture",
            "config": "playwright.visual.config.ts",
        }
        cwd = ROOT / "surfaces/operator-kit"
        command = ["npx", "playwright", "test", "--config", "playwright.visual.config.ts"]
    else:
        apps = {app["id"]: app for app in ledger["apps"]}
        app = apps.get(args.app)
        if not app:
            parser.error(f"app desconhecido: {args.app}")
        candidates = [
            surface for surface in app["surfaces"]
            if (not args.route or args.route in surface["routes"])
            and (not args.scenario or args.scenario in surface["variants"])
        ]
        if not candidates:
            parser.error("nenhuma tela do ledger casa com a rota/cenário")
        if len(candidates) > 1 and not args.route:
            parser.error("seleção ambígua; informe --route")
        surface = candidates[0]
        runner = surface.get("runner")
        if not runner:
            parser.error(
                f"{args.app}:{surface['id']} continua {surface['status']}; "
                "o WP do app deve declarar runner e evidências antes da execução canônica"
            )
        selection = {
            "app": args.app,
            "surface": surface["id"],
            "route": args.route,
            "scenario": args.scenario,
            "status": surface["status"],
            "runner": runner,
        }
        cwd = ROOT / "surfaces" / app["directory"]
        command = ["npx", "playwright", "test", "--config", runner["config"]]
        if runner.get("spec"):
            command.append(runner["spec"])
        if runner.get("grep"):
            command.extend(["--grep", runner["grep"]])
        # O reporter grava as capturas relativas à raiz declarada no ledger
        # (audit.evidence_root). Sem fixar a raiz aqui, cada app gravaria em
        # surfaces/<app>/test-results e o gate de fechamento não acharia o arquivo.
        evidence_root = str(
            ROOT / (ledger.get("audit") or {}).get("evidence_root", "test-results/operator-evidence")
        )

    print(json.dumps(selection, indent=2, ensure_ascii=False))
    if args.plan:
        return 0
    if args.update_snapshots:
        command.append("--update-snapshots")
    env = os.environ.copy()
    env.update({
        "OPERATOR_VISUAL_APP": args.app,
        "OPERATOR_VISUAL_ROUTE": args.route or "",
        "OPERATOR_VISUAL_SCENARIO": args.scenario or "",
        "OPERATOR_VISUAL_VIEWPORTS": args.viewports or "",
    })
    if args.app != "operator-kit":
        env["OPERATOR_VISUAL_EVIDENCE_ROOT"] = evidence_root
    return subprocess.run(command, cwd=cwd, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
