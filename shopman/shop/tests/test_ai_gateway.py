"""A porta única de IA: rota por propósito, chave cifrada, texto de cliente só liberado."""

from __future__ import annotations

import pytest

from shopman.shop import ai
from shopman.shop.models import AIConnection, Shop
from shopman.shop.secret_box import open_secret, seal_secret
from shopman.shop.tests.ai_support import configure_ai, configure_jev


def _connection(ref, *, key="k-" + "x" * 8, model="m", approved=False, protocol="anthropic", **extra):
    connection = AIConnection(
        ref=ref, name=ref, protocol=protocol, model=model, customer_text_approved=approved, **extra
    )
    connection.set_api_key(key)
    connection.save()
    return connection


def _routes(routes):
    shop = Shop.objects.first() or Shop.objects.create(name="Loja")
    shop.ai_routes = routes
    shop.save()


@pytest.fixture(autouse=True)
def _clean(db):
    AIConnection.objects.all().delete()


def test_secret_is_sealed_and_never_stored_plain():
    token = seal_secret("sk-segredo-1234")
    assert "segredo" not in token
    assert open_secret(token) == "sk-segredo-1234"
    assert open_secret("lixo") == ""


@pytest.mark.django_db
def test_key_is_stored_encrypted_with_last_four():
    connection = _connection("anthropic", key="sk-ant-abcd1234")
    connection.refresh_from_db()
    assert "abcd1234" not in connection.api_key_encrypted
    assert connection.api_key == "sk-ant-abcd1234"
    assert connection.api_key_last4 == "1234"


@pytest.mark.django_db
def test_single_active_connection_serves_every_purpose_without_routes():
    _connection("anthropic", model="claude-opus-5")
    resolved = ai.resolve("copy")
    assert (resolved.ref, resolved.model) == ("anthropic", "claude-opus-5")


@pytest.mark.django_db
def test_route_picks_connection_and_model_per_purpose():
    _connection("anthropic", model="claude-opus-5")
    _connection("deepseek", model="deepseek-flash", base_url="https://api.deepseek.com/anthropic")
    _routes({"default": {"connection": "anthropic"}, "copy": {"connection": "deepseek"}})

    assert ai.resolve("marketing").ref == "anthropic"
    copy = ai.resolve("copy")
    assert (copy.ref, copy.model, copy.base_url) == ("deepseek", "deepseek-flash", "https://api.deepseek.com/anthropic")


@pytest.mark.django_db
def test_two_connections_without_route_is_ambiguous_and_says_so():
    _connection("anthropic")
    _connection("deepseek")
    with pytest.raises(ai.AINotConfigured, match="mais de uma conexão"):
        ai.resolve("copy")


@pytest.mark.django_db
def test_customer_text_needs_an_approved_connection():
    _connection("deepseek", approved=False)
    assert ai.is_configured("copy")
    for purpose in ("concierge", "triage", "intents", "labeling"):
        with pytest.raises(ai.AINotConfigured, match="mensagem de cliente"):
            ai.resolve(purpose)


@pytest.mark.django_db
def test_key_missing_is_not_configured():
    _connection("anthropic", key="")
    assert ai.explain("copy") == "a conexão de IA 'anthropic' está sem chave"


@pytest.mark.django_db
def test_anthropic_client_points_at_the_connection_address():
    configure_ai("sk-deepseek", model="deepseek-flash", base_url="https://api.deepseek.com/anthropic")
    client, model = ai.anthropic_client("copy", timeout=5.0)
    assert model == "deepseek-flash"
    assert str(client.base_url).rstrip("/") == "https://api.deepseek.com/anthropic"
    assert client.api_key == "sk-deepseek"


@pytest.mark.django_db
def test_jev_uses_its_own_connection_never_the_default_route():
    configure_ai("sk-anthropic")
    _routes({"default": {"connection": "anthropic"}})
    with pytest.raises(ai.AINotConfigured):
        ai.jev_endpoint(customer_text=False)
    configure_jev("jev-key", customer_text=False)
    _routes({"default": {"connection": "anthropic"}})
    assert ai.jev_endpoint(customer_text=False) == (ai.JEV_DEFAULT_URL, "jev-key", "jev-latest")
    with pytest.raises(ai.AINotConfigured, match="mensagem de cliente"):
        ai.jev_endpoint(customer_text=True)


def test_prices_are_the_public_table_and_unknown_is_unknown():
    from shopman.shop.services.ai_pricing import model_prices

    assert model_prices("deepseek-flash") == (0.30, 1.20)
    assert model_prices("claude-opus-5") == (5.00, 25.00)
    assert model_prices("desconhecido") is None


# ── O pedido ajustado ao provedor ───────────────────────────────────────────

FULL_REQUEST = {
    "model": "m",
    "max_tokens": 600,
    "system": [{"type": "text", "text": "Sistema.", "cache_control": {"type": "ephemeral"}}],
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "oi", "cache_control": {"type": "ephemeral"}}]}
    ],
    "thinking": {"type": "adaptive"},
    "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": {"type": "object"}}},
}


def test_anthropic_gets_the_request_untouched():
    assert ai.fit_request(FULL_REQUEST, ai.extras_for("")) is FULL_REQUEST
    assert ai.extras_for("https://api.anthropic.com") == ai.EXTRAS


def test_deepseek_keeps_effort_and_thinking_and_gets_the_schema_as_instruction():
    fitted = ai.fit_request(FULL_REQUEST, ai.extras_for("https://api.deepseek.com/anthropic"))
    assert fitted["thinking"] == {"type": "adaptive"}
    assert fitted["output_config"] == {"effort": "low"}
    assert fitted["system"][0] == FULL_REQUEST["system"][0]
    assert "esquema JSON" in fitted["system"][-1]["text"]
    assert '{"type": "object"}' in fitted["system"][-1]["text"]


def test_unknown_provider_gets_only_the_basics():
    fitted = ai.fit_request(FULL_REQUEST, ai.extras_for("https://api.moonshot.ai/anthropic"))
    assert "thinking" not in fitted and "output_config" not in fitted
    assert "cache_control" not in fitted["system"][0]
    assert "cache_control" not in fitted["messages"][0]["content"][0]
    assert "cache_control" in FULL_REQUEST["system"][0], "o pedido original não muda"
    assert (fitted["max_tokens"], fitted["model"]) == (600, "m")


@pytest.mark.django_db
def test_the_gateway_client_fits_every_call(monkeypatch):
    sent = {}

    class _Messages:
        def create(self, **request):
            sent.update(request)
            return "ok"

    class _Client:
        def __init__(self, **kwargs):
            self.messages = _Messages()
            self.base_url = kwargs.get("base_url")

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    configure_ai("k", model="deepseek-flash", base_url="https://api.deepseek.com/anthropic")
    client, model = ai.anthropic_client("copy")
    output = {"format": {"type": "json_schema", "schema": {}}, "effort": "high"}
    assert client.messages.create(model=model, max_tokens=10, messages=[], output_config=output) == "ok"
    assert sent["output_config"] == {"effort": "high"}
    assert client.base_url == "https://api.deepseek.com/anthropic"
