"""A DANFE que vai na sacola da entrega (decisão do dono, 25/09/2026).

O que esta suíte prende:

- o papel é o do balcão (``danfe_nfce``), com o carimbo do balcão
  (``danfe_printed_at``) e "REIMPRESSÃO" quando já pode ter havido papel;
- a DANFE automática sai pelo SERVIDOR (``PrintJob`` no relay) para a
  impressora do despacho, sem depender de onde o Gestor está aberto; sai UMA
  vez, só na entrega despachada há pouco, e vale para as duas ordens do tempo:
  nota autorizada antes do despacho e depois;
- o despacho nunca espera a nota (a regra dura: expedição sem NFC-e só avisa);
- sem impressora, ou com a impressora sem responder, o card diz "não impressa"
  com o motivo, e um alerta de pedidos (não crítico) leva ao card e fecha
  sozinho quando a DANFE sai;
- retirada oferece imprimir e não imprime sozinha; iFood fica de fora.
"""

from __future__ import annotations

import base64
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from shopman.cashman.models import Terminal
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import OperatorAlert, PrintAgentCredential, PrintJob
from shopman.backstage.projections.order_queue import build_order_card
from shopman.backstage.services import order_danfe, print_jobs
from shopman.backstage.services.receipt_escpos import ENCODING
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

NOTA = {
    "nfce_access_key": "41260800000000000000650010000001521151375188",
    "nfce_status": "authorized",
    "nfce_number": 152,
    "nfce_series": 1,
    "nfce_protocol": "123",
    "nfce_qrcode_url": "http://www.fazenda.pr.gov.br/nfce/qrcode/?p=x",
}


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Nelson Boulangerie")


@pytest.fixture
def gestor(db, shop):
    user = User.objects.create_user("gestor-danfe", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    return user


@pytest.fixture
def logado(client, gestor):
    client.force_login(gestor)
    return client


@pytest.fixture
def balcao(db):
    """O balcão com o agente de impressão pareado ao relay."""
    terminal = Terminal.objects.create(ref="pdv-main", label="Balcão")
    credential, bearer = PrintAgentCredential.issue(terminal=terminal)
    return terminal, credential, bearer


def _order(
    ref: str,
    *,
    status: str = Order.Status.DISPATCHED,
    fulfillment: str = "delivery",
    channel_ref: str = "web",
    authorized: bool = True,
    dispatched_ago: timedelta | None = timedelta(seconds=20),
) -> Order:
    data = {"customer": {"name": "Ana"}, "payment": {"method": "pix"}, "fulfillment_type": fulfillment}
    if authorized:
        data.update(NOTA)
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, status=status, total_q=3600, data=data)
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO", name="Pão de fermentação natural", qty=2,
        unit_price_q=1800, line_total_q=3600,
    )
    if dispatched_ago is not None:
        Order.objects.filter(pk=order.pk).update(dispatched_at=timezone.now() - dispatched_ago)
        order.refresh_from_db()
    return order


def _post(client, ref: str, *, local_agent: bool = False):
    return client.post(
        reverse("api-backstage-order-danfe-escpos", args=[ref]),
        data={"local_agent": local_agent},
        content_type="application/json",
    )


def _paper(job: PrintJob) -> str:
    return bytes(job.payload).decode(ENCODING, "replace")


def _jobs(ref: str):
    return PrintJob.objects.filter(kind=PrintJob.Kind.ORDER_DANFE, order_ref=ref).order_by("pk")


def _alerts(ref: str):
    return OperatorAlert.objects.filter(type=order_danfe.ALERT_TYPE, order_ref=ref)


def _ack(bearer: str, credential, status: str):
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


# ── O estado do pedido ────────────────────────────────────────────────────


def test_entrega_despachada_com_nota_autorizada_imprime_sozinha():
    estado = order_danfe.danfe_state(_order("DLV-1"))

    assert estado == order_danfe.DanfeState(printable=True, printed=False, auto_print=True)


def test_nota_autorizada_ANTES_do_despacho_espera_o_despacho():
    pronto = _order("DLV-2", status=Order.Status.READY, dispatched_ago=None)

    assert order_danfe.danfe_state(pronto).auto_print is False

    Order.objects.filter(pk=pronto.pk).update(status=Order.Status.DISPATCHED, dispatched_at=timezone.now())
    pronto.refresh_from_db()
    assert order_danfe.danfe_state(pronto).auto_print is True


def test_fora_da_janela_a_sacola_ja_foi_e_nada_sai_sozinho():
    atrasado = _order("DLV-4", dispatched_ago=order_danfe.AUTO_PRINT_WINDOW + timedelta(seconds=1))

    estado = order_danfe.danfe_state(atrasado)
    assert estado.printable is True
    assert estado.auto_print is False


