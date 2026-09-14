#!/usr/bin/env python3
"""Prepared staging experiment: anonymous GETs only, no redirect or body output.

Not run by CI or deploy. Central review must approve the staging destination.
Read the temporary token from SHOPMAN_ADMIN_IP_PROBE_TOKEN, never from argv.
"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True, help="Isolated app ID verified and approved by central coordination")
    parser.add_argument("--url", required=True, help="Reviewed staging URL ending in /admin/login/")
    parser.add_argument("--staging-host", required=True, help="Exact staging host from the reviewed inventory")
    args = parser.parse_args()
    if args.app_id == "40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f":
        parser.error("The online Shopman app is forbidden for this experiment")
    url = urlsplit(args.url)
    online_hosts = {"shopman-staging-cdjpy.ondigitalocean.app", "menu.nelsonboulangerie.com.br",
                    "admin.boulangerie.com.br", "api.boulangerie.com.br", "backup.boulangerie.com.br",
                    "gestor.boulangerie.com.br", "kds.boulangerie.com.br", "pdv.boulangerie.com.br",
                    "prod.boulangerie.com.br", "central.boulangerie.com.br", "mkt.boulangerie.com.br",
                    "bi.boulangerie.com.br", "compras.boulangerie.com.br"}
    if url.hostname in online_hosts:
        parser.error("Online application hosts are forbidden, regardless of the supplied app ID")
    if (url.scheme != "https" or url.netloc != args.staging_host or url.path != "/admin/login/"
            or url.username or url.password or url.query or url.fragment):
        parser.error("Use the exact reviewed HTTPS staging host and /admin/login/, without query or credentials")
    token = os.environ.get("SHOPMAN_ADMIN_IP_PROBE_TOKEN", "")
    if len(token) < 32:
        parser.error("The temporary probe token must be supplied in the environment")
    # No environment HTTP proxy, cookies, authentication, or cross-host redirect.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    sentinel = "203.0.113.123"
    cases = [
        ("baseline", {}),
        ("forged-do", {"DO-Connecting-IP": sentinel}),
        ("forged-forwarded", {"X-Forwarded-For": sentinel, "CF-Connecting-IP": sentinel, "X-Real-IP": sentinel}),
        ("forged-all", {"DO-Connecting-IP": sentinel, "X-Forwarded-For": sentinel,
                        "CF-Connecting-IP": sentinel, "X-Real-IP": sentinel}),
        ("baseline-repeat", {}),
    ]
    expected = hmac.new(token.encode(), ("admin-ip-probe:" + sentinel).encode(), hashlib.sha256).hexdigest()
    print(json.dumps({"synthetic_spoof_fingerprint": expected}))
    for case, extra in cases:
        marker = secrets.token_hex(8)
        headers = {"X-Shopman-Admin-IP-Probe": token, "X-Shopman-Admin-IP-Probe-ID": marker, **extra}
        request = Request(args.url, headers=headers, method="GET")
        try:
            with opener.open(request, timeout=20) as response:
                status = response.status
        except HTTPError as error:
            status = error.code
            error.close()
        print(json.dumps({"case": case, "marker": marker, "status": status}))


if __name__ == "__main__":
    main()
