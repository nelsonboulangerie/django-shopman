"""OC-22: o pedido sabe de qual versão da loja veio.

A sacola grava ``Session.data["experience"]`` em toda escrita (e no login com a
sacola aberta), com o que ``shop.services.experience`` resolveu para o cliente; o
``CommitService`` copia a chave para ``Order.data``. Decisão do padrão: a chave só
existe quando há experimento valendo, e então grava também o braço padrão ("a"):
a métrica de pedido separa "sem experimento" (ausente) de "viu o padrão".

Nenhuma leitura grava nada: a marca nasce nas escritas da sacola, que são comandos
(``test_read_side_never_writes`` segue valendo).
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from shopman.orderman.models import Order, Session

from shopman.shop.models import RuleConfig
from shopman.shop.policies.experience import EXPERIENCE_RULE_PATH
from shopman.storefront.tests._checkout_baseline import with_baseline

from . import _journey as J

pytestmark = pytest.mark.django_db

SKU = "PAO-VERSAO"
REF = "para-quando"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _seed():
    J.seed_shop()
    J.seed_web_channel(allow_cash=True)
    collection = J.seed_collection()
    J.seed_product(SKU, "Pão da Versão", 90, collection=collection, stock_qty=20)


def _experiment(*, internal=(), generation: int = 1, environments=None) -> RuleConfig:
    params = {
        "ref": REF,
        "surface": "storefront",
        "variants": ["a", "b"],
        "default": "a",
        "cohorts": {"internal": list(internal)},
        "allocation": {"b": 0},
        "owner": "Engenharia",
        "hypothesis": "Perguntar o dia antes da lista reduz a sacola recusada.",
        "metrics": ["sacola_recusada"],
        "remove_after": (timezone.localdate() + timedelta(days=30)).isoformat(),
        "generation": generation,
    }
    if environments is not None:
        params["environments"] = environments
    return RuleConfig.objects.create(
        ref=f"experience.{REF}",
        rule_path=EXPERIENCE_RULE_PATH,
        label="Para quando primeiro",
        params=params,
    )


def _cart_session(client) -> Session:
    return Session.objects.get(session_key=client.session["cart_session_key"])


def _order(client, **checkout) -> Order:
    status, body = J.checkout(client, payment_method="cash", **checkout)
    assert status == 201, body
    return Order.objects.get(ref=body["order_ref"])


def test_pedido_da_coorte_b_sabe_que_veio_da_versao_b(client):
    _seed()
    customer = J.make_customer(ref="CLI-VERSAO-B")
    _experiment(internal=[customer.ref])
    J.authenticate(client, customer)

    status, body = J.set_cart_qty(client, SKU, 2)
    assert status == 200, body
    mark = {REF: {"variant": "b", "generation": 1}}
    assert _cart_session(client).data["experience"] == mark

    order = _order(client)
    assert order.data["experience"] == mark


def test_pedido_fora_da_coorte_sabe_que_veio_do_padrao(client):
    """Experimento valendo e cliente fora da coorte: o pedido diz "a", não omite."""
    _seed()
    customer = J.make_customer(ref="CLI-VERSAO-A")
    _experiment(internal=["CLI-OUTRA"])
    J.authenticate(client, customer)

    J.set_cart_qty(client, SKU, 1)
    order = _order(client)
    assert order.data["experience"] == {REF: {"variant": "a", "generation": 1}}


def test_sem_experimento_o_pedido_nao_leva_a_chave(client):
    _seed()
    J.authenticate(client, J.make_customer(ref="CLI-SEM-EXP"))

    J.set_cart_qty(client, SKU, 1)
    assert "experience" not in _cart_session(client).data
    assert "experience" not in _order(client).data


def test_experimento_de_outro_ambiente_nao_marca_o_pedido(client):
    """Ali não há experimento: o pedido não engrossa o braço padrão."""
    _seed()
    customer = J.make_customer(ref="CLI-OUTRO-AMBIENTE")
    _experiment(internal=[customer.ref], environments=["production"])
    J.authenticate(client, customer)

    J.set_cart_qty(client, SKU, 1)
    assert "experience" not in _cart_session(client).data


def test_experimento_vencido_nao_marca_o_pedido(client):
    _seed()
    customer = J.make_customer(ref="CLI-VENCIDO")
    rule = _experiment(internal=[customer.ref])
    # O prazo venceu depois de criado (o ``clean`` não aceita prazo passado).
    params = {**rule.params, "remove_after": (timezone.localdate() - timedelta(days=1)).isoformat()}
    RuleConfig.objects.filter(pk=rule.pk).update(params=params)
    cache.clear()
    J.authenticate(client, customer)

    J.set_cart_qty(client, SKU, 1)
    assert "experience" not in _cart_session(client).data


def test_quem_entra_com_a_sacola_anonima_leva_a_versao_de_quem_entrou(client):
    """Sacola montada anônima, login na coorte B, Finalizar sem mexer na sacola."""
    _seed()
    customer = J.make_customer(ref="CLI-ENTRA-B")
    _experiment(internal=[customer.ref])

    J.set_cart_qty(client, SKU, 1)
    assert _cart_session(client).data["experience"] == {REF: {"variant": "a", "generation": 1}}

    J.authenticate(client, customer)
    assert _cart_session(client).data["experience"] == {REF: {"variant": "b", "generation": 1}}
    assert _order(client).data["experience"] == {REF: {"variant": "b", "generation": 1}}


def test_experimento_desligado_sai_da_sacola_na_proxima_escrita(client):
    _seed()
    customer = J.make_customer(ref="CLI-DESLIGA")
    rule = _experiment(internal=[customer.ref])
    J.authenticate(client, customer)
    J.set_cart_qty(client, SKU, 1)
    assert _cart_session(client).data["experience"][REF]["variant"] == "b"

    rule.enabled = False
    rule.save()
    J.set_cart_qty(client, SKU, 2)
    assert "experience" not in _cart_session(client).data
    assert "experience" not in _order(client).data


def test_ler_a_sacola_e_o_checkout_nao_grava_a_marca(client):
    """A marca nasce na escrita; GET da sacola, do shell e do checkout não a criam."""
    _seed()
    customer = J.make_customer(ref="CLI-LEITURA")
    J.authenticate(client, customer)
    J.set_cart_qty(client, SKU, 1)
    assert "experience" not in _cart_session(client).data

    _experiment(internal=[customer.ref])
    for url in ("/api/v1/storefront/cart/", "/api/v1/storefront/shell/", "/api/v1/storefront/checkout/"):
        assert client.get(url).status_code == 200
    assert "experience" not in _cart_session(client).data


def test_a_marca_sobrevive_ao_commit_repetido(client):
    """O mesmo Finalizar duas vezes (mesma chave) devolve o mesmo pedido, ainda marcado."""
    _seed()
    customer = J.make_customer(ref="CLI-REPLAY")
    _experiment(internal=[customer.ref])
    J.authenticate(client, customer)
    J.set_cart_qty(client, SKU, 1)

    payload = with_baseline(client, {
        "name": "Ana Silva",
        "phone": J.DEFAULT_PHONE,
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_time_slot": J.today_pickup_slot(),
        "idempotency_key": "oc22-replay",
    })

    def post():
        resp = client.post("/api/v1/checkout/", data=json.dumps(payload), content_type="application/json")
        return resp.status_code, resp.json()

    first_status, first = post()
    assert first_status == 201, first
    replay_status, replay = post()
    assert replay_status in (200, 201), replay
    assert replay["order_ref"] == first["order_ref"]
    assert Order.objects.filter(ref=first["order_ref"]).count() == 1
    assert Order.objects.get(ref=first["order_ref"]).data["experience"] == {
        REF: {"variant": "b", "generation": 1}
    }
