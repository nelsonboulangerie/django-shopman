from pathlib import Path

from shopman.storefront.legal import PRIVACY_VERSION, TERMS_VERSION, checkout_legal_snapshot


def test_checkout_legal_snapshot_uses_public_page_versions():
    root = Path(__file__).resolve().parents[3]
    privacy = (root / "surfaces/storefront-nuxt/app/pages/privacy.vue").read_text()
    terms = (root / "surfaces/storefront-nuxt/app/pages/terms.vue").read_text()

    assert checkout_legal_snapshot() == {
        "terms_version": "2026-09-11",
        "privacy_version": "2026-09-11",
    }
    assert TERMS_VERSION in terms
    assert PRIVACY_VERSION in privacy
