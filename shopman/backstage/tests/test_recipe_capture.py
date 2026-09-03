"""Leitura de anotação/foto de receita por IA (``services/recipe_capture.py``).

O provedor é fingido no ``anthropic.Anthropic``: o que se prova aqui é o
contrato em volta dele. A anotação em francês volta em pt-BR com a linha
original preservada; a foto vira o bloco ``image`` certo; cerca de código é
tolerada; JSON ruim, resposta cortada e recusa do provedor viram
``RecipeCaptureError``; sem credencial nada é instanciado.
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from django.test import override_settings

from shopman.backstage.services import recipe_capture
from shopman.backstage.services.recipe_capture import (
    RecipeCaptureError,
    RecipeCaptureNotConfigured,
    read_recipe,
)

FRENCH_NOTE = (
    "Pain de campagne\n"
    "Farine T65 1 kg\n"
    "Eau 700 g\n"
    "Sel 20 g\n"
    "Levain 200 g\n"
    "Pétrir, pointage 2h, façonner, cuire 45 min à 240°C."
)

FRENCH_REPLY = {
    "name": "Pão de campanha",
    "kind": "bread",
    "language": "fr",
    "yield": {"quantity": 2, "unit": "un"},
    "items": [
        {"name": "Farinha de trigo T65", "original_text": "Farine T65 1 kg", "quantity": 1000, "unit": "g", "role": "flour", "note": ""},
        {"name": "Água", "original_text": "Eau 700 g", "quantity": 700, "unit": "g", "role": "liquid", "note": ""},
        {"name": "Sal", "original_text": "Sel 20 g", "quantity": 20, "unit": "g", "role": "salt", "note": ""},
        {"name": "Levain", "original_text": "Levain 200 g", "quantity": 200, "unit": "g", "role": "yeast", "note": ""},
    ],
    "steps": ["Sovar.", "Fermentar 2 h.", "Modelar.", "Assar 45 min a 240 °C."],
    "notes": "",
}


class _FakeAnthropic:
    """Cliente fingido: guarda os kwargs de ``messages.create`` e devolve o que o teste mandou."""

    reply_text = ""
    stop_reason = "end_turn"
    raise_exc: Exception | None = None
    calls: list[dict] = []
    instances = 0

    def __init__(self, api_key):
        assert api_key, "o cliente nunca nasce sem chave"
        type(self).instances += 1
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        type(self).calls.append(kwargs)
        if type(self).raise_exc is not None:
            raise type(self).raise_exc
        return SimpleNamespace(
            stop_reason=type(self).stop_reason,
            content=[SimpleNamespace(type="text", text=type(self).reply_text)],
        )


@pytest.fixture
def provider(monkeypatch):
    """Provedor fingido e credencial configurada. Devolve a classe para o teste ajustar a resposta."""
    _FakeAnthropic.reply_text = json.dumps(FRENCH_REPLY, ensure_ascii=False)
    _FakeAnthropic.stop_reason = "end_turn"
    _FakeAnthropic.raise_exc = None
    _FakeAnthropic.calls = []
    _FakeAnthropic.instances = 0
    monkeypatch.setattr("anthropic.Anthropic", _FakeAnthropic)
    with override_settings(AI_ASSIST_API_KEY="sk-ant-teste", AI_ASSIST_PROVIDER="anthropic", AI_ASSIST_MODEL="claude-opus-5"):
        yield _FakeAnthropic


# ── Anotação ────────────────────────────────────────────────────────────────


def test_a_french_note_comes_back_in_portuguese_with_the_original_line_kept(provider):
    recipe = read_recipe(text=FRENCH_NOTE)

    assert recipe.name == "Pão de campanha"
    assert recipe.kind == "bread"
    assert recipe.language == "fr"
    assert recipe.yield_quantity == Decimal("2")
    assert recipe.yield_unit == "un"
    assert [item.name for item in recipe.items] == ["Farinha de trigo T65", "Água", "Sal", "Levain"]
    assert recipe.items[0].original_text == "Farine T65 1 kg"
    assert recipe.items[0].quantity == Decimal("1000")
    assert isinstance(recipe.items[0].quantity, Decimal)
    assert recipe.items[0].role == "flour"
    assert recipe.steps[0] == "Sovar."
    assert recipe.raw_text == provider.reply_text


def test_the_note_travels_in_the_user_block_under_the_house_system_prompt(provider):
    read_recipe(text=FRENCH_NOTE, language_hint="fr")

    (call,) = provider.calls
    assert call["model"] == "claude-opus-5"
    assert call["max_tokens"] == recipe_capture.MAX_TOKENS
    assert call["system"] == recipe_capture.SYSTEM_PROMPT
    assert "thinking" not in call and "temperature" not in call
    (message,) = call["messages"]
    assert message["role"] == "user"
    blocks = message["content"]
    assert [block["type"] for block in blocks] == ["text"]
    assert "Pain de campagne" in blocks[0]["text"]
    assert "'fr'" in blocks[0]["text"]


def test_the_model_falls_back_to_the_house_default_when_unset(provider):
    with override_settings(AI_ASSIST_MODEL=""):
        read_recipe(text=FRENCH_NOTE)
    assert provider.calls[0]["model"] == recipe_capture.DEFAULT_MODEL


# ── Foto ────────────────────────────────────────────────────────────────────


def test_a_photo_becomes_an_image_block_before_the_instruction(provider):
    read_recipe(image_base64="aGVsbG8=", image_media_type="image/jpeg")

    blocks = provider.calls[0]["messages"][0]["content"]
    assert blocks[0] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": "aGVsbG8="},
    }
    assert blocks[1]["type"] == "text"
    assert "foto" in blocks[1]["text"]


def test_a_data_url_prefix_and_line_breaks_are_stripped_from_the_photo(provider):
    read_recipe(image_base64="data:image/png;base64,aGVs\nbG8=", image_media_type="")

    source = provider.calls[0]["messages"][0]["content"][0]["source"]
    assert source == {"type": "base64", "media_type": "image/png", "data": "aGVsbG8="}


def test_an_unsupported_image_type_is_refused_before_the_provider_is_called(provider):
    with pytest.raises(RecipeCaptureError, match="Formato de imagem"):
        read_recipe(image_base64="aGVsbG8=", image_media_type="image/bmp")
    assert provider.instances == 0


def test_an_oversized_photo_is_refused_before_the_provider_is_called(provider, monkeypatch):
    monkeypatch.setattr(recipe_capture, "MAX_IMAGE_BASE64_BYTES", 10)
    with pytest.raises(RecipeCaptureError, match="grande demais"):
        read_recipe(image_base64="a" * 11, image_media_type="image/jpeg")
    assert provider.instances == 0


def test_nothing_to_read_is_refused_before_the_provider_is_called(provider):
    with pytest.raises(RecipeCaptureError, match="anotação ou uma foto"):
        read_recipe(text="   ")
    assert provider.instances == 0


# ── Resposta ────────────────────────────────────────────────────────────────


def test_a_fenced_reply_is_still_read(provider):
    provider.reply_text = "```json\n" + json.dumps(FRENCH_REPLY, ensure_ascii=False) + "\n```"

    recipe = read_recipe(text=FRENCH_NOTE)

    assert recipe.name == "Pão de campanha"


def test_a_reply_that_is_not_json_is_an_error(provider):
    provider.reply_text = "Claro! Aqui está a receita: farinha, água, sal."

    with pytest.raises(RecipeCaptureError, match="não devolveu JSON"):
        read_recipe(text=FRENCH_NOTE)


def test_a_reply_missing_the_recipe_name_is_an_error(provider):
    provider.reply_text = json.dumps({**FRENCH_REPLY, "name": ""})

    with pytest.raises(RecipeCaptureError, match="'name'"):
        read_recipe(text=FRENCH_NOTE)


def test_a_reply_cut_at_the_token_ceiling_is_an_error_not_half_a_recipe(provider):
    provider.stop_reason = "max_tokens"
    provider.reply_text = '{"name": "Pão de cam'

    with pytest.raises(RecipeCaptureError, match=f"limite de {recipe_capture.MAX_TOKENS} tokens"):
        read_recipe(text=FRENCH_NOTE)


def test_a_refusal_is_an_error(provider):
    provider.stop_reason = "refusal"
    provider.reply_text = ""

    with pytest.raises(RecipeCaptureError, match="recusou"):
        read_recipe(text=FRENCH_NOTE)


def test_an_unknown_role_falls_back_to_other_with_a_note(provider):
    reply = json.loads(json.dumps(FRENCH_REPLY))
    reply["items"][1]["role"] = "hidratante"
    provider.reply_text = json.dumps(reply, ensure_ascii=False)

    recipe = read_recipe(text=FRENCH_NOTE)

    assert recipe.items[1].role == "other"
    assert "hidratante" in recipe.items[1].note
    assert recipe.items[0].role == "flour", "o que estava certo não muda"


def test_an_unknown_unit_and_kind_fall_back_without_exploding(provider):
    reply = json.loads(json.dumps(FRENCH_REPLY))
    reply["kind"] = "boulange"
    reply["items"][2]["unit"] = "pitada"
    reply["items"][2]["quantity"] = None
    reply["items"][3]["unit"] = "litros"
    reply["items"][3]["quantity"] = "0,2"
    provider.reply_text = json.dumps(reply, ensure_ascii=False)

    recipe = read_recipe(text=FRENCH_NOTE)

    assert recipe.kind == "other"
    assert recipe.items[2].unit == "g"
    assert recipe.items[2].quantity is None
    assert "pitada" in recipe.items[2].note
    assert recipe.items[3].unit == "L", "apelido conhecido é grafia, não erro"
    assert recipe.items[3].quantity == Decimal("0.2"), "vírgula decimal é lida"
    assert recipe.items[3].note == ""


def test_a_bogus_language_code_is_dropped_not_kept(provider):
    provider.reply_text = json.dumps({**FRENCH_REPLY, "language": "francês"})

    assert read_recipe(text=FRENCH_NOTE).language == ""


def test_an_empty_reply_is_an_error(provider):
    provider.reply_text = "   "

    with pytest.raises(RecipeCaptureError, match="vazia"):
        read_recipe(text=FRENCH_NOTE)


# ── Configuração e provedor ─────────────────────────────────────────────────


def test_without_a_key_it_is_configuration_not_failure_and_no_client_is_built(provider):
    with override_settings(AI_ASSIST_API_KEY=""):
        assert recipe_capture.is_configured() is False
        with pytest.raises(RecipeCaptureNotConfigured):
            read_recipe(text=FRENCH_NOTE)
    assert provider.instances == 0


def test_with_a_key_it_is_configured(provider):
    assert recipe_capture.is_configured() is True


def test_an_unknown_provider_is_refused(provider):
    with override_settings(AI_ASSIST_PROVIDER="papagaio"):
        with pytest.raises(RecipeCaptureError, match="papagaio"):
            read_recipe(text=FRENCH_NOTE)


def test_a_rate_limit_from_the_sdk_becomes_a_short_message(provider, monkeypatch):
    import anthropic

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    provider.raise_exc = anthropic.RateLimitError(
        "rate limited", response=httpx.Response(429, request=request), body=None,
    )
    # O logger da casa não propaga para a raiz; captura-se na fonte.
    logged: list[str] = []
    monkeypatch.setattr(
        recipe_capture.logger, "warning", lambda msg, *args, **kw: logged.append(msg % args),
    )

    with pytest.raises(RecipeCaptureError, match="ocupado"):
        read_recipe(text=FRENCH_NOTE)

    (line,) = logged
    assert "RateLimitError" in line and "429" in line
    assert "sk-ant-teste" not in line, "a chave nunca vai para o log"


def test_a_connection_error_from_the_sdk_becomes_a_short_message(provider):
    import anthropic

    provider.raise_exc = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )

    with pytest.raises(RecipeCaptureError, match="Não foi possível falar"):
        read_recipe(text=FRENCH_NOTE)


def test_the_errors_speak_the_backstage_dialect():
    """A API já mapeia ``AiAssistNotConfigured`` para 503 e ``AiAssistError`` para 502."""
    from shopman.backstage.services.exceptions import AiAssistError, AiAssistNotConfigured

    assert issubclass(RecipeCaptureNotConfigured, AiAssistNotConfigured)
    assert issubclass(RecipeCaptureError, AiAssistError)
