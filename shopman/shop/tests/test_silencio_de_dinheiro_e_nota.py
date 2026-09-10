"""Dinheiro entrando e nota saindo não podem falhar calados.

Cada teste aqui trava a volta de um site que estava nas faixas 💸 e 🧾 do
``docs/reference/silencio-inventario.md``. A régua é sempre a mesma, e é a
razão de o arquivo existir: simular a falha e provar que ou **nasce alerta**,
ou a operação **falha fechada** — nunca que ela segue afirmando sucesso.

O caso que dá nome ao arquivo é o do Efí: o Pix era confirmado no gateway, o
registro local falhava, e a função devolvia ``success=True``. Ele tem teste
próprio e explícito, dos dois lados (a falha que agora fecha, e o sucesso que
agora tem lastro no Payman).
"""

from __future__ import annotations

import base64
import gzip
import logging
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from shopman.cashman import services as cash
from shopman.payman import PaymentError, PaymentService
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import payment_efi, payment_stripe, purchase_invoice_nfe
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db


def _intent(*, method: str, gateway: str, gateway_id: str, order_ref: str = "ORD-SIL"):
    intent = PaymentService.create_intent(
        order_ref=order_ref,
        amount_q=1200,
        method=method,
        gateway=gateway,
        gateway_data={},
    )
    intent.gateway_id = gateway_id
    intent.save(update_fields=["gateway_id"])
    return intent


def _reconciliation_alerts():
    return OperatorAlert.objects.filter(type="payment_reconciliation_failed")


def _stripe_event(event_type: str, *, gateway_id: str, shopman_ref: str):
    event = MagicMock()
    event.type = event_type
    obj = MagicMock()
    obj.id = gateway_id
    obj.metadata = {"shopman_ref": shopman_ref}
    obj.last_payment_error = None
    event.data.object = obj
    return event


# ══════════════════════════════════════════════════════════════
# Stripe — dinheiro ENTRANDO alerta igual dinheiro saindo (E54)
# ══════════════════════════════════════════════════════════════


def test_stripe_authorize_que_falha_no_webhook_abre_alerta():
    """O cartão foi cobrado e o Payman não registrou: alguém precisa saber.

    Era ``except PaymentError: pass`` — a forma exata do incidente E54.
    """
    intent = _intent(method="card", gateway="stripe", gateway_id="pi_sil_1")
    event = _stripe_event("payment_intent.succeeded", gateway_id="pi_sil_1", shopman_ref=intent.ref)

    with patch.object(
        PaymentService, "authorize", side_effect=PaymentError(code="db_down", message="sem banco")
    ):
        payment_stripe.handle_webhook_event(event)

    alert = _reconciliation_alerts().get()
    assert alert.severity == "critical"
    assert intent.ref in alert.message
    intent.refresh_from_db()
    assert intent.status == "pending"


def test_stripe_webhook_repetido_nao_vira_alarme_falso():
    """O Stripe reentrega o mesmo dinheiro por contrato; isso não é divergência.

    Sem esta guarda, toda venda de cartão abriria um alerta crítico — e alarme
    falso é como um alerta verdadeiro morre.
    """
    intent = _intent(method="card", gateway="stripe", gateway_id="pi_sil_2")
    event = _stripe_event("payment_intent.succeeded", gateway_id="pi_sil_2", shopman_ref=intent.ref)

    payment_stripe.handle_webhook_event(event)
    payment_stripe.handle_webhook_event(event)

    intent.refresh_from_db()
    assert intent.status == "captured"
    assert not _reconciliation_alerts().exists()


def test_stripe_diz_que_falhou_e_o_livro_diz_capturado_abre_alerta():
    """Pedido pago sem dinheiro nenhum é o inverso do E54, e também gritava nada."""
    intent = _intent(method="card", gateway="stripe", gateway_id="pi_sil_3")
    PaymentService.authorize(intent.ref, gateway_id="pi_sil_3")
    PaymentService.capture(intent.ref, gateway_id="pi_sil_3")

    event = _stripe_event(
        "payment_intent.payment_failed", gateway_id="pi_sil_3", shopman_ref=intent.ref
    )
    payment_stripe.handle_webhook_event(event)

    assert _reconciliation_alerts().exists()


def test_stripe_cancel_sem_baixa_local_alerta_em_vez_de_jurar_sucesso():
    """A cobrança morreu no Stripe e o intent capturado ficou de pé no Payman."""
    intent = _intent(method="card", gateway="stripe", gateway_id="pi_sil_4")
    PaymentService.authorize(intent.ref, gateway_id="pi_sil_4")
    PaymentService.capture(intent.ref, gateway_id="pi_sil_4")

    with patch.object(payment_stripe, "_get_stripe", return_value=MagicMock()):
        result = payment_stripe.cancel(intent.ref)

    assert result.success is True  # o lado do gateway realmente cancelou
    assert _reconciliation_alerts().exists()


