"""A Via Cozinha: o posto do KDS sem tela recebe os pedidos impressos.

Decisão do dono (26/09/2026): o posto de Lanches tem só uma impressora térmica
de rede. O que esta suíte prende:

- posto com impressora escolhida gera UM papel por ticket, pelo relay, para o
  terminal escolhido; posto sem impressora não gera nada;
- o papel é idempotente por ticket (série determinística) e expira cedo;
- ticket cancelado sai como papel CANCELADO, com os itens retirados; ticket
  vivo cancelado só desdiz o papel que pode ter saído;
- o leiaute não tem preço, traz as observações e diz REIMPRESSÃO;
- pedido de teste não imprime; impressora sem agente pareado vira alerta;
- imprimir NÃO muda o status do ticket.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.cashman.models import Terminal
from shopman.orderman.models import Order

from shopman.backstage.admin.kds import KDSInstanceAdmin
from shopman.backstage.models import KDSInstance, KDSTicket, OperatorAlert, PrintAgentCredential, PrintJob
from shopman.backstage.services import kitchen_ticket_print, print_jobs
from shopman.backstage.services.receipt_escpos import ENCODING, kitchen_ticket
from shopman.shop.adapters import kds as kds_adapter

pytestmark = pytest.mark.django_db

ITENS = [
    {"sku": "X-BURGUER", "name": "X-Burguer da casa", "qty": 2, "notes": "sem cebola", "line_id": "L1"},
    {"sku": "CROQUE", "name": "Croque Monsieur", "qty": 1, "notes": "", "line_id": "L2"},
]


@pytest.fixture
def impressora(db):
    """A TM-T20X do posto, com o agente pareado ao relay."""
    terminal = Terminal.objects.create(ref="lanches-printer", label="Impressora Lanches")
    credential, bearer = PrintAgentCredential.issue(terminal=terminal)
    return terminal, credential, bearer


@pytest.fixture
def posto(impressora):
    terminal, _credential, _bearer = impressora
    return KDSInstance.objects.create(ref="lanches", name="Lanches", type="prep", print_terminal=terminal)


@pytest.fixture
def pedido(db):
    return Order.objects.create(
        ref="WEB-20260926-1012",
        channel_ref="web",
        session_key="sess-via-cozinha",
        status=Order.Status.PREPARING,
        total_q=5400,
        data={
            "customer": {"name": "Maria Aparecida da Silva Xavier"},
            "fulfillment_type": "delivery",
            "kitchen_note": "Mandar guardanapo extra",
            "order_notes": "Tocar a campainha",
        },
    )


def _ticket(posto, pedido, *, items=None, status="pending", on_commit=None) -> KDSTicket:
    kwargs = {"session_key": pedido.session_key, "kds_instance": posto, "items": items or ITENS, "status": status}
    if status == "cancelled":
        kwargs["cancelled_at"] = timezone.now()
    if on_commit is None:
        return KDSTicket.objects.create(**kwargs)
    with on_commit(execute=True):
        return KDSTicket.objects.create(**kwargs)


def _jobs():
    return PrintJob.objects.filter(kind=PrintJob.Kind.KITCHEN_TICKET).order_by("pk")


def _paper(job_or_bytes) -> str:
    raw = job_or_bytes if isinstance(job_or_bytes, bytes) else bytes(job_or_bytes.payload)
    return raw.decode(ENCODING, "replace")


def _claim_and_ack(credential, bearer, status: str):
    claimed = print_jobs.claim_next_job(credential=credential, telemetry={"build": "t"})
    assert claimed is not None
    job, _attempt, lease_token = claimed
    return print_jobs.acknowledge_job(
        credential=PrintAgentCredential.authenticate(bearer),
        job_ref=job.ref,
        status=status,
        spooler_job_id="cups-1" if status == "spooled" else "",
        detail="",
        payload_sha256=job.payload_sha256,
        lease_token=lease_token,
        telemetry={},
    )


# ── O disparo ─────────────────────────────────────────────────────────


def test_posto_com_impressora_gera_um_papel_por_ticket(posto, pedido, impressora, django_capture_on_commit_callbacks):
    terminal, _credential, _bearer = impressora
    ticket = _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)

    jobs = list(_jobs())
    assert len(jobs) == 1
    job = jobs[0]
    assert job.transport == PrintJob.Transport.RELAY
    assert job.status == PrintJob.Status.QUEUED
    assert job.target_terminal == terminal
    assert job.order_ref == pedido.ref
    assert job.requested_station_ref == "lanches"
    assert job.series_ref == kitchen_ticket_print.series_ref_for(ticket.pk, moment="fired")
    assert job.document["kds_ticket"] == ticket.pk
    assert job.document["moment"] == "fired"
    papel = _paper(job)
    assert "LANCHES" in papel
    assert "X-Burguer da casa" in papel


def test_um_segundo_posto_ganha_o_proprio_papel(posto, pedido, django_capture_on_commit_callbacks):
    outra = Terminal.objects.create(ref="cafe-printer", label="Impressora Café")
    PrintAgentCredential.issue(terminal=outra)
    cafe = KDSInstance.objects.create(ref="cafe", name="Café", type="prep", print_terminal=outra)
    _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)
    _ticket(cafe, pedido, items=[ITENS[1]], on_commit=django_capture_on_commit_callbacks)

    assert [job.target_terminal.ref for job in _jobs()] == ["lanches-printer", "cafe-printer"]


def test_posto_sem_impressora_nao_gera_papel(pedido, django_capture_on_commit_callbacks):
    tela = KDSInstance.objects.create(ref="confeitaria", name="Confeitaria", type="prep")
    _ticket(tela, pedido, on_commit=django_capture_on_commit_callbacks)

    assert not _jobs().exists()


def test_o_papel_e_idempotente_por_ticket(posto, pedido, django_capture_on_commit_callbacks):
    ticket = _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)

    # O mesmo papel pedido de novo (on_commit duplicado, sinal repetido)…
    assert kitchen_ticket_print.enqueue(ticket.pk, created=True) is None
    # …e o ticket que anda na tela: nenhum save que não crie ou cancele imprime.
    with django_capture_on_commit_callbacks(execute=True):
        ticket.status = "in_progress"
        ticket.save(update_fields=["status"])
        ticket.status = "done"
        ticket.completed_at = timezone.now()
        ticket.save(update_fields=["status", "completed_at"])

    assert _jobs().count() == 1


def test_imprimir_nao_muda_o_status_do_ticket(posto, pedido, impressora, django_capture_on_commit_callbacks):
    _terminal, credential, bearer = impressora
    ticket = _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        job = _claim_and_ack(credential, bearer, "spooled")

    assert job.status == PrintJob.Status.SPOOLED
    ticket.refresh_from_db()
    assert ticket.status == "pending"
    assert kitchen_ticket_print.on_print_behavior(posto) == kitchen_ticket_print.ON_PRINT_KEEP


def test_o_papel_expira_cedo(posto, pedido, impressora, django_capture_on_commit_callbacks):
    """Um agente que volta de pane não imprime a comanda de horas atrás."""
    _terminal, credential, _bearer = impressora
    antes = timezone.now()
    _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)
    job = _jobs().get()
    assert antes + kitchen_ticket_print.AUTO_PRINT_WINDOW - timedelta(seconds=5) <= job.expires_at
    assert job.expires_at <= timezone.now() + kitchen_ticket_print.AUTO_PRINT_WINDOW
    assert kitchen_ticket_print.AUTO_PRINT_WINDOW <= timedelta(minutes=10)

    PrintJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert print_jobs.claim_next_job(credential=credential, telemetry={}) is None
    job.refresh_from_db()
    assert job.status == PrintJob.Status.EXPIRED


def test_pedido_de_teste_nao_imprime(posto, pedido, django_capture_on_commit_callbacks):
    pedido.data = {**pedido.data, "ifood": {"is_test": True}}
    pedido.save(update_fields=["data"])
    _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)

    assert not _jobs().exists()


# ── O CANCELADO ───────────────────────────────────────────────────────


def test_itens_retirados_saem_num_papel_cancelado(posto, pedido, django_capture_on_commit_callbacks):
    ticket = _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        result = kds_adapter.unfire_session_lines(pedido.session_key, ["L1"])
    assert result == {"cancelled": 0, "trimmed": 1}

    fired, cancelled = list(_jobs())
    assert fired.document["kds_ticket"] == ticket.pk
    assert cancelled.document["moment"] == "cancelled"
    papel = _paper(cancelled)
    assert "CANCELADO" in papel
    assert "NÃO PREPARE" in papel
    assert "X-Burguer da casa" in papel
    assert "Croque Monsieur" not in papel


def test_ticket_cancelado_depois_do_papel_sair_manda_o_cancelado(
    posto, pedido, impressora, django_capture_on_commit_callbacks
):
    _terminal, credential, bearer = impressora
    ticket = _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        _claim_and_ack(credential, bearer, "spooled")
    with django_capture_on_commit_callbacks(execute=True):
        kds_adapter.cancel_open_tickets_for_session(pedido.session_key)

    fired, cancelled = list(_jobs())
    assert cancelled.series_ref == kitchen_ticket_print.series_ref_for(ticket.pk, moment="cancelled")
    assert "CANCELADO" in _paper(cancelled)
    assert "Croque Monsieur" in _paper(cancelled)


def test_ticket_cancelado_com_o_papel_ainda_na_fila_nao_imprime_nenhum(
    posto, pedido, django_capture_on_commit_callbacks
):
    _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        kds_adapter.cancel_open_tickets_for_session(pedido.session_key)

    jobs = list(_jobs())
    assert len(jobs) == 1
    assert jobs[0].status == PrintJob.Status.CANCELLED


# ── O leiaute ─────────────────────────────────────────────────────────


def test_o_leiaute_nao_tem_preco_e_traz_as_observacoes(posto, pedido):
    ticket = _ticket(posto, pedido)
    raw = kitchen_ticket(ticket)
    papel = _paper(raw)

    assert "R$" not in papel
    assert "54,00" not in papel
    assert "2 x X-Burguer da casa" in papel
    assert ">> sem cebola" in papel
    assert "1 x Croque Monsieur" in papel
    assert "Nota da cozinha:" in papel and "Mandar guardanapo extra" in papel
    assert "Observação do cliente:" in papel and "Tocar a campainha" in papel
    assert "WEB-20260926-1012" in papel
    # O nome de chamada encurta pelo meio, como na ficha do pedido.
    assert "Maria Xavier" in papel
    assert "ENTREGA" in papel
    assert "REIMPRESS" not in papel
    assert "2a VIA" not in papel
    # Reset no começo, corte parcial no fim.
    assert raw.startswith(b"\x1b@")
    assert raw.endswith(b"\x1dV\x01")


def test_a_reimpressao_diz_reimpressao_e_nunca_segunda_via(posto, pedido):
    papel = _paper(kitchen_ticket(_ticket(posto, pedido), reprint=True))

    assert "*** REIMPRESSÃO ***" in papel
    assert "2a VIA" not in papel


# ── Quando não sai ────────────────────────────────────────────────────


def test_impressora_sem_agente_pareado_vira_alerta_e_nao_papel(pedido, django_capture_on_commit_callbacks):
    sem_agente = Terminal.objects.create(ref="sem-agente", label="Impressora nova")
    posto = KDSInstance.objects.create(ref="lanches", name="Lanches", type="prep", print_terminal=sem_agente)
    ticket = _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)

    assert not _jobs().exists()
    alerta = OperatorAlert.objects.get(type=kitchen_ticket_print.ALERT_TYPE)
    assert alerta.audience == "orders"
    assert alerta.order_ref == pedido.ref
    assert f"Via Cozinha #{ticket.pk}:" in alerta.message
    assert "Lanches" in alerta.message


def test_recusa_do_agente_abre_o_alerta(posto, pedido, impressora, django_capture_on_commit_callbacks):
    _terminal, credential, bearer = impressora
    _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        _claim_and_ack(credential, bearer, "failed")

    assert OperatorAlert.objects.filter(type=kitchen_ticket_print.ALERT_TYPE, resolved_at__isnull=True).count() == 1


def test_papel_que_ninguem_buscou_vira_alerta_na_varredura(posto, pedido, django_capture_on_commit_callbacks):
    _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)
    PrintJob.objects.filter(kind=PrintJob.Kind.KITCHEN_TICKET).update(
        created_at=timezone.now() - kitchen_ticket_print.RELAY_GRACE - timedelta(seconds=1)
    )
    call_command("sweep_kitchen_print_jobs")
    call_command("sweep_kitchen_print_jobs")

    assert OperatorAlert.objects.filter(type=kitchen_ticket_print.ALERT_TYPE).count() == 1


def test_a_etiqueta_da_producao_nao_alcanca_a_via_cozinha(posto, pedido, django_capture_on_commit_callbacks):
    """A rota de reimpressão das etiquetas não pode passar a Via Cozinha pelo
    compositor de etiqueta: ela só enxerga os dois tipos de etiqueta."""
    from shopman.backstage.api.print_jobs import OperatorPrintJobMixin, PrintJobAPIError

    _ticket(posto, pedido, on_commit=django_capture_on_commit_callbacks)
    job = _jobs().get()
    with pytest.raises(PrintJobAPIError):
        OperatorPrintJobMixin().job(request=None, ref=job.ref)


# ── O Admin do posto ──────────────────────────────────────────────────


def test_o_admin_do_posto_mostra_a_saude_da_impressora(posto, impressora):
    from django.contrib import admin

    model_admin = KDSInstanceAdmin(KDSInstance, admin.site)
    assert "Aguardando estação" in str(model_admin.print_destination_display(posto))

    _terminal, credential, _bearer = impressora
    credential.last_seen_at = timezone.now()
    credential.save(update_fields=["last_seen_at"])
    assert "Pronta" in str(model_admin.print_destination_display(posto))

    tela = KDSInstance.objects.create(ref="confeitaria", name="Confeitaria", type="prep")
    assert "usa a tela" in str(model_admin.print_destination_display(tela))

    nova = Terminal.objects.create(ref="sem-agente", label="Impressora nova")
    posto.print_terminal = nova
    assert "Relay não pareado" in str(model_admin.print_destination_display(posto))
