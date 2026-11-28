"""Desconto automático por GRUPO de clientes no PDV (decisão do dono, 14/10/2026).

O caso real: alunos da Aliança Francesa consumindo no balcão. Em vez de cupom, o
grupo tem desconto: o gestor cadastra no Admin (grupo, % ou valor, onde vale) e,
no PDV, identificar o cliente basta para o desconto entrar sozinho, com o nome
do grupo na linha e no cadastro, disputando com os outros automáticos pela regra
"maior desconto ganha" (não soma com a Xepa).

O motor já sabia fazer a conta (``Promotion.customer_segments`` casa a faixa do
cliente). O que faltava, e é o que estes testes travam:

- o Admin cadastrar o desconto no próprio grupo (antes: uma faixa num lugar e
  uma promoção noutro, ligadas por um JSON escrito à mão com o rótulo "Segmentos RFM");
- a venda SEM comanda (a venda comum do balcão) dizer à tela o que cada linha
  cobra: o Subtotal caía para R$ 10,80 e a linha seguia dizendo R$ 12,00;
- o cadastro do cliente no PDV dizer que o desconto vai entrar.
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.guestman.models import Customer, PriceTier
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_pos_customer_lookup_by_ref
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Promotion, RuleConfig, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

pytestmark = pytest.mark.django_db

SAVE_URL = "/api/v1/backstage/pos/tabs/save/"
REVIEW_URL = "/api/v1/backstage/pos/sale/review/"
BRT = ZoneInfo("America/Sao_Paulo")


def _group_discount(*, value: int = 10, channels: tuple[str, ...] = ("pdv",)) -> Promotion:
    promo = Promotion.objects.create(
        ref="grupo-alianca-francesa",
        name="Aliança Francesa",
        type=Promotion.PERCENT,
        value=value,
        valid_from=timezone.now() - timezone.timedelta(days=1),
        valid_until=timezone.now() + timezone.timedelta(days=365),
        customer_segments=["alianca-francesa"],
    )
    promo.channels.set(Channel.objects.filter(ref__in=channels))
    return promo


@pytest.fixture
def balcao(client):
    cache.clear()
    Shop.objects.create(name="Nelson", brand_name="Nelson")
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
    Channel.objects.create(ref="web", name="Loja", is_active=True, config={})
    POSTab.objects.create(ref="00000077", label="77")
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    product = Product.objects.create(sku="CAFE", name="Café", base_price_q=800, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=listing, product=product, price_q=800)
    operator = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    shift = cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    tier = PriceTier.objects.create(
        ref="alianca-francesa",
        name="Aliança Francesa",
        metadata={
            "discount_kind": "parceiro",
            "rounding": 50,
            "savings_message": "Hoje você economizou {amount} por ser da Aliança Francesa",
        },
    )
    aluno = Customer.objects.create(ref="ALUNO", first_name="Louise", phone="+5543999990010", price_tiers=tier)
    yield {"client": client, "shift": shift, "aluno": aluno, "tier": tier}
    cache.clear()


def _items(**line) -> list[dict]:
    return [{"line_id": "L1", "sku": "CAFE", "name": "Café", "qty": 2, "unit_price_q": 800, **line}]


def _review(client, **overrides):
    body = {
        "intent_version": POS_SALE_INTENT_VERSION,
        "items": _items(),
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": "grupo-review",
        **overrides,
    }
    return client.post(REVIEW_URL, data=json.dumps(body), content_type="application/json")


# ── A venda comum do balcão: sem comanda ────────────────────────────────────


def test_aluno_identificado_ganha_o_desconto_e_a_linha_diz_qual(balcao):
    _group_discount()

    response = _review(balcao["client"], customer_ref="ALUNO", customer_phone="43999990010", customer_name="Louise")

    assert response.status_code == 200, response.content
    review = response.json()["review"]
    # 800 − 10% = 720 → arredonda para R$ 7,00 (o R$ 0,50 mais próximo).
    assert review["total_q"] == 1400  # 2 x R$ 7,00
    # O desconto do grupo não é desconto do operador: não pede gerente.
    assert review["discount_q"] == 0
    assert review["line_prices"]["L1"] == {
        "charged_price_q": 700,
        "list_price_q": 800,
        # O percentual não fecha limpo (100/800 = 12,5%): a tela mostra o R$.
        "pricing_discount": {"type": "promotion", "label": "Aliança Francesa", "amount_q": 100, "percent": 0},
        "manual_discount_discarded": False,
    }


def test_sem_cliente_a_linha_volta_ao_preco_cheio_e_sem_rotulo(balcao):
    _group_discount()

    review = _review(balcao["client"]).json()["review"]

    assert review["total_q"] == 1600
    assert review["line_prices"]["L1"] == {
        "charged_price_q": 800, "list_price_q": 800, "pricing_discount": None, "manual_discount_discarded": False,
    }


def test_cliente_de_outro_grupo_nao_ganha(balcao):
    _group_discount()
    Customer.objects.create(ref="VIZINHO", first_name="Ana", phone="+5543999990011")

    review = _review(balcao["client"], customer_ref="VIZINHO", customer_phone="43999990011").json()["review"]

    assert review["total_q"] == 1600
    assert review["line_prices"]["L1"]["pricing_discount"] is None


def test_desconto_so_da_loja_nao_entra_no_balcao(balcao):
    _group_discount(channels=("web",))

    review = _review(balcao["client"], customer_ref="ALUNO", customer_phone="43999990010").json()["review"]

    assert review["total_q"] == 1600


def test_cortesia_maior_que_o_desconto_do_grupo_vence_a_linha_sem_somar(balcao):
    _group_discount()

    review = _review(
        balcao["client"],
        customer_ref="ALUNO",
        customer_phone="43999990010",
        items=_items(discount={"type": "percent", "value": 50, "reason": "cortesia"}),
    ).json()["review"]

    # 50% de R$ 8,00 = R$ 4,00 por unidade; os 10% do grupo saem da linha (não somam).
    assert review["line_prices"]["L1"] == {
        "charged_price_q": 400, "list_price_q": 800, "pricing_discount": None, "manual_discount_discarded": False,
    }
    assert review["total_q"] == 800


def test_comanda_com_o_aluno_mostra_o_desconto_no_eco_do_salvar(balcao):
    _group_discount()
    session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref="77", actor="test", operator_username="marina")
    from shopman.backstage.projections.pos import build_open_tab

    body = {
        "intent_version": POS_SALE_INTENT_VERSION,
        "tab_ref": "77",
        "tab_session_key": session.session_key,
        "expected_revision": build_open_tab(session)["revision"],
        "items": _items(),
        "customer_ref": "ALUNO",
        "customer_phone": "43999990010",
        "customer_name": "Louise",
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": "grupo-comanda",
    }
    saved = balcao["client"].post(SAVE_URL, data=json.dumps(body), content_type="application/json")

    assert saved.status_code == 200, saved.content
    assert saved.json()["line_prices"]["L1"]["pricing_discount"]["label"] == "Aliança Francesa"
    assert saved.json()["line_prices"]["L1"]["charged_price_q"] == 700


# ── O pedido guarda o desconto, para medir depois ───────────────────────────


def test_o_pedido_registra_o_desconto_do_grupo(balcao):
    _group_discount()

    payload = {
        "items": _items(),
        "customer_ref": "ALUNO",
        "customer_phone": "43999990010",
        "customer_name": "Louise",
        "payment_method": "cash",
        "client_request_id": "grupo-fechar",
        "cash_shift_id": balcao["shift"].pk,
    }
    review = pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username="marina")
    payload["expected_total_q"] = review.total_q
    result = pos_service.close_sale(
        channel_ref="pdv",
        payload=payload,
        actor="pos:marina",
        operator_username="marina",
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1400
    (record,) = order.snapshot["pricing"]["discount"]["items"]
    assert record["type"] == "promotion"
    assert record["name"] == "Aliança Francesa"
    assert record["discount_q"] == 100
    # O tipo do desconto vai para o B.I. ler desconto por tipo.
    assert record["discount_kind"] == "parceiro"
    assert order.data["customer"]["price_tier"] == "alianca-francesa"
    # E a economia do grupo, com o texto do grupo, no snapshot imutável.
    savings = order.snapshot["pricing"]["discount"]["savings"]
    assert savings["amount_q"] == 200
    assert savings["group"] == "Aliança Francesa"
    assert savings["kind"] == "parceiro"
    assert savings["message"] == "Hoje você economizou R$ 2,00 por ser da Aliança Francesa"


# ── Maior desconto ganha: não soma com a Xepa ───────────────────────────────


def test_na_xepa_o_maior_desconto_ganha_e_nao_soma(balcao):
    _group_discount()
    xepa = RuleConfig.objects.create(
        ref="happy_hour", rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Hora da Xepa", params={"discount_percent": 40, "start": "17:00", "end": "18:00"}, enabled=True,
    )
    # A Xepa só vale nos canais listados (sem canal, em lugar nenhum).
    xepa.channels.add(Channel.objects.get(ref="pdv"))
    cache.clear()

    with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 14, 17, 30, tzinfo=BRT)):
        review = pos_service.review_sale(
            channel_ref="pdv",
            payload={
                "items": _items(),
                "customer_ref": "ALUNO",
                "customer_phone": "43999990010",
                "payment_method": "cash",
            },
            operator_username="marina",
        )

    # 40% da Xepa vence os 10% do grupo: R$ 4,80 cada, nunca R$ 4,32 (40% sobre os 10%).
    assert review.total_q == 960
    (line,) = review.priced_lines
    assert line["unit_price_q"] == 480
    assert line["meta"]["_disc"]["type"] == "happy_hour"


# ── O cadastro do cliente no PDV avisa que o desconto vai entrar ────────────


def test_o_cadastro_do_aluno_no_pdv_nomeia_o_desconto(balcao):
    _group_discount()

    lookup = build_pos_customer_lookup_by_ref("ALUNO")

    assert lookup.group_discount_label == "Aliança Francesa · 10%"


def test_o_cadastro_nao_promete_desconto_que_nao_vale_no_balcao(balcao):
    _group_discount(channels=("web",))

    assert build_pos_customer_lookup_by_ref("ALUNO").group_discount_label == ""


def test_desconto_pausado_nao_e_prometido(balcao):
    promo = _group_discount()
    promo.is_active = False
    promo.save(update_fields=["is_active"])

    assert build_pos_customer_lookup_by_ref("ALUNO").group_discount_label == ""


# ── O Admin: o grupo, o desconto e onde vale, num lugar só ──────────────────


@pytest.fixture
def gestor(client, balcao):
    user = get_user_model().objects.create_superuser("gestor", "gestor@test.com", "x")
    client.force_login(user)
    return client


def _tier_form(**overrides) -> dict:
    return {
        "name": "Aliança Francesa",
        "ref": "alianca-francesa",
        "description": "",
        "listing_ref": "",
        "priority": "0",
        "metadata": "{}",
        "group_discount_type": "percent",
        "group_discount_value": "10",
        "group_discount_channels": [str(Channel.objects.get(ref="pdv").pk)],
        "group_rounding": "on",
        # Formset das vantagens tipadas (inline): sem o management form o Admin
        # rejeita o POST inteiro, mesmo sem nenhuma vantagem marcada.
        "advantages-TOTAL_FORMS": "0",
        "advantages-INITIAL_FORMS": "0",
        "advantages-MIN_NUM_FORMS": "0",
        "advantages-MAX_NUM_FORMS": "1000",
        **overrides,
    }


def _errors(response) -> str:
    form = response.context["adminform"].form if response.context else None
    return str(form.errors) if form is not None else str(response.status_code)


def test_admin_cadastra_o_grupo_com_desconto_no_balcao(gestor):
    response = gestor.post(
        reverse("admin:guestman_pricetier_add"), _tier_form(name="Cultura Inglesa", ref="cultura-inglesa"),
    )

    assert response.status_code == 302, _errors(response)
    promo = Promotion.objects.get(ref="grupo-cultura-inglesa")
    assert promo.name == "Cultura Inglesa"
    assert promo.type == Promotion.PERCENT
    assert promo.value == 10
    assert promo.customer_segments == ["cultura-inglesa"]
    assert [c.ref for c in promo.channels.all()] == ["pdv"]
    assert promo.is_active
    assert promo.valid_from <= timezone.now() <= promo.valid_until


def test_admin_grava_tipo_arredondamento_e_mensagem_do_grupo(gestor):
    """As chaves do grupo (B.I., arredondamento, economia e retirada) vão ao metadata."""
    response = gestor.post(
        reverse("admin:guestman_pricetier_add"),
        _tier_form(
            name="Equipe",
            ref="staff",
            group_discount_type="percent",
            group_discount_value="30",
            group_pickup_only="on",
            group_discount_kind="equipe",
            group_savings_message="Hoje você economizou {amount} por ser da Equipe",
        ),
    )

    assert response.status_code == 302, _errors(response)
    tier = PriceTier.objects.get(ref="staff")
    assert tier.metadata["discount_kind"] == "equipe"
    assert tier.metadata["rounding"] == 50
    assert tier.metadata["savings_message"] == "Hoje você economizou {amount} por ser da Equipe"
    promo = Promotion.objects.get(ref="grupo-staff")
    assert promo.fulfillment_types == ["pickup"]


def test_admin_desconto_em_reais_por_pedido(gestor):
    tier = PriceTier.objects.get(ref="alianca-francesa")

    response = gestor.post(
        reverse("admin:guestman_pricetier_change", args=[tier.pk]),
        _tier_form(group_discount_type="fixed", group_discount_value="2,50"),
    )

    assert response.status_code == 302, _errors(response)
    promo = Promotion.objects.get(ref="grupo-alianca-francesa")
    assert (promo.type, promo.value) == (Promotion.FIXED, 250)


def test_admin_sem_desconto_pausa_a_promocao_do_grupo(gestor):
    tier = PriceTier.objects.get(ref="alianca-francesa")
    _group_discount()

    response = gestor.post(
        reverse("admin:guestman_pricetier_change", args=[tier.pk]),
        _tier_form(group_discount_type="", group_discount_value=""),
    )

    assert response.status_code == 302, _errors(response)
    assert not Promotion.objects.get(ref="grupo-alianca-francesa").is_active
    assert build_pos_customer_lookup_by_ref("ALUNO").group_discount_label == ""


def test_admin_recusa_percentual_acima_de_100(gestor):
    tier = PriceTier.objects.get(ref="alianca-francesa")

    response = gestor.post(
        reverse("admin:guestman_pricetier_change", args=[tier.pk]),
        _tier_form(group_discount_value="150"),
    )

    assert response.status_code == 200
    assert not Promotion.objects.filter(ref="grupo-alianca-francesa").exists()


def test_admin_novo_grupo_vem_marcado_para_o_balcao(gestor):
    response = gestor.get(reverse("admin:guestman_pricetier_add"))

    assert response.status_code == 200
    form = response.context["adminform"].form
    assert [c.ref for c in form.fields["group_discount_channels"].initial] == ["pdv"]


def test_admin_lista_mostra_o_desconto_do_grupo(gestor):
    _group_discount()

    response = gestor.get(reverse("admin:guestman_pricetier_changelist"))

    assert response.status_code == 200
    assert "10%" in response.content.decode()
