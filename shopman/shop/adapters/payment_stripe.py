"""
Stripe payment adapter — card payments via Stripe Checkout (hosted redirect).

Delegação total: criamos uma `CheckoutSession` via API e devolvemos a `session.url`
pública do Stripe. O cliente é redirecionado para `checkout.stripe.com` e a UI
inteira é do Stripe (PCI scope = SAQ A — nenhum dado de cartão toca o servidor).
Após pagamento, o webhook `checkout.session.completed` confirma o intent.

Persists via PaymentService (DB) + communicates with Stripe API.
Requires: pip install stripe

Além do ciclo da cobrança, este adapter escuta as **disputas** (`charge.dispute.*`)
e as traduz para o snapshot cumulativo de chargeback do Payman — ver
:func:`handle_dispute_event`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from shopman.shop.adapters.payment_types import PaymentIntent, PaymentResult
from shopman.shop.services import storefront_links

logger = logging.getLogger(__name__)


def _metadata_value(metadata, key: str) -> str:
    """Read metadata from dicts and StripeObject instances."""
    if not metadata:
        return ""
    if isinstance(metadata, dict):
        value = metadata.get(key)
    else:
        try:
            value = metadata[key]
        except (AttributeError, KeyError, TypeError):
            value = getattr(metadata, key, "")
    return str(value or "")


def _storefront_absolute(path: str, stripe_config: dict) -> str:
    """URL absoluta DA LOJA para onde o Stripe devolve o cliente.

    O Stripe exige URL absoluta, e ela tem que apontar para a loja (Nuxt), não
    para a API. Montar na mão a partir de um `domain` local rendeu três defeitos
    ao mesmo tempo: o default era a origem do Django (o cliente voltava para um
    host que não serve essa rota), a barra final não existe na rota Nuxt, e o
    destino de sucesso era `/pedido/<ref>/confirmacao/` — tela que deixou de
    existir quando o yoin migrou para o acompanhamento.

    Fonte da verdade é `storefront_links`; o `domain` do config fica só como
    reserva para quando a base da loja não estiver configurada.
    """
    url = storefront_links.storefront_url(path)
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = str(stripe_config.get("domain") or "").rstrip("/")
    return f"{base}{url}" if base else url


def _get_config() -> dict:
    """Read Stripe configuration from settings."""
    return getattr(settings, "SHOPMAN_STRIPE", {})


class StripeNotConfigured(RuntimeError):
    """Gateway de cartão sem credencial — não há como cobrar, e não se finge."""


def _get_stripe():
    """Lazy import of stripe SDK.

    ⚠️ Sem ``secret_key`` isto levanta ANTES de qualquer chamada de rede. É o
    contrário do que o simulador fazia: faltando gateway, o certo é o pedido
    parar com erro visível (``payment.initiate`` grava o erro e o
    acompanhamento mostra o degrau de falha), nunca seguir em frente. Falhar
    aqui também evita que a suíte tente falar com api.stripe.com por acidente.
    """
    try:
        import stripe
    except ImportError as err:
        raise ImportError(
            "stripe package is required. Install with: pip install stripe"
        ) from err
    config = _get_config()
    secret_key = str(config.get("secret_key") or "").strip()
    if not secret_key:
        raise StripeNotConfigured(
            "Cartão está apontado para o Stripe, mas STRIPE_SECRET_KEY está vazia. "
            "Configure a credencial (sk_test_ no alpha, sk_live_ em produção)."
        )
    stripe.api_key = secret_key
    return stripe


def test_mode() -> bool:
    """O Stripe configurado está em modo de TESTE?

    A verdade vem da própria chave (``pk_test_``/``sk_test_``), nunca de
    ``DEBUG`` nem de uma flag manual: flag manual é exatamente o tipo de coisa
    que vaza para produção. Chave ``live`` — ou ausente — responde ``False``.
    """
    config = _get_config()
    publishable = str(config.get("publishable_key") or "").strip()
    secret = str(config.get("secret_key") or "").strip()
    if not publishable and not secret:
        return False
    # Qualquer lado em `live` derruba o modo de teste: uma configuração
    # meio-a-meio é erro, e na dúvida a resposta segura é "isto é produção".
    if publishable.startswith("pk_live_") or secret.startswith("sk_live_"):
        return False
    return publishable.startswith("pk_test_") or secret.startswith("sk_test_")


def create_intent(
    *,
    order_ref: str,
    amount_q: int,
    currency: str = "BRL",
    method: str = "card",
    metadata: dict | None = None,
    **config,
) -> PaymentIntent:
    """Create a Stripe Checkout Session + persist via PaymentService.

    Returns a `PaymentIntent` whose `metadata["checkout_url"]` is the Stripe-hosted
    URL the client must be redirected to. `gateway_id` is the Checkout Session id
    (`cs_...`); the actual `payment_intent` id is filled in later by the webhook.
    """
    from shopman.payman import PaymentService

    metadata = metadata or {}
    idempotency_key = config.get("idempotency_key") or metadata.get("idempotency_key", "")
    stripe_config = _get_config()
    stripe_currency = currency.lower()

    # ⚠️ Credencial ANTES de escrever no Payman. Enquanto a ordem era a inversa,
    # um deploy sem `STRIPE_SECRET_KEY` criava a linha de cobrança, falhava ao
    # falar com o Stripe e deixava um intent órfão — que a recuperação de
    # `payment.initiate` (`_existing_active_intent`) então adotava como se fosse
    # boa, limpando o erro do pedido. Cobrança que o gateway nunca viu não pode
    # virar a cobrança do pedido.
    stripe = _get_stripe()

    db_intent = PaymentService.create_intent(
        order_ref=order_ref,
        amount_q=amount_q,
        method="card",
        gateway="stripe",
        gateway_data=metadata,
        idempotency_key=idempotency_key,
    )
    if db_intent.gateway_id and db_intent.gateway_data.get("checkout_url"):
        return _intent_from_db(db_intent, currency=currency)

    create_options = {"idempotency_key": idempotency_key} if idempotency_key else {}
    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": stripe_currency,
                "product_data": {"name": f"Pedido {order_ref}"},
                "unit_amount": amount_q,
            },
            "quantity": 1,
        }],
        success_url=_storefront_absolute(
            storefront_links.path_order_tracking(order_ref), stripe_config,
        ),
        cancel_url=_storefront_absolute(
            # PAYMENT-TRACKING-MERGE: cancelar no Stripe volta para o próprio
            # acompanhamento (onde o cartão é oferecido inline), não para uma tela.
            storefront_links.path_order_tracking(order_ref), stripe_config,
        ),
        metadata={
            "shopman_ref": db_intent.ref,
            "order_ref": order_ref,
            **metadata,
        },
        payment_intent_data={
            "capture_method": config.get("capture_method", "manual"),
            "metadata": {
                "shopman_ref": db_intent.ref,
                "order_ref": order_ref,
            },
        },
        **create_options,
    )

    db_intent.gateway_id = session.id
    db_intent.gateway_data = {
        **metadata,
        "checkout_session_id": session.id,
        "checkout_url": session.url,
    }
    db_intent.save(update_fields=["gateway_id", "gateway_data"])

    return PaymentIntent(
        intent_ref=db_intent.ref,
        status="pending",
        amount_q=amount_q,
        currency=currency,
        gateway_id=session.id,
        metadata={"checkout_url": session.url},
    )


def _intent_from_db(intent, *, currency: str = "BRL") -> PaymentIntent:
    gateway_data = dict(intent.gateway_data or {})
    return PaymentIntent(
        intent_ref=intent.ref,
        status=intent.status,
        amount_q=intent.amount_q,
        currency=currency or intent.currency,
        gateway_id=intent.gateway_id,
        metadata={"checkout_url": gateway_data.get("checkout_url", "")},
    )


def capture(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    **config,
) -> PaymentResult:
    """Capture a Stripe PaymentIntent.

    For capture_method="automatic", payment is already captured.
    For capture_method="manual", calls stripe.PaymentIntent.capture().
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError as e:
        return PaymentResult(success=False, error_code=e.code, message=e.message)

    stripe = _get_stripe()

    # ⚠️ Capturar exige o ``pi_...``, e o ``gateway_id`` só vira ``pi_`` quando o
    # webhook ``checkout.session.completed`` chega para promovê-lo. Enquanto ele
    # não chega (ou não chega nunca — endpoint errado no painel), o id guardado é
    # a Checkout Session, e capturar com ele falha. A reconciliação existe
    # justamente para o caso do webhook perdido, então ela não pode depender dele.
    payment_intent_id = gateway_payment_intent_id(intent_ref) or intent.gateway_id
    if payment_intent_id and payment_intent_id != intent.gateway_id:
        try:
            intent.gateway_id = payment_intent_id
            intent.save(update_fields=["gateway_id"])
        except Exception:
            logger.debug("stripe.capture gateway_id promotion degraded", exc_info=True)

    try:
        capture_params = {}
        if amount_q is not None:
            capture_params["amount_to_capture"] = amount_q

        # Já capturado no Stripe e não no Payman é divergência a RECONCILIAR, não
        # a recobrar: mandar ``capture`` de novo devolve erro do provedor, e o
        # erro fazia a reconciliação desistir de um pedido efetivamente pago.
        stripe_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        if str(getattr(stripe_intent, "status", "") or "") != "succeeded":
            stripe_intent = stripe.PaymentIntent.capture(
                payment_intent_id,
                **capture_params,
            )

        txn = PaymentService.capture(
            intent_ref,
            amount_q=amount_q,
            gateway_id=stripe_intent.id,
        )

        return PaymentResult(
            success=True,
            transaction_id=stripe_intent.latest_charge,
            amount_q=txn.amount_q,
        )
    except Exception as e:
        logger.exception("Stripe capture error for %s", intent_ref)
        return PaymentResult(
            success=False,
            error_code="stripe_error",
            message=str(e),
        )


