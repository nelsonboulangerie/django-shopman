"""Equipe falsa: fila que não aceita, resposta tardia, devolução da conversa.

Roteado não é aceito: ``ask`` devolve ``routed``; só ``record_acceptance``
nomeia quem aceitou. A resposta entra como fato com autoria e validade.
"""

from __future__ import annotations

import dataclasses

from conversational_commerce.contracts import Commitment, Known
from conversational_commerce.ports import (
    Capabilities,
    ConversationReturn,
    PortError,
    StaffQuestion,
    StaffTicket,
    TrustedContext,
)
from conversational_commerce.ports.staff import OPERATIONS

from .base import FakeBase
from .faults import Fault

ANSWER_VALIDITY_SECONDS = 3600


class FakeStaff(FakeBase):
    PORT = "staff"

    def __init__(self, clock, faults=None, *, member: str = "staff-1") -> None:
        super().__init__(clock, faults)
        self.member = member
        self.tickets: dict[str, StaffTicket] = {}
        self.questions: dict[str, StaffQuestion] = {}
        self.commitments: dict[str, Commitment] = {}
        self.epochs: dict[str, int] = {}
        self.returns: list[ConversationReturn] = []

    def capabilities(self) -> Capabilities:
        return Capabilities(port="staff", operations=OPERATIONS,
                            guarantees={"nominal_acceptance": True, "answer_is_authored_fact": True})

    def ask(self, ctx: TrustedContext, question: StaffQuestion) -> StaffTicket:
        fault = self._fault("ask")
        ticket = StaffTicket(ticket_id=self.clock.new_id("ticket"), episode_id=question.episode_id,
                             state="rejected" if fault is Fault.QUEUE_REJECTS else "routed")
        self.tickets[ticket.ticket_id] = ticket
        self.questions[ticket.ticket_id] = question
        return ticket

    def record_acceptance(self, ctx: TrustedContext, ticket_id: str) -> StaffTicket:
        self._fault("record_acceptance")
        ticket = self.tickets[ticket_id]
        if ticket.state == "rejected":
            raise PortError("capability_missing", "a fila não aceitou; ninguém assumiu")
        accepted = dataclasses.replace(ticket, state="accepted", accepted_by=self.member)
        self.tickets[ticket_id] = accepted
        return accepted

    def answer(self, ticket_id: str, value) -> StaffTicket:
        """O teste faz a pessoa responder. Com ``LATE_ANSWER`` armado, o relógio passa do prazo antes."""
        if self.faults.take("answer") is Fault.LATE_ANSWER:
            question = self.questions[ticket_id]
            while self.clock.now() <= question.respond_by:
                self.clock.advance(60)
        ticket = self.tickets[ticket_id]
        fact = Known(value=value, source=f"staff:{ticket.accepted_by or self.member}", observed_at=self.clock.now(),
                     valid_until=self.clock.at(ANSWER_VALIDITY_SECONDS))
        answered = dataclasses.replace(ticket, state="answered", answer=fact)
        self.tickets[ticket_id] = answered
        return answered

    def promote_answer(self, ctx: TrustedContext, ticket_id: str) -> Known:
        self._fault("promote_answer")
        ticket = self.tickets[ticket_id]
        if ticket.answer is None:
            raise PortError("fact_unavailable", "pergunta ainda sem resposta")
        return ticket.answer

    def open_or_update(self, ctx: TrustedContext, commitment: Commitment) -> Commitment:
        self._fault("open_or_update")
        self.commitments[commitment.commitment_id] = commitment
        return commitment

    def assign(self, ctx: TrustedContext, commitment_id: str, owner: str) -> Commitment:
        if self._fault("assign") is Fault.QUEUE_REJECTS:
            raise PortError("capability_missing", "a fila não aceitou a atribuição")
        current = self.commitments[commitment_id]
        updated = dataclasses.replace(current, id=self.clock.new_id("cmt"), owner=owner,
                                      occurred_at=self.clock.now())
        self.commitments[commitment_id] = updated
        return updated

    def record_fulfillment(self, ctx: TrustedContext, commitment_id: str, evidence: str) -> Commitment:
        self._fault("record_fulfillment")
        current = self.commitments[commitment_id]
        updated = dataclasses.replace(current, id=self.clock.new_id("cmt"), state="fulfilled",
                                      evidence=(*current.evidence, evidence), occurred_at=self.clock.now())
        self.commitments[commitment_id] = updated
        return updated

    def return_conversation(self, ctx: TrustedContext, episode_id: str, new_epoch: int) -> ConversationReturn:
        self._fault("return_conversation")
        current = self.epochs.get(episode_id, 0)
        if new_epoch <= current:
            raise PortError("revision_conflict", "a época de posse só cresce")
        self.epochs[episode_id] = new_epoch
        handback = ConversationReturn(episode_id=episode_id, new_epoch=new_epoch, returned_by=self.member)
        self.returns.append(handback)
        return handback
