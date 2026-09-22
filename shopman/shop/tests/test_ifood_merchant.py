"""iFood Merchant: o Shopman como fonte única de "loja aberta" no iFood.

Antes deste módulo, o Shopman não chamava o módulo Merchant: o horário e as
pausas do iFood moravam no Portal do Parceiro, e nenhum vigia via o iFood fechar
com a casa aberta (polling caído) ou abrir com ela fechada. Estes testes travam
as três metades — gravação de horário/calendário, pausa do gestor e conferência —
contra um iFood falso. Nenhuma chamada sai para a API real.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import IFOOD_MERCHANT_INTERRUPTION, IFOOD_MERCHANT_SYNC
from shopman.shop.handlers.ifood_merchant import (
    IFoodMerchantInterruptionHandler,
    IFoodMerchantSyncHandler,
    on_shop_saved,
)
from shopman.shop.models import IFoodInterruption, IFoodInterruptionState, IFoodStoreStatus, Shop
from shopman.shop.services import ifood_http, ifood_merchant

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("America/Sao_Paulo")
MID = "m-1"
BASE = f"/merchant/v1.0/merchants/{MID}"
ON = {"client_id": "cid", "client_secret": "sec", "merchant_id": MID, "merchant_sync_enabled": True}
OFF = {**ON, "merchant_sync_enabled": False}

WEEK = {
    day: {"open": "09:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
}
# Terça, 22/12/2026, 10:00 — loja aberta.
TUESDAY_10H = datetime(2026, 12, 22, 10, 0, tzinfo=TZ)


class _Resp:
    def __init__(self, status: int, body=None):
        self.status_code = status
        self._body = body
        self.text = "" if body is None else str(body)
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        if self._body is None:
            raise ValueError("sem corpo")
        return self._body


class FakeIFood:
    """O módulo Merchant de mentira: guarda horário, interrupções e status."""

    def __init__(self):
        self.shifts: list[dict] = []
        self.interruptions: list[dict] = []
        self.status: list[dict] = [{"operation": "DELIVERY", "available": True, "state": "OK", "validations": []}]
        self.calls: list[tuple[str, str, object]] = []
        self.next_id = 1
        self.override: dict[tuple[str, str], _Resp | None] = {}

    def request(self, method, path, *, label, idempotent=False, **kwargs):
        body = kwargs.get("json")
        self.calls.append((method, path, body))
        key = (method, path)
        if key in self.override:
            return self.override[key]
        if (method, path) == ("GET", f"{BASE}/opening-hours"):
            return _Resp(200, [{"shifts": list(self.shifts)}])
        if (method, path) == ("PUT", f"{BASE}/opening-hours"):
            self.shifts = [dict(shift, id=f"s{i}") for i, shift in enumerate(body["shifts"])]
            return _Resp(201, {"storeId": body["storeId"], "shifts": self.shifts})
        if (method, path) == ("GET", f"{BASE}/interruptions"):
            return _Resp(200, list(self.interruptions))
        if (method, path) == ("POST", f"{BASE}/interruptions"):
            created = {"id": f"int-{self.next_id}", **body}
            self.next_id += 1
            self.interruptions.append(created)
            return _Resp(201, created)
        if method == "DELETE" and path.startswith(f"{BASE}/interruptions/"):
            target = path.rsplit("/", 1)[1]
            self.interruptions = [i for i in self.interruptions if i["id"] != target]
            return _Resp(204)
        if (method, path) == ("GET", f"{BASE}/status"):
            return _Resp(200, self.status)
        raise AssertionError(f"chamada inesperada ao iFood: {method} {path}")

    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]


@pytest.fixture
def fake(monkeypatch):
    fake = FakeIFood()
    monkeypatch.setattr(ifood_http, "request", fake.request)
    return fake


def _shop(**extra):
    return Shop.objects.create(name="Nelson", timezone="America/Sao_Paulo", opening_hours=WEEK, **extra)


def _closed(*entries):
    return {"closed_dates": list(entries)}


# ── 1. Horário e calendário → iFood ───────────────────────────────────────────


@override_settings(SHOPMAN_IFOOD=ON)
def test_grade_semanal_vira_turnos_do_ifood_e_domingo_fica_de_fora(fake):
    _shop()

    result = ifood_merchant.sync_store(now=TUESDAY_10H)

    assert result.hours_written is True
    put = [call for call in fake.calls if call[0] == "PUT"]
    assert len(put) == 1
    assert put[0][2]["storeId"] == MID
    shifts = put[0][2]["shifts"]
    assert {s["dayOfWeek"] for s in shifts} == {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"}
    assert all(s["start"] == "09:00:00" and s["duration"] == 540 for s in shifts)


@override_settings(SHOPMAN_IFOOD=ON)
def test_horario_igual_ao_do_ifood_nao_e_regravado(fake):
    _shop()
    ifood_merchant.sync_store(now=TUESDAY_10H)
    fake.calls.clear()

    result = ifood_merchant.sync_store(now=TUESDAY_10H)

    assert result.hours_written is False
    assert fake.writes() == []


@override_settings(SHOPMAN_IFOOD=ON)
def test_feriado_vira_interrupcao_de_meia_noite_a_meia_noite_no_fuso_da_loja(fake):
    _shop(defaults=_closed({"date": "2026-12-25", "label": "Natal"}))

    ifood_merchant.sync_store(now=TUESDAY_10H)

    assert len(fake.interruptions) == 1
    created = fake.interruptions[0]
    assert created["start"] == "2026-12-25T00:00:00-03:00"
    assert created["end"] == "2026-12-26T00:00:00-03:00"
    assert "Natal" in created["description"]
    record = IFoodInterruption.objects.get()
    assert record.state == IFoodInterruptionState.ACTIVE
    assert record.ifood_id == created["id"]


@override_settings(SHOPMAN_IFOOD=ON)
def test_feriado_ja_gravado_nao_duplica_e_sai_quando_o_calendario_reabre(fake):
    shop = _shop(defaults=_closed({"date": "2026-12-25", "label": "Natal"}))
    ifood_merchant.sync_store(now=TUESDAY_10H)
    ifood_merchant.sync_store(now=TUESDAY_10H)
    assert len(fake.interruptions) == 1

    shop.defaults = {}
    shop.save()
    ifood_merchant.sync_store(now=TUESDAY_10H)

    assert fake.interruptions == []
    assert IFoodInterruption.objects.get().state == IFoodInterruptionState.REMOVED


@override_settings(SHOPMAN_IFOOD=ON)
def test_interrupcao_apagada_no_portal_e_recriada_enquanto_o_calendario_fecha(fake):
    _shop(defaults=_closed({"date": "2026-12-25", "label": "Natal"}))
    ifood_merchant.sync_store(now=TUESDAY_10H)
    fake.interruptions.clear()  # alguém apagou no Portal do Parceiro

    ifood_merchant.sync_store(now=TUESDAY_10H)

    assert len(fake.interruptions) == 1


@override_settings(SHOPMAN_IFOOD=ON)
def test_ferias_longas_viram_blocos_de_ate_sete_dias(fake):
    # A interrupção do iFood dura no máximo 7 dias: 13 dias seguidos viram 7 + 6.
    Shop.objects.create(
        name="Sete dias",
        timezone="America/Sao_Paulo",
        opening_hours={**WEEK, "sunday": {"open": "09:00", "close": "13:00"}},
        defaults=_closed({"from": "2026-12-23", "to": "2027-01-04", "label": "Férias"}),
    )

    ifood_merchant.sync_store(now=TUESDAY_10H)

    spans = sorted((i["start"][:10], i["end"][:10]) for i in fake.interruptions)
    assert spans == [("2026-12-23", "2026-12-30"), ("2026-12-30", "2027-01-05")]


@override_settings(SHOPMAN_IFOOD=ON)
def test_domingo_sem_grade_nao_entra_nas_ferias(fake):
    # 28/12 (seg) a 02/01 (sáb) + 04/01: o domingo 03/01 já está fechado pelo horário.
    _shop(defaults=_closed({"from": "2026-12-28", "to": "2027-01-04", "label": "Férias"}))

    ifood_merchant.sync_store(now=TUESDAY_10H)

    spans = sorted((i["start"][:10], i["end"][:10]) for i in fake.interruptions)
    assert spans == [("2026-12-28", "2027-01-03"), ("2027-01-04", "2027-01-05")]


@override_settings(SHOPMAN_IFOOD=ON)
def test_fechamento_em_dia_sem_grade_nao_vira_interrupcao(fake):
    _shop(defaults=_closed({"date": "2026-12-27", "label": "Domingo qualquer"}))

    ifood_merchant.sync_store(now=TUESDAY_10H)

    assert fake.interruptions == []


@override_settings(SHOPMAN_IFOOD=ON)
def test_loja_sem_grade_semanal_nao_governa_o_ifood(fake):
    Shop.objects.create(name="Sem grade", timezone="America/Sao_Paulo", opening_hours={})

    result = ifood_merchant.sync_store(now=TUESDAY_10H)

    assert result.skipped == "sem grade semanal"
    assert fake.calls == []


@override_settings(SHOPMAN_IFOOD=OFF)
def test_desligado_nada_e_gravado_nem_enfileirado(fake, django_capture_on_commit_callbacks):
    shop = _shop()

    with django_capture_on_commit_callbacks(execute=True):
        on_shop_saved(Shop, shop)
    result = ifood_merchant.sync_store(now=TUESDAY_10H)

    assert result.skipped == "desligado"
    assert fake.calls == []
    assert not Directive.objects.filter(topic=IFOOD_MERCHANT_SYNC).exists()


@override_settings(SHOPMAN_IFOOD=ON)
def test_salvar_a_loja_enfileira_uma_gravacao_so(django_capture_on_commit_callbacks):
    shop = _shop()

    with django_capture_on_commit_callbacks(execute=True):
        on_shop_saved(Shop, shop)
        on_shop_saved(Shop, shop)

    assert Directive.objects.filter(topic=IFOOD_MERCHANT_SYNC, status="queued").count() == 1


def test_a_chave_nasce_desligada():
    from django.conf import settings

    assert settings.SHOPMAN_IFOOD.get("merchant_sync_enabled") is False


@override_settings(SHOPMAN_IFOOD=ON)
def test_sem_resposta_do_ifood_a_directive_repete(fake):
    _shop()
    fake.override[("GET", f"{BASE}/opening-hours")] = None  # recusa de borda esgotada

    with pytest.raises(DirectiveTransientError):
        IFoodMerchantSyncHandler().handle(message=Directive(topic=IFOOD_MERCHANT_SYNC, payload={}), ctx={})


@override_settings(SHOPMAN_IFOOD=ON)
def test_grade_recusada_pelo_ifood_nao_repete(fake):
    _shop()
    fake.override[("PUT", f"{BASE}/opening-hours")] = _Resp(400, {"error": {"message": "overlap"}})

    with pytest.raises(DirectiveTerminalError):
        IFoodMerchantSyncHandler().handle(message=Directive(topic=IFOOD_MERCHANT_SYNC, payload={}), ctx={})


# ── 2. Pausa do gestor ────────────────────────────────────────────────────────


def _user(username="gerente", *perms):
    user = get_user_model().objects.create_user(username=username, password="x", is_staff=True)
    for codename in perms:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return get_user_model().objects.get(pk=user.pk)


def _run_interruption_directives():
    for directive in Directive.objects.filter(topic=IFOOD_MERCHANT_INTERRUPTION, status="queued").order_by("pk"):
        IFoodMerchantInterruptionHandler().handle(message=directive, ctx={})
        directive.status = "done"
        directive.save(update_fields=["status"])


@override_settings(SHOPMAN_IFOOD=ON)
def test_pausa_do_gestor_vira_interrupcao_com_motivo_e_autor(fake):
    _shop()
    user = _user()

    record = ifood_merchant.request_pause(duration="1h", reason="Cozinha cheia", user=user, now=TUESDAY_10H)

    assert record.state == IFoodInterruptionState.PENDING_CREATE
    assert record.requested_by == user
    assert fake.calls == []  # o request não atravessa a rede

    _run_interruption_directives()

    record.refresh_from_db()
    assert record.state == IFoodInterruptionState.ACTIVE
    assert fake.interruptions[0]["description"] == "Pausa pelo gestor: Cozinha cheia"
    assert fake.interruptions[0]["end"] == "2026-12-22T11:00:00-03:00"


@override_settings(SHOPMAN_IFOOD=ON)
def test_retomar_apaga_a_interrupcao_e_registra_quem_retomou(fake):
    _shop()
    user = _user()
    record = ifood_merchant.request_pause(duration="30m", reason="Sem entregador", user=user, now=TUESDAY_10H)
    _run_interruption_directives()

    ifood_merchant.request_resume(user=user, now=TUESDAY_10H + timedelta(minutes=5))
    _run_interruption_directives()

    record.refresh_from_db()
    assert record.state == IFoodInterruptionState.REMOVED
    assert record.removed_by == user
    assert fake.interruptions == []


@override_settings(SHOPMAN_IFOOD=ON)
def test_retomar_antes_da_criacao_nunca_cria_a_pausa(fake):
    _shop()
    user = _user()
    ifood_merchant.request_pause(duration="30m", reason="Engano", user=user, now=TUESDAY_10H)
    ifood_merchant.request_resume(user=user, now=TUESDAY_10H)

    _run_interruption_directives()

    assert not [c for c in fake.calls if c[0] == "POST"]
    assert IFoodInterruption.objects.get().state == IFoodInterruptionState.REMOVED


@override_settings(SHOPMAN_IFOOD=ON)
def test_post_perdido_e_adotado_em_vez_de_criar_outra_pausa(fake):
    _shop()
    user = _user()
    record = ifood_merchant.request_pause(duration="30m", reason="Cozinha cheia", user=user, now=TUESDAY_10H)
    # O iFood criou, mas a resposta se perdeu: a pausa já está lá.
    fake.interruptions.append({
        "id": "int-remota",
        "start": "2026-12-22T10:00:00-03:00",
        "end": "2026-12-22T10:30:00-03:00",
        "description": record.description,
    })

    _run_interruption_directives()

    record.refresh_from_db()
    assert record.ifood_id == "int-remota"
    assert not [c for c in fake.calls if c[0] == "POST"]


@override_settings(SHOPMAN_IFOOD=ON)
def test_pausa_sobreposta_e_recusada_e_vira_alerta(fake):
    from shopman.backstage.models import OperatorAlert

    _shop()
    fake.override[("POST", f"{BASE}/interruptions")] = _Resp(409, {"error": {"message": "InterruptionOverlap"}})
    record = ifood_merchant.request_pause(duration="1h", reason="Cozinha cheia", user=_user(), now=TUESDAY_10H)

    _run_interruption_directives()

    record.refresh_from_db()
    assert record.state == IFoodInterruptionState.FAILED
    assert "mesmo horário" in record.last_error
    assert OperatorAlert.objects.filter(type=ifood_merchant.ALERT_SYNC_FAILED).exists()


@override_settings(SHOPMAN_IFOOD=ON)
def test_pausa_ate_o_fim_do_expediente_termina_no_fechamento(fake):
    _shop()

    record = ifood_merchant.request_pause(duration="until_close", reason="Forno quebrado", user=_user(), now=TUESDAY_10H)

    assert record.ends_at == datetime(2026, 12, 22, 18, 0, tzinfo=TZ)


@override_settings(SHOPMAN_IFOOD=ON)
def test_pausa_com_a_loja_fechada_e_segunda_pausa_sao_recusadas():
    _shop()
    user = _user()

    with pytest.raises(ifood_merchant.PauseRefused, match="fechada"):
        ifood_merchant.request_pause(duration="1h", reason="x", user=user, now=datetime(2026, 12, 22, 20, 0, tzinfo=TZ))
    ifood_merchant.request_pause(duration="1h", reason="x", user=user, now=TUESDAY_10H)
    with pytest.raises(ifood_merchant.PauseRefused, match="já está pausado"):
        ifood_merchant.request_pause(duration="1h", reason="y", user=user, now=TUESDAY_10H)


# ── 3. Conferência ────────────────────────────────────────────────────────────

_CLOSED_NO_POLLING = [{
    "operation": "DELIVERY",
    "available": False,
    "state": "ERROR",
    "validations": [
        {"code": "is-connected", "state": "ERROR", "message": {"title": "Desconectado"}},
        {"code": "opening-hours", "state": "OK", "message": {"title": "Dentro do horário"}},
    ],
}]


@override_settings(SHOPMAN_IFOOD=ON)
def test_ifood_fechado_com_a_casa_aberta_alerta_na_segunda_conferencia(fake):
    from shopman.backstage.models import OperatorAlert

    _shop()
    fake.status = _CLOSED_NO_POLLING

    first = ifood_merchant.check_store(now=TUESDAY_10H)
    assert first.available is False and first.expected_available is True
    assert first.alerted == ""  # um instante de atraso do iFood não é defeito

    second = ifood_merchant.check_store(now=TUESDAY_10H + timedelta(minutes=5))

    assert second.alerted == ifood_merchant.ALERT_CLOSED_WHILE_OPEN
    alert = OperatorAlert.objects.get(type=ifood_merchant.ALERT_CLOSED_WHILE_OPEN)
    assert "ifood-poll-worker" in alert.message
    assert alert.get_type_display() == "iFood fechado com a loja aberta"


@override_settings(SHOPMAN_IFOOD=ON)
def test_ifood_aberto_com_a_casa_fechada_alerta(fake):
    from shopman.backstage.models import OperatorAlert

    _shop()
    evening = datetime(2026, 12, 22, 20, 0, tzinfo=TZ)

    ifood_merchant.check_store(now=evening)
    result = ifood_merchant.check_store(now=evening + timedelta(minutes=5))

    assert result.alerted == ifood_merchant.ALERT_OPEN_WHILE_CLOSED
    assert OperatorAlert.objects.filter(type=ifood_merchant.ALERT_OPEN_WHILE_CLOSED).count() == 1


@override_settings(SHOPMAN_IFOOD=ON)
def test_pausa_do_gestor_em_vigor_faz_a_casa_esperar_o_ifood_fechado(fake):
    _shop()
    ifood_merchant.request_pause(duration="1h", reason="Cozinha cheia", user=_user(), now=TUESDAY_10H)
    fake.status = [{"operation": "DELIVERY", "available": False, "state": "WARNING", "validations": [
        {"code": "unavailabilities", "state": "WARNING", "message": {"title": "Pausa"}},
    ]}]

    result = ifood_merchant.check_store(now=TUESDAY_10H + timedelta(minutes=1))

    assert result.expected_available is False
    assert IFoodStoreStatus.objects.get().divergent_since is None


@override_settings(SHOPMAN_IFOOD=ON)
def test_concordancia_limpa_a_divergencia_e_conferencia_pede_gravacao(fake):
    _shop()
    fake.status = _CLOSED_NO_POLLING
    ifood_merchant.check_store(now=TUESDAY_10H)
    fake.status = [{"operation": "DELIVERY", "available": True, "state": "OK", "validations": []}]

    ifood_merchant.check_store(now=TUESDAY_10H + timedelta(minutes=5))

    assert IFoodStoreStatus.objects.get().divergent_since is None
    # Nunca gravou (synced_at vazio): a conferência pede a gravação.
    assert Directive.objects.filter(topic=IFOOD_MERCHANT_SYNC).exists()


@override_settings(SHOPMAN_IFOOD=OFF)
def test_conferencia_desligada_nao_chama_o_ifood(fake):
    _shop()

    assert ifood_merchant.check_store(now=TUESDAY_10H) is None
    assert fake.calls == []


# ── API do Gestor ─────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_IFOOD=ON)
def test_api_quem_ve_a_fila_ve_o_status_mas_so_o_gerente_pausa(client, fake, monkeypatch):
    from django.utils import timezone

    monkeypatch.setattr(timezone, "now", lambda: TUESDAY_10H)  # loja aberta, sem depender do relógio
    _shop()
    caixa = _user("caixa", "manage_orders")
    gerente = _user("gerente", "manage_orders", "pause_ifood")

    client.force_login(caixa)
    projection = client.get(reverse("api-backstage-ifood-store")).json()
    assert projection["enabled"] is True and projection["can_pause"] is False
    denied = client.post(reverse("api-backstage-ifood-store-pause"), {"duration": "1h", "reason": "x"}, content_type="application/json")
    assert denied.status_code == 403

    client.force_login(gerente)
    ok = client.post(
        reverse("api-backstage-ifood-store-pause"),
        {"duration": "1h", "reason": "Cozinha cheia"},
        content_type="application/json",
    )
    assert ok.status_code == 200, ok.content
    body = ok.json()
    assert body["pause"]["state"] == "pending_create"
    assert body["pause"]["reason"] == "Cozinha cheia"
    assert body["pause"]["requested_by"] == "gerente"

    again = client.post(
        reverse("api-backstage-ifood-store-pause"),
        {"duration": "1h", "reason": "de novo"},
        content_type="application/json",
    )
    assert again.status_code == 409
    assert "já está pausado" in again.json()["detail"]

    resumed = client.post(reverse("api-backstage-ifood-store-resume"), {}, content_type="application/json")
    assert resumed.status_code == 200
    assert resumed.json()["pause"]["state"] == "pending_remove"


@override_settings(SHOPMAN_IFOOD=OFF)
def test_api_desligada_diz_so_que_esta_desligada(client):
    _shop()
    client.force_login(_user("gerente", "manage_orders", "pause_ifood"))

    body = client.get(reverse("api-backstage-ifood-store")).json()

    assert body["enabled"] is False
    assert body["pause"] is None and body["options"] == []
