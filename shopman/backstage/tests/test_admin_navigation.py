"""Contrato do menu lateral do Admin (WP-ADM-R0).

O menu é a única navegação do Admin (``show_all_applications: False``), então um
item que não resolve não é um detalhe cosmético: é uma tela que sumiu do alcance
do gestor. Foi exatamente o que aconteceu quando Promotion/Coupon/DeliveryZone
migraram de ``storefront`` para ``shop`` — o menu seguiu apontando para
``admin:storefront_*``, o helper devolvia ``"#"`` em silêncio e cinco telas de
configuração ficaram inalcançáveis sem que nenhum teste reclamasse.

O contrato tem duas metades, e a segunda é o que mantém o Admin enxuto: toda tela
registrada precisa estar no menu. Registrar sem dar caminho cria a tela que existe
mas ninguém encontra — havia 41 delas. Se uma tela não merece lugar no menu,
também não merece registro: o caminho é a curadoria, não esconder.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory

from shopman.backstage.admin.navigation import get_sidebar_navigation

# Telas cuja porta no menu é uma página própria, não a changelist crua. A chave é
# o model; o valor, a página que o apresenta melhor do que a tabela apresentaria.
REACHED_BY_CUSTOM_PAGE = {
    "shop.omotenashicopy": "Textos da interface (/admin/settings/copy/)",
}


def _superuser_request():
    request = RequestFactory().get("/admin/")
    request.user = User(username="nav-admin", is_staff=True, is_superuser=True)
    return request


def _menu_items(request) -> list[dict]:
    return [item for group in get_sidebar_navigation(request) for item in group["items"]]


@pytest.mark.django_db
def test_every_menu_link_resolves():
    """Nenhum item de menu pode apontar para lugar nenhum."""
    broken = [
        item["title"]
        for item in _menu_items(_superuser_request())
        if not item["link"] or item["link"] == "#"
    ]
    assert not broken, f"itens de menu sem destino: {broken}"


@pytest.mark.django_db
def test_no_registered_screen_is_orphan_from_the_menu():
    linked_paths = {
        item["link"].split("?")[0] for item in _menu_items(_superuser_request())
    }

    orphans = []
    for model in admin.site._registry:
        opts = model._meta
        key = f"{opts.app_label}.{opts.model_name}"
        if key in REACHED_BY_CUSTOM_PAGE:
            continue
        if f"/admin/{opts.app_label}/{opts.model_name}/" not in linked_paths:
            orphans.append(key)

    assert not orphans, (
        "telas registradas fora do menu — dê um item de menu ou tire da curadoria: "
        + ", ".join(sorted(orphans))
    )


@pytest.mark.django_db
def test_groups_stay_short_enough_to_scan():
    """Grupo longo é onde a busca visual falha e a pessoa desiste.

    O limite não é estético: o antigo "Configurações" juntava vinte itens de sete
    assuntos diferentes, e era exatamente ali que nada era encontrado. Um grupo
    que cresce demais está pedindo para virar dois.
    """
    oversized = {
        group["title"]: len(group["items"])
        for group in get_sidebar_navigation(_superuser_request())
        if len(group["items"]) > 11
    }

    assert not oversized, f"grupos longos demais para escanear: {oversized}"
