"""``StaffPort`` do framework sobre o "vou verificar" da Concierge (N7).

A Concierge pergunta à equipe pelo cartão ``concierge_verify`` do sino do Gestor
(``verification.py``, WP-05 a WP-07). A porta só embrulha esse caminho; os gestos da equipe
(``answer``, ``take_over``) continuam no Gestor, e a porta lê o desfecho:

| Operação | No "vou verificar" |
|---|---|
| ``ask`` | ``verification.open_for``: abre (ou estende) a verificação e cria o cartão |
| ``record_acceptance`` | lê o desfecho: ``taken_over`` é o aceite nominal (``closed_by`` = quem assumiu) |
| ``promote_answer`` | ``answered``: a resposta vira fato com autoria (``staff:<quem>``) e validade |
| ``open_or_update`` | a verificação é o próprio compromisso: devolve o compromisso como está |
| ``return_conversation`` | ``service.return_to_concierge``, com a época de posse que só cresce |
| ``assign`` | não existe: o cartão é de quem estiver com o Gestor aberto (P15) |
| ``record_fulfillment`` | não existe aqui: a resposta enviada pelo cartão já fecha a verificação |

**Roteado não é aceito** (K20): o cartão no sino é ``routed``. ``handed_off`` e ``returned``
(passou à equipe pelo prazo, sem ninguém assumir) continuam sem aceite de ninguém. Sem prazo
possível, ou com a conversa fora da Concierge, ``open_for`` não abre nada, e o tíquete é
``rejected``: ninguém recebeu, e nada afirma que recebeu.

Combinado com a Concierge na nota ``concierge-wp05-vou-verificar.md`` (seção N7).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conversational_commerce.contracts import Known
from conversational_commerce.ports import (
    Capabilities,
    ConversationReturn,
    PortError,
    StaffQuestion,
    StaffTicket,
    TrustedContext,
)
from conversational_commerce.ports.staff import OPERATIONS
from django.db import IntegrityError, transaction

from shopman.shop.conversational.store import instant

from .ports import SUBJECT_PREFIX

TICKET_PREFIX = "verify"
HANDOFF_TICKET_PREFIX = "handoff"
#: A pergunta que o movimento ``handoff`` faz à equipe (``engine/moves/handoff.py``): não é pergunta a
#: responder, é a conversa a assumir. A entrega é a de hoje (``service.mark_handoff``, ao fechar o turno).
HANDOFF_QUESTION = "take over the conversation"
EPISODE_PREFIX = "conversation-"
RETURN_SCHEMA = "nice.staff_return"
ACTOR = "framework"
#: A resposta da equipe vale como fato por uma hora (o mesmo horizonte do falso do framework).
ANSWER_VALIDITY_SECONDS = 3600


def _conversation_of(ctx: TrustedContext, episode_id: str = ""):
    """A conversa do contexto confiável; senão, a do episódio ``conversation-<pk>``."""
    from shopman.shop.models import Conversation

    for ref, prefix in ((ctx.subject or "", SUBJECT_PREFIX), (episode_id or "", EPISODE_PREFIX)):
        if ref.startswith(prefix):
            try:
                return Conversation.objects.filter(pk=int(ref[len(prefix):])).first()
            except ValueError:
                continue
    return None


def _customer_words(conversation) -> str:
    """A fala do cliente que abriu o turno: a última entrada da conversa (o que a equipe lê no cartão)."""
    from shopman.shop.models import ConversationMessage

    last = (ConversationMessage.objects.filter(conversation=conversation, kind=ConversationMessage.Kind.INBOUND)
            .order_by("-pk").values_list("text", flat=True).first())
    return " ".join(str(last or "").split())


def _handoff_state(ticket: str) -> StaffTicket:
    """O encaminhamento: a equipe atende pelo Live Chat, e a casa não registra quem assumiu. Sem prova de aceite,
    o tíquete segue "routed" (nada afirma que alguém aceitou, K20)."""
    from shopman.shop.models import Conversation

    _, pk, episode_id = (ticket.split(":", 2) + ["", ""])[:3]
    if not pk.isdigit() or not Conversation.objects.filter(pk=int(pk)).exists():
        raise PortError("object_forbidden", "tíquete de encaminhamento sem conversa")
    return StaffTicket(ticket_id=ticket, episode_id=episode_id, state="routed")


def ticket_id(conversation_pk: int, record_id: str) -> str:
    return f"{TICKET_PREFIX}:{conversation_pk}:{record_id}"


def _record_of(ticket: str):
    """``(conversa, registro da verificação)`` do tíquete, ou ``(None, None)``."""
    from shopman.shop.models import Conversation

    from .verification import FLAG_KEY

    parts = (ticket or "").split(":")
    if len(parts) != 3 or parts[0] != TICKET_PREFIX:
        return None, None
    try:
        conversation = Conversation.objects.filter(pk=int(parts[1])).first()
    except ValueError:
        return None, None
    record = ((conversation.flags or {}).get(FLAG_KEY) if conversation is not None else None) or {}
    if record.get("id") != parts[2]:
        return conversation, None
    return conversation, record


class NiceStaff:
    """A porta de equipe da Nice sobre o cartão ``concierge_verify``."""

    PORT = "staff"

    def capabilities(self) -> Capabilities:
        return Capabilities(port="staff", operations=OPERATIONS, unsupported=("assign", "record_fulfillment"),
                            guarantees={"nominal_acceptance": True, "answer_is_authored_fact": True,
                                        "routed_is_not_accepted": True, "queue": "operator_alert"})

    def ask(self, ctx: TrustedContext, question: StaffQuestion) -> StaffTicket:
        """A pergunta à equipe. O encaminhamento não abre cartão de verificar: a conversa vai à equipe pelo
        caminho de hoje (um cartão só, o de "cliente esperando atendente"). O "vou verificar" abre o cartão com a
        FALA do cliente, lida aqui na mensagem que abriu o turno (P17: a fala não entra na pergunta, no tíquete
        nem em contrato do motor; a pergunta do motor é interna e a equipe nunca a lê)."""
        from .verification import open_for

        conversation = _conversation_of(ctx, question.episode_id)
        if question.question == HANDOFF_QUESTION:
            if conversation is None:
                return StaffTicket(ticket_id=f"{HANDOFF_TICKET_PREFIX}:none:{question.episode_id}"[:128],
                                   episode_id=question.episode_id, state="rejected")
            return StaffTicket(ticket_id=f"{HANDOFF_TICKET_PREFIX}:{conversation.pk}:{question.episode_id}"[:128],
                               episode_id=question.episode_id, state="routed")
        said = _customer_words(conversation) if conversation is not None else ""
        record = open_for(conversation, said, actor=ACTOR) if conversation is not None and said else None
        if record is None:
            # Sem conversa ativa ou sem prazo possível: ninguém recebeu, e nada diz que recebeu.
            return StaffTicket(ticket_id=f"{TICKET_PREFIX}:none:{question.episode_id}"[:128],
                               episode_id=question.episode_id, state="rejected")
        return StaffTicket(ticket_id=ticket_id(conversation.pk, record["id"]), episode_id=question.episode_id,
                           state="routed")

    def record_acceptance(self, ctx: TrustedContext, ticket: str) -> StaffTicket:
        """O desfecho do cartão, lido: ``taken_over`` é aceite nominal; o resto não é.

        O encaminhamento: sem registro de quem assumiu, segue esperando (``_handoff_state``)."""
        from .verification import ANSWERED, TAKEN_OVER

        if (ticket or "").startswith(f"{HANDOFF_TICKET_PREFIX}:"):
            return _handoff_state(ticket)
        conversation, record = _record_of(ticket)
        if record is None:
            raise PortError("object_forbidden", "tíquete sem verificação")
        episode_id = f"{EPISODE_PREFIX}{conversation.pk}"
        status = record.get("status")
        if status == TAKEN_OVER:
            return StaffTicket(ticket_id=ticket, episode_id=episode_id, state="accepted",
                               accepted_by=str(record.get("closed_by") or "") or None)
        if status == ANSWERED:
            return StaffTicket(ticket_id=ticket, episode_id=episode_id, state="answered",
                               accepted_by=str(record.get("closed_by") or "") or None, answer=self._fact(record))
        # Aberta, ou passada à equipe pelo prazo sem ninguém assumir (handed_off, returned).
        return StaffTicket(ticket_id=ticket, episode_id=episode_id, state="routed")

    def promote_answer(self, ctx: TrustedContext, ticket: str) -> Known:
        from .verification import ANSWERED

        _, record = _record_of(ticket)
        if record is None or record.get("status") != ANSWERED:
            raise PortError("fact_unavailable", "a equipe ainda não respondeu por este cartão")
        return self._fact(record)

    @staticmethod
    def _fact(record: dict) -> Known:
        closed = record.get("closed_at") or ""
        try:
            at = datetime.fromisoformat(closed)
        except ValueError:
            at = datetime.now(UTC)
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        return Known(value={"answer": record.get("answer", "")}, source=f"staff:{record.get('closed_by') or 'team'}",
                     observed_at=instant(at), valid_until=instant(at + timedelta(seconds=ANSWER_VALIDITY_SECONDS)))

    def open_or_update(self, ctx: TrustedContext, commitment):
        """A verificação aberta é o próprio compromisso da casa: nada a gravar além dela."""
        if not commitment.owner:
            raise PortError("invalid_content", "compromisso sem dono não se registra (N04)")
        return commitment

    def assign(self, ctx: TrustedContext, commitment_id: str, owner: str):
        raise PortError("capability_missing", "o cartão é de quem estiver com o Gestor aberto (P15): não se atribui")

    def record_fulfillment(self, ctx: TrustedContext, commitment_id: str, evidence: str):
        raise PortError("capability_missing", "a resposta enviada pelo cartão já fecha a verificação")

    def return_conversation(self, ctx: TrustedContext, episode_id: str, new_epoch: int) -> ConversationReturn:
        """Devolve a conversa à Concierge. A época de posse só cresce: repetida ou menor é conflito."""
        from shopman.shop.models import ConversationalRecord

        from .service import return_to_concierge

        scope = {"tenant": ctx.tenant, "environment": ctx.environment}
        current = (ConversationalRecord.objects.filter(**scope, schema=RETURN_SCHEMA, episode_id=episode_id)
                   .order_by("-pk").values_list("document", flat=True).first())
        if current is not None and int(current.get("epoch", -1)) >= int(new_epoch):
            raise PortError("revision_conflict", "a época de posse só cresce")
        conversation = _conversation_of(TrustedContext(tenant=ctx.tenant, environment=ctx.environment), episode_id)
        if conversation is not None and not return_to_concierge(conversation):
            raise PortError("capability_missing", "a devolução não foi aceita (desligada ou o canal recusou)")
        try:
            with transaction.atomic():
                ConversationalRecord.objects.create(
                    **scope, episode_id=episode_id, schema=RETURN_SCHEMA,
                    record_id=f"return:{episode_id}:{new_epoch}"[:128],
                    document={"episode_id": episode_id, "epoch": int(new_epoch), "returned_by": ACTOR})
        except IntegrityError as conflict:
            raise PortError("revision_conflict", "a época de posse só cresce") from conflict
        return ConversationReturn(episode_id=episode_id, new_epoch=int(new_epoch), returned_by=ACTOR)
