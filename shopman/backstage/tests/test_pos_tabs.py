"""POS tab mutation semantics."""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Order, Session

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab, build_pos_tabs
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError


def _grant_pos_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from shopman.cashman.models import Shift

    ct = ContentType.objects.get_for_model(Shift)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


def _payload(
    *,
    sku: str = "POS-TAB-ITEM",
    name: str = "Tab Item",
    qty: int = 1,
    customer_name: str = "Ana",
    customer_phone: str = "",
    tab_ref: str = "00001007",
    tab_session_key: str = "",
) -> dict:
    return {
        "items": [{"sku": sku, "name": name, "qty": qty, "unit_price_q": 1000}],
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "payment_method": "cash",
        "manual_discount": None,
        "tab_ref": tab_ref,
        "tab_session_key": tab_session_key or None,
    }


class POSTabSessionTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        # Fechar venda exige turno de caixa aberto do operador (a linha `sale`
        # nasce no livro do cashman); o pk vai no payload como faz o backstage.
        from django.contrib.auth import get_user_model
        from shopman.cashman import services as cash

        alice = get_user_model().objects.create_user(username="alice", password="x")
        self.shift = cash.open_shift(operator=alice, float_q=0)
        POSTab.objects.create(ref="00001007", label="1007")
        POSTab.objects.create(ref="00001008", label="1008")
        from shopman.offerman.models import Product

        Product.objects.create(
            sku="POS-TAB-ITEM",
            name="Tab Item",
            base_price_q=1000,
            is_published=True,
            is_sellable=True,
        )
        Product.objects.create(
            sku="POS-TAB-ALT",
            name="Alt Item",
            base_price_q=1000,
            is_published=True,
            is_sellable=True,
        )

    def test_opening_empty_tab_creates_open_session(self) -> None:
        payload = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:alice",
            operator_username="alice",
        ))

        self.assertEqual(payload["tab_ref"], "00001007")
        self.assertEqual(payload["tab_display"], "1007")
        self.assertEqual(payload["items"], [])
        session = Session.objects.get(session_key=payload["tab_session_key"])
        self.assertEqual(session.handle_type, "pos_tab")
        self.assertEqual(session.handle_ref, "00001007")
        self.assertEqual(session.data["tab_ref"], "00001007")

    def test_saving_tab_keeps_single_in_use_session(self) -> None:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="00001007",
            actor="pos:alice",
            operator_username="alice",
        ))

        saved = pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(qty=2, tab_session_key=opened["tab_session_key"]),
            actor="pos:alice",
            operator_username="alice",
        )

        self.assertEqual(saved.tab_ref, "00001007")
        session = Session.objects.get(session_key=saved.session_key)
        self.assertEqual(Session.objects.filter(channel_ref="pdv", state="open").count(), 1)
        self.assertEqual(int(session.items[0]["qty"]), 2)

    def test_saving_tab_stamps_list_price_on_session_lines(self) -> None:
        """F4: a linha da comanda carrega a etiqueta (meta._list_q).

        Sem o carimbo na sessao, a review fica sem regua para o "maior
        desconto ganha" e sem preco para devolver quando o payload omite
        unit_price_q.
        """
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="1007",
            actor="pos:alice", operator_username="alice",
        ))
        skey = opened["tab_session_key"]
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(qty=2, tab_session_key=skey),
            actor="pos:alice", operator_username="alice",
        )
        session = Session.objects.get(session_key=skey)
        self.assertEqual((session.items[0].get("meta") or {}).get("_list_q"), 1000)

    def test_review_without_declared_prices_uses_session_prices(self) -> None:
        """F1: review com item sem unit_price_q usa o preco da sessao.

        A revisao nao pode devolver total 0 (e troco do valor inteiro
        entregue) quando o payload omite o preco — o carimbo da sessao cobre.
        """
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="1007",
            actor="pos:alice", operator_username="alice",
        ))
        skey = opened["tab_session_key"]
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(qty=2, tab_session_key=skey),
            actor="pos:alice", operator_username="alice",
        )
        payload = _payload(qty=2, tab_session_key=skey)
        payload["items"] = [{"sku": "POS-TAB-ITEM", "name": "Tab Item", "qty": 2}]
        payload["payment_tenders"] = [{"method": "cash", "amount_q": 2000}]
        payload["tendered_q"] = 2000
        review = pos_service.review_sale(
            channel_ref="pdv", payload=payload, operator_username="alice",
        )
        self.assertEqual(review.subtotal_q, 2000)
        self.assertEqual(review.total_q, 2000)
        self.assertEqual(review.change_q, 0)

    def test_review_without_session_and_prices_fails_loudly(self) -> None:
        """F1: sem sessao e sem preco declarado, a review recusa com clareza."""
        payload = _payload(tab_ref="", tab_session_key="")
        payload["items"] = [{"sku": "POS-TAB-ITEM", "name": "Tab Item", "qty": 1}]
        with self.assertRaises(PosIntentError) as ctx:
            pos_service.review_sale(
                channel_ref="pdv", payload=payload, operator_username="alice",
            )
        self.assertEqual(ctx.exception.code, "price_not_resolved")

    def test_open_tab_exposes_the_pricing_discount_stamped_on_the_line(self) -> None:
        """Transparência do desconto automático (o caso Batard 13,00 → 11,05).

        Os modifiers de pricing carimbam o desconto vencedor em ``meta._disc``
        (mecanismo ``_stamp_disc``: tipo, valor por unidade e rótulo) e o preço
        de lista em ``meta._list_q``. O payload da comanda expõe isso como
        ``pricing_discount`` para o PDV rotular a linha; o desconto MANUAL não
        entra aqui (já viaja em ``discount``).
        """
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="1007",
            actor="pos:alice", operator_username="alice",
        ))
        skey = opened["tab_session_key"]
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(sku="BATARD", name="Batard", tab_session_key=skey),
            actor="pos:alice", operator_username="alice",
        )
        session = Session.objects.get(session_key=skey)
        items = session.items
        # O carimbo durável dos modifiers (fonte: shopman/shop/modifiers.py).
        items[0]["meta"] = {
            **(items[0].get("meta") or {}),
            "_list_q": 1300,
            "_disc": {"type": "lot_discount", "amount_q": 195, "label": "Liquidação"},
        }
        items[0]["unit_price_q"] = 1105
        session.update_items(items)

        payload = build_open_tab(Session.objects.get(session_key=skey))
        self.assertEqual(payload["items"][0]["pricing_discount"], {
            "type": "lot_discount",
            "label": "Liquidação",
            "amount_q": 195,
            "percent": 15,
        })

        # Desconto manual continua fora do pricing_discount.
        items = Session.objects.get(session_key=skey).items
        items[0]["meta"]["_disc"] = {"type": "manual", "amount_q": 100, "label": "Cortesia"}
        session = Session.objects.get(session_key=skey)
        session.update_items(items)
        payload = build_open_tab(Session.objects.get(session_key=skey))
        self.assertIsNone(payload["items"][0]["pricing_discount"])

    def test_reopening_in_use_tab_loads_existing_cart(self) -> None:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:alice",
            operator_username="alice",
        ))
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(qty=3, tab_session_key=opened["tab_session_key"]),
            actor="pos:alice",
            operator_username="alice",
        )

        loaded = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="00001007",
            actor="pos:bob",
            operator_username="bob",
        ))

        self.assertEqual(loaded["tab_session_key"], opened["tab_session_key"])
        self.assertEqual(loaded["items"][0]["qty"], 3)

    def test_reopening_saved_tab_does_not_replay_generated_payment_tender(self) -> None:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:alice",
            operator_username="alice",
        ))
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(qty=1, tab_session_key=opened["tab_session_key"]),
            actor="pos:alice",
            operator_username="alice",
        )
        session = Session.objects.get(session_key=opened["tab_session_key"])
        self.assertEqual(session.data["payment"]["tenders"][0]["amount_q"], 1000)

        loaded = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:bob",
            operator_username="bob",
        ))

        self.assertEqual(loaded["payment_tenders"], [])
        self.assertEqual(loaded["tendered_q"], "")

    def test_saving_tab_allows_incomplete_mixed_payment_draft(self) -> None:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:alice",
            operator_username="alice",
        ))
        payload = _payload(qty=2, tab_session_key=opened["tab_session_key"])
        payload.update({
            "cash_shift_id": self.shift.pk,
            "payment_method": "mixed",
            "payment_tenders": [
                {"method": "cash", "amount_q": 1000, "collection": "terminal"},
            ],
        })

        saved = pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=payload,
            actor="pos:alice",
            operator_username="alice",
        )

        session = Session.objects.get(session_key=saved.session_key)
        self.assertEqual(session.data["payment"]["method"], "mixed")
        self.assertEqual(session.data["payment"]["tenders"][0]["amount_q"], 1000)

    def test_closing_tab_consumes_original_session_and_frees_tab(self) -> None:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:alice",
            operator_username="alice",
        ))
        result = pos_service.close_sale(
            channel_ref="pdv",
            payload={**_payload(qty=2, tab_session_key=opened["tab_session_key"]), "cash_shift_id": self.shift.pk},
            actor="pos:alice",
            operator_username="alice",
        )

        order = Order.objects.get(ref=result.order_ref)
        session = Session.objects.get(session_key=opened["tab_session_key"])
        self.assertEqual(order.session_key, opened["tab_session_key"])
        self.assertEqual(session.state, "committed")
        self.assertEqual(order.total_q, 2000)
        self.assertEqual(build_pos_tabs(channel_ref="pdv")[0].state, "empty")
        self.assertEqual(order.data["tab_ref"], "00001007")

    def test_closing_tab_persists_checkout_fields(self) -> None:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:alice",
            operator_username="alice",
        ))
        payload = _payload(tab_session_key=opened["tab_session_key"], customer_phone="43999990000")
        payload.update({
            "cash_shift_id": self.shift.pk,
            "fiscal_tax_id": "52998224725",
            "tendered_q": 5000,
            "receipt_channels": ["email"],
            "receipt_email": "ana@example.com",
        })

        result = pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor="pos:alice",
            operator_username="alice",
        )

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.data["payment"]["method"], "cash")
        self.assertEqual(order.data["payment"]["tendered_q"], 5000)
        # DUAS perguntas, dois campos — mas não dois mundos. Pedir CPF na nota
        # escreve o bloco fiscal SEMPRE; e como este cliente não tinha documento
        # no cadastro, a lacuna aprende (é o que faz o campo vir pré-preenchido na
        # próxima venda). Sobrescrever é que não acontece: cadastro com CPF fica
        # como está, por mais que o checkout peça outro.
        self.assertEqual(order.data["fiscal"], {"tax_id": "52998224725"})
        self.assertEqual(order.data["customer"]["tax_id"], "52998224725")
        self.assertEqual(order.data["receipt"], {"channels": ["email"], "email": "ana@example.com"})

    def test_closing_tab_can_create_delivery_with_payment_on_delivery(self) -> None:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:alice",
            operator_username="alice",
        ))
        payload = _payload(tab_session_key=opened["tab_session_key"], customer_phone="43999990000")
        payload.update({
            "cash_shift_id": self.shift.pk,
            "fulfillment_type": "delivery",
            "delivery_address": "Rua das Flores, 100",
            "delivery_time_slot": "14:00-14:30",
            "order_notes": "Portaria",
            "payment_method": "cash",
            "payment_collection": "on_delivery",
        })

        result = pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor="pos:alice",
            operator_username="alice",
        )

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.data["fulfillment_type"], "delivery")
        self.assertEqual(order.data["delivery_address"], "Rua das Flores, 100")
        self.assertEqual(order.data["delivery_time_slot"], "14:00-14:30")
        self.assertEqual(order.data["order_notes"], "Portaria")
        self.assertEqual(order.data["payment"]["method"], "cash")
        self.assertEqual(order.data["payment"]["collection"], "on_delivery")
        self.assertNotIn("cash_received_q", order.data["payment"])

    def test_tab_projection_shows_empty_and_in_use_tabs(self) -> None:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:alice",
            operator_username="alice",
        ))
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(customer_name="Ana Mesa", customer_phone="43999990000", tab_session_key=opened["tab_session_key"]),
            actor="pos:alice",
            operator_username="alice",
        )

        tabs = build_pos_tabs(channel_ref="pdv")
        self.assertEqual([(tab.ref, tab.state) for tab in tabs], [("00001007", "in_use"), ("00001008", "empty")])
        self.assertEqual([tab.ref for tab in build_pos_tabs(channel_ref="pdv", query="1007")], ["00001007"])
        self.assertEqual([tab.ref for tab in build_pos_tabs(channel_ref="pdv", query="ana")], ["00001007"])
        self.assertEqual([tab.ref for tab in build_pos_tabs(channel_ref="pdv", query="1008")], ["00001008"])

