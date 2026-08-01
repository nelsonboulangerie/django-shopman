"""Conversational projection for WhatsApp/ManyChat and other chat surfaces.

The projection in this module is a compact view over canonical tracking,
payment, and channel policy resolution. It intentionally does not define order
status, payment state, pricing, stock, or availability rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shopman.shop.projections import order_tracking
from shopman.shop.projections.channel_policy import resolve_channel_policy
from shopman.shop.projections.interaction_context import InteractionContext
from shopman.shop.projections.types import Action

# Ações em que a bola é do cliente pagar. Depois da fusão (PAYMENT-TRACKING-MERGE)
# elas vivem na PRÓPRIA promessa do acompanhamento — não há mais projeção de
# pagamento à parte.
_PAYMENT_ACTIONS = {"copy_pix", "pay_card", "retry_payment"}


@dataclass(frozen=True)
class RemoteConversationProjection:
    """Compact customer-facing contract for conversational surfaces."""

    order_ref: str
    order_status: str
    channel_ref: str
    source_projection: str
    state: str
    title: str
    message: str
    tone: str
    actions: tuple[Action, ...]
    deadline_at: str | None
    items_summary: tuple[str, ...]
    total_display: str
    tracking_url: str
    payment_url: str | None
    supports_access_link: bool
    requires_payment_gate: bool


def build_order_conversation(
    order: Any,
    *,
    channel_ref: str | None = None,
    is_debug: bool = False,
) -> RemoteConversationProjection:
    """Build a conversation projection from canonical order projections."""

    interaction = InteractionContext.from_order(
        order,
        surface_ref="manychat",
        channel_ref=channel_ref,
    )
    resolved_channel_ref = interaction.channel_ref or "web"
    policy = resolve_channel_policy(resolved_channel_ref)
    tracking = order_tracking.build_tracking(order, is_debug=is_debug)
    promise = tracking.promise
    # Uma verdade: o pagamento é um degrau do próprio acompanhamento. Quando a
    # bola é do cliente pagar, a "fonte" continua a se chamar payment (para a
    # superfície conversacional saber destacar), mas o link é o do acompanhamento.
    has_payment_action = _has_payment_action(promise)
    source_projection = "payment" if has_payment_action else "tracking"
    tracking_url = f"/pedido/{order.ref}/"
    payment_url = tracking_url if has_payment_action else None
    tracking_actions = _actions(getattr(tracking, "actions", ()))

    return RemoteConversationProjection(
        order_ref=str(getattr(tracking, "order_ref", getattr(order, "ref", ""))),
        order_status=str(getattr(order, "status", "")),
        channel_ref=resolved_channel_ref,
        source_projection=source_projection,
        state=str(getattr(promise, "state", "")),
        title=str(getattr(promise, "title", "")),
        message=str(getattr(promise, "message", "")),
        tone=str(getattr(promise, "tone", "info") or "info"),
        actions=_conversation_actions(
            promise,
            tracking_actions=tracking_actions,
            channel_can_cancel=bool(getattr(policy, "can_cancel", False)),
            channel_can_rate=bool(getattr(policy, "can_rate", False)),
        ),
        deadline_at=getattr(promise, "deadline_at", None),
        items_summary=_items_summary(getattr(tracking, "items", ())),
        total_display=str(getattr(tracking, "total_display", "")),
        tracking_url=tracking_url,
        payment_url=payment_url,
        supports_access_link=policy.supports_access_link,
        requires_payment_gate=policy.requires_payment_gate,
    )


def _promise_actions(promise: Any) -> tuple[Action, ...]:
    return _actions(getattr(promise, "actions", ()))


def _actions(actions: Any) -> tuple[Action, ...]:
    return tuple(action for action in (actions or ()) if isinstance(action, Action))


def _conversation_actions(
    promise: Any,
    *,
    tracking_actions: tuple[Action, ...],
    channel_can_cancel: bool,
    channel_can_rate: bool,
) -> tuple[Action, ...]:
    allowed_tracking_refs = set()
    if channel_can_cancel:
        allowed_tracking_refs.add("cancel_order")
    if channel_can_rate:
        allowed_tracking_refs.add("rate_order")

    actions = [
        action
        for action in _promise_actions(promise)
        if action.enabled
    ]
    actions.extend(
        action
        for action in tracking_actions
        if action.enabled and action.ref in allowed_tracking_refs
    )
    return _dedupe_actions(actions)


def _dedupe_actions(actions: list[Action]) -> tuple[Action, ...]:
    seen: set[str] = set()
    deduped: list[Action] = []
    for action in actions:
        if action.ref in seen:
            continue
        seen.add(action.ref)
        deduped.append(action)
    return tuple(deduped)


def _has_payment_action(promise: Any) -> bool:
    return any(action.enabled and action.ref in _PAYMENT_ACTIONS for action in _promise_actions(promise))


def _items_summary(items: Any) -> tuple[str, ...]:
    item_tuple = tuple(items)
    rows = []
    for item in item_tuple[:5]:
        qty = getattr(item, "qty", "")
        name = getattr(item, "name", "")
        if qty and name:
            rows.append(f"{qty}x {name}")
        elif name:
            rows.append(str(name))
    remaining = max(len(item_tuple) - 5, 0)
    if remaining:
        rows.append(f"+{remaining} itens")
    return tuple(rows)
