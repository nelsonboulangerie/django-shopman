"""
Fiscal (NFC-e) service.

ASYNC — creates Directives for later processing.
Smart no-op when fiscal_pool is empty (no backend configured).
"""

from __future__ import annotations

import logging

from shopman.shop import directives
from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE
from shopman.shop.fiscal import fiscal_pool

logger = logging.getLogger(__name__)


def _default_emission_decision(order) -> bool:
    """Fallback quando não há resolver configurado: emite se o operador optou por emitir
    (``order.data['fiscal']['issue_document']``)."""
    return bool(((order.data or {}).get("fiscal") or {}).get("issue_document"))


def emission_resolver(order) -> bool:
    """Decide SE a NFC-e deve ser emitida para este pedido.

    Delega a resolver(es) Python plugáveis (``settings.SHOPMAN_FISCAL_EMISSION_RESOLVER``,
    caminho pontilhado para ``callable(order) -> bool``). Centraliza a regra de negócio
    (acima de X, certos canais, com CPF na nota, forma de pagamento, ambiente…) sem tocar
    no fluxo. AUSENTE (ou com erro) → fallback padrão (opt-in do operador).

    **Vários resolvers**: separe por vírgula → combinados por OR (emite se QUALQUER um
    disser sim), ex.: ``"...on_request_or_tax_id,...card_payment"``. Para AND/NOT ou
    lógica composta, use os combinadores (``any_of``/``all_of``/``not_``) num resolver
    próprio. Exemplos prontos em ``shopman.shop.fiscal_resolvers``.
    """
    from django.conf import settings

    raw = getattr(settings, "SHOPMAN_FISCAL_EMISSION_RESOLVER", "") or ""
    paths = [p.strip() for p in str(raw).split(",") if p.strip()]
    if not paths:
        return _default_emission_decision(order)
    try:
        from django.utils.module_loading import import_string

        resolvers = [import_string(p) for p in paths]
        return any(bool(r(order)) for r in resolvers)  # múltiplos = OR
    except Exception:
        # Resolver quebrado NÃO deve travar o pedido — cai no fallback e registra.
        logger.warning("fiscal.emission_resolver: %s falhou; usando fallback", raw, exc_info=True)
        return _default_emission_decision(order)


def emit(order) -> None:
    """
    Schedule NFC-e emission for the order.

    Smart no-op if no fiscal backend is configured.
    Creates a Directive with topic FISCAL_EMIT_NFCE.

    ASYNC — retry-safe.
    """
    if not fiscal_pool.get_backend():
        return

    data = order.data or {}
    if data.get("nfce_access_key"):
        return

    if not emission_resolver(order):
        _alert_receipt_promised_without_emission(order, data)
        return

    payment = dict(data.get("payment", {}) or {})
    payment.setdefault("amount_q", order.total_q)

    if _payment_below_total(payment, order):
        _alert_payment_mismatch(order, payment)
        return

    payload = build_emission_payload(order)
    created = directives.create_deduped(
        FISCAL_EMIT_NFCE,
        payload=payload,
        dedupe_key=f"nfce:{order.ref}",
    )
    if created is not None:
        logger.info("fiscal.emit: queued for order %s", order.ref)


def build_emission_payload(order) -> dict:
    """Snapshot canônico tanto da primeira emissão quanto do reprocessamento."""
    data = order.data or {}
    payment = dict(data.get("payment") or {})
    payment.setdefault("amount_q", order.total_q)
    if _payment_below_total(payment, order):
        raise ValueError("Pagamento fiscal abaixo do total do pedido. Corrija antes de reprocessar.")
    delivery = None
    if data.get("fulfillment_type") == "delivery":
        delivery = {"address": dict(data.get("delivery_address_structured") or {})}
    payload = {"order_ref": order.ref}
    if order.channel_ref:
        payload["channel_ref"] = order.channel_ref
    payload.update(items=_build_fiscal_items(order), payment=payment, customer=_fiscal_customer(data), delivery=delivery)
    return payload


def _declared_payment_q(payment: dict) -> int:
    """Total declarado no pagamento, do jeito que o adapter fiscal soma.

    Espelha ``fiscal_focusnfe._payment_total_q``: numa venda mista, quem manda é
    a soma dos ``tenders`` (o documento diz a verdade sobre o mix); fora dela, o
    ``amount_q``.
    """
    tenders = payment.get("tenders") or []
    if tenders:
        return sum(
            max(0, int(t.get("amount_q") or 0)) for t in tenders if isinstance(t, dict)
        )
    return max(0, int(payment.get("amount_q") or 0))


