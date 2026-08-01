"""Storefront status & availability presentation.

Resolves the semantic enums the data Projection carries — order status, payment
method, ``Availability``, status ``Tone`` — into the display strings and
Tailwind colour tokens the storefront templates and REST surface consume.

Copy is authoritative in the orchestrator (``OMOTENASHI_DEFAULTS``); this module
only *places* it via :func:`build_copy`, passing the raw key as a last-resort
fallback. The tone→class map is the storefront's own design-token translation —
rule R-B keeps those classes out of ``shop/projections`` (the data read-side).
"""

from __future__ import annotations

from shopman.shop.projections.copy import build_copy
from shopman.shop.projections.types import ORDER_STATUS_TONES, Availability, Tone

# Tone → storefront design-token classes. Owned here because the concrete
# Tailwind tokens are this surface's render concern, not shared data.
_TONE_CLASSES: dict[Tone, str] = {
    Tone.INFO: "bg-info/10 text-info border border-info/20",
    Tone.WARNING: "bg-warning/10 text-warning border border-warning/20",
    Tone.SUCCESS: "bg-success/10 text-success border border-success/20",
    Tone.DANGER: "bg-danger/10 text-danger border border-danger/20",
    Tone.NEUTRAL: "bg-surface-alt text-on-surface/60 border border-outline",
}

# Fallback class for a status with no known tone (also the NEUTRAL token).
DEFAULT_STATUS_COLOR = "bg-surface-alt text-on-surface/60 border border-outline"


def status_color(status: str, fallback_status: str | None = None) -> str:
    """Map an order status to its storefront colour-token classes.

    ``status`` may be the semantic ``display_status_key`` (e.g. ``ready_pickup``,
    ``payment_expired``); when it has no tone of its own, ``fallback_status`` (the
    raw ``order.status``) resolves the accent. This keeps the panel colour
    consistent with the label, which is also resolved from the display key first
    and the raw status second.
    """
    tone = ORDER_STATUS_TONES.get(status)
    if tone is None and fallback_status:
        tone = ORDER_STATUS_TONES.get(fallback_status)
    return _TONE_CLASSES[tone] if tone else DEFAULT_STATUS_COLOR


def status_tone(status: str | None) -> str:
    """Map an order status to its semantic tone keyword (surface-agnostic).

    The data read-side carries *meaning* (the ``Tone``); each surface owns the
    tone→class translation. Surfaces that render their own classes (the Nuxt
    storefront) consume this keyword instead of the legacy class string.
    """
    tone = ORDER_STATUS_TONES.get(status or "")
    return tone.value if tone else Tone.INFO.value


# O cliente não lê o NOME DO ESTADO, lê a situação dele. Onde os dois divergem,
# a palavra do cliente vence — `ORDER_STATUS_*` é vocabulário do sistema (o card
# do operador diz "Novo"; o cliente não precisa saber que o pedido é novo, ele
# acabou de fazer — precisa saber que a loja ainda não olhou).
#
# Sem isto o cliente vazava para o vocabulário do sistema em dois caminhos que
# não passam pelo mapa semântico do acompanhamento: o pedido em DINHEIRO parado
# em `new` (nenhuma regra de pagamento o mapeia) e a lista "Meus pedidos".
_CUSTOMER_STATUS_COPY: dict[str, tuple[str, str]] = {
    "new": ("TRACKING_STATUS_WAITING_STORE_CONFIRMATION", "Aguardando a loja"),
}


def order_status_label(status: str | None, fallback: str | None = None) -> str:
    """Resolve an order-status key to its customer-facing label.

    ``fallback`` defaults to the raw status; pass ``""`` to detect a miss
    (the catalog returns the fallback when no copy is seeded for the key).
    """
    fb = (status or "") if fallback is None else fallback
    if not status:
        return fb
    proprio = _CUSTOMER_STATUS_COPY.get(status)
    if proprio:
        return build_copy("TRACKING").title(proprio[0], proprio[1])
    return build_copy("ORDER_STATUS").title(f"ORDER_STATUS_{status.upper()}", fb)


def payment_method_label(method: str) -> str:
    """Resolve a payment-method ref to its display label."""
    return build_copy("PAYMENT_METHOD").title(f"PAYMENT_METHOD_{method.upper()}", method)


def availability_label(availability: Availability) -> str:
    """Resolve an :class:`Availability` state to its display label."""
    return build_copy("AVAILABILITY").title(
        f"AVAILABILITY_{availability.upper()}", str(availability)
    )
