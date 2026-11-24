# ruff: noqa: F401, F811
"""N9b: o turno vivo passa pelo motor do framework só com a chave ligada (#3299).

Com as chaves desligadas, o turno é o de hoje, e o motor nem é montado. Com a classe "informar"
ligada, o agradecimento sai pelo motor, na frase de hoje e pelo mesmo envio, uma vez só. O que o
motor não sabe dizer com frase da Nice continua no caminho de hoje.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from shopman.shop.models import ConversationMessage, Shop
from shopman.storefront.concierge import service, turn_framework
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _binding,
    _receive,
    alpha_menu,
    conversation,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db


def _inform_on():
    shop = Shop.load()
    shop.conversational_live_inform = True
    shop.save()


def _replies(conversation):
    return list(ConversationMessage.objects.filter(conversation=conversation, kind="reply").order_by("pk"))


def test_with_the_switches_off_the_turn_is_today_and_the_engine_is_not_built(conversation, outbox, monkeypatch):
    monkeypatch.setattr(turn_framework, "build_engine", lambda *a, **k: pytest.fail("o motor não deveria ser montado"))
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "obrigada!", "troca-off-1")
        result = service.run_turn(conversation.pk, _binding(conversation).pk)
    assert result.fallback == "" and len(outbox.sent) == 1
    assert all("send_key" not in (reply.envelope or {}) for reply in _replies(conversation))


def test_a_thank_you_goes_through_the_engine_once_in_today_phrase(conversation, outbox):
    _inform_on()
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "obrigada!", "troca-on-1")
        result = service.run_turn(conversation.pk, _binding(conversation).pk)
    thanks = service.copy_message("CONCIERGE_SMALL_TALK_THANKS").strip()
    assert outbox.sent == [thanks]  # uma vez só: o motor enviou, o caminho de hoje não repete
    assert result.replies == [thanks] and result.processed_message_ids
    (reply,) = _replies(conversation)
    assert reply.envelope["send_key"].startswith("send:")  # saiu pelo motor
    # O turno se fecha como hoje: a entrada consumida, sob o mesmo fence.
    assert all(m.consumed_by is not None for m in ConversationMessage.objects.filter(pk__in=result.processed_message_ids))


def test_a_greeting_is_answered_with_today_greeting_not_with_the_thanks(conversation, outbox):
    """Calibragem do básico (23/11): pelo motor, "oi" saía "Nós que agradecemos!". O cumprimento é o de hoje."""
    from shopman.storefront.concierge.small_talk import INTRO_COPY_KEY

    _inform_on()
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "oi", "troca-oi-1")
        service.run_turn(conversation.pk, _binding(conversation).pk)
    thanks = service.copy_message("CONCIERGE_SMALL_TALK_THANKS").strip()
    assert len(outbox.sent) == 1 and outbox.sent[0] != thanks
    intro = service.copy_message(INTRO_COPY_KEY).split("{", 1)[0].strip()
    assert intro in outbox.sent[0]  # a apresentação de hoje ("Aqui é a concierge da …")
    assert all("send_key" not in (reply.envelope or {}) for reply in _replies(conversation))  # o caminho de hoje


def test_what_the_engine_cannot_say_in_the_nice_voice_stays_on_today_path(conversation, outbox):
    _inform_on()
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "qual o horário de vocês?", "troca-on-2")
        result = service.run_turn(conversation.pk, _binding(conversation).pk)
    assert result.fallback == "" and len(outbox.sent) == 1
    assert all("send_key" not in (reply.envelope or {}) for reply in _replies(conversation))  # o caminho de hoje


def test_an_interrupted_turn_sends_nothing_through_the_engine(conversation, outbox):
    _inform_on()
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "obrigada!", "troca-on-3")
        message = ConversationMessage.objects.filter(conversation=conversation, kind="inbound").latest("pk")
        assert turn_framework.run(conversation, message, interrupted=lambda: True) is None
    assert outbox.sent == []  # a conversa mudou de dono: o motor não envia, e o caminho de hoje decide


# ── #3410: o turno com efeito pelo motor no ar, pelo serviço de verdade ─────────────────────────

DECIDED = "2026-11-23T00:00:00.000000Z"
PIX = {"act": "choose_payment", "span": "pix", "product": "", "qty": 0, "change": "", "day": "", "mode": "",
       "time": "", "payment": "pix"}
OFFER_TEAM = "Isso eu não consigo fazer por aqui. Quer que eu chame alguém da equipe?"


@pytest.fixture
def order_on_air(conversation, monkeypatch):
    """O pedido pelo motor no ar: a chave "pedido" ligada, a P08 aprovada só em memória (espera o dono no
    perfil do ar) e a leitura "pix" por uma IA falsa. A validade da concessão (P22) e a janela do episódio
    (P23) são as do perfil de verdade."""
    import dataclasses
    import json

    from conversational_commerce.contracts.deployment_profile import LineSet

    from shopman.storefront.concierge import model_reader, profile
    from shopman.storefront.tests.test_concierge_model_reader import FakeAI

    real = model_reader.NiceReader
    monkeypatch.setattr(model_reader, "NiceReader",
                        lambda: real(client=FakeAI(raw=json.dumps({"acts": [PIX]})), model="m", gate=lambda t: ""))
    build = profile.build_profile

    def approved(**kwargs):
        built = build(**kwargs)
        lines = [dataclasses.replace(line, state="approved", decided_at=line.decided_at or DECIDED)
                 if line.id == "commerce.order_in_conversation" else line for line in built.lines]
        return dataclasses.replace(built, lines=tuple(lines))

    monkeypatch.setattr(profile, "build_profile", approved)
    shop = Shop.load()
    shop.conversational_live_order = True
    shop.save()
    return conversation


def _pix_turn(conversation, event_id):
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "pix", event_id)
        return service.run_turn(conversation.pk, _binding(conversation).pk)


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_a_payment_goes_out_through_the_engine_on_air(order_on_air, outbox):
    """O turno com efeito passa da sombra (julgada pelos moldes) e sai pelo motor no ar, uma vez só."""
    from shopman.orderman.models import Session

    _pix_turn(order_on_air, "pix-on-1")
    assert outbox.sent == ["Combinado: Pix."]
    (reply,) = _replies(order_on_air)
    assert reply.envelope["send_key"].startswith("send:")  # saiu pelo motor
    order_on_air.refresh_from_db()
    assert Session.objects.get(session_key=order_on_air.session_key).data["payment"] == {"method": "pix"}


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_an_effect_refused_on_air_says_the_nice_limitation(order_on_air, outbox, monkeypatch):
    """#3408: no ar, o efeito recusado refaz a decisão, e a limitação sai com a frase da Nice."""
    from conversational_commerce.contracts.errors import ErrorCode

    from shopman.shop.conversational.commerce_execute import Done
    from shopman.storefront.concierge.effect_site import ConciergeEffectSite

    monkeypatch.setattr(ConciergeEffectSite, "_set_payment",
                        lambda self, command: Done(False, refusal=ErrorCode.FACT_UNAVAILABLE.value))
    _pix_turn(order_on_air, "pix-refused-1")
    assert outbox.sent == [OFFER_TEAM]


