"""A sobra de hoje não lastreia encomenda (#2693, #2685).

Regra do dono (18/11/2026): "'a vitrine de hoje ainda vale amanhã': isso é
controverso! não oferecemos pães de um dia para o outro! eles não ficam
disponíveis para encomenda!"

O que foi medido no seed de 18/11 (baguete de um dia, ``shelf_life_days = 1``):
22 na vitrine de hoje (lote que vence amanhã) e 22 planejadas para amanhã. A
leitura de amanhã devolvia 44 no balcão e 42 na loja online, no WhatsApp e no
iFood; a loja aceitava 30 baguetes para amanhã contra uma fornada de 22. Para
depois de amanhã entrava a fornada da véspera (50 = 22 + 28). E a encomenda
acima do plano gravava a reserva INTEIRA como demanda, sem prender a fornada.

O cenário aqui é o medido, com a configuração de estoque de cada canal lida do
descritor da casa (``config/instances/nelson.json``), nos quatro canais que
vendem: ``pdv``, ``web``, ``whatsapp`` e ``ifood``.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.exceptions import ValidationError
from shopman.stockman import stock
from shopman.stockman.models import Batch, Hold, Position, PositionKind, Quant

from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.models import Channel, Shop
from shopman.shop.policies.promise_expiry_margin import (
    FUTURE_TARGET_EXPIRY_MARGIN_DAYS,
    expiry_margin_for_target,
)
from shopman.shop.projections import catalog_context
from shopman.shop.services import availability, waitlist
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db

DAY = timedelta(days=1)
NELSON_DESCRIPTOR = Path(__file__).resolve().parents[3] / "config" / "instances" / "nelson.json"
CHANNELS = ("pdv", "web", "whatsapp", "ifood")
REMOTE = ("web", "whatsapp", "ifood")
# Canais com portão de commit (``lifecycle`` chama ``stock.hold(require_all=True)``).
GATED = ("web", "whatsapp")

BAGUETE = "TRADI"  # pão de um dia
QUEIJO = "CAMEMBERT"  # 20 dias de validade
GELEIA = "GELEIA"  # revenda sem validade cadastrada

ABERTO_TODO_DIA = {
    day: {"open": "08:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


def _hoje():
    return timezone.localdate()


def _descriptor_overrides(ref: str) -> dict:
    """A configuração do canal como a casa a declara, só os aspectos que a reserva lê."""
    descriptor = json.loads(NELSON_DESCRIPTOR.read_text())
    [entry] = [c for c in descriptor["bootstrap"]["channels"] if c["ref"] == ref]
    overrides = entry["config"]["overrides"]
    return {key: overrides[key] for key in ("confirmation", "payment", "stock", "waitlist") if key in overrides}


def _position(ref: str, *, saleable: bool) -> Position:
    position, _ = Position.objects.get_or_create(
        ref=ref,
        defaults={"name": ref.title(), "kind": PositionKind.PHYSICAL, "is_saleable": saleable},
    )
    return position


def _lot(sku: str, ref: str, *, produced, expires, grade: str = "standard", percent: int = 0) -> None:
    Batch.objects.create(
        sku=sku, ref=ref, production_date=produced, expiry_date=expires,
        quality_grade_ref=grade, nonconformity_percent=percent,
    )


@pytest.fixture
def casa():
    """18/11 no seed: vitrine de hoje, o "Ontem" com desconto, e o plano dos dias."""
    hoje = _hoje()
    Shop.objects.create(name="Nelson", brand_name="Nelson", opening_hours=ABERTO_TODO_DIA)
    for ref in CHANNELS:
        Channel.objects.create(ref=ref, name=ref, is_active=True, config=_descriptor_overrides(ref))
    pao = Product.objects.create(
        sku=BAGUETE, name="Baguette de Tradition", base_price_q=1600,
        shelf_life_days=1, is_published=True, is_sellable=True,
    )
    Product.objects.create(
        sku=QUEIJO, name="Camembert", base_price_q=4200, shelf_life_days=20, is_published=True, is_sellable=True,
    )
    Product.objects.create(sku=GELEIA, name="Geleia", base_price_q=2800, is_published=True, is_sellable=True)
    vitrine = _position("vitrine", saleable=True)
    producao = _position("producao", saleable=False)

    # A fornada de hoje, na vitrine: lote de hoje, vence amanhã, preço cheio.
    _lot(BAGUETE, "TRADI-HOJE", produced=hoje, expires=hoje + DAY)
    stock.receive(quantity=Decimal("22"), sku=BAGUETE, position=vitrine, batch="TRADI-HOJE", reason="fornada")
    # O "Ontem": sobra da fornada de ontem, vence hoje, com desconto, só no balcão.
    _lot(BAGUETE, "TRADI-ONTEM", produced=hoje - DAY, expires=hoje, grade="fair", percent=30)
    stock.receive(quantity=Decimal("2"), sku=BAGUETE, position=vitrine, batch="TRADI-ONTEM", reason="sobra")
    # O plano: 22 para amanhã, 28 para depois de amanhã.
    stock.plan(quantity=Decimal("22"), product=pao, target_date=hoje + DAY, position=producao, reason="fornada")
    stock.plan(quantity=Decimal("28"), product=pao, target_date=hoje + 2 * DAY, position=producao, reason="fornada")

    # Mercadoria de validade longa: lote do queijo vence em dez dias; geleia não vence.
    _lot(QUEIJO, "CAMEMBERT-L1", produced=hoje - 10 * DAY, expires=hoje + 10 * DAY)
    stock.receive(quantity=Decimal("12"), sku=QUEIJO, position=vitrine, batch="CAMEMBERT-L1", reason="compra")
    stock.receive(quantity=Decimal("9"), sku=GELEIA, position=vitrine, reason="compra")
    return hoje


def _available(sku: str, channel: str, target) -> Decimal:
    [answer] = availability.decide_many([(sku, Decimal("1"))], channel_ref=channel, target_date=target)
    return Decimal(str(answer["available_qty"]))


def _hold(hold_id: str) -> Hold:
    return Hold.objects.select_related("quant").get(pk=int(hold_id.split(":")[1]))


def _order(channel: str, sku: str, qty, target, *, ref: str):
    order = MagicMock()
    order.ref = ref
    order.channel_ref = channel
    order.session_key = None
    order.data = {"delivery_date": target.isoformat()}
    order.snapshot = {
        "items": [{"sku": sku, "name": "Baguette de Tradition", "qty": qty, "line_id": "l1", "meta": {}}],
        "data": order.data,
    }
    order.items.all.return_value = []
    return order


def _order_holds(order) -> list[Hold]:
    pks = [int(str(entry["hold_id"]).split(":")[1]) for entry in order.data["hold_ids"]]
    return list(Hold.objects.select_related("quant").filter(pk__in=pks))


# ── A regra, sozinha ─────────────────────────────────────────────────────────


class TestTheRule:
    def test_today_keeps_the_channel_margin(self):
        hoje = _hoje()

        assert expiry_margin_for_target(0, hoje) == 0
        assert expiry_margin_for_target(0, None) == 0
        assert expiry_margin_for_target(3, hoje) == 3
        assert expiry_margin_for_target(0, hoje - DAY) == 0

    def test_future_target_asks_for_one_more_day_of_validity(self):
        hoje = _hoje()

        assert FUTURE_TARGET_EXPIRY_MARGIN_DAYS == 1
        assert expiry_margin_for_target(0, hoje + DAY) == 1
        assert expiry_margin_for_target(0, hoje + 30 * DAY) == 1
        assert expiry_margin_for_target(3, hoje + DAY) == 4

    def test_today_is_the_stores_today(self):
        hoje = _hoje()

        assert expiry_margin_for_target(0, hoje, today=hoje - DAY) == 1
        assert expiry_margin_for_target(0, hoje + DAY, today=hoje + DAY) == 0

    def test_missing_or_negative_margin_is_zero(self):
        assert expiry_margin_for_target(None, _hoje()) == 0
        assert expiry_margin_for_target(-2, _hoje()) == 0


# ── #2693: a leitura para data futura é a da fornada da data ─────────────────


@pytest.mark.parametrize("channel", CHANNELS)
class TestTheReadForAFutureDate:
    def test_tomorrow_is_tomorrows_batch_not_todays_showcase(self, casa, channel):
        """Antes: 44 no balcão, 42 nos remotos. Agora: as 22 da fornada de amanhã.

        A margem de segurança do canal desconta do PRONTO (vitrine), não da
        fornada planejada: por isso o número é 22 em todo canal.
        """
        assert _available(BAGUETE, channel, casa + DAY) == Decimal("22")

    def test_thirty_for_tomorrow_is_no_longer_approved(self, casa, channel):
        amanha = casa + DAY

        refused = availability.decide(BAGUETE, Decimal("30"), channel_ref=channel, target_date=amanha)
        covered = availability.decide(BAGUETE, Decimal("22"), channel_ref=channel, target_date=amanha)
        over_by_one = availability.check(BAGUETE, Decimal("23"), channel_ref=channel, target_date=amanha)

        assert refused["approved"] is False
        assert refused["reason_code"] == "insufficient_supply"
        assert refused["available_qty"] == Decimal("22")
        assert covered["approved"] is True
        assert over_by_one["ok"] is False

    def test_the_day_after_does_not_count_the_batch_of_the_eve(self, casa, channel):
        """Antes: 50 (22 de amanhã + 28 da data). A fornada planejada não tem lote."""
        assert _available(BAGUETE, channel, casa + 2 * DAY) == Decimal("28")

    def test_every_read_path_gives_the_same_number(self, casa, channel):
        amanha, depois = casa + DAY, casa + 2 * DAY
        scope = waitlist.scope_kwargs(channel)

        by_date = availability.stock_on_dates([BAGUETE], [casa, amanha, depois], **scope)
        catalog_many = catalog_context.availability_for_skus([BAGUETE], channel_ref=channel, target_date=amanha)
        catalog_one = catalog_context.availability_for_sku(BAGUETE, channel_ref=channel, target_date=amanha)

        assert by_date[amanha][BAGUETE]["total_promisable"] == Decimal("22")
        assert by_date[depois][BAGUETE]["total_promisable"] == Decimal("28")
        assert catalog_many[BAGUETE]["total_promisable"] == Decimal("22")
        assert catalog_one["total_promisable"] == Decimal("22")
        assert by_date[amanha][BAGUETE]["breakdown"]["ready"] == Decimal("0")

    def test_one_scan_reads_today_and_the_future_with_each_margin(self, casa, channel):
        """Hoje com a margem do canal e as datas futuras com a delas, numa leitura só."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        scope = waitlist.scope_kwargs(channel)
        with CaptureQueriesContext(connection) as queries:
            by_date = availability.stock_on_dates([BAGUETE], [casa, casa + DAY, casa + 2 * DAY], **scope)

        scans = [q for q in queries.captured_queries if "stockman_quant" in q["sql"] and "position" in q["sql"]]
        assert len(scans) == 1, [q["sql"] for q in scans]
        assert by_date[casa][BAGUETE]["ready_physical"] >= Decimal("22")


