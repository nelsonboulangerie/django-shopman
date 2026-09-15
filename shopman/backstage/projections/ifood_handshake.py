"""Operator decisions for iFood negotiations; the provider remains authoritative."""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.urls import reverse

from shopman.shop.projections.types import Action
from shopman.shop.services import operator_orders


@dataclass(frozen=True)
class IFoodNegotiationProjection:
    id: str
    type: str
    action: str
    message: str
    expires_at: str
    timeout_action: str
    state: str
    can_respond: bool
    response_notice: str
    items: tuple[str, ...]
    evidence_urls: tuple[str, ...]
    accept_reasons: tuple[str, ...]
    reject_reasons: tuple[str, ...]
    alternatives_available: bool
    actions: tuple[Action, ...]


def negotiations(order, *, user=None) -> tuple[IFoodNegotiationProjection, ...]:
    from shopman.shop.services import ifood_handshake
    from shopman.shop.services.ifood_evidence import evidence_links

    if order.channel_ref != "ifood":
        return ()
    authorized = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))
    results = []
    for entry in ifood_handshake.projection(order):
        enabled = bool(entry.get("can_respond")) and authorized
        reason = str(entry.get("response_notice") or "") if authorized else "Identifique uma pessoa com permissão para gerenciar pedidos."
        actions = tuple(Action(
            ref=decision, kind="mutation", label=label, priority="danger" if decision == "accept" else "secondary",
            enabled=enabled, reason=reason if not enabled else "", method="POST", idempotency="required",
            payload_schema={"expected_actor_id": getattr(user, "pk", None), "base_revision": operator_orders.operational_revision(order), "dispute_id": str(entry["id"]), "decision": decision},
            confirmation={"description": "Esta resposta será enviada ao iFood e pode alterar o cancelamento ou reembolso do pedido."},
        ) for decision, label in (("accept", "Aceitar solicitação"), ("reject", "Rejeitar solicitação")))
        results.append(IFoodNegotiationProjection(
            **{key: str(entry.get(key) or "") for key in ("id", "type", "action", "message", "expires_at", "timeout_action", "state", "response_notice")},
            can_respond=enabled,
            items=tuple(str(item) for item in entry.get("items", [])),
            evidence_urls=tuple(
                reverse("api-backstage-order-ifood-handshake-evidence", args=[order.ref]) + "?" + urlencode({"dispute_id": entry["id"], "index": link["index"]})
                if link["protected"] else link["url"]
                for link in evidence_links(order, entry["id"])
            ),
            accept_reasons=tuple(str(value) for value in entry.get("accept_reasons", [])),
            reject_reasons=tuple(str(value) for value in entry.get("reject_reasons", [])),
            alternatives_available=bool(entry.get("alternatives_available")), actions=actions,
        ))
    return tuple(results)