HELD = "Pronto, anotei. Já te confirmo os detalhes por aqui."


def _held_on_air(kind):
    """O motor do ar com a resposta do efeito segurada: molde fora da voz da Nice, ou referência que não resolve."""
    import dataclasses

    from conversational_commerce.reply import UnresolvedReference

    build = turn_framework.build_engine

    def held(conversation, *, environment=turn_framework.ENVIRONMENT, channel=None):
        engine = build(conversation, environment=environment, channel=channel)
        if engine is None or environment == "shadow":
            return engine
        if kind == "template_not_in_voice":
            house = {k: v for k, v in engine.house_templates.items() if k != "set_payment.done"}
            return dataclasses.replace(engine, house_templates=house)

        def unresolved(value):
            raise UnresolvedReference(str(value))

        return dataclasses.replace(engine, formatters={**engine.formatters, "method": unresolved})

    return held


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
@pytest.mark.parametrize("kind", ["template_not_in_voice", "reference_unresolved"])
def test_after_the_effect_a_held_answer_never_ends_in_silence(order_on_air, outbox, monkeypatch, kind):
    """#3413: o efeito aconteceu e a resposta segurou. O caminho de hoje não responde (refaria o efeito), o
    cliente ouve o recuo da casa, lastreado só no recibo, e a equipe recebe o cartão com prazo para confirmar."""
    from shopman.orderman.models import Session

    from shopman.backstage.models import OperatorAlert

    monkeypatch.setattr(turn_framework, "build_engine", _held_on_air(kind))
    seen, answer = [], turn_framework.answer_after_effect
    monkeypatch.setattr(turn_framework, "answer_after_effect",
                        lambda conversation, held: seen.append(turn_framework._findings(held)) or answer(conversation, held))
    result = _pix_turn(order_on_air, f"pix-held-{kind}")
    assert len(seen) == 1 and kind in seen[0]  # segurou pelo motivo que se quis provar
    assert outbox.sent == [HELD]  # nunca silêncio, nunca a voz do pacote, nunca o caminho de hoje
    assert result.processed_message_ids  # a entrada foi consumida: o caminho de hoje não a pega de novo
    order_on_air.refresh_from_db()
    assert Session.objects.get(session_key=order_on_air.session_key).data["payment"] == {"method": "pix"}
    card = OperatorAlert.objects.get(type=turn_framework.EFFECT_HELD_ALERT)
    assert card.respond_by is not None and card.resolved_at is None and "set_payment" in card.message


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_a_pending_effect_says_so_with_the_deadline(order_on_air, outbox, monkeypatch):
    """#3328: o efeito que não volta confirmado diz "ainda estou concluindo", na frase aprovada e com o prazo da
    reconciliação; nunca a voz do pacote, nunca o recuo de efeito segurado."""
    from conversational_commerce.contracts.errors import ErrorCode
    from conversational_commerce.ports import PortError

    from shopman.shop.conversational.commerce_execute import ShopmanCommerceExecute

    def running(self, ctx, command, guard):
        raise PortError(ErrorCode.EFFECT_PENDING, "a mesma chave está em execução")

    monkeypatch.setattr(ShopmanCommerceExecute, "execute", running)
    _pix_turn(order_on_air, "pix-pending-1")
    assert len(outbox.sent) == 1
    assert outbox.sent[0].startswith("Ainda estou concluindo isso. Te confirmo por aqui até ")


# ── (b2): a entrega de quem tem endereço salvo é do caminho de hoje ─────────────────────────────

DELIVERY = {"act": "choose_fulfillment", "span": "entrega", "product": "", "qty": 0, "change": "", "day": "",
            "mode": "delivery", "time": "", "payment": ""}


def _delivery_turn(conversation, monkeypatch, event_id):
    import json

    from shopman.storefront.concierge import model_reader
    from shopman.storefront.tests.test_concierge_model_reader import FakeAI

    real = type(model_reader.NiceReader())  # a classe, por baixo da leitura "pix" da fixture
    monkeypatch.setattr(model_reader, "NiceReader",
                        lambda: real(client=FakeAI(raw=json.dumps({"acts": [DELIVERY]})), model="m",
                                     gate=lambda t: ""))
    seen, run = [], turn_framework.run
    monkeypatch.setattr(turn_framework, "run", lambda *a, **k: seen.append(run(*a, **k)) or seen[-1])
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "quero entrega", event_id)
        service.run_turn(conversation.pk, _binding(conversation).pk)
    return seen


