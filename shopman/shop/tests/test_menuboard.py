"""Menuboard — canal de exibição sem formato, interno e em tempo real."""

from __future__ import annotations

import pytest
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.projections.menuboard import MenuboardError, build_menuboard
from shopman.shop.tests._display import display_channel


@pytest.fixture
def menuboard(db):
    display_channel("tv-balcao", "Quadro do Balcão", collections=["paes", "doces"], prices_from="pdv")
    paes = Collection.objects.create(ref="paes", name="Pães", is_active=True, sort_order=1)
    doces = Collection.objects.create(ref="doces", name="Doces", is_active=True, sort_order=2)
    pao = Product.objects.create(
        sku="PAO", name="Pão na Chapa", unit="un", base_price_q=800,
        is_published=True, is_sellable=True, short_description="Na manteiga",
    )
    bolo = Product.objects.create(
        sku="BOLO", name="Bolo", unit="un", base_price_q=1200, is_published=True, is_sellable=True,
    )
    CollectionItem.objects.create(collection=paes, product=pao)
    CollectionItem.objects.create(collection=doces, product=bolo)
    return {"pao": pao, "bolo": bolo}


def test_sections_are_showcase_collections(menuboard):
    board = build_menuboard("tv-balcao")
    assert board.title == "Quadro do Balcão"
    assert [g.title for g in board.groups] == ["Pães", "Doces"]  # ordem do feed
    assert board.available_count == 2
    pao = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao.price_q == 800 and pao.available is True and pao.description == "Na manteiga"


def test_paused_product_drops_from_available(menuboard):
    menuboard["pao"].is_sellable = False
    menuboard["pao"].save()
    board = build_menuboard("tv-balcao")
    pao = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao.available is False
    assert board.available_count == 1  # só o bolo


def test_local_pause_drops_item_on_this_channel(menuboard):
    """Pausa por-canal (display.paused_skus) tira o item DESTE quadro."""
    from shopman.shop.models import Channel
    channel = Channel.objects.get(ref="tv-balcao")
    channel.config = {**channel.config, "display": {**channel.config["display"], "paused_skus": ["PAO"]}}
    channel.save(update_fields=["config"])
    board = build_menuboard("tv-balcao")
    pao = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao.available is False
    assert board.available_count == 1  # só o bolo; PAO segue globalmente vendável


def test_smart_collection_section(db):
    display_channel("tv", "TV", collections=["caros"], prices_from="pdv")
    Collection.objects.create(
        ref="caros", name="Caros", is_active=True,
        rule={"match": "all", "conditions": [{"field": "base_price_q", "op": "gte", "value": 1000}]},
    )
    Product.objects.create(sku="BOLO", name="Bolo", base_price_q=4500, is_published=True, is_sellable=True)
    Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    board = build_menuboard("tv")
    assert [i.sku for g in board.groups for i in g.items] == ["BOLO"]  # regra resolve a seção


def test_rejects_platform_feed_channel(db):
    """Canal COM formato é feed de plataforma; o quadro recusa."""
    display_channel("google", "G", collections=["x"], fmt="google_merchant", prices_from="web")
    with pytest.raises(MenuboardError):
        build_menuboard("google")


def test_rejects_missing(db):
    with pytest.raises(MenuboardError):
        build_menuboard("fantasma")


# ── views: superfície INTERNA ───────────────────────────────────────────────────
#
# O menuboard deixou de ser público (ADR-018 §5.1): o preço dele vem do PDV, e preço
# alcançável publicamente é preço a honrar. Duas credenciais valem — sessão de staff
# (gente) e dispositivo confiável (a TV). E abrir logado É o provisionamento da TV.


def _staff(django_user_model, username="gestor"):
    return django_user_model.objects.create_user(username, password="x", is_staff=True)


def _drop_session(client):
    """Encerra a sessão SEM descartar os outros cookies.

    ``client.logout()`` do Django zera o jar inteiro, o que jogaria fora justamente
    o cookie de dispositivo confiável — uma TV real não perde o dela.
    """
    from django.conf import settings

    client.cookies.pop(settings.SESSION_COOKIE_NAME, None)


def test_page_denies_anonymous(client, menuboard):
    assert client.get("/menuboard/tv-balcao/").status_code == 403


def test_data_denies_anonymous(client, menuboard):
    assert client.get("/menuboard/tv-balcao/data/").status_code == 403


def test_staff_session_opens(client, menuboard, django_user_model):
    client.force_login(_staff(django_user_model))
    resp = client.get("/menuboard/tv-balcao/")
    assert resp.status_code == 200
    assert "Quadro do Balcão".encode() in resp.content
    assert b"menuboard()" in resp.content


def test_non_staff_user_is_refused(client, menuboard, django_user_model):
    user = django_user_model.objects.create_user("cliente", password="x")
    client.force_login(user)
    assert client.get("/menuboard/tv-balcao/").status_code == 403


def test_staff_visit_provisions_the_device(client, menuboard, django_user_model):
    """O provisionamento inteiro da TV: abrir logado deixa o dispositivo confiável."""
    from shopman.doorman.models import TrustedDevice

    client.force_login(_staff(django_user_model))
    client.get("/menuboard/tv-balcao/")

    device = TrustedDevice.objects.get(subject_type="display", subject_id="tv-balcao")
    assert device.is_valid

    # A TV continua abrindo depois, sem sessão nenhuma.
    _drop_session(client)
    resp = client.get("/menuboard/tv-balcao/")
    assert resp.status_code == 200


