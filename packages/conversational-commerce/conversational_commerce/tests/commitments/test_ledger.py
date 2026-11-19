"""O livro dos compromissos: dono, prazo ou motivo da ausência, eventos distintos e prazo vencido uma vez."""

from __future__ import annotations

import pytest

from conversational_commerce.contracts import Known, Producer, Unknown
from conversational_commerce.contracts.commitment import DeadlineAbsent, DeadlineSet
from conversational_commerce.contracts.errors import ContractError
from conversational_commerce.ledger import (
    CommitmentLedger,
    CommitmentRefused,
    make_commitment,
    staff_deadline,
    staff_owner,
)
from conversational_commerce.profile.test_profile import build_test_profile

NOW = "2026-01-05T09:00:00.000000Z"
OPEN = Known(value={"open": True, "opens": "08:00", "closes": "18:00"}, source="clock", observed_at=NOW)
CLOSED = Known(value={"open": False, "opens": "08:00", "closes": "18:00"}, source="clock", observed_at=NOW)
PROFILE = build_test_profile()


def record(n: int = 1, at: str = NOW):
    return {"id": f"cmt-{n}", "tenant": "tenant-a", "environment": "test", "trace_id": "trace-1", "occurred_at": at,
            "producer": Producer(name="test", version="1"), "episode_id": "ep-1"}


def promise(owner="attendant", deadline=None):
    return make_commitment(record=record(), commitment_id="c-1", type="promise", obligation="answer",
                           owner=owner, deadline=deadline or staff_deadline(PROFILE, OPEN, NOW, "respond"),
                           criterion="answer delivered")


def ledger_with(commitment):
    ledger = CommitmentLedger()
    ledger.open(commitment, move="verify_with_staff", need=None, binding=None, recipient="subject-1")
    return ledger


@pytest.mark.parametrize("owner", [None, ""])
def test_no_possible_owner_means_no_promise(owner):
    """N04: sem dono possível, não se promete; "encaminhei" sem destinatário é barrado na origem."""
    with pytest.raises(CommitmentRefused) as refused:
        promise(owner=owner)
    assert refused.value.code == "no_owner_possible"


def test_owner_comes_from_the_declared_queue_and_the_staff_adapter():
    assert staff_owner(PROFILE, "ask") == "attendant"
    assert staff_owner(build_test_profile(staff_queue=None), "ask") is None
    without_ask = build_test_profile(adapters={"commerce": (), "channel": (), "staff": ("assign",)})
    assert staff_owner(without_ask, "ask") is None


def test_deadline_is_the_queue_window_inside_business_hours():
    deadline = staff_deadline(PROFILE, OPEN, NOW, "respond")
    assert isinstance(deadline, DeadlineSet)
    assert deadline.at == "2026-01-05T09:30:00.000000Z"
    assert deadline.rule_ref == "staff_queue.respond_within_seconds"
    assert staff_deadline(PROFILE, OPEN, NOW, "accept").at == "2026-01-05T09:10:00.000000Z"


@pytest.mark.parametrize(("hours", "reason"), [(CLOSED, "outside_business_hours"),
                                                 (Unknown(reason="source_failed"), "business_hours_unknown")])
def test_absent_deadline_comes_with_reason_and_contingency(hours, reason):
    """Não se afirma prazo que ninguém definiu: fora do expediente, ou sem saber, o prazo é ausente."""
    deadline = staff_deadline(PROFILE, hours, NOW, "respond")
    assert isinstance(deadline, DeadlineAbsent)
    assert deadline.absent_reason == reason
    assert deadline.contingency == "inform_and_wait"


def test_acknowledge_accept_and_fulfil_are_distinct_events():
    ledger = ledger_with(promise())
    ledger.advance("c-1", record_id="cmt-2", at=NOW, cause_id="ticket-1", state="accepted", owner="staff-1")
    ledger.advance("c-1", record_id="cmt-3", at=NOW, cause_id="ticket-1", state="fulfilled", evidence=("ticket-1",))
    assert ledger.events_of("c-1") == ["acknowledged", "accepted", "fulfilled"]
    history = ledger.entries["c-1"].history
    assert [c.state for c in history] == ["open", "accepted", "fulfilled"]
    assert history[0].state == "open"  # o registro anterior fica como estava (N14)
    assert len({c.id for c in history}) == 3


def test_fulfilment_requires_evidence_and_transitions_are_checked():
    ledger = ledger_with(promise())
    with pytest.raises(ContractError):
        ledger.advance("c-1", record_id="cmt-2", at=NOW, cause_id="x", state="fulfilled")
    ledger = ledger_with(promise())
    ledger.advance("c-1", record_id="cmt-2", at=NOW, cause_id="x", state="fulfilled", evidence=("ticket-1",))
    with pytest.raises(CommitmentRefused) as refused:
        ledger.advance("c-1", record_id="cmt-3", at=NOW, cause_id="x", state="accepted")
    assert refused.value.code == "invalid_transition"
    reopened = ledger.advance("c-1", record_id="cmt-4", at=NOW, cause_id="x", state="reopened")
    assert reopened.reopened_from == "cmt-2"


def test_each_overdue_deadline_is_an_event_once():
    ledger = ledger_with(promise())
    assert ledger.due("2026-01-05T09:29:00.000000Z") == []
    assert [e.commitment_id for e in ledger.due("2026-01-05T09:31:00.000000Z")] == ["c-1"]
    assert ledger.due("2026-01-05T09:32:00.000000Z") == []
    absent = DeadlineAbsent(absent_reason="outside_business_hours", contingency="inform_and_wait")
    assert ledger_with(promise(deadline=absent)).due("2027-01-01T00:00:00.000000Z") == []
