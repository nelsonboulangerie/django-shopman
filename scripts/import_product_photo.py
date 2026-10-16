#!/usr/bin/env python3
"""Traz uma foto de produto para o host dedicado, na receita da casa.

Usage::

    python scripts/import_product_photo.py CAP ~/Dev/Claude/fotos-nelson/produtos/CAP.jpg
    python scripts/import_product_photo.py CAP https://images.unsplash.com/photo-...  # baixa a origem
    python scripts/import_product_photo.py CAP origem.jpg --name cap.v2.webp

Grava ``surfaces/storefront-nuxt/public/img/products/<nome>.webp`` (padrão:
``<sku em minúsculas>.webp``) com a receita do CATALOG-IMAGES-OFF-GITHUB-PLAN:
recorte quadrado central, 1200 px de lado (nunca ampliando), webp q80, sem EXIF.
Depois imprime a linha que entra em ``config/product_photos.py`` (``HOSTED_PHOTOS``).

Recusa sobrescrever: o host serve as fotos com cache imutável de um ano, e
sobrescrever deixaria o cliente na foto velha. Trocar foto é trocar o NOME.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PHOTO_DIR = REPO / "surfaces" / "storefront-nuxt" / "public" / "img" / "products"
SIDE = 1200
QUALITY = 80


def read_source(source: str) -> bytes:
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": "shopman-import-product-photo"})
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 — origem dada por quem roda
            return response.read()
    return Path(source).expanduser().read_bytes()


def to_house_webp(raw: bytes) -> bytes:
    """Recorte quadrado central, no máximo 1200 px, webp q80, sem EXIF."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    if side > SIDE:
        image = image.resize((SIDE, SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=QUALITY, method=6)
    return out.getvalue()


def import_photo(sku: str, source: str, *, name: str | None = None, photo_dir: Path = PHOTO_DIR) -> Path:
    filename = name or f"{sku.lower()}.webp"
    if not filename.endswith(".webp") or "/" in filename:
        raise ValueError(f"nome inválido: {filename!r} (um arquivo .webp, sem pasta)")
    target = photo_dir / filename
    if target.exists():
        raise FileExistsError(
            f"{target.name} já existe. O host serve foto com cache imutável: use outro nome (ex.: --name "
            f"{target.stem}.v2.webp)."
        )
    data = to_house_webp(read_source(source))
    photo_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sku")
    parser.add_argument("source", help="arquivo local ou URL http(s)")
    parser.add_argument("--name", default=None, help="nome do arquivo (.webp). Padrão: <sku>.webp")
    args = parser.parse_args(argv)
    try:
        target = import_photo(args.sku, args.source, name=args.name)
    except (FileExistsError, ValueError, OSError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"gravado: {target.relative_to(REPO)} ({target.stat().st_size // 1024} KB)")
    print(f'em config/product_photos.py, HOSTED_PHOTOS: "{args.sku}": "{target.name}",')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
