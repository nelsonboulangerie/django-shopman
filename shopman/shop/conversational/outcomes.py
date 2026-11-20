"""``OutcomesPort`` sobre o Orderman: pedidos do cliente numa janela, com censura (N8).

Garantias da porta (v2 5.4, N20, N21):

- **fonte independente do agente**: quem conta é o Orderman (``source="orderman"``);
- **janela aberta é censura**, sem valor (K33); **sem identidade é desconhecido**, nunca zero;
- **correção é registro novo** que ``supersedes`` o anterior: a porta não reescreve nada.

A métrica medida é a quantidade de pedidos do cliente (``customer_ref``) na janela; o nome da
métrica (``orders_24h``, ``orders_7d``) é de quem pede, a regra de contagem é a mesma.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from conversational_commerce.contracts import MetricRef, OutcomeEvent, Window
from conversational_commerce.ports import Capabilities, TrustedContext
from conversational_commerce.ports.outcomes import OPERATIONS

from .store import instant, moment

PRODUCER = {"name": "shopman-outcomes", "version": "1"}
SOURCE = "orderman"


@dataclass
class ShopmanOutcomes:
    """``clock``: o relógio de quem pede (o do núcleo); sem ele, o de parede, em UTC."""

    clock: object = None
    PORT = "outcomes"

    def _now(self) -> datetime:
        return moment(self.clock.now()) if self.clock is not None else datetime.now(UTC)

    def capabilities(self) -> Capabilities:
        return Capabilities(port="outcomes", operations=OPERATIONS,
                            guarantees={"independent_source": True, "censoring": True, "supersession": True})

    def harvest(self, ctx: TrustedContext, metric: MetricRef, subject: str, window: Window) -> OutcomeEvent:
        from shopman.orderman.models import Order

        from shopman.shop.services.customer_orders import customer_identity_filter

        now = self._now()
        base = {"id": f"out-{uuid.uuid4().hex}", "tenant": ctx.tenant, "environment": ctx.environment,
                "trace_id": f"trace-{uuid.uuid4().hex}", "occurred_at": instant(now), "producer": PRODUCER,
                "customer_ref": subject or None, "metric": metric, "window": window, "source": SOURCE}
        if moment(window.end) > now:
            return OutcomeEvent(**base, observation="censored")
        identity = customer_identity_filter(customer_ref=subject or None)
        if identity is None:
            return OutcomeEvent(**base, observation="unknown")
        count = (Order.objects.filter(identity, created_at__gte=moment(window.start), created_at__lt=moment(window.end))
                 .distinct().count())
        return OutcomeEvent(**base, observation="observed", value=count)
