"""PDV: a encomenda reserva contra a data dela, não contra hoje.

O balcão não reserva enquanto monta a comanda; a reserva nasce no commit
(``services/stock.hold``), na data do pedido. Estes testes prendem as duas
pontas: o pronto de hoje esgotado não impede a encomenda de amanhã quando a
fornada de amanhã existe, e o pronto de hoje (pão do dia) não serve a quem
encomendou para amanhã.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Order
from shopman.stockman import stock
from shopman.stockman.models import Batch, Hold, Position, PositionKind

from shopman.shop.tests.test_pos_scheduled_order import _close, _payload, balcao  # noqa: F401

pytestmark = pytest.mark.django_db


def _position():
    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


def _croissant_do_dia():
    product = Product.objects.get(sku="CR")
    product.shelf_life_days = 0
    product.save(update_fields=["shelf_life_days"])
    return product


def _pronto(qty: str):
    stock.receive(quantity=Decimal(qty), sku="CR", position=_position(), target_date=None, reason="pronto")
    # Produto com validade ganha lote; só lote classificado é vendável.
    Batch.objects.filter(sku="CR", quality_grade_ref="").update(quality_grade_ref="standard")


def _amanha():
    return timezone.localdate() + timedelta(days=1)


def _holds_do_pedido(order):
    ids = [int(str(entry["hold_id"]).split(":")[1]) for entry in order.data.get("hold_ids", [])]
    return list(Hold.objects.filter(pk__in=ids))


def test_pronto_de_hoje_esgotado_nao_impede_encomenda_da_fornada_de_amanha(balcao, django_capture_on_commit_callbacks):  # noqa: F811
    operator, shift = balcao
    product = _croissant_do_dia()
    _pronto("2")
    stock.hold(Decimal("2"), product, target_date=timezone.localdate(), reference="outra-venda")
    stock.plan(quantity=Decimal("4"), product=product, target_date=_amanha(), position=_position(), reason="fornada")

    with django_capture_on_commit_callbacks(execute=True):
        result = _close(operator, _payload(
            shift, client_request_id="enc-amanha", delivery_date=_amanha().isoformat(),
            items=[{"sku": "CR", "name": "Croissant", "qty": 3, "unit_price_q": 900}],
        ))

    order = Order.objects.get(ref=result.order_ref)
    holds = _holds_do_pedido(order)
    assert sum(h.quantity for h in holds) == Decimal("3")
    assert {h.target_date for h in holds} == {_amanha()}
    assert {h.quant.target_date for h in holds if h.quant} == {_amanha()}, "sai da fornada de amanhã"


def test_pronto_de_hoje_nao_serve_encomenda_de_amanha(balcao, django_capture_on_commit_callbacks):  # noqa: F811
    operator, shift = balcao
    _croissant_do_dia()
    _pronto("5")

    with django_capture_on_commit_callbacks(execute=True):
        result = _close(operator, _payload(
            shift, client_request_id="enc-sem-fornada", delivery_date=_amanha().isoformat(),
        ))

    order = Order.objects.get(ref=result.order_ref)
    holds = _holds_do_pedido(order)
    assert holds, "a encomenda registra a demanda da data"
    assert all(h.quant is None for h in holds), "o pão do dia de hoje não é reservado para amanhã"
    assert {h.target_date for h in holds} == {_amanha()}


def test_encomenda_acima_do_plano_grava_o_disponivel_real_e_avisa_a_producao(balcao, django_capture_on_commit_callbacks):  # noqa: F811
    """#2559: a encomenda PDV-261116-K16 pediu 200 baguetes contra 22 planejadas.

    A reserva ficou sem fornada, a decisão gravou ``available_qty 200`` e
    ninguém na Produção soube. Agora a decisão diz o que tem lastro e o que é
    demanda, e a Produção recebe o aviso com o pedido e os dois números.

    Acima do plano só fecha com o gerente (D-041, WP-E2): a encomenda leva a
    assinatura dos dois números, como a tela a pede.
    """
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission

    from shopman.backstage.models import OperatorAlert
    from shopman.shop.services import pos as pos_service

    operator, shift = balcao
    product = _croissant_do_dia()
    stock.plan(quantity=Decimal("4"), product=product, target_date=_amanha(), position=_position(), reason="fornada")
    gerente = get_user_model().objects.create_user(username="joyce", password="x", is_staff=True)
    gerente.user_permissions.add(Permission.objects.get(content_type__app_label="cashman", codename="adjust_shift"))
    payload = _payload(
        shift, client_request_id="enc-acima-do-plano", delivery_date=_amanha().isoformat(),
        items=[{"sku": "CR", "name": "Croissant", "qty": 10, "unit_price_q": 900}],
    )
    review = pos_service.review_sale(channel_ref="pdv", payload=dict(payload), operator_username=operator.username)
    payload["manager_approval"] = {"token": pos_service.issue_sale_approval(
        gerente,
        operator_username=operator.username,
        scope=pos_service.SaleApprovalScope(over_plan=pos_service.over_plan_scope(review.preorder_over_plan)),
    )}

    with django_capture_on_commit_callbacks(execute=True):
        result = _close(operator, payload)

    order = Order.objects.get(ref=result.order_ref)
    [decision] = [d for d in order.data["availability_decision"]["decisions"] if d["sku"] == "CR"]
    demand = sum(h.quantity for h in _holds_do_pedido(order) if h.quant_id is None)
    assert demand > 0, "o que passa do plano fica como demanda"
    assert Decimal(str(decision["available_qty"])) == Decimal("4"), "o plano da data, não o pedido"
    assert Decimal(str(decision["demand_qty"])) == demand
    assert decision["reason_code"] == "demand_over_plan"

    alert = OperatorAlert.objects.get(type="order_demand_over_plan", order_ref=order.ref)
    assert alert.audience == "production"
    day = _amanha().strftime("%d/%m")
    assert f"10 Croissant para {day}, e o plano da data cobre 4" in alert.message
    assert f"Planeje mais 6 para {day}" in alert.message


def test_a_ressalva_da_encomenda_fala_de_plano_e_nao_de_balcao():
    """#2559: "só 44 em estoque. A venda de balcão vale" numa encomenda para amanhã."""
    from shopman.shop.services.pos import _availability_shortfall

    text = _availability_shortfall({"available_qty": Decimal("22")}, requested_qty=Decimal("200"), target_date=_amanha())
    assert text.startswith("200 pedidas, 22 planejadas para ")
    assert "balcão" not in text and "estoque" not in text
    assert "Produção é avisada" in text
    # Hoje continua sendo o balcão.
    hoje = _availability_shortfall({"available_qty": 2}, requested_qty=3, target_date=timezone.localdate())
    assert "em estoque" in hoje
