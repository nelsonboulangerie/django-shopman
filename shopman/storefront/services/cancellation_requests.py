"""Adapter da superfície para o serviço canônico de cancelamento."""

from shopman.shop.services.cancellation_requests import (
    ALERT_TYPE,
    EVENT_TYPE,
    TERMINAL_STATUSES,
    CancellationRequest,
    CancellationRequestUnavailable,
    current,
    request_cancellation,
)

__all__ = [
    "ALERT_TYPE",
    "EVENT_TYPE",
    "TERMINAL_STATUSES",
    "CancellationRequest",
    "CancellationRequestUnavailable",
    "current",
    "request_cancellation",
]
