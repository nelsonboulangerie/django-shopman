"""Fronteira do orquestrador com os episódios de operação (backstage).

O episódio é fato da operação da instância e mora no backstage, junto com o
fechamento que o coleta (mesmo lugar de ``KDSTicket`` e ``OvenRun``). Mas quem
decide o que a fórmula de produção aprende é o orquestrador — e ele não pode
alcançar o backstage direto (a regra de dependência só abre exceção aqui, em
``adapters/``, como já acontece com o KDS).

Degrada para vazio: sem episódios legíveis a sugestão perde precisão e segue
funcionando. Nunca o contrário.
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def disrupted_days(*, since: date, until: date) -> frozenset[date]:
    """Dias atrapalhados por algum episódio — não devem ensinar demanda."""
    try:
        from shopman.backstage.services.episodes import disrupted_days as _read

        return _read(since=since, until=until)
    except Exception:
        logger.debug("leitura de episódios indisponível", exc_info=True)
        return frozenset()
