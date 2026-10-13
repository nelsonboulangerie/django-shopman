"""`relocate_product_images`: o conserto do dado que o gate `catalog.product_image_host` reprova."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from PIL import Image
from shopman.offerman.models import Product

from config import product_photos
from config.management.commands import relocate_product_images as command
from scripts import check_release_readiness as readiness
from scripts import import_product_photo

BASE = "https://img.padaria.test/products"
UNSPLASH = "https://images.unsplash.com/photo-1?auto=format&fit=crop&w=900&q=80"


@pytest.fixture
def host(monkeypatch):
    """O host dedicado de mentira: responde 200 para os arquivos em `served`."""
    served: set[str] = set()
    probed: list[str] = []

    def probe(url, **kwargs):
        probed.append(url)
        return None if url in served else "HTTP 404"

    monkeypatch.setattr(command, "probe_image", probe)
    monkeypatch.setenv("SHOPMAN_PRODUCT_IMAGE_BASE", BASE)
    return served, probed


def _run(*args) -> str:
    out = StringIO()
    call_command("relocate_product_images", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_dry_run_by_default_and_apply_moves_site_photo_and_gallery(host):
    served, _ = host
    served.update({f"{BASE}/ct.webp", f"{BASE}/ct2.webp"})
    Product.objects.create(
        sku="CT",
        name="Croissant",
        base_price_q=100,
        image_url="https://www.padaria.test/img/products/ct.webp",
        metadata={"gallery": ["https://menu.padaria.test/img/products/loja/ct2.webp"], "outra": 1},
    )

    report = _run()
    assert "Rode com --apply" in report
    assert Product.objects.get(sku="CT").image_url.startswith("https://www.")

    _run("--apply")
    product = Product.objects.get(sku="CT")
    assert product.image_url == f"{BASE}/ct.webp"
    assert product.metadata == {"gallery": [f"{BASE}/ct2.webp"], "outra": 1}
    assert readiness._product_image_host_check(profile="production", image_base=BASE).status == "passed"

    # Idempotente: a segunda rodada não tem nada a fazer e não grava história nova.
    history = product.history.count()
    assert "Nada a gravar." in _run("--apply")
    assert Product.objects.get(sku="CT").history.count() == history


@pytest.mark.django_db
def test_placeholder_without_a_hosted_photo_stays_and_is_reported(host):
    Product.objects.create(sku="CAP", name="Cappuccino", base_price_q=100, image_url=UNSPLASH, is_published=True)

    report = _run("--apply")

    assert Product.objects.get(sku="CAP").image_url == UNSPLASH
    assert "Sem foto no host dedicado (1 produtos, 1 publicados)" in report
    assert "CAP [publicado]: images.unsplash.com" in report
    assert "Nada a gravar." in report


@pytest.mark.django_db
def test_hosted_photo_table_replaces_the_placeholder_only_when_the_host_serves_it(host, monkeypatch):
    served, probed = host
    monkeypatch.setitem(product_photos.HOSTED_PHOTOS, "CAP", "cap.webp")
    Product.objects.create(sku="CAP", name="Cappuccino", base_price_q=100, image_url=UNSPLASH)

    report = _run("--apply")
    assert "Destino não responde" in report
    assert f"{BASE}/cap.webp HTTP 404" in report
    assert Product.objects.get(sku="CAP").image_url == UNSPLASH

    served.add(f"{BASE}/cap.webp")
    _run("--apply")
    assert Product.objects.get(sku="CAP").image_url == f"{BASE}/cap.webp"
    assert probed.count(f"{BASE}/cap.webp") == 2


@pytest.mark.django_db
def test_hosted_photo_table_gives_a_photo_to_a_product_without_one(host, monkeypatch):
    served, _ = host
    served.add(f"{BASE}/porq.webp")
    monkeypatch.setitem(product_photos.HOSTED_PHOTOS, "PORQ", "porq.webp")
    Product.objects.create(sku="PORQ", name="Porquinho", base_price_q=100, image_url="")

    _run("--apply")

    assert Product.objects.get(sku="PORQ").image_url == f"{BASE}/porq.webp"


@pytest.mark.django_db
def test_without_the_dedicated_host_the_command_refuses(monkeypatch):
    from django.core.management.base import CommandError

    monkeypatch.delenv("SHOPMAN_PRODUCT_IMAGE_BASE", raising=False)
    with pytest.raises(CommandError, match="SHOPMAN_PRODUCT_IMAGE_BASE"):
        _run()


def test_every_hosted_photo_exists_in_the_storefront_folder():
    """A tabela só aponta para arquivo que o deploy leva ao host."""
    missing = [
        f"{sku}: {name}"
        for sku, name in product_photos.HOSTED_PHOTOS.items()
        if not (import_product_photo.PHOTO_DIR / name).is_file()
    ]
    assert missing == []


def test_import_product_photo_follows_the_house_recipe_and_never_overwrites(tmp_path: Path):
    source = tmp_path / "origem.jpg"
    Image.new("RGB", (3000, 2000), (200, 150, 100)).save(source, format="JPEG")
    photo_dir = tmp_path / "products"

    target = import_product_photo.import_photo("CAP", str(source), photo_dir=photo_dir)

    assert target.name == "cap.webp"
    with Image.open(target) as saved:
        assert saved.format == "WEBP"
        assert saved.size == (1200, 1200)
        assert not saved.getexif()
    with pytest.raises(FileExistsError, match="cap.v2.webp"):
        import_product_photo.import_photo("CAP", str(source), photo_dir=photo_dir)


def test_import_product_photo_never_enlarges(tmp_path: Path):
    source = tmp_path / "pequena.png"
    Image.new("RGB", (400, 600), (10, 10, 10)).save(source, format="PNG")

    target = import_product_photo.import_photo("SP", str(source), photo_dir=tmp_path)

    with Image.open(target) as saved:
        assert saved.size == (400, 400)
