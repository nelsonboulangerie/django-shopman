"""Local certificate parsing and validity; never returns certificate contents."""
from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path


def certificate_issue(*, path: str = "", pfx_base64: str = "", password: str = "", pfx: bool = False) -> str:
    """An empty result means parseable and currently valid, not remotely trusted."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import pkcs12

        data = Path(path).read_bytes() if path else base64.b64decode(pfx_base64, validate=True)
        if pfx:
            key, certificate, _ = pkcs12.load_key_and_certificates(data, password.encode() if password else None)
            if key is None or certificate is None:
                return "invalid"
        else:
            certificate = x509.load_pem_x509_certificate(data)
        now = datetime.now(UTC)
        if now < certificate.not_valid_before_utc:
            return "not_yet_valid"
        if now >= certificate.not_valid_after_utc:
            return "expired"
    except Exception:
        # Includes unavailable parser, unreadable files, bad password and malformed data.
        return "invalid"
    return ""
