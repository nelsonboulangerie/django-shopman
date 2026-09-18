"""Etiquetas de timer — model, dedupe da criação pelo fournil e permissão.

O que estes testes protegem, em uma frase cada:

· o nome comparável é o MESMO dos dois lados (aqui e em presentation/timers.ts);
· criar "pausa cafe" quando já existe "Pausa-café" devolve a que existe, e a
  devolve INTACTA — o tempo digitado no turno não reescreve o padrão da casa;
· o banco recusa duas ativas com o mesmo nome mesmo por caminho programático;
· desativar libera o nome;
· quem não pode abrir o quadro de produção não lê nem cria etiqueta.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse

from shopman.backstage.models import TimerTag, TimerTagOrigin
from shopman.backstage.models.timer_tag import normalize_tag_label
from shopman.backstage.tests.production_grants import grant_production_operator

URL_NAME = "api-backstage-production-timer-tags"


@pytest.fixture
def timer_operator(db):
    user = User.objects.create_user("timer-op", password="pw", is_staff=True)
    return grant_production_operator(user)


@pytest.fixture
def estufa(db):
    return TimerTag.objects.create(ref="estufa", label="Estufa", minutes=60, position=10)


# ── Nome comparável ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Pausa-café", "pausa cafe"),
        ("  PAUSA   CAFÉ  ", "pausa cafe"),
        ("pausa cafe", "pausa cafe"),
        ("Estufa", "estufa"),
        ("Descanso 2ª volta", "descanso 2 volta"),
        ("   ", ""),
        ("---", ""),
    ],
)
def test_normalize_tag_label_folds_case_accent_and_punctuation(raw, expected):
    assert normalize_tag_label(raw) == expected


@pytest.mark.django_db
def test_saving_keeps_the_comparable_twin_in_sync(estufa):
    assert estufa.normalized_label == "estufa"
    estufa.label = "Estufa alta"
    estufa.save()
    estufa.refresh_from_db()
    assert estufa.normalized_label == "estufa alta"


@pytest.mark.django_db
def test_update_or_create_also_refreshes_the_twin(estufa):
    """O caminho do seed salva com ``update_fields``; o gêmeo vai junto."""
    TimerTag.objects.update_or_create(
        ref="estufa", defaults={"label": "Câmara", "minutes": 90}
    )
    assert TimerTag.objects.get(ref="estufa").normalized_label == "camara"


# ── Unique parcial sobre as ativas ─────────────────────────────────────────


@pytest.mark.django_db
def test_two_active_tags_cannot_share_a_name(estufa):
    with pytest.raises(IntegrityError), transaction.atomic():
        TimerTag.objects.create(ref="estufa-2", label="  estufa ", minutes=30)


@pytest.mark.django_db
def test_deactivating_frees_the_name(estufa):
    estufa.is_active = False
    estufa.save()
    livre = TimerTag.objects.create(ref="estufa-2", label="Estufa", minutes=30)
    assert livre.pk != estufa.pk


# ── Dedupe da criação pelo fournil ─────────────────────────────────────────


@pytest.mark.django_db
def test_operator_creation_returns_the_existing_equivalent_untouched(estufa):
    tag, created = TimerTag.objects.create_from_operator(label="  ESTUFA  ", minutes=5)

    assert created is False
    assert tag.pk == estufa.pk
    # O tempo digitado no turno NÃO reescreve o padrão combinado da casa.
    assert tag.minutes == 60
    assert TimerTag.objects.count() == 1


@pytest.mark.django_db
def test_operator_creation_marks_the_origin_and_goes_to_the_end_of_the_row(estufa):
    tag, created = TimerTag.objects.create_from_operator(label="Banho-maria", minutes=25)

    assert created is True
    assert tag.origin == TimerTagOrigin.OPERATOR
    assert tag.ref == "banho-maria"
    assert tag.position > estufa.position
    assert tag.is_active is True


@pytest.mark.django_db
def test_operator_creation_never_reuses_an_inactive_name(estufa):
    estufa.is_active = False
    estufa.save()

    tag, created = TimerTag.objects.create_from_operator(label="Estufa", minutes=45)

    assert created is True
    assert tag.pk != estufa.pk
    assert tag.minutes == 45


@pytest.mark.django_db
def test_ref_collision_gets_a_suffix(estufa):
    estufa.is_active = False
    estufa.save()

    tag, _ = TimerTag.objects.create_from_operator(label="Estufa", minutes=45)

    assert tag.ref == "estufa-2"


# ── API ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_get_lists_only_active_tags_in_display_order(client, timer_operator):
    TimerTag.objects.create(ref="descanso", label="Descanso", minutes=20, position=20)
    TimerTag.objects.create(ref="estufa", label="Estufa", minutes=60, position=10)
    TimerTag.objects.create(
        ref="antiga", label="Antiga", minutes=10, position=5, is_active=False
    )
    client.force_login(timer_operator)

    response = client.get(reverse(URL_NAME))

    assert response.status_code == 200
    assert [tag["label"] for tag in response.json()["tags"]] == ["Estufa", "Descanso"]
    assert response.json()["tags"][0] == {
        "ref": "estufa",
        "label": "Estufa",
        "minutes": 60,
        "origin": "admin",
    }


@pytest.mark.django_db
def test_post_creates_a_tag_from_the_shop_floor(client, timer_operator):
    client.force_login(timer_operator)

    response = client.post(
        reverse(URL_NAME),
        data={"label": "Banho-maria", "minutes": 25},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["tag"]["label"] == "Banho-maria"
    assert body["tag"]["origin"] == "operator"


@pytest.mark.django_db
def test_post_deduplicates_and_says_it_did_not_create(client, timer_operator, estufa):
    client.force_login(timer_operator)

    response = client.post(
        reverse(URL_NAME),
        data={"label": "pausa", "minutes": 15},
        content_type="application/json",
    )
    assert response.status_code == 201

    again = client.post(
        reverse(URL_NAME),
        data={"label": "PAUSA", "minutes": 30},
        content_type="application/json",
    )

    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["tag"]["minutes"] == 15
    assert TimerTag.objects.filter(normalized_label="pausa").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"label": "   ", "minutes": 10},
        {"label": "---", "minutes": 10},
        {"label": "Estufa", "minutes": 0},
        {"label": "Estufa", "minutes": 1000},
    ],
)
def test_post_rejects_junk_in_the_canonical_error_dialect(client, timer_operator, payload):
    client.force_login(timer_operator)

    response = client.post(
        reverse(URL_NAME), data=payload, content_type="application/json"
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]
    assert body["field"] in {"label", "minutes"}
    assert body["errors"]


# ── Permissão ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_reading_requires_the_production_surface(client):
    bare = User.objects.create_user("bare-timer", password="pw", is_staff=True)
    client.force_login(bare)

    assert client.get(reverse(URL_NAME)).status_code == 403


@pytest.mark.django_db
def test_creating_requires_the_production_surface(client):
    bare = User.objects.create_user("bare-timer-post", password="pw", is_staff=True)
    client.force_login(bare)

    response = client.post(
        reverse(URL_NAME),
        data={"label": "Estufa", "minutes": 30},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["capability"] == "can_access_board"
    assert TimerTag.objects.count() == 0


@pytest.mark.django_db
def test_anonymous_is_refused(client):
    assert client.get(reverse(URL_NAME)).status_code in (401, 403)
