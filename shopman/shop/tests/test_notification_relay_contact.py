"""Relé de voz da plataforma não é contato do cliente.

O iFood não entrega o telefone do cliente: manda o 0800 da central dele mais um
localizador, e quem liga digita o localizador para cair na pessoa. Esse número
chegava em ``order.data["customer"]["phone"]``, o guarda de "pedido sem contato"
só pulava com o campo VAZIO, e o canal ``ifood`` não declara ``notifications`` —
então todo pedido real do marketplace disparava consulta ao ManyChat com o
telefone de um terceiro. Medido em 19/09/2026, em pedido real:
``destinatario_manychat='+558007053040'``.

A outra metade, que estes testes seguram junto: pedido de canal próprio com
telefone de verdade continua avisando o cliente exatamente como antes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

IFOOD_RELAY_PHONE = "+558007053040"
CUSTOMER_PHONE = "+5543999990001"


def _make_order(**overrides):
    order = MagicMock()
    order.ref = overrides.get("ref", "ORD-RELAY-001")
    order.total_q = 5000
    order.status = "ready"
    order.handle_type = overrides.get("handle_type", "")
    order.handle_ref = overrides.get("handle_ref", "")
    order.data = overrides.get("data", {})
    order.snapshot = {"items": [], "data": {}}
    order.channel_ref = overrides.get("channel_ref", "web")
    return order


def _ifood_order(*, localizer: str = "9988", phone: str = IFOOD_RELAY_PHONE):
    customer = {"name": "Cliente iFood", "phone": phone, "phone_localizer": localizer}
    return _make_order(
        channel_ref="ifood",
        handle_type="ifood_order",
        handle_ref="IFOOD-ABC123",
        data={"origin_channel": "ifood", "customer": customer},
    )


def _channel(ref: str, config: dict | None = None):
    from shopman.shop.models import Channel

    channel, _ = Channel.objects.update_or_create(
        ref=ref, defaults={"name": ref, "config": config or {}},
    )
    return channel


def _deliver(order, template="order_ready"):
    """Entrega uma notificação observando backend e envio; devolve os três."""
    from shopman.shop.services.notification import deliver_order_notification

    payload = {"order_ref": order.ref}
    notify = MagicMock()
    get_backend = MagicMock()
    with patch(
        "shopman.shop.services.notification._resolve_backend_chain",
        return_value=["manychat", "sms"],
    ):
        with patch("shopman.shop.services.notification.notify", notify):
            with patch("shopman.shop.notifications.get_backend", get_backend):
                success, error = deliver_order_notification(order, template, payload)
    return (success, error), payload, (notify, get_backend)


# ── o defeito medido ──


@pytest.mark.django_db
def test_ifood_relay_does_not_notify_and_consults_no_backend():
    _channel("ifood", {"notifications": {"customer_phone": "relay"}})
    order = _ifood_order()

    (success, error), payload, (notify, get_backend) = _deliver(order)

    assert (success, error) == (True, None)
    assert payload["notification_delivery"]["status"] == "skipped"
    assert payload["notification_delivery"]["reason"] == "expected_no_contact"
    # O tráfego é o dano, mesmo quando a mensagem não sai: o número é de terceiro.
    notify.assert_not_called()
    get_backend.assert_not_called()


@pytest.mark.django_db
def test_ifood_relay_is_not_a_recipient_for_any_backend():
    from shopman.shop.services.notification import _resolve_recipient

    _channel("ifood", {"notifications": {"customer_phone": "relay"}})
    order = _ifood_order()

    assert _resolve_recipient(order, "manychat") is None
    assert _resolve_recipient(order, "sms") is None
    assert _resolve_recipient(order, "console") is None


@pytest.mark.django_db
def test_ifood_relay_never_looks_the_customer_up_by_the_platform_number():
    """Procurar cliente pelo 0800 da central acha a ficha de quem tiver o número."""
    from shopman.shop.services.notification import _resolve_customer_identity

    _channel("ifood", {"notifications": {"customer_phone": "relay"}})
    order = _ifood_order()

    get_by_phone = MagicMock(return_value=None)
    with patch("shopman.guestman.services.customer.get_by_phone", get_by_phone):
        state, customer_ref = _resolve_customer_identity(order)

    get_by_phone.assert_not_called()
    assert (state, customer_ref) == ("absent", "")


# ── a metade que impede virar "ninguém mais recebe aviso" ──


@pytest.mark.django_db
def test_own_channel_with_a_real_phone_still_notifies():
    _channel("web")
    order = _make_order(
        channel_ref="web",
        data={"origin_channel": "web", "customer": {"name": "João", "phone": CUSTOMER_PHONE}},
    )

    (success, error), payload, (notify, _get_backend) = _deliver(order)

    assert (success, error) == (True, None)
    assert payload["notification_delivery"]["status"] == "accepted"
    assert payload["notification_delivery"]["backend"] == "manychat"
    assert notify.call_count == 1
    assert notify.call_args.kwargs["recipient"] == CUSTOMER_PHONE


@pytest.mark.django_db
def test_own_channel_phone_is_contact_even_with_a_localizer_shaped_key_absent():
    from shopman.shop.services.notification import customer_contact_phone

    _channel("web")
    order = _make_order(
        channel_ref="web", data={"customer": {"phone": CUSTOMER_PHONE}},
    )

    assert customer_contact_phone(order) == CUSTOMER_PHONE


@pytest.mark.django_db
def test_order_without_any_phone_keeps_skipping():
    _channel("ifood", {"notifications": {"customer_phone": "relay"}})
    order = _make_order(
        channel_ref="ifood",
        handle_type="ifood_order",
        handle_ref="IFOOD-NO-PHONE",
        data={"origin_channel": "ifood", "customer": {"name": "Cliente iFood"}},
    )

    (success, error), payload, (notify, _get_backend) = _deliver(order)

    assert (success, error) == (True, None)
    assert payload["notification_delivery"]["reason"] == "expected_no_contact"
    notify.assert_not_called()


# ── localizador ausente: a decisão travada ──


@pytest.mark.django_db
def test_platform_number_without_localizer_is_still_not_a_contact():
    """Sem o localizador, quem responde é o canal — o número continua sendo dele.

    O iFood pode omitir o localizador (pedido antigo, payload diferente, campo
    vazio). Cravar "0800 705 3040" seria remédio no sintoma: o iFood tem mais de
    um número e eles mudam. O sinal que sobra é estrutural — o canal declara que
    o telefone que ele entrega é relé da plataforma.
    """
    from shopman.shop.services.notification import customer_contact_phone

    _channel("ifood", {"notifications": {"customer_phone": "relay"}})
    order = _ifood_order(localizer="")

    assert customer_contact_phone(order) == ""

    (success, error), payload, (notify, get_backend) = _deliver(order)

    assert (success, error) == (True, None)
    assert payload["notification_delivery"]["reason"] == "expected_no_contact"
    notify.assert_not_called()
    get_backend.assert_not_called()


@pytest.mark.django_db
def test_localizer_alone_is_enough_when_the_channel_says_nothing():
    """O sinal por pedido não depende da declaração do canal estar no banco."""
    from shopman.shop.services.notification import customer_contact_phone

    _channel("ifood")  # canal sem `notifications` — o default de hoje
    order = _ifood_order()

    assert customer_contact_phone(order) == ""


# ── a declaração do canal sobrevive à cascata ──


def test_notifications_declares_customer_phone_direct_by_default():
    from shopman.shop.config import ChannelConfig

    assert ChannelConfig().notifications.customer_phone == "direct"


def test_invalid_customer_phone_is_refused():
    from shopman.shop.config import ChannelConfig

    config = ChannelConfig.from_dict({"notifications": {"customer_phone": "0800"}})
    with pytest.raises(ValueError, match="notifications.customer_phone"):
        config.validate()


@pytest.mark.django_db
def test_channel_declaration_is_not_discarded_by_the_cascade():
    """Chave não declarada no dataclass é descartada em silêncio — esta é."""
    from shopman.shop.config import ChannelConfig

    _channel("ifood", {"notifications": {"customer_phone": "relay"}})
    config = ChannelConfig.for_channel("ifood")

    assert config.notifications.customer_phone == "relay"
    # Declarar o fato não muda a política de backends do canal.
    assert config.notifications.backend == "manychat"