def refund(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    reason: str = "",
    idempotency_key: str = "",
    **config,
) -> PaymentResult:
    """Process refund via Stripe + PaymentService.

    ``idempotency_key`` é repassado ao Stripe (``Refund.create`` é idempotente
    por essa chave), então um retry devolve o MESMO refund em vez de criar um
    segundo — e o id estável volta como gateway_id p/ o Payman.
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError as e:
        return PaymentResult(success=False, error_code=e.code, message=e.message)

    stripe = _get_stripe()

    try:
        refund_params = {"payment_intent": intent.gateway_id}
        if amount_q is not None:
            refund_params["amount"] = amount_q
        if reason:
            refund_params["reason"] = "requested_by_customer"
        if idempotency_key:
            refund_params["idempotency_key"] = idempotency_key

        stripe_refund = stripe.Refund.create(**refund_params)

        refund_amount = stripe_refund.amount
        try:
            PaymentService.refund(
                intent_ref,
                amount_q=refund_amount,
                reason=reason,
                gateway_id=stripe_refund.id,
            )
        except PaymentError as exc:
            # O dinheiro JÁ saiu no gateway. Sem o registro local, o Payman
            # continua mostrando saldo reembolsável e um trigger futuro faria
            # um SEGUNDO refund real — falha tem que ser visível, nunca muda.
            logger.error(
                "payment_stripe.refund: gateway devolveu %sq mas o registro local falhou (%s) intent=%s",
                refund_amount, exc, intent_ref,
            )
            from shopman.shop.services.observability import create_operator_alert

            create_operator_alert(
                type="payment_ledger_drift",
                severity="critical",
                message=(
                    f"Refund Stripe de {refund_amount} centavos executado no gateway "
                    f"mas NÃO registrado no Payman (intent {intent_ref}). "
                    "Conciliar manualmente antes de qualquer novo estorno."
                ),
                dedupe_key=f"refund_drift:{intent_ref}",
                intent_ref=intent_ref,
                gateway_refund_id=stripe_refund.id,
            )

        return PaymentResult(
            success=True,
            transaction_id=stripe_refund.id,
            amount_q=refund_amount,
        )
    except Exception as e:
        logger.exception("Stripe refund error for %s", intent_ref)
        return PaymentResult(
            success=False,
            error_code="stripe_error",
            message=str(e),
        )


def cancel(intent_ref: str, **config) -> PaymentResult:
    """Cancel a Stripe PaymentIntent + PaymentService."""
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        return PaymentResult(
            success=False,
            error_code="intent_not_found",
            message="Intent não encontrado",
        )

    stripe = _get_stripe()

    try:
        stripe.PaymentIntent.cancel(intent.gateway_id)

        try:
            PaymentService.cancel(intent_ref, reason=str(config.get("reason") or ""))
        except PaymentError:
            pass

        return PaymentResult(success=True)
    except Exception as e:
        logger.warning("Stripe cancel failed for %s: %s", intent_ref, e, exc_info=True)
        return PaymentResult(
            success=False,
            error_code="stripe_error",
            message=str(e),
        )


def get_status(intent_ref: str, **config) -> dict:
    """
    Get payment status from PaymentService (source of truth).

    Returns:
        {"intent_ref": str, "status": str, "amount_q": int,
         "captured_q": int, "refunded_q": int, "currency": str}
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        captured_q = PaymentService.captured_total(intent_ref)
        refunded_q = PaymentService.refunded_total(intent_ref)

        return {
            "intent_ref": intent_ref,
            "status": intent.status,
            "amount_q": intent.amount_q,
            "captured_q": captured_q,
            "refunded_q": refunded_q,
            "currency": intent.currency,
        }
    except PaymentError:
        return {
            "intent_ref": intent_ref,
            "status": "not_found",
            "amount_q": 0,
            "captured_q": 0,
            "refunded_q": 0,
            "currency": "",
        }


