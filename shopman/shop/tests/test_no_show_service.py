"""Não retirado (WP-G11): a política, a hora, o destino de cada linha e o comando.

Regra do dono numa frase: o dinheiro segue o produto. O que estes testes prendem:

- a política de ``Shop.defaults["no_show"]`` e os padrões dela;
- a hora em que o gesto libera, para pedido pago e não pago, com e sem hora
  combinada, em dia passado e em dia sem expediente;
- quem pode (pronto, retirada, fora do iFood e do balcão; a conta da casa só em aberto e sem outra forma junto);
- o destino de cada linha, decidido pelo servidor a partir de fatos;
- ``refund_q`` e ``retained_q`` com pedido todo de volta, todo perdido e misto;
- o comando grava o bloco e cancela com o motivo próprio, sob lock, uma vez só,
  e recusa tela velha;
- o texto que o cliente lê diz para onde o dinheiro foi.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.policies import no_show_reason
from shopman.shop.policies.no_show_policy import NoShowPolicy, resolve_no_show_policy
from shopman.shop.services import cancel_reasons, no_show
from shopman.shop.tests import _no_show as world

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv", "ifood")]


@pytest.fixture
def relogio(monkeypatch):
    """Crava o relógio: ``relogio(16)`` são 16h de hoje para todo o Django."""

    def set_now(hour: int, minute: int = 0, *, days: int = 0):
        moment = world.at(hour, minute, days=days)
        monkeypatch.setattr(timezone, "now", lambda: moment)
        return moment

    return set_now


@pytest.fixture
def shop():
    return world.make_shop()


@pytest.fixture
def paes(shop):
    world.product("CROIS", price_q=935)
    world.product("BOLO", price_q=3000)
    world.lot("CROIS")
    world.lot("BOLO")


def _today_at(slot: str) -> dict:
    return {"delivery_date": timezone.localdate().isoformat(), "delivery_time_slot": slot}


# ── Política ──────────────────────────────────────────────────────────────────


def test_policy_defaults_are_the_house_rule():
    policy = NoShowPolicy.from_defaults(None)

    assert (policy.tolerance_minutes, policy.cutoff_minutes_before_close, policy.paid_waits_cutoff) == (60, 0, True)


def test_policy_reads_the_shop_block_and_ignores_garbage(shop):
    shop.defaults = {"no_show": {"tolerance_minutes": 30, "cutoff_minutes_before_close": "x", "paid_waits_cutoff": "sim"}}
    shop.save(update_fields=["defaults"])

    policy = resolve_no_show_policy()

    assert policy.tolerance_minutes == 30
    # Valor ilegível cai no padrão declarado, nunca em zero por acidente.
    assert policy.cutoff_minutes_before_close == 0
    assert policy.paid_waits_cutoff is True


def test_policy_refuses_negative_and_boolean_minutes():
    policy = NoShowPolicy.from_defaults({"no_show": {"tolerance_minutes": -5, "cutoff_minutes_before_close": True}})

    assert (policy.tolerance_minutes, policy.cutoff_minutes_before_close) == (60, 0)


def test_policy_can_turn_the_paid_cutoff_off():
    assert NoShowPolicy.from_defaults({"no_show": {"paid_waits_cutoff": False}}).paid_waits_cutoff is False


# ── A hora em que libera ─────────────────────────────────────────────────────


def test_unpaid_order_waits_the_tolerance_after_the_agreed_time(paes, relogio):
    relogio(14)
    order = world.ready_order("NS-UNPAID-15", [("CROIS", 2, 935)], data=_today_at("15:00-15:30"))

    relogio(15, 59)
    at, why = no_show.release_gate(order)
    assert at == world.at(16)
    assert why == "A retirada foi combinada para as 15h: o não retirado libera às 16h."
    assert no_show.block_reason(order) == why

    relogio(16)
    assert no_show.release_gate(order) == (None, "")
    assert no_show.block_reason(order) == ""


def test_unpaid_order_without_agreed_time_counts_from_when_it_got_ready(paes, relogio):
    relogio(14, 10)
    order = world.ready_order("NS-UNPAID-READY", [("CROIS", 1, 935)])

    relogio(15)
    at, why = no_show.release_gate(order)
    assert at == world.at(15, 10)
    assert why == "O pedido ficou pronto às 14h10: o não retirado libera às 15h10."

    relogio(15, 10)
    assert no_show.block_reason(order) == ""


def test_paid_order_only_releases_at_the_closing_of_the_agreed_day(paes, relogio):
    relogio(14)
    order = world.ready_order("NS-PAID", [("CROIS", 2, 935)], data=_today_at("15:00-15:30"))
    world.pay(order, "pix")

    # Passou a hora e a tolerância, mas o pedido está pago: espera o fim do expediente.
    relogio(18, 59)
    at, why = no_show.release_gate(order)
    assert at == world.at(19)
    assert why == "Pedido pago: o não retirado libera no corte do dia, às 19h."

    relogio(19)
    assert no_show.block_reason(order) == ""


def test_paid_cutoff_can_come_before_closing(paes, relogio, shop):
    shop.defaults = {"no_show": {"cutoff_minutes_before_close": 30}}
    shop.save(update_fields=["defaults"])
    relogio(14)
    order = world.ready_order("NS-PAID-CUT", [("CROIS", 1, 935)], data=_today_at("15:00-15:30"))
    world.pay(order, "pix")

    relogio(18, 29)
    assert no_show.release_gate(order)[0] == world.at(18, 30)
    relogio(18, 30)
    assert no_show.block_reason(order) == ""


def test_paid_order_follows_the_unpaid_rule_when_the_house_turns_the_cutoff_off(paes, relogio, shop):
    shop.defaults = {"no_show": {"paid_waits_cutoff": False}}
    shop.save(update_fields=["defaults"])
    relogio(14)
    order = world.ready_order("NS-PAID-OFF", [("CROIS", 1, 935)], data=_today_at("15:00-15:30"))
    world.pay(order, "pix")

    relogio(16)
    assert no_show.block_reason(order) == ""


def test_paid_order_of_a_past_day_is_already_released(paes, relogio):
    relogio(14)
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    order = world.ready_order(
        "NS-PAID-ONTEM", [("CROIS", 1, 935)], data={"delivery_date": yesterday, "delivery_time_slot": "15:00-15:30"},
    )
    world.pay(order, "pix")

    # De manhã cedo, bem antes do fechamento de hoje: o dia combinado já passou.
    relogio(8)
    assert no_show.release_gate(order) == (None, "")


def test_paid_order_on_a_day_without_declared_hours_uses_the_unpaid_rule(paes, relogio, shop):
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[
        timezone.localdate().weekday()
    ]
    shop.opening_hours = {day: hours for day, hours in world.OPEN_EVERY_DAY.items() if day != weekday}
    shop.save(update_fields=["opening_hours"])
    relogio(14)
    order = world.ready_order("NS-PAID-FECHADO", [("CROIS", 1, 935)], data=_today_at("15:00-15:30"))
    world.pay(order, "pix")

    relogio(15, 30)
    assert no_show.release_gate(order)[0] == world.at(16)
    relogio(16)
    assert no_show.block_reason(order) == ""


def test_unreadable_payment_counts_as_paid_for_the_clock(paes, relogio, monkeypatch):
    relogio(14)
    order = world.ready_order("NS-ILEGIVEL", [("CROIS", 1, 935)], data=_today_at("15:00-15:30"))
    monkeypatch.setattr("shopman.shop.services.payment.captured_balance_q", lambda order, **kwargs: None)

    relogio(16)
    assert no_show.release_gate(order)[0] == world.at(19)


# ── Quem pode ────────────────────────────────────────────────────────────────


def test_only_a_ready_pickup_order_outside_ifood_and_the_counter_is_a_candidate(paes, relogio):
    relogio(10)
    ready = world.ready_order("NS-CAND", [("CROIS", 1, 935)])
    preparing = world.ready_order("NS-PREP", [("CROIS", 1, 935)], held=False)
    Order.objects.filter(pk=preparing.pk).update(status=Order.Status.PREPARING)
    preparing.refresh_from_db()
    delivery = world.ready_order("NS-ENTREGA", [("CROIS", 1, 935)], held=False, data={"fulfillment_type": "delivery"})
    ifood = world.ready_order("NS-IFOOD", [("CROIS", 1, 935)], held=False, channel_ref="ifood")
    counter = world.ready_order(
        "NS-BALCAO", [("CROIS", 1, 935)], held=False, channel_ref="pdv",
        data={"origin_channel": "pos", "pos": {"sales_mode": "counter"}},
    )

    assert no_show.is_candidate(ready) is True
    assert [no_show.is_candidate(order) for order in (preparing, delivery, ifood, counter)] == [False] * 4
    assert no_show.eligibility_reason(preparing) == "Não retirado é para pedido pronto, esperando a retirada."
    assert no_show.eligibility_reason(delivery) == "Este pedido é de entrega: não retirado é só para retirada."
    assert no_show.eligibility_reason(ifood) == "Pedido do iFood: o que não foi retirado é resolvido no portal do iFood."
    assert no_show.eligibility_reason(counter) == "Venda de balcão não tem retirada a esperar."


def _on_account(order, amount_q: int | None = None, *, customer_ref: str = "CLI-CONTA") -> str:
    """Lança o pedido na conta da casa, como o fechamento do PDV faz. Devolve o ``intent_ref``."""
    from shopman.payman import PaymentService

    intent = PaymentService.charge_to_account(
        order.ref, amount_q if amount_q is not None else order.total_q,
        customer_ref=customer_ref, idempotency_key=f"order-payment:{order.ref}:account:terminal",
    )
    order.data["payment"] = {**(order.data.get("payment") or {}), "method": "account", "intent_ref": intent.ref}
    order.save(update_fields=["data", "updated_at"])
    return intent.ref


def test_house_account_order_with_open_debt_can_be_closed_as_not_picked_up(paes, relogio):
    """A conta da casa entra no gesto (#2697): o que se perdeu fica como dívida, o resto sai da conta."""
    from shopman.shop.services import payment

    relogio(10)
    order = world.ready_order("NS-CONTA", [("CROIS", 2, 935), ("BOLO", 1, 3000)], held=False)
    order.data["hold_ids"] = [world.fulfilled_hold("CROIS", 2, order_ref=order.ref)]
    order.save(update_fields=["data", "updated_at"])
    _on_account(order)
    assert no_show.eligibility_reason(order) == ""

    relogio(19, 5)
    preview = no_show.preview(order)
    assert (preview["paid_q"], preview["refund_q"], preview["retained_q"]) == (4870, 1870, 3000)
    assert preview["money_sentence"] == "R$ 18,70 saem da conta do cliente. R$ 30,00 continuam nela, pelo que se perdeu."
    assert "Tiramos R$ 18,70 da sua conta na loja" in preview["customer_text"]
    assert "R$ 30,00 continuam na conta" in preview["customer_text"]

    block = no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")
    assert block["on_account"] is True
    order.refresh_from_db()
    # O que o ``on_cancelled`` faz com o dinheiro: a dívida fica com o valor da perda.
    payment.refund(order)
    assert payment.open_account_debt_q(order) == 3000
    event = order.events.get(type="account_debt_reduced")
    assert event.payload["amount_q"] == 1870
    # De novo (retry do cancelamento): nada sai duas vezes.
    payment.refund(order)
    assert payment.open_account_debt_q(order) == 3000


def test_house_account_order_with_everything_back_on_sale_leaves_nothing_owed(paes, relogio):
    from shopman.shop.services import payment

    relogio(10)
    order = world.ready_order("NS-CONTA-TUDO", [("CROIS", 1, 935)])
    _on_account(order)

    relogio(19, 5)
    no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")
    order.refresh_from_db()
    payment.refund(order)

    assert payment.open_account_debt_q(order) == 0


def test_house_account_already_settled_or_mixed_is_refused_with_a_clear_reason(paes, relogio):
    from shopman.payman import PaymentService

    relogio(10)
    settled = world.ready_order("NS-CONTA-ACERTADA", [("CROIS", 1, 935)])
    PaymentService.capture(_on_account(settled))
    mixed = world.ready_order(
        "NS-CONTA-MISTA", [("CROIS", 1, 935)],
        payment={"method": "account", "tenders": [{"method": "account", "amount_q": 500}, {"method": "cash", "amount_q": 435}]},
    )

    assert no_show.eligibility_reason(settled) == "A conta deste pedido já foi acertada: o não retirado dele é com o Dono."
    assert no_show.eligibility_reason(mixed) == (
        "Parte na conta da casa e parte em outra forma de pagamento: o não retirado deste pedido é com o Dono."
    )


def test_account_customer_text_says_what_left_the_account():
    everything = {"paid_q": 935, "refund_q": 935, "retained_q": 0, "on_account": True}
    nothing = {"paid_q": 935, "refund_q": 0, "retained_q": 935, "on_account": True}

    assert no_show_reason.customer_text(everything) == (
        "O pedido ficou pronto e não foi retirado. Tiramos R$ 9,35 da sua conta na loja."
    )
    assert no_show_reason.customer_text(nothing) == (
        "O pedido ficou pronto e não foi retirado. O valor continua na sua conta na loja, como dizem os Termos."
    )


def test_channel_whose_cycle_does_not_let_ready_be_cancelled_is_refused(paes, relogio):
    relogio(10)
    order = world.ready_order("NS-REGUA", [("CROIS", 1, 935)])
    # O ciclo padrão do Orderman (canal sem ``lifecycle.transitions``): pronto não cancela.
    Order.objects.filter(pk=order.pk).update(snapshot={"items": order.snapshot["items"]})
    order = Order.objects.get(pk=order.pk)

    relogio(12)
    assert no_show.eligibility_reason(order) == "Este canal não permite encerrar um pedido pronto como não retirado."
    with pytest.raises(no_show.NoShowRefused):
        no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "no_show" not in order.data


# ── O destino de cada linha ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (no_show.LineFacts(made_to_order=False, stock_fulfilled=True, lot_expired=False), ("restock", "")),
        (no_show.LineFacts(made_to_order=True, stock_fulfilled=True, lot_expired=False), ("loss", "made_to_order")),
        (no_show.LineFacts(made_to_order=False, stock_fulfilled=False, lot_expired=False), ("loss", "no_stock")),
        (no_show.LineFacts(made_to_order=False, stock_fulfilled=True, lot_expired=True), ("loss", "lot_expired")),
    ],
)
def test_destiny_is_decided_from_facts_in_one_place(facts, expected):
    assert no_show.decide_destiny(facts) == expected


