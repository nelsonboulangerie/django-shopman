"""Storefront signal receivers.

Alerts do cliente ("Me avise"), dois gatilhos persistentes:

- ``stock_back`` — cada ``Move`` reconcilia o ciclo indisponível→disponível;
- ``production_ready`` — uma fornada (``production_changed``, action=finished)
  conclui para esse SKU, com identidade da ordem de produção.

Nos dois casos o envio é agendado para *depois* do commit da transação, para
que o estoque novo já esteja visível quando o aviso prometer "pode pedir".
"""

from __future__ import annotations

import logging

from django.utils import timezone

from shopman.shop.handlers._resilient import resilient_receiver

logger = logging.getLogger(__name__)


def on_move_for_stock_alerts(sender, instance, **kwargs) -> None:
    """Chegou estoque: avisar quem espera — e, às vezes, quem espera fornada.

    ⚠️ A rede de segurança de quem assinou ``production_ready``: um item de
    fornada também volta a ter estoque por caminhos que não são produção
    (recebimento, devolução, ajuste de inventário). Nesses casos o
    ``production_changed`` nunca vai vir, e sem esta rede a pessoa ficaria
    calada para sempre. Estoque chegando cumpre a promessa "o produto está
    aí", então a fila da fornada é servida junto — com a copy de chegada.

    O ``Move`` de PRODUÇÃO (``kind="make"``) fica de fora da rede de propósito:
    a fornada tem receptor próprio, com a copy própria. Servir os dois no mesmo
    instante daria mensagem dobrada e, pior, a errada — os dois ``on_commit``
    correm em ordem de registro e o do ``Move`` costuma chegar primeiro.
    """
    quant_id = getattr(instance, "quant_id", None)
    if not quant_id:
        return
    # Débitos também passam pelo reconciliador: quando tornam o SKU indisponível,
    # encerram o ciclo aberto para que a próxima volta seja uma nova ocorrência.
    metadata = getattr(instance, "metadata", None) or {}
    if metadata.get("suppress_notifications"):
        return
    if metadata.get("operation") == "production_qc_correction":
        return
    quant = getattr(instance, "quant", None)
    target_date = getattr(quant, "target_date", None)
    if target_date is not None and target_date > timezone.localdate():
        return
    sku = getattr(quant, "sku", None)
    if not sku:
        return

    from shopman.storefront.services import stock_alerts

    if not stock_alerts.needs_stock_reconciliation(sku):
        return

    from django.db import transaction

    source_ref = str(getattr(instance, "pk", "") or getattr(instance, "ref", "") or "")
    transaction.on_commit(lambda: stock_alerts.notify_back_in_stock(sku, source_ref=source_ref))


@resilient_receiver
def on_production_finished_for_stock_alerts(sender, product_ref, date, action, work_order, **kwargs) -> None:
    """Criar a ocorrência da fornada e liberá-la após revisão gerencial do QC.

    Não-crítico: o aviso ao cliente não pode derrubar o ``finish`` da fornada
    (ver :func:`shopman.shop.handlers._resilient.resilient_receiver`).
    """
    if action not in {"finished", "quality_reviewed"} or not product_ref:
        return

    from shopman.storefront.services import stock_alerts

    if action == "finished" and not stock_alerts.has_pending(
        product_ref,
        alert_types=("production_ready",),
    ):
        return

    from django.db import transaction

    source_ref = str(getattr(work_order, "ref", "") or getattr(work_order, "pk", "") or date or "")
    if action == "finished":
        transaction.on_commit(lambda: stock_alerts.record_bake_pending(product_ref, source_ref=source_ref))
    else:
        transaction.on_commit(lambda: stock_alerts.review_bake_ready(product_ref, source_ref=source_ref))


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