def _payment_below_total(payment: dict, order) -> bool:
    """O pagamento gravado ficou ABAIXO do total do pedido?

    **Invariante de canal: quem escreve ``order.data['payment']`` escreve o valor
    FINAL.** O adapter deriva ``valor_desconto = produtos + frete − pagamento``,
    então um ``payment`` defasado (edição pós-pagamento que escape do
    ``_reconcile_order_payment_to_total`` do PDV) não vira erro: vira um
    **desconto que não houve** dentro de um XML válido, subdeclarando a venda.

    Só o lado de baixo é guardado aqui. Pagamento ACIMA do total gera
    ``valor_total > valor_produtos`` sem desconto, e a própria SEFAZ recusa —
    falha ruidosa não precisa de guarda nossa.
    """
    return 0 < _declared_payment_q(payment) < int(order.total_q or 0)


def _requested_receipt_channels(data: dict) -> list[str]:
    """Os canais de documento que o balcão pediu NESTA venda."""
    receipt = data.get("receipt") or {}
    channels = receipt.get("channels") or []
    if not isinstance(channels, (list, tuple, set)):
        return []
    return [c for c in (str(ch or "").strip() for ch in channels) if c]


def _alert_receipt_promised_without_emission(order, data: dict) -> None:
    """Prometeu-se o documento no balcão e a regra recusou a nota → grite.

    ``receipt.channels`` só é escrito quando o operador marcou "Impressa?" ou
    "Enviar por e-mail" — ou seja, alguém prometeu papel/anexo ao cliente. Nem
    DANFE nem XML existem sem NFC-e autorizada, então a recusa aqui significa que
    a promessa não vai ser cumprida. Morrer num ``return`` mudo é exatamente como
    o bug chegou até o balcão: o operador só descobre pela reclamação do cliente.

    Sem canal pedido não há promessa — a não-emissão é a regra funcionando, e
    alertar seria ruído em toda venda que não emite.
    """
    channels = _requested_receipt_channels(data)
    if not channels:
        return

    from shopman.shop.services.observability import create_operator_alert

    labels = {"print": "impressa", "email": "por e-mail"}
    pedido = ", ".join(labels.get(c.lower(), c) for c in channels)
    logger.error(
        "fiscal.emit: documento pedido (%s) em %s e a regra recusou — nada será emitido",
        pedido, order.ref,
    )
    create_operator_alert(
        type="fiscal_receipt_promised",
        severity="critical",
        message=(
            f"O pedido {order.ref} pediu a nota {pedido} e a regra de emissão "
            "RECUSOU: nenhuma NFC-e foi emitida, então não haverá DANFE nem XML "
            "para entregar. Emita a nota manualmente ou avise o cliente."
        ),
        order_ref=order.ref,
        dedupe_key=f"fiscal_receipt_promised:{order.ref}",
    )


def _alert_payment_mismatch(order, payment: dict) -> None:
    from shopman.shop.services.observability import create_operator_alert

    declared_q = _declared_payment_q(payment)
    logger.error(
        "fiscal.emit: pagamento (%s) abaixo do total (%s) em %s — NFC-e não emitida",
        declared_q, order.total_q, order.ref,
    )
    create_operator_alert(
        type="fiscal_payment_mismatch",
        severity="critical",
        message=(
            f"NFC-e do pedido {order.ref} NÃO foi emitida: o pagamento gravado "
            f"(R$ {declared_q / 100:.2f}) está abaixo do total do pedido "
            f"(R$ {int(order.total_q or 0) / 100:.2f}). Emitir assim colocaria no "
            "documento um desconto que não houve. Acerte o pagamento do pedido e "
            "emita de novo."
        ),
        order_ref=order.ref,
        dedupe_key=f"fiscal_payment_mismatch:{order.ref}",
    )


