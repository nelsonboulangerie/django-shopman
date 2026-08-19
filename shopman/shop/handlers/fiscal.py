"""
Fiscal handlers — emissão e cancelamento de NFC-e.

Tratamento de erro de produção:
- Falha de transporte/5xx/processando → ``DirectiveTransientError`` (retry com
  backoff); rejeição/payload/4xx → ``DirectiveTerminalError`` (visível na fila).
- Retry NUNCA re-POSTa cego: consulta ``query_status`` primeiro. Um timeout
  pós-emissão deixa a nota autorizada na SEFAZ com o mesmo ``ref`` — o re-POST
  responderia 422 ("referência já utilizada") para sempre e a nota ficaria órfã.
"""

from __future__ import annotations

import logging

from shopman.fiscalman.contracts import FiscalBackend, FiscalDocumentResult
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE

logger = logging.getLogger(__name__)

# Códigos que retry pode curar: transporte fora do ar, 5xx, rate limit e
# "processando_autorizacao" (async da SEFAZ). Qualquer 4xx/payload é terminal.
_TRANSIENT_PREFIXES = ("focus_nfe_http_5",)
_TRANSIENT_CODES = {
    "focus_nfe_http_error",
    "focus_nfe_http_429",
    "focus_nfe_http_408",
    "focus_nfe_processing",
}
_REFERENCE_CONFLICT_CODES = {"focus_nfe_http_422"}


def _is_transient(error_code: str | None) -> bool:
    code = str(error_code or "")
    return code in _TRANSIENT_CODES or code.startswith(_TRANSIENT_PREFIXES)


class NFCeEmitHandler:
    """Directive handler para emissão de NFC-e. Topic: fiscal.emit_nfce"""

    topic = FISCAL_EMIT_NFCE

    def __init__(self, backend: FiscalBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError("Order not found") from exc

        if order.data.get("nfce_access_key"):
            return

        if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED):
            raise DirectiveTerminalError(
                f"Pedido {order_ref} está {order.status}: não emitir NFC-e."
            )

        # Retry: o POST anterior pode ter emitido e a resposta se perdido
        # (timeout/worker morto). Consultar antes de re-POSTar com o mesmo ref.
        # attempts > 1 (não > 0): o dispatcher incrementa attempts para 1 ANTES
        # de chamar o handler, então a PRIMEIRA execução já chega com attempts=1;
        # só a partir da 2ª (re-claim após transiente) é retry de verdade.
        if int(getattr(message, "attempts", 0) or 0) > 1:
            if self._adopt_existing(order, order_ref):
                return

        result = self.backend.emit(
            reference=order_ref, items=payload["items"],
            customer=payload.get("customer"), payment=payload["payment"],
            additional_info=payload.get("additional_info"),
            delivery=payload.get("delivery"),
        )

        if result.success:
            self._record(order, result)
            return

        if result.error_code in _REFERENCE_CONFLICT_CODES:
            # "Referência já utilizada": a nota EXISTE no Focus — adotar.
            if self._adopt_existing(order, order_ref):
                return
            raise DirectiveTerminalError(
                f"NFC-e emission failed: ref em conflito e consulta não autorizada "
                f"({result.error_message})"
            )

        if _is_transient(result.error_code):
            raise DirectiveTransientError(
                f"NFC-e emission transient ({result.error_code}): {result.error_message}"
            )
        raise DirectiveTerminalError(f"NFC-e emission failed: {result.error_message}")

    def _adopt_existing(self, order, order_ref: str) -> bool:
        """Consulta o Focus pelo ref; se autorizada, adota a nota existente."""
        query = getattr(self.backend, "query_status", None)
        if query is None:
            return False
        status = query(reference=order_ref)
        if status.success and status.access_key:
            self._record(order, status)
            logger.info("fiscal.emit: nota existente adotada via consulta order=%s", order_ref)
            return True
        return False

    @staticmethod
    def _record(order, result: FiscalDocumentResult) -> None:
        """Grava a nota em ``order.data`` relendo a linha SOB LOCK.

        ``order.data`` é um JSON inteiro com muitos donos (pagamento, PDV,
        lifecycle) e este handler é assíncrono: gravar o dicionário que veio da
        leitura do início do ``handle`` é last-write-wins sobre tudo que os
        outros escreveram no meio do caminho. O dispatcher não protege disto —
        o claim dele é da **directive**, não do pedido
        (``orderman/dispatch.py::_process_directive``, ``UPDATE ... WHERE
        status='queued'``); nenhum lock de Order é tomado durante o handle.

        Perder chave aqui é caro de um jeito específico: sumindo o
        ``nfce_access_key`` sob uma gravação de payment, a nota fica autorizada
        na SEFAZ sem registro local, o dedupe deixa de ver a nota e só o
        ``query_status`` do retry a reencontraria — rede por acidente.

        O mesmo padrão dos outros escritores de ``order.data``
        (``services/pix_confirmation.py``, ``services/operator_orders.py``,
        ``handlers/returns.py``): reler ``select_for_update`` dentro do
        ``atomic`` e escrever a partir do valor fresco.
        """
        from django.db import transaction
        from shopman.orderman.models import Order

        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            data = dict(locked.data or {})
            data["nfce_access_key"] = result.access_key
            data["nfce_number"] = result.document_number
            data["nfce_series"] = result.document_series
            data["nfce_protocol"] = result.protocol_number
            data["nfce_xml_url"] = result.xml_url
            data["nfce_danfe_url"] = result.danfe_url
            data["nfce_qrcode_url"] = result.qrcode_url
            data["nfce_status"] = result.status
            locked.data = data
            locked.save(update_fields=["data", "updated_at"])

        # O objeto do chamador segue em uso (guarda de idempotência, logs).
        order.data = data


class NFCeCancelHandler:
    """Directive handler para cancelamento de NFC-e. Topic: fiscal.cancel_nfce"""

    topic = FISCAL_CANCEL_NFCE

    def __init__(self, backend: FiscalBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        reason = payload["reason"]

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError("Order not found") from exc

        if order.data.get("nfce_cancelled"):
            return

        result = self.backend.cancel(reference=order_ref, reason=reason)

        if result.success:
            order.data["nfce_cancelled"] = True
            order.data["nfce_cancellation_protocol"] = result.protocol_number
            order.save(update_fields=["data", "updated_at"])
            return

        if _is_transient(result.error_code):
            raise DirectiveTransientError(
                f"NFC-e cancellation transient ({result.error_code}): {result.error_message}"
            )

        # Nota válida em pé para venda cancelada é passivo fiscal — o operador
        # PRECISA saber (fora da janela da SEFAZ o caminho é outro documento).
        self._alert_cancel_failed(order, result)
        raise DirectiveTerminalError(f"NFC-e cancellation failed: {result.error_message}")

    @staticmethod
    def _alert_cancel_failed(order, result) -> None:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="fiscal_cancel_failed",
            severity="critical",
            message=(
                f"Cancelamento da NFC-e do pedido {order.ref} FALHOU "
                f"({result.error_message}). A nota continua válida na SEFAZ — "
                "resolver com o contador (cancelamento fora da janela exige outro instrumento)."
            ),
            order_ref=order.ref,
            dedupe_key=f"fiscal_cancel_failed:{order.ref}",
        )


__all__ = ["NFCeEmitHandler", "NFCeCancelHandler"]
