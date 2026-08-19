"""Reconciliação cruzada Payman × livro-caixa (WP-7 do CASHMAN-PLAN, ADR-022 §5).

O mesmo fato (dinheiro entrou ou saiu da gaveta) tem duas escritas: o intent
``cash`` no Payman e a linha ``sale``/``cod_settled``/``refund`` no livro do
turno. ``cash_ledger_mismatch`` prova que elas batem; os checks por pedido
aceitam a venda mista (um intent por MÉTODO) sem falso positivo.

As vendas aqui são as do PDV de verdade (``pos_service.close_sale``,
``cancel_recent_order``, ``settle_delivery_cash``): o contrato independe da
superfície, e o que se reconcilia é o que o shop deixa no banco.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.utils import timezone
from shopman.cashman import Entry
from shopman.cashman import services as cash
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.backstage.models import DayClosing
from shopman.backstage.services.financial_reconciliation import build_financial_reconciliation
from shopman.shop.models import Channel, Shop
from shopman.shop.services import operator_orders
from shopman.shop.services import pos as pos_service

pytestmark = pytest.mark.django_db


class _Counter:
    """Um balcão: canal PDV, um item de R$ 12, operador com turno aberto e fundo de R$ 100."""

    def __init__(self):
        from shopman.offerman.models import Product

        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={
                "confirmation": {"mode": "immediate"},
                "payment": {"method": "cash", "timing": "external"},
                "stock": {"check_on_commit": False},
            },
        )
        Product.objects.create(sku="PAO", name="Pão", base_price_q=1200, is_published=True, is_sellable=True)
        self.operator = get_user_model().objects.create_user(username="marina", password="x")
        self.shift = cash.open_shift(operator=self.operator, float_q=10000)

    def close(self, *, client_request_id: str, **overrides):
        payload = {
            "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Cliente",
            "payment_method": "cash",
            "client_request_id": client_request_id,
            "cash_shift_id": self.shift.pk,
        }
        payload.update(overrides)
        result = pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor=f"pos:{self.operator.username}",
            operator_username=self.operator.username,
        )
        # Em produção a confirmação imediata do PDV roda no on_commit do
        # ``commit_session``, ANTES da liquidação (``_settle_pos_sale``). Dentro
        # da transação do teste os callbacks ficam adiados, e executá-los depois
        # da liquidação regravaria o ``order.data`` velho (sem os intents) por
        # cima do que a liquidação persistiu. Aplica-se o status que o lifecycle
        # daria, sem replay: sem isso o pedido ficaria ``new`` com saldo
        # capturado (``paid_order_not_confirmed``), que não é o que se prova aqui.
        Order.objects.filter(ref=result.order_ref, status=Order.Status.NEW).update(status=Order.Status.ACCEPTED)
        return result


@pytest.fixture
def counter():
    return _Counter()


def _codes(report) -> list[str]:
    return [issue.code for issue in report.issues]


def _issue(report, code: str):
    return next(issue for issue in report.issues if issue.code == code)


def _today():
    return timezone.localdate()


# ── Sem falso positivo: o que o PDV deixa no banco reconcilia limpo ───────


def test_venda_so_dinheiro_com_troco_bate_nos_dois_livros(counter):
    """Cliente entrega R$ 20 por R$ 12: o Payman captura 12, a gaveta recebe 12."""
    counter.close(
        client_request_id="c1",
        payment_tenders=[{"method": "cash", "amount_q": 2000, "collection": "terminal"}],
        tendered_amount_q=2000,
    )
    DayClosing.objects.create(date=_today(), closed_by=counter.operator, data={"items": []})

    report = build_financial_reconciliation(reconciliation_date=_today(), require_closing=True)

    assert _codes(report) == []
    assert report.cash_ledger.payman_net_q == 1200
    assert report.cash_ledger.ledger_net_q == 1200
    assert report.cash_ledger.difference_q == 0
    assert report.by_method == {"cash": 1}
    assert report.by_gateway == {"-": 1}


def test_venda_mista_dinheiro_mais_pix_atestado_nao_e_falso_positivo(counter):
    """Um intent por método: cash 200 + pix 1000 (atestado, sem gateway) somam o
    total. Nenhum deles bate sozinho, e é a soma que a reconciliação cobra."""
    result = counter.close(
        client_request_id="c2",
        payment_tenders=[
            {"method": "cash", "amount_q": 200, "collection": "terminal"},
            {"method": "pix", "amount_q": 1000, "collection": "terminal"},
        ],
    )
    pix = PaymentIntent.objects.get(order_ref=result.order_ref, method="pix")
    assert pix.gateway == "" and pix.gateway_data["asserted_at_terminal"] is True
    DayClosing.objects.create(date=_today(), closed_by=counter.operator, data={"items": []})

    report = build_financial_reconciliation(reconciliation_date=_today(), require_closing=True)

    assert _codes(report) == []
    assert report.intent_count == 2
    assert report.captured_q == 1200
    # Só o dinheiro entra no cruzamento com a gaveta; o pix atestado fica no Payman.
    assert report.cash_ledger.payman_net_q == 200
    assert report.cash_ledger.ledger_net_q == 200


def test_venda_mista_dinheiro_mais_external_tambem_bate(counter):
    counter.close(
        client_request_id="c3",
        payment_tenders=[
            {"method": "cash", "amount_q": 500, "collection": "terminal"},
            {"method": "external", "amount_q": 700, "collection": "terminal"},
        ],
    )

    report = build_financial_reconciliation(reconciliation_date=_today())

    assert _codes(report) == ["day_closing_missing"]
    assert report.cash_ledger.payman_net_q == 500 == report.cash_ledger.ledger_net_q


def test_cod_acertado_conta_no_dia_do_acerto_nos_dois_livros(counter):
    """Venda de ontem paga na porta: ontem a linha ``sale`` vale zero e não há
    intent de dinheiro; hoje o acerto grava, juntos, o intent capturado e o
    ``cod_settled``. Nenhum dos dois dias diverge."""
    yesterday = _today() - timedelta(days=1)
    order = Order.objects.create(
        ref="COD-1",
        channel_ref="pdv",
        status=Order.Status.DISPATCHED,
        total_q=3000,
        data={
            "fulfillment_type": "delivery",
            "payment": {
                "method": "cash",
                "collection": "on_delivery",
                "amount_q": 3000,
                "tenders": [{"method": "cash", "amount_q": 3000, "collection": "on_delivery", "status": "pending"}],
            },
        },
    )
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=1))
    cash.record(
        "sale",
        shift=counter.shift,
        operator=counter.operator,
        amount_q=0,
        order_ref=order.ref,
        at=timezone.now() - timedelta(days=1),
    )

    before = build_financial_reconciliation(reconciliation_date=yesterday)
    assert _codes(before) == ["day_closing_missing"]
    assert before.cash_ledger.payman_net_q == 0 == before.cash_ledger.ledger_net_q

    operator_orders.settle_delivery_cash(order, cash_shift=counter.shift, actor="pos:marina")

    today = build_financial_reconciliation(reconciliation_date=_today())
    assert _codes(today) == ["day_closing_missing"]
    assert today.cash_ledger.payman_captured_q == 3000
    assert today.cash_ledger.ledger_cod_settled_q == 3000
    assert today.cash_ledger.difference_q == 0
    # O pedido é de ontem, mas o intent é de hoje: a soma por pedido roda mesmo assim.
    assert today.intent_count == 1 and today.order_count == 0

    again = build_financial_reconciliation(reconciliation_date=yesterday)
    assert again.cash_ledger.difference_q == 0


def test_troco_do_entregador_fica_fora_do_cruzamento_e_ganha_o_seu_espelho(counter):
    """``courier_out``/``courier_in`` não são pagamento: o cruzamento Payman ×
    livro não os vê. O espelho deles é outro: saiu e não voltou é ``warning``
    (``courier_change_unsettled``), e some quando o acerto diz quanto voltou
    (zero incluído)."""
    order = Order.objects.create(
        ref="DLV-1",
        channel_ref="pdv",
        status=Order.Status.READY,
        total_q=3000,
        data={
            "fulfillment_type": "delivery",
            "payment": {
                "method": "cash",
                "collection": "on_delivery",
                "amount_q": 3000,
                "change_for_q": 5000,
                "tenders": [{"method": "cash", "amount_q": 3000, "collection": "on_delivery", "status": "pending"}],
            },
        },
    )
    operator_orders.advance_order(order, actor="marina", change_out_q=2000, cash_shift=counter.shift)

    report = build_financial_reconciliation(reconciliation_date=_today())
    assert "cash_ledger_mismatch" not in _codes(report)
    issue = _issue(report, "courier_change_unsettled")
    assert issue.severity == "warning"
    assert issue.context == {"order_count": 1, "courier_out_q": 2000, "orders": "DLV-1"}
    assert report.cash_ledger.ledger_net_q == 0  # o troco na rua não é venda

    operator_orders.settle_delivery_cash(order, cash_shift=counter.shift, actor="marina", change_back_q=0)

    report = build_financial_reconciliation(reconciliation_date=_today())
    assert "courier_change_unsettled" not in _codes(report)
    assert "cash_ledger_mismatch" not in _codes(report)
    assert report.cash_ledger.payman_captured_q == 3000 == report.cash_ledger.ledger_cod_settled_q


def test_cancelamento_devolve_o_dinheiro_nos_dois_livros(counter, django_capture_on_commit_callbacks):
    """Cancel no PDV: ``REFUND`` no Payman e linha ``refund`` na gaveta, mesmo
    instante. Capturado 12, devolvido 12; gaveta +12 −12. Nada a gritar."""
    result = counter.close(client_request_id="c4", tendered_amount_q=1200)
    with django_capture_on_commit_callbacks(execute=True):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:marina")
    assert Order.objects.get(ref=result.order_ref).status == Order.Status.CANCELLED
    DayClosing.objects.create(date=_today(), closed_by=counter.operator, data={"items": []})

    report = build_financial_reconciliation(reconciliation_date=_today(), require_closing=True)

    assert _codes(report) == []
    assert report.captured_q == 1200 and report.refunded_q == 1200
    assert report.cash_ledger.as_dict() == {
        "payman_captured_q": 1200,
        "payman_refunded_q": 1200,
        "payman_net_q": 0,
        "ledger_sale_q": 1200,
        "ledger_cod_settled_q": 0,
        "ledger_refund_q": -1200,
        "ledger_net_q": 0,
        "difference_q": 0,
    }


def test_cancelamento_de_venda_mista_devolve_so_o_dinheiro_da_gaveta(counter, django_capture_on_commit_callbacks):
    """Mista cash 200 + pix 1000 cancelada: o Payman estorna os dois intents
    (o pix atestado sem gateway), a gaveta devolve só os 200. Os dois lados do
    dinheiro continuam iguais, e o cancelado não fica com saldo capturado."""
    result = counter.close(
        client_request_id="c5",
        payment_tenders=[
            {"method": "cash", "amount_q": 200, "collection": "terminal"},
            {"method": "pix", "amount_q": 1000, "collection": "terminal"},
        ],
    )
    with django_capture_on_commit_callbacks(execute=True):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:marina")

    report = build_financial_reconciliation(reconciliation_date=_today())

    assert _codes(report) == ["day_closing_missing"]
    assert report.refunded_q == 1200
    assert report.cash_ledger.payman_captured_q == 200
    assert report.cash_ledger.payman_refunded_q == 200
    assert report.cash_ledger.ledger_refund_q == -200
    assert report.cash_ledger.difference_q == 0


# ── Divergência real: uma escrita sem a outra ─────────────────────────────


def test_intent_de_dinheiro_sem_linha_no_livro_e_divergencia(counter):
    """Intent cash capturado sem a linha ``sale``: a gaveta não sabe desse
    dinheiro. O issue traz os dois números, a diferença e o pedido."""
    counter.close(client_request_id="c6", tendered_amount_q=1200)  # limpa: 12 nos dois
    PaymentService.settle("ORD-GHOST", 2500, "cash", ref="PAY-GHOST")
    Order.objects.create(
        ref="ORD-GHOST",
        channel_ref="pdv",
        status=Order.Status.COMPLETED,
        total_q=2500,
        data={"payment": {"method": "cash", "collection": "terminal", "intent_ref": "PAY-GHOST"}},
    )
    DayClosing.objects.create(date=_today(), closed_by=counter.operator, data={"items": []})

    report = build_financial_reconciliation(reconciliation_date=_today(), require_closing=True)

    assert _codes(report) == ["cash_ledger_mismatch"]
    issue = _issue(report, "cash_ledger_mismatch")
    assert issue.severity == "error"
    assert issue.context == {
        "payman_cash_q": 3700,
        "ledger_cash_q": 1200,
        "difference_q": 2500,
        "order_count": 1,
        "orders": "ORD-GHOST",
    }
    assert report.has_errors is True


def test_linha_no_livro_sem_intent_e_divergencia(counter):
    """Linha ``sale`` com dinheiro sem intent no Payman: o livro de pagamentos
    não sabe dessa venda. Diferença negativa, pedido apontado."""
    cash.record("sale", shift=counter.shift, operator=counter.operator, amount_q=900, order_ref="ORD-ONLY-LEDGER")

    report = build_financial_reconciliation(reconciliation_date=_today())

    assert "cash_ledger_mismatch" in _codes(report)
    issue = _issue(report, "cash_ledger_mismatch")
    assert issue.context["payman_cash_q"] == 0
    assert issue.context["ledger_cash_q"] == 900
    assert issue.context["difference_q"] == -900
    assert issue.context["orders"] == "ORD-ONLY-LEDGER"


def test_erros_que_se_compensam_no_total_continuam_sendo_erros(counter):
    """Intent sem linha (A, 12) e linha sem intent (B, 12): o total do dia
    bate, e mesmo assim são dois fatos com uma escrita só cada."""
    PaymentService.settle("ORD-A", 1200, "cash", ref="PAY-A")
    Order.objects.create(ref="ORD-A", channel_ref="pdv", status=Order.Status.COMPLETED, total_q=1200,
                         data={"payment": {"method": "cash", "collection": "terminal", "intent_ref": "PAY-A"}})
    cash.record("sale", shift=counter.shift, operator=counter.operator, amount_q=1200, order_ref="ORD-B")

    report = build_financial_reconciliation(reconciliation_date=_today())

    issue = _issue(report, "cash_ledger_mismatch")
    assert issue.context["difference_q"] == 0
    assert issue.context["orders"] == "ORD-A, ORD-B"
    assert "compensam" in issue.message


def test_cancel_pelo_gestor_nao_estorna_dinheiro_e_o_cruzamento_fica_quieto(counter, django_capture_on_commit_callbacks):
    """Cancelar não é devolver: o cancel pelo gestor (não pelo PDV) deixa o intent
    de dinheiro capturado e não grava ``refund`` na gaveta. Os dois livros seguem
    dizendo a mesma coisa (o dinheiro está na casa), o cruzamento fica quieto, e
    o que existe é a pendência de devolução, visível para quem abrir a gaveta."""
    from shopman.shop.services import payment as payment_service

    result = counter.close(client_request_id="c7", tendered_amount_q=1200)
    order = Order.objects.get(ref=result.order_ref)
    with django_capture_on_commit_callbacks(execute=True):
        operator_orders.cancel_order(order, reason="customer_requested", actor="gestor:pablo")
    assert PaymentIntent.objects.get(order_ref=order.ref).status == PaymentIntent.Status.CAPTURED
    assert not Entry.objects.filter(kind=Entry.Kind.REFUND).exists()

    report = build_financial_reconciliation(reconciliation_date=_today())

    assert "cash_ledger_mismatch" not in _codes(report)
    assert [p.order_ref for p in payment_service.pending_cash_refunds(channel_ref="pdv")] == [order.ref]


def test_estorno_so_no_payman_sem_linha_na_gaveta_aparece(counter):
    """Um ``REFUND`` gravado direto no Payman, sem ninguém abrir gaveta (caminho
    que o ``refund_cash`` existe para impedir): o dinheiro saiu de um livro e
    ficou no outro. É exatamente o que este check existe para pegar."""
    result = counter.close(client_request_id="c7", tendered_amount_q=1200)
    order = Order.objects.get(ref=result.order_ref)
    intent = PaymentIntent.objects.get(order_ref=order.ref)
    PaymentService.refund(intent.ref, reason="fora do balcão")
    assert PaymentIntent.objects.get(pk=intent.pk).status == PaymentIntent.Status.REFUNDED
    assert not Entry.objects.filter(kind=Entry.Kind.REFUND).exists()

    report = build_financial_reconciliation(reconciliation_date=_today())

    issue = _issue(report, "cash_ledger_mismatch")
    assert issue.context["payman_cash_q"] == 0
    assert issue.context["ledger_cash_q"] == 1200
    assert issue.context["orders"] == order.ref


def test_comando_persiste_o_cruzamento_e_falha_na_divergencia(counter):
    PaymentService.settle("ORD-GHOST-2", 700, "cash", ref="PAY-GHOST-2")
    Order.objects.create(ref="ORD-GHOST-2", channel_ref="pdv", status=Order.Status.COMPLETED, total_q=700,
                         data={"payment": {"method": "cash", "collection": "terminal", "intent_ref": "PAY-GHOST-2"}})
    closing = DayClosing.objects.create(date=_today(), closed_by=counter.operator, data={"items": []})
    out = StringIO()

    with pytest.raises(CommandError):
        call_command("reconcile_financial_day", date=_today().isoformat(), no_alert=True, stdout=out)

    closing.refresh_from_db()
    summary = closing.data["financial_reconciliation"]
    assert summary["cash_ledger"]["payman_net_q"] == 700
    assert summary["cash_ledger"]["ledger_net_q"] == 0
    assert summary["cash_ledger"]["difference_q"] == 700
    assert [e["code"] for e in closing.data["financial_reconciliation_errors"]] == ["cash_ledger_mismatch"]
    assert "Dinheiro (Payman × livro-caixa): payman=700q" in out.getvalue()


# ── Checks por pedido: somar, não exigir um intent ─────────────────────────


def _order(ref: str, *, total_q: int = 1200, payment: dict | None = None, status=Order.Status.COMPLETED) -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=status,
        total_q=total_q,
        data={"payment": payment or {"method": "pix", "intent_ref": f"PAY-{ref}"}},
    )


def test_soma_dos_liquidados_diferente_do_total_e_uma_divergencia_por_pedido(counter):
    """Mista cash 200 + external 500 num pedido de 12: os intents somam 7."""
    _order("ORD-SHORT", payment={
        "method": "mixed",
        "collection": "terminal",
        "tenders": [
            {"method": "cash", "amount_q": 200, "collection": "terminal", "intent_ref": "PAY-SHORT-CASH"},
            {"method": "external", "amount_q": 500, "collection": "terminal", "intent_ref": "PAY-SHORT-EXT"},
        ],
    })
    PaymentService.settle("ORD-SHORT", 200, "cash", ref="PAY-SHORT-CASH")
    PaymentService.settle("ORD-SHORT", 500, "external", ref="PAY-SHORT-EXT")
    cash.record("sale", shift=counter.shift, operator=counter.operator, amount_q=200, order_ref="ORD-SHORT",
                payment_ref="PAY-SHORT-CASH")

    report = build_financial_reconciliation(reconciliation_date=_today())

    assert _codes(report) == ["day_closing_missing", "intent_amount_mismatch"]
    issue = _issue(report, "intent_amount_mismatch")
    assert issue.order_ref == "ORD-SHORT" and issue.intent_ref == ""
    assert issue.context["order_total_q"] == 1200
    assert issue.context["intents_amount_q"] == 700
    assert issue.context["intent_count"] == 2
    assert issue.context["intent_refs"] == "PAY-SHORT-CASH, PAY-SHORT-EXT"


def test_dois_intents_capturados_do_mesmo_metodo_e_cobranca_em_dobro(counter):
    _order("ORD-DOUBLE", payment={"method": "cash", "collection": "terminal", "intent_ref": "PAY-DOUBLE-1"})
    PaymentService.settle("ORD-DOUBLE", 600, "cash", ref="PAY-DOUBLE-1")
    PaymentService.settle("ORD-DOUBLE", 600, "cash", ref="PAY-DOUBLE-2")
    cash.record("sale", shift=counter.shift, operator=counter.operator, amount_q=1200, order_ref="ORD-DOUBLE",
                payment_ref="PAY-DOUBLE-1")

    report = build_financial_reconciliation(reconciliation_date=_today())

    # Soma bate (6+6=12); o que grita é o mesmo método duas vezes e o intent
    # que o pedido não aponta.
    assert "intent_amount_mismatch" not in _codes(report)
    issue = _issue(report, "multiple_captured_intents_for_order")
    assert issue.severity == "critical"
    assert issue.context == {"method": "cash", "intent_count": 2}
    assert _issue(report, "order_intent_ref_mismatch").intent_ref == "PAY-DOUBLE-2"


def test_intent_obsoleto_cancelado_nao_soa_como_divergencia():
    """Carrinho mudou antes de pagar: o intent antigo foi cancelado (valor
    velho), o novo capturou o total. O morto não paga nada e não entra."""
    order = _order("ORD-STALE", payment={"method": "pix", "intent_ref": "PAY-STALE-NEW"})
    PaymentIntent.objects.create(ref="PAY-STALE-OLD", order_ref=order.ref, method="pix",
                                 status=PaymentIntent.Status.CANCELLED, amount_q=1000, gateway="efi")
    new = PaymentIntent.objects.create(ref="PAY-STALE-NEW", order_ref=order.ref, method="pix",
                                       status=PaymentIntent.Status.CAPTURED, amount_q=1200, gateway="efi")
    from shopman.payman.models import PaymentTransaction

    PaymentTransaction.objects.create(intent=new, type=PaymentTransaction.Type.CAPTURE, amount_q=1200, gateway_id="gw")

    report = build_financial_reconciliation(reconciliation_date=_today())

    assert "intent_amount_mismatch" not in _codes(report)
    assert "multiple_captured_intents_for_order" not in _codes(report)
    # O obsoleto continua apontado como "outro intent" (aviso), como antes.
    assert _issue(report, "order_intent_ref_mismatch").intent_ref == "PAY-STALE-OLD"


def test_intent_em_curso_com_valor_errado_continua_divergencia():
    order = _order("ORD-OPEN", status=Order.Status.NEW)
    PaymentIntent.objects.create(ref="PAY-ORD-OPEN", order_ref=order.ref, method="pix",
                                 status=PaymentIntent.Status.PENDING, amount_q=1000, gateway="efi")

    report = build_financial_reconciliation(reconciliation_date=_today())

    issue = _issue(report, "intent_amount_mismatch")
    assert issue.intent_ref == "PAY-ORD-OPEN"
    assert issue.context == {"order_total_q": 1200, "intent_amount_q": 1000}


def test_tender_apontando_intent_inexistente_e_erro_localizado():
    _order("ORD-BADREF", payment={
        "method": "mixed",
        "collection": "terminal",
        "tenders": [{"method": "cash", "amount_q": 1200, "collection": "terminal", "intent_ref": "PAY-NOPE"}],
    })

    report = build_financial_reconciliation(reconciliation_date=_today())

    issue = _issue(report, "order_data_intent_not_found")
    assert issue.intent_ref == "PAY-NOPE"
    assert issue.context == {"where": "tenders"}