def cancel(order) -> None:
    """
    Schedule NFC-e cancellation for the order.

    Smart no-op if no fiscal backend is configured or NFC-e was never emitted.
    Creates a Directive with topic FISCAL_CANCEL_NFCE.

    ASYNC — retry-safe.
    """
    if not fiscal_pool.get_backend():
        return

    if not (order.data or {}).get("nfce_access_key"):
        return

    if (order.data or {}).get("nfce_cancelled"):
        return

    directives.queue(
        FISCAL_CANCEL_NFCE, order,
        reason=(order.data or {}).get("cancellation_reason", "cancelled"),
    )

    logger.info("fiscal.cancel: queued for order %s", order.ref)


def _fiscal_customer(data: dict) -> dict:
    """O consumidor DA NOTA: identidade do cadastro, documento do PEDIDO.

    O adapter identifica o consumidor por ``tax_id``/``cpf``/``cnpj`` do dict —
    e esses campos só podem carregar o que foi PEDIDO nesta venda
    (``fiscal.tax_id``), nunca o documento do CRM. Sem esta separação, cliente
    identificado com CPF no cadastro saía identificado em toda nota.
    """
    customer = dict(data.get("customer") or {})
    requested = str((data.get("fiscal") or {}).get("tax_id") or "").strip()
    for key in ("tax_id", "cpf", "cnpj"):
        customer.pop(key, None)
    if requested:
        customer["tax_id"] = requested
    return customer


def emission_expected(order) -> bool:
    """Esta venda vai ter NFC-e?

    O balcão precisa oferecer a DANFE, e não pode perguntar isso ao toggle do
    operador: o ``emission_resolver`` também emite por forma de pagamento, e
    nota que ninguém pediu continua sendo nota que o cliente pode exigir
    impressa.

    Nem pode perguntar à Directive: quando a venda fecha, o pedido ainda está em
    ``new``. A emissão só acontece na conclusão, e a nota não existe no instante
    da tela de confirmação. O que existe já no fechamento é a *regra* e os dados
    que ela lê (forma de pagamento, CPF, pedido do operador) — então a pergunta
    honesta é "vai haver nota?", respondida pelo mesmo resolver que decide, sem
    cópia da regra no front.
    """
    return bool(fiscal_pool.get_backend()) and emission_resolver(order)


# ── Estado da NFC-e de um pedido ─────────────────────────────────────────
#
# A nota nasce em TRÊS pontos, e nenhuma tela pode adivinhar qual deles vale:
# no fechamento da venda para quem não exige captura (``pos.close_sale``), na
# captura do pix/link (``lifecycle._on_paid``) e na conclusão como rede
# (``lifecycle._on_completed``). "Fiscal na conclusão" era a tela chutando o
# terceiro ponto para um pedido que emite no segundo. O estado sai daqui, com
# um vocabulário só, para o PDV, as últimas vendas e a pill do Gestor.

FISCAL_STATE_NOT_EXPECTED = "not_expected"
FISCAL_STATE_QUEUED = "queued"
FISCAL_STATE_AWAITING_PAYMENT = "awaiting_payment"
FISCAL_STATE_AUTHORIZED = "authorized"
FISCAL_STATE_FAILED = "failed"
FISCAL_STATES = (
    FISCAL_STATE_NOT_EXPECTED,
    FISCAL_STATE_QUEUED,
    FISCAL_STATE_AWAITING_PAYMENT,
    FISCAL_STATE_AUTHORIZED,
    FISCAL_STATE_FAILED,
)

#: Directive viva ou concluída: houve tentativa de emissão, e a configuração de
#: hoje não apaga esse fato (o backend pode ter saído da env depois).
_DIRECTIVE_ATTEMPTED = frozenset({"queued", "running", "done"})

EMIT_FAILED_ALERT_TYPE = "fiscal_emit_failed"


def latest_emit_directive_status(order_ref: str) -> str:
    """Status da Directive ``FISCAL_EMIT_NFCE`` mais recente deste pedido, ou ``""``."""
    from shopman.orderman.models import Directive

    directive = (
        Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order_ref)
        .order_by("-created_at", "-pk")
        .values_list("status", flat=True)
        .first()
    )
    return str(directive or "")


