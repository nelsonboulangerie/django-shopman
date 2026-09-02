"""Per-line manual discount (POS numpad "Desc"): pricing, intent and gate.

Operator policy (decided 2026-05-30):
- promo vs manual on the same line → "maior desconto ganha" (best wins).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.backstage.projections import pos as pos_projection
from shopman.shop.modifiers import DiscountModifier
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import (
    PosIntentError,
    parse_pos_sale_intent,
)


class TestCalcManual:
    def test_percent_of_unit_price(self) -> None:
        # 10% of R$ 13,00 (1300) = 130
        assert DiscountModifier._calc_manual({"value": 10}, 1300) == 130

    def test_clamped_to_unit_price(self) -> None:
        assert DiscountModifier._calc_manual({"value": 200}, 1300) == 1300

    def test_zero_or_invalid_is_no_discount(self) -> None:
        assert DiscountModifier._calc_manual({"value": 0}, 1300) == 0
        assert DiscountModifier._calc_manual({"value": "abc"}, 1300) == 0
        assert DiscountModifier._calc_manual({}, 1300) == 0


class TestIntentPreservesLineDiscount:
    def test_discount_survives_parsing(self) -> None:
        intent = parse_pos_sale_intent(
            {
                "items": [
                    {"sku": "BAGUETE", "qty": 2, "unit_price_q": 1300,
                     "discount": {"value": 15, "reason": "fidelidade"}},
                ],
            },
            for_commit=True,
        )
        item = intent.payload["items"][0]
        assert item["discount"] == {"type": "percent", "value": 15.0, "reason": "fidelidade"}

    def test_percent_clamped_to_100(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [{"sku": "X", "qty": 1, "unit_price_q": 1000, "discount": {"value": 250}}]},
            for_commit=True,
        )
        assert intent.payload["items"][0]["discount"]["value"] == 100.0

    def test_no_discount_when_absent_or_zero(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [{"sku": "X", "qty": 1, "unit_price_q": 1000, "discount": {"value": 0}}]},
            for_commit=True,
        )
        assert "discount" not in intent.payload["items"][0]


class TestPayloadDiscountHelpers:
    def test_line_discounts_sum_per_unit_times_qty(self) -> None:
        payload = {"items": [
            {"sku": "A", "qty": 2, "unit_price_q": 1300, "discount": {"value": 10}},  # 130 * 2
            {"sku": "B", "qty": 1, "unit_price_q": 800},                               # no discount
        ]}
        assert pos_service._payload_line_discounts_q(payload) == 260

@pytest.mark.django_db
class TestBuildSessionOpsStampsDiscount:
    def test_stamps_manual_discount_meta_with_approved_by(self) -> None:
        payload = {
            "items": [{"sku": "BAGUETE", "name": "Baguete", "qty": 1, "unit_price_q": 1300,
                       "discount": {"type": "percent", "value": 10, "reason": "cortesia"}}],
        }
        ops = pos_service.build_session_ops(payload, operator_username="op", approved_by="gerente")
        add_line = next(op for op in ops if op["op"] == "add_line" and op["sku"] == "BAGUETE")
        assert add_line["meta"]["manual_discount"]["value"] == 10
        assert add_line["meta"]["manual_discount"]["reason"] == "cortesia"
        assert add_line["meta"]["manual_discount"]["approved_by"] == "gerente"

    def test_o_corpo_sozinho_nao_assina_nada(self) -> None:
        """⚠️ Era assim que a Joyce aprovava um desconto que nunca viu.

        O validador retorna cedo quando nada exige desafio, mas a construção lia
        ``manager_approval.username`` do corpo INCONDICIONALMENTE. Um payload montado à
        mão — ou uma tela com o campo do gerente preenchido e o PIN limpo — gravava a
        assinatura dela no pedido. Como o nome do corpo coincide com o verificado
        quando HÁ desafio, o defeito era invisível nos testes.
        """
        payload = {
            "items": [{"sku": "BAGUETE", "name": "Baguete", "qty": 1, "unit_price_q": 1300,
                       "discount": {"type": "percent", "value": 10, "reason": "cortesia"}}],
            "manager_approval": {"username": "joyce", "pin": ""},
        }
        ops = pos_service.build_session_ops(payload, operator_username="op")
        add_line = next(op for op in ops if op["op"] == "add_line" and op["sku"] == "BAGUETE")
        assert "approved_by" not in add_line["meta"]["manual_discount"]

    def test_no_meta_discount_without_line_discount(self) -> None:
        payload = {"items": [{"sku": "BAGUETE", "name": "Baguete", "qty": 1, "unit_price_q": 1300}]}
        ops = pos_service.build_session_ops(payload, operator_username="op")
        add_line = next(op for op in ops if op["op"] == "add_line" and op["sku"] == "BAGUETE")
        assert "manual_discount" not in (add_line.get("meta") or {})


@pytest.mark.django_db
class TestManagerApprovalGate:
    def test_plain_line_discount_below_threshold_passes(self) -> None:
        # Default threshold is 0 (no approval); a plain line discount does not gate.
        payload = {
            "items": [{"sku": "BAGUETE", "qty": 1, "unit_price_q": 1300, "discount": {"value": 10}}],
        }
        # Must not raise.
        pos_service.validate_manager_approval(payload, operator_username="op")


@pytest.mark.django_db
class TestTabPayloadRestore:
    def test_line_discount_surfaced_for_restore(self) -> None:
        item = {"sku": "X", "meta": {"manual_discount": {"value": 10, "reason": "cortesia"}}}
        assert pos_projection._tab_payload_line_discount(item) == {
            "value": 10,
            "reason": "cortesia",
            "type": "percent",
        }

    def test_restore_devolve_o_formato_em_reais(self) -> None:
        # Sem o `type` de volta, uma comanda salva com R$ 2,00 de cortesia voltava
        # do banco como 2% — o campo estava gravado, e era a projection que o
        # deixava para trás.
        item = {
            "sku": "X",
            "meta": {"manual_discount": {"value": 2.0, "reason": "qualidade", "type": "fixed"}},
        }
        assert pos_projection._tab_payload_line_discount(item) == {
            "value": 2.0,
            "reason": "qualidade",
            "type": "fixed",
        }

    def test_no_discount_returns_none(self) -> None:
        assert pos_projection._tab_payload_line_discount({"sku": "X", "meta": {}}) is None

    def test_display_price_uses_pre_discount_when_manual_applied(self) -> None:
        # After the modifier ran, unit_price_q is discounted; the reload restores the
        # base price from session.pricing (NOT from the item's modifiers_applied,
        # which is stripped on save) so the descriptor is not double-applied (B1-3).
        item = {
            "sku": "X",
            "unit_price_q": 1170,  # 1300 - 10%
            "meta": {"manual_discount": {"value": 10, "reason": "cortesia"}},
        }
        originals = {"X": 1300}
        assert pos_projection._tab_line_display_price_q(item, originals) == 1300

    def test_display_price_falls_back_when_no_pricing_record(self) -> None:
        # No surviving pricing record → fall back to the stored (baked) unit price
        # rather than guessing; the descriptor path only triggers with an original.
        item = {"sku": "X", "unit_price_q": 1170, "meta": {"manual_discount": {"value": 10}}}
        assert pos_projection._tab_line_display_price_q(item, {}) == 1170

    def test_display_price_falls_back_to_unit_price(self) -> None:
        item = {"sku": "X", "unit_price_q": 1300, "meta": {}}
        assert pos_projection._tab_line_display_price_q(item, {}) == 1300

    def test_manual_originals_map_from_session_pricing(self) -> None:
        # The surviving source: session.pricing["discount"]["items"]. Only manual
        # records with an original price map; promotion/coupon records are ignored
        # (their baked price is repriced on commit, not restored here).
        from types import SimpleNamespace

        session = SimpleNamespace(pricing={"discount": {"items": [
            {"sku": "X", "type": "manual", "original_price_q": 1300, "discount_q": 1170, "qty": 1},
            {"sku": "Y", "type": "promotion", "original_price_q": 900, "discount_q": 90, "qty": 1},
            {"sku": "", "type": "coupon", "original_price_q": 0, "discount_q": 500, "qty": 1},
        ]}})
        assert pos_projection._manual_discount_originals(session) == {"X": 1300}

    def test_manual_originals_map_empty_without_pricing(self) -> None:
        from types import SimpleNamespace

        assert pos_projection._manual_discount_originals(SimpleNamespace(pricing=None)) == {}