def _destinies(order, **kwargs) -> dict[str, tuple[str, str]]:
    return {line["sku"]: (line["destiny"], line["reason"]) for line in no_show.line_decisions(order, **kwargs)}


def test_line_with_fresh_stock_goes_back_on_sale(paes, relogio):
    relogio(10)
    order = world.ready_order("NS-FRESCO", [("CROIS", 2, 935)])

    assert _destinies(order) == {"CROIS": ("restock", "")}


def test_made_to_order_line_is_a_loss(shop, relogio):
    from shopman.craftsman.models import ProductionMode, Recipe

    relogio(10)
    world.product("CROQUE", price_q=2800)
    world.lot("CROQUE")
    Recipe.objects.create(
        ref="croque-na-hora", name="Croque", output_sku="CROQUE", batch_size=Decimal("1"),
        is_active=True, production_mode=ProductionMode.MADE_TO_ORDER,
    )
    order = world.ready_order("NS-NA-HORA", [("CROQUE", 1, 2800)])

    assert _destinies(order) == {"CROQUE": ("loss", "made_to_order")}


def test_line_without_fulfilled_stock_is_a_loss(paes, relogio):
    relogio(10)
    order = world.ready_order("NS-SEM-BAIXA", [("CROIS", 2, 935)], held=False)

    assert _destinies(order) == {"CROIS": ("loss", "no_stock")}


