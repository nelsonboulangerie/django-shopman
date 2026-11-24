"""O leitor da Nice para o motor: a IA do perfil lê os atos com os campos (passo 1 do pedido pelo motor).

O que estes testes seguram:

- a IA lê; a casa resolve: o produto vira SKU pela busca do cardápio, a quantidade sai
  absoluta pela sacola ("mais 2", "tira 1", "tira o croissant") e o dia vira data pelo
  relógio da loja;
- o portão do Jev entrega sem a IA só o ato que não pede campo;
- a IA fora (sem conexão, erro, resposta ilegível) cai para a regra local, e a queda aparece
  no nome do leitor;
- o texto que vai à IA sai redigido, e produto que não está na fala não entra;
- o motor monta a Nice com este leitor e uma chamada por turno.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest
from conversational_commerce.engine.acts import ACTS
from conversational_commerce.ports import InterpretRequest, ModelRequest, TrustedContext
from conversational_commerce.testing.conformance.harness import HarnessEnv, run_checks
from conversational_commerce.testing.fakes.clock import FakeClock

from shopman.shop.models import Conversation
from shopman.storefront.concierge import model_reader
from shopman.storefront.concierge.model_reader import NiceReader, Reading, resolve_day

CTX = TrustedContext(tenant="nelson-boulangerie", environment="shadow", subject="conversation:1")
TODAY = date(2026, 11, 23)  # segunda-feira
WITH_FULFILLMENT = tuple(dict.fromkeys((*ACTS, model_reader.FULFILLMENT_ACT)))
CROISSANT = {"sku": "CROISSANT", "name": "Croissant", "can_order": True}
BAGUETE = {"sku": "BAGUETE", "name": "Baguete", "can_order": True}


class FakeAI:
    """O cliente da rota ``intents``: devolve o JSON combinado e guarda o pedido que recebeu."""

    def __init__(self, acts=None, *, raw=None, error=None, stop_reason="end_turn"):
        self.raw = raw if raw is not None else json.dumps({"acts": [_act(**a) for a in acts or []]})
        self.error, self.stop_reason, self.requests = error, stop_reason, []
        self.messages = self

    def create(self, **request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=self.raw)])


def _act(act, span="", product="", qty=0, change="", day="", mode="", time=""):
    return {"act": act, "span": span, "product": product, "qty": qty, "change": change, "day": day, "mode": mode,
            "time": time}


def _request(text, allowed=ACTS, context=None):
    return InterpretRequest(request=ModelRequest(purpose="interpret", data_class="redacted",
                                                 budget={"max_calls": 1, "max_spend": {"amount_minor": 0,
                                                                                       "currency": "BRL"}}),
                            event_id="evt-1", content_ref=f"text:{text}", allowed_acts=allowed, context=context)


def _read(text, ai, *, allowed=ACTS, gate=lambda text: "", context=None):
    reader = NiceReader(client=ai, model="deepseek-flash", gate=gate, today=TODAY)
    return reader.interpret(CTX, _request(text, allowed, context))


def _fields(understanding):
    return [(a.act, dict(a.fields)) for a in understanding.acts]


@pytest.fixture
def conversation(db):
    return Conversation.objects.create(pk=1, channel_ref="whatsapp", session_key="sess-1")


@pytest.fixture
def menu(monkeypatch):
    """A busca do cardápio: o item cujo nome a consulta cita."""
    from shopman.storefront.concierge import tools

    def search(name, args, ctx):
        query = (ctx.customer_text or "").lower()
        return {"ok": True, "items": [i for i in (CROISSANT, BAGUETE) if i["name"].lower()[:5] in query]}

    monkeypatch.setattr(tools, "execute", search)


@pytest.fixture
def cart(monkeypatch):
    lines: list[dict] = []
    monkeypatch.setattr(model_reader, "_cart_lines", lambda conversation: list(lines))
    return lines


# ── a IA lê, a casa resolve ─────────────────────────────────────────────────────────────


def test_the_reader_passes_the_framework_shape_check(db):
    ai = FakeAI([{"act": "ask_hours", "span": "que horas abre"}])
    assert run_checks("model", NiceReader(client=ai, model="m", gate=lambda t: "", today=TODAY),
                      HarnessEnv(ctx=CTX, clock=FakeClock())) == []


def test_two_products_become_two_cart_changes_with_sku_and_quantity(conversation, menu, cart):
    ai = FakeAI([{"act": "change_quantity", "span": "2 croissants", "product": "croissants", "qty": 2,
                  "change": "set"},
                 {"act": "change_quantity", "span": "1 baguete", "product": "baguete", "qty": 1, "change": "set"}])
    understanding, consumption = _read("quero 2 croissants e 1 baguete", ai)
    assert _fields(understanding) == [("change_quantity", {"item": "CROISSANT", "quantity": "2"}),
                                      ("change_quantity", {"item": "BAGUETE", "quantity": "1"})]
    assert understanding.reader.name == "concierge-model-reader"
    assert consumption.calls == 1 and consumption.cost.status == "unavailable"  # custo sem preço nunca é zero


@pytest.mark.parametrize(("change", "qty", "expected"), [
    ("add", 2, "4"),         # "mais 2" com 2 na sacola
    ("remove", 1, "1"),      # "tira 1"
    ("remove_all", 0, "0"),  # "tira o croissant"
    ("set", 3, "3"),         # "muda para 3"
])
def test_the_quantity_is_absolute_by_the_cart(conversation, menu, cart, change, qty, expected):
    cart.append({"sku": "CROISSANT", "name": "Croissant", "qty": 2})
    ai = FakeAI([{"act": "change_quantity", "span": "croissant", "product": "croissant", "qty": qty,
                  "change": change}])
    [(act, fields)] = _fields(_read("croissant", ai)[0])
    assert (act, fields) == ("change_quantity", {"item": "CROISSANT", "quantity": expected})


def test_more_one_without_a_name_is_the_only_product_in_the_cart(conversation, menu, cart):
    cart.append({"sku": "BAGUETE", "name": "Baguete", "qty": 1})
    ai = FakeAI([{"act": "change_quantity", "span": "mais um", "qty": 1, "change": "add"}])
    assert _fields(_read("mais um", ai)[0]) == [("change_quantity", {"item": "BAGUETE", "quantity": "2"})]


def test_more_one_without_a_name_and_two_products_stays_without_item(conversation, menu, cart):
    cart.extend([{"sku": "BAGUETE", "qty": 1}, {"sku": "CROISSANT", "qty": 2}])
    ai = FakeAI([{"act": "change_quantity", "span": "mais um", "qty": 1, "change": "add"}])
    assert _fields(_read("mais um", ai)[0]) == [("change_quantity", {"quantity": "1"})]  # o motor pergunta qual


def test_a_product_the_customer_did_not_write_never_comes_in(conversation, menu, cart):
    ai = FakeAI([{"act": "change_quantity", "span": "quero 2", "product": "baguete", "qty": 2, "change": "set"}])
    assert _fields(_read("quero 2", ai)[0]) == [("change_quantity", {"quantity": "2"})]


def test_a_question_about_a_product_carries_the_sku(conversation, menu, cart):
    ai = FakeAI([{"act": "ask_item", "span": "tem croissant hoje?", "product": "croissant"},
                 {"act": "change_quantity", "span": "queria 2", "product": "croissant", "qty": 2, "change": "set"}])
    assert _fields(_read("tem croissant hoje? queria 2", ai)[0]) == [
        ("ask_item", {"item": "CROISSANT"}), ("change_quantity", {"item": "CROISSANT", "quantity": "2"})]


# ── o dia, o recebimento e a hora ───────────────────────────────────────────────────────


def test_day_pickup_and_time_said_with_the_order(conversation, menu, cart):
    ai = FakeAI([{"act": "change_quantity", "span": "2 croissants", "product": "croissants", "qty": 2,
                  "change": "set"},
                 {"act": "choose_fulfillment", "span": "amanhã às 16h vou aí buscar", "day": "tomorrow",
                  "mode": "pickup", "time": "16:00"}])
    understanding, _ = _read("quero 2 croissants, amanhã às 16h vou aí buscar", ai, allowed=WITH_FULFILLMENT)
    assert _fields(understanding) == [
        ("change_quantity", {"item": "CROISSANT", "quantity": "2"}),
        ("choose_fulfillment", {"date": "2026-11-24", "mode": "pickup", "time": "16:00"})]


def test_without_the_fulfillment_act_in_the_engine_the_reader_never_returns_it(conversation, menu, cart):
    ai = FakeAI([{"act": "choose_fulfillment", "span": "amanhã", "day": "tomorrow"}])
    # O motor que não conhece o ato (lista sem ``choose_fulfillment``): o leitor nunca o devolve.
    without = tuple(act for act in ACTS if act != model_reader.FULFILLMENT_ACT)
    understanding, _ = _read("pra amanhã", ai, allowed=without)
    assert [a.act for a in understanding.acts] == ["unknown"]
    assert "choose_fulfillment" not in json.dumps(ai.requests[0]["output_config"])  # nem pedido à IA


@pytest.mark.parametrize(("day", "expected"), [
    ("today", "2026-11-23"), ("tomorrow", "2026-11-24"), ("day_after_tomorrow", "2026-11-25"),
    ("friday", "2026-11-27"), ("monday", "2026-11-23"), ("sunday", "2026-11-29"),
    ("25/11", "2026-11-25"), ("02/01", "2027-01-02"), ("20/11", "2027-11-20"), ("31/02", ""), ("", ""),
    ("semana que vem", ""),
])
def test_the_day_is_resolved_by_the_store_clock(day, expected):
    assert resolve_day(day, TODAY) == expected


def test_an_hour_outside_the_clock_is_dropped():
    raw = json.dumps({"acts": [_act("choose_fulfillment", day="tomorrow", time="25:00", mode="drone")]})
    [reading] = model_reader.parse(raw, "amanhã", WITH_FULFILLMENT)
    assert (reading.time, reading.mode, reading.day) == ("", "", "tomorrow")


def test_absolute_quantity_without_a_number_is_unknown():
    assert model_reader.absolute_quantity(Reading(act="change_quantity", change="set"), 3) is None
    assert model_reader.absolute_quantity(Reading(act="change_quantity", change="add"), 3) == 4


# ── o portão do Jev ─────────────────────────────────────────────────────────────────────


def test_the_jev_gate_answers_a_fieldless_act_without_the_ai(conversation):
    ai = FakeAI(error=AssertionError("a IA não devia ser chamada"))
    understanding, consumption = _read("que horas vocês abrem?", ai, gate=lambda text: "ask_hours")
    assert _fields(understanding) == [("ask_hours", {})]
    assert understanding.reader.name == "concierge-jev-gate" and consumption.calls == 0 and ai.requests == []


@pytest.mark.parametrize(("intent", "expected"), [
    ("hours_delivery", "ask_hours"), ("human", "request_human"),
    ("order", ""), ("product_question", ""),  # pedem campo: vão à IA
])
def test_the_gate_lets_through_only_what_needs_no_field(monkeypatch, intent, expected):
    from shopman.storefront.concierge import intents, triage

    monkeypatch.setattr(triage, "jev_enabled", lambda: True)
    monkeypatch.setattr(triage, "classify_with_jev", lambda text, **k: {"intent": intent, "scores": {intent: 0.99}})
    monkeypatch.setattr(intents, "gate", lambda text, **k: intents.GateDecision(True, "jev_certain", intent))
    assert model_reader.jev_gate("qualquer fala") == expected


def test_without_jev_the_gate_never_answers(monkeypatch):
    from shopman.storefront.concierge import triage

    monkeypatch.setattr(triage, "jev_enabled", lambda: False)
    assert model_reader.jev_gate("que horas abre?") == ""


# ── a leitura com contexto (ADR-051) ────────────────────────────────────────────────────


def _asked(code, expected, recent=()):
    from conversational_commerce.ports import PendingQuestion, ReadingContext

    return ReadingContext(pending=PendingQuestion(kind="condition", code=code), expected_acts=expected, recent=recent)


def test_with_the_pickup_time_asked_the_gate_does_not_decide_alone_and_the_ai_reads_in_context(conversation):
    """Ensaio no ar (24/11): a Nice perguntou o horário da retirada, e o Jev leu "vou buscar às 16h" como o horário
    da loja. Com a pergunta no ar, o ato do portão fora do esperado não decide: a IA lê com o contexto, e a leitura
    do portão vai junto como alternativa, para o motor conferir."""
    ai = FakeAI([{"act": "choose_fulfillment", "span": "vou buscar às 16h", "mode": "pickup", "time": "16:00"}])
    understanding, consumption = _read("vou buscar às 16h", ai, allowed=WITH_FULFILLMENT, gate=lambda t: "ask_hours",
                                       context=_asked("delivery_time_slot", ("choose_fulfillment",)))
    assert _fields(understanding) == [("choose_fulfillment", {"mode": "pickup", "time": "16:00"})]
    assert [[a.act for a in alt.acts] for alt in understanding.alternatives] == [["ask_hours"]]
    assert consumption.calls == 1
    content = ai.requests[0]["messages"][0]["content"]
    assert "A Nice acabou de perguntar o horário da retirada" in content and "choose_fulfillment" in content
    assert "horário da retirada" not in ai.requests[0]["system"][0]["text"]  # o sistema segue igual, no cache


def test_the_gate_still_answers_when_its_act_answers_the_question(conversation):
    ai = FakeAI(error=AssertionError("a IA não devia ser chamada"))
    understanding, consumption = _read("sim", ai, gate=lambda t: "affirm",
                                       context=_asked("delivery_address_saved", ("give_address", "affirm", "deny")))
    assert _fields(understanding) == [("affirm", {})] and consumption.calls == 0


def test_the_recent_turns_go_to_the_ai_redacted_and_by_what_the_nice_asked(conversation, menu, cart):
    from conversational_commerce.ports import RecentTurn

    recent = (RecentTurn(role="customer", content_ref="text:quero 2 croissants pra amanhã"),
              RecentTurn(role="agent", template_ids=("present_terms.needs_fulfillment_type",)))
    ai = FakeAI([{"act": "choose_fulfillment", "span": "vou buscar", "mode": "pickup"}])
    _read("vou buscar", ai, allowed=WITH_FULFILLMENT,
          context=_asked("fulfillment_type", ("choose_fulfillment",), recent))
    content = ai.requests[0]["messages"][0]["content"]
    assert "- Cliente: quero 2 croissants pra amanhã" in content
    assert "- Nice: perguntou se o cliente vai retirar na loja ou receber em casa" in content
    assert content.index("Conversa até aqui") < content.index("<<<")  # o contexto antes da fala, nunca dentro


# ── a queda para a regra local ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("ai", [
    FakeAI(error=TimeoutError("rede")),
    FakeAI(raw="isto não é json"),
    FakeAI(raw=json.dumps({"partes": []})),
    FakeAI([{"act": "change_quantity"}], stop_reason="max_tokens"),
], ids=["erro", "ilegivel", "fora_do_esquema", "cortada"])
def test_when_the_ai_fails_the_local_rule_answers(conversation, ai, monkeypatch):
    failures = []
    monkeypatch.setattr("shopman.storefront.concierge.reading_health.record_read",
                        lambda *, ok: failures.append(ok))
    understanding, consumption = _read("qual o horário de vocês?", ai)
    assert understanding.reader.name == "concierge-local-rules" and consumption.calls == 0
    assert "ask_hours" in [a.act for a in understanding.acts]


def test_without_a_connection_the_local_rule_answers(conversation, monkeypatch):
    monkeypatch.setattr(model_reader, "build_client", lambda: (None, ""))
    reader = NiceReader(gate=lambda text: "", today=TODAY)
    understanding, consumption = reader.interpret(CTX, _request("qual o horário de vocês?"))
    assert understanding.reader.name == "concierge-local-rules" and consumption.calls == 0


def test_the_text_sent_to_the_ai_is_redacted_and_carries_the_cart(conversation, menu, cart):
    cart.append({"sku": "CROISSANT", "name": "Croissant", "qty": 2})
    ai = FakeAI([{"act": "change_quantity", "span": "mais 1", "qty": 1, "change": "add"}])
    _read("mais 1, meu cpf é 123.456.789-09 e meu email é ana@exemplo.com", ai)
    content = ai.requests[0]["messages"][0]["content"]
    assert "123.456.789-09" not in content and "ana@exemplo.com" not in content
    assert "2 × Croissant" in content
    assert ai.requests[0]["model"] == "deepseek-flash" and ai.requests[0]["thinking"] == {"type": "disabled"}


# ── o motor monta a Nice com este leitor ────────────────────────────────────────────────


def test_the_engine_reads_by_the_nice_reader_once_per_turn(db, monkeypatch):
    from shopman.shop.models import Channel, Shop
    from shopman.storefront.concierge import turn_framework
    from shopman.storefront.concierge.contracts import TransportConnection
    from shopman.storefront.concierge.ports import NiceChannel
    from shopman.storefront.concierge.transport import ManyChatWhatsAppAdapter

    Channel.objects.create(ref="whatsapp", name="WhatsApp", config={})  # o canal materializado, como no descritor
    Shop.objects.create(name="Nelson Boulangerie")
    connection = TransportConnection(key="manychat-whatsapp-primary", provider="manychat", account="acc-1",
                                     channel="whatsapp", adapter_path="x", options={})
    conversation = Conversation.objects.create(channel_ref="whatsapp")
    engine = turn_framework.build_engine(conversation, environment="shadow",
                                         channel=NiceChannel(ManyChatWhatsAppAdapter(connection=connection)))
    assert isinstance(engine.ports.model, NiceReader)
    assert engine.profile.limits.max_model_calls == 1
