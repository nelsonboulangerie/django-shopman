"""Handler da diretiva ``concierge.turn``: roda o turno do concierge no worker.

O webhook guarda a mensagem e enfileira; quem fala com o modelo é este handler,
no ``process_directives --watch``. Uma diretiva por conversa (dedupe), e o
turno responde TUDO que chegou desde a última resposta. Se chegou mensagem
nova enquanto o modelo respondia, ``pending_more`` vem ligado e o handler roda
de novo, até um teto, em vez de deixar a mensagem esperando a próxima.

Falha do provedor (rede, 429, 5xx) é transitória: o worker tenta de novo com
backoff. Conversa que não existe é terminal: não há o que tentar.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.models import Conversation
from shopman.storefront.concierge import service

logger = logging.getLogger(__name__)

#: Quantas vezes o turno roda em sequência quando mensagens continuam chegando.
MAX_LOOPS = 5


def _is_transient(exc: BaseException) -> bool:
    """Erro do provedor que vale retry: conexão, timeout, 429, 5xx."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependência do concierge
        return False
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.RateLimitError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", 0) or 0
        return status >= 500 or status == 429
    return False


class ConciergeTurnHandler:
    """Responde pelo vínculo causal indicado pela diretiva v3."""

    topic = service.TURN_TOPIC

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload or {}
        if payload.get("contract_version") != 3:
            raise DirectiveTerminalError("unsupported concierge contract")
        conversation_id = payload.get("conversation_id")
        binding_id = payload.get("binding_id")
        if not conversation_id or not binding_id:
            raise DirectiveTerminalError("missing conversation_id or binding_id")

        for loop in range(1, MAX_LOOPS + 1):
            try:
                result = service.run_turn(int(conversation_id), int(binding_id))
            except Conversation.DoesNotExist as exc:
                raise DirectiveTerminalError(f"Conversation not found: {conversation_id}") from exc
            except Exception as exc:
                if _is_transient(exc):
                    raise DirectiveTransientError(f"concierge provider: {exc}") from exc
                raise
            if not result.pending_more:
                return
            logger.info(
                "concierge.turn: mensagens novas durante o turno, rodando de novo (%d/%d) conversation=%s",
                loop, MAX_LOOPS, conversation_id,
            )
        # Deferir a MESMA Directive: fairness sem consumir tentativas nem criar
        # outra fila. O dispatcher preserva status alterado pelo handler.
        message.status = "queued"
        message.available_at = timezone.now() + timedelta(seconds=1)
        message.attempts = 0
        message.save(update_fields=["status", "available_at", "attempts", "updated_at"])
