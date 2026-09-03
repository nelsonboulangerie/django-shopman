"""Typed exceptions raised by backstage mutation services."""

from __future__ import annotations


class BackstageServiceError(Exception):
    """Base class for operator-surface service errors."""


class AlertError(BackstageServiceError):
    """Raised when an alert mutation cannot be applied."""


class KDSError(BackstageServiceError):
    """Raised when a KDS mutation cannot be applied."""


class KDSTicketNotFound(KDSError):
    """Ticket inexistente.

    A camada HTTP mapeia por TIPO para 404 (recurso não existe), nunca 400 —
    mesmo padrão de ``PosRecentSaleNotFound``.
    """


class KDSOrderNotFound(KDSError):
    """Pedido inexistente numa ação de expedição. A camada HTTP mapeia para 404."""


class OrderError(BackstageServiceError):
    """Raised when an order mutation cannot be applied."""


class OrderConflict(OrderError):
    """Raised when the order changed state before the operator action landed.

    Ex.: recusar um pedido que a auto-confirmação acabou de confirmar. A camada
    HTTP mapeia para 409 (conflito de estado), não 400 (request inválido).
    """


class POSError(BackstageServiceError):
    """Raised when a POS mutation cannot be applied."""


class POSPermissionError(POSError):
    """Raised when a POS actor lacks permission (ex.: fechar caixa de outro)."""


class POSTerminalAmbiguous(POSError):
    """Mais de uma gaveta ativa e ninguém disse em qual se está trabalhando.

    A camada HTTP mapeia para 409 (conflito de estado), não 400 — mesmo padrão de
    ``OrderConflict`` e ``ProductionConflict``. O operador não errou nada: falta a loja
    dizer qual é o balcão dele.

    ⚠️ Só a MUTAÇÃO recusa. A leitura escolhe, porque derrubar o quadro do PDV por
    ambiguidade trocaria um problema por outro maior — ver ``pos.resolve_terminal``.
    """


class ProductionError(BackstageServiceError):
    """Raised when a production mutation cannot be applied."""


class ProductionConflict(ProductionError):
    """Raised when the work order changed state before the operator action landed.

    Ex.: dois quiosques fechando a mesma fornada, ou o gestor estornando
    enquanto o forneiro fecha. A camada HTTP mapeia para 409 (conflito de
    estado), não 400 — mesmo padrão de ``OrderConflict``.
    """


class CatalogError(BackstageServiceError):
    """Raised when a catalog mutation cannot be applied."""


class AiAssistNotConfigured(BackstageServiceError):
    """Assist de IA sem credencial.

    A camada HTTP mapeia por TIPO para 503 (dependência indisponível), nunca 400 —
    o pedido do operador estava certo; falta configuração no deployment.
    """


class AiAssistError(BackstageServiceError):
    """Raised when the AI assist call fails (provider error, empty completion)."""


class RecipeBookServiceError(BackstageServiceError):
    """Recusa do inventário de receitas, já traduzida para a porta HTTP.

    Embrulha o ``RecipeBookError`` do Craftsman: ``detail`` é a mensagem ao
    operador, ``field`` o campo ofensor (``items[2].sku``) e ``code`` o código
    original, que a camada HTTP usa para escolher 400 (campo) ou 409 (estado,
    ex.: ``VERSION_NOT_DRAFT``).
    """

    def __init__(self, detail: str, *, field: str = "", code: str = ""):
        super().__init__(detail)
        self.detail = detail
        self.field = field
        self.code = code


class RecipeEntryNotFound(BackstageServiceError):
    """Receita inexistente no inventário. A camada HTTP mapeia para 404."""


class RecipeVersionNotFound(BackstageServiceError):
    """Versão inexistente na receita. A camada HTTP mapeia para 404."""