def test_line_whose_lot_expired_by_the_time_of_the_gesture_is_a_loss(shop, relogio):
    relogio(10)
    today = timezone.localdate()
    world.product("BRIOCHE", price_q=1200)
    world.lot("BRIOCHE", expires=today)
    order = world.ready_order("NS-VENCIDO", [("BRIOCHE", 1, 1200)])

    # No dia da validade, com a loja aberta, ainda volta à venda; no dia
    # seguinte, o lote venceu.
    assert _destinies(order) == {"BRIOCHE": ("restock", "")}
    assert _destinies(order, now=world.at(8, days=1)) == {"BRIOCHE": ("loss", "lot_expired")}


def test_lot_that_expires_today_is_a_loss_once_the_shop_has_closed(shop, relogio):
    """Depois do fechamento não há balcão para o lote de hoje voltar: é perda.

    É o caso do pedido PAGO, que só libera no corte do dia (o fechamento): o pão
    cujo último dia de venda é hoje não "volta à venda" numa loja fechada.
    """
    relogio(10)
    today = timezone.localdate()
    world.product("PAO-DO-DIA", price_q=1500)
    world.lot("PAO-DO-DIA", expires=today)
    world.product("BOLO-2D", price_q=3000)
    world.lot("BOLO-2D", expires=today + timedelta(days=1))
    order = world.ready_order("NS-FECHOU", [("PAO-DO-DIA", 1, 1500), ("BOLO-2D", 1, 3000)])

    # A loja de teste fecha às 19h.
    assert _destinies(order, now=world.at(18, 59)) == {"PAO-DO-DIA": ("restock", ""), "BOLO-2D": ("restock", "")}
    assert _destinies(order, now=world.at(19)) == {"PAO-DO-DIA": ("loss", "lot_expired"), "BOLO-2D": ("restock", "")}


