"""Gaveta aberta pelo tablet, com autoria, e a tolerância do caixa (decisões do dono, 04/10).

O que se prova aqui:

* toda abertura vira linha ``drawer_open`` no livro, com quem, de onde e por quê;
* o tablet pede pelo relay: a linha e o trabalho do pulso nascem juntos, o agente
  do terminal recebe os cinco bytes ``ESC p``, e a resposta volta ao livro;
* o pulso que ninguém buscou EXPIRA (nunca abre a gaveta minutos depois) e a
  tela lê isso, sem fingir sucesso;
* sem relay pareado, nada é gravado e a recusa diz por quê;
* a tolerância nasce depois do fechamento cego, só para quem audita, e fora
  dela abre um alerta do público ``finance``.
"""

from __future__ import annotations

import base64
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.exceptions import CashError
from shopman.cashman.models import Entry, Shift, Terminal

from shopman.backstage.models import OperatorAlert, PrintAgentCredential, PrintJob
from shopman.backstage.services import cash_tolerance, drawer_pulse, print_jobs
from shopman.backstage.services.exceptions import POSError
from shopman.backstage.services.receipt_escpos import drawer_kick

pytestmark = pytest.mark.django_db

AGENT = {"adapter": "agent", "pulse_pin": 0, "pulse_on_ms": 50, "pulse_off_ms": 500}


def _terminal_with_drawer() -> Terminal:
    terminal = Terminal.default()
    terminal.label = "Balcão"
    terminal.metadata = {
        "hardware": {
            "cash_drawer": AGENT,
            "device_agent": {"enabled": True, "agent_url": "http://127.0.0.1:47811", "token": "t" * 32},
        }
    }
    terminal.save()
    return terminal


@pytest.fixture
def operator():
    user = get_user_model().objects.create_user(username="jo", password="x", is_staff=True)
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="operate_pos"))
    return user


@pytest.fixture
def shift(operator):
    return cash.open_shift(operator=operator, terminal=_terminal_with_drawer(), float_q=10000)


@pytest.fixture
def credential(shift):
    credential, bearer = PrintAgentCredential.issue(terminal=shift.terminal, label="PC do Balcão")
    credential.last_seen_at = timezone.now()
    credential.save(update_fields=["last_seen_at"])
    return credential


def _cash_sale(shift, operator, *, order_ref="M6-1012", cash_q=5500, change_q=4500):
    return cash.record(
        "sale",
        shift=shift,
        operator=operator,
        amount_q=cash_q,
        order_ref=order_ref,
        payload={"method": "cash", "received_q": cash_q + change_q, "change_q": change_q},
    )


# ── O livro: toda abertura tem porquê ─────────────────────────────────────


def test_o_livro_recusa_abertura_por_venda_sem_pedido(shift, operator):
    with pytest.raises(CashError, match="pedido"):
        cash.record("drawer_open", shift=shift, operator=operator, payload={"purpose": "sale"})


def test_o_livro_recusa_abertura_sem_venda_sem_motivo(shift, operator):
    with pytest.raises(CashError, match="motivo"):
        cash.record("drawer_open", shift=shift, operator=operator, payload={"purpose": "no_sale"})


def test_o_livro_recusa_porque_desconhecido(shift, operator):
    with pytest.raises(CashError):
        cash.record("drawer_open", shift=shift, operator=operator, reason="x", payload={"purpose": "festa"})


def test_abertura_pelo_balcao_grava_linha_local(shift, operator):
    entry, job = drawer_pulse.open_drawer(operator=operator, purpose="no_sale", reason="Troco", via="local")

    assert job is None
    assert entry.kind == Entry.Kind.DRAWER_OPEN
    assert entry.payload["purpose"] == "no_sale"
    assert entry.payload["via"] == "local"
    assert entry.amount_q == 0


def test_abertura_por_venda_exige_que_o_dinheiro_tenha_entrado_nesta_gaveta(shift, operator, credential):
    with pytest.raises(POSError, match="não entrou em dinheiro"):
        drawer_pulse.open_drawer(operator=operator, purpose="sale", order_ref="M6-9999", via="relay")
    assert not Entry.objects.filter(kind=Entry.Kind.DRAWER_OPEN).exists()
    assert not PrintJob.objects.filter(kind=PrintJob.Kind.DRAWER_PULSE).exists()


# ── O tablet pede pelo relay ───────────────────────────────────────────────


