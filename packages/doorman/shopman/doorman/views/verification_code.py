"""
Verification code views.
"""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View

from ..conf import get_adapter, get_doorman_settings
from ..models import VerificationCode
from ..services.verification import AuthService
from ..utils import get_client_ip, safe_redirect_url

logger = logging.getLogger("shopman.doorman.views.verification_code")


class VerificationCodeRequestView(View):
    """
    Request a verification code.

    GET /doorman/code/request
        Renders code_request.html form

    POST /doorman/code/request
        Form data: target=...
        JSON data: {"target": "..."}

    On success (form): Redirects to code-verify
    On success (JSON): Returns {"success": true, "target": "..."}
    """

    def get_template_name(self):
        """Get template name from settings."""
        settings = get_doorman_settings()
        return settings.TEMPLATE_CODE_REQUEST

    def get(self, request):
        context = {
            "next": request.GET.get("next", ""),
            "target": "",
        }
        return render(request, self.get_template_name(), context)

    def post(self, request):
        template_name = self.get_template_name()

        # Parse input
        is_json = request.content_type == "application/json"

        if is_json:
            try:
                data = json.loads(request.body)
                target_raw = data.get("target", "")
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)
        else:
            target_raw = request.POST.get("target", "")

        if not target_raw:
            error = str(_("Por favor, informe seu identificador de acesso."))
            if is_json:
                return JsonResponse({"error": error}, status=400)
            return render(request, template_name, {"error": error, "target": ""})

        target = get_adapter().login_handle(target_raw).value
        if not target:
            error = str(_("Identificador de acesso inválido."))
            if is_json:
                return JsonResponse({"error": error}, status=400)
            return render(
                request,
                template_name,
                {"error": error, "target": target_raw},
            )

        # Request code
        settings = get_doorman_settings()
        result = AuthService.request_code(
            target_value=target,
            purpose=VerificationCode.Purpose.LOGIN,
            ip_address=get_client_ip(request, settings.TRUSTED_PROXY_DEPTH),
        )

        if not result.success:
            if is_json:
                return JsonResponse({"error": result.error}, status=429)
            return render(
                request,
                template_name,
                {"error": result.error, "target": target_raw},
            )

        # Success
        if is_json:
            return JsonResponse({"success": True, "target": target})

        # Store target and next URL in session
        request.session["auth_target"] = target
        raw_next = request.POST.get("next") or request.GET.get("next", "")
        if raw_next:
            # Validate before storing to prevent open redirect (H02)
            validated = safe_redirect_url(raw_next, request)
            if validated != get_doorman_settings().LOGIN_REDIRECT_URL:
                request.session["doorman_next"] = validated

        return redirect("doorman:code-verify")


class VerificationCodeVerifyView(View):
    """
    Verify a verification code.

    GET /doorman/code/verify
        Renders code_verify.html form

    POST /doorman/code/verify
        Form data: target=..., code=...
        JSON data: {"target": "...", "code": "..."}

    On success (form): Redirects to LOGIN_REDIRECT_URL
    On success (JSON): Returns {"success": true, "customer_id": "..."}
    """

    def get_template_name(self):
        """Get template name from settings."""
        settings = get_doorman_settings()
        return settings.TEMPLATE_CODE_VERIFY

    def get(self, request):
        target = request.session.get("auth_target")
        if not target:
            return redirect("doorman:code-request")
        return render(request, self.get_template_name(), {"target": target})

    def post(self, request):
        template_name = self.get_template_name()

        # Parse input
        is_json = request.content_type == "application/json"

        if is_json:
            try:
                data = json.loads(request.body)
                target = data.get("target", "")
                code = data.get("code", "")
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)
        else:
            target = request.POST.get("target") or request.session.get("auth_target", "")
            code = request.POST.get("code", "")

        # Validate input
        if not target or not code:
            error = str(_("Identificador e código são obrigatórios."))
            if is_json:
                return JsonResponse({"error": error}, status=400)
            return render(
                request,
                template_name,
                {"error": error, "target": target},
            )

        target = get_adapter().login_handle(target).value

        # Verify code
        result = AuthService.verify_for_login(target, code, request)

        if not result.success:
            if is_json:
                return JsonResponse(
                    {
                        "error": result.error,
                        "attempts_remaining": result.attempts_remaining,
                    },
                    status=400,
                )
            return render(
                request,
                template_name,
                {
                    "error": result.error,
                    "target": target,
                    "attempts_remaining": result.attempts_remaining,
                },
            )

        # Get next URL from session before clearing
        next_url = request.session.pop("doorman_next", None)

        # Clear session data
        request.session.pop("auth_target", None)

        # Success
        if is_json:
            return JsonResponse(
                {
                    "success": True,
                    "customer_id": str(result.customer.subject_id),
                }
            )

        # Redirect to next URL or default (H02 - validated)
        redirect_url = safe_redirect_url(next_url, request)
        return redirect(redirect_url)
