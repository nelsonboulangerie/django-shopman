"""Conexão de banco cuja thread morreu volta ao pool.

O furo (incidente do alpha, 14/10/2026): sob ASGI, o Django roda o código síncrono
de cada request (os middlewares síncronos, a view, a permissão do canal SSE) numa
thread do request, via ``sync_to_async``/``async_to_sync``. Quando o cliente desiste
no meio (aba fechada, troca de página, o BFF abortando o upstream do
``EventSource``), o Django cancela o request. Thread não se cancela: ela termina o
trabalho e abre a conexão (a sessão, o usuário, a view) DEPOIS que o
``request_finished`` já fechou as conexões que o request enxergava. Essa ninguém
fecha. Com o pool do psycopg (``OPTIONS["pool"]``, ``config/settings.py``) é
capacidade perdida para sempre: 8 desistências no momento errado e todo request
passa a esperar 10 s e cair com ``PoolTimeout``. Sem pool, a mesma conexão ficava
aberta até o coletor de lixo.

A conta é feita por DONO: toda conexão aberta (``connection_created``, inclusive
cada uma tirada do pool) fica anotada com a thread que a abriu. No
``request_started`` de cada request, as conexões abertas cuja thread já terminou
voltam ao pool. Thread morta não corre com ninguém, então devolver é seguro; a
thread de um request ASGI termina logo depois dele (o executor do
``ThreadSensitiveContext`` é desligado na saída), e qualquer request seguinte, até a
sonda de saúde, faz a devolução.

Thread viva nunca é tocada. Um ``EventSource`` aberto o dia todo mantém a sua thread
viva, e a conexão dele já volta ao pool a cada leitura (``shop/eventstream.py``).
"""

from __future__ import annotations

import logging
import threading
import weakref

logger = logging.getLogger(__name__)

#: ``DatabaseWrapper`` → a thread que abriu a conexão. Chave fraca: wrapper coletado
#: sai sozinho; entrada com a conexão já fechada sai na próxima varredura.
_owners: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_lock = threading.Lock()


def remember_owner(sender, connection, **kwargs) -> None:
    """``connection_created``: anota a thread dona da conexão."""
    with _lock:
        _owners[connection] = threading.current_thread()


def reclaim_dead_thread_connections(**kwargs) -> int:
    """``request_started``: devolve ao pool as conexões cuja thread dona terminou.

    Devolve quantas voltaram. Nunca levanta: a varredura não derruba o request que
    a disparou.
    """
    orphans = []
    with _lock:
        for wrapper, owner in list(_owners.items()):
            if wrapper.connection is None:
                del _owners[wrapper]
            elif not owner.is_alive():
                del _owners[wrapper]
                orphans.append(wrapper)
    reclaimed = 0
    for wrapper in orphans:
        # O wrapper é da thread morta; a validação de thread do Django só aceita
        # outro chamador com o compartilhamento declarado.
        wrapper.inc_thread_sharing()
        try:
            wrapper.close()
        except Exception:  # noqa: BLE001
            logger.warning("db_connection_orphan_reclaim_failed alias=%s", wrapper.alias, exc_info=True)
            continue
        finally:
            wrapper.dec_thread_sharing()
        reclaimed += 1
    if reclaimed:
        logger.warning("db_connection_orphan_reclaimed count=%d", reclaimed)
    return reclaimed


def connect() -> None:
    from django.core.signals import request_started
    from django.db.backends.signals import connection_created

    connection_created.connect(remember_owner, dispatch_uid="shopman.orphan_connections.owner")
    request_started.connect(reclaim_dead_thread_connections, dispatch_uid="shopman.orphan_connections.reclaim")
