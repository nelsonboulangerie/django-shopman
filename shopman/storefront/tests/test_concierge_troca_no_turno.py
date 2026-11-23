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
    perfil do ar) e a leitura "pix" por uma IA falsa. A validade da concessão entra só se faltar: o ``main``
    a tem desde 889240d50, e esta pilha é anterior a ele (sem ela, nenhuma concessão nasce)."""
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
        if not any(line.id == "grant.validity_seconds" for line in lines):
            lines.append(dataclasses.replace(lines[0], id="grant.validity_seconds", setting=LineSet(value=600),
                                             state="approved", decided_at=DECIDED))
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
def test_delivery_for_a_customer_with_a_saved_address_goes_to_today_path(order_on_air, outbox, monkeypatch):
    """O fechamento de hoje oferece primeiro o endereço do cadastro (dono, 25/09) e entende o "sim"; o motor ainda
    não. O turno que escolhe entrega, com endereço salvo e nenhum na sacola, é do caminho de hoje."""
    from shopman.storefront.concierge import address

    monkeypatch.setattr(address, "saved_addresses", lambda ref: [object()])
    why, today = [], turn_framework.today_closing_does_better
    monkeypatch.setattr(turn_framework, "today_closing_does_better",
                        lambda conv, rehearsal: why.append(today(conv, rehearsal)) or why[-1])
    seen = _delivery_turn(order_on_air, monkeypatch, "entrega-salvo-1")
    assert why == ["saved_address_offer"] and seen == [None]  # a sombra aprovou, e o motor deu a vez ao de hoje
    assert outbox.sent and all("send_key" not in (reply.envelope or {}) for reply in _replies(order_on_air))


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
