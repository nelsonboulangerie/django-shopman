from __future__ import annotations

import json
import re
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.directives import ANNOUNCEMENT_PUBLISH
from shopman.shop.models import (
    Announcement,
    AnnouncementDeliveryState,
    AnnouncementStatus,
    MarketingOutbox,
)
from shopman.shop.services.marketing_approval import PUBLISH_NOW, approve_command

pytestmark = pytest.mark.django_db


def test_diagnostic_is_one_safe_read_only_json(django_assert_max_num_queries):
    stdout = StringIO()
    with (
        # +2 do bloco `lanes`: Shop.integrations (camada do registro) e destinos na fila por plataforma.
        django_assert_max_num_queries(17),
        patch(
            "shopman.shop.adapters.notification_manychat.send",
            side_effect=AssertionError("diagnostic must not call provider"),
        ),
    ):
        call_command("diagnose_marketing", "--json", stdout=stdout)

    report = json.loads(stdout.getvalue())
    assert report["schema"] == "shopman.marketing.diagnostic.v1"
    assert report["result"] == "OK"
    assert report["mode"] == "read_only"
    assert report["provider_calls"] == 0
    assert report["pii"] is False
    assert report["scope"] == {"receipt_ref": "all", "platform": "all"}
    assert report["shadow"]["status"] == "GO"
    assert report["shadow"]["reasons"] == []
    assert report["shadow"]["inventory"]["graph"] == {
        "approval_scope": "global",
        "approved_without_complete_graph": 0,
        "binding_mismatch": 0,
        "checked_outboxes": 0,
    }
    assert report["shadow"]["inventory"]["hash"] == {
        "checked_artifacts": 0,
        "mismatch": 0,
    }
    assert report["shadow"]["inventory"]["legacy"] == {
        "cleanup_status": "BLOCKED",
        "platform_results_rows": 0,
        "reasons": ["legacy_v1_api_present", "legacy_permission_present"],
        "untracked_rows": 0,
        "v1_api_present": True,
        "wide_permission_present": True,
    }
    assert report["next"] == ["observe:no_mutation_indicated"]


def test_diagnostic_rejects_an_invalid_receipt_before_querying():
    with pytest.raises(CommandError, match="UUID técnica válida"):
        call_command("diagnose_marketing", "--receipt", "not-a-uuid")


def test_shadow_go_reads_the_complete_graph_without_writes_or_pii():
    marker = "CONTATO-SECRETO +55 43 99999-8888"
    approved = _approve("shadow-go", marker)
    outbox = approved.outbox[0]
    before = {
        "announcement": Announcement.objects.get(pk=approved.announcement.pk).status,
        "outbox": MarketingOutbox.objects.get(pk=outbox.pk).state,
        "directives": Directive.objects.count(),
    }
    stdout = StringIO()

    with (
        connection.execute_wrapper(_reject_mutating_sql),
        patch(
            "shopman.shop.adapters.notification_manychat.send",
            side_effect=AssertionError("diagnostic must not call provider"),
        ),
    ):
        call_command(
            "diagnose_marketing",
            "--receipt",
            str(approved.receipt.ref),
            "--json",
            stdout=stdout,
        )

    output = stdout.getvalue()
    report = json.loads(output)
    assert marker not in output
    assert report["shadow"]["status"] == "GO"
    assert report["shadow"]["reasons"] == []
    assert report["shadow"]["inventory"]["graph"] == {
        "approval_scope": "receipt",
        "approved_without_complete_graph": 0,
        "binding_mismatch": 0,
        "checked_outboxes": 1,
    }
    assert report["shadow"]["inventory"]["aggregate"] == {
        "checked_announcements": 1,
        "count_mismatch": 0,
        "state_mismatch": 0,
        "target_fanout_mismatch": 0,
    }
    assert before == {
        "announcement": Announcement.objects.get(pk=approved.announcement.pk).status,
        "outbox": MarketingOutbox.objects.get(pk=outbox.pk).state,
        "directives": Directive.objects.count(),
    }