@pytest.mark.django_db(transaction=True)
def test_delivery_without_a_saved_address_stays_with_the_engine(order_on_air, outbox, monkeypatch):
    from shopman.storefront.concierge import address

    monkeypatch.setattr(address, "saved_addresses", lambda ref: [])
    seen = _delivery_turn(order_on_air, monkeypatch, "entrega-sem-salvo-1")
    assert seen and seen[0] is not None and "set_fulfillment" in seen[0].chosen_moves


def test_after_the_effect_only_the_part_without_a_nice_phrase_drops(monkeypatch):
    """Rede de segurança: com o efeito feito e só o achado de voz, a parte sem frase da Nice cai e o resto sai."""
    from types import SimpleNamespace

    from conversational_commerce.reply.verify import Finding, RenderedPart, Segment

    said = []
    monkeypatch.setattr(service, "send_out_of_turn", lambda conv, text, **kw: said.append(text) or object())
    parts = (RenderedPart("set_fulfillment", (Segment("Combinado: entrega."),), (), "set_fulfillment.done_mode"),
             RenderedPart("present_terms", (Segment("Before I can place the order"),), (),
                          "present_terms.needs_delivery_address_saved"))
    result = SimpleNamespace(
        reply=SimpleNamespace(verification=SimpleNamespace(findings=(Finding("template_not_in_voice", 1),),
                                                           parts=parts)),
        commands=(SimpleNamespace(action="set_fulfillment"),), decision=SimpleNamespace(decision_id="dec-1"))
    voice = frozenset({"set_fulfillment.done_mode"})
    assert turn_framework.send_voiced_parts(SimpleNamespace(pk=1), result, voice)
    assert said == ["Combinado: entrega."]  # nunca a voz do pacote
    # Outro achado junto (referência que não resolve): nada sai por aqui; quem responde é o recuo.
    other = SimpleNamespace(**{**result.__dict__, "reply": SimpleNamespace(verification=SimpleNamespace(
        findings=(Finding("template_not_in_voice", 1), Finding("reference_unresolved", 0, "mode")), parts=parts))})
    assert not turn_framework.send_voiced_parts(SimpleNamespace(pk=1), other, voice)
    assert said == ["Combinado: entrega."]


# ── o Pix do pedido pelo motor ──────────────────────────────────────────────────────────────────

PIX_CODE = "00020126580014br.gov.bcb.pix0136teste-copia-e-cola5204000053039865802BR6304ABCD"


class _ScriptedAI:
    """A rota de leitura: devolve os atos de cada fala do roteiro (a fala vai entre ``<<<`` e ``>>>``)."""

    def __init__(self, script):
        self.script, self.messages = script, self

    def create(self, **request):
        import json
        from types import SimpleNamespace

        said = request["messages"][0]["content"].split("<<<\n", 1)[1].split("\n>>>", 1)[0]
        acts = self.script.get(said, [{"act": "unknown"}])
        full = [{"span": said, "product": "", "qty": 0, "change": "", "day": "", "mode": "", "time": "",
                 "payment": "", **act} for act in acts]
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text",
                                                                                text=json.dumps({"acts": full}))])


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_the_order_through_the_engine_sends_the_pix_apart_like_today(order_on_air, outbox, monkeypatch):
    """O pedido pelo motor entrega o copia-e-cola do Pix numa mensagem SEPARADA, depois da confirmação, como o
    caminho de hoje (``tools._placed_result`` → ``extra_replies``). Antes, ele ficava no contexto do sítio."""
    from shopman.storefront.concierge import model_reader, tools
    from shopman.storefront.tests.test_concierge_engine import SKU

    script = {
        "pode fechar": [{"act": "place_order"}],
        "pix": [{"act": "choose_payment", "payment": "pix"}],
        "sim": [{"act": "affirm"}],
    }
    real = type(model_reader.NiceReader())
    monkeypatch.setattr(model_reader, "NiceReader",
                        lambda: real(client=_ScriptedAI(script), model="m", gate=lambda t: ""))
    execute = tools.execute

    def house(name, args, ctx):
        if name == "review_order":
            return {"ok": True, "ready": True, "quote_token": "tok-pix", "payment_method": "pix"}
        return execute(name, args, ctx)

    def place(ctx, token, method, notes=""):
        ctx.extra_replies.append(PIX_CODE)  # como o _placed_result: o Pix numa mensagem separada
        return {"ok": True, "order_ref": "ORD-PIX-1", "payment": {"method": method,
                                                                 "pix_code_prepared_separately": True}}

    monkeypatch.setattr(tools, "execute", house)
    monkeypatch.setattr(tools, "place_order", place)
    shop = Shop.load()
    shop.conversational_live_inform = True  # "pronto", "obrigada": a cortesia do fechamento também é do motor
    shop.save()
    from shopman.orderman.models import Session

    # A sacola já com o pão (como depois do "quero 1 pão francês"): o teste é do fechamento e do Pix.
    Session.objects.create(session_key="sess-pix", channel_ref="whatsapp",
                           items=[{"sku": SKU, "qty": 1, "unit_price_q": 90, "line_total_q": 90}],
                           data={"fulfillment_type": "pickup", "delivery_date": "2026-11-25",
                                 "delivery_time_slot": "slot-15"})
    order_on_air.session_key = "sess-pix"
    order_on_air.save(update_fields=["session_key"])
    seen, run = [], turn_framework.run
    monkeypatch.setattr(turn_framework, "run", lambda *a, **k: seen.append(run(*a, **k)) or seen[-1])
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        for index, said in enumerate(script):
            _receive(order_on_air, said, f"pix-order-{index}")
            service.run_turn(order_on_air.pk, _binding(order_on_air).pk)
    last = seen[-1]
    assert last is not None and last.chosen_moves == ["commit_order"], [(r and r.chosen_moves) for r in seen]
    assert outbox.sent[-2].startswith("Pedido ORD-PIX-1 registrado.")  # a confirmação do motor
    assert outbox.sent[-1] == PIX_CODE  # e o Pix, separado, logo depois



