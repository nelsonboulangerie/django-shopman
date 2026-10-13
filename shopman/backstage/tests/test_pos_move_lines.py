"""Transfer / split / merge comanda lines via move_pos_tab_lines."""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Session

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError


def _payload(*, sku: str, qty: int, tab_ref: str, tab_session_key: str) -> dict:
    return {
        "items": [{"sku": sku, "name": sku, "qty": qty, "unit_price_q": 1000}],
        "payment_method": "cash",
        "manual_discount": None,
        "tab_ref": tab_ref,
        "tab_session_key": tab_session_key or None,
    }


class POSMoveTabLinesTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(ref="00001007", label="1007")
        POSTab.objects.create(ref="00001008", label="1008")
        # A comanda carimba quem lançou cada linha: o operador precisa existir.
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user(username="alice", password="x")
        from shopman.offerman.models import Product

        Product.objects.create(sku="POS-A", name="A", base_price_q=1000, is_published=True, is_sellable=True)
        Product.objects.create(sku="POS-B", name="B", base_price_q=1000, is_published=True, is_sellable=True)

    def _open_with_item(self, tab_ref: str, *, sku: str, qty: int) -> Session:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref=tab_ref, actor="pos:alice", operator_username="alice",
        ))
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(sku=sku, qty=qty, tab_ref=opened["tab_ref"], tab_session_key=opened["tab_session_key"]),
            actor="pos:alice", operator_username="alice",
        )
        return Session.objects.get(session_key=opened["tab_session_key"])

    def test_transfer_line_to_existing_tab_freezes_price(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        target = self._open_with_item("00001008", sku="POS-B", qty=1)
        line_id = source.items[0]["line_id"]

        result = pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_session_key=target.session_key,
            line_ids=[line_id],
            actor="pos:alice", operator_username="alice",
        )

        self.assertIsNotNone(result.target)
        self.assertFalse(result.source_closed)
        source.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(source.items, [])
        moved = next(item for item in target.items if item["sku"] == "POS-A")
        self.assertEqual(int(moved["qty"]), 2)
        self.assertEqual(moved["unit_price_q"], 1000)  # frozen verbatim

    def test_split_creates_new_tab_with_moved_line(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        line_id = source.items[0]["line_id"]

        result = pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_tab_ref="1009",
            line_ids=[line_id],
            actor="pos:alice", operator_username="alice",
        )

        self.assertIsNotNone(result.target)
        source.refresh_from_db()
        self.assertEqual(source.items, [])
        target = Session.objects.get(
            channel_ref="pdv", handle_type="pos_tab", handle_ref="00001009", state="open",
        )
        self.assertEqual(int(target.items[0]["qty"]), 2)
        self.assertEqual(target.items[0]["unit_price_q"], 1000)

    def test_merge_closes_emptied_source(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        target = self._open_with_item("00001008", sku="POS-B", qty=1)
        line_ids = [item["line_id"] for item in source.items]

        result = pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_session_key=target.session_key,
            line_ids=line_ids,
            close_source_when_empty=True,
            actor="pos:alice", operator_username="alice",
        )

        self.assertTrue(result.source_closed)
        self.assertIsNone(result.source)
        source.refresh_from_db()
        self.assertEqual(source.state, "abandoned")
        target.refresh_from_db()
        self.assertEqual(len(target.items), 2)

    def _merge(self, source: Session, target: Session) -> None:
        pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_session_key=target.session_key,
            line_ids=[item["line_id"] for item in source.items],
            close_source_when_empty=True,
            actor="pos:alice", operator_username="alice",
        )

    def test_merge_carries_customer_to_target_without_one(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=1)
        target = self._open_with_item("00001008", sku="POS-B", qty=1)
        Session.objects.filter(pk=source.pk).update(
            data={**source.data, "customer": {"name": "Ana", "phone": "5543999990001", "ref": "C-1"}, "customer_ref": "C-1"},
        )
        source.refresh_from_db()

        self._merge(source, target)

        target.refresh_from_db()
        self.assertEqual(target.data["customer"]["name"], "Ana")
        self.assertEqual(target.data["customer_ref"], "C-1")

    def test_merge_never_overwrites_target_customer(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=1)
        target = self._open_with_item("00001008", sku="POS-B", qty=1)
        Session.objects.filter(pk=source.pk).update(data={**source.data, "customer": {"name": "Ana", "ref": "C-1"}, "customer_ref": "C-1"})
        Session.objects.filter(pk=target.pk).update(data={**target.data, "customer": {"name": "Bia", "ref": "C-2"}, "customer_ref": "C-2"})
        source.refresh_from_db()
        target.refresh_from_db()

        self._merge(source, target)

        target.refresh_from_db()
        self.assertEqual(target.data["customer"]["name"], "Bia")
        self.assertEqual(target.data["customer_ref"], "C-2")

    def test_transfer_does_not_move_customer(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=1)
        target = self._open_with_item("00001008", sku="POS-B", qty=1)
        Session.objects.filter(pk=source.pk).update(data={**source.data, "customer": {"name": "Ana", "ref": "C-1"}, "customer_ref": "C-1"})
        source.refresh_from_db()

        pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_session_key=target.session_key,
            line_ids=[source.items[0]["line_id"]],
            actor="pos:alice", operator_username="alice",
        )

        target.refresh_from_db()
        self.assertFalse(target.data.get("customer_ref"))

    def test_transfer_of_every_line_releases_the_emptied_source(self) -> None:
        # Dono, T2=1 (13/10/2026): a comanda que fica vazia é liberada sozinha.
        source = self._open_with_item("00001007", sku="POS-A", qty=1)
        target = self._open_with_item("00001008", sku="POS-B", qty=1)
        result = pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_session_key=target.session_key,
            line_ids=[item["line_id"] for item in source.items],
            close_source_when_empty=True,
            actor="pos:alice", operator_username="alice",
        )
        self.assertTrue(result.source_closed)
        source.refresh_from_db()
        self.assertEqual(source.state, "abandoned")

    def test_split_of_every_line_releases_the_source_and_carries_the_customer(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=1)
        Session.objects.filter(pk=source.pk).update(data={**source.data, "customer": {"name": "Ana", "ref": "C-1"}, "customer_ref": "C-1"})
        source.refresh_from_db()
        result = pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_tab_ref="1007-2",
            line_ids=[item["line_id"] for item in source.items],
            close_source_when_empty=True,
            actor="pos:alice", operator_username="alice",
        )
        self.assertTrue(result.source_closed)
        self.assertEqual(result.target.data["customer_ref"], "C-1")

    def test_new_tab_keeps_the_trail_and_both_tabs_log_the_transfer(self) -> None:
        # Dono, T1=1 (13/10/2026): a comanda nova guarda de onde veio, e o log do PDV
        # diz quem, quando e quais itens.
        from shopman.orderman.models import SessionEvent

        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_tab_ref="1007-2",
            line_ids=[source.items[0]["line_id"]],
            actor="pos:alice", operator_username="alice",
        )
        target = Session.objects.get(channel_ref="pdv", handle_type="pos_tab", handle_ref="1007-2", state="open")
        trail = target.data["transferred_from"]
        self.assertEqual(trail["tab_display"], "1007")
        self.assertEqual(trail["session_key"], source.session_key)
        self.assertEqual(trail["by"], "alice")
        view = build_open_tab(target)["transferred_from"]
        self.assertEqual(view, {"tab_display": "1007", "label": "Transf. da #1007", "title": "Transferida da comanda #1007"})
        self.assertIsNone(build_open_tab(source)["transferred_from"])
        out = SessionEvent.objects.get(session_key=source.session_key, type="lines_transferred_out")
        incoming = SessionEvent.objects.get(session_key=target.session_key, type="lines_transferred_in")
        self.assertEqual(out.actor, "alice")
        self.assertEqual(incoming.payload["items"], [{"sku": "POS-A", "name": "POS-A", "qty": 2}])
        self.assertTrue(incoming.payload["new_tab"])

    def test_trail_label_for_the_order_detail(self) -> None:
        from shopman.backstage.projections.order_queue import transferred_from_label

        self.assertEqual(transferred_from_label({"transferred_from": {"tab_display": "13"}}), "Transferida da comanda #13")
        self.assertEqual(transferred_from_label({"transferred_from": {"tab_display": "Mesa 6"}}), "Transferida da comanda Mesa 6")
        self.assertEqual(transferred_from_label({}), "")

    def test_split_ref_with_slash_is_refused_with_a_clear_message(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=1)
        with self.assertRaises(PosIntentError) as raised:
            pos_service.move_pos_tab_lines(
                channel_ref="pdv",
                from_session_key=source.session_key,
                to_tab_ref="1007/2",
                line_ids=[source.items[0]["line_id"]],
                actor="pos:alice", operator_username="alice",
            )
        self.assertIn("1007-2", raised.exception.message)

    def test_split_rollback_failure_does_not_mask_move_error(self) -> None:
        # If the split target is created but the move fails, the cleanup
        # (abandon_session) is best-effort: a cleanup failure must NOT mask the
        # original move error the operator needs to see.
        from unittest.mock import patch

        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        line_id = source.items[0]["line_id"]

        with (
            patch.object(pos_service.session_service, "move_session_lines", side_effect=RuntimeError("kernel boom")),
            patch.object(pos_service.session_service, "abandon_session", side_effect=RuntimeError("cleanup boom")),
        ):
            with self.assertRaises(PosIntentError) as ctx:
                pos_service.move_pos_tab_lines(
                    channel_ref="pdv",
                    from_session_key=source.session_key,
                    to_tab_ref="1009",
                    line_ids=[line_id],
                    actor="pos:alice", operator_username="alice",
                )
        # the original move error surfaces (move_failed), not the cleanup RuntimeError
        self.assertEqual(ctx.exception.code, "move_failed")

    def test_split_to_occupied_ref_is_rejected(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        self._open_with_item("00001008", sku="POS-B", qty=1)
        line_id = source.items[0]["line_id"]

        with self.assertRaises(PosIntentError) as ctx:
            pos_service.move_pos_tab_lines(
                channel_ref="pdv",
                from_session_key=source.session_key,
                to_tab_ref="1008",
                line_ids=[line_id],
                actor="pos:alice", operator_username="alice",
            )
        self.assertEqual(ctx.exception.code, "tab_in_use")
