"""Cart product context — read-side facade for the cart mutation path.

Resolves a product's listed price for an add-to-cart intent. A clean read
facade (policy/data, no presentation), so it lives in the orchestrator
read-side (``shop/projections/``); the storefront cart intent consumes it
without ever reaching into the Core directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CartProductContext:
    product: object
    unit_price_q: int


def product_context(
    sku: str,
    *,
    channel_ref: str = "web",
    for_add: bool = True,
    qty: int = 1,
) -> CartProductContext | None:
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku, is_published=True).first()
    if not product:
        return None
    if not for_add:
        return CartProductContext(product=product, unit_price_q=0)

    return CartProductContext(
        product=product,
        unit_price_q=_price_q(product, channel_ref=channel_ref, qty=qty) or 0,
    )


def _price_q(product, *, channel_ref: str, qty: int = 1) -> int | None:
    # Offerman é a autoridade de preço: `unit_price` faz o cascade correto por tier
    # (min_qty__lte=qty), respeita is_sellable e a janela de validade do listing, e
    # cai para base_price_q. Reimplementar aqui (ex.: order_by("-min_qty").first() sem
    # filtro de qty) cobrava o tier de atacado ao adicionar 1 unidade.
    from shopman.offerman.service import CatalogError, CatalogService

    try:
        return CatalogService.unit_price(
            product.sku, qty=Decimal(str(qty or 1)), listing=channel_ref
        )
    except CatalogError:
        return product.base_price_q
