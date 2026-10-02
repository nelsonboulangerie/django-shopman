"""Escolhas no produto no PDV (Fase 1, dono 02/10/2026).

A comanda salva, reaberta e fechada mantém a escolha (``meta["options"]``) e a
identidade da linha: a cozinha recebe uma vez só, com o produto pelo nome e a
escolha na observação; o pedido cobra produto + opção numa linha só.
"""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Order, Session

from shopman.backstage.models import KDSInstance, KDSTicket, POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError

CROQUE_GROUPS = [
    {
        "ref": "adicionais", "label": "Adicionais", "min": 0, "max": 2,
        "options": [
            {"ref": "ovo-frito", "label": "Ovo frito", "price_q": 400, "available": True,
             "consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}]},
            {"ref": "salada", "label": "Salada", "price_q": 300, "available": True, "consumes": []},
        ],
    },
]
FRAPPE_GROUPS = [
    {
        "ref": "sabor", "label": "Sabor", "min": 1, "max": 1,
        "options": [{"ref": "cafe", "label": "Café", "price_q": 0, "available": True, "consumes": []}],
    },
]
EGG = [{"group": "adicionais", "ref": "ovo-frito"}]


class POSProductOptionsTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(ref="00002001", label="2001")
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user(username="alice", password="x")
        KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")
        from shopman.offerman.models import Product

        Product.objects.create(
            sku="CQMO", name="Croque Monsieur", base_price_q=2400, is_published=True, is_sellable=True,
            metadata={"option_groups": CROQUE_GROUPS},
        )
        Product.objects.create(
            sku="FRAP", name="Frappé", base_price_q=1800, is_published=True, is_sellable=True,
            metadata={"option_groups": FRAPPE_GROUPS},
        )

    def _open_tab(self) -> str:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="2001", actor="pos:alice", operator_username="alice",
        ))
        return opened["tab_session_key"]

    def _save(self, session_key: str, items: list[dict]) -> Session:
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={
                "items": items, "customer_name": "Ana", "payment_method": "cash",
                "manual_discount": None, "tab_ref": "2001", "tab_session_key": session_key,
            },
            actor="pos:alice", operator_username="alice",
        )
        return Session.objects.get(session_key=session_key)

    def _croque_lines(self) -> list[dict]:
        return [
            {"line_id": "L-OVO", "sku": "CQMO", "name": "Croque Monsieur (+ Ovo frito)", "qty": 2,
             "unit_price_q": 2800, "options": EGG, "notes": "gema mole"},
            {"line_id": "L-PURO", "sku": "CQMO", "name": "Croque Monsieur", "qty": 1, "unit_price_q": 2400},
        ]

    def test_save_reopen_fire_and_close_keep_the_options_and_fire_once(self) -> None:
        skey = self._open_tab()
        session = self._save(skey, self._croque_lines())

        by_id = {item["line_id"]: item for item in session.items}
        self.assertEqual(by_id["L-OVO"]["name"], "Croque Monsieur (+ Ovo frito)")
        self.assertEqual(by_id["L-OVO"]["unit_price_q"], 2800)
        self.assertEqual(by_id["L-OVO"]["meta"]["options"][0]["consumes"], [{"sku": "OVOS", "qty": "50", "unit": "g"}])
        self.assertNotIn("options", by_id["L-PURO"]["meta"])
        self.assertEqual(by_id["L-PURO"]["unit_price_q"], 2400)

        # Reaberta, a comanda devolve a escolha (sem o insumo) para o PDV reenviar.
        reopened = {item["line_id"]: item for item in build_open_tab(session)["items"]}
        self.assertEqual(
            reopened["L-OVO"]["options"],
            [{"group": "adicionais", "ref": "ovo-frito", "group_label": "Adicionais",
              "name": "Ovo frito", "unit_price_q": 400}],
        )
        self.assertEqual(reopened["L-PURO"]["options"], [])

        # Salvar de novo com o que voltou não duplica o resumo no nome.
        resent = [
            {"line_id": item["line_id"], "sku": item["sku"], "name": item["name"], "qty": item["qty"],
             "unit_price_q": item["price_q"], "options": item["options"], "notes": item["notes"]}
            for item in build_open_tab(session)["items"]
        ]
        session = self._save(skey, resent)
        self.assertEqual(
            sorted(item["name"] for item in session.items),
            ["Croque Monsieur", "Croque Monsieur (+ Ovo frito)"],
        )

        pos_service.fire_pos_tab(channel_ref="pdv", session_key=skey, actor="pos:alice", operator_username="alice")
        ticket = KDSTicket.objects.get(session_key=skey)
        kitchen = {entry["line_id"]: entry for entry in ticket.items}
        # A cozinha lê o produto pelo nome e a escolha na observação, antes da nota.
        self.assertEqual(kitchen["L-OVO"]["name"], "Croque Monsieur")
        self.assertEqual(kitchen["L-OVO"]["notes"], "+ Ovo frito\ngema mole")
        self.assertEqual(kitchen["L-PURO"]["notes"], "")
        # E a nota gravada na linha continua sendo só o texto do operador.
        session.refresh_from_db()
        self.assertEqual(
            next(item for item in session.items if item["line_id"] == "L-OVO")["meta"]["notes"], "gema mole",
        )

        from django.contrib.auth import get_user_model
        from shopman.cashman import services as cash

        shift = cash.open_shift(operator=get_user_model().objects.get(username="alice"), float_q=0)
        pos_service.close_sale(
            channel_ref="pdv",
            payload={
                "intent_version": pos_service.POS_SALE_INTENT_VERSION,
                "cash_shift_id": shift.pk, "tab_ref": "2001", "tab_session_key": skey,
                "items": resent, "fulfillment_type": "pickup", "payment_method": "cash",
                "payment_collection": "terminal", "tendered_q": 8000,
                "client_request_id": "pos-options-close-001",
            },
            actor="pos:alice", operator_username="alice",
        )

        order = Order.objects.get(session_key=skey)
        items = {item.line_id: item for item in order.items.all()}
        self.assertEqual(set(items), {"L-OVO", "L-PURO"})
        self.assertEqual(items["L-OVO"].unit_price_q, 2800)
        self.assertEqual(items["L-OVO"].line_total_q, 5600)
        self.assertEqual(items["L-OVO"].meta["options"][0]["ref"], "ovo-frito")
        self.assertEqual(order.total_q, 8000)
        self.assertEqual(KDSTicket.objects.filter(session_key=skey).exclude(status="cancelled").count(), 1)

    def test_frappe_without_flavor_is_refused_with_the_line_named(self) -> None:
        skey = self._open_tab()
        with self.assertRaises(PosIntentError) as caught:
            self._save(skey, [{"line_id": "L-F", "sku": "FRAP", "name": "Frappé", "qty": 1, "unit_price_q": 1800}])
        self.assertEqual(caught.exception.code, "option_required")
        self.assertEqual(caught.exception.field, "items.0.options")

        session = self._save(skey, [{
            "line_id": "L-F", "sku": "FRAP", "name": "Frappé", "qty": 1, "unit_price_q": 1800,
            "options": [{"group": "sabor", "ref": "cafe"}],
        }])
        self.assertEqual(session.items[0]["name"], "Frappé (Café)")
