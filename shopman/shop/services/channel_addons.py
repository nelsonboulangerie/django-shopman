"""Complementos de um produto no catálogo do iFood: grava aqui, envia e confirma.

Cada gesto é tudo ou nada: a gravação local só fica quando o iFood confirma pela
leitura do item. Falhou o envio, a transação volta e o cadastro continua igual ao
que está no iFood.

Qual chamada cada gesto faz (checklist de homologação do Catalog, 17/11/2026):

- criar grupo, criar complemento, renomear e trocar foto → ``PUT /items`` (o item
  inteiro, com grupos, opções e produtos);
- preço do complemento → ``PATCH /options/price``;
- pausar e retomar → ``PATCH /options/status``.

A escrita passa pela mesma política do catálogo
(``SHOPMAN_IFOOD_CATALOG_WRITE_POLICY``): fora da loja de teste, nada sai.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from django.db import transaction

from shopman.shop.models import Channel, ChannelAddon, ChannelAddonGroup

IFOOD_CHANNEL = "ifood"
_CONFIRM_WAITS = (0.0, 1.0, 2.0, 3.0, 4.0)


class AddonError(ValueError):
    """Entrada inválida ou envio que o iFood não confirmou."""


class AddonRemoteError(AddonError):
    """O iFood recusou ou não confirmou; nada foi gravado aqui."""


@dataclass(frozen=True)
class AddonReceipt:
    """O que o iFood confirmou, para a tela mostrar."""

    message: str
    remote: dict


def _slug(name: str, taken: set[str]) -> str:
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:40] or "item"
    ref, n = base, 2
    while ref in taken:
        ref, n = f"{base}-{n}", n + 1
    return ref


def _name(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AddonError("Informe o nome.")
    value = " ".join(value.split())
    if len(value) > 128:
        raise AddonError("O nome passa de 128 caracteres.")
    return value


def _price_q(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10_000_00:
        raise AddonError("Informe um preço entre R$ 0,00 e R$ 10.000,00.")
    return value


def _channel(channel_ref: str) -> Channel:
    if channel_ref != IFOOD_CHANNEL:
        raise AddonError("Complementos existem só no catálogo do iFood.")
    channel = Channel.objects.filter(ref=channel_ref).first()
    if channel is None:
        raise AddonError("Canal não encontrado.")
    return channel


def _backend():
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    return IFoodCatalogProjection()


def _projected_item(sku: str, channel_ref: str):
    from shopman.shop.handlers.catalog_projection import _get_projected_item

    item = _get_projected_item(sku, channel_ref)
    if item is None:
        raise AddonError("Este produto não está no catálogo do iFood.")
    return item


def _raise_remote(result) -> None:
    if not result.success:
        raise AddonRemoteError("O iFood não confirmou: " + "; ".join(result.errors))


def _push_item(sku: str, channel_ref: str) -> None:
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogWriteBlocked

    try:
        result = _backend().project([_projected_item(sku, channel_ref)], channel=channel_ref)
    except IFoodCatalogWriteBlocked as exc:
        raise AddonRemoteError(str(exc)) from exc
    _raise_remote(result)


def _read_until(sku: str, channel_ref: str, accept) -> dict:
    """Lê o item no iFood até ``accept`` aceitar; o PUT é eventualmente consistente."""
    body: dict = {}
    for wait in _CONFIRM_WAITS:
        if wait:
            time.sleep(wait)
        body = _read_item(sku, channel_ref)
        if accept(body):
            return body
    raise AddonRemoteError("O iFood recebeu o envio, mas a leitura do item ainda não mostra a mudança.")


def _read_item(sku: str, channel_ref: str) -> dict:
    """Leitura do item no iFood; qualquer falha vira erro de envio, com a causa."""
    import requests

    from shopman.shop.adapters.catalog_projection_ifood import (
        IFoodCatalogWriteBlocked,
        IFoodConfirmationError,
        IFoodRateLimitError,
    )

    try:
        return _backend().read_item(sku, channel=channel_ref)
    except IFoodRateLimitError:
        raise
    except (IFoodCatalogWriteBlocked, IFoodConfirmationError) as exc:
        raise AddonRemoteError(str(exc)) from exc
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        if code == 404:
            raise AddonRemoteError("O item ainda não está no iFood. Publique o produto antes.") from exc
        raise AddonRemoteError(f"A leitura do item no iFood respondeu HTTP {code}.") from exc
    except requests.RequestException as exc:
        raise AddonRemoteError("Não foi possível ler o item no iFood.") from exc


def _ids(addon: ChannelAddon) -> dict[str, str]:
    from django.conf import settings

    from shopman.shop.adapters.catalog_projection_ifood import addon_identity

    merchant = str((getattr(settings, "SHOPMAN_IFOOD", {}) or {}).get("merchant_id") or "")
    group = addon.group
    return addon_identity(merchant, group.sku, group.ref, addon.ref)


def _group_id(group: ChannelAddonGroup) -> str:
    from django.conf import settings

    from shopman.shop.adapters.catalog_projection_ifood import addon_identity

    merchant = str((getattr(settings, "SHOPMAN_IFOOD", {}) or {}).get("merchant_id") or "")
    return addon_identity(merchant, group.sku, group.ref)["group_id"]


def _remote_product(body: dict, product_id: str) -> dict:
    return next((row for row in body.get("products") or [] if row.get("id") == product_id), {})


def _remote_option(body: dict, option_id: str) -> dict:
    return next((row for row in body.get("options") or [] if row.get("id") == option_id), {})


# ── Leitura ──────────────────────────────────────────────────────────────────


def groups_for(channel_ref: str, sku: str) -> list[ChannelAddonGroup]:
    return list(
        ChannelAddonGroup.objects.filter(channel__ref=channel_ref, sku=sku)
        .prefetch_related("addons")
        .order_by("index", "pk")
    )


# ── Gestos ───────────────────────────────────────────────────────────────────


def create_group(*, channel_ref: str, sku: str, name: str, min_choices: int = 0, max_choices: int = 1) -> AddonReceipt:
    channel = _channel(channel_ref)
    name = _name(name)
    for value in (min_choices, max_choices):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 99:
            raise AddonError("Mínimo e máximo de escolhas vão de 0 a 99.")
    if max_choices < 1 or min_choices > max_choices:
        raise AddonError("O máximo de escolhas é pelo menos 1 e não fica abaixo do mínimo.")
    _projected_item(sku, channel_ref)
    with transaction.atomic():
        siblings = ChannelAddonGroup.objects.select_for_update().filter(channel=channel, sku=sku)
        group = ChannelAddonGroup.objects.create(
            channel=channel,
            sku=sku,
            ref=_slug(name, set(siblings.values_list("ref", flat=True))),
            name=name,
            min_choices=min_choices,
            max_choices=max_choices,
            index=siblings.count(),
        )
        # Grupo sem opção não vai: o iFood exige ``optionIds``. Ele sobe com o
        # primeiro complemento; aqui só confirma que o item existe lá.
        body = _read_item(sku, channel_ref)
        if not body.get("item"):
            raise AddonRemoteError("O item ainda não está no iFood. Publique o produto antes.")
    return AddonReceipt(
        message=f"Grupo {group.name!r} criado. Ele aparece no iFood com o primeiro complemento.",
        remote={"group_id": _group_id(group)},
    )


def add_addon(*, group_id: int, name: str, price_q: int, image_url: str = "") -> AddonReceipt:
    name = _name(name)
    price_q = _price_q(price_q)
    image_url = str(image_url or "").strip()
    with transaction.atomic():
        group = ChannelAddonGroup.objects.select_for_update().select_related("channel").get(pk=group_id)
        taken = set(group.addons.values_list("ref", flat=True))
        addon = ChannelAddon.objects.create(
            group=group,
            ref=_slug(name, taken),
            name=name,
            price_q=price_q,
            image_url=image_url,
            index=len(taken),
        )
        _push_item(group.sku, group.channel.ref)
        ids = _ids(addon)
        value = round(price_q / 100, 2)
        body = _read_until(
            group.sku,
            group.channel.ref,
            lambda body: _remote_option(body, ids["option_id"]).get("price", {}).get("value") == value
            and _remote_product(body, ids["product_id"]).get("name") == name
            and (not image_url or bool(_remote_product(body, ids["product_id"]).get("imagePath"))),
        )
    return AddonReceipt(
        message=f"Complemento {name!r} confirmado no iFood.",
        remote={"option": _remote_option(body, ids["option_id"]), "product": _remote_product(body, ids["product_id"])},
    )


def edit_addon(*, addon_id: int, name: str | None = None, image_url: str | None = None) -> AddonReceipt:
    """Nome e foto: vão no ``PUT /items`` do item inteiro."""
    with transaction.atomic():
        addon = ChannelAddon.objects.select_for_update().select_related("group__channel").get(pk=addon_id)
        before_image = addon.image_url
        fields = []
        if name is not None:
            addon.name = _name(name)
            fields.append("name")
        if image_url is not None:
            image_url = str(image_url).strip()
            if not image_url:
                raise AddonError("Escolha uma foto.")
            addon.image_url = image_url
            fields.append("image_url")
        if not fields:
            raise AddonError("Nada para alterar.")
        addon.save(update_fields=[*fields, "updated_at"])
        group = addon.group
        ids = _ids(addon)
        remote_before = _remote_product(_read_item(group.sku, group.channel.ref), ids["product_id"])
        _push_item(group.sku, group.channel.ref)

        def accept(body):
            product = _remote_product(body, ids["product_id"])
            if product.get("name") != addon.name:
                return False
            if "image_url" in fields and addon.image_url != before_image:
                return bool(product.get("imagePath")) and product.get("imagePath") != remote_before.get("imagePath")
            return True

        body = _read_until(group.sku, group.channel.ref, accept)
    return AddonReceipt(
        message=f"Complemento {addon.name!r} atualizado e confirmado no iFood.",
        remote={"option": _remote_option(body, ids["option_id"]), "product": _remote_product(body, ids["product_id"])},
    )


def change_addon_price(*, addon_id: int, price_q: int) -> AddonReceipt:
    """Só o preço, por ``PATCH /options/price``."""
    price_q = _price_q(price_q)
    with transaction.atomic():
        addon = ChannelAddon.objects.select_for_update().select_related("group__channel").get(pk=addon_id)
        addon.price_q = price_q
        addon.save(update_fields=["price_q", "updated_at"])
        channel_ref = addon.group.channel.ref
        _raise_remote(_backend().update_addon_price(addon, channel=channel_ref))
        body = _read_item(addon.group.sku, channel_ref)
    ids = _ids(addon)
    return AddonReceipt(
        message=f"Preço de {addon.name!r} confirmado no iFood.",
        remote={"option": _remote_option(body, ids["option_id"])},
    )


def set_addon_active(*, addon_id: int, active: bool) -> AddonReceipt:
    """Pausar ou retomar, por ``PATCH /options/status``."""
    if not isinstance(active, bool):
        raise AddonError("Escolha pausar ou retomar.")
    with transaction.atomic():
        addon = ChannelAddon.objects.select_for_update().select_related("group__channel").get(pk=addon_id)
        addon.is_active = active
        addon.save(update_fields=["is_active", "updated_at"])
        channel_ref = addon.group.channel.ref
        _raise_remote(_backend().set_addon_status(addon, channel=channel_ref))
        body = _read_item(addon.group.sku, channel_ref)
    ids = _ids(addon)
    verb = "retomado" if active else "pausado"
    return AddonReceipt(
        message=f"{addon.name!r} {verb}, confirmado no iFood.",
        remote={"option": _remote_option(body, ids["option_id"])},
    )


__all__ = [
    "AddonError",
    "AddonReceipt",
    "AddonRemoteError",
    "add_addon",
    "change_addon_price",
    "create_group",
    "edit_addon",
    "groups_for",
    "set_addon_active",
]
