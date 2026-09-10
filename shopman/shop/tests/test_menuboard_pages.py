"""Menuboard — rotação de páginas: cada página uma tela, na mesma TV.

O servidor pagina (``build_menuboard`` → ``pages``) e dita a cadência
(``rotate_seconds``); o Alpine só avança o ponteiro. ``groups`` segue completo:
é a pintura do servidor, que falha aberta mostrando o cardápio inteiro.
"""

from __future__ import annotations

import pytest
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.projections.menuboard import build_menuboard
from shopman.shop.tests._display import display_channel


def _collection(ref, name, sort_order, skus):
    coll = Collection.objects.create(ref=ref, name=name, is_active=True, sort_order=sort_order)
    for sku in skus:
        product = Product.objects.create(
            sku=sku, name=sku.title(), unit="un", base_price_q=1000,
            is_published=True, is_sellable=True,
        )
        CollectionItem.objects.create(collection=coll, product=product)
    return coll


@pytest.fixture
def catalog(db):
    """Três seções: 3 + 2 + 2 itens, na ordem paes → doces → bebidas."""
    _collection("paes", "Pães", 1, ["pao-1", "pao-2", "pao-3"])
    _collection("doces", "Doces", 2, ["doce-1", "doce-2"])
    _collection("bebidas", "Bebidas", 3, ["beb-1", "beb-2"])


def _titles(page):
    return [g.title for g in page.groups]


# ── Sem rotação (comportamento clássico) ────────────────────────────────────────


def test_default_is_a_single_page_with_everything(catalog):
    display_channel("tv", "TV", collections=["paes", "doces", "bebidas"], prices_from="pdv")
    board = build_menuboard("tv")
    assert board.rotate_seconds == 0
    assert len(board.pages) == 1
    assert _titles(board.pages[0]) == ["Pães", "Doces", "Bebidas"]


# ── Paginação ───────────────────────────────────────────────────────────────────


def test_whole_sections_pack_until_the_limit(catalog):
    """Seções entram inteiras: 3+2 cabem em 5; a terceira abre página nova."""
    display_channel(
        "tv", "TV", collections=["paes", "doces", "bebidas"], prices_from="pdv",
        rotate_seconds=10, items_per_page=5,
    )
    board = build_menuboard("tv")
    assert board.rotate_seconds == 10
    assert [_titles(p) for p in board.pages] == [["Pães", "Doces"], ["Bebidas"]]


def test_section_that_does_not_fit_opens_a_new_page(catalog):
    """Teto 4: Pães (3) + Doces (2) não cabem juntos — Doces desce de página."""
    display_channel(
        "tv", "TV", collections=["paes", "doces", "bebidas"], prices_from="pdv",
        rotate_seconds=10, items_per_page=4,
    )
    board = build_menuboard("tv")
    assert [_titles(p) for p in board.pages] == [["Pães"], ["Doces", "Bebidas"]]


def test_section_bigger_than_the_limit_splits_with_continuation(db):
    """Seção maior que o teto quebra em partes com o mesmo título + sufixo."""
    _collection("paes", "Pães", 1, ["p1", "p2", "p3", "p4", "p5"])
    _collection("doces", "Doces", 2, ["d1"])
    display_channel(
        "tv", "TV", collections=["paes", "doces"], prices_from="pdv",
        rotate_seconds=10, items_per_page=2,
    )
    board = build_menuboard("tv")
    assert [_titles(p) for p in board.pages] == [["Pães"], ["Pães (cont.)"], ["Pães (cont.)", "Doces"]]
    # nada se perde na quebra: os 6 itens seguem no quadro, na ordem
    skus = [i.sku for p in board.pages for g in p.groups for i in g.items]
    assert skus == ["p1", "p2", "p3", "p4", "p5", "d1"]


def test_groups_stay_complete_for_the_server_paint(catalog):
    """`groups` não pagina: é a pintura do servidor, que falha aberta."""
    display_channel(
        "tv", "TV", collections=["paes", "doces", "bebidas"], prices_from="pdv",
        rotate_seconds=10, items_per_page=2,
    )
    board = build_menuboard("tv")
    assert [g.title for g in board.groups] == ["Pães", "Doces", "Bebidas"]
    assert len(board.pages) > 1


# ── Config incoerente falha ABERTA ──────────────────────────────────────────────


def test_limit_without_rotation_does_not_hide_the_menu(catalog):
    """Teto sem cadência deixaria a TV parada na 1ª tela, escondendo o resto.

    O validate() recusa a combinação, mas config é JSONField editável por fora:
    a projection falha aberta — página única com tudo.
    """
    display_channel(
        "tv", "TV", collections=["paes", "doces", "bebidas"], prices_from="pdv",
        rotate_seconds=0, items_per_page=2,
    )
    board = build_menuboard("tv")
    assert len(board.pages) == 1
    assert board.rotate_seconds == 0


def test_rotation_without_limit_is_a_single_page(catalog):
    display_channel(
        "tv", "TV", collections=["paes", "doces", "bebidas"], prices_from="pdv",
        rotate_seconds=10, items_per_page=0,
    )
    board = build_menuboard("tv")
    assert len(board.pages) == 1
    assert board.rotate_seconds == 0


def test_garbage_config_values_degrade_to_off(catalog):
    display_channel("tv", "TV", collections=["paes"], prices_from="pdv")
    from shopman.shop.models import Channel

    channel = Channel.objects.get(ref="tv")
    channel.config["display"]["rotate_seconds"] = "dez"
    channel.config["display"]["items_per_page"] = -3
    channel.save(update_fields=["config"])
    board = build_menuboard("tv")
    assert board.rotate_seconds == 0
    assert len(board.pages) == 1


# ── A view JSON carrega a rotação ───────────────────────────────────────────────


def test_data_view_serializes_pages_and_cadence(client, catalog, django_user_model):
    display_channel(
        "tv", "TV", collections=["paes", "doces", "bebidas"], prices_from="pdv",
        rotate_seconds=15, items_per_page=5,
    )
    staff = django_user_model.objects.create_user("gestor", password="x", is_staff=True)
    client.force_login(staff)
    data = client.get("/menuboard/tv/data/").json()
    assert data["rotate_seconds"] == 15
    assert [[g["title"] for g in p["groups"]] for p in data["pages"]] == [
        ["Pães", "Doces"], ["Bebidas"],
    ]
