"""``Order.next_status``: o próximo passo adiante no ciclo do canal (ADR-006)."""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Order

S = Order.Status


class OrderNextStatusTests(TestCase):
    def _order(self, status, transitions=None) -> Order:
        snapshot = {"lifecycle": {"transitions": transitions}} if transitions else {}
        return Order.objects.create(
            ref=f"NX-{status}-{Order.objects.count()}",
            channel_ref="shop",
            status=status,
            total_q=1000,
            snapshot=snapshot,
        )

    def test_ciclo_padrao_sem_entrega(self) -> None:
        expected = {
            S.NEW: S.ACCEPTED,
            S.ACCEPTED: S.PREPARING,
            S.PREPARING: S.READY,
            S.READY: S.COMPLETED,
            S.COMPLETED: "",
            S.CANCELLED: "",
            S.RETURNED: "",
        }
        for status, nxt in expected.items():
            with self.subTest(status=status):
                self.assertEqual(self._order(status).next_status(dispatch=False), nxt)

    def test_ciclo_padrao_com_entrega(self) -> None:
        expected = {
            S.READY: S.DISPATCHED,
            S.DISPATCHED: S.DELIVERED,
            S.DELIVERED: S.COMPLETED,
        }
        for status, nxt in expected.items():
            with self.subTest(status=status):
                self.assertEqual(self._order(status).next_status(dispatch=True), nxt)

    def test_recall_da_cozinha_nao_e_avanco(self) -> None:
        # READY permite voltar a PREPARING; o avanço nunca escolhe o passo para trás.
        self.assertNotEqual(self._order(S.READY).next_status(dispatch=False), S.PREPARING)

    def test_segue_as_transicoes_do_canal(self) -> None:
        transitions = {S.ACCEPTED: [S.READY, S.CANCELLED], S.READY: [S.COMPLETED]}
        self.assertEqual(self._order(S.ACCEPTED, transitions).next_status(dispatch=False), S.READY)
        self.assertEqual(self._order(S.READY, transitions).next_status(dispatch=True), S.COMPLETED)
