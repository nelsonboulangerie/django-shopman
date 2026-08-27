"""O shop grava a venda no livro-caixa (WP-3 do CASHMAN-PLAN, ADR-022).

Toda venda no terminal escreve UMA linha ``sale`` no livro do turno aberto do
operador: ``amount_q`` é o efeito em dinheiro na gaveta (zero para pix, cartão,
external e entrega paga na porta), ``payment_ref`` aponta o intent do dinheiro
no Payman, e o payload guarda método, recebido, troco e os intents por método.
Cancelar grava ``refund`` na gaveta de quem devolve; o acerto de entrega grava
``cod_settled`` na gaveta de quem recebeu. Nada disso é etiqueta no pedido.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from shopman.cashman import Entry
from shopman.cashman import services as cash
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.shop.models import Channel, Shop
from shopman.shop.services import operator_orders
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db

# O duplo-submit simultâneo se defende com `select_for_update` numa linha de
# `IdempotencyKey`, e trava de linha é coisa que só existe em banco de verdade:
# em SQLite as duas threads se estrangulam com "database table is locked" e o
# teste falha por limitação do banco, não por defeito do código. Mesmo idioma do
# `test_directive_dedupe` e dos outros testes de corrida do repositório.
requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency testing",
)

_MOCK_ADAPTERS = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    }
)


class _Counter:
    """Um balcão: canal PDV, um item, um operador com turno aberto e fundo de R$ 100."""

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

    def close(self, *, client_request_id: str, shift=None, operator=None, **overrides):
        payload = {
            "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Cliente",
            "payment_method": "cash",
            "client_request_id": client_request_id,
            "cash_shift_id": (shift or self.shift).pk,
        }
        payload.update(overrides)
        operator = operator or self.operator
        return pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor=f"pos:{operator.username}",
            operator_username=operator.username,
        )

    def sale_lines(self, shift=None):
        return list(Entry.objects.filter(shift=shift or self.shift, kind=Entry.Kind.SALE).order_by("id"))


@pytest.fixture
def counter():
    return _Counter()


# ── A linha `sale` ────────────────────────────────────────────────────────


def test_venda_em_dinheiro_grava_uma_linha_com_o_efeito_na_gaveta(counter):
    """Cliente entrega R$ 20 por R$ 12: entra R$ 12 na gaveta; troco fica no payload."""
    result = counter.close(
        client_request_id="c1",
        payment_tenders=[{"method": "cash", "amount_q": 2000, "collection": "terminal"}],
        tendered_q=2000,
    )

    (line,) = counter.sale_lines()
    intent = PaymentIntent.objects.get(order_ref=result.order_ref)
    assert line.amount_q == 1200
    assert line.order_ref == result.order_ref
    assert line.payment_ref == intent.ref
    assert line.operator == counter.operator
    assert line.payload["method"] == "cash"
    assert line.payload["received_q"] == 2000
    assert line.payload["change_q"] == 800
    assert line.payload["intents"] == {"cash": intent.ref}
    assert cash.balance(counter.shift) == 11200


@_MOCK_ADAPTERS
def test_venda_em_pix_passa_pelo_turno_sem_tocar_na_gaveta(counter):
    """Pix sozinho vai ao gateway; a linha existe (a venda é deste turno) com efeito zero."""
    result = counter.close(client_request_id="c2", payment_method="pix")

    (line,) = counter.sale_lines()
    order = Order.objects.get(ref=result.order_ref)
    assert line.amount_q == 0
    assert line.payload["method"] == "pix"
    assert line.payment_ref == order.data["payment"]["intent_ref"]
    assert cash.balance(counter.shift) == 10000
    # O PDV recebe o que exibir (QR do mock).
    assert result.payment.get("method") == "pix"


def test_venda_mista_e_uma_linha_com_o_dinheiro_e_todos_os_intents(counter):
    result = counter.close(
        client_request_id="c3",
        payment_tenders=[
            {"method": "cash", "amount_q": 500, "collection": "terminal"},
            {"method": "external", "amount_q": 700, "collection": "terminal"},
        ],
    )

    (line,) = counter.sale_lines()
    intents = {i.method: i for i in PaymentIntent.objects.filter(order_ref=result.order_ref)}
    assert line.amount_q == 500
    assert line.payment_ref == intents["cash"].ref
    assert line.payload["method"] == "mixed"
    assert line.payload["intents"] == {"cash": intents["cash"].ref, "external": intents["external"].ref}
    assert cash.balance(counter.shift) == 10500


def test_venda_mista_com_nota_maior_registra_o_troco_que_o_operador_devolveu(counter):
    """Cartão R$ 7 + nota de R$ 20 por R$ 12: entram R$ 5, voltam R$ 15 de troco.

    O acerto abate o excedente da linha de dinheiro (é dela que sai o troco), e
    era só isso que sobrava: o pedido guardava `cash 500` e mais nada. A tela
    prometia troco, o registro não sabia de troco nenhum — recibo, gestor e
    leitura do turno mostravam uma venda de R$ 5 sem devolução. Agora o valor em
    mão e o troco ficam gravados, e a gaveta segue com o EFEITO LÍQUIDO.
    """
    result = counter.close(
        client_request_id="c3b",
        payment_tenders=[
            {"method": "external", "amount_q": 700, "collection": "terminal"},
            {"method": "cash", "amount_q": 2000, "collection": "terminal"},
        ],
    )

    payment = Order.objects.get(ref=result.order_ref).data["payment"]
    assert payment["tendered_q"] == 2000
    assert payment["change_q"] == 1500
    assert payment["cash_received_q"] == 500

    (line,) = counter.sale_lines()
    assert line.amount_q == 500
    assert line.payload["received_q"] == 2000
    assert line.payload["change_q"] == 1500
    assert cash.balance(counter.shift) == 10500


def test_pix_numa_venda_mista_e_atestado_no_balcao(counter):
    """Pix dentro de mista não passa por gateway (QR estático): o intent nasce
    atestado, e a reconciliação vê que foi o balcão, não o gateway."""
    result = counter.close(
        client_request_id="c4",
        payment_tenders=[
            {"method": "cash", "amount_q": 200, "collection": "terminal"},
            {"method": "pix", "amount_q": 1000, "collection": "terminal"},
        ],
    )

    pix = PaymentIntent.objects.get(order_ref=result.order_ref, method="pix")
    assert pix.status == PaymentIntent.Status.CAPTURED
    assert pix.gateway == ""
    assert pix.gateway_data["asserted_at_terminal"] is True
    (line,) = counter.sale_lines()
    assert line.amount_q == 200


def test_entrega_paga_na_porta_e_venda_deste_turno_sem_dinheiro_ainda(counter):
    result = counter.close(
        client_request_id="c5",
        fulfillment_type="delivery",
        payment_collection="on_delivery",
        delivery_address="Rua das Flores, 1",
        customer_phone="+5543999990001",
    )

    (line,) = counter.sale_lines()
    assert line.amount_q == 0
    assert line.payload["collection"] == "on_delivery"
    assert line.payment_ref == ""
    assert not PaymentIntent.objects.filter(order_ref=result.order_ref).exists()


def test_repetir_a_venda_nao_duplica_a_linha(counter):
    first = counter.close(client_request_id="c6", tendered_q=1200)
    second = counter.close(client_request_id="c6", tendered_q=1200)

    assert first.order_ref == second.order_ref
    assert len(counter.sale_lines()) == 1


# ── Sem turno não há venda; e o pedido não carrega etiqueta de turno ─────


def test_sem_turno_aberto_a_venda_e_recusada_antes_do_commit(counter):
    other = get_user_model().objects.create_user(username="sem-turno", password="x")
    before = Order.objects.count()

    with pytest.raises(PosIntentError) as exc:
        counter.close(client_request_id="c7", cash_shift_id=None, operator=other)
    assert exc.value.code == "cash_shift_required"
    assert exc.value.status == 409
    assert Order.objects.count() == before


def test_turno_fechado_tambem_recusa(counter):
    cash.close_shift(counter.shift, counted_q=10000, actor=counter.operator)
    with pytest.raises(PosIntentError) as exc:
        counter.close(client_request_id="c8")
    assert exc.value.code == "cash_shift_required"


def test_o_pedido_nao_carrega_etiqueta_de_turno(counter):
    """A atribuição da venda ao turno É a linha do livro; o pedido só sabe o terminal."""
    result = counter.close(
        client_request_id="c9",
        payment_tenders=[{"method": "cash", "amount_q": 1200, "collection": "terminal"}],
        pos_terminal_ref="pdv-main",
    )

    order = Order.objects.get(ref=result.order_ref)
    assert "cash_shift_id" not in (order.data.get("pos") or {})
    assert order.data["pos"]["terminal_ref"] == "pdv-main"
    for tender in order.data["payment"]["tenders"]:
        assert "cash_shift_id" not in tender


# ── Devolução: o dinheiro sai da gaveta de agora ─────────────────────────


def test_cancelar_venda_em_dinheiro_grava_refund_na_gaveta_de_quem_devolve(counter, django_capture_on_commit_callbacks):
    result = counter.close(client_request_id="c10", tendered_q=1200)
    (sale_line,) = counter.sale_lines()

    with django_capture_on_commit_callbacks(execute=True):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:marina")

    refund = Entry.objects.get(shift=counter.shift, kind=Entry.Kind.REFUND)
    assert refund.amount_q == -1200
    assert refund.parent == sale_line
    assert refund.order_ref == result.order_ref
    assert refund.payment_ref == sale_line.payment_ref
    assert cash.balance(counter.shift) == 10000
    intent = PaymentService.get(sale_line.payment_ref)
    assert intent.status == PaymentIntent.Status.REFUNDED


def test_devolver_por_outro_turno_aponta_a_venda_mas_nao_o_parent(counter, django_capture_on_commit_callbacks):
    """Quem devolve tem outro turno: o dinheiro sai DESSA gaveta; ``parent`` só
    liga linhas do mesmo livro, então fica vazio e o ``order_ref`` liga as duas."""
    result = counter.close(client_request_id="c11", tendered_q=1200)
    manager = get_user_model().objects.create_user(username="pablo", password="x")
    from shopman.cashman import Terminal

    other_shift = cash.open_shift(operator=manager, terminal=Terminal.objects.create(ref="pdv-2"), float_q=0)

    with django_capture_on_commit_callbacks(execute=True):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:pablo")

    refund = Entry.objects.get(kind=Entry.Kind.REFUND)
    assert refund.shift == other_shift
    assert refund.parent is None
    assert cash.balance(other_shift) == -1200
    assert cash.balance(counter.shift) == 11200


def test_devolver_dinheiro_com_a_GAVETA_fechada_e_recusado_e_o_pedido_fica(counter):
    """Dinheiro não sai de gaveta fechada — senão sairia sem linha no livro.

    O teste exigia "operador sem turno", de quando o turno era da pessoa: bastava
    outro usuário pedir o cancelamento para cair na recusa. Agora a pergunta é
    sobre a GAVETA, e quem a responde é o estado dela — por isso o turno é
    fechado aqui antes de tentar. Com a gaveta aberta, qualquer pessoa do balcão
    devolve, e é assim que o balcão funciona.
    """
    from shopman.cashman import services as cash
    from shopman.cashman.models import Terminal

    result = counter.close(client_request_id="c12", tendered_q=1200)
    operador = get_user_model().objects.create_user(username="sem-turno", password="x")
    turno = cash.open_shift_for_terminal(Terminal.default())
    cash.close_shift(turno, counted_q=0, actor=operador)

    with pytest.raises(ValueError, match="Abra o caixa"):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:sem-turno")

    assert Order.objects.get(ref=result.order_ref).status != Order.Status.CANCELLED
    assert not Entry.objects.filter(kind=Entry.Kind.REFUND).exists()


@_MOCK_ADAPTERS
def test_cancelar_venda_em_pix_nao_precisa_de_turno_nem_mexe_na_gaveta(counter, django_capture_on_commit_callbacks):
    result = counter.close(client_request_id="c13", payment_method="pix")
    get_user_model().objects.create_user(username="sem-turno", password="x")

    with django_capture_on_commit_callbacks(execute=True):
        pos_service.cancel_recent_order(order_ref=result.order_ref, actor="pos:sem-turno")

    assert Order.objects.get(ref=result.order_ref).status == Order.Status.CANCELLED
    assert not Entry.objects.filter(kind=Entry.Kind.REFUND).exists()


# ── Acerto de entrega: o turno que RECEBEU ────────────────────────────────


def _cod_order(ref: str, total_q: int = 3000) -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=Order.Status.DISPATCHED,
        total_q=total_q,
        data={
            "fulfillment_type": "delivery",
            "payment": {
                "method": "cash",
                "collection": "on_delivery",
                "amount_q": total_q,
                "tenders": [{"method": "cash", "amount_q": total_q, "collection": "on_delivery", "status": "pending"}],
            },
        },
    )


def test_acerto_de_entrega_grava_cod_settled_no_turno_de_quem_recebeu(counter):
    order = _cod_order("COD-1")

    amount = operator_orders.settle_delivery_cash(order, cash_shift=counter.shift, actor="pos:marina")

    assert amount == 3000
    line = Entry.objects.get(shift=counter.shift, kind=Entry.Kind.COD_SETTLED)
    intent = PaymentIntent.objects.get(order_ref="COD-1")
    assert line.amount_q == 3000
    assert line.payment_ref == intent.ref
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert intent.gateway_data["collection"] == "on_delivery"
    order.refresh_from_db()
    payment = order.data["payment"]
    assert payment["intent_ref"] == intent.ref
    assert payment["cod_settled_by"] == "pos:marina"
    assert "cod_cash_shift_id" not in payment and "cod_terminal_ref" not in payment
    assert payment["tenders"][0]["intent_ref"] == intent.ref
    assert "cash_shift_id" not in payment["tenders"][0]
    assert cash.balance(counter.shift) == 13000


def test_acerto_exige_turno_aberto_e_nao_repete(counter):
    order = _cod_order("COD-2")
    with pytest.raises(ValueError, match="turno"):
        operator_orders.settle_delivery_cash(order, cash_shift=None, actor="pos:marina")

    operator_orders.settle_delivery_cash(order, cash_shift=counter.shift, actor="pos:marina")
    order.refresh_from_db()
    with pytest.raises(ValueError, match="já foi acertado"):
        operator_orders.settle_delivery_cash(order, cash_shift=counter.shift, actor="pos:marina")
    assert Entry.objects.filter(kind=Entry.Kind.COD_SETTLED).count() == 1


# ── O troco da entrega sai e volta pelo livro (WP-9) ──────────────────────


def _delivery_cash_order(ref: str, *, total_q: int = 3000, change_for_q: int | None = None) -> Order:
    payment = {
        "method": "cash",
        "collection": "on_delivery",
        "amount_q": total_q,
        "tenders": [{"method": "cash", "amount_q": total_q, "collection": "on_delivery", "status": "pending"}],
    }
    if change_for_q is not None:
        payment["change_for_q"] = change_for_q
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=Order.Status.READY,
        total_q=total_q,
        data={"fulfillment_type": "delivery", "payment": payment},
    )


def test_despacho_com_troco_exige_o_valor_e_grava_courier_out(counter):
    """O cliente paga R$ 50 num pedido de R$ 30: a loja sugere R$ 20. Avançar sem
    dizer quanto o entregador leva é recusado (409 na API); com o valor, a linha
    ``courier_out`` nasce no turno de quem despacha e a gaveta mostra o desfalque."""
    order = _delivery_cash_order("DLV-1", change_for_q=5000)
    assert operator_orders.change_out_suggested_q(order) == 2000

    with pytest.raises(operator_orders.ChangeOutRequired) as exc:
        operator_orders.advance_order(order, actor="marina")
    assert exc.value.suggested_q == 2000
    order.refresh_from_db()
    assert order.status == Order.Status.READY

    status = operator_orders.advance_order(order, actor="marina", change_out_q=2000, cash_shift=counter.shift)

    assert status == Order.Status.DISPATCHED
    line = Entry.objects.get(kind=Entry.Kind.COURIER_OUT, order_ref="DLV-1")
    assert (line.amount_q, line.shift_id, line.operator, line.approved_by) == (-2000, counter.shift.pk, counter.operator, None)
    assert line.payload == {"change_for_q": 5000, "suggested_q": 2000, "dispatched_by": "marina"}
    assert cash.balance(counter.shift) == 8000
    change = operator_orders.courier_change(order)
    assert (change.out_q, change.back_q, change.pending) == (2000, None, True)


def test_despacho_sem_troco_nao_pergunta_e_sem_turno_nao_leva(counter):
    plain = _delivery_cash_order("DLV-2")
    assert operator_orders.advance_order(plain, actor="marina") == Order.Status.DISPATCHED
    assert not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).exists()

    asks = _delivery_cash_order("DLV-3", change_for_q=5000)
    with pytest.raises(ValueError, match="turno"):
        operator_orders.advance_order(asks, actor="marina", change_out_q=2000, cash_shift=None)
    asks.refresh_from_db()
    assert asks.status == Order.Status.READY
    # "Levou sem troco" é resposta válida: zero explícito despacha sem linha.
    assert operator_orders.advance_order(asks, actor="marina", change_out_q=0) == Order.Status.DISPATCHED
    assert not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).exists()
    # Pediu troco abaixo do total (erro de digitação): nada a levar.
    below = _delivery_cash_order("DLV-4", change_for_q=1000)
    assert operator_orders.change_out_suggested_q(below) == 0


def test_o_entregador_sai_com_vinte_de_dois_pedidos_e_volta_com_cinco(counter):
    """A fixture do plano: R$ 15 + R$ 5 saem com o entregador (gaveta 100 → 80);
    o acerto de A devolve R$ 5 de troco e a venda (80 → 80+30+5 = 115); o acerto
    de B diz que voltou zero (115 → 145). Em cada passo, Σ do livro é a gaveta."""
    a = _delivery_cash_order("DLV-A", change_for_q=5000)
    b = _delivery_cash_order("DLV-B", change_for_q=4000)
    operator_orders.advance_order(a, actor="marina", change_out_q=1500, cash_shift=counter.shift)
    operator_orders.advance_order(b, actor="marina", change_out_q=500, cash_shift=counter.shift)
    assert cash.balance(counter.shift) == 8000

    with pytest.raises(ValueError, match="quanto de troco voltou"):
        operator_orders.settle_delivery_cash(a, cash_shift=counter.shift, actor="marina")
    with pytest.raises(ValueError, match="maior do que saiu"):
        operator_orders.settle_delivery_cash(a, cash_shift=counter.shift, actor="marina", change_back_q=1600)
    a.refresh_from_db()
    assert not a.data["payment"].get("cod_settled_at")

    operator_orders.settle_delivery_cash(a, cash_shift=counter.shift, actor="marina", change_back_q=500)
    assert cash.balance(counter.shift) == 11500
    out_a = Entry.objects.get(kind=Entry.Kind.COURIER_OUT, order_ref="DLV-A")
    back_a = Entry.objects.get(kind=Entry.Kind.COURIER_IN, order_ref="DLV-A")
    assert (back_a.amount_q, back_a.parent_id, back_a.payload["courier_out_id"]) == (500, out_a.pk, out_a.pk)
    assert operator_orders.courier_change(a).back_q == 500
    assert not operator_orders.courier_change(a).pending

    operator_orders.settle_delivery_cash(b, cash_shift=counter.shift, actor="marina", change_back_q=0)
    assert cash.balance(counter.shift) == 14500
    back_b = Entry.objects.get(kind=Entry.Kind.COURIER_IN, order_ref="DLV-B")
    assert back_b.amount_q == 0
    assert operator_orders.courier_change(b).back_q == 0

    # Pedido que não levou troco não aceita "voltou".
    c = _delivery_cash_order("DLV-C")
    operator_orders.advance_order(c, actor="marina")
    with pytest.raises(ValueError, match="não levou troco"):
        operator_orders.settle_delivery_cash(c, cash_shift=counter.shift, actor="marina", change_back_q=100)


def test_troco_que_volta_noutro_turno_aponta_o_pedido_mas_nao_o_parent(counter):
    order = _delivery_cash_order("DLV-X", change_for_q=5000)
    operator_orders.advance_order(order, actor="marina", change_out_q=2000, cash_shift=counter.shift)
    cash.close_shift(counter.shift, counted_q=8000, actor=counter.operator)
    ana = get_user_model().objects.create_user(username="ana", password="x")
    evening = cash.open_shift(operator=ana, float_q=5000)

    operator_orders.settle_delivery_cash(order, cash_shift=evening, actor="ana", change_back_q=700)

    back = Entry.objects.get(kind=Entry.Kind.COURIER_IN, order_ref="DLV-X")
    out = Entry.objects.get(kind=Entry.Kind.COURIER_OUT, order_ref="DLV-X")
    assert (back.shift_id, back.parent_id, back.payload["courier_out_id"]) == (evening.pk, None, out.pk)
    assert cash.balance(evening) == 5000 + 3000 + 700
    by_order = operator_orders.courier_change_by_order(["DLV-X", "nunca"])
    assert by_order == {"DLV-X": (2000, 700)}


# ── A venda em voo quando o turno fecha ───────────────────────────────────
#
# O PDV valida o turno no começo de ``close_sale``; a linha do livro nasce
# centenas de milissegundos depois, com o pedido já commitado. Se o gerente
# fecha o turno nesse intervalo, ``record`` recusa com ``SHIFT_NOT_OPEN`` (de
# propósito) e o ``atomic`` desfaz junto a liquidação no Payman. Antes disto o
# ``except Exception`` engolia tudo: a tela imprimia "Pedido criado" e o
# dinheiro sumia dos DOIS livros, sem uma issue sequer na reconciliação do dia.
#
# ⚠️ O vizinho ``test_turno_fechado_tambem_recusa`` afirma o caso fácil (turno
# já fechado ANTES do começo) e por isso ficou verde o tempo todo. O que faltava
# é o turno fechando NO MEIO, por outra conexão — que é como acontece.


def _close_shift_in_another_connection(shift_pk: int, operator_pk: int, counted_q: int) -> None:
    """Fecha o turno como o gerente fecha: outra conexão, outra transação."""
    from django.db import connections

    try:
        from shopman.cashman.models import Shift

        shift = Shift.objects.get(pk=shift_pk)
        cash.close_shift(shift, counted_q=counted_q, actor=get_user_model().objects.get(pk=operator_pk))
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_venda_que_chega_depois_do_fechamento_grita_em_vez_de_evaporar(monkeypatch):
    import threading

    counter = _Counter()
    settle_original = pos_service.payment_service.settle_terminal_tenders
    a_caminho = threading.Event()
    fechado = threading.Event()

    def _settle_com_o_gerente_fechando(order):
        # Estamos DENTRO do atomic da liquidação, exatamente onde a corrida mora.
        a_caminho.set()
        assert fechado.wait(timeout=10)
        return settle_original(order)

    monkeypatch.setattr(pos_service.payment_service, "settle_terminal_tenders", _settle_com_o_gerente_fechando)

    def _gerente():
        assert a_caminho.wait(timeout=10)
        _close_shift_in_another_connection(counter.shift.pk, counter.operator.pk, counted_q=10000)
        fechado.set()

    gerente = threading.Thread(target=_gerente)
    gerente.start()
    try:
        with pytest.raises(PosIntentError) as exc:
            counter.close(client_request_id="voo-1", tendered_q=1200)
    finally:
        gerente.join(timeout=10)

    # 1. O operador SABE. O erro nomeia o pedido e proíbe refazer a venda.
    assert exc.value.code == "cash_shift_closed_mid_sale"
    assert exc.value.status == 409
    order = Order.objects.get(channel_ref="pdv")
    assert order.ref in exc.value.message
    assert "NÃO refaça" in exc.value.recovery

    # 2. A cobrança existe: o dinheiro está na gaveta, o pedido tem de dizer isso.
    assert PaymentIntent.objects.filter(order_ref=order.ref, status=PaymentIntent.Status.CAPTURED).exists()

    # 3. O turno fechado guarda o rastro, com pedido e valor. Não move saldo (a
    #    contagem está congelada), mas nomeia o que conferir na gaveta.
    counter.shift.refresh_from_db()
    assert not counter.shift.is_open
    nota = Entry.objects.get(shift=counter.shift, kind=Entry.Kind.NOTE)
    assert nota.payload["order_ref"] == order.ref
    assert nota.payload["cash_q"] == 1200
    assert not counter.sale_lines()

    # 4. E alguém é avisado: ninguém lê o livro de um turno fechado por acaso.
    from shopman.backstage.models import OperatorAlert

    alerta = OperatorAlert.objects.get(type="cash_sale_after_shift_close")
    assert (alerta.severity, alerta.order_ref) == ("critical", order.ref)


# ── Duplo-submit simultâneo: a chave do cliente tem de valer no banco ─────
#
# ``_existing_sale_by_client_request_id`` era read-then-write sem lock, e os ops
# de troca da comanda eram montados de um estado lido antes. Duas requests com a
# MESMA chave passavam as duas: carrinho dobrado (R$ 24 numa compra de R$ 12) ou
# dois pedidos. O vizinho ``test_repetir_a_venda_nao_duplica_a_linha`` repete em
# SEQUÊNCIA, que sempre funcionou, e por isso não pegava nada.


@requires_postgres
@pytest.mark.django_db(transaction=True)
def test_dois_submits_simultaneos_com_a_mesma_chave_viram_uma_venda_so():
    import threading

    from django.db import connections

    counter = _Counter()
    rodadas = 8
    for rodada in range(rodadas):
        chave = f"simultaneo-{rodada}"
        resultados: list = []
        erros: list = []
        largada = threading.Barrier(2)

        # Os argumentos vêm por parâmetro (e não pelo closure) porque a thread
        # sobrevive à volta do laço: com closure, a rodada seguinte trocaria a
        # chave debaixo de uma thread ainda viva.
        def _submete(largada=largada, chave=chave, resultados=resultados, erros=erros):
            try:
                largada.wait(timeout=10)
                resultados.append(counter.close(client_request_id=chave, tendered_q=1200))
            except Exception as exc:  # o par perdedor pode legitimamente falhar
                erros.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=_submete) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        assert not erros, f"rodada {rodada}: {erros}"
        from django.db.models import Q

        pedidos = list(
            Order.objects.filter(Q(data__client_request_id=chave) | Q(data__pos__client_request_id=chave))
        )
        assert len(pedidos) == 1, f"rodada {rodada}: {len(pedidos)} pedidos para uma chave"
        assert pedidos[0].total_q == 1200, f"rodada {rodada}: carrinho dobrado ({pedidos[0].total_q})"
        assert {r.order_ref for r in resultados} == {pedidos[0].ref}
        assert len(Entry.objects.filter(kind=Entry.Kind.SALE, order_ref=pedidos[0].ref)) == 1
