"""Receita favorita do operador: marcar, desmarcar e ler (idempotente).

Espelho de ``storefront.services.favorites`` com os eixos trocados: o operador
(``username``) no lugar do cliente, a receita do inventário (``RecipeEntry.ref``)
no lugar do SKU. Quem confere que a receita existe é a view (404 antes de
chegar aqui); este módulo só grava e lê a preferência.
"""

from __future__ import annotations

from shopman.backstage.models import OperatorRecipeFavorite


def mark(operator_ref: str, entry_ref: str) -> bool:
    """Marca a receita como favorita do operador. Idempotente; devolve ``True``."""
    if not operator_ref or not entry_ref:
        return False
    OperatorRecipeFavorite.objects.get_or_create(operator_ref=operator_ref, entry_ref=entry_ref)
    return True


def unmark(operator_ref: str, entry_ref: str) -> bool:
    """Desmarca. Idempotente; devolve ``False`` (não é mais favorita)."""
    if operator_ref and entry_ref:
        OperatorRecipeFavorite.objects.filter(operator_ref=operator_ref, entry_ref=entry_ref).delete()
    return False


def favorite_refs(operator_ref: str) -> set[str]:
    """As refs que este operador marcou (para o ``is_favorite`` dos cartões)."""
    if not operator_ref:
        return set()
    return set(
        OperatorRecipeFavorite.objects.filter(operator_ref=operator_ref).values_list("entry_ref", flat=True)
    )


def is_favorite(operator_ref: str, entry_ref: str) -> bool:
    if not operator_ref or not entry_ref:
        return False
    return OperatorRecipeFavorite.objects.filter(operator_ref=operator_ref, entry_ref=entry_ref).exists()
