"""API de notificações pessoais — isolamento por usuário e ação acionável.

O teste que importa mais aqui é o de isolamento: a caixa é da pessoa, e nem
staff nem superusuário leem (ou agem sobre) a notificação alheia.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    MarketingCommandReceipt,
    NotificationEventType,
    NotificationLifecycle,
    NotificationSeverity,
    UserNotification,
    UserNotificationEvent,
)
from shopman.shop.services import campaign
from shopman.shop.services.user_notifications import (
    ANNOUNCEMENT_REVIEW,
    create_condition_alert,
)

pytestmark = pytest.mark.django_db

User = get_user_model()

LIST_URL = "/api/v1/backstage/notifications/"


@pytest.fixture
def gestor():
    user = User.objects.create_user(username="gestor", password="x", is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(codename__in={
        "approve_marketing_announcements",
        "publish_marketing_announcements",
    }))
    return user


@pytest.fixture
def colega():
    return User.objects.create_user(username="colega", password="x", is_staff=True)


def _post() -> Announcement:
    template = AnnouncementTemplate.objects.create(name="T", body="{{product_name}}")
    rule = Campaign.objects.create(
        name="Fornada", trigger="production_finished",
        template=template, platforms=["instagram"],
    )
    return Announcement.objects.create(
        rule=rule, template=template, status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Saiu do forno"}, platforms=["instagram"],
    )


def _notification(user, *, announcement=None, actionable=True) -> UserNotification:
    source_ref = f"announcement:{announcement.pk}" if announcement else ""
    return UserNotification.objects.create(
        user=user,
        category="campaign",
        title="Anúncio pronto para revisão",
        message="Croissant saiu do forno",
        action_data={"announcement_id": announcement.pk} if announcement else {},
        is_actionable=actionable,
        severity=(
            NotificationSeverity.ACTION_REQUIRED
            if actionable and announcement
            else NotificationSeverity.INFORMATION
        ),
        source_condition=ANNOUNCEMENT_REVIEW if announcement else "",
        source_ref=source_ref,
        source_version=announcement.version if announcement else 1,
        group_key=(f"{ANNOUNCEMENT_REVIEW}:{source_ref}:v{announcement.version}" if announcement else ""),
        dedupe_key=(
            f"{ANNOUNCEMENT_REVIEW}:{source_ref}:v{announcement.version}:owner:{user.pk}"
            if announcement
            else ""
        ),
        owner_role="product" if announcement else "",
        escalation_role="ops" if announcement else "",
        expires_at=announcement.expires_at if announcement else None,
    )


# ── Listagem ─────────────────────────────────────────────────────────


class TestList:
    def test_anonymous_is_rejected(self, client):
        assert client.get(LIST_URL).status_code in (401, 403)

    def test_own_unread_notifications_are_listed(self, client, gestor):
        notification = _notification(gestor)
        notification.action_url = "https://evil.example/steal"
        notification.action_data = {"action": "approve", "href": "//evil.example"}
        notification.save(update_fields=["action_url", "action_data"])
        client.force_login(gestor)

        body = client.get(LIST_URL).json()
        assert len(body["notifications"]) == 1
        assert body["unread_count"] == 1
        assert body["actionable_count"] == 1
        assert [
            action["kind"] for action in body["notifications"][0]["actions"]
        ] == ["mark_notification_seen", "acknowledge_notification"]
        assert body["notifications"][0]["actions"][0]["href"].startswith("/")

    def test_another_users_box_is_invisible(self, client, gestor, colega):
        """A caixa é da pessoa: nem staff lê a alheia."""
        _notification(colega)
        client.force_login(gestor)

        body = client.get(LIST_URL).json()
        assert body["notifications"] == []
        assert body["unread_count"] == 0

    def test_read_ones_are_hidden_by_default(self, client, gestor):
        notification = _notification(gestor)
        notification.mark_read()
        client.force_login(gestor)

        assert client.get(LIST_URL).json()["notifications"] == []

    def test_all_flag_includes_the_read_ones(self, client, gestor):
        _notification(gestor).mark_read()
        client.force_login(gestor)

        assert len(client.get(f"{LIST_URL}?all=1").json()["notifications"]) == 1

    def test_limit_is_capped(self, client, gestor):
        for _ in range(5):
            _notification(gestor)
        client.force_login(gestor)

        assert len(client.get(f"{LIST_URL}?limit=2").json()["notifications"]) == 2


# ── Marcar como lida ─────────────────────────────────────────────────


class TestRead:
    def test_marking_read_drops_the_unread_count(self, client, gestor):
        notification = _notification(gestor, announcement=_post())
        client.force_login(gestor)

        body = client.post(f"{LIST_URL}{notification.pk}/read/").json()
        assert body["unread_count"] == 0
        assert body["unseen_count"] == 0
        assert body["unresolved_count"] == 1
        notification.refresh_from_db()
        assert notification.lifecycle == NotificationLifecycle.SEEN
        assert notification.resolved_at is None

    def test_rereading_keeps_the_first_timestamp(self, client, gestor):
        notification = _notification(gestor)
        client.force_login(gestor)

        client.post(f"{LIST_URL}{notification.pk}/read/")
        notification.refresh_from_db()
        first = notification.read_at

        client.post(f"{LIST_URL}{notification.pk}/read/")
        notification.refresh_from_db()
        assert notification.read_at == first

    def test_cannot_read_someone_elses(self, client, gestor, colega):
        notification = _notification(colega)
        client.force_login(gestor)

        assert client.post(f"{LIST_URL}{notification.pk}/read/").status_code == 404

    def test_acknowledging_keeps_condition_unresolved(self, client, gestor):
        notification = _notification(gestor, announcement=_post())
        client.force_login(gestor)

        body = client.post(f"{LIST_URL}{notification.pk}/acknowledge/").json()

        assert body["lifecycle"] == NotificationLifecycle.ACKNOWLEDGED
        assert body["unseen_count"] == 0
        assert body["unresolved_count"] == 1
        notification.refresh_from_db()
        assert notification.acknowledged_at is not None
        assert notification.resolved_at is None

    def test_cannot_acknowledge_someone_elses(self, client, gestor, colega):
        notification = _notification(colega, announcement=_post())
        client.force_login(gestor)

        assert client.post(f"{LIST_URL}{notification.pk}/acknowledge/").status_code == 404


# ── Ação ─────────────────────────────────────────────────────────────


class TestAction:
    def test_explicit_legacy_approve_is_moved_without_side_effect(self, client, gestor):
        announcement = _post()
        notification = _notification(gestor, announcement=announcement)
        client.force_login(gestor)

        response = client.post(
            f"{LIST_URL}{notification.pk}/action/", {"action": "approve"}
        )
        assert response.status_code == 410
        assert response.json()["code"] == "notification_action_moved"
        assert response.json()["action"] == {
            "kind": "open_announcement",
            "href": f"/announcements/{announcement.pk}#review",
        }
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW
        assert announcement.approved_by_id is None

    @pytest.mark.parametrize("payload", [{}, {"action": ""}, {"action": None}])
    def test_missing_action_is_invalid_and_never_defaults_to_approve(self, client, gestor, payload):
        announcement = _post()
        notification = _notification(gestor, announcement=announcement)
        client.force_login(gestor)

        response = client.post(
            f"{LIST_URL}{notification.pk}/action/",
            data=payload,
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "action"
        assert response.json()["code"] == "action_required"
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW
        assert announcement.approved_at is None

    def test_explicit_legacy_reject_is_also_moved_without_side_effect(self, client, gestor):
        announcement = _post()
        notification = _notification(gestor, announcement=announcement)
        client.force_login(gestor)

        response = client.post(
            f"{LIST_URL}{notification.pk}/action/",
            {"action": "reject"},
        )

        assert response.status_code == 410
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW
        assert announcement.rejected_by_id is None

    def test_unknown_action_is_rejected(self, client, gestor):
        notification = _notification(gestor, announcement=_post())
        client.force_login(gestor)

        response = client.post(
            f"{LIST_URL}{notification.pk}/action/", {"action": "incendiar"}
        )
        assert response.status_code == 400
        assert response.json()["field"] == "action"

    def test_a_non_actionable_notification_has_no_action(self, client, gestor):
        notification = _notification(gestor, actionable=False)
        client.force_login(gestor)

        assert client.post(f"{LIST_URL}{notification.pk}/action/").status_code == 400

    def test_cannot_act_on_someone_elses(self, client, gestor, colega):
        notification = _notification(colega, announcement=_post())
        client.force_login(gestor)

        assert client.post(f"{LIST_URL}{notification.pk}/action/").status_code == 404

    def test_malformed_stored_announcement_ref_is_not_reflected(self, client, gestor):
        notification = _notification(gestor)
        notification.is_actionable = True
        notification.action_data = {"announcement_id": "//evil.example"}
        notification.save(update_fields=["is_actionable", "action_data"])
        client.force_login(gestor)

        response = client.post(
            f"{LIST_URL}{notification.pk}/action/",
            {"action": "approve"},
        )

        assert response.status_code == 400
        assert "evil.example" not in str(response.json())


# ── Lifecycle v2 ─────────────────────────────────────────────────────


class TestLifecycleV2:
    V2_URL = f"{LIST_URL}v2/"

    def test_condition_alert_exposes_owner_source_deadline_and_exact_deep_link(self, client, gestor):
        announcement = _post()
        creation = create_condition_alert(
            user=gestor,
            category="campaign",
            title="Revisar anúncio",
            message="A fornada está pronta.",
            source_condition=ANNOUNCEMENT_REVIEW,
            source_ref=f"announcement:{announcement.pk}",
            source_version=announcement.version,
            action_data={"announcement_id": announcement.pk},
            owner_role="product",
            escalation_role="ops",
            expires_at=announcement.expires_at,
        )
        client.force_login(gestor)

        body = client.get(self.V2_URL).json()

        assert body["schema_version"] == 2
        assert body["shop_timezone"] == "America/Sao_Paulo"
        assert body["counts"] == {"unseen": 1, "unresolved": 1}
        item = body["notifications"][0]
        assert item["source"] == {
            "condition": ANNOUNCEMENT_REVIEW,
            "ref": f"announcement:{announcement.pk}",
            "version": announcement.version,
        }
        assert item["owner"] == {"user_id": gestor.pk, "role": "product"}
        assert item["escalation"]["role"] == "ops"
        assert [action["kind"] for action in item["actions"]] == [
            "open_announcement",
            "mark_notification_seen",
            "acknowledge_notification",
        ]
        assert item["actions"][0]["href"] == f"/announcements/{announcement.pk}#review"
        assert creation.notification.action_url == f"/announcements/{announcement.pk}#review"

    def test_same_condition_and_owner_is_deduped(self, gestor):
        announcement = _post()
        payload = {
            "user": gestor,
            "category": "campaign",
            "title": "Revisar anúncio",
            "message": "A fornada está pronta.",
            "source_condition": ANNOUNCEMENT_REVIEW,
            "source_ref": f"announcement:{announcement.pk}",
            "source_version": announcement.version,
            "owner_role": "product",
        }

        first = create_condition_alert(**payload)
        second = create_condition_alert(**payload)

        assert first.created is True
        assert second.created is False
        assert first.notification.pk == second.notification.pk
        assert UserNotification.objects.count() == 1
        assert first.notification.group_key == (
            f"{ANNOUNCEMENT_REVIEW}:announcement:{announcement.pk}:v{announcement.version}"
        )
        assert first.notification.dedupe_key.endswith(f":owner:{gestor.pk}")
        assert list(
            first.notification.lifecycle_events.values_list("event_type", flat=True)
        ) == [NotificationEventType.DEDUPED, NotificationEventType.CREATED]

    def test_object_decision_resolves_every_owner_sibling(self, gestor, colega):
        colleague_permission = Permission.objects.get(codename="approve_marketing_announcements")
        colega.user_permissions.add(colleague_permission)
        announcement = _post()
        for user in (gestor, colega):
            create_condition_alert(
                user=user,
                category="campaign",
                title="Revisar anúncio",
                message="A fornada está pronta.",
                source_condition=ANNOUNCEMENT_REVIEW,
                source_ref=f"announcement:{announcement.pk}",
                source_version=announcement.version,
                owner_role="product",
            )

        campaign.reject(announcement.pk, gestor)

        alerts = list(UserNotification.objects.order_by("user_id"))
        assert [alert.lifecycle for alert in alerts] == [
            NotificationLifecycle.RESOLVED,
            NotificationLifecycle.RESOLVED,
        ]
        assert all(alert.resolved_at is not None for alert in alerts)
        assert UserNotificationEvent.objects.filter(
            event_type=NotificationEventType.RESOLVED,
            outcome_code="announcement_rejected",
        ).count() == 2

    def test_modern_command_receipt_is_linked_to_resolution_event(self, client, gestor):
        announcement = _post()
        notification = _notification(gestor, announcement=announcement)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/reject/",
            data={"base_version": announcement.version, "reason": "Imagem incorreta"},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="notification-reject-link-0001",
        )

        assert response.status_code == 200
        receipt = MarketingCommandReceipt.objects.get(announcement=announcement)
        resolution = notification.lifecycle_events.get(
            event_type=NotificationEventType.RESOLVED,
        )
        assert resolution.command_id == receipt.pk
        assert resolution.outcome_code == "announcement_rejected"

    def test_source_version_refreshes_in_place_without_losing_seen_state(self, gestor):
        announcement = _post()
        notification = _notification(gestor, announcement=announcement)
        notification.mark_read()
        previous_dedupe = notification.dedupe_key

        updated = campaign.update_content(
            announcement.pk,
            body="Texto revisado",
            base_version=announcement.version,
        )

        notification.refresh_from_db()
        assert notification.lifecycle == NotificationLifecycle.SEEN
        assert notification.source_version == updated.version
        assert notification.dedupe_key != previous_dedupe
        assert notification.message == "Texto revisado"
        refreshed = notification.lifecycle_events.get(
            event_type=NotificationEventType.REFRESHED,
        )
        assert refreshed.facts == {
            "previous_source_version": announcement.version,
            "resulting_source_version": updated.version,
        }

    def test_resolution_pushes_invalidation_to_every_owner(
        self,
        gestor,
        colega,
        monkeypatch,
        django_capture_on_commit_callbacks,
    ):
        announcement = _post()
        for user in (gestor, colega):
            create_condition_alert(
                user=user,
                category="campaign",
                title="Revisar anúncio",
                message="A fornada está pronta.",
                source_condition=ANNOUNCEMENT_REVIEW,
                source_ref=f"announcement:{announcement.pk}",
                source_version=announcement.version,
                owner_role="product",
            )
        emitted = []
        monkeypatch.setattr(
            "django_eventstream.send_event",
            lambda channel, event, payload: emitted.append((channel, event, payload)),
        )

        with django_capture_on_commit_callbacks(execute=True):
            campaign.reject(announcement.pk, gestor)

        assert {channel for channel, _, _ in emitted} == {
            f"user-{gestor.pk}",
            f"user-{colega.pk}",
        }
        assert {event for _, event, _ in emitted} == {"user-notification"}
        assert all(set(payload) == {"id", "category"} for _, _, payload in emitted)

    def test_fetch_reconciles_a_source_changed_without_a_signal(self, client, gestor):
        announcement = _post()
        notification = _notification(gestor, announcement=announcement)
        UserNotification.objects.filter(pk=notification.pk).update(
            lifecycle=NotificationLifecycle.SEEN,
            is_read=True,
        )
        # QuerySet.update deliberately models an external writer that skipped signals.
        Announcement.objects.filter(pk=announcement.pk).update(status=AnnouncementStatus.REJECTED)
        client.force_login(gestor)

        body = client.get(self.V2_URL).json()

        assert body["notifications"] == []
        assert body["counts"] == {"unseen": 0, "unresolved": 0}
        notification.refresh_from_db()
        assert notification.lifecycle == NotificationLifecycle.RESOLVED

    def test_information_only_is_history_not_bell(self, client, gestor):
        UserNotification.objects.create(
            user=gestor,
            title="Relatório pronto",
            severity=NotificationSeverity.INFORMATION,
            lifecycle=NotificationLifecycle.UNSEEN,
        )
        client.force_login(gestor)

        assert client.get(self.V2_URL).json()["notifications"] == []
        history = client.get(f"{self.V2_URL}?history=1").json()
        assert [item["title"] for item in history["notifications"]] == ["Relatório pronto"]

    def test_retention_expired_item_is_not_projected_even_in_history(self, client, gestor):
        UserNotification.objects.create(
            user=gestor,
            title="Fora da retenção",
            severity=NotificationSeverity.INFORMATION,
            retention_until=timezone.now() - timedelta(seconds=1),
        )
        client.force_login(gestor)

        body = client.get(f"{self.V2_URL}?history=1").json()

        assert body["notifications"] == []

    def test_visible_page_is_marked_seen_in_one_owner_scoped_batch(self, client, gestor, colega):
        first = _notification(gestor, announcement=_post())
        second = _notification(gestor, announcement=_post())
        foreign = _notification(colega, announcement=_post())
        client.force_login(gestor)

        response = client.post(
            f"{self.V2_URL}seen/",
            data={"notification_ids": [first.pk, second.pk, foreign.pk]},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json() == {
            "ok": True,
            "changed": 2,
            "unseen_count": 0,
            "unresolved_count": 2,
        }
        first.refresh_from_db()
        second.refresh_from_db()
        foreign.refresh_from_db()
        assert first.lifecycle == NotificationLifecycle.SEEN
        assert second.lifecycle == NotificationLifecycle.SEEN
        assert foreign.lifecycle == NotificationLifecycle.UNSEEN
        assert UserNotificationEvent.objects.filter(
            event_type=NotificationEventType.SEEN,
            outcome_code="visible_in_alert_panel",
        ).count() == 2

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"notification_ids": "1"},
            {"notification_ids": [True]},
            {"notification_ids": [0]},
            {"notification_ids": list(range(1, 102))},
        ],
    )
    def test_seen_batch_rejects_malformed_or_oversized_input(self, client, gestor, payload):
        client.force_login(gestor)

        response = client.post(
            f"{self.V2_URL}seen/",
            data=payload,
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "notification_ids"

    def test_cursor_is_stable_and_tamper_evident(self, client, gestor):
        for index in range(3):
            UserNotification.objects.create(
                user=gestor,
                title=f"Histórico {index}",
                severity=NotificationSeverity.INFORMATION,
            )
        client.force_login(gestor)

        first = client.get(f"{self.V2_URL}?history=1&limit=2").json()
        assert first["page"]["has_more"] is True
        second = client.get(
            self.V2_URL,
            {"history": 1, "limit": 2, "cursor": first["page"]["next_cursor"]},
        ).json()
        assert len(second["notifications"]) == 1
        assert client.get(
            self.V2_URL,
            {"history": 1, "cursor": first["page"]["next_cursor"] + "x"},
        ).status_code == 422

    def test_bell_page_stays_within_board_query_budget(
        self,
        client,
        gestor,
        django_assert_max_num_queries,
    ):
        announcement = _post()
        for index in range(30):
            UserNotification.objects.create(
                user=gestor,
                category="campaign",
                title=f"Revisão {index}",
                action_data={"announcement_id": announcement.pk},
                is_actionable=True,
                severity=NotificationSeverity.ACTION_REQUIRED,
                source_condition=ANNOUNCEMENT_REVIEW,
                source_ref=f"announcement:{announcement.pk}",
                source_version=announcement.version,
                owner_role="product",
            )
        client.force_login(gestor)

        with django_assert_max_num_queries(25):
            response = client.get(f"{self.V2_URL}?limit=20")

        assert response.status_code == 200
        assert len(response.json()["notifications"]) == 20

    def test_notification_events_refuse_rewrite_and_direct_delete(self, gestor):
        announcement = _post()
        created = create_condition_alert(
            user=gestor,
            category="campaign",
            title="Revisar anúncio",
            message="A fornada está pronta.",
            source_condition=ANNOUNCEMENT_REVIEW,
            source_ref=f"announcement:{announcement.pk}",
            source_version=announcement.version,
            owner_role="product",
        )
        event = created.notification.lifecycle_events.get()

        event.outcome_code = "rewritten"
        with pytest.raises(ValidationError):
            event.save()
        with pytest.raises(ValidationError):
            UserNotificationEvent.objects.filter(pk=event.pk).update(outcome_code="rewritten")
        with pytest.raises(ValidationError):
            event.delete()


# ── Stream pessoal ───────────────────────────────────────────────────


class TestUserStream:
    def test_anonymous_gets_404_not_a_reconnect_loop(self, client):
        assert client.get("/events/me/").status_code == 404

    def test_channel_manager_only_lets_the_owner_read(self, gestor, colega):
        from shopman.shop.eventstream import ShopmanChannelManager

        manager = ShopmanChannelManager()
        assert manager.can_read_channel(gestor, f"user-{gestor.pk}")
        assert not manager.can_read_channel(colega, f"user-{gestor.pk}")

    def test_superuser_does_not_get_a_master_key(self, gestor):
        from shopman.shop.eventstream import ShopmanChannelManager

        root = User.objects.create_superuser(username="root", password="x")
        assert not ShopmanChannelManager().can_read_channel(root, f"user-{gestor.pk}")
