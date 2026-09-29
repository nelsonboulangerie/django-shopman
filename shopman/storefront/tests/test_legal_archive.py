"""O pedido cita os Termos e a Privacidade que valiam quando foi feito.

A página viva muda; a cópia arquivada, não. Estas travas cobram as três pontas:
o arquivo existe e bate com o hash declarado, o checkout grava a citação na parte
SELADA do pedido, e o gate de CI recusa reescrever uma versão já publicada.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from shopman.orderman.models import Order

from shopman.storefront.presentation.legal import (
    LEGAL_ARCHIVE,
    LEGAL_ARCHIVE_KINDS,
    LEGAL_VERSION,
    legal_archive_path,
    order_legal_snapshot,
)

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "surfaces/storefront-nuxt/public"
SCRIPTS = ROOT / "scripts"

#: A página viva de cada documento.
LIVE_PAGE = {"privacy": "/privacidade", "terms": "/termos"}

#: A cópia de 2026-09-24 foi tirada quando as páginas vivas moravam em /privacy e
#: /terms, e os links dela apontam para lá. Esses endereços deixaram de existir no
#: mesmo dia, SEM 301: pré-go-live, o Google reindexa, e redirect só existe quando o
#: Google exige. Os links dessa cópia levam a 404, e ela fica assim de propósito:
#: pedidos feitos desde o deploy do #1047 guardam em `Order.snapshot` o SHA-256
#: destes bytes, e reescrever o arquivo quebraria a prova de todos eles. As versões
#: seguintes não repetem o problema: o arquivador liga um documento à cópia IRMÃ da
#: mesma versão, e só a nota do topo aponta para a página viva.
FROZEN_WITH_PRE_RENAME_LINKS = {
    "2026-09-24": {"privacy": "/privacy", "terms": "/terms"},
}


def _load_script(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ── o arquivo ──────────────────────────────────────────────────────────


def test_every_archived_version_has_both_files_with_the_declared_hash():
    assert LEGAL_ARCHIVE, "nenhuma versão arquivada"
    for version, hashes in LEGAL_ARCHIVE.items():
        assert set(hashes) == set(LEGAL_ARCHIVE_KINDS), version
        for kind in LEGAL_ARCHIVE_KINDS:
            archived = PUBLIC / legal_archive_path(kind, version).removeprefix("/")
            assert archived.is_file(), f"falta {archived.relative_to(ROOT)}"
            assert hashlib.sha256(archived.read_bytes()).hexdigest() == hashes[kind], (
                f"{archived.relative_to(ROOT)} não é o arquivo declarado em LEGAL_ARCHIVE — "
                "versão publicada não se reescreve: publique uma versão nova"
            )


def test_no_archived_file_is_orphan():
    """Arquivo sem hash declarado é cópia que nenhum pedido consegue citar."""
    declared = {
        legal_archive_path(kind, version).removeprefix("/")
        for version in LEGAL_ARCHIVE
        for kind in LEGAL_ARCHIVE_KINDS
    }
    on_disk = {
        str(path.relative_to(PUBLIC))
        for path in (PUBLIC / "documentos-legais").rglob("*")
        if path.is_file()
    }
    assert on_disk == declared


def test_the_archiver_reads_the_live_page_where_it_lives():
    documents = _load_script("archive_legal_version").DOCUMENTS
    assert {kind: spec["path"] for kind, spec in documents.items()} == LIVE_PAGE


def test_the_archiver_links_each_document_to_its_sibling_copy_not_to_a_live_route():
    """Rota viva muda; a cópia irmã da mesma versão, não. Só a nota do topo é viva."""
    archiver = _load_script("archive_legal_version")
    page = (
        '<header id="legal-top"><h1>Termos de uso</h1>'
        '<div class="shop-muted">Atualizados em 1 de janeiro de 2099.</div></header>'
        '<div class="shop-legal"><section id="payment"><h2>Pagamento</h2>'
        '<p>Veja a <a href="/privacidade#processors">política</a> e a '
        '<a href="/conta/seguranca">conta</a>.</p></section></div>'
    )
    html, _meta = archiver.render_archive(
        kind="terms", version="2099-01-01", source_url="https://x.test/termos", page_html=page
    )
    assert 'href="/documentos-legais/privacidade/2099-01-01.html#processors"' in html
    assert 'href="/conta/seguranca"' in html
    assert 'href="/privacidade' not in html
    assert html.count('href="/termos"') == 1  # a nota do topo: "o texto que vale hoje"


def test_archive_is_the_published_text_of_its_own_version():
    """A cópia diz a versão dela e aponta para a página viva do dia em que foi tirada."""
    for version in LEGAL_ARCHIVE:
        live_page = FROZEN_WITH_PRE_RENAME_LINKS.get(version, LIVE_PAGE)
        for kind in LEGAL_ARCHIVE_KINDS:
            html = (PUBLIC / legal_archive_path(kind, version).removeprefix("/")).read_text()
            assert f"versão {version}" in html
            assert f'href="{live_page[kind]}"' in html
            # O Cloudflare ofusca e-mail no HTML servido; a cópia guarda o endereço lido.
            assert "email-protection" not in html
            assert "<script" not in html


# ── a citação no pedido ────────────────────────────────────────────────


def test_snapshot_of_an_archived_version_carries_url_and_hash():
    version = next(iter(LEGAL_ARCHIVE))
    snapshot = order_legal_snapshot(version)
    assert snapshot == {
        "version": version,
        "archived": True,
        "privacy_url": f"/documentos-legais/privacidade/{version}.html",
        "privacy_sha256": LEGAL_ARCHIVE[version]["privacy"],
        "terms_url": f"/documentos-legais/termos/{version}.html",
        "terms_sha256": LEGAL_ARCHIVE[version]["terms"],
    }


def test_snapshot_of_a_version_not_yet_archived_says_so_and_invents_no_hash():
    """Arquivar vem depois do deploy. Nessa janela o pedido declara a lacuna."""
    snapshot = order_legal_snapshot("2099-01-01")
    assert snapshot == {
        "version": "2099-01-01",
        "archived": False,
        "privacy_url": "/documentos-legais/privacidade/2099-01-01.html",
        "terms_url": "/documentos-legais/termos/2099-01-01.html",
    }


def test_archive_path_rejects_unknown_document():
    with pytest.raises(ValueError):
        legal_archive_path("cookies", LEGAL_VERSION)


@pytest.mark.django_db(transaction=True)
def test_checkout_seals_the_legal_versions_in_force_into_the_order(client):
    from shopman.storefront.tests._checkout_auth import authenticate_checkout
    from shopman.storefront.tests._checkout_baseline import with_baseline
    from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

    _seed_surface(stock_qty=Decimal("10"))
    authenticate_checkout(client)
    from django.utils import timezone

    from shopman.shop.models import Channel, DeliveryZone, Shop

    # O mesmo caminho de entrega do teste de cartão (test_checkout_card_web.py).
    Channel.objects.filter(ref="web").update(config={"payment": {"method": ["pix", "card"]}})
    DeliveryZone.objects.create(
        shop=Shop.objects.first(),
        name="Centro",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="860",
        fee_q=600,
    )
    add = client.put(
        "/api/v1/cart/skus/PAO-FRANCES/",
        data={"qty": 1},
        content_type="application/json",
    )
    assert add.status_code == 200, add.content

    resp = client.post(
        "/api/v1/checkout/",
        data=with_baseline(client, {
            "name": "Ana",
            "phone": "+5543999990001",
            "fulfillment_type": "delivery",
            "delivery_address": "Rua das Flores, 1",
            "delivery_address_structured": {
                "formatted_address": "Rua das Flores, 1 - Centro",
                "postal_code": "86050-270",
                "neighborhood": "Centro",
            },
            "delivery_date": timezone.localdate().isoformat(),
            "payment_method": "pix",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content

    order = Order.objects.get(ref=resp.json()["order_ref"])
    # Na parte SELADA: evidência não se edita depois do commit.
    assert order.snapshot["data"]["legal"] == order_legal_snapshot()
    assert order.snapshot["data"]["legal"]["version"] == LEGAL_VERSION
    # E não em `order.data`, que handlers reescrevem.
    assert "legal" not in (order.data or {})


# ── o gate de CI ───────────────────────────────────────────────────────


def test_gate_accepts_a_new_version_as_a_new_file():
    gate = _load_script("check_legal_archive")
    assert gate.classify_archive_changes(
        ["A\tsurfaces/storefront-nuxt/public/documentos-legais/termos/2026-10-01.html"]
    ) == []


def test_gate_refuses_rewriting_or_removing_a_published_version():
    gate = _load_script("check_legal_archive")
    lines = [
        "M\tsurfaces/storefront-nuxt/public/documentos-legais/termos/2026-09-24.html",
        "D\tsurfaces/storefront-nuxt/public/documentos-legais/privacidade/2026-09-24.html",
    ]
    assert [status for status, _path, _reason in gate.classify_archive_changes(lines)] == ["M", "D"]


def test_gate_refuses_an_ambiguous_name():
    gate = _load_script("check_legal_archive")
    violations = gate.classify_archive_changes(
        ["A\tsurfaces/storefront-nuxt/public/documentos-legais/termos/atual.html"]
    )
    assert [status for status, _path, _reason in violations] == ["A"]


def test_gate_ignores_everything_else():
    gate = _load_script("check_legal_archive")
    assert gate.classify_archive_changes(["M\tshopman/storefront/presentation/legal.py"]) == []
