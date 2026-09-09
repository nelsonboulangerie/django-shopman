"""Surface-safe communication consent checks owned by the orchestrator."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def customer_is_opted_out(customer_ref: str, channel: str) -> bool:
    """Fail closed when the consent source cannot be checked."""

    if not customer_ref:
        return False
    try:
        from shopman.guestman import ConsentService

        statuses = ConsentService.get_customer_statuses(channel, {customer_ref})
    except Exception:
        logger.warning("communication_consent.source_unavailable channel=%s", channel)
        return True
    return statuses.get(customer_ref) == "opted_out"
