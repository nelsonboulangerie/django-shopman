"""Beta SMS-21: copy do acompanhamento que o cliente lia errado."""

from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS, WILDCARD


def _entry(key):
    return OMOTENASHI_DEFAULTS[key][WILDCARD][WILDCARD]


def test_ready_delivery_does_not_read_as_customer_pickup():
    entry = _entry("TRACKING_DELIVERY_WAITING_COURIER")
    # "Pronto para coleta" soava como "venha buscar": a coleta era do entregador.
    assert "coleta" not in entry.title.lower()
    assert "entregador" in entry.title.lower()


def test_pix_title_does_not_repeat_the_message_verb():
    title = _entry("TRACKING_PAYMENT_REQUESTED").title
    message = _entry("TRACKING_PAYMENT_PIX_READY_MESSAGE_NEW").message
    assert not (title.startswith("Pague") and message.startswith("Pague"))