# ── #3421: o endereço do cadastro pelo motor ────────────────────────────────────────────────────


def _saved(pk, route, number, tag, *, default=False):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    return SimpleNamespace(pk=pk, is_default=default, updated_at=datetime(2026, 11, 1, tzinfo=UTC), route=route,
                           street_number=number, neighborhood="Centro", formatted_address=f"{route}, {number}",
                           label="other", label_custom=tag, display_label=tag)


def _saved_flow(conversation, monkeypatch, script, saved, *, said_in_order=None, before_turn=None):
    """A sacola com pão, entrega e Pix; o cadastro do cliente; a leitura e a gravação do recebimento da casa."""
    from shopman.guestman.services import address as address_service
    from shopman.orderman.models import Session

    from shopman.storefront.concierge import address, model_reader, tools
    from shopman.storefront.tests.test_concierge_engine import SKU

    monkeypatch.setattr(address_service, "addresses", lambda ref: list(saved))
    monkeypatch.setattr(address, "saved_addresses", lambda ref: sorted(
        saved, key=lambda item: (not item.is_default, -item.updated_at.timestamp(), item.pk)))
    real = type(model_reader.NiceReader())
    monkeypatch.setattr(model_reader, "NiceReader",
                        lambda: real(client=_ScriptedAI(script), model="m", gate=lambda t: ""))
    written = []

    def house_writes(ctx, **said):
        written.append(said)
        tools._set_session_data(ctx, ctx.conversation.session_key, {
            "delivery_address": "Rua do Cadastro, 10 - Centro",
            "delivery_address_structured": {"formatted_address": "Rua do Cadastro, 10 - Centro",
                                            "route": "Rua do Cadastro", "street_number": "10",
                                            "neighborhood": "Centro", "city": "Londrina", "state_code": "PR",
                                            "postal_code": "86010-000", "latitude": -23.3, "longitude": -51.1,
                                            "complement": ""}})
        return {"ok": True}

    monkeypatch.setattr(tools, "set_fulfillment", house_writes)
    Session.objects.create(session_key="sess-salvo", channel_ref="whatsapp",
                           items=[{"sku": SKU, "qty": 1, "unit_price_q": 90, "line_total_q": 90}],
                           data={"fulfillment_type": "delivery", "delivery_date": "2026-11-25",
                                 "delivery_time_slot": "slot-15", "payment": {"method": "pix"}})
    conversation.session_key = "sess-salvo"
    conversation.save(update_fields=["session_key"])
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        for index, said in enumerate(said_in_order or list(script)):
            if before_turn is not None:
                before_turn(index)
            _receive(conversation, said, f"salvo-{index}")
            service.run_turn(conversation.pk, _binding(conversation).pk)
    return written


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_the_saved_address_is_offered_with_today_phrase_and_yes_takes_it(order_on_air, outbox, monkeypatch):
    from shopman.storefront.concierge.address import saved_offer

    saved = [_saved(7, "Rua do Cadastro", "10", "Casa", default=True)]
    script = {"pode fechar": [{"act": "place_order"}], "sim": [{"act": "affirm"}]}
    written = _saved_flow(order_on_air, monkeypatch, script, saved)
    assert outbox.sent[0] == saved_offer(saved) == "Entregamos no endereço do seu cadastro, Rua do Cadastro, 10 - Centro?"
    assert written and written[0].get("saved_address_pk") == 7  # o "sim" grava O endereço oferecido, pelo id
    # O "sim" volta ao resumo, com o endereço do cadastro na linha da entrega, pronto para o "sim" do pedido.
    assert "Entrega: quarta-feira, 25/11, a partir das 15h\nRua do Cadastro, 10 - Centro\n" in outbox.sent[1]
    assert outbox.sent[1].endswith("Posso registrar?")


@pytest.mark.django_db(transaction=True)
def test_no_to_the_saved_address_asks_today_question_and_keeps_the_close(order_on_air, outbox, monkeypatch):
    from shopman.storefront.concierge.service import copy_message

    saved = [_saved(7, "Rua do Cadastro", "10", "Casa", default=True)]
    script = {"pode fechar": [{"act": "place_order"}], "não": [{"act": "deny"}]}
    written = _saved_flow(order_on_air, monkeypatch, script, saved)
    assert outbox.sent[1] == copy_message("CONCIERGE_CLOSE_ASK_ADDRESS").strip() and written == []


@pytest.mark.django_db(transaction=True)
def test_with_two_saved_addresses_the_name_chooses_one(order_on_air, outbox, monkeypatch):
    from shopman.storefront.concierge.address import saved_offer

    saved = [_saved(7, "Rua do Cadastro", "10", "Casa", default=True), _saved(9, "Avenida Brasil", "200", "Trabalho")]
    script = {"pode fechar": [{"act": "place_order"}], "o do trabalho": [{"act": "give_address"}]}
    written = _saved_flow(order_on_air, monkeypatch, script, saved)
    assert outbox.sent[0] == saved_offer(sorted(saved, key=lambda item: not item.is_default))
    assert written and written[0].get("saved_address_label") == "Trabalho"



