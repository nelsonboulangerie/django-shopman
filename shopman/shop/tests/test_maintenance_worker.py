"""maintenance_worker roda os "crons" do deployment em ciclo.

O worker é o coração operacional: resgata PIX pago com webhook perdido
(reconcile_payments), re-despacha pedido órfão em NEW (sweep_stuck_orders),
libera holds vencidos, limpa sessions/planejamento. Cobertura:

* cada tarefa do ciclo executa via ``--once`` e produz o efeito real esperado
  (cenários mínimos reais; só a fronteira ``lifecycle.dispatch`` é mockada,
  como em test_sweep_stuck_orders);
* exceção numa tarefa loga e NÃO derruba o ciclo nem impede as demais;
* o loop respeita ``--once`` (sem sleep) e o intervalo (floor de 30s).
"""

from __future__ import annotations

import contextlib
import logging
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import call, patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman.models import Order, Session
from shopman.payman.models import PaymentIntent
from shopman.stockman.models import Hold, HoldStatus, Quant

from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS

# ``transaction=True`` não é preferência de estilo: sem ele estes testes só
# passam em SQLite, e passam pelo motivo errado.
#
# `_run_cycle` começa com `close_old_connections()` — higiene obrigatória de um
# management command em loop, que não tem fronteira de request e por isso nunca
# recicla sozinho a conexão persistente do Postgres (o porquê está escrito no
# próprio worker). Num teste `django_db` comum o corpo roda dentro de um bloco
# atômico, então `get_autocommit()` diverge do configurado e o Django **fecha a
# conexão** — no Postgres o teste morre com "the connection is closed"; no SQLite
# em memória o `close()` é um no-op deliberado (fechar destruiria o banco), e o
# teste sobrevive.
#
# Resultado: a suíte ficava verde exatamente porque o banco de teste escondia o
# comportamento que o worker existe para executar. Sem transação de fora, o ciclo
# roda como roda em produção.
pytestmark = pytest.mark.django_db(transaction=True)

WORKER_LOGGER = "shopman.shop.management.commands.maintenance_worker"


@contextlib.contextmanager
def _capture_worker_logs(caplog, level=logging.ERROR):
    """Captura records do worker mesmo com ``propagate=False`` no logger ``shopman``.

    O ``caplog`` do pytest instala seu handler na raiz; o settings de produção põe
    ``propagate=False`` no logger ``shopman`` (config/settings.py), então os records
    do worker param antes da raiz e nunca chegam ao ``caplog``. Anexar o handler do
    ``caplog`` direto no logger do worker captura independente de propagação — vale
    igual local e no CI.
    """
    worker_logger = logging.getLogger(WORKER_LOGGER)
    with caplog.at_level(level, logger=WORKER_LOGGER):
        worker_logger.addHandler(caplog.handler)
        # Determinismo do count: com o handler do caplog anexado direto no logger
        # do worker, propagação ligada faria o MESMO record ser capturado de novo
        # pelo handler-raiz do caplog (record duplicado → count 2 em vez de 1). O
        # estado ambiente de propagate varia por ambiente/ordem (era flake de CI);
        # forçar False aqui garante captura única pelo handler direto, invariante.
        prev_propagate = worker_logger.propagate
        worker_logger.propagate = False
        try:
            yield
        finally:
            worker_logger.propagate = prev_propagate
            worker_logger.removeHandler(caplog.handler)


def _run_once():
    call_command("maintenance_worker", "--once", stdout=StringIO())


def _order(ref, *, status=Order.Status.NEW, data=None, age_minutes=30):
    o = Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=1000, data=data or {}
    )
    if age_minutes:
        old = timezone.now() - timedelta(minutes=age_minutes)
        Order.objects.filter(pk=o.pk).update(created_at=old)  # bypassa auto_now_add
    return o


# ── (a) Cada tarefa do ciclo executa e produz o efeito esperado ──────────────


def test_cycle_releases_expired_holds():
    quant = Quant.objects.create(sku="PAO", _quantity=Decimal("5"))
    expired = Hold.objects.create(
        sku="PAO",
        quant=quant,
        quantity=Decimal("2"),
        target_date=date.today(),
        status=HoldStatus.PENDING,
        expires_at=timezone.now() - timedelta(minutes=5),
    )
    active = Hold.objects.create(
        sku="PAO",
        quant=quant,
        quantity=Decimal("1"),
        target_date=date.today(),
        status=HoldStatus.PENDING,
        expires_at=timezone.now() + timedelta(hours=1),
    )

    _run_once()

    expired.refresh_from_db()
    active.refresh_from_db()
    assert expired.status == HoldStatus.RELEASED
    assert expired.resolved_at is not None
    assert active.status == HoldStatus.PENDING


