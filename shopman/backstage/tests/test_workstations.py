"""Postos de trabalho (UX-POSTO1): o posto separado do caixa.

O que este arquivo prende:

* todo caixa é um posto, com o mesmo ref (o cookie dos dispositivos já provisionados
  continua valendo, sem ninguém refazer nada);
* posto sem caixa NUNCA abre gaveta nem turno;
* cada app oferece os postos que fazem sentido nele, e o posto é um só;
* o cadastro de Postos (Gestor) cria, renomeia, desliga e desvincula dispositivos, só para
  quem gere operadores;
* a migração de dados leva a arrumação do Gestor do terminal para o posto.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from shopman.cashman.models import Shift, Terminal
from shopman.doorman.models import SubjectType, TrustedDevice

from shopman.backstage import station_trust
from shopman.backstage.models import Workstation
from shopman.backstage.services import workstations
from shopman.backstage.tests.support import trust_station
from shopman.backstage.workstation_vocabulary import COPY, KIND_LABELS, SURFACE_KINDS
from shopman.shop.models import Shop

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_loja")]

STATION_URL = "/api/v1/backstage/operator/station/"
LIST_URL = "/api/v1/backstage/workstations/"


@pytest.fixture
def _loja():
    return Shop.objects.create(name="Nelson", brand_name="Nelson")


def _grant(user, *codenames):
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)


@pytest.fixture
def gerente():
    user = get_user_model().objects.create_user("marina", password="x", is_staff=True)
    return _grant(user, "manage_operators", "operate_pos")


@pytest.fixture
def caixa_principal():
    return Terminal.objects.create(ref="pdv-main", label="Caixa principal")


@pytest.fixture
def expedicao():
    return Workstation.objects.create(ref="expedicao", label="Expedição", kind="dispatch")


# ── Modelo ──────────────────────────────────────────────────────────────


def test_todo_caixa_nasce_com_o_seu_posto_de_mesmo_ref(caixa_principal):
    posto = Workstation.objects.get(terminal=caixa_principal)

    assert posto.ref == "pdv-main"
    assert posto.kind == "cash_desk"
    assert posto.label == "Caixa principal"
    assert posto.has_cash_desk


def test_caixa_novo_nao_toma_o_ref_de_um_posto_sem_caixa(expedicao):
    """Senão os dispositivos da Expedição passariam a abrir a gaveta desse caixa."""
    with pytest.raises(ValidationError):
        Terminal.objects.create(ref="expedicao", label="Caixa da expedição")

    assert not Terminal.objects.filter(ref="expedicao").exists()


def test_posto_sem_caixa_nao_pode_ter_o_ref_de_um_caixa(caixa_principal):
    posto = Workstation(ref="pdv-main-2", label="Atendimento", kind="service")
    posto.full_clean()  # ref livre passa

    colidindo = Workstation(ref="pdv-main", label="Atendimento", kind="service")
    with pytest.raises(ValidationError):
        colidindo.clean()


def test_tipo_desconhecido_e_caixa_sem_terminal_sao_recusados():
    with pytest.raises(ValidationError):
        Workstation(ref="x", label="X", kind="doca").full_clean()
    with pytest.raises(ValidationError):
        Workstation(ref="y", label="Y", kind="cash_desk").full_clean()


def test_o_vocabulario_cobre_todo_app_de_operador():
    """Cada app de operador do registro oferece só tipos que existem."""
    import json
    from pathlib import Path

    registry = json.loads((Path(__file__).resolve().parents[3] / "surfaces/registry.json").read_text())
    operator_apps = {key for key, s in registry["surfaces"].items() if s["kind"] == "operator" and s.get("deployment") != "preview"}

    assert set(SURFACE_KINDS) == operator_apps
    for kinds in SURFACE_KINDS.values():
        assert kinds and set(kinds) <= set(KIND_LABELS)


def test_a_copy_nao_tem_travessao():
    textos = [*COPY.values(), *KIND_LABELS.values()]
    assert not [t for t in textos if "—" in t or "–" in t]


# ── Posto sem caixa não abre gaveta nem turno ───────────────────────────


def test_posto_sem_caixa_nao_abre_turno(client, gerente, caixa_principal, expedicao):
    trust_station(client, expedicao.ref)
    client.force_login(gerente)

    abrir = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "client_request_id": "abrir-1"},
        content_type="application/json",
    )

    assert abrir.status_code == 409
    assert abrir.json()["error"]["code"] == "pos_station_required"
    assert not Shift.objects.exists()


def test_posto_sem_caixa_nao_abre_gaveta(client, gerente, caixa_principal, expedicao):
    from shopman.cashman import services as cash

    cash.open_shift(operator=gerente, terminal=caixa_principal, float_q=0)
    trust_station(client, expedicao.ref)
    client.force_login(gerente)

    gaveta = client.post(
        reverse("api-backstage-pos-cash-drawer-open"),
        {"client_request_id": "gaveta-1", "reason": "troco"},
        content_type="application/json",
    )

    assert gaveta.status_code == 409
    assert gaveta.json()["error"]["code"] == "pos_station_required"


def test_o_posto_caixa_continua_abrindo_o_turno(client, gerente, caixa_principal):
    trust_station(client, caixa_principal.ref)
    client.force_login(gerente)

    abrir = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "client_request_id": "abrir-2"},
        content_type="application/json",
    )

    assert abrir.status_code in {200, 201}, abrir.content
    assert Shift.objects.filter(terminal=caixa_principal).exists()


# ── Provisionar: cada app oferece os seus, o posto é um só ──────────────


def _salas():
    for ref, label in (("sala-forno", "Sala Forno"), ("sala-massas", "Sala Massas")):
        Workstation.objects.create(ref=ref, label=label, kind="production_room")
    Workstation.objects.create(ref="lanches", label="Lanches", kind="kitchen_station")
    Workstation.objects.create(ref="escritorio", label="Escritório", kind="office")


@pytest.mark.parametrize(
    ("surface", "esperado"),
    [
        ("production", ["sala-forno", "sala-massas"]),
        ("kds", ["lanches", "expedicao"]),
        ("orders", ["expedicao", "escritorio"]),
        ("pos", ["pdv-main"]),
        ("bi", ["escritorio"]),
    ],
)
def test_cada_app_oferece_os_seus_postos(client, gerente, caixa_principal, expedicao, surface, esperado):
    _salas()
    client.force_login(gerente)

    estado = client.get(STATION_URL, {"surface": surface}).json()

    assert [w["ref"] for w in estado["workstations"]] == esperado
    assert [k["kind"] for k in estado["kinds"]] == list(SURFACE_KINDS[surface])
    assert estado["copy"]["setup_title"] == "Vincular este dispositivo a um posto de trabalho?"
    assert estado["copy"]["setup_confirm"] == "Vincular a este posto"


def test_a_central_oferece_todos(client, gerente, caixa_principal, expedicao):
    _salas()
    client.force_login(gerente)

    refs = {w["ref"] for w in client.get(STATION_URL, {"surface": "hub"}).json()["workstations"]}

    assert refs == {"pdv-main", "expedicao", "sala-forno", "sala-massas", "lanches", "escritorio"}


def test_posto_desativado_nao_e_oferecido(client, gerente, expedicao):
    workstations.update(expedicao.ref, is_active=False)
    client.force_login(gerente)

    assert client.get(STATION_URL, {"surface": "kds"}).json()["workstations"] == []
    recusa = client.post(STATION_URL, {"workstation_ref": "expedicao"}, content_type="application/json")
    assert recusa.status_code == 400


def test_vincular_a_expedicao_e_o_rail_diz_o_posto(client, gerente, expedicao):
    client.force_login(gerente)

    resposta = client.post(STATION_URL, {"workstation_ref": "expedicao"}, content_type="application/json")

    assert resposta.status_code == 200
    assert resposta.json()["workstation"]["context_label"] == "Posto Expedição"
    sessao = client.get(reverse("api-backstage-operator-session")).json()
    assert sessao["station"] == "expedicao"
    assert sessao["workstation"] == {
        "ref": "expedicao",
        "label": "Expedição",
        "kind": "dispatch",
        "kind_label": "Expedição",
        "has_cash_desk": False,
        "context_label": "Posto Expedição",
    }
    # O mesmo cookie vale em todos os apps: o estado de qualquer app vê o mesmo posto.
    assert client.get(STATION_URL, {"surface": "production"}).json()["workstation"]["ref"] == "expedicao"


def test_dois_dispositivos_no_posto_sem_caixa_nao_pedem_segunda_palavra(client, gerente, expedicao):
    """A segunda palavra é sobre dividir gaveta e turno; a Expedição não tem nenhum dos dois."""
    trust_station(Client(), expedicao.ref)
    client.force_login(gerente)

    resposta = client.post(STATION_URL, {"workstation_ref": "expedicao"}, content_type="application/json")

    assert resposta.status_code == 200
    assert len(station_trust.active_station_devices("expedicao")) == 2


def test_station_workstation_resolve_pelo_cookie(client, expedicao):
    trust_station(client, expedicao.ref)
    request = SimpleNamespace(COOKIES={k: v.value for k, v in client.cookies.items()}, META={})

    assert station_trust.station_workstation(request) == expedicao


# ── Cadastro de Postos (Gestor) ─────────────────────────────────────────


def test_quem_nao_gere_operadores_nao_ve_o_cadastro(client):
    caixa = _grant(get_user_model().objects.create_user("joyce", password="x", is_staff=True), "operate_pos")
    client.force_login(caixa)

    assert client.get(LIST_URL).status_code == 403
    assert client.post(LIST_URL, {"label": "X", "kind": "office"}, content_type="application/json").status_code == 403


def test_cria_renomeia_e_desliga(client, gerente, caixa_principal):
    client.force_login(gerente)

    criado = client.post(LIST_URL, {"label": "Sala Forno", "kind": "production_room"}, content_type="application/json")
    assert criado.status_code == 201, criado.content
    ref = criado.json()["workstation"]["ref"]
    assert ref == "sala-forno"

    renomeado = client.patch(f"{LIST_URL}{ref}/", {"label": "Forno"}, content_type="application/json")
    assert renomeado.status_code == 200
    assert Workstation.objects.get(ref=ref).label == "Forno"

    trust_station(Client(), ref)
    desligado = client.patch(f"{LIST_URL}{ref}/", {"is_active": False}, content_type="application/json")
    assert desligado.status_code == 200
    assert not Workstation.objects.get(ref=ref).is_active
    # Posto desligado desvincula todos os dispositivos: ele não abre mais a antessala.
    assert station_trust.active_station_devices(ref) == []

    lista = {w["ref"]: w for w in client.get(LIST_URL).json()["workstations"]}
    assert lista[ref]["is_active"] is False
    assert lista["pdv-main"]["has_cash_desk"] is True


def test_cadastro_nao_cria_caixa_nem_tipo_inventado(client, gerente):
    client.force_login(gerente)

    caixa = client.post(LIST_URL, {"label": "Caixa 2", "kind": "cash_desk"}, content_type="application/json")
    inventado = client.post(LIST_URL, {"label": "Doca", "kind": "dock"}, content_type="application/json")
    sem_nome = client.post(LIST_URL, {"label": "  ", "kind": "office"}, content_type="application/json")

    assert caixa.status_code == 400
    assert caixa.json()["error"]["code"] == "cash_desk_needs_terminal"
    assert inventado.status_code == 400 and inventado.json()["field"] == "kind"
    assert sem_nome.status_code == 400 and sem_nome.json()["field"] == "label"
    assert not Workstation.objects.exists()


def test_ref_novo_nao_colide_com_caixa(client, gerente):
    Terminal.objects.create(ref="lanches", label="Lanches (caixa)")
    client.force_login(gerente)

    criado = client.post(LIST_URL, {"label": "Lanches", "kind": "kitchen_station"}, content_type="application/json")

    assert criado.json()["workstation"]["ref"] == "lanches-2"


def test_posto_sem_caixa_nao_vira_caixa(client, gerente, expedicao):
    client.force_login(gerente)

    resposta = client.patch(f"{LIST_URL}expedicao/", {"kind": "cash_desk"}, content_type="application/json")

    assert resposta.status_code == 400
    assert Workstation.objects.get(ref="expedicao").kind == "dispatch"


def test_desvincular_um_dispositivo_do_posto(client, gerente, expedicao):
    trust_station(Client(), expedicao.ref)
    trust_station(Client(), expedicao.ref)
    client.force_login(gerente)
    lista = {w["ref"]: w for w in client.get(LIST_URL).json()["workstations"]}
    um, outro = lista["expedicao"]["devices"]

    resposta = client.delete(f"{LIST_URL}expedicao/devices/{um['id']}/")

    assert resposta.status_code == 200
    assert [str(d.pk) for d in station_trust.active_station_devices("expedicao")] == [outro["id"]]
    assert client.delete(f"{LIST_URL}expedicao/devices/nao-e-uuid/").status_code == 404


# ── Migração de dados ───────────────────────────────────────────────────


def test_migracao_cria_um_posto_por_caixa_e_preserva_a_confianca(client):
    """Um tablet já provisionado não pode ter de ser provisionado de novo."""
    migration = importlib.import_module("shopman.backstage.migrations.0081_workstation")
    board = {"columns": {"intake": {"open": False, "weight": 1}}}
    passe = Terminal.objects.create(
        ref="passe", label="Passe", metadata={"station": {"mode": "attended"}, "gestor_board": board}
    )
    painel = Terminal.objects.create(ref="painel", label="Painel", metadata={"station": {"mode": "autonomous"}})
    trust_station(client, passe.ref)
    # O banco de antes da migração: terminais sem posto.
    Workstation.objects.all().delete()

    migration.forward(django_apps, None)

    posto = Workstation.objects.get(ref="passe")
    assert posto.terminal == passe and posto.kind == "cash_desk"
    assert posto.metadata == {"gestor_board": board}
    passe.refresh_from_db()
    assert "gestor_board" not in passe.metadata
    assert passe.metadata["station"] == {"mode": "attended"}
    assert Workstation.objects.get(terminal=painel).kind == "production_room"
    # O cookie emitido antes da migração continua reconhecendo o mesmo posto.
    assert TrustedDevice.objects.filter(subject_type=SubjectType.STATION, subject_id="passe", is_active=True).exists()
    sessao = client.get(reverse("api-backstage-operator-session")).json()
    assert sessao["workstation"]["ref"] == "passe"

    migration.backward(django_apps, None)
    passe.refresh_from_db()
    assert passe.metadata["gestor_board"] == board


# ── A copy do posto na voz da casa (dono, 09/10/2026) ──────────────────────────


def test_copy_do_posto_e_curta_e_sem_jargao():
    """A frase de vincular foi recusada por prolixa; a de Postos repetia o mesmo
    defeito. Nenhuma frase do posto fala a língua do sistema (a trava irmã das telas
    é ``surfaces/operator-kit/tests/guardrails.jargon.test.ts``)."""
    import re

    from shopman.backstage.workstation_vocabulary import COPY

    assert COPY["setup_lead"] == "Escolha uma vez. Depois, o dispositivo abre direto no posto e só pede o PIN."
    assert "quem for operar" not in COPY["manage_lead"]
    jargon = re.compile(r"\b(Core|backend|servidor|endpoint|payload|token|API|SSE)\b", re.IGNORECASE)
    assert [key for key, text in COPY.items() if jargon.search(text)] == []
