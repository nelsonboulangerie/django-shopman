"""Shared-cache throttling for Django Admin password submissions."""
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

from shopman.backstage.services.admin_login_ip import admin_login_ip

logger = logging.getLogger(__name__)


class AdminLoginRateLimitMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Temporary staging probe: a separate, removable review patch.
        from shopman.backstage.services.admin_ip_probe import observe_admin_ip_probe

        observe_admin_ip_probe(request)
        if request.method != "POST" or request.path != reverse("admin:login"):
            return None
        window = max(1, int(getattr(settings, "SHOPMAN_ADMIN_LOGIN_WINDOW_SECONDS", 300)))
        try:
            address = admin_login_ip(request)
        except ValueError:
            logger.warning("admin_login_client_ip_unavailable")
            return self._response(503, 30, "Não foi possível verificar o acesso agora. Tente novamente em instantes.")
        username = str(request.POST.get("username") or "").strip().casefold()
        buckets = [(address, int(getattr(settings, "SHOPMAN_ADMIN_LOGIN_IP_LIMIT", 20))),
                   (address + "\0" + username, int(getattr(settings, "SHOPMAN_ADMIN_LOGIN_ACCOUNT_IP_LIMIT", 5)))]
        try:
            for identity, limit in buckets:
                digest = hashlib.sha256(identity.encode()).hexdigest()
                key = f"admin-login:v1:{digest}"
                if cache.add(key, 1, timeout=window):
                    count = 1
                else:
                    try:
                        count = cache.incr(key)
                    except ValueError:
                        # Expiration between add and incr: begin a fresh bucket.
                        if cache.add(key, 1, timeout=window):
                            count = 1
                        else:
                            count = cache.incr(key)
                if count > max(1, limit):
                    return self._response(429, window, "Muitas tentativas de acesso. Aguarde alguns minutos e tente novamente.")
        except Exception:
            logger.exception("admin_login_rate_limit_unavailable")
            return self._response(503, 30, "Não foi possível verificar o acesso agora. Tente novamente em instantes.")
        return None

    @staticmethod
    def _response(status, retry_after, message):
        response = HttpResponse(message, status=status, content_type="text/plain; charset=utf-8")
        response["Retry-After"] = str(retry_after)
        response["Cache-Control"] = "no-store"
        return response
