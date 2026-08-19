"""Forma de pagamento no B.I. (BI-QUESTION-CATALOG §3.3/F1).

O que estes testes cobram, além do caminho feliz:

- **pagamento dividido** reparte o valor entre as formas, em vez de creditar o
  total do pedido a uma delas;
- **cobrança na entrega ainda não recebida** NÃO conta como recebido, e aparece
  na métrica própria — dinheiro na rua não é caixa;
- **a forma crua do histórico** que o vocabulário não conhece **não some** num
  balde mudo: aparece com o texto original;
- **a mesma regra vale no fechamento e no B.I.** — a divergência entre as duas
  telas era o risco de reimplementar a repartição.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.backstage.models import HistoricalSale
from shopman.backstage.projections.bi_explore import ExploreError, build_bi_explore, validate_config
from shopman.backstage.projections.bi_payments import normalize_historical_payment
from shopman.backstage.services.payments import iter_order_payments
from shopman.backstage.tests.support import historical_batch


def _cells(report):
    return {(row.key, row.key2): row.value for row in report.rows}


def _labels(report):
    return {row.key: row.label for row in report.rows}


# ── Repartição do pedido (a regra compartilhada) ─────────────────────────────


def test_order_without_tenders_pays_the_whole_total_in_one_method():
    entries = list(iter_order_payments({"payment": {"method": "pix"}}, 2500))
    assert [(e.method, e.amount_q, e.pending) for e in entries] == [("pix", 2500, False)]


def test_order_without_payment_data_is_external_not_unknown():
    # "external" é o que o fechamento sempre usou; trocar aqui reescreveria
    # relatório antigo.
    entries = list(iter_order_payments({}, 900))
    assert [(e.method, e.amount_q) for e in entries] == [("external", 900)]


def test_split_payment_is_shared_between_methods_not_credited_to_one():
    data = {"payment": {"method": "mixed", "tenders": [
        {"method": "cash", "amount_q": 1000},
        {"method": "pix", "amount_q": 1500},
    ]}}
    entries = list(iter_order_payments(data, 2500))
    assert [(e.method, e.amount_q) for e in entries] == [("cash", 1000), ("pix", 1500)]


def test_cash_on_delivery_not_received_is_pending_not_cash_in_hand():
    data = {"payment": {"method": "cash", "collection": "on_delivery"}}
    entry = next(iter(iter_order_payments(data, 3000)))
    assert entry.pending is True

    settled = {"payment": {"method": "cash", "collection": "on_delivery",
                           "cod_settled_at": "2026-08-17T10:00:00"}}
    assert next(iter(iter_order_payments(settled, 3000))).pending is False


def test_closing_and_bi_count_the_same_money(db):
    """Duas fontes, um só dinheiro — o risco que este teste guarda é a divergência.

    O fechamento do dia lê o mix de meios do ``payman`` (intents capturados,
    ADR-022: dono único de "receita por método"); o explorador do B.I. lê a
    declaração do PEDIDO para cruzar com hora e canal. Quando o PDV liquida
    cada tender no ``payman`` (WP-3), os dois têm de bater ao centavo.
    """
    from django.utils import timezone
    from shopman.orderman.models import Order
    from shopman.payman.models import PaymentIntent, PaymentTransaction

    from shopman.backstage.services.closing import _payment_method_totals

    Order.objects.create(
        ref="PAY-SAME", channel_ref="pdv", status=Order.Status.COMPLETED, total_q=2500,
        data={"payment": {"method": "mixed", "tenders": [
            {"method": "cash", "amount_q": 1000},
            {"method": "pix", "amount_q": 1500},
        ]}},
    )
    for method, amount_q in (("cash", 1000), ("pix", 1500)):
        intent = PaymentIntent.objects.create(
            ref=f"PI-SAME-{method}", order_ref="PAY-SAME", method=method, amount_q=amount_q,
            status=PaymentIntent.Status.CAPTURED, gateway="" if method == "cash" else "test",
            captured_at=timezone.now(),
        )
        PaymentTransaction.objects.create(intent=intent, type=PaymentTransaction.Type.CAPTURE, amount_q=amount_q)

    totals = _payment_method_totals(timezone.localdate())
    report = build_bi_explore(metric="payment_received", by="payment_method")
    bi = {row.key: int(row.value) for row in report.rows}
    assert bi == {"cash": totals["cash"], "pix": totals["pix"]} == {"cash": 1000, "pix": 1500}


# ── No explorador ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_received_by_method_reads_the_order_not_the_closing(db):
    """Existe em dia sem fechamento — que era o limite do painel de caixa."""
    from shopman.orderman.models import Order

    Order.objects.create(ref="PAY-1", channel_ref="pdv", status=Order.Status.COMPLETED,
                         total_q=2000, data={"payment": {"method": "pix"}})
    Order.objects.create(ref="PAY-2", channel_ref="pdv", status=Order.Status.COMPLETED,
                         total_q=800, data={"payment": {"method": "cash"}})

    report = build_bi_explore(metric="payment_received", by="payment_method")
    assert {row.key: row.value for row in report.rows} == {"pix": 2000.0, "cash": 800.0}
    assert _labels(report) == {"pix": "PIX", "cash": "Dinheiro"}
    assert report.unit == "q"


@pytest.mark.django_db
def test_cancelled_order_pays_nobody(db):
    from shopman.orderman.models import Order

    Order.objects.create(ref="PAY-C", channel_ref="pdv", status=Order.Status.CANCELLED,
                         total_q=5000, data={"payment": {"method": "pix"}})
    assert build_bi_explore(metric="payment_received", by="payment_method").rows == ()


@pytest.mark.django_db
def test_pending_on_delivery_leaves_received_and_gets_its_own_metric(db):
    from shopman.orderman.models import Order

    Order.objects.create(
        ref="PAY-COD", channel_ref="web", status=Order.Status.COMPLETED, total_q=4000,
        data={"payment": {"method": "cash", "collection": "on_delivery"}},
    )
    received = build_bi_explore(metric="payment_received", by="payment_method")
    assert received.rows == ()  # não é caixa

    pending = build_bi_explore(metric="payment_pending", by="payment_method")
    assert {row.key: row.value for row in pending.rows} == {"cash": 4000.0}


@pytest.mark.django_db
def test_order_count_counts_orders_not_parcels(db):
    """Pedido dividido conta uma vez em cada forma — nunca duas na mesma."""
    from shopman.orderman.models import Order

    Order.objects.create(
        ref="PAY-SPLIT", channel_ref="pdv", status=Order.Status.COMPLETED, total_q=3000,
        data={"payment": {"method": "mixed", "tenders": [
            {"method": "cash", "amount_q": 1000},
            {"method": "cash", "amount_q": 500},
            {"method": "pix", "amount_q": 1500},
        ]}},
    )
    report = build_bi_explore(metric="payment_orders", by="payment_method")
    assert {row.key: row.value for row in report.rows} == {"cash": 1.0, "pix": 1.0}


@pytest.mark.django_db
def test_method_crossed_with_hour(db):
    """O cruzamento que o painel de caixa não fazia: forma × hora."""
    from shopman.orderman.models import Order

    order = Order.objects.create(ref="PAY-H", channel_ref="pdv", status=Order.Status.COMPLETED,
                                 total_q=1200, data={"payment": {"method": "pix"}})
    when = timezone.localtime(timezone.now()).replace(hour=9, minute=30)
    Order.objects.filter(pk=order.pk).update(created_at=when)

    report = build_bi_explore(metric="payment_received", by="payment_method", by2="hour")
    assert _cells(report) == {("pix", "09"): 1200.0}


# ── Histórico externo ────────────────────────────────────────────────────────


def test_known_historical_vocabulary_merges_with_native():
    assert normalize_historical_payment("Dinheiro")[0] == "cash"
    assert normalize_historical_payment("PIX")[0] == "pix"
    assert normalize_historical_payment("Cartão de Crédito")[0] == "credit"
    assert normalize_historical_payment("Cartão de Débito")[0] == "debit"
    assert normalize_historical_payment("Delivery - IFOOD")[0] == "ifood"
    assert normalize_historical_payment("Vale Refeição")[0] == "voucher"


def test_unknown_historical_form_keeps_its_own_words():
    """Balde mudo esconderia uma forma real que a casa usava — e eu não previ."""
    key, label = normalize_historical_payment("Fiado do seu Zé")
    assert key.startswith("raw:")
    assert label == "Fiado do seu Zé"


def test_blank_historical_form_is_external_not_a_row_of_its_own():
    assert normalize_historical_payment("")[0] == "external"
    assert normalize_historical_payment(None)[0] == "external"


@pytest.mark.django_db
def test_historical_and_native_share_the_axis_with_native_day_winning(db):
    from shopman.orderman.models import Order

    today = timezone.localtime(timezone.now())
    Order.objects.create(ref="PAY-N", channel_ref="pdv", status=Order.Status.COMPLETED,
                         total_q=1000, data={"payment": {"method": "pix"}})
    # Mesmo dia do nativo: a fusão descarta, senão a venda contaria duas vezes.
    HistoricalSale.objects.create(batch=historical_batch("yooga"), source="yooga", external_id=1, occurred_at=today,
                                  total_q=7777, payment="Dinheiro")
    # Dia sem nativo: entra, e soma no mesmo balde canônico.
    HistoricalSale.objects.create(batch=historical_batch("yooga"), source="yooga", external_id=2,
                                  occurred_at=today - timedelta(days=3),
                                  total_q=500, payment="Dinheiro")

    report = build_bi_explore(metric="payment_received", by="payment_method")
    assert {row.key: row.value for row in report.rows} == {"pix": 1000.0, "cash": 500.0}


@pytest.mark.django_db
def test_historical_sale_is_never_marked_as_owed(db):
    """O export só traz venda concluída — marcar pendente inventaria dívida."""
    HistoricalSale.objects.create(batch=historical_batch("yooga"), source="yooga", external_id=9,
                                  occurred_at=timezone.now() - timedelta(days=1),
                                  total_q=900, payment="Dinheiro")
    assert build_bi_explore(metric="payment_pending", by="payment_method").rows == ()


# ── Gramática ────────────────────────────────────────────────────────────────


def test_payment_metrics_are_in_the_grammar():
    assert validate_config("payment_received", "payment_method", "hour").family == "payment"
    with pytest.raises(ExploreError, match="não vale para Recebido"):
        validate_config("payment_received", "sku", "")
    # A receber na entrega não se cruza por hora: o instante que importa é o da
    # entrega, não o do pedido, e ele não é conhecido enquanto está na rua.
    with pytest.raises(ExploreError, match="não vale para A receber"):
        validate_config("payment_pending", "hour", "")


def test_payment_method_is_not_offered_where_it_makes_no_sense():
    with pytest.raises(ExploreError, match="não vale para Faturamento"):
        validate_config("revenue", "payment_method", "")
    with pytest.raises(ExploreError, match="não vale para Quantidade produzida"):
        validate_config("qty_produced", "payment_method", "")
