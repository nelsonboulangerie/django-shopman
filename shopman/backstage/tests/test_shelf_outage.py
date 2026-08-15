"""Não ter o produto para oferecer — a falta que o cliente sente.

O que o cliente encontra é o saldo MENOS o reservado. Um produto some do
cardápio com unidades ainda na loja (tudo reservado) e volta quando uma reserva
expira. Nenhum desses dois instantes aparece no ledger de estoque, que só
registra a saída física — por isso a falta é observada à parte.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman.models import Hold, Move, Position, Quant

from shopman.backstage.models import ShelfOutage
from shopman.backstage.projections.bi_explore import build_bi_explore
from shopman.backstage.services import shelf_outages

pytestmark = pytest.mark.django_db


@pytest.fixture
def vitrine(db):
    return Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)


@pytest.fixture
def canal(db):
    from shopman.shop.models import Channel, Shop

    shop = Shop.objects.create(name="Nelson")
    shop.opening_hours = {
        name: {"open": "09:00", "close": "18:00"}
        for name in (
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        )
    }
    shop.save()
    return Channel.objects.create(
        ref="web", name="Loja", commerce_policy="order", is_active=True, shop=shop
    )


@pytest.fixture
def pao(db):
    return Product.objects.create(
        sku="PAO", name="Pão", unit="un", base_price_q=100,
        is_sellable=True, availability_policy="stock_only",
    )


# Os receivers agendam a observação para DEPOIS do commit (a leitura precisa
# enxergar o estado gravado). Sob a transação do teste o commit não acontece,
# então os callbacks são capturados e executados explicitamente — é o que
# reproduz o comportamento real em vez de contorná-lo.
@pytest.fixture
def apos_commit(django_capture_on_commit_callbacks):
    class Executor:
        def __enter__(self):
            self._ctx = django_capture_on_commit_callbacks(execute=True)
            return self._ctx.__enter__()

        def __exit__(self, *exc):
            return self._ctx.__exit__(*exc)

    return Executor


def _receber(quant, quantidade: int):
    Move.objects.create(
        quant=quant, delta=Decimal(quantidade), kind=Move.Kind.MAKE, reason="fornada"
    )


def _vender(quant, quantidade: int):
    Move.objects.create(
        quant=quant, delta=Decimal(-quantidade), kind=Move.Kind.SELL, reason="venda"
    )


class TestObservingTheOutage:
    def test_selling_the_last_one_opens_the_outage(self, vitrine, canal, pao, apos_commit):
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 5)
        assert not ShelfOutage.objects.filter(ended_at__isnull=True).exists()

        with apos_commit():
            _vender(quant, 5)

        outage = ShelfOutage.objects.get(sku="PAO", channel_ref="web")
        assert outage.is_open

    def test_restocking_closes_the_outage(self, vitrine, canal, pao, apos_commit):
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 5)
            _vender(quant, 5)

        with apos_commit():
            _receber(quant, 3)

        outage = ShelfOutage.objects.get(sku="PAO", channel_ref="web")
        assert not outage.is_open
        assert ShelfOutage.objects.count() == 1

    def test_reserving_everything_takes_the_product_off_the_shelf(
        self, vitrine, canal, pao, apos_commit
    ):
        """A falta que o ledger não vê: unidades na loja, todas reservadas.

        Este é o caso que motivou o model — o cliente não consegue comprar
        embora o estoque físico ainda esteja lá.
        """
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 4)

        with apos_commit():
            Hold.objects.create(
                sku="PAO", quant=quant, quantity=Decimal("4"),
                target_date=timezone.localdate(),
                expires_at=timezone.now() + timedelta(hours=1),
            )

        assert ShelfOutage.objects.filter(sku="PAO", ended_at__isnull=True).exists()
        quant.refresh_from_db()
        assert quant.quantity == Decimal("4")  # o físico segue intacto

    def test_paused_product_is_not_a_shortage(self, vitrine, canal, pao, apos_commit):
        """Pausar é decisão comercial; misturar com falta mentiria sobre produção."""
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 5)
        Product.objects.filter(sku="PAO").update(is_sellable=False)

        with apos_commit():
            _vender(quant, 5)

        assert not ShelfOutage.objects.exists()

    def test_only_one_open_outage_per_sku_and_channel(self, vitrine, canal, pao, apos_commit):
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 5)
        with apos_commit():
            _vender(quant, 3)
        with apos_commit():
            _vender(quant, 2)

        assert ShelfOutage.objects.filter(sku="PAO", ended_at__isnull=True).count() == 1


class TestReconciliation:
    def test_expired_reservation_is_noticed_by_the_sweep(self, vitrine, canal, pao, apos_commit):
        """Reserva que expira sai por update em massa, sem signal.

        Sem a reconciliação, a volta do produto só seria percebida no próximo
        movimento de estoque — que pode ser no dia seguinte, inflando a falta.
        """
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 4)
        with apos_commit():
            hold = Hold.objects.create(
                sku="PAO", quant=quant, quantity=Decimal("4"),
                target_date=timezone.localdate(),
                expires_at=timezone.now() + timedelta(hours=1),
            )
        assert ShelfOutage.objects.filter(ended_at__isnull=True).exists()

        # Expira sem emitir signal — exatamente como o sweep faz.
        Hold.objects.filter(pk=hold.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        assert ShelfOutage.objects.filter(ended_at__isnull=True).exists()

        call_command("reconcile_shelf_outages")

        assert not ShelfOutage.objects.filter(ended_at__isnull=True).exists()

    def test_reconciling_twice_changes_nothing(self, vitrine, canal, pao, apos_commit):
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 2)
            _vender(quant, 2)

        first = shelf_outages.reconcile_outages()
        second = shelf_outages.reconcile_outages()

        assert second["opened"] == 0
        assert second["closed"] == 0
        assert first["checked"] == second["checked"]


class TestReadingTheOutage:
    def test_hours_are_clipped_to_business_hours(self, vitrine, canal, pao):
        """Faltar de madrugada não custa venda."""
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        tz = timezone.get_current_timezone()
        ShelfOutage.objects.create(
            sku="PAO", channel_ref="web",
            started_at=timezone.datetime(
                yesterday.year, yesterday.month, yesterday.day, 3, 0, tzinfo=tz
            ),
            ended_at=timezone.datetime(
                yesterday.year, yesterday.month, yesterday.day, 12, 0, tzinfo=tz
            ),
        )

        report = build_bi_explore(
            metric="unavailable_hours", by="sku",
            date_from=today - timedelta(days=3), date_to=today,
        )

        # Falta das 3h às 12h, expediente 9h–18h: contam três horas.
        assert [(row.key, row.value) for row in report.rows] == [("PAO", 3.0)]

    def test_outage_spanning_days_is_split_per_day(self, vitrine, canal, pao):
        today = timezone.localdate()
        start = today - timedelta(days=3)
        tz = timezone.get_current_timezone()
        ShelfOutage.objects.create(
            sku="PAO", channel_ref="web",
            started_at=timezone.datetime(
                start.year, start.month, start.day, 15, 0, tzinfo=tz
            ),
            ended_at=timezone.datetime(
                (start + timedelta(days=1)).year,
                (start + timedelta(days=1)).month,
                (start + timedelta(days=1)).day, 11, 0, tzinfo=tz,
            ),
        )

        report = build_bi_explore(
            metric="unavailable_hours", by="time",
            date_from=today - timedelta(days=5), date_to=today,
        )
        por_dia = {row.key: row.value for row in report.rows}

        assert por_dia[start.isoformat()] == 3.0                      # 15h→18h
        assert por_dia[(start + timedelta(days=1)).isoformat()] == 2.0  # 9h→11h

    def test_open_outage_counts_up_to_now(self, vitrine, canal, pao):
        """Falta em curso segue contando: parar fingiria que o produto voltou."""
        today = timezone.localdate()
        ShelfOutage.objects.create(
            sku="PAO", channel_ref="web",
            started_at=timezone.now() - timedelta(days=1),
        )

        report = build_bi_explore(
            metric="unavailable_hours", by="sku",
            date_from=today - timedelta(days=2), date_to=today,
        )

        assert report.rows and report.rows[0].value > 0

    def test_channel_is_a_dimension_because_availability_is_per_channel(
        self, vitrine, canal, pao
    ):
        today = timezone.localdate()
        tz = timezone.get_current_timezone()
        for channel_ref in ("web", "pdv"):
            ShelfOutage.objects.create(
                sku="PAO", channel_ref=channel_ref,
                started_at=timezone.datetime(
                    today.year, today.month, today.day, 10, 0, tzinfo=tz
                ),
                ended_at=timezone.datetime(
                    today.year, today.month, today.day, 12, 0, tzinfo=tz
                ),
            )

        report = build_bi_explore(
            metric="unavailable_hours", by="channel",
            date_from=today - timedelta(days=1), date_to=today,
        )

        assert {row.key for row in report.rows} == {"web", "pdv"}
