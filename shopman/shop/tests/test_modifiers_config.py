"""Tests: modifier RuleConfig integration.

Verifies that the rule-driven discount modifiers (time-window) and the
Employee modifier read params from RuleConfig, are gated by the rule's
enabled+channel state, and fall back to generic defaults. The rule lookup
is mocked (``get_channel_rule_params`` / ``get_rule_params``).
"""
from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock, patch

import pytest

# ─── helpers ────────────────────────────────────────────────────────────────


def _make_session(items=None, data=None, pricing=None):
    session = MagicMock()
    session.items = items if items is not None else [
        {"sku": "P001", "unit_price_q": 1000, "qty": 1}
    ]
    session.data = data if data is not None else {}
    session.pricing = pricing if pricing is not None else {}
    session.update_items = lambda x: None
    session.save = MagicMock()
    return session


def _make_channel(rules=None):
    ch = MagicMock()
    ch.config = {"rules": rules or {}}
    return ch


class TestPricingNoopModifiers:
    def test_loyalty_noop_does_not_save_when_pricing_key_absent(self):
        from shopman.shop.modifiers import LoyaltyRedeemModifier

        session = _make_session(data={}, pricing={})

        LoyaltyRedeemModifier().apply(channel=_make_channel(), session=session, ctx={})

        session.save.assert_not_called()
        assert session.pricing == {}

    def test_loyalty_noop_removes_stale_pricing_key(self):
        from shopman.shop.modifiers import LoyaltyRedeemModifier

        session = _make_session(data={}, pricing={"loyalty_redeem": {"total_discount_q": 100}})

        LoyaltyRedeemModifier().apply(channel=_make_channel(), session=session, ctx={})

        session.save.assert_called_once_with(update_fields=["pricing"])
        assert "loyalty_redeem" not in session.pricing

    def test_manual_discount_noop_does_not_save_when_pricing_key_absent(self):
        from shopman.shop.modifiers import ManualDiscountModifier

        session = _make_session(data={}, pricing={})

        ManualDiscountModifier().apply(channel=_make_channel(), session=session, ctx={})

        session.save.assert_not_called()
        assert session.pricing == {}

    def test_manual_discount_noop_removes_stale_pricing_key(self):
        from shopman.shop.modifiers import ManualDiscountModifier

        session = _make_session(data={}, pricing={"manual_discount": {"total_discount_q": 100}})

        ManualDiscountModifier().apply(channel=_make_channel(), session=session, ctx={})

        session.save.assert_called_once_with(update_fields=["pricing"])
        assert "manual_discount" not in session.pricing


class TestOrderDiscountSplitKeepsLinesCoherent:
    """``qty × unit_price_q == line_total_q`` sobrevive ao rateio.

    Os testes vizinhos de rateio só olhavam o TOTAL (resíduo não sumir, débito ==
    desconto), e por isso os três rateios de pedido puderam conviver com um unitário
    que não fecha com o total da própria linha: o unitário levava o piso
    (``share // qty``) e o total levava o valor exato (``line_total - share``).
    A sacola imprimia "3 × R$ 6,34" com total "R$ 19,00" — e é a única conta que o
    cliente confere sozinho.
    """

    @staticmethod
    def _assert_coherent(session) -> None:
        from decimal import Decimal

        from shopman.utils.monetary import monetary_mult

        for item in session.items:
            qty = Decimal(str(item.get("qty", 0)))
            assert int(item["line_total_q"]) == monetary_mult(qty, int(item["unit_price_q"])), (
                f"linha {item.get('sku')} incoerente: "
                f"{item.get('qty')} × {item['unit_price_q']} != {item['line_total_q']}"
            )

    def test_loyalty_redeem_never_leaves_an_incoherent_line(self):
        from shopman.shop.modifiers import LoyaltyRedeemModifier

        # 3 × R$ 6,50 = R$ 19,50; resgate de R$ 0,50 → 50/3 não é inteiro.
        session = _make_session(
            items=[{"sku": "PAO", "qty": 3, "unit_price_q": 650, "line_total_q": 1950, "meta": {}}],
            data={"loyalty": {"redeem_points_q": 50}},
            pricing={},
        )
        session.update_items = lambda new: setattr(session, "items", new)

        LoyaltyRedeemModifier().apply(channel=_make_channel(), session=session, ctx={})

        self._assert_coherent(session)
        applied = int(session.pricing["loyalty_redeem"]["total_discount_q"])
        # Fica ABAIXO do pedido (48 = 16 × 3): resgate nunca debita mais pontos do
        # que o cliente pediu, e o debitado é o desconto que ele de fato recebeu.
        assert applied == 1950 - int(session.items[0]["line_total_q"])
        assert applied == 48
        assert session.data["loyalty"]["applied_discount_q"] == applied

    def test_manual_discount_never_leaves_an_incoherent_line(self):
        from shopman.shop.modifiers import ManualDiscountModifier

        session = _make_session(
            items=[{"sku": "PAO", "qty": 3, "unit_price_q": 650, "line_total_q": 1950, "meta": {}}],
            data={"manual_discount": {"discount_q": 50, "reason": "cortesia"}},
            pricing={},
        )
        session.update_items = lambda new: setattr(session, "items", new)

        ManualDiscountModifier().apply(channel=_make_channel(), session=session, ctx={})

        self._assert_coherent(session)
        applied = int(session.pricing["manual_discount"]["total_discount_q"])
        # O operador autorizou um TETO de R$ 0,50; o rateio não passa dele.
        assert applied == 48
        assert applied == 1950 - int(session.items[0]["line_total_q"])


