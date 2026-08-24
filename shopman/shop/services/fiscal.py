"""
Fiscal (NFC-e) service.

ASYNC — creates Directives for later processing.
Smart no-op when fiscal_pool is empty (no backend configured).
"""

from __future__ import annotations

import logging

from shopman.shop import directives
from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE
from shopman.shop.fiscal import fiscal_pool

logger = logging.getLogger(__name__)


def _default_emission_decision(order) -> bool:
    """Fallback quando não há resolver configurado: emite se o operador optou por emitir
    (``order.data['fiscal']['issue_document']``)."""
    return bool(((order.data or {}).get("fiscal") or {}).get("issue_document"))


def emission_resolver(order) -> bool:
    """Decide SE a NFC-e deve ser emitida para este pedido.

    Delega a resolver(es) Python plugáveis (``settings.SHOPMAN_FISCAL_EMISSION_RESOLVER``,
    caminho pontilhado para ``callable(order) -> bool``). Centraliza a regra de negócio
    (acima de X, certos canais, com CPF na nota, forma de pagamento, ambiente…) sem tocar
    no fluxo. AUSENTE (ou com erro) → fallback padrão (opt-in do operador).

    **Vários resolvers**: separe por vírgula → combinados por OR (emite se QUALQUER um
    disser sim), ex.: ``"...on_request_or_tax_id,...card_payment"``. Para AND/NOT ou
    lógica composta, use os combinadores (``any_of``/``all_of``/``not_``) num resolver
    próprio. Exemplos prontos em ``shopman.shop.fiscal_resolvers``.
    """
    from django.conf import settings

    raw = getattr(settings, "SHOPMAN_FISCAL_EMISSION_RESOLVER", "") or ""
    paths = [p.strip() for p in str(raw).split(",") if p.strip()]
    if not paths:
        return _default_emission_decision(order)
    try:
        from django.utils.module_loading import import_string

        resolvers = [import_string(p) for p in paths]
        return any(bool(r(order)) for r in resolvers)  # múltiplos = OR
    except Exception:
        # Resolver quebrado NÃO deve travar o pedido — cai no fallback e registra.
        logger.warning("fiscal.emission_resolver: %s falhou; usando fallback", raw, exc_info=True)
        return _default_emission_decision(order)


def emit(order) -> None:
    """
    Schedule NFC-e emission for the order.

    Smart no-op if no fiscal backend is configured.
    Creates a Directive with topic FISCAL_EMIT_NFCE.

    ASYNC — retry-safe.
    """
    if not fiscal_pool.get_backend():
        return

    data = order.data or {}
    if data.get("nfce_access_key"):
        return

    if not emission_resolver(order):
        return

    payment = dict(data.get("payment", {}) or {})
    payment.setdefault("amount_q", order.total_q)

    if _payment_below_total(payment, order):
        _alert_payment_mismatch(order, payment)
        return

    delivery = None
    if data.get("fulfillment_type") == "delivery":
        delivery = {"address": dict(data.get("delivery_address_structured") or {})}

    directives.queue(
        FISCAL_EMIT_NFCE, order,
        items=_build_fiscal_items(order),
        payment=payment,
        customer=data.get("customer", {}),
        delivery=delivery,
    )

    logger.info("fiscal.emit: queued for order %s", order.ref)


def _declared_payment_q(payment: dict) -> int:
    """Total declarado no pagamento, do jeito que o adapter fiscal soma.

    Espelha ``fiscal_focusnfe._payment_total_q``: numa venda mista, quem manda é
    a soma dos ``tenders`` (o documento diz a verdade sobre o mix); fora dela, o
    ``amount_q``.
    """
    tenders = payment.get("tenders") or []
    if tenders:
        return sum(
            max(0, int(t.get("amount_q") or 0)) for t in tenders if isinstance(t, dict)
        )
    return max(0, int(payment.get("amount_q") or 0))


def _payment_below_total(payment: dict, order) -> bool:
    """O pagamento gravado ficou ABAIXO do total do pedido?

    **Invariante de canal: quem escreve ``order.data['payment']`` escreve o valor
    FINAL.** O adapter deriva ``valor_desconto = produtos + frete − pagamento``,
    então um ``payment`` defasado (edição pós-pagamento que escape do
    ``_reconcile_order_payment_to_total`` do PDV) não vira erro: vira um
    **desconto que não houve** dentro de um XML válido, subdeclarando a venda.

    Só o lado de baixo é guardado aqui. Pagamento ACIMA do total gera
    ``valor_total > valor_produtos`` sem desconto, e a própria SEFAZ recusa —
    falha ruidosa não precisa de guarda nossa.
    """
    return 0 < _declared_payment_q(payment) < int(order.total_q or 0)


