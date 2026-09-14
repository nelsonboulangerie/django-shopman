"""TEMPORARY: staging-only observation; remove after Admin ingress review.

No endpoint or response echo. Never log raw addresses, headers, credentials,
usernames or tokens. Fingerprints are scoped to an expiring probe secret.
"""
import hashlib
import hmac
import json
import logging
import re
import time

from django.conf import settings
from django.urls import reverse

from shopman.backstage.services.admin_login_ip import canonical_ip

logger = logging.getLogger(__name__)


def observe_admin_ip_probe(request) -> None:
    if settings.SHOPMAN_ENVIRONMENT != "staging" or request.method != "GET" or request.path != reverse("admin:login"):
        return
    if getattr(getattr(request, "user", None), "is_authenticated", False):
        return
    token = getattr(settings, "SHOPMAN_ADMIN_IP_PROBE_TOKEN", "")
    supplied = request.META.get("HTTP_X_SHOPMAN_ADMIN_IP_PROBE", "")
    if not isinstance(token, str) or len(token) < 32 or not isinstance(supplied, str):
        return
    if not hmac.compare_digest(token.encode(), supplied.encode()):
        return
    marker = request.META.get("HTTP_X_SHOPMAN_ADMIN_IP_PROBE_ID", "")
    if not isinstance(marker, str) or not re.fullmatch(r"[0-9a-f]{16}", marker):
        return
    try:
        remaining = float(getattr(settings, "SHOPMAN_ADMIN_IP_PROBE_UNTIL", 0)) - time.time()
    except (ValueError, TypeError):
        return  # Invalid probe configuration disables observation.
    if not 0 < remaining <= 900:
        return

    def fingerprint(value):
        try:
            address = canonical_ip(value)
        except ValueError:
            return "absent_or_invalid"
        return hmac.new(token.encode(), ("admin-ip-probe:" + address).encode(), hashlib.sha256).hexdigest()

    # Fixed keys only. An attacker-controlled chain is bounded and never echoed.
    xff = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))[:2048].split(",")
    record = {
        "marker": marker,
        "remote": fingerprint(request.META.get("REMOTE_ADDR", "")),
        "do": fingerprint(request.META.get("HTTP_DO_CONNECTING_IP", "")),
        "cf": fingerprint(request.META.get("HTTP_CF_CONNECTING_IP", "")),
        "real": fingerprint(request.META.get("HTTP_X_REAL_IP", "")),
        "xff": [fingerprint(value) for value in xff[:8]],
        "xff_truncated": len(xff) > 8,
    }
    logger.info("admin_ip_probe %s", json.dumps(record, sort_keys=True))
