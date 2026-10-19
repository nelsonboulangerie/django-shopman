"""Frete grátis do GRUPO do cliente: a vantagem que a tela do Gestor promete, cobrada pelo motor.

Medido em 19/10/2026: o Gestor gravava ``PriceTierAdvantage(kind="free_shipping")``
com ``min_order_q`` e nenhum consumidor lia; a loja e o balcão cobravam a taxa do
membro do grupo. Agora a vantagem é a terceira política do MESMO motor de renúncia
(``modifiers.resolve_delivery_fee_waiver``), junto do limiar da loja e da promoção:
vence a que mais renuncia, nada acumula, e o ``min_order_q`` do grupo é respeitado.

Cliente em dois grupos com frete grátis: vale o de MENOR pedido mínimo (o melhor
para o cliente, regra do dono de 14/10).
"""

from __future__ import annotations

import pytest
from shopman.guestman.models import Customer, PriceTier, PriceTierAdvantage
from shopman.offerman.models import Product
from shopman.orderman.models import Order

from shopman.shop.models import Channel, DeliveryZone, Shop
from shopman.shop.modifiers import resolve_delivery_fee_waiver
from shopman.shop.policies.group_advantage import free_shipping_minimum_q
from shopman.shop.projections.cart import build_cart
from shopman.shop.services import pos as pos_service
from shopman.shop.services import promotions, sessions
from shopman.shop.tests.test_pos_change_for_delivery import _close, _delivery_payload, counter  # noqa: F401

pytestmark = pytest.mark.django_db

FEE_Q = 800


def _group(ref: str, name: str, *, min_order_q: int | None = 0, active: bool = True, priority: int = 0):
    tier = PriceTier.objects.create(ref=ref, name=name, priority=priority)
    if min_order_q is not None:
        PriceTierAdvantage.objects.create(
            tier=tier, kind=PriceTierAdvantage.Kind.FREE_SHIPPING, is_active=active,
            config={"min_order_q": min_order_q},
        )
    return tier


def _member(ref: str, phone: str, *tiers):
    customer = Customer.objects.create(ref=ref, first_name=ref, phone=phone)
    customer.price_tiers.set(tiers)
    return customer


# ── o resolvedor ─────────────────────────────────────────────────────────────


def test_dois_grupos_com_frete_gratis_vale_o_menor_minimo():
    _group("equipe", "Equipe", min_order_q=5000, priority=10)
    _group("alianca", "Aliança Francesa", min_order_q=2000)

    best = promotions.best_group_advantage(["equipe", "alianca"], "free_shipping")

    assert best.tier_ref == "alianca"
    assert free_shipping_minimum_q(best.value.config) == 2000


def test_vantagem_desligada_nao_vale():
    _group("alianca", "Aliança Francesa", active=False)
    assert promotions.best_group_advantage(["alianca"], "free_shipping") is None


def test_o_motor_respeita_o_minimo_do_grupo_e_diz_o_grupo():
    _group("alianca", "Aliança Francesa", min_order_q=3000)

    below = resolve_delivery_fee_waiver(FEE_Q, merchandise_q=2999, channel_ref="web", price_tier_refs=["alianca"])
    at = resolve_delivery_fee_waiver(FEE_Q, merchandise_q=3000, channel_ref="web", price_tier_refs=["alianca"])

    assert below.fee_q == FEE_Q and below.reason == ""
    assert (at.fee_q, at.reason, at.group_name, at.threshold_q) == (0, "group", "Aliança Francesa", 3000)


def test_sem_grupo_o_motor_nao_consulta_a_vantagem(django_assert_num_queries):
    with django_assert_num_queries(1):  # só o Shop do limiar; lista vazia não pergunta ao banco
        resolve_delivery_fee_waiver(FEE_Q, merchandise_q=9999, channel_ref="", price_tier_refs=[])


def test_balcao_pdv_sem_cliente_nao_procura_grupo(django_assert_num_queries):
    with django_assert_num_queries(1):
        resolve_delivery_fee_waiver(FEE_Q, merchandise_q=9999, channel_ref="")


# ── a loja online ────────────────────────────────────────────────────────────


@pytest.fixture
def loja():
    shop = Shop.objects.create(name="Loja")
    DeliveryZone.objects.create(
        shop=shop, name="Centro", zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX, match_value="860", fee_q=FEE_Q,
    )
    Channel.objects.create(ref="web", name="Loja online")
    Product.objects.create(sku="PAO", name="Pão", base_price_q=2000, is_published=True, is_sellable=True)
    return shop


