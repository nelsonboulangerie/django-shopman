from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.watchman.contracts import Scope
from shopman.watchman.registry import build_registry
from shopman.watchman.runner import run_profile


class Command(BaseCommand):
    help = "Run and inspect Shopman Watchman checks."

    def add_arguments(self, parser):
        actions = parser.add_subparsers(dest="action", required=True)

        check = actions.add_parser("check", help="Run one configured profile.")
        check.add_argument("--profile", default="diagnostic")
        check.add_argument("--format", choices=("text", "json"), default="text")

        list_parser = actions.add_parser("list", help="List checks and profiles.")
        list_parser.add_argument("--format", choices=("text", "json"), default="text")

        explain = actions.add_parser("explain", help="Describe one check.")
        explain.add_argument("check_id")
        explain.add_argument("--format", choices=("text", "json"), default="text")

    def handle(self, *args, **options):
        try:
            if options["action"] == "check":
                return self._check(profile=options["profile"], output_format=options["format"])
            if options["action"] == "list":
                return self._list(output_format=options["format"])
            return self._explain(options["check_id"], output_format=options["format"])
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"Invalid Watchman configuration: {exc}", returncode=2) from exc

    def _check(self, *, profile: str, output_format: str):
        report = run_profile(profile)
        if output_format == "json":
            self.stdout.write(json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")))
        else:
            self.stdout.write(f"Watchman profile {profile}: {report.status.value}")
            for result in report.results:
                self.stdout.write(f"- {result.id}: {result.status.value} — {result.summary}")
        if report.exit_code:
            raise CommandError(f"Watchman profile {profile} did not pass", returncode=report.exit_code)

    def _list(self, *, output_format: str):
        registry = build_registry()
        payload = {
            "schema_version": 1,
            "checks": [
                {
                    "id": check.id,
                    "description": check.description,
                    "scopes": sorted(Scope(scope).value for scope in check.scopes),
                    "timeout_seconds": check.timeout_seconds,
                }
                for check in registry.checks
            ],
            "profiles": {name: list(check_ids) for name, check_ids in sorted(registry.profiles.items())},
        }
        if output_format == "json":
            self.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            return
        for check in payload["checks"]:
            self.stdout.write(f"{check['id']}: {check['description']}")

    def _explain(self, check_id: str, *, output_format: str):
        check = build_registry().by_id(check_id)
        payload = {
            "schema_version": 1,
            "id": check.id,
            "description": check.description,
            "scopes": sorted(Scope(scope).value for scope in check.scopes),
            "timeout_seconds": check.timeout_seconds,
        }
        if output_format == "json":
            self.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        else:
            self.stdout.write(f"{check.id}: {check.description}")
            self.stdout.write(f"Scopes: {', '.join(payload['scopes'])}")
            self.stdout.write(f"Timeout: {check.timeout_seconds:g}s")
