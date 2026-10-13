"""Leva as fotos de produto do banco para o host dedicado de imagens.

Usage::

    python manage.py relocate_product_images            # relatório (não escreve)
    python manage.py relocate_product_images --apply    # grava

**Por que existe.** A foto de produto mora no host dedicado
(``SHOPMAN_PRODUCT_IMAGE_BASE``, hoje ``https://img.nelsonboulangerie.com.br/products``):
ela quebrou duas vezes por morar no host de um site que mudou de papel (``menu.``
em 01/09, ``www.`` em 17/09/2026). Foto fora dele reprova o go-live
(``catalog.product_image_host``). Este comando é o conserto do dado: o mesmo
critério do gate, com o destino de cada foto.

**De onde vem o destino**, nesta ordem:

1. ``config/product_photos.py`` (``HOSTED_PHOTOS``): o arquivo que a casa
   escolheu para o SKU — a foto da casa ou o placeholder trazido para o host;
2. foto que já é da casa num host de site (caminho ``.../img/products/<arquivo>``
   em ``www.``, ``menu.`` ou qualquer outro): o mesmo arquivo no host dedicado.
   Vale para a foto principal e para a galeria.

O que não tem destino fica como está e sai no relatório, com o SKU: não existe
foto da casa para ele, e apagar a foto tira o produto dos canais remotos
(``sells_remotely``). Isso é decisão do dono, não do comando.

**Antes de gravar**, cada destino é conferido no host (HEAD, 200, ``image/*``).
Destino que não responde não é gravado: trocar uma foto que aparece por um
link quebrado é pior que deixar a de fora. Rodar de novo não muda nada
(idempotente): o que já está no host dedicado é deixado em paz.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from config.product_photos import hosted_photo_url

SITE_PHOTO_MARKER = "/img/products/"


@dataclass
class Relocation:
    sku: str
    product_id: int
    image_from: str = ""
    image_to: str = ""
    gallery_from: list[str] = field(default_factory=list)
    gallery_to: list[str] = field(default_factory=list)

    @property
    def targets(self) -> set[str]:
        changed_gallery = {new for old, new in zip(self.gallery_from, self.gallery_to, strict=True) if old != new}
        return ({self.image_to} if self.image_to else set()) | changed_gallery


@dataclass
class Plan:
    media_host: str
    relocations: list[Relocation] = field(default_factory=list)
    #: SKU → URLs fora do host dedicado que não têm destino.
    homeless: dict[str, list[str]] = field(default_factory=dict)
    published: set[str] = field(default_factory=set)


def _host(url: str) -> str:
    return (urlparse(str(url or "")).hostname or "").lower()


def _site_photo_target(url: str, image_base: str) -> str | None:
    """Foto da casa servida por um host de site: o mesmo arquivo no host dedicado."""
    path = urlparse(url).path
    if SITE_PHOTO_MARKER not in path:
        return None
    filename = path.rsplit("/", 1)[-1]
    return f"{image_base}/{filename}" if filename else None


def build_plan(image_base: str) -> Plan:
    from shopman.offerman.models import Product

    image_base = image_base.rstrip("/")
    media_host = _host(image_base)
    plan = Plan(media_host=media_host)

    rows = Product.objects.order_by("sku").values_list("pk", "sku", "image_url", "metadata", "is_published")
    for pk, sku, image_url, metadata, is_published in rows:
        image_url = str(image_url or "")
        relocation = Relocation(sku=sku, product_id=pk)
        homeless: list[str] = []

        hosted = hosted_photo_url(sku, image_base)
        if hosted and image_url != hosted:
            relocation.image_from, relocation.image_to = image_url, hosted
        elif image_url and _host(image_url) != media_host:
            target = _site_photo_target(image_url, image_base)
            if target:
                relocation.image_from, relocation.image_to = image_url, target
            else:
                homeless.append(image_url)

        gallery = (metadata or {}).get("gallery") if isinstance(metadata, dict) else None
        if isinstance(gallery, list):
            new_gallery = []
            for entry in gallery:
                url = str(entry or "")
                if url and _host(url) != media_host:
                    target = _site_photo_target(url, image_base)
                    if target:
                        new_gallery.append(target)
                        continue
                    homeless.append(url)
                new_gallery.append(entry)
            if new_gallery != gallery:
                relocation.gallery_from, relocation.gallery_to = list(gallery), new_gallery

        if relocation.image_to or relocation.gallery_to:
            plan.relocations.append(relocation)
        if homeless:
            plan.homeless[sku] = homeless
        if is_published:
            plan.published.add(sku)
    return plan


def probe_image(url: str, *, timeout: float = 10.0) -> str | None:
    """``None`` se o host serve a imagem; senão, o motivo."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "shopman-relocate-product-images"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — URL do host dedicado
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"sem resposta ({exc})"
    if status != 200:
        return f"HTTP {status}"
    if not content_type.startswith("image/"):
        return f"não é imagem ({content_type or 'sem Content-Type'})"
    return None