@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("another", ["outro", "Quero outro", "outro endereço?", "quais?"])
def test_another_lists_the_saved_addresses_with_today_phrase_and_the_name_chooses(
        order_on_air, outbox, monkeypatch, another):
    """#3454: "outro" à oferta, com dois endereços no cadastro, lista os dois pela frase de hoje (sem a IA), e o
    nome em seguida escolhe. A lista não é pergunta de sim ou não: nada se grava até o nome."""
    from shopman.storefront.concierge.address import saved_listing

    saved = [_saved(7, "Rua do Cadastro", "10", "Casa", default=True), _saved(9, "Avenida Brasil", "200", "Trabalho")]
    script = {"pode fechar": [{"act": "place_order"}]}  # o "outro" e o nome não vão à IA
    written = _saved_flow(order_on_air, monkeypatch, script, saved,
                          said_in_order=["pode fechar", another, "o do trabalho"])
    assert outbox.sent[1] == saved_listing(sorted(saved, key=lambda item: not item.is_default)) == (
        "Seus endereços cadastrados: Casa: Rua do Cadastro, 10 - Centro; Trabalho: Avenida Brasil, 200 - Centro. "
        "Em qual entregamos?")
    assert written and written[0].get("saved_address_label") == "Trabalho"


@pytest.mark.django_db(transaction=True)
def test_another_with_a_single_saved_address_asks_today_question(order_on_air, outbox, monkeypatch):
    """Com um endereço só não há lista: "outro" é "esse não", e pergunta o endereço como o "não" (nunca grava
    "outro" como endereço)."""
    from shopman.storefront.concierge.service import copy_message

    saved = [_saved(7, "Rua do Cadastro", "10", "Casa", default=True)]
    written = _saved_flow(order_on_air, monkeypatch, {"pode fechar": [{"act": "place_order"}]}, saved,
                          said_in_order=["pode fechar", "outro"])
    assert outbox.sent[1] == copy_message("CONCIERGE_CLOSE_ASK_ADDRESS").strip() and written == []


@pytest.mark.django_db(transaction=True)
def test_no_with_the_name_in_the_same_message_chooses_by_the_name(order_on_air, outbox, monkeypatch):
    """ "Não, o do trabalho": o "não" é correção, e ganha a escolha pela etiqueta. A IA lê o nome mascarado."""
    saved = [_saved(7, "Rua do Cadastro", "10", "Casa", default=True), _saved(9, "Avenida Brasil", "200", "Trabalho")]
    # A IA vê o nome mascarado: o roteiro dela é pela fala MASCARADA.
    script = {"pode fechar": [{"act": "place_order"}],
              "não, [endereço omitido]": [{"act": "deny"}, {"act": "give_address"}]}
    written = _saved_flow(order_on_air, monkeypatch, script, saved,
                          said_in_order=["pode fechar", "não, o do trabalho"])
    assert written and written[0].get("saved_address_label") == "Trabalho"
    assert not any("Qual é o endereço" in text for text in outbox.sent[1:])  # o "não" não pediu outro endereço


@pytest.mark.django_db(transaction=True)
def test_yes_after_the_saved_address_changed_writes_nothing(order_on_air, outbox, monkeypatch):
    """O "sim" aceita o endereço OFERECIDO: editado o cadastro depois da oferta, nada se grava no lugar dele."""
    saved = [_saved(7, "Rua do Cadastro", "10", "Casa", default=True)]

    def edit_after_offer(index):
        if index == 1:
            saved[0].street_number = "12"  # o cliente editou o número no site entre a oferta e o "sim"

    script = {"pode fechar": [{"act": "place_order"}], "sim": [{"act": "affirm"}]}
    written = _saved_flow(order_on_air, monkeypatch, script, saved, before_turn=edit_after_offer)
    assert written == []  # nada gravado com um endereço que o cliente não viu


# ── #3419: a porta de equipe da Nice pelo motor ─────────────────────────────────────────────────

HUMAN = {"atendente, por favor": [{"act": "request_human"}]}


def _human_on_air(conversation, monkeypatch, *, handoff=True, times=1):
    from shopman.storefront.concierge import model_reader

    real = type(model_reader.NiceReader())
    monkeypatch.setattr(model_reader, "NiceReader",
                        lambda: real(client=_ScriptedAI(HUMAN), model="m", gate=lambda t: ""))
    shop = Shop.load()
    shop.conversational_live_inform = True
    shop.conversational_live_handoff = handoff
    shop.save()
    seen, run = [], turn_framework.run
    monkeypatch.setattr(turn_framework, "run", lambda *a, **k: seen.append(run(*a, **k)) or seen[-1])
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        for index in range(times):
            _receive(conversation, "atendente, por favor", f"humano-{index}")
            service.run_turn(conversation.pk, _binding(conversation).pk)
    return seen


def _cards(kind):
    from shopman.backstage.models import OperatorAlert

    return OperatorAlert.objects.filter(type=kind).count()


@pytest.mark.django_db(transaction=True)
def test_asking_for_a_person_hands_over_with_the_approved_phrase_and_one_card(order_on_air, outbox, monkeypatch):
    """ "Quero falar com uma pessoa" pelo motor: a frase aprovada do encaminhamento, a MESMA entrega à equipe de
    hoje (a conversa com a equipe e o cartão de "cliente esperando atendente"), e nenhum cartão de verificar."""
    from shopman.shop.models import Conversation

    seen = _human_on_air(order_on_air, monkeypatch)
    assert seen and seen[0] is not None and "handoff" in seen[0].chosen_moves
    assert len(outbox.sent) == 1 and outbox.sent[0].startswith("Solicitei atendimento a alguém da equipe")
    assert Conversation.objects.get(pk=order_on_air.pk).state == Conversation.State.HANDOFF
    assert (_cards("concierge_handoff"), _cards("concierge_verify")) == (1, 0)


