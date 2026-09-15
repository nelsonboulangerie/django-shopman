"""Admin two-factor (TOTP) gate.

After individual enrollment, or when ``SHOPMAN_ADMIN_REQUIRE_2FA`` is enabled, a staff user
reaching ``/admin/`` must be OTP-verified (a confirmed TOTP device + a verified
session via the verify view). Off by default so it never locks anyone out before
enrollment; enable only after each admin has a device (``setup_admin_totp``).

Relies on ``django_otp.middleware.OTPMiddleware`` (which sets
``request.user.is_verified()``) running earlier in the stack.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse
from django.utils.http import urlencode

from shopman.backstage.models import AdminTwoFactorEnrollment


class AdminTwoFactorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            needs_verification = self._needs_verification(request)
        except NoReverseMatch:
            return HttpResponse("Verificação em duas etapas indisponível.", status=503)
        if needs_verification:
            try:
                verify_url = reverse("admin_2fa_verify")
            except NoReverseMatch:
                return HttpResponse("Verificação em duas etapas indisponível.", status=503)
            return redirect(f"{verify_url}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)

    @staticmethod
    def _needs_verification(request) -> bool:
        path = request.path
        if not path.startswith("/admin/"):
            return False
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and user.is_staff):
            return False
        # Completed enrollment is an individual opt-in; global rollout remains separate.
        required = getattr(settings, "SHOPMAN_ADMIN_REQUIRE_2FA", False) or AdminTwoFactorEnrollment.objects.filter(user=user).exists()
        if not required:
            return False
        exempt = {reverse("admin_2fa_verify"), reverse("admin_2fa_enroll"),
                  reverse("admin:login"), reverse("admin:logout")}
        if path in exempt:
            return False
        # is_verified() is added by OTPMiddleware; True once a TOTP token was accepted.
        return not getattr(user, "is_verified", lambda: False)()
