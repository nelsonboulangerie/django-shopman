"""iFood order status callbacks (WP-4) — push our lifecycle back to iFood.

The merchant must tell iFood how an order progresses. Verified live (routes
exist; a fake id returns ``404 OrderNotFound``):

- ``POST /order/v1.0/orders/{id}/confirm``          → accept the order.
- ``POST /order/v1.0/orders/{id}/startPreparation`` → preparation began.
- ``POST /order/v1.0/orders/{id}/readyToPickup``    → order is ready.
- ``POST /order/v1.0/orders/{id}/dispatch``         → order left for delivery.
- ``POST /order/v1.0/orders/{id}/requestCancellation`` → ask iFood to cancel.

Internal ``Order.Status`` → iFood action:

    CONFIRMED  → confirm
    PREPARING  → startPreparation
    READY      → readyToPickup (todo pedido: TAKEOUT, DINE_IN e DELIVERY)
    DISPATCHED → dispatch (entrega da loja — só ``deliveredBy: MERCHANT``)
    CANCELLED  → requestCancellation

``requestCancellation`` requires a valid ``cancellationCode`` and ``reason``.
A successful request is pending until the CAN event confirms cancellation.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from shopman.shop.services import ifood_auth

logger = logging.getLogger(__name__)


class IFoodCallbackError(Exception):
    """Safe provider failure, classified for durable retries."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


# Internal status → iFood order-action path segment.
#
# ``startPreparation`` é o único passo OPCIONAL do ciclo de vida FOOD — o
# workflow oficial lista "PREPARATION_STARTED — Preparo iniciado (opcional)" e
# os critérios de homologação não o exigem (só ``readyToPickup`` e
# ``dispatch``). Mesmo assim ele entra, por três razões medidas na
# documentação oficial
# (https://developer.ifood.com.br/pt-BR/docs/food/guides/modules/order/workflow):
#
# 1. Está no checklist de implementação deles ("Iniciando preparação") e no
#    diagrama de sequência do passo 9 ("5- Start Preparation").
# 2. O evento que ele gera — ``SEPARATION_STARTED`` / ``PREPARATION_STARTED`` —
#    é informativo dos dois lados ("Ação necessária: Nenhuma"), então avisar não
#    reabre nada nem muda o SLA. O único SLA documentado é o de CONFIRMAÇÃO (8
#    minutos), que não depende deste envio.
# 3. Sem ele o cliente vê o pedido parado em "confirmado" enquanto a cozinha já
#    está trabalhando: o iFood só sabe o que a loja conta.
#
# ⚠️ Pedido AGENDADO: a documentação manda respeitar ``preparationStartDateTime``.
# Quem garante isso não é este mapa e sim o portão local — ``operator_orders``
# recusa a transição para ``preparing`` enquanto ``ifood_schedule.block_reason``
# devolver motivo. O envio pega carona na transição, então nasce no horário.
STATUS_ACTION = {
    "accepted": "confirm",
    "preparing": "startPreparation",
    "ready": "readyToPickup",
    "dispatched": "dispatch",
    "cancelled": "requestCancellation",
}

#: Motivo escolhido no Gestor (diálogo de cancelamento) → cancellationCode do
#: iFood. A lista oficial é descoberta em homologação via
#: ``GET /order/v1.0/orders/{id}/cancellationReasons``; o mapeamento real é
#: config-driven (``SHOPMAN_IFOOD["cancellation_reason_codes"]``). Este
#: default fica VAZIO de propósito: sem código validado, cai no
#: ``cancellation_default_code`` — código errado é pior que falhar alto.
DEFAULT_REASON_CODES: dict[str, str] = {}


