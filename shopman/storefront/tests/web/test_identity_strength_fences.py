"""As cercas que dependem de quanto sabemos de quem está do outro lado.

O contexto, porque ele é a razão de cada linha aqui: o disparo do WhatsApp passou a levar um
link pessoal, então a pessoa chega **identificada** e o checkout não pede login. Só que
identificar por link não é o mesmo que reconhecer a pessoa: mensagem se encaminha, e quem
tocar num link encaminhado antes da dona vira ela para o sistema.

⚠️ A primeira versão do desenho pedia confirmação por OTP para ver endereço e usar pontos. O
dono derrubou com o argumento que faltava: **entrega precisa de endereço**, então proteger o
dado atrapalhando o fluxo principal é o pior dos dois mundos. Segurança que estraga a
experiência não é segurança, é imposto.

As duas cercas que sobreviveram não custam nada a quem é dona de verdade:

1. **Endereço desce reduzido** — rótulo e bairro, sem rua nem número. Escolher nunca exigiu
   ler: a seleção é por `id`, e o pedido é montado no servidor a partir dele.
2. **Pontos valem onde ela já vai** — endereço salvo ou balcão. É a única rota de perda
   material que um link encaminhado abria.

E a cerca inteira desaparece quando o aparelho é conhecido (`identity_strength = device`),
que é o caso da esmagadora maioria de quem volta: o celular dela já provou identidade um dia.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer, CustomerAddress
from shopman.orderman.models import Order

from shopman.storefront.identity import IDENTITY_NUMBER, IDENTITY_SESSION_KEY
from shopman.storefront.tests._checkout_baseline import displayed_total_q

pytestmark = pytest.mark.django_db


@pytest.fixture
def person(db):
    customer = Customer.objects.create(
        ref="CLI-FENCE", first_name="Ana", last_name="Ferreira", phone="+5543999998001",
    )
    CustomerAddress.objects.create(
        customer=customer,
        formatted_address="Rua das Flores, 123 - Centro, Londrina - PR",
        label="home",
        label_custom="Casa",
        is_default=True,
        route="Rua das Flores",
        street_number="123",
        neighborhood="Centro",
        city="Londrina",
        state_code="PR",
        # ⚠️ Coordenada NÃO é detalhe de fixture: ela é `Decimal` no model, e foi a ausência
        # dela aqui que deixou passar um 500 em produção-de-mentira — o teste passava com
        # endereço sem lat/lng enquanto o endereço real do seed derrubava o checkout.
        latitude=Decimal("-23.3103"),
        longitude=Decimal("-51.1628"),
    )
    return customer


def _sign_in(client, person, *, strength: str | None = None):
    """Sessão autenticada, opcionalmente marcada com a força da identidade."""
    from django.contrib.auth import get_user_model
    from shopman.doorman.models import CustomerUser

    User = get_user_model()
    user = User.objects.create_user(username=f"c-{person.ref}", password="x")
    CustomerUser.objects.create(user=user, customer_id=person.uuid)
    client.force_login(user)

    session = client.session
    if strength:
        session[IDENTITY_SESSION_KEY] = strength
    session.save()
    return user


def _checkout(client):
    """A projeção do checkout que o app Nuxt lê (`/storefront/checkout/`).

    `/checkout/` é o POST que confirma o pedido; a leitura é outra rota — confundir as duas
    dá 405 e nenhuma informação sobre o que se queria testar.
    """
    response = client.get("/api/v1/storefront/checkout/")
    assert response.status_code == 200, response.content
    body = response.json()
    return body.get("checkout") or body


# ── Endereço: escolher não exige ler ─────────────────────────────────


def test_a_known_device_sees_the_whole_address(client, person):
    """É o celular dela. Nada a reduzir — e reduzir aqui só atrapalharia."""
    _sign_in(client, person)

    addresses = _checkout(client)["saved_addresses"]

    assert addresses, "a pessoa tem endereço salvo"
    assert "Rua das Flores" in addresses[0]["formatted_address"]
    assert addresses[0]["street_number"] == "123"


def test_a_link_session_sees_the_label_and_the_neighbourhood_only(client, person):
    """Suficiente para ESCOLHER, insuficiente para saber onde ela mora."""
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    address = _checkout(client)["saved_addresses"][0]

    assert address["label"] == "Casa"
    assert address["formatted_address"] == "Centro · Londrina"
    assert "Rua das Flores" not in json.dumps(address)
    assert address["street_number"] == ""
    assert address["latitude"] is None


def test_the_id_still_travels_so_the_choice_still_works(client, person):
    """A seleção é por `id`: é isso que faz a redução ser grátis para a experiência."""
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    address = _checkout(client)["saved_addresses"][0]

    assert address["id"] == person.addresses.get().id
    assert address["is_default"] is True


# ── Entrega: o endereço salvo manda, o texto do cliente não ──────────


def _delivery_payload(person, **over):
    payload = {
        "name": "Ana",
        "phone": person.phone,
        "fulfillment_type": "delivery",
        "payment_method": "cash",
        "delivery_date": timezone.localdate().isoformat(),
    }
    payload.update(over)
    return payload


def test_choosing_a_saved_address_delivers_to_the_saved_address(
    cart_session_delivery, person, channel,
):
    """⚠️ A precedência era a inversa (`texto do cliente or salvo`).

    Com o endereço reduzido, o texto que a tela tem é "Centro · Londrina" — e o entregador
    receberia isso como endereço. Pior, e independente de redução: mandar um `id` e um texto
    diferente entregaria em lugar diferente do escolhido.
    """
    client = cart_session_delivery
    _sign_in(client, person, strength=IDENTITY_NUMBER)
    saved = person.addresses.get()

    payload = _delivery_payload(
        person,
        saved_address_id=saved.id,
        # O que a tela reduzida tem em mãos — e que NÃO pode virar o endereço do pedido.
        delivery_address="Centro · Londrina",
    )
    payload["expected_total_q"] = displayed_total_q(client, payload)

    response = client.post(
        "/api/v1/checkout/", data=json.dumps(payload), content_type="application/json",
    )

    assert response.status_code == 201, response.content
    order = Order.objects.latest("id")
    assert order.data["delivery_address"] == saved.formatted_address


# ── Pontos valem onde ela já vai ─────────────────────────────────────


def test_points_on_a_new_address_ask_for_confirmation(cart_session_delivery, person):
    """A única rota de perda MATERIAL que um link encaminhado abria: os pontos dela
    convertidos em pão entregue em outro lugar."""
    client = cart_session_delivery
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    payload = _delivery_payload(
        person,
        delivery_address="Rua de Outro Alguém, 999 - Centro, Londrina",
        use_loyalty=True,
        expected_total_q=3200,
    )
    response = client.post(
        "/api/v1/checkout/", data=json.dumps(payload), content_type="application/json",
    )

    assert response.status_code == 403, response.content
    body = response.json()
    assert body["error_code"] == "identity_confirmation_required"
    assert body["field"] == "use_loyalty"
    # A copy diz o que dá para fazer AGORA, não só o que está barrado.
    assert "salvo" in body["detail"] and "balcão" in body["detail"]


def test_points_on_a_saved_address_are_never_blocked(cart_session_delivery, person):
    """Endereço salvo é "onde ela já vai": a cerca não encosta em quem é dona."""
    client = cart_session_delivery
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    payload = _delivery_payload(
        person, saved_address_id=person.addresses.get().id, use_loyalty=True,
    )
    payload["expected_total_q"] = displayed_total_q(client, payload)
    response = client.post(
        "/api/v1/checkout/", data=json.dumps(payload), content_type="application/json",
    )

    assert response.status_code == 201, response.content


def test_points_at_the_counter_are_never_blocked(cart_session_delivery, person):
    """Retirada no balcão: quem retira aparece de corpo presente."""
    client = cart_session_delivery
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    # ⚠️ Horário HABILITADO, não o primeiro da lista. A projeção devolve todos os
    # configurados e marca `enabled=False` no que já passou (`reason` diz por quê) — pegar
    # `slots[0]` fazia o teste passar de manhã e falhar à tarde, que é o pior tipo de teste:
    # o que mente sobre o motivo da falha.
    slots = [s for s in (_checkout(client).get("pickup_slots") or []) if s.get("enabled")]
    if not slots:
        pytest.skip("nenhum horário de retirada habilitado agora (loja fechada ou dia vencido)")
    payload = {
        "name": "Ana",
        "phone": person.phone,
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "use_loyalty": True,
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_time_slot": slots[0]["ref"],
    }
    payload["expected_total_q"] = displayed_total_q(client, payload)
    response = client.post(
        "/api/v1/checkout/", data=json.dumps(payload), content_type="application/json",
    )

    assert response.status_code == 201, response.content


def test_a_known_device_spends_points_on_a_new_address(cart_session_delivery, person):
    """No celular dela não há cerca nenhuma — nem para endereço novo com pontos.

    É a resposta ao incômodo do dono: a restrição não é do sistema, é da falta de
    reconhecimento. Onde reconhecemos a pessoa, ela desaparece.
    """
    client = cart_session_delivery
    _sign_in(client, person)  # sem marca ⇒ força `device`

    payload = _delivery_payload(
        person,
        delivery_address="Rua Nova, 42 - Centro, Londrina - PR",
        delivery_address_structured={
            "formatted_address": "Rua Nova, 42 - Centro, Londrina - PR",
            "route": "Rua Nova",
            "street_number": "42",
            "neighborhood": "Centro",
            "city": "Londrina",
        },
        use_loyalty=True,
    )
    payload["expected_total_q"] = displayed_total_q(client, payload)
    response = client.post(
        "/api/v1/checkout/", data=json.dumps(payload), content_type="application/json",
    )

    assert response.status_code == 201, response.content


# ── O degrau dissolve a cerca, em vez de empilhá-la ──────────────────


def test_confirming_identity_makes_the_device_known_for_good(client, person, monkeypatch):
    """⚠️ Provar identidade tem de COMPRAR algo durável.

    A marca de step-up vale 10 minutos — foi feita para "excluir conta", que é ato único. Se
    a confirmação valesse só isso, quem chegou por link seria interrogado de novo na semana
    seguinte, no MESMO celular. Aí não é porta, é pedágio.

    Confirmando uma vez, o navegador entra em `TrustedDevice` e a sessão sobe para `device`:
    endereço completo volta, pontos valem em qualquer entrega, a conta abre.
    """
    from shopman.shop.services import auth as auth_service
    from shopman.storefront.identity import IDENTITY_DEVICE

    _sign_in(client, person, strength=IDENTITY_NUMBER)
    assert client.session[IDENTITY_SESSION_KEY] == IDENTITY_NUMBER

    monkeypatch.setattr(
        auth_service, "verify_for_login",
        lambda **kw: type("R", (), {"success": True})(),
    )

    response = client.post(
        "/api/v1/account/step-up/",
        data=json.dumps({"code": "123456"}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["device_trusted"] is True
    assert client.session[IDENTITY_SESSION_KEY] == IDENTITY_DEVICE

    # E o endereço volta inteiro na mesma sessão, sem novo login.
    address = _checkout(client)["saved_addresses"][0]
    assert "Rua das Flores" in address["formatted_address"]


def test_a_wrong_code_changes_nothing(client, person, monkeypatch):
    """Código errado não promove nada — nem meio."""
    from shopman.shop.services import auth as auth_service

    _sign_in(client, person, strength=IDENTITY_NUMBER)
    monkeypatch.setattr(
        auth_service, "verify_for_login",
        lambda **kw: type("R", (), {"success": False})(),
    )

    response = client.post(
        "/api/v1/account/step-up/",
        data=json.dumps({"code": "000000"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert client.session[IDENTITY_SESSION_KEY] == IDENTITY_NUMBER


def test_a_failure_to_remember_the_device_still_confirms(client, person, monkeypatch):
    """O cookie é atalho, não a confirmação: se ele não gravar, a confirmação vale."""
    from shopman.shop.services import auth as auth_service
    from shopman.storefront.identity import IDENTITY_DEVICE

    _sign_in(client, person, strength=IDENTITY_NUMBER)
    monkeypatch.setattr(
        auth_service, "verify_for_login",
        lambda **kw: type("R", (), {"success": True})(),
    )

    def explode(**kwargs):
        raise RuntimeError("cookie não gravou")

    monkeypatch.setattr(auth_service, "trust_device", explode)

    response = client.post(
        "/api/v1/account/step-up/",
        data=json.dumps({"code": "123456"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert client.session[IDENTITY_SESSION_KEY] == IDENTITY_DEVICE


# ── A cerca vale em TODO caminho, não só no checkout ─────────────────


def test_the_account_projection_reduces_the_saved_addresses(person):
    """⚠️ O furo que a descrição do fluxo revelou ANTES de eu implementar.

    A redução nasceu só no checkout — então bastava abrir a conta para ler a rua que a outra
    tela escondia. Cerca que vale num caminho e não no outro é decoração.

    Exercitado na projeção porque é ela que as duas telas da conta consomem; o endpoint de
    lista tem teste próprio abaixo. (O `/account/summary/` não devolve endereço: quem os
    busca é `/account/addresses/`.)
    """
    from shopman.storefront.presentation.account import build_account

    reduced = build_account(person, reduced_addresses=True).saved_addresses[0]
    full = build_account(person, reduced_addresses=False).saved_addresses[0]

    assert reduced.formatted_address == "Centro · Londrina"
    assert reduced.route == "" and reduced.street_number == ""
    assert reduced.id == full.id, "o id continua descendo: é ele que faz a escolha funcionar"
    assert "Rua das Flores" in full.formatted_address


def test_the_address_list_endpoint_reduces_as_well(client, person):
    """`/account/addresses/` é o outro caminho para a mesma informação."""
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    response = client.get("/api/v1/account/addresses/")

    assert response.status_code == 200, response.content
    body = response.json()
    rows = body if isinstance(body, list) else body.get("addresses", body.get("results", []))
    assert rows, body
    assert rows[0]["formatted_address"] == "Centro · Londrina"
    assert rows[0]["route"] == ""
    assert rows[0]["latitude"] is None
    # E o `id` continua descendo: é ele que faz a escolha funcionar.
    assert rows[0]["id"] == person.addresses.get().id


def test_writing_an_address_still_answers_with_what_was_written(client, person):
    """Quem acabou de digitar o endereço não precisa que a resposta o esconda — e esconder
    ali quebraria o formulário sem proteger nada."""
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    response = client.post(
        "/api/v1/account/addresses/",
        data=json.dumps({
            "formatted_address": "Rua Nova, 42 - Centro, Londrina - PR",
            "label": "work",
        }),
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assert "Rua Nova" in response.json()["formatted_address"]


def test_a_saved_address_with_coordinates_does_not_break_the_checkout(
    cart_session_delivery, person,
):
    """⚠️ O 500 que só a tela achou.

    `Session.data` é JSONField, e `json.dumps` não serializa `Decimal`:

        TypeError: Object of type Decimal is not JSON serializable
        (modifiers.py:844 → session.save)

    Ficava escondido porque o app sempre manda `delivery_address_structured` com lat/lng em
    float, e o merge deixava o float por cima. Bastou a precedência virar "o salvo manda"
    para o `Decimal` do banco chegar ao JSON — e o endereço do seed TEM coordenada, o da
    fixture não tinha. Daí o teste verde e a tela vermelha.

    A normalização agora é de quem monta o dicionário (`_clean_structured_address`), então
    vale para as DUAS fontes.
    """
    client = cart_session_delivery
    _sign_in(client, person, strength=IDENTITY_NUMBER)
    saved = person.addresses.get()
    assert saved.latitude is not None, "a fixture precisa ter coordenada — é o ponto do teste"

    payload = _delivery_payload(person, saved_address_id=saved.id)
    payload["expected_total_q"] = displayed_total_q(client, payload)

    response = client.post(
        "/api/v1/checkout/", data=json.dumps(payload), content_type="application/json",
    )

    assert response.status_code == 201, response.content
    order = Order.objects.latest("id")
    structured = order.data.get("delivery_address_structured") or {}
    assert isinstance(structured.get("latitude"), float)
    assert order.data["delivery_address"] == saved.formatted_address
