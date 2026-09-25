"""iFood Order Module event polling loop (WP-2).

Verified live (2026-06-30):

- Poll: ``GET /order/v1.0/events:polling`` → ``200`` with an events array, or
  ``204`` when there is nothing to process.
- Acknowledge: ``POST /order/v1.0/events/acknowledgment`` with body
  ``[{"id": "<eventId>"}, ...]`` → ``202``. An empty body is rejected ``400``.

Each event is lightweight (``id``, ``code`` / ``fullCode``, ``orderId``). This
service turns a ``PLACED`` event into a real ``Order`` by fetching the full
order (:mod:`shopman.shop.services.ifood_orders`) and handing the canonical
payload to :func:`shopman.shop.services.ifood_ingest.ingest`.

Robustness contract
-------------------

- Dedupe is durable, via :mod:`shopman.shop.services.webhook_idempotency`
  (scope ``webhook:ifood``, one claim per event id) — the same event never
  ingests twice, even across worker restarts.
- An event is **acknowledged only after it is handled** (ingested, deduped, or
  an ignorable code). A processing failure leaves the event un-acked so iFood
  re-delivers it — the same at-least-once guarantee the webhook path has.

O que "ignorable" quer dizer, desde 19/09/2026
----------------------------------------------

Até aqui, TODO código sem processador era ``ignored`` e entrava no lote de
acknowledge: dizíamos ao iFood "tratamos" para qualquer coisa que não
soubéssemos tratar. O ``ORDER_PATCHED`` — cliente altera itens depois do
``CONFIRMED`` — caía nesse ramo, e o pedido local seguia com os itens
originais, divergindo o que a cozinha prepara, o estoque, a cobrança e a nota.

Agora há três destinos, e nenhum deles é silêncio:

- **tratado** — tem processador (``PLC``, ``CFM``, ``DSP``, ``CAN``, ``CON``,
  handshake e ``ORDER_PATCHED``);
- **inerte** (``_INERT_CODES``) — ACK calado, mas por DECISÃO escrita e com
  motivo ao lado de cada código;
- **qualquer outro** — ACK (não ackar faria o iFood reentregar em laço) + log de
  ``warning`` + alerta ``ifood_event_unhandled`` ao operador. Um código novo do
  marketplace aparece antes de virar prejuízo, em vez de depois.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings

from shopman.shop.services import ifood_http, ifood_ingest, ifood_orders, webhook_idempotency

logger = logging.getLogger(__name__)

_IDEMPOTENCY_SCOPE = "webhook:ifood"
# Event codes that create a new order. iFood sends both a short ``code`` (PLC)
# and a ``fullCode`` (PLACED); we accept either.
_PLACED_CODES = {"PLC", "PLACED"}
# Cancelamento originado no iFood (cliente desistiu no app / iFood cancelou):
# refletir no Order local para o Gestor nao tratar pedido ja cancelado pelo iFood.
_CANCELLATION_CODES = {"CAN", "CANCELLED"}
_CONCLUSION_CODES = {"CON", "CONCLUDED"}
_CONFIRMATION_CODES = {"CFM", "CONFIRMED"}
_DISPATCH_CODES = {"DSP", "DISPATCHED"}
_HANDSHAKE_CODES = {"HSD", "HANDSHAKE_DISPUTE", "HSS", "HANDSHAKE_SETTLEMENT"}
# Cliente alterou o pedido DEPOIS do CONFIRMED. Só `ORDER_PATCHED`, e é
# deliberado: na referência oficial de eventos este é um dos poucos códigos cujo
# `code` e `fullCode` são a MESMA string — a tabela "Referência rápida" lista
# `ORDER_PATCHED` e os três exemplos trazem `"code": "ORDER_PATCHED"`. Não há
# sigla de três letras documentada, e inventar uma ("PTC") seria adivinhar. Se
# uma sigla aparecer no vivo, ela cai no ramo de código não tratado logo abaixo,
# que grita — em vez de ser engolida como era até 19/09/2026.
_PATCH_CODES = {"ORDER_PATCHED"}
# Códigos documentados que esta casa decidiu não tratar, COM motivo. Não é
# silêncio: é decisão escrita, e o ACK calado é a resposta certa para eles.
_INERT_CODES = {
    # Eco das nossas próprias chamadas. A tabela oficial diz "Ação necessária:
    # Nenhuma" para os quatro.
    "SEPARATION_STARTED", "PREPARATION_STARTED", "SEPARATION_ENDED",
    "PREPARATION_ENDED", "READY_TO_PICKUP",
    # Rastreio do entregador do iFood. A loja não repassa rastreio ao cliente
    # (é o app deles que mostra), então nenhum destes vira trabalho aqui.
    "ASSIGN_DRIVER", "GOING_TO_ORIGIN", "ARRIVED_AT_ORIGIN", "COLLECTED",
    "ARRIVED_AT_DESTINATION", "DELIVERY_GROUP_ASSIGNED",
    # Sugestão de horário para pedido agendado, de loja com "Preparo
    # Inteligente". A casa começa o preparo pelo `preparationStartDateTime` do
    # próprio pedido, que a documentação chama de mais restritivo.
    "RECOMMENDED_PREPARATION_START",
    # Pedido de cancelamento em trânsito: quem fecha é o CAN, que é tratado.
    "CANCELLATION_REQUESTED",
}
_ACK_BATCH = 100  # iFood acknowledges in batches.


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def poll() -> list[dict]:
    """Poll the iFood event stream. Returns the events list (``[]`` on 204/idle)."""
    merchant_id = str(_cfg().get("merchant_id") or "").strip()
    extra = {"x-polling-merchants": merchant_id} if merchant_id else None

    resp = ifood_http.request(
        "GET", "/order/v1.0/events:polling", label="poll", extra_headers=extra, idempotent=True
    )
    if resp is None:
        # Sem credencial, transporte caído ou recusa de edge que sobreviveu às
        # retentativas — `ifood_http` já registrou a forense.
        return []

    # Never broaden merchant scope on a rejected filter: the same app may
    # authorize other stores, including production stores during testing.
    if resp.status_code == 400 and merchant_id:
        logger.warning(
            "ifood_events.poll: iFood rejeitou x-polling-merchants (400) — "
            "IFOOD_MERCHANT_ID provavelmente errado. Filtro preservado; "
            "confira o Merchant ID no portal iFood."
        )
        return []

    if resp.status_code == 204:
        return []
    if resp.status_code != 200:
        return []
    try:
        events = resp.json()
    except ValueError:
        logger.warning("ifood_events.poll: response was not JSON")
        return []
    return events if isinstance(events, list) else []


def acknowledge(event_ids: list[str]) -> bool:
    """Acknowledge processed events so iFood stops re-delivering them."""
    event_ids = [e for e in event_ids if e]
    if not event_ids:
        return True
    ok = True
    for start in range(0, len(event_ids), _ACK_BATCH):
        batch = [{"id": eid} for eid in event_ids[start:start + _ACK_BATCH]]
        # Idempotente por id de evento: reconhecer o mesmo id duas vezes é
        # inócuo, então vale retentar também `5xx` e transporte. O risco aqui é
        # o inverso — um ACK que não sai faz o iFood reentregar o evento, e a
        # reentrega já é tratada pelo dedupe durável.
        resp = ifood_http.request(
            "POST",
            "/order/v1.0/events/acknowledgment",
            label="acknowledge",
            extra_headers={"Content-Type": "application/json"},
            json=batch,
            idempotent=True,
        )
        if resp is None or resp.status_code not in (200, 202):
            ok = False
    return ok


def process_events(events: list[dict]) -> dict:
    """Handle a batch of events; acknowledge the ones that were handled.

    Returns a small summary dict: ``{polled, ingested, deduped, ignored, failed, acked}``.
    """
    ingested = deduped = ignored = failed = 0
    handled_ids: list[str] = []
    merchant_id = str(_cfg().get("merchant_id") or "").strip()

    # A API entrega fora de ordem; a doc manda ordenar por ``createdAt``. Sem isso
    # um CON pode ser processado antes do DSP que o precede.
    for event in sorted(events, key=lambda e: str(e.get("createdAt") or "")):
        event_id = str(event.get("id") or "").strip()
        code = str(event.get("fullCode") or event.get("code") or "").upper()
        order_id = str(event.get("orderId") or "").strip()

        # Check before handling even ignorable codes: acknowledging an event
        # from another merchant would consume it for that store's integration.
        # Legacy event fixtures/providers can omit merchantId; retain support
        # for those while rejecting explicit mismatches.
        event_merchant_id = str(event.get("merchantId") or "").strip()
        if merchant_id and event_merchant_id and event_merchant_id != merchant_id:
            logger.warning("ifood_events: event %s belongs to another merchant; leaving unacknowledged", event_id)
            failed += 1
            continue

        if not event_id:
            logger.warning("ifood_events: event without id, skipping: %s", event)
            failed += 1
            continue

        # Remote state changes reconcile only after the order exists.
        if code in (
            _CANCELLATION_CODES | _CONCLUSION_CODES | _CONFIRMATION_CODES
            | _DISPATCH_CODES | _HANDSHAKE_CODES | _PATCH_CODES
        ):
            if code in _PATCH_CODES:
                outcome = _process_patch(event, event_id, order_id)
            elif code in _HANDSHAKE_CODES:
                outcome = _process_handshake(event, settlement=code in {"HSS", "HANDSHAKE_SETTLEMENT"})
            elif code in _CANCELLATION_CODES:
                outcome = _process_cancellation(event_id, order_id)
            elif code in _CONCLUSION_CODES:
                outcome = _process_conclusion(event_id, order_id)
            else:
                outcome = _process_remote_progress(event_id, order_id, dispatch=code in _DISPATCH_CODES)
            if outcome == "ingested":
                ingested += 1
                handled_ids.append(event_id)
            elif outcome == "deduped":
                deduped += 1
                handled_ids.append(event_id)
            else:  # failed — sem ack, iFood reentrega
                failed += 1
            continue

        # Código sem processador. Continua sendo ackado — não ackar faria o
        # iFood reentregar para sempre, e a reentrega infinita esconde tanto
        # quanto o silêncio. O que muda é que ele deixa de ser INVISÍVEL: só os
        # códigos de `_INERT_CODES` passam calados, porque para eles existe
        # decisão escrita. Qualquer outro vira aviso ao operador.
        if code not in _PLACED_CODES:
            if code not in _INERT_CODES:
                _alert_unhandled_event(code, order_id)
            ignored += 1
            handled_ids.append(event_id)
            continue

        outcome = _process_placed(event_id, order_id)
        if outcome == "ingested":
            ingested += 1
            handled_ids.append(event_id)
        elif outcome == "deduped":
            deduped += 1
            handled_ids.append(event_id)
        else:  # "failed" — leave un-acked for redelivery
            failed += 1

    acked = acknowledge(handled_ids) if handled_ids else True
    summary = {
        "polled": len(events),
        "ingested": ingested,
        "deduped": deduped,
        "ignored": ignored,
        "failed": failed,
        "acked": acked,
    }
    logger.info("ifood_events.process_events: %s", summary)
    return summary


def _process_placed(event_id: str, order_id: str) -> str:
    """Ingest one PLACED event. Returns 'ingested' | 'deduped' | 'failed'."""
    if not order_id:
        logger.warning("ifood_events: PLACED event %s without orderId", event_id)
        return "failed"

    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE,
        f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )
    if claim.replayed:
        return "deduped"  # já ingerido antes (done) — seguro ackar
    if claim.in_progress:
        # Outra instância (ex.: rolling deploy) está processando ESTE evento agora.
        # NÃO ackar: se ela concluir, o próximo poll vê replayed e acka; se ela
        # morrer, o iFood reentrega. Ackar aqui perderia o pedido caso a outra
        # instância falhasse no meio.
        return "failed"

    # Order already ingested via another event/webhook for the same orderId.
    from shopman.orderman.models import Order

    if Order.objects.filter(
        channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, external_ref=order_id
    ).exists():
        webhook_idempotency.mark_done(claim, response_body={"status": "already_processed"})
        return "deduped"

    try:
        order = ifood_orders.fetch_order(order_id)
        payload = ifood_orders.map_order(order)
        created = ifood_ingest.ingest(payload)
    except Exception:
        logger.exception("ifood_events: failed to ingest order %s (event %s)", order_id, event_id)
        webhook_idempotency.mark_failed(claim)
        return "failed"

    webhook_idempotency.mark_done(claim, response_body={"status": "accepted", "order_ref": created.ref})
    return "ingested"


def _alert_unhandled_event(code: str, order_id: str) -> None:
    """Um código do iFood chegou sem processador — o ACK sai, mas não calado."""
    from shopman.shop.services.observability import create_operator_alert

    logger.warning(
        "ifood_events: código %s sem tratamento (pedido %s); reconhecido para não "
        "reentregar em laço, mas NADA foi aplicado ao pedido local",
        code or "(vazio)", order_id or "(sem orderId)",
    )
    create_operator_alert(
        type="ifood_event_unhandled",
        severity="warning",
        message=(
            f"O iFood enviou o evento {code or '(sem código)'} e esta loja não sabe tratá-lo. "
            "O pedido local não mudou. Confira o pedido no portal do iFood antes de continuar."
        ),
        order_ref="",
        dedupe_key=f"ifood_event_unhandled:{code}",
        debounce_minutes=60,
    )


#: Como a documentação nomeia cada alteração, em português de tela. A chave é o
#: ``metadata.changeType``; os três valores são os documentados na referência de
#: eventos (exemplos "Item removido", "Item adicionado" e "Quantidade
#: modificada"). Valor fora desta tabela não vira "desconhecido" calado: cai no
#: texto genérico e o changeType cru vai junto, porque o operador precisa saber
#: o que o iFood disse, não o que nós conseguimos classificar.
_CHANGE_TYPE_LABEL = {
    "DELETE_ITEMS": "itens removidos",
    "ADD_ITEMS": "itens adicionados",
    "UPDATE_ITEMS": "quantidade de itens alterada",
}


def _money_q(value) -> int | None:
    """Reais do iFood → centavos. ``None`` quando o campo não veio.

    Distinguir ausente de zero importa: um total ausente não pode virar
    "R$ 0,00" no aviso que o operador lê.
    """
    if value is None:
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def _describe_patch(metadata: dict) -> str:
    """Uma frase inequívoca sobre o que o cliente mexeu, para o operador."""
    change_type = str(metadata.get("changeType") or "").upper()
    label = _CHANGE_TYPE_LABEL.get(change_type)
    items = metadata.get("items") if isinstance(metadata.get("items"), list) else []
    named = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or "").strip()
        # UPDATE_ITEMS traz oldQuantity/newQuantity; os outros trazem quantity.
        if item.get("newQuantity") is not None or item.get("oldQuantity") is not None:
            named.append(f"{name} (de {item.get('oldQuantity')} para {item.get('newQuantity')})")
        elif item.get("quantity") is not None:
            named.append(f"{name} ({item['quantity']}x)")
        elif name:
            named.append(name)
    detail = "; ".join(n for n in named if n)
    if label is None:
        head = f"alteração do tipo {change_type or '(sem tipo)'}"
    else:
        head = label
    return f"{head}: {detail}" if detail else head


def _brl(value_q: int | None) -> str:
    if value_q is None:
        return "(não informado)"
    return f"R$ {value_q / 100:.2f}".replace(".", ",")


#: Enquanto o pedido está num destes, a mercadoria ainda está na casa e mexer em
#: estoque e cozinha é mexer em coisa que existe. Depois que ele saiu
#: (despachado, entregue) o pão foi junto com o entregador: creditar o estoque de
#: volta inventaria pão que não está na prateleira. O AJUSTE continua valendo —
#: o Gestor, as vias e o B.I. passam a mostrar o que a plataforma vai pagar —,
#: mas o físico não se desfaz por evento.
_GOODS_STILL_IN_THE_HOUSE = frozenset({"new", "accepted", "preparing", "ready"})


def _patch_block_reason(order, *, fiscal_authorized: bool) -> str:
    """Por que este pedido NÃO pode ser reconciliado; ``""`` quando pode.

    Três portas fechadas, cada uma por um motivo diferente:

    - ``test_order`` — pedido de homologação do marketplace. A supressão da #887
      é sobre não fazer a padaria trabalhar por um pedido que não existe, e
      reconciliar é trabalho: mexeria em reserva, em ticket e no que o Gestor
      mostra. O fato continua sendo gravado e logado.
    - ``fiscal_authorized`` — a NFC-e já saiu. Corrigir a nota é decisão fiscal
      (devolução, cancelamento e reemissão, ou outra coisa) e a pergunta está com
      o contador. Reconciliar os itens aqui faria o pedido e a nota divergirem em
      silêncio, que é pior do que a divergência que o operador já foi avisado de
      ter. Mantém-se o comportamento da Etapa 1: marca, avisa e para.
    - ``terminal`` — cancelado, devolvido ou concluído. Não há pedido a ajustar:
      as reservas já foram soltas ou o caixa já fechou em cima do que houve.
    """
    from shopman.orderman.models import Order

    from shopman.shop.services.order_helpers import is_test_order

    if is_test_order(order):
        return "test_order"
    if fiscal_authorized:
        return "fiscal_authorized"
    if order.status in Order.TERMINAL_STATUSES:
        return "terminal"
    return ""


def _process_patch(event: dict, event_id: str, order_id: str) -> str:
    """Reconciliar o pedido que o cliente alterou — e gritar o que mudou.

    O iFood emite ``ORDER_PATCHED`` quando o cliente adiciona, remove ou muda a
    quantidade de itens depois do ``CONFIRMED``. A Etapa 1 (#897) parou de
    mentir: o evento ganhou processador, o fato passou a ser gravado em
    ``order.data["ifood"]["patches"]`` com ``reconciled: False`` e o operador
    passou a ser avisado. Esta é a Etapa 2 — o pedido local passa a refletir a
    alteração.

    **Relê o pedido inteiro, não aplica o delta.** O ``metadata`` do evento traz
    só os itens afetados mais ``oldTotal``/``newTotal``. Delta é frágil contra
    reentrega e evento fora de ordem, que é exatamente o que este módulo já trata
    com cuidado em ``_process_remote_progress`` e ``_process_conclusion``. A
    reconciliação chama ``ifood_orders.fetch_order`` e usa o estado FINAL; assim
    uma reentrega é no-op natural, e duas alterações fora de ordem convergem para
    o mesmo lugar.

    **O ajuste vive ao lado, nunca por cima.** ``Order.total_q`` e
    ``Order.snapshot`` são ``SEALED_FIELDS`` do Core: qualquer ``save()`` que os
    altere levanta ``ImmutabilityError``. O estado novo é gravado em
    ``order.data["adjustment"]``, e quem lê item ou total de pedido lê a
    composição das duas coisas por ``services.order_composition`` — uma leitura
    só, para cozinha, separação, Gestor, vias e B.I. não somarem cada um por
    conta própria e divergirem.

    **Nada de cancelar e recriar.** No iFood, cancelar localmente PEDE ao iFood
    que cancele o pedido do cliente (``STATUS_ACTION`` mapeia
    ``"cancelled" → "requestCancellation"``) — o oposto do que o cliente quis ao
    alterar, e irreversível do lado de lá.

    A releitura acontece FORA da transação: segurar o lock do pedido durante um
    ``GET`` no iFood é convite a prender a linha por segundos. Quando ela falha,
    o caminho não some — cai de volta no comportamento da Etapa 1 (grava o fato,
    avisa alto, dá ACK) em vez de deixar o evento em reentrega infinita.
    """
    if not order_id:
        logger.warning("ifood_events: ORDER_PATCHED %s sem orderId", event_id)
        return "failed"

    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE, f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )
    if claim.replayed:
        return "deduped"
    if claim.in_progress:
        return "failed"

    from django.db import transaction
    from django.utils import timezone
    from shopman.orderman.models import Order

    from shopman.shop.services.order_helpers import is_test_order

    order = Order.objects.filter(
        channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, external_ref=order_id,
    ).first()
    if order is None:
        # Pode chegar antes do PLACED, inclusive no mesmo lote. Sem ACK: a
        # reentrega aplica o registro depois de o pedido existir.
        logger.warning(
            "ifood_events: ORDER_PATCHED para pedido %s ainda inexistente; "
            "deixando sem ACK para reentrega", order_id,
        )
        webhook_idempotency.mark_failed(claim)
        return "failed"

    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    data = order.data or {}
    fiscal_authorized = bool(data.get("nfce_access_key")) and not data.get("nfce_cancelled")
    block = _patch_block_reason(order, fiscal_authorized=fiscal_authorized)

    payload = None
    if not block:
        try:
            payload = ifood_orders.map_order(ifood_orders.fetch_order(order_id))
        except Exception:
            logger.exception(
                "ifood_events: releitura do pedido %s falhou; ORDER_PATCHED %s fica "
                "registrado sem reconciliação", order_id, event_id,
            )
            block = "fetch_failed"

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, external_ref=order_id,
            ).first()
            if order is None:
                webhook_idempotency.mark_failed(claim)
                return "failed"

            patches = list(((order.data or {}).get("ifood") or {}).get("patches") or [])
            if any(str(p.get("event_id")) == event_id for p in patches if isinstance(p, dict)):
                webhook_idempotency.mark_done(claim, response_body={"status": "already_recorded"})
                return "deduped"

            # A decisão de reconciliar foi tomada com o pedido SEM lock, porque
            # a releitura no iFood não pode segurar a linha. Entre as duas
            # leituras o pedido pode ter sido cancelado, ou a nota pode ter
            # saído — refazer a pergunta com o lock na mão é o que impede
            # reconciliar um pedido que deixou de aceitar reconciliação.
            data = order.data or {}
            fiscal_authorized = bool(data.get("nfce_access_key")) and not data.get("nfce_cancelled")
            late_block = _patch_block_reason(order, fiscal_authorized=fiscal_authorized)
            if late_block:
                payload, block = None, late_block

            record = {
                "event_id": event_id,
                "change_type": str(metadata.get("changeType") or ""),
                "items": metadata.get("items") if isinstance(metadata.get("items"), list) else [],
                "old_total_q": _money_q(metadata.get("oldTotal")),
                "new_total_q": _money_q(metadata.get("newTotal")),
                "observed_at": timezone.now().isoformat(),
                "order_status": order.status,
                "local_total_q": order.total_q,
                "fiscal_authorized": fiscal_authorized,
            }
            outcome = None
            if payload is None:
                # Porta fechada (ou releitura falhada): o comportamento da Etapa 1
                # continua sendo a resposta certa — gravar, avisar e parar.
                record["reconciled"] = False
                record["reconciliation"] = f"blocked:{block}"
            else:
                outcome = _apply_patch(order, payload, event_id)
                record["reconciled"] = True
                record["reconciliation"] = outcome

            patches.append(record)
            # Relido DEPOIS de ``_apply_patch``, que gravou o ajuste no mesmo
            # ``data`` — copiar antes apagaria o ajuste ao salvar aqui.
            data = dict(order.data or {})
            data["ifood"] = {**(data.get("ifood") or {}), "patches": patches}
            order.data = data
            order.save(update_fields=["data", "updated_at"])

            _alert_patched(
                order, record, outcome,
                fiscal_authorized=fiscal_authorized,
                block=block,
                suppressed=is_test_order(order),
            )
            webhook_idempotency.mark_done(
                claim,
                response_body={
                    "status": "reconciled" if outcome else "recorded",
                    "order_ref": order.ref,
                },
            )
    except Exception:
        logger.exception(
            "ifood_events: falha ao tratar ORDER_PATCHED do pedido %s (evento %s)", order_id, event_id,
        )
        webhook_idempotency.mark_failed(claim)
        return "failed"
    return "ingested"


def _apply_patch(order, payload: dict, event_id: str) -> dict:
    """Grava o ajuste e traz estoque e cozinha para a lista nova.

    Chamada com o pedido travado, dentro da transação do chamador: se o estoque
    recusar no meio, nada fica meio feito e o evento segue sem ACK para o iFood
    reentregar.
    """
    from shopman.shop.services import kds as kds_service
    from shopman.shop.services import order_composition, stock

    items = ifood_ingest.normalize_items(payload["items"])
    subtotal_q = sum(int(item["line_total_q"]) for item in items)
    # Mesma régua da ingestão: o total que vale é o ``orderAmount`` do iFood
    # (subtotal + entrega + taxas − benefícios), porque é o que a plataforma
    # paga. Sem ele (simulação de dev), o subtotal das linhas.
    total_q = int((payload.get("totals") or {}).get("order_amount_q") or 0) or subtotal_q

    before = order_composition.effective_items(order)
    previous_total_q = order_composition.effective_total_q(order)
    previous_lines = kds_service.order_lines(order)

    adjustment = order_composition.record(
        order, items=items, total_q=total_q, source="ifood:ORDER_PATCHED", event_id=event_id,
    )
    data = dict(order.data or {})
    data[order_composition.KEY] = adjustment
    order.data = data
    order.save(update_fields=["data", "updated_at"])

    difference = order_composition.diff(before, order_composition.effective_items(order))
    outcome = {
        "revision": adjustment["revision"],
        "total_q": total_q,
        "previous_total_q": previous_total_q,
        "diff": difference,
    }
    if order.status in _GOODS_STILL_IN_THE_HOUSE:
        outcome["stock"] = stock.reconcile_to_items(
            order, items=items, reference=f"ifood_patch:{order.ref}",
        )
        outcome["kds"] = kds_service.reconcile_to_lines(order, previous_lines=previous_lines)
    else:
        # A mercadoria já saiu com o entregador. O ajuste vale (é o que o iFood
        # vai pagar), o físico não se desfaz por evento.
        outcome["stock"] = {"skipped": "goods_left"}
        outcome["kds"] = {"skipped": "goods_left"}
    return outcome


_BLOCK_EXPLANATION = {
    "fiscal_authorized": (
        "A NFC-e deste pedido já foi autorizada, então a loja NÃO acompanhou a alteração: "
        "corrigir a nota é decisão fiscal (devolução ou cancelamento) e o sistema não faz isso "
        "sozinho — fale com o contador."
    ),
    "terminal": (
        "O pedido já está encerrado nesta loja, então a alteração NÃO foi aplicada: "
        "confira no portal do iFood o que ficou diferente."
    ),
    "fetch_failed": (
        "Não conseguimos reler o pedido no iFood para aplicar a alteração, então a loja segue "
        "com os itens originais. Confira o pedido no portal do iFood e ajuste à mão."
    ),
}


def _alert_patched(order, record: dict, outcome: dict | None, *, fiscal_authorized: bool,
                   block: str, suppressed: bool) -> None:
    """Diz ao operador o que mudou — e se a loja acompanhou ou não.

    O log sai SEMPRE, inclusive para pedido de teste: quem depura precisa ver o
    evento. O alerta na tela do operador é que é suprimido no pedido de teste —
    a supressão da #887 é sobre não fazer a padaria trabalhar por homologação, e
    um alerta vermelho no Gestor é trabalho.

    Duas mensagens diferentes, porque são dois fatos diferentes. Reconciliado, o
    aviso é ``warning`` e diz o que a loja JÁ fez (a cozinha recebeu, o estoque
    acompanhou) — o operador precisa conferir, não consertar. Bloqueado, é
    ``error`` e diz por que a loja não acompanhou, que é a Etapa 1 continuando a
    valer onde ela ainda é a resposta certa.
    """
    from shopman.shop.services import order_composition
    from shopman.shop.services.observability import create_operator_alert

    description = _describe_patch({
        "changeType": record["change_type"], "items": record["items"],
    })
    if outcome is not None and not order_composition.is_empty(outcome["diff"]):
        description = order_composition.describe(outcome["diff"])

    logger.warning(
        "ifood_events: pedido %s ALTERADO pelo cliente no iFood (%s). Total do iFood: %s → %s; "
        "total local: %s. NFC-e autorizada: %s. Reconciliado: %s%s",
        order.ref, description,
        _brl(record["old_total_q"]), _brl(record["new_total_q"]),
        _brl(record["local_total_q"]), "sim" if fiscal_authorized else "não",
        "sim" if outcome else "NÃO", f" ({block})" if block else "",
    )
    if suppressed:
        return

    if outcome is None:
        message = (
            f"O cliente alterou o pedido {order.ref} no iFood depois de confirmado: {description}. "
            f"O total no iFood foi de {_brl(record['old_total_q'])} para {_brl(record['new_total_q'])}; "
            f"o pedido nesta loja continua em {_brl(record['local_total_q'])} e com os itens originais. "
            + _BLOCK_EXPLANATION.get(block, "Confira o pedido no portal do iFood antes de continuar.")
        )
        create_operator_alert(
            type="ifood_order_patched",
            severity="error",
            message=message,
            order_ref=order.ref,
            dedupe_key=f"ifood_order_patched:{order.ref}:{record['event_id']}",
        )
        return

    applied = []
    stock_outcome = outcome.get("stock") or {}
    kds_outcome = outcome.get("kds") or {}
    if stock_outcome.get("skipped") == "goods_left":
        applied.append(
            "o pedido já saiu, então o estoque NÃO foi ajustado — confira o que foi na sacola"
        )
    elif any(stock_outcome.get(key) for key in ("released", "returned", "held", "fulfilled")):
        applied.append("o estoque acompanhou")
    if kds_outcome.get("unfired") or kds_outcome.get("refired"):
        applied.append("a cozinha recebeu a comanda atualizada")
    if stock_outcome.get("gaps"):
        applied.append(
            "FALTOU estoque para o que foi acrescentado — veja o alerta de reserva ao lado"
        )
    tail = f" A loja acompanhou: {'; '.join(applied)}." if applied else ""

    create_operator_alert(
        type="ifood_order_patched",
        severity="warning",
        message=(
            f"O cliente alterou o pedido {order.ref} no iFood depois de confirmado: {description}. "
            f"O pedido nesta loja foi atualizado: de {_brl(outcome['previous_total_q'])} "
            f"para {_brl(outcome['total_q'])}." + tail
        ),
        order_ref=order.ref,
        dedupe_key=f"ifood_order_patched:{order.ref}:{record['event_id']}",
    )


def _process_remote_progress(event_id: str, order_id: str, *, dispatch: bool) -> str:
    """Apply CFM/DSP only along a legal canonical transition.

    CFM authorizes acceptance; DSP records a handoff only after local readiness.
    Neither event manufactures intermediate preparation stages. Persist remote
    evidence before the transition so its callback cannot echo the same fact.
    """
    if not order_id:
        return "failed"
    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE, f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )
    if claim.replayed:
        return "deduped"
    if claim.in_progress:
        return "failed"

    from django.db import transaction
    from shopman.orderman.models import Order

    from shopman.shop.services.order_helpers import get_fulfillment_type

    code = "DSP" if dispatch else "CFM"
    target = Order.Status.DISPATCHED if dispatch else Order.Status.ACCEPTED
    marker = "remote_dispatched" if dispatch else "remote_confirmed"
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, external_ref=order_id,
            ).first()
            if order is None:
                webhook_idempotency.mark_failed(claim)
                return "failed"
            if dispatch and get_fulfillment_type(order) != "delivery":
                # Fato sem transição possível: pedido de retirada não "sai". Gravar
                # e dar ACK — deixar sem ACK só faz o iFood reentregar para sempre.
                logger.warning("ifood_events: DSP for non-delivery order %s; recorded, nothing to apply", order_id)
                _record_remote(order, marker, event_id)
                webhook_idempotency.mark_done(claim, response_body={"status": "recorded", "order_ref": order.ref})
                return "deduped"

            terminal = order.status in Order.TERMINAL_STATUSES
            already_applied = terminal or order.status in (
                {Order.Status.DISPATCHED, Order.Status.DELIVERED}
                if dispatch else {Order.Status.ACCEPTED, Order.Status.PREPARING, Order.Status.READY,
                                  Order.Status.DISPATCHED, Order.Status.DELIVERED}
            )
            expected = Order.Status.READY if dispatch else Order.Status.NEW
            # O fato é gravado ANTES de qualquer transição, para o aviso dela não
            # ecoar ao iFood o que veio dele.
            _record_remote(order, marker, event_id)
            if not already_applied and order.status != expected:
                # ACK é "armazenei", não "apliquei" (doc do polling). O fato fica no
                # pedido e a reconciliação o aplica quando o estado local chegar lá
                # — antes, o evento ficava sem ACK e o iFood usava a fila de
                # reentrega como fila de espera nossa, o que o Firefly pune.
                logger.info(
                    "ifood_events: %s recorded for order %s (status %s); applies when the local order catches up",
                    code, order_id, order.status,
                )
                webhook_idempotency.mark_done(
                    claim, response_body={"status": "recorded_pending", "order_ref": order.ref},
                )
                return "ingested"
            if not already_applied:
                _reconcile_locked(order)
                order.refresh_from_db()
                if order.status == expected:
                    raise ValueError(f"iFood {code} did not reach its local target status")
            webhook_idempotency.mark_done(
                claim, response_body={"status": "already_processed" if already_applied else target, "order_ref": order.ref},
            )
    except Exception:
        logger.exception("ifood_events: failed to reconcile %s for order %s (event %s)", code, order_id, event_id)
        webhook_idempotency.mark_failed(claim)
        return "failed"
    return "deduped" if already_applied else "ingested"


def _process_cancellation(event_id: str, order_id: str) -> str:
    """Reflect an iFood-originated cancellation into our Order.

    Mesma disciplina do PLACED: claim por event id (idempotente), ack só
    quando tratado, sem ack em falha (o iFood reentrega). Usa o serviço
    canônico de cancelamento (grava cancellation_reason/cancelled_by antes
    da transição) com a marca ifood_cancelled para o ifood_status não
    responder requestCancellation de volta para quem já cancelou.
    """
    if not order_id:
        logger.warning("ifood_events: CAN event %s without orderId", event_id)
        return "failed"

    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE,
        f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )
    if claim.replayed:
        return "deduped"
    if claim.in_progress:
        return "failed"

    from shopman.orderman.models import Order

    order = Order.objects.filter(
        channel_ref=ifood_ingest.IFOOD_CHANNEL_REF,
        external_ref=order_id,
    ).first()
    if order is None:
        # CAN can arrive before PLACED, including earlier in the same batch.
        # Release the claim and leave CAN unacknowledged so redelivery applies
        # the cancellation after the order has been materialized.
        webhook_idempotency.mark_failed(claim)
        return "failed"
    if order.status == "cancelled":
        # Legacy versions cancelled locally before sending requestCancellation.
        # CAN still confirms remote ownership, so queued legacy callbacks must
        # be suppressed even when no further local transition is needed.
        if not (order.data or {}).get("ifood_cancelled"):
            order.data = {**(order.data or {}), "ifood_cancelled": True}
            order.save(update_fields=["data", "updated_at"])
        webhook_idempotency.mark_done(claim, response_body={"status": "already_cancelled"})
        return "deduped"

    try:
        from shopman.shop.services import cancellation

        cancelled = cancellation.cancel(
            order,
            reason="Cancelamento confirmado pelo iFood",
            actor="system:ifood",
            extra_data={"ifood_cancelled": True},
        )
        if not cancelled and order.status not in Order.TERMINAL_STATUSES:
            logger.warning(
                "ifood_events: CAN cannot reconcile active order %s (status %s); "
                "leaving unacknowledged for operational review", order_id, order.status,
            )
            webhook_idempotency.mark_failed(claim)
            return "failed"
        outcome = "ingested" if cancelled else "deduped"
    except Exception:
        logger.exception("ifood_events: failed to cancel order %s (event %s)", order_id, event_id)
        webhook_idempotency.mark_failed(claim)
        return "failed"

    webhook_idempotency.mark_done(claim, response_body={"status": "cancelled", "order_ref": order.ref})
    return outcome


def _process_conclusion(event_id: str, order_id: str) -> str:
    """Close an order through its canonical handoff flow, without inventing work.

    CON can precede PLACED or the operator's dispatch. Keep it retryable until
    the local order can conclude legally; never manufacture preparation or
    dispatch transitions (and their outbound iFood callbacks).
    """
    if not order_id:
        return "failed"

    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE,
        f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )
    if claim.replayed:
        return "deduped"
    if claim.in_progress:
        return "failed"

    from django.db import transaction
    from shopman.orderman.models import Order


    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, external_ref=order_id,
            ).first()
            if order is None:
                webhook_idempotency.mark_failed(claim)
                return "failed"
            if order.status in Order.TERMINAL_STATUSES:
                # A later CON must not reopen a cancellation or a return.
                webhook_idempotency.mark_done(claim, response_body={"status": "already_terminal"})
                return "deduped"

            _record_remote(order, "remote_concluded", event_id)
            if not _conclusion_allowed(order):
                # O iFood já encerrou, mas aqui o pedido ainda não chegou à entrega
                # (entrega própria parada em preparo, retirada ainda não pronta).
                # A regra de NÃO pular a custódia do entregador continua de pé; o
                # que muda é o ACK: o fato fica gravado, o card avisa que o iFood
                # concluiu, e a reconciliação fecha quando o pedido chegar lá.
                logger.info(
                    "ifood_events: CON recorded for order %s (status %s); concludes when the local handoff happens",
                    order_id, order.status,
                )
                webhook_idempotency.mark_done(
                    claim, response_body={"status": "recorded_pending", "order_ref": order.ref},
                )
                return "ingested"
            _reconcile_locked(order)
            order.refresh_from_db()
            if order.status != Order.Status.COMPLETED:
                raise ValueError("iFood conclusion did not complete the local order")
            webhook_idempotency.mark_done(claim, response_body={"status": "concluded", "order_ref": order.ref})
    except Exception:
        logger.exception("ifood_events: failed to conclude order %s (event %s)", order_id, event_id)
        webhook_idempotency.mark_failed(claim)
        return "failed"
    return "ingested"


# ── Fatos do iFood × estado local ──────────────────────────────────────────────
# Um evento de status do iFood (CFM, DSP, CON) é FATO sobre o pedido lá. Ele é
# gravado em ``order.data["ifood"]`` e recebe ACK na mesma transação — a doc do
# polling pede ACK "após armazenar", não após aplicar. A aplicação local segue as
# regras de sempre (nunca inventa preparo nem saída, nunca pula a custódia do
# entregador) e acontece em dois momentos: quando o fato chega, se o pedido já
# está no ponto certo, e depois de cada transição local, pelo ``order_changed``.
_RECONCILING = threading.local()


def _record_remote(order, marker: str, event_id: str) -> None:
    """Grava o fato do iFood no pedido, uma vez só (o primeiro evento é a prova)."""
    from django.utils import timezone

    data = dict(order.data or {})
    facts = dict(data.get("ifood") or {})
    if facts.get(marker):
        return
    facts[marker] = {"event_id": event_id, "observed_at": timezone.now().isoformat()}
    data["ifood"] = facts
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def _conclusion_allowed(order) -> bool:
    """Onde o CON pode fechar o pedido: depois da entrega, ou na retirada pronta."""
    from shopman.orderman.models import Order

    from shopman.shop.services.order_helpers import get_fulfillment_type

    fulfillment_type = get_fulfillment_type(order)
    if fulfillment_type == "delivery":
        return order.status in (Order.Status.DISPATCHED, Order.Status.DELIVERED)
    return fulfillment_type == "pickup" and order.status == Order.Status.READY


def _reconcile_locked(order) -> None:
    """Aplica, pelo caminho legal, o que os fatos do iFood já autorizam.

    Chamada com o pedido travado (``select_for_update``). Cada passo é uma das
    transições que o processamento dos eventos sempre fez; o laço só encadeia
    quando um fato destrava o seguinte (DSP leva a "saiu", e aí o CON conclui).
    """
    from django.utils import timezone
    from shopman.orderman.models import Order

    from shopman.shop.services import ifood_cancellation, operator_orders
    from shopman.shop.services.order_helpers import get_fulfillment_type

    for _ in range(4):
        if order.status in Order.TERMINAL_STATUSES:
            return
        facts = (order.data or {}).get("ifood") or {}
        if facts.get("remote_concluded") and _conclusion_allowed(order):
            if ifood_cancellation.is_pending(order):
                # CON confirma a entrega, não o cancelamento. Guarda o pedido
                # original para auditoria e aposenta a trava operacional dele na
                # mesma transação da conclusão.
                data = dict(order.data or {})
                request = dict(data[ifood_cancellation.KEY])
                request.update(
                    state="superseded", resolution="order_concluded",
                    resolved_at=timezone.now().isoformat(), retryable=False,
                )
                data[ifood_cancellation.KEY] = request
                order.data = data
                order.save(update_fields=["data", "updated_at"])
            if get_fulfillment_type(order) == "delivery" and order.status == Order.Status.DISPATCHED:
                operator_orders.confirm_received(order, actor="system:ifood")
                order.refresh_from_db()
            if order.status != Order.Status.COMPLETED:
                operator_orders.advance_order(order, actor="system:ifood")
                order.refresh_from_db()
            return
        if (facts.get("remote_dispatched") and order.status == Order.Status.READY
                and get_fulfillment_type(order) == "delivery"):
            operator_orders.advance_order(order, actor="system:ifood:DSP")
            order.refresh_from_db()
            continue
        if facts.get("remote_confirmed") and order.status == Order.Status.NEW:
            operator_orders.confirm_order(order, actor="system:ifood:CFM")
            order.refresh_from_db()
            continue
        return


def reconcile_remote(order) -> None:
    """Depois de uma transição local, aplica o que o iFood já tinha dito.

    Ex.: o entregador do iFood retirou antes de a cozinha marcar "Pronto" (DSP
    gravado com o pedido em preparo); quando a cozinha marca, o pedido sai e, se
    o CON também já chegou, conclui — sem nenhum aviso ecoar ao iFood.
    """
    if getattr(order, "channel_ref", "") != ifood_ingest.IFOOD_CHANNEL_REF:
        return
    facts = (order.data or {}).get("ifood") or {}
    if not any(facts.get(m) for m in ("remote_confirmed", "remote_dispatched", "remote_concluded")):
        return
    if getattr(_RECONCILING, "active", False):
        return  # as transições da própria reconciliação disparam order_changed

    from django.db import transaction
    from shopman.orderman.models import Order

    _RECONCILING.active = True
    try:
        with transaction.atomic():
            locked = Order.objects.select_for_update().filter(pk=order.pk).first()
            if locked is not None:
                _reconcile_locked(locked)
    except Exception:
        # A transição do operador já aconteceu e não pode ser desfeita por isto;
        # o fato continua gravado e a próxima transição tenta de novo.
        logger.exception("ifood_events: reconcile failed for order %s", getattr(order, "ref", "?"))
    finally:
        _RECONCILING.active = False


def run_once() -> dict:
    """Poll once and process. Used by the management command / cron tick."""
    return process_events(poll())


__all__ = ["poll", "acknowledge", "process_events", "run_once"]


def _process_handshake(event: dict, *, settlement: bool) -> str:
    from django.db import transaction
    from shopman.orderman.models import Order

    from shopman.shop.services import ifood_handshake

    if not event.get("orderId"):
        return "failed"
    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE, f"event:{webhook_idempotency.stable_webhook_key(event['id'])}",
    )
    if claim.replayed:
        return "deduped"
    if claim.in_progress:
        return "failed"
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(channel_ref="ifood", external_ref=event["orderId"])
            changed = ifood_handshake.persist_event(order, event, settlement=settlement)
            webhook_idempotency.mark_done(claim, response_body={"status": "persisted", "order_ref": order.ref})
        return "ingested" if changed else "deduped"
    except Exception:
        logger.exception("ifood_events: handshake persistence failed for event %s", event["id"])
        webhook_idempotency.mark_failed(claim)
        return "failed"
