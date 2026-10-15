#!/usr/bin/env python
"""Shopman migrations gate.

Answers one question, honestly, in the pre-prod phase:

    "Does the migration graph build a clean schema from zero, with nothing
     uncommitted?"

Checks executed today (pre go-live):

1. ``makemigrations --check --dry-run`` — no model change lacks a migration.
2. Fresh ``migrate`` from zero into a throwaway SQLite database — the whole
   graph applies linearly without errors.
3. ``migrate --check`` against that fresh database — the graph is fully applied
   and internally consistent (no missing dependency, no unapplied leftover).
4. **Unambiguous migration numbering** — two files in the same app sharing a
   number, without a merge migration reconciling them, means the next
   ``makemigrations`` picks an arbitrary base and one of them becomes an orphan
   leaf (``multiple leaf nodes in the migration graph``). Duplicates already in
   the repository before this check existed are NAMED in
   ``LEGACY_PREFIX_COLLISIONS`` and stay green (renumbering an applied migration
   is forbidden); any new one fails. ``SHOPMAN_MIGRATION_PREFIX_STRICT=1`` fails
   on the inherited ones too.

From go-live onward (the ``go-live-v1`` tag exists — ADR-015) one more check
arms itself:

5. Every migration file added AFTER the tag that contains a destructive
   operation (``RemoveField``, ``DeleteModel``, ``RenameField``,
   ``RenameModel``, ``AlterField``) must carry an explicit expand-contract
   marker — ``# expand-contract: <fase> — <link do plano>``. Before the tag
   this check is an honest no-op (skipped, not silently passed).

Reserved for go-live (WP-GAP-07): replaying a real production *baseline*
snapshot and validating data survives the upgrade. That step needs a snapshot
to exist, so it stays a documented, skipped slot until then — see
``SHOPMAN_MIGRATIONS_BASELINE`` below.

Local failures exit non-zero. The script never touches the dev database: it
migrates into a temporary SQLite file that is removed on exit.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import check_adr015  # noqa: E402 — ADR-015 helpers (tag detection, destructive-op scan)

Status = Literal["passed", "failed", "skipped"]


@dataclass(frozen=True)
class MigrationCheck:
    id: str
    title: str
    status: Status
    message: str
    details: dict[str, object] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status == "failed"

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "message": self.message,
        }
        if self.details:
            data["details"] = self.details
        return data


@dataclass(frozen=True)
class MigrationReport:
    checks: tuple[MigrationCheck, ...]

    @property
    def blocking(self) -> bool:
        return any(check.failed for check in self.checks)

    @property
    def status(self) -> str:
        return "failed" if self.blocking else "passed"

    @property
    def counts(self) -> dict[str, int]:
        statuses = ("passed", "failed", "skipped")
        return {status: sum(1 for check in self.checks if check.status == status) for status in statuses}

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "counts": self.counts,
            "checks": [check.as_dict() for check in self.checks],
        }


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        django.setup()
    finally:
        logging.disable(previous_disable_level)


@contextmanager
def _suppress_logs():
    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous_disable_level)


def _no_uncommitted_migrations() -> MigrationCheck:
    from django.core.management import call_command

    try:
        output = StringIO()
        call_command("makemigrations", check=True, dry_run=True, stdout=output, stderr=output, verbosity=0)
    except SystemExit as exc:  # makemigrations --check exits non-zero when changes are missing
        if exc.code:
            return MigrationCheck(
                id="migrations.committed",
                title="No model change without a migration",
                status="failed",
                message="Model changes exist without a matching migration. Run makemigrations.",
            )
    except Exception as exc:  # noqa: BLE001 - any failure here blocks release
        return MigrationCheck(
            id="migrations.committed",
            title="No model change without a migration",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )
    return MigrationCheck(
        id="migrations.committed",
        title="No model change without a migration",
        status="passed",
        message="No model changes without migrations.",
    )


@contextmanager
def _fresh_sqlite_database():
    """Point the default connection at a throwaway SQLite file.

    Django fills missing connection defaults when the handler re-reads
    ``settings.DATABASES``, so a minimal ENGINE+NAME dict is enough. The dev
    database is never touched.
    """
    from django.conf import settings
    from django.db import connections

    tmp_dir = tempfile.mkdtemp(prefix="shopman-migrations-")
    db_path = os.path.join(tmp_dir, "fresh.sqlite3")

    original = settings.DATABASES
    settings.DATABASES = {
        **original,
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": db_path,
            "OPTIONS": {"timeout": 10},
        },
    }
    connections.close_all()
    connections.__dict__.pop("databases", None)  # drop cached_property so settings re-read
    try:
        yield db_path
    finally:
        connections.close_all()
        connections.__dict__.pop("databases", None)
        settings.DATABASES = original
        try:
            os.remove(db_path)
        except OSError:
            pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


def _clean_schema_build() -> tuple[MigrationCheck, MigrationCheck]:
    from django.core.management import call_command

    try:
        with _fresh_sqlite_database():
            output = StringIO()
            call_command("migrate", stdout=output, stderr=output, verbosity=0, no_input=True)
            build = MigrationCheck(
                id="migrations.clean_build",
                title="Clean schema builds from zero",
                status="passed",
                message="Full migration graph applied on an empty database.",
            )

            consistent = StringIO()
            try:
                call_command("migrate", check_unapplied=True, stdout=consistent, stderr=consistent, verbosity=0)
            except SystemExit as exc:
                if exc.code:
                    graph = MigrationCheck(
                        id="migrations.graph_consistent",
                        title="Migration graph fully applied",
                        status="failed",
                        message="migrate --check reported unapplied/inconsistent migrations after a full build.",
                    )
                    return build, graph
            graph = MigrationCheck(
                id="migrations.graph_consistent",
                title="Migration graph fully applied",
                status="passed",
                message="migrate --check is clean after a full build.",
            )
            return build, graph
    except Exception as exc:  # noqa: BLE001 - a broken graph must surface as a failure
        build = MigrationCheck(
            id="migrations.clean_build",
            title="Clean schema builds from zero",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )
        graph = MigrationCheck(
            id="migrations.graph_consistent",
            title="Migration graph fully applied",
            status="failed",
            message="Skipped because the clean build failed.",
        )
        return build, graph


def _baseline_replay() -> MigrationCheck:
    """Reserved go-live step: replay a real baseline snapshot and validate data.

    Activates only once ``SHOPMAN_MIGRATIONS_BASELINE`` points at a snapshot,
    which exists from go-live onward (WP-GAP-07). Until then it is an honest,
    explicitly skipped slot — not a silent pass.
    """
    baseline = (os.environ.get("SHOPMAN_MIGRATIONS_BASELINE", "") or "").strip()
    if not baseline:
        return MigrationCheck(
            id="migrations.baseline_replay",
            title="Baseline snapshot replay (go-live)",
            status="skipped",
            message="No baseline snapshot declared yet (pre go-live).",
            details={
                "expected": "Set SHOPMAN_MIGRATIONS_BASELINE=/path/to/snapshot once a production baseline exists."
            },
        )
    if not Path(baseline).expanduser().exists():
        return MigrationCheck(
            id="migrations.baseline_replay",
            title="Baseline snapshot replay (go-live)",
            status="failed",
            message="SHOPMAN_MIGRATIONS_BASELINE is set but the snapshot file does not exist.",
            details={"baseline": baseline},
        )
    # Replay against a real baseline is implemented at go-live (WP-GAP-07), when
    # the snapshot format and validation set are known. Declaring it here keeps
    # the contract visible without pretending it ran.
    return MigrationCheck(
        id="migrations.baseline_replay",
        title="Baseline snapshot replay (go-live)",
        status="skipped",
        message="Baseline declared; replay harness lands at go-live (WP-GAP-07).",
        details={"baseline": baseline},
    )


def _expand_contract_markers() -> MigrationCheck:
    """ADR-015: post-tag migrations with destructive ops need the marker.

    Armed by the existence of the ``go-live-v1`` tag. Before that it is an
    honest, explicitly skipped slot — pre-go-live the policy is inactive.
    """
    check_id = "migrations.expand_contract"
    title = "Destructive migrations carry the expand-contract marker (ADR-015)"
    if not check_adr015.go_live_active(ROOT):
        return MigrationCheck(
            id=check_id,
            title=title,
            status="skipped",
            message="pré-go-live: política ADR-015 inativa (tag go-live-v1 ausente).",
        )
    try:
        violations = check_adr015.expand_contract_violations(ROOT)
    except RuntimeError as exc:
        return MigrationCheck(
            id=check_id,
            title=title,
            status="failed",
            message=f"Não foi possível comparar com a baseline da tag: {exc}",
        )
    if violations:
        return MigrationCheck(
            id=check_id,
            title=title,
            status="failed",
            message=check_adr015.EXPAND_CONTRACT_HOWTO,
            details={"violations": [{"migration": path, "operations": ops} for path, ops in violations]},
        )
    return MigrationCheck(
        id=check_id,
        title=title,
        status="passed",
        message="Nenhuma migração pós-tag com operação destrutiva sem marcador expand-contract.",
    )


#: Duplicatas de prefixo numérico já existentes no repositório, herdadas de
#: sequências paralelas de duas sessões antes desta trava existir. O Django não
#: as confunde (a chave da migração é o NOME do arquivo, não o número), então o
#: grafo as resolve — mas o número repetido esconde qual das duas é a "próxima".
#: Renumerar migração já aplicada é proibido (o `git tag go-live-v1` a torna
#: imutável, e antes dele o histórico ainda é o mesmo), então esta dívida fica
#: NOMEADA em vez de ignorada. A trava reprova qualquer duplicata NOVA; com
#: ``SHOPMAN_MIGRATION_PREFIX_STRICT=1`` ela reprova até estas.
LEGACY_PREFIX_COLLISIONS: frozenset[tuple[str, str]] = frozenset(
    [
        *(("shop", f"{number:04d}") for number in range(23, 40)),
        ("backstage", "0036"),
        ("backstage", "0058"),
        ("backstage", "0065"),
    ]
)


def migration_prefix_check(graph: object, *, strict: bool | None = None) -> MigrationCheck:
    """Analisa um grafo de migrações já carregado. Puro: não toca o banco.

    Recebe o grafo (e não o caminho do arquivo) porque a pergunta é sobre a
    FORMA do grafo: quem são as folhas de cada app. Um teste alimenta um grafo
    sintético e prova o veredito sem escrever arquivo em disco.

    ``strict=None`` lê ``SHOPMAN_MIGRATION_PREFIX_STRICT`` do ambiente; um valor
    explícito serve ao teste.
    """
    check_id = "migrations.prefix_collisions"
    title = "No ambiguous migration numbering (two files, same number)"
    if strict is None:
        strict = (os.environ.get("SHOPMAN_MIGRATION_PREFIX_STRICT", "") or "").strip() in {
            "1",
            "true",
            "yes",
        }

    nodes = sorted(graph.nodes)  # type: ignore[attr-defined]
    leaves = sorted(graph.leaf_nodes())  # type: ignore[attr-defined]

    # Número de ponta repetido SEM merge reconciliando: o caso perigoso.
    ambiguous_leaves: list[dict[str, object]] = []
    for app_label in sorted({label for label, _ in leaves}):
        app_leaves = sorted(name for label, name in leaves if label == app_label)
        if len(app_leaves) < 2:
            continue
        by_prefix: dict[str, list[str]] = {}
        for name in app_leaves:
            by_prefix.setdefault(name.split("_", 1)[0], []).append(name)
        for prefix, names in sorted(by_prefix.items()):
            if len(names) > 1:
                ambiguous_leaves.append({"app": app_label, "prefix": prefix, "leaves": names})

    # Todas as duplicatas de prefixo, com o estado de reconciliação.
    collisions: list[dict[str, object]] = []
    new_collisions: list[dict[str, object]] = []
    for app_label in sorted({label for label, _ in nodes}):
        by_prefix: dict[str, list[str]] = {}
        for _, name in (node for node in nodes if node[0] == app_label):
            by_prefix.setdefault(name.split("_", 1)[0], []).append(name)
        for prefix, names in sorted(by_prefix.items()):
            if len(names) < 2:
                continue
            entry = {
                "app": app_label,
                "prefix": prefix,
                "migrations": names,
                "reconciled_by": [n for n in names if n.endswith("_merge") or "_merge_" in n],
                "legacy": (app_label, prefix) in LEGACY_PREFIX_COLLISIONS,
            }
            collisions.append(entry)
            if not entry["legacy"]:
                new_collisions.append(entry)

    legacy_entries = [entry for entry in collisions if entry["legacy"]]
    details: dict[str, object] = {
        "legacy_count": len(legacy_entries),
        "new_count": len(new_collisions),
        "ambiguous_leaf_count": len(ambiguous_leaves),
    }
    if collisions:
        details["collisions"] = collisions
    if ambiguous_leaves:
        details["ambiguous_leaves"] = ambiguous_leaves
    if legacy_entries:
        details["legacy_note"] = (
            "Duplicatas herdadas, nomeadas e não bloqueantes. Renumerar migração já "
            "aplicada é proibido; a dívida é só de nomenclatura, o grafo resolve."
        )

    if ambiguous_leaves:
        return MigrationCheck(
            id=check_id,
            title=title,
            status="failed",
            message=(
                "Duas migrações dividem o número de PONTA sem uma migração de merge "
                "reconciliando: a próxima makemigrations escolhe uma base arbitrária. "
                "Reconcilie com `makemigrations --merge` (que gera a merge) ou renumere a nova."
            ),
            details=details,
        )
    if new_collisions:
        return MigrationCheck(
            id=check_id,
            title=title,
            status="failed",
            message=(
                "Duplicata NOVA de numeração de migração. Pegue o próximo número livre do app "
                "(`ls <app>/migrations | grep -oE '^[0-9]+' | sort | uniq -d`) antes de commitar."
            ),
            details=details,
        )
    if legacy_entries and strict:
        return MigrationCheck(
            id=check_id,
            title=title,
            status="failed",
            message="SHOPMAN_MIGRATION_PREFIX_STRICT=1: as duplicatas herdadas também reprovam.",
            details=details,
        )
    if legacy_entries:
        return MigrationCheck(
            id=check_id,
            title=title,
            status="passed",
            message=(
                f"Nenhuma duplicata nova. {len(legacy_entries)} herdada(s) seguem nomeadas "
                "(dívida de nomenclatura; o grafo resolve)."
            ),
            details=details,
        )
    return MigrationCheck(
        id=check_id,
        title=title,
        status="passed",
        message="Nenhuma numeração de migração ambígua.",
    )


def _prefix_collisions() -> MigrationCheck:
    """Carrega o grafo real do Django e delega a análise a :func:`migration_prefix_check`."""
    from django.db.migrations.loader import MigrationLoader

    return migration_prefix_check(MigrationLoader(None, ignore_no_migrations=True).graph)


def build_report() -> MigrationReport:
    setup_django()
    with _suppress_logs():
        committed = _no_uncommitted_migrations()
        build, graph = _clean_schema_build()
        prefixes = _prefix_collisions()
        expand_contract = _expand_contract_markers()
        baseline = _baseline_replay()
    return MigrationReport(checks=(committed, build, graph, prefixes, expand_contract, baseline))


def print_human(report: MigrationReport) -> None:
    print(f"check-migrations: {report.status}")
    print(
        f"counts: passed={report.counts['passed']} failed={report.counts['failed']} skipped={report.counts['skipped']}"
    )
    for check in report.checks:
        marker = {"passed": "OK", "failed": "FAIL", "skipped": "SKIP"}[check.status]
        print(f"- [{marker}] {check.id}: {check.message}")
        if check.details:
            print(f"  details={json.dumps(check.details, ensure_ascii=False, sort_keys=True)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Shopman migration graph health.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--strict-prefixes",
        action="store_true",
        help=("Também reprova as duplicatas de numeração herdadas (equivale a SHOPMAN_MIGRATION_PREFIX_STRICT=1)."),
    )
    args = parser.parse_args(argv)

    if args.strict_prefixes:
        os.environ["SHOPMAN_MIGRATION_PREFIX_STRICT"] = "1"

    report = build_report()
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print_human(report)
    return 1 if report.blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