def test_ifood_fica_de_fora():
    assert order_danfe.danfe_state(_order("IFOOD-1", channel_ref="ifood")) == order_danfe.DanfeState()


# ── Para onde vai ─────────────────────────────────────────────────────────


def test_sem_agente_pareado_nao_ha_destino_e_a_frase_diz_o_que_fazer():
    Terminal.objects.create(ref="pdv-main", label="Balcão")

    destino = order_danfe.danfe_destination()

    assert destino.available is False
    assert "Terminais do PDV" in destino.problem
    assert "credencial do agente" in destino.problem


def test_o_balcao_com_agente_e_o_destino_padrao(balcao):
    terminal, _credential, _bearer = balcao
    outro = Terminal.objects.create(ref="cozinha", label="Cozinha")
    PrintAgentCredential.issue(terminal=outro)

    destino = order_danfe.danfe_destination()

    assert destino.terminal == terminal
    assert destino.label == "Balcão"


def test_a_impressora_marcada_vence_o_balcao(balcao):
    despacho = Terminal.objects.create(
        ref="despacho", label="Despacho", metadata={"station": {order_danfe.DESTINATION_FLAG: True}}
    )
    PrintAgentCredential.issue(terminal=despacho)

    assert order_danfe.danfe_destination().terminal == despacho


def test_marcada_sem_agente_diz_que_falta_o_agente(balcao):
    Terminal.objects.create(ref="despacho", label="Despacho", metadata={"station": {order_danfe.DESTINATION_FLAG: True}})

    destino = order_danfe.danfe_destination()

    assert destino.available is False
    assert "Despacho" in destino.problem


def test_duas_impressoras_sem_marca_e_sem_balcao_pede_para_marcar():
    for ref in ("a", "b"):
        PrintAgentCredential.issue(terminal=Terminal.objects.create(ref=ref, label=ref.upper()))

    destino = order_danfe.danfe_destination()

    assert destino.available is False
    assert "Imprime a DANFE das entregas" in destino.problem


# ── A automática, pelo servidor ───────────────────────────────────────────


def test_a_automatica_vai_para_o_relay_do_balcao_e_carimba(balcao):
    terminal, _credential, _bearer = balcao
    order = _order("DLV-6")

    job = order_danfe.enqueue_auto_print(order.ref)

    assert job is not None
    assert (job.kind, job.transport, job.status) == (
        PrintJob.Kind.ORDER_DANFE, PrintJob.Transport.RELAY, PrintJob.Status.QUEUED,
    )
    assert job.target_terminal == terminal
    assert job.order_ref == "DLV-6"
    assert job.requested_by is None
    texto = _paper(job)
    assert "DANFE NFC-e" in texto
    assert "Pedido DLV-6" in texto
    assert "REIMPRESSÃO" not in texto
    order.refresh_from_db()
    assert order.data.get("danfe_printed_at")


def test_a_automatica_sai_UMA_vez(balcao):
    order = _order("DLV-7")

    assert order_danfe.enqueue_auto_print(order.ref) is not None
    assert order_danfe.enqueue_auto_print(order.ref) is None
    assert _jobs(order.ref).count() == 1


def test_retirada_e_entrega_fora_da_janela_nao_saem_sozinhas(balcao):
    retirada = _order("PCK-1", status=Order.Status.READY, fulfillment="pickup", dispatched_ago=None)
    atrasada = _order("DLV-8", dispatched_ago=order_danfe.AUTO_PRINT_WINDOW + timedelta(minutes=1))

    assert order_danfe.enqueue_auto_print(retirada.ref) is None
    assert order_danfe.enqueue_auto_print(atrasada.ref) is None
    assert not PrintJob.objects.exists()


def test_a_nota_que_autoriza_depois_do_despacho_dispara_pelo_servidor(balcao, django_capture_on_commit_callbacks):
    """O caso normal: a nota nasce no despacho e a DANFE vai atrás dela."""
    from shopman.shop.handlers.fiscal import NFCeEmitHandler

    order = _order("DLV-9", authorized=False)
    order.data.update(NOTA)
    Order.objects.filter(pk=order.pk).update(data=order.data)
    handler = NFCeEmitHandler(backend=mock.Mock(spec=[]))

    with django_capture_on_commit_callbacks(execute=True):
        handler._after_authorized(order)

    assert _jobs(order.ref).count() == 1


def test_o_despacho_com_a_nota_ja_autorizada_dispara_pelo_servidor(balcao, django_capture_on_commit_callbacks):
    from shopman.orderman.signals import order_changed

    order = _order("DLV-10")

    with django_capture_on_commit_callbacks(execute=True):
        order_changed.send(sender=Order, order=order, event_type="status_changed", actor="teste")

    assert _jobs(order.ref).count() == 1


