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

from shopman.backstage.models import OutageReason, ShelfOutage
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
def expediente(canal):
    """Carimba o expediente dos dias da janela — o denominador das métricas."""
    from shopman.backstage.services.business_day import stamp_day

    today = timezone.localdate()
    for offset in range(0, 6):
        stamp_day(today - timedelta(days=offset))


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

    def test_pausing_also_blocks_the_customer_and_is_recorded(
        self, vitrine, canal, pao, apos_commit
    ):
        """Pausado com estoque cheio: o cliente não compra, e isso conta.

        Para quem queria comprar tanto faz o motivo. O motivo importa para o
        gestor — e fica registrado para separar depois.
        """
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 5)
        assert not ShelfOutage.objects.exists()

        Product.objects.filter(sku="PAO").update(is_sellable=False)
        shelf_outages.observe("PAO")

        outage = ShelfOutage.objects.get(sku="PAO", ended_at__isnull=True)
        assert outage.reason == OutageReason.PAUSED
        quant.refresh_from_db()
        assert quant.quantity == Decimal("5")  # estoque intacto; a pausa é que bloqueia

    def test_unpausing_ends_the_block(self, vitrine, canal, pao, apos_commit):
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 5)
        Product.objects.filter(sku="PAO").update(is_sellable=False)
        shelf_outages.observe("PAO")

        Product.objects.filter(sku="PAO").update(is_sellable=True)
        shelf_outages.observe("PAO")

        assert not ShelfOutage.objects.filter(ended_at__isnull=True).exists()

    def test_changing_reason_splits_the_period(self, vitrine, canal, pao, apos_commit):
        """Despausar sem estoque não devolve o produto: o bloqueio continua.

        Fecha o período de pausa e abre o de falta no mesmo instante — contínuo
        para o cliente, atribuído ao motivo certo para o gestor.
        """
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        with apos_commit():
            _receber(quant, 5)
            _vender(quant, 5)
        Product.objects.filter(sku="PAO").update(is_sellable=False)
        shelf_outages.observe("PAO")
        assert (
            ShelfOutage.objects.get(ended_at__isnull=True).reason
            == OutageReason.PAUSED
        )

        Product.objects.filter(sku="PAO").update(is_sellable=True)
        shelf_outages.observe("PAO")

        aberto = ShelfOutage.objects.get(ended_at__isnull=True)
        assert aberto.reason == OutageReason.SOLD_OUT
        assert ShelfOutage.objects.filter(reason=OutageReason.PAUSED).count() == 1

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


class TestPausedTime:
    """Quanto tempo um produto ficou parado — métrica por si só."""

    def test_paused_hours_counts_only_the_pause(self, vitrine, canal, pao, expediente):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        tz = timezone.get_current_timezone()

        def _periodo(reason, de, ate):
            ShelfOutage.objects.create(
                sku="PAO", channel_ref="web", reason=reason,
                started_at=timezone.datetime(
                    yesterday.year, yesterday.month, yesterday.day, de, 0, tzinfo=tz
                ),
                ended_at=timezone.datetime(
                    yesterday.year, yesterday.month, yesterday.day, ate, 0, tzinfo=tz
                ),
            )

        _periodo(OutageReason.PAUSED, 9, 12)      # 3h pausado
        _periodo(OutageReason.SOLD_OUT, 14, 18)   # 4h esgotado

        janela = {"date_from": today - timedelta(days=3), "date_to": today}
        pausado = build_bi_explore(metric="paused_hours", by="sku", **janela)
        total = build_bi_explore(metric="unavailable_hours", by="sku", **janela)

        assert [(r.key, r.value) for r in pausado.rows] == [("PAO", 3.0)]
        # O total soma os dois: para o cliente, sete horas sem poder comprar.
        assert [(r.key, r.value) for r in total.rows] == [("PAO", 7.0)]

    def test_reason_is_a_dimension_of_the_total(self, vitrine, canal, pao, expediente):
        today = timezone.localdate()
        tz = timezone.get_current_timezone()
        for reason, de, ate in (
            (OutageReason.PAUSED, 9, 11),
            (OutageReason.SOLD_OUT, 15, 18),
        ):
            ShelfOutage.objects.create(
                sku="PAO", channel_ref="web", reason=reason,
                started_at=timezone.datetime(today.year, today.month, today.day, de, 0, tzinfo=tz),
                ended_at=timezone.datetime(today.year, today.month, today.day, ate, 0, tzinfo=tz),
            )

        report = build_bi_explore(
            metric="unavailable_hours", by="outage_reason",
            date_from=today - timedelta(days=1), date_to=today,
        )

        assert {r.label: r.value for r in report.rows} == {
            "Pausado": 2.0,
            "Esgotado": 3.0,
        }


