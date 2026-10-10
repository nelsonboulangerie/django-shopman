"""Mudança no que já está na cozinha chega com alarde, nunca em silêncio.

Decisão do dono (10/10/2026): quando o PDV mexe num item que já foi enviado
(remove, diminui, observação nova, cancela o envio, libera a comanda, transfere,
a comanda vira pedido), o ajuste é automático, mas a cozinha recebe a mudança
"com alarde, a cada mudança. Jamais silenciosamente!".

Estes testes passam pelos caminhos canônicos do servidor (``pos_service`` e
``kds`` do shop) e leem o quadro como a estação lê (``build_kds_board``):

- o item que saiu aparece NO CARD vivo do pedido ("Cancelado: 1× Fire B"), e o
  Pronto espera o Visto;
- a linha que volta com outra quantidade ou observação diz o que mudou;
- o pedido que cai inteiro vira card próprio, que não some sozinho;
- o pedido que muda de nome (comanda renomeada, paga, transferida) diz qual era.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Session

from shopman.backstage.models import KDSInstance, KDSTicket, POSTab
from shopman.backstage.projections.kds import build_kds_board
from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.models import Channel, Shop
from shopman.shop.services import kds as kds_core
from shopman.shop.services import pos as pos_service


class KDSChangesAreLoudTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(ref="00002001", label="2001")
        User = get_user_model()
        User.objects.create_user(username="alice", password="x")
        self.cook = User.objects.create_user(username="rafael", password="x", is_staff=True)
        self.cook.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(KDSTicket), codename="operate_kds",
            )
        )
        self.station = KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")
        from shopman.offerman.models import Product

        for sku in ("FIRE-A", "FIRE-B"):
            Product.objects.create(sku=sku, name=sku, base_price_q=1000, is_published=True, is_sellable=True)

    # ── a comanda, como o PDV a manipula ────────────────────────────────────

    def _open_tab(self) -> str:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="2001", actor="pos:alice", operator_username="alice",
        ))
        return opened["tab_session_key"]

    def _save(self, session_key: str, items: list[dict]) -> Session:
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={
                "items": items,
                "customer_name": "Ana",
                "payment_method": "cash",
                "manual_discount": None,
                "tab_ref": "2001",
                "tab_session_key": session_key,
            },
            actor="pos:alice", operator_username="alice",
        )
        return Session.objects.get(session_key=session_key)

    def _line(self, line_id: str, sku: str, qty: int = 1, notes: str = "") -> dict:
        return {"line_id": line_id, "sku": sku, "name": sku, "qty": qty, "unit_price_q": 1000, "notes": notes}

    def _fire(self, session_key: str, line_ids: list[str] | None = None) -> None:
        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session_key, line_ids=line_ids,
            actor="pos:alice", operator_username="alice",
        )

    def _unfire(self, session_key: str, line_ids: list[str]) -> None:
        pos_service.cancel_fired_pos_tab_lines(
            channel_ref="pdv", session_key=session_key, line_ids=line_ids,
            actor="pos:alice", operator_username="alice",
        )

    def _fired_tab(self) -> str:
        key = self._open_tab()
        self._save(key, [self._line("L-A", "FIRE-A"), self._line("L-B", "FIRE-B", qty=3)])
        self._fire(key)
        return key

    def _board(self):
        return build_kds_board(self.station.ref)

    def _seen(self, card, *, seen_ref: str | None = None):
        self.client.force_login(self.cook)
        return self.client.post(
            reverse("api-backstage-kds-ticket-changes-seen", args=[card.pk]),
            {"cancelled_pks": list(card.change_ticket_pks), "seen_ref": seen_ref or card.order_ref},
            content_type="application/json",
        )

    # ── os casos ────────────────────────────────────────────────────────────

    def test_item_removed_shows_on_the_live_card_and_holds_ready_until_seen(self) -> None:
        key = self._fired_tab()
        self._unfire(key, ["L-B"])

        board = self._board()
        [card] = board.tickets
        self.assertEqual([(c.kind, c.text) for c in card.changes], [("cancelled", "Cancelado: 3× FIRE-B")])
        self.assertEqual(board.cancelled_tickets, ())  # o aviso mora no card, não solto

        ticket = KDSTicket.objects.get(pk=card.pk)
        kds_core.start_ticket(ticket, actor="rafael")
        with self.assertRaises(kds_core.TicketCompletionBlocked):
            kds_core.complete_ticket(KDSTicket.objects.get(pk=card.pk), actor="rafael")

        response = self._seen(card)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["acknowledged"], 1)
        self.assertEqual(self._board().tickets[0].changes, ())
        self.assertTrue(kds_core.complete_ticket(KDSTicket.objects.get(pk=card.pk), actor="rafael"))

    def test_quantity_down_says_now_and_before(self) -> None:
        key = self._fired_tab()
        # O caminho canônico do ajuste automático: desfaz o envio da linha e envia de novo.
        self._save(key, [self._line("L-A", "FIRE-A"), self._line("L-B", "FIRE-B", qty=1)])
        self._unfire(key, ["L-B"])
        self._fire(key, ["L-B"])

        changes = [(c.kind, c.text) for t in self._board().tickets for c in t.changes]
        self.assertEqual(changes, [("qty", "FIRE-B: agora 1, eram 3")])

    def test_new_note_says_which_note(self) -> None:
        key = self._fired_tab()
        self._save(key, [self._line("L-A", "FIRE-A", notes="sem glúten"), self._line("L-B", "FIRE-B", qty=3)])
        self._unfire(key, ["L-A"])
        self._fire(key, ["L-A"])

        changes = [(c.kind, c.text) for t in self._board().tickets for c in t.changes]
        self.assertEqual(changes, [("note", "Observação nova em FIRE-A: sem glúten")])

    def test_released_tab_becomes_its_own_card_and_does_not_expire(self) -> None:
        key = self._fired_tab()
        pos_service.clear_pos_tab(channel_ref="pdv", session_key=key, operator_username="alice")

        # Meia hora depois, ninguém deu ciência: o card continua lá (antes sumia em 10 min).
        KDSTicket.objects.filter(session_key=key).update(cancelled_at=timezone.now() - timedelta(minutes=30))
        board = self._board()
        self.assertEqual(board.tickets, ())
        [cancelled] = board.cancelled_tickets
        self.assertTrue(cancelled.is_cancelled)
        self.assertEqual({item.name for item in cancelled.items}, {"FIRE-A", "FIRE-B"})

    def test_cancellation_from_yesterday_is_not_on_today_board(self) -> None:
        key = self._fired_tab()
        pos_service.clear_pos_tab(channel_ref="pdv", session_key=key, operator_username="alice")
        KDSTicket.objects.filter(session_key=key).update(cancelled_at=timezone.now() - timedelta(days=1))

        self.assertEqual(self._board().cancelled_tickets, ())

    def test_renamed_tab_says_what_it_was_until_seen(self) -> None:
        key = self._fired_tab()
        ticket = KDSTicket.objects.get(session_key=key)
        self.assertEqual(ticket.known_ref, "2001")

        pos_service.rename_pos_tab(
            channel_ref="pdv", session_key=key, new_tab_ref="Mesa 5", actor="pos:alice", operator_username="alice",
        )
        [card] = self._board().tickets
        self.assertEqual(card.order_ref, "Mesa 5")
        self.assertEqual([(c.kind, c.text) for c in card.changes], [("moved", "Era a comanda 2001")])

        response = self._seen(card)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["renamed"])
        self.assertEqual(self._board().tickets[0].changes, ())

    def test_seen_only_clears_what_the_screen_showed(self) -> None:
        key = self._fired_tab()
        self._unfire(key, ["L-B"])
        [card] = self._board().tickets
        # Chega outro cancelamento entre a leitura e o toque.
        self._unfire(key, ["L-A"])

        self._seen(card)
        board = self._board()
        # L-A esvaziou o ticket vivo: o pedido caiu inteiro e vira card próprio, com aviso.
        self.assertEqual(board.tickets, ())
        self.assertEqual(len(board.cancelled_tickets), 1)
        self.assertEqual(board.cancelled_tickets[0].items[0].name, "FIRE-A")

    def test_seen_never_clears_another_station_or_sale(self) -> None:
        key = self._fired_tab()
        self._unfire(key, ["L-B"])
        [card] = self._board().tickets
        other_key = self._fired_tab_on_another_tab()
        pos_service.clear_pos_tab(channel_ref="pdv", session_key=other_key, operator_username="alice")
        foreign = KDSTicket.objects.get(session_key=other_key)

        self.client.force_login(self.cook)
        response = self.client.post(
            reverse("api-backstage-kds-ticket-changes-seen", args=[card.pk]),
            {"cancelled_pks": [*card.change_ticket_pks, foreign.pk], "seen_ref": card.order_ref},
            content_type="application/json",
        )
        self.assertEqual(response.json()["acknowledged"], 1)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.acknowledged_at)

    def test_bad_cancelled_list_is_a_field_error(self) -> None:
        key = self._fired_tab()
        ticket = KDSTicket.objects.get(session_key=key)
        self.client.force_login(self.cook)
        response = self.client.post(
            reverse("api-backstage-kds-ticket-changes-seen", args=[ticket.pk]),
            {"cancelled_pks": "1", "seen_ref": "2001"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "cancelled_pks")

    def _fired_tab_on_another_tab(self) -> str:
        POSTab.objects.create(ref="00002002", label="2002")
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="2002", actor="pos:alice", operator_username="alice",
        ))
        key = opened["tab_session_key"]
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={
                "items": [self._line("M-A", "FIRE-A")],
                "payment_method": "cash",
                "manual_discount": None,
                "tab_ref": "2002",
                "tab_session_key": key,
            },
            actor="pos:alice", operator_username="alice",
        )
        self._fire(key)
        return key
