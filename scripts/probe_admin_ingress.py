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
import socket
import ssl
from http.client import HTTPSConnection
from ipaddress import ip_address
from urllib.parse import urlsplit


def send_case(host, token, marker, extra, connection_factory=HTTPSConnection, connect_ip=None):
    """One HTTPS GET, preserving duplicate field lines; no redirects/cookie jar."""
    connection = connection_factory(host, timeout=20)
    try:
        if connect_ip:
            # Resolve-only override: HTTPS authority, certificate validation and SNI
            # remain the reviewed hostname. Controller verifies DNS -> isolated app.
            address = str(ip_address(connect_ip))
            plain = socket.create_connection((address, 443), timeout=20)
            try:
                connection.sock = ssl.create_default_context().wrap_socket(plain, server_hostname=host)
            except BaseException:
                plain.close()
                raise
        connection.putrequest("GET", "/admin/login/", skip_accept_encoding=True)
        connection.putheader("X-Shopman-Admin-IP-Probe", token)
        connection.putheader("X-Shopman-Admin-IP-Probe-ID", marker)
        for name, value in extra:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        return response.status
    finally:
        connection.close()


def probe_cases():
    sentinel = "203.0.113.123"
    second = "198.51.100.123"
    return [
        ("baseline", []),
        ("forged-do", [("DO-Connecting-IP", sentinel)]),
        ("forged-forwarded", [("X-Forwarded-For", sentinel), ("CF-Connecting-IP", sentinel),
                              ("X-Real-IP", sentinel)]),
        ("forged-all", [("DO-Connecting-IP", sentinel), ("X-Forwarded-For", sentinel),
                       ("CF-Connecting-IP", sentinel), ("X-Real-IP", sentinel)]),
        ("duplicate-do", [("DO-Connecting-IP", sentinel), ("DO-Connecting-IP", second)]),
        ("duplicate-do-reverse", [("DO-Connecting-IP", second), ("DO-Connecting-IP", sentinel)]),
        ("baseline-repeat", []),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True, help="Isolated app ID verified and approved by central coordination")
    parser.add_argument("--url", required=True, help="Reviewed staging URL ending in /admin/login/")
    parser.add_argument("--staging-host", required=True, help="Exact staging host from the reviewed inventory")
    parser.add_argument("--omit-synthetic-fingerprints", action="store_true")
    parser.add_argument("--connect-ip", help="Optional IP from DNS verified by the isolated experiment controller")
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
    # HTTPSConnection does not consult HTTP proxy environment or retain cookies.
    for sentinel in ("203.0.113.123", "198.51.100.123"):
        expected = hmac.new(token.encode(), ("admin-ip-probe:" + sentinel).encode(), hashlib.sha256).hexdigest()
        if not args.omit_synthetic_fingerprints:
            print(json.dumps({"synthetic_spoof_fingerprint": expected}), flush=True)
    for case, extra in probe_cases():
        marker = secrets.token_hex(8)
        status = send_case(args.staging_host, token, marker, extra, connect_ip=args.connect_ip)
        print(json.dumps({"case": case, "marker": marker, "status": status}), flush=True)


if __name__ == "__main__":
    main()