def apply_plan(plan: Plan, relocations: list[Relocation]) -> None:
    from shopman.offerman.models import Product

    with transaction.atomic():
        for relocation in relocations:
            product = Product.objects.select_for_update().get(pk=relocation.product_id)
            update_fields = []
            if relocation.image_to:
                product.image_url = relocation.image_to
                update_fields.append("image_url")
            if relocation.gallery_to:
                metadata = dict(product.metadata or {})
                metadata["gallery"] = relocation.gallery_to
                product.metadata = metadata
                update_fields.append("metadata")
            product.save(update_fields=[*update_fields, "updated_at"])


class Command(BaseCommand):
    help = "Leva as fotos de produto para o host dedicado de imagens (relatório sem --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Grava. Sem esta opção o comando só relata.")
        parser.add_argument(
            "--image-base",
            default=None,
            help="Base do host dedicado. Padrão: a env SHOPMAN_PRODUCT_IMAGE_BASE (a mesma do gate).",
        )

    def handle(self, *args, **options):
        image_base = (options["image_base"] or os.environ.get("SHOPMAN_PRODUCT_IMAGE_BASE", "")).strip()
        if not _host(image_base):
            raise CommandError(
                "SHOPMAN_PRODUCT_IMAGE_BASE não está configurada (nem --image-base): não há host dedicado de fotos."
            )

        plan = build_plan(image_base)
        out = self.stdout

        unreachable: dict[str, str] = {}
        for target in sorted({t for r in plan.relocations for t in r.targets}):
            reason = probe_image(target)
            if reason:
                unreachable[target] = reason
        ready = [r for r in plan.relocations if not (r.targets & unreachable.keys())]
        blocked = [r for r in plan.relocations if r.targets & unreachable.keys()]

        out.write(f"Host dedicado: {plan.media_host}")
        if ready:
            out.write(f"\nVão para o host dedicado ({len(ready)}):")
            for r in ready:
                if r.image_to:
                    out.write(f"  {r.sku}: {r.image_from or '(sem foto)'} → {r.image_to}")
                for old, new in zip(r.gallery_from, r.gallery_to, strict=True):
                    if old != new:
                        out.write(f"  {r.sku} (galeria): {old} → {new}")
        if blocked:
            out.write(self.style.WARNING(f"\nDestino não responde, ficam como estão ({len(blocked)}):"))
            for r in blocked:
                reasons = "; ".join(f"{t} {unreachable[t]}" for t in sorted(r.targets & unreachable.keys()))
                out.write(f"  {r.sku}: {reasons}")
        if plan.homeless:
            published = sorted(set(plan.homeless) & plan.published)
            out.write(
                self.style.WARNING(
                    f"\nSem foto no host dedicado ({len(plan.homeless)} produtos, {len(published)} publicados). "
                    "Destino: foto da casa ou placeholder trazido para o host, em config/product_photos.py."
                )
            )
            for sku, urls in plan.homeless.items():
                mark = " [publicado]" if sku in plan.published else ""
                hosts = ", ".join(sorted({_host(u) for u in urls}))
                out.write(f"  {sku}{mark}: {hosts}")

        if not ready:
            out.write("\nNada a gravar.")
            return
        if not options["apply"]:
            out.write(f"\nMudaria {len(ready)} produto(s). Rode com --apply para gravar.")
            return
        apply_plan(plan, ready)
        out.write(self.style.SUCCESS(f"\nGravado: {len(ready)} produto(s) no host dedicado."))