def test_tablet_pede_e_o_relay_leva_o_pulso_com_autoria(shift, operator, credential):
    _cash_sale(shift, operator)

    entry, job = drawer_pulse.open_drawer(operator=operator, purpose="sale", order_ref="M6-1012", via="relay")

    assert entry.operator == operator
    assert entry.order_ref == "M6-1012"
    assert entry.reason == "Venda M6-1012"
    assert entry.payload == {"purpose": "sale", "via": "relay", "pulse_job": str(job.ref)}
    assert job.kind == PrintJob.Kind.DRAWER_PULSE
    assert job.transport == PrintJob.Transport.RELAY
    assert job.target_terminal == shift.terminal
    assert bytes(job.payload) == drawer_kick(pin=0, on_ms=50, off_ms=500) == bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])
    assert job.document["entry_id"] == entry.pk
    # O pulso vale segundos: chegar depois abriria a gaveta sem ninguém na frente.
    assert job.expires_at - job.created_at <= drawer_pulse.PULSE_WINDOW + timedelta(seconds=1)


def test_o_agente_busca_entrega_e_a_resposta_volta_ao_livro(shift, operator, credential, django_capture_on_commit_callbacks):
    _cash_sale(shift, operator)
    entry, job = drawer_pulse.open_drawer(operator=operator, purpose="sale", order_ref="M6-1012", via="relay")

    claimed = print_jobs.claim_next_job(credential=credential, telemetry={"build": "t"})
    assert claimed is not None
    claimed_job, attempt, lease = claimed
    data = print_jobs.claimed_job_data(claimed_job, attempt, lease)
    assert base64.b64decode(data["payload_b64"]) == bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])
    assert data["kind"] == "drawer_pulse"

    with django_capture_on_commit_callbacks(execute=True):
        print_jobs.acknowledge_job(
            credential=credential,
            job_ref=job.ref,
            status="spooled",
            spooler_job_id="cups-1",
            detail="",
            payload_sha256=job.payload_sha256,
            lease_token=lease,
            telemetry={},
        )

    state = drawer_pulse.pulse_state(ref=job.ref, terminal_ref=shift.terminal.ref)
    assert state.state == "sent"
    note = Entry.objects.get(parent=entry, kind=Entry.Kind.NOTE)
    assert note.payload["event"] == "drawer_pulse_result"
    assert note.payload["status"] == "sent"


def test_pulso_que_ninguem_buscou_expira_e_a_tela_le_que_nao_abriu(shift, operator, credential):
    entry, job = drawer_pulse.open_drawer(operator=operator, purpose="no_sale", reason="Troco", via="relay")
    PrintJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))

    state = drawer_pulse.pulse_state(ref=job.ref, terminal_ref=shift.terminal.ref)

    assert state.state == "expired"
    assert "não abriu" in state.message
    # Nem o agente que volta depois leva o pulso vencido.
    assert print_jobs.claim_next_job(credential=credential, telemetry={}) is None
    note = Entry.objects.get(parent=entry, kind=Entry.Kind.NOTE)
    assert note.payload["status"] == "expired"


def test_sem_relay_pareado_nada_e_gravado_e_a_recusa_diz_por_que(shift, operator):
    with pytest.raises(POSError, match="credencial do relay"):
        drawer_pulse.open_drawer(operator=operator, purpose="no_sale", reason="Troco", via="relay")
    assert not Entry.objects.filter(kind=Entry.Kind.DRAWER_OPEN).exists()


def test_gaveta_de_chave_nao_tem_pulso(shift, operator):
    terminal = shift.terminal
    terminal.metadata = {"hardware": {"cash_drawer": {"adapter": "manual"}}}
    terminal.save()
    capability = drawer_pulse.relay_capability(terminal)
    assert capability["available"] is False
    assert "chave" in capability["reason"]


def test_capacidade_do_relay_diz_quando_o_agente_sumiu(shift, credential):
    assert drawer_pulse.relay_capability(shift.terminal)["online"] is True
    credential.last_seen_at = timezone.now() - timedelta(minutes=5)
    credential.save(update_fields=["last_seen_at"])
    capability = drawer_pulse.relay_capability(shift.terminal)
    assert capability["available"] is True
    assert capability["online"] is False
    assert "não responde" in capability["reason"]


