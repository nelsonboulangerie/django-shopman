"""POST /api/v1/backstage/operator/capacity/ — amostra do contêiner + limites do Admin.

Quem chama é o BFF da layer ``operator-kit`` (rota ``/health/capacity``), com o
cookie do operador. A mesma chamada autentica, devolve os limites e anda a regra.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Shop

URL_NAME = "api-backstage-operator-capacity"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def staff(db):
    return User.objects.create_user("capacidade-staff", password="pw", is_staff=True)


def _post(client, body):
    return client.post(reverse(URL_NAME), body, content_type="application/json")


SAMPLE = {"service": "operator-floor", "available": True, "memory_percent": 62.0, "cpu_percent": 18.0}


@pytest.mark.django_db
def test_anonymous_is_refused_with_the_session_code(client):
    response = _post(client, SAMPLE)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.django_db
def test_non_staff_is_refused(client):
    client.force_login(User.objects.create_user("cliente", password="pw", is_staff=False))

    response = _post(client, SAMPLE)

    assert response.status_code == 403
    assert "error" not in response.json()


@pytest.mark.django_db
def test_operator_gets_default_thresholds_and_the_level(client, staff):
    client.force_login(staff)

    response = _post(client, SAMPLE)

    assert response.status_code == 200
    assert response.json() == {
        "service": "operator-floor",
        "level": "normal",
        "recorded": True,
        "thresholds": {"attention_percent": 75, "critical_percent": 90, "sustain_minutes": 5},
    }


@pytest.mark.django_db
def test_admin_values_come_back_to_the_app(client, staff):
    Shop.objects.create(
        name="Loja",
        defaults={"operator_capacity": {"attention_percent": 60, "critical_percent": 70, "sustain_minutes": 2}},
    )
    cache.clear()
    client.force_login(staff)

    body = _post(client, {**SAMPLE, "memory_percent": 65.0}).json()

    assert body["thresholds"] == {"attention_percent": 60, "critical_percent": 70, "sustain_minutes": 2}
    assert body["level"] == "attention"


@pytest.mark.django_db
def test_unavailable_reading_answers_without_recording(client, staff):
    client.force_login(staff)

    body = _post(client, {"service": "pos", "available": False, "memory_percent": None, "cpu_percent": None}).json()

    assert body["level"] == "unknown"
    assert body["recorded"] is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"service": "operator-floor"},
        {**SAMPLE, "memory_percent": 140},
        {**SAMPLE, "service": "Não é slug"},
    ],
)
def test_payload_outside_the_contract_is_400(client, staff, body):
    client.force_login(staff)

    response = _post(client, body)

    assert response.status_code == 400
    assert response.json()["detail"]
    assert not OperatorAlert.objects.exists()


@pytest.mark.django_db
def test_sustained_critical_through_the_api_creates_the_alert(client, staff, monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    from shopman.shop.services import operator_capacity

    client.force_login(staff)
    base = timezone.now()

    class _Clock:
        current = base

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(operator_capacity, "timezone", _Clock)

    for index in range(9):
        _Clock.current = base + timedelta(seconds=45 * index)
        response = _post(client, {**SAMPLE, "memory_percent": 94.0})
        assert response.status_code == 200
        assert response.json()["level"] == "critical"

    alert = OperatorAlert.objects.get(type="operator_capacity_critical")
    assert alert.severity == "critical"
    assert "memória 94%" in alert.message
