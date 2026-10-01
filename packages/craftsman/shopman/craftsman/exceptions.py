"""
Craftsman Exceptions.

All Craftsman errors are wrapped in CraftError for consistent handling.
"""

from shopman.utils.exceptions import BaseError


class CraftError(BaseError):
    """
    Base exception for all Craftsman errors.

    Usage:
        raise CraftError('INVALID_STATUS', current='started', expected='planned')
        raise CraftError('INVALID_QUANTITY', quantity=-1)

    Attributes:
        code: Error code (INVALID_QUANTITY, TERMINAL_STATUS, etc.)
        message: Human-readable description
        data: Additional context as keyword arguments
    """

    _default_messages = {
        "INVALID_QUANTITY": "Quantity must be greater than zero",
        "INVALID_REF": "Reference must be a non-empty string",
        "INVALID_PAYLOAD": "Payload item must be an object",
        "INVALID_STATUS": "Work order is not in the expected status for this operation",
        "TERMINAL_STATUS": "Cannot modify a work order in terminal status",
        "VOID_FROM_DONE": "Cannot void a completed work order",
        "STALE_REVISION": "Work order was modified by another process",
        "BOM_CYCLE": "BOM expansion exceeded maximum depth",
        "RECIPE_NOT_FOUND": "Recipe not found",
        "AMBIGUOUS_RECIPE": "More than one active recipe exists for this output SKU",
        "WORK_ORDER_NOT_FOUND": "Work order not found",
        "COMMITTED_HOLDS": "Quantity below committed orders for this date",
        "INSUFFICIENT_MATERIALS": "Insufficient shared ingredients for rescheduled quantity",
        "DOWNSTREAM_DEFICIT": "Reducing this work order creates ingredient shortage for downstream production",
        "IDEMPOTENCY_CONFLICT": "Idempotency key was already used for another work order",
    }


class RecipeBookError(CraftError):
    """Erro do inventário de receitas (RecipeEntry / RecipeVersion).

    ``FORMULA_INVALID`` carrega o caminho do campo ofensor em ``data["field"]``
    (ex.: ``items[2].quantity``) para a tela apontar a linha certa.
    """

    _default_messages = {
        **CraftError._default_messages,
        "FORMULA_INVALID": "A fórmula não segue o schema esperado.",
        "ENTRY_WITHOUT_SKU": "A receita precisa de um SKU de saída para ser publicada.",
        "ITEM_WITHOUT_SKU": "Todo ingrediente precisa de um insumo associado para publicar.",
        "VERSION_NOT_DRAFT": "Só um rascunho pode ser editado ou publicado.",
        "PART_WITHOUT_FORMULA": "A parte não tem fórmula conhecida; publique a receita da parte antes.",
        "PART_EXCEEDS_BASE": "A parte contém mais de um ingrediente do que a receita base declara.",
        "ENTRY_ARCHIVED": "A receita está arquivada.",
        "ANCHOR_EMPTY": "A âncora da fórmula soma zero; não há como padronizar.",
    }


class StaleRevision(CraftError):
    """Raised when expected_rev does not match the current rev."""

    def __init__(self, order, expected_rev):
        super().__init__(
            "STALE_REVISION",
            expected_rev=expected_rev,
            current_rev=order.rev,
            work_order=order.ref,
        )
