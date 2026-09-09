"""Contrato da superfície Campanha (surfaces/marketing-nuxt).

O que este arquivo protege, em ordem de importância:

1. **Os gates.** Capabilities separam leitura, edição, decisão, publicação,
   teste e configuração. Staff comum não publica.
2. **Anúncio que já saiu não se reescreve.** Editar o corpo depois de publicado
   seria mentira retroativa sobre o que o cliente leu.
3. **As chaves que o Nuxt lê.** Se a projection mudar de forma, o app quebra em
   silêncio; aqui quebra em vermelho.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    AudienceSnapshot,
    Campaign,
    MarketingAuditEvent,
    MarketingCommandReceipt,
    MarketingContentArtifact,
    MarketingOutbox,
)

pytestmark = pytest.mark.django_db

User = get_user_model()

BOARD_URL = "/api/v1/backstage/marketing/"
RULES_URL = "/api/v1/backstage/marketing/rules/"
TEMPLATES_URL = "/api/v1/backstage/marketing/templates/"
OPTIONS_URL = "/api/v1/backstage/marketing/options/"
HISTORY_URL = "/api/v1/backstage/marketing/history/"


@pytest.fixture
def gestor():
    user = User.objects.create_user(username="marketing", password="x", is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(codename__in={
        "view_marketing",
        "edit_marketing_campaigns",
        "edit_marketing_templates",
        "preview_marketing_audience",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
        "fire_marketing_campaigns",
        "send_marketing_test",
        "configure_marketing_platforms",
    }))
    return user


@pytest.fixture
def template():
    return AnnouncementTemplate.objects.create(name="Fornada", body="{{product_name}} saiu do forno!")


@pytest.fixture
def rule(template):
    return Campaign.objects.create(
        name="Fornada de pães",
        trigger="production_finished",
        template=template,
        platforms=["instagram", "google_business"],
        audience_rules={"favorites": True},
    )


def _post(rule, template, *, status=AnnouncementStatus.PENDING_REVIEW, **kwargs) -> Announcement:
    defaults = {
        "content": {"body": "Croissant saiu do forno", "hashtags": ["padaria"], "link": "/p/cro"},
        "platforms": ["instagram", "google_business"],
        "audience": {"favorites": 12, "alerts": 3, "total": 15},
        "trigger_context": {"sku": "CRO-001"},
    }
    return Announcement.objects.create(
        rule=rule, template=template, status=status, **{**defaults, **kwargs}
    )


def _confirmed_post(client, url: str, payload: dict, *, key: str):
    """Exercise the operator contract without inventing confirmation facts client-side."""

    response = client.post(
        url,
        data=payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    if response.status_code != 428:
        return response
    confirmation = response.json()["confirmation"]
    if confirmation["step_up"] != "none":
        method = confirmation["step_up"]
        credential = "x" if method == "password" else "000000"
        stepped = client.post(
            "/api/v1/backstage/marketing/security/step-up/",
            data={"method": method, "credential": credential},
            content_type="application/json",
        )
        assert stepped.status_code == 200
    return client.post(
        url,
        data={
            **payload,
            "confirmation_token": confirmation["token"],
            "typed_confirmation": confirmation["typed_phrase"],
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


# ── Gate ─────────────────────────────────────────────────────────────


class TestGate:
    def test_anonymous_is_rejected(self, client):
        assert client.get(BOARD_URL).status_code in (401, 403)

    def test_staff_without_permission_is_rejected(self, client):
        User.objects.create_user(username="caixa", password="x", is_staff=True)
        client.login(username="caixa", password="x")
        assert client.get(BOARD_URL).status_code == 403

    def test_manager_with_permission_gets_the_board(self, client, gestor):
        client.force_login(gestor)
        assert client.get(BOARD_URL).status_code == 200

    def test_staff_without_permission_cannot_approve(self, client, rule, template):
        announcement = _post(rule, template)
        User.objects.create_user(username="caixa", password="x", is_staff=True)
        client.login(username="caixa", password="x")
        response = _confirmed_post(
            client,
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            {"base_version": 1, "publish_mode": "now"},
            key="legacy-contract-replaced-0001",
        )
        assert response.status_code == 403
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW


# ── Painel ───────────────────────────────────────────────────────────


class TestBoard:
    def test_pending_post_carries_the_keys_the_surface_reads(self, client, gestor, rule, template):
        _post(rule, template)
        client.force_login(gestor)

        board = client.get(BOARD_URL).json()["board"]

        assert board["stats"]["pending_count"] == 1
        card = board["pending"][0]
        assert card["body"] == "Croissant saiu do forno"
        assert card["audience_total"] == 15
        assert card["rule_name"] == "Fornada de pães"
        assert card["sku"] == "CRO-001"
        assert [r["platform"] for r in card["platform_results"]] == [
            "instagram",
            "google_business",
        ]

    def test_expired_pending_post_leaves_the_board(self, client, gestor, rule, template):
        """Anúncio vencido não pede decisão: propaganda velha destrói confiança."""
        _post(rule, template, expires_at=timezone.now() - timezone.timedelta(minutes=1))
        client.force_login(gestor)

        board = client.get(BOARD_URL).json()["board"]
        assert board["pending"] == []
        assert board["stats"]["pending_count"] == 0

    def test_history_lists_what_went_out(self, client, gestor, rule, template):
        _post(rule, template, status=AnnouncementStatus.PUBLISHED, published_at=timezone.now())
        _post(rule, template)  # pendente não é histórico
        client.force_login(gestor)

        announcements = client.get(HISTORY_URL).json()["announcements"]
        assert len(announcements) == 1
        assert announcements[0]["status"] == AnnouncementStatus.PUBLISHED


# ── Decisão sobre o announcement ─────────────────────────────────────────────


class TestPostDecision:
    def test_approve_dispatches_the_post(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = _confirmed_post(
            client,
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            {"base_version": 1, "publish_mode": "now"},
            key="approve-dispatch-contract-0001",
        )

        assert response.status_code == 200
        announcement.refresh_from_db()
        assert announcement.status in (AnnouncementStatus.APPROVED, AnnouncementStatus.PUBLISHING, AnnouncementStatus.PUBLISHED)
        assert announcement.approved_by_id == gestor.pk

    def test_v2_approval_returns_one_receipt_and_only_durable_outbox(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)
        url = f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/"
        payload = {
            "base_version": 1,
            "publish_mode": "now",
            "body": "Croissant revisado",
            "hashtags": ["feitohoje"],
            "platforms": ["instagram", "google_business"],
        }

        first = _confirmed_post(
            client,
            url,
            payload,
            key="idem-api-approval-000001",
        )
        replay = client.post(
            url,
            data=payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-api-approval-000001",
        )

        assert first.status_code == replay.status_code == 200
        assert first.json()["receipt"] == replay.json()["receipt"]
        assert first.json()["replayed"] is False
        assert replay.json()["replayed"] is True
        assert first.json()["announcement"]["version"] == 2
        assert MarketingCommandReceipt.objects.count() == 1
        assert MarketingContentArtifact.objects.count() == 1
        assert AudienceSnapshot.objects.count() == 1
        assert MarketingAuditEvent.objects.count() == 1
        assert MarketingOutbox.objects.count() == 2
        assert Directive.objects.count() == 0

    def test_v2_approval_never_downgrades_when_idempotency_header_is_missing(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            data={"base_version": 1, "publish_mode": "now"},
            content_type="application/json",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_idempotency_key"
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW
        assert Directive.objects.count() == 0

    def test_v2_now_overrides_the_announcement_suggested_schedule(
        self, client, gestor, rule, template
    ):
        suggested = timezone.now() + timedelta(hours=3)
        announcement = _post(rule, template, publish_at=suggested)
        client.force_login(gestor)

        response = _confirmed_post(
            client,
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            {"base_version": 1, "publish_mode": "now"},
            key="idem-api-now-beats-schedule",
        )

        assert response.status_code == 200
        assert response.json()["scheduled"] is False
        assert response.json()["receipt"]["outcome"]["publish_mode"] == "now"
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PUBLISHING
        assert announcement.publish_at is None
        assert suggested not in set(
            MarketingOutbox.objects.values_list("available_at", flat=True)
        )

    def test_v2_now_with_a_timestamp_is_rejected_instead_of_guessing(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            data={
                "base_version": 1,
                "publish_mode": "now",
                "publish_at": (timezone.now() + timedelta(hours=3)).isoformat(),
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-api-now-no-timestamp",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "publish_now_has_schedule"
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW
        assert MarketingOutbox.objects.count() == 0

    def test_v2_same_key_with_changed_content_returns_conflict_not_second_approval(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)
        url = f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/"
        base = {"base_version": 1, "publish_mode": "now", "body": "Primeiro"}

        assert _confirmed_post(
            client,
            url,
            base,
            key="idem-api-approval-000002",
        ).status_code == 200
        conflict = client.post(
            url,
            data={**base, "body": "Segundo"},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-api-approval-000002",
        )

        assert conflict.status_code == 409
        assert conflict.json()["code"] == "idempotency_conflict"
        assert MarketingCommandReceipt.objects.count() == 1

    def test_v2_replays_its_version_conflict_even_if_server_content_changes_again(
        self, client, gestor, rule, template
    ):
        from shopman.shop.services import campaign as campaign_service

        announcement = _post(rule, template)
        campaign_service.update_content(announcement.pk, body="Versão dois", base_version=1)
        client.force_login(gestor)
        url = f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/"
        payload = {"base_version": 1, "publish_mode": "now", "body": "Minha revisão"}

        first = client.post(
            url,
            data=payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-api-approval-000003",
        )
        campaign_service.update_content(announcement.pk, body="Versão três", base_version=2)
        replay = client.post(
            url,
            data=payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-api-approval-000003",
        )

        assert first.status_code == replay.status_code == 409
        assert first.json()["code"] == replay.json()["code"] == "version_conflict"
        assert first.json()["receipt_ref"] == replay.json()["receipt_ref"]
        assert first.json()["current_version"] == replay.json()["current_version"] == 2
        assert MarketingCommandReceipt.objects.count() == 1

    def test_v2_reject_has_version_receipt_and_session_actor(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/reject/",
            data={"base_version": 1, "reason": "Imagem incorreta"},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-api-reject-0000001",
        )

        assert response.status_code == 200
        assert response.json()["receipt"]["kind"] == "reject"
        assert response.json()["announcement"]["version"] == 2
        receipt = MarketingCommandReceipt.objects.get()
        assert receipt.actor_id == gestor.pk
        assert receipt.actor_ref == f"user:{gestor.pk}"

    def test_v2_cancel_tombstones_scheduled_outbox(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)
        base_url = f"/api/v1/backstage/marketing/announcements/{announcement.pk}"
        when = timezone.now() + timedelta(hours=2)
        approved = _confirmed_post(
            client,
            f"{base_url}/approve/",
            {
                "base_version": 1,
                "publish_mode": "scheduled",
                "publish_at": when.isoformat(),
            },
            key="idem-api-schedule-00001",
        )
        cancelled = _confirmed_post(
            client,
            f"{base_url}/cancel/",
            {"base_version": 2, "reason": "Oferta interrompida"},
            key="idem-api-cancel-0000001",
        )

        assert approved.status_code == cancelled.status_code == 200
        assert cancelled.json()["announcement"]["status"] == "cancelled"
        assert cancelled.json()["receipt"]["outcome"]["outbox_cancelled"] == 2
        assert MarketingOutbox.objects.filter(
            state=MarketingOutbox.State.CANCELLED,
            cancelled_by_command__kind="cancel",
        ).count() == 2

    def test_v2_reschedule_moves_pending_outbox_and_returns_absolute_time(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)
        base_url = f"/api/v1/backstage/marketing/announcements/{announcement.pk}"
        first_at = timezone.now() + timedelta(hours=2)
        next_at = first_at + timedelta(hours=4)
        _confirmed_post(
            client,
            f"{base_url}/approve/",
            {
                "base_version": 1,
                "publish_mode": "scheduled",
                "publish_at": first_at.isoformat(),
            },
            key="idem-api-schedule-00002",
        )

        response = _confirmed_post(
            client,
            f"{base_url}/reschedule/",
            {"base_version": 2, "publish_at": next_at.isoformat()},
            key="idem-api-reschedule-0001",
        )

        assert response.status_code == 200
        assert response.json()["receipt"]["kind"] == "reschedule"
        assert response.json()["receipt"]["outcome"]["publish_at"] == next_at.isoformat()
        assert set(MarketingOutbox.objects.values_list("available_at", flat=True)) == {next_at}

    def test_rejecting_keeps_it_off_the_air_and_records_who(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/reject/",
            data={"base_version": 1, "reason": "Foto ruim"},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="reject-photo-reason-0001",
        )

        assert response.status_code == 200
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.REJECTED
        # ⚠️ Recusa anônima num balcão com quatro pessoas no turno não é auditável.
        assert announcement.rejected_by_id == gestor.pk
        assert announcement.rejected_reason == "Foto ruim"

    def test_rejecting_without_a_reason_is_blocked(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/reject/",
            data={"base_version": 1},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="reject-reason-required-0001",
        )
        assert response.status_code == 422
        assert response.json()["code"] == "reason_required"
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW
        assert announcement.rejected_reason == ""

    def test_the_projection_tells_the_screen_who_rejected_and_why(self, client, gestor, rule, template):
        """Registrar o motivo sem mostrá-lo em lugar nenhum não serviria para nada."""
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/reject/",
            data={"base_version": 1, "reason": "Produto acabou"},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="reject-projection-reason-001",
        )

        body = response.json()["announcement"]
        assert body["status"] == "rejected"
        assert body["status_label"] == "recusado"
        assert body["rejected_reason"] == "Produto acabou"
        assert body["rejected_by"] != ""

    def test_edit_before_approving(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.patch(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/",
            data={"body": "Fornada quentinha agora", "hashtags": ["#paes", "artesanal"]},
            content_type="application/json",
        )

        assert response.status_code == 200
        announcement.refresh_from_db()
        assert announcement.content["body"] == "Fornada quentinha agora"
        # O "#" é do texto, não do dado: guardar a tag limpa evita "##paes".
        assert announcement.content["hashtags"] == ["paes", "artesanal"]

    def test_edit_returns_next_version_and_stale_edit_preserves_current_draft(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)
        url = f"/api/v1/backstage/marketing/announcements/{announcement.pk}/"

        first = client.patch(
            url,
            data={"body": "Primeira revisão", "base_version": 1},
            content_type="application/json",
        )
        stale = client.patch(
            url,
            data={"body": "Revisão que chegou tarde", "base_version": 1},
            content_type="application/json",
        )

        assert first.status_code == 200
        assert first.json()["announcement"]["version"] == 2
        assert stale.status_code == 409
        assert stale.json()["code"] == "version_conflict"
        assert stale.json()["current_version"] == 2
        announcement.refresh_from_db()
        assert announcement.content["body"] == "Primeira revisão"

    def test_boolean_is_not_accepted_as_a_resource_version(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.patch(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/",
            data={"body": "Texto", "base_version": True},
            content_type="application/json",
        )

        assert response.status_code == 422
        assert response.json()["field"] == "base_version"
        announcement.refresh_from_db()
        assert announcement.version == 1

    def test_published_post_cannot_be_rewritten(self, client, gestor, rule, template):
        announcement = _post(rule, template, status=AnnouncementStatus.PUBLISHED)
        client.force_login(gestor)

        response = client.patch(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/",
            data={"body": "outra coisa"},
            content_type="application/json",
        )

        assert response.status_code == 400
        announcement.refresh_from_db()
        assert announcement.content["body"] == "Croissant saiu do forno"

    def test_empty_body_is_refused(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.patch(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/",
            data={"body": "   "},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "body"


# ── Regras ───────────────────────────────────────────────────────────


class TestRules:
    def test_create_rule(self, client, gestor, template):
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={
                "name": "Estoque baixo → Google",
                "trigger": "low_stock",
                "template_id": template.pk,
                "platforms": ["google_business"],
                "expires_after_minutes": 240,
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        rule = Campaign.objects.get(name="Estoque baixo → Google")
        assert rule.trigger == "low_stock"
        assert rule.expires_after_minutes == 240

    def test_unknown_trigger_is_refused(self, client, gestor, template):
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={
                "name": "X", "trigger": "fornada_magica",
                "template_id": template.pk, "platforms": ["instagram"],
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "trigger"

    def test_unknown_platform_is_refused(self, client, gestor, template):
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={
                "name": "X", "trigger": "low_stock",
                "template_id": template.pk, "platforms": ["tiktok"],
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "platforms"

    def test_rule_without_platform_is_refused(self, client, gestor, template):
        """Regra sem destino dispara no vazio — melhor recusar na criação."""
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={"name": "X", "trigger": "low_stock", "template_id": template.pk, "platforms": []},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "platforms"

    def test_a_scheduled_rule_without_a_firing_schedule_is_refused(self, client, gestor, template):
        """⚠️ A regra vive no `clean()` do model, mas quem salva aqui é a API.

        Django só chama `clean()` em formulário — o Admin chamava, esta API não. Sem a
        ponte, o app do gestor criava a campanha agendada que nunca dispara.
        """
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={
                "name": "Relâmpago torta", "trigger": "schedule",
                "template_id": template.pk, "platforms": ["whatsapp"],
                "schedule": {"type": "immediate"},
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "schedule"
        assert not Campaign.objects.filter(name="Relâmpago torta").exists()

    def test_a_scheduled_rule_with_a_real_occasion_is_created(self, client, gestor, template):
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={
                "name": "Relâmpago das 17h30", "trigger": "schedule",
                "template_id": template.pk, "platforms": ["whatsapp"],
                "schedule": {"type": "recurring", "windows": [["17:30", "18:30"]]},
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        body = response.json()["rule"]
        assert body["fires_on_its_own"] is True
        assert body["exhausted"] is False
        assert "17:30" in body["schedule_label"], body["schedule_label"]

    def test_patching_into_the_impossible_pairing_is_refused(self, client, gestor, rule):
        """Editar também precisa do guarda — senão a regra entra pela porta de trás."""
        client.force_login(gestor)

        response = client.patch(
            f"{RULES_URL}{rule.pk}/",
            data={"trigger": "schedule"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "schedule"
        rule.refresh_from_db()
        assert rule.trigger != "schedule"

    def test_toggle_rule_off(self, client, gestor, rule):
        client.force_login(gestor)

        response = client.patch(
            f"{RULES_URL}{rule.pk}/",
            data={"is_active": False},
            content_type="application/json",
        )

        assert response.status_code == 200
        rule.refresh_from_db()
        assert rule.is_active is False


# ── Modelos de announcement ──────────────────────────────────────────────────


class TestTemplates:
    def test_create_template(self, client, gestor):
        client.force_login(gestor)

        response = client.post(
            TEMPLATES_URL,
            data={"name": "Simples", "body": "{{product_name}} por {{price}}"},
            content_type="application/json",
        )

        assert response.status_code == 201
        assert AnnouncementTemplate.objects.filter(name="Simples").exists()

    def test_template_in_use_cannot_be_deleted(self, client, gestor, rule, template):
        """PROTECT no model: apagar deixaria a regra disparando no vazio."""
        client.force_login(gestor)

        response = client.delete(f"{TEMPLATES_URL}{template.pk}/")

        assert response.status_code == 400
        assert AnnouncementTemplate.objects.filter(pk=template.pk).exists()

    def test_unused_template_can_be_deleted(self, client, gestor):
        template = AnnouncementTemplate.objects.create(name="Órfão", body="x")
        client.force_login(gestor)

        assert client.delete(f"{TEMPLATES_URL}{template.pk}/").status_code == 200
        assert not AnnouncementTemplate.objects.filter(pk=template.pk).exists()


# ── Opções do formulário ─────────────────────────────────────────────


class TestOptions:
    def test_options_feed_the_rule_form(self, client, gestor, template):
        client.force_login(gestor)

        options = client.get(OPTIONS_URL).json()["options"]

        assert {t["value"] for t in options["triggers"]} >= {"production_finished", "low_stock"}
        assert {p["value"] for p in options["platforms"]} >= {"instagram", "google_business"}
        assert template.pk in {t["pk"] for t in options["templates"]}
        assert "product_name" in options["variables"]


class TestScheduledPublishing:
    """"Agendar" no card: a decisão é agora, a publicação é na hora marcada."""

    def test_future_publish_at_schedules_instead_of_dispatching(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)
        when = timezone.now() + timedelta(hours=3)

        response = _confirmed_post(
            client,
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            {
                "base_version": 1,
                "publish_mode": "scheduled",
                "publish_at": when.isoformat(),
            },
            key="scheduled-publish-contract-0001",
        )

        assert response.status_code == 200
        assert response.json()["scheduled"] is True
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.APPROVED
        assert announcement.publish_at is not None

    def test_approve_applies_the_card_edits_in_the_same_request(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = _confirmed_post(
            client,
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            {
                "base_version": 1,
                "publish_mode": "now",
                "body": "Texto revisado pelo gestor",
                "platforms": ["instagram"],
            },
            key="approval-with-edits-contract-01",
        )

        assert response.status_code == 200
        announcement.refresh_from_db()
        assert announcement.content["body"] == "Texto revisado pelo gestor"
        assert announcement.platforms == ["instagram"]

    def test_garbage_date_is_refused_before_anything_is_published(
        self, client, gestor, rule, template
    ):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            data={
                "base_version": 1,
                "publish_mode": "scheduled",
                "publish_at": "amanhã cedo",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="invalid-schedule-contract-0001",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_publish_at"
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW

    def test_empty_body_is_refused(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            data={"base_version": 1, "publish_mode": "now", "body": "   "},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="empty-body-contract-000001",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_approval_content"


class TestPlatformResultDetail:
    """O painel precisa do PORQUÊ, e o handler não grava numa chave só."""

    def _results(self, client, gestor, rule, template, results):
        announcement = _post(rule, template, status=AnnouncementStatus.PUBLISHED, platform_results=results)
        client.force_login(gestor)
        response = client.get(HISTORY_URL)
        assert response.status_code == 200
        found = next(p for p in response.json()["announcements"] if p["pk"] == announcement.pk)
        return {r["platform"]: r for r in found["platform_results"]}

    def test_failure_reason_reaches_the_screen(self, client, gestor, rule, template):
        # O handler grava ``error`` na falha — ler só ``detail`` deixaria um
        # "falhou" mudo no histórico.
        results = self._results(
            client, gestor, rule, template,
            {"instagram": {"status": "failed", "error": "token expirado"}},
        )
        assert results["instagram"]["detail"] == "token expirado"

    def test_manual_pending_explains_itself(self, client, gestor, rule, template):
        results = self._results(
            client, gestor, rule, template,
            {"instagram": {"status": "pending_manual", "reason": "sem adapter configurado"}},
        )
        assert results["instagram"]["status"] == "pending_manual"
        assert results["instagram"]["detail"] == "sem adapter configurado"

    def test_whatsapp_reports_how_many_actually_went_out(self, client, gestor, rule, template):
        announcement = _post(
            rule, template, status=AnnouncementStatus.PUBLISHED, platforms=["whatsapp"],
            platform_results={"whatsapp": {"status": "sent", "sent": 38, "failed": 2}},
        )
        client.force_login(gestor)
        found = next(
            p for p in client.get(HISTORY_URL).json()["announcements"] if p["pk"] == announcement.pk
        )
        assert found["platform_results"][0]["detail"] == "38 enviados, 2 falharam"

    def test_a_clean_whatsapp_wave_does_not_invent_a_failure_count(
        self, client, gestor, rule, template
    ):
        announcement = _post(
            rule, template, status=AnnouncementStatus.PUBLISHED, platforms=["whatsapp"],
            platform_results={"whatsapp": {"status": "sent", "sent": 40, "failed": 0}},
        )
        client.force_login(gestor)
        found = next(
            p for p in client.get(HISTORY_URL).json()["announcements"] if p["pk"] == announcement.pk
        )
        assert found["platform_results"][0]["detail"] == "40 enviados"

    def test_targeted_platform_with_no_answer_yet_stays_visible(
        self, client, gestor, rule, template
    ):
        # Silêncio no painel esconderia justamente o caso que precisa de ação.
        results = self._results(client, gestor, rule, template, {})
        assert results["instagram"]["status"] == "queued"


# ── Disparo manual (F8) ──────────────────────────────────────────────
#
# Até aqui um anúncio só nascia de evento operacional, então "quero avisar meus clientes
# hoje" não tinha caminho nenhum. Esta é a Action que dá produtor real ao
# `Trigger.MANUAL`.


def _fire_url(rule) -> str:
    return f"{RULES_URL}{rule.pk}/fire/"


class TestManualFire:
    def test_legacy_fire_is_contained_before_any_announcement_or_effect(
        self, client, gestor, rule
    ):
        client.force_login(gestor)
        resp = client.post(
            _fire_url(rule),
            data={"body": "Fornada extra hoje, a partir das 16h."},
            content_type="application/json",
        )

        assert resp.status_code == 409
        assert resp.json()["code"] == "fire_command_upgrade_required"
        assert Announcement.objects.filter(rule=rule).count() == 0
        assert MarketingCommandReceipt.objects.count() == 0

    def test_firing_requires_the_permission(self, client, rule):
        outsider = User.objects.create_user(username="curioso", password="x", is_staff=True)
        client.force_login(outsider)
        resp = client.post(_fire_url(rule), data={}, content_type="application/json")
        assert resp.status_code == 403


# ── Escolher o template do WhatsApp DAQUI, não no Admin ──────────────
#
# "Admin = só config" limita o Admin; não exila configuração do app de operador. Escolher
# o template com que o anúncio sai é inseparável de operar o anúncio.

WA_TEMPLATE_URL = "/api/v1/backstage/marketing/whatsapp-template/"

FAKE_FLOWS = (
    ("content20240614222050_512341", "Fresh batch announcement"),
    ("content20210201131015_377918", "Product available alert"),
)


@pytest.fixture
def flows(monkeypatch):
    from shopman.shop.services import manychat_flows

    monkeypatch.setattr(manychat_flows, "list_flows", lambda **kw: FAKE_FLOWS)


@pytest.fixture
def no_flows(monkeypatch):
    """A plataforma não respondeu — diferente de "não há template"."""
    from shopman.shop.services import manychat_flows

    monkeypatch.setattr(manychat_flows, "list_flows", lambda **kw: ())


class TestWhatsAppTemplateFromTheSurface:
    def test_it_lists_the_approved_templates(self, client, gestor, flows):
        client.force_login(gestor)
        body = client.get(WA_TEMPLATE_URL).json()

        assert body["can_list"] is True
        assert {t["ns"] for t in body["available"]} == {ns for ns, _ in FAKE_FLOWS}
        assert body["current"] == ""
        assert body["configured"] is False

    def test_legacy_config_write_is_contained_until_cas_command(
        self, client, gestor, flows
    ):
        from shopman.shop.models import NotificationTemplate

        client.force_login(gestor)
        resp = client.post(
            WA_TEMPLATE_URL,
            data={"flow_ns": FAKE_FLOWS[0][0]},
            content_type="application/json",
        )

        assert resp.status_code == 409
        assert resp.json()["code"] == "platform_config_cas_not_ready"
        assert not NotificationTemplate.objects.filter(
            event="announcement_published"
        ).exists()

    def test_clearing_cannot_bypass_the_same_config_command(self, client, gestor, flows):
        from shopman.shop.models import NotificationTemplate

        client.force_login(gestor)
        resp = client.post(WA_TEMPLATE_URL, data={"flow_ns": ""},
                           content_type="application/json")

        assert resp.status_code == 409
        assert not NotificationTemplate.objects.filter(
            event="announcement_published"
        ).exists()

    def test_a_template_that_no_longer_exists_is_refused(self, client, gestor, flows):
        client.force_login(gestor)
        resp = client.post(WA_TEMPLATE_URL, data={"flow_ns": "content20200101000000_000000"},
                           content_type="application/json")

        assert resp.status_code == 409
        assert resp.json()["code"] == "platform_config_cas_not_ready"

    def test_platform_outage_cannot_turn_into_an_unverified_write(
        self, client, gestor, no_flows
    ):
        client.force_login(gestor)
        resp = client.post(WA_TEMPLATE_URL, data={"flow_ns": "content20991231235959_999999"},
                           content_type="application/json")

        assert resp.status_code == 409
        assert resp.json()["code"] == "platform_config_cas_not_ready"

    def test_the_surface_distinguishes_cannot_list_from_empty(self, client, gestor, no_flows):
        client.force_login(gestor)
        body = client.get(WA_TEMPLATE_URL).json()

        assert body["can_list"] is False, "a tela precisa saber que não foi possível perguntar"

    def test_it_requires_the_campaign_permission(self, client, flows):
        outsider = User.objects.create_user(username="curioso2", password="x", is_staff=True)
        client.force_login(outsider)
        assert client.get(WA_TEMPLATE_URL).status_code == 403


class _SandboxAdapter:
    def __init__(self, *, accepted=True, available=True, error=None):
        self.accepted = accepted
        self.available = available
        self.error = error
        self.calls = []

    def is_available(self, _recipient):
        return self.available

    def send(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.accepted


@pytest.fixture
def test_lane(settings, monkeypatch):
    recipient = "4605528796186498"
    settings.SHOPMAN_MARKETING_TEST_TARGETS = {
        "owner-sandbox": {
            "label": "Aparelho verificado",
            "recipient": recipient,
            "backend": "manychat",
            "sandbox": True,
            "ownership_verified": True,
        },
    }
    adapter = _SandboxAdapter()
    monkeypatch.setattr("shopman.shop.notifications._adapters", {"manychat": adapter})
    return adapter, recipient


class TestWhatsAppTestSend:
    """Teste isolado: ref verificada, receipt, max-1, quota e zero PII."""

    URL = "/api/v1/backstage/marketing/whatsapp-template/test/"
    KEY = "test-send-0123456789"

    def _post(self, client, payload, *, key=None):
        return client.post(
            self.URL,
            data=payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key or self.KEY,
        )

    def test_staff_without_permission_cannot_send(self, client):
        User.objects.create_user(username="caixa2", password="x", is_staff=True)
        client.login(username="caixa2", password="x")
        assert client.post(self.URL).status_code == 403

    def test_a_verified_target_is_required(self, client, gestor):
        client.force_login(gestor)
        response = self._post(client, {})
        assert response.status_code == 422

    def test_free_recipient_and_audience_payload_are_rejected_before_adapter(
        self, client, gestor, test_lane
    ):
        adapter, _recipient = test_lane
        client.force_login(gestor)
        response = self._post(client, {
            "target_ref": "owner-sandbox",
            "recipient": "4605528796186498,4605528796186499",
            "audience_rules": {"favorites": True},
        })

        assert response.status_code == 422
        assert response.json()["code"] == "test_payload_not_isolated"
        assert adapter.calls == []

    def test_missing_idempotency_key_is_rejected(self, client, gestor, test_lane):
        client.force_login(gestor)
        response = client.post(
            self.URL,
            data={"target_ref": "owner-sandbox"},
            content_type="application/json",
        )
        assert response.status_code == 422

    def test_it_sends_once_and_returns_safe_receipt(self, client, gestor, test_lane):
        from shopman.offerman.models import Product

        from shopman.shop.models import MarketingTestReceipt

        adapter, recipient = test_lane
        Product.objects.create(
            sku="BAGUETE-TEST", name="Baguete", base_price_q=1600,
            is_published=True, is_sellable=True,
        )
        client.force_login(gestor)
        response = self._post(client, {
            "target_ref": "owner-sandbox", "sku": "BAGUETE-TEST",
        })

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["state"] == "accepted_unconfirmed"
        assert body["sandbox"] is True
        assert body["max_targets"] == 1
        assert body["target_ref"] == "owner-sandbox"
        assert body["fields"]["customer_name"] == "Cliente teste"
        assert body["fields"]["product_name"] == "Baguete"
        assert body["fields"]["product_sku"] == "BAGUETE-TEST"
        assert len(adapter.calls) == 1
        assert adapter.calls[0]["recipient"] == recipient
        assert recipient not in json.dumps(body)
        receipt = MarketingTestReceipt.objects.get(ref=body["receipt_ref"])
        assert receipt.sandbox is True
        assert receipt.max_targets == 1
        assert receipt.retention_until >= timezone.now() + timedelta(days=179)
        stored_fields = {field.name for field in receipt._meta.fields}
        assert "recipient" not in stored_fields
        assert "body" not in stored_fields
        assert "idempotency_key" not in stored_fields

    def test_target_options_expose_safe_refs_never_recipient(
        self, client, gestor, test_lane, monkeypatch
    ):
        _adapter, recipient = test_lane
        monkeypatch.setattr("shopman.shop.services.manychat_flows.list_flows", lambda: [])
        client.force_login(gestor)

        response = client.get("/api/v1/backstage/marketing/whatsapp-template/")

        assert response.json()["test_targets"] == [{
            "ref": "owner-sandbox",
            "label": "Aparelho verificado",
            "backend": "manychat",
        }]
        assert recipient not in response.content.decode()

    def test_same_key_same_payload_replays_receipt_without_second_effect(
        self, client, gestor, test_lane
    ):
        adapter, _recipient = test_lane
        client.force_login(gestor)
        payload = {"target_ref": "owner-sandbox"}

        first = self._post(client, payload).json()
        second = self._post(client, payload).json()

        assert first["receipt_ref"] == second["receipt_ref"]
        assert second["replayed"] is True
        assert len(adapter.calls) == 1

    def test_same_key_different_payload_is_conflict(self, client, gestor, test_lane):
        client.force_login(gestor)
        assert self._post(client, {"target_ref": "owner-sandbox", "body": "A"}).status_code == 200

        response = self._post(client, {"target_ref": "owner-sandbox", "body": "B"})

        assert response.status_code == 409
        assert response.json()["code"] == "idempotency_conflict"

    def test_provider_exception_is_unknown_and_redacted(
        self, client, gestor, test_lane, monkeypatch
    ):
        adapter, recipient = test_lane
        adapter.error = RuntimeError(f"vendor exploded for {recipient}")
        emitted = []
        monkeypatch.setattr(
            "shopman.shop.services.campaign.logger.warning",
            lambda message, *args: emitted.append(message % args),
        )
        client.force_login(gestor)

        response = self._post(client, {"target_ref": "owner-sandbox"})
        serialized = json.dumps(response.json()) + " ".join(emitted)

        assert response.status_code == 200
        assert response.json()["state"] == "unknown"
        assert response.json()["detail"] == "provider_outcome_unknown"
        assert recipient not in serialized
        assert "vendor exploded" not in serialized

    def test_unavailable_sandbox_is_503_with_a_safe_receipt(
        self, client, gestor, test_lane
    ):
        from shopman.shop.models import MarketingTestReceipt

        adapter, _recipient = test_lane
        adapter.available = False
        client.force_login(gestor)

        response = self._post(client, {"target_ref": "owner-sandbox"})

        assert response.status_code == 503
        assert response.json()["code"] == "sandbox_unavailable"
        receipt = MarketingTestReceipt.objects.get(ref=response.json()["receipt_ref"])
        assert receipt.state == MarketingTestReceipt.State.FAILED_FINAL

    def test_sixth_test_in_an_hour_is_throttled_with_retry_after(
        self, client, gestor, test_lane
    ):
        adapter, _recipient = test_lane
        client.force_login(gestor)
        for index in range(5):
            response = self._post(
                client,
                {"target_ref": "owner-sandbox"},
                key=f"test-send-throttle-{index:04d}",
            )
            assert response.status_code == 200

        response = self._post(
            client,
            {"target_ref": "owner-sandbox"},
            key="test-send-throttle-9999",
        )

        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0
        assert len(adapter.calls) == 5

    def test_twenty_first_test_in_rolling_day_is_shop_throttled(
        self, client, gestor, test_lane, monkeypatch
    ):
        adapter, _recipient = test_lane
        monkeypatch.setattr(
            "shopman.shop.services.campaign._TEST_USER_HOURLY_LIMIT", 100
        )
        client.force_login(gestor)
        for index in range(20):
            assert self._post(
                client,
                {"target_ref": "owner-sandbox"},
                key=f"test-send-daily-{index:04d}",
            ).status_code == 200

        response = self._post(
            client,
            {"target_ref": "owner-sandbox"},
            key="test-send-daily-9999",
        )

        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 3600
        assert len(adapter.calls) == 20

    def test_test_path_never_calls_audience_resolver(
        self, client, gestor, test_lane, monkeypatch
    ):
        monkeypatch.setattr(
            "shopman.shop.services.audience.resolve",
            lambda *_args, **_kwargs: pytest.fail("test-send alcançou audience resolver"),
        )
        client.force_login(gestor)

        assert self._post(client, {"target_ref": "owner-sandbox"}).status_code == 200


# ── Quantas pessoas isto alcança ─────────────────────────────────────


COUNT_URL = "/api/v1/backstage/marketing/audience/count/"


class TestAudienceCount:
    """⚠️ A tela deixava escolher público às cegas: o tamanho só aparecia depois do envio.

    E sem contagem, a diferença entre somar e cruzar as regras era invisível — "leais +
    atacado" alargava para 5 quando o gestor queria os 2 que são as duas coisas.
    """

    def _audience(self):
        """Três pessoas: uma fiel-e-atacado, uma só fiel, uma só atacado."""
        from shopman.guestman import ConsentService
        from shopman.guestman.contrib.insights.models import CustomerInsight
        from shopman.guestman.models import Customer, PriceTier

        atacado = PriceTier.objects.create(ref="atacado", name="Atacado")
        rows = [
            ("CLI-BOTH", "+5543999993001", atacado, "loyal_customer"),
            ("CLI-LOYAL", "+5543999993002", None, "loyal_customer"),
            ("CLI-WHOLE", "+5543999993003", atacado, "at_risk"),
        ]
        for ref, phone, tier, segment in rows:
            customer = Customer.objects.create(ref=ref, first_name="Ana", phone=phone, price_tier=tier)
            CustomerInsight.objects.create(customer=customer, rfm_segment=segment)
            ConsentService.grant_consent(ref, "whatsapp", source="test")

    def test_the_gate_holds(self, client, django_user_model):
        """Público é informação de cliente: quem não gerencia campanha não conta ninguém."""
        django_user_model.objects.create_user(username="caixa", password="x", is_staff=True)
        client.login(username="caixa", password="x")
        assert client.post(COUNT_URL, {}, content_type="application/json").status_code == 403

    def test_adding_rules_widens_the_reach(self, client, gestor):
        self._audience()
        client.force_login(gestor)

        response = client.post(
            COUNT_URL,
            {"audience_rules": {"price_tiers": ["atacado"], "rfm_segments": ["loyal_customer"]}},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["match"] == "any"
        assert data["match_label"] == "Somando as regras"

    def test_crossing_rules_narrows_it(self, client, gestor):
        """"fiéis QUE são atacado" — o recorte que a união não sabe fazer."""
        self._audience()
        client.force_login(gestor)

        response = client.post(
            COUNT_URL,
            {"audience_rules": {
                "price_tiers": ["atacado"], "rfm_segments": ["loyal_customer"], "match": "all",
            }},
            content_type="application/json",
        )

        data = response.json()
        assert data["total"] == 1
        assert data["match_label"] == "Cruzando as regras"

    def test_the_parts_explain_the_total(self, client, gestor):
        """""Faixa de preço 2, comportamento 2, total 1": a leitura junta ensina o recorte."""
        self._audience()
        client.force_login(gestor)

        data = client.post(
            COUNT_URL,
            {"audience_rules": {
                "price_tiers": ["atacado"], "rfm_segments": ["loyal_customer"], "match": "all",
            }},
            content_type="application/json",
        ).json()

        parts = {part["label"]: part["count"] for part in data["parts"]}
        assert parts == {"Faixa de preço": 2, "Comportamento de compra": 2}
        assert data["total"] == 1

    def test_nothing_chosen_is_not_the_same_as_nobody_found(self, client, gestor):
        """A tela precisa dizer coisas diferentes nos dois casos."""
        client.force_login(gestor)

        empty = client.post(COUNT_URL, {}, content_type="application/json").json()
        assert empty["empty_selection"] is True
        assert empty["total"] == 0
        assert empty["parts"] == []

        chosen = client.post(
            COUNT_URL, {"audience_rules": {"birthday_today": True}},
            content_type="application/json",
        ).json()
        assert chosen["empty_selection"] is False
        assert chosen["total"] == 0

    def test_it_never_returns_a_recipient(self, client, gestor):
        """Só números. A lista de destinatários não sai da resolução — nem para contar."""
        self._audience()
        client.force_login(gestor)

        raw = client.post(
            COUNT_URL, {"audience_rules": {"price_tiers": ["atacado"]}},
            content_type="application/json",
        ).content.decode()

        assert "5543999993001" not in raw
        assert "CLI-BOTH" not in raw

    def test_source_outage_is_explicit_and_blocks_approval(self, client, gestor):
        from unittest.mock import patch

        client.force_login(gestor)
        with patch(
            "shopman.shop.adapters.audience_sources.favorite_customer_refs",
            side_effect=RuntimeError("unavailable"),
        ):
            data = client.post(
                COUNT_URL,
                {"sku": "SKU-OUTAGE", "audience_rules": {"favorites": True}},
                content_type="application/json",
            ).json()

        assert data["total"] == 0
        assert data["degraded_sources"] == ["favorites"]
        assert data["can_approve"] is False
        assert data["blocked_reason"]

    def test_a_broken_payload_counts_nobody_instead_of_exploding(self, client, gestor):
        client.force_login(gestor)
        response = client.post(
            COUNT_URL, {"audience_rules": "atacado"}, content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0
