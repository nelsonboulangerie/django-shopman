"""``ClockPort`` sobre o Shopman: agora, identificador, agenda e expediente (N8).

- ``now`` é o relógio do servidor, em UTC, no formato canônico do framework;
- ``new_id`` é um UUID com o prefixo pedido: nunca repete, entre processos também;
- ``schedule`` grava o vencimento como trabalho na caixa de saída do inquilino (o prazo vencido
  vira evento reivindicável, não laço, v2 5.4); ``cancel`` tira o que ninguém reivindicou;
- ``business_hours`` é o calendário da casa (``business_calendar``), como fato com fonte.

O protocolo do relógio não recebe contexto; por isso o relógio nasce com o contexto confiável
do inquilino a que a agenda pertence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from conversational_commerce.contracts import Known, Unknown
from conversational_commerce.ports import Capabilities, TrustedContext, WorkItem
from conversational_commerce.ports.clock import OPERATIONS

from .store import ShopmanStore, instant, moment

FACT_VALIDITY_SECONDS = 120


@dataclass
class ShopmanClock:
    ctx: TrustedContext
    PORT = "clock"

    def capabilities(self) -> Capabilities:
        return Capabilities(port="clock", operations=OPERATIONS,
                            guarantees={"monotonic_ids": False, "unique_ids": True, "schedule_is_outbox": True})

    def now(self) -> str:
        return instant(datetime.now(UTC))

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex}"

    def schedule(self, at: str, work: WorkItem) -> str:
        return ShopmanStore().schedule(self.ctx, WorkItem(work_id=work.work_id, kind=work.kind,
                                                          payload=dict(work.payload), due_at=at))

    def cancel(self, handle: str) -> bool:
        return ShopmanStore().cancel(self.ctx, handle)

    def business_hours(self, at: str):
        """Aberta ou não no instante ``at``, com o horário do dia. Fonte que falha: ``Unknown``."""
        from datetime import timedelta

        from shopman.shop.services.business_calendar import current_business_state

        try:
            state = current_business_state(now=moment(at))
        except Exception:  # noqa: BLE001 - K04: a fonte que falha vira Unknown, nunca o valor velho
            import logging

            logging.getLogger(__name__).warning("conversational.clock: calendário falhou", exc_info=True)
            return Unknown(reason="source_failed")
        return Known(value={"open": bool(state.is_open), "opens": state.opens_at, "closes": state.closes_at},
                     source="shop:business_calendar", observed_at=at,
                     valid_until=instant(moment(at) + timedelta(seconds=FACT_VALIDITY_SECONDS)))