@pytest.mark.django_db(transaction=True)
def test_asking_twice_for_a_person_is_one_card_and_one_phrase(order_on_air, outbox, monkeypatch):
    """Idempotência: com a conversa já com a equipe, o segundo pedido não abre outro cartão nem repete a frase."""
    _human_on_air(order_on_air, monkeypatch, times=2)
    assert len(outbox.sent) == 1 and _cards("concierge_handoff") == 1


@pytest.mark.django_db(transaction=True)
def test_with_the_handoff_class_off_nothing_changes(order_on_air, outbox, monkeypatch):
    """A configuração de teste do dono: "encaminhar" desligado. O pedido de pessoa segue o caminho de hoje."""
    seen = _human_on_air(order_on_air, monkeypatch, handoff=False)
    assert seen == [None]  # o motor não respondeu
    assert outbox.sent and not outbox.sent[0].startswith("Solicitei atendimento a alguém da equipe")
    assert all("send_key" not in (reply.envelope or {}) for reply in _replies(order_on_air))


@pytest.mark.django_db(transaction=True)
def test_the_verify_card_shows_the_customer_words_and_the_ask_carries_only_the_internal_code(conversation):
    """P17: a pergunta do motor à equipe é interna ("ask_item: …") e é tudo o que o ask e o tíquete levam; a fala
    do cliente, que a equipe lê no cartão, é lida AQUI, na mensagem que abriu o turno."""
    from conversational_commerce.ports import TrustedContext
    from conversational_commerce.ports.staff import StaffQuestion

    from shopman.shop.models import Conversation
    from shopman.storefront.concierge.ports import subject_of
    from shopman.storefront.concierge.staff_port import NiceStaff
    from shopman.storefront.concierge.verification import FLAG_KEY

    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "tem glúten no pão de queijo?", "verify-1")
    question = StaffQuestion(episode_id="ep-x", question="ask_item: item.PAO-QUEIJO",
                             respond_by="2026-11-23T23:59:00.000000Z")
    ctx = TrustedContext(tenant="nelson-boulangerie", environment="live", subject=subject_of(conversation.pk))
    ticket = NiceStaff().ask(ctx, question)
    assert ticket.state == "routed" and "glúten" not in ticket.ticket_id
    assert set(question.__dataclass_fields__) == {"episode_id", "question", "respond_by"}  # nada além do código
    record = (Conversation.objects.get(pk=conversation.pk).flags or {}).get(FLAG_KEY) or {}
    asked = str(record)
    assert "glúten" in asked and "ask_item" not in asked  # a equipe lê a fala, nunca o código interno


@pytest.mark.django_db(transaction=True)
def test_the_deadline_notice_goes_out_once(order_on_air, outbox, monkeypatch):
    """K22 de ponta a ponta: o motor encaminhou com prazo; a equipe devolveu a conversa sem responder; vencido o
    prazo, o cliente é avisado UMA vez na frase aprovada, e o tick seguinte cala."""
    from datetime import UTC, datetime, timedelta

    from shopman.shop.conversational import clock
    from shopman.shop.models import Conversation

    _human_on_air(order_on_air, monkeypatch)
    with override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "human_return_enabled": True}):
        assert service.return_to_concierge(Conversation.objects.get(pk=order_on_air.pk))  # a equipe devolveu
    # Passado o prazo de aceite (minutos), dentro da janela de 24 h do WhatsApp (fora dela, nada sai).
    later = datetime.now(UTC) + timedelta(minutes=30)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return later if tz is not None else later.replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", Later)
    monkeypatch.setattr("django.utils.timezone.now", lambda: later)
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        first = turn_framework.tick()
        second = turn_framework.tick()
    assert (first["notices"], second["notices"]) == (1, 0), (first, second)
    assert len(outbox.sent) == 2 and outbox.sent[1].startswith("Desculpe a demora.")


