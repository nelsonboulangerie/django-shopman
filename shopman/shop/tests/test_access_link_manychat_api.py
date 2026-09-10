"""O corpo do request carrega SÓ o `subscriber_id`; o resto vem do ManyChat.

Provado com dado real do contato 1962036908 em 01/09:

    whatsapp_phone:  "+5543984035793"
    last_input_text: "#menu NB-282SW9"
    phone:           null              ← nulo num contato de WhatsApp saudável

Foi assumir o `phone` que quebrou o login. Estes testes pinam a busca na fonte.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.test import Client

URL = "/api/auth/access/create/"
KEY = "mc-api"

# O JSON real, reduzido aos campos que importam.
INFO_WHATSAPP = {
    "id": "1962036908",
    "first_name": "Joyce",
    "last_name": "Nogueira",
    "phone": None,
    "whatsapp_phone": "+5543984035793",
    "optin_whatsapp": True,
    "last_input_text": "#menu {code}",
    "ig_id": None,
}


@pytest.fixture(autouse=True)
def _api_key(settings):
    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_API_KEY"] = KEY
    settings.DOORMAN = base


def _post(payload):
    return Client().post(
        URL, data=json.dumps(payload), content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {KEY}",
    )


def _start(cart_key="cart-api"):
    from shopman.shop.services.whatsapp_verify import start_access_link

    return start_access_link(cart_session_key=cart_key, next_path="/menu")


@pytest.mark.django_db
def test_corpo_so_com_subscriber_id_resolve_identidade_e_sacola():
    """Nem telefone nem código no corpo — e mesmo assim entra com a sacola."""
    out = _start()
    info = {**INFO_WHATSAPP, "last_input_text": f"#menu {out['code']}"}

    with patch(
        "shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.fetch_subscriber_info",
        return_value=info,
    ):
        r = _post({"subscriber": {"id": "1962036908"}})

    body = r.json()
    assert r.status_code == 200, body
    assert body["has_context"] is True, "a sacola veio pelo last_input_text da API"
    assert body["handoff_expired"] is False


@pytest.mark.django_db
def test_o_telefone_vem_de_whatsapp_phone_nunca_do_phone_nulo():
    from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver
    from shopman.guestman.models import Customer

    with patch.object(ManychatSubscriberResolver, "fetch_subscriber_info", return_value=INFO_WHATSAPP):
        r = _post({"subscriber": {"id": "1962036908"}})

    assert r.status_code == 200, r.content
    customer = Customer.objects.get(first_name="Joyce")
    assert customer.phone.endswith("43984035793"), customer.phone


@pytest.mark.django_db
def test_api_indisponivel_nao_derruba_o_login():
    """API lenta ou fora do ar não pode virar porta fechada — só perde a sacola."""
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
    from shopman.guestman.models import Customer
    from shopman.guestman.services import customer as customer_service

    c = customer_service.create(
        ref=Customer.generate_ref(), first_name="Joyce",
        phone="5543984035793", source_system="doorman",
    )
    CustomerIdentifier.objects.create(
        customer=c, identifier_type=IdentifierType.MANYCHAT,
        identifier_value="1962036908", is_primary=True,
    )

    with patch(
        "shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.fetch_subscriber_info",
        side_effect=OSError("timeout"),
    ):
        r = _post({"subscriber": {"id": "1962036908", "whatsapp_id": "5543984035793"}})

    assert r.status_code == 200, r.content


@pytest.mark.django_db
def test_codigo_no_corpo_tem_precedencia_e_nao_chama_a_api():
    """Fluxo bem configurado não paga round-trip: a API é fallback, não caminho."""
    out = _start()

    with patch(
        "shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.fetch_subscriber_info",
    ) as fetch:
        r = _post({
            "subscriber": {"id": "1962036908", "whatsapp_id": "5543984035793"},
            "access_code": f"#menu {out['code']}",
        })

    assert r.json()["has_context"] is True
    assert not fetch.called, "com tudo no corpo, não há por que consultar o ManyChat"
