"""Export the OpenAPI-derived TypeScript client for Marketing v2."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from shopman.backstage.marketing_client_contract import (
    render_marketing_client_ts,
    render_marketing_openapi_json,
)
from shopman.backstage.projections.marketing_v2 import schema

PROJECTION_RELATIVE_PATH = Path("contracts/projections/marketing_v2.schema.json")
OPENAPI_RELATIVE_PATH = Path("contracts/openapi/marketing_v2.openapi.json")
CLIENT_RELATIVE_PATH = Path(
    "surfaces/marketing-nuxt/app/generated/marketingClient.ts"
)


def rendered_artifacts() -> dict[Path, str]:
    return {
        PROJECTION_RELATIVE_PATH: (
            json.dumps(schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ),
        OPENAPI_RELATIVE_PATH: render_marketing_openapi_json(),
        CLIENT_RELATIVE_PATH: render_marketing_client_ts(),
    }


def write_artifacts(root: Path) -> tuple[Path, ...]:
    written: list[Path] = []
    for relative_path, rendered in rendered_artifacts().items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        written.append(path)
    return tuple(written)


class Command(BaseCommand):
    help = "Generate Marketing v2 OpenAPI and its TypeScript client."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero if either generated artifact is stale.",
        )

    def handle(self, *args, **options) -> None:
        root = Path(settings.BASE_DIR)
        artifacts = rendered_artifacts()
        stale = tuple(
            relative_path
            for relative_path, rendered in artifacts.items()
            if not (root / relative_path).exists()
            or (root / relative_path).read_text(encoding="utf-8") != rendered
        )
        if options.get("check"):
            if stale:
                joined = ", ".join(str(path) for path in stale)
                self.stderr.write(
                    self.style.ERROR(
                        f"Marketing client artifacts are stale: {joined}. "
                        "Run: python manage.py export_marketing_client"
                    )
                )
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS("Marketing client artifacts are up to date."))
            return
        written = write_artifacts(root)
        for path in written:
            self.stdout.write(self.style.SUCCESS(f"Wrote {path.relative_to(root)}"))