class TestReadingTheOutage:
    def test_hours_are_clipped_to_business_hours(self, vitrine, canal, pao, expediente):
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

    def test_outage_spanning_days_is_split_per_day(self, vitrine, canal, pao, expediente):
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

    def test_open_outage_counts_up_to_now(self, vitrine, canal, pao, expediente):
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
        self, vitrine, canal, pao, expediente
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


class TestBusinessDayIsTheDenominator:
    """O expediente do dia é congelado; sem ele, não se calcula proporção."""

    def test_share_compares_days_of_different_length(self, vitrine, canal, pao):
        from shopman.backstage.models import DayContext
        from shopman.backstage.services.business_day import stamp_day

        today = timezone.localdate()
        longo = today - timedelta(days=2)   # expediente de 9h
        curto = today - timedelta(days=1)   # meio expediente
        tz = timezone.get_current_timezone()
        stamp_day(longo)
        stamp_day(curto)
        DayContext.objects.filter(date=curto).update(
            open_minutes=240, opens_at="09:00", closes_at="13:00"
        )

        for dia, fim in ((longo, 12), (curto, 12)):
            ShelfOutage.objects.create(
                sku="PAO", channel_ref="web",
                started_at=timezone.datetime(dia.year, dia.month, dia.day, 9, 0, tzinfo=tz),
                ended_at=timezone.datetime(dia.year, dia.month, dia.day, fim, 0, tzinfo=tz),
            )

        janela = {"date_from": today - timedelta(days=4), "date_to": today}
        horas = build_bi_explore(metric="unavailable_hours", by="time", **janela)
        share = build_bi_explore(metric="unavailable_share", by="time", **janela)

        por_dia_horas = {r.key: r.value for r in horas.rows}
        por_dia_share = {r.key: r.value for r in share.rows}
        # Mesmas três horas nos dois dias…
        assert por_dia_horas[longo.isoformat()] == 3.0
        assert por_dia_horas[curto.isoformat()] == 3.0
        # …mas pesos bem diferentes: 3h de 9h contra 3h de 4h.
        assert por_dia_share[longo.isoformat()] == 33.3
        assert por_dia_share[curto.isoformat()] == 75.0

    def test_closed_day_stamps_zero_and_leaves_the_reading(self, canal, pao):
        """Dia em que a casa não abriu não conta como falta.

        Antes, o expediente vinha do horário de HOJE e um feriado fechado
        aparecia como um dia inteiro sem produto.
        """
        from shopman.backstage.models import DayContext
        from shopman.backstage.services.business_day import stamp_day

        today = timezone.localdate()
        feriado = today - timedelta(days=1)
        shop = canal.shop
        shop.defaults = {
            "closed_dates": [{"date": feriado.isoformat(), "label": "Feriado"}]
        }
        shop.save()
        stamp_day(feriado)

        contexto = DayContext.objects.get(date=feriado)
        assert contexto.open_minutes == 0
        assert contexto.closed_reason
        assert contexto.was_open is False

        tz = timezone.get_current_timezone()
        ShelfOutage.objects.create(
            sku="PAO", channel_ref="web",
            started_at=timezone.datetime(feriado.year, feriado.month, feriado.day, 0, 0, tzinfo=tz),
            ended_at=timezone.datetime(today.year, today.month, today.day, 0, 0, tzinfo=tz),
        )

        report = build_bi_explore(
            metric="unavailable_hours", by="sku",
            date_from=feriado, date_to=feriado,
        )

        assert report.rows == ()

    def test_day_without_stamp_is_not_counted(self, vitrine, canal, pao):
        """Sem saber o expediente, contar horas seria inventar o denominador."""
        today = timezone.localdate()
        ontem = today - timedelta(days=1)
        tz = timezone.get_current_timezone()
        ShelfOutage.objects.create(
            sku="PAO", channel_ref="web",
            started_at=timezone.datetime(ontem.year, ontem.month, ontem.day, 10, 0, tzinfo=tz),
            ended_at=timezone.datetime(ontem.year, ontem.month, ontem.day, 12, 0, tzinfo=tz),
        )

        report = build_bi_explore(
            metric="unavailable_hours", by="sku",
            date_from=today - timedelta(days=3), date_to=today,
        )

        assert report.rows == ()
