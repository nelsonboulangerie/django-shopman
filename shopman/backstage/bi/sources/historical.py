"""O histórico externo aterrissado (``HistoricalSale``) como venda canônica.

A origem vem do campo ``source`` de cada linha, nunca de um literal: dado de
demonstração carimbado como ``seed`` não pode aparecer na tela com o nome de um
export real que ninguém carregou.

O que o histórico NÃO sabe fica declarado, não inventado: cobrança pendente
não existe (o export só traz venda concluída); forma de pagamento é texto cru
que o vocabulário confirmado (``PaymentMethodAlias``) traduz — o que ele não
reconhece sai ``raw:<texto>`` e ``payment_known=False``. Canal: só
``is_delivery`` é rótulo confiável (mesa/balcão do sistema antigo nunca viram
verdade); o resto é ``"<fonte> · loja"``.

Nas linhas, o de-para de produto confirmado (``ProductAlias``) resolve o SKU
da fonte para o SKU do catálogo — é isso que junta dois anos de Yooga com o
presente no mesmo ranking. Sem de-para, a linha segue pelo SKU da fonte, ou
pelo nome quando nem isso há.
"""

from __future__ import annotations

import re
from datetime import date

from django.utils import timezone

from shopman.backstage.bi.canonical import CanonicalPayment, CanonicalSale, CanonicalSaleLine

#: O texto cru pode listar mais de uma forma ("DINHEIRO, CARTÃO"); qualquer
#: parcela em espécie faz da venda uma venda com dinheiro (pode ter pedido troco).
_PAYMENT_SPLIT = re.compile(r"[,;+/]|\s+e\s+")


def _channel(source: str, is_delivery: bool) -> str:
    return f"{source} · {'delivery' if is_delivery else 'loja'}"


def read_sales(window) -> list[CanonicalSale]:
    from shopman.backstage.models import HistoricalSale
    from shopman.backstage.projections.bi_payments import (
        UNKNOWN_PREFIX,
        normalize_historical_payment,
        payment_vocabulary,
    )

    vocabulary = payment_vocabulary()  # uma consulta, milhares de vendas
    sales: list[CanonicalSale] = []
    rows = HistoricalSale.objects.filter(occurred_at__range=window).values_list(
        "id", "source", "external_id", "occurred_at", "total_q", "is_delivery", "payment"
    )
    for pk, source, external_id, occurred_at, total_q, is_delivery, raw in rows:
        local = timezone.localtime(occurred_at)
        method, label = normalize_historical_payment(raw, vocabulary)
        known = bool((raw or "").strip()) and not method.startswith(UNKNOWN_PREFIX)
        is_cash = any(
            normalize_historical_payment(part, vocabulary)[0] == "cash"
            for part in _PAYMENT_SPLIT.split(raw or "")
            if part.strip()
        )
        sales.append(
            CanonicalSale(
                source=source,
                key=pk,
                ref=f"{source}:{external_id}",
                occurred_at=local,
                day=local.date(),
                channel_key=_channel(source, is_delivery),
                is_delivery=is_delivery,
                total_q=total_q,
                payments=(CanonicalPayment(method=method, label=label, amount_q=total_q, pending=False),),
                payment_known=known,
                is_cash=is_cash,
                change_q=None,  # o export não tem troco: ausência declarada
            )
        )
    return sales


def read_lines(window, *, skip_days: frozenset[date] = frozenset()) -> list[CanonicalSaleLine]:
    """As linhas do histórico na janela, fora dos dias em que o nativo venceu."""
    from shopman.backstage.models import HistoricalSaleItem

    by_sku, by_name = _confirmed_product_aliases()
    rows = HistoricalSaleItem.objects.filter(sale__occurred_at__range=window).values_list(
        "sale_id", "sale__source", "sale__occurred_at", "sku", "product_name", "category", "qty", "line_total_q"
    )
    lines: list[CanonicalSaleLine] = []
    for sale_id, source, occurred_at, sku, name, category, qty, line_total_q in rows:
        if skip_days and timezone.localtime(occurred_at).date() in skip_days:
            continue
        sku = sku or ""
        name = name or ""
        product_ref = by_sku.get((source, sku), "") if sku else by_name.get((source, name), "")
        lines.append(
            CanonicalSaleLine(
                source=source,
                sale_key=sale_id,
                product_ref=product_ref,
                external_sku=sku,
                name=name,
                category=category or "",
                qty=qty,
                line_total_q=line_total_q,
            )
        )
    return lines


def _confirmed_product_aliases() -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    """({(fonte, sku externo): sku do catálogo}, {(fonte, nome externo): sku do catálogo}).

    Só confirmados e só com produto: alias de produto extinto (FK vazia) não
    traduz nada — a linha segue com o SKU/nome da fonte, que é o que ela é.
    """
    from shopman.backstage.models import ProductAlias

    by_sku: dict[tuple[str, str], str] = {}
    by_name: dict[tuple[str, str], str] = {}
    rows = (
        ProductAlias.objects.confirmed()
        .exclude(product__isnull=True)
        .values_list("source", "external_sku", "external_name", "product__sku")
    )
    for source, external_sku, external_name, product_sku in rows:
        if external_sku:
            by_sku[(source, external_sku)] = product_sku
        else:
            by_name[(source, external_name)] = product_sku
    return by_sku, by_name
