"""MKT-024 — conditional reads, errors, cursors and safe HTTP metadata."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.test import APIRequestFactory

from shopman.backstage.api.marketing import _CampaignV2Base
from shopman.backstage.api.marketing_v2_http import MarketingV2Problem
from shopman.shop.models import Announcement, AnnouncementStatus

pytestmark = pytest.mark.django_db

BOARD_PATH = "/api/v1/backstage/marketing/v2/"
HISTORY_PATH = "/api/v1/backstage/marketing/v2/history/"


def _reader(*, username: str = "marketing-v2-reader"):
    operator = get_user_model().objects.create_user(username=username, is_staff=True)
    operator.user_permissions.add(Permission.objects.get(codename="view_marketing"))
    return operator


def test_v2_conditional_get_has_private_versioned_correlation_metadata(client):
    operator = _reader()
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "never projected"},
    )
    client.force_login(operator)

    first = client.get(
        f"{BOARD_PATH}announcements/{announcement.pk}/",
        HTTP_X_REQUEST_ID="req_browser_42",
    )
    etag = first.headers["ETag"]

    assert first.status_code == 200
    assert etag.startswith('W/"marketing-v2-')
    assert first.headers["X-Request-ID"] == "req_browser_42"
    assert first.headers["X-API-Version"] == "1"
    assert first.headers["X-Contract-Version"] == "marketing.v2"
    assert first.headers["X-Resource-Version"] == str(first.json()["resource_version"])
    assert first.headers["Cache-Control"] == "private, no-cache, must-revalidate"
    assert "Cookie" in first.headers["Vary"]

    unchanged = client.get(
        f"{BOARD_PATH}announcements/{announcement.pk}/",
        HTTP_IF_NONE_MATCH=etag,
        HTTP_X_REQUEST_ID="req_browser_43",
    )

    assert unchanged.status_code == 304
    assert unchanged.content == b""
    assert unchanged.headers["ETag"] == etag
    assert unchanged.headers["X-Request-ID"] == "req_browser_43"
    assert unchanged.headers["X-Resource-Version"] == str(announcement.version)

    Announcement.objects.filter(pk=announcement.pk).update(version=announcement.version + 1)
    changed = client.get(
        f"{BOARD_PATH}announcements/{announcement.pk}/",
        HTTP_IF_NONE_MATCH=etag,
    )

    assert changed.status_code == 200
    assert changed.headers["ETag"] != etag
    assert changed.headers["X-Request-ID"].startswith("req_")


def test_history_cursor_is_stable_across_identical_timestamps_and_new_inserts(client):
    operator = _reader(username="history-reader")
    anchor = timezone.now() - timedelta(minutes=1)
    originals = [
        Announcement.objects.create(
            status=AnnouncementStatus.PUBLISHED,
            content={"body": f"history {index}"},
        )
        for index in range(5)
    ]
    Announcement.objects.filter(pk__in=[item.pk for item in originals]).update(
        created_at=anchor
    )
    client.force_login(operator)

    first = client.get(HISTORY_PATH, {"limit": 2})
    first_body = first.json()
    cursor = first_body["data"]["page"]["next_cursor"]
    as_of = first_body["data"]["page"]["as_of"]
    first_refs = [item["ref"] for item in first_body["data"]["items"]]

    inserted = Announcement.objects.create(
        status=AnnouncementStatus.PUBLISHED,
        content={"body": "inserted after the snapshot"},
    )
    second = client.get(HISTORY_PATH, {"limit": 2, "cursor": cursor})
    second_body = second.json()
    third = client.get(
        HISTORY_PATH,
        {
            "limit": 2,
            "cursor": second_body["data"]["page"]["next_cursor"],
        },
    )

    pages = [*first_refs]
    pages.extend(item["ref"] for item in second_body["data"]["items"])
    pages.extend(item["ref"] for item in third.json()["data"]["items"])
    expected = [f"announcement:{item.pk}" for item in reversed(originals)]
    assert pages == expected
    assert len(pages) == len(set(pages))
    assert f"announcement:{inserted.pk}" not in pages
    assert second_body["data"]["page"]["as_of"] == as_of
    assert third.json()["data"]["page"] == {
        "as_of": as_of,
        "limit": 2,
        "has_more": False,
        "next_cursor": "",
    }


@pytest.mark.parametrize(
    ("query", "field"),
    [({"cursor": "tampered"}, "cursor"), ({"limit": "101"}, "limit")],
)
def test_history_rejects_invalid_cursor_or_silent_limit_caps(client, query, field):
    client.force_login(_reader(username=f"invalid-{field}"))

    response = client.get(HISTORY_PATH, query)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == f"invalid_{field}"
    assert field in response.json()["error"]["field_errors"]
    assert response.headers["X-Request-ID"].startswith("req_")


def test_v2_keeps_unauthenticated_forbidden_and_not_found_distinct(client):
    anonymous = client.get(BOARD_PATH)
    operator = get_user_model().objects.create_user(
        username="marketing-forbidden",
        is_staff=True,
    )
    client.force_login(operator)
    forbidden = client.get(BOARD_PATH)
    operator.user_permissions.add(Permission.objects.get(codename="view_marketing"))
    missing = client.get(f"{BOARD_PATH}announcements/999999/")

    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "authentication_required"
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "capability_required"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "resource_not_found"


@pytest.mark.parametrize(
    ("raised", "status_code", "code", "retry_after"),
    [
        (
            MarketingV2Problem(
                status_code=409,
                code="version_conflict",
                detail="presentation.version_conflict",
                current_version=18,
            ),
            409,
            "version_conflict",
            None,
        ),
        (
            MarketingV2Problem(
                status_code=503,
                code="dependency_unavailable",
                detail="presentation.dependency_unavailable",
                retryable=True,
            ),
            503,
            "dependency_unavailable",
            None,
        ),
        (exceptions.Throttled(wait=7), 429, "rate_limited", "7"),
    ],
)
def test_v2_problem_boundary_preserves_conflict_throttle_and_unavailable(
    raised,
    status_code,
    code,
    retry_after,
):
    class ProblemView(_CampaignV2Base):
        permission_classes = []

        def get(self, request):
            raise raised

    response = ProblemView.as_view()(APIRequestFactory().get("/problem"))
    response.render()

    assert response.status_code == status_code
    assert response.data["error"]["code"] == code
    assert response.data["error"]["detail"].startswith("presentation.")
    assert response.data["error"]["current_version"] == (
        18 if status_code == 409 else None
    )
    if retry_after is not None:
        assert response.headers["Retry-After"] == retry_after