def test_sem_impressora_nada_e_carimbado_e_o_alerta_leva_ao_card(shop):
    order = _order("DLV-11")

    assert order_danfe.enqueue_auto_print(order.ref) is None

    order.refresh_from_db()
    assert "danfe_printed_at" not in order.data
    alerta = _alerts(order.ref).get()
    assert alerta.audience == "orders"
    assert alerta.severity == "warning"
    assert "Imprima pelo card do pedido" in alerta.message
    assert "Dedupe" not in alerta.message
    assert "—" not in alerta.message
    card = build_order_card(order)
    assert card.danfe_state == order_danfe.STATE_NOT_PRINTED
    assert "Terminais do PDV" in card.danfe_problem


# ── Depois que a impressora responde ──────────────────────────────────────


def test_o_card_acompanha_a_fila_e_a_impressora(shop, balcao):
    _terminal, credential, bearer = balcao
    order = _order("DLV-12")

    assert build_order_card(order).danfe_state == order_danfe.STATE_SENDING
    order_danfe.enqueue_auto_print(order.ref)
    order.refresh_from_db()
    assert build_order_card(order).danfe_state == order_danfe.STATE_SENDING

    _ack(bearer, credential, "spooled")

    card = build_order_card(order)
    assert (card.danfe_state, card.danfe_printed) == (order_danfe.STATE_PRINTED, True)


def test_impressora_que_recusa_abre_o_alerta_e_a_que_imprime_fecha(shop, balcao, django_capture_on_commit_callbacks):
    _terminal, credential, bearer = balcao
    order = _order("DLV-13")
    order_danfe.enqueue_auto_print(order.ref)

    with django_capture_on_commit_callbacks(execute=True):
        _ack(bearer, credential, "failed")

    order.refresh_from_db()
    card = build_order_card(order)
    assert card.danfe_state == order_danfe.STATE_NOT_PRINTED
    assert "recusou" in card.danfe_problem
    assert _alerts(order.ref).filter(resolved_at__isnull=True).count() == 1

    resposta = order_danfe.print_on_demand(order.ref)
    assert resposta.via == "relay"
    # O agente recusou: não houve papel, e a próxima não é reimpressão.
    assert resposta.reprint is False
    with django_capture_on_commit_callbacks(execute=True):
        _ack(bearer, credential, "spooled")

    assert _alerts(order.ref).filter(resolved_at__isnull=True).count() == 0


def test_impressora_que_nao_busca_vira_nao_impressa_e_alerta_no_worker(shop, balcao):
    order = _order("DLV-14")
    job = order_danfe.enqueue_auto_print(order.ref)
    PrintJob.objects.filter(pk=job.pk).update(created_at=timezone.now() - order_danfe.RELAY_GRACE - timedelta(seconds=1))
    order.refresh_from_db()

    card = build_order_card(order)
    assert card.danfe_state == order_danfe.STATE_NOT_PRINTED
    assert "não buscou a DANFE" in card.danfe_problem

    call_command("sweep_danfe_print_jobs")
    call_command("sweep_danfe_print_jobs")

    assert _alerts(order.ref).count() == 1


# ── O botão do card ───────────────────────────────────────────────────────


def test_o_botao_manda_para_a_impressora_do_despacho(logado, balcao):
    order = _order("DLV-15")

    resposta = _post(logado, order.ref)

    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True, "via": "relay", "reprint": False, "target_label": "Balcão"}
    job = _jobs(order.ref).get()
    assert job.requested_by is not None
    assert "REIMPRESSÃO" not in _paper(job)


def test_reimprimir_depois_do_papel_sai_REIMPRESSAO(logado, balcao):
    _terminal, credential, bearer = balcao
    order = _order("DLV-16")
    order_danfe.enqueue_auto_print(order.ref)
    _ack(bearer, credential, "spooled")

    resposta = _post(logado, order.ref).json()

    assert resposta["reprint"] is True
    assert "REIMPRESSÃO" in _paper(_jobs(order.ref).last())


def test_o_botao_substitui_a_automatica_ainda_na_fila(logado, balcao):
    order = _order("DLV-17")
    auto = order_danfe.enqueue_auto_print(order.ref)

    _post(logado, order.ref)

    auto.refresh_from_db()
    assert auto.status == PrintJob.Status.CANCELLED
    assert _jobs(order.ref).filter(status=PrintJob.Status.QUEUED).count() == 1


def test_sem_impressora_do_despacho_o_agente_local_da_estacao_imprime(logado):
    order = _order("PCK-2", status=Order.Status.READY, fulfillment="pickup", dispatched_ago=None)

    resposta = _post(logado, order.ref, local_agent=True)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["via"] == "local"
    assert corpo["title"] == "danfe:PCK-2"
    assert "DANFE NFC-e" in base64.b64decode(corpo["payload_b64"]).decode(ENCODING, "replace")


