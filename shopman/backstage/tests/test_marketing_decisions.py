"""UX-M1 — a casa do Marketing é a fila de decisões, ordenada por prazo."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone

from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.marketing_decisions import build_decision_queue
from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    DeliveryReconciliation,
    DeliveryTarget,
)
from shopman.shop.services.marketing_contracts import ProviderOutcome, ProviderOutcomeKind
from shopman.shop.services.marketing_delivery_recovery import (
    claim_reconciliations,
    execute_reconciliation,
    request_automatic_reconciliations,
)
from shopman.shop.tests.test_marketing_delivery_recovery import _targets

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/marketing/decisions/"


@pytest.fixture
def rule():
    template = AnnouncementTemplate.objects.create(name="Fornada", body="{{product_name}} saiu")
    return Campaign.objects.create(
        name="Fornada de pães",
        trigger="production_finished",
        template=template,
        platforms=["instagram", "facebook", "whatsapp"],
        audience_rules={"favorites": True},
    )


def _pending(rule, *, minutes: int | None, **kwargs) -> Announcement:
    now = timezone.now()
    defaults = {
        "content": {"body": "Croissant saiu do forno, 24 unidades"},
        "platforms": ["instagram", "facebook", "whatsapp"],
        "audience": {"eligible_count": 86, "total": 86},
        "trigger_context": {"sku": "CRO-001"},
        "expires_at": now + timedelta(minutes=minutes) if minutes is not None else None,
    }
    return Announcement.objects.create(
        rule=rule,
        template=rule.template,
        status=AnnouncementStatus.PENDING_REVIEW,
        **{**defaults, **kwargs},
    )


def test_queue_orders_by_deadline_and_separates_posts_from_people(rule):
    later = _pending(rule, minutes=90)
    sooner = _pending(rule, minutes=12)
    no_deadline = _pending(rule, minutes=None, platforms=["instagram"])
    _pending(rule, minutes=-5)  # venceu: não é mais decisão de ninguém

    queue = build_decision_queue()

    assert [item.announcement_id for item in queue.items] == [
        sooner.pk,
        later.pk,
        no_deadline.pk,
    ]
    first = queue.items[0]
    assert first.kind == "review"
    assert first.href == f"/announcements/{sooner.pk}#review"
    assert first.campaign_name == "Fornada de pães"
    # Duas postagens (Instagram + Facebook) e 86 pessoas (WhatsApp): nunca 88 "envios".
    assert (first.reach.posts, first.reach.people) == (2, 86)
    # Sem WhatsApp, o público não vira "pessoas": postagem não tem destinatário.
    assert (queue.items[2].reach.posts, queue.items[2].reach.people) == (1, 0)


def test_queue_brings_retryable_failure_with_written_reason_and_deadline(rule):
    announcement, targets = _targets(
        suffix="queue-retry",
        states=(DeliveryTarget.State.FAILED_RETRYABLE, DeliveryTarget.State.CONFIRMED),
    )
    deadline = timezone.now() + timedelta(minutes=40)
    Announcement.objects.filter(pk=announcement.pk).update(expires_at=deadline)
    DeliveryTarget.objects.filter(pk=targets[0].pk).update(last_error_code="subscriber_busy")

    queue = build_decision_queue()

    [item] = [item for item in queue.items if item.kind == "retry_failed"]
    assert item.announcement_id == announcement.pk
    assert item.href == f"/announcements/{announcement.pk}#result"
    assert item.deadline_at == timezone.localtime(deadline, item.deadline_at.tzinfo)
    [failure] = item.failures
    assert (failure.platform_ref, failure.delivery_kind, failure.count) == (
        "whatsapp",
        "direct_message",
        1,
    )
    assert failure.reason_code == "subscriber_busy"
    assert (item.reach.posts, item.reach.people) == (0, 1)


def test_uncertain_result_is_automatic_check_not_a_decision_until_lookup_fails():
    announcement, _rows = _targets(
        suffix="queue-unknown",
        states=(DeliveryTarget.State.UNKNOWN,),
    )

    waiting = build_decision_queue()
    assert [item.kind for item in waiting.items] == []
    [check] = waiting.automatic_checks
    assert (check.announcement_id, check.platform_ref, check.state) == (
        announcement.pk,
        "whatsapp",
        "checking",
    )

    request_automatic_reconciliations(platforms=("whatsapp",))
    claimed = claim_reconciliations(worker_id="queue-test").reconciliations[0]

    class StillUnknown:
        def lookup(self, **_kwargs):
            return ProviderOutcome(
                kind=ProviderOutcomeKind.UNKNOWN,
                code="provider_still_unknown",
                retryable=False,
            )

    execute_reconciliation(claimed.ref, provider=StillUnknown(), worker_id="queue-test")

    after = build_decision_queue()
    # O sistema já consultou sozinho e a plataforma não soube dizer: agora pedir
    # de novo é gesto do operador, e ele aparece na fila.
    assert [item.kind for item in after.items] == ["reconcile_unknown"]
    [check] = after.automatic_checks
    assert check.state == "still_unknown"
    assert check.checked_at is not None


def test_automatic_check_reports_what_the_lookup_found():
    _targets(suffix="queue-confirmed", states=(DeliveryTarget.State.UNKNOWN,))
    request_automatic_reconciliations(platforms=("whatsapp",))
    claimed = claim_reconciliations(worker_id="queue-test").reconciliations[0]

    class Confirmed:
        def lookup(self, **_kwargs):
            return ProviderOutcome(
                kind=ProviderOutcomeKind.CONFIRMED,
                code="provider_confirmed",
                retryable=False,
                provider_receipt_ref="receipt-1",
            )

    execute_reconciliation(claimed.ref, provider=Confirmed(), worker_id="queue-test")

    queue = build_decision_queue()

    assert queue.items == ()
    [check] = queue.automatic_checks
    assert check.state == "confirmed"
    assert DeliveryReconciliation.objects.get().state == DeliveryReconciliation.State.COMPLETED


def test_scheduled_line_counts_today_and_active_campaigns(rule):
    now = timezone.now()
    Announcement.objects.create(
        rule=rule,
        template=rule.template,
        status=AnnouncementStatus.APPROVED,
        platforms=["instagram"],
        publish_at=now + timedelta(minutes=1),
    )
    Announcement.objects.create(
        rule=rule,
        template=rule.template,
        status=AnnouncementStatus.APPROVED,
        platforms=["instagram"],
        publish_at=now + timedelta(days=3),
    )
    Campaign.objects.create(
        name="Desligada",
        trigger="manual",
        template=rule.template,
        platforms=["instagram"],
        is_active=False,
    )

    queue = build_decision_queue()

    assert len(queue.scheduled) == 2
    assert queue.scheduled[0].scheduled_for < queue.scheduled[1].scheduled_for
    assert queue.scheduled_today_count in {1, 2}  # 2 só se "agora + 1 min" virar o dia
    assert queue.active_campaign_count == 1
    assert queue.items == ()


def test_endpoint_needs_marketing_capability_and_carries_no_copy(client, rule):
    _pending(rule, minutes=12)
    outsider = get_user_model().objects.create_user(username="sem-mkt", password="x", is_staff=True)
    client.force_login(outsider)
    assert client.get(URL).status_code == 403

    gestor = get_user_model().objects.create_user(username="mkt", password="x", is_staff=True)
    gestor.user_permissions.add(Permission.objects.get(codename="view_marketing"))
    client.force_login(gestor)
    response = client.get(URL)

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    payload = response.json()["queue"]
    assert payload["items"][0]["kind"] == "review"
    serialized = json.dumps(payload, ensure_ascii=False)
    # Texto do anúncio não viaja na fila: ela aponta, a tela do anúncio mostra.
    assert "Croissant saiu do forno" not in serialized
    assert not any(key.endswith("_label") for key in payload["items"][0])


def test_projection_data_is_json_safe(rule):
    _pending(rule, minutes=12)
    json.dumps(projection_data(build_decision_queue()))
