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
    user.user_permissions.add(Permission.objects.get(codename="manage_campaigns"))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def anuncio(db):
    """Mesma forma do `_post` de `test_api_marketing_surface` — `content`, não `body`."""
    modelo = AnnouncementTemplate.objects.create(name="Fornada", body="{{product_name}} saiu!")
    campanha = Campaign.objects.create(
        name="Fornada", trigger="production_finished", template=modelo,
        platforms=["whatsapp"], audience_rules={"favorites": True},
    )
    return Announcement.objects.create(
        rule=campanha,
        template=modelo,
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Saiu pão", "hashtags": [], "link": "/p/pao"},
        platforms=["whatsapp"],
        audience={"favorites": 3, "alerts": 0, "total": 3},
        trigger_context={"sku": "PAO"},
    )


# ── "Publicar agora" que agendava ────────────────────────────────────────────


@pytest.mark.django_db
def test_agendar_para_o_PASSADO_e_recusado(client, gestor, anuncio):
    """A validação só conferia o FORMATO.

    Data no passado passava e o despacho saía IMEDIATAMENTE — com o toast dizendo
    "Anúncio agendado.". É o espelho exato do "Publicar agora" que agendava: nos dois
    casos o gestor sai da tela acreditando no contrário do que aconteceu.
    """
    client.force_login(gestor)
    ontem = (timezone.now() - timedelta(days=1)).isoformat()

    resposta = client.post(
        reverse("api-backstage-marketing-approve", args=[anuncio.pk]),
        data={"publish_at": ontem},
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert resposta.json()["field"] == "publish_at"
    anuncio.refresh_from_db()
    assert anuncio.status == AnnouncementStatus.PENDING_REVIEW


@pytest.mark.django_db
def test_agendar_para_o_FUTURO_continua_agendando(client, gestor, anuncio):
    """Assert-positivo: a recusa não pode ter comido o agendamento legítimo."""
    client.force_login(gestor)
    amanha = (timezone.now() + timedelta(days=1)).isoformat()

    resposta = client.post(
        reverse("api-backstage-marketing-approve", args=[anuncio.pk]),
        data={"publish_at": amanha},
        content_type="application/json",
    )

    assert resposta.status_code == 200
    assert resposta.json()["scheduled"] is True


@pytest.mark.django_db
def test_a_resposta_diz_se_agendou_para_a_tela_nao_ter_que_adivinhar(client, gestor, anuncio):
    """`scheduled` já existia; a tela é que lia o corpo ENVIADO em vez da resposta.

    Era isso que fazia o toast dizer "publicado" justamente quando a agenda venceu.
    """
    client.force_login(gestor)

    resposta = client.post(
        reverse("api-backstage-marketing-approve", args=[anuncio.pk]),
        data={"publish_now": True},
        content_type="application/json",
    )

    assert resposta.status_code == 200
    assert "scheduled" in resposta.json()
