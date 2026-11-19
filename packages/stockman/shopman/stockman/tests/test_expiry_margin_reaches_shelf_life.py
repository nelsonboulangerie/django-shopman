"""
A margem de validade alcança o saldo SEM lote (validade implícita).

``expiry_margin_days`` sempre valeu para o lote datado (``Batch.expiry_date``):
com margem N, sai do escopo o lote que vence a menos de N dias da data-alvo. O
saldo sem lote só era julgado por ``shelf_life_days``, e a margem não o
alcançava. É o caso de toda fornada PLANEJADA (quant com ``target_date`` e sem
lote) e do que está em produção (``started``): para um pão de um dia, a fornada
de quinta contava inteira para uma promessa de sexta, com qualquer margem.

Medido em 18/11/2026 no seed (issue #2693): baguete de um dia, 22 planejadas
para 19/11 e 28 para 20/11; a leitura de 20/11 devolvia 50, com margem 0 e com
margem 1.

Estes testes prendem as três pontas da regra:

- margem 0 não muda nada (o comportamento de sempre, em todo teste da suíte);
- com margem, o saldo sem lote vale enquanto ``produção + shelf_life_days >=
  alvo + margem``, a mesma conta do lote;
- a fornada planejada PARA a data-alvo sempre conta, com qualquer validade
  (inclusive zero): na data dela o produto é o do dia.

E as duas formas da regra (o filtro de queryset e o predicado em Python, que a
leitura em lote usa) dão a mesma resposta, como a leitura de uma data e a de
várias.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from itertools import product as cartesian
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.stockman import stock
from shopman.stockman.adapters.sku_validation import reset_sku_validator
from shopman.stockman.models import Batch, Hold, Position, PositionKind, Quant
from shopman.stockman.services.availability import (
    STARTED_BATCH,
    availability_for_sku,
    availability_for_skus,
    availability_for_skus_on_dates,
)
from shopman.stockman.services.scope import quants_eligible_for
from shopman.stockman.shelflife import filter_valid_quants, is_valid_for_date
from shopman.stockman.tests.fakes import OrderableSkuValidator

pytestmark = pytest.mark.django_db

DAY = timedelta(days=1)

#: Validade por SKU neste arquivo. O que não está aqui não vence.
SHELF_LIFE = {"PAO-1D": 1, "CROISSANT-0D": 0, "BOLO-3D": 3, "QUEIJO-20D": 20}


class ShelfLifeBySkuValidator(OrderableSkuValidator):
    def get_sku_info(self, sku: str):
        return replace(super().get_sku_info(sku), shelflife_days=SHELF_LIFE.get(sku))


@pytest.fixture(autouse=True)
def _shelf_life_validator(settings):
    settings.STOCKMAN = {
        **getattr(settings, "STOCKMAN", {}),
        "SKU_VALIDATOR": f"{__name__}.ShelfLifeBySkuValidator",
    }
    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.fixture
def hoje():
    return timezone.localdate()


@pytest.fixture
def vitrine_pos(db):
    position, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return position


@pytest.fixture
def producao_pos(db):
    position, _ = Position.objects.get_or_create(
        ref="producao",
        defaults={"name": "Produção", "kind": PositionKind.PHYSICAL, "is_saleable": False},
    )
    return position


def _quant(sku, position, qty, *, target=None, batch="", created_days_ago=0):
    quant = Quant.objects.create(
        sku=sku, position=position, target_date=target, batch=batch, _quantity=Decimal(str(qty)),
    )
    if created_days_ago:
        Quant.objects.filter(pk=quant.pk).update(created_at=quant.created_at - created_days_ago * DAY)
        quant.refresh_from_db()
    return quant


# ── A regra, sem banco ───────────────────────────────────────────────────────


def _planned(target_date):
    return SimpleNamespace(target_date=target_date, created_at=timezone.now())


def _physical(created_days_ago=0):
    return SimpleNamespace(target_date=None, created_at=timezone.now() - created_days_ago * DAY)


class TestThePredicate:
    def test_margin_zero_is_the_historical_window(self, hoje):
        pao = SimpleNamespace(shelf_life_days=1)

        assert is_valid_for_date(_planned(hoje), pao, hoje + DAY) is True
        assert is_valid_for_date(_physical(), pao, hoje + DAY) is True
        assert is_valid_for_date(_planned(hoje), pao, hoje + DAY, margin_days=0) is True

    def test_batch_of_the_eve_does_not_count_with_a_margin(self, hoje):
        """Pão de um dia: a fornada de hoje não lastreia a data de amanhã."""
        pao = SimpleNamespace(shelf_life_days=1)

        assert is_valid_for_date(_planned(hoje), pao, hoje + DAY, margin_days=1) is False
        assert is_valid_for_date(_physical(), pao, hoje + DAY, margin_days=1) is False

    @pytest.mark.parametrize("shelf_life", [0, 1, 3, 20])
    @pytest.mark.parametrize("margin", [0, 1, 2, 5])
    def test_batch_planned_for_the_target_date_always_counts(self, hoje, shelf_life, margin):
        product = SimpleNamespace(shelf_life_days=shelf_life)

        assert is_valid_for_date(_planned(hoje + DAY), product, hoje + DAY, margin_days=margin) is True

    def test_plan_after_the_target_never_counts(self, hoje):
        product = SimpleNamespace(shelf_life_days=3)

        assert is_valid_for_date(_planned(hoje + 2 * DAY), product, hoje + DAY, margin_days=1) is False

    def test_long_shelf_life_keeps_backing_until_the_eve_of_expiry(self, hoje):
        """Queijo de 20 dias criado hoje vence em hoje+20: lastreia até hoje+19."""
        queijo = SimpleNamespace(shelf_life_days=20)

        assert is_valid_for_date(_physical(), queijo, hoje + DAY, margin_days=1) is True
        assert is_valid_for_date(_physical(), queijo, hoje + 19 * DAY, margin_days=1) is True
        assert is_valid_for_date(_physical(), queijo, hoje + 20 * DAY, margin_days=1) is False
        assert is_valid_for_date(_physical(), queijo, hoje + 20 * DAY, margin_days=0) is True

    def test_no_shelf_life_ignores_the_margin(self, hoje):
        lata = SimpleNamespace(shelf_life_days=None)

        assert is_valid_for_date(_physical(created_days_ago=400), lata, hoje + DAY, margin_days=7) is True
        assert is_valid_for_date(_planned(hoje), lata, hoje + DAY, margin_days=7) is True

    def test_negative_margin_is_no_margin(self, hoje):
        pao = SimpleNamespace(shelf_life_days=1)

        assert is_valid_for_date(_planned(hoje), pao, hoje + DAY, margin_days=-3) is True


# ── Queryset ≡ predicado ─────────────────────────────────────────────────────


def test_queryset_filter_and_python_predicate_agree(hoje, vitrine_pos, producao_pos):
    """O hold filtra no banco; a leitura em lote decide em Python. Uma regra só."""
    for sku in ("PAO-1D", "CROISSANT-0D", "BOLO-3D"):
        _quant(sku, vitrine_pos, 5)
        _quant(sku, vitrine_pos, 4, batch="VELHO-1", created_days_ago=1)
        _quant(sku, vitrine_pos, 3, batch="VELHO-2", created_days_ago=2)
        _quant(sku, vitrine_pos, 2, batch="VELHO-4", created_days_ago=4)
        for offset in (-1, 0, 1, 2, 3):
            _quant(sku, producao_pos, 10 + offset, target=hoje + offset * DAY)

    for sku, margin, offset in cartesian(("PAO-1D", "CROISSANT-0D", "BOLO-3D"), (0, 1, 2, 4), range(-1, 5)):
        target = hoje + offset * DAY
        ns = SimpleNamespace(sku=sku, shelf_life_days=SHELF_LIFE[sku])
        every = Quant.objects.filter(sku=sku)
        by_queryset = set(filter_valid_quants(every, ns, target, margin_days=margin).values_list("pk", flat=True))
        by_python = {q.pk for q in every if is_valid_for_date(q, ns, target, margin_days=margin)}
        assert by_queryset == by_python, (sku, margin, offset)


# ── O cenário medido: baguete de um dia, hoje e as fornadas ──────────────────


@pytest.fixture
def baguete(hoje, vitrine_pos, producao_pos):
    """18/11 no seed: 22 na vitrine (lote de hoje, vence amanhã), 2 da sobra de
    ontem (vence hoje), fornada de hoje ainda no forno, e o plano dos dias."""
    sku = "PAO-1D"
    Batch.objects.create(sku=sku, ref="PAO-HOJE", production_date=hoje, expiry_date=hoje + DAY)
    Batch.objects.create(sku=sku, ref="PAO-ONTEM", production_date=hoje - DAY, expiry_date=hoje)
    return SimpleNamespace(
        sku=sku,
        vitrine=_quant(sku, vitrine_pos, 22, batch="PAO-HOJE"),
        sobra=_quant(sku, vitrine_pos, 2, batch="PAO-ONTEM", created_days_ago=1),
        no_forno=_quant(sku, producao_pos, 6, target=hoje, batch=STARTED_BATCH),
        amanha=_quant(sku, producao_pos, 22, target=hoje + DAY),
        depois=_quant(sku, producao_pos, 28, target=hoje + 2 * DAY),
    )


class TestTheMeasuredScenario:
    def test_today_is_untouched(self, baguete, hoje):
        """A leitura de HOJE (margem 0): vitrine, sobra de ontem e o que está no forno."""
        eligible = {q.pk for q in quants_eligible_for(baguete.sku, target_date=hoje)}

        assert eligible == {baguete.vitrine.pk, baguete.sobra.pk, baguete.no_forno.pk}
        info = availability_for_sku(baguete.sku, target_date=hoje)
        assert info["breakdown"] == {"ready": Decimal("24"), "in_production": Decimal("6"), "planned": Decimal("0")}

    def test_without_margin_tomorrow_counts_todays_bread(self, baguete, hoje):
        """O defeito, que continua sendo a resposta de quem NÃO pede margem."""
        info = availability_for_sku(baguete.sku, target_date=hoje + DAY)

        assert info["total_promisable"] == Decimal("50")  # 22 vitrine + 6 no forno + 22 planejadas

    def test_with_margin_tomorrow_counts_only_tomorrows_batch(self, baguete, hoje):
        eligible = {q.pk for q in quants_eligible_for(baguete.sku, target_date=hoje + DAY, expiry_margin_days=1)}

        assert eligible == {baguete.amanha.pk}
        info = availability_for_sku(baguete.sku, target_date=hoje + DAY, expiry_margin_days=1)
        assert info["total_promisable"] == Decimal("22")
        assert info["breakdown"] == {"ready": Decimal("0"), "in_production": Decimal("0"), "planned": Decimal("22")}

    def test_with_margin_the_day_after_counts_only_its_own_batch(self, baguete, hoje):
        """A porta que a margem do lote não fechava: fornada planejada da véspera."""
        without = availability_for_sku(baguete.sku, target_date=hoje + 2 * DAY)
        with_margin = availability_for_sku(baguete.sku, target_date=hoje + 2 * DAY, expiry_margin_days=1)

        assert without["total_promisable"] == Decimal("50")  # 22 de amanhã + 28 da data
        assert with_margin["total_promisable"] == Decimal("28")

    def test_single_read_and_batch_read_agree(self, baguete, hoje):
        for offset, margin in cartesian(range(0, 4), (0, 1, 2)):
            target = hoje + offset * DAY
            single = availability_for_sku(baguete.sku, target_date=target, expiry_margin_days=margin)
            batch = availability_for_skus([baguete.sku], target_date=target, expiry_margin_days=margin)[baguete.sku]
            for key in ("total_promisable", "available", "expected", "planned", "ready_physical", "breakdown"):
                assert single[key] == batch[key], (offset, margin, key)


# ── A reserva ancora onde a leitura contou ───────────────────────────────────


class TestTheHoldFollowsTheRead:
    def test_without_margin_fefo_anchors_tomorrows_order_on_todays_lot(self, baguete, hoje):
        """Medido: sem margem, a reserva para amanhã prende primeiro o lote de HOJE."""
        product = SimpleNamespace(sku=baguete.sku, shelf_life_days=1)

        hold_id = stock.hold(Decimal("5"), product, target_date=hoje + DAY)

        hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
        assert hold.quant_id == baguete.vitrine.pk

    def test_with_margin_tomorrows_order_anchors_on_tomorrows_batch(self, baguete, hoje):
        product = SimpleNamespace(sku=baguete.sku, shelf_life_days=1)

        hold_id = stock.hold(Decimal("5"), product, target_date=hoje + DAY, expiry_margin_days=1)

        hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
        assert hold.quant_id == baguete.amanha.pk
        assert hold.quant.target_date == hoje + DAY

    def test_with_margin_the_hold_refuses_what_the_read_refuses(self, baguete, hoje):
        """23 para amanhã contra uma fornada de 22: nem leitura nem reserva aprovam."""
        from shopman.stockman.exceptions import StockError
        from shopman.stockman.services.availability import promise_for_sku

        product = SimpleNamespace(sku=baguete.sku, shelf_life_days=1)
        decision = promise_for_sku(baguete.sku, Decimal("23"), target_date=hoje + DAY, expiry_margin_days=1)

        assert decision.approved is False
        assert decision.available_qty == Decimal("22")
        with pytest.raises(StockError):
            stock.hold(Decimal("23"), product, target_date=hoje + DAY, expiry_margin_days=1)


# ── Várias datas, uma varredura, cada data com a margem dela ─────────────────


class TestMarginByDate:
    def test_each_date_equals_its_own_single_date_read(self, baguete, hoje):
        dates = [hoje, hoje + DAY, hoje + 2 * DAY, hoje + 3 * DAY]
        margins = {hoje + DAY: 1, hoje + 2 * DAY: 1, hoje + 3 * DAY: 2}  # hoje fica fora do mapa: margem base

        by_date = availability_for_skus_on_dates(
            [baguete.sku], dates, expiry_margin_days=0, expiry_margin_days_by_date=margins,
        )

        for target in dates:
            alone = availability_for_skus([baguete.sku], target_date=target, expiry_margin_days=margins.get(target, 0))
            assert by_date[target] == alone, target
        assert by_date[hoje][baguete.sku]["breakdown"]["ready"] == Decimal("24")
        assert by_date[hoje + DAY][baguete.sku]["total_promisable"] == Decimal("22")
        assert by_date[hoje + 2 * DAY][baguete.sku]["total_promisable"] == Decimal("28")

    def test_date_missing_from_the_map_uses_the_base_margin(self, baguete, hoje):
        by_date = availability_for_skus_on_dates(
            [baguete.sku], [hoje, hoje + DAY], expiry_margin_days=1, expiry_margin_days_by_date={hoje: 0},
        )

        assert by_date[hoje][baguete.sku]["breakdown"]["ready"] == Decimal("24")
        assert by_date[hoje + DAY][baguete.sku]["total_promisable"] == Decimal("22")

    def test_lot_cutoff_follows_the_margin_of_each_date(self, hoje, vitrine_pos):
        """Lote que vence em D: fora de D quando a margem de D é 1, dentro de D-1."""
        Batch.objects.create(sku="QUEIJO-20D", ref="Q-1", production_date=hoje, expiry_date=hoje + 3 * DAY)
        _quant("QUEIJO-20D", vitrine_pos, 7, batch="Q-1")
        dates = [hoje + 2 * DAY, hoje + 3 * DAY]

        by_date = availability_for_skus_on_dates(
            ["QUEIJO-20D"], dates, expiry_margin_days_by_date=dict.fromkeys(dates, 1),
        )

        assert by_date[hoje + 2 * DAY]["QUEIJO-20D"]["total_promisable"] == Decimal("7")
        assert by_date[hoje + 3 * DAY]["QUEIJO-20D"]["total_promisable"] == Decimal("0")

    def test_the_map_costs_no_extra_query(self, baguete, hoje):
        dates = [hoje, hoje + DAY, hoje + 2 * DAY]
        with CaptureQueriesContext(connection) as plain:
            availability_for_skus_on_dates([baguete.sku], dates)
        with CaptureQueriesContext(connection) as mapped:
            availability_for_skus_on_dates(
                [baguete.sku], dates, expiry_margin_days_by_date=dict.fromkeys(dates[1:], 1),
            )

        assert len(mapped.captured_queries) == len(plain.captured_queries)


# ── O dia de produção do saldo físico de lote é o do lote ────────────────────
#
# O ``created_at`` do saldo é o dia em que ele entrou no estoque. O lote de
# amanhã fechado hoje à noite é pão de amanhã: com margem, julgá-lo pelo
# ``created_at`` o tirava da encomenda de amanhã (a falha que tirou o #2703 da
# fila, em ``test_iniciar_lote_leva_a_reserva``). A margem de um saldo físico de
# lote é julgada na ``production_date`` do lote, pela régua da fornada planejada.


class TestTheLotAnswersForItsProductionDay:
    def test_the_predicate_judges_the_margin_on_the_lot_date(self, hoje):
        pao = SimpleNamespace(shelf_life_days=1)
        amanha = hoje + DAY
        quant = _physical()

        assert is_valid_for_date(quant, pao, amanha, margin_days=1) is False, "sem lote: pão de hoje"
        assert is_valid_for_date(quant, pao, amanha, margin_days=1, lot_production_date=amanha) is True
        assert is_valid_for_date(quant, pao, amanha, margin_days=1, lot_production_date=hoje) is False

    def test_the_unmargined_window_on_created_at_still_holds(self, hoje):
        """O lote declara a data, mas o saldo entrou há dois dias: fora, como sempre foi."""
        pao = SimpleNamespace(shelf_life_days=1)
        velho = _physical(created_days_ago=2)

        assert is_valid_for_date(velho, pao, hoje + DAY, margin_days=1, lot_production_date=hoje + DAY) is False
        assert is_valid_for_date(velho, pao, hoje + DAY, margin_days=0) is False

    def test_without_margin_the_lot_date_changes_nothing(self, hoje):
        pao = SimpleNamespace(shelf_life_days=1)
        for created_days_ago, lot_offset in cartesian((0, 1, 2), (-2, -1, 0, 1, 2)):
            quant = _physical(created_days_ago)
            for target_offset in (-1, 0, 1, 2):
                target = hoje + target_offset * DAY
                with_lot = is_valid_for_date(quant, pao, target, lot_production_date=hoje + lot_offset * DAY)
                assert with_lot is is_valid_for_date(quant, pao, target), (created_days_ago, lot_offset, target_offset)

    @pytest.fixture
    def vespera(self, hoje, vitrine_pos, producao_pos):
        """Hoje à noite: a fornada de hoje na vitrine, a de amanhã já fechada, e os desvios."""
        sku = "PAO-1D"
        amanha = hoje + DAY
        Batch.objects.create(sku=sku, ref="PAO-HOJE", production_date=hoje, expiry_date=amanha)
        Batch.objects.create(sku=sku, ref="PAO-AMANHA", production_date=amanha, expiry_date=amanha + DAY)
        # Fechado pela tela sem validade na ficha: o lote só declara a produção.
        Batch.objects.create(sku=sku, ref="PAO-AMANHA-SEM-VALIDADE", production_date=amanha)
        Batch.objects.create(sku=sku, ref="PAO-SEM-DATA")
        return SimpleNamespace(
            sku=sku,
            hoje=_quant(sku, vitrine_pos, 22, batch="PAO-HOJE"),
            amanha=_quant(sku, vitrine_pos, 10, batch="PAO-AMANHA"),
            amanha_sem_validade=_quant(sku, vitrine_pos, 4, batch="PAO-AMANHA-SEM-VALIDADE"),
            sem_data=_quant(sku, vitrine_pos, 3, batch="PAO-SEM-DATA"),
            sem_batch=_quant(sku, vitrine_pos, 5, batch="LOTE-SEM-CADASTRO"),
            sem_lote=_quant(sku, vitrine_pos, 2),
            planejado_hoje=_quant(sku, producao_pos, 6, target=hoje),
            no_forno=_quant(sku, producao_pos, 7, target=hoje, batch=STARTED_BATCH),
        )

    def test_tomorrows_lot_closed_today_counts_for_tomorrow(self, vespera, hoje):
        amanha = hoje + DAY

        eligible = {q.pk for q in quants_eligible_for(vespera.sku, target_date=amanha, expiry_margin_days=1)}

        assert eligible == {vespera.amanha.pk, vespera.amanha_sem_validade.pk}
        info = availability_for_sku(vespera.sku, target_date=amanha, expiry_margin_days=1)
        assert info["total_promisable"] == Decimal("14")
        assert info["breakdown"] == {"ready": Decimal("14"), "in_production": Decimal("0"), "planned": Decimal("0")}

    def test_todays_bread_stays_out_of_tomorrow(self, vespera, hoje):
        eligible = {q.pk for q in quants_eligible_for(vespera.sku, target_date=hoje + DAY, expiry_margin_days=1)}

        assert vespera.hoje.pk not in eligible, "lote de hoje: sai pela data do lote"
        assert vespera.sem_lote.pk not in eligible, "físico sem lote: sai pelo created_at"

    def test_the_eve_planned_batch_stays_out_of_tomorrow(self, vespera, hoje):
        eligible = {q.pk for q in quants_eligible_for(vespera.sku, target_date=hoje + DAY, expiry_margin_days=1)}

        assert vespera.planejado_hoje.pk not in eligible
        assert vespera.no_forno.pk not in eligible

    def test_a_lot_that_declares_nothing_gets_no_pass(self, vespera, hoje):
        """Lote nomeado sem ``Batch`` e ``Batch`` sem data de produção: a margem cai no ``created_at``."""
        eligible = {q.pk for q in quants_eligible_for(vespera.sku, target_date=hoje + DAY, expiry_margin_days=1)}

        assert vespera.sem_batch.pk not in eligible
        assert vespera.sem_data.pk not in eligible

    def test_today_reads_everything_as_before(self, vespera, hoje):
        eligible = {q.pk for q in quants_eligible_for(vespera.sku, target_date=hoje)}

        assert eligible == {
            vespera.hoje.pk, vespera.amanha.pk, vespera.amanha_sem_validade.pk, vespera.sem_data.pk,
            vespera.sem_batch.pk, vespera.sem_lote.pk, vespera.planejado_hoje.pk, vespera.no_forno.pk,
        }

    def test_the_scope_query_and_the_batch_read_give_the_same_number(self, vespera, hoje):
        """A consulta do escopo (a da reserva) e a leitura em lote, data a data e margem a margem."""
        for offset, margin in cartesian(range(-1, 4), (0, 1, 2)):
            target = hoje + offset * DAY
            by_scope = sum(
                (q.quantity for q in quants_eligible_for(vespera.sku, target_date=target, expiry_margin_days=margin)),
                Decimal("0"),
            )
            single = availability_for_sku(vespera.sku, target_date=target, expiry_margin_days=margin)
            batch = availability_for_skus([vespera.sku], target_date=target, expiry_margin_days=margin)[vespera.sku]
            on_dates = availability_for_skus_on_dates(
                [vespera.sku], [target], expiry_margin_days_by_date={target: margin},
            )[target][vespera.sku]
            numbers = {
                "escopo": by_scope,
                "uma data": single["total_promisable"],
                "em lote": batch["total_promisable"],
                "por datas": on_dates["total_promisable"],
            }
            assert len(set(numbers.values())) == 1, (offset, margin, numbers)

    def test_queryset_filter_and_python_predicate_agree_with_lots(self, vespera, hoje):
        every = Quant.objects.filter(sku=vespera.sku)
        lots = Batch.objects.filter(sku=vespera.sku)
        production = dict(lots.exclude(production_date=None).values_list("ref", "production_date"))
        ns = SimpleNamespace(sku=vespera.sku, shelf_life_days=1)

        for margin, offset in cartesian((0, 1, 2), range(-1, 4)):
            target = hoje + offset * DAY
            by_queryset = set(
                filter_valid_quants(every, ns, target, margin_days=margin, lots=lots).values_list("pk", flat=True)
            )
            by_python = {
                q.pk
                for q in every
                if is_valid_for_date(q, ns, target, margin_days=margin, lot_production_date=production.get(q.batch))
            }
            assert by_queryset == by_python, (margin, offset)

    def test_the_hold_for_tomorrow_anchors_on_tomorrows_lot(self, vespera, hoje):
        from shopman.stockman.exceptions import StockError

        product = SimpleNamespace(sku=vespera.sku, shelf_life_days=1)

        hold_id = stock.hold(Decimal("8"), product, target_date=hoje + DAY, expiry_margin_days=1)

        hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
        assert hold.quant_id == vespera.amanha.pk
        with pytest.raises(StockError):
            stock.hold(Decimal("7"), product, target_date=hoje + DAY, expiry_margin_days=1)

    def test_the_lots_cost_no_extra_query(self, vespera, hoje):
        dates = [hoje, hoje + DAY, hoje + 2 * DAY]
        with CaptureQueriesContext(connection) as plain:
            availability_for_skus_on_dates([vespera.sku], dates)
        with CaptureQueriesContext(connection) as mapped:
            availability_for_skus_on_dates(
                [vespera.sku], dates, expiry_margin_days_by_date=dict.fromkeys(dates[1:], 1),
            )

        assert len(mapped.captured_queries) == len(plain.captured_queries)
