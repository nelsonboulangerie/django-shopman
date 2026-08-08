"""Shopman models — Shop, Channel, RuleConfig, NotificationTemplate, OmotenashiCopy, Campaign."""

from .campaign import (
    QUALITY_LEVELS,
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    Trigger,
)
from .catalog_sync import CatalogSyncState, SyncStatus
from .channel import Channel
from .omotenashi_copy import OmotenashiCopy
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
)
from .shop import NotificationTemplate, Shop
from .user_notification import NotificationCategory, UserNotification

__all__ = [
    "Shop",
    "Channel",
    "CatalogSyncState",
    "SyncStatus",
    "NotificationTemplate",
    "RuleConfig",
    "OmotenashiCopy",
    "ShopAppearance",
    "ShopOperation",
    "ShopMenu",
    "ShopOrdering",
    "ShopLoyalty",
    "ShopPos",
    "ShopProduction",
    "ShopIntegrations",
    "Campaign",
    "Announcement",
    "AnnouncementTemplate",
    "AnnouncementStatus",
    "Trigger",
    "QUALITY_LEVELS",
    "UserNotification",
    "NotificationCategory",
]