def emit_failed_alert_open(order_ref: str) -> bool:
    """Há alerta ``fiscal_emit_failed`` ABERTO para este pedido?

    Cobre a falha que morreu antes de virar Directive (o fechamento do PDV que
    não conseguiu enfileirar) e a falha terminal do worker — as duas gritam
    pelo mesmo tipo, com ``Dedupe: fiscal_emit_failed:{ref}`` no corpo.
    """
    from django.utils import timezone

    from shopman.shop.adapters import alert as alert_adapter

    return alert_adapter.recent_exists(
        EMIT_FAILED_ALERT_TYPE,
        timezone.now(),
        message_contains=f"{EMIT_FAILED_ALERT_TYPE}:{order_ref}",
        order_ref=order_ref,
    )


def fiscal_state(order, *, directive_status: str | None = None, emit_failed_alert: bool | None = None) -> str:
    """Em que pé está a NFC-e deste pedido — um de :data:`FISCAL_STATES`.

    - ``authorized``: ``order.data["nfce_access_key"]`` existe. É FATO, e vale
      antes de qualquer regra.
    - ``failed``: a Directive de emissão mais recente morreu (``failed``) ou há
      alerta ``fiscal_emit_failed`` aberto para o pedido.
    - ``queued``: há Directive viva/concluída sem chave ainda — ou a emissão é
      esperada, o dinheiro não segura, e a nota só está esperando a vez (no
      fechamento, ou na conclusão para quem paga na porta).
    - ``not_expected``: :func:`emission_expected` disse não.
    - ``awaiting_payment``: esperada, sem chave, e a cobrança é digital
      antecipada ainda não capturada — a nota nasce na captura
      (``lifecycle._on_paid``), não na conclusão.

    A evidência de tentativa (Directive/alerta) vem ANTES da regra: mudar o
    resolver ou tirar o backend da env não apaga uma nota que já tentou sair.

    ``directive_status``/``emit_failed_alert`` existem para o painel do Gestor
    ler em lote (uma query por quadro, não uma por card); sozinho, o serviço
    pergunta ao banco.
    """
    from shopman.shop.services.payment_gate import payment_is_captured, requires_captured_payment

    data = order.data or {}
    if data.get("nfce_access_key"):
        return FISCAL_STATE_AUTHORIZED

    if directive_status is None:
        directive_status = latest_emit_directive_status(order.ref)
    if directive_status == "failed":
        return FISCAL_STATE_FAILED
    if emit_failed_alert is None:
        emit_failed_alert = emit_failed_alert_open(order.ref)
    if emit_failed_alert:
        return FISCAL_STATE_FAILED
    if directive_status in _DIRECTIVE_ATTEMPTED:
        return FISCAL_STATE_QUEUED

    if not emission_expected(order):
        return FISCAL_STATE_NOT_EXPECTED
    if requires_captured_payment(order) and not payment_is_captured(order):
        return FISCAL_STATE_AWAITING_PAYMENT
    return FISCAL_STATE_QUEUED


#: Resolvers com os quais "pedir papel já pede a nota" é verdade.
_RECEIPT_REQUEST_RESOLVERS = frozenset({
    "shopman.shop.fiscal_resolvers.on_requested_receipt",
    "shopman.shop.fiscal_resolvers.always",
})


def receipt_request_emits() -> bool:
    """Pedir o comprovante (papel ou e-mail) faz a NFC-e sair?

    Só é verdade quando ``SHOPMAN_FISCAL_EMISSION_RESOLVER`` carrega o resolver
    de comprovante (``on_requested_receipt``) — ou ``always``. A env do
    deployment sobrescreve o default do código, então a frase do balcão
    ("imprime sozinha assim que autorizar") tem que perguntar aqui, nunca ao
    default.
    """
    from django.conf import settings

    raw = getattr(settings, "SHOPMAN_FISCAL_EMISSION_RESOLVER", "") or ""
    paths = {p.strip() for p in str(raw).split(",") if p.strip()}
    return bool(paths & _RECEIPT_REQUEST_RESOLVERS)


HANDOFF_WITHOUT_NFCE_ALERT_TYPE = "fiscal_handoff_without_nfce"

#: Transições em que a mercadoria SAI da casa: a sacola com o entregador ou a
#: mão do cliente no balcão. ``PREPARING`` fica de fora — nada sai ali.
_HANDOFF_STATUSES = frozenset({"dispatched", "completed"})


