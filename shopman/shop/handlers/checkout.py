"""Recover only missing local checkout convenience effects via the existing worker."""

from shopman.shop.directives import CHECKOUT_CONVENIENCE


class CheckoutConvenienceHandler:
    topic = CHECKOUT_CONVENIENCE

    def handle(self, *, message, ctx):
        from shopman.shop.services.checkout import recover_convenience_effect

        recover_convenience_effect(message)
