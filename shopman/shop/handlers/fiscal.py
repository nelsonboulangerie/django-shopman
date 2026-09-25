"""
Fiscal handlers — emissão e cancelamento de NFC-e.

Tratamento de erro de produção:
- Rejeição da SEFAZ por GTIN → reemite na hora com "SEM GTIN", marca o
  produto e alerta (``_reemit_without_rejected_gtin``): o GTIN nunca trava a venda.
- Falha de transporte/5xx/processando → ``DirectiveTransientError`` (retry com
  backoff); rejeição/payload/4xx → ``DirectiveTerminalError`` (visível na fila).
- Retry NUNCA re-POSTa cego: consulta ``query_status`` primeiro. Um timeout
  pós-emissão deixa a nota autorizada na SEFAZ com o mesmo ``ref`` — o re-POST
  responderia 422 ("referência já utilizada") para sempre e a nota ficaria órfã.
"""

from __future__ import annotations

import logging
import re

from shopman.fiscalman.contracts import FiscalBackend, FiscalDocumentResult
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE

logger = logging.getLogger(__name__)

#: O aviso ao cliente da loja online de que a NFC-e dele está autorizada.
FISCAL_NOTE_READY_TEMPLATE = "fiscal_note_ready"

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
# A SEFAZ recusou o GTIN e a nota foi reemitida "SEM GTIN" (rótulo em
# ``backstage.models.alerts.OperatorAlert.TYPE_CHOICES``).
GTIN_REJECTED_ALERT_TYPE = "fiscal_gtin_rejected"


def _is_transient(error_code: str | None) -> bool:
    code = str(error_code or "")
    return code in _TRANSIENT_CODES or code.startswith(_TRANSIENT_PREFIXES)


# A SEFAZ aponta o item pelo número dele na nota: "[nItem:3]" / "[nItem: 3]".
_ITEM_NUMBER = re.compile(r"nItem\s*:\s*(\d+)", re.IGNORECASE)


def _is_delivery_fee_line(item: dict) -> bool:
    """A taxa de entrega não é item da nota (vira frete) e não conta no nItem.

    Mesma regra do adapter (``fiscal_focusnfe._is_delivery_fee_item``), que
    numera só a mercadoria. Se as duas divergirem, o item apontado não leva
    GTIN e a reemissão cai no caminho seguro: tira o GTIN de todos.
    """
    meta = item.get("meta") or {}
    return item.get("sku") == "__DELIVERY_FEE__" or meta.get("type") == "delivery_fee"


def _items_with_rejected_gtin(items: list[dict], sefaz_message: str) -> list[dict]:
    """Itens cujo GTIN sai da nota: o apontado pela SEFAZ, ou todos que o levam."""
    with_gtin = [item for item in items if str(item.get("gtin") or "").strip()]
    match = _ITEM_NUMBER.search(sefaz_message)
    if match:
        merchandise = [item for item in items if not _is_delivery_fee_line(item)]
        number = int(match.group(1))
        if 1 <= number <= len(merchandise):
            pointed = merchandise[number - 1]
            if str(pointed.get("gtin") or "").strip():
                return [pointed]
    return with_gtin


