"""O cliente é avisado do estorno e da devolução (P1-9, cenários de pedido).

Antes: o evento ``payment_refunded`` tinha texto e ninguém o emitia; o cliente que
pagou um pedido cancelado (ou pago depois de cancelado) só via o dinheiro voltar,
sem uma palavra da casa. E ``order_returned`` era emitido sem texto nenhum.

Regras que os testes pinam:

- o aviso de estorno sai quando o GATEWAY devolveu (Pix/cartão), uma vez por
  estorno (a chave de idempotência do estorno é a ocorrência do aviso);
- estorno sem gateway (maquininha, cobrança externa) NÃO avisa como se o sistema
  tivesse devolvido: quem devolve ali é gente, e isso é outra frente (P0-2);
- o texto diz quanto, por onde volta e quanto pode demorar, sem prometer prazo do
  banco.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from shopman.orderman.models import Directive, Order
from shopman.payman import PaymentService

from shopman.shop.models import Channel
from shopman.shop.notification_copy import CUSTOMER_COPY
from shopman.shop.services import payment as payment_service
from shopman.shop.services.notification import TOPIC, _build_context

pytestmark = pytest.mark.django_db

_MOCK_ADAPTERS = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    }
)


def _paid_order(ref: str, *, method: str = "pix", gateway: str = "mock", total_q: int = 5000) -> Order:
    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})
    intent_ref = f"INT-{ref}"
    PaymentService.create_intent(ref, total_q, method, gateway=gateway, ref=intent_ref)
    PaymentService.authorize(intent_ref, gateway_id=f"gw-{ref}")
    PaymentService.capture(intent_ref)
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=Order.Status.CANCELLED,
        total_q=total_q,
        data={
            "payment": {"method": method, "intent_ref": intent_ref},
            "customer": {"name": "Ana", "phone": "+5543999990001"},
        },
    )


def _refund_notices(order_ref: str):
    return Directive.objects.filter(
        topic=TOPIC, payload__order_ref=order_ref, payload__template="payment_refunded"
    ).order_by("id")


# ══════════════════════════════════════════════════════════════════════
# 1. Quem emite
# ══════════════════════════════════════════════════════════════════════


@_MOCK_ADAPTERS
def test_estorno_do_pix_pelo_gateway_avisa_o_cliente_uma_vez():
    order = _paid_order("ORD-RF-PIX")

    payment_service.refund(order)
    # Retry do mesmo estorno (worker reapresentado, cancel em dobro): nada novo.
    payment_service.refund(order)

    notices = list(_refund_notices(order.ref))
    assert len(notices) == 1
    payload = notices[0].payload
    assert payload["refund_amount_q"] == 5000
    assert "Pix" in payload["status_note"]


@_MOCK_ADAPTERS
def test_retry_da_mesma_devolucao_parcial_nao_avisa_duas_vezes():
    order = _paid_order("ORD-RF-RETRY")
    key = f"return:{order.ref}:0"

    payment_service.refund(order, amount_q=2000, idempotency_key=key)
    payment_service.refund(order, amount_q=2000, idempotency_key=key)

    assert _refund_notices(order.ref).count() == 1


@_MOCK_ADAPTERS
def test_duas_devolucoes_parciais_sao_dois_avisos_com_o_valor_de_cada_uma():
    order = _paid_order("ORD-RF-PARC")

    payment_service.refund(order, amount_q=1500, idempotency_key=f"return:{order.ref}:0")
    payment_service.refund(order, amount_q=1000, idempotency_key=f"return:{order.ref}:1")

    amounts = [d.payload["refund_amount_q"] for d in _refund_notices(order.ref)]
    assert amounts == [1500, 1000]


@_MOCK_ADAPTERS
def test_estorno_do_cartao_diz_que_volta_na_fatura():
    order = _paid_order("ORD-RF-CARD", method="card")

    payment_service.refund(order)

    notice = _refund_notices(order.ref).get()
    assert "cartão" in notice.payload["status_note"]
    assert "fatura" in notice.payload["status_note"]


@_MOCK_ADAPTERS
def test_estorno_sem_gateway_nao_avisa_como_se_o_sistema_tivesse_devolvido():
    # Maquininha / cobrança externa: quem devolve é gente. O livro só registra no
    # "Estornei na maquininha" (P0-2), e nenhum aviso sai antes disso.
    order = _paid_order("ORD-RF-EXT", method="external", gateway="")

    payment_service.refund(order)

    assert PaymentService.refunded_total(f"INT-{order.ref}") == 0
    assert not _refund_notices(order.ref).exists()


@_MOCK_ADAPTERS
def test_estorno_recusado_pelo_gateway_nao_avisa():
    order = _paid_order("ORD-RF-RECUSA")
    from shopman.shop.adapters.payment_types import PaymentResult

    with patch(
        "shopman.shop.adapters.payment_mock.refund",
        return_value=PaymentResult(success=False, error_code="refused", message="recusado"),
    ):
        payment_service.refund(order)

    assert not _refund_notices(order.ref).exists()


# ══════════════════════════════════════════════════════════════════════
# 2. O texto
# ══════════════════════════════════════════════════════════════════════


def _context_order(**data):
    order = MagicMock()
    order.ref = "ORD-1"
    order.total_q = 5000
    order.status = "cancelled"
    order.channel_ref = "web"
    order.data = {"customer": {"name": "Ana", "phone": "+5543999990001"}, **data}
    order.snapshot = {"items": []}
    return order


def test_texto_do_estorno_diz_quanto_e_por_onde_volta():
    from shopman.shop.adapters._notification_templates import derive_context

    ctx = _build_context(
        _context_order(),
        {"order_ref": "ORD-1", "refund_amount_q": 2000, "status_note": "Volta por Pix"},
        "payment_refunded",
    )
    ctx = derive_context(ctx)
    body = CUSTOMER_COPY["payment_refunded"]["body"].format_map(ctx)

    assert "R$ 20,00" in body
    assert "Volta por Pix" in body
    assert "{" not in body


def test_texto_do_estorno_sem_valor_no_payload_usa_o_total():
    ctx = _build_context(_context_order(), {"order_ref": "ORD-1"}, "payment_refunded")
    assert ctx["refund_amount_display"] == "R$ 50,00"
    # A frase nunca fica vazia (cabe no template do WhatsApp).
    assert ctx["status_note"]


@pytest.mark.parametrize("event", ["payment_refunded", "order_returned"])
def test_textos_de_estorno_e_devolucao_seguem_a_voz_da_casa(event):
    copy = CUSTOMER_COPY[event]
    text = copy["subject"] + copy["body"]
    assert "—" not in text and "–" not in text
    assert copy["body"].startswith("Oi{customer_name_greeting}")
    # O template da Meta não pode terminar em variável.
    assert not copy["body"].rstrip().endswith("}") or event == "order_returned"


def test_texto_da_devolucao_diz_o_que_foi_devolvido_e_o_que_acontece_com_o_dinheiro():
    body = CUSTOMER_COPY["order_returned"]["body"]
    assert "{order_ref_short}" in body
    assert "{status_note}" in body
    assert "todos os itens" in body


# ══════════════════════════════════════════════════════════════════════
# 3. A frase do dinheiro na devolução
# ══════════════════════════════════════════════════════════════════════


@_MOCK_ADAPTERS
def test_devolucao_paga_pelo_gateway_promete_aviso_do_estorno():
    order = _paid_order("ORD-RT-PIX")
    ctx = _build_context(order, {"order_ref": order.ref}, "order_returned")
    assert "mesma forma de pagamento" in ctx["status_note"]
    assert "avisamos" in ctx["status_note"]


@_MOCK_ADAPTERS
def test_devolucao_paga_no_balcao_diz_que_a_equipe_devolve():
    order = _paid_order("ORD-RT-EXT", method="external", gateway="")
    ctx = _build_context(order, {"order_ref": order.ref}, "order_returned")
    assert "equipe" in ctx["status_note"]
    assert "avisamos" not in ctx["status_note"]


def test_devolucao_do_ifood_diz_que_o_ifood_devolve():
    from shopman.shop.services.ifood_ingest import IFOOD_CHANNEL_REF

    order = _context_order()
    order.channel_ref = IFOOD_CHANNEL_REF
    ctx = _build_context(order, {"order_ref": "ORD-1"}, "order_returned")
    assert "iFood" in ctx["status_note"]


def test_devolucao_sem_cobranca_diz_que_nada_foi_cobrado():
    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})
    order = Order.objects.create(ref="ORD-RT-NADA", channel_ref="web", status="returned", total_q=5000, data={})
    ctx = _build_context(order, {"order_ref": order.ref}, "order_returned")
    assert "Nada foi cobrado" in ctx["status_note"]

# A ordem das mensagens na devolução (aviso antes do estorno) está em
# test_lifecycle.TestOnReturned (sem banco: o pedido é um mock).
