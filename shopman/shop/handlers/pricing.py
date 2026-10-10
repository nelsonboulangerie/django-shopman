"""
Pricing modifiers — precificação de itens e totais.

Inline de shopman.pricing.modifiers.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from shopman.shop.adapters import get_adapter

logger = logging.getLogger(__name__)


class OffermanPricingBackend:
    """Resolve preço pela cascata: grupo do cliente → listing do canal → preço base."""

    def get_price(self, sku: str, channel: Any, customer=None, qty: int = 1) -> int | None:
        catalog = get_adapter("catalog")

        # 1. Preço da faixa do cliente (se identificado e a faixa aponta um listing)
        if customer and getattr(customer, "price_tier", None):
            listing_ref = getattr(customer.price_tier, "listing_ref", None)
            if listing_ref:
                item = self._get_listing_item(catalog, listing_ref, sku, qty=qty)
                if item and item.get("is_sellable"):
                    return item["price_q"]

        # 2. Preço do canal (canal.ref == listing.ref por convenção)
        channel_listing = getattr(channel, "ref", None) if channel else None
        if channel_listing:
            item = self._get_listing_item(catalog, channel_listing, sku, qty=qty)
            if item and item.get("is_sellable"):
                return item["price_q"]

        # 3. Preço base do produto
        try:
            return catalog.get_product_base_price(sku)
        except Exception:
            logger.debug("pricing.get_price degraded; using fallback", exc_info=True)
            return None

    def get_prices(self, skus: list[str], channel: Any, qty: int = 1) -> dict[str, int | None]:
        """``get_price`` sem cliente para vários SKUs, com a vitrine e o preço base lidos uma vez.

        Mesma cascata de ``get_price`` (vitrine do canal → preço base), mesma
        resposta SKU a SKU. Sem as leituras em lote no adapter, cai no
        ``get_price`` de cada um.
        """
        unique = list(dict.fromkeys(skus))
        catalog = get_adapter("catalog")
        bulk_tiers = getattr(catalog, "bulk_listing_tiers", None)
        bulk_base = getattr(catalog, "bulk_product_base_prices", None)
        if bulk_tiers is None or bulk_base is None:
            return {sku: self.get_price(sku, channel, qty=qty) for sku in unique}

        prices: dict[str, int | None] = {}
        channel_listing = getattr(channel, "ref", None) if channel else None
        if channel_listing:
            tiers_by_sku = bulk_tiers(unique, channel_listing)
            for sku in unique:
                item = next((t for t in tiers_by_sku.get(sku) or [] if t["min_qty"] <= qty), None)
                if item and item.get("is_sellable"):
                    prices[sku] = item["price_q"]
        missing = [sku for sku in unique if sku not in prices]
        if missing:
            try:
                base = bulk_base(missing)
            except Exception:
                logger.debug("pricing.get_prices degraded; using fallback", exc_info=True)
                base = {}
            for sku in missing:
                prices[sku] = base.get(sku)
        return prices

    def get_line_prices(self, lines: list[tuple[str, Any]], channel: Any, customer=None) -> list[int | None]:
        """``get_price`` de cada ``(sku, qty)``, com as vitrines e o preço base lidos uma vez.

        A mesma cascata, linha a linha (faixa do cliente → vitrine do canal → preço
        base) e a mesma faixa por quantidade; só a leitura muda. O salvar da
        comanda reprecifica todas as linhas a cada vez, e eram duas idas ao banco
        por linha. Sem as leituras em lote no adapter, cai no ``get_price``.
        """
        catalog = get_adapter("catalog")
        bulk_tiers = getattr(catalog, "bulk_listing_tiers", None)
        bulk_base = getattr(catalog, "bulk_product_base_prices", None)
        if bulk_tiers is None or bulk_base is None:
            kwargs = {"customer": customer} if customer is not None else {}
            return [self.get_price(sku, channel, qty=qty, **kwargs) for sku, qty in lines]

        skus = list(dict.fromkeys(sku for sku, _qty in lines))
        customer_listing = None
        if customer and getattr(customer, "price_tier", None):
            customer_listing = getattr(customer.price_tier, "listing_ref", None) or None
        channel_listing = (getattr(channel, "ref", None) if channel else None) or None
        customer_tiers = bulk_tiers(skus, customer_listing) if customer_listing else {}
        channel_tiers = bulk_tiers(skus, channel_listing) if channel_listing else {}
        base: dict[str, int] | None = None

        prices: list[int | None] = []
        for sku, qty in lines:
            price = None
            for tiers in (customer_tiers, channel_tiers):
                item = next((t for t in tiers.get(sku) or [] if t["min_qty"] <= qty), None)
                if item and item.get("is_sellable"):
                    price = item["price_q"]
                    break
            if price is None:
                if base is None:
                    try:
                        base = bulk_base(skus)
                    except Exception:
                        logger.debug("pricing.get_line_prices degraded; using fallback", exc_info=True)
                        base = {}
                price = base.get(sku)
            prices.append(price)
        return prices

    def _get_listing_item(self, catalog, listing_ref, sku, qty=1):
        """Find the tier with highest min_qty <= qty."""
        tiers = catalog.find_listing_tiers(sku, listing_ref)
        return next((t for t in tiers if t["min_qty"] <= qty), None)


class ItemPricingModifier:
    """
    Modifier que aplica preços e calcula totais de linha. Ordem: 10.

    Para internal pricing: sempre re-resolve o preço do backend a cada run,
    garantindo que discount modifiers partam do preço base correto. O estado de
    desconto por-linha (``meta["_disc"]``) é zerado abaixo para os descontos
    recalcularem do zero (o vestígio ``modifiers_applied``, que não persistia, foi
    removido — ver DISCOUNT-AUDIT-2026-08).
    """

    code = "pricing.item"
    order = 10

    def __init__(self, backend):
        self.backend = backend

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        items = session.items
        trace = []
        modified = False

        customer = ctx.get("customer")
        option_products = (
            _products_with_line_options(items) if session.pricing_policy == "internal" else {}
        )
        # As faixas e o preço base de todas as linhas numa leitura (a cascata é a
        # mesma do ``get_price``; ver ``get_line_prices``).
        line_prices = None
        if session.pricing_policy == "internal" and hasattr(self.backend, "get_line_prices"):
            line_prices = self.backend.get_line_prices(
                [(item["sku"], max(Decimal("1"), Decimal(str(item.get("qty", 1) or 1)))) for item in items],
                channel,
                customer=customer,
            )
        for index, item in enumerate(items):
            sku = item["sku"]

            # ⚠️ Havia aqui um ramo que CONGELAVA a linha: com
            # ``meta.price_overridden``, o preço digitado à mão pelo operador era
            # honrado verbatim e o backend não reprecificava. O mecanismo saiu
            # inteiro — preço à mão não passava pela régua do desconto (limite da
            # loja, motivo, "maior desconto ganha") e tinha portão próprio. Sem
            # ele, TODA linha volta a ser precificada pelo backend, que é o único
            # lugar onde preço é política.
            if session.pricing_policy == "internal":
                # Always re-resolve price from backend
                # A faixa de preço por quantidade (``min_qty``) compara contra a
                # quantidade REAL. ``int()`` zerava a linha pesada (0,312 kg → 0)
                # e nenhuma faixa casava: o listing do canal era pulado e o
                # queijo saía pelo preço base. Menos de uma unidade é a 1ª faixa.
                qty_val = max(Decimal("1"), Decimal(str(item.get("qty", 1) or 1)))
                if line_prices is not None:
                    price = line_prices[index]
                else:
                    kwargs = {"qty": qty_val}
                    if customer is not None:
                        kwargs["customer"] = customer
                    price = self.backend.get_price(sku, channel, **kwargs)
                if price is not None and sku in option_products:
                    # Escolhas no produto: o preço da linha é o do produto MAIS as
                    # opções, relidas pelo ``ref`` no catálogo de agora (o cliente
                    # nunca manda preço). O ``_list_q`` abaixo herda o total, então
                    # descontos de linha incidem sobre produto + opções.
                    from shopman.shop import product_options

                    price += product_options.options_unit_price_q(
                        option_products[sku], product_options.line_options(item),
                    )
                if price is not None:
                    if item.get("unit_price_q") != price:
                        item["unit_price_q"] = price
                        modified = True
                        trace.append({
                            "line_id": item["line_id"],
                            "sku": sku,
                            "price_q": price,
                            "source": "internal",
                        })
            else:
                # External: restore base price if it was modified by discounts
                base = item.get("_base_price_q")
                if base is not None:
                    if item.get("unit_price_q") != base:
                        item["unit_price_q"] = base
                        modified = True
                else:
                    # First run — save current price as base
                    item["_base_price_q"] = item.get("unit_price_q", 0)

            # Árbitro "maior desconto ganha": carimba o preço de LISTA (pré-desconto)
            # e zera o vencedor da rodada. Os descontos por-linha (promo,
            # funcionário, happy hour) calculam sobre ``_list_q`` e só vencem se
            # baterem o ``_disc`` atual — nunca compõem sobre um preço já reduzido.
            # ``meta`` sobrevive ao ``_normalize_items``; ``modifiers_applied`` NÃO.
            meta = item.get("meta")
            if not isinstance(meta, dict):
                meta = {}
                item["meta"] = meta
            meta["_list_q"] = int(item.get("unit_price_q", 0) or 0)
            meta.pop("_disc", None)
            modified = True

            from shopman.utils.monetary import monetary_mult

            qty = Decimal(str(item.get("qty", 0)))
            unit_price = item.get("unit_price_q", 0)
            calculated_total = monetary_mult(qty, unit_price)

            if item.get("line_total_q") != calculated_total:
                item["line_total_q"] = calculated_total
                modified = True

        if modified:
            session.update_items(items)

        if trace:
            if not session.pricing_trace:
                session.pricing_trace = []
            session.pricing_trace.extend(trace)


def _products_with_line_options(items) -> dict:
    """Produtos das linhas que têm escolha desta casa (``meta["options"]`` com ``ref``)."""
    from shopman.shop import product_options

    skus = {
        item.get("sku")
        for item in items
        if product_options.own_options(product_options.line_options(item))
    }
    skus.discard(None)
    if not skus:
        return {}
    from shopman.offerman.models import Product

    return {product.sku: product for product in Product.objects.filter(sku__in=skus)}


class SessionTotalModifier:
    """Recalcula o total da sessão. Ordem 90 — DEPOIS de todos os descontos
    (funcionário 60, happy hour 65, taxa 70, loyalty 80, manual 85), senão
    ``pricing["total_q"]`` fica defasado (S2 da DISCOUNT-AUDIT). O total cobrado
    canônico segue sendo ``sum(line_total_q)``/``order.total_q``; esta chave é
    conveniência de leitura e agora reflete o valor final."""

    code = "pricing.session_total"
    order = 90

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        total = sum(item.get("line_total_q", 0) for item in session.items)

        if not session.pricing:
            session.pricing = {}

        session.pricing["total_q"] = total
        session.pricing["items_count"] = len(session.items)


__all__ = ["ItemPricingModifier", "SessionTotalModifier"]