def test_cycle_removes_stale_sessions():
    stale = Session.objects.create(session_key="S-STALE", channel_ref="web")
    Session.objects.filter(pk=stale.pk).update(
        updated_at=timezone.now() - timedelta(hours=72)  # bypassa auto_now
    )
    fresh = Session.objects.create(session_key="S-FRESH", channel_ref="web")

    _run_once()

    assert not Session.objects.filter(pk=stale.pk).exists()
    assert Session.objects.filter(pk=fresh.pk).exists()


def test_cycle_removes_stale_planning_quants():
    yesterday = date.today() - timedelta(days=1)
    ghost = Quant.objects.create(sku="GHOST", target_date=yesterday, _quantity=Decimal("5"))
    planned = Quant.objects.create(
        sku="PLANNED", target_date=date.today() + timedelta(days=1), _quantity=Decimal("5")
    )

    _run_once()

    assert not Quant.objects.filter(pk=ghost.pk).exists()
    assert Quant.objects.filter(pk=planned.pk).exists()


def test_cycle_zeroes_dead_production_residue():
    from shopman.craftsman.contrib.stockman.handlers import STARTED_BATCH
    from shopman.craftsman.models import Recipe, WorkOrder
    from shopman.stockman.models import Position, PositionKind

    producao = Position.objects.create(
        ref="producao-mw", name="Produção", kind=PositionKind.PROCESS, is_saleable=False
    )
    recipe = Recipe.objects.create(
        ref="rc-mw-dead", name="Pão", output_sku="PAO-MW-DEAD", batch_size=Decimal("1")
    )
    yesterday = date.today() - timedelta(days=1)
    # WO morta (void sem o ajuste do handler) deixou resíduo started de ontem…
    dead = Quant.objects.create(
        sku="PAO-MW-DEAD", position=producao, target_date=yesterday,
        batch=STARTED_BATCH, _quantity=Decimal("7"),
    )
    WorkOrder.objects.create(
        recipe=recipe, output_sku="PAO-MW-DEAD", quantity=Decimal("7"),
        status=WorkOrder.Status.VOID, target_date=yesterday,
    )
    # …e a WO ainda viva de ontem segue intocável (finish tardio possível).
    live = Quant.objects.create(
        sku="PAO-MW-LIVE", position=producao, target_date=yesterday,
        batch=STARTED_BATCH, _quantity=Decimal("4"),
    )
    live_recipe = Recipe.objects.create(
        ref="rc-mw-live", name="Broa", output_sku="PAO-MW-LIVE", batch_size=Decimal("1")
    )
    WorkOrder.objects.create(
        recipe=live_recipe, output_sku="PAO-MW-LIVE", quantity=Decimal("4"),
        status=WorkOrder.Status.STARTED, target_date=yesterday,
    )

    _run_once()

    dead.refresh_from_db()
    live.refresh_from_db()
    assert dead.quantity == 0
    assert live.quantity == Decimal("4")


def test_cycle_rescues_paid_order_with_lost_webhook():
    # PIX capturado no Payman, mas o webhook nunca chegou: o pedido ficou em NEW.
    # O marcador on_commit=done mantém o sweep_stuck_orders fora do caminho —
    # aqui o resgate tem que vir do reconcile_payments.
    order = _order(
        "ORD-LOST-WEBHOOK",
        data={
            "lifecycle": {"on_commit": "done"},
            "payment": {"intent_ref": "PI-LOST"},
        },
        age_minutes=180,
    )
    PaymentIntent.objects.create(
        ref="PI-LOST",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.CAPTURED,
        amount_q=1000,
    )

    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run_once()

    dispatch.assert_called_once()
    dispatched_order, phase = dispatch.call_args.args
    assert dispatched_order.ref == order.ref
    assert phase == "on_paid"


def test_cycle_skips_order_with_pending_intent():
    order = _order(
        "ORD-STILL-PENDING",
        data={
            "lifecycle": {"on_commit": "done"},
            "payment": {"intent_ref": "PI-PENDING"},
        },
        age_minutes=180,
    )
    PaymentIntent.objects.create(
        ref="PI-PENDING",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.PENDING,
        amount_q=1000,
    )

    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run_once()

    dispatch.assert_not_called()
    order.refresh_from_db()
    assert order.status == Order.Status.NEW


