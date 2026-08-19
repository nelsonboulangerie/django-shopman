"""
Payment Service — The single public interface for all payment operations.

Usage:
    from shopman.payman import PaymentService, PaymentError

    intent = PaymentService.create_intent("ORD-001", 1500, "pix")
    PaymentService.authorize(intent.ref, gateway_id="efi_txid_123")
    tx = PaymentService.capture(intent.ref)
    PaymentService.refund(intent.ref, amount_q=500, reason="item danificado")

    # Sem gateway (dinheiro no balcão, cobrança externa): nasce capturado.
    intent = PaymentService.settle("ORD-002", 1500, "cash")

Lifecycle:
    create_intent → authorize → capture → (refund)
                  → cancel
                  → fail
    settle (cash/external) = create_intent + capture, atômico

7 verbos: create_intent, settle, authorize, capture, refund, cancel, fail.
Reconciliação: reconcile_gateway_status (snapshot cumulativo do gateway).
Consultas: get, get_by_order, get_by_gateway_id, get_active_intent
(cobrança de pé — pendente ou autorizada, nunca capturada).
Somas: captured_total, refunded_total, chargeback_total.

Domain Contracts:

    Capture:
        - Payman allows a SINGLE capture per intent.
        - ``amount_q < authorized`` means partial capture; the uncaptured
          balance is abandoned (no second capture is allowed).
        - Full capture: omit ``amount_q`` (defaults to ``intent.amount_q``).

    Refund:
        - ``REFUNDED`` status means "at least one refund exists".
        - ``refunded_total(ref)`` is the financial source of truth for how
          much has actually been returned to the customer.
        - Multiple partial refunds are allowed as long as
          ``captured_total - refunded_total - chargeback_total > 0``.

    Chargeback:
        - Devolução decidida por terceiro (disputa de cartão, MED do Pix).
          Entra pelo snapshot do gateway (``reconcile_gateway_status``), não
          por verbo próprio: a loja não decide o fato, só registra.
        - Não muda o ``status`` do intent — consome saldo devolvível e é
          contado por ``chargeback_total(ref)``.

    Mutation Surface:
        - ``PaymentService`` is the canonical mutation surface. All status
          transitions, transaction creation, and signal emission happen here.
        - ``intent.transition_status()`` is an internal helper used only by
          the model's own ``save()`` concurrency guard; external code must
          always go through ``PaymentService`` methods.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import IntegrityError, models, transaction
from django.db.models import Count, Min, Q, Sum
from django.utils import timezone
from shopman.payman.exceptions import PaymentError
from shopman.payman.models.intent import PaymentIntent
from shopman.payman.models.transaction import PaymentTransaction
from shopman.payman.signals import (
    payment_authorized,
    payment_cancelled,
    payment_captured,
    payment_failed,
    payment_refunded,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger("shopman.payman")


@dataclass(frozen=True)
class PaymentReconciliationResult:
    """Result of applying a cumulative gateway snapshot to a Payman intent."""

    intent_ref: str
    status: str
    captured_q: int
    refunded_q: int
    changed: bool
    actions: tuple[str, ...]
    drift: tuple[str, ...] = ()
    # Devolvido por decisão de terceiro (disputa de cartão, MED do Pix), não
    # pela loja. Fica separado de ``refunded_q`` porque a natureza muda o que
    # o gestor faz a seguir — contestar, não conferir.
    chargeback_q: int = 0


class PaymentService:
    """
    Interface pública para operações de pagamento.

    Todas as operações state-changing usam @transaction.atomic + select_for_update().
    Toda transição anuncia o signal correspondente DEPOIS do COMMIT (``_announce``).
    O core é AGNÓSTICO — não sabe nada sobre gateways (Efi, Stripe, etc.).
    """

    # ================================================================
    # Create
    # ================================================================

    @classmethod
    def create_intent(
        cls,
        order_ref: str,
        amount_q: int,
        method: str,
        *,
        currency: str = "BRL",
        gateway: str = "",
        gateway_id: str = "",
        gateway_data: dict | None = None,
        expires_at=None,
        ref: str | None = None,
        idempotency_key: str = "",
    ) -> PaymentIntent:
        """
        Cria intenção de pagamento.

        Args:
            order_ref: Referência do pedido (string, sem FK)
            amount_q: Valor em centavos
            method: Método de pagamento (pix, card, cash, external)
            currency: Código ISO 4217
            gateway: Nome do gateway (ex: "efi", "stripe")
            gateway_id: ID da transação no gateway
            gateway_data: Dados extras do gateway (JSON)
            expires_at: Datetime de expiração
            ref: Referência customizada (auto-gerada se None)
            idempotency_key: Chave estável para retry seguro da mesma criação

        Returns:
            PaymentIntent criado com status PENDING ou intent existente para a
            mesma chave idempotente.
        """
        if amount_q <= 0:
            raise PaymentError(
                code="invalid_amount",
                message="Valor deve ser positivo",
                context={"amount_q": amount_q},
            )

        idempotency_key = (idempotency_key or "").strip()
        if idempotency_key:
            existing = PaymentIntent.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                cls._require_idempotent_match(
                    existing,
                    order_ref=order_ref,
                    amount_q=amount_q,
                    method=method,
                    currency=currency,
                    gateway=gateway,
                )
                return existing

        try:
            intent = PaymentIntent.objects.create(
                ref=ref or cls._generate_ref(),
                order_ref=order_ref,
                method=method,
                amount_q=amount_q,
                currency=currency,
                gateway=gateway,
                gateway_id=gateway_id,
                gateway_data=gateway_data or {},
                expires_at=expires_at,
                idempotency_key=idempotency_key,
            )
        except IntegrityError:
            if not idempotency_key:
                raise
            existing = PaymentIntent.objects.filter(idempotency_key=idempotency_key).first()
            if not existing:
                raise
            cls._require_idempotent_match(
                existing,
                order_ref=order_ref,
                amount_q=amount_q,
                method=method,
                currency=currency,
                gateway=gateway,
            )
            return existing

        logger.info(
            "Intent created",
            extra={"ref": intent.ref, "order_ref": order_ref, "amount_q": amount_q, "method": method},
        )

        return intent

    # ================================================================
    # Settle (métodos sem gateway)
    # ================================================================

    @classmethod
    @transaction.atomic
    def settle(
        cls,
        order_ref: str,
        amount_q: int,
        method: str,
        *,
        currency: str = "BRL",
        gateway_data: dict | None = None,
        ref: str | None = None,
        idempotency_key: str = "",
        asserted_at_terminal: bool = False,
    ) -> PaymentIntent:
        """
        Cria e captura, na mesma transação, um pagamento que liquidou sem gateway.

        Dinheiro em espécie e cobrança externa (maquininha avulsa, marketplace)
        não passam por autorização remota nem por webhook: o valor está na mão
        no instante em que a venda fecha. Mesmo assim o Payman é o livro de
        pagamentos de TODOS os métodos: é isso que dá ao mix de meios de
        pagamento um dono só (receita por método sai daqui, não do JSON do
        pedido) e deixa a reconciliação financeira enxergar dinheiro em vez
        de ser cega para ele. O caixa físico (turno, gaveta, sangria) é
        pergunta de outro pacote (``cashman``); o único fato compartilhado é o
        tender em dinheiro, ligado pelo ``ref`` deste intent.

        Não é adapter nem Protocol: só existe uma forma de "capturar" dinheiro,
        e um seam plugável sem duas implementações reais é dívida. É um ramo
        do próprio service, com ``gateway=""`` e ``gateway_id=""``. O intent
        percorre a máquina de estados normal (pending → authorized →
        captured): autorização e captura são o mesmo gesto porque a nota já
        está na gaveta, mas os invariantes do modelo continuam os mesmos.

        Estorno de dinheiro é ``refund`` normal (``PaymentTransaction(REFUND)``).

        Args:
            order_ref: Referência do pedido (string, sem FK)
            amount_q: Valor efetivamente recebido para este pedido, em centavos
                (o valor do tender depois de descontado o troco; nunca o que
                o cliente entregou)
            method: ``cash`` ou ``external`` (``PaymentIntent.METHODS_WITHOUT_GATEWAY``)
            currency: Código ISO 4217
            gateway_data: Dados livres de auditoria (ex.: terminal, operador)
            ref: Referência customizada (auto-gerada se None)
            idempotency_key: Chave estável para retry seguro; uma repetição
                devolve o intent já capturado em vez de cobrar duas vezes
            asserted_at_terminal: O operador ATESTOU no terminal que um método
                COM gateway (pix, cartão) foi recebido fora dele — QR estático,
                maquininha avulsa numa venda mista. É a única porta para pix/card
                passarem por aqui, e fica gravada em ``gateway_data`` para a
                reconciliação distinguir "capturado pelo gateway" de "atestado
                pelo balcão". Sem a flag, pix/card continuam recusados: o caminho
                deles é o gateway.

        Returns:
            PaymentIntent com status CAPTURED e uma ``PaymentTransaction`` de captura.

        Raises:
            PaymentError: METHOD_REQUIRES_GATEWAY (pix/card sem a atestação),
                INVALID_AMOUNT, IDEMPOTENCY_KEY_CONFLICT, INVALID_TRANSITION
                (chave reutilizada por um intent que já morreu)
        """
        if method == PaymentIntent.Method.ACCOUNT:
            raise PaymentError(
                code="account_is_not_settled_at_sale",
                message="Venda em conta não liquida na hora: use charge_to_account (autoriza) e capture no acerto.",
                context={"method": method, "order_ref": order_ref},
            )
        if method not in PaymentIntent.METHODS_WITHOUT_GATEWAY and not asserted_at_terminal:
            raise PaymentError(
                code="method_requires_gateway",
                message=(
                    f"Método '{method}' passa por gateway; use create_intent/authorize/capture. "
                    f"Sem gateway só {sorted(PaymentIntent.METHODS_WITHOUT_GATEWAY)}, "
                    "ou pix/card atestados no terminal (asserted_at_terminal=True)."
                ),
                context={"method": method, "order_ref": order_ref},
            )
        gateway_data = dict(gateway_data or {})
        if asserted_at_terminal:
            gateway_data["asserted_at_terminal"] = True

        intent = cls.create_intent(
            order_ref,
            amount_q,
            method,
            currency=currency,
            gateway="",
            gateway_id="",
            gateway_data=gateway_data,
            ref=ref,
            idempotency_key=idempotency_key,
        )
        intent = cls._get_for_update(intent.ref)

        # Retry com a mesma chave: o intent já liquidou, devolve como está.
        if intent.status in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED):
            return intent

        cls._require_status(intent, PaymentIntent.Status.PENDING, "settle")

        intent.status = PaymentIntent.Status.AUTHORIZED
        intent.save()
        intent.status = PaymentIntent.Status.CAPTURED
        intent.save()

        txn = PaymentTransaction.objects.create(
            intent=intent,
            type=PaymentTransaction.Type.CAPTURE,
            amount_q=intent.amount_q,
            gateway_id="",
        )

        cls._announce(
            payment_captured,
            intent=intent,
            order_ref=intent.order_ref,
            amount_q=intent.amount_q,
            transaction=txn,
        )

        logger.info(
            "Intent settled without gateway",
            extra={"ref": intent.ref, "order_ref": order_ref, "amount_q": intent.amount_q, "method": method},
        )

        return intent

    # ================================================================
    # Conta do cliente (account)
    # ================================================================

    @classmethod
    @transaction.atomic
    def charge_to_account(
        cls,
        order_ref: str,
        amount_q: int,
        *,
        customer_ref: str,
        currency: str = "BRL",
        gateway_data: dict | None = None,
        ref: str | None = None,
        idempotency_key: str = "",
    ) -> PaymentIntent:
        """
        Venda "em conta": o intent nasce AUTORIZADO (= deve) e só vira capturado no acerto (= pagou).

        É a máquina de estados que o Payman já tem, sem gateway, parando em
        ``authorized``: a venda aconteceu, a obrigação está reconhecida, o
        dinheiro ainda não. O saldo devedor do cliente é derivado
        (``account_balance_q``: Σ dos intents ``account`` autorizados e não
        capturados, por ``customer_ref``), nunca uma tabela de saldo. O acerto é
        ``capture`` dos intents mais antigos até o valor (quem orquestra decide o
        método com que o cliente pagou e grava em ``gateway_data``).

        Quem pode comprar em conta NÃO é pergunta do Payman: é elegibilidade do
        cliente (guestman), e o orquestrador recusa antes de chegar aqui.
        """
        if not str(customer_ref or "").strip():
            raise PaymentError(
                code="customer_required",
                message="Venda em conta exige o cliente identificado.",
                context={"order_ref": order_ref},
            )
        gateway_data = {**dict(gateway_data or {}), "customer_ref": str(customer_ref)}
        intent = cls.create_intent(
            order_ref,
            amount_q,
            PaymentIntent.Method.ACCOUNT,
            currency=currency,
            gateway="",
            gateway_id="",
            gateway_data=gateway_data,
            ref=ref,
            idempotency_key=idempotency_key,
        )
        intent = cls._get_for_update(intent.ref)
        # Retry com a mesma chave: já está em conta (ou já foi acertada).
        if intent.status != PaymentIntent.Status.PENDING:
            return intent
        cls._require_status(intent, PaymentIntent.Status.PENDING, "charge_to_account")
        intent.status = PaymentIntent.Status.AUTHORIZED
        intent.save()
        cls._announce(
            payment_authorized,
            intent=intent,
            order_ref=intent.order_ref,
            amount_q=intent.amount_q,
            method=intent.method,
        )
        logger.info(
            "Intent charged to account",
            extra={"ref": intent.ref, "order_ref": order_ref, "amount_q": intent.amount_q, "customer_ref": customer_ref},
        )
        return intent

    @classmethod
    def account_open_intents(cls, customer_ref: str):
        """Os intents ``account`` ainda devidos do cliente, do mais antigo para o mais novo (FIFO do acerto)."""
        return PaymentIntent.objects.filter(
            method=PaymentIntent.Method.ACCOUNT,
            status=PaymentIntent.Status.AUTHORIZED,
            gateway_data__customer_ref=str(customer_ref),
        ).order_by("authorized_at", "id")

    @classmethod
    def account_balance_q(cls, customer_ref: str) -> int:
        """Saldo devedor do cliente: Σ dos intents ``account`` autorizados e não capturados. Derivado, nunca tabela."""
        return int(cls.account_open_intents(customer_ref).aggregate(total=Sum("amount_q"))["total"] or 0)

    @classmethod
    def account_balances(cls) -> list[dict]:
        """Todos os clientes com saldo em aberto: ``[{customer_ref, balance_q, intents, oldest_at}]``, maior saldo primeiro."""
        rows = (
            PaymentIntent.objects.filter(
                method=PaymentIntent.Method.ACCOUNT, status=PaymentIntent.Status.AUTHORIZED
            )
            .values("gateway_data__customer_ref")
            .annotate(balance_q=Sum("amount_q"), intents=Count("id"), oldest_at=Min("authorized_at"))
            .order_by("-balance_q")
        )
        return [
            {
                "customer_ref": str(row["gateway_data__customer_ref"] or ""),
                "balance_q": int(row["balance_q"] or 0),
                "intents": int(row["intents"] or 0),
                "oldest_at": row["oldest_at"],
            }
            for row in rows
        ]

    # ================================================================
    # Authorize
    # ================================================================

    @classmethod
    @transaction.atomic
    def authorize(
        cls,
        ref: str,
        *,
        gateway_id: str = "",
        gateway_data: dict | None = None,
    ) -> PaymentIntent:
        """
        Autoriza pagamento (pending → authorized).

        O gateway externo já confirmou que os fundos estão disponíveis.
        O backend do App chama este método após receber confirmação do gateway.

        Args:
            ref: Referência do intent
            gateway_id: ID da transação no gateway
            gateway_data: Dados extras do gateway

        Returns:
            PaymentIntent atualizado

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION, INTENT_EXPIRED
        """
        intent = cls._get_for_update(ref)

        cls._require_status(intent, PaymentIntent.Status.PENDING, "authorize")
        cls._check_not_expired(intent)

        intent.status = PaymentIntent.Status.AUTHORIZED
        if gateway_id:
            intent.gateway_id = gateway_id
        if gateway_data:
            intent.gateway_data = {**intent.gateway_data, **gateway_data}
        intent.save()

        cls._announce(
            payment_authorized,
            intent=intent,
            order_ref=intent.order_ref,
            amount_q=intent.amount_q,
            method=intent.method,
        )

        logger.info("Intent authorized", extra={"ref": ref, "order_ref": intent.order_ref})

        return intent

    # ================================================================
    # Capture
    # ================================================================

    @classmethod
    @transaction.atomic
    def capture(
        cls,
        ref: str,
        *,
        amount_q: int | None = None,
        gateway_id: str = "",
        gateway_data: dict | None = None,
    ) -> PaymentTransaction:
        """
        Captura pagamento autorizado (authorized → captured).

        Contract: a single capture per intent. If ``amount_q < intent.amount_q``,
        this is a partial capture and the uncaptured balance is abandoned.
        No second capture is possible once the intent transitions to CAPTURED.

        Args:
            ref: Referência do intent
            amount_q: Valor a capturar (None = total autorizado).
                      Partial capture: pass a value < intent.amount_q.
            gateway_id: ID da captura no gateway
            gateway_data: Dados de auditoria a MESCLAR no intent (ex.: com que
                      método e por quem um intent ``account`` foi acertado)

        Returns:
            PaymentTransaction de captura criada

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION, CAPTURE_EXCEEDS_AUTHORIZED
        """
        intent = cls._get_for_update(ref)

        cls._require_status(intent, PaymentIntent.Status.AUTHORIZED, "capture")

        capture_amount = amount_q if amount_q is not None else intent.amount_q

        if capture_amount <= 0:
            raise PaymentError(
                code="invalid_amount",
                message=f"Valor de captura deve ser positivo, recebido: {capture_amount}q",
                context={"capture_amount": capture_amount},
            )

        if capture_amount > intent.amount_q:
            raise PaymentError(
                code="capture_exceeds_authorized",
                message=f"Captura ({capture_amount}q) excede autorizado ({intent.amount_q}q)",
                context={"capture_amount": capture_amount, "authorized_amount": intent.amount_q},
            )

        if gateway_data:
            intent.gateway_data = {**(intent.gateway_data or {}), **gateway_data}
        intent.status = PaymentIntent.Status.CAPTURED
        intent.save()

        txn = PaymentTransaction.objects.create(
            intent=intent,
            type=PaymentTransaction.Type.CAPTURE,
            amount_q=capture_amount,
            gateway_id=gateway_id,
        )

        cls._announce(
            payment_captured,
            intent=intent,
            order_ref=intent.order_ref,
            amount_q=capture_amount,
            transaction=txn,
        )

        logger.info(
            "Intent captured",
            extra={"ref": ref, "order_ref": intent.order_ref, "amount_q": capture_amount},
        )

        return txn

    # ================================================================
    # Refund
    # ================================================================

    @classmethod
    @transaction.atomic
    def refund(
        cls,
        ref: str,
        *,
        amount_q: int | None = None,
        reason: str = "",
        gateway_id: str = "",
        idempotency_key: str = "",
    ) -> PaymentTransaction:
        """
        Processa reembolso (parcial ou total).

        Contract: multiple partial refunds are allowed while
        ``captured_total - refunded_total - chargeback_total > 0`` (dinheiro
        tomado de volta pelo banco já saiu). The intent transitions to
        REFUNDED on the first refund and stays there for subsequent ones.
        ``refunded_total(ref)`` is the financial source of truth, not the
        status field alone.

        Args:
            ref: Referência do intent
            amount_q: Valor a reembolsar (None = total capturado - já reembolsado)
            reason: Motivo do reembolso. Fica gravado na própria transação
                (imutável, como ela): é o "por quê" que auditoria e contador
                perguntam sobre dinheiro que SAIU.
            gateway_id: ID do refund no gateway
            idempotency_key: Chave estável do chamador para retry seguro.
                Necessária porque a dedupe por ``gateway_id`` não alcança
                estorno de DINHEIRO: ele não tem gateway, e dois disparos do
                mesmo estorno de balcão (retry de rede, duplo clique) criariam
                duas devoluções enquanto houvesse saldo.

        Returns:
            PaymentTransaction de refund criada, ou a existente quando a mesma
            chave/gateway_id é reapresentada.

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION,
                AMOUNT_EXCEEDS_CAPTURED, IDEMPOTENCY_KEY_CONFLICT
        """
        intent = cls._get_for_update(ref)

        # Idempotência por gateway_id: um retry (worker morto, at-least-once)
        # que reapresenta o MESMO id de refund do gateway não pode criar uma
        # segunda transação de reembolso — devolve a existente.
        if gateway_id:
            existing = intent.transactions.filter(
                type=PaymentTransaction.Type.REFUND, gateway_id=gateway_id
            ).first()
            if existing is not None:
                return existing

        idempotency_key = (idempotency_key or "").strip()
        if idempotency_key:
            existing = PaymentTransaction.objects.filter(
                type=PaymentTransaction.Type.REFUND, idempotency_key=idempotency_key
            ).first()
            if existing is not None:
                cls._require_idempotent_refund_match(existing, intent=intent, amount_q=amount_q)
                return existing

        if intent.status not in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED):
            raise PaymentError(
                code="invalid_transition",
                message=f"Refund não permitido no status {intent.status}",
                context={"current_status": intent.status},
            )

        captured_q = cls._captured_total(intent)
        returned_q = cls._returned_total(intent)
        available_q = captured_q - returned_q

        if available_q <= 0:
            raise PaymentError(
                code="already_refunded",
                message="Intent não tem saldo capturado para devolver",
                context={
                    "captured_q": captured_q,
                    "refunded_q": cls._refunded_total(intent),
                    "chargeback_q": cls._chargeback_total(intent),
                },
            )

        refund_amount = amount_q if amount_q is not None else available_q

        if refund_amount <= 0:
            raise PaymentError(
                code="invalid_amount",
                message=f"Valor de reembolso deve ser positivo, recebido: {refund_amount}q",
                context={"refund_amount": refund_amount},
            )

        if refund_amount > available_q:
            raise PaymentError(
                code="amount_exceeds_captured",
                message=f"Reembolso ({refund_amount}q) excede disponível ({available_q}q)",
                context={"refund_amount": refund_amount, "available_q": available_q},
            )

        try:
            txn = PaymentTransaction.objects.create(
                intent=intent,
                type=PaymentTransaction.Type.REFUND,
                amount_q=refund_amount,
                gateway_id=gateway_id,
                reason=reason,
                idempotency_key=idempotency_key,
            )
        except IntegrityError:
            # A constraint parcial única é a rede final: dois estornos com a
            # mesma chave em intents diferentes (bug do chamador), ou uma
            # corrida que escapou do lock deste intent.
            if not idempotency_key:
                raise
            existing = PaymentTransaction.objects.filter(
                type=PaymentTransaction.Type.REFUND, idempotency_key=idempotency_key
            ).first()
            if existing is None:
                raise
            cls._require_idempotent_refund_match(existing, intent=intent, amount_q=refund_amount)
            return existing

        # Transition to refunded status (idempotent if already refunded)
        if intent.status != PaymentIntent.Status.REFUNDED:
            intent.status = PaymentIntent.Status.REFUNDED
            intent.save()

        cls._announce(
            payment_refunded,
            intent=intent,
            order_ref=intent.order_ref,
            amount_q=refund_amount,
            transaction=txn,
        )

        logger.info(
            "Intent refunded",
            extra={
                "ref": ref,
                "order_ref": intent.order_ref,
                "amount_q": refund_amount,
                "reason": reason,
            },
        )

        return txn

    # ================================================================
    # Cancel
    # ================================================================

    @classmethod
    @transaction.atomic
    def cancel(cls, ref: str, *, reason: str = "") -> PaymentIntent:
        """
        Cancela intent não capturado.

        Args:
            ref: Referência do intent
            reason: Motivo do cancelamento

        Returns:
            PaymentIntent cancelado

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION
        """
        intent = cls._get_for_update(ref)

        cls._require_can_transition(intent, PaymentIntent.Status.CANCELLED, "cancel")

        intent.status = PaymentIntent.Status.CANCELLED
        intent.cancel_reason = reason
        intent.save()

        cls._announce(
            payment_cancelled,
            intent=intent,
            order_ref=intent.order_ref,
        )

        logger.info(
            "Intent cancelled",
            extra={"ref": ref, "order_ref": intent.order_ref, "reason": reason},
        )

        return intent

    # ================================================================
    # Fail
    # ================================================================

    @classmethod
    @transaction.atomic
    def fail(
        cls,
        ref: str,
        *,
        error_code: str = "",
        message: str = "",
    ) -> PaymentIntent:
        """
        Marca intent como falho.

        Args:
            ref: Referência do intent
            error_code: Código de erro do gateway
            message: Mensagem de erro

        Returns:
            PaymentIntent com status FAILED

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION
        """
        intent = cls._get_for_update(ref)

        cls._require_can_transition(intent, PaymentIntent.Status.FAILED, "fail")

        intent.status = PaymentIntent.Status.FAILED
        if error_code or message:
            intent.gateway_data = {
                **intent.gateway_data,
                "error_code": error_code,
                "error_message": message,
            }
        intent.save()

        cls._announce(
            payment_failed,
            intent=intent,
            order_ref=intent.order_ref,
            error_code=error_code,
            message=message,
        )

        logger.info(
            "Intent failed",
            extra={"ref": ref, "order_ref": intent.order_ref, "error_code": error_code},
        )

        return intent

    # ================================================================
    # Queries
    # ================================================================

    @classmethod
    @transaction.atomic
    def reconcile_gateway_status(
        cls,
        ref: str,
        *,
        gateway_status: str,
        amount_q: int | None = None,
        captured_q: int | None = None,
        refunded_q: int = 0,
        chargeback_q: int = 0,
        currency: str = "BRL",
        gateway_id: str = "",
        gateway_data: dict | None = None,
        capture_gateway_id: str = "",
        refund_gateway_id: str = "",
        chargeback_gateway_id: str = "",
    ) -> PaymentReconciliationResult:
        """
        Reconcile Payman with a cumulative gateway snapshot.

        Gateways often report totals, not deltas. Stripe's
        ``charge.amount_refunded`` is cumulative, for example. This method is
        the canonical place to apply those snapshots without double refunding,
        missing a later partial refund, or moving money backwards.

        Chargeback
        ----------

        ``chargeback_q`` é o total devolvido por decisão de TERCEIRO — disputa
        de cartão, MED do Pix — e não por vontade da loja. Mesma mecânica do
        refund: snapshot cumulativo, guarda de monotonicidade nos dois
        sentidos, uma ``PaymentTransaction(CHARGEBACK)`` só pelo delta.

        Duas diferenças deliberadas em relação ao refund:

        * **viaja como valor, não como status.** Não existe ``gateway_status``
          de chargeback no mapa: a disputa acontece por fora do ciclo da
          cobrança, o dinheiro capturado continua capturado no vocabulário da
          máquina de estados, e quem responde "quanto voltou" é o livro
          (``chargeback_total``), não o campo ``status``. Inventar um status
          traria uma transição nova para um fato que a loja não decide.
        * **não emite signal.** Os cinco sinais do pacote anunciam transições
          de status, e aqui não há transição. Quem precisa ver chargeback vê
          pela reconciliação financeira diária, que tem issue-code próprio
          (``intent_has_chargeback`` em
          ``shopman/backstage/services/financial_reconciliation.py``).

        Quem alimenta: qualquer chamador do gateway. Hoje nenhum adapter
        escuta os eventos de disputa (o adapter Stripe trata
        ``charge.refunded``, não ``charge.dispute.*``); o valor chega por
        reconciliação manual do operador até que passem a escutar.
        """
        intent = cls._get_for_update(ref)
        status = cls._normalize_gateway_status(gateway_status)
        actions: list[str] = []
        drift: list[str] = []
        changed = False

        snapshot_amount_q = intent.amount_q if amount_q is None else int(amount_q)
        snapshot_captured_q = (
            snapshot_amount_q
            if captured_q is None and status in {"captured", "refunded"}
            else int(captured_q or 0)
        )
        snapshot_refunded_q = int(refunded_q or 0)
        snapshot_chargeback_q = int(chargeback_q or 0)
        snapshot_currency = (currency or intent.currency).upper()

        cls._validate_gateway_snapshot(
            intent,
            status=status,
            amount_q=snapshot_amount_q,
            captured_q=snapshot_captured_q,
            refunded_q=snapshot_refunded_q,
            chargeback_q=snapshot_chargeback_q,
            currency=snapshot_currency,
            gateway_id=gateway_id,
        )

        if gateway_id and not intent.gateway_id:
            intent.gateway_id = gateway_id
            changed = True
        if gateway_data:
            intent.gateway_data = {**(intent.gateway_data or {}), **gateway_data}
            changed = True
        if changed:
            intent.save()

        if status == "authorized" and intent.status == PaymentIntent.Status.PENDING:
            intent.status = PaymentIntent.Status.AUTHORIZED
            intent.save()
            cls._announce(
                payment_authorized,
                intent=intent,
                order_ref=intent.order_ref,
                amount_q=intent.amount_q,
                method=intent.method,
            )
            actions.append("authorized")
            changed = True

        if status in {"captured", "refunded"} or snapshot_captured_q > 0:
            if intent.status in {PaymentIntent.Status.FAILED, PaymentIntent.Status.CANCELLED}:
                raise PaymentError(
                    code="reconciliation_terminal_drift",
                    message="Gateway reportou captura para intent terminal local",
                    context={
                        "ref": ref,
                        "local_status": intent.status,
                        "gateway_status": status,
                        "captured_q": snapshot_captured_q,
                    },
                )

            if intent.status == PaymentIntent.Status.PENDING:
                intent.status = PaymentIntent.Status.AUTHORIZED
                intent.save()
                cls._announce(
                    payment_authorized,
                    intent=intent,
                    order_ref=intent.order_ref,
                    amount_q=intent.amount_q,
                    method=intent.method,
                )
                actions.append("authorized")
                changed = True

            local_captured_q = cls._captured_total(intent)
            if local_captured_q == 0 and snapshot_captured_q > 0:
                if intent.status == PaymentIntent.Status.AUTHORIZED:
                    intent.status = PaymentIntent.Status.CAPTURED
                    intent.save()
                elif intent.status not in {PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED}:
                    raise PaymentError(
                        code="reconciliation_capture_drift",
                        message="Status local não permite registrar captura reconciliada",
                        context={
                            "ref": ref,
                            "local_status": intent.status,
                            "gateway_status": status,
                        },
                    )

                txn = PaymentTransaction.objects.create(
                    intent=intent,
                    type=PaymentTransaction.Type.CAPTURE,
                    amount_q=snapshot_captured_q,
                    gateway_id=capture_gateway_id or gateway_id,
                )
                cls._announce(
                    payment_captured,
                    intent=intent,
                    order_ref=intent.order_ref,
                    amount_q=snapshot_captured_q,
                    transaction=txn,
                )
                actions.append("captured")
                changed = True
            elif local_captured_q != snapshot_captured_q:
                raise PaymentError(
                    code="reconciliation_capture_mismatch",
                    message="Total capturado local diverge do gateway",
                    context={
                        "ref": ref,
                        "local_captured_q": local_captured_q,
                        "gateway_captured_q": snapshot_captured_q,
                    },
                )

        if status in {"captured", "refunded"} or snapshot_refunded_q:
            local_refunded_q = cls._refunded_total(intent)
            if snapshot_refunded_q < local_refunded_q:
                raise PaymentError(
                    code="reconciliation_refund_mismatch",
                    message="Total reembolsado local excede o gateway",
                    context={
                        "ref": ref,
                        "local_refunded_q": local_refunded_q,
                        "gateway_refunded_q": snapshot_refunded_q,
                    },
                )

            refund_delta_q = snapshot_refunded_q - local_refunded_q
            if refund_delta_q > 0:
                if intent.status not in {PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED}:
                    raise PaymentError(
                        code="reconciliation_refund_drift",
                        message="Gateway reportou refund para intent sem captura local",
                        context={
                            "ref": ref,
                            "local_status": intent.status,
                            "gateway_refunded_q": snapshot_refunded_q,
                        },
                    )

                txn = PaymentTransaction.objects.create(
                    intent=intent,
                    type=PaymentTransaction.Type.REFUND,
                    amount_q=refund_delta_q,
                    gateway_id=refund_gateway_id or gateway_id,
                    reason="gateway_reconciliation",
                )
                if intent.status != PaymentIntent.Status.REFUNDED:
                    intent.status = PaymentIntent.Status.REFUNDED
                    intent.save()
                cls._announce(
                    payment_refunded,
                    intent=intent,
                    order_ref=intent.order_ref,
                    amount_q=refund_delta_q,
                    transaction=txn,
                )
                actions.append("refunded")
                changed = True

        if snapshot_chargeback_q:
            local_chargeback_q = cls._chargeback_total(intent)
            if snapshot_chargeback_q < local_chargeback_q:
                raise PaymentError(
                    code="reconciliation_chargeback_mismatch",
                    message="Total de chargeback local excede o gateway",
                    context={
                        "ref": ref,
                        "local_chargeback_q": local_chargeback_q,
                        "gateway_chargeback_q": snapshot_chargeback_q,
                    },
                )

            chargeback_delta_q = snapshot_chargeback_q - local_chargeback_q
            if chargeback_delta_q > 0:
                if intent.status not in {PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED}:
                    raise PaymentError(
                        code="reconciliation_chargeback_drift",
                        message="Gateway reportou chargeback para intent sem captura local",
                        context={
                            "ref": ref,
                            "local_status": intent.status,
                            "gateway_chargeback_q": snapshot_chargeback_q,
                        },
                    )

                PaymentTransaction.objects.create(
                    intent=intent,
                    type=PaymentTransaction.Type.CHARGEBACK,
                    amount_q=chargeback_delta_q,
                    gateway_id=chargeback_gateway_id or gateway_id,
                    reason="gateway_chargeback",
                )
                actions.append("chargeback")
                changed = True

        if status == "cancelled" and intent.status in {PaymentIntent.Status.PENDING, PaymentIntent.Status.AUTHORIZED}:
            intent.status = PaymentIntent.Status.CANCELLED
            intent.cancel_reason = "gateway_reconciliation"
            intent.save()
            cls._announce(payment_cancelled, intent=intent, order_ref=intent.order_ref)
            actions.append("cancelled")
            changed = True

        if status == "failed" and intent.status in {PaymentIntent.Status.PENDING, PaymentIntent.Status.AUTHORIZED}:
            intent.status = PaymentIntent.Status.FAILED
            intent.gateway_data = {
                **(intent.gateway_data or {}),
                "error_code": "gateway_reconciliation",
                "error_message": "Gateway reportou falha no pagamento",
            }
            intent.save()
            cls._announce(
                payment_failed,
                intent=intent,
                order_ref=intent.order_ref,
                error_code="gateway_reconciliation",
                message="Gateway reportou falha no pagamento",
            )
            actions.append("failed")
            changed = True

        final_captured_q = cls._captured_total(intent)
        final_refunded_q = cls._refunded_total(intent)
        final_chargeback_q = cls._chargeback_total(intent)
        result = PaymentReconciliationResult(
            intent_ref=ref,
            status=PaymentIntent.objects.only("status").get(pk=intent.pk).status,
            captured_q=final_captured_q,
            refunded_q=final_refunded_q,
            changed=changed,
            actions=tuple(actions),
            drift=tuple(drift),
            chargeback_q=final_chargeback_q,
        )
        logger.info(
            "payment.reconciled",
            extra={
                "event": "payment.reconciled",
                "intent_ref": ref,
                "order_ref": intent.order_ref,
                "gateway": intent.gateway,
                "gateway_status": status,
                "local_status": result.status,
                "captured_q": final_captured_q,
                "refunded_q": final_refunded_q,
                "chargeback_q": final_chargeback_q,
                "changed": changed,
                "actions": result.actions,
            },
        )
        return result

    @classmethod
    def get(cls, ref: str) -> PaymentIntent:
        """
        Busca intent por ref.

        Raises:
            PaymentError: INTENT_NOT_FOUND
        """
        try:
            return PaymentIntent.objects.get(ref=ref)
        except PaymentIntent.DoesNotExist as e:
            raise PaymentError(
                code="intent_not_found",
                message=f"Intent '{ref}' não encontrado",
                context={"ref": ref},
            ) from e

    @classmethod
    def get_by_order(cls, order_ref: str) -> QuerySet[PaymentIntent]:
        """Retorna todos os intents de um pedido, mais recentes primeiro."""
        return PaymentIntent.objects.filter(order_ref=order_ref)

    @classmethod
    def get_active_intent(cls, order_ref: str, *, method: str | None = None) -> PaymentIntent | None:
        """A cobrança de pé para o pedido: pendente ou autorizada, não expirada.

        "Ativo" é o dinheiro que ainda se espera, não o que já entrou:
        ``captured`` fica de fora (ver ``PaymentIntent.ACTIVE_STATUSES``, que
        não é o complemento de ``TERMINAL_STATUSES``). Quem quer saber se o
        pedido foi pago pergunta a ``captured_total``.

        Cardinalidade: um pedido pode ter mais de um intent — venda mista cria
        um por método (``settle_terminal_tenders`` em
        ``shopman/shop/services/payment.py``), e uma tentativa de pix que falha
        deixa a geração anterior para trás. Os do terminal nascem capturados e
        já saem daqui; das gerações queimadas, a mais recente é a cobrança
        corrente (o orquestrador cancela as anteriores em
        ``cancel_stale_intents``). Passe ``method`` quando a pergunta for sobre
        um meio de pagamento específico, ou use ``get_by_order`` para ver todos.
        """
        now = timezone.now()
        qs = PaymentIntent.objects.filter(
            order_ref=order_ref,
            status__in=PaymentIntent.ACTIVE_STATUSES,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        if method is not None:
            qs = qs.filter(method=method)
        return qs.order_by("-created_at").first()

    @classmethod
    def get_by_gateway_id(
        cls,
        gateway_id: str,
        *,
        gateway: str | None = None,
    ) -> PaymentIntent | None:
        """Busca intent por ID externo, opcionalmente restrito ao gateway."""
        qs = PaymentIntent.objects.filter(gateway_id=gateway_id)
        if gateway is not None:
            qs = qs.filter(gateway=gateway)
        return qs.order_by("-created_at").first()

    # ================================================================
    # Aggregates
    # ================================================================

    @classmethod
    def captured_total(cls, ref: str) -> int:
        """Total capturado para um intent."""
        intent = cls.get(ref)
        return cls._captured_total(intent)

    @classmethod
    def refunded_total(cls, ref: str) -> int:
        """Total reembolsado para um intent."""
        intent = cls.get(ref)
        return cls._refunded_total(intent)

    @classmethod
    def chargeback_total(cls, ref: str) -> int:
        """Total devolvido por decisão de terceiro (disputa, MED) para um intent."""
        intent = cls.get(ref)
        return cls._chargeback_total(intent)

    # ================================================================
    # Private
    # ================================================================

    @classmethod
    def _announce(cls, signal, **kwargs) -> None:
        """Anuncia um fato de pagamento DEPOIS do COMMIT.

        Dentro da transação o anúncio é promessa, não fato: o chamador pode
        abrir um atomic externo, capturar e falhar depois — é literalmente o
        que ``_settle_pos_sale`` faz em ``shopman/shop/services/pos.py`` (um
        ``atomic`` em volta de ``settle_terminal_tenders`` + escrita da venda
        no livro do turno). Com o ``send`` lá dentro, o rollback desfaz o
        pagamento e deixa de pé o que o receiver já fez com a notícia de um
        dinheiro que, para o banco, nunca existiu. Pior: exceção de receiver
        aborta a própria captura — o rabo abana o cachorro.

        ``on_commit`` inverte as duas coisas: o fato só é anunciado quando é
        fato, e quem escuta não derruba quem cobra. É o idioma do pacote irmão
        (``packages/cashman/shopman/cashman/services/ledger.py``). Fora de
        bloco atômico o Django roda o callback na hora, então chamador
        não-transacional não muda de comportamento.

        O kwarg ``intent`` é a instância viva, não um retrato do instante do
        fato: quando um mesmo verbo encadeia transições (o ``reconcile`` que
        autoriza e captura no mesmo snapshot), o receiver lê o estado FINAL.
        Quem precisar do estado exato de cada etapa lê ``transaction`` (linha
        imutável) ou refaz a leitura no banco.
        """
        transaction.on_commit(lambda: signal.send(sender=cls, **kwargs))

    @classmethod
    def _get_for_update(cls, ref: str) -> PaymentIntent:
        """Get intent with select_for_update."""
        try:
            return PaymentIntent.objects.select_for_update().get(ref=ref)
        except PaymentIntent.DoesNotExist as e:
            raise PaymentError(
                code="intent_not_found",
                message=f"Intent '{ref}' não encontrado",
                context={"ref": ref},
            ) from e

    @classmethod
    def _require_status(cls, intent: PaymentIntent, expected: str, operation: str) -> None:
        """Raise if intent is not in the expected status."""
        if intent.status != expected:
            raise PaymentError(
                code="invalid_transition",
                message=f"Não é possível {operation}: status atual é {intent.status}, esperado {expected}",
                context={
                    "current_status": intent.status,
                    "expected_status": expected,
                    "operation": operation,
                },
            )

    @classmethod
    def _require_can_transition(cls, intent: PaymentIntent, target: str, operation: str) -> None:
        """Raise if intent cannot transition to target status."""
        if not intent.can_transition_to(target):
            raise PaymentError(
                code="invalid_transition",
                message=f"Não é possível {operation}: transição {intent.status} → {target} não permitida",
                context={
                    "current_status": intent.status,
                    "target_status": target,
                    "operation": operation,
                },
            )

    @classmethod
    def _check_not_expired(cls, intent: PaymentIntent) -> None:
        """Raise if intent is expired."""
        if intent.expires_at and intent.expires_at <= timezone.now():
            raise PaymentError(
                code="intent_expired",
                message=f"Intent '{intent.ref}' expirado em {intent.expires_at}",
                context={"ref": intent.ref, "expires_at": str(intent.expires_at)},
            )

    @classmethod
    def _require_idempotent_match(
        cls,
        intent: PaymentIntent,
        *,
        order_ref: str,
        amount_q: int,
        method: str,
        currency: str,
        gateway: str,
    ) -> None:
        """Raise if a repeated idempotency key is being reused for another payment."""
        expected = {
            "order_ref": order_ref,
            "amount_q": amount_q,
            "method": method,
            "currency": currency,
            "gateway": gateway,
        }
        actual = {
            "order_ref": intent.order_ref,
            "amount_q": intent.amount_q,
            "method": intent.method,
            "currency": intent.currency,
            "gateway": intent.gateway,
        }
        mismatched = {
            field: {"expected": value, "actual": actual[field]}
            for field, value in expected.items()
            if actual[field] != value
        }
        if mismatched:
            raise PaymentError(
                code="idempotency_key_conflict",
                message="Chave de idempotência reutilizada com parâmetros diferentes",
                context={"idempotency_key": intent.idempotency_key, "mismatched": mismatched},
            )

    @classmethod
    def _require_idempotent_refund_match(
        cls,
        txn: PaymentTransaction,
        *,
        intent: PaymentIntent,
        amount_q: int | None,
    ) -> None:
        """Recusa a chave de um estorno reapresentada para OUTRO estorno.

        Mesma postura do ``create_intent``: devolver a transação existente em
        silêncio quando os parâmetros mudaram mascara o bug do chamador — e
        aqui o bug é sobre dinheiro que sai.
        """
        mismatched: dict[str, dict] = {}
        if txn.intent_id != intent.pk:
            mismatched["intent_ref"] = {"expected": intent.ref, "actual": txn.intent.ref}
        if amount_q is not None and txn.amount_q != int(amount_q):
            mismatched["amount_q"] = {"expected": int(amount_q), "actual": txn.amount_q}
        if mismatched:
            raise PaymentError(
                code="idempotency_key_conflict",
                message="Chave de idempotência reutilizada com outro reembolso",
                context={"idempotency_key": txn.idempotency_key, "mismatched": mismatched},
            )

    @classmethod
    def _normalize_gateway_status(cls, status: str) -> str:
        normalized = str(status or "").strip().lower()
        status_map = {
            "ativa": "pending",
            "active": "pending",
            "processing": "pending",
            "requires_payment_method": "pending",
            "requires_action": "pending",
            "requires_capture": "authorized",
            "authorized": "authorized",
            "succeeded": "captured",
            "paid": "captured",
            "captured": "captured",
            "concluida": "captured",
            "completed": "captured",
            "refunded": "refunded",
            "failed": "failed",
            "declined": "failed",
            "canceled": "cancelled",
            "cancelled": "cancelled",
            "removida_pelo_usuario_recebedor": "cancelled",
            "removida_pelo_psp": "cancelled",
        }
        return status_map.get(normalized, normalized)

    @classmethod
    def _validate_gateway_snapshot(
        cls,
        intent: PaymentIntent,
        *,
        status: str,
        amount_q: int,
        captured_q: int,
        refunded_q: int,
        chargeback_q: int,
        currency: str,
        gateway_id: str,
    ) -> None:
        if status not in {"pending", "authorized", "captured", "refunded", "failed", "cancelled"}:
            raise PaymentError(
                code="reconciliation_unknown_status",
                message=f"Status de gateway desconhecido: {status}",
                context={"ref": intent.ref, "gateway_status": status},
            )
        if amount_q <= 0 or captured_q < 0 or refunded_q < 0 or chargeback_q < 0:
            raise PaymentError(
                code="reconciliation_invalid_amount",
                message="Snapshot do gateway tem valores invalidos",
                context={
                    "ref": intent.ref,
                    "amount_q": amount_q,
                    "captured_q": captured_q,
                    "refunded_q": refunded_q,
                    "chargeback_q": chargeback_q,
                },
            )
        if amount_q != intent.amount_q:
            raise PaymentError(
                code="reconciliation_amount_mismatch",
                message="Valor do gateway diverge do intent local",
                context={"ref": intent.ref, "local_amount_q": intent.amount_q, "gateway_amount_q": amount_q},
            )
        if currency and currency != intent.currency.upper():
            raise PaymentError(
                code="reconciliation_currency_mismatch",
                message="Moeda do gateway diverge do intent local",
                context={"ref": intent.ref, "local_currency": intent.currency, "gateway_currency": currency},
            )
        if captured_q > amount_q:
            raise PaymentError(
                code="reconciliation_capture_exceeds_amount",
                message="Total capturado no gateway excede o valor do intent",
                context={"ref": intent.ref, "amount_q": amount_q, "captured_q": captured_q},
            )
        if refunded_q > captured_q:
            raise PaymentError(
                code="reconciliation_refund_exceeds_capture",
                message="Total reembolsado no gateway excede o capturado",
                context={"ref": intent.ref, "captured_q": captured_q, "refunded_q": refunded_q},
            )
        if refunded_q + chargeback_q > captured_q:
            raise PaymentError(
                code="reconciliation_chargeback_exceeds_capture",
                message="Reembolso + chargeback no gateway excedem o capturado",
                context={
                    "ref": intent.ref,
                    "captured_q": captured_q,
                    "refunded_q": refunded_q,
                    "chargeback_q": chargeback_q,
                },
            )
        if gateway_id and intent.gateway_id and gateway_id != intent.gateway_id:
            raise PaymentError(
                code="reconciliation_gateway_id_mismatch",
                message="Gateway id do snapshot diverge do intent local",
                context={"ref": intent.ref, "local_gateway_id": intent.gateway_id, "gateway_id": gateway_id},
            )

    @classmethod
    def _captured_total(cls, intent: PaymentIntent) -> int:
        return (
            intent.transactions.filter(type=PaymentTransaction.Type.CAPTURE).aggregate(
                total=models.Sum("amount_q")
            )["total"]
            or 0
        )

    @classmethod
    def _refunded_total(cls, intent: PaymentIntent) -> int:
        return (
            intent.transactions.filter(type=PaymentTransaction.Type.REFUND).aggregate(
                total=models.Sum("amount_q")
            )["total"]
            or 0
        )

    @classmethod
    def _chargeback_total(cls, intent: PaymentIntent) -> int:
        return (
            intent.transactions.filter(type=PaymentTransaction.Type.CHARGEBACK).aggregate(
                total=models.Sum("amount_q")
            )["total"]
            or 0
        )

    @classmethod
    def _returned_total(cls, intent: PaymentIntent) -> int:
        """Tudo que voltou ao cliente: reembolso da loja + chargeback de terceiro.

        É este o saldo que limita um novo reembolso. Dinheiro tomado de volta
        pelo banco já saiu da conta; estornar de novo pagaria duas vezes.
        """
        return cls._refunded_total(intent) + cls._chargeback_total(intent)

    @classmethod
    def _generate_ref(cls) -> str:
        return f"PAY-{uuid.uuid4().hex[:12].upper()}"
