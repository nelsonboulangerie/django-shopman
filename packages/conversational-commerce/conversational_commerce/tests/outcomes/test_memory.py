"""Memória declarada: correção e vencimento alcançam recuperação e resumo (K28)."""

from __future__ import annotations

import pytest

from conversational_commerce.contracts import MemoryItem
from conversational_commerce.memory import MemoryRefused, MemoryStore
from conversational_commerce.testing.conformance import conformance

from .helpers import NOW, record

LATER = "2026-01-06T09:00:00.000000Z"


def item(n, value, *, category="diet", valid_until=None, sensitivity="ordinary", evidence="declared", **extra):
    return MemoryItem(**record(n), memory_id=f"mem-{n}", subject_ref="subject-1", category=category, value=value,
                      evidence_state=evidence, source=f"event-{n}", purpose="service", sensitivity=sensitivity,
                      valid_until=valid_until, **extra)


@conformance("K28", scope="core")
def test_k28_corrected_or_expired_memory_never_reappears_in_recall_or_summary():
    memory = MemoryStore()
    memory.declare(item(1, "no sugar"))
    memory.declare(item(2, "pickup", category="delivery", valid_until="2026-01-05T12:00:00.000000Z"))
    before = memory.summary("subject-1", NOW)
    assert before.value == {"diet": "no sugar", "delivery": "pickup"}

    memory.correct("mem-1", new=item(3, "no lactose"))
    after = memory.summary("subject-1", NOW)
    assert after.value == {"diet": "no lactose", "delivery": "pickup"} and "mem-1" not in after.sources
    assert [m.memory_id for m in memory.recall("subject-1", NOW)] == ["mem-2", "mem-3"]

    # Vencido some da recuperação e do resumo, sem ninguém pedir.
    expired = memory.summary("subject-1", LATER)
    assert expired.value == {"diet": "no lactose"} and expired.sources == ("mem-3",)
    assert "no sugar" not in str(expired.value) and "pickup" not in str(expired.value)
    # O histórico fica: o corrigido não é apagado, só deixa de valer.
    assert [m.memory_id for m in memory.history] == ["mem-1", "mem-2", "mem-3"]


def test_derived_summary_is_rebuilt_not_served_stale():
    memory = MemoryStore()
    memory.declare(item(1, "no sugar"))
    calls = []

    def render(items):
        calls.append(tuple(i.memory_id for i in items))
        return ", ".join(i.value for i in items)

    assert memory.summary("subject-1", NOW, render).value == "no sugar"
    assert memory.summary("subject-1", NOW, render).value == "no sugar"
    memory.correct("mem-1", new=item(2, "no lactose"))
    assert memory.summary("subject-1", NOW, render).value == "no lactose"
    assert calls == [("mem-1",), ("mem-2",)]


def test_only_declared_and_sensitive_only_with_confirmation():
    memory = MemoryStore()
    with pytest.raises(MemoryRefused) as refused:
        memory.declare(item(1, "likes fridays", evidence="inferred"))
    assert refused.value.code == "not_declared"
    with pytest.raises(MemoryRefused) as refused:
        memory.declare(item(2, "nut allergy", category="allergy", sensitivity="sensitive"))
    assert refused.value.code == "sensitive_needs_confirmation"
    memory.declare(item(3, "nut allergy", category="allergy", sensitivity="sensitive"), confirmed=True)
    assert memory.value("subject-1", "allergy", NOW) == "nut allergy"


def test_correction_keeps_the_referent_and_supersedes_once():
    memory = MemoryStore()
    memory.declare(item(1, "no sugar"))
    with pytest.raises(MemoryRefused) as refused:
        memory.correct("mem-1", new=item(2, "pickup", category="delivery"))
    assert refused.value.code == "correction_changes_referent"
    memory.correct("mem-1", new=item(3, "no lactose"))
    with pytest.raises(MemoryRefused) as refused:
        memory.correct("mem-1", new=item(4, "no gluten"))
    assert refused.value.code == "already_superseded"