class NFCeEmitHandler:
    """Directive handler para emissão de NFC-e. Topic: fiscal.emit_nfce"""

    topic = FISCAL_EMIT_NFCE
    # A transient fiscal outage gets a bounded recovery window (~64 minutes),
    # always querying the same reference before another emission attempt.
    retry_delays_seconds = (30, 60, 120, 300, 600, 900, 1800)

    def on_terminal_failure(self, *, message: Directive) -> None:
        from shopman.shop.services.observability import create_operator_alert

        order_ref = str((message.payload or {}).get("order_ref") or "")
        if self._undone_before_any_emission(order_ref, message):
            return
        create_operator_alert(
            type="fiscal_emit_failed", severity="critical", order_ref=order_ref,
            message=f"NFC-e do pedido {order_ref} sem emissão confirmada após {message.attempts} tentativa(s). Confira a fila fiscal e consulte a referência antes de reenviar.",
            dedupe_key=f"fiscal_emit_failed:{order_ref}",
        )

    @staticmethod
    def _undone_before_any_emission(order_ref: str, message: Directive) -> bool:
        """Venda desfeita antes da 1ª tentativa: a recusa É o desfecho certo.

        Na 1ª execução (``attempts == 1``) nenhum POST aconteceu, então não há
        nota que possa ter ficado autorizada sem chave — não há o que o
        operador conferir. Alertar ``fiscal_emit_failed`` aqui só ensinava o
        balcão a ignorar o alerta que importa. Com ``attempts > 1`` (retry, ou
        emissão reaberta por ``fiscal.cancel`` para consulta) o alerta fica:
        pode haver nota órfã.
        """
        from shopman.orderman.models import Order

        if int(message.attempts or 0) > 1:
            return False
        row = Order.objects.filter(ref=order_ref).values_list("status", "data").first()
        if row is None:
            return False
        status, data = row
        return (
            status in (Order.Status.CANCELLED, Order.Status.RETURNED)
            and not (data or {}).get("nfce_access_key")
        )

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
            # A nota já existe (emitida por outro caminho, adotada num retry, ou
            # por uma directive irmã). Sair daqui ANTES do e-mail fazia a
            # promessa do balcão morrer junto com a guarda de idempotência: nota
            # autorizada, cliente esperando o anexo, ninguém enviando. O envio
            # tem a própria idempotência (``nfce_email_sent_at``).
            self._send_receipt_email(order)
            return

        # attempts > 1 (não > 0): o dispatcher incrementa attempts para 1 ANTES
        # de chamar o handler, então a PRIMEIRA execução já chega com attempts=1;
        # só a partir da 2ª (re-claim após transiente) é retry de verdade — e
        # só então pode existir um POST anterior com a resposta perdida.
        is_retry = int(getattr(message, "attempts", 0) or 0) > 1

        if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED):
            # Venda desfeita enquanto a emissão estava em retry: o POST anterior
            # pode ter AUTORIZADO a nota (timeout pós-emissão). Recusar sem
            # consultar deixava nota válida na SEFAZ sem chave no pedido e sem
            # cancelamento — ``fiscal.cancel`` não age sem a chave. Nunca POSTa
            # para pedido desfeito: só consulta, adota e cancela.
            if is_retry and self._adopt_for_cancellation(order, order_ref):
                return
            raise DirectiveTerminalError(
                f"Pedido {order_ref} está {order.status}: não emitir NFC-e."
            )

        # Retry: o POST anterior pode ter emitido e a resposta se perdido
        # (timeout/worker morto). Consultar antes de re-POSTar com o mesmo ref.
        if is_retry:
            if self._adopt_existing(order, order_ref):
                return

        result = self._emit(order_ref, payload)
        result = self._reemit_without_rejected_gtin(message, order_ref, payload, result)

        if result.success:
            self._record(order, result)
            self._after_authorized(order)
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
        if result.error_code == "focus_nfe_invalid_payload":
            from shopman.shop.services.observability import record_integration_failure

            record_integration_failure(
                provider="fiscal", operation="emit_nfce",
                detail=f"Pedido {order_ref}: {result.error_message}",
                context={"order_ref": order_ref, "error_code": result.error_code},
            )
        raise DirectiveTerminalError(f"NFC-e emission failed: {result.error_message}")

    def _emit(self, order_ref: str, payload: dict) -> FiscalDocumentResult:
        return self.backend.emit(
            reference=order_ref, items=payload["items"],
            customer=payload.get("customer"), payment=payload["payment"],
            additional_info=payload.get("additional_info"),
            delivery=payload.get("delivery"),
            intermediary=payload.get("intermediary"),
        )

    def _reemit_without_rejected_gtin(
        self, message: Directive, order_ref: str, payload: dict, result: FiscalDocumentResult,
    ) -> FiscalDocumentResult:
        """SEFAZ recusou o GTIN → a mesma nota sai de novo com "SEM GTIN".

        Decisão do dono (24/09/2026): o GTIN nunca trava a venda. Para cada
        rejeição de GTIN (``services.fiscal.SEFAZ_GTIN_REJECTION_CODES``):

        1. o item culpado sai "SEM GTIN" — o apontado por ``[nItem:N]`` na
           mensagem da SEFAZ; sem apontamento (ou apontando item que não levava
           GTIN), TODOS os itens que levavam GTIN;
        2. o produto ganha ``metadata['gtin_nf_rejected']`` — dali em diante
           ``_trusted_gtin`` o manda "SEM GTIN" em toda nota, até alguém
           conferir a embalagem e limpar a marca;
        3. o payload da directive é regravado, para que um retry transiente
           depois daqui também saia "SEM GTIN";
        4. a nota é reenviada com a MESMA referência: nota rejeitada não fica
           na SEFAZ, e a Focus aceita o reenvio da ref em ``erro_autorizacao``
           (só recusa ref já autorizada — ``already_processed``).

        Repete enquanto a SEFAZ acusar outro item (ela aponta um por vez);
        termina porque cada volta tira ao menos um GTIN. Rejeição que não é de
        GTIN, ou GTIN que já não está na nota (889, por exemplo), volta ao
        caminho de sempre. Ao fim, um alerta diz qual produto e qual código.
        """
        from shopman.shop.services import fiscal as fiscal_service

        stripped: list[dict] = []
        while not result.success:
            code = fiscal_service.sefaz_gtin_rejection_code(result.error_code)
            if not code:
                break
            items = payload.get("items") or []
            targets = _items_with_rejected_gtin(items, result.error_message or "")
            if not targets:
                break
            for item in targets:
                sku = str(item.get("sku") or "")
                gtin = str(item.get("gtin") or "")
                item["gtin"] = ""
                fiscal_service.mark_gtin_rejected(
                    sku, gtin=gtin, code=code, reason=result.error_message or "", order_ref=order_ref,
                )
                stripped.append({
                    "sku": sku, "name": str(item.get("name") or sku), "gtin": gtin,
                    "code": code, "reason": result.error_message or "",
                })
            Directive.objects.filter(pk=message.pk).update(payload=payload)
            message.payload = payload
            logger.warning(
                "fiscal.emit: GTIN recusado pela SEFAZ (%s), reenviando SEM GTIN order=%s skus=%s",
                code, order_ref, [item.get("sku") for item in targets],
            )
            result = self._emit(order_ref, payload)

        if stripped:
            self._alert_gtin_rejected(order_ref, stripped, result)
        return result

    @staticmethod
    def _alert_gtin_rejected(order_ref: str, stripped: list[dict], result: FiscalDocumentResult) -> None:
        from shopman.shop.services.observability import create_operator_alert

        products = "; ".join(
            f"{row['name']} (SKU {row['sku']}, GTIN {row['gtin']}): rejeição {row['code']}"
            for row in stripped
        )
        outcome = (
            "A nota foi reemitida SEM GTIN e autorizada."
            if result.success
            else "A nota foi reenviada SEM GTIN e ainda não foi autorizada — veja a fila fiscal."
        )
        create_operator_alert(
            type=GTIN_REJECTED_ALERT_TYPE,
            severity="warning",
            message=(
                f"A SEFAZ recusou o GTIN na NFC-e do pedido {order_ref}: {products}. {outcome} "
                "Esses produtos saem SEM GTIN nas próximas notas até alguém conferir o código "
                "na embalagem e limpar a marca gtin_nf_rejected do produto."
            ),
            order_ref=order_ref,
            dedupe_key=f"{GTIN_REJECTED_ALERT_TYPE}:{order_ref}",
        )

    def _adopt_existing(self, order, order_ref: str) -> bool:
        """Consulta o Focus pelo ref; se autorizada, adota a nota existente."""
        query = getattr(self.backend, "query_status", None)
        if query is None:
            return False
        status = query(reference=order_ref)
        if status.success and status.access_key:
            self._record(order, status)
            self._after_authorized(order)
            logger.info("fiscal.emit: nota existente adotada via consulta order=%s", order_ref)
            return True
        return False

    def _adopt_for_cancellation(self, order, order_ref: str) -> bool:
        """Pedido desfeito com POST anterior: a nota existe? Então adote e cancele.

        ``True`` quando adotou (a directive de emissão termina ``done`` e a de
        cancelamento fica na fila). Nota ainda em processamento ou Focus fora é
        transiente: consultar de novo, porque recusar agora é o que deixava a
        nota órfã. Sem nota, ``False`` — a recusa terminal segue no chamador.
        """
        query = getattr(self.backend, "query_status", None)
        if query is None:
            return False
        status = query(reference=order_ref)
        if status.success and status.access_key:
            self._record(order, status)
            self._after_authorized(order)
            logger.warning(
                "fiscal.emit: nota autorizada de pedido desfeito adotada para cancelamento order=%s",
                order_ref,
            )
            return True
        if _is_transient(status.error_code):
            raise DirectiveTransientError(
                f"Pedido {order_ref} desfeito com NFC-e sem resposta ({status.error_code}): "
                "consultar de novo antes de encerrar."
            )
        return False

    def _after_authorized(self, order) -> None:
        """Nota gravada: pedido vivo recebe o e-mail; pedido desfeito, o cancelamento.

        A venda pode ter sido desfeita com o POST em voo — ``_on_cancelled``
        chamou ``fiscal.cancel`` quando ainda não havia chave, e ninguém mais
        pediria o cancelamento desta nota. O status vem da linha, não do
        objeto lido no início do ``handle``.
        """
        from shopman.orderman.models import Order

        order.status = Order.objects.values_list("status", flat=True).get(pk=order.pk)
        if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED):
            from shopman.shop.services import fiscal

            fiscal.cancel(order)
            return
        self._send_receipt_email(order)
        self._notify_online_customer(order)

    @staticmethod
    def _notify_online_customer(order) -> None:
        """Pedido da loja online: a nota vai ao cliente pelo aviso de pedido.

        Decisão do dono (25/09/2026): a loja online não imprime nem pede e-mail;
        a nota chega DIGITAL — na página do pedido e numa mensagem com o link da
        DANFE, pela cadeia de avisos do pedido (WhatsApp primeiro). Só o canal da
        loja: o balcão entrega a nota no papel ou no e-mail que o operador
        anotou, e o marketplace não é contato nosso. A mensagem é a da nota
        AUTORIZADA, e não um pedaço do aviso de despacho: na entrega a nota nasce
        no despacho, depois de o aviso já ter saído.

        Best-effort, como o e-mail: a nota já existe, e o aviso não pode derrubar
        a directive de emissão. ``notification.send`` é deduplicado por pedido e
        evento, então o retry da directive não repete a mensagem.
        """
        from django.conf import settings

        storefront_channel = getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")
        if (order.channel_ref or "") != storefront_channel:
            return
        try:
            from shopman.shop.services import notification

            notification.send(order, FISCAL_NOTE_READY_TEMPLATE)
        except Exception:
            logger.warning("fiscal.notify: aviso da nota não agendado order=%s", order.ref, exc_info=True)

    def _send_receipt_email(self, order) -> None:
        """Nota autorizada + cliente pediu e-mail → o Focus envia (DANFE + XML).

        Best-effort de propósito: a nota JÁ EXISTE — falha de e-mail não pode
        derrubar a directive de emissão nem provocar retry que re-POSTaria o
        ref. O reenvio manual mora nas "Últimas vendas" do PDV. Idempotente por
        ``nfce_email_sent_at`` (o carimbo só entra quando o Focus aceitou).
        """
        send = getattr(self.backend, "send_email", None)
        if send is None:
            return
        data = order.data or {}
        if data.get("nfce_email_sent_at"):
            return
        receipt = data.get("receipt") or {}
        wants_email = receipt.get("mode") == "email" or "email" in (receipt.get("channels") or [])
        email = str(receipt.get("email") or (data.get("customer") or {}).get("email") or "").strip()
        if not (wants_email and email):
            return
        try:
            ok, message = send(reference=order.ref, emails=[email])
        except Exception as exc:
            logger.warning("fiscal.email: envio falhou order=%s", order.ref, exc_info=True)
            self._alert_email_failed(order, email, str(exc) or exc.__class__.__name__)
            return
        if not ok:
            logger.warning("fiscal.email: Focus recusou order=%s: %s", order.ref, message)
            self._alert_email_failed(order, email, message)
            return
        from django.db import transaction
        from django.utils import timezone
        from shopman.orderman.models import Order

        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            fresh = dict(locked.data or {})
            fresh["nfce_email_sent_at"] = timezone.now().isoformat()
            locked.data = fresh
            locked.save(update_fields=["data", "updated_at"])
        order.data = fresh
        logger.info("fiscal.email: enviado via Focus order=%s", order.ref)

    @staticmethod
    def _alert_email_failed(order, email: str, reason: str) -> None:
        """O cliente pediu a nota por e-mail e o envio não saiu — o balcão precisa saber.

        A nota está autorizada e o retry não pode ser automático (re-POSTar o ref
        traria 422), então o único caminho é humano: reenviar pelas "Últimas
        vendas" do PDV. Um ``logger.warning`` não chega a ninguém no balcão.
        """
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="fiscal_email_failed",
            severity="warning",
            message=(
                f"A NFC-e do pedido {order.ref} foi autorizada, mas o envio para "
                f"{email} FALHOU ({reason}). O cliente pediu a nota por e-mail e não "
                "recebeu — reenviar pelas Últimas vendas do PDV."
            ),
            order_ref=order.ref,
            dedupe_key=f"fiscal_email_failed:{order.ref}",
        )

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

        # A nota nasce no despacho da entrega e a DANFE vai na sacola: o
        # Gestor precisa saber AGORA, não no próximo poll.
        from shopman.shop.handlers._sse_emitters import emit_fiscal_update

        emit_fiscal_update(locked)


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
