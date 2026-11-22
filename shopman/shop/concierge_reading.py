"""O redator do texto de cliente, para quem lê a Concierge de fora da superfície (o B.I.).

O redator de verdade (nome, documento, telefone, e-mail, endereço, dado financeiro, link)
mora na Concierge (``storefront/concierge/observation_privacy``). Pela regra de dependência
o backstage não importa o storefront: a Concierge registra o redator aqui na subida
(``StorefrontConfig.ready``), como faz com o "vou verificar" (``concierge_verification``).

Sem redator registrado, ``redact`` devolve ``None`` e quem lê não mostra o texto: falha
fechada, nunca texto cru.
"""

from __future__ import annotations

from collections.abc import Callable

_redactor: list[Callable[[str], str]] = []


def register(*, redact: Callable[[str], str]) -> None:
    _redactor[:] = [redact]


def redact(text: str) -> str | None:
    if not _redactor:
        return None
    return _redactor[0](text or "")
