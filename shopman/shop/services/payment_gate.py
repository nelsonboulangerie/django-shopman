"""A régua única do dinheiro: este pedido pode receber trabalho e sair da casa?

Duas superfícies fazem a MESMA pergunta — o Gestor (``operator_orders.advance_block``)
e a expedição do KDS (``kds.expedition_action``) — e as duas perguntam aqui. Antes
havia duas réguas: a do Gestor só olhava ``ACCEPTED`` e não conhecia o ``link``; a da
expedição não existia — o painel por onde a mercadoria fisicamente sai chamava
``transition_status`` sem consultar pagamento nenhum.

A distinção que este módulo carrega, e que é a razão de ele existir:

**Não pago porque a casa combinou receber na porta ≠ não pago porque o link venceu.**

O pagamento na entrega (COD) é venda legítima: o dinheiro entra quando o entregador
chega, o troco sai da gaveta no despacho (``operator_orders.advance_order``) e a
liquidação acontece no retorno (``operator_orders.settle_delivery_cash``). Barrar o
despacho de um COD por "não capturado" quebraria a operação de dinheiro na porta —
ela nunca teria captura ANTES, por desenho.

Já o pix/cartão/link é cobrança digital ANTECIPADA: o dinheiro deveria ter entrado
antes do trabalho começar. Sem captura, a mercadoria não sai.

O critério é a NATUREZA do método, não o canal: ``payment.timing == "external"``
descreve o balcão recebendo na hora (dinheiro, maquininha), e o link existe
justamente para o pedido que NÃO está no balcão — o mesmo raciocínio do
``lifecycle._requires_payment_before_physical_work``.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

# Cobrança digital ANTECIPADA: passa por gateway e o dinheiro chega antes da
# mercadoria. ``link`` mora aqui porque é o pedido REMOTO anotado no balcão — o
# cliente não está na loja, paga pelo celular e vem buscar (ou recebe em casa).
UPFRONT_DIGITAL_PAYMENT_METHODS = frozenset({"pix", "card", "link"})

# Dinheiro que a casa recebe no mundo físico — no terminal (já recebido na venda)
# ou na porta (COD). Não passa por captura de intent antes da entrega.
ON_DELIVERY_PAYMENT_METHODS = frozenset({"cash", "mixed"})


def collects_on_delivery(order) -> bool:
    """A casa combinou receber o dinheiro NA PORTA?

    Marca canônica: ``order.data["payment"]["collection"] == "on_delivery"``,
    gravada pelo PDV (``pos_intent``) e — desde o gate de expedição — também pela
    loja online no checkout de dinheiro com entrega.

    O fallback por natureza cobre o pedido antigo (gravado antes de a loja
    carimbar ``collection``): dinheiro + entrega só pode ser recebido na porta.
    Sem ele, um pedido em dinheiro da loja online não seria reconhecido como COD.
    """
    from shopman.shop.services.order_helpers import get_fulfillment_type

    payment = (order.data or {}).get("payment") or {}
    collection = str(payment.get("collection") or "").strip().lower()
    if collection == "on_delivery":
        return True
    if collection:
        # ``terminal`` (ou qualquer outra marca explícita) é decisão gravada:
        # não deduzir por cima dela.
        return False

    method = str(payment.get("method") or "").strip().lower()
    return method in ON_DELIVERY_PAYMENT_METHODS and get_fulfillment_type(order) == "delivery"


def requires_captured_payment(order) -> bool:
    """True quando este pedido é cobrança digital antecipada (pix/cartão/link).

    COD sai daqui pela porta da frente: ``collects_on_delivery`` responde antes,
    e ``cash``/``mixed`` nem chegam ao conjunto digital.
    """
    if collects_on_delivery(order):
        return False
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").strip().lower()
    if method:
        return method in UPFRONT_DIGITAL_PAYMENT_METHODS

    # Sem método gravado, o intent é a prova: só dinheiro de gateway nasce com
    # ``intent_ref``/``status`` sem que ninguém tenha dito a forma. Pedido sem
    # informação de pagamento NENHUMA continua fora do gate — barrar por
    # ausência de dado travaria pedido importado e legado sem recuperar
    # centavo algum; quem cuida disso é o pill "Pagamento não informado".
    return bool(payment.get("intent_ref") or payment.get("status"))


def payment_is_captured(order) -> bool:
    """O Payman mostra dinheiro capturado cobrindo o total? Degrada para False."""
    from shopman.shop.services import payment as payment_service

    try:
        return payment_service.has_sufficient_captured_payment(order) is True
    except Exception:
        logger.warning(
            "payment_gate.capture_lookup_failed order=%s", getattr(order, "ref", "?"), exc_info=True
        )
        # Falhar fechado: pergunta que não responde não libera mercadoria.
        return False


# Transições em que a casa entrega TRABALHO ou MERCADORIA e não pode voltar atrás.
#
# - ``PREPARING``: a cozinha começa, o insumo é consumido, o estoque baixa.
# - ``DISPATCHED``: a sacola sai pela porta com o entregador.
# - ``COMPLETED`` vindo de qualquer lugar que não seja ``DELIVERED``: é o balcão
#   entregando na mão do cliente (``READY → COMPLETED``). Vindo de ``DELIVERED``
#   é só escrituração — a mercadoria já saiu, barrar ali não recupera nada.
#
# ``PREPARING → READY`` fica de fora de propósito: o trabalho já foi feito e nada
# sai da casa ao marcar "pronto". Barrar ali só deixaria um card encalhado na
# cozinha; quem segura a mercadoria é o degrau seguinte, que está nesta lista.
# ``DISPATCHED → DELIVERED`` idem: o entregador já saiu.


def transition_hands_over_goods(current_status: str, target_status: str) -> bool:
    """A transição entrega trabalho físico ou mercadoria ao cliente?"""
    target = str(target_status or "").strip().lower()
    current = str(current_status or "").strip().lower()
    if target in {Order.Status.PREPARING, Order.Status.DISPATCHED}:
        return True
    if target == Order.Status.COMPLETED:
        return current != Order.Status.DELIVERED
    return False


def payment_blocks_transition(order, *, current_status: str, target_status: str) -> bool:
    """A régua: este pedido está barrado por falta de dinheiro nesta transição?

    Devolve True só quando as três coisas valem ao mesmo tempo: a transição
    entrega trabalho ou mercadoria, a cobrança é digital antecipada (logo NÃO é
    dinheiro na porta) e o Payman não mostra captura suficiente.
    """
    if not transition_hands_over_goods(current_status, target_status):
        return False
    if not requires_captured_payment(order):
        return False
    return not payment_is_captured(order)


__all__ = [
    "ON_DELIVERY_PAYMENT_METHODS",
    "UPFRONT_DIGITAL_PAYMENT_METHODS",
    "collects_on_delivery",
    "payment_blocks_transition",
    "payment_is_captured",
    "requires_captured_payment",
    "transition_hands_over_goods",
]