def check_gateway_status(intent_ref: str) -> str:
    """O que o STRIPE diz sobre este intent? LEITURA pura, sem efeito colateral.

    Mesmo contrato de ``payment_efi.check_gateway_status``, com um degrau a mais
    que só o cartão tem: ``authorized``. Devolve ``captured``, ``authorized``,
    ``pending``, ``cancelled``, ``not_found`` ou ``error``.

    ⚠️ **Este verbo existia na Efí e no mock, e não existia aqui.** Sem ele,
    NADA no sistema jamais perguntava ao Stripe: ``get_status`` lê o Payman, o
    webhook é a única escrita, e ``reconcile_payments`` também só lê o Payman.
    Webhook perdido (endpoint errado no painel, segredo de outro ambiente, 400
    na assinatura) virava dano permanente — o cliente pagava, voltava para o
    acompanhamento e continuava lendo "Pagar com cartão", para sempre. E o
    guard de timeout, sem ninguém a quem perguntar, respondia ``unpaid`` para
    cartão por construção, autorizando o cancelamento de um pedido pago.

    ``authorized`` é degrau próprio porque ``capture_method="manual"`` é o
    padrão da casa: o Stripe segura o dinheiro em ``requires_capture`` até
    alguém capturar. Achatar isso em ``pending`` diria "não pagou" sobre quem
    pagou; achatar em ``captured`` diria que o dinheiro entrou antes de entrar.

    ``not_found`` e ``error`` seguem sendo respostas DIFERENTES: intent que
    nunca existiu é ausência de pagamento (cancelar é certo), gateway mudo é
    incerteza (esperar é certo).
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        return "not_found"

    gateway_id = str(intent.gateway_id or "")
    session_id = str((intent.gateway_data or {}).get("checkout_session_id") or "")

    try:
        stripe = _get_stripe()
    except (StripeNotConfigured, ImportError):
        # Sem credencial não se responde "não pagou": responde-se "não sei".
        logger.warning("stripe.check_gateway_status_unconfigured intent=%s", intent_ref)
        return "error"

    try:
        payment_intent_id = gateway_id if gateway_id.startswith("pi_") else ""
        if not payment_intent_id:
            # Antes do webhook o ``gateway_id`` ainda é a Checkout Session; é ela
            # quem sabe qual PaymentIntent nasceu do checkout.
            lookup_session = session_id or (gateway_id if gateway_id.startswith("cs_") else "")
            if not lookup_session:
                return "not_found"
            session = stripe.checkout.Session.retrieve(lookup_session)
            if str(getattr(session, "status", "") or "") == "expired":
                return "cancelled"
            payment_intent_id = _stripe_object_id(getattr(session, "payment_intent", None))
            if not payment_intent_id:
                # Sessão aberta, cliente ainda não concluiu: não há cobrança.
                return "pending"

        stripe_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    except Exception as e:
        logger.warning("stripe.check_gateway_status_failed intent=%s: %s", intent_ref, e)
        return "error"

    status = str(getattr(stripe_intent, "status", "") or "")
    if status == "succeeded" or int(getattr(stripe_intent, "amount_received", 0) or 0) > 0:
        return "captured"
    if status == "requires_capture":
        return "authorized"
    if status == "canceled":
        return "cancelled"
    if status in {
        "requires_payment_method",
        "requires_confirmation",
        "requires_action",
        "processing",
    }:
        return "pending"
    # Status novo do provedor: incerteza, e incerteza espera.
    logger.warning("stripe.check_gateway_status_unknown intent=%s status=%s", intent_ref, status)
    return "error"


def gateway_payment_intent_id(intent_ref: str) -> str:
    """O id do PaymentIntent no Stripe, resolvendo a Checkout Session se preciso.

    Existe para a reconciliação poder CAPTURAR uma autorização cujo webhook se
    perdeu: o ``gateway_id`` do Payman ainda pode ser o ``cs_...``, e capturar
    exige o ``pi_...``. Devolve string vazia quando não dá para resolver.
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        return ""

    gateway_id = str(intent.gateway_id or "")
    if gateway_id.startswith("pi_"):
        return gateway_id

    session_id = str((intent.gateway_data or {}).get("checkout_session_id") or "")
    lookup_session = session_id or (gateway_id if gateway_id.startswith("cs_") else "")
    if not lookup_session:
        return ""
    try:
        stripe = _get_stripe()
        session = stripe.checkout.Session.retrieve(lookup_session)
    except Exception as e:
        logger.warning("stripe.gateway_payment_intent_lookup_failed intent=%s: %s", intent_ref, e)
        return ""
    return _stripe_object_id(getattr(session, "payment_intent", None))


