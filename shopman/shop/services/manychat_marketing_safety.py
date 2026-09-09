"""Fail-closed boundary for unproven ManyChat Marketing flow semantics.

ManyChat custom fields are persistent subscriber state.  Shopman currently has
no vendor evidence that a later ``sendFlow`` snapshots those fields atomically,
so two campaigns for the same subscriber can interleave and render each other's
values.  G-H03 explicitly keeps real Marketing blocked until a controlled
sandbox proves isolation or the adapter is redesigned around an atomic payload.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.shop.services.marketing_contracts import MarketingContractError

BLOCK_CODE = "manychat_custom_fields_unverified"
MARKETING_FLOW_EVENTS = frozenset({
    "announcement_published",
    "production_ready",
    "stock_arrived",
})
_SANDBOX_MARKER_KEY = "__shopman_marketing_sandbox_probe__"
_SANDBOX_MARKER = object()


@dataclass(frozen=True, slots=True)
class ManyChatMarketingSafety:
    safe: bool
    state: str
    reason_code: str
    reason: str
    action: str


def safety_state() -> ManyChatMarketingSafety:
    """Return the approved negative guarantee until external evidence exists."""

    return ManyChatMarketingSafety(
        safe=False,
        state="blocked_unverified",
        reason_code=BLOCK_CODE,
        reason=(
            "O flow depende de campos persistentes cuja isolação entre campanhas "
            "concorrentes ainda não foi comprovada."
        ),
        action=(
            "Executar o ensaio sandbox G-H03 com o Platform Owner; até lá, nenhum "
            "envio real de Marketing por WhatsApp é permitido"
        ),
    )


def require_safe_delivery() -> None:
    state = safety_state()
    if not state.safe:
        raise MarketingContractError(
            code=state.reason_code,
            detail=f"{state.reason} {state.action}.",
            field_errors={"platforms.whatsapp": (state.action,)},
        )


def sandbox_probe_context(context: dict) -> dict:
    """Mark one server-authorized max-1 sandbox probe; marker never leaves process."""

    return dict(context) | {_SANDBOX_MARKER_KEY: _SANDBOX_MARKER}


def consume_sandbox_probe(context: dict) -> bool:
    """Remove and recognize the non-serializable in-process sandbox sentinel."""

    return context.pop(_SANDBOX_MARKER_KEY, None) is _SANDBOX_MARKER
