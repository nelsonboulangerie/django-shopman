"""Armazenamento falso, em memória: comparar e gravar, caixa de saída na mesma "transação".

Falhas: conflito de versão, morte do trabalhador (a reivindicação vence e o
trabalho volta), reivindicação dupla. Isolamento por inquilino: o que um
inquilino grava, outro não lê.
"""

from __future__ import annotations

from conversational_commerce.contracts import ActionReceipt, Episode, InteractionEvent, Record
from conversational_commerce.ports import Capabilities, Claim, PortError, Transition, TrustedContext, WorkItem
from conversational_commerce.ports.store import OPERATIONS

from .base import FakeBase
from .faults import Fault


class FakeStore(FakeBase):
    PORT = "store"

    def __init__(self, clock, faults=None) -> None:
        super().__init__(clock, faults)
        self.events: dict[tuple[str, str, str], InteractionEvent] = {}
        self.anonymous_events: list[InteractionEvent] = []
        self.episodes: dict[tuple[str, str], Episode] = {}
        self.records: list[tuple[str, Record]] = []
        self.outbox: dict[str, tuple[str, WorkItem]] = {}
        self.leases: dict[str, Claim] = {}
        self.receipts: list[tuple[str, ActionReceipt]] = []
        self.commits = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(port="store", operations=OPERATIONS,
                            guarantees={"compare_and_set": True, "transactional_outbox": True,
                                        "tenant_isolation": True, "real_concurrency": False})

    def record_event_once(self, ctx: TrustedContext, event: InteractionEvent) -> tuple[InteractionEvent, bool]:
        self._fault("record_event_once")
        identity = event.event_identity
        if identity.id is None:
            # Sem identidade estável não há como deduplicar: texto igual não prova duplicata (K02).
            self.anonymous_events.append(event)
            return event, True
        key = (ctx.tenant, event.channel_binding.channel, identity.id)
        if key in self.events:
            return self.events[key], False
        self.events[key] = event
        return event, True

    def load_episode(self, ctx: TrustedContext, episode_id: str) -> Episode | None:
        self._fault("load_episode")
        return self.episodes.get((ctx.tenant, episode_id))

    def commit_transition(self, ctx: TrustedContext, transition: Transition, records: tuple[Record, ...],
                          outbox: tuple[WorkItem, ...]) -> Episode:
        fault = self._fault("commit_transition")
        episode = transition.episode
        key = (ctx.tenant, episode.episode_id)
        current = self.episodes.get(key)
        # Episódio novo: versão esperada 0. Existente: a versão gravada.
        current_version = 0 if current is None else current.version
        if fault is Fault.VERSION_CONFLICT or transition.expected_version != current_version:
            raise PortError("revision_conflict", f"versão {current_version}, esperada {transition.expected_version}")
        if episode.version != transition.expected_version + 1:
            raise PortError("invalid_content", "a transição incrementa a versão em um")
        # Tudo ou nada: estado, registros e caixa de saída.
        self.episodes[key] = episode
        self.records.extend((ctx.tenant, record) for record in records)
        for work in outbox:
            self.outbox[work.work_id] = (ctx.tenant, work)
        self.commits += 1
        return episode

    def claim_work(self, ctx: TrustedContext, kind: str, lease_seconds: int) -> Claim | None:
        fault = self._fault("claim_work")
        now = self.clock.now()
        for work_id, (tenant, work) in sorted(self.outbox.items()):
            if tenant != ctx.tenant or work.kind != kind or work.due_at > now:
                continue
            lease = self.leases.get(work_id)
            if lease is not None and lease.lease_until > now and fault is not Fault.DOUBLE_CLAIM:
                continue
            attempt = 1 if lease is None else lease.attempt + 1
            claim = Claim(work=work, lease_until=self.clock.at(lease_seconds), attempt=attempt)
            self.leases[work_id] = claim
            if fault is Fault.WORKER_DIES:
                # O trabalhador morre segurando o trabalho: a reivindicação vence sozinha.
                self.leases[work_id] = Claim(work=work, lease_until=now, attempt=attempt)
            return claim
        return None

    def complete_work(self, ctx: TrustedContext, work_id: str) -> None:
        self.outbox.pop(work_id, None)
        self.leases.pop(work_id, None)

    def append_receipt(self, ctx: TrustedContext, receipt: ActionReceipt) -> ActionReceipt:
        self._fault("append_receipt")
        self.receipts.append((ctx.tenant, receipt))
        return receipt
