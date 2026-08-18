"""Uma TV, um quadro — e um navegador pode ser confiável para os DOIS.

O defeito que este arquivo guarda: o cookie de confiança de display tinha **um
nome só** para todos os quadros. Autorizar o segundo sobrescrevia o token do
primeiro, e o primeiro voltava a dar 403. Numa casa com duas TVs tocadas pelo
mesmo navegador, o resultado é as duas telas em branco alternadamente — que foi
exatamente o que aconteceu na Nelson.
"""

from __future__ import annotations

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
    product = Product.objects.create(sku="BAGUETE", name="Baguette de Tradition",
                                     base_price_q=1600, is_published=True, is_sellable=True)
    CollectionItem.objects.create(collection=col, product=product)
    for ref, name in (("tv-salao", "TV do Salão"), ("tv-cafe", "TV do Café")):
        Channel.objects.create(
            ref=ref, name=name,
            commerce_policy=Channel.CommercePolicy.DISPLAY, is_active=True,
            config={"display": {"format": "", "collections": ["rusticos"],
                                "prices_from": "pdv", "paused_skus": []}},
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

    assert tv.get("/menuboard/tv-salao/").status_code == 200, (
        "autorizar o segundo quadro derrubou o primeiro"
    )
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
