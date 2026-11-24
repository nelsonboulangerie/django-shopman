"""X8: copy editada no Admin chega à loja em até 60 s, sem deploy (OC-03).

O Admin roda em ``web-operator`` e a API da loja em ``web-storefront``: dois
processos, cada um com o seu memo de copy. Aqui cada "processo" é um
``_ProcessMemo`` próprio, trocado no módulo antes de cada leitura, e o cache do
Django faz o papel do Valkey que os dois enxergam. O que se prova:

- gravar no operador (save, delete, formulário do Admin, ação em lote) faz a loja
  reler no request seguinte;
- a versão só muda depois do commit, para a loja não guardar o texto velho sob a
  versão nova;
- sem o cache compartilhado, o memo da loja vence sozinho em ``LOCAL_MEMO_TTL`` e
  o erro aparece no log; nunca copy eterna;
- a versão é lida uma vez por request, não uma vez por chave.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse

from shopman.shop.models import OmotenashiCopy, Shop
from shopman.shop.omotenashi import copy as copy_module
from shopman.shop.omotenashi.context import AUDIENCE_ANON, MOMENT_MANHA
from shopman.shop.omotenashi.copy import (
    COPY_VERSION_CACHE_KEY,
    LOCAL_MEMO_TTL,
    default_for,
    resolve_copy,
)
from shopman.shop.request_memo import request_memo_scope

pytestmark = pytest.mark.django_db

KEY = "CART_EMPTY"
CHANGELIST = "admin:shop_omotenashicopy_changelist"


@pytest.fixture(autouse=True)
def _cache_limpo():
    cache.delete(COPY_VERSION_CACHE_KEY)
    yield
    cache.delete(COPY_VERSION_CACHE_KEY)
    copy_module._memo.clear()


@pytest.fixture
def operador():
    return copy_module._ProcessMemo()


@pytest.fixture
def loja():
    return copy_module._ProcessMemo()


@contextmanager
def no_processo(memo):
    """Executa o bloco como se fosse o processo dono de ``memo``."""
    anterior = copy_module._memo
    copy_module._memo = memo
    try:
        yield
    finally:
        copy_module._memo = anterior


def _padrao() -> str:
    return default_for(KEY, MOMENT_MANHA, AUDIENCE_ANON).title


def _titulo_na(memo) -> str:
    with no_processo(memo):
        return resolve_copy(KEY, moment=MOMENT_MANHA, audience=AUDIENCE_ANON).title


@pytest.fixture
def admin_client(client):
    # Sem `Shop`, o `OnboardingMiddleware` manda todo o Admin para o cadastro da loja.
    Shop.objects.create(name="Test Shop")
    user = User.objects.create_superuser("admin", "admin@test.com", "pass")
    client.force_login(user)
    return client


def test_salvar_no_operador_faz_a_loja_reler(loja, operador, django_capture_on_commit_callbacks):
    padrao = _padrao()
    assert _titulo_na(loja) == padrao  # a loja guardou o padrão

    with no_processo(operador), django_capture_on_commit_callbacks(execute=True):
        OmotenashiCopy.objects.create(key=KEY, title="Sacola vazia, por enquanto")

    assert _titulo_na(loja) == "Sacola vazia, por enquanto"


def test_sem_versao_nova_a_loja_seguiria_com_o_texto_velho(loja, operador):
    """O contraponto: o que muda a leitura da loja é a versão, não o banco.

    Sem o commit (``on_commit`` não roda), o operador esquece o próprio memo mas a
    versão compartilhada fica como estava, e a loja segue servindo o que guardou.
    É exatamente o defeito T1, e é por isso que a versão existe.
    """
    padrao = _padrao()
    assert _titulo_na(loja) == padrao

    with no_processo(operador):
        OmotenashiCopy.objects.create(key=KEY, title="Ainda não confirmado")

    assert _titulo_na(operador) == "Ainda não confirmado"
    assert _titulo_na(loja) == padrao


def test_a_versao_so_muda_depois_do_commit(loja, operador, django_capture_on_commit_callbacks):
    padrao = _padrao()
    assert _titulo_na(loja) == padrao

    with no_processo(operador), django_capture_on_commit_callbacks(execute=False) as callbacks:
        OmotenashiCopy.objects.create(key=KEY, title="Depois do commit")

    versao_antes = cache.get(COPY_VERSION_CACHE_KEY)
    assert _titulo_na(loja) == padrao

    for callback in callbacks:
        callback()

    assert cache.get(COPY_VERSION_CACHE_KEY) != versao_antes
    assert _titulo_na(loja) == "Depois do commit"


def test_apagar_no_operador_devolve_o_padrao_na_loja(loja, operador, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        row = OmotenashiCopy.objects.create(key=KEY, title="Some daqui a pouco")
    assert _titulo_na(loja) == "Some daqui a pouco"

    with no_processo(operador), django_capture_on_commit_callbacks(execute=True):
        row.delete()

    assert _titulo_na(loja) == _padrao()


def test_formulario_do_admin_chega_a_loja(admin_client, loja, operador, django_capture_on_commit_callbacks):
    assert _titulo_na(loja) == _padrao()

    with no_processo(operador), django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(
            reverse("admin:shop_omotenashicopy_add"),
            {
                "key": KEY,
                "moment": "*",
                "audience": "*",
                "active": "on",
                "title": "Escrito no Admin",
                "message": "",
            },
        )

    assert response.status_code == 302, response.content[:2000]
    assert _titulo_na(loja) == "Escrito no Admin"


def test_acao_em_lote_do_admin_chega_a_loja(admin_client, loja, operador, django_capture_on_commit_callbacks):
    """``reset_to_default`` grava por ``QuerySet.update()``, que não dispara sinal."""
    with django_capture_on_commit_callbacks(execute=True):
        rows = [
            OmotenashiCopy.objects.create(key=KEY, title="Em lote"),
            OmotenashiCopy.objects.create(key=KEY, moment=MOMENT_MANHA, title="Em lote, manhã"),
        ]
    assert _titulo_na(loja) == "Em lote, manhã"

    with no_processo(operador), django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(
            reverse(CHANGELIST),
            {"action": "reset_to_default", "_selected_action": [row.pk for row in rows]},
            follow=True,
        )

    assert response.status_code == 200
    assert not OmotenashiCopy.objects.filter(active=True).exists()
    assert _titulo_na(loja) == _padrao()


class _CacheForaDoAr:
    def get(self, *args, **kwargs):
        raise ConnectionError("valkey fora do ar")

    def set(self, *args, **kwargs):
        raise ConnectionError("valkey fora do ar")


@pytest.fixture
def log_do_modulo(caplog):
    """O logger ``shopman`` não propaga para a raiz (settings.LOGGING): escuta direto nele."""
    caplog.set_level(logging.ERROR, logger=copy_module.logger.name)
    copy_module.logger.addHandler(caplog.handler)
    yield caplog
    copy_module.logger.removeHandler(caplog.handler)


def test_sem_cache_compartilhado_o_memo_vence_no_teto(
    loja, operador, monkeypatch, log_do_modulo, django_capture_on_commit_callbacks
):
    caplog = log_do_modulo
    relogio = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: relogio[0])
    padrao = _padrao()
    assert _titulo_na(loja) == padrao

    monkeypatch.setattr("django.core.cache.cache", _CacheForaDoAr())

    # O operador grava: o save não cai, mas a versão nova não sai, e isso grita.
    with no_processo(operador), django_capture_on_commit_callbacks(execute=True):
        OmotenashiCopy.objects.create(key=KEY, title="Com o Valkey caído")
    assert any("não consegui publicar" in r.getMessage() for r in caplog.records)

    # Dentro do teto, a loja ainda serve o que guardou, e avisa que está cega.
    relogio[0] += LOCAL_MEMO_TTL - 1
    assert _titulo_na(loja) == padrao
    assert any("cache compartilhado ilegível" in r.getMessage() for r in caplog.records)

    # Passado o teto, relê o banco: nunca copy eterna.
    relogio[0] += 1
    assert _titulo_na(loja) == "Com o Valkey caído"


def test_o_teto_vale_mesmo_com_o_cache_no_ar(loja, monkeypatch):
    """Gravação fora do ORM (SQL cru, restauração) não troca a versão; o teto cobre."""
    relogio = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: relogio[0])
    assert _titulo_na(loja) == _padrao()

    OmotenashiCopy.objects.bulk_create([OmotenashiCopy(key=KEY, title="Sem sinal nenhum")])
    assert _titulo_na(loja) == _padrao()

    relogio[0] += LOCAL_MEMO_TTL
    assert _titulo_na(loja) == "Sem sinal nenhum"


def test_a_versao_e_lida_uma_vez_por_request(loja, monkeypatch):
    leituras = []
    original = copy_module._read_shared_version

    def contando():
        leituras.append(1)
        return original()

    monkeypatch.setattr(copy_module, "_read_shared_version", contando)

    with request_memo_scope(), no_processo(loja):
        for _ in range(20):
            resolve_copy(KEY, moment=MOMENT_MANHA, audience=AUDIENCE_ANON)

    assert len(leituras) == 1
