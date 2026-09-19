"""
Fiscal (NFC-e) service.

ASYNC — creates Directives for later processing.
Smart no-op when fiscal_pool is empty (no backend configured).
"""

from __future__ import annotations

import logging

from shopman.shop import directives, fiscal_intermediary
from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE
from shopman.shop.fiscal import fiscal_pool
from shopman.shop.services.order_helpers import is_test_order

logger = logging.getLogger(__name__)


def _default_emission_decision(order) -> bool:
    """Fallback quando não há resolver configurado (ou ele quebrou): emite quando
    a venda PEDIU a nota — CPF na nota, papel ou e-mail (``on_request_or_tax_id``).
    Um resolver quebrado não pode ser a razão de a promessa do balcão morrer."""
    from shopman.shop.fiscal_resolvers import on_request_or_tax_id

    return bool(on_request_or_tax_id(order))


def _fiscal_backend_is_homologation() -> bool:
    """O backend fiscal declara que emite em homologação (nota sem valor fiscal)?

    Backend que não declara é tratado como PRODUÇÃO: falha fechado. Errar para
    "é produção" custa uma nota de teste que não sai; errar para o outro lado
    custa uma NFC-e de verdade sobre dinheiro que não existe.
    """
    backend = fiscal_pool.get_backend()
    return getattr(backend, "is_homologation", False) is True


def simulated_payment_blocks_emission(order) -> bool:
    """A venda foi paga por simulação e a nota seria de PRODUÇÃO?

    A marca é a mesma régua que tira o pagamento simulado da receita
    (``payment_provenance``): simulador local, Efí homologação, Stripe em chave
    de teste. Em homologação a nota sai — não tem valor fiscal, e é assim que o
    alpha exercita a emissão do Pix simulado. Em produção, nunca.
    """
    from shopman.shop.services.payment_provenance import is_simulated_order_payment

    return is_simulated_order_payment(order) and not _fiscal_backend_is_homologation()


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

    # Pagamento SIMULADO nunca vira nota de verdade — nem com a emissão avulsa do
    # gerente. Vem antes do override de propósito: nota de produção é documento
    # da Receita sobre uma venda que recebeu dinheiro, e aqui nenhum entrou.
    if simulated_payment_blocks_emission(order):
        return False

    # A emissão avulsa autorizada pelo gerente (Últimas vendas do PDV) passa POR
    # CIMA da regra — é exatamente para isso que ela existe. Só um escritor grava
    # a chave (``backstage.services.orders.emit_fiscal_on_demand``), depois do
    # desafio gerencial; nenhuma outra porta a toca.
    if issue_override(order):
        return True

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


# ── Emissão avulsa (a regra da casa disse não; o gerente disse sim) ──────
#
# A regra padrão emite só quando pedem (nota, CPF ou comprovante). O cliente que
# volta ao balcão meia hora depois pedindo a nota não tinha como ser atendido:
# a regra já tinha decidido. A emissão avulsa é a exceção auditada — sempre com
# o desafio gerencial, e com quem autorizou gravado no pedido.

#: Chave em ``Order.data["fiscal"]``. Ver docs/reference/data-schemas.md.
ISSUE_OVERRIDE_KEY = "issue_override"

#: Chave em ``Shop.defaults["pos"]``: quantos dias DEPOIS do dia da venda a
#: emissão avulsa ainda vale. ``0`` (e ausente) = só no MESMO dia de operação.
#: Editada no Admin (Configurações da loja → PDV e alertas).
LATE_EMISSION_DAYS_KEY = "late_fiscal_emission_days"


def late_emission_days() -> int:
    """Dias além do dia da venda em que a emissão avulsa ainda vale (``0`` = mesmo dia).

    A nota sai com a data e a hora da EMISSÃO (``data_emissao`` do adapter é o
    agora), não da venda — quanto mais longe da venda, mais a nota descola dela.
    Por isso o padrão é o mesmo dia, e esticar é decisão da loja, no Admin.
    Valor ilegível cai no padrão seguro (mesmo dia), nunca em "sem limite".
    """
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        pos_cfg = (shop.defaults.get("pos") or {}) if shop and isinstance(shop.defaults, dict) else {}
        raw = pos_cfg.get(LATE_EMISSION_DAYS_KEY)
        return max(0, int(raw)) if raw is not None else 0
    except (TypeError, ValueError):
        logger.warning("fiscal.late_emission_days: valor ilegível em Shop.defaults; usando o mesmo dia")
        return 0


