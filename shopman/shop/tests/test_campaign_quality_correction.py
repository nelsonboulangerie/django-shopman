"""A correção de QC fecha comunicação que ainda não saiu — e só essa."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.directives import ANNOUNCEMENT_PUBLISH
from shopman.shop.handlers import campaign as campaign_handlers
from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    NotificationCategory,
    UserNotification,
)
from shopman.shop.services import campaign

pytestmark = pytest.mark.django_db

WO_REF = "WO-QC-COMMS-1"


@pytest.fixture
def rule():
    template = AnnouncementTemplate.objects.create(
        name="Fornada normal",
        body="A fornada saiu.",
    )
    return Campaign.objects.create(
        name="Só qualidade normal ou melhor",
        trigger="production_finished",
        trigger_filter={"quality_min": "standard"},
        template=template,
        platforms=["instagram"],
    )


def _announcement(rule, *, status=AnnouncementStatus.PENDING_REVIEW, platforms=None):
    return Announcement.objects.create(
        rule=rule,
        template=rule.template,
        status=status,
        content={"body": "A fornada saiu."},
        platforms=platforms if platforms is not None else list(rule.platforms),
        trigger_context={
            "trigger": "production_finished",
            "work_order_ref": WO_REF,
            "quality": "standard",
            "output_partition": [{"grade_ref": "standard", "quantity": "10"}],
            "planned_qty": "10",
        },
    )


def _correct(*, grade="fair"):
    return campaign.reconcile_quality_correction(
        SimpleNamespace(ref=WO_REF),
        [
            {
                "quantity": "10",
                "quality_grade_ref": grade,
                "quality_defect_ref": "overbaked" if grade == "fair" else "",
                "loss": False,
            }
        ],
    )


def test_pending_announcement_and_its_review_notification_are_closed(rule):
    announcement = _announcement(rule)
    user = get_user_model().objects.create_user("reviewer")
    notification = UserNotification.objects.create(
        user=user,
        category=NotificationCategory.CAMPAIGN,
        title="Revisar",
        action_url=f"/campaign/announcements/{announcement.pk}/",
        action_data={"announcement_id": announcement.pk},
        is_actionable=True,
    )
    unrelated = UserNotification.objects.create(
        user=user,
        category=NotificationCategory.CAMPAIGN,
        title="Outra",
        action_url="/campaign/announcements/99999/",
        is_actionable=True,
    )

    impact = _correct()

    announcement.refresh_from_db()
    notification.refresh_from_db()
    unrelated.refresh_from_db()
    assert announcement.status == AnnouncementStatus.SUPERSEDED
    assert impact["superseded_announcement_ids"] == [announcement.pk]
    assert impact["closed_review_notification_ids"] == [notification.pk]
    assert notification.is_read is True
    assert notification.read_at is not None
    assert notification.is_actionable is False
    assert unrelated.is_read is False
    assert unrelated.is_actionable is True


def test_correction_that_still_matches_quality_leaves_announcement_alone(rule):
    announcement = _announcement(rule)

    impact = _correct(grade="excellent")

    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW
    assert impact["superseded_announcement_ids"] == []
    assert impact["irreversible_announcements"] == []


def test_publishing_with_only_queued_directives_is_superseded_and_handler_is_noop(rule):
    announcement = _announcement(rule, status=AnnouncementStatus.PUBLISHING)
    directive = Directive.objects.create(
        topic=ANNOUNCEMENT_PUBLISH,
        status=Directive.Status.QUEUED,
        payload={"announcement_id": announcement.pk, "platform": "instagram"},
    )

    impact = _correct()

    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.SUPERSEDED
    assert impact["superseded_announcement_ids"] == [announcement.pk]

    adapter = MagicMock()
    with patch.object(campaign_handlers, "_posting_adapter", return_value=adapter):
        campaign_handlers.AnnouncementHandler().handle(message=directive, ctx={})
    adapter.publish.assert_not_called()
    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.SUPERSEDED
    assert announcement.platform_results == {}


@pytest.mark.parametrize("directive_status", [Directive.Status.RUNNING, Directive.Status.DONE])
def test_running_or_done_directive_is_reported_as_irreversible(rule, directive_status):
    announcement = _announcement(rule, status=AnnouncementStatus.PUBLISHING)
    directive = Directive.objects.create(
        topic=ANNOUNCEMENT_PUBLISH,
        status=directive_status,
        payload={"announcement_id": announcement.pk, "platform": "instagram"},
    )

    impact = _correct()

    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PUBLISHING
    assert impact["superseded_announcement_ids"] == []
    assert impact["irreversible_announcements"] == [
        {
            "announcement_id": announcement.pk,
            "status": AnnouncementStatus.PUBLISHING,
            "published_at": "",
            "directives": [
                {
                    "id": directive.pk,
                    "topic": ANNOUNCEMENT_PUBLISH,
                    "status": directive_status,
                }
            ],
        }
    ]


def test_published_announcement_is_preserved_and_reported(rule):
    announcement = _announcement(rule, status=AnnouncementStatus.PUBLISHED)
    announcement.published_at = timezone.now()
    announcement.save(update_fields=["published_at"])

    impact = _correct()

    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PUBLISHED
    assert impact["irreversible_announcements"][0]["announcement_id"] == announcement.pk
    assert impact["irreversible_announcements"][0]["published_at"]


def test_superseded_announcement_cannot_be_dispatched_or_approved(rule):
    announcement = _announcement(rule)
    stale = Announcement.objects.get(pk=announcement.pk)
    _correct()

    assert campaign.dispatch(stale) == 0
    assert Directive.objects.filter(payload__announcement_id=announcement.pk).count() == 0
    with pytest.raises(campaign.CampaignError, match="substituído"):
        campaign.approve(announcement.pk, get_user_model().objects.create_user("gestor"))


def test_superseded_whatsapp_handler_never_resolves_or_sends_audience(rule):
    announcement = _announcement(
        rule,
        status=AnnouncementStatus.PENDING_REVIEW,
        platforms=["whatsapp"],
    )
    _correct()
    message = SimpleNamespace(
        pk=7,
        payload={"announcement_id": announcement.pk, "wave": "all"},
    )

    with (
        patch("shopman.shop.services.audience.select_wave") as select_wave,
        patch("shopman.shop.notifications.notify") as notify,
    ):
        campaign_handlers.AnnouncementNotifyHandler().handle(message=message, ctx={})

    select_wave.assert_not_called()
    notify.assert_not_called()
