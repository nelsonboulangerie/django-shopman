"""Leituras salvas (os favoritos do painel de filtros, WP-FASE2-UX-OPERADOR K4).

Por pessoa, por superfície e por tela; a tela declara a permissão e a gramática do
recorte (``api/saved_views.SCREENS``). E a ``backstage.0090`` leva os cenários do B.I.
(``BIView``) para o modelo genérico sem perder nenhum.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from shopman.backstage.api.saved_views import QueryError, screen_query
from shopman.backstage.models import SavedView

LIST = "api-backstage-saved-views"
HISTORY = {"surface": "orders", "screen": "history"}


def _user(username: str, *codenames: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for codename in codenames:
        app_label, code = codename.split(".")
        user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=code))
    return user


@pytest.fixture
def gestor(db):
    return _user("gestor-favoritos", "shop.manage_orders")


# ── a gramática do recorte de uma lista ──────────────────────────────────────


def test_screen_query_accepts_filters_period_and_group():
    query = screen_query(
        {
            "filters": {"payment": ["pix", "card"], "status": ["cancelled"]},
            "period": {"preset": "7d"},
            "group": "channel",
        }
    )
    assert query == {
        "filters": {"payment": ["pix", "card"], "status": ["cancelled"]},
        "period": {"from": "", "preset": "7d", "to": ""},
        "group": "channel",
    }
    assert screen_query({}) == {"filters": {}}


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {"hack": 1},
        {"filters": {"Status": ["x"]}},
        {"filters": {"status": "cancelled"}},
        {"filters": {"status": [1]}},
        {"filters": {"status": ["x" * 121]}},
        {"filters": {f"f{n}": [] for n in range(21)}},
        {"period": {"preset": "7d", "until": "x"}},
        {"group": "Canal"},
    ],
)
def test_screen_query_refuses_what_is_out_of_the_grammar(raw):
    with pytest.raises(QueryError):
        screen_query(raw)


# ── a API ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_save_list_pin_rename_and_delete(client, gestor):
    client.force_login(gestor)
    url = reverse(LIST)
    query = {"filters": {"status": ["cancelled"]}, "period": {"preset": "7d"}}

    saved = client.post(url, {**HISTORY, "name": "Cancelados da semana", "query": query}, content_type="application/json")
    assert saved.status_code == 200, saved.json()
    view = saved.json()["view"]
    assert view["query"]["filters"] == {"status": ["cancelled"]} and view["pinned"] is False

    # Mesmo nome na mesma tela atualiza; o fixado vem no POST quando dito.
    again = client.post(
        url,
        {**HISTORY, "name": "Cancelados da semana", "query": {"filters": {"status": ["returned"]}}, "pinned": True},
        content_type="application/json",
    )
    assert again.json()["view"]["id"] == view["id"] and again.json()["view"]["pinned"] is True
    assert SavedView.objects.count() == 1

    # A lista é da tela pedida: o mesmo dono em outra tela não aparece.
    client.post(url, {"surface": "orders", "screen": "queue", "name": "Só iFood", "query": {}}, content_type="application/json")
    names = [row["name"] for row in client.get(url, HISTORY).json()["views"]]
    assert names == ["Cancelados da semana"]

    detail = reverse("api-backstage-saved-view", kwargs={"pk": view["id"]})
    renamed = client.patch(detail, {"name": "Devolvidos"}, content_type="application/json")
    assert renamed.json()["view"]["name"] == "Devolvidos"
    assert client.patch(detail, {}, content_type="application/json").status_code == 400
    assert client.patch(detail, {"name": "  "}, content_type="application/json").status_code == 400

    assert client.delete(detail).status_code == 200
    assert client.get(url, HISTORY).json()["views"] == []


@pytest.mark.django_db
def test_rename_onto_an_existing_name_is_refused_without_losing_either(client, gestor):
    client.force_login(gestor)
    url = reverse(LIST)
    first = client.post(url, {**HISTORY, "name": "A", "query": {}}, content_type="application/json").json()["view"]
    client.post(url, {**HISTORY, "name": "B", "query": {}}, content_type="application/json")
    detail = reverse("api-backstage-saved-view", kwargs={"pk": first["id"]})
    clash = client.patch(detail, {"name": "B"}, content_type="application/json")
    assert clash.status_code == 400 and clash.json()["field"] == "name"
    assert sorted(SavedView.objects.values_list("name", flat=True)) == ["A", "B"]


@pytest.mark.django_db
def test_unknown_screen_bad_query_and_missing_name_are_refused(client, gestor):
    client.force_login(gestor)
    url = reverse(LIST)
    unknown = client.post(url, {"surface": "orders", "screen": "nope", "name": "X", "query": {}}, content_type="application/json")
    assert unknown.status_code == 400 and unknown.json()["field"] == "screen"
    assert client.get(url, {"surface": "orders"}).status_code == 400
    bad = client.post(url, {**HISTORY, "name": "X", "query": {"hack": 1}}, content_type="application/json")
    assert bad.status_code == 400 and bad.json()["field"] == "query"
    nameless = client.post(url, {**HISTORY, "name": " ", "query": {}}, content_type="application/json")
    assert nameless.status_code == 400 and nameless.json()["field"] == "name"


@pytest.mark.django_db
def test_screen_permission_is_the_permission_of_who_reads_the_screen(client, gestor):
    client.force_login(gestor)
    url = reverse(LIST)
    catalog = {"surface": "orders", "screen": "catalog"}
    # Quem gerencia pedidos e não o catálogo não guarda favorito do catálogo.
    assert client.get(url, catalog).status_code == 403
    assert client.get(url, {"surface": "bi", "screen": "explore"}).status_code == 403


@pytest.mark.django_db
def test_someone_elses_favorite_does_not_exist(client, gestor):
    client.force_login(gestor)
    view = client.post(reverse(LIST), {**HISTORY, "name": "Meu", "query": {}}, content_type="application/json").json()["view"]
    other = _user("outro-gestor", "shop.manage_orders")
    client.force_login(other)
    detail = reverse("api-backstage-saved-view", kwargs={"pk": view["id"]})
    assert client.get(reverse(LIST), HISTORY).json()["views"] == []
    assert client.patch(detail, {"pinned": True}, content_type="application/json").status_code == 404
    assert client.delete(detail).status_code == 404
    assert SavedView.objects.filter(pk=view["id"]).exists()


# ── a migração: os cenários do B.I. viram leituras salvas, sem perder nenhum ──

BEFORE = [("backstage", "0089_alerta_responder_ate")]
AFTER = [("backstage", "0090_saved_view")]


@pytest.fixture
def _leave_the_schema_at_the_head():
    yield
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_bi_scenarios_become_saved_views_and_come_back(_leave_the_schema_at_the_head):
    ana = User.objects.create(username="ana-bi")
    bia = User.objects.create(username="bia-bi")
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    old = executor.loader.project_state(BEFORE).apps
    BIView = old.get_model("backstage", "BIView")
    config = {"metric": "loss", "by": "defect", "by2": "", "window": {"preset": "28d"}}
    BIView.objects.create(owner_id=ana.pk, name="Perda por defeito", config=config, is_favorite=True)
    BIView.objects.create(owner_id=ana.pk, name="Por dia", config={**config, "by": "time"})
    BIView.objects.create(owner_id=bia.pk, name="Perda por defeito", config=config)

    executor = MigrationExecutor(connection)
    executor.migrate(AFTER)
    new = executor.loader.project_state(AFTER).apps
    Saved = new.get_model("backstage", "SavedView")
    rows = sorted(
        (row.owner_id, row.surface, row.screen, row.name, row.pinned, row.query == config)
        for row in Saved.objects.all()
    )
    assert rows == sorted(
        [
            (ana.pk, "bi", "explore", "Perda por defeito", True, True),
            (ana.pk, "bi", "explore", "Por dia", False, False),
            (bia.pk, "bi", "explore", "Perda por defeito", False, True),
        ]
    )

    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    back = executor.loader.project_state(BEFORE).apps.get_model("backstage", "BIView")
    assert back.objects.count() == 3
    assert back.objects.get(owner_id=ana.pk, name="Perda por defeito").is_favorite is True
