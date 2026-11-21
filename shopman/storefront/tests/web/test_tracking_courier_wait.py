"""A página do pedido entre a chamada do entregador e a coleta (L2, DEV-2026-026).

Antes, do pronto até a coleta, a página dizia sempre "Pronto, esperando o
entregador", com ou sem entregador chamado, com ele a caminho ou com ninguém
aceitando. Agora cada momento da corrida tem a sua frase (decisão 7 = B do dono,
16/11/2026), derivada do estado NEUTRO da corrida (``courier.customer_wait``), e
o link de rastreio só aparece depois da coleta.

O teste cobra a frase que o cliente lê, pela mesma apresentação da página.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.projections import order_tracking
from shopman.shop.services import courier
from shopman.storefront.presentation.order_tracking import build_order_tracking

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_courier_adapter", "_no_payment")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
TRACK = "https://rastreio.example/r/abc"
#: Palavras que o cliente nunca lê nesta página (decisão do dono, 16/11/2026).
FORBIDDEN = ("corrida", "aceite", "aceitou", "taon", "avisamos", "—")


@pytest.fixture
def _courier_adapter():
    with override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER):
        yield


@pytest.fixture
def _no_payment(monkeypatch):
    ps = order_tracking.payment_status
    monkeypatch.setattr(ps, "has_sufficient_captured_payment", lambda order: False)
    monkeypatch.setattr(ps, "payment_deadline_passed", lambda order: False)
    monkeypatch.setattr(ps, "get_payment_status", lambda order: None)
    monkeypatch.setattr(order_tracking, "store_review_deferred_state", lambda order, state=None: None)


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _frozen_at(hour: int, minute: int):
    """O relógio parado num horário de 20/11/2026 em Brasília: a frase depende do dia."""
    at = datetime(2026, 11, 20, hour, minute, tzinfo=SAO_PAULO)
    return patch("django.utils.timezone.now", return_value=at.astimezone(UTC))


def _ago(minutes: float) -> str:
    return (timezone.now() - timedelta(minutes=minutes)).isoformat()


def _at(minutes: float) -> str:
    return (timezone.now() + timedelta(minutes=minutes)).isoformat()


def _order(channel, *, status="ready", courier_block=None):
    data = {"fulfillment_type": "delivery", "payment": {"method": "cash"}}
    if courier_block is not None:
        data["courier"] = courier_block
    return Order.objects.create(
        ref=f"ORD-L2-{Order.objects.count() + 1:03d}",
        channel_ref=channel.ref,
        status=status,
        total_q=2500,
        handle_type="phone",
        handle_ref="5543999990001",
        data=data,
    )


def _page(order):
    page = build_order_tracking(order)
    promise = page.promise
    return promise.title, promise.message, [action.ref for action in promise.actions]


def _ride(status: str, **extra) -> dict:
    return {"id_mch": "777", "status": status, "called_at": _ago(2), "requested_at": _ago(2), **extra}


def _assert_customer_voice(title: str, message: str) -> None:
    text = f"{title} {message}".lower()
    for word in FORBIDDEN:
        assert word not in text, (word, title, message)
    assert title[:1].isupper() and message[:1].isupper(), (title, message)


def test_without_a_ride_the_page_says_only_that_the_order_is_ready(channel):
    title, message, actions = _page(_order(channel))

    assert (title, message) == ("Seu pedido está pronto", "Logo sai para entrega.")
    assert "track_courier" not in actions


def test_called_and_nobody_coming_yet(channel):
    title, message, actions = _page(_order(channel, courier_block=_ride("D")))

    assert (title, message) == ("Seu pedido está pronto", "Estamos chamando o entregador.")
    assert "track_courier" not in actions
    _assert_customer_voice(title, message)


def test_coming_to_the_store_after_midnight_says_the_day(channel):
    """Às 23h55, a chegada em 12 minutos é no dia seguinte: a frase leva a data."""
    with _frozen_at(23, 55):
        eta = timezone.localtime(timezone.now() + timedelta(minutes=12)).replace(second=0, microsecond=0)
        block = _ride(
            "A",
            driver={"name": "DIEGO SOUZA LIMA", "phone": "43999990000"},
            progress={"pickup_eta_at": eta.isoformat()},
            tracking_url=TRACK,
        )

        _title, message, _actions = _page(_order(channel, courier_block=block))

    assert message == "Chega à loja por volta de 0h07 de 21/11."


def test_nobody_takes_it_for_too_long(channel):
    late = courier.LATE_SEARCH_MINUTES + 1
    block = _ride("D", called_at=_ago(late), requested_at=_ago(late))

    title, message, _ = _page(_order(channel, courier_block=block))

    assert (title, message) == (
        "Seu pedido está pronto",
        "Está demorando mais que o normal. Seguimos chamando o entregador.",
    )
    _assert_customer_voice(title, message)


def test_the_service_gave_up_finding_someone_reads_as_late(channel):
    title, message, _ = _page(_order(channel, courier_block=_ride("N")))

    assert message.startswith("Está demorando mais que o normal.")


def test_coming_to_the_store_with_name_and_time(channel):
    # Meio do dia: o horário de chegada cai no mesmo dia, e a frase diz só a hora.
    with _frozen_at(12, 0):
        eta = timezone.localtime(timezone.now() + timedelta(minutes=12)).replace(second=0, microsecond=0)
        block = _ride(
            "A",
            driver={"name": "DIEGO SOUZA LIMA", "phone": "43999990000"},
            progress={"pickup_eta_at": eta.isoformat()},
            tracking_url=TRACK,
        )

        title, message, actions = _page(_order(channel, courier_block=block))

    assert title == "Diego vem buscar seu pedido"
    assert message == "Chega à loja por volta de 12h12."
    # Decisão 7 = B: o link existe desde o aceite, mas só aparece depois da coleta.
    assert "track_courier" not in actions
    _assert_customer_voice(title, message)


def test_coming_without_name_or_time(channel):
    title, message, _ = _page(_order(channel, courier_block=_ride("A")))

    assert (title, message) == ("O entregador vem buscar seu pedido", "Seu pedido está pronto.")


def test_at_the_store(channel):
    block = _ride("S", driver={"name": "Diego"}, progress={"arrived_pickup_at": _ago(1)})

    title, message, _ = _page(_order(channel, courier_block=block))

    assert (title, message) == ("Diego chegou à loja", "Logo sai com seu pedido.")
    _assert_customer_voice(title, message)


def test_the_driver_gave_up_and_another_is_being_called(channel):
    block = _ride("D", reopens=[{"at": _ago(1), "driver": "Diego Souza", "source": "webhook", "reason": "withdrew"}])

    title, message, actions = _page(_order(channel, courier_block=block))

    assert (title, message) == ("Diego não pôde vir", "Estamos chamando outro entregador.")
    assert "track_courier" not in actions
    _assert_customer_voice(title, message)


def test_a_cancelled_ride_goes_back_to_ready(channel):
    title, message, _ = _page(_order(channel, courier_block=_ride("C")))

    assert (title, message) == ("Seu pedido está pronto", "Logo sai para entrega.")


def test_after_pickup_the_name_the_time_and_the_tracking_link(channel):
    block = _ride("E", driver={"name": "Diego"}, tracking_url=TRACK, tracking_match="stop")
    order = _order(channel, status="dispatched", courier_block=block)

    title, message, _ = _page(order)

    assert title == "Saiu para entrega"
    assert message.startswith("Diego está a caminho.")


def test_the_house_courier_reads_the_same_neutral_states(channel, monkeypatch):
    """Entregador da casa (DEV-2026-030): o serviço muda, a frase não."""
    from shopman.shop.adapters import courier_own_fleet
    from shopman.shop.services import delivery_services

    monkeypatch.setattr(delivery_services, "courier_backend", lambda block=None: courier_own_fleet)
    block = _ride("A", id_mch="CASA-1", driver={"name": "Marcos"})

    title, _, _ = _page(_order(channel, courier_block=block))

    assert title == "Marcos vem buscar seu pedido"


def test_owner_edited_copy_wins(channel):
    from shopman.shop.models import OmotenashiCopy

    OmotenashiCopy.objects.create(
        key="TRACKING_DELIVERY_COURIER_CALLED", title="Já pedimos alguém", message="Seu pedido está guardado.",
    )

    title, message, _ = _page(_order(channel, courier_block=_ride("D")))

    assert (title, message) == ("Já pedimos alguém", "Seu pedido está guardado.")


def test_customer_wait_never_reads_the_raw_letter_without_the_service():
    """Sem corrida (sem ``id_mch``) não há estado a ler."""
    assert courier.customer_wait({})["stage"] == ""
    assert courier.customer_wait({"status": "A"})["stage"] == ""


def test_courier_change_reaches_the_page_channel_and_the_page_rereads(channel, monkeypatch,
                                                                       django_capture_on_commit_callbacks):
    """O ``courier_changed`` vai ao canal do pedido; no push a página relê e lê a frase nova.

    A página (``useOrderTrackingStream``) refaz o fetch em todo ``order-update``;
    o vitest do composable prova esse lado com o corpo do ``courier_changed``.
    """
    sent: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        "django_eventstream.send_event",
        lambda channel_name, event_type, payload, *a, **k: sent.append((channel_name, event_type, payload)),
    )
    order = _order(channel, courier_block=_ride("A", driver={"name": "Diego"}))
    assert _page(order)[0] == "Diego vem buscar seu pedido"

    with django_capture_on_commit_callbacks(execute=True):
        assert courier.record_reopen(order, at=_ago(0)) == "applied"

    pushed = [(name, kind, body) for name, kind, body in sent if name == f"order-{order.ref}"]
    assert pushed and pushed[-1][1] == "order-update"
    # ``emit_courier_update`` abre com ``kind="courier_changed"`` e o funil da
    # corrida diz o que mudou por cima ("reopened"); a página relê em qualquer um.
    assert pushed[-1][2]["kind"] == "reopened"
    order.refresh_from_db()
    assert _page(order)[:2] == ("Diego não pôde vir", "Estamos chamando outro entregador.")


def test_delay_and_withdrawal_are_never_painted_as_good_news(channel):
    # O ✔ verde de sucesso sobre "Diego não pôde vir" mentiria. Demora e
    # desistência ficam neutras; o caminho que anda segue como sucesso.
    late = courier.LATE_SEARCH_MINUTES + 1
    cases = {
        "late": _ride("D", called_at=_ago(late), requested_at=_ago(late)),
        "replaced": _ride("D", reopens=[{"at": _ago(1), "driver": "Diego", "source": "webhook", "reason": "withdrew"}]),
        "called": _ride("D"),
        "at_store": _ride("S", driver={"name": "Diego"}, progress={"arrived_pickup_at": _ago(1)}),
    }
    tones = {stage: build_order_tracking(_order(channel, courier_block=block)).promise.tone
             for stage, block in cases.items()}

    assert tones == {"late": "info", "replaced": "info", "called": "success", "at_store": "success"}
