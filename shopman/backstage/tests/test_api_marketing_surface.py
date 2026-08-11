"""Contrato da superfície Campanha (surfaces/marketing-nuxt).

O que este arquivo protege, em ordem de importância:

1. **O gate.** ``shop.manage_campaigns`` é o portão. Staff comum não publica —
   quem cuida da fila de pedidos não decide o que a padaria diz ao mundo.
2. **Anúncio que já saiu não se reescreve.** Editar o corpo depois de publicado
   seria mentira retroativa sobre o que o cliente leu.
3. **As chaves que o Nuxt lê.** Se a projection mudar de forma, o app quebra em
   silêncio; aqui quebra em vermelho.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone

from shopman.shop.models import Announcement, AnnouncementStatus, AnnouncementTemplate, Campaign

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
    user.user_permissions.add(Permission.objects.get(codename="manage_campaigns"))
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
        response = client.post(f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/")
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

        response = client.post(f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/")

        assert response.status_code == 200
        announcement.refresh_from_db()
        assert announcement.status in (AnnouncementStatus.APPROVED, AnnouncementStatus.PUBLISHING, AnnouncementStatus.PUBLISHED)
        assert announcement.approved_by_id == gestor.pk

    def test_rejecting_keeps_it_off_the_air_and_records_who(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/reject/",
            data={"reason": "Foto ruim"},
            content_type="application/json",
        )

        assert response.status_code == 200
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.REJECTED
        # ⚠️ Recusa anônima num balcão com quatro pessoas no turno não é auditável.
        assert announcement.rejected_by_id == gestor.pk
        assert announcement.rejected_reason == "Foto ruim"

    def test_rejecting_without_a_reason_still_works(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        assert client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/reject/"
        ).status_code == 200
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.REJECTED
        assert announcement.rejected_reason == ""

    def test_the_projection_tells_the_screen_who_rejected_and_why(self, client, gestor, rule, template):
        """Registrar o motivo sem mostrá-lo em lugar nenhum não serviria para nada."""
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/reject/",
            data={"reason": "Produto acabou"},
            content_type="application/json",
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

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            data={"publish_at": when.isoformat()},
            content_type="application/json",
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

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            data={"body": "Texto revisado pelo gestor", "platforms": ["instagram"]},
            content_type="application/json",
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
            data={"publish_at": "amanhã cedo"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "publish_at"
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW

    def test_empty_body_is_refused(self, client, gestor, rule, template):
        announcement = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            data={"body": "   "},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "body"


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
    def test_firing_creates_an_announcement_now(self, client, gestor, rule):
        client.force_login(gestor)
        resp = client.post(_fire_url(rule), data={}, content_type="application/json")

        assert resp.status_code == 201
        body = resp.json()
        assert body["ok"] is True
        assert Announcement.objects.filter(rule=rule).count() == 1

    def test_firing_without_a_text_still_goes_to_review(self, client, gestor, rule):
        """Sem texto escrito, quem escreveu foi o modelo — e aí a revisão tem função."""
        client.force_login(gestor)
        client.post(_fire_url(rule), data={}, content_type="application/json")

        announcement = Announcement.objects.get(rule=rule)
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW

    def test_a_text_written_now_publishes_straight_away(self, client, gestor, rule):
        """⚠️ "Quem cria publica" (ADR-020 §8).

        Não existe segundo par de olhos quando o autor e o revisor são a mesma pessoa. A
        revisão continua valendo para o que a OPERAÇÃO gerou — fornada, estoque baixo —,
        que é o caso em que existe outra pessoa para conferir.
        """
        client.force_login(gestor)

        resp = client.post(
            _fire_url(rule),
            data={"body": "Fornada extra hoje, a partir das 16h."},
            content_type="application/json",
        )

        assert resp.status_code == 201
        announcement = Announcement.objects.get(rule=rule)
        assert announcement.status != AnnouncementStatus.PENDING_REVIEW
        assert announcement.content["body"] == "Fornada extra hoje, a partir das 16h."

    def test_publishing_without_review_still_records_who_decided(self, client, gestor, rule):
        """Anúncio que saiu sem revisão não pode ficar sem nome atrás."""
        client.force_login(gestor)

        client.post(
            _fire_url(rule),
            data={"body": "Fornada extra hoje."},
            content_type="application/json",
        )

        announcement = Announcement.objects.get(rule=rule)
        assert announcement.approved_by_id == gestor.pk
        assert announcement.approved_at is not None

    def test_a_blank_text_is_not_a_text(self, client, gestor, rule):
        """⚠️ Só espaços publicaria uma mensagem em branco, sem ninguém revisar."""
        client.force_login(gestor)

        client.post(_fire_url(rule), data={"body": "   "}, content_type="application/json")

        announcement = Announcement.objects.get(rule=rule)
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW

    def test_writing_the_text_does_not_change_the_saved_campaign(self, client, gestor, rule):
        """`requires_approval` da campanha não é atropelado em silêncio."""
        client.force_login(gestor)

        client.post(
            _fire_url(rule), data={"body": "Fornada extra."}, content_type="application/json"
        )

        rule.refresh_from_db()
        assert rule.requires_approval is True

    def test_a_chosen_audience_applies_to_this_shot_only(self, client, gestor, rule):
        """A campanha salva mantém o público dela; a escolha vale para este disparo."""
        client.force_login(gestor)
        resp = client.post(
            _fire_url(rule),
            data={"audience_rules": {"birthday_today": True}},
            content_type="application/json",
        )
        assert resp.status_code == 201

        rule.refresh_from_db()
        assert rule.audience_rules == {"favorites": True}, "a campanha não devia ter mudado"

    def test_an_inactive_campaign_refuses_instead_of_going_quiet(self, client, gestor, rule):
        """Disparar campanha desligada é quase sempre engano; silêncio esconderia."""
        rule.is_active = False
        rule.save(update_fields=["is_active"])
        client.force_login(gestor)

        resp = client.post(_fire_url(rule), data={}, content_type="application/json")
        assert resp.status_code == 400
        assert Announcement.objects.filter(rule=rule).count() == 0

    def test_a_malformed_audience_is_a_400_not_a_500(self, client, gestor, rule):
        client.force_login(gestor)
        resp = client.post(
            _fire_url(rule),
            data={"audience_rules": ["nao", "e", "objeto"]},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.json()["field"] == "audience_rules"

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

    def test_choosing_one_configures_the_event(self, client, gestor, flows):
        from shopman.shop.models import NotificationTemplate

        client.force_login(gestor)
        resp = client.post(
            WA_TEMPLATE_URL,
            data={"flow_ns": FAKE_FLOWS[0][0]},
            content_type="application/json",
        )

        assert resp.status_code == 200
        assert resp.json()["configured"] is True
        saved = NotificationTemplate.objects.get(event="announcement_published")
        assert saved.whatsapp_flow_ns == FAKE_FLOWS[0][0]

    def test_clearing_is_allowed_and_says_what_it_costs(self, client, gestor, flows):
        from shopman.shop.models import NotificationTemplate

        client.force_login(gestor)
        client.post(WA_TEMPLATE_URL, data={"flow_ns": FAKE_FLOWS[0][0]},
                    content_type="application/json")
        resp = client.post(WA_TEMPLATE_URL, data={"flow_ns": ""},
                           content_type="application/json")

        assert resp.status_code == 200
        assert resp.json()["configured"] is False
        assert NotificationTemplate.objects.get(event="announcement_published").whatsapp_flow_ns == ""

    def test_a_template_that_no_longer_exists_is_refused(self, client, gestor, flows):
        client.force_login(gestor)
        resp = client.post(WA_TEMPLATE_URL, data={"flow_ns": "content20200101000000_000000"},
                           content_type="application/json")

        assert resp.status_code == 400
        assert resp.json()["field"] == "flow_ns"

    def test_with_the_platform_down_the_choice_is_not_blocked(self, client, gestor, no_flows):
        """Indisponibilidade de terceiro não pode travar o operador."""
        client.force_login(gestor)
        resp = client.post(WA_TEMPLATE_URL, data={"flow_ns": "content20991231235959_999999"},
                           content_type="application/json")

        assert resp.status_code == 200, "sem lista para validar, aceita e confia"

    def test_the_surface_distinguishes_cannot_list_from_empty(self, client, gestor, no_flows):
        client.force_login(gestor)
        body = client.get(WA_TEMPLATE_URL).json()

        assert body["can_list"] is False, "a tela precisa saber que não foi possível perguntar"

    def test_it_requires_the_campaign_permission(self, client, flows):
        outsider = User.objects.create_user(username="curioso2", password="x", is_staff=True)
        client.force_login(outsider)
        assert client.get(WA_TEMPLATE_URL).status_code == 403


class TestWhatsAppTestSend:
    """Testar o template é conferência de dez segundos, e mora na tela.

    Existia só como comando de terminal, e o dono foi direto ao ponto: por que ele abriria
    um terminal para isso? Este endpoint é o mesmo serviço, alcançável pelo painel.
    """

    URL = "/api/v1/backstage/marketing/whatsapp-template/test/"

    def test_staff_without_permission_cannot_send(self, client):
        User.objects.create_user(username="caixa2", password="x", is_staff=True)
        client.login(username="caixa2", password="x")
        assert client.post(self.URL).status_code == 403

    def test_a_recipient_is_required(self, client, gestor):
        client.force_login(gestor)
        response = client.post(self.URL, data={}, content_type="application/json")
        assert response.status_code == 400

    def test_it_refuses_a_list(self, client, gestor):
        """⚠️ Um destinatário por chamada: aceitar lista transformaria isto em disparo."""
        client.force_login(gestor)
        response = client.post(
            self.URL,
            data={"recipient": "4605528796186498,4605528796186499"},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_without_transport_it_says_so_instead_of_pretending(self, client, gestor, monkeypatch):
        client.force_login(gestor)
        monkeypatch.setattr("shopman.shop.handlers.campaign._whatsapp_backend", lambda: None)

        response = client.post(
            self.URL, data={"recipient": "4605528796186498"}, content_type="application/json"
        )

        assert response.status_code == 400
        assert "transporte" in response.json()["detail"]

    def test_it_sends_the_real_variables_and_reports_them(self, client, gestor, monkeypatch):
        """A tela mostra o que o template recebeu — campo vazio explica variável vazia."""
        from shopman.offerman.models import Product

        Product.objects.create(
            sku="BAGUETE-TEST", name="Baguete", base_price_q=1600,
            is_published=True, is_sellable=True,
        )
        client.force_login(gestor)
        monkeypatch.setattr("shopman.shop.handlers.campaign._whatsapp_backend", lambda: "manychat")
        monkeypatch.setattr(
            "shopman.shop.notifications.notify",
            lambda **kw: type("R", (), {"success": True, "message_id": "m1"})(),
        )

        response = client.post(
            self.URL,
            data={"recipient": "4605528796186498", "sku": "BAGUETE-TEST", "name": "Pablo"},
            content_type="application/json",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["fields"]["customer_name"] == "Pablo"
        assert body["fields"]["product_name"] == "Baguete"
        assert body["fields"]["product_sku"] == "BAGUETE-TEST"

    def test_a_refused_send_is_reported_as_refused(self, client, gestor, monkeypatch):
        client.force_login(gestor)
        monkeypatch.setattr("shopman.shop.handlers.campaign._whatsapp_backend", lambda: "manychat")
        monkeypatch.setattr(
            "shopman.shop.notifications.notify",
            lambda **kw: type("R", (), {"success": False, "error": "sem janela"})(),
        )

        body = client.post(
            self.URL, data={"recipient": "4605528796186498"}, content_type="application/json"
        ).json()

        assert body["ok"] is False
        assert body["detail"]


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
        assert data["match_label"] == "somando as regras"

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
        assert data["match_label"] == "cruzando as regras"

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

    def test_a_broken_payload_counts_nobody_instead_of_exploding(self, client, gestor):
        client.force_login(gestor)
        response = client.post(
            COUNT_URL, {"audience_rules": "atacado"}, content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0
