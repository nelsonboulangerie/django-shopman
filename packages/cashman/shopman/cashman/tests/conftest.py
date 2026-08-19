import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import services as cash
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


@pytest.fixture
def shift(operator, terminal):
    """Um turno aberto com R$ 100 de fundo de troco: o ponto de partida do balcão."""
    return cash.open_shift(operator=operator, terminal=terminal, float_q=10000)