def construct_webhook_event(payload: bytes, sig_header: str):
    stripe = _get_stripe()
    stripe_config = _get_config()
    return stripe.Webhook.construct_event(
        payload, sig_header, stripe_config.get("webhook_secret"),
    )


def webhook_event_key(event, payload: bytes) -> str:
    from shopman.shop.services.webhook_idempotency import stable_webhook_key

    event_id = getattr(event, "id", "")
    if isinstance(event_id, str) and event_id.strip():
        return f"event:{stable_webhook_key(event_id.strip())}"
    return f"payload:{stable_webhook_key(payload)}"


# ══════════════════════════════════════════════════════════════════════
# Disputas (chargeback)
# ══════════════════════════════════════════════════════════════════════

# Os cinco eventos de disputa do Stripe. Todos chegam pelo MESMO endpoint e
# passam pelo mesmo dedupe durável por `event.id`
# (`shopman/shop/services/webhook_idempotency.py`), então cada um pode chegar
# repetido e fora de ordem.
DISPUTE_EVENT_TYPES = frozenset({
    "charge.dispute.created",
    "charge.dispute.updated",
    "charge.dispute.closed",
    "charge.dispute.funds_withdrawn",
    "charge.dispute.funds_reinstated",
})

# `Dispute.status` (https://docs.stripe.com/api/disputes/object). Terminal =
# a disputa acabou; o valor não muda mais.
_DISPUTE_LOST_STATUSES = frozenset({"lost"})
_DISPUTE_TERMINAL_STATUSES = frozenset({"lost", "won", "warning_closed", "prevented"})


