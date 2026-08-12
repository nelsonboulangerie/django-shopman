"""Customer identity resolution for the storefront API surface.

Headless: the customer-facing pages live in the Nuxt store; the Django
storefront is the API the BFF consumes. This helper resolves the authenticated
customer from the request (``request.customer`` is set by the doorman auth
middleware) for the API views.
"""

from __future__ import annotations

from shopman.shop.services import auth as auth_service


def get_authenticated_customer(request):
    """Return the Customer model for an authenticated request, or None.

    Reads ``request.customer`` (set by AuthCustomerMiddleware) and resolves the
    full Customer model via the auth service.
    """
    customer_info = getattr(request, "customer", None)
    if customer_info is None:
        return None
    return auth_service.customer_by_uuid(customer_info.uuid)


def customer_pricing_hints(request) -> tuple[str, str]:
    """Return ``(price_tier, customer_segment)`` for the authenticated viewer.

    Feeds the pricing context so a promotion gated by ``customer_segments``
    (price tier or RFM segment) shows on the menu/PDP for an eligible member —
    the same two axes ``DiscountModifier._matches`` checks in the cart. Returns
    ``("", "")`` for an anonymous viewer or on any lookup failure (open to all).
    """
    import logging

    from django.core.exceptions import ObjectDoesNotExist

    logger = logging.getLogger(__name__)
    if request is None:
        return "", ""
    try:
        customer = get_authenticated_customer(request)
        if customer is None:
            return "", ""
        tier = customer.price_tier.ref if getattr(customer, "price_tier_id", None) else ""
        try:
            segment = customer.insight.rfm_segment or ""
        except ObjectDoesNotExist:
            segment = ""  # insight (OneToOne) not computed yet — match by tier only
        return tier, segment
    except Exception:
        logger.warning("customer_pricing_hints failed", exc_info=True)
        return "", ""


# ── Quanto sabemos de quem está do outro lado ────────────────────────
#
# Uma pergunta só, e ela decide tudo o que as telas mostram: **este aparelho é conhecido?**
#
# ⚠️ Não é a `audience` do `AccessLink`. Ela existe no model e ninguém a aplica
# (`exchange_token` nunca passa `required_audience`), então usá-la como cerca seria confiar
# num campo que ninguém lê.

#: O cookie de confiança deste navegador já provou identidade por OTP algum dia
#: (`DeviceTrustService`). Sabemos que é a pessoa: nada é reduzido.
IDENTITY_DEVICE = "device"
#: Veio de um link que mandamos a um número conhecido. Sabemos o NÚMERO, não as MÃOS —
#: mensagem se encaminha. Compra à vontade; dado pessoal aparece reduzido.
IDENTITY_NUMBER = "number"
IDENTITY_SESSION_KEY = "identity_strength"


def identity_strength(request) -> str:
    """A força da identidade desta sessão. Ausente ⇒ ``device``.

    O padrão é o FORTE de propósito: quem entrou pelo login normal (OTP) ou já era confiado
    não passa por aqui, e tratar "sem marca" como fraco esconderia dado de quem provou
    identidade — quebrando a loja para consertar nada.
    """
    session = getattr(request, "session", None)
    if session is None:
        return IDENTITY_DEVICE
    return session.get(IDENTITY_SESSION_KEY) or IDENTITY_DEVICE


def knows_only_the_number(request) -> bool:
    """Atalho de leitura: esta sessão conhece o número, mas não provou as mãos."""
    return identity_strength(request) == IDENTITY_NUMBER
