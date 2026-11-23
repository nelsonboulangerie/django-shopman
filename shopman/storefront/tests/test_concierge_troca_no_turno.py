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


@pytest.mark.django_db(transaction=True)  # o executor é a transação de fora (commerce_execute)
def test_after_the_effect_a_part_outside_the_nice_voice_holds_and_today_path_stays_quiet(order_on_air, outbox,
                                                                                         monkeypatch):
    """O porteiro de voz: no ar, a parte por molde sem frase da Nice segura. O efeito já aconteceu, por isso o
    caminho de hoje não responde (refaria o efeito); nenhum texto do pacote chega ao cliente."""
    import dataclasses

    from shopman.orderman.models import Session

    build = turn_framework.build_engine

    def without_done_on_air(conversation, *, environment=turn_framework.ENVIRONMENT, channel=None):
        engine = build(conversation, environment=environment, channel=channel)
        if engine is None or environment == "shadow":
            return engine
        house = {k: v for k, v in engine.house_templates.items() if k != "set_payment.done"}
        return dataclasses.replace(engine, house_templates=house)

    monkeypatch.setattr(turn_framework, "build_engine", without_done_on_air)
    result = _pix_turn(order_on_air, "pix-held-1")
    assert outbox.sent == [] and result.replies == []  # nada saiu, nem na voz do pacote, nem pelo caminho de hoje
    assert result.processed_message_ids  # a entrada foi consumida: o caminho de hoje não a pega de novo
    order_on_air.refresh_from_db()
    assert Session.objects.get(session_key=order_on_air.session_key).data["payment"] == {"method": "pix"}
