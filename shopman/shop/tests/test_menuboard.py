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
# O menuboard deixou de ser público (ADR-018 §5.1): o preço dele vem do PDV, e
# preço alcançável publicamente é preço a honrar. Duas credenciais valem — sessão
# de staff (gente) e token de quiosque na URL (TV na parede).


def _kiosk_url(ref: str, suffix: str = "") -> str:
    from shopman.shop.menuboard_access import KIOSK_PARAM, make_kiosk_token

    return f"/menuboard/{ref}/{suffix}?{KIOSK_PARAM}={make_kiosk_token(ref)}"


def test_page_denies_anonymous(client, menuboard):
    assert client.get("/menuboard/tv-balcao/").status_code == 403


def test_data_denies_anonymous(client, menuboard):
    assert client.get("/menuboard/tv-balcao/data/").status_code == 403


def test_page_with_kiosk_token(client, menuboard):
    resp = client.get(_kiosk_url("tv-balcao"))
    assert resp.status_code == 200
    assert "Quadro do Balcão".encode() in resp.content
    assert b"menuboard()" in resp.content


def test_data_with_kiosk_token(client, menuboard):
    resp = client.get(_kiosk_url("tv-balcao", "data/"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["ref"] == "tv-balcao"
    assert body["available_count"] == 2
    assert [g["title"] for g in body["groups"]] == ["Pães", "Doces"]


def test_token_of_another_board_is_refused(client, menuboard):
    """Token carrega a ref: o do quadro do balcão não abre outro quadro."""
    from shopman.shop.menuboard_access import KIOSK_PARAM, make_kiosk_token

    other = make_kiosk_token("tv-balcao")
    assert client.get(f"/menuboard/outro/?{KIOSK_PARAM}={other}").status_code == 403


def test_tampered_token_is_refused(client, menuboard):
    from shopman.shop.menuboard_access import KIOSK_PARAM, make_kiosk_token

    bad = make_kiosk_token("tv-balcao") + "x"
    assert client.get(f"/menuboard/tv-balcao/?{KIOSK_PARAM}={bad}").status_code == 403


def test_staff_session_opens_without_token(client, menuboard, django_user_model):
    staff = django_user_model.objects.create_user("gestor", password="x", is_staff=True)
    client.force_login(staff)
    assert client.get("/menuboard/tv-balcao/").status_code == 200


def test_non_staff_user_is_refused(client, menuboard, django_user_model):
    user = django_user_model.objects.create_user("cliente", password="x")
    client.force_login(user)
    assert client.get("/menuboard/tv-balcao/").status_code == 403


def test_public_escape_hatch_reopens(client, menuboard, settings):
    settings.SHOPMAN_MENUBOARD_PUBLIC = True
    assert client.get("/menuboard/tv-balcao/").status_code == 200


def test_unknown_ref_denies_before_revealing_existence(client, db):
    """A trava roda ANTES da checagem de existência: anônimo não descobre o que existe."""
    assert client.get("/menuboard/fantasma/").status_code == 403
    assert client.get("/menuboard/fantasma/data/").status_code == 403


def test_unknown_ref_is_404_once_authorized(client, db, django_user_model):
    staff = django_user_model.objects.create_user("gestor", password="x", is_staff=True)
    client.force_login(staff)
    assert client.get("/menuboard/fantasma/").status_code == 404
    assert client.get("/menuboard/fantasma/data/").status_code == 404
