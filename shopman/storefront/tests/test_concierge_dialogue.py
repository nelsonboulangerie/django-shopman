# ruff: noqa: F811
"""Memória da conversa (OBS0310-N, bloco 2 da CONCIERGE-ARQUITETURA-ALVO-V2).

Régua do dono: nunca afirmar algo falso; sem referente que ainda valha, a casa
pergunta. A memória vence pelo que acontece (orçamento trocado, pedido entregue,
próximo dia de funcionamento encerrado, equipe devolvendo a conversa), não pelo relógio.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings as django_settings
from django.test import override_settings
from django.utils import timezone

from shopman.shop.models import Conversation, Shop
from shopman.storefront.concierge import dialogue, service
from shopman.storefront.concierge.dialogue import Facts, OrderFact
from shopman.storefront.concierge.dialogue_eval import load_labels, registry_copy, render, run
from shopman.storefront.concierge.reply_eval import load_golden
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401  (fixtures)
    CONCIERGE_SETTINGS,
    ScriptedClient,
    _binding,
    _listed,
    _receive,
    _response,
    _text,
    _tool,
    alpha_menu,
    conversation,
    customer,
    outbox,
    surface,
)

TZ = ZoneInfo(django_settings.TIME_ZONE)
NOW = datetime(2026, 10, 3, 10, 0, tzinfo=TZ)  # sábado


def _resolve(text, state, facts=None):
    facts = facts or Facts(now=NOW)
    return dialogue.resolve(text, dialogue.effective(state, facts), facts, copy=registry_copy)


def _state(*memos, now=NOW, until=None):
    return dialogue.next_state({}, list(memos), now=now, fence=1, until=until or now + timedelta(days=1))


TWO = {"tool": "search_storefront", "items": [{"ref": "CROISSANT", "name": "Croissant"}, {"ref": "PAIN-CHOC", "name": "Pain au Chocolat"}]}
ONE = {"tool": "search_storefront", "items": [{"ref": "CROISSANT", "name": "Croissant"}]}


# ── O placar dos 47 casos de contexto do golden set ───────────────────


def test_every_context_case_of_the_golden_set_is_labelled():
    context = {case["ref"] for case in load_golden() if case["expected"]["layer"] == "context"}
    assert context == set(load_labels())


def test_scoreboard_resolves_or_asks_every_context_case():
    results = run(load_golden())
    assert len(results) == 47
    misses = [(r.case["ref"], r.expected, r.after, r.resolution.reason) for r in results if not r.ok("after")]
    assert misses == []
    # Antes (sem memória) só acertam as falas que se bastam.
    assert sum(r.ok("before") for r in results) == sum(1 for r in results if r.expected == "pass")
    text = render(results)
    assert "'Sim' aplicado à pergunta errada: 0. Suposição onde cabia pergunta: 0." in text


# ── Resolução ─────────────────────────────────────────────────────────


def test_ordinal_picks_from_the_last_list():
    resolution = _resolve("o segundo", _state(TWO))
    assert resolution.outcome == "resolved" and resolution.text == "Pain au Chocolat"
    assert resolution.refs == ("PAIN-CHOC",)
    assert resolution.memo["focus"]["ref"] == "PAIN-CHOC"


def test_yes_to_two_options_asks_which_instead_of_guessing():
    resolution = _resolve("sim", _state(TWO))
    assert resolution.outcome == "ask"
    assert resolution.reply == "Qual deles? 1) Croissant; 2) Pain au Chocolat"


def test_deeliv_case_quantity_after_two_options_asks_which():
    # Deeliv, 03/10: "quero 2 então" depois de duas pizzas foi para o link sem perguntar.
    resolution = _resolve("quero 2 então", _state(TWO))
    assert resolution.outcome == "ask" and resolution.reason == "ask_which"


def test_more_of_the_focused_product():
    resolution = _resolve("mais 2", _state(ONE))
    assert resolution.outcome == "resolved" and resolution.text == "2 Croissant"
    assert resolution.reason == "focus_qty"


def test_more_without_focus_asks_which_product():
    resolution = _resolve("mais 2", {})
    assert resolution.outcome == "ask" and resolution.reply == "De qual produto você quer 2?"


def test_more_relative_to_the_cart_tells_the_total():
    facts = Facts(now=NOW, cart={"CROISSANT": {"name": "Croissant", "qty": 2}})
    resolution = _resolve("mais 2", _state(ONE), facts)
    assert resolution.outcome == "resolved" and resolution.reason == "relative_cart"
    assert "total pedida é 4" in resolution.note


def test_pronoun_points_to_the_focus_and_plural_to_the_list():
    assert _resolve("ele tem quantas fatias?", _state(ONE)).text.endswith("Croissant")
    plural = _resolve("tem essas opções?", _state(TWO))
    assert plural.outcome == "resolved" and plural.refs == ("CROISSANT", "PAIN-CHOC")


def test_ailo_case_they_with_another_product_is_not_rewritten():
    # Ailo, 03/10: "e pain au chocolat, eles têm?" virou busca em outra loja. Aqui
    # a fala nomeia outro produto: a memória não a reescreve para o foco.
    resolution = _resolve("e pain au chocolat, eles têm?", _state(ONE))
    assert resolution.outcome == "pass" and not resolution.text


def test_pronoun_without_focus_asks():
    assert _resolve("pago nele 12 reais", {}).reply == "De qual produto você está falando?"


def test_correction_swaps_to_the_other_item_and_names_the_cart_change():
    state = _state(TWO, {"tool": "set_item", "ref": "CROISSANT", "name": "Croissant", "qty": 2})
    resolution = _resolve("não, era o outro", state)
    assert resolution.outcome == "resolved" and resolution.text == "Pain au Chocolat"
    assert "troque pelo item certo" in resolution.note


def test_yes_without_pending_question_asks():
    for text in ("sim", "Issoooo", "pode ser?"):
        assert _resolve(text, {}).reply == registry_copy(dialogue.ASK_WHAT_KEY), text
    # Concordância fraca sem pergunta no ar não vira interrogatório.
    assert _resolve("ok", {}).outcome == "pass"


def test_yes_to_team_offer_calls_the_team_and_no_declines():
    state = _state({"tool": "search_storefront", "found": False})
    assert _resolve("sim", state).outcome == "handoff"
    declined = _resolve("não", state)
    assert declined.outcome == "ask" and declined.reply == "Combinado. Posso ajudar com mais alguma coisa?"


def test_yes_to_the_recap_needs_the_same_quote():
    state = _state({"tool": "review_order", "ready": True, "token": "q1"})
    assert _resolve("sim", state, Facts(now=NOW, quote_token="q1")).reason == "confirm_order"
    # O orçamento acabou (pedido feito, sacola esvaziada): o "sim" não confirma nada.
    stale = _resolve("sim", state, Facts(now=NOW, quote_token=""))
    assert stale.outcome == "ask" and stale.reason == "no_pending"
    assert "pending" not in dialogue.effective(state, Facts(now=NOW, quote_token="q2"))


def test_information_in_the_same_turn_does_not_erase_the_recap_question():
    # Medido no teste vertical: o resumo e, na mesma resposta, a busca de um item só.
    state = _state({"tool": "review_order", "ready": True, "token": "q1"}, ONE)
    assert state["pending"] == {"kind": dialogue.CONFIRM_ORDER, "token": "q1"}
    assert _resolve("confirmo", state, Facts(now=NOW, quote_token="q1")).reason == "confirm_order"


def test_slot_by_time():
    state = _state({"tool": "list_fulfillment_slots", "date": "2026-10-03", "slots": [
        {"ref": "a", "name": "14:00 às 14:30"}, {"ref": "b", "name": "14:30 às 15:00"}]})
    resolution = _resolve("14:30", state)
    assert resolution.outcome == "resolved" and resolution.text == "14:30 às 15:00"


# ── Vencimento pelo que acontece ──────────────────────────────────────


def test_pending_question_about_today_expires_when_the_day_passes():
    state = _state({"tool": "search_storefront", "found": False}, until=NOW + timedelta(days=3))
    tomorrow = Facts(now=NOW + timedelta(days=1))
    assert "pending" not in dialogue.effective(state, tomorrow)
    assert _resolve("sim", state, tomorrow).reason == "no_pending"


def test_list_and_focus_expire_after_the_horizon():
    state = _state(ONE, until=NOW + timedelta(hours=5))
    assert dialogue.effective(state, Facts(now=NOW + timedelta(hours=4)))["focus"]["ref"] == "CROISSANT"
    later = Facts(now=NOW + timedelta(hours=6))
    assert "focus" not in dialogue.effective(state, later)
    assert _resolve("mais 2", state, later).outcome == "ask"


@pytest.mark.django_db
def test_weekend_turn_friday_night_still_valid_on_monday():
    # Seg a sex, 7h às 19h; fim de semana fechado.
    week = {day: {"open": "07:00", "close": "19:00"} for day in ("monday", "tuesday", "wednesday", "thursday", "friday")}
    Shop.objects.create(name="Casa", opening_hours=week)
    friday_night = datetime(2026, 10, 2, 21, 0, tzinfo=TZ)
    assert dialogue.horizon(friday_night) == datetime(2026, 10, 5, 19, 0, tzinfo=TZ)
    state = dialogue.next_state({}, [ONE], now=friday_night, fence=1)
    monday = Facts(now=datetime(2026, 10, 5, 9, 0, tzinfo=TZ))
    assert _resolve("mais 2", state, monday).text == "2 Croissant"
    tuesday = Facts(now=datetime(2026, 10, 6, 9, 0, tzinfo=TZ))
    assert _resolve("mais 2", state, tuesday).outcome == "ask"


def test_delivered_order_closes_its_memory_but_stays_recent():
    state = dialogue.next_state({}, [ONE, {"tool": "place_order", "order_ref": "P1"}], now=NOW, fence=1,
                                until=NOW + timedelta(days=1))
    open_facts = Facts(now=NOW, order_status={"P1": "preparing"})
    assert dialogue.effective(state, open_facts)["focus"]["ref"] == "CROISSANT"
    recent = OrderFact("P1", "delivered", "pedido P1, entrega hoje", "delivery", NOW)
    delivered = Facts(now=NOW + timedelta(hours=1), order_status={"P1": "delivered"}, recent_order=recent)
    memory = dialogue.effective(state, delivered)
    assert "focus" not in memory and memory["order"]["ref"] == "P1"
    # Pedido entregue não aceita item: "mais 2" pergunta se é pedido novo.
    more = _resolve("mais 2 croissant", state, delivered)
    assert more.outcome == "ask" and more.reason == "ask_new_after_closed"
    assert more.reply == "Seu último pedido (pedido P1, entrega hoje) já foi entregue. Quer fazer um pedido novo com 2 croissant?"
    follow = dialogue.next_state(memory, [more.memo], now=delivered.now, fence=2, until=NOW + timedelta(days=1))
    assert _resolve("sim", follow, delivered).text == "2 croissant"


def test_next_day_more_croissant_with_open_order_asks_order_or_new():
    order = OrderFact("P7", "accepted", "pedido P7, retirada hoje a partir das 15h", "pickup")
    facts = Facts(now=NOW, open_order=order, order_status={"P7": "accepted"})
    asked = _resolve("Mais 4 croissant", {}, facts)
    assert asked.outcome == "ask" and asked.reason == "ask_order_or_new"
    assert asked.reply.startswith("Você quer acrescentar 4 croissant ao seu pedido aberto (pedido P7, retirada hoje")
    state = dialogue.next_state({}, [asked.memo], now=NOW, fence=1, until=NOW + timedelta(days=1))
    new = _resolve("2", state, facts)
    assert new.outcome == "resolved" and new.text == "4 croissant" and new.reason == "new_order"
    add = _resolve("1", state, facts)
    assert add.outcome == "handoff" and "P7" in add.handoff_reason
    assert _resolve("sim", state, facts).reason == "ask_which"


# ── Cortesia com contexto ─────────────────────────────────────────────


def test_thanks_after_a_delivery_recognises_it():
    recent = OrderFact("P1", "delivered", "pedido P1, entrega hoje", "delivery", NOW)
    resolution = _resolve("obrigado, chegou!", {}, Facts(now=NOW, recent_order=recent))
    assert resolution.outcome == "courtesy" and resolution.reply == "Que bom que chegou! Bom apetite 💛"


def test_thanks_at_the_end_of_a_confirmed_order_confirms_what_was_agreed():
    order = OrderFact("P9", "new", "pedido P9, retirada amanhã a partir das 9h", "pickup")
    state = dialogue.next_state({}, [{"tool": "place_order", "order_ref": "P9"}], now=NOW, fence=1,
                                until=NOW + timedelta(days=1))
    resolution = _resolve("ok obrigada", state, Facts(now=NOW, open_order=order, order_status={"P9": "new"}))
    assert resolution.outcome == "courtesy"
    assert resolution.reply == "Nós que agradecemos! Fica combinado: pedido P9, retirada amanhã a partir das 9h. 💛"


def test_thanks_without_recent_event_keeps_the_simple_courtesy():
    assert _resolve("obrigado, chegou!", {}).outcome == "pass"
    assert _resolve("ok obrigada", {}).outcome == "pass"


# ── O turno de verdade: escrita, revogação, retorno da equipe ─────────


@pytest.mark.django_db(transaction=True)
@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_turn_writes_the_list_and_the_next_turn_resolves_the_ordinal(conversation, outbox, alpha_menu):
    _listed("PAIN-CHOC", "Pain au Chocolat", description="Folhado amanteigado com chocolate", stock="5")
    _receive(conversation, "tem folhado amanteigado?", "d1")
    first = ScriptedClient(
        _response(_tool("search_storefront", {"query": "folhado amanteigado"}), stop_reason="tool_use"),
        _response(_text("."), stop_reason="end_turn"),
    )
    service.run_turn(conversation.pk, _binding(conversation).pk, client=first)
    conversation.refresh_from_db()
    state = conversation.flags["dialogue"]
    names = [item["name"] for item in state["listed"]]
    assert len(names) >= 2 and state["pending"]["kind"] == dialogue.CHOOSE

    _receive(conversation, "o segundo", "d2")
    second = ScriptedClient(_response(_text("."), stop_reason="end_turn"))
    result = service.run_turn(conversation.pk, _binding(conversation).pk, client=second)
    assert names[1] in result.replies[0] and names[0] not in result.replies[0]
    system = second.requests[0]["system"]
    assert any("Memória da conversa" in block["text"] for block in system)
    conversation.refresh_from_db()
    assert conversation.flags["dialogue"]["focus"]["name"] == names[1]


@pytest.mark.django_db(transaction=True)
@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_yes_after_no_match_calls_the_team_without_the_model(conversation, outbox):
    _receive(conversation, "vocês vendem bicicletas?", "t1")
    first = ScriptedClient(
        _response(_tool("search_storefront", {"query": "bicicleta"}), stop_reason="tool_use"),
        _response(_text("."), stop_reason="end_turn"),
    )
    reply = service.run_turn(conversation.pk, _binding(conversation).pk, client=first).replies[0]
    assert "Posso chamar a equipe" in reply
    _receive(conversation, "sim", "t2")
    result = service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())
    assert result.handoff
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF


@pytest.mark.django_db(transaction=True)
@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_revoked_turn_does_not_write_memory(conversation, outbox):
    _receive(conversation, "tem pão?", "r1")

    class NewInputDuringModel(ScriptedClient):
        def _create(self, **kwargs):
            response = super()._create(**kwargs)
            if len(self.requests) == 2:
                Conversation.objects.filter(pk=conversation.pk).update(turn_fence=999)
            return response

    client = NewInputDuringModel(
        _response(_tool("search_storefront", {"query": "pão"}), stop_reason="tool_use"),
        _response(_text("."), stop_reason="end_turn"),
    )
    result = service.run_turn(conversation.pk, _binding(conversation).pk, client=client)
    assert result.fallback == "revoked"
    conversation.refresh_from_db()
    assert "dialogue" not in conversation.flags


@pytest.mark.django_db(transaction=True)
def test_team_returning_the_conversation_zeroes_the_memory(conversation, outbox, settings):
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "human_return_enabled": True}
    state = _state(ONE, {"tool": "search_storefront", "found": False}, now=timezone.now())
    Conversation.objects.filter(pk=conversation.pk).update(
        state=Conversation.State.HANDOFF, flags={"dialogue": state, "triage": {"intent": "x"}}
    )
    assert service.return_to_concierge(conversation)
    conversation.refresh_from_db()
    assert "dialogue" not in conversation.flags and conversation.flags["triage"] == {"intent": "x"}


@pytest.mark.django_db
def test_open_and_recent_orders_come_from_the_order_history(conversation, customer, settings):
    from shopman.orderman.models import Order

    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "recent_order_days": 7}
    now = timezone.now()
    delivered = Order.objects.create(
        ref="P-OLD", channel_ref="whatsapp", total_q=100,
        data={"customer_ref": customer.ref, "fulfillment_type": "delivery"},
    )
    Order.objects.filter(pk=delivered.pk).update(status="delivered", delivered_at=now - timedelta(days=2))
    facts = dialogue.load_facts(conversation, now=now)
    assert facts.open_order is None and facts.recent_order.ref == "P-OLD"
    # Passado o prazo, deixa de ser "pedido recente".
    assert dialogue.load_facts(conversation, now=now + timedelta(days=6)).recent_order is None
    # O próximo pedido encerra o "recente" do anterior.
    Order.objects.create(
        ref="P-NEW", channel_ref="whatsapp", total_q=100,
        data={"customer_ref": customer.ref, "fulfillment_type": "pickup",
              "delivery_date": timezone.localdate().isoformat()},
    )
    facts = dialogue.load_facts(conversation, now=now)
    assert facts.recent_order is None and facts.open_order.ref == "P-NEW"
    assert facts.open_order.label == "pedido P-NEW, retirada hoje"
