"""Dump, diff ou apply do descritor de Instância.

``apply`` é ensaio por padrão: imprime o diff (o que seria criado, atualizado,
removido, e o que diverge da última versão aplicada) e não escreve nada. Grava
só com ``--commit`` e ``--confirm-instance <ref>``. Valor que o banco tem
diferente da última versão aplicada recusa o apply, a menos que se diga o que
fazer com ele (``--keep-drift`` ou ``--overwrite-drift``). Cada apply gravado
deixa a trilha em ``InstanceApplyRecord`` (quem, quando, o quê).
"""

from __future__ import annotations

import getpass
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from config.instance_descriptors import (
    InstanceDriftConflict,
    ShopSingletonViolation,
    UnsafeDescriptor,
    UnsupportedInstanceSection,
    apply_to_database,
    assert_export_safe,
    descriptor_diff,
    load_descriptor,
    project_from_database,
    without_operational_state,
)


def _default_actor() -> str:
    try:
        return f"cli:{getpass.getuser()}"
    except (OSError, KeyError, ImportError):
        return "cli"


class Command(BaseCommand):
    help = "Dump, diff, or apply (dry-run by default) a database-backed Instance descriptor"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=("dump", "diff", "apply"))
        parser.add_argument("--descriptor", type=Path, required=True)
        parser.add_argument("--confirm-instance")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="apply: grava. Sem isto o apply só relata o diff.",
        )
        parser.add_argument("--actor", help="apply: quem aplica (vai para a trilha)")
        drift = parser.add_mutually_exclusive_group()
        drift.add_argument(
            "--keep-drift",
            action="store_true",
            help="apply: preserva o valor do banco que divergiu da última versão aplicada",
        )
        drift.add_argument(
            "--overwrite-drift",
            action="store_true",
            help="apply: sobrescreve o valor do banco que divergiu da última versão aplicada",
        )

    def handle(self, *args, **options):
        path: Path = options["descriptor"]
        try:
            declared = load_descriptor(path)
            assert_export_safe(declared["bootstrap"])
            if options["action"] == "apply":
                self._apply(declared, options)
                return
            projected = project_from_database(declared)
        except InstanceDriftConflict as exc:
            raise CommandError(str(exc), returncode=1) from exc
        except (
            OSError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
            UnsafeDescriptor,
            UnsupportedInstanceSection,
            ShopSingletonViolation,
        ) as exc:
            raise CommandError(str(exc)) from exc

        if options["action"] == "dump":
            self.stdout.write(json.dumps(projected, ensure_ascii=False, indent=2, sort_keys=True))
            return

        changes = descriptor_diff(without_operational_state(declared), projected)
        self.stdout.write(json.dumps({"drift": bool(changes), "changes": changes}, ensure_ascii=False, indent=2, sort_keys=True))
        if changes:
            raise CommandError(f"instance descriptor drift: {len(changes)} change(s)", returncode=1)

    def _apply(self, declared: dict, options) -> None:
        on_drift = "refuse"
        if options["keep_drift"]:
            on_drift = "keep"
        elif options["overwrite_drift"]:
            on_drift = "overwrite"
        commit = options["commit"]
        if commit:
            expected_ref = declared["instance"]["ref"]
            if options["confirm_instance"] != expected_ref:
                raise ValueError(f"apply --commit requires --confirm-instance {expected_ref}")
        result = apply_to_database(
            declared,
            actor=options["actor"] or _default_actor(),
            on_drift=on_drift,
            dry_run=not commit,
        )
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if not commit:
            self.stderr.write(
                "ensaio: nada foi gravado. Repita com --commit --confirm-instance "
                f"{declared['instance']['ref']} para aplicar."
            )
            conflicts = result["summary"].get("conflict", 0)
            if conflicts:
                raise CommandError(
                    f"{conflicts} valor(es) divergem da última versão aplicada; "
                    "o --commit vai recusar sem --keep-drift ou --overwrite-drift",
                    returncode=1,
                )
