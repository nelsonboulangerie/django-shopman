"""A fila da fornada de hoje não cobra no fechamento do pedido (#2730).

Política da casa (28/08/2026): "Encomenda cobra antes. Fornada de hoje não
cobra para garantir vaga." A casa assa a fornada de hoje de qualquer jeito:
quem desiste devolve o pão à gôndola, que o vende.

Medido em 18/11/2026 pelo commit real, com a configuração do canal ``web``
(``payment.timing = at_commit``): o pedido entrava em ``fermata`` e o Pix nascia
no mesmo commit. Pago, o pedido saía da fila, e o que a fila promete ("Nada foi
cobrado ainda", a confirmação da vaga quando a fornada sai) nunca acontecia. Os
testes da fila montam a ``fermata`` à mão; por isso passavam.

Aqui o pedido nasce pelo commit de verdade, a fornada sai pela Produção da tela
(``apply_start``/``apply_finish``), a confirmação e a conferência de pagamento
são os serviços que os endpoints do acompanhamento chamam
(``waitlist.confirm`` em ``orders/<ref>/waitlist-confirm/``,
``customer_orders.ensure_payment_intent`` em ``orders/<ref>/payment/check/``),
o pagamento chega pelo webhook da Efí, e a configuração de cada canal é a da
casa (``config/instances/nelson.json``).
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from shopman.craftsman.models import Recipe
from shopman.craftsman.service import CraftService as craft
from shopman.offerman.models import Product
from shopman.orderman.models import Directive, Order, Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.tests.commit_support import seal_for
from shopman.payman.models import PaymentIntent
from shopman.stockman.models import Hold, HoldStatus, Position, PositionKind, Quant

from shopman.backstage.services import production
from shopman.shop.models import Channel, Shop
from shopman.shop.policies.waitlist_charge import charge_waits_for_the_queue
from shopman.shop.services import availability, customer_orders, waitlist
from shopman.shop.services.operator_orders import confirm_order
from shopman.storefront.presentation.order_tracking import build_order_tracking

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"
ACTOR = "production:forneiro"
DAY = timedelta(days=1)
D = Decimal
NELSON_DESCRIPTOR = Path(__file__).resolve().parents[3] / "config" / "instances" / "nelson.json"
#: Os canais da casa que cobram ao pedir (Pix ou cartão, ``at_commit``).
LOJA = ("web", "whatsapp")


def _descriptor_overrides(ref: str) -> dict:
    """A configuração do canal como a casa a declara, só os aspectos que o pedido lê."""
    descriptor = json.loads(NELSON_DESCRIPTOR.read_text())
    [entry] = [c for c in descriptor["bootstrap"]["channels"] if c["ref"] == ref]
    overrides = entry["config"]["overrides"]
    return {key: overrides[key] for key in ("confirmation", "payment", "stock", "waitlist") if key in overrides}


@pytest.fixture
def ficha(monkeypatch):
    # A conferência de insumo é outra história: aqui a ficha não tem insumo.
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    for ref in LOJA:
        config = _descriptor_overrides(ref)
        assert config["payment"]["timing"] == "at_commit", "a casa cobra ao pedir nestes canais"
        Channel.objects.create(ref=ref, name=ref, is_active=True, config=config)
    Product.objects.create(
        sku=SKU, name="Baguete", unit="un", base_price_q=1100, availability_policy="planned_ok",
        shelf_life_days=1, is_published=True, is_sellable=True,
    )
    Position.objects.create(
        ref="producao", name="Produção", kind=PositionKind.PHYSICAL, is_saleable=False, is_default=True,
    )
    Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
    return Recipe.objects.create(ref="baguete", name="Baguete", output_sku=SKU, batch_size=D("10"))


def _hoje():
    return timezone.localdate()


def _planejar(ficha, day, qty="10"):
    return craft.plan(ficha, quantity=D(qty), date=day, position_ref="producao")


def _iniciar(work_order, qty="10") -> None:
    work_order.refresh_from_db()
    production.apply_start(
        work_order_id=work_order.pk, quantity=qty, actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"start-{work_order.pk}",
    )


def _fechar(work_order, qty="10") -> None:
    work_order.refresh_from_db()
    production.apply_finish(
        work_order_id=work_order.pk, quantity=qty, actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"finish-{work_order.pk}", partition=[{"quantity": qty, "quality_grade_ref": "standard"}],
    )


def _pedir(channel: str, qty: int, callbacks, *, day=None, key: str = "1", pela_sacola: bool = False) -> Order:
    """O pedido da loja pelo commit de verdade, com os efeitos pós-commit rodados.

    ``pela_sacola``: a reserva da sacola é feita antes (``availability.reserve``),
    como a loja faz ao pôr o item no carrinho. É ela que escolhe a fornada quando
    não há pão para hoje, e o commit a adota.
    """
    session_key = f"S-{channel}-{key}"
    data = {"payment": {"method": "pix"}, "fulfillment_type": "pickup", "origin_channel": channel}
    if day is not None:
        data["delivery_date"] = day.isoformat()
    Session.objects.create(
        session_key=session_key, channel_ref=channel, state="open", rev=1, data=data,
        items=[{"line_id": "L1", "sku": SKU, "name": "Baguete", "qty": qty, "unit_price_q": 1100}],
    )
    if pela_sacola:
        reserva = availability.reserve(SKU, D(qty), session_key=session_key, channel_ref=channel)
        assert reserva["ok"], reserva
    with callbacks(execute=True):
        result = CommitService.commit(
            session_key=session_key, channel_ref=channel, idempotency_key=f"K-{channel}-{key}",
            seal=seal_for(session_key, channel), channel_config={},
        )
    return Order.objects.get(ref=result["order_ref"] if isinstance(result, dict) else result.order_ref)


def _pagamento(order: Order) -> dict:
    order.refresh_from_db()
    return (order.data or {}).get("payment") or {}


def _cobrancas(order: Order) -> int:
    return PaymentIntent.objects.filter(order_ref=order.ref).count()


def _avisos_de_cobranca(order: Order) -> int:
    return Directive.objects.filter(
        topic="notification.send", payload__order_ref=order.ref, payload__template="payment_requested",
    ).count()


def _prazos_de_pagamento(order: Order) -> int:
    return Directive.objects.filter(topic="payment.timeout", payload__order_ref=order.ref).count()


def _reserva(order: Order) -> Hold:
    order.refresh_from_db()
    [entry] = order.data["hold_ids"]
    return Hold.objects.select_related("quant").get(pk=int(entry["hold_id"].split(":")[1]))


def _pagar_pelo_webhook(order: Order, callbacks):
    intent = PaymentIntent.objects.get(ref=_pagamento(order)["intent_ref"])
    with callbacks(execute=True):
        return APIClient().post(
            "/api/webhooks/efi/pix/",
            {"pix": [{"txid": intent.gateway_id, "endToEndId": "E2730", "valor": f"{order.total_q / 100:.2f}"}]},
            format="json", HTTP_X_EFI_WEBHOOK_TOKEN="test-efi-token",
        )


# ── A fila da fornada de hoje: reserva de graça, cobrança na confirmação ─────


@pytest.mark.parametrize("channel", LOJA)
@pytest.mark.parametrize("lote_aberto", [False, True], ids=["lote-planejado", "lote-no-forno"])
def test_pedido_na_fila_da_fornada_de_hoje_nao_nasce_cobrado(
    ficha, channel, lote_aberto, django_capture_on_commit_callbacks,
):
    lote = _planejar(ficha, _hoje())
    if lote_aberto:
        with django_capture_on_commit_callbacks(execute=True):
            _iniciar(lote)

    order = _pedir(channel, 4, django_capture_on_commit_callbacks)

    assert order.status == "new"
    assert waitlist.state_for(order) == waitlist.FERMATA
    assert waitlist.planned_batch_date(order) == _hoje()
    assert charge_waits_for_the_queue(order) is True
    pagamento = _pagamento(order)
    assert pagamento.get("method") == "pix", "o meio escolhido fica guardado para a hora de cobrar"
    assert not pagamento.get("intent_ref")
    assert not pagamento.get("qr_code") and not pagamento.get("copy_paste")
    assert _cobrancas(order) == 0, "nenhuma cobrança nasce no fechamento do pedido"
    assert _prazos_de_pagamento(order) == 0, "sem cobrança não há prazo de pagamento correndo"
    assert _avisos_de_cobranca(order) == 0
    # A reserva está feita: a vaga é dele, de graça.
    reserva = _reserva(order)
    assert reserva.status in (HoldStatus.PENDING, HoldStatus.CONFIRMED)
    assert reserva.expires_at is None


@pytest.mark.parametrize("channel", LOJA)
def test_a_tela_de_acompanhamento_nao_cria_a_cobranca_que_o_commit_segurou(
    ficha, channel, django_capture_on_commit_callbacks,
):
    """A conferência de pagamento da tela é recuperação, não um segundo caminho de cobrança."""
    _planejar(ficha, _hoje())
    order = _pedir(channel, 4, django_capture_on_commit_callbacks)

    assert customer_orders.ensure_payment_intent(order) is False

    assert _cobrancas(order) == 0
    assert not _pagamento(order).get("intent_ref")
    acompanhamento = build_order_tracking(order)
    assert acompanhamento.waitlist_state == waitlist.FERMATA, "o cliente lê a fila, não um pedido de pagamento"


@override_settings(SHOPMAN_EFI_WEBHOOK={"webhook_token": "test-efi-token"})
@pytest.mark.parametrize("channel", LOJA)
def test_a_cobranca_nasce_quando_o_cliente_confirma_a_vaga(ficha, channel, django_capture_on_commit_callbacks):
    """Ponta a ponta: pedido, fornada sai, loja chama, cliente confirma, Pix nasce, paga, loja aceita."""
    lote = _planejar(ficha, _hoje())
    order = _pedir(channel, 4, django_capture_on_commit_callbacks)
    assert _cobrancas(order) == 0

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    assert waitlist.state_for(order) == waitlist.FERMATA
    assert _cobrancas(order) == 0, "lote no forno: a vaga continua de graça"
    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)

    # A fornada saiu: a loja chama, com prazo. Ainda nada cobrado.
    order.refresh_from_db()
    assert waitlist.state_for(order) == waitlist.CONFIRMING
    assert _cobrancas(order) == 0
    assert customer_orders.ensure_payment_intent(order) is False, "chamado ainda não é cobrança"
    assert _cobrancas(order) == 0

    with django_capture_on_commit_callbacks(execute=True):
        assert waitlist.confirm(order) is True

    # Confirmou: a cobrança nasce aqui, com o aviso e o prazo dela.
    order.refresh_from_db()
    assert waitlist.state_for(order) == waitlist.CONFIRMED
    pagamento = _pagamento(order)
    assert pagamento.get("intent_ref")
    assert pagamento.get("qr_code") or pagamento.get("copy_paste")
    assert _cobrancas(order) == 1
    assert _avisos_de_cobranca(order) == 1
    assert customer_orders.ensure_payment_intent(order) is True

    # Dali em diante é o Pix de sempre: paga, a loja aceita, a baixa sai do pão que existe.
    assert _pagar_pelo_webhook(order, django_capture_on_commit_callbacks).status_code == 200
    order.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        confirm_order(order, actor="operator")
    order.refresh_from_db()
    assert order.status == "accepted"
    assert _reserva(order).status == HoldStatus.FULFILLED
    vitrine = Quant.objects.get(sku=SKU, target_date__isnull=True)
    assert vitrine.quantity == D("6")
    assert _cobrancas(order) == 1, "uma cobrança só, do começo ao fim"


# ── Quem continua cobrando ao pedir ──────────────────────────────────────────


@pytest.mark.parametrize("channel", LOJA)
def test_pao_pronto_cobra_ao_pedir_como_sempre(ficha, channel, django_capture_on_commit_callbacks):
    lote = _planejar(ficha, _hoje())
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)

    order = _pedir(channel, 4, django_capture_on_commit_callbacks)

    assert waitlist.state_for(order) == waitlist.NONE
    assert _pagamento(order).get("intent_ref")
    assert _cobrancas(order) == 1


@pytest.mark.parametrize("channel", LOJA)
def test_encomenda_cobra_antes(ficha, channel, django_capture_on_commit_callbacks):
    """Data combinada com o cliente: produção dedicada, cobrança no pedido."""
    amanha = _hoje() + DAY
    _planejar(ficha, amanha)

    order = _pedir(channel, 4, django_capture_on_commit_callbacks, day=amanha)

    assert order.data.get("is_preorder") is True
    assert waitlist.state_for(order) == waitlist.NONE, "encomenda não está na fila"
    assert charge_waits_for_the_queue(order) is False
    assert _pagamento(order).get("intent_ref")
    assert _cobrancas(order) == 1


@pytest.mark.parametrize("channel", LOJA)
def test_fila_de_lote_de_outro_dia_nao_existe_sem_data_combinada(ficha, channel, django_capture_on_commit_callbacks):
    """Só há fornada para amanhã e o pedido é para hoje: a sacola reserva a vaga no
    lote de amanhã, mas o commit recusa o pedido sem a data. Com a data ele é
    encomenda, e cobra antes: fila sem cobrança é sempre a da fornada de hoje."""
    from shopman.orderman.exceptions import ValidationError

    amanha = _hoje() + DAY
    _planejar(ficha, amanha)

    with pytest.raises(ValidationError) as error:
        _pedir(channel, 4, django_capture_on_commit_callbacks, pela_sacola=True)

    assert error.value.code == "order_date_before_batch"
    assert not Order.objects.filter(channel_ref=channel).exists()

    order = _pedir(channel, 4, django_capture_on_commit_callbacks, day=amanha, key="2")

    assert order.data.get("is_preorder") is True
    assert charge_waits_for_the_queue(order) is False
    assert _cobrancas(order) == 1
