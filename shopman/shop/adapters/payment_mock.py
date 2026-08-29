"""
Gateway **de Pix** simulado, para desenvolvimento e teste.

Persiste via PaymentService (DB) e simula o lado do gateway em memória.

⚠️ **Cartão não passa por aqui.** Cartão é redirect para ambiente hospedado
(Stripe Checkout), e simular isso não testava nada: testava o simulador. Um
cartão de teste do Stripe (``4242…``) exercita o caminho REAL inteiro — Checkout
Session, redirect, webhook assinado, captura. Por isso ``method="card"`` é
recusado (:func:`_refuse_card`) em vez de atendido; a configuração certa é
``SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_stripe`` com chave
``sk_test_``.

Foi exatamente esse ramo que custou dinheiro: o mock autorizava o cartão no ato,
o storefront pulava o Stripe e o acompanhamento anunciava "Pagamento autorizado";
um minuto depois a confirmação otimista capturava a autorização de mentira
(``lifecycle._on_accepted``: cartão + autorizado → ``payment.capture``). Pedido
pago, pão entregue, zero dinheiro.

⚠️ **Um simulador nunca autoriza.** Autorizar é o gateway dizendo "conferi o
instrumento do cliente e ele cobre este valor". Aqui não existe gateway, então
não existe essa frase para dizer: o intent nasce ``pending`` e só anda por ato
explícito — ``mock_confirm`` (atrás de ``SHOPMAN_EXPOSE_MOCK_CAPTURE``) ou a
confirmação de Pix agendada por ``SHOPMAN_MOCK_PIX_AUTO_CONFIRM``.

⚠️ **E um simulador não roda fora de dev.** Ver :func:`_ensure_simulation_allowed`.
A porta fica nos verbos que CRIAM ou CAPTURAM dinheiro (``create_intent``,
``capture``). ``refund`` e ``cancel`` ficam abertos de propósito: nenhum dos dois
consegue inventar receita, e recusá-los num ambiente mal configurado só prende
pedido que precisa ser desfeito.

Returns canonical DTOs from shopman.shop.adapters.payment_types.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.utils import timezone

from shopman.shop.adapters.payment_types import PaymentIntent, PaymentResult

logger = logging.getLogger(__name__)


class MockCardNotSupported(RuntimeError):
    """Pediram cartão ao simulador — que deliberadamente não atende cartão."""


def _refuse_card(method: str) -> None:
    """Cartão não tem versão simulada. Recusa alto, no primeiro ponto possível.

    Antes daqui o mock atendia cartão e devolvia um intent sem ``checkout_url``,
    o que fazia a loja anunciar pagamento sem nunca ter cobrado. Fechar o ramo
    seria suficiente para não perder dinheiro, mas ainda deixaria de pé a ideia
    de que existe "cartão de mentira" — e é justamente ela que não se sustenta:
    o que precisa ser testado no cartão (redirect, 3DS, recusa, webhook) só
    existe no gateway de verdade, e o Stripe entrega tudo isso em modo de teste.
    """
    if str(method or "").strip().lower() != "card":
        return
    raise MockCardNotSupported(
        "O gateway simulado não atende cartão. Configure "
        "SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_stripe e use os "
        "cartões de teste do Stripe (chave sk_test_)."
    )


class MockGatewayNotAllowed(RuntimeError):
    """O gateway simulado foi chamado num ambiente que não autoriza simulação."""


def _ensure_simulation_allowed() -> None:
    """Recusa a simulação fora de dev — o simulador FALHA, nunca inventa dinheiro.

    ``SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS`` já existia, mas só como *check de
    deploy* (``SHOPMAN_E003``/``SHOPMAN_W006``, ``@register(deploy=True)``): ele
    roda em ``manage.py check --deploy``, não no boot e muito menos por
    requisição. Um deploy com ``SHOPMAN_CARD_ADAPTER`` apontando para cá subia
    normalmente e cobrava ninguém em silêncio.

    Aqui a mesma env vira porta de runtime. Fora de ``DEBUG`` e sem opt-in
    explícito, ``create_intent`` levanta — ``payment.initiate`` grava o erro em
    ``order.data["payment"]["error"]`` e o cliente vê o degrau de falha do
    acompanhamento. Parar é o comportamento correto: melhor um pedido que não
    fecha do que um pedido "pago" que ninguém pagou.
    """
    if settings.DEBUG:
        return
    if getattr(settings, "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", False):
        return
    raise MockGatewayNotAllowed(
        "Gateway de pagamento simulado (payment_mock) recusado fora de DEBUG. "
        "Configure SHOPMAN_PIX_ADAPTER/SHOPMAN_CARD_ADAPTER com um gateway real, "
        "ou ligue SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true apenas em staging técnico."
    )


def create_intent(
    *,
    order_ref: str,
    amount_q: int,
    currency: str = "BRL",
    method: str = "pix",
    metadata: dict | None = None,
    **config,
) -> PaymentIntent:
    """Create a mock **Pix** intent with persistence via PaymentService.

    O intent nasce ``pending``. Confirmar é ato explícito: a captura simulada do
    acompanhamento (``mock_confirm``, atrás de ``SHOPMAN_EXPOSE_MOCK_CAPTURE``)
    ou a directive agendada por ``mock_pix_auto_confirm=True``, para quem
    precisa exercitar a paridade com o webhook assíncrono.

    ⚠️ ``method="card"`` não existe aqui — ver :func:`_refuse_card`.
    """
    _ensure_simulation_allowed()
    _refuse_card(method)

    from shopman.orderman.models import Directive
    from shopman.payman import PaymentService

    metadata = metadata or {}
    idempotency_key = config.get("idempotency_key") or metadata.get("idempotency_key", "")
    pix_timeout = config.get("pix_timeout_minutes", 30)
    expires_at = timezone.now() + timedelta(minutes=pix_timeout) if method == "pix" else None

    db_intent = PaymentService.create_intent(
        order_ref=order_ref,
        amount_q=amount_q,
        method=method,
        gateway="mock",
        gateway_data=metadata,
        expires_at=expires_at,
        idempotency_key=idempotency_key,
    )
    if db_intent.gateway_id and db_intent.gateway_data.get("client_secret"):
        return _intent_from_db(db_intent, currency=currency)

    gateway_id = f"mock_pi_{uuid4().hex[:12]}"

    db_intent.gateway_id = gateway_id
    gateway_data = {**metadata}
    intent_metadata = {}
    client_secret = None
    if method == "pix":
        mock_brcode = (
            f"00020126580014br.gov.bcb.pix0136mock-{gateway_id}"
            f"5204000053039865404{amount_q / 100:.2f}"
            f"5802BR5913MOCK6008SHOPMAN62070503***6304MOCK"
        )
        mock_qr_image = _qr_png_data_url(mock_brcode)
        client_secret = json.dumps({"qrcode": mock_brcode, "brcode": mock_brcode, "imagemQrcode": mock_qr_image})
        gateway_data["client_secret"] = client_secret
        intent_metadata = {"qrcode": mock_brcode, "brcode": mock_brcode, "imagemQrcode": mock_qr_image}
    db_intent.gateway_data = gateway_data
    db_intent.save(update_fields=["gateway_id", "gateway_data"])

    status = db_intent.status

    if method == "pix" and config.get("mock_pix_auto_confirm") is True:
        delay_seconds = int(config.get("mock_pix_confirm_delay_seconds", 10))
        available_at = timezone.now() + timedelta(seconds=delay_seconds)
        Directive.objects.create(
            topic="mock_pix.confirm",
            payload={
                "order_ref": order_ref,
                "txid": gateway_id,
                "e2e_id": f"E2E{uuid4().hex[:24].upper()}",
                "amount": f"{amount_q / 100:.2f}",
                "mock_pix_auto_confirm": True,
            },
            available_at=available_at,
        )
        logger.info(
            "payment_mock: scheduled mock_pix.confirm for order=%s txid=%s in %ss",
            order_ref, gateway_id, delay_seconds,
        )

    return PaymentIntent(
        intent_ref=db_intent.ref,
        status=status,
        amount_q=amount_q,
        currency=currency,
        client_secret=client_secret,
        expires_at=expires_at,
        gateway_id=gateway_id,
        metadata=intent_metadata,
    )


def _intent_from_db(intent, *, currency: str = "BRL") -> PaymentIntent:
    client_secret = (intent.gateway_data or {}).get("client_secret")
    metadata = dict(intent.gateway_data or {})
    if client_secret:
        try:
            parsed = json.loads(client_secret)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            metadata.update(parsed)
    return PaymentIntent(
        intent_ref=intent.ref,
        status=intent.status,
        amount_q=intent.amount_q,
        currency=currency or intent.currency,
        client_secret=client_secret,
        expires_at=intent.expires_at,
        gateway_id=intent.gateway_id,
        metadata=metadata,
    )


def _qr_png_data_url(value: str) -> str:
    """Return a real scannable QR image as a PNG data URL for local PIX testing."""
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=6,
        border=4,
    )
    qr.add_data(value)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def capture(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    **config,
) -> PaymentResult:
    """Capture mock payment via PaymentService.

    Captura é escrita de dinheiro no livro do Payman, então passa pela mesma
    porta de ambiente do ``create_intent``: fora de dev, sem opt-in, levanta.
    """
    _ensure_simulation_allowed()

    from shopman.payman import PaymentError, PaymentService

    try:
        txn = PaymentService.capture(intent_ref, amount_q=amount_q)
        return PaymentResult(
            success=True,
            transaction_id=f"mock_txn_{intent_ref}",
            amount_q=txn.amount_q,
        )
    except PaymentError as e:
        return PaymentResult(
            success=False,
            error_code=e.code,
            message=e.message,
        )


def refund(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    reason: str = "",
    idempotency_key: str = "",
    **config,
) -> PaymentResult:
    """Process mock refund via PaymentService.

    Espelha o contrato real: ``idempotency_key`` vira gateway_id determinístico,
    então o Payman deduplica um retry (não estorna duas vezes).
    """
    from shopman.payman import PaymentError, PaymentService

    gateway_id = f"mock_refund_{idempotency_key}" if idempotency_key else f"mock_refund_{uuid4().hex[:8]}"
    try:
        txn = PaymentService.refund(
            intent_ref,
            amount_q=amount_q,
            reason=reason,
            gateway_id=gateway_id,
        )
        return PaymentResult(
            success=True,
            transaction_id=gateway_id,
            amount_q=txn.amount_q,
        )
    except PaymentError as e:
        return PaymentResult(
            success=False,
            error_code=e.code,
            message=e.message,
        )


def cancel(intent_ref: str, **config) -> PaymentResult:
    """Cancel mock payment intent via PaymentService."""
    from shopman.payman import PaymentError, PaymentService

    try:
        PaymentService.cancel(intent_ref, reason=str(config.get("reason") or ""))
        return PaymentResult(success=True)
    except PaymentError as e:
        return PaymentResult(
            success=False,
            error_code=e.code,
            message=e.message,
        )


def get_status(intent_ref: str, **config) -> dict:
    """Get payment status from PaymentService.

    Returns a plain dict because get_status is a read-only convenience that
    doesn't participate in the orchestrator contract.
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
    """O "gateway" simulado tem pagamento para este intent? LEITURA, sem efeito.

    Mesmo contrato do ``payment_efi.check_gateway_status``: devolve ``captured``,
    ``pending``, ``cancelled``, ``not_found`` ou ``error``. Quem pergunta é
    ``shop.services.payment.verify_gateway_before_timeout_cancel``, antes de
    auto-cancelar um PIX vencido.

    ``not_found`` e ``error`` são respostas DIFERENTES e não podem ser a mesma:
    intent que nunca existiu é ausência de pagamento (cancelar é certo), enquanto
    gateway mudo é incerteza (esperar é certo). Confundir os dois faz a directive
    de timeout tentar para sempre um pedido que nunca teve cobrança.

    ⚠️ O ponto deste verbo é **não** ser o ``capture()``. O ``capture()`` do mock
    captura incondicionalmente — é o que se espera de um simulador quando alguém
    manda capturar de propósito. Mas responder a uma PERGUNTA com ele fazia todo
    PIX vencido sem pagamento virar "pago". Aqui não há gateway externo, então a
    única verdade disponível é o estado do próprio intent: ele só está pago se
    alguém o capturou explicitamente (o botão de simular, ou o auto-confirm).
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        return "not_found"

    if PaymentService.captured_total(intent_ref) > 0:
        return "captured"
    return "cancelled" if intent.status == "cancelled" else "pending"
