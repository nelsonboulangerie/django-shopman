"""Admin da superfície de cliente — favoritos e assinaturas de alerta.

Promoção, cupom, zona de entrega e faixa de distância **saíram para `shop/admin/`**
junto com os models (ADR-019).
"""

from shopman.storefront.admin.concierge import ConversationAdmin  # noqa: F401
from shopman.storefront.admin.favorites import CustomerFavoriteAdmin  # noqa: F401
from shopman.storefront.admin.stock_alerts import StockAlertSubscriptionAdmin  # noqa: F401
