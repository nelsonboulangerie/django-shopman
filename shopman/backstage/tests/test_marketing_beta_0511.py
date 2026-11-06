"""Beta test de 05/11/2026, frente do Marketing: o que a API precisa recusar na porta."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from shopman.shop.models import AnnouncementTemplate, Campaign

pytestmark = pytest.mark.django_db

User = get_user_model()

RULES_URL = "/api/v1/backstage/marketing/rules/"
TEMPLATES_URL = "/api/v1/backstage/marketing/templates/"


@pytest.fixture
def gestor():
    user = User.objects.create_user(username="marketing-beta", password="x", is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(codename__in={
        "view_marketing",
        "edit_marketing_campaigns",
        "preview_marketing_audience",
        "edit_marketing_templates",
    }))
    return user


@pytest.fixture
def template():
    return AnnouncementTemplate.objects.create(name="Fornada", body="{{product_name}} saiu")


@pytest.fixture
def rule(template):
    return Campaign.objects.create(
        name="Fornada de pães",
        trigger="production_finished",
        template=template,
        platforms=["instagram"],
        audience_rules={"favorites": True},
    )


class TestNameLength:
    """ge:MKT-04: nome com mais de 100 caracteres dava DataError e 500."""

    def test_campaign_patch_with_long_name_is_a_400_on_the_field(self, client, gestor, rule):
        client.force_login(gestor)
        response = client.patch(
            f"{RULES_URL}{rule.pk}/",
            data={"name": "x" * 101},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.json()["field"] == "name"
        assert "100" in response.json()["detail"]
        rule.refresh_from_db()
        assert rule.name == "Fornada de pães"

    def test_campaign_with_exactly_100_characters_saves(self, client, gestor, rule):
        client.force_login(gestor)
        response = client.patch(
            f"{RULES_URL}{rule.pk}/",
            data={"name": "x" * 100},
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_template_post_with_long_name_is_a_400_on_the_field(self, client, gestor):
        client.force_login(gestor)
        response = client.post(
            TEMPLATES_URL,
            data={"name": "y" * 101, "body": "{{product_name}} saiu"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.json()["field"] == "name"
        assert not AnnouncementTemplate.objects.filter(name="y" * 101).exists()


class TestTemplateVariables:
    """ge:MKT-13: variável que não existe era aceita e só falhava na aprovação."""

    def test_unknown_variable_in_body_is_refused(self, client, gestor):
        client.force_login(gestor)
        response = client.post(
            TEMPLATES_URL,
            data={"name": "Teste", "body": "{{product_name}} {{inexistente}}"},
            content_type="application/json",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["field"] == "body"
        assert "{{inexistente}}" in body["detail"]
        assert not AnnouncementTemplate.objects.filter(name="Teste").exists()

    def test_unknown_variable_in_platform_variant_is_refused(self, client, gestor, template):
        client.force_login(gestor)
        response = client.patch(
            f"{TEMPLATES_URL}{template.pk}/",
            data={"platform_variants": {"whatsapp": {"body": "Oi {{nome_errado}}"}}},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.json()["field"] == "platform_variants"

    def test_supported_variables_still_save(self, client, gestor):
        client.force_login(gestor)
        response = client.post(
            TEMPLATES_URL,
            data={
                "name": "Completo",
                "body": "{{ product_name }} por {{price}}. {{availability_phrase}} {{link}}",
            },
            content_type="application/json",
        )
        assert response.status_code in {200, 201}


def test_audience_choices_exclude_empty_serialized_tags_without_deleting_them():
    from shopman.guestman.models import CustomerTag

    from shopman.backstage.projections.marketing import _tag_choices

    for name, slug in [("[]", "empty-list"), ("{}", "empty-object"), (" ", "blank"), ("Sem glúten", "sem-gluten")]:
        CustomerTag.objects.create(name=name, slug=slug)

    assert [(choice.value, choice.label) for choice in _tag_choices()] == [
        ("sem-gluten", "Sem glúten (ninguém)"),
    ]
    assert CustomerTag.objects.filter(slug="empty-list").exists()