def test_next_selling_day_is_today_while_open_and_tomorrow_after_closing(shop):
    today = timezone.localdate()

    assert no_show.next_selling_day(world.at(10)) == today
    assert no_show.next_selling_day(world.at(19)) == today + timedelta(days=1)
    assert no_show.next_selling_day(world.at(23, 30)) == today + timedelta(days=1)


def test_lot_without_expiry_falls_back_to_the_product_shelf_life(shop, relogio):
    relogio(10)
    world.product("BAGUETE", price_q=900, shelf_life_days=0)
    world.lot("BAGUETE", expires=None)
    order = world.ready_order("NS-PRAZO", [("BAGUETE", 1, 900)])

    assert _destinies(order) == {"BAGUETE": ("restock", "")}
    assert _destinies(order, now=world.at(8, days=1)) == {"BAGUETE": ("loss", "lot_expired")}


def test_stock_with_no_way_to_know_the_expiry_goes_back_on_sale(shop, relogio):
    relogio(10)
    world.product("GELEIA", price_q=2500)
    world.lot("GELEIA", expires=None)
    order = world.ready_order("NS-SEM-VALIDADE", [("GELEIA", 1, 2500)])

    assert _destinies(order, now=world.at(8, days=30)) == {"GELEIA": ("restock", "")}