# ─── TimeWindowDiscountModifier (generic Happy Hour) ─────────────────────────


class TestTimeWindowDiscountModifier:
    """Rule-driven time-window discount.

    Parity: the cents asserted here (20% → 800, 15% → 850) pin the discount math.
    A channel where the rule is not enabled gets no discount
    (``get_channel_rule_params`` returns ``None``).
    """

    @pytest.fixture
    def modifier(self):
        from shopman.shop.modifiers import TimeWindowDiscountModifier
        return TimeWindowDiscountModifier()

    def _at(self, h, m=0):
        mock = MagicMock()
        mock.return_value.time.return_value = time(h, m)
        return mock

    def _gate(self, params):
        return patch(
            "shopman.shop.rules.engine.get_channel_rule_params",
            return_value=params,
        )

    def test_reads_percent_from_ruleconfig(self, modifier):
        session = _make_session()
        channel = _make_channel()
        rc = {"discount_percent": 20, "start": "00:00", "end": "23:59"}
        with self._gate(rc), patch("django.utils.timezone.localtime", self._at(12)):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 800  # 1000 - 20%

    def test_outside_window_no_discount(self, modifier):
        session = _make_session()
        channel = _make_channel()
        # RuleConfig says 14:00-15:00; check at 13:00 → outside window → no discount
        rc = {"discount_percent": 15, "start": "14:00", "end": "15:00"}
        with self._gate(rc), patch("django.utils.timezone.localtime", self._at(13)):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000  # outside window, no discount

    def test_inside_window_applies(self, modifier):
        session = _make_session()
        channel = _make_channel()
        rc = {"discount_percent": 15, "start": "14:00", "end": "15:00"}
        with self._gate(rc), patch("django.utils.timezone.localtime", self._at(14, 30)):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 850  # 1000 - 15%

    def test_falls_back_to_default_percent_when_params_empty(self, modifier):
        session = _make_session()
        channel = _make_channel()
        # Empty params dict = rule enabled, default window 17:30-18:00, 25%.
        with self._gate({}), patch("django.utils.timezone.localtime", self._at(17, 45)):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 750  # 1000 - 25% (module default)

    def test_does_not_compound_on_a_bigger_existing_discount(self, modifier):
        # "Maior desconto ganha": a line already at 50% off (manual → 500) must NOT
        # get happy hour (20%) stacked on top. 20% < 50% → happy hour skips it.
        session = _make_session(items=[{
            "sku": "P001", "unit_price_q": 500, "qty": 1,
            "meta": {"_list_q": 1000, "_disc": {"type": "manual", "amount_q": 500}},
        }])
        channel = _make_channel()
        rc = {"discount_percent": 20, "start": "00:00", "end": "23:59"}
        with self._gate(rc), patch("django.utils.timezone.localtime", self._at(12)):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 500  # kept the bigger discount

    def test_skips_when_rule_not_enabled_for_channel(self, modifier):
        # No enabled rule for this channel → None → no discount.
        session = _make_session()
        channel = _make_channel()
        with self._gate(None), patch("django.utils.timezone.localtime", self._at(12)):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000  # channel-scoped out


# ─── EmployeeDiscountModifier ───────────────────────────────────────────────


class TestEmployeeModifierRuleConfig:
    @pytest.fixture
    def modifier(self):
        from shopman.shop.modifiers import EmployeeDiscountModifier
        return EmployeeDiscountModifier()

    def _staff_session(self):
        return _make_session(data={"customer": {"price_tier": "staff"}})

    def test_reads_percent_from_ruleconfig(self, modifier):
        session = self._staff_session()
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 30}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 700  # 1000 - 30%

    def test_channel_config_overrides_ruleconfig(self, modifier):
        session = self._staff_session()
        channel = _make_channel(rules={"employee_discount_percent": 40})
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 30}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 600  # 1000 - 40%

    def test_falls_back_to_default_when_no_ruleconfig(self, modifier):
        session = self._staff_session()
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 800  # 1000 - 20% (default)

    def test_non_staff_not_affected(self, modifier):
        session = _make_session(data={"customer": {"price_tier": "regular"}})
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 30}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000  # not staff, not touched

    def test_employee_tier_comes_from_ruleconfig_not_a_literal(self, modifier):
        """O parâmetro ``price_tier`` da regra é o DONO da pergunta "qual tier
        marca funcionário" — era um literal "staff" cravado e o parâmetro ficava
        decorativo (achado da faxina 2026-08-13; one question, one owner)."""
        channel = _make_channel()
        params = {"discount_percent": 30, "price_tier": "vip"}

        # O tier configurado ganha o desconto…
        session = _make_session(data={"customer": {"price_tier": "vip"}})
        with patch("shopman.shop.rules.engine.get_rule_params", return_value=params):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 700  # 1000 - 30%

        # …e "staff" deixa de ser mágico quando a regra aponta outro tier.
        session = self._staff_session()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value=params):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000

    def test_modifier_records_discount_in_meta_and_pricing(self, modifier):
        # A transparência durável vive em ``meta["_disc"]`` (modifiers_applied não
        # sobrevive ao normalize) e em ``session.pricing["employee_discount"]``.
        session = self._staff_session()
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 20}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["meta"]["_disc"]["type"] == "employee_discount"
        assert session.pricing["employee_discount"]["total_discount_q"] == 200




