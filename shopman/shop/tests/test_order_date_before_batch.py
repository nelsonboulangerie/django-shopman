"""Um pedido, uma data: a sacola presa a uma fornada futura não vira pedido de antes dela.

Beta 09/11 (NB-261109-Y61/N40/G46): o Kuro Pan entrou na sacola pela fila da
fornada de quarta; o checkout fechou um pedido para retirar HOJE, o Pix foi
pago e a retirada prometida era impossível. O gate de commit
(``stock.hold(require_all=True)``) adotava a reserva de quarta no pedido de
hoje sem olhar a data da fornada a que ela estava presa.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.exceptions import ValidationError
from shopman.stockman import HoldStatus, PositionKind
from shopman.stockman.models import Hold, Position, Quant

from shopman.shop.models import Channel
from shopman.shop.services import checkout as checkout_service
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db

SKU = "KURO-PAN-T"
SESSION_KEY = "sess-kuro"
CHANNEL_REF = "web"


def _world() -> Position:
    Channel.objects.create(ref=CHANNEL_REF, name="Web", is_active=True)
    Product.objects.create(
        sku=SKU,
        name="Kuro Pan",
        base_price_q=1500,
        is_published=True,
        is_sellable=True,
    )
    position, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return position


def _quant(position: Position, *, target_date=None, qty="10") -> Quant:
    return Quant.objects.create(
        sku=SKU,
        position=position,
        target_date=target_date,
        _quantity=Decimal(qty),
    )


def _session_hold(quant: Quant, qty="1") -> Hold:
    """A reserva que a sacola deixou: presa ao quant (planejado ou físico)."""
    return Hold.objects.create(
        sku=SKU,
        quant=quant,
        quantity=Decimal(qty),
        target_date=quant.target_date or timezone.localdate(),
        status=HoldStatus.PENDING,
        expires_at=None if quant.target_date else timezone.now() + timedelta(minutes=30),
        metadata={"reference": SESSION_KEY, "planned": bool(quant.target_date)},
    )


def _order(*, delivery_date=None, session_key=SESSION_KEY, ref="ORD-KURO", qty=1):
    data = {}
    if delivery_date is not None:
        data["delivery_date"] = delivery_date.isoformat()
    return SimpleNamespace(
        ref=ref,
        channel_ref=CHANNEL_REF,
        session_key=session_key,
        snapshot={"items": [{"sku": SKU, "name": "Kuro Pan", "qty": qty}], "data": {}},
        data=data,
        save=lambda update_fields=None: None,
    )


class TestSacolaPresaAFornadaFutura:
    def test_pedido_de_hoje_com_reserva_da_fornada_de_quarta_e_recusado(self):
        today = timezone.localdate()
        wednesday = today + timedelta(days=2)
        position = _world()
        hold = _session_hold(_quant(position, target_date=wednesday))

        with pytest.raises(ValidationError) as caught:
            stock_service.hold(_order(), require_all=True)

        error = caught.value
        assert error.code == stock_service.ORDER_DATE_BEFORE_BATCH
        assert error.message == (
            f"Kuro Pan sai {stock_service.batch_day_phrase(wednesday)}. "
            "Escolha essa data ou uma depois dela."
        )
        assert wednesday.strftime("%d/%m") in error.message
        assert error.context["field"] == "delivery_date"
        assert error.context["batch_date"] == wednesday.isoformat()
        # Nada foi adotado: a reserva continua da sacola, presa à quarta.
        hold.refresh_from_db()
        assert hold.metadata["reference"] == SESSION_KEY

    def test_pedido_com_data_explicita_anterior_a_fornada_tambem_e_recusado(self):
        today = timezone.localdate()
        position = _world()
        _session_hold(_quant(position, target_date=today + timedelta(days=2)))

        with pytest.raises(ValidationError) as caught:
            stock_service.hold(_order(delivery_date=today + timedelta(days=1)), require_all=True)

        assert caught.value.code == stock_service.ORDER_DATE_BEFORE_BATCH

    def test_pedido_para_o_dia_da_fornada_passa(self):
        today = timezone.localdate()
        wednesday = today + timedelta(days=2)
        position = _world()
        _session_hold(_quant(position, target_date=wednesday))
        order = _order(delivery_date=wednesday)

        stock_service.hold(order, require_all=True)

        entries = order.data["hold_ids"]
        assert [entry["sku"] for entry in entries] == [SKU]
        held = Hold.objects.get(pk=int(entries[0]["hold_id"].split(":")[1]))
        assert held.quant.target_date == wednesday

    def test_fornada_de_hoje_mais_tarde_continua_passando(self):
        today = timezone.localdate()
        position = _world()
        hold = _session_hold(_quant(position, target_date=today))
        order = _order()

        stock_service.hold(order, require_all=True)

        assert order.data["hold_ids"][0]["hold_id"] == hold.hold_id
        hold.refresh_from_db()
        assert hold.metadata["reference"] == f"order:{order.ref}"

    def test_pedido_do_dia_com_pao_pronto_continua_passando(self):
        position = _world()
        hold = _session_hold(_quant(position))
        order = _order()

        stock_service.hold(order, require_all=True)

        assert order.data["hold_ids"][0]["hold_id"] == hold.hold_id

    def test_canal_sem_sessao_nao_e_afetado(self):
        """PDV/balcão: sem sacola, o gate nem olha (mesmo havendo fornada futura)."""
        today = timezone.localdate()
        position = _world()
        _quant(position)
        _session_hold(_quant(position, target_date=today + timedelta(days=2)))
        order = _order(session_key=None, ref="ORD-PDV")

        stock_service.hold(order)

        held = Hold.objects.get(pk=int(order.data["hold_ids"][0]["hold_id"].split(":")[1]))
        assert held.quant.target_date is None

    def test_caminho_brando_nao_adota_a_reserva_da_fornada_futura(self):
        today = timezone.localdate()
        position = _world()
        _quant(position)
        future = _session_hold(_quant(position, target_date=today + timedelta(days=2)))
        order = _order(ref="ORD-BRANDO")

        stock_service.hold(order)

        assert all(entry["hold_id"] != future.hold_id for entry in order.data["hold_ids"])
        future.refresh_from_db()
        assert future.status == HoldStatus.RELEASED


class TestRecusaNoDialetoDoCheckout:
    def test_recusa_aponta_o_campo_da_data(self):
        error = ValidationError(
            code=stock_service.ORDER_DATE_BEFORE_BATCH,
            message="Kuro Pan sai na quarta, 11/11. Escolha essa data ou uma depois dela.",
            context={"field": "delivery_date"},
        )

        assert checkout_service.map_checkout_error(error) == {
            "delivery_date": "Kuro Pan sai na quarta, 11/11. Escolha essa data ou uma depois dela.",
        }

    def test_frase_do_dia_da_fornada(self):
        from datetime import date

        monday = date(2026, 11, 9)
        assert stock_service.batch_day_phrase(date(2026, 11, 10), today=monday) == "amanhã, 10/11"
        assert stock_service.batch_day_phrase(date(2026, 11, 11), today=monday) == "na quarta, 11/11"
        assert stock_service.batch_day_phrase(date(2026, 11, 14), today=monday) == "no sábado, 14/11"