def test_shadow_filters_platform_with_a_constant_query_budget(django_assert_max_num_queries):
    _approve("shadow-instagram", "privado instagram", platforms=["instagram"])
    _approve("shadow-facebook", "privado facebook", platforms=["facebook"])
    stdout = StringIO()

    # +2 do bloco `lanes`: Shop.integrations (camada do registro) e destinos na fila por plataforma.
    with django_assert_max_num_queries(17):
        call_command(
            "diagnose_marketing",
            "--platform",
            "instagram",
            "--json",
            stdout=stdout,
        )

    report = json.loads(stdout.getvalue())
    assert report["scope"] == {"receipt_ref": "all", "platform": "instagram"}
    assert report["shadow"]["status"] == "GO"
    assert report["shadow"]["inventory"]["graph"]["checked_outboxes"] == 1
    assert report["shadow"]["inventory"]["hash"]["checked_artifacts"] == 1
    assert report["shadow"]["inventory"]["directive"]["checked_outboxes"] == 1
    assert report["shadow"]["inventory"]["aggregate"]["checked_announcements"] == 1


def test_shadow_intersects_receipt_and_platform_with_a_constant_query_budget(
    django_assert_max_num_queries,
):
    approved = _approve("shadow-receipt", "privado facebook", platforms=["facebook"])
    stdout = StringIO()

    # +2 do bloco `lanes`: Shop.integrations (camada do registro) e destinos na fila por plataforma.
    with django_assert_max_num_queries(18):
        call_command(
            "diagnose_marketing",
            "--receipt",
            str(approved.receipt.ref),
            "--platform",
            "facebook",
            "--json",
            stdout=stdout,
        )

    report = json.loads(stdout.getvalue())
    assert report["scope"] == {
        "receipt_ref": str(approved.receipt.ref),
        "platform": "facebook",
    }
    assert report["shadow"]["status"] == "GO"
    assert report["shadow"]["inventory"]["graph"] == {
        "approval_scope": "receipt",
        "approved_without_complete_graph": 0,
        "binding_mismatch": 0,
        "checked_outboxes": 1,
    }


def test_shadow_blocks_with_deterministic_graph_hash_directive_and_aggregate_reasons():
    broken = _approve("shadow-broken", "conteúdo não deve sair")
    missing = _approve("shadow-missing", "outro conteúdo privado")
    broken_outbox = broken.outbox[0]
    missing_outbox = missing.outbox[0]

    broken.artifact.__class__._base_manager.filter(pk=broken.artifact.pk).update(
        artifact_hash="0" * 64
    )
    MarketingOutbox.objects.filter(pk=broken_outbox.pk).update(
        platform="facebook",
        state=MarketingOutbox.State.DISPATCHED,
        dispatch_ref="directive:999999",
        dispatched_at=timezone.now(),
    )
    Announcement.objects.filter(pk=broken.announcement.pk).update(
        delivery_state=AnnouncementDeliveryState.SUCCEEDED,
        delivery_settled_at=timezone.now(),
        platform_results={
            "instagram": {
                "status": "failed",
                "error": "CONTATO-SECRETO +55 43 99999-8888",
            }
        },
    )
    MarketingOutbox.objects.filter(pk=missing_outbox.pk).delete()
    stdout = StringIO()

    call_command("diagnose_marketing", "--json", stdout=stdout)

    output = stdout.getvalue()
    report = json.loads(output)
    assert "CONTATO-SECRETO" not in output
    assert "+55 43 99999-8888" not in output
    assert report["result"] == "WARN"
    assert report["shadow"]["status"] == "BLOCKED"
    assert report["shadow"]["reasons"] == [
        "approved_without_complete_graph",
        "graph_binding_mismatch",
        "artifact_hash_mismatch",
        "dispatched_without_directive",
        "aggregate_state_mismatch",
    ]
    assert report["shadow"]["inventory"]["legacy"]["platform_results_rows"] == 1
    assert report["shadow"]["inventory"]["legacy"]["cleanup_status"] == "BLOCKED"
    assert report["next"] == ["hold_and_open:marketing-rollout-rollback.md"]


