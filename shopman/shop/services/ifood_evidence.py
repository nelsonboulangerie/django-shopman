"""Read registered iFood evidence bytes without exposing the merchant credential.

Official FOOD handshake-platform-guide documents GET cancellationEvidences with
Bearer authorization and a blob response. External links are never fetched here.
"""
import re
from urllib.parse import urlsplit

import requests

from shopman.shop.services import ifood_auth

MAX_BYTES = 10 * 1024 * 1024
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_-]+\Z")


class EvidenceUnavailable(ValueError):
    def __init__(self):
        super().__init__("Evidência indisponível. Consulte a negociação no iFood.")


def protected_evidence_url(order, url):
    """Only the canonical provider endpoint belonging to this order is trusted."""
    if order.channel_ref != "ifood" or not isinstance(url, str):
        return False
    external_ref = str(order.external_ref or "")
    if not _SAFE_SEGMENT.fullmatch(external_ref):
        return False
    try:
        parsed = urlsplit(url)
        prefix = f"/order/v1.0/orders/{external_ref}/cancellationEvidences/"
        return bool(
            parsed.scheme == "https" and parsed.netloc == "merchant-api.ifood.com.br"
            and not parsed.query and not parsed.fragment and parsed.path.startswith(prefix)
            and _SAFE_SEGMENT.fullmatch(parsed.path[len(prefix):])
            and url == f"https://merchant-api.ifood.com.br{parsed.path}"
        )
    except ValueError:
        return False


def evidence_links(order, dispute_id):
    """Safe display links with their original registered evidence indices."""
    if order.channel_ref != "ifood":
        return []
    records = (order.data or {}).get("ifood", {}).get("handshakes", {})
    raw = records.get(dispute_id, {}).get("raw", {})
    nested = raw.get("metadata")
    evidences = raw.get("evidences", nested.get("evidences", []) if isinstance(nested, dict) else [])
    if not isinstance(evidences, list):
        return []
    links = []
    for index, item in enumerate(evidences):
        url = item.get("url") if isinstance(item, dict) else None
        if not isinstance(url, str) or any(ord(char) < 33 for char in url):
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                continue
            protected = protected_evidence_url(order, url)
            # Do not offer a credential-only provider URL that failed ownership/path validation.
            if parsed.hostname == "merchant-api.ifood.com.br" and not protected:
                continue
            links.append({"url": url, "index": index, "protected": protected})
        except ValueError:
            continue
    return links


def fetch_evidence(order, *, dispute_id, index):
    """Return (bytes, MIME). Caller authorizes staff and serves attachment/nosniff."""
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise EvidenceUnavailable()
    records = (order.data or {}).get("ifood", {}).get("handshakes", {})
    record = records.get(dispute_id, {})
    raw = record.get("raw", {})
    nested = raw.get("metadata")
    evidences = raw.get("evidences", nested.get("evidences", []) if isinstance(nested, dict) else [])
    if not isinstance(evidences, list) or index >= len(evidences) or not isinstance(evidences[index], dict):
        raise EvidenceUnavailable()
    url = evidences[index].get("url")
    if not protected_evidence_url(order, url):
        raise EvidenceUnavailable()
    try:
        headers = ifood_auth.authorized_headers()
        if not headers:
            raise EvidenceUnavailable()
        headers = {**headers, "Accept": "image/jpeg, image/png, image/gif, image/webp, application/pdf"}
        with requests.get(url, headers=headers, timeout=(5, 15), allow_redirects=False, stream=True) as response:
            mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if response.status_code != 200 or mime not in _ALLOWED_TYPES:
                raise EvidenceUnavailable()
            declared = response.headers.get("Content-Length")
            if declared is not None and (not declared.isdigit() or int(declared) > MAX_BYTES):
                raise EvidenceUnavailable()
            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if len(content) + len(chunk) > MAX_BYTES:
                    raise EvidenceUnavailable()
                content.extend(chunk)
            if not content:
                raise EvidenceUnavailable()
            return bytes(content), mime
    except requests.RequestException:
        raise EvidenceUnavailable() from None
