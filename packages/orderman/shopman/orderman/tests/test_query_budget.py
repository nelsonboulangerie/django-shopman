"""Orçamento de consultas dos caminhos quentes do orderman.

Trava: o número de consultas não pode crescer com N (N+1). Medido com
CaptureQueriesContext contra Postgres (config.settings_test + DATABASE_URL) e
também no settings do próprio pacote (SQLite); o teste é portátil.

Cobre dois caminhos: o commit (OrderItem em um INSERT só) e a listagem de
sessões (as linhas da página vêm no prefetch, não uma consulta por sessão).
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from shopman.orderman.ids import generate_idempotency_key
from shopman.orderman.models import Session
from shopman.orderman.services import CommitService
from shopman.orderman.signals import order_changed

CHANNEL_REF = "qc-budget"
ITEMS_PER_SESSION = 3


def _line(i: int) -> dict:
    return {
        "line_id": f"L{i}",
        "sku": f"SKU{i}",
        "name": f"Item {i}",
        "qty": 1,
        "unit_price_q": 100,
    }


def _open_session(items: int, *, key: str) -> Session:
    return Session.objects.create(
        session_key=key,
        channel_ref=CHANNEL_REF,
        state="open",
        pricing_policy="internal",
        edit_policy="open",
        rev=0,
        items=[_line(i) for i in range(items)],
    )


class CommitQueryBudgetTests(TestCase):
    """CommitService: os OrderItem são gravados em um INSERT, não um por linha."""

    def _commit_and_count(self, items: int):
        session = _open_session(items, key=f"QC-COMMIT-{items}-{generate_idempotency_key()[:8]}")
        # O fan-out de order_changed (estoque, notificação) consulta por item e
        # também cresce com N, mas é outro caminho: aqui o alvo é o INSERT dos
        # OrderItem dentro do CommitService, então o sinal é isolado.
        with mock.patch.object(order_changed, "send"):
            with CaptureQueriesContext(connection) as ctx:
                CommitService.commit(
                    session_key=session.session_key,
                    channel_ref=CHANNEL_REF,
                    idempotency_key=generate_idempotency_key(),
                )
        return len(ctx), [q["sql"] for q in ctx.captured_queries]

    def test_commit_query_count_does_not_grow_with_items(self) -> None:
        one, _ = self._commit_and_count(1)
        ten, _ = self._commit_and_count(10)
        self.assertEqual(
            ten,
            one,
            f"commit com 1 item = {one} consultas; com 10 itens = {ten}. "
            "O número voltou a crescer com N (OrderItem.objects.create dentro do laço).",
        )

    def test_order_items_are_written_in_a_single_insert(self) -> None:
        _, sql = self._commit_and_count(10)
        inserts = [s for s in sql if "INSERT INTO" in s and "orderman_orderitem" in s]
        self.assertEqual(len(inserts), 1, f"esperado 1 INSERT de OrderItem, obtido {len(inserts)}")


class SessionListQueryBudgetTests(TestCase):
    """GET /api/sessions: a página custa o mesmo com N e com 2N sessões.

    O defeito era uma consulta de ``orderman_sessionitem`` por sessão da página
    (25 sessões = 26 consultas). Aqui a página cresce junto com N via
    ``page_size``, então a contagem só fica igual se as linhas vierem de um
    prefetch: uma consulta para a página e uma para as linhas, independente do
    tamanho.
    """

    def setUp(self) -> None:
        super().setUp()
        self.user = get_user_model().objects.create_user("qc-budget-user", password="qc-budget")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _open_sessions(self, count: int, *, offset: int) -> None:
        for i in range(offset, offset + count):
            _open_session(ITEMS_PER_SESSION, key=f"QC-LIST-{i}")

    def _list(self, page_size: int):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get("/api/sessions", {"page_size": str(page_size)})
        self.assertEqual(response.status_code, 200, response.data)
        return len(ctx), response.data["results"]

    def test_list_query_count_does_not_grow_with_page_size(self) -> None:
        half = 5
        self._open_sessions(half, offset=0)
        small, small_rows = self._list(half)

        self._open_sessions(half, offset=half)
        large, large_rows = self._list(half * 2)

        self.assertEqual(len(small_rows), half)
        self.assertEqual(len(large_rows), half * 2)
        for row in small_rows + large_rows:
            self.assertEqual(len(row["items"]), ITEMS_PER_SESSION, row)
        self.assertEqual(
            large,
            small,
            f"página de {half} sessões = {small} consultas; de {half * 2} = {large}. "
            "O número voltou a crescer com o tamanho da página (uma consulta de "
            'orderman_sessionitem por sessão): falta o prefetch_related("session_items").',
        )
