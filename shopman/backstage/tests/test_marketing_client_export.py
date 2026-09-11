"""MKT-023 — generated Marketing OpenAPI/TypeScript drift gate."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings

from shopman.backstage.management.commands.export_marketing_client import (
    CLIENT_RELATIVE_PATH,
    OPENAPI_RELATIVE_PATH,
    PROJECTION_RELATIVE_PATH,
    rendered_artifacts,
    write_artifacts,
)
from shopman.backstage.marketing_client_contract import marketing_openapi


def test_committed_openapi_and_typescript_client_have_no_drift() -> None:
    root = Path(settings.BASE_DIR)
    for relative_path, rendered in rendered_artifacts().items():
        path = root / relative_path
        assert path.exists(), (
            f"{path} missing — run: python manage.py export_marketing_client"
        )
        assert path.read_text(encoding="utf-8") == rendered, (
            f"{path} is stale — run: python manage.py export_marketing_client"
        )


def test_temporary_generation_matches_both_committed_artifacts(tmp_path) -> None:
    generated = write_artifacts(tmp_path)

    assert set(generated) == {
        tmp_path / PROJECTION_RELATIVE_PATH,
        tmp_path / OPENAPI_RELATIVE_PATH,
        tmp_path / CLIENT_RELATIVE_PATH,
    }
    for temporary_path in generated:
        committed_path = Path(settings.BASE_DIR) / temporary_path.relative_to(tmp_path)
        assert temporary_path.read_bytes() == committed_path.read_bytes()


def test_openapi_operations_reference_the_strict_projection_schema() -> None:
    document = marketing_openapi()
    encoded = json.dumps(document)
    operations = {
        operation["operationId"]
        for path in document["paths"].values()
        for operation in path.values()
    }

    assert document["openapi"] == "3.1.0"
    assert operations == {
        "getMarketingAnnouncement",
        "getMarketingBoard",
        "getMarketingHistory",
    }
    assert "#/$defs/" not in encoded
    action = document["components"]["schemas"]["MarketingActionProjectionV2"]
    assert action["additionalProperties"] is False
    assert "publish_announcement_now" in action["properties"]["kind"]["enum"]
    assert document["paths"]["/api/v1/backstage/marketing/v2/"]["get"]["responses"]["304"]["headers"]["ETag"]
    error = document["components"]["schemas"]["MarketingErrorV2"]
    assert error["additionalProperties"] is False
    assert set(error["required"]) == {
        "actions",
        "code",
        "current_version",
        "detail",
        "field_errors",
        "request_id",
        "retryable",
    }