def test_stripe_cancel_de_intent_ja_cancelado_nao_alerta():
    """Retry idempotente não é divergência."""
    intent = _intent(method="card", gateway="stripe", gateway_id="pi_sil_5")
    PaymentService.cancel(intent.ref, reason="teste")

    with patch.object(payment_stripe, "_get_stripe", return_value=MagicMock()):
        payment_stripe.cancel(intent.ref)

    assert not _reconciliation_alerts().exists()


# ══════════════════════════════════════════════════════════════
# Efí — o `success=True` sobre falha
# ══════════════════════════════════════════════════════════════


_EFI_CONCLUIDA = {"status": "CONCLUIDA", "valor": {"original": "12.00"}}


def test_efi_capture_com_registro_local_falhando_nao_diz_sucesso():
    """⚠️ O pior dos 94 sites: Pix pago na Efí, nada no livro, ``success=True``.

    A afirmação de sucesso era sobre um registro que não existia. Agora a
    função falha FECHADA e o alerta nasce — o dinheiro entrou, e é preciso
    conciliar antes de qualquer nova cobrança.
    """
    intent = _intent(method="pix", gateway="efi", gateway_id="txid_sil_1")

    with (
        patch.object(payment_efi, "_request", return_value=_EFI_CONCLUIDA),
        patch.object(
            PaymentService,
            "reconcile_gateway_status",
            side_effect=PaymentError(code="reconciliation_capture_drift", message="deriva"),
        ),
    ):
        result = payment_efi.capture(intent.ref)

    assert result.success is False
    assert result.error_code == "reconciliation_failed"
    assert "Concilie" in result.message
    alert = _reconciliation_alerts().get()
    assert alert.severity == "critical"
    assert "efi" in alert.message


def test_efi_capture_bem_sucedida_tem_lastro_no_payman():
    """A outra metade da mesma promessa: quando diz sucesso, o livro registrou.

    Prova de que o ``authorize`` removido daqui não fazia falta — o
    ``reconcile_gateway_status`` do Core já leva o intent de ``pending`` a
    ``captured`` e já anuncia a autorização.
    """
    intent = _intent(method="pix", gateway="efi", gateway_id="txid_sil_2")

    with patch.object(payment_efi, "_request", return_value=_EFI_CONCLUIDA):
        result = payment_efi.capture(intent.ref)

    assert result.success is True
    assert result.amount_q == 1200
    intent.refresh_from_db()
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert PaymentTransaction.objects.filter(
        intent=intent, type=PaymentTransaction.Type.CAPTURE
    ).exists()
    assert not _reconciliation_alerts().exists()


def test_efi_cancel_sem_baixa_local_alerta():
    intent = _intent(method="pix", gateway="efi", gateway_id="txid_sil_3")
    PaymentService.authorize(intent.ref, gateway_id="txid_sil_3")
    PaymentService.capture(intent.ref, gateway_id="txid_sil_3")

    with patch.object(payment_efi, "_request", return_value={}):
        result = payment_efi.cancel(intent.ref)

    assert result.success is True
    assert _reconciliation_alerts().exists()


def test_efi_cancel_de_intent_ja_cancelado_nao_alerta():
    intent = _intent(method="pix", gateway="efi", gateway_id="txid_sil_4")
    PaymentService.cancel(intent.ref, reason="teste")

    with patch.object(payment_efi, "_request", return_value={}):
        payment_efi.cancel(intent.ref)

    assert not _reconciliation_alerts().exists()


# ══════════════════════════════════════════════════════════════
# Faxina de cobranças antigas — QR velho pagável é dinheiro em dobro
# ══════════════════════════════════════════════════════════════


def test_faxina_de_cobrancas_antigas_que_falha_inteira_grita():
    """O laço interno já gritava por intent; o ``except`` de fora ficou mudo."""
    from shopman.shop.services import payment as payment_service

    order = MagicMock()
    order.ref = "ORD-FAXINA"
    with (
        patch.object(PaymentService, "get_by_order", side_effect=RuntimeError("sem banco")),
        _assert_warns("shopman.shop.services.payment", "cancel_stale_intents_failed"),
    ):
        assert payment_service.cancel_stale_intents(order, keep_intent_ref="PAY-1") == 0


def test_faxina_do_pix_confirmado_que_falha_grita():
    from shopman.shop.services import pix_confirmation

    order = MagicMock()
    order.ref = "ORD-PIX-FAXINA"
    with (
        patch(
            "shopman.shop.services.payment.cancel_stale_intents",
            side_effect=RuntimeError("sem banco"),
        ),
        _assert_warns("shopman.shop.services.pix_confirmation", "cancel_stale_intents_failed"),
    ):
        pix_confirmation._cancel_stale_intents(order, keep_intent_ref="PAY-1")


