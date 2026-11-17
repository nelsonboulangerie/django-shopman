"""Complementos do catálogo do iFood no Gestor: ler e mudar, com confirmação remota.

Cada mudança passa pela intenção recuperável do Gestor (``Idempotency-Key`` e quem
a tela leu) e pela revisão do cadastro de complementos do produto: se outra pessoa
mudou o mesmo produto, a gravação responde 409 e a tela relê.
"""

from __future__ import annotations

import hashlib
import json

from rest_framework.response import Response

from shopman.backstage.api.catalog_bindings import _Base, _error
from shopman.backstage.api.projections import read_data
from shopman.backstage.services import catalog_bindings as binding_service
from shopman.shop.services import channel_addons as service

_ACTIONS = {"create_group", "add", "edit", "price", "status"}


def _revision(groups) -> str:
    state = [
        [g.pk, g.name, g.min_choices, g.max_choices, g.is_active,
         [[a.pk, a.name, a.price_q, a.image_url, a.is_active] for a in g.addons.all()]]
        for g in groups
    ]
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def _products(ref: str) -> list[dict]:
    from shopman.offerman.service import CatalogService

    return [
        {"sku": item.sku, "name": item.name}
        for item in sorted(CatalogService.get_projection_items(ref), key=lambda item: item.name.lower())
    ]


class ChannelAddonsView(_Base):
    operation = "catalog.addons.change"

    def get(self, request, ref):
        if request.query_params.get("idempotency_key"):
            return super().get(request, ref)
        if ref != service.IFOOD_CHANNEL:
            return Response(_error("Complementos existem só no catálogo do iFood."), status=404)
        sku = str(request.query_params.get("sku") or "").strip()
        groups = service.groups_for(ref, sku) if sku else []
        actor_id = request.user.pk if request.user.has_perm("shop.manage_catalog") else None
        return Response(read_data(addons={
            "channel_ref": ref,
            "sku": sku,
            "products": _products(ref),
            "groups": [
                {
                    "id": group.pk,
                    "name": group.name,
                    "min_choices": group.min_choices,
                    "max_choices": group.max_choices,
                    "is_active": group.is_active,
                    "addons": [
                        {
                            "id": addon.pk,
                            "name": addon.name,
                            "price_q": addon.price_q,
                            "image_url": addon.image_url,
                            "is_active": addon.is_active,
                        }
                        for addon in sorted(group.addons.all(), key=lambda a: (a.index, a.pk))
                    ],
                }
                for group in groups
            ],
            "action": {
                "ref": "catalog.addons.change",
                "kind": "mutation",
                "label": "Alterar complementos",
                "enabled": bool(sku) and actor_id is not None,
                "reason": "" if sku else "Escolha um produto.",
                "href": f"/api/v1/backstage/catalog/channels/{ref}/addons/",
                "method": "POST",
                "idempotency": "required",
                "payload_schema": {
                    "expected_actor_id": actor_id,
                    "sku": sku,
                    "base_revision": _revision(groups) if sku else "",
                },
            },
        }))

    def post(self, request, ref):
        data = request.data if isinstance(request.data, dict) else None
        if data is None:
            return Response(_error("Informe um objeto JSON."), status=400)
        action, sku, base = data.get("action"), data.get("sku"), data.get("base_revision")
        if action not in _ACTIONS:
            return Response(_error("Ação de complemento desconhecida.", "action"), status=400)
        if not isinstance(sku, str) or not sku.strip() or len(sku) > 100:
            return Response(_error("Escolha um produto.", "sku"), status=400)
        if not isinstance(base, str) or len(base) != 64:
            return Response(_error("Atualize a tela antes de gravar.", "base_revision"), status=400)
        sku = sku.strip()

        def owned(model, key):
            # O alvo tem de ser deste produto neste canal; id de outro produto é 400.
            value = data.get(key)
            if isinstance(value, bool) or not isinstance(value, int):
                raise binding_service.CatalogBindingError("Escolha um item válido.")
            lookup = {"pk": value, "channel__ref": ref, "sku": sku} if key == "group_id" else {
                "pk": value, "group__channel__ref": ref, "group__sku": sku}
            if not model.objects.filter(**lookup).exists():
                raise binding_service.CatalogBindingError("Este item não é deste produto.")
            return value

        def execute():
            from shopman.shop.models import ChannelAddon, ChannelAddonGroup

            if _revision(service.groups_for(ref, sku)) != base:
                raise binding_service.CatalogBindingConflict(
                    "Os complementos deste produto mudaram. A tela foi atualizada; confira e repita."
                )
            try:
                if action == "create_group":
                    receipt = service.create_group(
                        channel_ref=ref, sku=sku, name=data.get("name"),
                        min_choices=data.get("min_choices", 0), max_choices=data.get("max_choices", 1),
                    )
                elif action == "add":
                    receipt = service.add_addon(
                        group_id=owned(ChannelAddonGroup, "group_id"), name=data.get("name"),
                        price_q=data.get("price_q"), image_url=data.get("image_url") or "",
                    )
                elif action == "edit":
                    receipt = service.edit_addon(
                        addon_id=owned(ChannelAddon, "addon_id"),
                        name=data.get("name"), image_url=data.get("image_url"),
                    )
                elif action == "price":
                    receipt = service.change_addon_price(
                        addon_id=owned(ChannelAddon, "addon_id"), price_q=data.get("price_q"),
                    )
                else:
                    receipt = service.set_addon_active(
                        addon_id=owned(ChannelAddon, "addon_id"), active=data.get("active"),
                    )
            except service.AddonError as exc:
                raise binding_service.CatalogBindingError(str(exc)) from exc
            return {"action": action, "message": receipt.message, "remote": receipt.remote}

        inputs = {key: data.get(key) for key in (
            "action", "sku", "base_revision", "group_id", "addon_id", "name",
            "min_choices", "max_choices", "price_q", "image_url", "active")}
        return self.mutate(request, ref, inputs, execute)