def test_sem_impressora_nenhuma_recusa_e_nao_carimba(logado):
    order = _order("DLV-18")

    resposta = _post(logado, order.ref)

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "danfe_no_printer"
    order.refresh_from_db()
    assert "danfe_printed_at" not in order.data


def test_sem_nota_autorizada_nao_ha_danfe(logado, balcao):
    resposta = _post(logado, _order("DLV-19", authorized=False).ref)

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "danfe_not_authorized"


def test_ifood_recusa_ate_a_mao(logado, balcao):
    resposta = _post(logado, _order("IFOOD-2", channel_ref="ifood").ref)

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "danfe_ifood"


def test_pedido_inexistente_e_404(logado):
    assert _post(logado, "NAO-EXISTE").status_code == 404


def test_sem_manage_orders_nao_imprime(client, shop):
    User.objects.create_user("sem-permissao", password="pw", is_staff=True)
    client.login(username="sem-permissao", password="pw")

    assert _post(client, _order("DLV-20").ref).status_code in (401, 403)


def test_a_danfe_nao_passa_pelo_reimprimir_de_etiqueta(logado, balcao):
    """A rota da Produção só conhece etiqueta: a DANFE ali seria 404."""
    order = _order("DLV-21")
    job = order_danfe.enqueue_auto_print(order.ref)

    from shopman.backstage.api.print_jobs import OperatorPrintJobMixin, PrintJobAPIError

    with pytest.raises(PrintJobAPIError):
        OperatorPrintJobMixin().job(mock.Mock(user=mock.Mock(pk=1)), job.ref)


# ── O quadro sabe na hora ─────────────────────────────────────────────────


def test_a_autorizacao_empurra_o_quadro_do_gestor(shop):
    from shopman.shop.handlers.fiscal import NFCeEmitHandler

    order = _order("DLV-22", authorized=False)
    resultado = mock.Mock(
        access_key=NOTA["nfce_access_key"], document_number=152, document_series=1,
        protocol_number="123", xml_url="", danfe_url="", qrcode_url="", status="authorized",
    )
    with mock.patch("shopman.shop.handlers._sse_emitters._emit_backstage") as emit:
        NFCeEmitHandler._record(order, resultado)

    emit.assert_called_once()
    args, _kwargs = emit.call_args
    assert (args[0], args[2]["kind"], args[2]["ref"]) == ("orders", "fiscal_changed", "DLV-22")


def test_a_resposta_da_impressora_empurra_o_quadro(shop, balcao, django_capture_on_commit_callbacks):
    _terminal, credential, bearer = balcao
    order = _order("DLV-23")
    order_danfe.enqueue_auto_print(order.ref)

    with mock.patch("shopman.shop.handlers._sse_emitters._emit_backstage") as emit:
        with django_capture_on_commit_callbacks(execute=True):
            _ack(bearer, credential, "spooled")

    kinds = [call.args[2]["kind"] for call in emit.call_args_list]
    assert "danfe_changed" in kinds


# ── Como trocar a impressora: o Admin do terminal ─────────────────────────


def _form_data(ref: str, **overrides) -> dict:
    data = {
        "ref": ref,
        "label": ref.title(),
        "channel_ref": "pdv",
        "location_ref": "",
        "is_active": "on",
        "drawer_adapter": "",
        "counter_agent_url": "http://127.0.0.1:47811",
        "drawer_pulse_pin": "0",
        "drawer_pulse_on_ms": "50",
        "drawer_pulse_off_ms": "500",
        "station_mode": "attended",
    }
    data.update(overrides)
    return data


def test_marcar_no_admin_leva_a_danfe_para_la_e_desmarca_a_outra(balcao):
    from shopman.backstage.admin.terminal import TerminalForm

    despacho = Terminal.objects.create(ref="despacho", label="Despacho")
    PrintAgentCredential.issue(terminal=despacho)
    antiga = Terminal.objects.create(
        ref="antiga", label="Antiga", metadata={"station": {order_danfe.DESTINATION_FLAG: True, "mode": "attended"}}
    )

    form = TerminalForm(_form_data("despacho", prints_delivery_danfe="on"), instance=despacho)
    assert form.is_valid(), form.errors
    form.save()

    assert order_danfe.danfe_destination().terminal == despacho
    assert order_danfe.DESTINATION_FLAG not in Terminal.objects.get(pk=antiga.pk).metadata["station"]
    assert TerminalForm(instance=Terminal.objects.get(pk=despacho.pk)).fields["prints_delivery_danfe"].initial is True

    form = TerminalForm(_form_data("despacho"), instance=Terminal.objects.get(pk=despacho.pk))
    assert form.is_valid(), form.errors
    form.save()

    assert order_danfe.danfe_destination().terminal.ref == "pdv-main"
