"""Orçamento de consultas dos caminhos quentes do orderman.

Trava: o número de consultas não pode crescer com N (N+1). Medido com
CaptureQueriesContext contra Postgres (config.settings_test + DATABASE_URL) e
também no settings do próprio pacote (SQLite); o teste é portátil.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate
from shopman.orderman.api.views import SessionViewSet
from shopman.orderman.ids import generate_idempotency_key
from shopman.orderman.models import Session
from shopman.orderman.services import CommitService
from shopman.orderman.signals import order_changed

CHANNEL_REF = "qc-budget"


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
    """SessionViewSet.list: os items vêm por prefetch, não um SELECT por comanda."""

    def setUp(self) -> None:
        super().setUp()
        self.user = get_user_model().objects.create_user("qc-budget-user", password="x")

    def _list_and_count(self, rows: int):
        Session.objects.filter(channel_ref=CHANNEL_REF).delete()
        for i in range(rows):
            _open_session(2, key=f"QC-LIST-{rows}-{i}")
        request = APIRequestFactory().get("/api/sessions", {"channel_ref": CHANNEL_REF, "page_size": 25})
        force_authenticate(request, user=self.user)
        with CaptureQueriesContext(connection) as ctx:
            view = SessionViewSet.as_view({"get": "list"}, throttle_classes=[])
            response = view(request)
        if hasattr(response, "render"):
            response.render()
        return response.status_code, len(ctx)

    def test_session_list_query_count_does_not_grow_with_rows(self) -> None:
        # O 200 também trava a paginação: a lista de sessões herdava o cursor
        # de Order (ordena por created_at, que Session não tem) e respondia 500.
        one_status, one = self._list_and_count(1)
        many_status, many = self._list_and_count(25)
        self.assertEqual(one_status, 200)
        self.assertEqual(many_status, 200)
        self.assertEqual(
            many,
            one,
            f"lista com 1 comanda = {one} consultas; com 25 comandas = {many}. "
            "O número voltou a crescer com N (session_items sem prefetch).",
        )
