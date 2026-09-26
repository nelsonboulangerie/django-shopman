"""Uma TV, um quadro — e um navegador pode ser confiável para os DOIS.

O defeito que este arquivo guarda: o cookie de confiança de display tinha **um
nome só** para todos os quadros. Autorizar o segundo sobrescrevia o token do
primeiro, e o primeiro voltava a dar 403. Numa casa com duas TVs tocadas pelo
mesmo navegador, o resultado é as duas telas em branco alternadamente — que foi
exatamente o que aconteceu na Nelson.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth.models import User
from django.test import Client


def _expira_a_sessao(client) -> None:
    """Só a sessão vai embora; o cookie de dispositivo fica, como na TV."""
    client.cookies.pop(dj_settings.SESSION_COOKIE_NAME, None)


@pytest.fixture
def dois_quadros(db):
    from shopman.offerman.models import Collection, CollectionItem, Product

    from shopman.shop.models import Channel

    col = Collection.objects.create(ref="rusticos", name="Rústicos")
    product = Product.objects.create(
        sku="BAGUETE", name="Baguette de Tradition", base_price_q=1600, is_published=True, is_sellable=True
    )
    CollectionItem.objects.create(collection=col, product=product)
    for ref, name in (("tv-salao", "TV do Salão"), ("tv-cafe", "TV do Café")):
        Channel.objects.create(
            ref=ref,
            name=name,
            commerce_policy=Channel.CommercePolicy.DISPLAY,
            is_active=True,
            config={"display": {"format": "", "collections": ["rusticos"], "prices_from": "pdv", "paused_skus": []}},
        )


@pytest.mark.django_db
def test_um_navegador_pode_ser_confiavel_para_os_dois_quadros(dois_quadros, settings):
    """O caso real: um PC toca as duas TVs, e as duas precisam funcionar.

    Antes, autorizar a segunda derrubava a primeira — um cookie, um token.
    """
    settings.SHOPMAN_MENUBOARD_PUBLIC = False
    User.objects.create_user("operador", password="pw", is_staff=True)

    tv = Client()
    tv.login(username="operador", password="pw")
    assert tv.get("/menuboard/tv-salao/").status_code == 200
    assert tv.get("/menuboard/tv-cafe/").status_code == 200

    # A sessão de staff acaba, o dispositivo continua confiável — que é a vida
    # real da TV. `Client.logout()` não serve aqui: ele limpa TODOS os cookies,
    # inclusive o de confiança, e o teste passaria a medir outra coisa.
    _expira_a_sessao(tv)

    assert tv.get("/menuboard/tv-salao/").status_code == 200, "autorizar o segundo quadro derrubou o primeiro"
    assert tv.get("/menuboard/tv-cafe/").status_code == 200


@pytest.mark.django_db
def test_confianca_de_um_quadro_nao_abre_outro(dois_quadros, settings):
    """O que NÃO pode mudar: cookie de um quadro não vale para o vizinho."""
    settings.SHOPMAN_MENUBOARD_PUBLIC = False
    User.objects.create_user("operador", password="pw", is_staff=True)

    tv = Client()
    tv.login(username="operador", password="pw")
    tv.get("/menuboard/tv-salao/")
    _expira_a_sessao(tv)

    assert tv.get("/menuboard/tv-salao/").status_code == 200
    assert tv.get("/menuboard/tv-cafe/").status_code == 403


@pytest.mark.django_db
def test_bearer_do_player_so_abre_controle_do_proprio_quadro(dois_quadros, settings):
    from shopman.doorman.models import TrustedDevice

    from shopman.shop.menuboard_access import PLAYER_USER_AGENT_PREFIX

    settings.SHOPMAN_MENUBOARD_PUBLIC = False
    _, token = TrustedDevice.create_for(
        subject_type="display",
        subject_id="tv-salao",
        user_agent=f"{PLAYER_USER_AGENT_PREFIX}1.0",
    )
    _, browser_token = TrustedDevice.create_for(subject_type="display", subject_id="tv-salao")
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    assert Client().get("/menuboard/tv-salao/control/", **headers).status_code == 200
    assert Client().get("/menuboard/tv-cafe/control/", **headers).status_code == 403
    assert Client().get("/menuboard/tv-salao/data/", **headers).status_code == 403
    assert Client().get("/menuboard/tv-salao/", **headers).status_code == 403
    assert Client().get(
        "/menuboard/tv-salao/control/", HTTP_AUTHORIZATION=f"Bearer {browser_token}"
    ).status_code == 403


@pytest.mark.django_db
def test_controle_expõe_intenção_sem_conteúdo_ou_preço(dois_quadros, settings, monkeypatch):
    settings.SHOPMAN_MENUBOARD_PUBLIC = True
    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime(2026, 9, 28, 3, 0, tzinfo=tz)
    wakes_at = datetime(2026, 9, 28, 8, 45, tzinfo=tz)
    monkeypatch.setattr("shopman.shop.views.menuboard.timezone.now", lambda: now)
    monkeypatch.setattr(
        "shopman.shop.services.menuboard_schedule.resolve_menuboard_automatic_state",
        lambda channel, now=None: SimpleNamespace(
            enabled=True,
            is_sleeping=True,
            wakes_at=wakes_at,
            sleeps_at=None,
        ),
    )

    payload = Client().get("/menuboard/tv-salao/control/").json()

    assert payload == {
        "ref": "tv-salao",
        "mode": "sleep",
        "automatic_enabled": True,
        "standby_allowed": True,
        "server_time": now.isoformat(),
        "next_transition_at": wakes_at.isoformat(),
    }
    assert "pages" not in payload and "price" not in str(payload).lower()
