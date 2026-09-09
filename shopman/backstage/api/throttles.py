"""Low-cardinality Marketing abuse limits from approved gate G-H04."""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class _MarketingThrottleAuditMixin:
    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)
        if not allowed:
            from shopman.shop.services.marketing_security import record_security_denial

            record_security_denial(
                actor=getattr(request, "user", None),
                reason_code="quota_exceeded",
                action="rate_limit",
            )
        return allowed


class MarketingDangerousUserThrottle(_MarketingThrottleAuditMixin, UserRateThrottle):
    scope = "marketing_dangerous_user"


class MarketingDangerousShopThrottle(_MarketingThrottleAuditMixin, SimpleRateThrottle):
    scope = "marketing_dangerous_shop"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": "default"}


class MarketingAudienceUserThrottle(_MarketingThrottleAuditMixin, UserRateThrottle):
    scope = "marketing_audience_user"


class MarketingAudienceShopThrottle(_MarketingThrottleAuditMixin, SimpleRateThrottle):
    scope = "marketing_audience_shop"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": "default"}


class MarketingFireUserThrottle(_MarketingThrottleAuditMixin, UserRateThrottle):
    scope = "marketing_fire_user"


class MarketingFireShopThrottle(_MarketingThrottleAuditMixin, SimpleRateThrottle):
    scope = "marketing_fire_shop"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": "default"}
