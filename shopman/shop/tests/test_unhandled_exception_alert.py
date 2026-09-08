"""Erro 500 vira OperatorAlert — sem PII, sem tempestade, sem derrubar a request.

O ponto de captura é ``got_request_exception`` (ligado no ``ShopmanConfig.ready``),
então estes testes passam por uma request de verdade: o que se prova aqui é o
comportamento na porta, não o de uma função chamada à mão.

O urlconf de teste é este próprio módulo — ``ROOT_URLCONF=__name__`` — para que
a view que explode viva ao lado da asserção que a descreve.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import Client, override_settings
from django.urls import path

from shopman.backstage.models import OperatorAlert
from shopman.shop.services import unhandled_errors

pytestmark = pytest.mark.django_db


# ── urlconf do teste ─────────────────────────────────────────────────────────


def boom(request):
    raise ValueError("total do pedido inválido")


def boom_com_pii(request):
    raise ValueError(
        "falha ao notificar nelson@example.com / 43 99999-8888 / CPF 123.456.789-01 "
        "token sk_test_51NabcDEFghiJKLmnoPQR"
    )


def ok(request):
    return HttpResponse("ok")


urlpatterns = [
    path("api/v1/boom/", boom, name="test-boom"),
    path("api/v1/boom-pii/", boom_com_pii, name="test-boom-pii"),
    path("api/v1/ok/", ok, name="test-ok"),
]


@pytest.fixture(autouse=True)
def _reset_gate():
    unhandled_errors.reset_local_gate()
    yield
    unhandled_errors.reset_local_gate()


@pytest.fixture
def quiet_client():
    """Cliente que NÃO re-levanta: queremos ver a resposta que o cliente vê."""
    return Client(raise_request_exception=False)


# ── 1. a exceção vira alerta, e a resposta não muda ──────────────────────────


@override_settings(ROOT_URLCONF=__name__)
def test_exception_nao_tratada_vira_alerta(quiet_client):
    response = quiet_client.get("/api/v1/boom/")

    assert response.status_code == 500
    alert = OperatorAlert.objects.get(type="unhandled_exception")
    assert alert.severity == "error"
    assert "ValueError" in alert.message
    assert "total do pedido inválido" in alert.message
    # A rota vem do PADRÃO de URL, não do caminho concreto.
    assert "GET /api/v1/boom/" in alert.message
    # O local aponta o arquivo deste teste, que é onde o `raise` mora.
    assert "test_unhandled_exception_alert.py" in alert.message


@override_settings(ROOT_URLCONF=__name__)
def test_request_saudavel_nao_gera_alerta(quiet_client):
    assert quiet_client.get("/api/v1/ok/").status_code == 200
    assert not OperatorAlert.objects.filter(type="unhandled_exception").exists()


@override_settings(ROOT_URLCONF=__name__)
def test_404_nao_gera_alerta(quiet_client):
    assert quiet_client.get("/api/v1/nao-existe/").status_code == 404
    assert not OperatorAlert.objects.filter(type="unhandled_exception").exists()


# ── 1b. zero PII ─────────────────────────────────────────────────────────────


@override_settings(ROOT_URLCONF=__name__)
def test_alerta_nao_carrega_pii(quiet_client):
    quiet_client.get("/api/v1/boom-pii/?token=segredo-do-webhook&phone=43999998888")

    message = OperatorAlert.objects.get(type="unhandled_exception").message
    assert "nelson@example.com" not in message
    assert "[email]" in message
    assert "123.456.789-01" not in message
    assert "[documento]" in message
    assert "99999-8888" not in message
    assert "sk_test_51NabcDEFghiJKLmnoPQR" not in message
    # A query string nunca entra — nem a chave, nem o valor.
    assert "segredo-do-webhook" not in message
    assert "43999998888" not in message


def test_scrub_apaga_o_que_nao_pode_sair():
    scrubbed = unhandled_errors.scrub(
        "cliente ana@padaria.com.br cpf 111.222.333-44 cnpj 12.345.678/0001-90 "
        "fone 43 98888-7777 conta 12345678901234"
    )
    assert "ana@padaria.com.br" not in scrubbed
    assert "111.222.333-44" not in scrubbed
    assert "12.345.678/0001-90" not in scrubbed
    assert "98888-7777" not in scrubbed
    assert "12345678901234" not in scrubbed


def test_scrub_preserva_nome_de_codigo():
    """O corte não pode comer o que faz o aviso ser útil."""
    texto = "MultipleObjectsReturned em shopman/shop/services/pos.py:412"
    assert unhandled_errors.scrub(texto) == texto


def test_sanitize_path_troca_identificador_por_asterisco():
    assert unhandled_errors.sanitize_path("/api/v1/orders/") == "/api/v1/orders/"
    assert unhandled_errors.sanitize_path("/pedido/ORD-20260908-0001/") == "/pedido/*/"
    assert unhandled_errors.sanitize_path("/auth/5543999998888/") == "/auth/*/"
    assert unhandled_errors.sanitize_path("/x/?token=abc") == "/x/"


# ── 2. dedupe: 50 vezes, um alerta ───────────────────────────────────────────


@override_settings(ROOT_URLCONF=__name__)
def test_cinquenta_vezes_a_mesma_excecao_gera_um_alerta(quiet_client):
    for _ in range(50):
        assert quiet_client.get("/api/v1/boom/").status_code == 500

    assert OperatorAlert.objects.filter(type="unhandled_exception").count() == 1


@override_settings(ROOT_URLCONF=__name__)
def test_dedupe_do_banco_segura_processo_sem_memoria(quiet_client):
    """Processo novo (memória vazia) não repete o que o banco já tem.

    O portão de memória é otimização; a garantia é o banco. Esvaziar a memória
    entre as duas chamadas simula outro worker vendo o mesmo bug.
    """
    quiet_client.get("/api/v1/boom/")
    unhandled_errors.reset_local_gate()
    quiet_client.get("/api/v1/boom/")

    assert OperatorAlert.objects.filter(type="unhandled_exception").count() == 1


@override_settings(ROOT_URLCONF=__name__)
def test_alerta_reconhecido_tambem_segura_a_janela(quiet_client):
    quiet_client.get("/api/v1/boom/")
    OperatorAlert.objects.filter(type="unhandled_exception").update(acknowledged=True)
    unhandled_errors.reset_local_gate()

    quiet_client.get("/api/v1/boom/")

    assert OperatorAlert.objects.filter(type="unhandled_exception").count() == 1


@override_settings(ROOT_URLCONF=__name__)
def test_bug_em_outro_lugar_e_fato_novo(quiet_client):
    quiet_client.get("/api/v1/boom/")
    quiet_client.get("/api/v1/boom-pii/")

    assert OperatorAlert.objects.filter(type="unhandled_exception").count() == 2


# ── 3. falhar ao avisar não pode derrubar a request ──────────────────────────


@override_settings(ROOT_URLCONF=__name__)
def test_falha_ao_criar_alerta_deixa_a_excecao_original_prevalecer(monkeypatch):
    """A exceção que chega ao cliente é a do bug, não a do aviso."""

    def explode(*args, **kwargs):
        raise ImproperlyConfigured("o registrador de alerta quebrou")

    monkeypatch.setattr(unhandled_errors, "record_unhandled_exception", explode)

    with pytest.raises(ValueError, match="total do pedido inválido"):
        Client().get("/api/v1/boom/")

    assert not OperatorAlert.objects.filter(type="unhandled_exception").exists()


@override_settings(ROOT_URLCONF=__name__)
def test_falha_ao_criar_alerta_nao_muda_a_resposta(quiet_client, monkeypatch):
    def explode(*args, **kwargs):
        raise ImproperlyConfigured("o registrador de alerta quebrou")

    monkeypatch.setattr(unhandled_errors, "record_unhandled_exception", explode)

    assert quiet_client.get("/api/v1/boom/").status_code == 500


@override_settings(ROOT_URLCONF=__name__)
def test_falha_no_banco_do_alerta_nao_derruba_a_request(quiet_client, monkeypatch):
    """Nem a criação do alerta em si: `create_operator_alert` já engole."""
    from shopman.shop.adapters import alert as alert_adapter

    def explode(*args, **kwargs):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(alert_adapter, "create", explode)

    assert quiet_client.get("/api/v1/boom/").status_code == 500
    assert not OperatorAlert.objects.filter(type="unhandled_exception").exists()