def test_cycle_sweeps_stuck_new_order():
    # Órfão em NEW sem marcador (crash pós-commit); jovem demais para o
    # reconcile (cutoff 2h), velho o bastante para o sweeper (15 min).
    order = _order("ORD-ORPHAN", data={}, age_minutes=30)

    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run_once()

    dispatch.assert_called_once()
    dispatched_order, phase = dispatch.call_args.args
    assert dispatched_order.ref == order.ref
    assert phase == "on_commit"


# ── (b) Falha numa tarefa não derruba o ciclo ────────────────────────────────


def test_task_failure_logs_and_cycle_continues(caplog):
    # A PRIMEIRA tarefa do ciclo quebra de verdade (release_expired explode);
    # as demais ainda têm que rodar — a session stale abaixo deve sumir.
    stale = Session.objects.create(session_key="S-AFTER-FAILURE", channel_ref="web")
    Session.objects.filter(pk=stale.pk).update(
        updated_at=timezone.now() - timedelta(hours=72)
    )

    with (
        patch(
            "shopman.stockman.stock.release_expired",
            side_effect=RuntimeError("boom"),
        ),
        _capture_worker_logs(caplog),
    ):
        _run_once()

    assert not Session.objects.filter(pk=stale.pk).exists()
    # Robusto a ruído/duplicata de captura (a ordem de coleta de testes pode variar):
    # asserta o record ESPECÍFICO da falha esperada, não a contagem total de logs do
    # worker (que era frágil e flakava no CI).
    failures = [
        r
        for r in caplog.records
        if r.name == WORKER_LOGGER and "release_expired_holds" in r.getMessage()
    ]
    assert failures, "esperava um log de falha de release_expired_holds"
    assert "ciclo continua" in failures[0].getMessage()
    assert failures[0].exc_info is not None  # logger.exception preserva o traceback


def test_every_task_failing_still_completes_the_cycle(caplog):
    with (
        patch(
            "shopman.shop.management.commands.maintenance_worker.call_command",
            side_effect=RuntimeError("boom"),
        ) as cc,
        _capture_worker_logs(caplog),
    ):
        _run_once()

    assert cc.call_count == len(MAINTENANCE_COMMANDS)
    logged = [r.getMessage() for r in caplog.records if r.name == WORKER_LOGGER]
    # Cada comando que falhou tem que ter sido logado (o ciclo não para no 1º erro).
    # Presença por comando, não contagem total — imune a duplicata de captura / ruído
    # de ordem de coleta (o exato `== len` flakava no CI).
    for command in MAINTENANCE_COMMANDS:
        assert any(command in message for message in logged), f"faltou log de {command}"


# ── (c) Loop: --once, intervalo e floor ──────────────────────────────────────


class _StopLoop(Exception):
    """Escape determinístico do loop infinito nos testes (via time.sleep mockado)."""


def test_once_runs_one_cycle_in_order_and_never_sleeps():
    with (
        patch("shopman.shop.management.commands.maintenance_worker.call_command") as cc,
        patch("shopman.shop.management.commands.maintenance_worker.time.sleep") as sleep,
    ):
        _run_once()

    sleep.assert_not_called()
    assert cc.call_args_list == [
        call("release_expired_holds"),
        call("cleanup_stale_sessions"),
        call("sweep_orphan_holds"),
        call("cleanup_stale_planning"),
        # Depois de liberar reservas: reserva que expira sai por update em massa,
        # sem signal, então é aqui que a volta do produto é percebida.
        call("reconcile_shelf_outages"),
        call("stamp_business_days"),
        call("detect_operation_episodes"),
        call("sweep_stale_oven_runs"),
        # A série diária materializada do B.I. acompanha o dia (P3 da fundação).
        call("refresh_bi_daily_series"),
        call("evaluate_bi_alerts"),
        call("expire_stale_announcements"),
        call("dispatch_due_announcements"),
        call("arm_scheduled_campaigns"),
        call("reconcile_payments"),
        # Depois dos pagamentos sararem: o dia de ontem reconcilia inteiro e
        # divergência vira OperatorAlert (dedupe/debounce no serviço).
        call("reconcile_financial_day"),
        call("sweep_stuck_orders"),
        # O mesmo resgate do lado da produção: fornada concluída cujo ledger
        # de estoque não fechou volta a ser realizada.
        call("sweep_unrealized_production"),
        # Depois do resgate: resíduo de processo de WO morta é zerado pelo
        # ledger — só quando nenhuma WO viva nem ledger aberto o reivindica.
        call("sweep_dead_production_stock"),
        call("check_directive_health"),
    ]