def alert_handoff_without_nfce(order, *, target_status: str) -> None:
    """A mercadoria vai sair sem NFC-e autorizada: GRITA, não barra.

    Nenhum portão de expedição conferia ``nfce_access_key`` — um pedido podia
    ser despachado ou concluído com a nota na fila ou com a emissão morta, e
    ninguém ficava sabendo. Barrar a saída é decisão do dono (a nota do COD só
    nasce na conclusão, por desenho); avisar não é. Um alerta por pedido.

    Nunca levanta: a transição já é a operação de verdade, e o aviso dela não
    pode derrubá-la.
    """
    target = str(target_status or "").strip().lower()
    if target not in _HANDOFF_STATUSES:
        return
    try:
        state = fiscal_state(order)
    except Exception:
        logger.warning("fiscal.handoff_state_failed order=%s", getattr(order, "ref", "?"), exc_info=True)
        return
    if state not in {FISCAL_STATE_QUEUED, FISCAL_STATE_FAILED}:
        return

    from shopman.shop.services.observability import create_operator_alert

    verbo = "despachado" if target == "dispatched" else "concluído"
    logger.warning(
        "fiscal.handoff_without_nfce order=%s target=%s fiscal_state=%s", order.ref, target, state,
    )
    create_operator_alert(
        type=HANDOFF_WITHOUT_NFCE_ALERT_TYPE,
        severity="warning",
        message=(
            f"Pedido {order.ref} saiu sem NFC-e autorizada: {verbo} com a nota "
            + ("na fila." if state == FISCAL_STATE_QUEUED else "com falha de emissão.")
            + " Confira a fila fiscal."
        ),
        order_ref=order.ref,
        dedupe_key=f"{HANDOFF_WITHOUT_NFCE_ALERT_TYPE}:{order.ref}",
        fiscal_state=state,
        target_status=target,
    )


def _build_fiscal_items(order) -> list[dict]:
    """Build item list for fiscal emission from order items.

    Fiscal codes are resolved by Fiscalman from each product's classification
    (``Product.metadata['fiscal']`` → profile + NCM/CEST → CFOP/CSOSN/origem/
    PIS/COFINS). NFC-e is intrastate, so ``interstate=False``. A per-line
    override in ``item.meta['fiscal']`` still wins (rare).
    """
    from shopman.fiscalman.classification import from_metadata, resolve_fiscal_item

    items = []
    products_by_sku = _products_by_sku([item.sku for item in order.items.all()])
    for item in order.items.all():
        product = products_by_sku.get(item.sku)
        metadata = dict(getattr(product, "metadata", None) or {})
        fiscal = resolve_fiscal_item(from_metadata(metadata))
        override = (item.meta or {}).get("fiscal")
        if override:
            fiscal = {**fiscal, **dict(override)}
        items.append({
            "sku": item.sku,
            "name": item.name,
            "qty": str(item.qty.normalize()) if hasattr(item.qty, "normalize") else float(item.qty),
            "unit": getattr(product, "unit", "") or fiscal.get("unit") or "UN",
            "unit_price_q": item.unit_price_q,
            "total_q": item.line_total_q,
            "meta": dict(item.meta or {}),
            "fiscal": fiscal,
        })
    return items


def _products_by_sku(skus: list[str]) -> dict[str, object]:
    """Produtos por SKU para montar o payload fiscal. A falha de leitura SOBE.

    Engolir a exceção aqui (``except Exception`` → ``{}``) compunha três decisões
    razoáveis num modo de falha péssimo: um soluço de banco fazia TODOS os itens
    perderem o metadado fiscal; o adapter, correto, recusava item sem NCM; e o
    handler classificava essa recusa como **terminal** — nota morta na fila,
    sem retry, com um diagnóstico ("produto sem NCM") que mentia sobre a causa
    ("o SELECT falhou").

    São dois fatos diferentes e cada um vai para o seu lado: **NCM ausente no
    produto** é verdade terminal (o adapter recusa em
    ``fiscal_focusnfe._map_item``, e o pedido precisa de gente); **catálogo
    ilegível** é transiente, e quem re-tenta transiente é quem chamou, não este
    módulo. Como o payload é montado no fechamento do pedido (``fiscal.emit``
    dentro do ``on_commit`` do lifecycle), deixar subir também garante que
    nenhuma directive nasça com um retrato falso do catálogo.
    """
    if not skus:
        return {}
    from shopman.offerman.models import Product

    return {
        product.sku: product
        for product in Product.objects.filter(sku__in=set(skus)).only("sku", "unit", "metadata")
    }
