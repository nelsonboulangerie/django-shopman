import hashlib
from pathlib import Path

from shopman.storefront.legal import (
    PRIVACY_ARCHIVE_PATH,
    PRIVACY_VERSION,
    TERMS_ARCHIVE_PATH,
    TERMS_VERSION,
    checkout_legal_snapshot,
)


def test_checkout_legal_snapshot_uses_public_page_versions():
    root = Path(__file__).resolve().parents[3]
    privacy = (root / "surfaces/storefront-nuxt/app/pages/privacy.vue").read_text()
    terms = (root / "surfaces/storefront-nuxt/app/pages/terms.vue").read_text()
    checkout = (root / "surfaces/storefront-nuxt/app/pages/finalizar.vue").read_text()
    public = root / "surfaces/storefront-nuxt/public"
    terms_archive = public / TERMS_ARCHIVE_PATH.removeprefix("/")
    privacy_archive = public / PRIVACY_ARCHIVE_PATH.removeprefix("/")

    assert checkout_legal_snapshot() == {
        "terms_version": "2026-09-12",
        "terms_url": "/documentos-legais/termos/2026-09-12.html",
        "terms_sha256": hashlib.sha256(terms_archive.read_bytes()).hexdigest(),
        "privacy_version": "2026-09-12",
        "privacy_url": "/documentos-legais/privacidade/2026-09-12.html",
        "privacy_sha256": hashlib.sha256(privacy_archive.read_bytes()).hexdigest(),
    }
    assert TERMS_VERSION in terms
    assert PRIVACY_VERSION in privacy
    assert terms_archive.is_file()
    assert privacy_archive.is_file()
    assert TERMS_ARCHIVE_PATH in checkout
    assert PRIVACY_ARCHIVE_PATH in checkout
