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
seguinte tem de ver o valor novo. Se o próprio request grava um ``Channel``, o
``post_save``/``post_delete`` esvazia o memo e a leitura seguinte vai ao banco.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from django.db.models.signals import post_delete, post_save

_store: ContextVar[dict[Any, Any] | None] = ContextVar("shopman_request_memo", default=None)


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


def channel_by_ref(channel_ref: str):
    """A linha ``Channel`` de ``channel_ref`` (ou ``None``), lida uma vez por request.

    Quem recebe a instância só lê: para mexer em ``config``, copie antes.
    """

    def load():
        from shopman.shop.models import Channel

        return Channel.objects.filter(ref=channel_ref).first()

    return memoized(("channel", channel_ref), load)


def _clear_on_write(**_kwargs) -> None:
    clear()


post_save.connect(_clear_on_write, sender="shop.Channel", dispatch_uid="request_memo_channel_saved")
post_delete.connect(_clear_on_write, sender="shop.Channel", dispatch_uid="request_memo_channel_deleted")


class RequestMemoMiddleware:
    """Abre o escopo do memo para o request inteiro (view e demais middlewares)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with request_memo_scope():
            return self.get_response(request)
