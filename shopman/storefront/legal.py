"""Versões públicas aplicáveis ao checkout da loja."""

TERMS_VERSION = "2026-09-12"
PRIVACY_VERSION = "2026-09-12"
TERMS_ARCHIVE_PATH = f"/documentos-legais/termos/{TERMS_VERSION}.html"
PRIVACY_ARCHIVE_PATH = f"/documentos-legais/privacidade/{PRIVACY_VERSION}.html"
TERMS_SHA256 = "afb821f0fe2d00c9cb41334b4fa9e042b8b2a6556e62c0f6da8fb4288265311f"
PRIVACY_SHA256 = "260a07f6f16ca357ddd4d6a5f82a4ed622fb641e19cb7540b5909fc1337ee5bc"


def checkout_legal_snapshot() -> dict[str, str]:
    """Retrato reproduzível dos documentos apresentados no checkout."""
    return {
        "terms_version": TERMS_VERSION,
        "terms_url": TERMS_ARCHIVE_PATH,
        "terms_sha256": TERMS_SHA256,
        "privacy_version": PRIVACY_VERSION,
        "privacy_url": PRIVACY_ARCHIVE_PATH,
        "privacy_sha256": PRIVACY_SHA256,
    }