def test_endpoint_do_tablet_pede_e_acompanha_o_pulso(client, shift, operator, credential):
    from shopman.backstage.tests.pos_test_runtime import bind_station

    _cash_sale(shift, operator)
    client.force_login(operator)
    bind_station(client, shift.terminal.ref)

    response = client.post(
        reverse("api-backstage-pos-cash-drawer-open"),
        data={"purpose": "sale", "order_ref": "M6-1012", "via": "relay"},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["pulse"]["state"] == "sending"

    status = client.get(reverse("api-backstage-pos-cash-drawer-pulse", args=[body["pulse"]["ref"]]))
    assert status.status_code == 200
    assert status.json()["pulse"]["state"] == "sending"


def test_endpoint_sem_venda_sem_motivo_e_recusado(client, shift, operator, credential):
    from shopman.backstage.tests.pos_test_runtime import bind_station

    client.force_login(operator)
    bind_station(client, shift.terminal.ref)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-open"),
        data={"purpose": "no_sale", "via": "relay"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "motivo" in response.json()["detail"]


def test_bi_nao_conta_abertura_por_venda_como_abertura_sem_venda(shift, operator, credential):
    from shopman.backstage.projections.bi_cash import build_bi_cash

    _cash_sale(shift, operator)
    drawer_pulse.open_drawer(operator=operator, purpose="sale", order_ref="M6-1012", via="relay")
    drawer_pulse.open_drawer(operator=operator, purpose="no_sale", reason="Troco", via="local")

    today = timezone.localdate()
    report = build_bi_cash(date_from=today, date_to=today)
    (row,) = [r for r in report.by_operator if r.operator == "jo"]
    assert row.drawer_openings == 1


# ── Tolerância ─────────────────────────────────────────────────────────────


def test_regua_padrao_do_dono():
    policy = cash_tolerance.TolerancePolicy()
    assert policy.tolerance_q(0) == 200  # piso R$ 2
    assert policy.tolerance_q(100_000) == 500  # 0,5% de R$ 1.000
    assert policy.tolerance_q(10_000_000) == 2000  # teto R$ 20


def test_terminal_sobrescreve_a_loja_chave_a_chave(shift):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja", defaults={"pos": {"cash_tolerance": {"percent": "1", "min_q": 300}}})
    terminal = shift.terminal
    terminal.metadata = {**terminal.metadata, "cash_tolerance": {"max_q": 1000}}
    terminal.save()

    policy = cash_tolerance.policy_for(terminal)
    assert policy == cash_tolerance.TolerancePolicy(percent=Decimal("1"), min_q=300, max_q=1000)


def test_valor_ilegivel_nao_desliga_a_regua(shift):
    terminal = shift.terminal
    terminal.metadata = {**terminal.metadata, "cash_tolerance": {"percent": "muito", "min_q": -5, "max_q": "x"}}
    terminal.save()
    assert cash_tolerance.policy_for(terminal) == cash_tolerance.TolerancePolicy()


def test_fechamento_dentro_da_tolerancia_so_registra(shift, operator, django_capture_on_commit_callbacks):
    _cash_sale(shift, operator, cash_q=100_000, change_q=0)
    with django_capture_on_commit_callbacks(execute=True):
        cash.close_shift(shift, counted_q=10000 + 100_000 - 300, actor=operator)

    note = Entry.objects.get(shift=shift, kind=Entry.Kind.NOTE, payload__event="cash_tolerance")
    assert note.payload["within"] is True
    assert note.payload["tolerance_q"] == 500
    assert not OperatorAlert.objects.filter(type="cash_out_of_tolerance").exists()


def test_fechamento_fora_da_tolerancia_avisa_so_quem_audita(shift, operator, django_capture_on_commit_callbacks):
    _cash_sale(shift, operator, cash_q=100_000, change_q=0)
    with django_capture_on_commit_callbacks(execute=True):
        cash.close_shift(shift, counted_q=10000 + 100_000 - 2500, actor=operator)

    note = Entry.objects.get(shift=shift, kind=Entry.Kind.NOTE, payload__event="cash_tolerance")
    assert note.payload["within"] is False
    alert = OperatorAlert.objects.get(type="cash_out_of_tolerance")
    assert alert.audience == "finance"
    assert "falta de R$ 25,00" in alert.message


def test_correcao_da_contagem_refaz_o_veredito(shift, operator, django_capture_on_commit_callbacks):
    manager = get_user_model().objects.create_user(username="gerente", password="x")
    with django_capture_on_commit_callbacks(execute=True):
        cash.close_shift(shift, counted_q=10000 - 1000, actor=operator)
    with django_capture_on_commit_callbacks(execute=True):
        cash.correct_count(shift, delta_q=1000, actor=manager, approved_by=manager, reason="recontei")

    verdicts = list(
        Entry.objects.filter(shift=shift, kind=Entry.Kind.NOTE, payload__event="cash_tolerance").order_by("id")
    )
    assert [v.payload["within"] for v in verdicts] == [False, True]


def test_o_veredito_nunca_chega_a_projection_do_operador(shift, operator, django_capture_on_commit_callbacks):
    """O fechamento é cego: nem o X/Z do balcão nem a projection do PDV falam em tolerância."""
    from dataclasses import asdict

    from shopman.backstage.projections.cash_session import build_cash_session_report

    with django_capture_on_commit_callbacks(execute=True):
        cash.close_shift(shift, counted_q=1, actor=operator)
    report = asdict(build_cash_session_report(operator=operator, terminal_ref=shift.terminal.ref))
    assert "toler" not in repr(report).lower()
