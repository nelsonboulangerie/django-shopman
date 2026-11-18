"""PDV: encomenda acima da fornada planejada da data bloqueia; só o gerente libera.

Decisão do dono D-041 (WP-E2 do EXCELENCIA-PDV-PLANO). Na encomenda
PDV-261116-K16 a Caixa prometeu 200 baguetes para 17/11 contra 22 planejadas, e
os R$ 2.747,00 ficaram "Na retirada", sem cobrança. Agora:

1. a review publica, por linha, o pedido, a fornada planejada e o livre da data;
2. o fechamento acima do plano sem a assinatura do gerente é recusado NO
   SERVIDOR, e a assinatura vale só para os números que ele viu;
3. encomenda de outro dia não fica para pagar na retirada.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.utils import timezone
from shopman.cashman.models import Shift
from shopman.offerman.models import Product
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind

from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos import SaleApprovalScope, issue_sale_approval, over_plan_scope
from shopman.shop.services.pos_intent import PosIntentError
from shopman.shop.tests.test_pos_scheduled_order import _payload, balcao  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _cache_limpo():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def joyce():
    user = get_user_model().objects.create_user(username="joyce", password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="adjust_shift"))
    return user


def _amanha():
    return timezone.localdate() + timedelta(days=1)


def _plano(qty: str, *, sku: str = "CR", day=None):
    product = Product.objects.get(sku=sku)
    product.shelf_life_days = 0
    product.save(update_fields=["shelf_life_days"])
    position, _ = Position.objects.get_or_create(
        ref="loja", defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.plan(quantity=Decimal(qty), product=product, target_date=day or _amanha(), position=position, reason="fornada")


def _encomenda(shift, *, qty: int, client_request_id: str = "enc-1", **overrides) -> dict:
    return _payload(
        shift,
        client_request_id=client_request_id,
        delivery_date=_amanha().isoformat(),
        items=[{"sku": "CR", "name": "Croissant", "qty": qty, "unit_price_q": 900}],
        **overrides,
    )


def _review(operator, payload):
    return pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username)


def _fechar(operator, payload):
    payload["expected_total_q"] = _review(operator, dict(payload)).total_q
    return pos_service.close_sale(
        channel_ref="pdv", payload=payload, actor=f"pos:{operator.username}", operator_username=operator.username,
    )


def _carimbo(joyce, operator, review) -> dict:
    token = issue_sale_approval(
        joyce,
        operator_username=operator.username,
        scope=SaleApprovalScope(tab_ref="", over_plan=over_plan_scope(review.preorder_over_plan)),
    )
    return {"token": token}


# ── A review diz os dois números ─────────────────────────────────────────────


def test_a_review_publica_pedido_plano_e_livre_e_chama_o_gerente(balcao):  # noqa: F811
    operator, shift = balcao
    _plano("22")

    review = _review(operator, _encomenda(shift, qty=200))

    assert review.requires_manager_approval
    assert "preorder_over_plan" in review.approval_reasons
    [line] = review.preorder_over_plan
    assert line["sku"] == "CR"
    assert line["requested_qty"] == Decimal("200")
    assert line["planned_qty"] == Decimal("22")
    assert line["unclaimed_qty"] == Decimal("22")
    assert line["date"] == _amanha().isoformat()
    assert set(line) == {"sku", "name", "requested_qty", "planned_qty", "unclaimed_qty", "date"}


def test_dentro_do_plano_nao_chama_ninguem(balcao):  # noqa: F811
    operator, shift = balcao
    _plano("22")

    review = _review(operator, _encomenda(shift, qty=22))

    assert not review.preorder_over_plan
    assert "preorder_over_plan" not in review.approval_reasons


def test_lote_parcialmente_prometido_mede_contra_o_que_sobra_dele(balcao):  # noqa: F811
    """22 planejadas, 15 já prometidas a outra encomenda: 10 passa do plano."""
    operator, shift = balcao
    _plano("22")
    stock.hold(Decimal("15"), Product.objects.get(sku="CR"), target_date=_amanha(), reference="outra-encomenda")

    [line] = _review(operator, _encomenda(shift, qty=10)).preorder_over_plan

    assert line["planned_qty"] == Decimal("22")
    assert line["unclaimed_qty"] == Decimal("7")


def test_a_sobra_de_hoje_nao_lastreia_encomenda_de_amanha(balcao):  # noqa: F811
    """Dono, 18/11/2026: "não oferecemos pães de um dia para o outro!".

    O pão que sobra hoje vira "Ontem" (D-1, só no balcão) e nunca lastreia
    encomenda, mesmo com validade que o deixaria vendável amanhã.
    """
    operator, shift = balcao
    _plano("22")
    product = Product.objects.get(sku="CR")
    product.shelf_life_days = 1
    product.save(update_fields=["shelf_life_days"])
    position = Position.objects.get(ref="loja")
    stock.receive(quantity=Decimal("22"), sku="CR", position=position, target_date=None, reason="sobra de hoje")

    [line] = _review(operator, _encomenda(shift, qty=30)).preorder_over_plan

    assert line["planned_qty"] == Decimal("22")
    assert line["unclaimed_qty"] == Decimal("22"), "a vitrine de hoje não entra em nenhum dos números"


def test_duas_encomendas_de_20_contra_22_nao_passam_as_duas_sem_gerente(balcao, django_capture_on_commit_callbacks):  # noqa: F811
    operator, shift = balcao
    _plano("22")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(operator, _encomenda(shift, qty=20, client_request_id="primeira"))

    [line] = _review(operator, _encomenda(shift, qty=20, client_request_id="segunda")).preorder_over_plan
    assert line["planned_qty"] == Decimal("22")
    assert line["unclaimed_qty"] == Decimal("2")
    with pytest.raises(PosIntentError) as exc:
        _fechar(operator, _encomenda(shift, qty=20, client_request_id="segunda"))
    assert "20 pedidas, 22 planejadas" in exc.value.message
    assert "2 ainda sem encomenda" in exc.value.message


def test_venda_de_hoje_nao_e_encomenda(balcao):  # noqa: F811
    operator, shift = balcao
    _plano("2", day=timezone.localdate() + timedelta(days=1))

    review = _review(operator, _payload(shift, client_request_id="hoje", items=[
        {"sku": "CR", "name": "Croissant", "qty": 50, "unit_price_q": 900},
    ]))

    assert not review.preorder_over_plan


# ── O bloqueio vale no servidor ──────────────────────────────────────────────


def test_acima_do_plano_sem_o_gerente_nao_fecha(balcao):  # noqa: F811
    operator, shift = balcao
    _plano("22")

    with pytest.raises(PosIntentError) as exc:
        _fechar(operator, _encomenda(shift, qty=200))

    assert exc.value.code == "manager_approval_required"
    assert "200 pedidas, 22 planejadas" in exc.value.message
    assert "Só o gerente libera" in exc.value.message


def test_com_a_assinatura_do_gerente_fecha_e_assina(balcao, joyce, django_capture_on_commit_callbacks):  # noqa: F811
    from shopman.orderman.models import Order

    operator, shift = balcao
    _plano("22")
    payload = _encomenda(shift, qty=200)
    payload["manager_approval"] = _carimbo(joyce, operator, _review(operator, dict(payload)))

    with django_capture_on_commit_callbacks(execute=True):
        result = _fechar(operator, payload)

    assert Order.objects.filter(ref=result.order_ref).exists()


def test_a_assinatura_vale_so_para_os_numeros_que_o_gerente_viu(balcao, joyce):  # noqa: F811
    """Assinou 30 contra 22; a encomenda chegou com 200."""
    operator, shift = balcao
    _plano("22")
    assinada = _review(operator, _encomenda(shift, qty=30))
    payload = _encomenda(shift, qty=200)
    payload["manager_approval"] = _carimbo(joyce, operator, assinada)

    with pytest.raises(PosIntentError) as exc:
        _fechar(operator, payload)

    assert exc.value.code == "manager_approval_invalid"
    assert "30 pedidas, 22 planejadas" in exc.value.recovery
    assert "200 pedidas, 22 planejadas" in exc.value.recovery


def test_carimbo_de_desconto_nao_libera_encomenda_acima_do_plano(balcao, joyce):  # noqa: F811
    operator, shift = balcao
    _plano("22")
    payload = _encomenda(shift, qty=200)
    payload["manager_approval"] = {
        "token": issue_sale_approval(joyce, operator_username=operator.username, scope=SaleApprovalScope(tab_ref="")),
    }

    with pytest.raises(PosIntentError) as exc:
        _fechar(operator, payload)

    assert exc.value.code == "manager_approval_invalid"


def test_dentro_do_plano_fecha_sem_gerente(balcao, django_capture_on_commit_callbacks):  # noqa: F811
    operator, shift = balcao
    _plano("22")

    with django_capture_on_commit_callbacks(execute=True):
        result = _fechar(operator, _encomenda(shift, qty=20))

    assert result.order_ref


def test_o_escopo_do_dialogo_vem_do_corpo_do_pedido():
    """O diálogo manda as linhas como a review publicou; o carimbo as normaliza."""
    scope = SaleApprovalScope.from_request({
        "tab_ref": "",
        "over_plan": [{"sku": "CR", "date": "2026-11-17", "requested_qty": 200.0, "planned_qty": 22, "unclaimed_qty": "22"}],
    })
    assert scope.over_plan == (("2026-11-17", "CR", "200", "22", "22"),)


# ── Encomenda de outro dia não fica "Na retirada" ────────────────────────────


def test_encomenda_de_outro_dia_nao_fica_para_pagar_na_retirada(balcao):  # noqa: F811
    from shopman.guestman.models import Customer

    operator, shift = balcao
    _plano("22")
    Customer.objects.create(ref="MARIA", first_name="Maria", phone="+5543999990001")

    with pytest.raises(PosIntentError) as exc:
        _fechar(operator, _encomenda(
            shift, qty=2, sales_mode="order", customer_ref="MARIA", payment_collection="on_delivery",
        ))

    assert exc.value.code == "pay_at_pickup_other_day"
    assert exc.value.field == "payment_collection"


# ── A projeção do agendamento mostra o lastro ────────────────────────────────


def test_o_agendamento_devolve_planejado_e_livre_por_sku(balcao):  # noqa: F811
    from shopman.backstage.projections.pos import build_pos_schedule

    _plano("22")
    stock.hold(Decimal("5"), Product.objects.get(sku="CR"), target_date=_amanha(), reference="outra-encomenda")

    schedule = build_pos_schedule(delivery_date=_amanha().isoformat(), skus=["CR", "BF"])

    assert schedule["plan_by_sku"] == {"CR": {"planned_qty": 22, "unclaimed_qty": 17}}


def test_o_agendamento_nao_soma_a_sobra_de_hoje(balcao):  # noqa: F811
    from shopman.backstage.projections.pos import build_pos_schedule

    _plano("22")
    product = Product.objects.get(sku="CR")
    product.shelf_life_days = 1
    product.save(update_fields=["shelf_life_days"])
    stock.receive(quantity=Decimal("22"), sku="CR", position=Position.objects.get(ref="loja"), target_date=None, reason="sobra")

    assert build_pos_schedule(delivery_date=_amanha().isoformat(), skus=["CR"])["plan_by_sku"] == {
        "CR": {"planned_qty": 22, "unclaimed_qty": 22},
    }


def test_o_agendamento_de_hoje_nao_tem_lastro_de_encomenda(balcao):  # noqa: F811
    from shopman.backstage.projections.pos import build_pos_schedule

    _plano("22")

    assert build_pos_schedule(delivery_date="", skus=["CR"])["plan_by_sku"] == {}
