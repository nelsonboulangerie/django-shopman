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


def customer_is_opted_in(customer_ref: str, channel: str) -> bool:
    """Opt-in verificado e vigente neste canal; na dúvida, NÃO.

    O irmão de :func:`customer_is_opted_out` falha fechado para o lado oposto:
    quem pergunta "posso contar com o consentimento?" recebe ``False`` quando a
    fonte não responde — nunca uma permissão presumida. A falha é relatada com
    o motivo, porque o chamador segue em frente sem o que dependia dela.
    """

    if not customer_ref:
        return False
    try:
        from shopman.guestman import ConsentService

        statuses = ConsentService.get_customer_statuses(channel, {customer_ref})
    except Exception:
        logger.warning(
            "communication_consent.source_unavailable channel=%s reason=opt_in_unreadable",
            channel,
            exc_info=True,
        )
        return False
    return statuses.get(customer_ref) == "opted_in"
