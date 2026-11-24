#!/usr/bin/env python
"""Mede o X da retenção do não retirado: custo de produção ÷ preço, por SKU feito aqui.

DEV-2026-089. O dono fixou 40% PROVISÓRIO em 24/11/2026 ("arredondei pra cima, pois
não temos como computar o custo de oportunidade"); este script mede o número real
quando houver custo: para cada SKU vendável com ficha ativa, o custo vivo da ficha
(``adapters/cost.RecipeCostBackend``, ADR-023: insumos da ficha × custo
preferencial do Compras ÷ rendimento) contra o preço de venda, e o peso de cada SKU
nas vendas de ENCOMENDA (``order_helpers.is_preorder``) dos últimos ``--days`` dias.

SÓ LEITURA. Sem custo, o SKU sai "sem custo" e entra na contagem de lacunas, nunca
num chute ("estimado, não medido" não vira medida).

Uso:

    .venv/bin/python scripts/measure_no_show_retention.py            # banco do ambiente
    .venv/bin/python scripts/measure_no_show_retention.py --days 180
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANDIDATES = (30, 35, 40, 45, 50)


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=120, help="janela das vendas de encomenda (padrão 120)")
    args = parser.parse_args(argv)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from django.utils import timezone
    from shopman.craftsman.models import Recipe
    from shopman.offerman.models import Product
    from shopman.orderman.models import Order, OrderItem

    from shopman.shop.adapters.cost import RecipeCostBackend
    from shopman.shop.policies.no_show_policy import TERMS_RETENTION_CAP_PERCENT, resolve_no_show_policy
    from shopman.shop.services.order_helpers import is_preorder

    produced = set(Recipe.objects.filter(is_active=True).values_list("output_sku", flat=True))
    products = {p.sku: p for p in Product.objects.filter(sku__in=produced, is_sellable=True)}

    since = timezone.now() - timedelta(days=args.days)
    weight_q: dict[str, int] = defaultdict(int)
    preorders = [o for o in Order.objects.filter(created_at__gte=since).exclude(status="cancelled") if is_preorder(o)]
    for item in OrderItem.objects.filter(order__in=preorders, sku__in=list(products)):
        weight_q[item.sku] += int(item.line_total_q or 0)

    backend = RecipeCostBackend()
    rows, gaps = [], []
    for sku, product in sorted(products.items()):
        price_q = int(product.base_price_q or 0)
        cost_q = backend.get_cost(sku)
        if cost_q is None or price_q <= 0:
            gaps.append((sku, backend.get_cost_gap(sku) or "sem preço"))
            continue
        rows.append((sku, product.name, price_q, cost_q, cost_q / price_q, weight_q.get(sku, 0)))

    policy = resolve_no_show_policy()
    rule = policy.retention
    print(f"Regra vigente: {rule.percent}% (decidida em {rule.decided_at}, provisória={rule.provisional})" if rule else "Regra vigente: nenhuma")
    print(f"Teto dos Termos: {TERMS_RETENTION_CAP_PERCENT}%")
    print(f"SKUs feitos aqui e vendáveis: {len(products)}; com custo: {len(rows)}; sem custo: {len(gaps)}")
    print(f"Encomendas na janela de {args.days} dias: {len(preorders)}")
    if not rows:
        print("Nenhuma razão custo/preço medida: cadastre os custos preferenciais no Compras.")
        return 1

    ratios = [r[4] for r in rows]
    total_w = sum(r[5] for r in rows)
    weighted = sum(r[4] * r[5] for r in rows) / total_w if total_w else None
    print(f"Média simples: {100 * sum(ratios) / len(ratios):.1f}%")
    print(f"Média ponderada pelas encomendas: {100 * weighted:.1f}%" if weighted is not None else "Média ponderada: sem encomenda com custo")
    for q in (0.5, 0.75, 0.9):
        print(f"p{int(q * 100)}: {100 * _percentile(ratios, q):.1f}%")
    print(f"máx: {100 * max(ratios):.1f}%")
    for x in CANDIDATES:
        print(f"SKUs acima de {x}%: {sum(1 for r in ratios if 100 * r > x)}")
    print("\nSKU | nome | preço | custo | razão | peso nas encomendas")
    for sku, name, price_q, cost_q, ratio, w in sorted(rows, key=lambda r: -r[5])[:20]:
        print(f"{sku} | {name} | {price_q / 100:.2f} | {cost_q / 100:.2f} | {100 * ratio:.1f}% | {w / 100:.2f}")
    if gaps:
        print("\nSem custo (o porquê do custeio):")
        for sku, why in gaps:
            print(f"  {sku}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
