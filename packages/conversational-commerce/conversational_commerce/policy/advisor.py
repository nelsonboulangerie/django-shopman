"""Restrição de conselheiro (v2 4.3), só com o substituto (i): aderência à necessidade declarada.

Uma ação comercial só é elegível se não piora o cliente em expectativa. No
começo, o único substituto disponível de ``u_c`` é a aderência ao que o
cliente DISSE precisar: toda exigência declarada tem de ser atendida pelo que
se oferece. Aceite da oferta não é substituto (é o que a persuasão infla), e
exigência desconhecida no item é não atendida, nunca "provavelmente sim".
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def adheres_to_declared_need(declared: Mapping[str, Any], offer: Mapping[str, Any]) -> bool:
    """Verdadeiro só se a necessidade foi declarada e o item atende cada exigência dela."""
    if not declared:
        return False  # sem necessidade declarada não há o que aderir
    for attribute, wanted in declared.items():
        if attribute not in offer:
            return False
        have = offer[attribute]
        if isinstance(wanted, list | tuple | set | frozenset):
            if have not in wanted:
                return False
        elif have != wanted:
            return False
    return True
