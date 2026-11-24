"""O "Separado" da Preparação mora no servidor (WP-F09a, #3524; D-042, item 5).

A marca é presa ao item e à data, e à quantidade do momento: vale para todos os
tablets do dia, cai quando a quantidade daquele item muda (e só então), guarda quem
marcou pelo PIN, desmarcar grava, dois tablets ao mesmo tempo dão uma marca só, cada
gesto avisa a grade pelo SSE da produção, e a estação autônoma (o Letreiro) só lê.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem

from shopman.backstage import station_trust
from shopman.backstage.models import PrepChecklistMark
from shopman.backstage.services import prep_checklist
from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db

User = get_user_model()
URL = "api-backstage-production-prep-checklist"


@pytest.fixture
def pao(db):
    recipe = Recipe.objects.create(ref="pao-frances", name="Pão Francês", output_sku="PAO-FRANCES", batch_size=10)
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity="5", unit="kg")
    RecipeItem.objects.create(recipe=recipe, input_sku="SAL-REFINADO", quantity="0.1", unit="kg")
    RecipeItem.objects.create(recipe=recipe, input_sku="FERMENTO", quantity="0.05", unit="kg")
    return recipe


@pytest.fixture
def brioche(db):
    recipe = Recipe.objects.create(ref="brioche", name="Brioche", output_sku="BRIOCHE", batch_size=10)
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity="4", unit="kg")
    RecipeItem.objects.create(recipe=recipe, input_sku="OVOS", quantity="20", unit="un")
    return recipe


def _cook(username: str, first_name: str):
    user = User.objects.create_user(username, password="pw", is_staff=True, first_name=first_name)
    return User.objects.get(pk=grant_production_operator(user).pk)


@pytest.fixture
def ana(db):
    return _cook("ana-cozinha", "Ana")


@pytest.fixture
def bia(db):
    return _cook("bia-cozinha", "Bia")


@pytest.fixture
def sse(monkeypatch):
    sent: list[tuple] = []
    from shopman.shop.handlers import _sse_emitters

    monkeypatch.setattr(
        _sse_emitters,
        "_emit_backstage",
        # Só os gestos do Separado: planejar o lote também avisa a grade.
        lambda kind, event_type, payload, *, scope=None: (
            sent.append((kind, event_type, payload)) if payload.get("kind") == "prep_checklist" else None
        ),
    )
    return sent


def _quantity(sku: str, today: date | None = None) -> str:
    current = prep_checklist.current_quantities(selected_date=today or date.today())
    (value,) = current[sku]
    return value


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _mark(client, item_ref: str, quantity: str, *, checked: bool = True, day: date | None = None):
    return client.post(
        reverse(URL),
        {"date": (day or date.today()).isoformat(), "item_ref": item_ref, "quantity": quantity, "checked": checked},
        format="json",
    )


def _marks(client, day: date | None = None) -> dict[str, dict]:
    response = client.get(reverse(URL), {"date": (day or date.today()).isoformat()})
    assert response.status_code == 200, response.content
    return {mark["item_ref"]: mark for mark in response.json()["marks"]}


class TestRoteiroPelaApi:
    def test_tres_insumos_marcados_num_tablet_aparecem_no_outro_com_quem_e_a_hora(self, pao, ana, bia, sse):
        craft.plan(pao, 20, date=date.today())
        tablet_a, tablet_b = _client(ana), _client(bia)

        for sku in ("FARINHA", "SAL-REFINADO", "FERMENTO"):
            response = _mark(tablet_a, sku, _quantity(sku))
            assert response.status_code == 200, response.content
            assert response.json()["mark"]["marked_by"] == "Ana"

        seen = _marks(tablet_b)
        assert set(seen) == {"FARINHA", "SAL-REFINADO", "FERMENTO"}
        assert seen["FARINHA"]["quantity"] == "10000 g"
        assert {mark["marked_by"] for mark in seen.values()} == {"Ana"}
        assert all(mark["marked_at"] for mark in seen.values())

        response = _mark(tablet_b, "SAL-REFINADO", "", checked=False)
        assert response.status_code == 200, response.content
        assert response.json()["mark"] is None
        assert {mark["item_ref"] for mark in response.json()["marks"]} == {"FARINHA", "FERMENTO"}
        assert set(_marks(tablet_a)) == {"FARINHA", "FERMENTO"}
        assert len(sse) == 4
        assert all(kind == "production" and event == "backstage-production-update" for kind, event, _ in sse)
        assert sse[-1][2] == {
            "kind": "prep_checklist",
            "date": date.today().isoformat(),
            "item_ref": "SAL-REFINADO",
            "checked": False,
        }

    def test_marca_presa_a_data(self, pao, ana):
        craft.plan(pao, 20, date=date.today())
        tomorrow = date.today() + timedelta(days=1)
        craft.plan(pao, 20, date=tomorrow)
        client = _client(ana)
        assert _mark(client, "FARINHA", _quantity("FARINHA")).status_code == 200

        assert set(_marks(client)) == {"FARINHA"}
        assert _marks(client, tomorrow) == {}


class TestQuantidadeDoMomento:
    def test_a_marca_cai_quando_a_quantidade_daquele_item_muda_e_so_entao(self, pao, brioche, ana):
        craft.plan(pao, 20, date=date.today())
        client = _client(ana)
        for sku in ("FARINHA", "SAL-REFINADO"):
            assert _mark(client, sku, _quantity(sku)).status_code == 200

        # Um lote de brioche soma farinha (e traz ovos); o sal não muda.
        craft.plan(brioche, 10, date=date.today())

        assert set(_marks(client)) == {"SAL-REFINADO"}
        mark = PrepChecklistMark.objects.get(item_ref="FARINHA")
        assert mark.checked  # não apagou: a marca guardada é de outra quantidade

    def test_marcar_olhando_uma_lista_velha_recebe_a_quantidade_de_agora(self, pao, ana):
        craft.plan(pao, 20, date=date.today())
        client = _client(ana)

        response = _mark(client, "FARINHA", "9000 g")

        assert response.status_code == 409
        body = response.json()
        assert body["field"] == "quantity"
        assert body["current_quantities"] == ["10000 g"]
        assert "10000 g" in body["detail"]
        assert not PrepChecklistMark.objects.exists()

    def test_item_que_saiu_da_preparacao_nao_marca(self, pao, ana):
        craft.plan(pao, 20, date=date.today())
        response = _mark(_client(ana), "MANTEIGA", "100 g")
        assert response.status_code == 409
        assert response.json()["current_quantities"] == []

    def test_ingrediente_de_um_preparo_marca_pela_chave_do_preparo(self, pao, ana):
        craft.plan(pao, 20, date=date.today())
        current = prep_checklist.current_quantities(selected_date=date.today())
        prep_item = prep_checklist.item_ref_for_prep_ingredient("pao-frances", "FARINHA")
        assert prep_item in current
        (quantity,) = current[prep_item]

        client = _client(ana)
        assert _mark(client, prep_item, quantity).status_code == 200
        assert set(_marks(client)) == {prep_item}


class TestHistoriaEConcorrencia:
    def test_desmarcar_grava_e_guarda_a_historia(self, pao, ana, bia):
        craft.plan(pao, 20, date=date.today())
        quantity = _quantity("FARINHA")
        prep_checklist.set_mark(
            selected_date=date.today(), item_ref="FARINHA", quantity=quantity, checked=True, user=ana
        )
        prep_checklist.set_mark(selected_date=date.today(), item_ref="FARINHA", quantity="", checked=False, user=bia)
        prep_checklist.set_mark(
            selected_date=date.today(), item_ref="FARINHA", quantity=quantity, checked=True, user=ana
        )

        mark = PrepChecklistMark.objects.get(item_ref="FARINHA")
        assert mark.checked and mark.marked_by == ana and mark.marked_by_name == "Ana"
        assert [(step["checked"], step["by"]) for step in mark.history] == [
            (True, "Ana"),
            (False, "Bia"),
            (True, "Ana"),
        ]

    def test_dois_tablets_marcando_o_mesmo_item_dao_uma_marca_so(self, pao, ana, bia, sse):
        craft.plan(pao, 20, date=date.today())
        quantity = _quantity("FARINHA")
        first = prep_checklist.set_mark(
            selected_date=date.today(), item_ref="FARINHA", quantity=quantity, checked=True, user=ana
        )
        second = prep_checklist.set_mark(
            selected_date=date.today(), item_ref="FARINHA", quantity=quantity, checked=True, user=bia
        )

        assert first == second
        mark = PrepChecklistMark.objects.get(item_ref="FARINHA")
        assert mark.marked_by_name == "Ana"
        assert len(mark.history) == 1
        assert len(sse) == 1

    def test_corrida_na_criacao_fica_com_a_linha_que_chegou_primeiro(self, pao, ana, bia, monkeypatch):
        craft.plan(pao, 20, date=date.today())
        quantity = _quantity("FARINHA")
        prep_checklist.set_mark(
            selected_date=date.today(), item_ref="FARINHA", quantity=quantity, checked=True, user=ana
        )

        # O tablet B leu "não existe" um instante antes de A gravar.
        real_locked = prep_checklist._locked_mark
        calls = {"n": 0}

        def stale_then_real(selected_date, item_ref):
            calls["n"] += 1
            return None if calls["n"] == 1 else real_locked(selected_date, item_ref)

        monkeypatch.setattr(prep_checklist, "_locked_mark", stale_then_real)
        view = prep_checklist.set_mark(
            selected_date=date.today(), item_ref="FARINHA", quantity=quantity, checked=True, user=bia
        )

        assert PrepChecklistMark.objects.count() == 1
        assert view.marked_by == "Ana"

    def test_desmarcar_o_que_nunca_foi_marcado_nao_grava(self, pao, ana, sse):
        craft.plan(pao, 20, date=date.today())
        assert (
            prep_checklist.set_mark(
                selected_date=date.today(), item_ref="FARINHA", quantity="", checked=False, user=ana
            )
            is None
        )
        assert not PrepChecklistMark.objects.exists()
        assert sse == []


class TestQuemPode:
    def test_o_letreiro_so_le(self, pao, ana, monkeypatch):
        craft.plan(pao, 20, date=date.today())
        client = _client(ana)
        assert _mark(client, "FARINHA", _quantity("FARINHA")).status_code == 200

        monkeypatch.setattr(station_trust, "station_mode", lambda request: station_trust.AUTONOMOUS)
        response = _mark(client, "SAL-REFINADO", _quantity("SAL-REFINADO"))

        assert response.status_code == 403
        assert set(_marks(client)) == {"FARINHA"}
        assert not PrepChecklistMark.objects.filter(item_ref="SAL-REFINADO").exists()

    def test_sem_a_preparacao_nao_le_nem_marca(self, pao):
        craft.plan(pao, 20, date=date.today())
        stranger = User.objects.create_user("sem-producao", password="pw", is_staff=True)
        client = _client(stranger)

        assert client.get(reverse(URL)).status_code == 403
        assert _mark(client, "FARINHA", "10000 g").status_code == 403

    def test_item_mal_formado_e_400(self, pao, ana):
        craft.plan(pao, 20, date=date.today())
        response = _mark(_client(ana), "A/B/C", "1 g")
        assert response.status_code == 400
        assert response.json()["field"] == "item_ref"
