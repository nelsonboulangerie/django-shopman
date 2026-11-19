"""Regra de perguntar por custo do erro (v2 4.2) e restrição de conselheiro, substituto (i)."""

from __future__ import annotations

import pytest

from conversational_commerce.policy import AskEconomics, adheres_to_declared_need, resolve_ambiguity


@pytest.mark.parametrize(
    ("kind", "readings", "missing", "economics", "expected"),
    [
        ("change", 1, True, None, "ask"),  # campo obrigatório sempre se pergunta
        ("query", 1, False, None, "act"),
        ("query", 2, False, None, "cover_both"),
        ("change", 2, False, None, "ask"),  # mudança sem estimativa: pergunta
        ("change", 2, False, AskEconomics("0.6", "10", "1"), "ask"),  # (1-0.6)*10 = 4 > 1
        ("change", 2, False, AskEconomics("0.95", "10", "1"), "act"),  # 0.5 < 1
    ],
)
def test_resolve_ambiguity(kind, readings, missing, economics, expected):
    assert resolve_ambiguity(request_kind=kind, reading_count=readings, missing_required_field=missing,
                             economics=economics) == expected


def test_economics_are_decimal_text_and_bounded():
    with pytest.raises(ValueError):
        AskEconomics("1.5", "10", "1")
    with pytest.raises(ValueError):
        AskEconomics("0.5", "-1", "1")


def test_advisor_constraint_is_adherence_to_the_declared_need():
    assert adheres_to_declared_need({"size": "large", "diet": ["vegan", "vegetarian"]},
                                    {"size": "large", "diet": "vegan", "price": 10})
    assert not adheres_to_declared_need({}, {"size": "large"})  # sem necessidade declarada, não recomenda
    assert not adheres_to_declared_need({"diet": "vegan"}, {"size": "large"})  # desconhecido não é "sim"
    assert not adheres_to_declared_need({"size": "large"}, {"size": "small"})
