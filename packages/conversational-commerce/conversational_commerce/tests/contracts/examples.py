"""Um documento válido de cada um dos 17 contratos, para os testes que varrem todos.

Cada função devolve um documento novo (pode ser mutado pelo teste). Os de hash
saem selados.
"""

from __future__ import annotations

import copy
from typing import Any

from conversational_commerce.contracts import (
    CONTRACTS,
    ContextSnapshot,
    Record,
    TermsDocument,
    command_content_hash,
    seal,
)

T0 = "2026-11-18T14:00:00.000000Z"
T1 = "2026-11-18T14:10:00.000000Z"
T2 = "2026-11-18T14:30:00.000000Z"


def envelope(contract: type[Record], **extra: Any) -> dict[str, Any]:
    return {
        "schema": contract.SCHEMA,
        "kind": contract.KIND,
        "schema_version": contract.VERSION,
        "id": f"rec-{contract.KIND.lower()}",
        "tenant": "tenant-a",
        "environment": "test",
        "trace_id": "trace-1",
        "occurred_at": T0,
        "producer": {"name": "core", "version": "0.1.0"},
        "episode_id": "ep-1",
        **extra,
    }


UNAVAILABLE = {"status": "unavailable", "reason": "no_estimator"}


def _sealed(contract: type[Record], document: dict[str, Any]) -> dict[str, Any]:
    """O documento com o hash que o produtor calcula (``seal``)."""
    body = {key: value for key, value in document.items() if key not in ("schema", "kind")}
    return {**document, "hash": seal(contract(**body)).hash}


def interaction_event() -> dict[str, Any]:
    return envelope(
        CONTRACTS[0],
        channel_binding={"channel": "chat", "conversation_ref": "conv-1"},
        actor="customer",
        event_identity={"id": "provider-msg-1", "assurance": "provider_claimed"},
        type="message",
        content_ref="vault://msg/1",
        identity_evidence=[{"kind": "channel_identity", "ref": "binding-1", "assurance": "transported"}],
    )


def understanding() -> dict[str, Any]:
    return envelope(
        CONTRACTS[1],
        event_id="evt-1",
        acts=[
            {
                "act": "ask_availability",
                "fields": {"item": "SKU-A", "quantity": "2"},
                "span": {"start": 0, "end": 12},
                "confidence": {"status": "estimate", "value": "0.82", "method": "calibrated_reader",
                               "population": "labelled-2026-11", "version": "1"},
            }
        ],
        alternatives=[{"acts": [{"act": "place_order", "fields": {}, "confidence": UNAVAILABLE}],
                       "confidence": UNAVAILABLE}],
        signals={"friction": "low", "risk": "none"},
        reader={"name": "rule-reader", "version": "3"},
    )


def context_snapshot() -> dict[str, Any]:
    document = envelope(
        ContextSnapshot,
        episode_version=4,
        ownership_epoch=1,
        identity={"subject_ref": "customer-1", "assurance": "transported"},
        needs=[{"need_id": "n1", "type": "availability", "state": "open"}],
        facts={
            "stock.SKU-A": {"status": "known", "value": {"available": "3", "unit": "unit"}, "source": "commerce",
                            "observed_at": T0, "valid_until": T1, "source_version": "v9"},
            "hours.today": {"status": "unknown", "reason": "source_failed"},
        },
        hypotheses=[{"claim": "pickup_today", "value": True, "confidence": UNAVAILABLE}],
        unknowns=["delivery_window"],
        dialogue_state={"open_question": None, "focus": "SKU-A"},
        relationship_state={},
        open_commitments=["c-1"],
        profile_ref={"id": "profile-test", "version": "1"},
        policy_ref={"id": "moves", "version": "2026.11.1"},
    )
    return _sealed(ContextSnapshot, document)


def candidate_action() -> dict[str, Any]:
    return envelope(
        CONTRACTS[3],
        candidate_id="cand-1",
        need_id="n1",
        move="inform",
        move_version="1",
        content={"facts": ["stock.SKU-A"]},
        preconditions=[{"code": "fact_known", "result": "pass", "evidence": "stock.SKU-A"}],
        reversibility="none_needed",
        authority_required="A0",
        confirmation_required=False,
        prediction=UNAVAILABLE,
    )


