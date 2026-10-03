"""A régua da Concierge (OBS0310-K): custo e tempo por resposta, e o golden set.

Fatia 1 do ``docs/plans/CONCIERGE-ARQUITETURA-ALVO.md``. O cliente não vê nada
mudar; o turno grava em ``ConversationMessage.usage`` do primeiro bloco da
resposta quem respondeu, os tokens por (etapa, modelo) com a escrita de cache, o
custo estimado e o tempo de ponta a ponta e por etapa.
"""

from __future__ import annotations

import io
import json
import re
from types import SimpleNamespace

import pytest
from django.core.management import call_command

from shopman.shop.models import ConversationMessage
from shopman.shop.services.ai_pricing import usage_cost
from shopman.storefront.concierge import metrics, reply_eval, service
from shopman.storefront.tests import test_concierge_engine as engine
from shopman.storefront.tests.test_concierge_engine import ScriptedClient, _binding, _receive, _response, _text, _tool

surface = engine.surface
customer = engine.customer
conversation = engine.conversation
outbox = engine.outbox

pytestmark = pytest.mark.django_db


class UsageClient:
    """Cliente da triagem que devolve JSON e um ``usage`` com escrita de cache."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
            usage=SimpleNamespace(
                input_tokens=300, output_tokens=40, cache_read_input_tokens=0, cache_creation_input_tokens=0
            ),
        )


def _first_reply(conversation) -> ConversationMessage:
    return ConversationMessage.objects.filter(conversation=conversation, kind="reply").order_by("id").first()


# ── Preço ────────────────────────────────────────────────────────────


def test_cost_counts_cache_read_at_a_tenth_and_cache_write_at_one_and_a_quarter():
    cost = usage_cost(
        "claude-sonnet-5",
        {
            "input_tokens": 1_000_000,
            "output_tokens": 100_000,
            "cache_read_input_tokens": 1_000_000,
            "cache_creation_input_tokens": 1_000_000,
        },
    )
    assert cost == pytest.approx(2.00 + 1.00 + 0.20 + 2.50)


def test_unknown_model_has_unknown_cost_not_zero():
    assert usage_cost("modelo-inventado", {"input_tokens": 10}) is None


# ── O turno grava a régua ────────────────────────────────────────────


def test_agent_turn_records_tokens_cost_and_latency_on_the_first_reply_block(conversation, outbox):
    _receive(conversation, "tem pão francês?", "m1")
    client = ScriptedClient(
        _response(_tool("search_storefront", {"query": "pão"}), stop_reason="tool_use"),
        _response(_text("Temos sim."), stop_reason="end_turn"),
    )
    service.run_turn(conversation.pk, _binding(conversation).pk, client=client)

    usage = _first_reply(conversation).usage
    assert usage["version"] == 1 and usage["layer"] == "agent"
    assert usage["triage"] == {"classifier": "anthropic", "source": "rules"}
    [call] = usage["calls"]
    assert call == {
        "stage": "model",
        "model": "claude-sonnet-5",
        "provider": "anthropic",
        "calls": 2,
        "input_tokens": 200,
        "output_tokens": 40,
        "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 0,
        "cost_usd": pytest.approx(usage_cost("claude-sonnet-5", call)),
    }
    assert usage["cost_usd"] == call["cost_usd"] > 0
    latency = usage["latency_ms"]
    assert {"total", "turn", "triage", "agent", "model", "tools"} <= set(latency)
    assert latency["total"] >= latency["turn"] >= latency["agent"] >= latency["model"]


def test_only_the_first_block_carries_the_turn(conversation, outbox):
    _receive(conversation, "tem pão francês?", "m2")
    client = ScriptedClient(
        _response(_tool("search_storefront", {"query": "pão"}), stop_reason="tool_use"),
        _response(_text("Temos sim."), stop_reason="end_turn"),
    )
    service.run_turn(conversation.pk, _binding(conversation).pk, client=client)
    replies = list(ConversationMessage.objects.filter(conversation=conversation, kind="reply").order_by("id"))
    assert replies[0].usage["version"] == 1
    assert all(reply.usage == {} for reply in replies[1:])


def test_courtesy_turn_costs_nothing_and_never_builds_a_model_client(conversation, outbox, monkeypatch):
    def forbidden():
        raise AssertionError("cortesia não chama o modelo")

    monkeypatch.setattr("shopman.storefront.concierge.agent.build_client", forbidden)
    _receive(conversation, "bom dia!", "m3")
    service.run_turn(conversation.pk, _binding(conversation).pk)

    usage = _first_reply(conversation).usage
    assert usage["layer"] == "courtesy"
    assert usage["calls"] == [] and usage["cost_usd"] == 0
    assert "model" not in usage["latency_ms"]


def test_triage_model_tokens_are_recorded_with_the_handoff_ack(conversation, outbox):
    _receive(conversation, "olha, sobre a conta de ontem", "m4")
    triage_client = UsageClient({"intent": "complaint", "urgency": "now", "summary": "Contesta a conta."})
    result = service.run_turn(
        conversation.pk, _binding(conversation).pk, client=ScriptedClient(), triage_client=triage_client
    )
    assert result.handoff
    ack = ConversationMessage.objects.get(conversation=conversation, kind="reply", envelope__purpose="handoff_ack")
    assert ack.usage["layer"] == "team"
    assert ack.usage["triage"]["source"] == "model"
    [call] = ack.usage["calls"]
    assert call["stage"] == "triage" and call["input_tokens"] == 300 and call["output_tokens"] == 40


def test_media_turn_is_recorded_as_media(conversation, outbox, monkeypatch):
    monkeypatch.setattr(service, "copy_message", lambda key: f"[{key}]")
    _receive(conversation, "opaque-provider-reference", "m5", message_type="image")
    service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())
    reply = _first_reply(conversation)
    assert reply is not None and reply.usage["layer"] == "media"


def test_jev_triage_is_metered_by_input_tokens(settings):
    meter = metrics.TurnMeter()

    class Contender:
        model = "jev-1"

        def scores(self, sample, categories):
            return SimpleNamespace(intents={}, input_tokens=500, output_tokens=0)

    meter.wrap_jev(Contender()).scores(None, [])
    usage = meter.as_usage()
    [call] = usage["calls"]
    assert call["provider"] == "typesafe" and call["input_tokens"] == 500
    assert usage["cost_usd"] == pytest.approx(500 * 0.042 / 1_000_000, abs=1e-6)
    assert "jev" in usage["latency_ms"]


# ── O golden set ─────────────────────────────────────────────────────


def test_golden_set_is_labeled_and_carries_no_personal_data():
    from shopman.storefront.concierge.intent_pilot import DEFAULT_INTENTS

    intents = {ref for ref, *_ in DEFAULT_INTENTS}
    cases = reply_eval.load_golden()
    assert len(cases) >= 150
    refs = [case["ref"] for case in cases]
    assert len(refs) == len(set(refs))
    for case in cases:
        expected = case["expected"]
        assert expected["layer"] in reply_eval.LAYERS
        assert expected["intent"] in intents | {""}
        assert set(expected.get("accept", [])) <= intents
        assert expected["destination"] in {"answer", "team", "other_desk"}
        for text in [case["text"], *(line["text"] for line in case["previous"])]:
            assert "@" not in text, case["ref"]
            assert not re.search(r"\d{8,}|\(?\d{2}\)?\s?9?\d{4}-?\d{4}", text), case["ref"]
            assert "http" not in text, case["ref"]


def test_eval_runs_the_current_path_without_network():
    report = reply_eval.run(reply_eval.load_golden(), classifier="rules")
    assert len(report.results) == len(reply_eval.load_golden())
    assert all(result.cost_usd == 0 for result in report.results)
    text = report.render()
    assert "Destino certo:" in text and "Chegam ao modelo de resposta" in text


def test_eval_command_prints_the_scoreboard():
    out = io.StringIO()
    call_command("concierge_reply_eval", "--limit", "20", stdout=out)
    assert "Placar da Concierge" in out.getvalue() and "Nada foi gravado" in out.getvalue()


def test_eval_refuses_a_provider_it_cannot_reach(settings):
    settings.AI_ASSIST_API_KEY = ""
    with pytest.raises(ValueError, match="indisponível"):
        reply_eval.run(reply_eval.load_golden()[:1], classifier="model")


def test_production_summary_reads_what_the_turn_recorded(conversation, outbox):
    _receive(conversation, "bom dia!", "m6")
    service.run_turn(conversation.pk, _binding(conversation).pk)
    assert "cortesia (1)" in reply_eval.production_summary(days=1)


def test_export_redacts_and_proposes_unreviewed_labels(conversation, outbox, tmp_path):
    _receive(conversation, "meu telefone é 43 99999-1234, tem croissant?", "m7")
    path = tmp_path / "export.jsonl"
    call_command("concierge_golden_export", "--output", str(path), stdout=io.StringIO())
    [case] = [json.loads(line) for line in path.read_text().splitlines()]
    assert "99999" not in case["text"]
    assert case["expected"]["reviewed"] is False
    assert case["expected"]["intent"] == "product_question"
