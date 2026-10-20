"""Coleções exclusivas de grupo: o membro enxerga; o resto, anônimo incluído, não."""

from __future__ import annotations

from shopman.shop.policies.exclusive_collections import collection_access

ROWS = [
    ("alianca", {"collection_refs": ["cardapio-alianca", "doces"]}),
    ("equipe", {"collection_refs": ["equipe"]}),
    ("vazio", {}),
    ("nulo", None),
]


def test_exclusive_collections_truth_table() -> None:
    anon = collection_access(ROWS)
    assert anon.hidden == {"cardapio-alianca", "doces", "equipe"}
    assert anon.is_hidden("doces") and not anon.is_hidden("paes") and not anon.is_hidden("")

    alianca = collection_access(ROWS, member_of=["alianca"])
    assert alianca.hidden == {"equipe"}
    assert not alianca.is_hidden("doces")

    both = collection_access(ROWS, member_of=["alianca", "equipe"])
    assert both.hidden == frozenset()  # dois grupos: enxerga as dos dois, nada compete

    assert collection_access([]).hidden == frozenset()
