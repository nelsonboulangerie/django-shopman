"""Transferir, separar e juntar comandas levam junto o estado da COZINHA.

O kernel (``ModifyService.move_lines``) dá ``line_id`` novo à linha movida, e o
livro da cozinha é por comanda + ``line_id``. Sem o orquestrador carregar o
estado, a linha já enviada chegava "a enviar" no destino (o próximo Enviar a
mandava de novo ao KDS, e a cozinha fazia duas vezes) e o ticket da origem
ficava órfão, apontando para uma linha que não existe mais.
"""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Session

from shopman.backstage.models import KDSInstance, KDSTicket, POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.adapters.kds import KDS_INHERITED_KEY
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service


class POSMoveLinesKeepsKitchenStateTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(ref="00001007", label="1007")
        POSTab.objects.create(ref="00001008", label="1008")
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user(username="alice", password="x")
        # Estação catch-all: todo SKU cai nela, um ticket por envio.
        KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")
        from shopman.offerman.models import Product

        for sku in ("MV-A", "MV-B", "MV-C"):
            Product.objects.create(sku=sku, name=sku, base_price_q=1000, is_published=True, is_sellable=True)

    # ── apoio ──────────────────────────────────────────────────────────

    def _open(self, tab_ref: str, items: list[dict]) -> Session:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref=tab_ref, actor="pos:alice", operator_username="alice",
        ))
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={
                "items": items,
                "payment_method": "cash",
                "manual_discount": None,
                "tab_ref": opened["tab_ref"],
                "tab_session_key": opened["tab_session_key"],
            },
            actor="pos:alice", operator_username="alice",
        )
        return Session.objects.get(session_key=opened["tab_session_key"])

    def _fire(self, session_key: str, line_ids: list[str] | None = None):
        return pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session_key, line_ids=line_ids,
            actor="pos:alice", operator_username="alice",
        )

    def _move(self, source: Session, line_ids: list[str], **target) -> pos_service.PosMoveResult:
        return pos_service.move_pos_tab_lines(
            channel_ref="pdv", from_session_key=source.session_key, line_ids=line_ids,
            actor="pos:alice", operator_username="alice", **target,
        )

    def _line(self, session: Session, sku: str) -> dict:
        payload = build_open_tab(Session.objects.get(pk=session.pk))
        return next(item for item in payload["items"] if item["sku"] == sku)

    def _kitchen_lines(self) -> list[tuple[str, str]]:
        """(sku, session_key) de cada item em ticket vivo: o que a cozinha vai fazer."""
        return sorted(
            (item["sku"], ticket.session_key)
            for ticket in KDSTicket.objects.exclude(status="cancelled")
            for item in ticket.items
        )

    # ── transferir ─────────────────────────────────────────────────────

    def test_transferred_fired_line_stays_fired_and_is_not_sent_again(self) -> None:
        source = self._open("1007", [{"line_id": "L-A", "sku": "MV-A", "name": "A", "qty": 2, "unit_price_q": 1000}])
        target = self._open("1008", [{"line_id": "L-B", "sku": "MV-B", "name": "B", "qty": 1, "unit_price_q": 1000}])
        self._fire(source.session_key)
        ticket = KDSTicket.objects.get(session_key=source.session_key)
        ticket.status = "in_progress"
        ticket.save(update_fields=["status"])

        self._move(source, ["L-A"], to_session_key=target.session_key)

        moved = self._line(target, "MV-A")
        self.assertTrue(moved["fired"], "a linha enviada chega enviada no destino")
        self.assertEqual(moved["fired_qty"], 2)
        self.assertEqual(moved["kitchen_status"], "in_progress", "o preparo continua de onde estava")
        # O ticket segue o prato: mesmo ticket, agora da comanda de destino.
        ticket.refresh_from_db()
        self.assertEqual(ticket.session_key, target.session_key)
        self.assertEqual(ticket.status, "in_progress")
        self.assertEqual([it["line_id"] for it in ticket.items], [moved["line_id"]])
        self.assertFalse(KDSTicket.objects.filter(session_key=source.session_key).exists())
        self.assertEqual(Session.objects.get(pk=source.pk).data.get("fired_lines"), [])

        # Enviar o destino manda só o que é dele e ainda não foi.
        self._fire(target.session_key)
        self.assertEqual(self._kitchen_lines(), [("MV-A", target.session_key), ("MV-B", target.session_key)])
        self.assertEqual(self._fire(target.session_key).fired_count, 0)

    def test_unfired_line_moves_still_to_send(self) -> None:
        source = self._open("1007", [{"line_id": "L-A", "sku": "MV-A", "name": "A", "qty": 1, "unit_price_q": 1000}])
        target = self._open("1008", [{"line_id": "L-B", "sku": "MV-B", "name": "B", "qty": 1, "unit_price_q": 1000}])

        self._move(source, ["L-A"], to_session_key=target.session_key)

        self.assertFalse(self._line(target, "MV-A")["fired"])
        self.assertEqual(self._fire(target.session_key).fired_count, 1)
        self.assertEqual(self._kitchen_lines(), [("MV-A", target.session_key), ("MV-B", target.session_key)])

    # ── separar ────────────────────────────────────────────────────────

    def test_split_part_of_a_ticket_divides_it_without_duplicating(self) -> None:
        source = self._open("1007", [
            {"line_id": "L-A", "sku": "MV-A", "name": "A", "qty": 1, "unit_price_q": 1000},
            {"line_id": "L-B", "sku": "MV-B", "name": "B", "qty": 1, "unit_price_q": 1000},
        ])
        self._fire(source.session_key)
        original = KDSTicket.objects.get(session_key=source.session_key)
        original.status = "in_progress"
        original.save(update_fields=["status"])

        result = self._move(source, ["L-A"], to_tab_ref="1009")
        target = result.target

        # A origem fica com o que é dela; o prato movido segue com o destino,
        # no mesmo estado, sem ticket novo "pendente" para a cozinha refazer.
        original.refresh_from_db()
        self.assertEqual([it["sku"] for it in original.items], ["MV-B"])
        self.assertEqual(original.status, "in_progress")
        moved_ticket = KDSTicket.objects.get(session_key=target.session_key)
        self.assertEqual(moved_ticket.status, "in_progress")
        self.assertEqual(moved_ticket.kds_instance_id, original.kds_instance_id)
        self.assertEqual(moved_ticket.created_at, original.created_at)
        self.assertEqual(self._kitchen_lines(), [("MV-A", target.session_key), ("MV-B", source.session_key)])
        self.assertTrue(self._line(target, "MV-A")["fired"])
        self.assertTrue(self._line(source, "MV-B")["fired"])

        self.assertEqual(self._fire(target.session_key).fired_count, 0)
        self.assertEqual(self._fire(source.session_key).fired_count, 0)
        self.assertEqual(KDSTicket.objects.exclude(status="cancelled").count(), 2)

    # ── juntar ─────────────────────────────────────────────────────────

    def test_merge_carries_every_fired_line_and_closes_source(self) -> None:
        source = self._open("1007", [
            {"line_id": "L-A", "sku": "MV-A", "name": "A", "qty": 1, "unit_price_q": 1000},
            {"line_id": "L-C", "sku": "MV-C", "name": "C", "qty": 1, "unit_price_q": 1000},
        ])
        target = self._open("1008", [{"line_id": "L-B", "sku": "MV-B", "name": "B", "qty": 1, "unit_price_q": 1000}])
        self._fire(source.session_key, ["L-A"])  # C fica por enviar
        self._fire(target.session_key)

        result = self._move(
            source, ["L-A", "L-C"], to_session_key=target.session_key, close_source_when_empty=True,
        )
        self.assertTrue(result.source_closed)

        self.assertTrue(self._line(target, "MV-A")["fired"])
        self.assertFalse(self._line(target, "MV-C")["fired"])
        fire = self._fire(target.session_key)
        self.assertEqual(fire.fired_count, 1, "só o C, que nunca foi, vai à cozinha")
        self.assertEqual(
            self._kitchen_lines(),
            [("MV-A", target.session_key), ("MV-B", target.session_key), ("MV-C", target.session_key)],
        )

    # ── herdada (venda sem conexão) ────────────────────────────────────

    def test_inherited_line_keeps_being_inherited_after_move(self) -> None:
        """A linha que a comanda herdou já enviada (``kds_inherited_lines``) não volta à cozinha ao mudar de comanda."""
        source = self._open("1007", [{"line_id": "L-A", "sku": "MV-A", "name": "A", "qty": 1, "unit_price_q": 1000}])
        target = self._open("1008", [{"line_id": "L-B", "sku": "MV-B", "name": "B", "qty": 1, "unit_price_q": 1000}])
        source.data = {**source.data, KDS_INHERITED_KEY: ["L-A"], "fired_lines": ["L-A"], "fired_qty": {"L-A": 1}}
        source.save(update_fields=["data"])

        self._move(source, ["L-A"], to_session_key=target.session_key)

        moved = self._line(target, "MV-A")
        self.assertTrue(moved["fired"])
        self.assertEqual(Session.objects.get(pk=target.pk).data[KDS_INHERITED_KEY], [moved["line_id"]])
        self.assertEqual(Session.objects.get(pk=source.pk).data.get(KDS_INHERITED_KEY), [])
        self.assertEqual(self._fire(target.session_key).fired_count, 1)  # só o B
        self.assertEqual(self._kitchen_lines(), [("MV-B", target.session_key)])
