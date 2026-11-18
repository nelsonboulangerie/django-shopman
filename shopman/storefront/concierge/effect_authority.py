"""Posse da conversa reconferida no instante do efeito (#2625, v2 4.7, propriedade 4).

Conferir a autoridade, soltar e só depois gravar deixa uma janela: a equipe assume
(``service.mark_handoff`` trava a linha da conversa e sobe ``turn_fence``) e o efeito
nasce do comando antigo. Por isso todo efeito local da Concierge (pedido, desconto,
cancelamento, acréscimo) chama ``lock_turn_authority`` DENTRO da transação que grava,
antes de gravar. Com as duas pontas travando a mesma linha, a transferência e o efeito
ficam em fila: quem chegou primeiro vence, e o outro vê o resultado.

- a transferência venceu: a reconferência levanta ``TurnRevoked`` e nada é gravado (K11);
- o efeito venceu: a transferência espera o commit, e o que já foi feito fica feito e
  reconciliável, sem promessa de desfazer (K12).

A chamada de rede (Pix, estorno) fica fora: ela roda depois do commit, pelo lifecycle.
"""

from __future__ import annotations

from django.db import transaction

from shopman.shop.models import Conversation


def lock_turn_authority(conversation, *, channel_ref: str | None = None) -> Conversation:
    """Trava a conversa e reconfere a posse na transação corrente do efeito.

    Exige transação aberta: a trava fora dela seria solta na mesma instrução, e a
    reconferência voltaria a ser "confere, solta, grava".
    """
    from .service import TurnRevoked, assert_turn_authority

    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("lock_turn_authority exige a transação do efeito")
    Conversation.objects.select_for_update().only("pk").get(pk=conversation.pk)
    current = assert_turn_authority(conversation, for_mutation=True)
    if channel_ref is not None and current.channel_ref != channel_ref:
        raise TurnRevoked("identity_changed")
    return current