# ── O dinheiro ───────────────────────────────────────────────────────────────


def _line(destiny: str, value_q: int) -> dict:
    return {"destiny": destiny, "value_q": value_q}


@pytest.mark.parametrize(
    ("lines", "paid_q", "expected"),
    [
        # Tudo volta à venda: o cliente recebe tudo.
        ([_line("restock", 1870), _line("restock", 3000)], 4870, (4870, 0)),
        # Tudo se perdeu: a loja fica com tudo.
        ([_line("loss", 1870), _line("loss", 3000)], 4870, (0, 4870)),
        # Misto: volta o valor das linhas que voltam.
        ([_line("restock", 1870), _line("loss", 3000)], 4870, (1870, 3000)),
        # Não pago: nada a devolver, nada retido.
        ([_line("restock", 1870), _line("loss", 3000)], 0, (0, 0)),
        # Pagou só um sinal, menor que a perda: a loja fica com o sinal todo.
        ([_line("restock", 1870), _line("loss", 3000)], 1000, (0, 1000)),
        # Sinal maior que a perda: a loja fica com a perda, o resto volta.
        ([_line("restock", 1870), _line("loss", 3000)], 4000, (1000, 3000)),
        # Pagou a mais (pedido reduzido depois de pago): o excedente volta junto.
        ([_line("restock", 1870), _line("loss", 3000)], 6000, (3000, 3000)),
        # Tudo volta e havia excedente: volta tudo o que entrou.
        ([_line("restock", 1870)], 2500, (2500, 0)),
    ],
)
def test_the_shop_keeps_the_value_of_what_was_lost_and_only_that(lines, paid_q, expected):
    assert no_show.money_split(lines, paid_q) == expected


def test_line_value_is_the_price_paid_times_the_quantity(paes, relogio):
    relogio(10)
    order = world.ready_order("NS-VALOR", [("CROIS", 2, 935), ("BOLO", 1, 3000)])

    assert [(line["line_id"], line["qty"], line["value_q"]) for line in no_show.line_decisions(order)] == [
        ("L1", "2", 1870),
        ("L2", "1", 3000),
    ]


# ── Prévia ───────────────────────────────────────────────────────────────────


