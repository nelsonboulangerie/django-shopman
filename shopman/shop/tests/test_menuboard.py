"""Menuboard — Feed (Showcase) de tipo menuboard, público e em tempo real."""

from __future__ import annotations

import pytest
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.models import Showcase
from shopman.shop.projections.menuboard import MenuboardError, build_menuboard


@pytest.fixture
def menuboard(db):
    Showcase.objects.create(
        ref="tv-balcao", name="Quadro do Balcão", kind="menuboard", collections=["paes", "doces"]
    )
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


def test_local_pause_drops_item_on_this_showcase(menuboard):
    """Pausa por-feed (options[paused_skus]) tira o item DESTE quadro."""
    sc = Showcase.objects.get(ref="tv-balcao")
    sc.options = {"paused_skus": ["PAO"]}
    sc.save(update_fields=["options"])
    board = build_menuboard("tv-balcao")
    pao = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao.available is False
    assert board.available_count == 1  # só o bolo; PAO segue globalmente vendável


def test_smart_collection_section(db):
    Showcase.objects.create(ref="tv", name="TV", kind="menuboard", collections=["caros"])
    Collection.objects.create(
        ref="caros", name="Caros", is_active=True,
        rule={"match": "all", "conditions": [{"field": "base_price_q", "op": "gte", "value": 1000}]},
    )
    Product.objects.create(sku="BOLO", name="Bolo", base_price_q=4500, is_published=True, is_sellable=True)
    Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    board = build_menuboard("tv")
    assert [i.sku for g in board.groups for i in g.items] == ["BOLO"]  # regra resolve a seção


def test_rejects_feed_showcase(db):
    Showcase.objects.create(ref="google", name="G", kind="google", collections=["x"])
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
    Showcase.objects.create(ref="tv-outro", name="Outro", kind="menuboard", collections=["paes"])
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
