"""Throttles DRF que contam o cliente pelo mesmo IP que o resto da casa."""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle


class ClientIpAnonRateThrottle(AnonRateThrottle):
    """``AnonRateThrottle`` com o balde no IP de ``auth.client_ip``.

    O ``get_ident`` do DRF só sabe contar ``NUM_PROXIES`` da direita. Pedido que
    chega pelo BFF da loja tem um salto a mais, e ali o N-ésimo da direita é o IP
    de saída do Nitro: todo visitante anônimo da loja cairia no MESMO balde. O
    rate limit do doorman (``RATELIMIT_IP_META_KEY``) e o IP de evidência já
    resolvem por ``client_ip``; este throttle conta igual, por construção.
    """

    def get_ident(self, request):
        from shopman.shop.services.auth import client_ip

        return client_ip(request) or super().get_ident(request)
