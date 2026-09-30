"""O dispositivo que está agindo nesta requisição — para os escritores únicos das trilhas.

Os livros que respondem "quem fez o quê" (o do caixa, os eventos da comanda) têm
cada um UM escritor. Pôr o dispositivo neles pelos chamadores seria depender de
cada chamador lembrar de uma chave, e o que pode sumir em silêncio por um caminho
não é trilha. Então o dispositivo não viaja pelos chamadores: quem conhece a
requisição (o middleware da superfície) declara aqui COMO descobri-lo, e o
escritor único pergunta na hora de gravar.

Genérico de propósito: este módulo não sabe o que é estação, cookie ou
``TrustedDevice``. Guarda um resolvedor preguiçoso (só roda se alguém gravar) e
o resultado dele, uma vez por requisição. Fora de requisição (worker, comando,
teste de serviço) não há dispositivo, e a resposta é ``""`` — que é a verdade:
nenhum dispositivo agiu.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

#: A chave com que os escritores gravam o dispositivo. A MESMA nas três trilhas
#: (acesso, caixa, comanda): é o que deixa cruzar "quem entrou neste dispositivo"
#: com "o que ele lançou nesta gaveta".
DEVICE_KEY = "station_device_id"

_resolver: ContextVar[Callable[[], str] | None] = ContextVar("shopman_acting_device_resolver", default=None)


@contextmanager
def acting_device(resolver: Callable[[], str]) -> Iterator[None]:
    """Declara, para o bloco, como descobrir o dispositivo que está agindo."""
    cache: list[str] = []

    def resolve_once() -> str:
        if not cache:
            cache.append(str(resolver() or ""))
        return cache[0]

    token = _resolver.set(resolve_once)
    try:
        yield
    finally:
        _resolver.reset(token)


def current_device_id() -> str:
    """O dispositivo que está agindo agora, ou ``""`` quando nenhum."""
    resolver = _resolver.get()
    if resolver is None:
        return ""
    return resolver()


def stamp(payload: dict) -> dict:
    """Carimba o dispositivo atual em ``payload`` (cópia), e só ele.

    O que o chamador tenha posto na chave é descartado: quem diz qual dispositivo
    agiu é a requisição, nunca o corpo. Sem dispositivo, a chave não aparece.
    """
    stamped = {key: value for key, value in (payload or {}).items() if key != DEVICE_KEY}
    device_id = current_device_id()
    if device_id:
        stamped[DEVICE_KEY] = device_id
    return stamped
