"""Adversarial audit of discount stacking / interaction (pricing safety).

Drives the REAL modifier chain (`ModifyService.modify_session`) to prove
concrete money bugs found in the audit. Each test asserts the CORRECT
invariant — while the bug is present these FAIL, which is the proof; after the
fix they become the regression guard.

Invariants under test:
- "maior desconto ganha": at most ONE discount applies per line (the best one);
  discounts must NOT compound (a later modifier taking % off an already-reduced
  unit price).
- a distributed order-level discount must reduce the charged total by EXACTLY
  its amount (no residue swallowed by a skipped line).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.ids import generate_session_key
from shopman.orderman.models import Session
from shopman.orderman.services.modify import ModifyService

from shopman.shop.models import Channel, RuleConfig


def _wide_window_params(discount_percent: int) -> dict:
    """Happy-hour params whose [start, end) window always contains 'now'."""
    now = timezone.localtime()
    start = (now - timedelta(hours=1)).strftime("%H:%M")
    end = (now + timedelta(hours=1)).strftime("%H:%M")
    # Guard against midnight wrap making start > end (window would be empty).
    if start > end:
        start, end = "00:00", "23:59"
    return {"discount_percent": discount_percent, "start": start, "end": end}


class DiscountStackingAuditTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.channel = Channel.objects.create(ref="web", name="Web", is_active=True)
        self.product = Product.objects.create(
            sku="AUDIT-SKU",
            name="Audit Product",
            base_price_q=1000,  # R$ 10,00 list
            is_published=True,
            is_sellable=True,
        )

    def tearDown(self) -> None:
        cache.clear()
        super().tearDown()

    def _open_session(self) -> str:
        key = generate_session_key()
        Session.objects.create(
            session_key=key,
            channel_ref="web",
            state="open",
            pricing_policy="fixed",  # keep the R$10 line price; don't re-resolve
            edit_policy="open",
            data={"origin_channel": "web"},
        )
        return key

    def _line(self, session: Session):
        return next(i for i in session.items if i.get("sku") == self.product.sku)

    # ── HOLE 1: happy hour must NOT compound on a D-1 line (best-wins) ───────
    def test_happy_hour_does_not_compound_on_d1(self) -> None:
        RuleConfig.objects.create(
            ref="d1_discount",
            rule_path="shopman.shop.rules.pricing.D1Rule",
            label="D-1",
            params={"discount_percent": 50},
            enabled=True,
        )
        RuleConfig.objects.create(
            ref="happy_hour",
            rule_path="shopman.shop.rules.pricing.HappyHourRule",
            label="Happy Hour",
            params=_wide_window_params(25),
            enabled=True,
        )
        cache.clear()

        key = self._open_session()
        session = ModifyService.modify_session(
            session_key=key,
            channel_ref="web",
            ops=[{"op": "add_line", "sku": self.product.sku, "qty": 1,
                  "unit_price_q": 1000, "is_d1": True}],
        )
        unit = self._line(session)["unit_price_q"]
        # Best-wins: the deeper discount (50% D-1) applies; happy hour must NOT
        # stack. Correct = 500. Bug compounds: 1000→500 (D-1)→375 (−25% again).
        self.assertEqual(unit, 500, f"happy hour compounded on D-1: got {unit}, expected 500")

    # ── HOLE 2: employee discount must NOT compound on a promo line (best-wins) ─
    def test_employee_does_not_compound_on_promotion(self) -> None:
        from shopman.storefront.models import Promotion

        now = timezone.now()
        Promotion.objects.create(
            name="Promo 30",
            type=Promotion.PERCENT,
            value=30,
            is_active=True,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
        )
        cache.clear()

        key = self._open_session()
        # Link a staff customer so the employee discount (20%) fires.
        ModifyService.modify_session(
            session_key=key, channel_ref="web",
            ops=[{"op": "set_data", "path": "customer", "value": {"group": "staff"}}],
        )
        session = ModifyService.modify_session(
            session_key=key, channel_ref="web",
            ops=[{"op": "add_line", "sku": self.product.sku, "qty": 1, "unit_price_q": 1000}],
        )
        unit = self._line(session)["unit_price_q"]
        # Best-wins: max(30% promo, 20% employee) = 30% → 700. Bug compounds:
        # 1000→700 (promo)→560 (−20% employee on the reduced price).
        self.assertEqual(unit, 700, f"employee compounded on promo: got {unit}, expected 700")

    # ── Invariante: cadeia inteira (D-1 + funcionário + happy hour) = 1 melhor ─
    def test_full_chain_takes_single_best_discount(self) -> None:
        RuleConfig.objects.create(
            ref="d1_discount", rule_path="shopman.shop.rules.pricing.D1Rule",
            label="D-1", params={"discount_percent": 50}, enabled=True,
        )
        RuleConfig.objects.create(
            ref="happy_hour", rule_path="shopman.shop.rules.pricing.HappyHourRule",
            label="Happy Hour", params=_wide_window_params(25), enabled=True,
        )
        cache.clear()

        key = self._open_session()
        # Staff customer + D-1 line + happy hour window open — all three "apply".
        ModifyService.modify_session(
            session_key=key, channel_ref="web",
            ops=[{"op": "set_data", "path": "customer", "value": {"group": "staff"}}],
        )
        session = ModifyService.modify_session(
            session_key=key, channel_ref="web",
            ops=[{"op": "add_line", "sku": self.product.sku, "qty": 1,
                  "unit_price_q": 1000, "is_d1": True}],
        )
        unit = self._line(session)["unit_price_q"]
        # Best of {D-1 50%, funcionário 20%, happy hour 25%} = 50% → 500. Nunca
        # compõe (o bug empilhava 1000→500→400→300).
        self.assertEqual(unit, 500, f"chain compounded: got {unit}, expected 500 (D-1 wins)")

    def test_flat_discount_wins_when_bigger_than_existing(self) -> None:
        # Happy hour (40%) É maior que uma promo de 10% → substitui (maior ganha).
        from shopman.storefront.models import Promotion

        now = timezone.now()
        Promotion.objects.create(
            name="Promo 10", type=Promotion.PERCENT, value=10, is_active=True,
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        )
        RuleConfig.objects.create(
            ref="happy_hour", rule_path="shopman.shop.rules.pricing.HappyHourRule",
            label="Happy Hour", params=_wide_window_params(40), enabled=True,
        )
        cache.clear()

        key = self._open_session()
        session = ModifyService.modify_session(
            session_key=key, channel_ref="web",
            ops=[{"op": "add_line", "sku": self.product.sku, "qty": 1, "unit_price_q": 1000}],
        )
        unit = self._line(session)["unit_price_q"]
        # max(10% promo, 40% happy hour) = 40% → 600 (não 1000×0.9×0.6 = 540).
        self.assertEqual(unit, 600, f"best-wins replace failed: got {unit}, expected 600")
        # Transparência reconciliada: a promo saiu, o happy hour entrou.
        pricing = session.pricing or {}
        self.assertNotIn(self.product.sku, [d.get("sku") for d in (pricing.get("discount") or {}).get("items", [])])
        self.assertEqual((pricing.get("happy_hour") or {}).get("total_discount_q"), 400)

    # ── HOLE 5: manual order-level discount residue lost on a skipped tail ───
    def test_manual_discount_residue_not_swallowed_by_fee_line(self) -> None:
        # Two R$10 lines + a trailing non-merchandise line. A R$15,00 manual
        # discount must reduce the charged total by exactly 1500.
        p2 = Product.objects.create(
            sku="AUDIT-SKU-2", name="Audit 2", base_price_q=1000,
            is_published=True, is_sellable=True,
        )
        key = self._open_session()
        ModifyService.modify_session(
            session_key=key, channel_ref="web",
            ops=[
                {"op": "add_line", "sku": self.product.sku, "qty": 1, "unit_price_q": 1000},
                {"op": "add_line", "sku": p2.sku, "qty": 1, "unit_price_q": 1000},
            ],
        )
        # Trailing non-merchandise fee line (so the last index is skipped).
        session = Session.objects.get(session_key=key, channel_ref="web")
        items = list(session.items)
        items.append({
            "line_id": "fee-line",
            "sku": "__DELIVERY_FEE__",
            "name": "Taxa",
            "qty": 1,
            "unit_price_q": 500,
            "line_total_q": 500,
            "meta": {"type": "delivery_fee", "non_production": True},
        })
        session.update_items(items)
        session.save()

        charged_before = sum(int(i.get("line_total_q") or 0) for i in session.items)
        # 999 across two equal 1000 lines → 499 + 499, residue 1 destined for the
        # LAST INDEX (the fee line, which is skipped) → never applied.
        session = ModifyService.modify_session(
            session_key=key, channel_ref="web",
            ops=[{"op": "set_data", "path": "manual_discount",
                  "value": {"discount_q": 999, "reason": "audit"}}],
        )
        charged_after = sum(int(i.get("line_total_q") or 0) for i in session.items)
        applied = charged_before - charged_after
        reported = (session.pricing or {}).get("manual_discount", {}).get("total_discount_q", 0)
        # The charged total must drop by exactly what we reported as discounted.
        self.assertEqual(applied, reported,
                         f"charged dropped {applied} but reported {reported} discounted")
        self.assertEqual(applied, 999, f"manual discount under-applied: {applied} of 999")

    # ── HOLE 3: guard exposes the fresh total (structured) so the modal can
    # show old→new instead of a stale number beside the warning. ───────────────
    def test_total_changed_guard_carries_new_total(self) -> None:
        from shopman.orderman.exceptions import ValidationError as OrderingValidationError

        from shopman.shop.services import checkout as checkout_service
        from shopman.storefront.models import Promotion

        key = self._open_session()
        # Line persisted at R$10 with NO promo active → the customer sees R$10.
        ModifyService.modify_session(
            session_key=key, channel_ref="web",
            ops=[{"op": "add_line", "sku": self.product.sku, "qty": 1, "unit_price_q": 1000}],
        )
        # A 50%-off promo appears AFTER review; the confirm reprice picks it up (→R$5).
        now = timezone.now()
        Promotion.objects.create(
            name="Mudou", type=Promotion.PERCENT, value=50, is_active=True,
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        )
        cache.clear()

        # Client sends what it displayed (R$10). Guard must block the surprise AND
        # carry the fresh total (R$5) + the old one, so the UI can show old→new.
        with self.assertRaises(OrderingValidationError) as caught:
            checkout_service.process_ops(
                session_key=key, channel_ref="web",
                ops=[{"op": "set_data", "path": "note", "value": "x"}],
                idempotency_key="audit-h3",
                expected_total_q=1000,
            )
        self.assertEqual(caught.exception.code, "total_changed")
        self.assertEqual(caught.exception.context.get("new_total_q"), 500)
        self.assertEqual(caught.exception.context.get("old_total_q"), 1000)

    # ── HOLE D0: fixed promo must NOT become a per-card menu discount ────────
    def test_menu_backend_ignores_fixed_promo_percent_still_applies(self) -> None:
        from shopman.shop.adapters.pricing import StorefrontPricingBackend
        from shopman.storefront.models import Promotion

        now = timezone.now()
        Promotion.objects.create(
            name="R$5 no pedido", type=Promotion.FIXED, value=500, is_active=True,
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        )
        backend = StorefrontPricingBackend()
        priced = backend.get_price(
            sku="AUDIT-SKU", qty=Decimal("1"), listing="web",
            list_unit_price_q=1000, list_total_price_q=1000, context={},
        )
        # Fixed promo is order-level → NO per-card discount (menu == list price).
        self.assertEqual(priced.final_unit_price_q, 1000)
        self.assertEqual(list(priced.adjustments), [])

        # Control: a percent promo still discounts the card.
        Promotion.objects.create(
            name="20%", type=Promotion.PERCENT, value=20, is_active=True,
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        )
        cache.clear()
        priced2 = backend.get_price(
            sku="AUDIT-SKU", qty=Decimal("1"), listing="web",
            list_unit_price_q=1000, list_total_price_q=1000, context={},
        )
        self.assertEqual(priced2.final_unit_price_q, 800)

    def test_total_changed_maps_to_structured_api_error(self) -> None:
        # Contrato que o modal do checkout consome: total_changed NÃO vira erro de
        # form-field (que descartaria o contexto), e sim erro estruturado com
        # error_code + context (novo/antigo total).
        from shopman.orderman.exceptions import ValidationError as OrderingValidationError

        from shopman.shop.services import checkout as checkout_service

        exc = OrderingValidationError(
            code="total_changed", message="mudou",
            context={"new_total_q": 500, "old_total_q": 1000},
        )
        self.assertIsNone(checkout_service.map_checkout_error(exc))
        dom = checkout_service.map_order_error(exc)
        self.assertEqual(dom.error_code, "total_changed")
        self.assertEqual(dom.context.get("new_total_q"), 500)
        self.assertEqual(dom.http_status, 400)