def test_the_waitlist_promises_the_batch_of_the_date(casa):
    """A fila da loja online: a próxima fornada é a de amanhã, com o tamanho dela."""
    target, info = waitlist.next_batch_availability_for_skus([BAGUETE], channel_ref="web")[BAGUETE]

    assert target == casa + DAY
    assert info["total_promisable"] == Decimal("22")


# ── A venda de HOJE não muda ─────────────────────────────────────────────────


class TestTodayIsUntouched:
    def test_the_counter_sells_todays_bread_and_yesterdays_lot(self, casa):
        info = catalog_context.availability_for_sku(BAGUETE, channel_ref="pdv", target_date=casa)

        assert _available(BAGUETE, "pdv", casa) == Decimal("24")
        assert {p["batch"] for p in info["positions"]} == {"TRADI-HOJE", "TRADI-ONTEM"}

    @pytest.mark.parametrize("channel", REMOTE)
    def test_remote_channels_stay_without_the_discounted_lot(self, casa, channel):
        """22 de hoje menos a margem de segurança de 2; o "Ontem" não aparece."""
        info = catalog_context.availability_for_sku(BAGUETE, channel_ref=channel, target_date=casa)

        assert _available(BAGUETE, channel, casa) == Decimal("20")
        assert {p["batch"] for p in info["positions"]} == {"TRADI-HOJE"}

    def test_the_counter_hold_of_today_takes_yesterdays_lot_first(self, casa):
        """FEFO de sempre: o balcão vende primeiro o que vence antes."""
        result = stock_adapter.create_hold(BAGUETE, Decimal("2"), reference="balcao", channel_ref="pdv")

        assert result["success"], result
        assert _hold(result["hold_id"]).quant.batch == "TRADI-ONTEM"

    @pytest.mark.parametrize("channel", REMOTE)
    def test_the_remote_hold_of_today_takes_todays_lot(self, casa, channel):
        result = stock_adapter.create_hold(BAGUETE, Decimal("2"), reference="sacola", channel_ref=channel)

        assert result["success"], result
        assert _hold(result["hold_id"]).quant.batch == "TRADI-HOJE"

    @pytest.mark.parametrize("channel", CHANNELS)
    def test_reading_without_a_date_is_the_reading_of_today(self, casa, channel):
        scope = stock_adapter.get_channel_scope(channel)
        kwargs = {
            "safety_margin": scope["safety_margin"],
            "allowed_positions": scope["allowed_positions"],
            "excluded_positions": scope.get("excluded_positions"),
            "expiry_margin_days": scope.get("expiry_margin_days", 0),
            "include_nonconforming": scope.get("sells_nonconforming", True),
            "allowed_quality_grade_refs": scope.get("allowed_quality_grade_refs"),
        }

        today = stock_adapter.get_availability(BAGUETE, target_date=casa, **kwargs)
        by_dates = availability.stock_on_dates([BAGUETE], [casa], **kwargs)[casa][BAGUETE]

        assert by_dates["total_promisable"] == today["total_promisable"]
        assert today["total_promisable"] == _available(BAGUETE, channel, casa)