def test_shadow_detects_mismatched_unlinked_and_duplicate_directives():
    mismatched = _approve("shadow-directive-bad", "texto privado")
    unlinked = _approve("shadow-directive-unlinked", "outro texto privado")
    mismatched_outbox = mismatched.outbox[0]
    unlinked_outbox = unlinked.outbox[0]

    mismatched_directive = Directive.objects.create(
        topic=ANNOUNCEMENT_PUBLISH,
        payload={"announcement_id": -1},
        dedupe_key=f"marketing-outbox:{mismatched_outbox.ref}",
    )
    MarketingOutbox.objects.filter(pk=mismatched_outbox.pk).update(
        state=MarketingOutbox.State.DISPATCHED,
        dispatch_ref=f"directive:{mismatched_directive.pk}",
        dispatched_at=timezone.now(),
    )
    payload = _directive_payload(unlinked)
    Directive.objects.create(
        topic=ANNOUNCEMENT_PUBLISH,
        status=Directive.Status.DONE,
        payload=payload,
        dedupe_key=f"marketing-outbox:{unlinked_outbox.ref}",
    )
    Directive.objects.create(
        topic=ANNOUNCEMENT_PUBLISH,
        status=Directive.Status.DONE,
        payload=payload,
        dedupe_key=f"marketing-outbox:{unlinked_outbox.ref}",
    )
    stdout = StringIO()

    call_command("diagnose_marketing", "--json", stdout=stdout)

    report = json.loads(stdout.getvalue())
    assert report["shadow"]["status"] == "BLOCKED"
    assert report["shadow"]["reasons"] == [
        "directive_identity_mismatch",
        "unlinked_existing_directive",
        "duplicate_directive_key",
        "aggregate_state_mismatch",
    ]
    assert report["shadow"]["inventory"]["directive"] == {
        "checked_outboxes": 2,
        "dispatched_without_directive": 0,
        "duplicate_keys": 1,
        "identity_mismatch": 1,
        "matched": 0,
        "unlinked_existing": 1,
    }


def _approve(slug: str, body: str, *, platforms: list[str] | None = None):
    selected_platforms = platforms or ["instagram"]
    actor = get_user_model().objects.create_user(username=f"operator-{slug}")
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": body, "image_url": "/media/shadow.jpg"},
        platforms=selected_platforms,
    )
    return approve_command(
        announcement.pk,
        actor=actor,
        idempotency_key=f"diagnose-{slug}-approval",
        base_version=1,
        publish_mode=PUBLISH_NOW,
        content=announcement.content,
        platform_content={},
        platforms=selected_platforms,
    )


def _directive_payload(approved) -> dict:
    row = approved.outbox[0]
    return {
        "announcement_id": approved.announcement.pk,
        "artifact_hash": approved.artifact.artifact_hash,
        "artifact_ref": str(approved.artifact.ref),
        "content_version": approved.artifact.version,
        "outbox_ref": str(row.ref),
        "platform": row.platform,
        "snapshot_ref": str(approved.snapshot.ref),
    }


def _reject_mutating_sql(execute, sql, params, many, context):
    if re.match(r"^\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP)\b", sql, re.I):
        raise AssertionError(f"diagnostic attempted mutating SQL: {sql.split()[0]}")
    return execute(sql, params, many, context)


def test_diagnostic_tells_a_switched_off_platform_from_a_broken_configuration(settings):
    """Desligada pela flag não é defeito; flag ligada sem integração registrada é."""
    from shopman.shop.models import DeliveryTarget
    from shopman.shop.services.marketing_delivery_attempts import queue_target
    from shopman.shop.services.marketing_delivery_worker import fanout_in_chunks
    from shopman.shop.tests.test_marketing_delivery_ledger import _graph

    settings.SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED = False
    settings.SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED = False
    settings.SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED = True
    settings.SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED = True
    settings.SHOPMAN_MARKETING_DELIVERY_ADAPTERS = {
        "whatsapp": "shopman.shop.adapters.marketing_delivery_whatsapp",
    }
    outbox, _members = _graph(platform="instagram", suffix="diagnose-lanes", target_keys=())
    fanout_in_chunks(outbox.ref)
    for target in DeliveryTarget.objects.filter(outbox=outbox):
        queue_target(target.ref)

    stdout = StringIO()
    call_command("diagnose_marketing", "--json", stdout=stdout)
    report = json.loads(stdout.getvalue())

    assert report["provider_calls"] == 0
    assert report["lanes"]["whatsapp"]["state"] == "registered"
    assert report["lanes"]["instagram"] == {
        "state": "switched_off",
        "switch": "SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED",
        "queued_targets": 1,
    }
    assert report["lanes"]["google_business"]["state"] == "unconfigured"
    assert report["result"] == "WARN"
    assert (
        "observe:platform_switched_off_holds_queued platform=instagram "
        "switch=SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED queued=1"
    ) in report["next"]
    assert (
        "check_config:delivery_integration_unregistered platform=google_business "
        "switch=SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED"
    ) in report["next"]
    assert not [action for action in report["next"] if "platform=facebook" in action]
