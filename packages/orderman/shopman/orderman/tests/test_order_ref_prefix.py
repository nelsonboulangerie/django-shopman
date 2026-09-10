"""Prefixo do ref de pedido vem da config resolvida do canal.

Decisão do dono (01/09): pedido da loja online nasce ``NB-...`` — marca no ref
que o cliente vê, sem tocar no formato. Sem a chave ``order_ref_prefix`` na
config, o prefixo é o canal, como sempre foi.
"""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Session
from shopman.orderman.services import CommitService


class OrderRefPrefixTests(TestCase):
    def _session(self, key: str) -> Session:
        return Session.objects.create(
            session_key=key,
            channel_ref="web",
            state="open",
            rev=1,
            items=[{"line_id": "L1", "sku": "A", "qty": 1, "unit_price_q": 1000}],
        )

    def test_config_prefix_wins(self) -> None:
        self._session("PREFIX-SESS-001")
        result = CommitService.commit(
            session_key="PREFIX-SESS-001",
            channel_ref="web",
            idempotency_key="prefix-key-1",
            channel_config={"order_ref_prefix": "NB"},
        )
        assert result.order_ref.startswith("NB-"), result.order_ref

    def test_without_key_prefix_is_the_channel(self) -> None:
        self._session("PREFIX-SESS-002")
        result = CommitService.commit(
            session_key="PREFIX-SESS-002",
            channel_ref="web",
            idempotency_key="prefix-key-2",
            channel_config={},
        )
        assert result.order_ref.startswith("WEB-"), result.order_ref
