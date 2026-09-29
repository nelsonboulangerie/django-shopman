"""Todo handler registrado aceita a chamada que os dois executores fazem.

O despacho inline (`dispatch._process_directive`) e o worker de produção
(`process_directives`) chamam `handler.handle(message=..., ctx=...)`. Um handler
com outra assinatura estoura `TypeError` em TODA directive do tópico e termina
`failed` — foi o que houve com o Web Push, cujos testes chamavam o handler
posicionalmente e por isso ficavam verdes.
"""

from __future__ import annotations

import inspect

from shopman.orderman import registry


def test_every_registered_directive_handler_accepts_message_and_ctx_keywords():
    handlers = registry.get_directive_handlers()
    assert handlers, "nenhum handler registrado — o boot do shop não rodou"

    wrong = []
    for topic, handler in sorted(handlers.items()):
        try:
            inspect.signature(handler.handle).bind(message=object(), ctx={})
        except TypeError as exc:
            wrong.append(f"{topic}: {type(handler).__name__}.handle — {exc}")

    assert not wrong, "handlers que os executores não conseguem chamar:\n" + "\n".join(wrong)
