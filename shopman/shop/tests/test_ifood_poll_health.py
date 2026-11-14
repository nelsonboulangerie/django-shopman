"""Sinal de vida do polling do iFood (DEV-2026-017, issue #2325).

Sem webhook, o iFood entra só pelo ``ifood_poll --watch``. O que este arquivo
prende: toda resposta do iFood (200 com lista, 204) grava a hora do poll; falta
de resposta não grava; passados 2 minutos a sonda ``ifood_polling`` reprova e o
``check_ifood_polling`` abre um alerta crítico, que fecha quando o polling volta.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from shopman.orderman import worker_heartbeat
from shopman.watchman.contracts import Status
from shopman.watchman.registry import build_registry
from shopman.watchman.runner import run_profile

from shopman.backstage.models import OperatorAlert
from shopman.shop.services import ifood_events, ifood_poll_health

pytestmark = pytest.mark.django_db

IFOOD = {"client_id": "cid", "client_secret": "secret", "merchant_id": "m-1"}


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _beat_ago(seconds: int) -> None:
    with mock.patch("django.utils.timezone.now", return_value=timezone.now() - timedelta(seconds=seconds)):
        worker_heartbeat.beat(ifood_poll_health.POLL_HEARTBEAT)


def _shared():
    return mock.patch.object(ifood_poll_health, "_shared_cache", return_value=True)


# ── gravação ─────────────────────────────────────────────────────────


@override_settings(SHOPMAN_IFOOD=IFOOD)
@pytest.mark.parametrize("resp", [_Resp(204), _Resp(200, [])])
def test_resposta_do_ifood_grava_a_hora_do_poll(resp):
    with mock.patch.object(ifood_events.ifood_http, "request", return_value=resp):
        ifood_events.poll()

    assert ifood_poll_health.last_success() is not None


@override_settings(SHOPMAN_IFOOD=IFOOD)
@pytest.mark.parametrize("resp", [None, _Resp(500), _Resp(400), _Resp(200)])
def test_sem_resposta_valida_nao_grava(resp):
    with mock.patch.object(ifood_events.ifood_http, "request", return_value=resp):
        assert ifood_events.poll() == []

    assert ifood_poll_health.last_success() is None


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_cache_fora_nao_derruba_o_poll():
    with mock.patch.object(ifood_events.ifood_http, "request", return_value=_Resp(200, [])), \
         mock.patch.object(ifood_poll_health, "record_success", side_effect=RuntimeError("redis")):
        assert ifood_events.poll() == []


# ── estado ───────────────────────────────────────────────────────────


@override_settings(SHOPMAN_IFOOD={})
def test_sem_credencial_o_polling_esta_desligado():
    assert ifood_poll_health.current().state == ifood_poll_health.DISABLED


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_limiar_de_dois_minutos():
    _beat_ago(90)
    assert ifood_poll_health.current().state == ifood_poll_health.FRESH
    _beat_ago(150)
    health = ifood_poll_health.current()
    assert health.state == ifood_poll_health.STALE
    assert health.age_seconds >= 150


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_sem_registro_e_desconhecido_no_cache_por_processo():
    assert ifood_poll_health.current().state == ifood_poll_health.UNKNOWN


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_sem_registro_com_cache_compartilhado_reprova():
    with _shared():
        assert ifood_poll_health.current().state == ifood_poll_health.MISSING


# ── sonda ────────────────────────────────────────────────────────────


def test_a_sonda_esta_registrada_fora_da_prontidao():
    registry = build_registry()

    assert "ifood_polling" in [c.id for c in registry.for_profile("diagnostic")]
    assert [c.id for c in registry.for_profile("ifood")] == ["ifood_polling"]
    assert "ifood_polling" not in [c.id for c in registry.for_profile("readiness")]
    assert "ifood_polling" not in [c.id for c in registry.for_profile("liveness")]


def _probe():
    return next(r for r in run_profile("ifood").results if r.id == "ifood_polling")


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_sonda_passa_com_poll_recente_e_reprova_depois_de_dois_minutos():
    _beat_ago(10)
    assert _probe().status is Status.PASS

    _beat_ago(180)
    result = _probe()
    assert result.status is Status.FAIL
    assert result.evidence["limit_seconds"] == 120
    assert result.evidence["age_seconds"] >= 180


@override_settings(SHOPMAN_IFOOD={})
def test_sonda_pula_sem_integracao():
    assert _probe().status is Status.SKIPPED


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_sonda_reprova_sem_registro_com_cache_compartilhado():
    with _shared():
        assert _probe().status is Status.FAIL


# ── alerta ───────────────────────────────────────────────────────────


def _check():
    with mock.patch("shopman.shop.services.critical_alerts.deliver_now") as page:
        call_command("check_ifood_polling", stdout=StringIO())
    return page


def _open_alerts():
    return OperatorAlert.objects.filter(type="ifood_poll_stale", resolved_at__isnull=True)


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_poll_recente_nao_alerta():
    _beat_ago(30)
    page = _check()
    assert not _open_alerts().exists()
    page.assert_not_called()


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_poll_parado_abre_alerta_critico_e_manda_email():
    _beat_ago(300)
    page = _check()

    alert = _open_alerts().get()
    assert alert.severity == "critical"
    assert "Os pedidos do iFood pararam de entrar no sistema" in alert.message
    assert "há 5 min" in alert.message
    assert "—" not in alert.message
    page.assert_called_once()


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_alerta_nao_repete_na_janela():
    _beat_ago(300)
    _check()
    _check()
    assert _open_alerts().count() == 1


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_polling_que_volta_resolve_o_alerta():
    _beat_ago(300)
    _check()
    _beat_ago(5)
    _check()

    assert not _open_alerts().exists()
    assert OperatorAlert.objects.get(type="ifood_poll_stale").resolved_by == "check_ifood_polling"


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_sem_registro_com_cache_compartilhado_alerta():
    with _shared():
        _check()
    assert "nenhuma leitura do iFood foi registrada" in _open_alerts().get().message


@override_settings(SHOPMAN_IFOOD=IFOOD)
def test_desconhecido_nao_alerta():
    _check()
    assert not OperatorAlert.objects.filter(type="ifood_poll_stale").exists()


@override_settings(SHOPMAN_IFOOD={})
def test_sem_integracao_nao_alerta():
    _beat_ago(3600)
    _check()
    assert not OperatorAlert.objects.filter(type="ifood_poll_stale").exists()
