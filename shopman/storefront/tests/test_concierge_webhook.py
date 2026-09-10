"""Webhook do concierge: auth fechada, chave desligada, e a entrada certa."""

from __future__ import annotations

import json

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from shopman.storefront.concierge import service, webhook

pytestmark = pytest.mark.django_db

KEY = "chave-do-manychat"
CONFIG_ON = {"enabled": True, "api_key": KEY, "handoff_field": "concierge_handoff"}
CONFIG_OFF = {"enabled": False, "api_key": KEY}


@pytest.fixture(autouse=True)
def _anthropic_key(settings):
    """O concierge só atende com a credencial da Anthropic; os testes do webhook a dão."""
    settings.AI_ASSIST_API_KEY = "sk-teste"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def url():
    return reverse("concierge:manychat-conversation")


@pytest.fixture
def intake(monkeypatch):
    """Substitui ``receive_inbound`` e devolve a lista de chamadas."""
    seen: list[dict] = []

    def fake(**kwargs):
        seen.append(kwargs)
        return service.IntakeResult(conversation_id=42, message_id=7, queued=True, reason="queued")

    monkeypatch.setattr(service, "receive_inbound", fake)
    return seen


def _post(client, url, body, **headers):
    return client.post(url, data=json.dumps(body), content_type="application/json", **headers)


def test_url_e_em_ingles_e_nao_colide_com_o_sync_do_guestman(url):
    assert url == "/api/webhooks/manychat/conversation/"


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_chave_errada_da_401(url, intake):
    res = _post(Client(), url, {"subscriber_id": "1", "text": "oi"}, HTTP_X_API_KEY="errada")
    assert res.status_code == 401
    assert intake == []


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_sem_chave_da_401(url, intake):
    res = _post(Client(), url, {"subscriber_id": "1", "text": "oi"})
    assert res.status_code == 401


@override_settings(SHOPMAN_CONCIERGE={"enabled": True, "api_key": ""}, DEBUG=False)
def test_sem_chave_configurada_fora_de_debug_falha_fechado(url, intake):
    res = _post(Client(), url, {"subscriber_id": "1", "text": "oi"}, HTTP_X_API_KEY="qualquer")
    assert res.status_code == 503
    assert "detail" in res.json()
    assert intake == []


