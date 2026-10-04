"""PDV › Ajustes › Salão: a planta das mesas, a regra de tempo e o registro.

Decisão do dono (04/10/2026): quem opera o PDV redesenha o salão, e toda
mudança fica registrada (quem, quando, o quê, antes e depois). O B.I. mede a
lotação com o mesmo cadastro, então mudar lugares ou a capacidade vale de hoje
em diante e não reescreve os dias de antes.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.cashman.models import Shift

from shopman.backstage.models import SeatingSpot, SpotKind, SpotShape
from shopman.backstage.services import seating
from shopman.backstage.services.room import capacity_on
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Shop

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_loja")]

URL = "/api/v1/backstage/pos/seating/"


@pytest.fixture
def _loja():
    return Shop.objects.create(name="Nelson", brand_name="Nelson")


def _user(username, *codenames):
    user = get_user_model().objects.create_user(username, password="x", is_staff=True,
                                                first_name=username.title())
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)


@pytest.fixture
def operador():
    return _user("bruna", "operate_pos")


@pytest.fixture
def salao():
    long_ago = timezone.localdate() - timedelta(days=200)
    return {
        "m1": SeatingSpot.objects.create(ref="mesa-1", label="Mesa 1", short_label="M1", area="Salão interno",
                                         shape=SpotShape.ROUND, seats=2, plan_x=40, plan_y=40,
                                         active_from=long_ago),
        "m2": SeatingSpot.objects.create(ref="mesa-2", label="Mesa 2", short_label="M2", area="Salão interno",
                                         shape=SpotShape.SQUARE, seats=4, plan_x=160, plan_y=40),
        "b1": SeatingSpot.objects.create(ref="balcao-1", label="Balcão 1", kind=SpotKind.COUNTER,
                                         shape=SpotShape.STOOL, area="Balcão", seats=1),
        "velha": SeatingSpot.objects.create(ref="mesa-velha", label="Mesa velha", seats=2,
                                            active_until=long_ago),
    }


def _read(client):
    response = client.get(URL)
    assert response.status_code == 200, response.content
    return response.json()


def _save(client, body):
    return client.post(URL, data=json.dumps(body), content_type="application/json")


def _entries():
    ct = ContentType.objects.get_for_model(SeatingSpot)
    return [json.loads(entry.change_message) | {"_user": entry.user.username}
            for entry in LogEntry.objects.filter(content_type=ct).order_by("pk")]


# ── Leitura ─────────────────────────────────────────────────────────────


def test_a_planta_mostra_so_as_mesas_de_hoje_com_o_total_do_bi(client, operador, salao):
    client.force_login(operador)
    data = _read(client)

    refs = [spot["ref"] for spot in data["spots"]]
    assert sorted(refs) == ["balcao-1", "mesa-1", "mesa-2"]  # a que saiu não aparece
    assert data["totals"] == {"capacity_seats": 7, "capacity_spots": 3, "extra_seats": 0}
    mesa = next(spot for spot in data["spots"] if spot["ref"] == "mesa-1")
    assert mesa["shape"] == "round"
    assert (mesa["plan_x"], mesa["plan_y"]) == (40, 40)
    assert mesa["since"] == salao["m1"].active_from.isoformat()
    assert {shape["value"] for shape in data["shapes"]} == {"round", "square", "long", "stool"}
    assert data["revision"]


def test_sem_operador_nao_le_e_sem_permissao_recusa(client, salao):
    assert client.get(URL).status_code in (401, 403)

    client.force_login(_user("visita"))
    response = client.get(URL)
    assert response.status_code == 403
    assert response.json()["detail"] == "Operador sem permissão para esta ação."


def test_estacao_travada_pede_identificacao(client, salao):
    trust_station(client)
    response = client.get(URL)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "station_locked"


# ── Desenho: muda no lugar ──────────────────────────────────────────────


def test_mover_e_trocar_a_forma_muda_no_lugar_e_fica_registrado(client, operador, salao):
    client.force_login(operador)
    revision = _read(client)["revision"]

    response = _save(client, {"revision": revision, "spots": [
        {"ref": "mesa-1", "plan_x": 300, "plan_y": 120, "rotation": 90, "shape": "square"},
    ]})

    assert response.status_code == 200, response.content
    assert response.json()["saved"] == {"changed": 1, "created": 0, "versioned": 0, "removed": 0}
    salao["m1"].refresh_from_db()
    assert (salao["m1"].plan_x, salao["m1"].plan_y, salao["m1"].rotation) == (300, 120, 90)
    assert salao["m1"].shape == "square"
    assert salao["m1"].active_until is None  # desenho não versiona
    assert SeatingSpot.objects.count() == 4

    [entry] = _entries()
    assert entry["_user"] == "bruna"
    assert entry["action"] == "seating.spot.change"
    assert entry["before"] == {"shape": "round", "plan_x": 40, "plan_y": 40, "rotation": 0}
    assert entry["after"] == {"shape": "square", "plan_x": 300, "plan_y": 120, "rotation": 90}

    history = response.json()["history"]
    assert history[0]["who"] == "Bruna"
    assert "forma de Redonda para Quadrada" in history[0]["summary"]
    assert "mudou de lugar na planta" in history[0]["summary"]


# ── Medida: vale de hoje em diante ──────────────────────────────────────


def test_mudar_lugares_versiona_a_mesa_e_o_passado_nao_muda(client, operador, salao):
    client.force_login(operador)
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    spots = list(SeatingSpot.objects.all())
    capacity_yesterday = capacity_on(yesterday, spots)

    response = _save(client, {"revision": _read(client)["revision"], "spots": [
        {"ref": "mesa-1", "seats": 4, "counts_in_capacity": False, "plan_x": 90},
    ]})

    assert response.status_code == 200, response.content
    assert response.json()["saved"]["versioned"] == 1
    salao["m1"].refresh_from_db()
    assert salao["m1"].active_until == yesterday
    assert salao["m1"].seats == 2 and salao["m1"].counts_in_capacity is True  # o passado fica
    nova = salao["m1"].replaced_by
    assert nova.active_from == today
    assert (nova.seats, nova.counts_in_capacity, nova.plan_x, nova.label) == (4, False, 90, "Mesa 1")

    spots = list(SeatingSpot.objects.all())
    assert capacity_on(yesterday, spots) == capacity_yesterday  # ontem segue igual
    assert capacity_on(today, spots) == capacity_yesterday - 1  # hoje a mesa é extra

    data = response.json()
    mesa = next(spot for spot in data["spots"] if spot["ref"] == nova.ref)
    assert mesa["since"] == salao["m1"].active_from.isoformat()  # "existe desde" atravessa versões
    assert data["totals"]["extra_seats"] == 4

    [entry] = _entries()
    assert entry["action"] == "seating.spot.version"
    assert entry["replaces"] == "mesa-1"
    assert entry["before"]["seats"] == 2 and entry["after"]["seats"] == 4


def test_mesa_nascida_hoje_muda_no_lugar_ate_na_medida(client, operador, salao):
    client.force_login(operador)
    created = _save(client, {"revision": _read(client)["revision"], "spots": [
        {"label": "Mesa 9", "short_label": "M9", "shape": "round", "seats": 2, "area": "Calçada",
         "plan_x": 400, "plan_y": 500},
    ]})
    assert created.status_code == 200, created.content
    nova = SeatingSpot.objects.get(label="Mesa 9")
    assert nova.active_from == timezone.localdate()
    assert nova.ref == "mesa-9"

    response = _save(client, {"revision": created.json()["revision"], "spots": [{"ref": "mesa-9", "seats": 3}]})

    assert response.status_code == 200, response.content
    assert response.json()["saved"] == {"changed": 1, "created": 0, "versioned": 0, "removed": 0}
    nova.refresh_from_db()
    assert nova.seats == 3
    assert [entry["action"] for entry in _entries()] == ["seating.spot.add", "seating.spot.change"]


def test_banqueta_e_lugar_de_balcao_com_um_assento(client, operador, salao):
    client.force_login(operador)
    response = _save(client, {"revision": _read(client)["revision"], "spots": [
        {"label": "Banqueta 7", "shape": "stool", "area": "Balcão"},
        {"ref": "mesa-2", "shape": "stool"},
    ]})
    assert response.status_code == 200, response.content
    banqueta = SeatingSpot.objects.get(label="Banqueta 7")
    assert (banqueta.kind, banqueta.seats) == (SpotKind.COUNTER, 1)
    # Mesa 2 tinha 4 lugares e passado: virar banqueta muda a medida, e versiona.
    salao["m2"].refresh_from_db()
    assert salao["m2"].active_until == timezone.localdate() - timedelta(days=1)
    assert (salao["m2"].replaced_by.kind, salao["m2"].replaced_by.seats) == (SpotKind.COUNTER, 1)


def test_tirar_do_salao_encerra_ontem_sem_apagar(client, operador, salao):
    client.force_login(operador)
    response = _save(client, {"revision": _read(client)["revision"], "removed": ["balcao-1"]})

    assert response.status_code == 200, response.content
    salao["b1"].refresh_from_db()
    assert salao["b1"].active_until == timezone.localdate() - timedelta(days=1)
    assert "balcao-1" not in [spot["ref"] for spot in response.json()["spots"]]
    [entry] = _entries()
    assert entry["action"] == "seating.spot.remove"
    assert "saiu do salão a partir de hoje" in response.json()["history"][0]["summary"]


# ── Recusas no dialeto da casa ──────────────────────────────────────────


def test_outro_dispositivo_salvou_no_meio_recusa_com_conflito(client, operador, salao):
    client.force_login(operador)
    revision = _read(client)["revision"]
    assert _save(client, {"revision": revision, "spots": [{"ref": "mesa-2", "plan_x": 10}]}).status_code == 200

    response = _save(client, {"revision": revision, "spots": [{"ref": "mesa-2", "plan_x": 99}]})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "seating_conflict"
    salao["m2"].refresh_from_db()
    assert salao["m2"].plan_x == 10


@pytest.mark.parametrize(
    ("spot", "field"),
    [
        ({"ref": "mesa-1", "seats": 0}, "spots[0].seats"),
        ({"ref": "mesa-1", "seats": 41}, "spots[0].seats"),
        ({"ref": "mesa-1", "shape": "hexagonal"}, "spots[0].shape"),
        ({"ref": "mesa-1", "rotation": 45}, "spots[0].rotation"),
        ({"ref": "mesa-1", "plan_x": -1}, "spots[0].plan_x"),
        ({"ref": "mesa-1", "label": "  "}, "spots[0].label"),
        ({"ref": "mesa-1", "counts_in_capacity": "sim"}, "spots[0].counts_in_capacity"),
        ({"ref": "mesa-velha", "plan_x": 1}, "spots[0].ref"),
        ({"shape": "round"}, "spots[0].label"),
    ],
)
def test_pedido_invalido_diz_o_campo_e_nao_grava_nada(client, operador, salao, spot, field):
    client.force_login(operador)
    response = _save(client, {"revision": _read(client)["revision"],
                              "spots": [spot], "removed": []})
    assert response.status_code == 400, response.content
    body = response.json()
    assert body["field"] == field
    assert body["errors"] == {field: [body["detail"]]}
    assert "—" not in body["detail"]
    assert _entries() == []


def test_tudo_ou_nada(client, operador, salao):
    client.force_login(operador)
    response = _save(client, {"revision": _read(client)["revision"], "spots": [
        {"ref": "mesa-1", "plan_x": 500},
        {"ref": "mesa-2", "seats": 99},
    ]})
    assert response.status_code == 400
    salao["m1"].refresh_from_db()
    assert salao["m1"].plan_x == 40
    assert _entries() == []


def test_sem_revisao_pede_recarregar(client, operador, salao):
    client.force_login(operador)
    response = _save(client, {"spots": []})
    assert response.status_code == 400
    assert response.json()["field"] == "revision"


def test_ref_nova_nao_colide(operador, salao):
    revision = seating.revision()
    seating.save_layout(actor=operador, spots=[{"label": "Mesa 1"}], removed=[], expected_revision=revision)
    assert SeatingSpot.objects.filter(label="Mesa 1").count() == 2
    assert SeatingSpot.objects.filter(ref="mesa-1-2").exists()
