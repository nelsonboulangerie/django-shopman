"""As recusas do envio falam a língua da loja, nunca a do Core (#3267, parte 1).

O envio do pedido lê a sacola (``_cart_data``), grava as escolhas na sessão
(``modify_session``) e só então a sela (``commit_session``). Entre um passo e
outro a sacola pode deixar de existir:

- outra aba do MESMO navegador enviou a mesma sacola;
- outro aparelho da mesma pessoa enviou um pedido, e esta sacola foi encerrada
  (``finalize_phone_handle`` abandona as sacolas antigas do mesmo telefone);
- a limpeza apagou a sacola parada (``cleanup_stale_sessions``);
- outra aba tirou o último item.

O Core recusa com a frase dele ("Esta sessão foi abandonada…", "Sessão foi
abandonada", "Sessão não encontrada: web:…", "Commit já está em andamento com
esta chave"), ou com uma frase que manda conferir uma sacola que não existe mais
("Sua sacola mudou. Confira os itens…"), e a API repassava a frase como
``detail``: o cliente lia texto de sistema num toast, sem saída.

Cada teste segue o fluxo real da loja (sacola pela API, baseline lida da
projeção, ``POST /api/v1/checkout/``) e provoca o caso no instante exato em que
ele acontece na vida.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from shopman.shop.models import DeliveryZone, Shop
from shopman.storefront.tests._checkout_auth import authenticate_checkout
from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

# O que o Core diz e o cliente nunca pode ler.
SYSTEM_WORDS = ("Sessão", "sessão", "Commit", "commit", "web:", "chave")

BAG_GONE = "Sua sacola ficou vazia antes do envio."
MENU_ACTION = [{"ref": "menu", "kind": "link", "label": "Ver o cardápio", "href": "/menu"}]

ADDRESS = {
    "formatted_address": "Rua das Flores, 1 - Centro, Londrina - PR",
    "route": "Rua das Flores",
    "street_number": "1",
    "city": "Londrina",
    "state_code": "PR",
    "postal_code": "86050-270",
    "neighborhood": "Centro",
}


def _payload() -> dict:
    return {
        "name": "Ana",
        "payment_method": "cash",
        "phone": "+5543999990001",
        "fulfillment_type": "delivery",
        "delivery_address": "Rua das Flores, 1",
        "delivery_address_structured": ADDRESS,
        "delivery_date": timezone.localdate().isoformat(),
    }


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    # O limite de envios (3/min) mora no cache; um teste não gasta o do outro.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def bag(client):
    """Cliente logado com um pão na sacola, pronto para enviar."""
    authenticate_checkout(client)
    _seed_surface()
    DeliveryZone.objects.create(
        shop=Shop.objects.first(),
        name="Centro",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="860",
        fee_q=600,
    )
    added = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 1}, content_type="application/json")
    assert added.status_code == 200, added.content
    return client


def _send(client, payload: dict, **headers):
    return client.post("/api/v1/checkout/", data=payload, content_type="application/json", **headers)


def _cart_session_key(client) -> str:
    return client.session["cart_session_key"]


def _once(effect):
    fired = []

    def run():
        if not fired:
            fired.append(True)
            effect()

    return run


def _when_the_bag_is_read(monkeypatch, effect, *, before: bool):
    """Roda ``effect`` logo antes (ou logo depois) de a loja ler a sacola."""
    from shopman.storefront.api import views

    real = views._cart_data
    run = _once(effect)

    def read(request):
        if before:
            run()
        cart = real(request)
        if not before:
            run()
        return cart

    monkeypatch.setattr(views, "_cart_data", read)


def _just_before_the_seal(monkeypatch, effect):
    """Roda ``effect`` depois de as escolhas entrarem na sessão, antes do selo."""
    from shopman.shop.services import sessions

    real = sessions.commit_session
    run = _once(effect)

    def seal(**kwargs):
        run()
        return real(**kwargs)

    monkeypatch.setattr(sessions, "commit_session", seal)


def _assert_house_sentence(body: dict) -> None:
    detail = body["detail"]
    assert not any(word in detail for word in SYSTEM_WORDS), detail
    assert "—" not in detail, detail


def _assert_order_already_sent(resp, order_ref: str) -> None:
    assert resp.status_code == 409, resp.content
    body = resp.json()
    _assert_house_sentence(body)
    assert body["detail"] == "Este pedido já foi enviado."
    assert body["error_code"] == "order_already_sent"
    order_url = f"/pedido/{order_ref}"
    assert body["next_url"] == order_url
    assert body["actions"] == [{"ref": "view_order", "kind": "link", "label": "Ver o pedido", "href": order_url}]


def _assert_bag_is_gone(resp) -> None:
    assert resp.status_code == 409, resp.content
    body = resp.json()
    _assert_house_sentence(body)
    assert body["error_code"] == "cart_empty"
    assert body["detail"] == BAG_GONE
    assert body["actions"] == MENU_ACTION


# ── Duas abas, a mesma sacola ────────────────────────────────────────────────


@pytest.mark.parametrize("before", [True, False], ids=["antes_de_ler_a_sacola", "depois_de_ler_a_sacola"])
def test_a_outra_aba_enviou_primeiro_leva_ao_pedido_que_ja_saiu(bag, monkeypatch, before):
    client = bag
    payload = with_baseline(client, _payload())
    sent = {}

    def other_tab_sends():
        first = _send(client, payload)
        assert first.status_code == 201, first.content
        sent["order_ref"] = first.json()["order_ref"]

    _when_the_bag_is_read(monkeypatch, other_tab_sends, before=before)

    resp = _send(client, payload)

    _assert_order_already_sent(resp, sent["order_ref"])
    # O acompanhamento abre neste navegador, e a sacola enviada não volta.
    from shopman.shop.services.customer_orders import ORDER_ACCESS_SESSION_KEY

    assert sent["order_ref"] in client.session.get(ORDER_ACCESS_SESSION_KEY, [])
    assert "cart_session_key" not in client.session


# ── A sacola deixou de existir no meio do envio ──────────────────────────────


def _abandon(session_key):
    from shopman.shop.services import sessions

    return lambda: sessions.abandon_session(session_key=session_key, channel_ref="web")


def _delete(session_key):
    from shopman.orderman.models import Session

    return lambda: Session.objects.filter(session_key=session_key, channel_ref="web").delete()


@pytest.mark.parametrize("effect", [_abandon, _delete], ids=["outro_aparelho_encerrou", "a_limpeza_apagou"])
def test_sacola_que_sumiu_depois_de_lida(bag, monkeypatch, effect):
    client = bag
    payload = with_baseline(client, _payload())
    _when_the_bag_is_read(monkeypatch, effect(_cart_session_key(client)), before=False)

    _assert_bag_is_gone(_send(client, payload))


@pytest.mark.parametrize("effect", [_abandon, _delete], ids=["outro_aparelho_encerrou", "a_limpeza_apagou"])
def test_sacola_que_sumiu_antes_do_selo(bag, monkeypatch, effect):
    client = bag
    payload = with_baseline(client, _payload())
    _just_before_the_seal(monkeypatch, effect(_cart_session_key(client)))

    _assert_bag_is_gone(_send(client, payload))


def test_a_outra_aba_tirou_o_ultimo_item(bag, monkeypatch):
    """"Confira os itens e confirme novamente" sobre uma sacola sem item nenhum."""
    client = bag
    payload = with_baseline(client, _payload())

    def other_tab_empties_the_bag():
        removed = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 0}, content_type="application/json")
        assert removed.status_code == 200, removed.content

    _when_the_bag_is_read(monkeypatch, other_tab_empties_the_bag, before=False)

    _assert_bag_is_gone(_send(client, payload))


def test_sacola_ja_vazia_no_envio_diz_o_que_fazer(bag):
    """A recusa que já era da loja ganha o código e a saída para o cardápio."""
    client = bag
    payload = with_baseline(client, _payload())
    removed = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 0}, content_type="application/json")
    assert removed.status_code == 200, removed.content

    _assert_bag_is_gone(_send(client, payload))


def test_a_mudanca_de_verdade_segue_pedindo_conferencia(bag, monkeypatch):
    """Sacola viva que mudou continua "Sua sacola mudou": a tela reprecifica e reabre."""
    client = bag
    payload = with_baseline(client, _payload())

    def other_tab_adds_one_more():
        added = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 2}, content_type="application/json")
        assert added.status_code == 200, added.content

    _when_the_bag_is_read(monkeypatch, other_tab_adds_one_more, before=False)

    resp = _send(client, payload)

    assert resp.status_code == 409, resp.content
    assert resp.json()["error_code"] == "revision_changed"


# ── O selo do Core ainda em andamento ────────────────────────────────────────


def test_envio_que_o_core_ainda_esta_selando_vira_conferencia(bag):
    """O recibo da loja expira em 30 s; o do Core, não.

    Uma tentativa que demorou mais que o recibo da loja e é reenviada com a
    mesma chave passa pela loja e encontra o selo do Core ainda em andamento.
    A tela já sabe esperar esse caso (``mutation_in_progress``): confere até o
    pedido aparecer, sem pedir um segundo envio.
    """
    from shopman.orderman.models import IdempotencyKey
    from shopman.orderman.services.commit import CommitService

    client = bag
    payload = with_baseline(client, _payload())
    key = "tentativa-demorada"
    IdempotencyKey.objects.create(
        scope=CommitService._idempotency_scope(_cart_session_key(client), "web"),
        key=key,
        status="in_progress",
        expires_at=timezone.now() + timedelta(hours=1),
    )

    resp = _send(client, payload, HTTP_IDEMPOTENCY_KEY=key)

    assert resp.status_code == 409, resp.content
    body = resp.json()
    _assert_house_sentence(body)
    assert body["error_code"] == "mutation_in_progress"
    assert body["detail"] == "Seu pedido ainda está sendo enviado. Aguarde a confirmação nesta tela."