def _delivery_cart(customer=None, *, qty: int = 1):
    session = sessions.create_session("web")
    ops = [
        {"op": "add_line", "sku": "PAO", "name": "Pão", "qty": qty, "unit_price_q": 2000},
        {"op": "set_data", "path": "fulfillment_type", "value": "delivery"},
        {"op": "set_data", "path": "delivery_address", "value": "Rua das Flores, 1"},
        {"op": "set_data", "path": "delivery_address_structured",
         "value": {"postal_code": "86050-270", "neighborhood": "Centro"}},
    ]
    if customer is not None:
        ops.append({"op": "set_data", "path": "customer", "value": {
            "ref": customer.ref, "price_tiers": [t.ref for t in customer.price_tiers.all()],
        }})
    sessions.modify_session(session_key=session.session_key, channel_ref="web", ops=ops)
    session.refresh_from_db()
    return session


def _fee_q(session) -> int:
    return int((session.data or {}).get("delivery_fee_q") or 0)


def _fee_lines(session) -> list:
    return [i for i in (session.items or []) if i.get("sku") == "__DELIVERY_FEE__"]


def test_loja_membro_do_grupo_nao_paga_a_entrega(loja):
    ana = _member("CLI-ANA", "+5543999990001", _group("alianca", "Aliança Francesa"))

    session = _delivery_cart(ana)

    assert _fee_q(session) == 0
    assert _fee_lines(session) == []


def test_loja_quem_nao_e_do_grupo_paga(loja):
    _group("alianca", "Aliança Francesa")
    beto = _member("CLI-BETO", "+5543999990002")

    assert _fee_q(_delivery_cart(beto)) == FEE_Q
    assert _fee_q(_delivery_cart()) == FEE_Q


def test_loja_minimo_do_grupo_e_respeitado(loja):
    ana = _member("CLI-ANA", "+5543999990001", _group("alianca", "Aliança Francesa", min_order_q=5000))

    assert _fee_q(_delivery_cart(ana, qty=2)) == FEE_Q  # R$ 40,00
    assert _fee_q(_delivery_cart(ana, qty=3)) == 0  # R$ 60,00


def test_loja_a_barra_de_frete_gratis_mede_contra_o_minimo_do_grupo(loja):
    loja.defaults = {"rules": {"free_delivery_above_q": 15000}}
    loja.save(update_fields=["defaults"])
    ana = _member("CLI-ANA", "+5543999990001", _group("alianca", "Aliança Francesa", min_order_q=5000))

    progress = build_cart(_delivery_cart(ana, qty=2).session_key, channel_ref="web").free_delivery

    assert progress.threshold_q == 5000
    assert progress.remaining_q == 1000


# ── o balcão (PDV) ───────────────────────────────────────────────────────────

ENDERECO = {
    "formatted_address": "Rua Pará, 86 - Centro, Londrina - PR",
    "postal_code": "86010-000",
    "neighborhood": "Centro",
}


@pytest.fixture
def balcao(counter):  # noqa: F811
    DeliveryZone.objects.create(
        shop=Shop.objects.get(), name="Centro", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_OVERRIDE, fee_q=FEE_Q, is_active=True,
    )
    return counter


def _payload(shift, request_id, **overrides):
    return _delivery_payload(
        shift, client_request_id=request_id, delivery_address=ENDERECO["formatted_address"],
        delivery_address_structured=dict(ENDERECO), **overrides,
    )


def _review(operator, payload):
    return pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username)


def test_balcao_membro_do_grupo_nao_paga_e_a_revisao_diz_o_grupo(balcao):
    operator, shift = balcao
    _member("CLI-ANA", "+5543999990001", _group("alianca", "Aliança Francesa"))

    review = _review(operator, _payload(shift, "fgg-1", customer_ref="CLI-ANA"))

    assert review.delivery_fee_q == 0
    assert review.delivery_fee_waiver == {
        "reason": "group", "promotion_name": "", "threshold_q": 0, "base_fee_q": FEE_Q,
        "group_name": "Aliança Francesa",
    }


def test_balcao_pedido_fecha_sem_linha_de_taxa(balcao):
    operator, shift = balcao
    _member("CLI-ANA", "+5543999990001", _group("alianca", "Aliança Francesa"))

    result = _close(operator, _payload(shift, "fgg-2", customer_ref="CLI-ANA"))

    order = Order.objects.get(ref=result.order_ref)
    assert [i for i in order.items.all() if i.sku == "__DELIVERY_FEE__"] == []
    assert order.total_q == 1200


def test_balcao_minimo_do_grupo_e_respeitado_e_quem_nao_e_do_grupo_paga(balcao):
    operator, shift = balcao
    tier = _group("alianca", "Aliança Francesa", min_order_q=5000)
    _member("CLI-ANA", "+5543999990001", tier)
    _member("CLI-BETO", "+5543999990002")

    assert _review(operator, _payload(shift, "fgg-3", customer_ref="CLI-ANA")).delivery_fee_q == FEE_Q
    assert _review(operator, _payload(shift, "fgg-4", customer_ref="CLI-BETO")).delivery_fee_q == FEE_Q
    assert _review(operator, _payload(shift, "fgg-5")).delivery_fee_q == FEE_Q
