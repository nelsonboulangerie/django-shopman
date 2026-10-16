"""Fotos de produto que já moram no host dedicado e substituem a de fora.

A foto de produto mora no host dedicado de imagens (``SHOPMAN_PRODUCT_IMAGE_BASE``,
hoje ``https://img.nelsonboulangerie.com.br/products``), que serve os arquivos de
``surfaces/storefront-nuxt/public/img/products/``. Foto fora dele reprova o
go-live (``catalog.product_image_host`` em ``scripts/check_release_readiness.py``).

Esta tabela diz, por SKU, qual arquivo daquela pasta é a foto do produto quando o
``seed`` ainda aponta para fora (o placeholder do Unsplash). Duas pontas a leem:

- o ``seed``: um banco novo já nasce com a foto no host dedicado;
- ``manage.py relocate_product_images``: leva o banco que já existe para o
  mesmo lugar, conferindo antes que o arquivo responde 200 no host.

Como uma foto entra aqui:

1. ``scripts/import_product_photo.py <SKU> <origem>`` grava o webp na pasta, na
   receita da casa (1200 px quadrado, q80, sem EXIF, nunca ampliando);
2. a linha ``"<SKU>": "<arquivo>"`` entra nesta tabela, no mesmo PR;
3. depois do deploy, ``relocate_product_images --apply`` no banco vivo.

O arquivo é imutável: o host serve com cache de um ano. Trocar a foto é trocar o
NOME do arquivo (``cap.v2.webp``), nunca sobrescrever.
"""

from __future__ import annotations

#: SKU → nome do arquivo em ``surfaces/storefront-nuxt/public/img/products/``.
HOSTED_PHOTOS: dict[str, str] = {}


def hosted_photo_url(sku: str, image_base: str) -> str | None:
    """A URL da foto do SKU no host dedicado, ou ``None`` se a tabela não a conhece."""
    filename = HOSTED_PHOTOS.get(sku)
    if not filename:
        return None
    return f"{image_base.rstrip('/')}/{filename}"
