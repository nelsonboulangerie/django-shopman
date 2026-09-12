import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("check_legal_archive", SCRIPTS / "check_legal_archive.py")
check_legal_archive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(check_legal_archive)


def test_new_version_is_append_only_and_versioned():
    assert check_legal_archive.classify_archive_changes(
        ["A\tsurfaces/storefront-nuxt/public/documentos-legais/termos/2026-09-12.html"]
    ) == []


def test_existing_version_cannot_be_rewritten_or_removed():
    lines = [
        "M\tsurfaces/storefront-nuxt/public/documentos-legais/termos/2026-09-12.html",
        "D\tsurfaces/storefront-nuxt/public/documentos-legais/privacidade/2026-09-12.html",
    ]
    assert check_legal_archive.classify_archive_changes(lines) == [
        (
            "M",
            "surfaces/storefront-nuxt/public/documentos-legais/termos/2026-09-12.html",
            "versão existente não pode ser alterada ou removida",
        ),
        (
            "D",
            "surfaces/storefront-nuxt/public/documentos-legais/privacidade/2026-09-12.html",
            "versão existente não pode ser alterada ou removida",
        ),
    ]


def test_archive_rejects_ambiguous_filename():
    assert check_legal_archive.classify_archive_changes(
        ["A\tsurfaces/storefront-nuxt/public/documentos-legais/termos/atual.html"]
    ) == [
        (
            "A",
            "surfaces/storefront-nuxt/public/documentos-legais/termos/atual.html",
            "use tipo/data.html em termos ou privacidade",
        )
    ]


def test_unrelated_files_are_ignored():
    assert check_legal_archive.classify_archive_changes(["M\tshopman/storefront/legal.py"]) == []
