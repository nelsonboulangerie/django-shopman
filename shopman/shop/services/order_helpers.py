"""
Shared helpers for reading canonical order data fields.

These helpers centralise fallback logic for fields that were renamed
during the session→order data schema evolution.
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone


def get_fulfillment_type(order) -> str:
    """Return the order's fulfillment type.

    Uses the canonical ``fulfillment_type`` key with a fallback to the
    legacy ``delivery_method`` key so both old and new orders work.

    Returns an empty string when neither key is present.
    """
    return (
        (order.data or {}).get("fulfillment_type")
        or (order.data or {}).get("delivery_method", "")
    )


def delivery_eta_minutes(shop, order_data: dict) -> float:
    """Minutos estimados de entrega a partir da SAÍDA.

    Percurso (distância ÷ velocidade urbana efetiva) + folga fixa (saída,
    trânsito, achar o endereço, handoff). Couriers terceirizados/sem rastreio,
    então é estimativa honesta por configuração. Calibrável em
    ``Shop.defaults["delivery"]``: ``avg_speed_kmh`` (18), ``handoff_buffer_minutes``
    (12), ``estimated_minutes`` (40 — fallback quando não há distância).
    """
    cfg = (getattr(shop, "defaults", None) or {}).get("delivery") or {}
    distance_km = (order_data or {}).get("delivery_distance_km")
    if distance_km:
        speed = float(cfg.get("avg_speed_kmh") or 18)
        buffer_minutes = float(cfg.get("handoff_buffer_minutes") or 12)
        if speed > 0:
            return buffer_minutes + (float(distance_km) / speed) * 60.0
    return float(cfg.get("estimated_minutes") or 40)


def delivery_auto_complete_grace_minutes(shop) -> int:
    """Folga após o ETA antes de auto-concluir um pedido em entrega (rede de
    segurança se nem cliente nem operador fecharem). Calibrável em
    ``Shop.defaults["delivery"]["auto_complete_grace_minutes"]`` (default 30).
    ``0`` ou negativo DESLIGA a auto-conclusão."""
    cfg = (getattr(shop, "defaults", None) or {}).get("delivery") or {}
    raw = cfg.get("auto_complete_grace_minutes")
    return int(raw) if raw is not None else 30


def parse_commitment_date(value) -> date | None:
    """Parse an ISO delivery date into a ``date`` object."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def get_commitment_date(source) -> date | None:
    """Return the committed fulfillment date from an order/session/data dict."""
    if source is None:
        return None

    if isinstance(source, dict):
        data = source
    else:
        data = getattr(source, "data", None) or {}

    return parse_commitment_date(data.get("delivery_date"))


def customer_holds_the_goods(order) -> bool:
    """Venda de balcão presencial: a mercadoria já está na mão do cliente?

    É a pergunta que decide duas coisas, e por isso tem UMA resposta: se a
    venda fecha no ato (``lifecycle`` — ``system:counter_handoff``) e se o pão
    de prateleira vira ticket de separação (``kds`` — ``prep_only``). Enquanto
    cada um respondia por conta própria, uma regra nova entrava num e faltava
    no outro.

    Sim quando: PDV, retirada, sem data futura — e pagamento que NÃO é link.
    O link é o pedido REMOTO anotado no balcão: o cliente não está na loja,
    paga depois pelo celular e vem buscar. A sacola não está na mão dele; há
    trajeto pela frente por definição. Sem esta linha a venda de link fechava
    COMPLETED sem um centavo capturado, e o vencimento do link não alcançava
    mais o pedido. Encomenda agendada e entrega ficam de fora pelo mesmo
    motivo: têm trabalho e trajeto pela frente, e a esteira existe para elas.
    """
    data = order.data or {}
    if data.get("origin_channel") != "pos":
        return False
    if (data.get("fulfillment_type") or "pickup") != "pickup":
        return False
    payment = data.get("payment") or {}
    if str(payment.get("method") or "").strip().lower() == "link":
        return False
    commitment = get_commitment_date(order)
    return not (commitment and commitment > timezone.localdate())
