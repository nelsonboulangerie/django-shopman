"""O salvar da comanda devolve o preço que cada linha COBRA.

Relato do dono (13/10/2026, no alpha): deu R$ 1,00 de desconto numa linha do PDV
e o total da linha só mudou quando recarregou a página. O desconto manual muda o
preço no SERVIDOR (``DiscountModifier``), e a gravação silenciosa da comanda só
devolvia revisão e autoria: a tela continuava com o ``charged_price_q`` velho até
reabrir a comanda. Este arquivo trava o eco: cada gravação diz, por linha, o que
ela cobra, com os mesmos números que a comanda reaberta mostraria.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Promotion, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

pytestmark = pytest.mark.django_db

SAVE_URL = "/api/v1/backstage/pos/tabs/save/"
REVIEW_URL = "/api/v1/backstage/pos/sale/review/"


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
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
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref="77", actor="test", operator_username="marina")
    return {"client": client, "session": session}


def _intent(session, *, discount: dict | None, revision: str) -> dict:
    return {
        "intent_version": POS_SALE_INTENT_VERSION,
        "tab_ref": "77",
        "tab_session_key": session.session_key,
        "expected_revision": revision,
        "items": [
            {
                "line_id": "L1",
                "sku": "CAFE",
                "name": "Café",
                "qty": 3,
                "unit_price_q": 800,
                **({"discount": discount} if discount else {}),
            }
        ],
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": "desconto-linha-eco",
    }


def _save(client, body: dict):
    return client.post(SAVE_URL, data=json.dumps(body), content_type="application/json")


def test_o_salvar_devolve_o_preco_cobrado_da_linha_com_o_desconto_em_reais(balcao):
    client, session = balcao["client"], balcao["session"]
    first = _save(client, _intent(session, discount=None, revision=build_open_tab(session)["revision"]))
    assert first.status_code == 200, first.content
    assert first.json()["line_prices"]["L1"]["charged_price_q"] == 800

    saved = _save(
        client,
        _intent(
            session,
            discount={"type": "fixed", "value": 1, "reason": "cortesia"},
            revision=first.json()["revision"],
        ),
    )

    assert saved.status_code == 200, saved.content
    eco = saved.json()["line_prices"]["L1"]
    # R$ 1,00 por unidade: a linha de 3 cafés cobra R$ 7,00 cada, R$ 21,00 no total.
    assert eco["charged_price_q"] == 700
    assert eco["list_price_q"] == 800
    session.refresh_from_db()
    reaberta = {item["line_id"]: item for item in build_open_tab(session)["items"]}
    assert eco == {
        key: reaberta["L1"][key]
        for key in ("charged_price_q", "list_price_q", "pricing_discount", "manual_discount_discarded")
    }
    assert eco["manual_discount_discarded"] is False


# ── O descarte do desconto manual vem do MOTOR (laudo de soberania, A3-1) ────
#
# A tela adivinhava se o desconto do operador tinha perdido para o automático da
# linha, com a régua dela. Agora o eco diz: `manual_discount_discarded`, lido do
# carimbo que o motor deixou na linha. E a revisão da comanda devolve o preço das
# linhas com desconto manual, para a prévia do editor e o total da linha não
# esperarem a próxima gravação.


def _semana_do_cafe(percent: int = 15) -> Promotion:
    promo = Promotion.objects.create(
        ref="semana-do-cafe",
        name="Semana do Café",
        type=Promotion.PERCENT,
        value=percent,
        valid_from=timezone.now() - timezone.timedelta(days=1),
        valid_until=timezone.now() + timezone.timedelta(days=30),
    )
    promo.channels.set(Channel.objects.filter(ref="pdv"))
    return promo


def _review(client, body: dict):
    return client.post(REVIEW_URL, data=json.dumps(body), content_type="application/json")


def test_cortesia_menor_que_o_automatico_volta_descartada_no_eco_do_salvar(balcao):
    client, session = balcao["client"], balcao["session"]
    _semana_do_cafe()

    saved = _save(
        client,
        _intent(
            session,
            discount={"type": "percent", "value": 10, "reason": "cortesia"},
            revision=build_open_tab(session)["revision"],
        ),
    )

    assert saved.status_code == 200, saved.content
    eco = saved.json()["line_prices"]["L1"]
    # 15% de R$ 8,00 = R$ 1,20 vence os 10% (R$ 0,80): a linha cobra R$ 6,80.
    assert eco["charged_price_q"] == 680
    assert eco["pricing_discount"]["label"] == "Semana do Café"
    assert eco["manual_discount_discarded"] is True


def test_cortesia_em_reais_maior_que_o_automatico_vale(balcao):
    """R$ 2,50 contra −15% (R$ 1,20): a régua velha da tela dizia que perdia."""
    client, session = balcao["client"], balcao["session"]
    _semana_do_cafe()

    saved = _save(
        client,
        _intent(
            session,
            discount={"type": "fixed", "value": 2.5, "reason": "cortesia"},
            revision=build_open_tab(session)["revision"],
        ),
    )

    eco = saved.json()["line_prices"]["L1"]
    assert eco["charged_price_q"] == 550
    assert eco["pricing_discount"] is None
    assert eco["manual_discount_discarded"] is False


def test_a_revisao_da_comanda_responde_pela_linha_com_desconto_antes_de_gravar(balcao):
    """A prévia do editor e o total da linha perguntam à revisão, não à próxima gravação."""
    client, session = balcao["client"], balcao["session"]
    _semana_do_cafe()
    first = _save(client, _intent(session, discount=None, revision=build_open_tab(session)["revision"]))
    revision = first.json()["revision"]

    sem_desconto = _review(client, _intent(session, discount=None, revision=revision))
    assert sem_desconto.status_code == 200, sem_desconto.content
    # Sem desconto manual, quem responde pela linha da comanda é o salvar.
    assert sem_desconto.json()["review"]["line_prices"] == {}

    perde = _review(
        client, _intent(session, discount={"type": "percent", "value": 10, "reason": "cortesia"}, revision=revision),
    ).json()["review"]
    assert perde["line_prices"]["L1"]["charged_price_q"] == 680
    assert perde["line_prices"]["L1"]["manual_discount_discarded"] is True
    assert perde["total_q"] == 3 * 680

    vale = _review(
        client, _intent(session, discount={"type": "percent", "value": 50, "reason": "cortesia"}, revision=revision),
    ).json()["review"]
    assert vale["line_prices"]["L1"] == {
        "charged_price_q": 400, "list_price_q": 800, "pricing_discount": None, "manual_discount_discarded": False,
    }
    assert vale["total_q"] == 3 * 400


def test_venda_sem_comanda_tambem_diz_o_descarte(balcao):
    client = balcao["client"]
    _semana_do_cafe()
    body = {
        "intent_version": POS_SALE_INTENT_VERSION,
        "items": [{
            "line_id": "L1", "sku": "CAFE", "name": "Café", "qty": 1, "unit_price_q": 800,
            "discount": {"type": "fixed", "value": 0.5, "reason": "cortesia"},
        }],
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": "descarte-sem-comanda",
    }

    review = _review(client, body).json()["review"]

    assert review["line_prices"]["L1"]["charged_price_q"] == 680
    assert review["line_prices"]["L1"]["manual_discount_discarded"] is True
