"""O sino do Gestor de pedidos: só o que é de pedido, com o gesto ao lado, e
fechando sozinho quando a operação resolve (pedido do dono, 25/09/2026).

O que esta suíte prende:

- ``?scope=orders`` deixa no sino só o que é de pedido; infraestrutura,
  marketing e B.I. ficam no Admin;
- a mensagem chega sem o marcador técnico "Dedupe:" (que continua no banco,
  porque o dedupe e ``fiscal.emit_failed_alert_open`` procuram por ele);
- todo alerta de pedido leva ao pedido ("Abrir o pedido");
- "Visto" funciona com o corpo que o Gestor manda;
- o fato que encerra a causa fecha o alerta: aceite, nota autorizada, nota
  reprocessada, maquininha de volta, corrida viva, pedido cancelado;
- os alertas do ciclo do pedido falam português, com o que fazer.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.orderman.models import Order
from shopman.orderman.signals import order_changed

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.alerts import readable_message
from shopman.shop.models import Shop
from shopman.shop.services.observability import create_operator_alert

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Nelson Boulangerie")


@pytest.fixture
def gestor(db, shop):
    user = User.objects.create_user("gestor-alertas", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    return user


def _alert(type_: str, *, order_ref: str = "", message: str = "", audience: str = "") -> OperatorAlert:
    return OperatorAlert.objects.create(
        type=type_,
        severity="warning",
        message=message or f"alerta {type_}",
        order_ref=order_ref,
        **({"audience": audience} if audience else {}),
    )


def _open(type_: str, ref: str) -> bool:
    return OperatorAlert.objects.filter(type=type_, order_ref=ref, resolved_at__isnull=True).exists()


def _order(ref: str, *, status: str = Order.Status.NEW) -> Order:
    return Order.objects.create(ref=ref, channel_ref="web", status=status, total_q=1000, data={})


def _changed(order: Order, status: str) -> None:
    order.status = status
    order_changed.send(sender=Order, order=order, event_type="status_changed", actor="teste")


# ── O que chega ao sino ───────────────────────────────────────────────────


def test_o_sino_do_gestor_so_mostra_o_que_e_de_pedido(client, gestor):
    _alert("stale_new_order", order_ref="WEB-1")
    _alert("fiscal_emit_failed", order_ref="WEB-2")
    _alert("directive_backlog")
    _alert("marketing_outbox_stuck")
    _alert("ifood_store_closed_while_open")
    _alert("fiscal_intermediary_not_declared", order_ref="IFOOD-1")
    client.force_login(gestor)

    geral = client.get(reverse("api-backstage-alerts")).json()
    pedidos = client.get(reverse("api-backstage-alerts"), {"scope": "orders"}).json()

    assert {a["type"] for a in geral["alerts"]} >= {"directive_backlog", "marketing_outbox_stuck"}
    assert {a["type"] for a in pedidos["alerts"]} == {
        "stale_new_order",
        "fiscal_emit_failed",
        "ifood_store_closed_while_open",
    }
    assert pedidos["counts"]["active"] == 3


def test_a_mensagem_chega_sem_o_marcador_de_dedupe_que_segue_no_banco(client, gestor):
    create_operator_alert(
        type="fiscal_emit_failed",
        severity="critical",
        order_ref="WEB-3",
        message="A NFC-e do pedido WEB-3 não foi autorizada.",
        dedupe_key="fiscal_emit_failed:WEB-3",
    )
    client.force_login(gestor)

    lida = client.get(reverse("api-backstage-alerts"), {"scope": "orders"}).json()["alerts"][0]

    assert lida["message"] == "A NFC-e do pedido WEB-3 não foi autorizada."
    assert "Dedupe: fiscal_emit_failed:WEB-3" in OperatorAlert.objects.get().message
    assert readable_message("frase\n\nDedupe: x:1") == "frase"


def test_todo_alerta_de_pedido_leva_ao_pedido(client, gestor):
    _alert("courier_not_attended", order_ref="WEB-4")
    _alert("danfe_print_failed", order_ref="WEB-5", audience="orders")
    client.force_login(gestor)

    alertas = {a["type"]: a for a in client.get(reverse("api-backstage-alerts"), {"scope": "orders"}).json()["alerts"]}
    abrir = {a["type"]: next(x for x in a["actions"] if x["kind"] == "open_alert_context") for a in alertas.values()}

    assert (abrir["courier_not_attended"]["label"], abrir["courier_not_attended"]["href"]) == ("Abrir o pedido", "/WEB-4")
    assert (abrir["danfe_print_failed"]["label"], abrir["danfe_print_failed"]["href"]) == (
        "Imprimir a DANFE no card",
        "/?q=WEB-5",
    )


def test_visto_funciona_com_o_corpo_que_o_gestor_manda(client, gestor):
    alerta = _alert("stale_new_order", order_ref="WEB-6")
    client.force_login(gestor)
    leitura = client.get(reverse("api-backstage-alerts"), {"scope": "orders"}).json()
    acao = next(a for a in leitura["alerts"][0]["actions"] if a["kind"] == "acknowledge_alert")

    resposta = client.post(
        reverse("api-backstage-alert-ack", args=[alerta.pk]),
        data={
            "idempotency_key": "visto-1",
            "expected_rev": acao["expected_rev"],
            "projection_generated_at": leitura["generated_at"],
            "source_revision": leitura["source_revision"],
            "fresh_until": leitura["fresh_until"],
            "contract_version": leitura["contract_version"],
            "action_ref": acao["ref"],
            "action_proof": acao["proof"],
        },
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    alerta.refresh_from_db()
    assert alerta.acknowledged is True
    assert alerta.resolved_at is None, "Visto é ciência; quem fecha é a causa acabar"


# ── O fato que encerra a causa fecha o alerta ─────────────────────────────


def test_aceitar_o_pedido_fecha_os_avisos_de_espera(django_capture_on_commit_callbacks):
    order = _order("WEB-7")
    _alert("stale_new_order", order_ref=order.ref)
    _alert("payment_awaiting_confirmation", order_ref=order.ref)

    with django_capture_on_commit_callbacks(execute=True):
        _changed(order, Order.Status.ACCEPTED)

    assert not _open("stale_new_order", order.ref)
    assert not _open("payment_awaiting_confirmation", order.ref)


def test_cancelar_fecha_espera_corrida_e_danfe_mas_nao_a_nota(django_capture_on_commit_callbacks):
    order = _order("WEB-8", status=Order.Status.DISPATCHED)
    for tipo in ("courier_not_attended", "danfe_print_failed", "fiscal_emit_failed"):
        _alert(tipo, order_ref=order.ref)

    with django_capture_on_commit_callbacks(execute=True):
        _changed(order, Order.Status.CANCELLED)

    assert not _open("courier_not_attended", order.ref)
    assert not _open("danfe_print_failed", order.ref)
    assert _open("fiscal_emit_failed", order.ref), "nota com problema é da contabilidade, não some com o pedido"


def test_nota_autorizada_fecha_emissao_falha_e_saida_sem_nota(django_capture_on_commit_callbacks):
    from shopman.shop.signals import nfce_authorized

    order = _order("WEB-9", status=Order.Status.DISPATCHED)
    for tipo in ("fiscal_emit_failed", "fiscal_handoff_without_nfce", "fiscal_email_failed"):
        _alert(tipo, order_ref=order.ref)

    with django_capture_on_commit_callbacks(execute=True):
        nfce_authorized.send(sender=None, order=order)

    assert not _open("fiscal_emit_failed", order.ref)
    assert not _open("fiscal_handoff_without_nfce", order.ref)
    assert _open("fiscal_email_failed", order.ref), "o e-mail que não saiu continua não tendo saído"


def test_reprocessar_a_nota_fecha_o_alerta_e_o_pedido_sai_de_nao_autorizada(django_capture_on_commit_callbacks):
    from shopman.orderman.models import Directive

    from shopman.backstage.services.orders import requeue_fiscal_emission
    from shopman.shop.directives import FISCAL_EMIT_NFCE
    from shopman.shop.services import fiscal

    order = _order("WEB-10", status=Order.Status.COMPLETED)
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, payload={"order_ref": order.ref}, status="failed")
    create_operator_alert(
        type="fiscal_emit_failed",
        severity="critical",
        order_ref=order.ref,
        message="A NFC-e não foi autorizada.",
        dedupe_key=f"fiscal_emit_failed:{order.ref}",
    )
    with (
        mock.patch.object(fiscal, "emission_resolver", return_value=True),
        mock.patch.object(fiscal, "build_emission_payload", return_value={"order_ref": order.ref}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        requeue_fiscal_emission(order, actor="gestor")

    assert not _open("fiscal_emit_failed", order.ref)
    assert fiscal.fiscal_state(order) == fiscal.FISCAL_STATE_QUEUED


def test_maquininha_de_volta_fecha_o_aviso_de_maquininha_fora(django_capture_on_commit_callbacks):
    from shopman.shop.services import operator_orders

    order = _order("WEB-11", status=Order.Status.DELIVERED)
    _alert("card_machine_overdue", order_ref=order.ref, audience="orders")

    with django_capture_on_commit_callbacks(execute=True):
        operator_orders._stamp_equipment_back(order, actor="gestor")

    assert not _open("card_machine_overdue", order.ref)


def test_corrida_viva_fecha_os_avisos_de_corrida(django_capture_on_commit_callbacks):
    from shopman.shop.handlers.alert_resolution import COURIER_TYPES, resolve_on_commit

    order = _order("WEB-12", status=Order.Status.READY)
    for tipo in COURIER_TYPES:
        _alert(tipo, order_ref=order.ref)

    with django_capture_on_commit_callbacks(execute=True):
        resolve_on_commit(order.ref, COURIER_TYPES, actor="courier:A")

    assert not any(_open(tipo, order.ref) for tipo in COURIER_TYPES)


# ── O que o alerta diz ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tipo",
    [
        "payment_after_cancel",
        "payment_awaiting_confirmation",
        "preorder_activation_blocked_unpaid",
        "rejected_unavailable",
        "rejected_oos",
    ],
)
def test_os_alertas_do_ciclo_falam_portugues(tipo):
    from shopman.shop.lifecycle import _create_alert

    order = _order(f"WEB-{tipo}")
    _create_alert(order, tipo)

    mensagem = OperatorAlert.objects.get(type=tipo).message
    assert order.ref in mensagem
    assert tipo.replace("_", " ") not in mensagem
    assert "—" not in mensagem


def test_o_troco_sugerido_vem_em_reais_nao_em_centavos():
    from shopman.shop.services.operator_orders import ChangeOutRequired

    frase = str(ChangeOutRequired(1250))

    assert "R$ 12,50" in frase
    assert "centavos" not in frase
