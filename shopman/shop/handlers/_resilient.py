"""Blindagem da cauda NÃO-crítica do fan-out de ``production_changed``.

O sinal ``production_changed`` sai com ``.send()`` (propaga a exceção de
QUALQUER receiver e aborta os posteriores + o caller), FORA do ``atomic`` do
``CraftExecution.finish`` e DEPOIS do commit. Junte a isso o replay idempotente
— o segundo ``finish`` com a mesma ``idempotency_key`` devolve a WO existente
ANTES do ``.send()``, então NÃO reemite o sinal — e um receiver cosmético que
estoura uma vez deixa dois estragos permanentes:

- a fornada está 100% commitada e mesmo assim o operador leva 500;
- os efeitos POSTERIORES daquele receiver (sync de pedido, SSE, FOMO, campanha,
  aviso ao cliente) nunca rodam, e o retry idempotente também não os refaz.

A cura é cirúrgica: cada receiver da cauda não-crítica encapsula o próprio corpo
aqui, para NUNCA abortar a cadeia nem o caller. O erro vira log com traceback
(chega ao Sentry), não exceção.

⚠️ Isto é SÓ para a cauda cosmética. A perna de ESTOQUE (``craftsman.contrib.
stockman.handlers.handle_production_changed``, o receiver #0, que roda antes de
tudo) continua podendo GRITAR: dinheiro/estoque falha alto, nunca calado (ver
``feedback_falhar_fechado_ou_falhar_gritando``). Blindar a perna de estoque com
isto seria o oposto do que a casa quer.

O sync de pedido↔fornada É blindado aqui, mas não fica órfão: ele ganhou uma
rede de segurança no caminho guardado do finish
(``shopman.shop.services.production._ensure_order_links_closed``, irmã de
``_ensure_stock_ledger_closed``) que reconstrói o vínculo — idempotente — mesmo
quando o receiver de sinal estoura ou quando o replay não reemite o sinal. Sem
essa rede, blindá-lo deixaria o vínculo órfão; por isso as duas mudanças andam
juntas.
"""

from __future__ import annotations

import functools
import logging

logger = logging.getLogger(__name__)


def resilient_receiver(fn):
    """Torna um receiver não-crítico de ``production_changed`` à prova de aborto.

    Preserva ``__name__``/``__module__`` (via :func:`functools.wraps`) para a
    introspecção da ordem de conexão e para logs continuarem legíveis. O retorno
    é sempre ``None`` no caminho de erro — o resultado de um receiver de sinal é
    descartado pelo dispatcher de qualquer forma.
    """

    @functools.wraps(fn)
    def _wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception(
                "production_changed: receiver não-crítico %s.%s estourou — "
                "engolido para não abortar a fornada nem a cauda de receivers",
                getattr(fn, "__module__", "?"),
                getattr(fn, "__name__", "?"),
            )
            return None

    return _wrapped