def _alert_payment_mismatch(order, payment: dict) -> None:
    from shopman.shop.services.observability import create_operator_alert

    declared_q = _declared_payment_q(payment)
    logger.error(
        "fiscal.emit: pagamento (%s) abaixo do total (%s) em %s — NFC-e não emitida",
        declared_q, order.total_q, order.ref,
    )
    create_operator_alert(
        type="fiscal_payment_mismatch",
        severity="critical",
        message=(
            f"NFC-e do pedido {order.ref} NÃO foi emitida: o pagamento gravado "
            f"(R$ {declared_q / 100:.2f}) está abaixo do total do pedido "
            f"(R$ {int(order.total_q or 0) / 100:.2f}). Emitir assim colocaria no "
            "documento um desconto que não houve. Acerte o pagamento do pedido e "
            "emita de novo."
        ),
        order_ref=order.ref,
        dedupe_key=f"fiscal_payment_mismatch:{order.ref}",
    )


def cancel(order) -> None:
    """
    Schedule NFC-e cancellation for the order.

    Smart no-op if no fiscal backend is configured or NFC-e was never emitted.
    Creates a Directive with topic FISCAL_CANCEL_NFCE.

    ASYNC — retry-safe.
    """
    if not fiscal_pool.get_backend():
        return

    if not (order.data or {}).get("nfce_access_key"):
        return

    if (order.data or {}).get("nfce_cancelled"):
        return

    directives.queue(
        FISCAL_CANCEL_NFCE, order,
        reason=(order.data or {}).get("cancellation_reason", "cancelled"),
    )

    logger.info("fiscal.cancel: queued for order %s", order.ref)


def emission_expected(order) -> bool:
    """Esta venda vai ter NFC-e?

    O balcão precisa oferecer a DANFE, e não pode perguntar isso ao toggle do
    operador: o ``emission_resolver`` também emite por forma de pagamento, e
    nota que ninguém pediu continua sendo nota que o cliente pode exigir
    impressa.

    Nem pode perguntar à Directive: quando a venda fecha, o pedido ainda está em
    ``new``. A emissão só acontece na conclusão, e a nota não existe no instante
    da tela de confirmação. O que existe já no fechamento é a *regra* e os dados
    que ela lê (forma de pagamento, CPF, pedido do operador) — então a pergunta
    honesta é "vai haver nota?", respondida pelo mesmo resolver que decide, sem
    cópia da regra no front.
    """
    return bool(fiscal_pool.get_backend()) and emission_resolver(order)


def _build_fiscal_items(order) -> list[dict]:
    """Build item list for fiscal emission from order items.

    Fiscal codes are resolved by Fiscalman from each product's classification
    (``Product.metadata['fiscal']`` → profile + NCM/CEST → CFOP/CSOSN/origem/
    PIS/COFINS). NFC-e is intrastate, so ``interstate=False``. A per-line
    override in ``item.meta['fiscal']`` still wins (rare).
    """
    from shopman.fiscalman.classification import from_metadata, resolve_fiscal_item

    items = []
    products_by_sku = _products_by_sku([item.sku for item in order.items.all()])
    for item in order.items.all():
        product = products_by_sku.get(item.sku)
        metadata = dict(getattr(product, "metadata", None) or {})
        fiscal = resolve_fiscal_item(from_metadata(metadata))
        override = (item.meta or {}).get("fiscal")
        if override:
            fiscal = {**fiscal, **dict(override)}
        items.append({
            "sku": item.sku,
            "name": item.name,
            "qty": str(item.qty.normalize()) if hasattr(item.qty, "normalize") else float(item.qty),
            "unit": getattr(product, "unit", "") or fiscal.get("unit") or "UN",
            "unit_price_q": item.unit_price_q,
            "total_q": item.line_total_q,
            "meta": dict(item.meta or {}),
            "fiscal": fiscal,
        })
    return items


def _products_by_sku(skus: list[str]) -> dict[str, object]:
    """Produtos por SKU para montar o payload fiscal. A falha de leitura SOBE.

    Engolir a exceção aqui (``except Exception`` → ``{}``) compunha três decisões
    razoáveis num modo de falha péssimo: um soluço de banco fazia TODOS os itens
    perderem o metadado fiscal; o adapter, correto, recusava item sem NCM; e o
    handler classificava essa recusa como **terminal** — nota morta na fila,
    sem retry, com um diagnóstico ("produto sem NCM") que mentia sobre a causa
    ("o SELECT falhou").

    São dois fatos diferentes e cada um vai para o seu lado: **NCM ausente no
    produto** é verdade terminal (o adapter recusa em
    ``fiscal_focusnfe._map_item``, e o pedido precisa de gente); **catálogo
    ilegível** é transiente, e quem re-tenta transiente é quem chamou, não este
    módulo. Como o payload é montado no fechamento do pedido (``fiscal.emit``
    dentro do ``on_commit`` do lifecycle), deixar subir também garante que
    nenhuma directive nasça com um retrato falso do catálogo.
    """
    if not skus:
        return {}
    from shopman.offerman.models import Product

    return {
        product.sku: product
        for product in Product.objects.filter(sku__in=set(skus)).only("sku", "unit", "metadata")
    }
