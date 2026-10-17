"""
Pricing modifiers — precificação de itens e totais.

Inline de shopman.pricing.modifiers.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


class OffermanPricingBackend:
    """Resolve preço pela cascata: grupo do cliente → listing do canal → preço base."""

    def get_price(self, sku: str, channel: Any, customer=None, qty: int = 1) -> int | None:
        return self.get_line_prices([(sku, qty)], channel, customer=customer)[0]

    def get_prices(self, skus: list[str], channel: Any, qty: int = 1) -> dict[str, int | None]:
        """Resolva vários SKUs sem cliente pela operação em lote do Offerman.

        A ordem da primeira ocorrência de cada SKU é preservada. A seleção da
        faixa por quantidade e o fallback para preço base pertencem ao kernel.
        """
        unique = list(dict.fromkeys(skus))
        resolved = self.get_line_prices([(sku, qty) for sku in unique], channel)
        return dict(zip(unique, resolved, strict=True))

    def get_line_prices(self, lines: list[tuple[str, Any]], channel: Any, customer=None) -> list[int | None]:
        """Resolva ``(sku, qty)`` em lote pela cascata declarada pelo orquestrador.

        O orquestrador fornece a precedência das vitrines; o Offerman decide a
        faixa por quantidade e o preço base, preservando a ordem das linhas.
        """
        from shopman.offerman.service import CatalogService

        customer_listing = getattr(customer, "listing_ref", None) if customer else None
        channel_listing = getattr(channel, "ref", None) if channel else None
        listings = tuple(ref for ref in (customer_listing, channel_listing) if ref)
        return CatalogService.unit_prices(lines, listings=listings)


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
                [(item["sku"], Decimal(str(item.get("qty", 1)))) for item in items],
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
                # A quantidade segue intacta até o Offerman. A interpretação de
                # ``min_qty`` pertence ao kernel; o orquestrador não arredonda,
                # trunca nem escolhe uma faixa em nome dele.
                qty_val = Decimal(str(item.get("qty", 1)))
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
            # grupo, happy hour) calculam sobre ``_list_q`` e só vencem se
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
    (happy hour 65, taxa 70, loyalty 80, manual 85), senão
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
