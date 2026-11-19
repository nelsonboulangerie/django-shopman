"""Promessa em risco (WP-G08, EXCELENCIA-GESTOR P0-1, P1-22, P2-19).

A encomenda aceita e paga cujo lote era cancelado perdia a reserva em silêncio:
o cartão do Gestor passava a parecer sem pendência. A leitura
``projections/order_promise`` deriva a saúde da reserva do que o estoque e a
Produção dizem agora, para o painel inteiro de uma vez. Esta suíte prende:

- reserva inteira num lote de data futura não aparece;
- reserva perdida (lote cancelado pela Produção), em parte (a produção encolheu)
  e acima do estoque;
- lote fechado com menos que o planejado, lote atrasado e lote que só não ficou
  pronto ainda;
- o lote que abre não acusa ninguém (o saldo de produção é um bolo só);
- a demanda sem saldo: coberta pela produção da data, acima dela, sem lote
  ainda, e a do produto feito na hora;
- o pedido pago do dia que espera o lote volta a ter o selo e o bloqueio, sem
  depender do estado da fila de espera;
- cartão, Fila e detalhe leem a mesma leitura, com as três saídas ao lado;
- o número de consultas não cresce com o número de pedidos.

Os lotes são planejados, abertos, fechados e cancelados pelo Craftsman de
verdade: é a ponte dele com o estoque que mexe nos saldos.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.service import CraftService as craft
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderItem
from shopman.payman import PaymentService
from shopman.stockman import stock
from shopman.stockman.models import Hold, HoldStatus, Position, PositionKind, Quant
from shopman.stockman.services.holds import (
    QUALITY_GRADE_POLICY_VERSION,
    QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
)

from shopman.backstage.projections import order_promise
from shopman.backstage.projections.order_attention import commitment_day_label
from shopman.backstage.projections.order_queue import (
    build_operator_order,
    build_order_card,
    build_two_zone_queue,
)
from shopman.shop.models import Channel, Shop

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

SKU = "BAGUETE"
NAME = "Baguete de tradição"


def _at(hour: int, minute: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(timezone.localdate(), time(hour, minute)))


@pytest.fixture
def relogio(monkeypatch):
    """Crava o relógio: ``relogio(9)`` são 9h de hoje para todo o Django."""

    def set_now(hour: int, minute: int = 0) -> datetime:
        moment = _at(hour, minute)
        monkeypatch.setattr(timezone, "now", lambda: moment)
        return moment

    return set_now


@pytest.fixture(autouse=True)
def casa(db):
    # A ponte do Craftsman com o estoque: é ela que mexe nos saldos de produção.
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401, I001
    from django.core.cache import cache

    cache.clear()
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.update_or_create(ref="web", defaults={"name": "Loja online", "config": {}})
    Position.objects.get_or_create(
        ref="loja", defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    yield
    cache.clear()


@pytest.fixture
def gerente(django_user_model):
    user = django_user_model.objects.create_user(username="gerente-g08", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    return user


@pytest.fixture
def baguete(db):
    return Product.objects.create(
        sku=SKU, name=NAME, unit="un", base_price_q=1100, availability_policy="planned_ok", is_sellable=True,
    )


@pytest.fixture
def ficha(baguete):
    Product.objects.create(sku="FARINHA", name="Farinha", unit="kg", base_price_q=500, is_sellable=False)
    recipe = Recipe.objects.create(ref="baguete", name="Baguete", output_sku=SKU, batch_size=Decimal("10"))
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity=Decimal("0.5"), unit="kg")
    return recipe


def _day(days: int = 0):
    return timezone.localdate() + timedelta(days=days)


def _order(ref: str, *, days: int | None = 1, status: str = "accepted", slot: str = "", **data) -> Order:
    body = {
        "customer": {"name": f"Cliente {ref}", "phone": "+5543999990000"},
        "fulfillment_type": "pickup",
        "payment": {"method": "cash"},
        "availability_decision": {"approved": True, "decisions": []},
        **data,
    }
    if days is not None:
        body["is_preorder"] = True
        body["delivery_date"] = _day(days).isoformat()
        if slot:
            body["delivery_time_slot"] = slot
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=status, total_q=4400, data=body,
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku=SKU, name=NAME, qty=4, unit_price_q=1100, line_total_q=4400,
    )
    return order


def _planned_quant(day) -> Quant:
    return Quant.objects.get(sku=SKU, target_date=day, batch="")


def _reserve(order: Order, qty: str, *, day, quant: Quant | None = None, sku: str = SKU, **metadata) -> Hold:
    """A reserva do pedido, como o commit a deixa: presa ao saldo (ou sem saldo) e listada em ``hold_ids``."""
    hold = Hold.objects.create(
        sku=sku, quant=quant, quantity=Decimal(qty), target_date=day, status=HoldStatus.CONFIRMED,
        metadata={
            "reference": f"order:{order.ref}",
            QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            "priority": 0,
            **({"planned": True} if quant is not None and quant.target_date else {"on_demand": True} if quant is None else {}),
            **metadata,
        },
    )
    order.data.setdefault("hold_ids", []).append({"sku": sku, "hold_id": hold.hold_id, "qty": float(qty)})
    order.save(update_fields=["data"])
    return hold


def _lot(recipe, qty: str, *, days: int = 1):
    return craft.plan(recipe, quantity=Decimal(qty), date=_day(days))


def _encomenda(recipe, ref: str = "ENC-1", *, qty: str = "4", lot: str = "10", days: int = 1, **order_kwargs):
    """Uma encomenda aceita com a reserva presa ao lote planejado da data."""
    work_order = _lot(recipe, lot, days=days)
    order = _order(ref, days=days, **order_kwargs)
    hold = _reserve(order, qty, day=_day(days), quant=_planned_quant(_day(days)))
    return order, work_order, hold


def _promise(order: Order):
    return order_promise.read_for([Order.objects.get(pk=order.pk)]).get(order.ref)


def _one(promise):
    assert promise is not None
    assert len(promise.items) == 1
    return promise.items[0]


# ── Reserva inteira ──────────────────────────────────────────────────────────


def test_reserva_inteira_no_lote_da_data_nao_aparece(ficha, gerente):
    order, _wo, _hold = _encomenda(ficha)

    assert order_promise.read_for([order]) == {}
    card = build_order_card(order, user=gerente)
    assert card.promise is None
    assert card.attention == ""


def test_reserva_ja_baixada_nao_aparece_e_custa_uma_consulta(baguete):
    order = _order("HOJE-BAIXADA", days=None)
    loja = Position.objects.get(ref="loja")
    stock.receive(quantity=Decimal("10"), sku=SKU, position=loja, reason="vitrine")
    hold_id = stock.hold(quantity=Decimal("4"), product=baguete, target_date=_day(), reference=f"order:{order.ref}")
    stock.confirm(hold_id)
    stock.fulfill(hold_id)
    order.data["hold_ids"] = [{"sku": SKU, "hold_id": hold_id, "qty": 4.0}]
    order.save(update_fields=["data"])

    with CaptureQueriesContext(connection) as queries:
        assert order_promise.read_for([order]) == {}
    assert len(queries) == 1


def test_o_lote_que_abre_nao_acusa_ninguem(ficha):
    """Abrir o lote tira a quantidade do saldo planejado e a põe no "em produção",
    e a reserva vai junto (conserto da #2709): o pedido segue com lastro."""
    order, work_order, hold = _encomenda(ficha)
    work_order.refresh_from_db()
    craft.start(work_order, quantity=Decimal("10"), expected_rev=work_order.rev)

    hold.refresh_from_db()
    assert hold.quant.quantity >= hold.quantity  # a reserva está no saldo que tem o pão
    assert order_promise.read_for([order]) == {}


# ── Reserva perdida e em parte ───────────────────────────────────────────────


def test_lote_cancelado_pela_producao_deixa_a_encomenda_em_risco(ficha, gerente, settings):
    settings.SHOPMAN_SURFACE_URLS = {"pos": "https://pdv.example.test/"}
    order, work_order, hold = _encomenda(ficha, "ENC-CANCELADA")

    craft.void(work_order, reason="Forno parou")

    hold.refresh_from_db()
    assert hold.status == HoldStatus.RELEASED  # a Produção soltou a reserva sem lastro
    promise = _promise(order)
    assert (promise.state, promise.label) == ("at_risk", "Promessa em risco")
    assert promise.blocks_start is False
    assert promise.since_iso == hold.resolved_at.isoformat()
    item = _one(promise)
    assert (item.sku, item.name) == (SKU, NAME)
    assert (item.reservation, item.cause, item.at_risk) == ("lost", "batch_cancelled", True)
    assert (item.qty, item.missing_qty) == ("4", "4")
    assert item.label == "4x Baguete de tradição sem reserva"
    assert item.detail == "O lote de amanhã foi cancelado."
    assert item.batch_date == _day(1).isoformat()
    assert item.batch_status == "void"
    assert item.work_order_refs == (work_order.ref,)

    # O cartão: o selo, as três saídas e o lugar na Fila "Precisa de você".
    card = build_order_card(Order.objects.get(pk=order.pk), user=gerente)
    assert card.promise.state == "at_risk"
    assert card.attention == "promise"
    assert card.attention_since_iso == promise.since_iso
    actions = {action.ref: action for action in card.promise.actions}
    assert list(actions) == ["contact-customer", "reschedule-at-pos", "cancel"]
    assert [action.label for action in card.promise.actions] == ["Avisar o cliente", "Remarcar no PDV", "Cancelar pedido"]
    assert all(action.kind == "link" and action.enabled for action in actions.values())
    assert actions["contact-customer"].href == "/ENC-CANCELADA#promise"
    assert actions["reschedule-at-pos"].href == "https://pdv.example.test/preorders/ENC-CANCELADA"
    assert actions["cancel"].href == "/ENC-CANCELADA#cancel"
    # O telefone do cliente não vai para o cartão do painel (#2434).
    assert "5543999990000" not in "".join(action.href for action in card.promise.actions)


def test_a_linha_do_tempo_diz_o_item_e_o_lote_sem_codigo_cru(ficha, gerente):
    """O evento do lote cancelado carrega um código em ``reason``; a tela mostra o item e o lote."""
    order, work_order, _hold = _encomenda(ficha, "ENC-LINHA")
    work_order.refresh_from_db()
    craft.void(work_order, reason="Forno parou")

    detail = build_operator_order(Order.objects.get(pk=order.pk), user=gerente)
    lost = [event for event in detail.timeline if event.event_type == "production_hold_lost"]
    assert len(lost) == 1
    assert lost[0].label == "Produção cancelada: item ficou sem reserva"
    assert lost[0].detail.startswith("4x ")
    assert "lote de " in lost[0].detail
    assert "production_voided" not in lost[0].detail
    assert "_" not in lost[0].detail


def test_o_detalhe_abre_com_promessa_em_risco_e_as_saidas_de_verdade(ficha, gerente, settings):
    settings.SHOPMAN_SURFACE_URLS = {"pos": "https://pdv.example.test/"}
    order, work_order, _hold = _encomenda(ficha, "ENC-DETALHE")
    craft.void(work_order, reason="Forno parou")

    detail = build_operator_order(Order.objects.get(pk=order.pk), user=gerente)

    assert detail.promise.state == "at_risk"
    actions = {action.ref: action for action in detail.promise.actions}
    assert actions["contact-customer"].href == "https://wa.me/5543999990000"
    assert actions["reschedule-at-pos"].href == "https://pdv.example.test/preorders/ENC-DETALHE"
    # Cancelar é a MESMA ação do detalhe, com a revisão e a régua do gerente.
    assert actions["cancel"] is next(action for action in detail.actions if action.ref == "cancel")
    assert actions["cancel"].kind == "mutation"

    first = detail.pending[0]
    assert (first.key, first.tone, first.label) == ("promise", "error", "Promessa em risco")
    assert first.reason == "4x Baguete de tradição sem reserva. O lote de amanhã foi cancelado."
    assert [action.ref for action in first.actions] == ["contact-customer", "reschedule-at-pos", "cancel"]
    assert first.actions[0].href == "https://wa.me/5543999990000"


def test_quem_nao_gerencia_pedidos_ve_o_risco_e_nao_recebe_atalho(ficha, django_user_model):
    order, work_order, _hold = _encomenda(ficha, "ENC-SEM-PERMISSAO")
    craft.void(work_order, reason="Forno parou")
    visitante = django_user_model.objects.create_user(username="so-olha", is_staff=True)

    card = build_order_card(Order.objects.get(pk=order.pk), user=visitante)

    assert card.promise.state == "at_risk"
    assert all(not action.enabled and action.reason and not action.href for action in card.promise.actions)


def test_saldo_do_lote_que_encolhe_deixa_a_reserva_em_parte(ficha):
    """Dois pedidos no mesmo lote de 10, e o saldo planejado cai para 8. Quem
    reservou primeiro fica inteiro, e o segundo perde o que passou do saldo.

    A Produção não baixa o plano abaixo do comprometido (o Craftsman recusa com
    ``COMMITTED_HOLDS``); o saldo encolhe por ajuste de estoque.
    """
    _lot(ficha, "10")
    quant = _planned_quant(_day(1))
    primeiro = _order("ENC-PRIMEIRO")
    _reserve(primeiro, "6", day=_day(1), quant=quant)
    segundo = _order("ENC-SEGUNDO")
    _reserve(segundo, "4", day=_day(1), quant=quant)

    stock.adjust(quant, Decimal("8"), reason="Ajuste do plano")

    promises = order_promise.read_for([primeiro, segundo])
    assert list(promises) == ["ENC-SEGUNDO"]
    item = _one(promises["ENC-SEGUNDO"])
    assert (item.reservation, item.cause) == ("partial", "plan_short")
    assert (item.qty, item.missing_qty) == ("4", "2")
    assert item.label == "Baguete de tradição: 2 de 4 sem reserva"
    assert item.detail == "A produção planejada para amanhã não cobre o pedido."


def test_um_de_dois_lotes_cancelado_so_acusa_quem_ficou_sem_lastro(ficha):
    """O saldo de produção é compartilhado pelos lotes do dia: cancelar um deles
    só tira a reserva de quem passou do que o outro cobre."""
    _lot(ficha, "5")
    cancelado = _lot(ficha, "5")
    quant = _planned_quant(_day(1))
    coberto = _order("ENC-COBERTO")
    _reserve(coberto, "5", day=_day(1), quant=quant)
    descoberto = _order("ENC-DESCOBERTO")
    hold = _reserve(descoberto, "4", day=_day(1), quant=quant)

    craft.void(cancelado, reason="Massa passou do ponto")

    hold.refresh_from_db()
    assert hold.status == HoldStatus.RELEASED
    promises = order_promise.read_for([coberto, Order.objects.get(pk=descoberto.pk)])
    assert list(promises) == ["ENC-DESCOBERTO"]
    item = _one(promises["ENC-DESCOBERTO"])
    assert (item.reservation, item.cause) == ("lost", "batch_cancelled")
    assert item.detail == "Um lote de amanhã foi cancelado, e o que ficou não cobre o pedido."


def test_estoque_menor_que_o_reservado(baguete):
    """Pedido de hoje reservado na vitrine, e a contagem baixa o saldo depois."""
    loja = Position.objects.get(ref="loja")
    stock.receive(quantity=Decimal("3"), sku=SKU, position=loja, reason="vitrine")
    quant = Quant.objects.get(sku=SKU, position=loja, target_date__isnull=True)
    order = _order("HOJE-VITRINE", days=None, status="new")
    _reserve(order, "3", day=_day(), quant=quant)
    stock.adjust(quant, Decimal("2"), reason="Quebra")

    item = _one(_promise(order))
    assert (item.reservation, item.cause) == ("partial", "stock_short")
    assert (item.qty, item.missing_qty) == ("3", "1")
    assert item.detail == "O estoque é menor que o reservado."
    assert item.batch_date == ""


def test_reserva_vencida_e_reserva_perdida(baguete):
    loja = Position.objects.get(ref="loja")
    stock.receive(quantity=Decimal("5"), sku=SKU, position=loja, reason="vitrine")
    quant = Quant.objects.get(sku=SKU, position=loja, target_date__isnull=True)
    order = _order("HOJE-VENCIDA", days=None)
    hold = _reserve(order, "4", day=_day(), quant=quant)
    Hold.objects.filter(pk=hold.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

    item = _one(_promise(order))
    assert (item.reservation, item.cause) == ("lost", "hold_released")
    assert item.detail == "A reserva deste item foi solta."


# ── O lote: fechado com menos, atrasado, esperando ───────────────────────────


def test_lote_fechado_com_menos_que_o_planejado(ficha, relogio):
    """Lote de 10 fecha com 6: a reserva de 4 vai para a vitrine, a de 5 fica sem pão."""
    relogio(9)
    work_order = _lot(ficha, "10", days=0)
    quant = _planned_quant(_day())
    cabe = _order("HOJE-CABE", days=0)
    hold_cabe = _reserve(cabe, "4", day=_day(), quant=quant)
    nao_cabe = _order("HOJE-NAO-CABE", days=0)
    _reserve(nao_cabe, "5", day=_day(), quant=quant)

    work_order.refresh_from_db()
    craft.finish(work_order, finished=Decimal("6"), expected_rev=work_order.rev)

    hold_cabe.refresh_from_db()
    assert hold_cabe.quant.target_date is None  # materializou na vitrine
    promises = order_promise.read_for([Order.objects.get(pk=cabe.pk), Order.objects.get(pk=nao_cabe.pk)])
    assert list(promises) == ["HOJE-NAO-CABE"]
    promise = promises["HOJE-NAO-CABE"]
    item = _one(promise)
    assert (item.reservation, item.cause) == ("lost", "batch_short")
    assert (item.qty, item.missing_qty) == ("5", "5")
    assert item.detail == "O lote de hoje fechou com 6, e o planejado era 10."
    assert item.batch_status == "finished"
    assert promise.since_iso  # desde o fechamento do lote


def test_lote_fechado_inteiro_com_a_reserva_fora_dele(ficha, relogio):
    """O lote fechou com tudo o que planejou, o saldo de produção zerou e a
    reserva continuou presa a ele: o pão está na vitrine, sem dono. O estado é
    montado à mão para a leitura não depender de como a ponte chega até ele."""
    from shopman.craftsman.models import WorkOrder

    relogio(9)
    order, work_order, hold = _encomenda(ficha, "HOJE-FICOU-DE-FORA", days=0)
    stock.adjust(hold.quant, Decimal("0"), reason="Saldo de produção realizado")
    WorkOrder.objects.filter(pk=work_order.pk).update(
        status=WorkOrder.Status.FINISHED, finished=Decimal("10"), finished_at=timezone.now(),
    )

    item = _one(_promise(order))
    assert (item.reservation, item.cause) == ("lost", "batch_closed")
    assert item.detail == "O lote de hoje já fechou e esta reserva ficou de fora."


def test_lote_de_hoje_antes_da_hora_so_espera(ficha, baguete, relogio):
    Product.objects.filter(pk=baguete.pk).update(metadata={"ready_from": "12:00"})
    relogio(9)
    order, _wo, _hold = _encomenda(ficha, "HOJE-ESPERA", days=0)

    promise = _promise(order)
    assert (promise.state, promise.label) == ("waiting_batch", "Esperando o lote")
    assert promise.blocks_start is True
    item = _one(promise)
    assert (item.reservation, item.cause, item.at_risk) == ("whole", "batch_waiting", False)
    assert (item.qty, item.missing_qty) == ("4", "0")
    assert item.label == "4x Baguete de tradição"
    assert item.detail == "O lote de hoje não começou. Fica pronto às 12h."
    assert item.batch_status == "planned"
    assert item.batch_ready_at_iso == _at(12).isoformat()


def test_lote_de_hoje_depois_da_hora_esta_atrasado(ficha, baguete, relogio):
    Product.objects.filter(pk=baguete.pk).update(metadata={"ready_from": "12:00"})
    relogio(9)
    order, work_order, _hold = _encomenda(ficha, "HOJE-ATRASADO", days=0)
    work_order.refresh_from_db()
    craft.start(work_order, quantity=Decimal("10"), expected_rev=work_order.rev)
    relogio(13)

    promise = _promise(order)
    assert promise.state == "at_risk"
    assert promise.blocks_start is True
    assert promise.since_iso == _at(12).isoformat()
    item = _one(promise)
    assert (item.reservation, item.cause, item.at_risk) == ("whole", "batch_late", True)
    assert item.missing_qty == "0"
    assert item.detail == "O lote de hoje está atrasado: devia ficar pronto às 12h e está em andamento."
    assert item.batch_status == "started"


def test_lote_de_ontem_que_nunca_ficou_pronto_esta_atrasado(ficha, relogio):
    relogio(9)
    work_order = _lot(ficha, "10", days=-1)
    order = _order("ONTEM-ESQUECIDO", days=-1)
    _reserve(order, "4", day=_day(-1), quant=_planned_quant(_day(-1)))

    item = _one(_promise(order))
    assert (item.cause, item.at_risk) == ("batch_late", True)
    assert item.detail == "O lote de ontem não ficou pronto."
    assert item.work_order_refs == (work_order.ref,)


def test_sem_hora_de_prontidao_o_lote_de_hoje_nunca_vira_atraso(ficha, relogio):
    """A casa não declarou a hora e não há histórico: a leitura não inventa atraso."""
    relogio(23)
    order, _wo, _hold = _encomenda(ficha, "HOJE-SEM-HORA", days=0)

    item = _one(_promise(order))
    assert (item.cause, item.at_risk) == ("batch_waiting", False)
    assert item.detail == "O lote de hoje não começou."
    assert item.batch_ready_at_iso == ""


# ── Demanda sem saldo ────────────────────────────────────────────────────────


def test_demanda_de_data_futura_sem_lote_ainda_nao_e_risco(baguete):
    """A encomenda feita antes do plano nasce assim: a Produção ainda não planejou o dia."""
    order = _order("ENC-SEM-PLANO", days=3)
    _reserve(order, "4", day=_day(3))

    assert order_promise.read_for([order]) == {}


def test_demanda_coberta_pela_producao_da_data_nao_e_risco(ficha):
    order = _order("ENC-COBERTA-PELO-PLANO", days=2)
    _reserve(order, "4", day=_day(2))
    _lot(ficha, "10", days=2)  # o plano veio depois, e cobre sem ancorar

    assert order_promise.read_for([order]) == {}


def test_demanda_acima_do_plano_da_data(ficha):
    """Encomenda de 20 com plano de 10: 6 presos ao lote, 14 como demanda, e o
    lote ainda tem 4 livres. Faltam 10."""
    _lot(ficha, "10", days=2)
    order = _order("ENC-ACIMA-DO-PLANO", days=2)
    _reserve(order, "6", day=_day(2), quant=_planned_quant(_day(2)))
    _reserve(order, "14", day=_day(2))

    item = _one(_promise(order))
    assert (item.reservation, item.cause) == ("partial", "plan_short")
    assert (item.qty, item.missing_qty) == ("20", "10")
    assert item.label == "Baguete de tradição: 10 de 20 sem reserva"
    assert item.detail == f"A produção planejada para {commitment_day_label(_day(2))} não cobre o pedido."


def test_demanda_de_hoje_sem_lote_e_risco(baguete):
    order = _order("HOJE-SEM-LOTE", days=0)
    _reserve(order, "4", day=_day())

    item = _one(_promise(order))
    assert (item.reservation, item.cause) == ("lost", "no_batch")
    assert item.detail == "Não há lote planejado para hoje."


def test_a_sobra_de_hoje_nao_lastreia_a_encomenda_de_amanha(baguete, ficha):
    """Dono, 18/11/2026: a encomenda mede só o lote da data. Vitrine cheia hoje
    não cobre a demanda de amanhã que passou do plano."""
    loja = Position.objects.get(ref="loja")
    stock.receive(quantity=Decimal("50"), sku=SKU, position=loja, reason="vitrine de hoje")
    _lot(ficha, "2", days=1)
    order = _order("ENC-SOBRA", days=1)
    _reserve(order, "4", day=_day(1))

    item = _one(_promise(order))
    assert (item.cause, item.missing_qty) == ("plan_short", "2")


def test_produto_feito_na_hora_nao_espera_lote(db):
    """Reserva sem saldo de produto ``demand_ok`` (café, croque) é o desenho, não uma falta."""
    Product.objects.create(
        sku="CROQUE", name="Croque monsieur", unit="un", base_price_q=2800, availability_policy="demand_ok",
        is_sellable=True,
    )
    order = _order("HOJE-CROQUE", days=0)
    _reserve(order, "2", day=_day(), sku="CROQUE")

    assert order_promise.read_for([order]) == {}


# ── P1-22: o pedido pago do dia que espera o lote ────────────────────────────


def _paid_today(ref: str) -> Order:
    order = _order(ref, days=None, payment={"method": "pix", "intent_ref": f"INT-{ref}"})
    PaymentService.create_intent(order.ref, order.total_q, "pix", gateway="mock", ref=f"INT-{ref}")
    PaymentService.authorize(f"INT-{ref}")
    PaymentService.capture(f"INT-{ref}")
    return order


def test_pedido_pago_do_dia_que_espera_o_lote_tem_o_selo_e_o_bloqueio(ficha, baguete, gerente, relogio):
    from shopman.shop.services import waitlist

    Product.objects.filter(pk=baguete.pk).update(metadata={"ready_from": "12:00"})
    relogio(9)
    _lot(ficha, "10", days=0)
    order = _paid_today("HOJE-PAGO")
    _reserve(order, "4", day=_day(), quant=_planned_quant(_day()))
    order = Order.objects.get(pk=order.pk)

    # A fila de espera não conta o pedido pago: era dela que o selo dependia.
    assert waitlist.state_for(order) == waitlist.NONE

    card = build_order_card(order, user=gerente)
    assert card.waitlist_state == ""
    assert (card.promise.state, card.promise.label) == ("waiting_batch", "Esperando o lote")
    assert card.promise.actions == ()
    advance = next(action for action in card.actions if action.ref == "advance")
    assert advance.enabled is False
    assert advance.reason == (
        "O preparo abre quando o lote ficar pronto. "
        "Baguete de tradição: o lote de hoje não começou. Fica pronto às 12h."
    )
    assert (card.can_advance, card.next_status) == (False, "")
    assert card.advance_block_label == "Esperando o lote…"
    assert card.advance_block_reason == advance.reason
    assert card.attention == ""  # espera saudável não é "precisa de você"

    detail = build_operator_order(order, user=gerente)
    assert detail.promise.state == "waiting_batch"
    assert detail.can_advance is False
    assert detail.advance_block_label == "Esperando o lote…"
    assert next(action for action in detail.actions if action.ref == "advance").enabled is False
    line = next(item for item in detail.pending if item.key == "advance")
    assert (line.tone, line.label) == ("info", "Esperando o lote")
    assert line.reason == advance.reason


def test_lote_pronto_devolve_o_iniciar_preparo(ficha, gerente, relogio):
    relogio(9)
    work_order = _lot(ficha, "10", days=0)
    order = _paid_today("HOJE-PAGO-PRONTO")
    _reserve(order, "4", day=_day(), quant=_planned_quant(_day()))

    work_order.refresh_from_db()
    craft.finish(work_order, finished=Decimal("10"), expected_rev=work_order.rev)

    card = build_order_card(Order.objects.get(pk=order.pk), user=gerente)
    assert card.promise is None
    assert next(action for action in card.actions if action.ref == "advance").enabled is True
    assert card.advance_block_label == ""


def test_o_bloqueio_do_pagamento_vem_antes_do_lote(ficha, gerente, relogio):
    """Quem espera o dinheiro lê a frase do dinheiro; o lote aparece só como selo."""
    relogio(9)
    _lot(ficha, "10", days=0)
    order = _order("HOJE-SEM-PIX", days=None, payment={"method": "pix", "intent_ref": "INT-HOJE-SEM-PIX"})
    PaymentService.create_intent(order.ref, order.total_q, "pix", gateway="mock", ref="INT-HOJE-SEM-PIX")
    _reserve(order, "4", day=_day(), quant=_planned_quant(_day()))

    card = build_order_card(Order.objects.get(pk=order.pk), user=gerente)
    assert card.promise.state == "waiting_batch"
    assert card.advance_block_label != "Esperando o lote…"
    assert card.payment_pending is True


# ── O painel ─────────────────────────────────────────────────────────────────


def test_no_painel_a_encomenda_em_risco_pede_alguem_e_a_inteira_nao(ficha, gerente):
    _lot(ficha, "20", days=2)
    inteira = _order("ENC-INTEIRA", days=2)
    _reserve(inteira, "4", day=_day(2), quant=_planned_quant(_day(2)))
    em_risco, work_order, _hold = _encomenda(ficha, "ENC-EM-RISCO", days=1, slot="15:00-15:30")
    craft.void(work_order, reason="Forno parou")

    queue = build_two_zone_queue(user=gerente)

    cards = {card.ref: card for card in queue.preorders}
    assert cards["ENC-INTEIRA"].promise is None
    assert cards["ENC-INTEIRA"].attention == ""
    risk = cards["ENC-EM-RISCO"]
    assert risk.promise.state == "at_risk"
    assert risk.attention == "promise"
    # A meta é o combinado com o cliente: é contra ele que a promessa quebra.
    assert risk.goal_label == "combinado para amanhã às 15h"
    assert risk.goal_minutes > 0


def test_o_numero_de_consultas_nao_cresce_com_o_numero_de_pedidos(ficha, baguete, relogio):
    """Um painel com 3 pedidos e um com 15 custam as mesmas consultas."""
    Product.objects.filter(pk=baguete.pk).update(metadata={"ready_from": "12:00"})
    relogio(9)
    _lot(ficha, "200", days=0)
    _lot(ficha, "200", days=1)
    cancelado = _lot(ficha, "200", days=2)

    def painel(prefix: str, groups: int) -> list[Order]:
        orders = []
        for index in range(groups):
            hoje = _order(f"{prefix}-HOJE-{index}", days=0)
            _reserve(hoje, "4", day=_day(), quant=_planned_quant(_day()))
            amanha = _order(f"{prefix}-AMANHA-{index}", days=1)
            _reserve(amanha, "4", day=_day(1), quant=_planned_quant(_day(1)))
            _reserve(amanha, "2", day=_day(1))
            depois = _order(f"{prefix}-DEPOIS-{index}", days=2)
            _reserve(depois, "4", day=_day(2), quant=_planned_quant(_day(2)))
            orders.extend([hoje, amanha, depois])
        return orders

    small = painel("P", 1)
    large = painel("G", 5)
    craft.void(cancelado, reason="Forno parou")
    small = [Order.objects.get(pk=order.pk) for order in small]
    large = [Order.objects.get(pk=order.pk) for order in large]

    with CaptureQueriesContext(connection) as few:
        first = order_promise.read_for(small)
    with CaptureQueriesContext(connection) as many:
        second = order_promise.read_for(large)

    # Os três casos estão nos dois painéis: esperando o lote, inteiro e em risco.
    assert {promise.state for promise in first.values()} == {"waiting_batch", "at_risk"}
    assert len(first) == 2 and len(second) == 10
    assert len(many) == len(few)
    assert len(few) <= 8
