"""Public probes with small disclosures and a protected diagnostic endpoint."""

from __future__ import annotations

import logging

from django.http import JsonResponse
from django.views import View

from shopman.watchman.runner import run_profile

logger = logging.getLogger(__name__)


def _headers(response: JsonResponse) -> JsonResponse:
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class ProbeView(View):
    profile = "liveness"

    def get(self, request):
        try:
            report = run_profile(self.profile, metadata={"request": request})
        except Exception:  # noqa: BLE001 - Watchman configuration cannot break the observed app
            logger.exception("watchman_probe_error profile=%s", self.profile)
            return _headers(
                JsonResponse(
                    {"status": "ok", "checks": {"watchman": "unknown"}},
                    status=200,
                )
            )
        payload = {
            "status": "error" if report.probe_failed else "ok",
            "checks": {result.id: result.status.value for result in report.results},
        }
        return _headers(JsonResponse(payload, status=503 if report.probe_failed else 200))


class LiveView(ProbeView):
    profile = "liveness"


class ReadyView(ProbeView):
    profile = "readiness"


class StatusView(View):
    """Full evidence for authenticated staff; never suitable as a platform probe."""

    def get(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not user.is_staff:
            return _headers(JsonResponse({"detail": "Forbidden."}, status=403))
        profile = request.GET.get("profile", "diagnostic")
        try:
            report = run_profile(profile, metadata={"request": request})
        except Exception as exc:  # configuration errors are safe to disclose only by class
            logger.exception("watchman_status_error profile=%s", profile)
            return _headers(
                JsonResponse(
                    {"schema_version": 1, "status": "unknown", "error": exc.__class__.__name__},
                    status=500,
                )
            )
        return _headers(JsonResponse(report.to_dict(include_evidence=True), status=200))