# ── A reserva ancora na fornada da data, nunca no lote de hoje ───────────────


@pytest.mark.parametrize("channel", CHANNELS)
class TestTheHoldForAFutureDate:
    def test_anchors_on_the_batch_of_the_date(self, casa, channel):
        amanha = casa + DAY

        result = stock_adapter.create_hold(
            BAGUETE, Decimal("5"), reference="encomenda", channel_ref=channel, target_date=amanha,
        )

        assert result["success"], result
        hold = _hold(result["hold_id"])
        assert hold.quant.target_date == amanha, "prende a fornada de amanhã"
        assert hold.quant.batch == "", "nunca o lote de hoje"
        assert result["is_planned"] is True

    def test_the_cart_reserve_for_tomorrow_refuses_above_the_batch(self, casa, channel):
        amanha = casa + DAY

        refused = availability.reserve(
            BAGUETE, Decimal("30"), session_key=f"S-30-{channel}", channel_ref=channel, target_date=amanha,
        )
        accepted = availability.reserve(
            BAGUETE, Decimal("22"), session_key=f"S-22-{channel}", channel_ref=channel, target_date=amanha,
        )

        assert refused["ok"] is False
        assert refused["hold_ids"] == []
        assert accepted["ok"] is True
        assert {_hold(hold_id).quant.target_date for hold_id in accepted["hold_ids"]} == {amanha}

    def test_the_hold_finds_exactly_what_the_read_counted(self, casa, channel):
        """Leitura e reserva pela mesma régua: nem mais, nem menos, em cada data."""
        for target, expected in ((casa + DAY, Decimal("22")), (casa + 2 * DAY, Decimal("28"))):
            read = _available(BAGUETE, channel, target)

            pieces = stock_adapter.create_holds_up_to(
                BAGUETE, Decimal("500"), reference=f"tudo-{target}", channel_ref=channel,
                target_date=target, apply_safety_margin=False,
            )

            assert read == expected
            assert sum((qty for _hold_id, qty in pieces), Decimal("0")) == expected
            assert {_hold(hold_id).quant.target_date for hold_id, _qty in pieces} == {target}
        assert Quant.objects.get(sku=BAGUETE, batch="TRADI-HOJE").held == Decimal("0")


