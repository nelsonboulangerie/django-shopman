"""Explicit operator decisions only; ambiguous sends are never replayed."""
from shopman.shop.directives import IFOOD_HANDSHAKE_RESPONSE
from shopman.shop.services.ifood_handshake import deliver_response


class IFoodHandshakeResponseHandler:
    topic = IFOOD_HANDSHAKE_RESPONSE

    def handle(self, *, message, ctx):
        deliver_response(message.payload)
