import pytest
from django.contrib.auth import get_user_model
from shopman.cashman.models import Terminal


@pytest.fixture
def operator(db):
    return get_user_model().objects.create_user(username="marina", password="x")


@pytest.fixture
def manager(db):
    return get_user_model().objects.create_user(username="pablo", password="x")


@pytest.fixture
def terminal(db):
    return Terminal.objects.create(ref="pdv-1", label="Balcão")