def late_emission_rule_text(days: int) -> str:
    """A regra por extenso, para a recusa dizer o que vale — não só que não vale."""
    if days <= 0:
        return "Só dá para emitir nota de venda do mesmo dia."
    return f"Só dá para emitir nota de venda de até {days} dia{'s' if days > 1 else ''} atrás."


def issue_override(order) -> dict:
    """A autorização gravada da emissão avulsa, ou ``{}``."""
    value = ((order.data or {}).get("fiscal") or {}).get(ISSUE_OVERRIDE_KEY)
    return value if isinstance(value, dict) and value.get("approved_by") else {}


def issue_override_refusal(order, *, state: str | None = None) -> str:
    """Por que a emissão avulsa NÃO pode sair para este pedido — ``""`` quando pode.

    Uma função só para a lista (que decide se mostra o botão) e para o serviço
    (que decide de novo, dentro da trava): botão que aparece e endpoint que
    recusa é rótulo que mente.

    Só serve para a nota que a regra NÃO emitiu (``not_expected``). Falha tem o
    seu caminho (reprocessar); nota na fila ou esperando o pagamento já vai sair.
    """
    from django.utils import timezone

    from shopman.shop.services.payment_gate import payment_is_captured, requires_captured_payment

    data = order.data or {}
    if data.get("nfce_access_key"):
        return "A NFC-e desta venda já foi autorizada."
    if str(order.status) in ("cancelled", "returned"):
        return "Venda cancelada ou devolvida não emite NFC-e."
    if is_test_order(order):
        return "Pedido de teste não emite NFC-e."
    if simulated_payment_blocks_emission(order):
        return "Pagamento simulado não emite NFC-e: nenhum dinheiro entrou."
    if not fiscal_pool.get_backend():
        return "A emissão de NFC-e não está configurada nesta loja."
    if order.created_at:
        # Dia de OPERAÇÃO, pelo relógio da loja (TIME_ZONE), não UTC nem 24 h
        # corridas: a venda das 23h e a nota das 0h10 são dias diferentes.
        days = late_emission_days()
        sale_day = timezone.localtime(order.created_at).date()
        if (timezone.localdate() - sale_day).days > days:
            return late_emission_rule_text(days)
    if state is None:
        state = fiscal_state(order)
    if state != FISCAL_STATE_NOT_EXPECTED:
        return "Esta venda já tem NFC-e em andamento."
    if requires_captured_payment(order) and not payment_is_captured(order):
        return "O pagamento desta venda ainda não confirmou. A nota só sai depois."
    return ""


def emit(order) -> None:
    """
    Schedule NFC-e emission for the order.

    Smart no-op if no fiscal backend is configured.
    Creates a Directive with topic FISCAL_EMIT_NFCE.

    ASYNC — retry-safe.
    """
    # Pedido de teste de marketplace: nota fiscal é documento da Receita sobre
    # uma venda que não existiu. Hoje a emissão não dispara por acidente
    # (``method="external"`` derruba os resolvers), mas o payload de teste traz
    # CPF e o operador tem o botão "enviar nota" — o gate fica aqui, no único
    # caminho por onde a emissão nasce, e não na sorte da configuração.
    if is_test_order(order):
        logger.info("fiscal.emit: pedido de teste order=%s — emissão suprimida", order.ref)
        return

    if not fiscal_pool.get_backend():
        return

    data = order.data or {}
    if data.get("nfce_access_key"):
        return

    if not emission_resolver(order):
        _alert_receipt_promised_without_emission(order, data)
        return

    payment = _fiscal_payment(order, data)

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
    payment = _fiscal_payment(order, data)
    if _payment_below_total(payment, order):
        raise ValueError("Pagamento fiscal abaixo da base da nota. Corrija antes de reprocessar.")
    payment = _payment_net_of_change(payment, note_base_q(order))
    delivery = None
    if data.get("fulfillment_type") == "delivery":
        delivery = {"address": dict(data.get("delivery_address_structured") or {})}
    payload = {"order_ref": order.ref}
    if order.channel_ref:
        payload["channel_ref"] = order.channel_ref
    items = _build_fiscal_items(order)
    amounts = fiscal_intermediary.seller_amounts(order)
    if amounts is not None and amounts["freight_q"] > 0:
        items.append(_intermediary_freight_item(amounts["freight_q"]))
    payload.update(items=items, payment=payment, customer=_fiscal_customer(data), delivery=delivery)
    intermediary = fiscal_intermediary.intermediary_for(order)
    if intermediary is not None:
        payload["intermediary"] = intermediary
    else:
        _alert_intermediary_not_declared(order)
    return payload


