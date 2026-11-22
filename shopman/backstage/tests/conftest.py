import uuid

import pytest
from django.test import override_settings


@pytest.fixture(autouse=True)
def _copy_cache_per_test():
    """Cada teste lê a copy do PRÓPRIO banco.

    A copy da casa (``OmotenashiCopy``) fica num cache do processo, invalidado no
    save/delete, mas não no rollback do fim do teste. Um teste que grava a linha
    (o ``seed`` grava "Hora da Xepa") e lê a copy deixava o cache cheio; o vizinho
    no mesmo worker, já sem a linha no banco, lia o rótulo dela. Era o instável do
    ``test_pos_grade_preco_da_xepa``. A suíte do Storefront já faz o mesmo.
    """
    from shopman.shop.omotenashi.copy import invalidate_cache

    invalidate_cache()
    yield
    invalidate_cache()


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
