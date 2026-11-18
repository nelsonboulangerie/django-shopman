"""Limites de abuso do backstage: Marketing (gate G-H04) e a busca de cliente do PDV."""

from __future__ import annotations

import hashlib

from django.core.cache import cache
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


class _MarketingLogicalFireThrottle(SimpleRateThrottle):
    """Charge one fire intent, not every round-trip of its confirmation gate."""

    def allow_request(self, request, view):
        if self.rate is None:
            return True
        throttle_key = self.get_cache_key(request, view)
        if throttle_key is None:
            return True
        idempotency_key = str(request.headers.get("Idempotency-Key") or "").strip()
        if not idempotency_key:
            return super().allow_request(request, view)
        operation_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        operation_key = f"{throttle_key}:operation:{operation_hash}"
        if cache.get(operation_key):
            return True
        allowed = super().allow_request(request, view)
        if allowed:
            cache.set(operation_key, True, timeout=self.duration)
        return allowed


class MarketingFireUserThrottle(
    _MarketingThrottleAuditMixin,
    _MarketingLogicalFireThrottle,
    UserRateThrottle,
):
    scope = "marketing_fire_user"


class MarketingFireShopThrottle(
    _MarketingThrottleAuditMixin,
    _MarketingLogicalFireThrottle,
):
    scope = "marketing_fire_shop"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": "default"}


class MarketingAIThrottle(_MarketingThrottleAuditMixin, UserRateThrottle):
    """Provider-cost and prompt-abuse budget, scoped to the signed-in operator."""

    scope = "marketing_ai"


class POSCustomerSearchThrottle(UserRateThrottle):
    """A busca de cliente do PDV, por operador (#2336).

    A lista sai mascarada, mas sem teto "aa", "ab", "ac"... enumerava a base de
    clientes. A régua (``pos_customer_search``) deixa folga para quem digita um
    nome letra a letra (a tela espera a pausa antes de buscar) e trava o
    varredor. Por operador, não por loja: dois balcões não se travam.
    """

    scope = "pos_customer_search"
