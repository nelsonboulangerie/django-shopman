"""Shopman models — Shop, Channel, RuleConfig, Promotion, Coupon, entrega, Campaign."""

from .affinity import ProductAffinity
from .attributes import (
    AttributeDefinition,
    AttributePurpose,
    AttributeSource,
    AttributeType,
)
from .campaign import (
    Announcement,
    AnnouncementDeliveryState,
    AnnouncementStatus,
    AnnouncementTemplate,
    AudienceSnapshot,
    AudienceSnapshotMember,
    Campaign,
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
    MarketingAISuggestion,
    MarketingAISuggestionEvent,
    MarketingAuditEvent,
    MarketingCommandReceipt,
    MarketingConfirmation,
    MarketingContentArtifact,
    MarketingOutbox,
    MarketingPlatformAuditEvent,
    MarketingQuotaUsage,
    MarketingSafetyState,
    MarketingSecurityEvent,
    MarketingTestReceipt,
    Trigger,
)
from .catalog_binding import CatalogBinding, CatalogSnapshot
from .catalog_sync import CatalogSyncState, SyncStatus
from .channel import Channel
from .concierge import (
    Conversation,
    ConversationBinding,
    ConversationMessage,
    OutboundAttempt,
)
from .contact_release import ContactRelease, ReleasedContactKind
from .delivery import DeliveryDistanceBand, DeliveryZone
from .faq import FAQEntry
from .omotenashi_copy import OmotenashiCopy
from .privacy import (
    PrivacyRequestOperation,
    PrivacyRequestReceipt,
    PrivacyRequestState,
)
from .promotion import Coupon, Promotion
from .push_subscription import (
    PUSH_CATEGORIES,
    PUSH_SURFACE_CATEGORIES,
    PushSubscription,
    PushSurface,
)
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
    ShopSearch,
)
from .shop import NotificationTemplate, Shop
from .user_notification import (
    NotificationCategory,
    NotificationEventType,
    NotificationLifecycle,
    NotificationSeverity,
    UserNotification,
    UserNotificationEvent,
)

__all__ = [
    "Shop",
    "AttributeDefinition",
    "AttributePurpose",
    "AttributeSource",
    "AttributeType",
    "ProductAffinity",
    "Conversation",
    "ConversationBinding",
    "ConversationMessage",
    "OutboundAttempt",
    "ContactRelease",
    "ReleasedContactKind",
    "Channel",
    "Promotion",
    "Coupon",
    "PrivacyRequestOperation",
    "PrivacyRequestReceipt",
    "PrivacyRequestState",
    "DeliveryZone",
    "DeliveryDistanceBand",
    "FAQEntry",
    "CatalogBinding",
    "CatalogSnapshot",
    "CatalogSyncState",
    "SyncStatus",
    "NotificationTemplate",
    "QualityDefect",
    "QualityGrade",
    "RuleConfig",
    "OmotenashiCopy",
    "ShopAppearance",
    "ShopSearch",
    "ShopOperation",
    "ShopMenu",
    "ShopOrdering",
    "ShopLoyalty",
    "ShopPurchase",
    "ShopPos",
    "ShopProduction",
    "ShopIntegrations",
    "Campaign",
    "DeliveryTarget",
    "DeliveryAttempt",
    "DeliveryReconciliation",
    "Announcement",
    "AnnouncementDeliveryState",
    "AnnouncementTemplate",
    "AnnouncementStatus",
    "AudienceSnapshot",
    "AudienceSnapshotMember",
    "MarketingAuditEvent",
    "MarketingAISuggestion",
    "MarketingAISuggestionEvent",
    "MarketingCommandReceipt",
    "MarketingConfirmation",
    "MarketingContentArtifact",
    "MarketingOutbox",
    "MarketingPlatformAuditEvent",
    "MarketingQuotaUsage",
    "MarketingSafetyState",
    "MarketingSecurityEvent",
    "MarketingTestReceipt",
    "Trigger",
    "UserNotification",
    "UserNotificationEvent",
    "NotificationCategory",
    "NotificationEventType",
    "NotificationLifecycle",
    "NotificationSeverity",
    "PUSH_CATEGORIES",
    "PUSH_SURFACE_CATEGORIES",
    "PushSubscription",
    "PushSurface",
]
