"""O desfecho de um turno da Concierge, e os auxiliares que as partes usam.

Quem lê o turno (``intents.run``) devolve um ``TurnOutcome``; quem grava e responde
(``service.run_turn``) lê dele a resposta, o handoff, a memória e o que vai à régua.
Não fala com o transporte nem com modelo nenhum.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shopman.shop.models import Conversation, ConversationMessage

from .metrics import LAYER_CONTEXT, LAYER_INTENTS

#: O motivo do handoff quando o cancelamento não é do autoatendimento (regra R4).
CANCEL_HANDOFF_REASON = "Cancelamento de pedido: fora do que o cliente cancela pelo site"


@dataclass
class TurnOutcome:
    reply_text: str
    handoff: bool = False
    handoff_reason: str = ""
    #: O aviso do handoff quando quem chamou a equipe tem o que dizer (o motivo
    #: verdadeiro e "já chamei a equipe"); vazio = o aviso padrão da casa.
    handoff_ack: str = ""
    extra_replies: list[str] = field(default_factory=list)
    tool_events: list[dict] = field(default_factory=list)
    order_ref: str = ""
    quote_token: str = ""
    disclosure: dict = field(default_factory=dict)
    #: Quem respondeu (``metrics.LAYER_*``): a régua grava em ``usage["layer"]``.
    layer: str = LAYER_INTENTS
    #: Intenções no plural (``intents.Plan.as_dict``): as partes do turno e quem as leu.
    intents: dict = field(default_factory=dict)
    #: Intenções no plural: a triagem do cartão da equipe (parte sensível no turno) e a
    #: que a conversa guarda quando a alergia foi respondida pelo aviso da casa.
    team_triage: object | None = None
    triage_update: object | None = None
    #: Memória da conversa (``dialogue``): o estado que valia no começo do turno e
    #: o que a resolução quer gravar. ``None`` quando o turno não passou por ela
    #: (mídia, teto diário): aí o estado fica como estava.
    memory: object | None = None
    memory_memos: list[dict] = field(default_factory=list)
    #: O turno disse "não entendi": a conversa guarda, e a segunda vez vai para a equipe.
    unclear: bool = False


def current_customer_text(conversation: Conversation) -> str:
    """Texto humano coberto pelo claim atual: as entradas deste turno, na ordem."""
    inbound_ids = tuple(getattr(conversation, "_inbound_ids", ()) or ())
    if not inbound_ids:
        return ""
    return "\n".join(
        conversation.messages.filter(
            pk__in=inbound_ids,
            kind=ConversationMessage.Kind.INBOUND,
        )
        .order_by("pk")
        .values_list("text", flat=True)
    ).strip()


def addition_outcome(conversation, resolution, *, memory, memos) -> TurnOutcome | None:
    """Acrescentar a pedido já feito, pelo mesmo serviço do PDV (dono, 03/10/2026).

    A memória resolveu o "1" (``add_preview``: a pergunta de uma linha) ou o "sim" a
    ela (``add_apply``). Sem modelo. Recusa numa encomenda chama a equipe com o
    motivo no aviso. ``None`` quando a fala é outra coisa.
    """
    if resolution.outcome not in {"add_preview", "add_apply"}:
        return None
    from . import order_addition

    request = resolution.request
    if resolution.outcome == "add_preview":
        addition = order_addition.propose(
            conversation, order_ref=request.get("order_ref", ""), additions=request.get("add")
        )
    else:
        addition = order_addition.apply(conversation, request)
    if addition.handoff:
        return TurnOutcome(
            reply_text="", handoff=True, handoff_reason=addition.handoff_reason,
            handoff_ack=addition.text, layer=LAYER_CONTEXT, memory=memory, memory_memos=memos,
        )
    return TurnOutcome(
        reply_text=addition.text,
        order_ref=addition.order_ref if addition.code == "added" else "",
        layer=LAYER_CONTEXT,
        memory=memory,
        memory_memos=[*memos, addition.memo],
    )
