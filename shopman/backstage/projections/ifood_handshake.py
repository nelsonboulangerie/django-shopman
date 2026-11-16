"""Operator decisions for iFood negotiations; the provider remains authoritative."""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.urls import reverse
from shopman.utils.monetary import format_money

from shopman.shop.projections.types import Action
from shopman.shop.services import operator_orders

ALTERNATIVE_LABELS = {
    "REFUND": "Reembolsar parte do valor",
    "BENEFIT": "Dar um benefício ao cliente",
    "ADDITIONAL_TIME": "Pedir mais tempo de entrega",
}

# Motivos do tempo adicional: o iFood manda a lista em cada disputa. Os conhecidos
# ganham texto; o desconhecido aparece com o código, para não virar outro motivo.
ADDITIONAL_TIME_REASON_LABELS = {
    "HIGH_STORE_DEMAND": "Alta demanda na loja",
    "HIGH_DEMAND": "Alta demanda na loja",
    "PRODUCT_PREPARATION": "Preparo do produto",
    "DRIVER_DELAY": "Atraso do entregador",
    "TRAFFIC": "Trânsito intenso",
    "WEATHER": "Condições do tempo",
    "SYSTEM_ISSUE": "Problema no sistema",
    "INVENTORY_CHECK": "Conferência de estoque",
    "UNKNOWN_ISSUE": "Problema não identificado",
}


@dataclass(frozen=True)
class IFoodNegotiationChoice:
    value: str
    label: str


@dataclass(frozen=True)
class IFoodNegotiationAlternative:
    """Uma contraproposta que o operador pode enviar.

    Valor (``REFUND``/``BENEFIT``): ``max_amount_q`` > 0, sem minutos nem motivos.
    Tempo (``ADDITIONAL_TIME``): ``minutes_options`` e ``reason_options``, teto 0."""

    id: str
    type: str
    label: str
    max_amount_q: int
    max_amount_display: str
    minutes_options: tuple[int, ...]
    reason_options: tuple[IFoodNegotiationChoice, ...]


def _alternative(row) -> IFoodNegotiationAlternative:
    max_q = int(row.get("max_amount_q") or 0)
    return IFoodNegotiationAlternative(
        id=row["id"],
        type=row["type"],
        label=ALTERNATIVE_LABELS[row["type"]],
        max_amount_q=max_q,
        max_amount_display=f"R$ {format_money(max_q)}" if max_q else "",
        minutes_options=tuple(row.get("minutes") or ()),
        reason_options=tuple(
            IFoodNegotiationChoice(value=reason, label=ADDITIONAL_TIME_REASON_LABELS.get(reason, f"Motivo do iFood: {reason}"))
            for reason in row.get("reasons") or ()
        ),
    )


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
    alternatives: tuple[IFoodNegotiationAlternative, ...]
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
        alternatives = tuple(_alternative(row) for row in entry.get("alternatives", []))
        decisions = [
            ("accept", "Aceitar solicitação", "Esta resposta será enviada ao iFood e pode alterar o cancelamento ou reembolso do pedido."),
            ("reject", "Rejeitar solicitação", "Esta resposta será enviada ao iFood e pode alterar o cancelamento ou reembolso do pedido."),
        ]
        # Contraproposta só aparece quando o iFood ofereceu uma que o Gestor sabe enviar.
        if alternatives:
            decisions.append(("alternative", "Fazer contraproposta",
                              "Esta contraproposta será enviada ao iFood. O cliente decide se aceita, e o resultado chega pelo iFood."))
        actions = tuple(Action(
            ref=decision, kind="mutation", label=label, priority="danger" if decision == "accept" else "secondary",
            enabled=enabled, reason=reason if not enabled else "", method="POST", idempotency="required",
            payload_schema={"expected_actor_id": getattr(user, "pk", None), "base_revision": operator_orders.operational_revision(order), "dispute_id": str(entry["id"]), "decision": decision},
            confirmation={"description": description},
        ) for decision, label, description in decisions)
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
            alternatives_available=bool(entry.get("alternatives_available")), alternatives=alternatives, actions=actions,
        ))
    return tuple(results)
