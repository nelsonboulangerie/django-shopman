"""Versões públicas aplicáveis ao checkout da loja."""

TERMS_VERSION = "2026-09-11"
PRIVACY_VERSION = "2026-09-11"


def checkout_legal_snapshot() -> dict[str, str]:
    """Retrato mínimo que acompanha o pedido para a versão ser comprovável."""
    return {
        "terms_version": TERMS_VERSION,
        "privacy_version": PRIVACY_VERSION,
    }
