"""O turno da Concierge lido por um dublê, para os testes do que vem em volta dele.

O caminho do turno é um só (``intents.run``, WP-08). Os testes do transporte, da janela,
da posse e do envio não medem a leitura: trocam ``intents.run`` por uma função que recebe
``conversation`` e devolve o ``TurnOutcome`` que o teste quer ver gravado e enviado.
"""

from __future__ import annotations

from shopman.storefront.concierge import intents


def stub_turn(monkeypatch, respond) -> None:
    """``respond(conversation=..., binding=..., decision=..., client=...)`` responde o turno."""
    monkeypatch.setattr(
        intents, "run", lambda conversation, **kwargs: respond(conversation=conversation, **kwargs)
    )