def test_preview_says_everything_before_the_gesture_and_writes_nothing(paes, relogio):
    relogio(10)
    order = world.ready_order("NS-PREVIA", [("CROIS", 2, 935), ("BOLO", 1, 3000)], held=False)
    order.data["hold_ids"] = [world.fulfilled_hold("CROIS", 2, order_ref=order.ref)]
    order.save(update_fields=["data", "updated_at"])
    world.pay(order, "pix")

    relogio(19)
    preview = no_show.preview(order)

    assert preview["allowed"] is True
    assert preview["block_reason"] == ""
    assert [(line["sku"], line["destiny"]) for line in preview["lines"]] == [("CROIS", "restock"), ("BOLO", "loss")]
    assert (preview["paid_q"], preview["refund_q"], preview["retained_q"]) == (4870, 1870, 3000)
    assert preview["money_sentence"] == (
        "R$ 18,70 serão estornados ao Pix do cliente. R$ 30,00 ficam com a loja, pelo que se perdeu."
    )
    assert preview["customer_text"] == no_show_reason.customer_text(preview)
    assert preview["revision"] == no_show.revision(order)
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "no_show" not in order.data


def test_preview_before_the_time_says_when_it_releases(paes, relogio):
    relogio(14)
    order = world.ready_order("NS-CEDO", [("CROIS", 1, 935)], data=_today_at("15:00-15:30"))

    relogio(15)
    preview = no_show.preview(order)

    assert preview["allowed"] is False
    assert preview["block_reason"] == "A retirada foi combinada para as 15h: o não retirado libera às 16h."
    assert preview["releases_at"] == world.at(16).isoformat()


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("cash", "R$ 9,35 em dinheiro ficam a devolver no caixa do PDV."),
        ("credit", "R$ 9,35 ficam a estornar na maquininha, pelo PDV."),
        ("card", "R$ 9,35 serão estornados no cartão do cliente."),
    ],
)
def test_money_sentence_names_the_way_back_by_payment_method(paes, relogio, method, expected):
    relogio(10)
    order = world.ready_order(f"NS-FRASE-{method}", [("CROIS", 1, 935)])
    world.pay(order, method)

    assert no_show.preview(order, now=world.at(19))["money_sentence"] == expected


def test_money_sentence_for_unpaid_and_for_everything_lost(paes, relogio):
    relogio(10)
    unpaid = world.ready_order("NS-FRASE-NAO-PAGO", [("CROIS", 1, 935)])
    lost = world.ready_order("NS-FRASE-PERDA", [("CROIS", 1, 935)], held=False)
    world.pay(lost, "pix")

    assert no_show.preview(unpaid, now=world.at(19))["money_sentence"] == (
        "O pedido não foi pago: não há dinheiro a devolver."
    )
    assert no_show.preview(lost, now=world.at(19))["money_sentence"] == (
        "Nada volta ao cliente: R$ 9,35 ficam com a loja, pelo que se perdeu."
    )


# ── O comando ────────────────────────────────────────────────────────────────


def test_command_writes_the_block_and_cancels_with_its_own_reason(paes, relogio):
    relogio(10)
    order = world.ready_order("NS-CMD", [("CROIS", 2, 935), ("BOLO", 1, 3000)], held=False)
    order.data["hold_ids"] = [world.fulfilled_hold("CROIS", 2, order_ref=order.ref)]
    order.save(update_fields=["data", "updated_at"])
    world.pay(order, "pix")

    moment = relogio(19, 5)
    block = no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")

    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert order.data["cancellation_reason"] == "not_picked_up"
    assert order.data["cancellation_reason_key"] == "not_picked_up"
    assert order.data["cancelled_by"] == "ana"
    assert order.data["no_show"] == block
    assert block["at"] == moment.isoformat()
    assert (block["actor"], block["approved_by"]) == ("ana", "gerente")
    assert (block["paid_q"], block["refund_q"], block["retained_q"]) == (4870, 1870, 3000)
    assert block["lines"] == [
        {"line_id": "L1", "sku": "CROIS", "name": "Crois", "qty": "2", "destiny": "restock", "reason": "", "value_q": 1870},
        {"line_id": "L2", "sku": "BOLO", "name": "Bolo", "qty": "1", "destiny": "loss", "reason": "no_stock", "value_q": 3000},
    ]


def test_command_before_the_time_is_refused_and_writes_nothing(paes, relogio):
    relogio(14)
    order = world.ready_order("NS-CMD-CEDO", [("CROIS", 1, 935)], data=_today_at("15:00-15:30"))

    relogio(15)
    with pytest.raises(no_show.NoShowRefused, match="libera às 16h"):
        no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")

    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "no_show" not in order.data


