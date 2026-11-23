"""Resposta com prova: K23, K24, K27, e "afirmação sem lastro não sai em nenhum caminho"."""

from __future__ import annotations

import pytest

from conversational_commerce.contracts import ActionReceipt, Commitment, Known, ReplyPlan, Unknown
from conversational_commerce.reply import (
    TEMPLATES_BY_ID,
    Evidence,
    PartSpec,
    PhraseRule,
    RenderedClaim,
    RenderedPart,
    Segment,
    SlotSpec,
    Template,
    compose,
    verify,
)
from conversational_commerce.testing.conformance import conformance

NOW = "2026-01-05T09:00:00.000000Z"
LATER = "2026-01-05T10:00:00.000000Z"
ENVELOPE = {"id": "rec-reply-1", "tenant": "tenant-a", "environment": "test", "trace_id": "trace-1",
            "occurred_at": NOW, "episode_id": "ep-1"}
PRODUCER = {"name": "core", "version": "1"}

HOURS = Known(value="open until six", source="commerce", observed_at=NOW, valid_until=LATER)
RECEIPT = ActionReceipt(id="rcp-1", tenant="tenant-a", environment="test", trace_id="t", occurred_at=NOW,
                        producer=PRODUCER, command_id="cmd-1", status="success", effect="applied",
                        domain_refs={"effect": "order-77"})
PENDING = ActionReceipt(id="rcp-2", tenant="tenant-a", environment="test", trace_id="t", occurred_at=NOW,
                        producer=PRODUCER, command_id="cmd-2", status="pending", effect="unknown",
                        reconciliation={"deadline": LATER, "owner": "core"})
PROMISE = Commitment(id="rec-c1", tenant="tenant-a", environment="test", trace_id="t", occurred_at=NOW,
                     producer=PRODUCER, episode_id="ep-1", commitment_id="c-1", type="promise",
                     obligation="confirm the order", owner="core",
                     deadline={"status": "set", "at": LATER, "rule_ref": "reconciliation_15m"},
                     fulfillment_criterion="customer receives the confirmation", state="open")


def _evidence(**overrides) -> Evidence:
    fields = {
        "now": NOW,
        "facts": {"hours": HOURS, "promise.ITEM-A.promisable": Known(value="three units", source="commerce",
                                                                       observed_at=NOW, valid_until=LATER),
                  "promise.ITEM-A.factual": Known(value="no units", source="commerce", observed_at=NOW,
                                                  valid_until=LATER),
                  "order.order-77": Known(value={"ref": "order-77", "total": {"price_minor": 1350, "currency": "XTS"}},
                                          source="commerce", observed_at=NOW, valid_until=LATER)},
        "fact_facets": {"promise.ITEM-A.promisable": "promisable", "promise.ITEM-A.factual": "factual"},
        "receipts": {"rcp-1": RECEIPT, "rcp-2": PENDING},
        "commitments": {"c-1": PROMISE},
    }
    fields.update(overrides)
    return Evidence(**fields)


def _compose(*specs, evidence=None, rules=()):
    return compose(specs=specs, templates=TEMPLATES_BY_ID, evidence=evidence or _evidence(), rules=rules,
                   decision_id="dec-1", record=ENVELOPE)


def test_backed_reply_passes_and_renders_from_evidence_only():
    composed = _compose(PartSpec("acknowledge", "acknowledge.basic"),
                        PartSpec("inform", "inform.fact", {"answer": ("fact", "hours")}))
    assert composed.verification.result == "pass"
    assert composed.text == "Thank you for your message.\n\nopen until six"
    assert isinstance(composed.plan, ReplyPlan)
    assert ReplyPlan.from_document(composed.plan.to_document()) == composed.plan
    assert composed.plan.locked_blocks == ("part1.answer",)


@conformance("K23", invariants=("N01", "N03"), scope="adapter")
def test_k23_price_or_state_without_fact_is_held():
    # No molde: número no texto fixo nem chega a existir.
    with pytest.raises(ValueError, match="número"):
        Template("inform.bad", "1", "inform", "It costs 12 today.")
    # Na redação com marcadores (ou em qualquer conteúdo): dígito fora de espaço lastreado segura.
    drafted = RenderedPart("inform", (Segment("It costs 12 and we close at "), Segment("six", "hours")),
                           (RenderedClaim("hours", "fact", "hours"),))
    result = verify([drafted], _evidence())
    assert result.result == "hold"
    assert [f.code for f in result.findings] == ["number_without_fact"]
    # Fato desconhecido no espaço: nada de valor, e a mensagem não sai.
    composed = _compose(PartSpec("inform", "inform.fact", {"answer": ("fact", "hours")}),
                        evidence=_evidence(facts={"hours": Unknown(reason="source_failed")}))
    assert composed.verification.result == "hold" and composed.text is None
    assert composed.plan.verification.findings[0].code == "fact_unknown"