def test_provisioning_is_idempotent(client, menuboard, django_user_model):
    """Visita repetida não cria uma linha de TrustedDevice por acesso."""
    from shopman.doorman.models import TrustedDevice

    client.force_login(_staff(django_user_model))
    for _ in range(3):
        client.get("/menuboard/tv-balcao/")
    assert TrustedDevice.objects.filter(subject_type="display").count() == 1


def test_trust_of_another_board_does_not_open_this_one(client, menuboard, django_user_model):
    """A confiança carrega a ref: dispositivo de um quadro não abre outro."""
    display_channel("tv-outro", "Outro", collections=["paes"], prices_from="pdv")
    client.force_login(_staff(django_user_model))
    client.get("/menuboard/tv-outro/")  # provisiona só o OUTRO quadro
    _drop_session(client)

    assert client.get("/menuboard/tv-outro/").status_code == 200
    assert client.get("/menuboard/tv-balcao/").status_code == 403


def test_revoking_the_device_closes_the_board(client, menuboard, django_user_model):
    """A vantagem sobre token em URL: revogação existe, e é por dispositivo."""
    from shopman.doorman.models import TrustedDevice

    client.force_login(_staff(django_user_model))
    client.get("/menuboard/tv-balcao/")
    _drop_session(client)
    assert client.get("/menuboard/tv-balcao/").status_code == 200

    TrustedDevice.objects.filter(subject_type="display").update(is_active=False)
    assert client.get("/menuboard/tv-balcao/").status_code == 403


def test_public_escape_hatch_reopens(client, menuboard, settings):
    settings.SHOPMAN_MENUBOARD_PUBLIC = True
    assert client.get("/menuboard/tv-balcao/").status_code == 200


def test_unknown_ref_denies_before_revealing_existence(client, db):
    """A trava roda ANTES da checagem de existência: anônimo não descobre o que existe."""
    assert client.get("/menuboard/fantasma/").status_code == 403
    assert client.get("/menuboard/fantasma/data/").status_code == 403


def test_unknown_ref_is_404_once_authorized(client, db, django_user_model):
    client.force_login(_staff(django_user_model))
    assert client.get("/menuboard/fantasma/").status_code == 404
    assert client.get("/menuboard/fantasma/data/").status_code == 404


# ── A fonte do preço (ADR-018 §4) ──────────────────────────────────────────────
#
# O quadro deixou de ler `Product.base_price_q` e passou a ler o preço do canal
# apontado por `display.prices_from`. Com todos os canais cobrando igual isso não muda
# um centavo — foi verificado byte a byte contra a saída anterior. Estes testes criam a
# divergência de propósito, porque é o único jeito de provar que a fonte nova é a que
# manda; sem eles, o refactor passaria idêntico mesmo se tivesse ficado lendo a tabela.


@pytest.fixture
def diverging_pos(db, menuboard):
    """PDV cobra R$ 9,00 pelo pão que a tabela diz R$ 8,00."""
    from shopman.offerman.models import Listing, ListingItem

    listing = Listing.objects.create(ref="pdv", name="PDV")
    ListingItem.objects.create(listing=listing, product=menuboard["pao"], price_q=900)
    return listing


def test_board_shows_the_price_of_the_channel_it_points_at(diverging_pos, menuboard):
    board = build_menuboard("tv-balcao")
    pao = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao.price_q == 900, "o quadro tem de concordar com o caixa, não com a tabela"


def test_product_without_channel_price_falls_back_to_the_table(diverging_pos, menuboard):
    """Sem ListingItem no canal apontado, vale o de tabela — a mesma resposta do PDV."""
    board = build_menuboard("tv-balcao")
    bolo = next(i for g in board.groups for i in g.items if i.sku == "BOLO")
    assert bolo.price_q == 1200


def test_pointing_at_another_channel_changes_the_price_shown(menuboard):
    """A mesma TV, apontada para a loja online, mostra o preço da loja online."""
    from shopman.offerman.models import Listing, ListingItem

    from shopman.shop.models import Channel

    web = Listing.objects.create(ref="web", name="Loja online")
    ListingItem.objects.create(listing=web, product=menuboard["pao"], price_q=1100)

    channel = Channel.objects.get(ref="tv-balcao")
    channel.config = {**channel.config, "display": {**channel.config["display"], "prices_from": "web"}}
    channel.save(update_fields=["config"])

    board = build_menuboard("tv-balcao")
    pao = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao.price_q == 1100


def test_channel_without_a_price_source_still_renders(menuboard):
    """Config faltando não deixa a TV em branco: cai na tabela e o check W008 avisa."""
    from shopman.shop.models import Channel

    channel = Channel.objects.get(ref="tv-balcao")
    channel.config = {**channel.config, "display": {**channel.config["display"], "prices_from": ""}}
    channel.save(update_fields=["config"])

    board = build_menuboard("tv-balcao")
    pao = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao.price_q == 800
