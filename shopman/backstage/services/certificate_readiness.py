"""Local certificate parsing and validity; never returns certificate contents."""
from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def certificate_issue(*, path: str = "", pfx_base64: str = "", password: str = "", pfx: bool = False) -> str:
    """An empty result means locally usable and currently valid, not remotely trusted."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import pkcs12

        data = Path(path).read_bytes() if path else base64.b64decode(pfx_base64, validate=True)
        if pfx:
            private_key, certificate, _ = pkcs12.load_key_and_certificates(
                data,
                password.encode() if password else None,
            )
            if private_key is None:
                return "missing_private_key"
            if certificate is None:
                return "invalid"
        else:
            certificate = x509.load_pem_x509_certificate(data)
            if b"PRIVATE KEY-----" not in data:
                return "missing_private_key"
            private_key = serialization.load_pem_private_key(data, password=None)
        certificate_public_key = certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_public_key = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if certificate_public_key != private_public_key:
            return "private_key_mismatch"
        now = datetime.now(UTC)
        if now < certificate.not_valid_before_utc:
            return "not_yet_valid"
        if now >= certificate.not_valid_after_utc:
            return "expired"
    except Exception:
        logger.warning("certificate_readiness_invalid")
        # Includes unavailable parser, unreadable files, bad password and malformed data.
        return "invalid"
    return ""
