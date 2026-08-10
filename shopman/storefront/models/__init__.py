"""Models da superfície de cliente — favoritos e assinatura de alerta por SKU.

`Promotion`, `Coupon`, `DeliveryZone` e `DeliveryDistanceBand` **saíram daqui** para
`shopman.shop` (ADR-019): eram regra de preço e geografia de entrega morando numa
superfície, o que obrigava o orquestrador a alcançá-las por adapter. Os dois que ficam
são dado de cliente de verdade — o que a pessoa favoritou, o que ela pediu para ser
avisada — e por isso seguem sendo lidos pelo shop via `adapters/audience_sources.py`,
que é adapter legítimo.
"""

from .favorites import CustomerFavorite
from .stock_alerts import StockAlertSubscription

__all__ = [
    "StockAlertSubscription",
    "CustomerFavorite",
]
