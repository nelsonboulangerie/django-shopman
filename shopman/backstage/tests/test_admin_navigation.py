"""Contrato do menu lateral do Admin (WP-ADM-R0).

O menu é a única navegação do Admin (``show_all_applications: False``), então um
item que não resolve não é um detalhe cosmético: é uma tela que sumiu do alcance
do gestor. Foi exatamente o que aconteceu quando Promotion/Coupon/DeliveryZone
migraram de ``storefront`` para ``shop`` — o menu seguiu apontando para
``admin:storefront_*``, o helper devolvia ``"#"`` em silêncio e cinco telas de
configuração ficaram inalcançáveis sem que nenhum teste reclamasse.

O contrato tem duas metades, e a segunda é o que mantém o Admin enxuto: toda tela
registrada precisa ser alcançável. Registrar sem dar caminho cria a tela que existe
mas ninguém encontra — havia 41 delas. Se uma tela não merece caminho, também não
merece registro: o caminho é a curadoria, não esconder.

"Alcançável" tem duas portas desde que a configuração virou destino próprio: o menu
de operação e a tela de Configuração. A segunda é consultada na própria projection
que a monta — manter aqui uma cópia da lista seria criar a divergência que o teste
existe para impedir.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory

from shopman.backstage.admin.navigation import get_sidebar_navigation
from shopman.backstage.projections.settings_hub import settings_screen_urls

# Telas cuja porta é uma página própria, não a changelist crua. A chave é o model;
# o valor, a página que o apresenta melhor do que a tabela apresentaria.
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
def test_no_registered_screen_is_orphan():
    linked_paths = {
        item["link"].split("?")[0] for item in _menu_items(_superuser_request())
    }
    linked_paths |= {url.split("?")[0] for url in settings_screen_urls()}

    orphans = []
    for model in admin.site._registry:
        opts = model._meta
        key = f"{opts.app_label}.{opts.model_name}"
        if key in REACHED_BY_CUSTOM_PAGE:
            continue
        if f"/admin/{opts.app_label}/{opts.model_name}/" not in linked_paths:
            orphans.append(key)

    assert not orphans, (
        "telas registradas sem caminho — dê um item de menu, um cartão na "
        "Configuração, ou tire da curadoria: " + ", ".join(sorted(orphans))
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


@pytest.mark.django_db
def test_menu_makes_sense_without_any_operator_app_configured():
    """O menu de dev precisa fazer o mesmo sentido que o de produção.

    Os links dos apps do operador são condicionais: sem a URL do deployment eles
    somem, para não virarem link morto. Com "Alertas ativos" dentro do grupo, um
    ambiente sem app configurado (dev, por exemplo) mostrava um grupo chamado
    "Aplicativos" contendo um único item que não é aplicativo nenhum — o rótulo
    prometia uma coisa e entregava outra.

    Agora o grupo de apps só existe quando há app configurado, e o alarme saiu do
    menu: a home do Admin já mostra os alertas numa seção, e a lista deles é item
    normal de Auditoria.
    """
    from django.test import override_settings

    with override_settings(
        SHOPMAN_ORDERS_BASE_URL="",
        SHOPMAN_POS_BASE_URL="",
        SHOPMAN_KDS_BASE_URL="",
        SHOPMAN_PRODUCTION_BASE_URL="",
        SHOPMAN_PURCHASE_BASE_URL="",
    ):
        groups = get_sidebar_navigation(_superuser_request())

    apps_group = next((g for g in groups if g["title"] == "Aplicativos"), None)
    assert apps_group is not None
    assert apps_group["items"] == [], (
        "sem app configurado o grupo tem de ficar vazio (o Unfold então não o "
        f"desenha), mas veio {[i['title'] for i in apps_group['items']]}"
    )

    # A lista de alertas continua alcançável — em Auditoria, sem badge de alarme.
    auditoria = next(g for g in groups if g["title"] == "Auditoria")
    assert "Alertas do operador" in [item["title"] for item in auditoria["items"]]
    assert not any(
        item.get("badge")
        for group in groups
        for item in group["items"]
        if item["title"] == "Alertas do operador"
    ), "o alarme mora na home, não num badge permanente do menu"


@pytest.mark.django_db
def test_apps_group_holds_only_actual_apps():
    """Com as URLs configuradas, "Aplicativos" tem só o que É aplicativo."""
    from django.test import override_settings

    with override_settings(
        SHOPMAN_ORDERS_BASE_URL="https://gestor.example.com",
        SHOPMAN_POS_BASE_URL="https://pos.example.com",
        SHOPMAN_KDS_BASE_URL="https://kds.example.com",
        SHOPMAN_PRODUCTION_BASE_URL="https://prod.example.com",
        SHOPMAN_PURCHASE_BASE_URL="https://compras.example.com",
    ):
        groups = get_sidebar_navigation(_superuser_request())

    apps_group = next(g for g in groups if g["title"] == "Aplicativos")
    titles = [item["title"] for item in apps_group["items"]]

    assert titles == ["Pedidos", "Fechamento", "PDV", "KDS", "Produção ao vivo", "Compras"]
    assert "Alertas ativos" not in titles, "o alarme não é um aplicativo"
    for item in apps_group["items"]:
        assert item["link"].startswith("https://"), (
            f"{item['title']} deveria abrir um app fora do Admin: {item['link']}"
        )