def test_loop_sleeps_the_remainder_of_the_interval():
    """Dorme `intervalo - duração do ciclo`, não o intervalo inteiro.

    ⚠️ Este teste ANTES exigia `sleep(300)` cheio — ele codificava o defeito. O período
    real era `intervalo + duração do ciclo`, então "a cada 5 minutos" era falso para todos
    os crons da vassoura, e a deriva se acumulava. Doeu quando o agendamento de campanha
    passou a depender do relógio.

    O relógio é injetado para o teste ser exato: com ciclo de 90s e intervalo de 300s, o
    sono é 210s — e não "aproximadamente 300".
    """
    clock = {"t": 0.0}

    def _cycle_costs_90s(*args, **kwargs):
        clock["t"] += 90.0 / len(MAINTENANCE_COMMANDS)

    with (
        patch(
            "shopman.shop.management.commands.maintenance_worker.call_command",
            side_effect=_cycle_costs_90s,
        ) as cc,
        patch(
            "shopman.shop.management.commands.maintenance_worker.time.monotonic",
            side_effect=lambda: clock["t"],
        ),
        patch(
            "shopman.shop.management.commands.maintenance_worker.time.sleep",
            side_effect=[None, _StopLoop()],
        ) as sleep,
        pytest.raises(_StopLoop),
    ):
        call_command("maintenance_worker", stdout=StringIO())

    assert cc.call_count == 2 * len(MAINTENANCE_COMMANDS)
    # Tolerância porque a soma de N frações de 90s acumula erro de ponto flutuante; o
    # que importa é que o sono seja o RESTANTE (210), não o intervalo (300).
    napped = [args[0] for args, _kwargs in sleep.call_args_list]
    assert len(napped) == 2
    assert all(abs(seconds - 210.0) < 0.01 for seconds in napped), napped


def test_a_cycle_slower_than_the_interval_does_not_sleep():
    """Ciclo que não cabe no intervalo é sinal de manutenção não dando conta.

    Não dormir nada é o comportamento certo (o próximo ciclo começa já), e o warning
    existe para o silêncio não esconder a saturação.
    """
    clock = {"t": 0.0}

    def _cycle_costs_400s(*args, **kwargs):
        clock["t"] += 400.0 / len(MAINTENANCE_COMMANDS)

    # ⚠️ `_StopLoop` deriva de `Exception`, e `_run_cycle` engole `Exception` de propósito
    # (um cron quebrado não pode derrubar o worker). Para escapar de um loop que NÃO
    # dorme, o sinal tem de vir de `BaseException` — daí o KeyboardInterrupt.
    cycles = {"n": 0}

    def _cycle_then_stop(*args, **kwargs):
        _cycle_costs_400s()
        cycles["n"] += 1
        if cycles["n"] > len(MAINTENANCE_COMMANDS):
            raise KeyboardInterrupt

    with (
        patch(
            "shopman.shop.management.commands.maintenance_worker.call_command",
            side_effect=_cycle_then_stop,
        ),
        patch(
            "shopman.shop.management.commands.maintenance_worker.time.monotonic",
            side_effect=lambda: clock["t"],
        ),
        patch(
            "shopman.shop.management.commands.maintenance_worker.time.sleep",
        ) as sleep,
        pytest.raises(KeyboardInterrupt),
    ):
        call_command("maintenance_worker", stdout=StringIO())

    sleep.assert_not_called()


@pytest.mark.parametrize(("requested", "effective"), [(5, 30), (60, 60)])
def test_interval_respects_floor_of_30_seconds(requested, effective):
    # Relógio parado: com o sono virando `intervalo - duração`, um relógio real
    # devolveria 59,9998 e o teste passaria a falhar por ruído de medição em vez de
    # por comportamento.
    with (
        patch("shopman.shop.management.commands.maintenance_worker.call_command"),
        patch(
            "shopman.shop.management.commands.maintenance_worker.time.monotonic",
            return_value=0.0,
        ),
        patch(
            "shopman.shop.management.commands.maintenance_worker.time.sleep",
            side_effect=_StopLoop(),
        ) as sleep,
        pytest.raises(_StopLoop),
    ):
        call_command("maintenance_worker", "--interval", str(requested), stdout=StringIO())

    sleep.assert_called_once_with(effective)