def _fiscal_payment(order, data: dict) -> dict:
    """O pagamento **da nota** — que não é sempre o total do pedido.

    Numa venda direta os dois são a mesma coisa, e o ``amount_q`` gravado pelo
    canal é quem manda. Numa venda por intermediador o total do pedido carrega
    dinheiro que não é da casa (receita da plataforma, e o frete de quem não
    entregou), e a nota declara só a parte da casa — ver
    :mod:`shopman.shop.fiscal_intermediary`.

    A base calculada **sobrescreve**, e não é ``setdefault``: o ingest do
    marketplace grava ``payment`` sem valor nenhum (método ``external``), e um
    default teria deixado passar justamente o número errado.
    """
    payment = dict(data.get("payment") or {})
    amounts = fiscal_intermediary.seller_amounts(order)
    if amounts is not None:
        payment["amount_q"] = int(amounts["base_q"])
        return payment
    payment.setdefault("amount_q", order.total_q)
    return payment


def _intermediary_freight_item(freight_q: int) -> dict:
    """A taxa de entrega que É DA CASA vira a linha de frete da nota.

    Pedido de marketplace não tem a linha ``__DELIVERY_FEE__`` que o carrinho
    da casa monta: a plataforma manda a taxa no detalhamento financeiro, não
    como item. O adapter fiscal separa frete de mercadoria por esta marca e
    nunca mapeia a linha como produto — por isso ela não precisa (nem deve ter)
    classificação fiscal.
    """
    return {
        "sku": "__DELIVERY_FEE__",
        "name": "Taxa de entrega",
        "qty": "1",
        "unit": "UN",
        "unit_price_q": int(freight_q),
        "total_q": int(freight_q),
        "meta": {"type": "delivery_fee"},
        "fiscal": {},
    }


def _alert_intermediary_not_declared(order) -> None:
    """Venda intermediada indo para a nota SEM o grupo do intermediador: grite.

    Emitir assim produz uma NFC-e válida e fora do Ajuste SINIEF 22/20 — o pior
    tipo de defeito fiscal, porque nada reclama. Só fala quando o canal está
    declarado como intermediado e a configuração não fecha; venda direta não
    passa por aqui.
    """
    missing = fiscal_intermediary.missing_configuration(order)
    if not missing:
        return

    from shopman.shop.services.observability import create_operator_alert

    logger.error(
        "fiscal.intermediary_not_declared order=%s channel=%s missing=%s",
        order.ref, order.channel_ref, missing,
    )
    create_operator_alert(
        type="fiscal_intermediary_not_declared",
        severity="critical",
        message=(
            f"A NFC-e do pedido {order.ref} vai sair SEM identificar o "
            f"intermediador da venda, o que o Ajuste SINIEF 22/20 exige. "
            f"Falta configurar: {missing}."
        ),
        order_ref=order.ref,
        dedupe_key=f"fiscal_intermediary_not_declared:{order.ref}",
    )


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


