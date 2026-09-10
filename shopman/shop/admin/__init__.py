"""Shopman admin — Unfold admin de shop, rules, orders, channel, promoção e entrega."""

from shopman.shop.admin.attributes import AttributeDefinitionAdmin  # noqa: F401
from shopman.shop.admin.campaign import (  # noqa: F401
    AnnouncementAdmin,
    AnnouncementTemplateAdmin,
    CampaignAdmin,
)
from shopman.shop.admin.channel import ChannelAdmin  # noqa: F401
from shopman.shop.admin.delivery import (  # noqa: F401
    DeliveryDistanceBandAdmin,
    DeliveryZoneAdmin,
)
from shopman.shop.admin.omotenashi import OmotenashiCopyAdmin  # noqa: F401
from shopman.shop.admin.orders import OrderAdmin  # noqa: F401
from shopman.shop.admin.promotion import CouponAdmin, PromotionAdmin  # noqa: F401
from shopman.shop.admin.quality import QualityDefectAdmin, QualityGradeAdmin  # noqa: F401
from shopman.shop.admin.rules import RuleConfigAdmin  # noqa: F401
from shopman.shop.admin.shop import NotificationTemplateAdmin, ShopAdmin  # noqa: F401