def test_command_refuses_a_stale_screen(paes, relogio):
    relogio(10)
    order = world.ready_order("NS-CMD-VELHA", [("CROIS", 1, 935)])
    stale = no_show.revision(order)
    # Depois que a tela leu a prévia, o pagamento chegou: o dinheiro do gesto mudou.
    world.pay(order, "pix")

    relogio(19)
    with pytest.raises(no_show.NoShowStale):
        no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente", expected_revision=stale)

    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "no_show" not in order.data


def test_command_is_idempotent(paes, relogio):
    relogio(10)
    order = world.ready_order("NS-CMD-DUAS", [("CROIS", 1, 935)])

    relogio(12)
    first = no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")
    relogio(13)
    second = no_show.mark_not_picked_up(order, actor="bia", approved_by="outra")

    assert second == first
    order.refresh_from_db()
    assert order.data["no_show"]["approved_by"] == "gerente"
    assert order.events.filter(type="status_changed").count() == 1


def test_command_refuses_when_the_payment_cannot_be_read(paes, relogio, monkeypatch):
    relogio(10)
    order = world.ready_order("NS-CMD-ILEGIVEL", [("CROIS", 1, 935)])
    monkeypatch.setattr("shopman.shop.services.payment.captured_balance_q", lambda order, **kwargs: None)

    relogio(19)
    assert no_show.preview(order)["allowed"] is False
    with pytest.raises(no_show.NoShowRefused, match="ler o pagamento"):
        no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")

    order.refresh_from_db()
    assert order.status == Order.Status.READY


# ── O texto que o cliente lê ─────────────────────────────────────────────────


def test_not_picked_up_is_not_a_reason_the_operator_picks():
    assert "not_picked_up" not in {reason.key for reason in cancel_reasons.OPERATOR_CANCEL_REASONS}
    assert cancel_reasons.validation_message("not_picked_up") == cancel_reasons.UNKNOWN_REASON_MESSAGE
    assert cancel_reasons.cancel_reason("not_picked_up").label == "Não retirado"


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        (
            {"paid_q": 1870, "refund_q": 1870, "retained_q": 0},
            "O pedido ficou pronto e não foi retirado. Vamos devolver R$ 18,70 pelo mesmo meio de pagamento.",
        ),
        (
            {"paid_q": 3000, "refund_q": 0, "retained_q": 3000},
            "O pedido ficou pronto e não foi retirado. O valor ficou com a loja, como dizem os Termos.",
        ),
        (
            {"paid_q": 4870, "refund_q": 1870, "retained_q": 3000},
            "O pedido ficou pronto e não foi retirado. Vamos devolver R$ 18,70 pelo mesmo meio de pagamento, "
            "pelo que ainda pôde voltar à venda. R$ 30,00 ficaram com a loja, como dizem os Termos.",
        ),
        # Não pago: nenhuma frase de dinheiro.
        ({"paid_q": 0, "refund_q": 0, "retained_q": 0}, "O pedido ficou pronto e não foi retirado."),
    ],
)
def test_customer_text_says_where_the_money_went(block, expected):
    data = {"cancellation_reason_key": "not_picked_up", "no_show": block}

    text = cancel_reasons.customer_text(data)

    assert text == expected
    assert "—" not in text and "–" not in text


def test_cancellation_notice_carries_the_text_with_the_money(paes, relogio, django_capture_on_commit_callbacks, monkeypatch):
    from shopman.shop.adapters._notification_templates import derive_context

    relogio(10)
    order = world.ready_order("NS-AVISO", [("CROIS", 2, 935)])
    sent = []
    monkeypatch.setattr("shopman.shop.lifecycle.notification.send", lambda order, template, **kwargs: sent.append((template, kwargs)))

    relogio(12)
    with django_capture_on_commit_callbacks(execute=True):
        no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")

    ((template, kwargs),) = [entry for entry in sent if entry[0] == "order_cancelled"]
    assert kwargs["reason_key"] == "not_picked_up"
    assert kwargs["status_note"] == "O pedido ficou pronto e não foi retirado."
    context = derive_context({"order_ref": order.ref, "status_note": kwargs["status_note"]})
    assert context["cancellation_reason_suffix"] == ". O pedido ficou pronto e não foi retirado."
