"""Memo que vive um request — e só um.

O caminho quente do storefront pergunta pelo MESMO canal várias vezes num
request: a cascata do ``ChannelConfig`` (cardápio, disponibilidade, fila de
espera, bundle), o "está recebendo pedidos?" da home e a política de superfície.
Cada pergunta era uma consulta à tabela ``Channel`` (seis linhas), e era daí que
vinham os ~100 mil seq scans por dia nela.

O memo é um ``ContextVar`` aberto por :class:`RequestMemoMiddleware` no começo do
request e descartado no fim. Fora de um request (comando, worker, teste que chama
a função direto) não há memo e tudo consulta o banco como sempre. Não é cache
global de propósito: o estado do canal muda (toggle, agenda, Admin) e o request
seguinte tem de ver o valor novo. Se o próprio request grava um ``Channel`` ou o
``Shop``, o ``post_save``/``post_delete`` esvazia o memo e a leitura seguinte vai
ao banco.

O ``Shop.load()`` também passa por aqui: era o campeão de idas ao Redis do
cardápio (6 de 10 ``GET`` por request, todos da mesma chave ``shop_singleton``).
Também passam o ``ChannelConfig`` montado das leituras de estoque
(:func:`channel_config`) e o registro de atributos
(``services.attributes.registry``).

Leituras de estoque têm um memo à parte, mais estreito (:func:`stock_reads_scope`):

- só existe em request **GET/HEAD**. Mutação (PUT da sacola, checkout, PDV) lê
  sempre do banco, como antes: a decisão de reservar nunca se apoia em leitura
  guardada. A única exceção é a resposta do PUT da sacola, que abre o memo
  DEPOIS que a mutação voltou (``storefront.api.surface``), só para a montagem
  da sacola: toda leitura ali é posterior à escrita;
- qualquer escrita SQL dentro do request (INSERT, UPDATE, DELETE, o que não for
  ``SELECT``), em qualquer conexão, **esvazia e desliga** o memo até o fim do
  request. Vale também para ``QuerySet.update()`` e SQL cru, que não disparam
  sinal, e para escrita desfeita por rollback: depois de qualquer escrita nada
  mais é guardado, então não sobra leitura de um estado que deixou de existir.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from typing import Any

from django.db import connections
from django.db.models.signals import post_delete, post_save

_store: ContextVar[dict[Any, Any] | None] = ContextVar("shopman_request_memo", default=None)
_stock_store: ContextVar[dict[Any, Any] | None] = ContextVar("shopman_request_stock_reads", default=None)

#: Marca, dentro do memo de estoque, de que o request já escreveu no banco.
_WROTE = object()

#: Métodos HTTP em que o memo de estoque existe: os que não mutam.
STOCK_READ_METHODS = frozenset({"GET", "HEAD"})


@contextmanager
def request_memo_scope() -> Iterator[None]:
    token = _store.set({})
    try:
        yield
    finally:
        _store.reset(token)


def memoized[T](key: Any, compute: Callable[[], T]) -> T:
    """``compute()`` uma vez por request para ``key``; sem escopo, sempre ``compute()``."""
    store = _store.get()
    if store is None:
        return compute()
    if key not in store:
        store[key] = compute()
    return store[key]


def clear() -> None:
    store = _store.get()
    if store is not None:
        store.clear()


def forget(key: Any) -> None:
    """Esquece só ``key``: a próxima leitura dela neste request recalcula."""
    store = _store.get()
    if store is not None:
        store.pop(key, None)


def channel_by_ref(channel_ref: str):
    """A linha ``Channel`` de ``channel_ref`` (ou ``None``), lida uma vez por request.

    Quem recebe a instância só lê: para mexer em ``config``, copie antes.
    """

    def load():
        from shopman.shop.models import Channel

        return Channel.objects.filter(ref=channel_ref).first()

    return memoized(("channel", channel_ref), load)


def channel_config(channel_ref: str):
    """O ``ChannelConfig`` de ``channel_ref`` montado uma vez por request.

    ``ChannelConfig.for_channel`` monta a cascata inteira a cada chamada (cópia
    profunda do ``Shop.defaults`` e do ``Channel.config``, ``from_dict`` e
    ``validate``), e o caminho da disponibilidade pedia o MESMO config três vezes
    por leitura de estoque: o recorte do canal duas vezes (cardápio e fila) e o
    aspecto da fila uma. As entradas da cascata já são lidas uma vez por request
    (a linha do canal e o ``Shop``), então guardar o resultado montado não muda a
    resposta, e ele cai junto com elas quando o request grava ``Channel`` ou
    ``Shop``.

    Só leitura, como :func:`channel_by_ref`: quem precisa devolver um pedaço
    mutável (lista, sub-config) entrega uma cópia. Quem quer um config para
    mexer chama ``ChannelConfig.for_channel``, que continua montando um novo.
    """

    def load():
        from shopman.shop.config import ChannelConfig

        return ChannelConfig.for_channel(channel_ref)

    return memoized(("channel_config", channel_ref), load)


def _is_read_only_sql(sql: str) -> bool:
    """``SELECT`` (inclui ``SELECT ... FOR UPDATE``) e marcação de savepoint não mudam dado.

    Todo o resto conta como escrita, inclusive o que só PODE escrever
    (``WITH``, ``ROLLBACK TO SAVEPOINT``, ``PRAGMA``): na dúvida, desliga.
    """
    head = str(sql).lstrip()[:20].upper()
    return head.startswith(("SELECT", "SAVEPOINT", "RELEASE SAVEPOINT"))


@contextmanager
def stock_reads_scope() -> Iterator[None]:
    """Abre o memo de leituras de estoque (ver o docstring do módulo).

    Quem abre é :class:`RequestMemoMiddleware`, e só em GET/HEAD; e a resposta
    do PUT da sacola, depois que a mutação voltou. Fora deste
    escopo :func:`stock_bucket` devolve ``None`` e toda leitura vai ao banco.
    """
    store: dict[Any, Any] = {}

    def watch_writes(execute, sql, params, many, context):
        if _WROTE not in store and not _is_read_only_sql(sql):
            store.clear()
            store[_WROTE] = True
        return execute(sql, params, many, context)

    token = _stock_store.set(store)
    try:
        with ExitStack() as stack:
            for alias in connections:
                stack.enter_context(connections[alias].execute_wrapper(watch_writes))
            yield
    finally:
        _stock_store.reset(token)


def stock_bucket(key: Any) -> dict[Any, Any] | None:
    """O dicionário de ``key`` no memo de estoque deste request.

    ``None`` quando não há memo: fora de request, em request que muta, ou depois
    da primeira escrita SQL do request. Quem recebe ``None`` lê do banco.
    """
    store = _stock_store.get()
    if store is None or _WROTE in store:
        return None
    return store.setdefault(key, {})


def stock_reads_active() -> bool:
    store = _stock_store.get()
    return store is not None and _WROTE not in store


def _clear_on_write(**_kwargs) -> None:
    clear()


post_save.connect(_clear_on_write, sender="shop.Channel", dispatch_uid="request_memo_channel_saved")
post_delete.connect(_clear_on_write, sender="shop.Channel", dispatch_uid="request_memo_channel_deleted")
post_save.connect(_clear_on_write, sender="shop.Shop", dispatch_uid="request_memo_shop_saved")
post_delete.connect(_clear_on_write, sender="shop.Shop", dispatch_uid="request_memo_shop_deleted")


class RequestMemoMiddleware:
    """Abre o escopo do memo para o request inteiro (view e demais middlewares).

    O memo de estoque só em GET/HEAD (:data:`STOCK_READ_METHODS`).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with request_memo_scope():
            if request.method in STOCK_READ_METHODS:
                with stock_reads_scope():
                    return self.get_response(request)
            return self.get_response(request)
