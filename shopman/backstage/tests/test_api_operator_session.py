"""A antessala: quem sou eu, quem pode entrar, entrar e sair.

``operator/session|eligible|unlock|lock`` do ponto de vista do balcão travado —
que é o estado em que a loja amanhece. Não há ninguém logado ali: o aparelho é
reconhecido por confiança de dispositivo, e é ISSO que faz a tela de
identificação aparecer.

⚠️ Estes testes tinham uma fixture ``device``: um usuário staff logado que
representava a máquina. Ela morreu com a D1 Parte B, e não por arrumação — era
ela o buraco. Um aparelho com sessão Django é um aparelho com permissões, e no
staging essa sessão era o ``admin`` superusuário.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.doorman.models import PinCredential

from shopman.backstage.models import DayClosing
from shopman.backstage.tests.support import trust_station

User = get_user_model()


def _grant(user, codename, app="backstage"):
    user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def balcao(client):
    """O aparelho do balcão: reconhecido, e sem ninguém identificado nele."""
    return trust_station(client, "balcao")


@pytest.fixture
def baker(db):
    user = User.objects.create_user("bia", password="x", is_staff=True, first_name="Bia")
    PinCredential.set_for(user, "4321")
    return _grant(user, "operate_production")


@pytest.fixture
def operate_production_perm(db):
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_production",
    )


# ── Session / eligible ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_session_reports_locked_then_operator(client, balcao, baker):
    body = client.get(reverse("api-backstage-operator-session")).json()
    assert body["locked"] is True and body["operator"] is None
    # A tela travada precisa saber DE QUE BALCÃO ela é — não com que conta a
    # máquina entrou, porque não há conta de máquina.
    assert body["station"] == balcao
    client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "4321", "perm": "backstage.operate_production"},
        content_type="application/json",
    )
    body = client.get(reverse("api-backstage-operator-session")).json()
    assert body["locked"] is False
    assert body["operator"]["username"] == "bia"
    # E a estação continua a mesma: quem entrou foi uma pessoa, não o aparelho.
    assert body["station"] == balcao


@pytest.mark.django_db
def test_eligible_filters_by_perm_and_validates(client, balcao, baker):
    ok = client.get(reverse("api-backstage-operator-eligible"), {"perm": "backstage.operate_production"})
    assert ok.status_code == 200
    assert any(o["username"] == "bia" for o in ok.json()["operators"])
    # an operator without operate_pos must not appear in the POS picker
    pos = client.get(reverse("api-backstage-operator-eligible"), {"perm": "cashman.operate_pos"})
    assert all(o["username"] != "bia" for o in pos.json()["operators"])
    # unknown perm rejected
    assert client.get(reverse("api-backstage-operator-eligible"), {"perm": "evil"}).status_code == 400


@pytest.mark.django_db
def test_a_antessala_nao_atende_aparelho_de_fora(client, baker):
    """Sem confiança de estação, nem a lista de quem destrava sai.

    É o outro lado da chave da antessala: ela abre pouca coisa, mas quem não a
    tem não abre nem essa pouca. Senão o seletor de operadores da loja — nomes de
    quem trabalha ali — responderia para o navegador de qualquer um.
    """
    assert client.get(reverse("api-backstage-operator-eligible")).status_code == 403
    assert client.get(reverse("api-backstage-operator-session")).status_code == 403
    assert client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "4321"},
        content_type="application/json",
    ).status_code == 403


# ── Unlock by PIN / badge ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_unlock_wrong_pin_and_missing_perm(client, balcao, baker):
    bad = client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "0000"},
        content_type="application/json",
    )
    assert bad.status_code == 403
    # right pin but demanding a perm the operator lacks → rejected
    nope = client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "4321", "perm": "cashman.operate_pos"},
        content_type="application/json",
    )
    assert nope.status_code == 403


@pytest.mark.django_db
def test_unlock_by_badge(client, balcao, baker):
    token = PinCredential.issue_badge(baker)
    ok = client.post(
        reverse("api-backstage-operator-unlock"),
        {"badge": token, "perm": "backstage.operate_production"},
        content_type="application/json",
    )
    assert ok.status_code == 200
    assert ok.json()["operator"]["username"] == "bia"


# ── O ciclo do dia: destravar → agir → travar ────────────────────────────────


@pytest.mark.django_db
def test_unlock_enables_action_lock_blocks_it(client, balcao, baker, operate_production_perm):
    board = reverse("api-backstage-production")

    # a estação sozinha → travada
    assert client.get(board).status_code == 403

    # unlock the baker (has operate_production) → action passes
    client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "4321", "perm": "backstage.operate_production"},
        content_type="application/json",
    )
    assert client.get(board).status_code == 200

    # lock → blocked again
    client.post(reverse("api-backstage-operator-lock"))
    assert client.get(board).status_code == 403


@pytest.mark.django_db
def test_travar_derruba_a_pessoa_e_NAO_a_estacao(client, balcao, baker):
    """Travar é sair, não desprovisionar.

    Se a trava levasse a estação junto, o balcão sairia do ar ao fim de cada
    turno e alguém teria de reprovisionar de manhã com senha de gestor. O cookie
    de confiança não mora na sessão exatamente para sobreviver a isto.
    """
    client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": baker.pk, "pin": "4321", "perm": "backstage.operate_production"},
        content_type="application/json",
    )
    client.post(reverse("api-backstage-operator-lock"))

    body = client.get(reverse("api-backstage-operator-session")).json()
    assert body["locked"] is True and body["operator"] is None
    assert body["station"] == balcao
