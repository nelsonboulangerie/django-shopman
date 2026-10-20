"""Cockpit do Marketing: campanha exclusiva de grupo, pela API que a tela usa.

O gestor marca os grupos em ``exclusive_price_tiers`` no CRUD da campanha; o servidor
grava ``campaign:<pk>`` no ``campaign_refs`` da vantagem ``exclusive_notifications`` de
cada grupo (e só ali), devolve a escolha na projeção, conta pela mesma régua do envio
quando a contagem é do disparo e recusa a postagem pública, que não é exclusiva.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from shopman.guestman import ConsentService
from shopman.guestman.models import Customer, PriceTier, PriceTierAdvantage

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    MarketingCommandReceipt,
)
from shopman.shop.services import audience, campaign_exclusivity

pytestmark = pytest.mark.django_db

User = get_user_model()

RULES_URL = "/api/v1/backstage/marketing/rules/"
COUNT_URL = "/api/v1/backstage/marketing/audience/count/"
APPROVE_URL = "/api/v1/backstage/marketing/announcements/{pk}/approve/"


@pytest.fixture
def gestor(client):
    user = User.objects.create_user(username="marketing", password="x", is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(codename__in={
        "view_marketing",
        "edit_marketing_campaigns",
        "preview_marketing_audience",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
    }))
    client.force_login(user)
    return user


@pytest.fixture
def template():
    return AnnouncementTemplate.objects.create(name="Recado", body="Um recado.")


@pytest.fixture
def groups():
    return (
        PriceTier.objects.create(ref="equipe", name="Equipe"),
        PriceTier.objects.create(ref="alianca", name="Aliança Francesa"),
    )


def _create(client, template, **extra):
    payload = {
        "name": "Prévia da Aliança",
        "trigger": "manual",
        "template_id": template.pk,
        "platforms": ["whatsapp"],
        "audience_rules": {},
        **extra,
    }
    return client.post(RULES_URL, data=payload, content_type="application/json")


def test_create_with_groups_writes_the_reference_and_projects_it(client, gestor, template, groups):
    response = _create(client, template, exclusive_price_tiers=["alianca"])

    assert response.status_code == 201, response.json()
    rule = response.json()["rule"]
    assert rule["exclusive_price_tiers"] == ["alianca"]
    advantage = PriceTierAdvantage.objects.get(tier__ref="alianca", kind="exclusive_notifications")
    assert advantage.config["campaign_refs"] == [f"campaign:{rule['pk']}"]

    listed = client.get(RULES_URL).json()["rules"]
    assert [r["exclusive_price_tiers"] for r in listed] == [["alianca"]]


def test_patch_without_the_key_keeps_the_groups_and_with_it_replaces(client, gestor, template, groups):
    pk = _create(client, template, exclusive_price_tiers=["alianca"]).json()["rule"]["pk"]
    rule = Campaign.objects.get(pk=pk)

    kept = client.patch(
        f"{RULES_URL}{pk}/",
        data={"name": "Prévia", "base_updated_at": rule.updated_at.isoformat()},
        content_type="application/json",
    )
    assert kept.status_code == 200, kept.json()
    assert kept.json()["rule"]["exclusive_price_tiers"] == ["alianca"]

    rule.refresh_from_db()
    moved = client.patch(
        f"{RULES_URL}{pk}/",
        data={"exclusive_price_tiers": ["equipe"], "base_updated_at": rule.updated_at.isoformat()},
        content_type="application/json",
    )
    assert moved.status_code == 200, moved.json()
    assert moved.json()["rule"]["exclusive_price_tiers"] == ["equipe"]
    assert campaign_exclusivity.for_campaign(pk).declared == ("equipe",)


def test_public_post_is_refused_for_an_exclusive_campaign(client, gestor, template, groups):
    response = _create(
        client, template, platforms=["whatsapp", "instagram"], exclusive_price_tiers=["alianca"]
    )

    assert response.status_code == 400
    assert response.json()["field"] == "exclusive_price_tiers"
    assert not Campaign.objects.exists()
    assert not PriceTierAdvantage.objects.exists()


def test_unknown_group_is_refused(client, gestor, template, groups):
    response = _create(client, template, exclusive_price_tiers=["sumiu"])

    assert response.status_code == 400
    assert response.json()["field"] == "exclusive_price_tiers"
    assert not Campaign.objects.exists()


def test_deleting_the_campaign_removes_the_reference(client, gestor, template, groups):
    pk = _create(client, template, exclusive_price_tiers=["alianca"]).json()["rule"]["pk"]

    assert client.delete(f"{RULES_URL}{pk}/").status_code == 200
    advantage = PriceTierAdvantage.objects.get(tier__ref="alianca", kind="exclusive_notifications")
    assert advantage.config["campaign_refs"] == []


def test_the_count_of_a_fire_uses_the_campaign_exclusivity(client, gestor, template, groups):
    equipe, alianca = groups
    today = timezone.localdate()
    for ref, phone, tier in (("CLI-A", "+5543999993001", alianca), ("CLI-E", "+5543999993002", equipe)):
        Customer.objects.create(
            ref=ref, first_name="Ana", phone=phone, price_tiers=[tier],
            birthday=today.replace(year=today.year - 30),
        )
        ConsentService.grant_consent(ref, audience.DELIVERY_CONSENT_CHANNEL, source="test")
    pk = _create(client, template, exclusive_price_tiers=["alianca"]).json()["rule"]["pk"]
    rules = {"price_tiers": ["equipe", "alianca"]}

    loose = client.post(COUNT_URL, {"audience_rules": rules}, content_type="application/json")
    fire = client.post(
        COUNT_URL, {"audience_rules": rules, "campaign_id": pk}, content_type="application/json"
    )

    assert loose.json()["total"] == 2
    assert fire.status_code == 200
    assert fire.json()["total"] == 1
    assert fire.json()["excluded_by_reason"]["outside_exclusive_groups"] == 1
    # A ida que o gestor espera a cada clique diz onde foi o tempo.
    assert "projection;dur=" in fire.headers["Server-Timing"]
    assert "db;" in fire.headers["Server-Timing"]

    bad = client.post(
        COUNT_URL, {"audience_rules": rules, "campaign_id": "x"}, content_type="application/json"
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "invalid_campaign"


def test_approval_refuses_a_public_post_when_exclusivity_was_written_later(
    client, gestor, template, groups
):
    """O Gestor ainda aceita ``campaignRefs``: a aprovação fecha a porta que o CRUD não vê."""
    rule = Campaign.objects.create(
        name="Fornada", trigger="manual", template=template, platforms=["instagram"]
    )
    campaign_exclusivity.set_exclusive_tiers(rule.pk, ["alianca"])
    announcement = Announcement.objects.create(
        rule=rule,
        template=template,
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Fornada pronta", "image_url": "/media/fornada.jpg"},
        platforms=["instagram"],
    )

    response = client.post(
        APPROVE_URL.format(pk=announcement.pk),
        data={"base_version": announcement.version, "publish_mode": "now"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="approve-exclusive-public-0001",
    )

    assert response.status_code in (409, 422), response.json()
    assert response.json()["code"] == "exclusive_campaign_public_post"
    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW
    assert MarketingCommandReceipt.objects.filter(state="applied").count() == 0


def test_deleting_the_campaign_hands_the_exclusivity_to_its_pending_announcement(
    client, gestor, template, groups
):
    """Apagar a campanha não transforma o anúncio pendente em envio para todos.

    A FK do anúncio vira nula; antes disso ele herda os grupos, a contagem segue só com
    os membros e a aprovação continua recusando a postagem pública.
    """
    equipe, alianca = groups
    today = timezone.localdate()
    for ref, phone, tier in (("CLI-A9", "+5543999993091", alianca), ("CLI-E9", "+5543999993092", equipe)):
        Customer.objects.create(
            ref=ref, first_name="Ana", phone=phone, price_tiers=[tier],
            birthday=today.replace(year=today.year - 30),
        )
        ConsentService.grant_consent(ref, audience.DELIVERY_CONSENT_CHANNEL, source="test")
    pk = _create(client, template, exclusive_price_tiers=["alianca"]).json()["rule"]["pk"]
    announcement = Announcement.objects.create(
        rule_id=pk,
        template=template,
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Fornada pronta", "image_url": "/media/fornada.jpg"},
        platforms=["instagram"],
        trigger_context={"audience_rules": {"price_tiers": ["equipe", "alianca"]}},
    )

    assert client.delete(f"{RULES_URL}{pk}/").status_code == 200

    announcement.refresh_from_db()
    assert announcement.rule_id is None
    assert announcement.trigger_context["exclusive_price_tiers"] == ["alianca"]
    result = audience.resolve(
        announcement.trigger_context["audience_rules"], announcement=announcement
    )
    assert [r.customer_ref for r in result.all_recipients()] == ["CLI-A9"]
    assert result.excluded_by_reason["outside_exclusive_groups"] == 1

    response = client.post(
        APPROVE_URL.format(pk=announcement.pk),
        data={"base_version": announcement.version, "publish_mode": "now"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="approve-orphan-exclusive-0001",
    )
    assert response.status_code in (409, 422), response.json()
    assert response.json()["code"] == "exclusive_campaign_public_post"
