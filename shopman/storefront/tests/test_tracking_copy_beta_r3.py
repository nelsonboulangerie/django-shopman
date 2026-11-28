"""Beta SMS-21: copy do acompanhamento que o cliente lia errado."""

from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS, WILDCARD


def _entry(key):
    return OMOTENASHI_DEFAULTS[key][WILDCARD][WILDCARD]


def test_ready_delivery_does_not_read_as_customer_pickup():
    entry = _entry("TRACKING_DELIVERY_WAITING_COURIER")
    # "Pronto para coleta" soava como "venha buscar": a coleta era do entregador.
    # Desde a L2 (decisão 7 = B) o título diz só "Seu pedido está pronto", e a
    # frase diz que ele vai até o cliente.
    assert "coleta" not in f"{entry.title} {entry.message}".lower()
    assert "entrega" in entry.message.lower()


def test_pix_title_does_not_repeat_the_message_verb():
    title = _entry("TRACKING_PAYMENT_REQUESTED").title
    message = _entry("TRACKING_PAYMENT_PIX_READY_MESSAGE_NEW").message
    assert not (title.startswith("Pague") and message.startswith("Pague"))
