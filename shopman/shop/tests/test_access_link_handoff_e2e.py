"""PONTA A PONTA do handoff: site gera o NB-XxXx, ManyChat devolve, `has_context`.

`has_context` é `bool(metadata["cart_session_key"])`, e esse dado só existe se o
código NB-XxXx gerado pelo `/start` do site for consumido no `/create`. Se ele
sempre volta false, o código não está chegando — ou não está sendo extraído da
mensagem inteira.

Cada teste isola um elo da corrente.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client

URL = "/api/auth/access/create/"
KEY = "e2e-handoff"


@pytest.fixture(autouse=True)
def _api_key(settings):
    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_API_KEY"] = KEY
    settings.DOORMAN = base


@pytest.fixture
def joyce():
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
    from shopman.guestman.models import Customer
    from shopman.guestman.services import customer as customer_service

    c = customer_service.create(
        ref=Customer.generate_ref(), first_name="Joyce",
        phone="5543999990009", source_system="doorman",
    )
    CustomerIdentifier.objects.create(
        customer=c, identifier_type=IdentifierType.MANYCHAT,
        identifier_value="mc-joyce", is_primary=True,
    )
    return c


def _post(payload):
    return Client().post(
        URL, data=json.dumps(payload), content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {KEY}",
    )


def _start(cart_key=""):
    from shopman.shop.services.whatsapp_verify import start_access_link

    return start_access_link(cart_session_key=cart_key, next_path="/menu")


@pytest.mark.django_db
def test_elo_1_o_start_gera_codigo_e_a_mensagem_do_botao():
    out = _start(cart_key="cart-abc")
    print("\n[E1] start →", json.dumps(out, ensure_ascii=False)[:300])


@pytest.mark.django_db
def test_elo_2_extracao_do_codigo_da_mensagem_inteira():
    from shopman.doorman.services.link_state import contains_code, extract_code

    out = _start(cart_key="cart-abc")
    code = out.get("code") or out.get("access_code") or ""
    msg = f"#menu {code}"
    print(f"[E2] mensagem={msg!r} contains={contains_code(msg)} extract={extract_code(msg)!r}")


@pytest.mark.django_db
def test_elo_3_create_com_a_mensagem_inteira(joyce):
    out = _start(cart_key="cart-abc")
    code = out.get("code") or out.get("access_code") or ""
    r = _post({
        "subscriber": {"id": "mc-joyce", "whatsapp_id": "5543999990009", "first_name": "Joyce"},
        "access_code": f"#menu {code}",
    })
    print("[E3] create com msg inteira →", r.status_code, r.content[:220])


@pytest.mark.django_db
def test_elo_4_create_sem_access_code(joyce):
    _start(cart_key="cart-abc")
    r = _post({
        "subscriber": {"id": "mc-joyce", "whatsapp_id": "5543999990009", "first_name": "Joyce"},
    })
    print("[E4] create SEM access_code       →", r.status_code, r.content[:220])


@pytest.mark.django_db
def test_elo_5_codigo_usado_duas_vezes(joyce):
    out = _start(cart_key="cart-abc")
    code = out.get("code") or out.get("access_code") or ""
    payload = {
        "subscriber": {"id": "mc-joyce", "whatsapp_id": "5543999990009", "first_name": "Joyce"},
        "access_code": f"#menu {code}",
    }
    first = _post(payload)
    second = _post(payload)
    print("[E5] 1ª chamada →", first.status_code, first.content[:150])
    print("[E5] 2ª chamada →", second.status_code, second.content[:150])


@pytest.mark.django_db
def test_elo_6_start_sem_sacola(joyce):
    out = _start(cart_key="")
    code = out.get("code") or out.get("access_code") or ""
    r = _post({
        "subscriber": {"id": "mc-joyce", "whatsapp_id": "5543999990009", "first_name": "Joyce"},
        "access_code": f"#menu {code}",
    })
    print("[E6] start SEM sacola             →", r.status_code, r.content[:220])


@pytest.mark.django_db
def test_elo_7_access_code_com_lixo_nao_passa_por_login_organico(joyce):
    """URL de mídia do Instagram no lugar do código: a sacola não some calada."""
    from unittest.mock import patch

    IG = ("https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=17977763199107464"
          "&signature=Ab035A76yatScvNo-tUb5HFGO0gyp0gt")
    with patch("shopman.doorman.views.access_link.logger") as log:
        r = _post({
            "subscriber": {"id": "mc-joyce", "whatsapp_id": "5543999990009"},
            "access_code": IG,
        })
    body = r.json()
    print("\n[E7] access_code = URL do Instagram →", r.status_code,
          "handoff_expired=", body["handoff_expired"])
    assert r.status_code == 200, "o login NUNCA falha por causa da sacola"
    assert body["handoff_expired"] is True, "a sacola sumiu — e isso tem de ser dito"
    assert log.warning.called, "e o log tem de gritar, senão ninguém descobre a variável errada"
    assert "access_code_sem_codigo" in log.warning.call_args[0][0]


@pytest.mark.django_db
def test_elo_8_menu_seco_continua_sendo_login_organico(joyce):
    """`#menu` puro é entrada legítima pelo WhatsApp: não é handoff falho."""
    r = _post({
        "subscriber": {"id": "mc-joyce", "whatsapp_id": "5543999990009"},
        "access_code": "#menu",
    })
    body = r.json()
    print("[E8] access_code = '#menu' →", r.status_code, "handoff_expired=", body["handoff_expired"])
    assert body["handoff_expired"] is False
