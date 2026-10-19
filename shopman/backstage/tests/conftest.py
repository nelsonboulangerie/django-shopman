import uuid

import pytest
from django.test import override_settings


@pytest.fixture(autouse=True)
def _ratelimit_counters_per_test():
    """Cada teste conta as próprias tentativas no rate-limit.

    O cache dos testes é um só (LocMem) e todo cliente de teste fala do mesmo IP:
    sem isto, o freio do ``operator/unlock`` (5/min por operador, 30/min por IP)
    somava os destraves de testes VIZINHOS dentro do mesmo minuto e devolvia 429
    a quem nunca tentou nada. Um prefixo por teste isola os contadores sem
    desligar o rate-limit nem limpar o resto do cache.
    """
    with override_settings(RATELIMIT_CACHE_PREFIX=f"rl:{uuid.uuid4().hex}:"):
        yield
