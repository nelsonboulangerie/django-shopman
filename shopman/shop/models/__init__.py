"""Shopman models — Shop, Channel, RuleConfig, Promotion, Coupon, entrega, Campaign."""

from .campaign import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    Trigger,
)
from .catalog_sync import CatalogSyncState, SyncStatus
from .channel import Channel
from .delivery import DeliveryDistanceBand, DeliveryZone
from .omotenashi_copy import OmotenashiCopy
from .promotion import Coupon, Promotion
from .quality import QualityDefect, QualityGrade
from .rules import RuleConfig
from .settings_proxies import (
    ShopAppearance,
    ShopIntegrations,
    ShopLoyalty,
    ShopMenu,
    ShopOperation,
    ShopOrdering,
    ShopPos,
    ShopProduction,
    ShopPurchase,
)
from .shop import NotificationTemplate, Shop
from .user_notification import NotificationCategory, UserNotification

__all__ = [
    "Shop",
    "Channel",
    "Promotion",
    "Coupon",
    "DeliveryZone",
    "DeliveryDistanceBand",
    "CatalogSyncState",
    "SyncStatus",
    "NotificationTemplate",
    "QualityDefect",
    "QualityGrade",
    "RuleConfig",
    "OmotenashiCopy",
    "ShopAppearance",
    "ShopOperation",
    "ShopMenu",
    "ShopOrdering",
    "ShopLoyalty",
    "ShopPurchase",
    "ShopPos",
    "ShopProduction",
    "ShopIntegrations",
    "Campaign",
    "Announcement",
    "AnnouncementTemplate",
    "AnnouncementStatus",
    "Trigger",
    "UserNotification",
    "NotificationCategory",
]