def resolve_cancellation_code(reason: str, default: str = "") -> str:
    """Cancellation code for a Gestor reason, falling back to default/config.

    Os códigos oficiais só devem entrar depois da homologação; até lá o
    fallback garante que o pedido de cancelamento não morre por falta de code
    (o default configurado em ``SHOPMAN_IFOOD["cancellation_default_code"]``).
    """
    codes = dict(DEFAULT_REASON_CODES)
    codes.update(_cfg().get("cancellation_reason_codes") or {})
    return (
        codes.get(str(reason or "").strip())
        or default
        or str(_cfg().get("cancellation_default_code") or "")
    )


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def _base_url() -> str:
    return str(_cfg().get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def action_for_status(
    status: str,
    *,
    fulfillment_type: str | None = None,
    delivered_by: str = "",
) -> str | None:
    """Map status; only ``dispatch`` depende de quem faz a entrega.

    Workflow oficial do módulo Order
    (https://developer.ifood.com.br/pt-BR/docs/food/guides/modules/order/workflow):

    - ``readyToPickup`` é "obrigatório para pedidos TAKEOUT, DINE_IN e DELIVERY"
      — ou seja, para **todo** tipo de pedido, inclusive DELIVERY com entrega
      própria: "Para pedidos com entrega própria, notifique o pedido pronto via
      ``/readyToPickup`` **antes** de despachar via ``/dispatch``". Avisar que a
      comida ficou pronta não afirma nada sobre quem leva, então o dono da
      entrega não entra nesta decisão — nem quando vem vazio. Deixar de avisar
      é que é desvio: foi o defeito medido ao vivo em 19/09/2026 (pedido
      ``IFOOD-260919-Q38``, ``deliveredBy: MERCHANT``), onde o "pronto" do
      operador não gerou chamada nenhuma.
    - ``dispatch`` é o espelho e continua restrito: só a loja despacha, e só
      quando ela é a dona da entrega. Dono ausente **nunca** é lido como
      MERCHANT — despachar no lugar do entregador do iFood afirmaria uma
      entrega que não existe.

    A forma sem contexto (``fulfillment_type is None``) segue sendo consulta
    pura de capacidade para quem só quer saber se o status tem ação.
    """
    status = str(status or "").lower()
    action = STATUS_ACTION.get(status)
    if status != "dispatched" or fulfillment_type is None:
        return action
    fulfillment = str(fulfillment_type or "").lower()
    owner = str(delivered_by or "").upper()
    return action if fulfillment == "delivery" and owner == "MERCHANT" else None


def workflow_context(order) -> dict[str, str]:
    """Read the same canonical fulfillment (including legacy key) as operations."""
    from shopman.shop.services.order_helpers import get_fulfillment_type

    return {
        "fulfillment_type": get_fulfillment_type(order),
        "delivered_by": ((order.data or {}).get("ifood") or {}).get("delivered_by", ""),
    }


def remote_status_observed(order, status: str) -> bool:
    """Do not echo a confirmed remote transition, even from an older Directive."""
    remote = (order.data or {}).get("ifood") or {}
    # O iFood já CONCLUIU o pedido: qualquer aviso de progresso chegaria depois do
    # fim e contaria ao marketplace um passado que ele encerrou. Medido em
    # 21/09/2026: o pedido 1416 foi concluído lá às 14:54:56 e o nosso despacho
    # saiu um minuto depois.
    if remote.get("remote_concluded"):
        return status in {"accepted", "preparing", "ready", "dispatched"}
    if status == "accepted":
        return bool(remote.get("remote_confirmed") or remote.get("remote_dispatched"))
    # ``preparing`` entra aqui com ``ready``/``dispatched``, não com ``accepted``:
    # a confirmação remota PRECEDE o preparo e não o dispensa, mas um despacho já
    # observado significa que o pedido saiu — avisar "comecei a preparar" depois
    # disso contaria ao iFood um passado que ele já superou.
    if status in {"preparing", "ready", "dispatched"}:
        return bool(remote.get("remote_dispatched"))
    return False


def send_action(order_id: str, action: str, *, body: dict | None = None) -> None:
    """POST a status action to iFood. Raises :class:`IFoodCallbackError` on failure."""
    headers = ifood_auth.authorized_headers({"Content-Type": "application/json"})
    if not headers:
        raise IFoodCallbackError("iFood OAuth is not configured (client_id/client_secret)")

    url = f"{_base_url()}/order/v1.0/orders/{order_id}/{action}"
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=int(_cfg().get("timeout") or 30))
    except requests.RequestException as exc:
        raise IFoodCallbackError(f"iFood {action} request failed") from exc

    # iFood returns 202 Accepted for status actions.
    if resp.status_code not in (200, 202):
        retryable = resp.status_code in (408, 429) or resp.status_code >= 500
        if resp.status_code == 403:
            # The edge can return HTML "Access Denied" intermittently. That is
            # not a marketplace decision: preserve the pending request and retry.
            # Only a structured API response supports treating 403 as a definite
            # authorization/configuration failure. Never retain its raw body.
            try:
                structured_error = isinstance(resp.json(), (dict, list))
            except ValueError:
                structured_error = False
            content_type = str(resp.headers.get("Content-Type", "")).lower()
            retryable = "html" in content_type or not structured_error
        raise IFoodCallbackError(
            f"iFood {action} HTTP {resp.status_code}",
            retryable=retryable,
        )
    logger.info("ifood_callbacks: %s ok for order %s", action, order_id)