def decision_record() -> dict[str, Any]:
    return envelope(
        CONTRACTS[4],
        decision_id="dec-1",
        turn=7,
        context={"snapshot_ref": "rec-contextsnapshot", "snapshot_hash": context_snapshot()["hash"]},
        candidates=[
            {"candidate_ref": "cand-1", "need_id": "n1", "move": "inform", "content": {"facts": ["F1"]},
             "eligible": True, "prediction": UNAVAILABLE},
            {"candidate_ref": "cand-2", "need_id": "n1", "move": "recommend", "content": {"ref": "SKU-B"},
             "eligible": False, "blocked_by": ["advisor_constraint"], "prediction": UNAVAILABLE},
        ],
        chosen=[0],
        selection={"method": "deterministic", "tie_break": "catalog_order", "propensity": {"status": "not_applicable"}},
        policy={"id": "moves", "version": "2026.11.1"},
        profile={"id": "profile-test", "version": "1"},
        model_calls=[{"model": {"name": "fake-reader", "version": "1"}, "purpose": "read"}],
    )


def terms_document() -> dict[str, Any]:
    document = envelope(
        TermsDocument,
        terms_id="terms-1",
        version=1,
        items=[{"ref": "SKU-A", "quantity": {"value": "2", "unit": "unit"},
                "unit_price": {"amount_minor": 750, "currency": "BRL"},
                "line_total": {"amount_minor": 1500, "currency": "BRL"}}],
        total={"amount_minor": 1500, "currency": "BRL"},
        recipient={"subject_ref": "customer-1"},
        fulfillment={"mode": "pickup"},
        valid_until=T2,
    )
    return _sealed(TermsDocument, document)


def authorization_grant() -> dict[str, Any]:
    return envelope(
        CONTRACTS[6],
        grant_id="grant-1",
        subject="customer-1",
        issuer="core",
        basis="customer_confirmation",
        purpose="place_order",
        action="commit_order",
        targets=["terms-1"],
        terms_hash=terms_document()["hash"],
        limits={"max_uses": 1},
        identity_evidence=[{"kind": "channel_identity", "ref": "binding-1", "assurance": "transported"}],
        confirmation_evidence={"event_id": "evt-2", "event_assurance": "provider_claimed", "after_terms": True},
        valid_from=T0,
        valid_until=T1,
    )


def action_command() -> dict[str, Any]:
    parameters = {"note": "sem cebola", "quantity": "2"}
    terms_hash = terms_document()["hash"]
    return envelope(
        CONTRACTS[7],
        command_id="cmd-1",
        decision_id="dec-1",
        grant_id="grant-1",
        action="commit_order",
        targets=["terms-1"],
        parameters=parameters,
        terms_hash=terms_hash,
        expected_versions={"episode": 4, "cart": 2},
        expected_ownership_epoch=1,
        idempotency={"scope": "commit_order", "key": "ep-1:terms-1:v1"},
        content_hash=command_content_hash(action="commit_order", targets=("terms-1",), parameters=parameters,
                                          terms_hash=terms_hash),
        deadline=T1,
    )


def action_receipt() -> dict[str, Any]:
    return envelope(
        CONTRACTS[8],
        command_id="cmd-1",
        status="success",
        effect="applied",
        domain_refs={"order": "order-1"},
        observed_versions={"cart": 3},
    )


def reply_plan() -> dict[str, Any]:
    return envelope(
        CONTRACTS[9],
        decision_id="dec-1",
        parts=[
            {"move": "acknowledge", "claims": [{"slot": "greeting", "backing": "courtesy"}]},
            {"move": "inform", "claims": [{"slot": "stock", "backing": "fact", "ref": "stock.SKU-A"}]},
        ],
        locked_blocks=["price"],
        verification={"result": "pass"},
    )


def exposure_event() -> dict[str, Any]:
    return envelope(
        CONTRACTS[10],
        decision_id="dec-1",
        content_hash="sha256:" + "a" * 64,
        realizer={"name": "template-realizer", "version": "2"},
        recipient="customer-1",
        attempt=1,
        state="accepted",
    )


