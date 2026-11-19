"""O detalhe tem o gesto (WP-G05, EXCELENCIA-GESTOR P1-13 a P1-16, P1-19, P2-20, P2-22, P2-25, P2-26).

O detalhe do pedido publica "O que falta neste pedido": cada pendência com o
fato, o motivo e a ação JÁ EXISTENTE que a resolve. Esta suíte prende:

- a nota recusada traz a resposta do emissor e o "Reprocessar NFC-e" ao lado;
- a DANFE chega ao detalhe com os mesmos campos do cartão, e a que não saiu é pendência;
- a cobrança vencida é um fato só, com o cancelar e o contato ao lado;
- espera saudável (Pix no prazo, o dia da encomenda, o lote) não usa tom de erro;
- o dinheiro do cancelado em três estados (estorno pedido, estornado, estorno que
  não saiu), lido do mesmo ``cancelled_money`` da loja, com a frase que o cliente lê;
- os quatro avisos do sino que pediam gesto no detalhe viram linha da lista.

Os estados fiscais ficam por teste de projeção: a pilha local não emite nota.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.payman import PaymentService

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections import order_pending
from shopman.backstage.projections.order_queue import build_operator_order
from shopman.shop.directives import FISCAL_EMIT_NFCE
from shopman.shop.models import Shop
from shopman.shop.services import payment as payment_service

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

ACCESS_KEY = "41260800000000000000650010000001521151375188"


@pytest.fixture(autouse=True)
def _shop():
    Shop.objects.create(name="Padaria do detalhe")


@pytest.fixture
def gerente(django_user_model):
    user = django_user_model.objects.create_user(username="gerente-detalhe", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    return user


def _order(ref: str, status: str = "accepted", *, payment: dict | None = None, total_q: int = 2200, **data) -> Order:
    body = {
        "customer": {"name": f"Cliente {ref}"},
        "fulfillment_type": "pickup",
        "payment": payment or {"method": "cash"},
        "availability_decision": {"approved": True, "decisions": []},
        **data,
    }
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=status, total_q=total_q, data=body,
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=1, unit_price_q=total_q, line_total_q=total_q,
    )
    return order


def _pending(detail) -> dict:
    return {item.key: item for item in detail.pending}


def _alert(order: Order, alert_type: str) -> OperatorAlert:
    return OperatorAlert.objects.create(
        type=alert_type, severity="critical", message=f"aviso de teste do pedido {order.ref}", order_ref=order.ref,
    )


def _pix_intent(order: Order, *, created_minutes_ago: int, window: int = 10) -> None:
    from shopman.payman.models import PaymentIntent

    created = timezone.now() - timedelta(minutes=created_minutes_ago)
    intent = PaymentIntent.objects.create(
        ref=order.data["payment"]["intent_ref"], order_ref=order.ref, method="pix", amount_q=order.total_q,
        status="pending", expires_at=created + timedelta(minutes=window),
    )
    PaymentIntent.objects.filter(pk=intent.pk).update(created_at=created)


def _paid_pix(ref: str, status: str = "cancelled") -> Order:
    order = _order(ref, status, payment={"method": "pix", "intent_ref": f"INT-{ref}"})
    PaymentService.create_intent(order.ref, order.total_q, "pix", gateway="mock", ref=f"INT-{ref}")
    PaymentService.authorize(f"INT-{ref}")
    PaymentService.capture(f"INT-{ref}")
    return order


# ── P1-13: a nota recusada ───────────────────────────────────────────────────


def test_nota_recusada_e_pendencia_com_a_resposta_do_emissor_e_o_reprocessar(gerente):
    order = _order("G05-NFCE", "ready")
    Directive.objects.create(
        topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref},
        last_error="NFC-e emission failed: Rejeição 778: NCM inexistente.",
    )

    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None):
        detail = build_operator_order(order, user=gerente)

    nfce = _pending(detail)["nfce"]
    assert (nfce.tone, nfce.label) == ("error", "NFC-e não autorizada")
    assert nfce.reason == (
        "Resposta do emissor: Rejeição 778: NCM inexistente. Se reprocessar não resolver, chame o contador."
    )
    (action,) = nfce.actions
    assert (action.ref, action.label, action.enabled) == ("requeue-fiscal", "Reprocessar NFC-e", True)
    # A ação da pendência é a MESMA do detalhe, não uma segunda porta.
    assert any(item.ref == "requeue-fiscal" for item in detail.actions)
    # Quem precisa agir vem primeiro.
    assert detail.pending[0].key == "nfce"


def test_nota_recusada_sem_resposta_do_emissor_nao_inventa_motivo():
    order = _order("G05-NFCE-MUDO", "ready")
    Directive.objects.create(
        topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref}, last_error="Order not found",
    )

    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None):
        detail = build_operator_order(order)

    nfce = _pending(detail)["nfce"]
    assert nfce.reason == "Se reprocessar não resolver, chame o contador."
    # Sem pessoa identificada a ação aparece desligada, com o motivo: nunca some.
    (action,) = nfce.actions
    assert action.enabled is False
    assert action.reason == "Identifique uma pessoa com permissão para gerenciar pedidos."


def test_nota_autorizada_nao_e_pendencia():
    order = _order("G05-NFCE-OK", "ready", nfce_access_key=ACCESS_KEY)

    assert "nfce" not in _pending(build_operator_order(order))


# ── P1-14: a DANFE no detalhe ────────────────────────────────────────────────


def test_danfe_da_retirada_chega_ao_detalhe_sem_virar_pendencia():
    order = _order("G05-DANFE-RET", "ready", nfce_access_key=ACCESS_KEY)

    detail = build_operator_order(order)

    assert (detail.danfe_printable, detail.danfe_printed, detail.danfe_state) == (True, False, "available")
    assert "danfe" not in _pending(detail)


def test_danfe_da_entrega_que_nao_saiu_e_pendencia_com_o_imprimir():
    order = _order("G05-DANFE-ENT", "dispatched", nfce_access_key=ACCESS_KEY, fulfillment_type="delivery")
    Order.objects.filter(pk=order.pk).update(dispatched_at=timezone.now() - timedelta(minutes=40))
    order.refresh_from_db()

    detail = build_operator_order(order)

    assert (detail.danfe_printable, detail.danfe_state) == (True, "not_printed")
    danfe = _pending(detail)["danfe"]
    assert (danfe.tone, danfe.label) == ("warning", "DANFE não impressa")
    assert danfe.reason == "A DANFE deste pedido ainda não saiu em nenhuma impressora."
    (action,) = danfe.actions
    assert (action.ref, action.label, action.enabled) == ("print-danfe", "Imprimir DANFE", True)


def test_danfe_ja_impressa_oferece_reimprimir_e_o_motivo_do_servidor():
    order = _order(
        "G05-DANFE-REIMP", "dispatched", nfce_access_key=ACCESS_KEY, fulfillment_type="delivery",
        danfe_printed_at="2026-11-18T10:00:00-03:00",
    )
    card = type("Danfe", (), {"printable": True, "printed": True, "state": "not_printed", "problem": "A impressora de Balcão recusou a DANFE. Confira o papel e imprima de novo."})()

    with patch("shopman.backstage.services.order_danfe.card_state", return_value=card):
        danfe = _pending(build_operator_order(order))["danfe"]

    assert danfe.reason == "A impressora de Balcão recusou a DANFE. Confira o papel e imprima de novo."
    assert danfe.actions[0].label == "Reimprimir DANFE"


def test_pedido_encerrado_nao_cobra_papel_que_nao_saiu():
    order = _order("G05-DANFE-FIM", "completed", nfce_access_key=ACCESS_KEY, fulfillment_type="delivery")

    detail = build_operator_order(order)

    assert detail.danfe_printable is True
    assert "danfe" not in _pending(detail)


# ── P1-16 e P2-26: o pagamento e as esperas ──────────────────────────────────


def test_cobranca_vencida_e_um_fato_so_com_o_cancelar_e_o_contato_ao_lado(gerente):
    order = _order(
        "G05-PIX-VENCIDO", "accepted", payment={"method": "pix", "intent_ref": "INT-G05-PIX-VENCIDO"},
        customer={"name": "Ana", "phone": "+5543999990000"},
    )
    _pix_intent(order, created_minutes_ago=30)

    detail = build_operator_order(Order.objects.get(pk=order.pk), user=gerente)

    payment_lines = [item for item in detail.pending if item.key == "payment"]
    assert len(payment_lines) == 1
    line = payment_lines[0]
    assert (line.tone, line.label) == ("error", "Pix expirado")
    assert line.reason.startswith("Gerado às ")
    assert "expirou às" in line.reason
    assert [action.ref for action in line.actions] == ["cancel", "contact-customer"]
    cancel, contact = line.actions
    assert cancel.enabled is True
    assert cancel.label in {"Cancelar pedido", "Cancelar pedido (pede gerente)"}
    assert contact.label == "Chamar no WhatsApp"
    assert contact.href == detail.customer_whatsapp_url != ""
    assert detail.payment_lapsed is True


def test_pix_dentro_do_prazo_e_espera_saudavel_sem_cor_de_erro():
    order = _order("G05-PIX-PRAZO", "new", payment={"method": "pix", "intent_ref": "INT-G05-PIX-PRAZO"})
    _pix_intent(order, created_minutes_ago=2)

    line = _pending(build_operator_order(Order.objects.get(pk=order.pk)))["payment"]

    assert (line.tone, line.label) == ("info", "Aguardando Pix")
    assert line.reason.endswith("sem pagamento até lá, cancela sozinho.")
    assert line.actions == ()


def test_o_dia_da_encomenda_e_espera_saudavel_e_diz_o_dia():
    tomorrow = timezone.localdate() + timedelta(days=1)
    order = _order("G05-ENCOMENDA", "accepted", delivery_date=tomorrow.isoformat(), is_preorder=True)

    detail = build_operator_order(order)

    line = _pending(detail)["advance"]
    assert (line.tone, line.label) == ("info", "Aguardando o dia da encomenda")
    assert line.reason == f"Combinado: {detail.schedule_label}. O preparo abre nesse dia."
    assert "Amanhã" in line.reason
    assert all(item.tone != "error" for item in detail.pending)


def test_pedido_sem_nada_pendente_tem_a_lista_vazia():
    assert build_operator_order(_order("G05-LIMPO", "preparing")).pending == ()


def test_o_balcao_nao_recebe_as_pendencias_do_gestor():
    order = _order("G05-POS", "ready")
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})

    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None):
        assert build_operator_order(order, context="pos").pending == ()


# ── P2-20: o lote que o pedido espera ────────────────────────────────────────


def test_o_lote_que_o_pedido_espera_aparece_nas_palavras_do_cartao():
    from shopman.craftsman import craft
    from shopman.craftsman.models import Recipe

    recipe = Recipe.objects.create(ref="g05-kuro", name="Kuro Pan", output_sku="PAO", batch_size=Decimal("10"))
    wo = craft.plan(recipe, 10, date=date.today())
    order = _order("G05-LOTE", "accepted", awaiting_wo_refs=[wo.ref])

    line = _pending(build_operator_order(order))["production"]

    assert (line.tone, line.label) == ("info", "Esperando o lote")
    assert line.reason == "Produção de Kuro Pan: não começou."


# ── P1-15 e P2-25: o dinheiro do cancelado, em três estados ──────────────────


def test_estorno_pedido_diz_o_estado_e_a_frase_que_o_cliente_le():
    order = _paid_pix("G05-ESTORNO-PEDIDO")

    detail = build_operator_order(order)

    money = detail.cancelled_money
    assert (money.state, money.label, money.settled) == ("refund_requested", "Estorno pedido", False)
    assert money.amount_display == "R$ 22,00"
    assert money.customer_line == "Estamos devolvendo os R$ 22,00 do seu Pix para a mesma conta."
    assert detail.payment_status_label == "Estorno pedido"
    refund = _pending(detail)["refund"]
    assert (refund.tone, refund.label) == ("info", "Estorno pedido")
    assert refund.reason == (
        "A devolução de R$ 22,00 foi pedida e ainda não foi confirmada. "
        "O cliente lê na loja: “Estamos devolvendo os R$ 22,00 do seu Pix para a mesma conta.”"
    )
    assert refund.actions == ()


def test_estornado_usa_a_mesma_palavra_do_historico_e_sai_da_lista():
    order = _paid_pix("G05-ESTORNADO")
    PaymentService.refund("INT-G05-ESTORNADO", reason="order_cancelled")
    order.emit_event("payment.refunded", actor="payment.refund", payload={"method": "pix", "amount_q": 2200})

    detail = build_operator_order(order)

    money = detail.cancelled_money
    assert (money.state, money.label, money.settled) == ("refunded", "Estornado", True)
    assert money.customer_line == "Devolvemos os R$ 22,00 do seu Pix para a mesma conta."
    assert detail.payment_status_label == "Estornado"
    assert "refund" not in _pending(detail)
    labels = {event.event_type: event.label for event in detail.timeline}
    assert labels["payment.refunded"] == "Pagamento estornado"


def test_estorno_que_nao_saiu_e_o_terceiro_estado_e_pede_alguem():
    order = _paid_pix("G05-ESTORNO-FALHOU")
    payment_service.alert_refund_failed(order, "INT-G05-ESTORNO-FALHOU", 2200, "gateway fora do ar")

    detail = build_operator_order(order)

    money = detail.cancelled_money
    assert (money.state, money.label, money.settled) == ("refund_failed", "Estorno não saiu", False)
    # A loja ainda diz "estamos devolvendo": o Gestor não repete o que não é verdade.
    assert money.customer_line == ""
    assert detail.payment_status_label == "Estorno não saiu"
    refund = _pending(detail)["refund"]
    assert (refund.tone, refund.label) == ("error", "Estorno não saiu")
    assert refund.reason.startswith("A devolução de R$ 22,00 não chegou ao cliente.")
    assert detail.pending[0].key == "refund"


def test_o_estorno_que_fechou_vence_o_aviso_de_falha_ainda_aberto():
    order = _paid_pix("G05-ESTORNO-FECHOU")
    payment_service.alert_refund_failed(order, "INT-G05-ESTORNO-FECHOU", 2200, "gateway fora do ar")
    PaymentService.refund("INT-G05-ESTORNO-FECHOU", reason="order_cancelled")

    detail = build_operator_order(order)

    assert detail.cancelled_money.state == "refunded"
    assert "refund" not in _pending(detail)


def test_o_dinheiro_do_cancelado_e_o_mesmo_que_a_loja_le():
    """Uma fonte só: o que ``payment.cancelled_money`` disser, o Gestor diz."""
    order = _paid_pix("G05-MESMA-FONTE")
    source = payment_service.CancelledMoney("refunded", amount_q=1870, method="card")

    with patch.object(payment_service, "cancelled_money", return_value=source) as read:
        money = order_pending.cancelled_money(order, alerts=frozenset())

    read.assert_called_once_with(order)
    assert money.customer_line == (
        "Estornamos os R$ 18,70 no seu cartão. O valor volta na fatura no prazo do seu banco."
    )


def test_cancelado_sem_cobranca_nao_troca_o_rotulo_do_pagamento():
    order = _order("G05-NADA-COBRADO", "cancelled", payment={"method": "pix", "intent_ref": "INT-G05-NADA"})
    _pix_intent(order, created_minutes_ago=30)
    PaymentService.cancel("INT-G05-NADA", reason="payment_timeout")

    detail = build_operator_order(Order.objects.get(pk=order.pk))

    money = detail.cancelled_money
    assert (money.state, money.label, money.settled) == ("nothing_charged", "Nada foi cobrado", True)
    assert money.customer_line == "Nada foi cobrado."
    assert detail.payment_status_label not in {"Estornado", "Estorno pedido", "Estorno não saiu"}
    assert "refund" not in _pending(detail)


def test_pedido_vivo_nao_tem_dinheiro_de_cancelado():
    assert build_operator_order(_paid_pix("G05-VIVO", "accepted")).cancelled_money is None


# ── P1-19: os avisos do sino que pediam gesto no detalhe ─────────────────────


def test_nota_que_nao_cancelou_diz_quem_resolve_e_leva_a_chave():
    order = _order("G05-NOTA-CANC", "cancelled", nfce_access_key=ACCESS_KEY)
    _alert(order, "fiscal_cancel_failed")

    line = _pending(build_operator_order(order))["nfce_cancel"]

    assert (line.tone, line.label) == ("error", "NFC-e não foi cancelada")
    assert "Quem resolve é o contador" in line.reason
    assert line.reason.endswith(f"Chave de acesso: {ACCESS_KEY}.")
    assert line.actions == ()


def test_etapa_travada_diz_para_nao_refazer_a_mao():
    order = _order("G05-ETAPA", "preparing")
    _alert(order, "lifecycle_phase_stuck")

    line = _pending(build_operator_order(order))["phase"]

    assert (line.tone, line.label) == ("error", "Etapa automática travada")
    assert line.reason.endswith("Até ele conferir, não refaça a etapa à mão.")
    assert line.actions == ()


def test_encomenda_sem_pagamento_na_hora_da_cozinha_traz_o_cobrar_e_o_cancelar(gerente):
    order = _order(
        "G05-SEM-PAGAR", "accepted", payment={"method": "pix", "intent_ref": "INT-G05-SEM-PAGAR"},
        customer={"name": "Ana", "phone": "+5543999990000"},
    )
    _pix_intent(order, created_minutes_ago=30)
    _alert(order, "preorder_activation_blocked_unpaid")

    detail = build_operator_order(Order.objects.get(pk=order.pk), user=gerente)

    payment_lines = [item for item in detail.pending if item.key == "payment"]
    assert len(payment_lines) == 1
    line = payment_lines[0]
    assert (line.tone, line.label) == ("error", "Encomenda sem pagamento não foi para a Cozinha")
    assert line.reason.startswith("Chegou a hora do preparo e o pagamento não entrou.")
    assert line.reason.endswith("Cobre o cliente ou cancele a encomenda.")
    assert [action.ref for action in line.actions] == ["cancel", "contact-customer"]


def test_aviso_resolvido_nao_e_mais_pendencia():
    order = _order("G05-RESOLVIDO", "preparing")
    alert = _alert(order, "lifecycle_phase_stuck")
    OperatorAlert.objects.filter(pk=alert.pk).update(resolved_at=timezone.now())

    assert "phase" not in _pending(build_operator_order(order))


# ── P2-22: frases que só nomeiam o que existe na tela ────────────────────────


def test_o_link_que_pode_nao_ter_chegado_e_pendencia_com_o_reenviar(gerente):
    order = _order("G05-LINK", "accepted", payment={"method": "link", "intent_ref": "INT-G05-LINK"})
    PaymentService.create_intent(order.ref, order.total_q, "link", gateway="mock", ref="INT-G05-LINK")
    problem = "O envio do link falhou. Reenvie o link."

    with (
        patch("shopman.backstage.projections.order_queue._payment_link_delivery", return_value=(problem, True)),
        patch("shopman.shop.services.notification.payment_link_resend_refusal", return_value=None),
    ):
        detail = build_operator_order(order, user=gerente)

    line = _pending(detail)["payment"]
    assert line.tone == "warning"
    assert line.reason.startswith(problem)
    assert [(action.ref, action.label, action.enabled) for action in line.actions] == [
        ("resend-payment-link", "Reenviar link de pagamento", True),
    ]
    assert detail.payment_link_notice == problem


def test_nenhuma_frase_do_link_nomeia_controle_ou_pessoa_que_nao_existe():
    import inspect

    from shopman.backstage.projections import order_queue

    source = inspect.getsource(order_queue._payment_link_delivery)
    assert "copie o link" not in source
    assert "com o responsável" not in source


# ── A régua da copy ──────────────────────────────────────────────────────────


def test_nenhuma_frase_de_pendencia_usa_travessao_ou_termina_solta():
    import inspect

    source = inspect.getsource(order_pending)
    code = source.split('"""', 2)[2]
    assert "—" not in code
    assert "–" not in code