# ── #2685: acima do plano, prende a fornada e só o resto é demanda ───────────


@pytest.mark.parametrize("channel", CHANNELS)
class TestTheOrderAboveThePlan:
    def test_holds_the_batch_and_only_the_rest_is_demand(self, casa, channel):
        """30 baguetes para amanhã contra 22 planejadas: 22 presas, 8 de demanda.

        Só na venda já consumada (balcão, iFood). No portão de commit (loja,
        WhatsApp) o plano da data é o teto e a encomenda é recusada (dono,
        28/11/2026; ``test_plano_e_o_teto_da_venda``).
        """
        from shopman.backstage.models import OperatorAlert

        amanha = casa + DAY
        # O portão de commit é da loja e do WhatsApp; balcão e iFood chegam consumados.
        order = _order(channel, BAGUETE, 30, amanha, ref=f"ENC-{channel.upper()}-30")

        if channel in GATED:
            with pytest.raises(ValidationError) as exc:
                stock_service.hold(order, require_all=True)
            assert exc.value.code == "insufficient_supply"
            return
        stock_service.hold(order, require_all=False)

        holds = _order_holds(order)
        backed = [h for h in holds if h.quant_id is not None]
        demand = [h for h in holds if h.quant_id is None]
        assert sum(h.quantity for h in backed) == Decimal("22"), "o que a fornada da data cobre"
        assert {h.quant.target_date for h in backed} == {amanha}
        assert sum(h.quantity for h in demand) == Decimal("8"), "só o resto é demanda sem fornada"
        assert {h.target_date for h in holds} == {amanha}
        assert Quant.objects.get(sku=BAGUETE, batch="TRADI-HOJE").held == Decimal("0"), "o pão de hoje fica livre"

        # A fornada não segue prometível a outro pedido.
        assert _available(BAGUETE, channel, amanha) == Decimal("0")

        [decision] = stock_service.availability_decisions_from_holds(order)
        assert Decimal(str(decision["available_qty"])) == Decimal("22")
        assert Decimal(str(decision["demand_qty"])) == Decimal("8")
        assert decision["reason_code"] == "demand_over_plan"

        assert stock_service.alert_demand_over_plan(order) == 1
        alert = OperatorAlert.objects.get(type="order_demand_over_plan", order_ref=order.ref)
        day = amanha.strftime("%d/%m")
        assert alert.audience == "production"
        assert f"30 Baguette de Tradition para {day}, e o plano da data cobre 22" in alert.message
        assert f"Planeje mais 8 para {day}" in alert.message

    def test_within_the_plan_everything_is_backed(self, casa, channel):
        amanha = casa + DAY
        order = _order(channel, BAGUETE, 10, amanha, ref=f"ENC-{channel.upper()}-10")

        stock_service.hold(order, require_all=channel in ("web", "whatsapp"))

        holds = _order_holds(order)
        assert sum(h.quantity for h in holds) == Decimal("10")
        assert all(h.quant_id is not None and h.quant.target_date == amanha for h in holds)
        [decision] = stock_service.availability_decisions_from_holds(order)
        assert Decimal(str(decision["available_qty"])) == Decimal("10")
        assert decision["demand_qty"] == 0
        assert decision["reason_code"] is None
        assert stock_service.alert_demand_over_plan(order) == 0

    def test_without_a_plan_for_the_date_everything_is_demand(self, casa, channel):
        """Data sem fornada: a vitrine de hoje não entra, e a encomenda vira demanda inteira."""
        sem_plano = casa + 3 * DAY
        order = _order(channel, BAGUETE, 6, sem_plano, ref=f"ENC-{channel.upper()}-6")

        stock_service.hold(order, require_all=channel in ("web", "whatsapp"))

        holds = _order_holds(order)
        assert sum(h.quantity for h in holds) == Decimal("6")
        assert all(h.quant_id is None for h in holds)

    def test_plan_split_in_two_balances_is_held_before_any_demand(self, casa, channel):
        """A fornada da data em duas posições (22 + 5): prende as 27 e só 3 são demanda."""
        amanha = casa + DAY
        stock.plan(
            quantity=Decimal("5"), product=Product.objects.get(sku=BAGUETE), target_date=amanha,
            position=_position("producao-2", saleable=False), reason="fornada extra",
        )
        order = _order(channel, BAGUETE, 30, amanha, ref=f"ENC-{channel.upper()}-SPLIT")

        if channel in GATED:
            # O portão de commit: as 27 das duas posições não cobrem 30, e o plano é o teto.
            with pytest.raises(ValidationError):
                stock_service.hold(order, require_all=True)
            return
        stock_service.hold(order, require_all=False)

        holds = _order_holds(order)
        assert sum(h.quantity for h in holds if h.quant_id is not None) == Decimal("27")
        assert sum(h.quantity for h in holds if h.quant_id is None) == Decimal("3")