@override_settings(SHOPMAN_CONCIERGE=CONFIG_OFF, DEBUG=False)
def test_desligado_responde_200_disabled_sem_quebrar_o_flow(url, intake):
    res = _post(Client(), url, {"subscriber_id": "1", "text": "oi"}, HTTP_X_API_KEY=KEY)
    assert res.status_code == 200
    assert res.json() == {"status": "disabled", "reason": "switch_off"}
    assert intake == []


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, AI_ASSIST_API_KEY="", DEBUG=False)
def test_ligado_sem_chave_da_anthropic_diz_o_motivo(url, intake):
    """"disabled" sem motivo mandou procurar a chave errada; agora o corpo nomeia."""
    res = _post(Client(), url, {"subscriber_id": "1", "text": "oi"}, HTTP_X_API_KEY=KEY)
    assert res.status_code == 200
    assert res.json() == {"status": "disabled", "reason": "ai_key_missing"}
    assert intake == []


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_payload_plano_chama_receive_inbound(url, intake):
    res = _post(
        Client(), url,
        {"subscriber_id": 123, "text": "quero 2 baguetes", "message_id": "m-1",
         "first_name": "Ana", "whatsapp_phone": "+5543999990000"},
        HTTP_AUTHORIZATION=f"Bearer {KEY}",
    )
    assert res.status_code == 202
    assert res.json() == {"status": "queued", "conversation_id": 42, "queued": True}
    assert intake == [{
        "subscriber_id": "123",
        "text": "quero 2 baguetes",
        "external_id": "m-1",
        "profile": {"first_name": "Ana", "whatsapp_phone": "+5543999990000"},
    }]


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_payload_aninhado_chama_receive_inbound(url, intake):
    res = _post(
        Client(), url,
        {"subscriber": {"id": "456", "first_name": "Bia"}, "text": "tem pão de queijo?"},
        HTTP_X_API_KEY=KEY,
    )
    assert res.status_code == 202
    assert intake[0]["subscriber_id"] == "456"
    assert intake[0]["profile"] == {"first_name": "Bia"}
    assert intake[0]["external_id"] == ""


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_texto_ausente_vem_do_getinfo(url, intake, monkeypatch):
    from shopman.guestman.adapters.auth import CustomerResolver

    asked: list[str] = []

    def fake_last_input(self, subscriber_id):
        asked.append(subscriber_id)
        return "  quero um croissant  "

    monkeypatch.setattr(CustomerResolver, "manychat_last_input_text", fake_last_input)
    res = _post(Client(), url, {"manychat_id": "789"}, HTTP_X_API_KEY=KEY)
    assert res.status_code == 202
    assert asked == ["789"]
    assert intake[0]["text"] == "quero um croissant"


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_variavel_nao_renderizada_vem_do_getinfo(url, intake, monkeypatch):
    from shopman.guestman.adapters.auth import CustomerResolver

    monkeypatch.setattr(CustomerResolver, "manychat_last_input_text", lambda self, sid: "de verdade")
    res = _post(Client(), url, {"subscriber_id": "1", "text": "{{last_input_text}}"}, HTTP_X_API_KEY=KEY)
    assert res.status_code == 202
    assert intake[0]["text"] == "de verdade"


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_sem_subscriber_da_400(url, intake):
    res = _post(Client(), url, {"text": "oi"}, HTTP_X_API_KEY=KEY)
    assert res.status_code == 400
    assert res.json()["field"] == "subscriber_id"
    assert intake == []


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_razao_nao_enfileirada_responde_200(url, monkeypatch):
    monkeypatch.setattr(
        service, "receive_inbound",
        lambda **kw: service.IntakeResult(conversation_id=42, message_id=None, queued=False, reason="handoff"),
    )
    res = _post(Client(), url, {"subscriber_id": "1", "text": "oi"}, HTTP_X_API_KEY=KEY)
    assert res.status_code == 200
    assert res.json() == {"status": "handoff", "conversation_id": 42, "queued": False}


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_erro_inesperado_vira_500_com_log(url, monkeypatch):
    logged: list[str] = []
    monkeypatch.setattr(webhook.logger, "exception", lambda msg, *args, **kw: logged.append(msg % args))

    def boom(**kw):
        raise RuntimeError("banco caiu")

    monkeypatch.setattr(service, "receive_inbound", boom)
    res = _post(Client(), url, {"subscriber_id": "1", "text": "oi"}, HTTP_X_API_KEY=KEY)
    assert res.status_code == 500
    assert res.json() == {"detail": "Erro interno"}
    assert any("falha inesperada" in line for line in logged)


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_rate_limit_da_429(url, intake, monkeypatch):
    monkeypatch.setattr(webhook, "is_ratelimited", lambda **kw: True)
    res = _post(Client(), url, {"subscriber_id": "1", "text": "oi"}, HTTP_X_API_KEY=KEY)
    assert res.status_code == 429
    assert intake == []


@override_settings(SHOPMAN_CONCIERGE=CONFIG_ON, DEBUG=False)
def test_get_nao_e_aceito(url):
    res = Client().get(url, HTTP_X_API_KEY=KEY)
    assert res.status_code == 405


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("#c tem croissant hoje?", "tem croissant hoje?"),
        ("#C   quero 2 baguetes", "quero 2 baguetes"),
        ("#concierge oi", "oi"),
        ("#c", ""),
        ("#croissant é bom", "#croissant é bom"),
        ("oi #c", "oi #c"),
    ],
)
def test_a_palavra_chave_do_piloto_sai_do_texto(raw, clean):
    """O "#c" é do gatilho do ManyChat, não da conversa: nunca chega ao modelo."""
    assert webhook.strip_pilot_prefix(raw) == clean
