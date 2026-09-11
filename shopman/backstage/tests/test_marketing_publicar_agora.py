"""Marketing: a agenda que mentia sobre o que aconteceu com o anúncio.

Achados do WP-08 que moram nesta superfície. O fio comum é **o gestor não saber o que
aconteceu**: aprovar sem data não publicava, agendar para trás publicava na hora, e o
toast dizia o contrário do que o servidor fez.

Os outros dois achados do WP-08 não moram aqui e são provados onde acontecem:
o link de acesso pessoal que virava campo no perfil do ManyChat, em
`shopman/shop/tests/test_manychat_flow_variables.py`; a onda que não chegava a quem
devia, em `shopman/shop/tests/test_campaign_handlers.py`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    Shop,
)


@pytest.fixture
def gestor(db):
    Shop.objects.create(name="Nelson")
    user = User.objects.create_user("gestor-mkt", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="view_marketing"),
        Permission.objects.get(codename="approve_marketing_announcements"),
        Permission.objects.get(codename="publish_marketing_announcements"),
    )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def anuncio(db):
    """Mesma forma do `_post` de `test_api_marketing_surface` — `content`, não `body`."""
    modelo = AnnouncementTemplate.objects.create(name="Fornada", body="{{product_name}} saiu!")
    campanha = Campaign.objects.create(
        name="Fornada", trigger="production_finished", template=modelo,
        platforms=["instagram"], audience_rules={"favorites": True},
    )
    return Announcement.objects.create(
        rule=campanha,
        template=modelo,
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Saiu pão", "hashtags": [], "link": "/produto/pao"},
        platforms=["instagram"],
        audience={"favorites": 3, "alerts": 0, "total": 3},
        trigger_context={"sku": "PAO"},
    )


# ── "Publicar agora" que agendava ────────────────────────────────────────────


def _confirmed_approval(client, announcement, payload, *, key: str):
    """Use o protocolo atual sem fabricar o desafio no teste."""

    url = reverse("api-backstage-marketing-approve", args=[announcement.pk])
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
        assert confirmation["step_up"] == "password"
        stepped = client.post(
            "/api/v1/backstage/marketing/security/step-up/",
            data={"method": "password", "credential": "pw"},
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


@pytest.mark.django_db
def test_agendar_para_o_PASSADO_e_recusado(client, gestor, anuncio):
    """A validação só conferia o FORMATO.

    Data no passado passava e o despacho saía IMEDIATAMENTE — com o toast dizendo
    "Anúncio agendado.". É o espelho exato do "Publicar agora" que agendava: nos dois
    casos o gestor sai da tela acreditando no contrário do que aconteceu.
    """
    client.force_login(gestor)
    ontem = timezone.localtime(timezone.now() - timedelta(days=1)).isoformat()

    resposta = _confirmed_approval(
        client,
        anuncio,
        {
            "base_version": 1,
            "publish_mode": "scheduled",
            "publish_at": ontem,
            "publish_timezone": "America/Sao_Paulo",
        },
        key="schedule-past-contract-0001",
    )

    assert resposta.status_code == 422
    assert "publish_at" in resposta.json()["field_errors"]
    anuncio.refresh_from_db()
    assert anuncio.status == AnnouncementStatus.PENDING_REVIEW


@pytest.mark.django_db
def test_agendar_para_o_FUTURO_continua_agendando(client, gestor, anuncio):
    """Assert-positivo: a recusa não pode ter comido o agendamento legítimo."""
    client.force_login(gestor)
    amanha = timezone.localtime(timezone.now() + timedelta(days=1)).isoformat()

    resposta = _confirmed_approval(
        client,
        anuncio,
        {
            "base_version": 1,
            "publish_mode": "scheduled",
            "publish_at": amanha,
            "publish_timezone": "America/Sao_Paulo",
        },
        key="schedule-future-contract-0001",
    )

    assert resposta.status_code == 200
    assert resposta.json()["scheduled"] is True


@pytest.mark.django_db
def test_a_resposta_diz_se_agendou_para_a_tela_nao_ter_que_adivinhar(client, gestor, anuncio):
    """`scheduled` já existia; a tela é que lia o corpo ENVIADO em vez da resposta.

    Era isso que fazia o toast dizer "publicado" justamente quando a agenda venceu.
    """
    client.force_login(gestor)

    resposta = _confirmed_approval(
        client,
        anuncio,
        {
            "base_version": 1,
            "publish_mode": "now",
            "publish_timezone": "America/Sao_Paulo",
        },
        key="publish-now-contract-0001",
    )

    assert resposta.status_code == 200
    assert "scheduled" in resposta.json()