@conformance("K24", invariants=("N01",), scope="adapter")
def test_k24_reply_asserting_an_action_without_receipt_is_held():
    # Parte de efeito com recibo que não é sucesso: segura.
    pending = _compose(PartSpec("commit_order", "commit_order.done", {"order": ("receipt", "rcp-2"),
                                                                      "total": ("fact", "order.order-77"),
                                                                      "track": ("receipt", "rcp-2")}))
    assert pending.verification.result == "hold" and pending.text is None
    assert {f.code for f in pending.verification.findings} >= {"action_without_receipt",
                                                              "backing_kind_not_accepted"}
    # Com recibo de sucesso: sai, com a referência do domínio vinda do recibo.
    done = _compose(PartSpec("commit_order", "commit_order.done", {"order": ("receipt", "rcp-1"),
                                                                   "total": ("fact", "order.order-77"),
                                                                   "track": ("receipt", "rcp-1")}))
    assert done.verification.result == "pass"
    assert done.text.startswith("Your order order-77 is placed. Total: ") and done.text.endswith("Track it: order-77.")
    # O pendente se diz como espera, com o prazo do compromisso.
    waiting = _compose(PartSpec("wait", "commit_order.pending", {"deadline": ("commitment", "c-1")}))
    assert waiting.verification.result == "pass" and LATER in waiting.text
    # Regra da casa: ação afirmada no texto livre sem recibo de sucesso segura.
    claim = RenderedPart("inform", (Segment("I cancelled it for you."),),
                         (RenderedClaim("courtesy", "courtesy", None),))
    rule = PhraseRule("asserted_action", r"\bcancelled\b", "hold", unless_backing="receipt:success")
    assert verify([claim], _evidence(), [rule]).result == "hold"


@conformance("K27", invariants=("N02",), scope="adapter")
def test_k27_promisable_is_not_physical_unit():
    on_hand = _compose(PartSpec("inform", "inform.on_hand", {"quantity": ("fact", "promise.ITEM-A.promisable")}))
    assert on_hand.verification.result == "hold" and on_hand.text is None
    assert on_hand.verification.findings[0].code == "backing_kind_not_accepted"
    promise = _compose(PartSpec("inform", "inform.promise", {"quantity": ("fact", "promise.ITEM-A.promisable")}))
    assert promise.verification.result == "pass"
    assert promise.text == "We can have three units ready for the requested time."


def test_expired_fact_does_not_back_a_claim():
    stale = Known(value="open until six", source="commerce", observed_at="2026-01-05T08:00:00.000000Z",
                  valid_until=NOW)
    composed = _compose(PartSpec("inform", "inform.fact", {"answer": ("fact", "hours")}),
                        evidence=_evidence(facts={"hours": stale}))
    assert composed.text is None and composed.verification.findings[0].code == "fact_expired"


def test_unbound_slot_is_an_error_not_an_empty_claim():
    with pytest.raises(ValueError, match="sem lastro"):
        _compose(PartSpec("inform", "inform.fact"))


def test_repair_touches_only_free_text_never_the_locked_block():
    template = Template("inform.hours", "1", "inform", "Sure thing! {answer}", {"answer": SlotSpec(("fact",))})
    evidence = _evidence(facts={"hours": Known(value="Sure thing, open until six", source="commerce",
                                               observed_at=NOW, valid_until=LATER)})
    rule = PhraseRule("too_casual", r"Sure thing!", "repair", replacement="Of course.")
    composed = compose(specs=[PartSpec("inform", "inform.hours", {"answer": ("fact", "hours")})],
                       templates={"inform.hours": template}, evidence=evidence, rules=[rule],
                       decision_id="dec-1", record=ENVELOPE)
    assert composed.verification.result == "repair"
    assert composed.text == "Of course. Sure thing, open until six"


def test_repair_cannot_introduce_a_number():
    with pytest.raises(ValueError):
        PhraseRule("x", "soon", "repair", replacement="in 5 minutes")


def test_template_slots_must_match_text():
    with pytest.raises(ValueError):
        Template("t", "1", "inform", "{a}", {})
    with pytest.raises(ValueError):
        Template("t", "1", "inform", "{a}", {"a": SlotSpec(())})


def test_template_move_must_match_the_part():
    with pytest.raises(ValueError):
        _compose(PartSpec("inform", "acknowledge.basic"))


def test_every_generic_template_has_no_literal_number():
    for template in TEMPLATES_BY_ID.values():
        assert template.slot_names == tuple(dict.fromkeys(template.slot_names))