def _after_the_accept_window(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from shopman.shop.conversational import clock

    later = datetime.now(UTC) + timedelta(minutes=30)  # passado o aceite, dentro da janela de 24 h do WhatsApp

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return later if tz is not None else later.replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", Later)
    monkeypatch.setattr("django.utils.timezone.now", lambda: later)


@pytest.mark.django_db(transaction=True)
def test_the_team_holds_the_conversation_and_does_not_answer_the_notice_goes_out_once(order_on_air, outbox,
                                                                                      monkeypatch):
    """A frase do encaminhamento prometeu "te aviso por aqui até {deadline}". Com a conversa na equipe e ninguém
    tendo assumido, o aviso sai UMA vez (a Nice nunca afirma falso), e o tick seguinte cala."""
    from shopman.shop.models import Conversation

    _human_on_air(order_on_air, monkeypatch)
    assert Conversation.objects.get(pk=order_on_air.pk).state == Conversation.State.HANDOFF
    _after_the_accept_window(monkeypatch)
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        first = turn_framework.tick()
        second = turn_framework.tick()
    assert (first["notices"], second["notices"]) == (1, 0), (first, second)
    assert len(outbox.sent) == 2 and outbox.sent[1].startswith("Desculpe a demora.")


@pytest.mark.django_db(transaction=True)
def test_the_team_took_over_and_the_tick_stays_quiet(order_on_air, outbox, monkeypatch):
    """Alguém da equipe assumiu o cartão de atendimento depois do encaminhamento: a promessa está com a equipe, e
    o tick não fala."""
    from shopman.backstage.models import OperatorAlert
    from shopman.shop.models import Conversation

    _human_on_air(order_on_air, monkeypatch)
    pk = (Conversation.objects.get(pk=order_on_air.pk).flags or {})["alerts"]["concierge_handoff"]
    _after_the_accept_window(monkeypatch)
    from django.utils import timezone

    OperatorAlert.objects.filter(pk=pk).update(acknowledged=True, acknowledged_at=timezone.now(),
                                               acknowledged_by="ana")
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        counts = turn_framework.tick()
    assert counts["notices"] == 0 and len(outbox.sent) == 1


# ── #3482: o quando antes do "Posso registrar?" ──────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_the_close_asks_the_when_with_today_questions_before_the_summary(order_on_air, outbox, monkeypatch):
    """O cartão 5 pelo serviço real, sacola sem dia. Antes, "pode fechar" ia ao resumo ("Retirada", sem dia nem
    horário) e o "sim" ouvia "não entendi": a casa não grava retirada sem horário. Agora o motor pergunta o dia,
    o modo e o horário com as perguntas de hoje, na ordem do fechamento, e só então o resumo."""
    from datetime import timedelta

    from django.utils import timezone
    from shopman.orderman.models import Session

    from shopman.storefront.concierge import model_reader, tools
    from shopman.storefront.tests.test_concierge_engine import SKU

    script = {"pode fechar": [{"act": "place_order"}], "amanhã": [{"act": "choose_fulfillment", "day": "tomorrow"}],
              "vou retirar": [{"act": "choose_fulfillment", "mode": "pickup"}],
              "às 16h": [{"act": "choose_fulfillment", "time": "16:00"}],
              "pix": [{"act": "choose_payment", "payment": "pix"}], "sim": [{"act": "affirm"}]}
    real = type(model_reader.NiceReader())
    monkeypatch.setattr(model_reader, "NiceReader",
                        lambda: real(client=_ScriptedAI(script), model="m", gate=lambda t: ""))
    placed = []
    execute = tools.execute

    def house(name, args, ctx):
        if name == "review_order":
            return {"ok": True, "ready": True, "quote_token": "tok-when", "payment_method": "pix"}
        return execute(name, args, ctx)

    monkeypatch.setattr(tools, "execute", house)
    monkeypatch.setattr(tools, "place_order", lambda ctx, token, method, notes="": placed.append(token) or {
        "ok": True, "order_ref": "ORD-WHEN-1", "payment": {"method": method}})
    shop = Shop.load()
    shop.conversational_live_inform = True  # a config do teste do dono: "informar" e "pedido"
    shop.save()
    Session.objects.create(session_key="sess-when", channel_ref="whatsapp",
                           items=[{"sku": SKU, "qty": 1, "unit_price_q": 90, "line_total_q": 90}])
    order_on_air.session_key = "sess-when"
    order_on_air.save(update_fields=["session_key"])
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        for index, said in enumerate(script):
            _receive(order_on_air, said, f"when-{index}")
            service.run_turn(order_on_air.pk, _binding(order_on_air).pk)
    ask = {key: service.copy_message(key).strip() for key in (
        "CONCIERGE_CLOSE_ASK_DATE", "CONCIERGE_CLOSE_ASK_FULFILLMENT")}
    close, day, mode, time, pix, yes = outbox.sent[:6]
    assert close == ask["CONCIERGE_CLOSE_ASK_DATE"]  # "Para quando é o pedido? …"
    assert day == ask["CONCIERGE_CLOSE_ASK_FULFILLMENT"]  # "retirar ou entrega?"
    assert mode.startswith("Qual horário de retirada fica melhor?") and "15h" in mode  # a grade do dia
    assert time.startswith("Como você prefere pagar?")
    tomorrow = (timezone.localdate() + timedelta(days=1)).strftime("%d/%m")
    assert "Retirada: " in pix and tomorrow in pix and pix.endswith("Posso registrar?")  # o resumo com o quando
    assert yes.startswith("Pedido ORD-WHEN-1 registrado.") and placed == ["tok-when"]
    data = Session.objects.get(session_key="sess-when").data
    assert data["fulfillment_type"] == "pickup" and data["delivery_time_slot"]


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_the_day_said_with_the_order_is_not_asked_again(order_on_air, outbox, monkeypatch):
    """Controle negativo do #3482: "pra amanhã, pode fechar" já diz o dia; o fechamento segue para retirar ou
    entregar e o horário, e nunca pergunta o dia de novo."""
    from shopman.orderman.models import Session

    from shopman.storefront.concierge import model_reader
    from shopman.storefront.tests.test_concierge_engine import SKU

    script = {"pra amanhã, pode fechar": [{"act": "choose_fulfillment", "day": "tomorrow"}, {"act": "place_order"}],
              "vou retirar": [{"act": "choose_fulfillment", "mode": "pickup"}]}
    real = type(model_reader.NiceReader())
    monkeypatch.setattr(model_reader, "NiceReader",
                        lambda: real(client=_ScriptedAI(script), model="m", gate=lambda t: ""))
    shop = Shop.load()
    shop.conversational_live_inform = True  # a config do teste do dono: "informar" e "pedido"
    shop.save()
    Session.objects.create(session_key="sess-day", channel_ref="whatsapp",
                           items=[{"sku": SKU, "qty": 1, "unit_price_q": 90, "line_total_q": 90}])
    order_on_air.session_key = "sess-day"
    order_on_air.save(update_fields=["session_key"])
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        for index, said in enumerate(script):
            _receive(order_on_air, said, f"day-{index}")
            service.run_turn(order_on_air.pk, _binding(order_on_air).pk)
    ask_date = service.copy_message("CONCIERGE_CLOSE_ASK_DATE").strip()
    assert not any(ask_date in text for text in outbox.sent)
    assert outbox.sent[0].endswith(service.copy_message("CONCIERGE_CLOSE_ASK_FULFILLMENT").strip())
    assert outbox.sent[1].startswith("Qual horário de retirada fica melhor?")
    assert Session.objects.get(session_key="sess-day").data["delivery_date"]


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_a_cart_change_in_the_middle_of_the_close_says_it_changed_and_keeps_the_question(order_on_air, outbox,
                                                                                        monkeypatch):
    """#3488: "na verdade 3" com o fechamento perguntando o dia muda a sacola, diz o total novo e repete a pergunta
    aberta. Antes, só a pergunta voltava, como se nada tivesse acontecido."""
    from shopman.orderman.models import Session

    from shopman.storefront.concierge import model_reader
    from shopman.storefront.tests.test_concierge_engine import SKU

    script = {"pode fechar": [{"act": "place_order"}],
              "na verdade 3": [{"act": "change_quantity", "product": "pão francês", "qty": 3, "change": "set"}]}
    real = type(model_reader.NiceReader())
    monkeypatch.setattr(model_reader, "NiceReader",
                        lambda: real(client=_ScriptedAI(script), model="m", gate=lambda t: ""))
    shop = Shop.load()
    shop.conversational_live_inform = True  # a config do teste do dono: "informar" e "pedido"
    shop.save()
    Session.objects.create(session_key="sess-adj", channel_ref="whatsapp",
                           items=[{"sku": SKU, "qty": 2, "unit_price_q": 90, "line_total_q": 180}])
    order_on_air.session_key = "sess-adj"
    order_on_air.save(update_fields=["session_key"])
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        for index, said in enumerate(script):
            _receive(order_on_air, said, f"adj-{index}")
            service.run_turn(order_on_air.pk, _binding(order_on_air).pk)
    ask_date = service.copy_message("CONCIERGE_CLOSE_ASK_DATE").strip()
    assert outbox.sent[0] == ask_date
    assert outbox.sent[1] == f"Pronto, a sacola foi atualizada. Total: R$ 2,70.\n\n{ask_date}"
    assert Session.objects.get(session_key="sess-adj").items[0]["qty"] == 3



@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_the_delivery_asks_the_window_after_the_address_and_the_summary_shows_it(order_on_air, outbox, monkeypatch):
    """Coordenação, 24/11: na entrega, depois do endereço, "Qual janela de entrega fica melhor?" com as janelas do
    dia (as da loja on-line); a hora dita grava a janela, e o resumo a mostra. Pelo serviço real."""
    import re

    from shopman.orderman.models import Session

    from shopman.storefront.concierge import address, model_reader, tools
    from shopman.storefront.tests.test_concierge_engine import SKU

    # O endereço inteiro chega à IA mascarado (P17): o roteiro é pela fala mascarada.
    script = {"pode fechar": [{"act": "place_order"}], "às 15h": [{"act": "choose_fulfillment", "time": "15:00"}],
              "pix": [{"act": "choose_payment", "payment": "pix"}],
              "[endereço omitido]": [{"act": "give_address"}], "[endereço omitido], Centro": [{"act": "give_address"}]}
    real = type(model_reader.NiceReader())
    monkeypatch.setattr(model_reader, "NiceReader",
                        lambda: real(client=_ScriptedAI(script), model="m", gate=lambda t: ""))
    monkeypatch.setattr(address, "saved_addresses", lambda ref: [])

    def house_writes(ctx, **said):  # a geocodificação da casa: o endereço inteiro, sem complemento
        tools._set_session_data(ctx, ctx.conversation.session_key, {
            "delivery_address": "Rua das Flores, 120 - Centro",
            "delivery_address_structured": {"formatted_address": "Rua das Flores, 120 - Centro",
                                            "route": "Rua das Flores", "street_number": "120",
                                            "neighborhood": "Centro", "city": "Londrina", "state_code": "PR",
                                            "postal_code": "86010-000", "latitude": -23.3, "longitude": -51.1,
                                            "complement": ""}})
        return {"ok": True}

    monkeypatch.setattr(tools, "set_fulfillment", house_writes)
    shop = Shop.load()
    shop.conversational_live_inform = True  # a config do teste do dono: "informar" e "pedido"
    shop.save()
    Session.objects.create(session_key="sess-win", channel_ref="whatsapp",
                           items=[{"sku": SKU, "qty": 1, "unit_price_q": 90, "line_total_q": 90}],
                           data={"fulfillment_type": "delivery", "delivery_date": "2026-11-25"})
    order_on_air.session_key = "sess-win"
    order_on_air.save(update_fields=["session_key"])
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        for index, said in enumerate(["pode fechar", "Rua das Flores 120, Centro", "às 15h", "pix"]):
            _receive(order_on_air, said, f"win-{index}")
            service.run_turn(order_on_air.pk, _binding(order_on_air).pk)
    close, window, pay, summary = outbox.sent[:4]
    assert close == service.copy_message("CONCIERGE_CLOSE_ASK_ADDRESS").strip()
    assert window.startswith("Qual janela de entrega fica melhor? ") and re.search(r"\d+h", window)
    assert "a partir das" in window and "A partir" not in window  # o rótulo da grade, minúsculo na frase
    assert pay.startswith("Como você prefere pagar?")
    assert re.search(r"Entrega: quarta-feira, 25/11, .*15h", summary) and summary.endswith("Posso registrar?")
    assert Session.objects.get(session_key="sess-win").data["delivery_time_slot"]