def _payment_net_of_change(payment: dict, total_q: int) -> dict:
    """O pagamento que a NOTA declara: o dinheiro entra líquido do troco.

    Numa venda mista com troco (crédito 10,00 + dinheiro 5,00 numa venda de
    13,00), os ``tenders`` gravados no commit são o que veio na mão. O PDV só
    acerta o troco no ``settle`` (``pos._reconcile_order_payment_to_total``),
    DEPOIS dos ``on_commit`` do commit — e a venda de balcão chega a COMPLETED
    ali mesmo, com o ``on_completed`` pedindo a nota antes do acerto. O pedido
    de nota que vem depois, já com o valor certo, cai no dedupe ``nfce:{ref}``.
    Declarar 15,00 contra 13,00 de produtos, sem ``valor_troco``, a SEFAZ recusa.

    Por isso a nota não depende da ordem: o excedente sobre o total sai das
    linhas de DINHEIRO (a única forma que gera troco; a maquininha capturou o
    valor inteiro), da última para a primeira — a mesma regra do acerto do PDV.
    Excedente que o dinheiro não cobre não é troco: fica como está, e a recusa
    continua ruidosa. Pagamento já acertado passa intocado.
    """
    tenders = [dict(t) for t in payment.get("tenders") or [] if isinstance(t, dict)]
    excess_q = _declared_payment_q(payment) - total_q
    if not tenders or excess_q <= 0:
        return payment
    cash = [t for t in reversed(tenders) if str(t.get("method") or "").lower() == "cash"]
    if sum(max(0, int(t.get("amount_q") or 0)) for t in cash) < excess_q:
        return payment
    for tender in cash:
        take_q = min(excess_q, max(0, int(tender.get("amount_q") or 0)))
        tender["amount_q"] = int(tender.get("amount_q") or 0) - take_q
        excess_q -= take_q
        if not excess_q:
            break
    net = dict(payment)
    net["tenders"] = tenders
    net["amount_q"] = total_q
    return net


def note_base_q(order) -> int:
    """Quanto esta venda deve declarar na nota, em centavos.

    Venda direta: o total do pedido. Venda por intermediador: a parte da casa
    — o total do pedido menos a receita da plataforma e menos o frete que não
    foi a casa que prestou.
    """
    amounts = fiscal_intermediary.seller_amounts(order)
    if amounts is not None:
        return int(amounts["base_q"])
    return int(order.total_q or 0)


def _payment_below_total(payment: dict, order) -> bool:
    """O pagamento gravado ficou ABAIXO da base da nota?

    **Invariante de canal: quem escreve ``order.data['payment']`` escreve o valor
    FINAL.** O adapter deriva ``valor_desconto = produtos + frete − pagamento``,
    então um ``payment`` defasado (edição pós-pagamento que escape do
    ``_reconcile_order_payment_to_total`` do PDV) não vira erro: vira um
    **desconto que não houve** dentro de um XML válido, subdeclarando a venda.

    A régua é a base DA NOTA (:func:`note_base_q`), não ``Order.total_q``: numa
    venda por marketplace o total do pedido inclui dinheiro que nunca foi da
    casa, e comparar com ele recusaria para sempre justamente a nota corrigida.

    Só o lado de baixo é guardado aqui. Pagamento ACIMA da base por troco em
    dinheiro é acertado na montagem (``_payment_net_of_change``); o excedente
    que não é troco gera ``valor_total > valor_produtos`` sem desconto, e a
    própria SEFAZ recusa — falha ruidosa não precisa de guarda nossa.
    """
    return 0 < _declared_payment_q(payment) < note_base_q(order)


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
    base_q = note_base_q(order)
    logger.error(
        "fiscal.emit: pagamento (%s) abaixo da base da nota (%s) em %s — NFC-e não emitida",
        declared_q, base_q, order.ref,
    )
    create_operator_alert(
        type="fiscal_payment_mismatch",
        severity="critical",
        message=(
            f"NFC-e do pedido {order.ref} NÃO foi emitida: o pagamento gravado "
            f"(R$ {declared_q / 100:.2f}) está abaixo do valor que a nota deve "
            f"declarar (R$ {base_q / 100:.2f}). Emitir assim colocaria no "
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
        _verify_failed_emission(order)
        return

    if (order.data or {}).get("nfce_cancelled"):
        return

    directives.queue(
        FISCAL_CANCEL_NFCE, order,
        reason=(order.data or {}).get("cancellation_reason", "cancelled"),
    )

    logger.info("fiscal.cancel: queued for order %s", order.ref)


def _verify_failed_emission(order) -> None:
    """Venda desfeita sem chave, mas com emissão que já tentou: a nota pode existir.

    Uma emissão que parou em ``failed`` depois de um POST (timeout pós-emissão,
    janela de retry esgotada) pode ter deixado a nota AUTORIZADA na SEFAZ sem
    que a resposta chegasse. Sem chave, não há o que cancelar — e ninguém mais
    olharia. A directive volta para a fila com ``attempts=1``: o handler vê o
    pedido desfeito, só CONSULTA o Focus pela referência (nunca POSTa) e, se a
    nota existir, grava a chave e enfileira o cancelamento.

    Directive viva (``queued``/``running``) não precisa disto: o próprio
    handler faz a mesma consulta quando o pedido chega desfeito.
    """
    from django.utils import timezone
    from shopman.orderman.models import Directive

    directive = (
        Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order.ref)
        .order_by("-created_at", "-pk")
        .first()
    )
    if directive is None or directive.status != "failed" or int(directive.attempts or 0) < 1:
        return
    directive.status = "queued"
    directive.attempts = 1
    directive.available_at = timezone.now()
    directive.save(update_fields=["status", "attempts", "available_at", "updated_at"])
    logger.info("fiscal.cancel: emissão falha de %s reaberta para consulta", order.ref)


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
    "shopman.shop.fiscal_resolvers.on_request_or_tax_id",
    "shopman.shop.fiscal_resolvers.on_requested_receipt",
    "shopman.shop.fiscal_resolvers.always",
})