def confirm(order_id: str) -> None:
    send_action(order_id, "confirm")


def start_preparation(order_id: str) -> None:
    send_action(order_id, "startPreparation")


def ready_to_pickup(order_id: str) -> None:
    send_action(order_id, "readyToPickup")


def dispatch(order_id: str) -> None:
    send_action(order_id, "dispatch")


def fetch_cancellation_reasons(order_id: str) -> list[dict]:
    """Fetch the cancellation codes iFood accepts for a specific order.

    ``GET /order/v1.0/orders/{id}/cancellationReasons`` → list of
    ``{"cancelCodeId": "...", "description": "..."}``. Use it to discover the
    valid codes to configure ``cancellation_default_code``.
    """
    # Pelo invólucro com retry, não por ``requests`` cru. Medido em 21/09/2026: uma
    # única recusa de borda do Akamai nesta leitura virou 503 no meio de um
    # cancelamento com o prazo do iFood correndo, e o operador perdeu a tentativa.
    # É GET — idempotente —, então também repete em 5xx e queda de transporte.
    from shopman.shop.services import ifood_http

    resp = ifood_http.request(
        "GET", f"/order/v1.0/orders/{order_id}/cancellationReasons",
        label="cancellation_reasons", idempotent=True,
    )
    if resp is None:
        raise IFoodCallbackError("iFood cancellationReasons unavailable after retries (edge, transport or no OAuth)")
    if resp.status_code != 200:
        raise IFoodCallbackError(
            f"iFood cancellationReasons HTTP {resp.status_code}: {resp.text[:200]}"
        )
    try:
        reasons = resp.json()
    except ValueError as exc:
        raise IFoodCallbackError("iFood cancellationReasons response was not JSON") from exc
    if not isinstance(reasons, list) or any(not isinstance(r, dict) or not r.get("cancelCodeId") for r in reasons):
        raise IFoodCallbackError("iFood cancellationReasons response has invalid shape")
    return reasons


def request_cancellation(order_id: str, *, code: str = "", description: str = "") -> None:
    """Ask iFood to cancel an order with a valid cancellation code.

    The code must come from iFood's fixed list (see
    :func:`fetch_cancellation_reasons`). It is config-driven
    (``cancellation_default_code``) rather than guessed — sending a wrong code
    is worse than failing loudly.
    """
    code = str(code or _cfg().get("cancellation_default_code") or "").strip()
    if not code:
        raise IFoodCallbackError(
            "no iFood cancellation code — set SHOPMAN_IFOOD['cancellation_default_code'] "
            "(discover valid codes with fetch_cancellation_reasons)"
        )
    # iFood rejects requestCancellation with 400 when `reason` is empty
    # (verified live 2026-07-01) — it is required alongside the code.
    reason = (
        str(description or "").strip()
        or str(_cfg().get("cancellation_default_reason") or "").strip()
        or "Cancelado pela loja"
    )
    send_action(
        order_id,
        "requestCancellation",
        body={"reason": reason, "cancellationCode": code},
    )


def send_for_status(
    order_id: str,
    status: str,
    *,
    cancellation_reason: str = "",
    cancellation_code: str = "",
    fulfillment_type: str = "",
    delivered_by: str = "",
) -> bool:
    """Send a workflow-valid action; missing ownership never authorizes dispatch."""
    if str(order_id).upper().startswith("IFOOD-SIM-"):
        return False
    action = action_for_status(status, fulfillment_type=fulfillment_type, delivered_by=delivered_by)
    if not action:
        return False
    if action == "requestCancellation":
        code = cancellation_code or resolve_cancellation_code(cancellation_reason)
        request_cancellation(order_id, code=code, description=cancellation_reason)
    else:
        send_action(order_id, action)
    return True


__all__ = [
    "confirm",
    "start_preparation",
    "ready_to_pickup",
    "dispatch",
    "request_cancellation",
    "fetch_cancellation_reasons",
    "send_action",
    "send_for_status",
    "action_for_status",
    "workflow_context",
    "remote_status_observed",
    "resolve_cancellation_code",
    "STATUS_ACTION",
    "IFoodCallbackError",
]
