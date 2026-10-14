"""P2-22: o teto do desconto manual do PDV é a mercadoria, nunca a taxa de entrega.

O kernel (``ManualDiscountModifier``) rateia o desconto de pedido só sobre
mercadoria. A conta do PDV (review e o gatilho do PIN de gerente) media o
percentual sobre o subtotal COM a linha de taxa, e o mesmo subtotal servia de
limite do valor fixo: o desconto pedido crescia pela taxa e o gerente era
chamado por um valor que a venda não dá.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from shopman.shop.services import pos

_FEE_LINE = {
    "sku": "__DELIVERY_FEE__",
    "qty": 1,
    "unit_price_q": 1000,
    "meta": {"type": "delivery_fee", "non_production": True},
}


def _payload(discount: dict) -> dict:
    return {
        "items": [{"sku": "PAO", "qty": 1, "unit_price_q": 10000}, dict(_FEE_LINE)],
        "manual_discount": discount,
    }


def test_percentual_mede_so_a_mercadoria():
    manual = pos._payload_manual_discount(_payload({"type": "percent", "value": 10}))

    assert manual["discount_q"] == 1000  # 10% de R$ 100,00, sem a taxa de R$ 10,00


def test_valor_fixo_tem_teto_na_mercadoria():
    manual = pos._payload_manual_discount(_payload({"type": "fixed", "value": "105,00"}))

    assert manual["discount_q"] == 10000  # nunca come a taxa de entrega


def test_gatilho_do_gerente_nao_soma_a_taxa():
    # Teto da loja em R$ 10,00: 10% de R$ 100,00 de mercadoria fica no teto.
    with patch.object(pos, "discount_approval_threshold_q", return_value=1000):
        approver = pos.validate_manager_approval(
            _payload({"type": "percent", "value": 10}), operator_username="caixa",
        )

    assert approver is None


def test_portao_do_desconto_de_linha_ignora_a_linha_de_taxa():
    """O portão do ``DiscountModifier`` que pergunta se há desconto manual de linha
    não conta a linha de taxa: sem promoção e sem desconto em mercadoria, o pricing
    velho sai em vez de virar um desconto vazio."""
    from shopman.shop.modifiers import DiscountModifier

    session = MagicMock()
    session.items = [
        {"sku": "PAO", "qty": 1, "unit_price_q": 1000, "line_total_q": 1000},
        {**_FEE_LINE, "line_total_q": 1000, "meta": {**_FEE_LINE["meta"], "manual_discount": {"value": 10}}},
    ]
    session.data = {}
    session.pricing = {"discount": {"total_discount_q": 0, "items": []}}
    channel = MagicMock(ref="pdv")

    with (
        patch("shopman.shop.services.promotions.get_active_promotions", return_value=[]),
        patch.object(DiscountModifier, "_resolve_customer_ctx"),
    ):
        DiscountModifier().apply(channel=channel, session=session, ctx={})

    assert "discount" not in session.pricing
