"""A loja no iFood, consultada ao vivo (homologação do módulo Merchant, DEV-2026-044).

O checklist do iFood pede, dentro do nosso sistema: listar as lojas vinculadas, ver o
detalhe completo e a disponibilidade; pausar, listar as pausas e remover; consultar o
horário. Estes testes travam o que a tela mostra contra um iFood falso, inclusive as
recusas (403 do módulo não liberado, 409 de pausa sobreposta).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse

from shopman.backstage.projections import ifood_merchant_console as console
from shopman.shop.models import IFoodInterruption, IFoodInterruptionKind, IFoodInterruptionState, Shop
from shopman.shop.services import ifood_http
from shopman.shop.tests.test_ifood_merchant import BASE, MID, ON, FakeIFood, _Resp

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 11, 21, 11, 0, tzinfo=TZ)  # sábado, 11h
HOURS = {
    "saturday": {"open": "10:00", "close": "19:00"},
    "sunday": {
        "open": "09:00",
        "close": "23:00",
        "breaks": [{"start": "12:00", "end": "13:00"}, {"start": "16:00", "end": "17:00"}],
    },
}


class ConsoleIFood(FakeIFood):
    def request(self, method, path, *, label, idempotent=False, **kwargs):
        if (method, path) not in self.override:
            if (method, path) == ("GET", "/merchant/v1.0/merchants"):
                return _Resp(200, [{"id": MID, "name": "Teste - Nelson Boulangerie", "corporateName": "NB LTDA"}])
            if (method, path) == ("GET", BASE):
                return _Resp(
                    200,
                    {
                        "id": MID,
                        "name": "Teste - Nelson Boulangerie",
                        "corporateName": "NB LTDA",
                        "averageTicket": 50,
                        "exclusive": False,
                        "address": {"city": "Londrina", "state": "PR"},
                        "operations": [{"name": "DELIVERY", "salesChannel": {"name": "IFOOD", "enabled": True}}],
                    },
                )
        return super().request(method, path, label=label, idempotent=idempotent, **kwargs)


@pytest.fixture
def fake(monkeypatch):
    fake = ConsoleIFood()
    monkeypatch.setattr(ifood_http, "request", fake.request)
    monkeypatch.setattr("django.utils.timezone.now", lambda: NOW)
    Shop.objects.create(name="Nelson", timezone="America/Sao_Paulo", opening_hours=HOURS)
    return fake


def _user(*perms):
    user = get_user_model().objects.create_user(username="gerente", password="x", is_staff=True)
    for codename in perms:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return get_user_model().objects.get(pk=user.pk)


@override_settings(SHOPMAN_IFOOD=ON)
def test_lojas_vinculadas_marcam_a_loja_desta_casa(fake):
    projection = console.build_merchants()

    assert projection.error == ""
    assert [(m.id, m.name, m.is_current) for m in projection.merchants] == [(MID, "Teste - Nelson Boulangerie", True)]


@override_settings(SHOPMAN_IFOOD=ON)
def test_detalhe_mostra_todos_os_campos_e_status_mostra_as_validacoes(fake):
    fake.status = [
        {
            "operation": "DELIVERY",
            "salesChannel": "IFOOD",
            "available": False,
            "state": "CLOSED",
            "message": {"title": "Loja fechada", "subtitle": "Fora do horário"},
            "validations": [
                {"code": "opening-hours", "state": "CLOSED", "message": {"title": "Fora do horário"}},
                {"code": "is-connected", "state": "OK", "message": {"title": "Conectada"}},
            ],
        }
    ]

    projection = console.build_merchant()

    rows = {row.label: row.value for row in projection.detail}
    assert rows["Nome"] == "Teste - Nelson Boulangerie"
    assert rows["Cidade"] == "Londrina"
    assert rows["Exclusiva do iFood"] == "Não"
    assert rows["Operação 1 · canal de venda"] == "IFOOD"  # campo sem rótulo próprio também aparece
    assert projection.available is False
    operation = projection.operations[0]
    assert (operation.state_label, operation.title) == ("Fechada", "Loja fechada")
    assert [(c.code, c.state) for c in operation.checks] == [("opening-hours", "CLOSED"), ("is-connected", "OK")]


@override_settings(SHOPMAN_IFOOD=ON)
def test_403_do_modulo_nao_liberado_vira_frase_e_nao_derruba_as_outras_secoes(fake):
    fake.override[("GET", f"{BASE}/status")] = _Resp(403, {"message": "forbidden"})

    projection = console.build_merchant()

    assert "módulo Merchant não está liberado" in projection.status_error
    assert projection.detail  # o detalhe veio mesmo com o status recusado


@override_settings(SHOPMAN_IFOOD=ON)
def test_pausas_dizem_de_onde_vieram(fake):
    fake.interruptions = [
        {
            "id": "p-portal",
            "description": "Feita no Portal",
            "start": "2026-11-21T10:30:00-03:00",
            "end": "2026-11-21T12:00:00-03:00",
        },
        {
            "id": "p-gestor",
            "description": "iFood desligado no Gestor",
            "start": "2026-11-21T11:30:00-03:00",
            "end": "2026-11-21T12:30:00-03:00",
        },
        {
            "id": "p-velha",
            "description": "Já acabou",
            "start": "2026-11-20T10:00:00-03:00",
            "end": "2026-11-20T11:00:00-03:00",
        },
    ]
    IFoodInterruption.objects.create(
        kind=IFoodInterruptionKind.CALENDAR,
        state=IFoodInterruptionState.ACTIVE,
        merchant_id=MID,
        ifood_id="p-gestor",
        description="iFood desligado no Gestor",
        starts_at=datetime(2026, 11, 21, 11, 30, tzinfo=TZ),
        ends_at=datetime(2026, 11, 21, 12, 30, tzinfo=TZ),
        calendar_key="off:2611211130-2611211230",
    )

    projection = console.build_interruptions()

    assert [(i.id, i.origin_label, i.in_effect, i.removable) for i in projection.items] == [
        ("p-portal", "Portal do Parceiro", True, True),
        ("p-gestor", "iFood desligado no Gestor", False, False),
    ]


@override_settings(SHOPMAN_IFOOD=ON)
def test_pausa_recusada_com_409_aparece_com_o_motivo(fake):
    IFoodInterruption.objects.create(
        kind=IFoodInterruptionKind.CALENDAR,
        state=IFoodInterruptionState.FAILED,
        merchant_id=MID,
        description="iFood desligado no Gestor",
        starts_at=datetime(2026, 11, 21, 11, 0, tzinfo=TZ),
        ends_at=datetime(2026, 11, 21, 11, 30, tzinfo=TZ),
        calendar_key="off:2611211100-2611211130",
        last_error="O iFood recusou: já existe outra pausa no mesmo horário (criada no Portal do Parceiro?).",
    )

    refused = console.build_interruptions().refused

    assert len(refused) == 1
    assert refused[0].origin_label == "iFood desligado no Gestor"
    assert "já existe outra pausa" in refused[0].error


@override_settings(SHOPMAN_IFOOD=ON)
def test_horario_do_ifood_ao_lado_do_da_casa(fake):
    fake.shifts = [
        {"dayOfWeek": "SATURDAY", "start": "10:00:00", "duration": 540},
        {"dayOfWeek": "SUNDAY", "start": "09:00:00", "duration": 180},
    ]

    projection = console.build_opening_hours()

    days = {d.day: d for d in projection.days}
    assert days["saturday"].matches is True
    assert days["sunday"].house == "9h às 12h, 13h às 16h e 17h às 23h"
    assert days["sunday"].ifood == "9h às 12h"
    assert days["sunday"].matches is False
    assert projection.matches is False


# ── API ───────────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_IFOOD=ON)
def test_api_das_consultas(client, fake):
    client.force_login(_user("manage_orders"))

    assert client.get(reverse("api-backstage-ifood-merchants")).json()["merchants"][0]["is_current"] is True
    assert client.get(reverse("api-backstage-ifood-merchant")).json()["merchant_id"] == MID
    assert client.get(reverse("api-backstage-ifood-interruptions")).json()["items"] == []
    assert len(client.get(reverse("api-backstage-ifood-opening-hours")).json()["days"]) == 7


@override_settings(SHOPMAN_IFOOD={**ON, "merchant_sync_enabled": False})
def test_api_desligada_so_diz_que_esta_desligada(client, fake):
    client.force_login(_user("manage_orders"))

    assert client.get(reverse("api-backstage-ifood-merchant")).json() == {"enabled": False}
    assert not fake.calls


@override_settings(SHOPMAN_IFOOD=ON)
def test_gerente_remove_a_pausa_do_portal_mas_nao_a_do_gestor(client, fake):
    fake.interruptions = [
        {
            "id": "p-portal",
            "description": "Portal",
            "start": "2026-11-21T10:30:00-03:00",
            "end": "2026-11-21T12:00:00-03:00",
        },
        {
            "id": "p-gestor",
            "description": "Gestor",
            "start": "2026-11-21T10:30:00-03:00",
            "end": "2026-11-21T12:00:00-03:00",
        },
    ]
    IFoodInterruption.objects.create(
        kind=IFoodInterruptionKind.CALENDAR,
        state=IFoodInterruptionState.ACTIVE,
        merchant_id=MID,
        ifood_id="p-gestor",
        description="iFood desligado no Gestor",
        starts_at=datetime(2026, 11, 21, 10, 30, tzinfo=TZ),
        ends_at=datetime(2026, 11, 21, 12, 0, tzinfo=TZ),
        calendar_key="off:x",
    )
    client.force_login(_user("manage_orders", "adjust_shift"))

    removed = client.delete(reverse("api-backstage-ifood-interruption", args=["p-portal"]))
    kept = client.delete(reverse("api-backstage-ifood-interruption", args=["p-gestor"]))

    assert removed.status_code == 200
    assert [i["id"] for i in removed.json()["items"]] == ["p-gestor"]
    assert kept.status_code == 409
    assert "ligue o iFood de novo" in kept.json()["detail"]


@override_settings(SHOPMAN_IFOOD=ON)
def test_caixa_nao_remove_pausa(client, fake):
    client.force_login(_user("manage_orders"))

    assert client.delete(reverse("api-backstage-ifood-interruption", args=["p-portal"])).status_code == 403
    assert not fake.writes()
