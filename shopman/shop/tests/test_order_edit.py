"""Editar a encomenda no próprio pedido (``shop.services.order_edit``, WP-E6).

O que se prova aqui:

- itens: quantidade a mais vira saldo a receber; trocar item grava o ajuste
  (lista FINAL, ``source: pos:edit``), reserva na data combinada e a trilha;
  quantidade a mais com preço de catálogo diferente vira linha própria;
- a diferença a menos volta pelo MESMO meio: cartão online (estorno parcial no
  Stripe), Pix (devolução parcial na Efí), dinheiro (pendência da gaveta, que
  devolve só a diferença) e maquininha (pendência guiada, registrada);
- meio que não devolve parte recusa (pagamento em dois meios);
- sem saldo na data: recusa e NADA muda;
- NFC-e autorizada: a porta fecha e a tela oferece cancelar e refazer; iFood
  edita pelo iFood;
- recebimento: retirada → entrega com a taxa como linha do ajuste, o saldo na
  porta e o CPF da entrega com nota (regra de 24/09); entrega → retirada tira a taxa;
- data: vai pelo reagendar, na mesma transação, com UM aviso só;
- o aviso ao cliente diz o que mudou, o total e o destino da diferença, e sai
  um por edição.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.payman import PaymentService
from shopman.stockman.models import Hold, Position, PositionKind
from shopman.stockman.services.planning import StockPlanning

from shopman.shop.models import Channel, Shop
from shopman.shop.services import order_composition, order_edit, payment, stock
from shopman.shop.services.order_edit import EditRefused

pytestmark = pytest.mark.django_db

BAGUETE = "BAGUETE"
CROISSANT = "CROISSANT"
ABERTO_TODO_DIA = {
    day: {"open": "07:00", "close": "19:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}
MANAGER = SimpleNamespace(get_username=lambda: "gerente")


@pytest.fixture(autouse=True)
def _noop_sku_validator(settings):
    from shopman.stockman.adapters.sku_validation import reset_sku_validator

    settings.STOCKMAN = {
        **getattr(settings, "STOCKMAN", {}),
        "SKU_VALIDATOR": "shopman.stockman.adapters.noop.NoopSkuValidator",
    }
    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.fixture(autouse=True)
def casa(db):
    from shopman.offerman.models import Product

    Shop.objects.create(name="Nelson", brand_name="Nelson", opening_hours=ABERTO_TODO_DIA)
    Channel.objects.create(ref="web", name="Loja", config={"payment": {"timing": "external", "method": "cash"}})
    Product.objects.create(sku=BAGUETE, name="Baguete", base_price_q=1200, is_published=True, is_sellable=True)
    Product.objects.create(sku=CROISSANT, name="Croissant", base_price_q=900, is_published=True, is_sellable=True)


@pytest.fixture
def vitrine(db):
    return Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)


def _day(offset: int):
    return timezone.localdate() + timedelta(days=offset)


def _plan(sku: str, offset: int, qty: int, position) -> None:
    product = SimpleNamespace(sku=sku, name=sku.title(), shelf_life_days=None)
    StockPlanning.plan(Decimal(qty), product, _day(offset), position=position)


def _encomenda(ref: str, offset: int = 3, *, qty: int = 2, payment_data: dict | None = None, **extra) -> Order:
    day = _day(offset)
    total = 1200 * qty
    order = Order.objects.create(
        ref=ref,
        channel_ref=extra.pop("channel", "web"),
        session_key=f"SESS-{ref}",
        status=extra.pop("status", Order.Status.ACCEPTED),
        snapshot={"items": [{"line_id": "L1", "sku": BAGUETE, "name": "Baguete", "qty": qty, "unit_price_q": 1200}]},
        data={
            "customer": {"name": "Ana", "phone": "+5543999990000"},
            "fulfillment_type": "pickup",
            "payment": payment_data or {"method": "cash"},
            "delivery_date": day.isoformat(),
            "delivery_time_slot": "slot-09",
            "is_preorder": True,
            **extra,
        },
        total_q=total,
    )
    OrderItem.objects.create(
        order=order, line_id="L1", sku=BAGUETE, name="Baguete", qty=qty, unit_price_q=1200, line_total_q=total,
    )
    stock.hold(order)
    order.refresh_from_db()
    return order


def _holds_by_sku(order) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for entry in order.data.get("hold_ids") or []:
        if not entry.get("hold_id"):
            continue
        hold = Hold.objects.get(pk=int(entry["hold_id"].split(":")[1]))
        if hold.status in ("pending", "confirmed", "fulfilled"):
            out[entry["sku"]] = out.get(entry["sku"], Decimal("0")) + hold.quantity
    return out


def _updated_notices(order):
    return Directive.objects.filter(
        topic="notification.send", payload__order_ref=order.ref, payload__template="order_updated",
    ).order_by("pk")


def _captured(order, amount_q: int, method: str, **kwargs):
    """Um pagamento capturado (dinheiro/maquininha sem gateway; cartão/Pix com gateway)."""
    gateway = kwargs.pop("gateway", "")
    if not gateway:
        intent = PaymentService.settle(order.ref, amount_q, method, idempotency_key=f"test:{order.ref}:{method}")
    else:
        intent = PaymentService.create_intent(
            order.ref, amount_q, method, gateway=gateway, gateway_id=kwargs.pop("gateway_id", f"gw-{order.ref}"),
            gateway_data=kwargs.pop("gateway_data", {}),
        )
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
    data = dict(order.data)
    data["payment"] = {**(data.get("payment") or {}), "method": method, "intent_ref": intent.ref}
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    return intent


# ── Itens ────────────────────────────────────────────────────────────────────


def test_quantidade_a_mais_vira_saldo_a_receber_e_ajuste_do_pedido(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-1")
    _captured(order, 2400, "cash")

    result = order_edit.edit(order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 3}], actor="pos:marina")

    order.refresh_from_db()
    assert result.revision == 1
    record = order_composition.adjustment(order)
    assert record["source"] == "pos:edit" and record["event_id"] == "pos-edit:ED-1:1"
    assert record["total_q"] == 3600 and record["sealed_total_q"] == 2400
    (line,) = order_composition.effective_items(order)
    assert line.line_id == "L1" and line.qty == 3 and line.unit_price_q == 1200
    # O selado continua intacto — é o "antes".
    assert order.total_q == 2400 and order.items.get().qty == 2
    # A diferença é saldo a receber na retirada.
    assert result.plan.settlement.kind == order_edit.SETTLE_COLLECT
    assert payment.balance_due_q(order) == 1200
    # Reserva na data combinada acompanhou.
    assert _holds_by_sku(order) == {BAGUETE: Decimal("3")}
    # Trilha.
    event = order.events.get(type="order_edited")
    assert event.actor == "pos:marina"
    assert event.payload["previous_total_q"] == 2400 and event.payload["total_q"] == 3600
    assert event.payload["diff"]["changed"][0]["previous_qty"] == 2


def test_trocar_item_reserva_o_novo_solta_o_velho_e_avisa_o_cliente(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    _plan(CROISSANT, 3, 10, vitrine)
    order = _encomenda("ED-2", qty=1)

    result = order_edit.edit(order, lines=[{"sku": CROISSANT, "qty": 2}], actor="pos:marina")

    order.refresh_from_db()
    (line,) = order_composition.effective_items(order)
    assert line.sku == CROISSANT and line.unit_price_q == 900 and line.line_id == "E1-1"
    assert line.meta == {"added_by": "pos:edit"}
    assert order_composition.effective_total_q(order) == 1800
    assert _holds_by_sku(order) == {CROISSANT: Decimal("2")}
    assert result.plan.diff["added"][0]["sku"] == CROISSANT
    assert result.plan.diff["removed"][0]["sku"] == BAGUETE

    (aviso,) = _updated_notices(order)
    assert aviso.payload["status_note"] == (
        "Saiu 1 Baguete e entraram 2 Croissant. O novo total é R$ 18,00, a pagar na retirada."
    )
    assert aviso.dedupe_key.startswith("notification.send:ED-2:order_updated:")


def test_quantidade_a_mais_com_preco_novo_vira_linha_propria(vitrine):
    from shopman.offerman.models import Product

    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-3")
    Product.objects.filter(sku=BAGUETE).update(base_price_q=1500)

    result = order_edit.plan(order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 3}])

    by_line = {item["line_id"]: item for item in result.items}
    assert by_line["L1"]["qty"] == 2 and by_line["L1"]["unit_price_q"] == 1200
    assert by_line["E1-1"]["qty"] == 1 and by_line["E1-1"]["unit_price_q"] == 1500
    assert result.total_q == 3900


def test_sem_saldo_na_data_recusa_e_nada_muda(vitrine):
    _plan(BAGUETE, 3, 2, vitrine)
    order = _encomenda("ED-4")
    antes = _holds_by_sku(order)

    with pytest.raises(EditRefused) as refused:
        order_edit.edit(order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 5}], actor="pos:marina")

    assert refused.value.code == "insufficient_stock"
    assert "Baguete não tem saldo" in refused.value.message
    order.refresh_from_db()
    assert not order_composition.is_adjusted(order)
    assert _holds_by_sku(order) == antes
    assert not order.events.filter(type="order_edited").exists()
    assert not _updated_notices(order).exists()


def test_mesma_lista_nao_mexe_em_nada(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-5")

    result = order_edit.edit(order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 2}], actor="pos:marina")

    assert result.plan.changed is False and result.revision is None
    assert not order.events.filter(type="order_edited").exists()


# ── Diferença a menos: o MESMO meio ──────────────────────────────────────────


@override_settings(SHOPMAN_PAYMENT_ADAPTERS={"card": "shopman.shop.adapters.payment_stripe"})
def test_reduzir_com_cartao_online_estorna_parte_no_stripe(vitrine, django_capture_on_commit_callbacks):
    from shopman.shop.adapters import payment_stripe

    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-6", qty=3, payment_data={"method": "card"})
    intent = _captured(order, 3600, "card", gateway="stripe", gateway_id="pi_ed6")

    # Redução com dinheiro recebido pede o gerente.
    with pytest.raises(EditRefused) as refused:
        order_edit.edit(order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 2}], actor="pos:marina")
    assert refused.value.code == "manager_approval_required"

    refunds = []

    def create(**params):
        refunds.append(params)
        return SimpleNamespace(id="re_ed6", amount=params["amount"])

    stripe = SimpleNamespace(Refund=SimpleNamespace(create=create))
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        with django_capture_on_commit_callbacks(execute=True):
            result = order_edit.edit(
                order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 2}], actor="pos:marina", approved_by=MANAGER,
            )

    assert result.plan.settlement == order_edit.Settlement(order_edit.SETTLE_REFUND_GATEWAY, 1200, "card")
    assert refunds and refunds[0]["amount"] == 1200 and refunds[0]["payment_intent"] == "pi_ed6"
    assert refunds[0]["idempotency_key"] == "order-edit:ED-6:1"
    assert PaymentService.refunded_total(intent.ref) == 1200
    order.refresh_from_db()
    assert payment.balance_due_q(order) == 0
    assert payment.overpaid_q(order) == 0
    assert order.events.get(type="order_edited").payload["approved_by"] == "gerente"
    (aviso,) = _updated_notices(order)
    assert aviso.payload["status_note"] == (
        "Baguete passou de 3 para 2. O novo total é R$ 24,00. Devolvemos R$ 12,00 no seu cartão."
    )


@override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={"pix": "shopman.shop.adapters.payment_efi"},
    SHOPMAN_EFI={"sandbox": True},
)
def test_reduzir_com_pix_devolve_parte_na_efi(vitrine, django_capture_on_commit_callbacks):
    from shopman.shop.adapters import payment_efi

    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-7", qty=3, payment_data={"method": "pix"})
    intent = _captured(
        order, 3600, "pix", gateway="efi", gateway_id="txid-ed7",
        gateway_data={"provider_environment": "sandbox", "confirmation_mode": "provider_simulated"},
    )
    calls = []

    def remote(method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return {"status": "CONCLUIDA", "pix": [{"endToEndId": "E2E-ED7"}], "valor": {"original": "36.00"}}
        return {"id": "dev-ed7"}

    with patch.object(payment_efi, "_request", side_effect=remote):
        with django_capture_on_commit_callbacks(execute=True):
            result = order_edit.edit(
                order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 2}], actor="pos:marina", approved_by=MANAGER,
            )

    assert result.plan.settlement.kind == order_edit.SETTLE_REFUND_GATEWAY
    puts = [(path, body) for method, path, body in calls if method == "PUT"]
    assert len(puts) == 1 and puts[0][0].startswith("/v2/pix/E2E-ED7/devolucao/")
    assert puts[0][1] == {"valor": "12.00"}
    assert PaymentService.refunded_total(intent.ref) == 1200
    assert "Devolvemos R$ 12,00 pelo Pix." in result.plan.customer_note


def test_reduzir_pago_em_dinheiro_vira_devolucao_da_gaveta_so_da_diferenca(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-8", qty=3)
    intent = _captured(order, 3600, "cash")

    result = order_edit.edit(
        order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 1}], actor="pos:marina", approved_by=MANAGER,
    )

    assert result.plan.settlement == order_edit.Settlement(order_edit.SETTLE_REFUND_CASH, 2400, "cash")
    assert "Devolvemos R$ 24,00 em dinheiro na retirada." in result.plan.customer_note
    (pendente,) = payment.pending_cash_refunds()
    assert pendente.order_ref == "ED-8" and pendente.amount_q == 2400 and pendente.reason == "reduced"

    order.refresh_from_db()
    shift = SimpleNamespace(is_open=True, pk=None)
    with patch("shopman.cashman.services.record") as ledger:
        devolvido = payment.refund_cash(order, shift=shift, actor="pos:marina")
    # Devolve SÓ a diferença: o que a encomenda ainda vale fica na casa.
    assert devolvido == 2400
    assert PaymentService.refunded_total(intent.ref) == 2400
    assert ledger.call_args.kwargs["amount_q"] == -2400
    assert payment.pending_cash_refunds() == []


def test_reduzir_pago_na_maquininha_vira_pendencia_guiada_e_registro(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-9", qty=3, payment_data={"method": "credit", "collection": "terminal"})
    intent = _captured(order, 3600, "credit")

    result = order_edit.edit(
        order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 2}], actor="pos:marina", approved_by=MANAGER,
    )

    assert result.plan.settlement == order_edit.Settlement(order_edit.SETTLE_REFUND_CARD_MACHINE, 1200, "credit")
    # O sistema não estornou nada sozinho: a maquininha é física.
    assert PaymentService.refunded_total(intent.ref) == 0
    (pendente,) = payment.pending_card_machine_refunds()
    assert pendente.order_ref == "ED-9" and pendente.amount_q == 1200 and pendente.method == "credit"
    assert payment.pending_cash_refunds() == []

    order.refresh_from_db()
    assert payment.record_card_machine_refund(order, actor="pos:marina", approved_by=MANAGER) == 1200
    assert PaymentService.refunded_total(intent.ref) == 1200
    assert payment.pending_card_machine_refunds() == []
    # De novo não registra outra vez.
    assert payment.record_card_machine_refund(order, actor="pos:marina") == 0
    assert order.events.filter(type="card_machine_refund_recorded").count() == 1


def test_reducao_paga_em_dois_meios_recusa(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-10", qty=3, payment_data={"method": "mixed"})
    cash = PaymentService.settle(order.ref, 1800, "cash", idempotency_key="t:ed10:cash")
    credit = PaymentService.settle(order.ref, 1800, "credit", idempotency_key="t:ed10:credit")
    order.data["payment"]["tenders"] = [
        {"method": "cash", "amount_q": 1800, "status": "received", "collection": "terminal", "intent_ref": cash.ref},
        {"method": "credit", "amount_q": 1800, "status": "received", "collection": "terminal", "intent_ref": credit.ref},
    ]
    order.save(update_fields=["data", "updated_at"])

    with pytest.raises(EditRefused) as refused:
        order_edit.plan(order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 2}])

    assert refused.value.code == "mixed_payment_refund"


def test_cobranca_digital_aberta_trava_mudanca_de_valor(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-11", payment_data={"method": "pix"})
    PaymentService.create_intent(order.ref, 2400, "pix", gateway="efi", gateway_id="txid-open")

    with pytest.raises(EditRefused) as refused:
        order_edit.plan(order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 3}])
    assert refused.value.code == "open_digital_charge"
    # Mudar só a observação não mexe no valor e passa.
    assert order_edit.plan(order, notes="sem gergelim").notes_changed


# ── Portas fechadas ──────────────────────────────────────────────────────────


def test_nota_autorizada_fecha_a_porta_e_oferece_cancelar_e_refazer(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-12", nfce_access_key="4126" + "0" * 40)

    code, reason = order_edit.state_refusal(order)
    assert code == "fiscal_authorized" and "cancele e refaça" in reason
    with pytest.raises(EditRefused) as refused:
        order_edit.plan(order, notes="x")
    assert refused.value.code == "fiscal_authorized"


@pytest.mark.parametrize(
    ("status", "code"),
    [("ready", "order_not_editable"), ("completed", "order_not_editable"), ("cancelled", "order_not_editable")],
)
def test_pedido_pronto_ou_encerrado_nao_se_edita(vitrine, status, code):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda(f"ED-ST-{status}")
    Order.objects.filter(pk=order.pk).update(status=status)
    order.refresh_from_db()

    assert order_edit.state_refusal(order)[0] == code


def test_ifood_edita_pelo_ifood(vitrine):
    order = Order.objects.create(ref="IF-ED", channel_ref="ifood", status="accepted", total_q=1000, data={})

    assert order_edit.state_refusal(order)[0] == "marketplace_order"


# ── Recebimento ──────────────────────────────────────────────────────────────

ENDERECO = {
    "formatted_address": "Rua Sergipe, 100 - Centro, Londrina - PR",
    "route": "Rua Sergipe", "street_number": "100", "neighborhood": "Centro",
    "city": "Londrina", "state_code": "PR", "postal_code": "86010-000",
}


@override_settings(SHOPMAN_PAYMENT_ADAPTERS={"pix": "shopman.shop.adapters.payment_mock"})
def test_retirada_paga_no_pix_vira_entrega_com_taxa_e_saldo_na_porta(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-13", payment_data={"method": "pix"})
    intent = _captured(order, 2400, "pix", gateway="mock", gateway_id="mock-ed13")
    fulfillment = {"type": "delivery", "delivery_address_structured": ENDERECO, "delivery_fee_override_q": 800}

    # Saldo na porta: tem de dizer como o entregador recebe.
    with pytest.raises(EditRefused) as refused:
        order_edit.plan(order, fulfillment=fulfillment)
    assert refused.value.code == "delivery_payment_method_required"
    assert refused.value.field == "fulfillment.delivery_payment_method"

    result = order_edit.edit(
        order, fulfillment={**fulfillment, "delivery_payment_method": "cash"}, actor="pos:marina",
    )

    order.refresh_from_db()
    assert order.data["fulfillment_type"] == "delivery"
    assert order.data["delivery_address_structured"] == ENDERECO
    assert order.data["delivery_fee_q"] == 800
    fee = [item for item in order_composition.effective_items(order) if item.sku == "__DELIVERY_FEE__"]
    assert len(fee) == 1 and fee[0].line_total_q == 800
    assert order_composition.effective_total_q(order) == 3200
    # O pagamento continua somando o total: o Pix recebido + o saldo na porta.
    pay = order.data["payment"]
    assert pay["collection"] == "on_delivery" and pay["method"] == "mixed"
    assert pay["tenders"] == [
        {"method": "pix", "amount_q": 2400, "collection": "online", "status": "received", "intent_ref": intent.ref},
        {"method": "cash", "amount_q": 800, "collection": "on_delivery", "status": "pending"},
    ]
    assert payment.balance_due_q(order) == 800
    # A taxa não é produção: a reserva segue só com o pão.
    assert _holds_by_sku(order) == {BAGUETE: Decimal("2")}
    assert result.plan.customer_note == (
        "Agora é entrega em Rua Sergipe, 100 - Centro, Londrina - PR, com taxa de R$ 8,00. "
        "O novo total é R$ 32,00. A diferença de R$ 8,00 fica para a entrega."
    )


def test_entrega_vira_retirada_e_a_taxa_sai(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-14")
    order_edit.edit(
        order, fulfillment={"type": "delivery", "delivery_address_structured": ENDERECO, "delivery_fee_override_q": 500},
        actor="pos:marina",
    )
    order.refresh_from_db()
    assert order_composition.effective_total_q(order) == 2900

    result = order_edit.edit(order, fulfillment={"type": "pickup"}, actor="pos:marina")

    order.refresh_from_db()
    assert order.data["fulfillment_type"] == "pickup"
    assert "delivery_address_structured" not in order.data and "delivery_fee_q" not in order.data
    assert [item.sku for item in order_composition.effective_items(order)] == [BAGUETE]
    assert order_composition.effective_total_q(order) == 2400
    assert result.revision == 2
    assert result.plan.customer_note.startswith("Agora é retirada na loja.")


def test_entrega_com_nota_exige_cpf_como_na_venda(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-15")
    fulfillment = {"type": "delivery", "delivery_address_structured": ENDERECO, "delivery_fee_override_q": 0}

    with patch("shopman.shop.services.fiscal.emission_expected", return_value=True):
        with pytest.raises(EditRefused) as refused:
            order_edit.plan(order, fulfillment=fulfillment)
        assert refused.value.code == "delivery_tax_id_required"
        assert refused.value.field == "fulfillment.fiscal_tax_id"

        ok = order_edit.plan(order, fulfillment={**fulfillment, "fiscal_tax_id": "52998224725"})
    assert ok.fulfillment_changed and ok.data_updates["fiscal"] == {"tax_id": "52998224725"}


def test_endereco_fora_da_area_recusa(vitrine):
    from shopman.shop.services.pos import DeliveryFeeResolution

    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-16")
    blocked = DeliveryFeeResolution(fee_q=0, source="blocked", blocked=True)
    with patch("shopman.shop.services.pos._compute_delivery_fee", return_value=blocked):
        with pytest.raises(EditRefused) as refused:
            order_edit.plan(order, fulfillment={"type": "delivery", "delivery_address_structured": ENDERECO})
    assert refused.value.code == "delivery_out_of_area"


# ── Data e observação ────────────────────────────────────────────────────────


def test_data_nova_vai_pelo_reagendar_com_um_aviso_so(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    _plan(BAGUETE, 5, 10, vitrine)
    order = _encomenda("ED-17")

    result = order_edit.edit(
        order, notes="sem gergelim", schedule={"date": _day(5).isoformat(), "slot": "slot-12"}, actor="pos:marina",
    )

    order.refresh_from_db()
    assert order.data["delivery_date"] == _day(5).isoformat() and order.data["delivery_time_slot"] == "slot-12"
    assert order.data["order_notes"] == "sem gergelim"
    assert order.data["reschedule_history"][0]["reason"] == "edição da encomenda"
    # Um gesto, uma mensagem: nada de "nova data" separado.
    assert not Directive.objects.filter(payload__order_ref=order.ref, payload__template="order_rescheduled").exists()
    (aviso,) = _updated_notices(order)
    assert aviso.payload["status_note"].startswith("Nova data: ")
    assert aviso.payload["status_note"].endswith("Anotamos sua observação.")
    assert result.revision is None  # itens não mudaram: sem ajuste novo


def test_data_recusada_desfaz_tudo(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-18")

    with pytest.raises(EditRefused) as refused:
        order_edit.edit(order, notes="x", schedule={"date": _day(-1).isoformat(), "slot": ""}, actor="pos:marina")

    assert refused.value.field == "date"
    order.refresh_from_db()
    assert "order_notes" not in order.data


def test_cada_edicao_avisa_uma_vez(vitrine):
    _plan(BAGUETE, 3, 10, vitrine)
    order = _encomenda("ED-19")

    order_edit.edit(order, notes="primeira", actor="pos:marina")
    order.refresh_from_db()
    order_edit.edit(order, notes="segunda", actor="pos:marina")

    avisos = list(_updated_notices(order))
    assert len(avisos) == 2
    assert avisos[0].dedupe_key != avisos[1].dedupe_key


def test_o_aviso_usa_a_frase_da_edicao(vitrine):
    from shopman.shop.services.notification import _status_note

    order = SimpleNamespace(status="accepted", data={})
    assert _status_note(order, "order_updated", None, note="Anotamos sua observação.") == "Anotamos sua observação."
    assert _status_note(order, "order_updated", None) == "Os detalhes estão no acompanhamento."


def test_edicao_grande_vira_resumo_e_o_dinheiro_sai_sempre():
    """Um aviso não é extrato: acima de 3 mudanças de itens, a frase resume."""
    from shopman.shop.services.order_edit import MAX_ITEM_CHANGES_DESCRIBED, _describe_for_customer

    diff = {"added": [{"sku": f"S{i}", "name": f"Pão {i}", "qty": 1} for i in range(MAX_ITEM_CHANGES_DESCRIBED + 2)]}

    assert _describe_for_customer(diff) == f"Ajustamos {MAX_ITEM_CHANGES_DESCRIBED + 2} itens."
    assert _describe_for_customer({"added": diff["added"][:1]}) == "Entrou 1 Pão 0."


# ── Vendido por peso: entra como na venda ────────────────────────────────────

QUEIJO = "QUEIJO-KG"


@pytest.fixture
def queijo(db):
    from shopman.offerman.models import Product

    # R$ 89,90 o quilo; a etiqueta de R$ 28,05 é a peça de 312 g.
    return Product.objects.create(
        sku=QUEIJO, name="Queijo", unit="kg", base_price_q=8990, is_published=True, is_sellable=True,
    )


def _plan_kg(sku: str, offset: int, qty: str, position) -> None:
    product = SimpleNamespace(sku=sku, name=sku.title(), shelf_life_days=None)
    StockPlanning.plan(Decimal(qty), product, _day(offset), position=position)


def test_peca_pesada_entra_pela_etiqueta_com_o_peso_da_venda(vitrine, queijo):
    _plan(BAGUETE, 3, 10, vitrine)
    _plan_kg(QUEIJO, 3, "5", vitrine)
    order = _encomenda("ED-KG-1")

    result = order_edit.edit(
        order,
        lines=[
            {"line_id": "L1", "sku": BAGUETE, "qty": 2},
            {"sku": QUEIJO, "qty": 1, "weighed": {"entry": "label", "label_q": 2805}},
        ],
        actor="pos:marina",
    )

    order.refresh_from_db()
    by_line = {item.line_id: item for item in order_composition.effective_items(order)}
    piece = by_line["E1-1"]
    assert piece.qty == Decimal("0.312") and piece.unit_price_q == 8990 and piece.line_total_q == 2805
    assert piece.meta["weighed"] == {
        "entry": "label", "weight_g": 312, "price_per_kg_q": 8990, "total_q": 2805, "label_q": 2805,
    }
    assert result.plan.total_q == 2400 + 2805
    # A reserva é do peso, com fração.
    assert _holds_by_sku(order)[QUEIJO] == Decimal("0.312")


def test_duas_etiquetas_sao_duas_pecas(vitrine, queijo):
    order = _encomenda("ED-KG-2")

    result = order_edit.plan(
        order,
        lines=[
            {"line_id": "L1", "sku": BAGUETE, "qty": 2},
            {"sku": QUEIJO, "qty": 1, "weighed": {"entry": "label", "label_q": 2805}},
            {"sku": QUEIJO, "qty": 1, "weighed": {"entry": "label", "label_q": 2805}},
        ],
    )

    pieces = [item for item in result.items if item["sku"] == QUEIJO]
    assert [piece["line_id"] for piece in pieces] == ["E1-1", "E1-2"]
    assert result.total_q == 2400 + 2 * 2805


def test_item_por_peso_sem_etiqueta_recusa_com_a_frase_da_venda(vitrine, queijo):
    order = _encomenda("ED-KG-3")

    with pytest.raises(EditRefused) as refused:
        order_edit.plan(order, lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 2}, {"sku": QUEIJO, "qty": 1}])

    assert refused.value.code == "weight_entry_required"
    assert refused.value.message == "Queijo é vendido por peso: informe o valor da etiqueta."
    assert refused.value.field == "items.1.weighed"


def test_peso_digitado_so_com_a_entrada_por_peso_ligada(vitrine, queijo):
    order = _encomenda("ED-KG-4")
    lines = [
        {"line_id": "L1", "sku": BAGUETE, "qty": 2},
        {"sku": QUEIJO, "qty": 1, "weighed": {"entry": "weight", "weight_g": 500}},
    ]

    with pytest.raises(EditRefused) as refused:
        order_edit.plan(order, lines=lines)
    assert refused.value.code == "weight_entry_disabled"

    shop = Shop.load()
    shop.defaults = {**(shop.defaults or {}), "pos": {"weighed_weight_entry": True}}
    shop.save()
    result = order_edit.plan(order, lines=lines)
    (piece,) = [item for item in result.items if item["sku"] == QUEIJO]
    assert Decimal(str(piece["qty"])) == Decimal("0.5")
    assert piece["line_total_q"] == 4495


def test_etiqueta_em_item_por_unidade_recusa(vitrine, queijo):
    order = _encomenda("ED-KG-5")

    with pytest.raises(EditRefused) as refused:
        order_edit.plan(order, lines=[{"sku": CROISSANT, "qty": 1, "weighed": {"entry": "label", "label_q": 900}}])

    assert refused.value.code == "not_sold_by_weight"


def _com_peca(ref: str) -> Order:
    order = _encomenda(ref)
    OrderItem.objects.create(
        order=order, line_id="L2", sku=QUEIJO, name="Queijo", qty=Decimal("0.312"), unit_price_q=8990,
        line_total_q=2805,
        meta={"weighed": {"entry": "label", "label_q": 2805, "weight_g": 312, "price_per_kg_q": 8990, "total_q": 2805}},
    )
    Order.objects.filter(pk=order.pk).update(total_q=2400 + 2805)
    return Order.objects.get(pk=order.pk)


def test_peca_que_ja_estava_fica_e_nao_muda_de_peso(vitrine, queijo):
    order = _com_peca("ED-KG-6")

    kept = order_edit.plan(
        order,
        lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 3}, {"line_id": "L2", "sku": QUEIJO, "qty": "0.312"}],
    )
    by_line = {item["line_id"]: item for item in kept.items}
    assert by_line["L2"]["line_total_q"] == 2805 and kept.total_q == 3600 + 2805

    with pytest.raises(EditRefused) as refused:
        order_edit.plan(
            order,
            lines=[{"line_id": "L1", "sku": BAGUETE, "qty": 2}, {"line_id": "L2", "sku": QUEIJO, "qty": 1}],
        )
    assert refused.value.code == "weighed_line_changed"
