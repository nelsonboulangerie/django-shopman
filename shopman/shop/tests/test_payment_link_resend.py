"""Reenvio manual do link de pagamento (Frente 5 do WP-PAGAMENTO).

O envio automático nasce deduplicado por (pedido, template) — e o mesmo dedupe
que protege contra o retry do PDV impedia o operador de mandar de novo quando o
cliente diz "não chegou". O reenvio é UMA Directive nova por gesto, com sufixo
de tentativa na chave de dedupe: retry, backoff e escalada de graça, e o dedupe
do envio original intacto.

Quatro coisas, cada uma com o seu teste:

1. o reenvio cria uma Directive nova e não mexe na original;
2. a cadência: envio em andamento e "cedo demais" recusam, e o clique duplo do
   mesmo segundo devolve a MESMA Directive;
3. cada guarda do pedido (forma, URL, cancelado, pago, vencido) recusa com o
   código certo — e a projection do gestor concorda com o guarda;
4. reenvio manda a MESMA URL: não existe regeneração.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.services import notification as notification_svc
from shopman.shop.services.notification import NotificationResendRefused, resend_payment_link

CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_resend"


def _order(ref: str = "PDV-R1", *, status: str = "accepted", **payment_extra) -> Order:
    payment = {"method": "link", "amount_q": 3800, "checkout_url": CHECKOUT_URL}
    payment.update(payment_extra)
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        session_key=f"s-{ref}",
        status=status,
        total_q=3800,
        data={"customer": {"name": "Joyce", "phone": "+5543999990001"}, "fulfillment_type": "pickup", "payment": payment},
    )


def _directives(order: Order):
    return Directive.objects.filter(
        topic=notification_svc.TOPIC, payload__template="payment_link_sent", payload__order_ref=order.ref
    ).order_by("pk")


def _age(directive: Directive, seconds: int) -> None:
    """Envelhece a Directive: ``created_at`` é auto_now_add, só o UPDATE mexe nele."""
    Directive.objects.filter(pk=directive.pk).update(created_at=timezone.now() - timedelta(seconds=seconds))


def _settled(directive: Directive, status: str = "done") -> None:
    directive.status = status
    directive.save(update_fields=["status", "updated_at"])


@pytest.fixture
def sent(db):
    """Pedido de link com o envio original já entregue há mais de um minuto."""
    order = _order()
    notification_svc.send(order, "payment_link_sent")
    (original,) = _directives(order)
    _settled(original)
    _age(original, 120)
    return order, original


# ══════════════════════════════════════════════════════════════════════
# 1. Uma Directive nova, a original intacta
# ══════════════════════════════════════════════════════════════════════


def test_o_reenvio_cria_uma_directive_nova_e_deixa_a_original_em_paz(sent):
    order, original = sent

    created = resend_payment_link(order)

    assert created.pk != original.pk
    assert created.status == "queued"
    assert created.payload["template"] == "payment_link_sent"
    assert created.payload["order_ref"] == order.ref
    assert created.payload["requires_active_notification"] is True, "falha de entrega tem que gritar"
    assert created.dedupe_key == f"{original.dedupe_key}:resend:2"
    original.refresh_from_db()
    assert original.status == "done"
    assert _directives(order).count() == 2


def test_o_dedupe_do_envio_original_segue_intacto_depois_do_reenvio(sent):
    """Um retry do PDV depois do reenvio continua não mandando o link de novo."""
    order, _ = sent
    resend_payment_link(order)

    notification_svc.send(order, "payment_link_sent")

    assert _directives(order).count() == 2


def test_cada_reenvio_ganha_o_proprio_sufixo(sent):
    order, original = sent
    first = resend_payment_link(order)
    _settled(first)
    _age(first, 120)

    second = resend_payment_link(order)

    assert first.dedupe_key.endswith(":resend:2")
    assert second.dedupe_key.endswith(":resend:3")


def test_reenvio_sem_envio_original_e_a_primeira_tentativa(db):
    """Pedido de link cujo envio automático nunca enfileirou (fila fora do ar na venda)."""
    order = _order("PDV-R0")
    created = resend_payment_link(order)
    assert created.dedupe_key.endswith(":resend:1")


# ══════════════════════════════════════════════════════════════════════
# 2. Cadência
# ══════════════════════════════════════════════════════════════════════


def test_envio_ainda_na_fila_recusa(db):
    order = _order("PDV-R2")
    notification_svc.send(order, "payment_link_sent")
    (original,) = _directives(order)
    _age(original, 120)  # velho, mas ainda `queued`

    with pytest.raises(NotificationResendRefused) as exc:
        resend_payment_link(order)

    assert exc.value.code == "payment_link_send_pending"
    assert _directives(order).count() == 1


def test_reenvio_logo_depois_do_envio_recusa_cedo_demais(db):
    order = _order("PDV-R3")
    notification_svc.send(order, "payment_link_sent")
    (original,) = _directives(order)
    _settled(original)  # entregue há segundos

    with pytest.raises(NotificationResendRefused) as exc:
        resend_payment_link(order)

    assert exc.value.code == "payment_link_resend_too_soon"
    assert exc.value.status == 409
    assert "Aguarde" in exc.value.message


def test_envio_que_falhou_pode_ser_reenviado_na_hora(db):
    """Falha terminal não é "cedo demais": é exatamente o caso do reenvio."""
    order = _order("PDV-R4")
    notification_svc.send(order, "payment_link_sent")
    (original,) = _directives(order)
    _settled(original, "failed")
    _age(original, 120)

    created = resend_payment_link(order)

    assert created.status == "queued"


def test_clique_duplo_no_mesmo_segundo_devolve_a_mesma_directive(sent):
    """O UNIQUE parcial do Core recusa o segundo INSERT; devolvemos a do primeiro.

    A corrida de verdade: os dois cliques passam pelos guardas e computam o
    mesmo ``n`` antes de qualquer INSERT. Aqui o "outro clique" commita dentro
    do nosso ``create_deduped`` (que então devolve ``None``, como faz quando a
    constraint viola), e o service tem que achar a Directive dele pela chave.
    """
    from shopman.shop import directives as directives_module

    order, _ = sent
    real_create = directives_module.create_deduped
    other_click: list[Directive] = []

    def racing(**kwargs):
        other_click.append(real_create(**kwargs))  # o outro clique chegou primeiro
        return None  # o nosso INSERT violou o UNIQUE parcial

    with patch("shopman.shop.directives.create_deduped", side_effect=racing):
        joined = resend_payment_link(order)

    assert joined.pk == other_click[0].pk
    assert _directives(order).count() == 2, "dois cliques, UMA Directive nova"


# ══════════════════════════════════════════════════════════════════════
# 3. Guardas do pedido — e a projection concorda
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGuardasDoPedido:
    def _refuses(self, order: Order, code: str) -> None:
        from shopman.backstage.projections.order_queue import build_operator_order

        with pytest.raises(NotificationResendRefused) as exc:
            resend_payment_link(order)
        assert exc.value.code == code
        assert not _directives(order).exists()
        refusal = notification_svc.payment_link_resend_refusal(order)
        assert refusal is not None and refusal.code == code
        assert build_operator_order(order).can_resend_payment_link is False, "a tela não oferece o que o servidor nega"

    def test_outra_forma_de_pagamento(self):
        order = _order("PDV-G1", method="pix")
        self._refuses(order, "payment_link_unavailable")

    def test_link_sem_url_gravada(self):
        """Gateway falhou na venda: não há o que mandar."""
        order = _order("PDV-G2", checkout_url="")
        self._refuses(order, "payment_link_unavailable")

    def test_pedido_cancelado(self):
        order = _order("PDV-G3", status="cancelled")
        self._refuses(order, "payment_link_order_cancelled")

    def test_pedido_ja_pago(self):
        order = _order("PDV-G4")
        with patch("shopman.shop.services.payment.has_sufficient_captured_payment", return_value=True):
            self._refuses(order, "payment_link_already_paid")

    def test_link_vencido(self):
        expired = (timezone.now() - timedelta(minutes=1)).isoformat()
        order = _order("PDV-G5", expires_at=expired)
        self._refuses(order, "payment_link_expired")

    def test_prazo_ilegivel_nao_bloqueia(self):
        """O dado que falta (ou está torto) não fecha a porta do reenvio — o
        vencimento de verdade é a máquina de timeout, que pergunta ao gateway."""
        order = _order("PDV-G6", expires_at="amanhã de manhã")
        assert notification_svc.payment_link_resend_refusal(order) is None

    def test_pedido_de_link_valido_pode_e_a_projection_oferece(self):
        from shopman.backstage.projections.order_queue import build_operator_order

        future = (timezone.now() + timedelta(hours=3)).isoformat()
        order = _order("PDV-G7", expires_at=future)
        assert notification_svc.payment_link_resend_refusal(order) is None
        assert build_operator_order(order).can_resend_payment_link is True

    def test_pedido_de_outra_forma_nao_paga_a_leitura(self):
        """Só o pedido de link consulta Payman e Directive na projection."""
        from shopman.backstage.projections.order_queue import build_operator_order

        order = _order("PDV-G8", method="cash")
        with patch.object(notification_svc, "payment_link_resend_refusal") as guard:
            proj = build_operator_order(order)
        guard.assert_not_called()
        assert proj.can_resend_payment_link is False
        assert proj.payment_link_notice == ""


# ══════════════════════════════════════════════════════════════════════
# 4. A mesma URL, e a prova de envio
# ══════════════════════════════════════════════════════════════════════


def test_o_reenvio_entrega_a_mesma_url(sent):
    """Não existe regenerar: o handler lê `checkout_url` do pedido, que não mudou."""
    from shopman.shop.services.notification import _build_context

    order, _ = sent
    created = resend_payment_link(order)
    context = _build_context(order, created.payload, "payment_link_sent")
    assert context["checkout_url"] == CHECKOUT_URL


@pytest.mark.django_db
class TestProvaDeEnvio:
    def _notice(self, order):
        from shopman.backstage.projections.order_queue import payment_link_notice

        return payment_link_notice(order)

    def test_sem_directive_nenhuma_cala(self):
        assert self._notice(_order("PDV-N0")) == ""

    def test_na_fila_diz_enviando(self):
        order = _order("PDV-N1")
        notification_svc.send(order, "payment_link_sent")
        assert self._notice(order) == "Enviando o link ao cliente…"

    def test_entregue_diz_a_hora(self):
        order = _order("PDV-N2")
        notification_svc.send(order, "payment_link_sent")
        (directive,) = _directives(order)
        _settled(directive)
        directive.refresh_from_db()
        local = timezone.localtime(directive.updated_at)
        assert self._notice(order) == f"Link enviado às {local.hour}h{local.minute:02d}"

    def test_falhou_convida_ao_gesto(self):
        order = _order("PDV-N3")
        notification_svc.send(order, "payment_link_sent")
        (directive,) = _directives(order)
        _settled(directive, "failed")
        assert self._notice(order) == "O envio do link falhou. Reenvie ou copie o link."

    def test_a_ultima_directive_manda(self):
        """Depois do reenvio, a prova é do reenvio — não do envio original."""
        order = _order("PDV-N4")
        notification_svc.send(order, "payment_link_sent")
        (original,) = _directives(order)
        _settled(original, "failed")
        _age(original, 120)
        resend_payment_link(order)
        assert self._notice(order) == "Enviando o link ao cliente…"