def _stripe_object_id(value) -> str:
    """Id de um campo expandível do Stripe (string crua ou objeto com `.id`)."""
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    nested = getattr(value, "id", None)
    if nested is None and isinstance(value, dict):
        nested = value.get("id")
    return str(nested or "").strip()


def _resolve_disputed_intent(dispute):
    """Acha o intent local da disputa pelo id que o Payman guarda.

    O `gateway_id` do intent é o `payment_intent` do Stripe — promovido a
    partir do id da Checkout Session quando `checkout.session.completed`
    chega. A `charge` entra como segunda tentativa para a janela em que a
    promoção não aconteceu.
    """
    from shopman.payman import PaymentService

    for candidate in (
        getattr(dispute, "payment_intent", None),
        getattr(dispute, "charge", None),
    ):
        gateway_id = _stripe_object_id(candidate)
        if not gateway_id:
            continue
        db_intent = PaymentService.get_by_gateway_id(gateway_id, gateway="stripe")
        if db_intent is not None:
            return db_intent
    return None


def _evidence_due_by(dispute) -> str:
    details = getattr(dispute, "evidence_details", None)
    due_by = getattr(details, "due_by", None)
    if due_by is None and isinstance(details, dict):
        due_by = details.get("due_by")
    try:
        return datetime.fromtimestamp(int(due_by), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def handle_dispute_event(event) -> str:
    """Traduz um evento `charge.dispute.*` para o snapshot do Payman.

    **Só entra como chargeback o dinheiro que saiu e não volta mais.** O ciclo
    do Stripe tem três regimes distintos de dinheiro, e confundi-los é
    contabilizar prejuízo que não houve:

    * ``warning_needs_response`` / ``warning_under_review`` — *inquiry*: o
      emissor pergunta antes de abrir disputa formal e **nenhum dinheiro se
      move**. ``warning_closed`` encerra sem chargeback.
    * ``needs_response`` / ``under_review`` — disputa aberta. O Stripe retira o
      valor da conta (``charge.dispute.funds_withdrawn``), mas a retirada é
      **reversível**: ganhando, ``charge.dispute.funds_reinstated`` devolve.
    * ``won`` / ``prevented`` — acabou a favor da loja. **Não é chargeback.**
    * ``lost`` — acabou contra a loja. O dinheiro foi e não volta.

    Por isso a ``PaymentTransaction(CHARGEBACK)`` nasce **só em ``lost``**, e a
    razão é o formato do livro, não preferência: a transação é imutável e o
    snapshot de chargeback do ``reconcile_gateway_status`` é monotônico (total
    menor que o local levanta ``reconciliation_chargeback_mismatch``, ver
    ``packages/payman/shopman/payman/service.py``). Chargeback lançado não tem
    como ser desfeito — lançar na abertura deixaria a loja permanentemente mais
    pobre no livro toda vez que ela **ganhasse** a disputa.

    Enquanto a disputa está viva o valor em risco fica em
    ``intent.gateway_data["disputes"][<dispute_id>]``, que é contexto
    (reversível) e não livro, e o operador é avisado pelo alerta
    ``payment_disputed`` — a defesa tem prazo. ⚠️ A disputa **aberta** não
    aparece no relatório financeiro diário: o intent só entra no escopo do dia
    em que teve transação (ver ``build_financial_reconciliation``), e uma
    disputa aberta não cria transação nenhuma. O canal dela é o alerta; o do
    dinheiro é o chargeback, que cria transação e dispara
    ``intent_has_chargeback``.

    Entrega at-least-once e fora de ordem: o estado por disputa é guardado por
    id, o status terminal é **grudento** (um ``created`` atrasado não reabre
    disputa encerrada) e o valor mandado ao Payman é a soma cumulativa das
    disputas perdidas — reapresentar o mesmo ``closed`` dá delta zero.

    Returns:
        A ref do intent afetado, ou string vazia quando a disputa não mapeia
        para nenhum intent local.
    """
    from shopman.payman import PaymentError, PaymentService
    from shopman.payman import PaymentIntent as PaymanIntentModel

    dispute = event.data.object
    dispute_id = _stripe_object_id(dispute)
    event_type = str(getattr(event, "type", "") or "")
    db_intent = _resolve_disputed_intent(dispute)

    if db_intent is None or not dispute_id:
        logger.warning(
            "payment_stripe: disputa %s (%s) não mapeia para nenhum intent local — "
            "sem intent não há livro onde lançar",
            dispute_id or "?",
            event_type,
        )
        return ""

    incoming_status = str(getattr(dispute, "status", "") or "").strip()
    incoming_amount_q = int(getattr(dispute, "amount", 0) or 0)

    with transaction.atomic():
        # Lock da linha: dois eventos da mesma disputa (ou de duas disputas da
        # mesma cobrança) chegam por requests diferentes, e o merge do
        # `gateway_data` é read-modify-write.
        locked = PaymanIntentModel.objects.select_for_update().get(pk=db_intent.pk)
        gateway_data = dict(locked.gateway_data or {})
        disputes = dict(gateway_data.get("disputes") or {})
        stored = dict(disputes.get(dispute_id) or {})
        stored_status = str(stored.get("status") or "")

        status = incoming_status
        amount_q = incoming_amount_q or int(stored.get("amount_q") or 0)
        if stored_status in _DISPUTE_TERMINAL_STATUSES and status not in _DISPUTE_TERMINAL_STATUSES:
            # Fora de ordem: `created` chegando depois do `closed` não reabre
            # o que já terminou.
            status = stored_status
            amount_q = int(stored.get("amount_q") or amount_q)

        record = {
            "status": status,
            "amount_q": amount_q,
            "currency": str(getattr(dispute, "currency", "") or "").upper(),
            "reason": str(getattr(dispute, "reason", "") or ""),
            "charge_id": _stripe_object_id(getattr(dispute, "charge", None)),
            "evidence_due_by": _evidence_due_by(dispute) or str(stored.get("evidence_due_by") or ""),
            "funds_withdrawn": bool(stored.get("funds_withdrawn"))
            or event_type == "charge.dispute.funds_withdrawn",
            "funds_reinstated": bool(stored.get("funds_reinstated"))
            or event_type == "charge.dispute.funds_reinstated",
            "last_event": event_type,
            "updated_at": timezone.now().isoformat(),
        }
        disputes[dispute_id] = record
        gateway_data["disputes"] = disputes
        locked.gateway_data = gateway_data
        locked.save(update_fields=["gateway_data"])

        was_lost = stored_status in _DISPUTE_LOST_STATUSES
        is_lost = status in _DISPUTE_LOST_STATUSES

        if was_lost and not is_lost:
            # Reversão depois do lançamento (arbitragem ganha depois de
            # perdida). O livro é imutável: o chargeback lançado FICA, e a
            # correção é humana — dinheiro que volta por outra via.
            from shopman.shop.services import observability

            observability.create_operator_alert(
                type="payment_reconciliation_failed",
                severity="critical",
                message=(
                    f"Disputa {dispute_id} do intent {locked.ref} saiu de 'lost' para "
                    f"'{status}': o chargeback já lançado no Payman não é reversível. "
                    "Conciliar à mão com o extrato do Stripe."
                ),
                dedupe_key=f"dispute-reversal:{dispute_id}",
                intent_ref=locked.ref,
                order_ref=locked.order_ref,
            )

        lost_total_q = sum(
            int(item.get("amount_q") or 0)
            for item in disputes.values()
            if str(item.get("status") or "") in _DISPUTE_LOST_STATUSES
        )
        local_chargeback_q = PaymentService.chargeback_total(locked.ref)

        if lost_total_q > local_chargeback_q:
            captured_q = PaymentService.captured_total(locked.ref)
            refunded_q = PaymentService.refunded_total(locked.ref)
            try:
                PaymentService.reconcile_gateway_status(
                    locked.ref,
                    gateway_status="refunded" if refunded_q else "captured",
                    amount_q=locked.amount_q,
                    # Captura e reembolso vão com o total LOCAL de propósito: o
                    # evento de disputa não fala da cobrança, só do valor
                    # contestado. Passar o local deixa esses dois braços do
                    # snapshot em delta zero e mexe apenas no chargeback — e
                    # ainda satisfaz as guardas de soma do
                    # `_validate_gateway_snapshot`.
                    captured_q=captured_q,
                    refunded_q=refunded_q,
                    chargeback_q=lost_total_q,
                    gateway_id=locked.gateway_id,
                    chargeback_gateway_id=dispute_id,
                )
            except PaymentError as exc:
                logger.warning(
                    "Stripe dispute reconciliation drift intent=%s dispute=%s code=%s context=%s",
                    locked.ref,
                    dispute_id,
                    exc.code,
                    exc.context,
                )
                from shopman.shop.services import observability

                observability.record_payment_reconciliation_failure(
                    gateway="stripe",
                    intent_ref=locked.ref,
                    order_ref=locked.order_ref,
                    code=exc.code,
                    context={**(exc.context or {}), "dispute_id": dispute_id},
                    exc=exc,
                )
            else:
                _alert_dispute_lost(
                    intent_ref=locked.ref,
                    order_ref=locked.order_ref,
                    dispute_id=dispute_id,
                    amount_q=amount_q,
                )
        elif status and status not in _DISPUTE_TERMINAL_STATUSES:
            _alert_dispute_open(
                intent_ref=locked.ref,
                order_ref=locked.order_ref,
                dispute_id=dispute_id,
                amount_q=amount_q,
                evidence_due_by=record["evidence_due_by"],
            )

    from shopman.shop.services import observability

    observability.operational_event(
        "payment_dispute.received",
        gateway="stripe",
        event_type=event_type,
        dispute_id=dispute_id,
        intent_ref=db_intent.ref,
        order_ref=db_intent.order_ref,
        dispute_status=status,
        amount_q=amount_q,
    )
    return db_intent.ref


def _alert_dispute_open(
    *,
    intent_ref: str,
    order_ref: str,
    dispute_id: str,
    amount_q: int,
    evidence_due_by: str,
) -> None:
    from shopman.shop.services import observability

    prazo = f" Prazo de defesa: {evidence_due_by}." if evidence_due_by else ""
    observability.create_operator_alert(
        type="payment_disputed",
        severity="error",
        order_ref=order_ref,
        message=(
            f"Cartão contestado: {amount_q} centavos do pedido {order_ref or '-'} "
            f"estão em disputa no Stripe (intent {intent_ref}).{prazo} "
            "Sem defesa no prazo, o valor vira chargeback."
        ),
        dedupe_key=f"dispute-open:{dispute_id}",
        debounce_minutes=60,
        intent_ref=intent_ref,
        dispute_id=dispute_id,
    )


def _alert_dispute_lost(
    *,
    intent_ref: str,
    order_ref: str,
    dispute_id: str,
    amount_q: int,
) -> None:
    from shopman.shop.services import observability

    observability.create_operator_alert(
        type="payment_disputed",
        severity="critical",
        order_ref=order_ref,
        message=(
            f"Disputa perdida: {amount_q} centavos do pedido {order_ref or '-'} "
            f"foram retirados pelo banco (intent {intent_ref}). "
            "Lançado como chargeback no Payman."
        ),
        dedupe_key=f"dispute-lost:{dispute_id}",
        debounce_minutes=60,
        intent_ref=intent_ref,
        dispute_id=dispute_id,
    )


def handle_webhook_event(event) -> dict:
    """Process a verified Stripe webhook event."""
    from shopman.payman import PaymentError, PaymentService

    intent_ref = None

    if event.type == "checkout.session.completed":
        session = event.data.object
        session_metadata = getattr(session, "metadata", None) or {}
        shopman_ref = _metadata_value(session_metadata, "shopman_ref")
        payment_intent_id = getattr(session, "payment_intent", None)
        if shopman_ref:
            intent_ref = shopman_ref
            # Promote gateway_id from session id to payment_intent id so
            # downstream refund/cancel calls hit the canonical Stripe object.
            if payment_intent_id:
                try:
                    db_intent = PaymentService.get(shopman_ref)
                    if db_intent.gateway_id != payment_intent_id:
                        db_intent.gateway_id = payment_intent_id
                        db_intent.save(update_fields=["gateway_id"])
                except PaymentError:
                    pass
            try:
                PaymentService.authorize(
                    shopman_ref, gateway_id=payment_intent_id or shopman_ref,
                )
            except PaymentError:
                pass

    elif event.type == "payment_intent.succeeded":
        stripe_intent = event.data.object
        shopman_ref = _metadata_value(
            getattr(stripe_intent, "metadata", None),
            "shopman_ref",
        )
        if shopman_ref:
            intent_ref = shopman_ref
            try:
                PaymentService.authorize(shopman_ref, gateway_id=stripe_intent.id)
            except PaymentError:
                pass
            try:
                PaymentService.capture(shopman_ref, gateway_id=stripe_intent.id)
            except PaymentError:
                pass

    elif event.type == "payment_intent.payment_failed":
        stripe_intent = event.data.object
        shopman_ref = _metadata_value(
            getattr(stripe_intent, "metadata", None),
            "shopman_ref",
        )
        if shopman_ref:
            intent_ref = shopman_ref
            last_error = getattr(stripe_intent, "last_payment_error", None)
            try:
                PaymentService.fail(
                    shopman_ref,
                    error_code=last_error.code if last_error else "unknown",
                    message=last_error.message if last_error else "",
                )
            except PaymentError:
                pass

    elif event.type in DISPUTE_EVENT_TYPES:
        intent_ref = handle_dispute_event(event) or None

    elif event.type == "charge.refunded":
        charge = event.data.object
        stripe_intent_id = charge.payment_intent
        if stripe_intent_id:
            db_intent = PaymentService.get_by_gateway_id(stripe_intent_id, gateway="stripe")
            if db_intent:
                intent_ref = db_intent.ref
                try:
                    PaymentService.reconcile_gateway_status(
                        db_intent.ref,
                        gateway_status="refunded",
                        amount_q=db_intent.amount_q,
                        captured_q=getattr(charge, "amount_captured", getattr(charge, "amount", db_intent.amount_q)),
                        refunded_q=charge.amount_refunded,
                        gateway_id=stripe_intent_id,
                        refund_gateway_id=charge.id,
                    )
                except PaymentError as exc:
                    logger.warning(
                        "Stripe refund reconciliation drift intent=%s code=%s context=%s",
                        db_intent.ref,
                        exc.code,
                        exc.context,
                    )
                    from shopman.shop.services import observability

                    observability.record_payment_reconciliation_failure(
                        gateway="stripe",
                        intent_ref=db_intent.ref,
                        order_ref=db_intent.order_ref,
                        code=exc.code,
                        context=exc.context,
                        exc=exc,
                    )

    return {"event_type": event.type, "intent_ref": intent_ref}


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Process a Stripe webhook event.

    Called by older code paths. Verifies signature and processes event.

    Returns:
        {"event_type": str, "intent_ref": str | None}
    """
    event = construct_webhook_event(payload, sig_header)
    return handle_webhook_event(event)
