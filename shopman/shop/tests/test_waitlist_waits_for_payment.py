"""Uma bola de cada vez: a fila não fala enquanto o pagamento está em aberto.

⚠️ Relato de campo: no fluxo de fila de espera, a tela dizia as duas coisas ao
mesmo tempo — "pague para confirmar sua reserva" (eixo do pagamento) e "Você
está na fila. Nada foi cobrado ainda" (eixo da fila). Lidos juntos, o segundo
desfaz o primeiro: a tela informava ao cliente que a vaga já era dele e que pagar
podia ficar para depois.

Os dois eixos derivam de sinais DIFERENTES e por isso não se viam. Não era
hipótese: eles disparam juntos por construção sempre que há hold planejado ativo
num pedido com pagamento pendente.

A correção é de ORDEM, não de política. A decisão de 28/08 continua de pé
(fornada do dia não cobra para garantir vaga): pedido sem pagamento em aberto
segue vendo a fila normalmente. O que muda é quem fala primeiro quando os dois
têm o que dizer.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Channel
from shopman.shop.projections.order_tracking import build_tracking

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel(db):
    return Channel.objects.create(ref="web", name="Web")


def _order(*, payment: dict, ref: str = "WEB-FILA-1") -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=Order.Status.NEW,
        total_q=5000,
        handle_type="guest",
        handle_ref="teste",
        data={"fulfillment_type": "pickup", "payment": payment},
    )


def _planned_hold(order, *, sku: str = "PAO-DE-FORNADA"):
    """Reserva de FORNADA (não de demanda): sem prazo, datada, ancorada no LOTE.

    O quant não é enfeite do fixture. Reserva de fila nasce ancorada no lote que
    espera (``next_batch_date`` só devolve data onde existe quant planejado), e é
    o quant que separa a fila da demanda ``demand_ok`` — que também nasce sem
    prazo e, até 29/08, levava o mesmo carimbo. Fila sem lote é um mundo que a
    produção não produz.
    """
    from shopman.stockman.models import Hold, HoldStatus, Position, Quant

    position, _ = Position.objects.get_or_create(ref="forno", defaults={"name": "Forno"})
    quant = Quant.objects.create(
        sku=sku,
        position=position,
        target_date=date.today() + timedelta(days=1),
        _quantity=Decimal("10"),
    )
    return Hold.objects.create(
        sku=sku,
        quant=quant,
        quantity=Decimal("1"),
        status=HoldStatus.PENDING,
        expires_at=None,
        target_date=date.today() + timedelta(days=1),
        metadata={"reference": f"order:{order.ref}", "planned": True},
    )


def test_the_queue_story_is_silent_while_payment_is_open(channel):
    """Enquanto falta pagar, quem fala é o pagamento."""
    order = _order(payment={
        "method": "pix",
        "intent_ref": "INT-FILA-1",
        "expires_at": (timezone.now() + timedelta(minutes=10)).isoformat(),
    })
    _planned_hold(order)

    tracking = build_tracking(order)

    assert tracking.waitlist_state == "none"
    assert tracking.waitlist_planned_for is None


def test_an_authorized_card_also_keeps_the_queue_quiet(channel):
    """"Nada foi cobrado ainda" com o dinheiro já reservado é meia-verdade.

    E meia-verdade sobre dinheiro é a metade errada.
    """
    from shopman.payman import PaymentService

    PaymentService.create_intent(
        "WEB-FILA-2", 5000, "card", gateway="stripe", ref="INT-FILA-2",
    )
    PaymentService.authorize("INT-FILA-2", gateway_id="pi_reservado")

    order = _order(
        payment={"method": "card", "intent_ref": "INT-FILA-2"},
        ref="WEB-FILA-2",
    )
    _planned_hold(order)

    tracking = build_tracking(order)

    assert tracking.waitlist_state == "none"


def test_once_paid_the_queue_tells_its_story(channel):
    """A contraprova, e o coração da política: pago, a fila volta a falar.

    Sem esta metade, "calar a fila" viraria "apagar a fila", e a decisão de
    28/08 (fornada do dia não cobra para garantir vaga) morreria por acidente.
    """
    from shopman.payman import PaymentService

    from shopman.shop.services import waitlist

    PaymentService.create_intent(
        "WEB-FILA-3", 5000, "pix", gateway="efi", ref="INT-FILA-3",
    )
    PaymentService.authorize("INT-FILA-3", gateway_id="txid")
    PaymentService.capture("INT-FILA-3")

    order = _order(
        payment={"method": "pix", "intent_ref": "INT-FILA-3"},
        ref="WEB-FILA-3",
    )
    _planned_hold(order)

    tracking = build_tracking(order)

    assert tracking.waitlist_state == waitlist.FERMATA
    assert tracking.waitlist_planned_for is not None


def test_the_confirmation_window_is_never_silenced(channel):
    """⚠️ Calar a fila INTEIRA custava a vaga do cliente, e custava calado.

    ``fermata`` é uma frase passiva — é ela que contradiz o pedido de pagamento,
    e é ela que o gate existe para calar. ``confirming`` é outra coisa: é a loja
    CHAMANDO, com prazo, e a tela do cliente só desenha o botão de aceitar
    quando lê esse estado. Zerado o estado, o chamado some, o relógio continua
    correndo e ``sweep_waitlist_windows`` entrega a vaga ao próximo.

    E não é caso de canto: com ``charge_at="confirmation"`` (o default) a
    cobrança nasce NA confirmação — pagamento em aberto é o estado normal de
    quem está sendo chamado.
    """
    deadline = (timezone.now() + timedelta(minutes=15)).isoformat()
    order = _order(
        payment={
            "method": "pix",
            "intent_ref": "INT-FILA-5",
            "expires_at": (timezone.now() + timedelta(minutes=10)).isoformat(),
        },
        ref="WEB-FILA-5",
    )
    _planned_hold(order)
    order.data["waitlist"] = {"state": "confirming", "sku": "PAO-DE-FORNADA", "deadline": deadline}
    order.save(update_fields=["data"])

    tracking = build_tracking(order)

    assert tracking.waitlist_state == "confirming"
    assert tracking.waitlist_deadline == deadline


def test_a_released_slot_is_never_silenced_either(channel):
    """Desfecho de vaga não se esconde de quem esperou por ela."""
    order = _order(
        payment={
            "method": "pix",
            "intent_ref": "INT-FILA-6",
            "expires_at": (timezone.now() + timedelta(minutes=10)).isoformat(),
        },
        ref="WEB-FILA-6",
    )
    _planned_hold(order)
    order.data["waitlist"] = {"state": "released", "release_reason": "confirmation_timeout"}
    order.save(update_fields=["data"])

    tracking = build_tracking(order)

    assert tracking.waitlist_state == "released"


def test_an_order_without_digital_payment_sees_the_queue_normally(channel):
    """Dinheiro no balcão não tem pagamento "em aberto" na tela: a fila fala."""
    from shopman.shop.services import waitlist

    order = _order(payment={"method": "cash"}, ref="WEB-FILA-4")
    _planned_hold(order)

    tracking = build_tracking(order)

    assert tracking.waitlist_state == waitlist.FERMATA
