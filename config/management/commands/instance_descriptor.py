"""Dump or diff the database projection of an Instance descriptor."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from config.instance_descriptors import (
    UnsafeDescriptor,
    UnsupportedInstanceSection,
    apply_to_database,
    assert_export_safe,
    descriptor_diff,
    load_descriptor,
    project_from_database,
)


class Command(BaseCommand):
    help = "Dump, diff, or atomically apply a database-backed Instance descriptor"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=("dump", "diff", "apply"))
        parser.add_argument("--descriptor", type=Path, required=True)
        parser.add_argument("--confirm-instance")

    def handle(self, *args, **options):
        path: Path = options["descriptor"]
        try:
            declared = load_descriptor(path)
            assert_export_safe(declared["bootstrap"])
            if options["action"] == "apply":
                expected_ref = declared["instance"]["ref"]
                if options["confirm_instance"] != expected_ref:
                    raise ValueError(
                        f"apply requires --confirm-instance {expected_ref}"
                    )
                result = apply_to_database(declared)
                self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
                return
            projected = project_from_database(declared)
        except (
            OSError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
            UnsafeDescriptor,
            UnsupportedInstanceSection,
        ) as exc:
            raise CommandError(str(exc)) from exc

        if options["action"] == "dump":
            self.stdout.write(json.dumps(projected, ensure_ascii=False, indent=2, sort_keys=True))
            return

        changes = descriptor_diff(declared, projected)
        self.stdout.write(json.dumps({"drift": bool(changes), "changes": changes}, ensure_ascii=False, indent=2, sort_keys=True))
        if changes:
            raise CommandError(f"instance descriptor drift: {len(changes)} change(s)", returncode=1)
