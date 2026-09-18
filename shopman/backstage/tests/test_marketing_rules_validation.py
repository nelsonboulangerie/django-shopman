"""Regra de público com valor que não é inteiro: recusada na porta, e gritando depois.

O ``_rule_fields`` validava chave, não tipo: ``PATCH {"bought_within_days": "sete"}``
salvava limpo e cada caminho que resolve o público (contagem, disparo, aprovação,
anúncio do evento) estourava ``ValueError`` — 500 sem código. Agora o CRUD recusa
antes de gravar no dialeto dele (``{detail, field, fields}``), e uma linha já
quebrada (escrita por fora) vira ``invalid_audience_rules`` no dialeto de comando
em todos os caminhos, sem receipt nem anúncio pela metade.

Também cobre o 404 do CRUD, que diz "Campanha" ao operador (o identificador
``rules/`` fica).
"""

from __future__ import annotations

import sys

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    MarketingCommandReceipt,
)
from shopman.shop.services import campaign as campaign_service
from shopman.shop.services.marketing_contracts import MarketingContractError

pytestmark = pytest.mark.django_db

User = get_user_model()

RULES_URL = "/api/v1/backstage/marketing/rules/"
COUNT_URL = "/api/v1/backstage/marketing/audience/count/"
APPROVE_URL = "/api/v1/backstage/marketing/announcements/{pk}/approve/"
BROKEN_RULES = {"bought_within_days": "sete"}


@pytest.fixture
def gestor():
    user = User.objects.create_user(username="marketing", password="x", is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(codename__in={
        "view_marketing",
        "edit_marketing_campaigns",
        "preview_marketing_audience",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
        "fire_marketing_campaigns",
    }))
    return user


@pytest.fixture
def template():
    return AnnouncementTemplate.objects.create(name="Fornada", body="Novidades frescas hoje!")


@pytest.fixture
def rule(template):
    return Campaign.objects.create(
        name="Fornada de pães",
        trigger="production_finished",
        template=template,
        platforms=["instagram", "google_business"],
        audience_rules={"favorites": True},
    )


@pytest.fixture
def broken_rule(rule):
    """Linha já gravada por fora do CRUD — o caso que a porta de entrada não alcança."""
    Campaign.objects.filter(pk=rule.pk).update(audience_rules=BROKEN_RULES)
    rule.refresh_from_db()
    return rule


def _patch(client, rule, payload):
    return client.patch(
        f"{RULES_URL}{rule.pk}/", data=payload, content_type="application/json"
    )


class TestCrudRefusesBeforeSaving:
    def test_patch_with_a_non_integer_rule_is_refused_in_the_crud_dialect(
        self, client, gestor, rule
    ):
        client.force_login(gestor)

        response = _patch(client, rule, {"audience_rules": BROKEN_RULES})

        assert response.status_code == 400
        body = response.json()
        assert body["field"] == "audience_rules"
        assert body["fields"] == ["bought_within_days"]
        assert body["detail"]
        rule.refresh_from_db()
        assert rule.audience_rules == {"favorites": True}

    def test_post_with_a_non_integer_rule_names_only_the_offending_keys(
        self, client, gestor, template
    ):
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={
                "name": "Nova",
                "trigger": "production_finished",
                "template_id": template.pk,
                "platforms": ["instagram"],
                "audience_rules": {
                    "vip_first_minutes": "dez",
                    "preferred_hour_window_hours": None,
                },
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "audience_rules"
        assert response.json()["fields"] == ["vip_first_minutes"]
        assert Campaign.objects.filter(name="Nova").count() == 0

    def test_an_integer_rule_still_saves(self, client, gestor, rule):
        client.force_login(gestor)

        response = _patch(client, rule, {"audience_rules": {"bought_within_days": 7}})

        assert response.status_code == 200
        rule.refresh_from_db()
        assert rule.audience_rules["bought_within_days"] == 7


class TestEveryResolvingPathFailsLoud:
    def test_count_answers_422_with_the_named_code(self, client, gestor):
        client.force_login(gestor)

        response = client.post(
            COUNT_URL, {"audience_rules": BROKEN_RULES}, content_type="application/json"
        )

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "invalid_audience_rules"
        assert body["field_errors"] == {"audience_rules": ["bought_within_days"]}
        assert body["detail"]

    def test_fire_answers_422_and_leaves_no_receipt_or_announcement(
        self, client, gestor, broken_rule
    ):
        client.force_login(gestor)

        response = client.post(
            f"{RULES_URL}{broken_rule.pk}/fire/",
            data={"base_version": broken_rule.version},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="fire-broken-rule-0001",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_audience_rules"
        assert MarketingCommandReceipt.objects.count() == 0
        assert Announcement.objects.filter(rule=broken_rule).count() == 0

    def test_approval_answers_422_and_leaves_no_receipt(
        self, client, gestor, broken_rule, template
    ):
        announcement = Announcement.objects.create(
            rule=broken_rule,
            template=template,
            status=AnnouncementStatus.PENDING_REVIEW,
            content={"body": "Fornada pronta", "image_url": "/media/fornada.jpg"},
            platforms=["instagram"],
        )
        client.force_login(gestor)

        response = client.post(
            APPROVE_URL.format(pk=announcement.pk),
            data={"base_version": announcement.version, "publish_mode": "now"},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="approve-broken-rule-0001",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_audience_rules"
        assert MarketingCommandReceipt.objects.count() == 0
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PENDING_REVIEW

    def test_the_event_announcement_names_the_broken_rule(self, broken_rule, monkeypatch):
        with pytest.raises(MarketingContractError) as caught:
            campaign_service.fire_now(broken_rule.pk)

        assert caught.value.code == "invalid_audience_rules"
        assert Announcement.objects.filter(rule=broken_rule).count() == 0

        # O avaliador do evento isola regra quebrada para não calar as outras nem
        # derrubar a fornada; o aviso precisa nomear o contrato, não um ValueError.
        # (O logger `shopman.*` não propaga ao root, então `caplog` não o vê; o
        # espião lê a exceção ativa no instante do aviso.)
        warnings: list[tuple[str, type | None]] = []

        def spy(message, *args, **kwargs):
            warnings.append((message, sys.exc_info()[0]))

        monkeypatch.setattr(campaign_service.logger, "warning", spy)
        created = campaign_service.evaluate("production_finished", {})

        assert created == []
        assert warnings == [("campaign.rule_failed rule=%s trigger=%s", MarketingContractError)]


def test_a_missing_campaign_says_campaign_to_the_operator(client, gestor):
    client.force_login(gestor)

    response = client.get(f"{RULES_URL}999999/")

    assert response.status_code == 404
    assert response.json() == {"detail": "Campanha não encontrada."}
