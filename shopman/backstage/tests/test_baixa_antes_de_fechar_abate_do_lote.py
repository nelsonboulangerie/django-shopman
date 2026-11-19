"""A baixa feita antes de o lote fechar abate do lote (#2724).

Medido em 18/11/2026 pelos caminhos reais: lote de 10 baguetes para hoje, o
balcão vende e entrega 4 com o lote ainda aberto (ou a loja recebe, o cliente
paga e o operador aceita um pedido de 4 com o lote só planejado). O fechamento
com 10 creditava a vitrine com 10: o que já tinha saído voltava como
disponível. Com o lote só planejado a inflação entrava antes, no "Iniciar": o
saldo em produção nascia com 10. E fechar com quebra depois de uma venda
antecipada era recusado, com o lote sem saída pela tela.

Decisão da coordenação (19/11/2026): a baixa sai na hora, e o fechamento do
lote credita a vitrine só com o que ainda não foi vendido. O abatimento sai do
ledger (o ``Move`` da entrega no saldo de produção); o registro de produção
continua dizendo o lote inteiro.

Aqui tudo passa pela fiação real: Produção pela tela (``apply_start`` e
``apply_finish``), balcão pelo fechamento de venda do PDV, loja pelo commit,
pagamento pelo webhook da Efí, aceite pelo gesto do operador, e a configuração
de cada canal é a da casa (``config/instances/nelson.json``).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from shopman.cashman import services as cash
from shopman.craftsman.models import Recipe
from shopman.craftsman.service import CraftService as craft
from shopman.offerman.models import Product
from shopman.orderman.models import Order, Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.tests.commit_support import seal_for
from shopman.payman.models import PaymentIntent
from shopman.stockman.models import Batch, Hold, HoldStatus, Move, Position, PositionKind, Quant
from shopman.stockman.services.queries import StockQueries

from shopman.backstage.projections import bi_production
from shopman.backstage.services import closing, production
from shopman.shop.models import Channel, QualityDefect, Shop
from shopman.shop.services import availability, cancellation
from shopman.shop.services import pos as pos_service
from shopman.shop.services.operator_orders import confirm_order

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"
ACTOR = "production:forneiro"
D = Decimal
NELSON_DESCRIPTOR = Path(__file__).resolve().parents[3] / "config" / "instances" / "nelson.json"
ABERTO_TODO_DIA = {
    day: {"open": "00:00", "close": "23:59"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


def _descriptor_overrides(ref: str) -> dict:
    """A configuração do canal como a casa a declara, só os aspectos que a reserva lê."""
    descriptor = json.loads(NELSON_DESCRIPTOR.read_text())
    [entry] = [c for c in descriptor["bootstrap"]["channels"] if c["ref"] == ref]
    overrides = entry["config"]["overrides"]
    return {key: overrides[key] for key in ("confirmation", "payment", "stock", "waitlist") if key in overrides}


@pytest.fixture
def ficha(monkeypatch):
    """A ficha da baguete, o balcão e a loja da casa, sem nenhum lote ainda."""
    # A conferência de insumo é outra história: aqui a ficha não tem insumo.
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    Shop.objects.create(name="Nelson", brand_name="Nelson", opening_hours=ABERTO_TODO_DIA)
    for ref in ("pdv", "web"):
        Channel.objects.create(ref=ref, name=ref, is_active=True, config=_descriptor_overrides(ref))
    Product.objects.create(
        sku=SKU, name="Baguete", unit="un", base_price_q=1100, availability_policy="planned_ok",
        shelf_life_days=1, is_published=True, is_sellable=True,
    )
    Position.objects.create(
        ref="producao", name="Produção", kind=PositionKind.PHYSICAL, is_saleable=False, is_default=True,
    )
    Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
    return Recipe.objects.create(ref="baguete", name="Baguete", output_sku=SKU, batch_size=D("10"))


def _planejar(ficha, qty="10"):
    return craft.plan(ficha, quantity=D(qty), date=timezone.localdate(), position_ref="producao")


@pytest.fixture
def lote(ficha):
    """Um lote de 10 baguetes planejado para hoje."""
    return _planejar(ficha)


@pytest.fixture
def caixa():
    operator = get_user_model().objects.create_user(username="marina", password="x")
    return operator, cash.open_shift(operator=operator, float_q=10000)


def _iniciar(work_order, qty="10") -> None:
    work_order.refresh_from_db()
    production.apply_start(
        work_order_id=work_order.pk, quantity=qty, actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"start-{work_order.pk}",
    )


def _fechar(work_order, qty="10", *, partition=None, **kwargs) -> None:
    work_order.refresh_from_db()
    production.apply_finish(
        work_order_id=work_order.pk, quantity=qty, actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"finish-{work_order.pk}",
        partition=partition or [{"quantity": qty, "quality_grade_ref": "standard"}],
        **kwargs,
    )


def _com_desconto(qty: str) -> dict:
    defect = QualityDefect.objects.filter(is_active=True, forces_discard=False).values_list("ref", flat=True).first()
    return {"quantity": qty, "quality_grade_ref": "fair", "quality_defect_ref": defect}


def _vender_no_balcao(caixa, qty: int, *, key: str = "venda-1") -> Order:
    """A venda de balcão pela tela do PDV: revisão, fechamento e entrega no ato."""
    operator, shift = caixa
    payload = {
        "items": [{"sku": SKU, "name": "Baguete", "qty": qty, "unit_price_q": 1100}],
        "customer_name": "Cliente",
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "client_request_id": key,
        "cash_shift_id": shift.pk,
    }
    review = pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username)
    payload["expected_total_q"] = review.total_q
    result = pos_service.close_sale(
        channel_ref="pdv", payload=payload, actor=f"pos:{operator.username}", operator_username=operator.username,
    )
    return Order.objects.get(ref=result.order_ref)


def _hold(hold_id: str) -> Hold:
    return Hold.objects.select_related("quant__position").get(pk=int(hold_id.split(":")[1]))


def _reserva(order: Order) -> Hold:
    order.refresh_from_db()
    [entry] = order.data["hold_ids"]
    return _hold(entry["hold_id"])


def _onde(hold: Hold) -> str:
    """Onde está a reserva: ``planejado``, ``em_producao`` ou a posição física."""
    hold.refresh_from_db()
    quant = hold.quant
    if quant.target_date is None:
        return quant.position.ref
    return "em_producao" if quant.batch == "started" else "planejado"


def _livre(channel: str) -> Decimal:
    [answer] = availability.decide_many([(SKU, D("1"))], channel_ref=channel, target_date=timezone.localdate())
    return D(str(answer["available_qty"]))


def _saldo(onde: str) -> Decimal:
    """Soma do saldo: ``planejado``, ``em_producao`` ou ``vitrine``."""
    quants = Quant.objects.filter(sku=SKU)
    if onde == "vitrine":
        quants = quants.filter(target_date__isnull=True, position__ref="vitrine")
    else:
        quants = quants.filter(target_date__isnull=False, batch="started" if onde == "em_producao" else "")
    return sum((quant.quantity for quant in quants), D("0"))


def _producao_no_ledger() -> list[tuple[str, Decimal, str]]:
    """As pernas de produção (``MAKE``) do SKU: onde, quanto e por quê."""
    rows = []
    for move in Move.objects.filter(quant__sku=SKU, kind=Move.Kind.MAKE).select_related("quant").order_by("pk"):
        quant = move.quant
        onde = "vitrine" if quant.target_date is None else ("em_producao" if quant.batch == "started" else "planejado")
        rows.append((onde, move.delta, move.reason))
    return rows


def _vendido_no_ledger() -> Decimal:
    return sum((move.delta for move in Move.objects.filter(quant__sku=SKU, kind=Move.Kind.SELL)), D("0"))


# ── Balcão: vende e entrega antes de o lote fechar ───────────────────────────


def test_balcao_vende_com_o_lote_aberto_e_o_fechamento_credita_o_que_sobra(
    lote, caixa, django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        order = _vender_no_balcao(caixa, 4)
    assert _reserva(order).status == HoldStatus.FULFILLED, "o balcão entrega no ato"
    assert _saldo("em_producao") == D("6")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)

    assert _saldo("vitrine") == D("6"), "10 produzidas, 4 já entregues no balcão"
    assert _saldo("em_producao") == D("0")
    assert (_livre("pdv"), _livre("web")) == (D("6"), D("4")), "a loja guarda a margem de 2"
    assert _onde(_reserva(order)) == "vitrine", "a entrega passa a pesar no lote que a pagou"
    assert _vendido_no_ledger() == D("-4"), "a venda continua contada uma vez só"


def test_balcao_vende_com_o_lote_so_planejado_e_o_iniciar_nao_nasce_cheio(
    lote, caixa, django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        order = _vender_no_balcao(caixa, 4)
    assert _saldo("planejado") == D("6")

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)

    assert (_saldo("planejado"), _saldo("em_producao")) == (D("0"), D("6"))
    assert _livre("pdv") == D("6"), "antes o balcão lia 10 com o lote no forno"
    assert _onde(_reserva(order)) == "em_producao"

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)

    assert _saldo("vitrine") == D("6")
    assert (_livre("pdv"), _livre("web")) == (D("6"), D("4"))
    assert _vendido_no_ledger() == D("-4")


def test_lote_fechado_direto_do_planejado_tambem_abate(lote, caixa, django_capture_on_commit_callbacks):
    """Sem "Iniciar": o fechamento que abre e fecha o lote de uma vez (a avulsa do quiosque)."""
    with django_capture_on_commit_callbacks(execute=True):
        _vender_no_balcao(caixa, 4)

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, allow_implicit_start=True)

    assert (_saldo("planejado"), _saldo("vitrine")) == (D("0"), D("6"))
    assert _livre("pdv") == D("6")


def test_baixa_de_tudo_antes_de_fechar_credita_zero(lote, caixa, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        _vender_no_balcao(caixa, 6, key="venda-1")
        _vender_no_balcao(caixa, 4, key="venda-2")
    assert _saldo("em_producao") == D("0")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)

    lote.refresh_from_db()
    assert lote.finished == D("10")
    assert _saldo("vitrine") == D("0")
    assert (_livre("pdv"), _livre("web")) == (D("0"), D("0"))
    assert _vendido_no_ledger() == D("-10")


# ── Loja: pago e aceito antes de o lote fechar ───────────────────────────────


@override_settings(SHOPMAN_EFI_WEBHOOK={"webhook_token": "test-efi-token"})
def test_pedido_da_loja_pago_e_aceito_antes_de_o_lote_fechar(lote, django_capture_on_commit_callbacks):
    """Commit, webhook de pagamento e aceite de ponta a ponta, com o lote só planejado."""
    Session.objects.create(
        session_key="S-WEB", channel_ref="web", state="open", rev=1,
        data={"payment": {"method": "pix"}, "fulfillment_type": "pickup", "origin_channel": "web"},
        items=[{"line_id": "L1", "sku": SKU, "name": "Baguete", "qty": 4, "unit_price_q": 1100}],
    )
    with django_capture_on_commit_callbacks(execute=True):
        result = CommitService.commit(
            session_key="S-WEB", channel_ref="web", idempotency_key="K-WEB",
            seal=seal_for("S-WEB", "web"), channel_config={},
        )
    order = Order.objects.get(ref=result["order_ref"] if isinstance(result, dict) else result.order_ref)
    hold = _reserva(order)
    assert (_onde(hold), hold.status) == ("planejado", HoldStatus.PENDING)

    intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
    with django_capture_on_commit_callbacks(execute=True):
        response = APIClient().post(
            "/api/webhooks/efi/pix/",
            {"pix": [{"txid": intent.gateway_id, "endToEndId": "E2724", "valor": f"{order.total_q / 100:.2f}"}]},
            format="json", HTTP_X_EFI_WEBHOOK_TOKEN="test-efi-token",
        )
    assert response.status_code == 200
    hold.refresh_from_db()
    assert hold.status == HoldStatus.PENDING, "o pagamento sozinho não baixa"

    order.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        confirm_order(order, actor="operator")
    hold.refresh_from_db()
    assert hold.status == HoldStatus.FULFILLED, "o aceite do pedido pago baixa na hora"
    assert _saldo("planejado") == D("6")

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    assert (_saldo("planejado"), _saldo("em_producao")) == (D("0"), D("6"))

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)

    assert _saldo("vitrine") == D("6")
    assert (_livre("pdv"), _livre("web")) == (D("6"), D("4"))
    assert _onde(hold) == "vitrine"


# ── Quebra, e entrega maior que a produção ───────────────────────────────────


def test_fechar_com_quebra_tendo_havido_baixa(lote, caixa, django_capture_on_commit_callbacks):
    """Antes: ``INSUFFICIENT_AVAILABLE``, e o lote ficava aberto sem saída pela tela."""
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        _vender_no_balcao(caixa, 4)

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, "6", yield_deviation_confirmed=True, yield_deviation_reason="Contagem conferida.")

    lote.refresh_from_db()
    assert (lote.status, lote.finished) == ("finished", D("6"))
    assert _saldo("vitrine") == D("2"), "6 saíram do forno, 4 já tinham sido entregues"
    assert _saldo("em_producao") == D("0")
    [perda] = Move.objects.filter(quant__sku=SKU, kind=Move.Kind.WASTE)
    assert perda.delta == D("-4"), "a quebra é a do lote: previsto 10, realizado 6"
    assert _livre("pdv") == D("2")


def test_fechar_abaixo_do_ja_entregue_com_o_pedido_ativo_e_recusado(lote, caixa, django_capture_on_commit_callbacks):
    """Entregou 4 e diz que produziu 3: a guarda de pedidos do fechamento recusa, como já recusava."""
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        _vender_no_balcao(caixa, 4)

    with pytest.raises(production.ProductionOrderShortError):
        _fechar(lote, "3", yield_deviation_confirmed=True, yield_deviation_reason="Contagem conferida.")

    lote.refresh_from_db()
    assert lote.status == "started"
    assert (_saldo("em_producao"), _saldo("vitrine")) == (D("6"), D("0"))


def test_fechar_abaixo_do_ja_entregue_falha_fechado_no_ledger(lote, caixa, django_capture_on_commit_callbacks):
    """O pedido já saiu da conta dos ativos (concluído): quem recusa é o ledger.

    4 entregues, 3 produzidas. Os 3 abatem do lote, e a unidade sem lastro não
    vira saldo negativo nem perda inventada: a ponte procura 7 de quebra, acha
    6 e desfaz o fechamento inteiro. O lote segue aberto e nada mudou.
    """
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        order = _vender_no_balcao(caixa, 4)
    Order.objects.filter(pk=order.pk).update(status="completed")
    antes = list(Move.objects.filter(quant__sku=SKU).order_by("pk").values_list("pk", flat=True))

    with pytest.raises(production.ProductionError) as error:
        _fechar(lote, "3", yield_deviation_confirmed=True, yield_deviation_reason="Contagem conferida.")

    assert "INSUFFICIENT_AVAILABLE" in str(error.value)
    lote.refresh_from_db()
    assert lote.status == "started"
    assert (_saldo("em_producao"), _saldo("vitrine")) == (D("6"), D("0"))
    assert list(Move.objects.filter(quant__sku=SKU).order_by("pk").values_list("pk", flat=True)) == antes
    assert _onde(_reserva(order)) == "em_producao"


# ── Mais de um lote, mais de um grau ─────────────────────────────────────────


def test_dois_lotes_do_mesmo_sku_e_dia(ficha, caixa, django_capture_on_commit_callbacks):
    """Dois lotes de 10 no mesmo saldo em produção: a entrega pesa uma vez, no primeiro que fecha."""
    primeiro, segundo = _planejar(ficha), _planejar(ficha)
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(primeiro)
        _iniciar(segundo)
    with django_capture_on_commit_callbacks(execute=True):
        _vender_no_balcao(caixa, 4)
    assert _saldo("em_producao") == D("16")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(primeiro)
    assert (_saldo("em_producao"), _saldo("vitrine")) == (D("10"), D("6"))
    assert _livre("pdv") == D("16")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(segundo)

    assert (_saldo("em_producao"), _saldo("vitrine")) == (D("0"), D("16"))
    assert _livre("pdv") == D("16")
    recebidos = [delta for onde, delta, _ in _producao_no_ledger() if onde == "vitrine"]
    assert recebidos == [D("10"), D("10")], "cada lote continua registrado inteiro"


def test_lote_que_sai_com_desconto(lote, caixa, django_capture_on_commit_callbacks):
    """A entrega feita antes da inspeção abate do lote, qualquer que seja o grau dele."""
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        order = _vender_no_balcao(caixa, 4)

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, partition=[_com_desconto("10")])

    vitrine = Quant.objects.get(sku=SKU, target_date__isnull=True)
    assert Batch.objects.get(ref=vitrine.batch).quality_grade_ref == "fair"
    assert vitrine.quantity == D("6")
    assert _onde(_reserva(order)) == "vitrine"
    assert (_livre("pdv"), _livre("web")) == (D("6"), D("0")), "a loja não vende o lote com desconto"


def test_fechamento_partido_em_dois_graus(lote, caixa, django_capture_on_commit_callbacks):
    """7 integrais e 3 com desconto, com 8 já entregues: a entrega ocupa o primeiro lote
    da partição e o resto dela, o segundo. Sobram 2, e a soma fecha com o forno."""
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        _vender_no_balcao(caixa, 8)

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, partition=[{"quantity": "7", "quality_grade_ref": "standard"}, _com_desconto("3")])

    por_grau = {
        Batch.objects.get(ref=quant.batch).quality_grade_ref: quant.quantity
        for quant in Quant.objects.filter(sku=SKU, target_date__isnull=True)
    }
    assert por_grau == {"standard": D("0"), "fair": D("2")}
    assert _saldo("em_producao") == D("0")
    assert _vendido_no_ledger() == D("-8")


# ── O pedido baixado é cancelado ─────────────────────────────────────────────


def test_pedido_cancelado_antes_de_o_lote_fechar_devolve_ao_saldo_de_producao(
    lote, caixa, django_capture_on_commit_callbacks,
):
    """A venda desfeita volta para o lote que ainda está no forno, e ele fecha inteiro.

    Antes a devolução entrava como pão pronto na posição de produção, com o
    lote ainda aberto: o balcão passava a ler 14 depois de fechado.
    """
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        order = _vender_no_balcao(caixa, 4)
    order.refresh_from_db()

    with django_capture_on_commit_callbacks(execute=True):
        assert cancellation.cancel(order, reason="Cliente desistiu", actor="pos:marina") is True

    assert _saldo("em_producao") == D("10")
    assert not Quant.objects.filter(sku=SKU, target_date__isnull=True).exists(), "nenhum pão pronto antes da hora"
    assert _livre("pdv") == D("10")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)

    assert _saldo("vitrine") == D("10")
    assert (_livre("pdv"), _livre("web")) == (D("10"), D("8"))
    assert Quant.objects.filter(sku=SKU, _quantity__gt=0).count() == 1, "tudo no lote, nada sobrando em outro saldo"


def test_pedido_cancelado_depois_de_o_lote_fechar_devolve_a_vitrine(lote, caixa, django_capture_on_commit_callbacks):
    """Fechado o lote, a entrega pesa nele: a devolução entra na posição dele, a vitrine."""
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        order = _vender_no_balcao(caixa, 4)
    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)
    order.refresh_from_db()

    with django_capture_on_commit_callbacks(execute=True):
        assert cancellation.cancel(order, reason="Cliente desistiu", actor="pos:marina") is True

    assert _saldo("vitrine") == D("10")
    assert _livre("pdv") == D("10")
    assert not Quant.objects.filter(sku=SKU, _quantity__gt=0).exclude(position__ref="vitrine").exists()


# ── As reservas ainda ativas seguem para a vitrine ───────────────────────────


def test_reserva_ativa_segue_para_a_vitrine_no_que_sobra_do_lote(lote, caixa, django_capture_on_commit_callbacks):
    """O balcão entrega 4 e a loja tem 3 reservadas no mesmo saldo: fechado o lote,
    a vitrine tem 6 e 3 delas são da reserva, que chega materializada."""
    reserva = availability.reserve(SKU, D("3"), session_key="S-WEB-1", channel_ref="web")
    assert reserva["ok"], reserva
    [hold_id] = reserva["hold_ids"]
    with django_capture_on_commit_callbacks(execute=True):
        _vender_no_balcao(caixa, 4)

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, allow_implicit_start=True)

    hold = _hold(hold_id)
    assert _onde(hold) == "vitrine"
    assert hold.status in (HoldStatus.PENDING, HoldStatus.CONFIRMED)
    vitrine = Quant.objects.get(sku=SKU, target_date__isnull=True)
    assert (vitrine.quantity, vitrine.held) == (D("6"), D("3"))
    assert _livre("pdv") == D("3")


# ── O registro de produção continua dizendo o lote inteiro ───────────────────


def test_quem_le_a_producao_continua_vendo_o_lote_inteiro(lote, caixa, django_capture_on_commit_callbacks):
    """Ledger ``MAKE``, B.I. da fornada, resumo do fechamento do dia e histórico de prateleira."""
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        _vender_no_balcao(caixa, 4)
    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)
    lote.refresh_from_db()
    hoje = timezone.localdate()

    # As pernas de produção são as mesmas de um lote sem venda antecipada.
    assert _producao_no_ledger() == [
        ("planejado", D("10"), f"Produção planejada: {lote.ref}"),
        ("em_producao", D("10"), f"Produção do lote: {lote.ref}"),
        ("em_producao", D("-10"), f"Transferência: Finalização do lote: {lote.ref}"),
        ("vitrine", D("10"), f"Recebido de produção: Finalização do lote: {lote.ref}"),
    ]
    assert lote.finished == D("10")

    # B.I.: a fornada é dona do lote pelo recebimento de produção, e o que resta é o saldo real.
    vitrine = Quant.objects.get(sku=SKU, target_date__isnull=True)
    owners = bi_production._stock_batch_owners([lote])
    assert owners == {vitrine.batch: lote.ref}
    assert bi_production._lot_state(owners)[lote.ref][0] == D("6")

    # Fechamento do dia: o produzido vem da ordem de produção.
    [row] = closing.production_summary(hoje).values()
    assert (row["output_sku"], row["finished"], row["loss"]) == (SKU, D("10"), D("0"))

    # Prateleira: chegaram 10, 4 vendidas, nenhuma descartada.
    day = StockQueries.shelf_history([SKU], since=hoje, until=hoje)[SKU][hoje]
    assert (day.received, day.sold, day.discarded) == (D("10"), D("4"), D("0"))
    assert day.closing == D("6")


def test_lote_sem_baixa_antecipada_fecha_como_sempre(lote, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)

    assert _saldo("vitrine") == D("10")
    assert [(onde, delta) for onde, delta, _ in _producao_no_ledger()] == [
        ("planejado", D("10")), ("em_producao", D("10")), ("em_producao", D("-10")), ("vitrine", D("10")),
    ]
    assert not Move.objects.filter(quant__sku=SKU, kind=Move.Kind.SELL).exists()