def test_cobranca_viva_ilegivel_grita_em_vez_de_abrir_a_segunda():
    """Vazio por falha de leitura vira segunda cobrança do mesmo pedido."""
    from shopman.shop.services import payment as payment_service

    order = MagicMock()
    order.ref = "ORD-REUSO"
    with (
        patch.object(PaymentService, "get_by_order", side_effect=RuntimeError("sem banco")),
        _assert_warns("shopman.shop.services.payment", "existing_intent_lookup_failed"),
    ):
        assert payment_service._existing_active_intent(order, method="pix", amount_q=1200) is None


# ══════════════════════════════════════════════════════════════
# 🧾 Nota fiscal
# ══════════════════════════════════════════════════════════════


def test_doczip_corrompido_nao_volta_como_xml_ilegivel():
    """gzip de verdade que não infla é corrupção: some do silêncio, vira aviso."""
    broken = base64.b64encode(gzip.compress(b"<nfeProc/>")[:-4] + b"\x00\x00\x00\x00").decode()

    with _assert_warns("shopman.shop.adapters.purchase_invoice_nfe", "doczip_inflate_failed"):
        assert purchase_invoice_nfe._decode_doc_zip(broken) == ""


def test_doczip_sem_compressao_continua_sendo_lido():
    """A SEFAZ manda o XML cru em base64 às vezes; isso nunca foi falha."""
    plain = base64.b64encode(b"<nfeProc>ok</nfeProc>").decode()

    assert purchase_invoice_nfe._decode_doc_zip(plain) == "<nfeProc>ok</nfeProc>"


def test_doczip_comprimido_continua_sendo_lido():
    packed = base64.b64encode(gzip.compress(b"<nfeProc>ok</nfeProc>")).decode()

    assert purchase_invoice_nfe._decode_doc_zip(packed) == "<nfeProc>ok</nfeProc>"


# ══════════════════════════════════════════════════════════════
# 🧾 Venda sem nota, no balcão
# ══════════════════════════════════════════════════════════════


class _Counter:
    """Um balcão mínimo: canal PDV, um item, um operador com turno aberto."""

    def __init__(self):
        from shopman.offerman.models import Product

        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={
                "confirmation": {"mode": "immediate"},
                "payment": {"method": "cash", "timing": "external"},
                "stock": {"check_on_commit": False},
            },
        )
        Product.objects.create(
            sku="PAO", name="Pão", base_price_q=1200, is_published=True, is_sellable=True
        )
        self.operator = get_user_model().objects.create_user(username="marina", password="x")
        self.shift = cash.open_shift(operator=self.operator, float_q=10000)

    def close(self, *, client_request_id: str):
        from shopman.shop.services import pos as pos_service

        return pos_service.close_sale(
            channel_ref="pdv",
            payload={
                "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
                "customer_name": "Cliente",
                "payment_method": "cash",
                "client_request_id": client_request_id,
                "cash_shift_id": self.shift.pk,
            },
            actor=f"pos:{self.operator.username}",
            operator_username=self.operator.username,
        )


@override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    }
)
def test_venda_sem_nota_no_balcao_abre_alerta_no_gestor():
    """A venda fecha (o cliente já foi embora), mas a nota que não saiu grita.

    Era ``logger.warning`` e mais nada — e a tela do PDV diz "Fiscal pendente"
    também quando está tudo certo, então ninguém tinha como notar.
    """
    counter = _Counter()

    with patch(
        "shopman.shop.services.fiscal.emit", side_effect=RuntimeError("provedor fora do ar")
    ):
        result = counter.close(client_request_id="sil-fiscal-1")

    assert result.order_ref
    alert = OperatorAlert.objects.get(type="integration_failed")
    assert result.order_ref in alert.message
    assert "Nota fiscal" in alert.message


# ── utilitários de log ────────────────────────────────────────


class _assert_warns:
    """``assertLogs`` de WARNING em forma de context manager de pytest."""

    def __init__(self, logger_name: str, needle: str):
        self.logger_name = logger_name
        self.needle = needle
        self._handler: logging.Handler | None = None
        self._records: list[logging.LogRecord] = []

    def __enter__(self):
        self._records = []
        records = self._records

        class _Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        self._handler = _Collector(level=logging.WARNING)
        self._logger = logging.getLogger(self.logger_name)
        self._previous_level = self._logger.level
        self._logger.setLevel(logging.WARNING)
        self._logger.addHandler(self._handler)
        return self

    def __exit__(self, exc_type, exc, tb):
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._previous_level)
        if exc_type is not None:
            return False
        emitted = [r for r in self._records if r.levelno >= logging.WARNING]
        assert emitted, f"nada foi registrado em WARNING no logger {self.logger_name}"
        assert any(self.needle in r.getMessage() for r in emitted), (
            f"nenhum WARNING contendo {self.needle!r}: "
            f"{[r.getMessage() for r in emitted]}"
        )
        return False