def receipt_request_emits() -> bool:
    """Pedir o comprovante (papel ou e-mail) faz a NFC-e sair?

    É verdade quando ``SHOPMAN_FISCAL_EMISSION_RESOLVER`` carrega um resolver
    que lê o pedido de comprovante (``on_request_or_tax_id``, que é a base de
    toda configuração, ``on_requested_receipt`` ou ``always``) — e também sem
    resolver nenhum, porque o fallback é o mesmo ``on_request_or_tax_id``. A env
    do deployment sobrescreve o default do código, então a frase do balcão
    ("imprime sozinha assim que autorizar") tem que perguntar aqui, nunca ao
    default.
    """
    from django.conf import settings

    raw = getattr(settings, "SHOPMAN_FISCAL_EMISSION_RESOLVER", "") or ""
    paths = {p.strip() for p in str(raw).split(",") if p.strip()}
    if not paths:
        return True
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
        # Vendido por peso, a quantidade da linha É quilo (0,312) e o valor
        # unitário é o preço do quilo: a unidade comercial não pode ser a "UN"
        # que a classificação fiscal traz por padrão — a nota diria 0,312
        # unidade. Não é segunda opinião fiscal: é a unidade da quantidade.
        from shopman.shop.services.weighed_sale import is_sold_by_weight

        if is_sold_by_weight(getattr(product, "unit", "")):
            fiscal = {**fiscal, "unit": "KG", "unidade_comercial": "KG"}
        items.append({
            "sku": item.sku,
            "name": item.name,
            "qty": str(item.qty.normalize()) if hasattr(item.qty, "normalize") else float(item.qty),
            "unit": getattr(product, "unit", "") or fiscal.get("unit") or "UN",
            "unit_price_q": item.unit_price_q,
            "total_q": item.line_total_q,
            "meta": dict(item.meta or {}),
            "fiscal": fiscal,
            "gtin": _trusted_gtin(metadata),
        })
    return items


def _trusted_gtin(metadata: dict) -> str:
    """GTIN que pode ir para a NFC-e (cEAN/cEANTrib), ou ``""`` quando não há.

    A SEFAZ confere o GTIN contra o Cadastro Centralizado de GTIN (rejeições
    890/894 da NT 2021.003): um código errado não é dado a mais, é nota
    recusada no balcão. Por isso a nota só leva GTIN de fonte que decide:

    - dígito verificador GS1 válido (``gtin_is_valid``), E
    - ``metadata['gtin_source']`` que não comece com ``"web"``. Ausente = o
      GTIN veio da NF-e de compra (declaração fiscal do fornecedor);
      ``"embalagem, dono, <data>"`` = lido no produto. ``"web, a confirmar na
      embalagem"`` é palpite de fontes públicas — fica fora da nota até alguém
      ler o código na embalagem.

    Produto da casa não tem GTIN. Nos casos sem GTIN confiável o adapter
    escreve o literal ``"SEM GTIN"``, que é o que o leiaute 4.0 exige.
    """
    from shopman.offerman import get_social_attributes, gtin_is_valid

    gtin = get_social_attributes(metadata).gtin.strip()
    if not gtin or not gtin_is_valid(gtin):
        return ""
    source = str(metadata.get("gtin_source") or "").strip().lower()
    if source.startswith("web"):
        return ""
    return gtin


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
