"""Storefront signal receivers.

Alerts do cliente ("Me avise"), dois gatilhos:

- ``stock_back`` — um ``Move`` do Stockman pousa para um SKU com inscrições
  pendentes;
- ``production_ready`` — uma fornada (``production_changed``, action=finished)
  conclui para esse SKU.

Nos dois casos o envio é agendado para *depois* do commit da transação, para
que o estoque novo já esteja visível quando o aviso prometer "pode pedir".
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def on_move_for_stock_alerts(sender, instance, **kwargs) -> None:
    quant_id = getattr(instance, "quant_id", None)
    if not quant_id:
        return
    sku = getattr(getattr(instance, "quant", None), "sku", None)
    if not sku:
        return

    from shopman.storefront.services import stock_alerts

    # Fast path: skip unless someone is actually waiting on this SKU.
    if not stock_alerts.has_pending(sku, alert_type="stock_back"):
        return

    from django.db import transaction

    transaction.on_commit(lambda: stock_alerts.notify_back_in_stock(sku))


def on_production_finished_for_stock_alerts(
    sender, product_ref, date, action, work_order, **kwargs
) -> None:
    """Avisar quem pediu "me avise quando sair do forno" (F9)."""
    if action != "finished" or not product_ref:
        return

    from shopman.storefront.services import stock_alerts

    if not stock_alerts.has_pending(product_ref, alert_type="production_ready"):
        return

    from django.db import transaction

    transaction.on_commit(lambda: stock_alerts.notify_bake_ready(product_ref))


def on_customer_anonymized(sender, customer_ref: str = "", phone: str = "", **kwargs) -> None:
    """Apaga o que a LOJA guarda do titular quando ele pede exclusão.

    O `shop` orquestra a exclusão mas não pode importar `storefront` (a seta de
    dependência só aponta para ele), então o alcance chega por signal. Duas
    tabelas moram aqui e as duas ficavam para trás: os favoritos são um retrato
    de gosto ligado ao `customer_ref`, e o aviso de reposição guarda o TELEFONE
    em `contact_phone` — inclusive de quem se inscreveu sem conta.

    Sem este receptor, "excluir minha conta" deixava o número de volta na fila
    do próximo "voltou ao estoque".
    """
    from shopman.storefront.models import CustomerFavorite, StockAlertSubscription

    if customer_ref:
        CustomerFavorite.objects.filter(customer_ref=customer_ref).delete()
        StockAlertSubscription.objects.filter(customer_ref=customer_ref).delete()
    if phone:
        StockAlertSubscription.objects.filter(contact_phone=phone).delete()
