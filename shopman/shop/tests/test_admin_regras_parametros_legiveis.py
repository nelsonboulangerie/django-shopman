"""Coluna "parâmetros" das Regras de preço sem dict cru (beta test 05/11/2026, ADM-11)."""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib import admin

from shopman.shop.models import RuleConfig


def test_estrutura_aparece_contada_e_nao_como_dict_do_python():
    rule_admin = admin.site._registry[RuleConfig]
    rule = SimpleNamespace(
        params={
            "pairings": [{"when": ["CAFE"], "then": ["PAO"]}, {"when": ["CHA"], "then": ["BOLO"]}],
            "percent": 10,
            "only_members": True,
        }
    )
    summary = rule_admin.params_summary(rule)
    assert "{'when'" not in summary
    assert summary == "pairings: 2 itens · percent: 10 · only_members: sim"


def test_total_do_pedido_em_reais_e_nao_em_codigo_de_moeda():
    """ADM-11: a lista de pedidos dizia "BRL 156.00"."""
    from shopman.orderman.models import Order

    order_admin = admin.site._registry[Order]
    order = SimpleNamespace(total_q=15600, currency="BRL")
    assert order_admin.total_display(order) == "R$ 156,00"
