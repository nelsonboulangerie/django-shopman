"""Admin da superfície de cliente — favoritos, assinaturas de alerta, concierge e o piloto de intenções.

Promoção, cupom, zona de entrega e faixa de distância **saíram para `shop/admin/`**
junto com os models (ADR-019).
"""

from shopman.storefront.admin.concierge import ConversationAdmin  # noqa: F401
from shopman.storefront.admin.favorites import CustomerFavoriteAdmin  # noqa: F401
from shopman.storefront.admin.intents import IntentCategoryAdmin, MessageIntentSampleAdmin  # noqa: F401
from shopman.storefront.admin.stock_alerts import (  # noqa: F401
    StockAlertDeliveryAdmin,
    StockAlertOccurrenceAdmin,
    StockAlertSubscriptionAdmin,
)