# ── Mercadoria de validade longa segue lastreando a encomenda ────────────────


@pytest.mark.parametrize("channel", CHANNELS)
class TestLongShelfLifeStillBacksOrders:
    def test_cheese_backs_orders_until_the_eve_of_expiry(self, casa, channel):
        """O lote vence em hoje+10: lastreia até hoje+9; no dia do vencimento, não."""
        safety = stock_adapter.get_channel_scope(channel)["safety_margin"]
        ready = Decimal("12") - safety

        assert _available(QUEIJO, channel, casa) == ready
        assert _available(QUEIJO, channel, casa + DAY) == ready
        assert _available(QUEIJO, channel, casa + 9 * DAY) == ready
        assert _available(QUEIJO, channel, casa + 10 * DAY) == Decimal("0")

    def test_cheese_order_anchors_on_the_lot_in_stock(self, casa, channel):
        result = stock_adapter.create_hold(
            QUEIJO, Decimal("3"), reference="encomenda", channel_ref=channel, target_date=casa + 5 * DAY,
        )

        assert result["success"], result
        assert _hold(result["hold_id"]).quant.batch == "CAMEMBERT-L1"

    def test_goods_without_shelf_life_back_any_date(self, casa, channel):
        safety = stock_adapter.get_channel_scope(channel)["safety_margin"]

        assert _available(GELEIA, channel, casa + DAY) == Decimal("9") - safety
        assert _available(GELEIA, channel, casa + 30 * DAY) == Decimal("9") - safety