def outcome_event() -> dict[str, Any]:
    return envelope(
        CONTRACTS[11],
        customer_ref="customer-1",
        metric={"id": "repurchase_30d", "definition_version": "1"},
        window={"start": T0, "end": T2},
        observation="censored",
        source="order_ledger",
        decision_ids=["dec-1"],
    )


def episode() -> dict[str, Any]:
    return envelope(
        CONTRACTS[12],
        subject="customer-1",
        state="waiting_input",
        version=4,
        ownership={"owner": "automation", "epoch": 1},
        needs=["n1"],
        waits=[{"condition": "customer answers the open question", "owner": "core", "deadline": T2}],
        opened_at=T0,
    )


def need() -> dict[str, Any]:
    return envelope(CONTRACTS[13], need_id="n1", type="availability", state="open")


def commitment() -> dict[str, Any]:
    return envelope(
        CONTRACTS[14],
        commitment_id="c-1",
        type="promise",
        obligation="confirm with staff whether SKU-A can be sliced",
        owner="staff-queue",
        deadline={"status": "set", "at": T2, "rule_ref": "staff_verification_30m"},
        fulfillment_criterion="customer receives the staff answer",
        state="open",
    )


def memory_item() -> dict[str, Any]:
    return envelope(
        CONTRACTS[15],
        memory_id="m-1",
        subject_ref="customer-1",
        category="preference",
        value={"item": "SKU-A", "note": "sliced"},
        evidence_state="declared",
        source="evt-1",
        purpose="service",
        sensitivity="personal",
    )


def deployment_profile() -> dict[str, Any]:
    return envelope(
        CONTRACTS[16],
        version="1",
        adapters={"commerce": ["quote", "commit"], "channel": ["send", "delivery_receipts"]},
        catalog_version="1",
        policy_version="2026.11.1",
        actions={
            "commit_order": {"authority": "A3", "min_identity": {"chat": "transported"}, "confirmation": True,
                             "line_ref": "line-commit"},
            "grant_discount": {"authority": "A4", "min_identity": {"chat": "weak_verified"}, "confirmation": True,
                               "caps": ["one_per_order"], "line_ref": "line-discount-cap"},
        },
        lines=[
            {"id": "line-commit", "setting": {"status": "set", "value": True}, "owner": "owner",
             "decided_at": T0, "state": "approved"},
            {"id": "line-discount-cap", "setting": {"status": "absent", "reason": "owner has not decided"},
             "owner": "owner", "state": "proposed"},
        ],
        fact_sources={"stock": {"source": "commerce", "validity_rule": "5m"}},
        staff_queue={"role": "attendant", "nominal_acceptance": True, "accept_within_seconds": 600,
                     "respond_within_seconds": 1800, "after_hours_contingency": "next_opening"},
        limits={"max_steps": 6, "max_seconds": 20, "max_queries": 10, "max_model_calls": 0,
                "max_spend": {"amount_minor": 0, "currency": "BRL"}},
        privacy={"purposes": ["service"], "retention_days": {"transcript": 30},
                 "fields_by_recipient": {"reader-model": ["text_redacted"]}},
        metrics=[{"id": "repurchase_30d", "definition_version": "1", "window_seconds": 2592000,
                  "design": "observational"}],
    )


BUILDERS = {
    "cc.interaction_event": interaction_event,
    "cc.understanding": understanding,
    "cc.context_snapshot": context_snapshot,
    "cc.candidate_action": candidate_action,
    "cc.decision_record": decision_record,
    "cc.terms_document": terms_document,
    "cc.authorization_grant": authorization_grant,
    "cc.action_command": action_command,
    "cc.action_receipt": action_receipt,
    "cc.reply_plan": reply_plan,
    "cc.exposure_event": exposure_event,
    "cc.outcome_event": outcome_event,
    "cc.episode": episode,
    "cc.need": need,
    "cc.commitment": commitment,
    "cc.memory_item": memory_item,
    "cc.deployment_profile": deployment_profile,
}


def example(contract: type[Record]) -> dict[str, Any]:
    return copy.deepcopy(BUILDERS[contract.SCHEMA]())
