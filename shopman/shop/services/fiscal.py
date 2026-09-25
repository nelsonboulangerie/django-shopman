"""
Fiscal (NFC-e) service.

ASYNC — creates Directives for later processing.
Smart no-op when fiscal_pool is empty (no backend configured).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.utils.monetary import format_money

from shopman.shop import directives, fiscal_intermediary
from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE
from shopman.shop.fiscal import fiscal_pool
from shopman.shop.services import order_composition
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


#: Enquanto o pedido está num destes, a mercadoria ainda está NA CASA.
#:
#: É a segunda condição do art. 35 do Subanexo I do Anexo III do RICMS/PR —
#: cancelar exige "que não tenha havido a saída da mercadoria" — e é também a
#: pergunta que o estoque faz antes de creditar de volta (se o pão saiu com o
#: entregador, devolvê-lo ao saldo inventaria o que não está na prateleira).
#: Duas perguntas diferentes sobre o MESMO fato físico, por isso um conjunto só.
GOODS_NOT_DISPATCHED = frozenset({"new", "accepted", "preparing", "ready"})

#: O que dá para fazer com uma NFC-e autorizada que precisa ser desfeita.
CANCEL_AND_REISSUE = "cancel_and_reissue"
RETURN_NOTE = "return_note"
CANCELLATION_PATH_UNKNOWN = "unknown"


def cancellation_window_minutes() -> int:
    """Quantos minutos após a Autorização de Uso a NFC-e ainda pode ser cancelada.

    O número e a norma que o sustenta moram em
    ``settings.SHOPMAN_NFCE_CANCELLATION_WINDOW_MINUTES`` — é lei da UF, não
    regra desta lógica. Valor ilegível cai em zero, que é o lado seguro: manda
    para o estorno, que sempre vale, em vez de mandar cancelar uma nota fora do
    prazo (e receber a recusa do autorizador com a mercadoria já na rua).
    """
    try:
        return max(0, int(getattr(settings, "SHOPMAN_NFCE_CANCELLATION_WINDOW_MINUTES", 30)))
    except (TypeError, ValueError):
        logger.warning("fiscal.cancellation_window_minutes: valor ilegível em settings; usando 0")
        return 0


def nfce_authorized_at(order):
    """Quando a Autorização de Uso saiu, ou ``None`` se a nota não disse.

    É o instante que o art. 35 manda contar, e vem da SEFAZ (``data_autorizacao``
    da Focus) — não do nosso relógio, nem da hora em que gravamos.
    """
    raw = (order.data or {}).get("nfce_authorized_at")
    if not raw:
        return None
    parsed = parse_datetime(str(raw))
    if parsed is None:
        logger.warning("fiscal.nfce_authorized_at: data ilegível %r em %s", raw, order.ref)
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def cancellation_path(order) -> dict:
    """Como desfazer a NFC-e já autorizada deste pedido.

    ``{"path", "deadline", "minutes_left", "reason"}``. São dois caminhos de
    verdade, e a diferença entre eles é prazo, não preferência:

    - :data:`CANCEL_AND_REISSUE` — dentro da janela do art. 35 **e** com a
      mercadoria ainda na casa. Cancela e emite de novo.
    - :data:`RETURN_NOTE` — fora da janela, ou mercadoria já despachada. No
      Paraná **não existe cancelamento extemporâneo**: o caminho é documento
      fiscal de estorno (RICMS/2017, art. 298, VII), limpo dentro do mesmo
      período de apuração e, depois dele, com os acréscimos legais do § 2º.
    - :data:`CANCELLATION_PATH_UNKNOWN` — a nota não trouxe a hora da
      autorização, então o prazo não pode ser medido. Não vira "provavelmente
      dá tempo": vira pergunta explícita, porque errar para o lado do
      cancelamento é tentar cancelar fora do prazo e ficar sem documento nenhum.

    ``reason`` diz QUAL das duas condições fechou a porta — ``window_closed``
    ou ``goods_dispatched``. Não é detalhe: o aviso que diz "o prazo passou"
    para um pedido já entregue, com a nota de dois minutos atrás, está mentindo
    — e manda o operador procurar o erro no relógio.
    """
    window = cancellation_window_minutes()
    authorized_at = nfce_authorized_at(order)
    if authorized_at is None:
        return {
            "path": CANCELLATION_PATH_UNKNOWN, "deadline": None,
            "minutes_left": None, "reason": "",
        }

    deadline = authorized_at + timedelta(minutes=window)
    minutes_left = (deadline - timezone.now()).total_seconds() / 60
    dispatched = str(getattr(order, "status", "")) not in GOODS_NOT_DISPATCHED
    if minutes_left <= 0 or dispatched:
        return {
            "path": RETURN_NOTE, "deadline": deadline, "minutes_left": minutes_left,
            # Quando as duas fecharam, a saída da mercadoria é a que se diz: é a
            # irreversível, e é a que o operador consegue conferir com os olhos.
            "reason": "goods_dispatched" if dispatched else "window_closed",
        }
    return {
        "path": CANCEL_AND_REISSUE, "deadline": deadline,
        "minutes_left": minutes_left, "reason": "",
    }


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
    customer = _fiscal_customer(data)
    # Entrega intermediada sem documento sai presencial, sem destinatário nem
    # frete — ver fiscal_intermediary.issues_as_presential. Canal próprio nunca.
    presential = fiscal_intermediary.issues_as_presential(
        order, requested_tax_id=customer.get("tax_id") or "",
    )
    delivery = None
    if data.get("fulfillment_type") == "delivery" and not presential:
        delivery = {
            "address": dict(data.get("delivery_address_structured") or {}),
            # Quem transportou decide a modalidade do frete (X02) e se a padaria
            # se declara transportadora. Venda direta é sempre da casa.
            "by_house": fiscal_intermediary.house_delivered(order),
        }
    payload = {"order_ref": order.ref}
    if order.channel_ref:
        payload["channel_ref"] = order.channel_ref
    items = _build_fiscal_items(order)
    amounts = fiscal_intermediary.seller_amounts(order)
    if amounts is not None and amounts["freight_q"] > 0:
        items.append(_intermediary_freight_item(amounts["freight_q"], as_other_expense=presential))
    payload.update(items=items, payment=payment, customer=customer, delivery=delivery)
    intermediary = fiscal_intermediary.intermediary_for(order)
    if intermediary is not None:
        payload["intermediary"] = intermediary
    else:
        _alert_intermediary_not_declared(order)
    _alert_intermediary_base_unknown(order)
    _alert_intermediary_benefit_unattributed(order)
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
    payment.setdefault("amount_q", order_composition.effective_total_q(order))
    return payment


def _intermediary_freight_item(freight_q: int, *, as_other_expense: bool = False) -> dict:
    """A taxa de entrega que É DA CASA vira a linha de frete da nota.

    Pedido de marketplace não tem a linha ``__DELIVERY_FEE__`` que o carrinho
    da casa monta: a plataforma manda a taxa no detalhamento financeiro, não
    como item. O adapter fiscal separa frete de mercadoria por esta marca e
    nunca mapeia a linha como produto — por isso ela não precisa (nem deve ter)
    classificação fiscal.

    ``as_other_expense``: a nota sai presencial, sem frete
    (``fiscal_intermediary.issues_as_presential``), e a mesma taxa entra como
    **outras despesas** (``vOutro``). A linha ganha outra marca, e o adapter a
    declara em ``valor_outras_despesas``, nunca como frete nem como mercadoria.
    """
    if as_other_expense:
        return {
            "sku": "__OTHER_EXPENSE__",
            "name": "Taxa de entrega",
            "qty": "1",
            "unit": "UN",
            "unit_price_q": int(freight_q),
            "total_q": int(freight_q),
            "meta": {"type": "other_expense"},
            "fiscal": {},
        }
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
    # Pedido + ajustes: a nota é do pedido que VALE. Um pedido cujo cliente
    # tirou um item e cuja NFC-e ainda não saiu declara a lista de agora — a que
    # já saiu é decisão fiscal e nem chega aqui
    # (``ifood_events._patch_block_reason`` para em ``fiscal_authorized``).
    return order_composition.effective_total_q(order)


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


def _alert_intermediary_base_unknown(order) -> None:
    """Venda intermediada cuja BASE não pôde ser corrigida: grite igual.

    Irmão de :func:`_alert_intermediary_not_declared`, e existe porque as duas
    omissões da mesma família falhavam em sentidos opostos: faltar a
    configuração do grupo gritava, faltar o detalhamento financeiro saía calado
    pelo total cheio — com a receita da plataforma dentro da base, que é o
    defeito de origem.

    Silêncio legítimo (venda direta, e pedido do iFood sem ``totals``, cujo
    total já vem da soma dos itens) é decidido em
    ``fiscal_intermediary.unreadable_breakdown``, não aqui.
    """
    missing = fiscal_intermediary.unreadable_breakdown(order)
    if not missing:
        return

    from shopman.shop.services.observability import create_operator_alert

    logger.error(
        "fiscal.intermediary_base_unknown order=%s channel=%s motivo=%s",
        order.ref, order.channel_ref, missing,
    )
    create_operator_alert(
        type="fiscal_intermediary_base_unknown",
        severity="critical",
        message=(
            f"A NFC-e do pedido {order.ref} vai declarar o total CHEIO do pedido: "
            f"{missing}."
        ),
        order_ref=order.ref,
        dedupe_key=f"fiscal_intermediary_base_unknown:{order.ref}",
    )


def _alert_intermediary_benefit_unattributed(order) -> None:
    """Cupom de venda intermediada sem patrocinador legível: grite.

    Terceiro irmão de :func:`_alert_intermediary_not_declared` e
    :func:`_alert_intermediary_base_unknown`. Cupom patrocinado pela LOJA é
    desconto e derruba a base; cupom patrocinado pelo iFood, por parceiro
    externo ou pela rede é repasse e COMPÕE a base. Sem saber qual é, a conta
    escolhe o lado que declara a mais — nunca a menos —, e essa escolha não
    pode ficar só no código.
    """
    missing = fiscal_intermediary.unattributable_benefits(order)
    if not missing:
        return

    from shopman.shop.services.observability import create_operator_alert

    logger.error(
        "fiscal.intermediary_benefit_unattributed order=%s channel=%s motivo=%s",
        order.ref, order.channel_ref, missing,
    )
    create_operator_alert(
        type="fiscal_intermediary_benefit_unattributed",
        severity="critical",
        message=(
            f"A NFC-e do pedido {order.ref} vai declarar o cupom como repasse da "
            f"plataforma (base cheia), porque não deu para saber quem o patrocinou: "
            f"{missing}. Se o cupom era da loja, a nota está declarando a MAIS — "
            "confira no portal do iFood antes de fechar o mês."
        ),
        order_ref=order.ref,
        dedupe_key=f"fiscal_intermediary_benefit_unattributed:{order.ref}",
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
            f"A NFC-e do pedido {order.ref} não foi emitida: o pagamento registrado "
            f"(R$ {format_money(declared_q)}) está abaixo do valor que a nota deve "
            f"declarar (R$ {format_money(base_q)}). Emitir assim colocaria na "
            "nota um desconto que não houve. Registre o pagamento que falta no pedido "
            "e toque em Reprocessar NFC-e."
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
            f"O pedido {order.ref} foi {verbo} sem NFC-e autorizada. "
            + (
                "A nota ainda está sendo emitida; este aviso fecha sozinho quando ela autorizar."
                if state == FISCAL_STATE_QUEUED
                else "A emissão falhou: abra o pedido e toque em Reprocessar NFC-e."
            )
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

    **Kit sai aberto na nota** (decisão do dono, 24/09/2026). Linha cujo produto
    tem componentes (``offerman.ProductComponent``) vira uma linha fiscal POR
    COMPONENTE, cada uma com a tributação do próprio componente (NCM, CEST,
    perfil, origem, GTIN): a caixa presente com pão, geleia e vinho não pode sair
    com o NCM de pão para o vinho. O rateio do preço está em
    :func:`_kit_lines`. Os pacotes de N unidades do mesmo pão (``BRBB2`` =
    2 × ``BRBB``) seguem a mesma regra, de propósito: sai "2 × Brioche Burger
    Bun" pelo preço do pacote, com o fiscal do pão — é o mesmo pão, e a nota
    diz o que foi entregue. Caixa presente com preço próprio: os itens saem
    pelo preço avulso e o ágio sai na linha da embalagem (ver
    :func:`_kit_lines`). Kit sem mercadoria (só a caixa, ou nada) não chega
    aqui vendido: fica ``is_sellable=False`` (``apply_grocery_catalog``).
    """
    # Pedido + ajustes: a nota é do pedido que VALE, não do que nasceu. Um
    # pedido cujo cliente tirou um item e cuja NFC-e ainda não saiu declara a
    # lista de agora; o que já saiu é decisão fiscal e nem chega aqui
    # (``ifood_events._patch_block_reason`` para em ``fiscal_authorized``).
    order_items = list(order_composition.effective_items(order))
    skus = [item.sku for item in order_items]
    products_by_sku = _products_by_sku(skus)
    components_by_sku = _kit_components_by_sku(skus)

    items = []
    for item in order_items:
        override = (item.meta or {}).get("fiscal")
        components = components_by_sku.get(item.sku)
        if components:
            items.extend(_kit_lines(item, components, override))
            continue
        items.append(_fiscal_line(
            products_by_sku.get(item.sku),
            sku=item.sku,
            name=item.name,
            qty=item.qty,
            unit_price_q=item.unit_price_q,
            total_q=item.line_total_q,
            meta=dict(item.meta or {}),
            override=override,
        ))
    return items


def _fiscal_line(product, *, sku, name, qty, unit_price_q, total_q, meta, override) -> dict:
    """Uma linha do payload fiscal, com a tributação resolvida do ``product``."""
    from shopman.fiscalman.classification import from_metadata, resolve_fiscal_item

    from shopman.shop.services.weighed_sale import is_sold_by_weight

    metadata = dict(getattr(product, "metadata", None) or {})
    fiscal = resolve_fiscal_item(from_metadata(metadata))
    if override:
        fiscal = {**fiscal, **dict(override)}
    # Vendido por peso, a quantidade da linha É quilo (0,312) e o valor
    # unitário é o preço do quilo: a unidade comercial não pode ser a "UN"
    # que a classificação fiscal traz por padrão — a nota diria 0,312
    # unidade. Não é segunda opinião fiscal: é a unidade da quantidade.
    if is_sold_by_weight(getattr(product, "unit", "")):
        fiscal = {**fiscal, "unit": "KG", "unidade_comercial": "KG"}
    return {
        "sku": sku,
        "name": name,
        "qty": str(qty.normalize()) if hasattr(qty, "normalize") else float(qty),
        "unit": getattr(product, "unit", "") or fiscal.get("unit") or "UN",
        "unit_price_q": unit_price_q,
        "total_q": total_q,
        "meta": meta,
        "fiscal": fiscal,
        "gtin": _trusted_gtin(metadata),
    }


def _kit_lines(item, components: list, override) -> list[dict]:
    """Abre a linha do kit em uma linha fiscal por componente.

    **Quantidade**: ``qty da linha × qty do componente`` (2 caixas com 3 pães
    = 6 pães).

    **Valor — primeiro o preço cheio do kit** (``meta['_list_q']``, o preço de
    lista carimbado antes de qualquer desconto; sem ele, ``unit_price_q``) ×
    qty da linha, repartido assim:

    - **Kit com ágio** (preço do kit > soma dos componentes avulsos, e o kit
      declara a embalagem — componente com ``metadata['kit_packaging']``):
      cada componente sai pelo **preço avulso** (``base_price_q × qty``) e a
      **diferença** sai na linha da embalagem (a caixa física entregue ao
      cliente, NCM de embalagem, perfil sem ST, sem GTIN). O serviço de
      montagem vai embutido no valor da mercadoria: no Simples a caixa
      presente é VENDA DE MERCADORIA, e NFC-e não tem ISS — não existe linha
      de serviço a separar.
    - **Kit com desconto** (soma avulsa ≥ preço do kit), ou kit sem embalagem
      declarada: **sem linha de embalagem**. O preço do kit é rateado entre os
      componentes proporcional ao preço avulso (todos zerados → rateio igual).
      A embalagem não entra com valor simbólico: ela simplesmente não aparece.

    **Depois o desconto da venda** (o que o ``line_total_q`` cobrado ficou
    abaixo do preço cheio): aplicado ao total do kit e rateado entre TODAS as
    linhas acima, embalagem inclusa, proporcional ao valor de cada uma. Na
    prática as duas etapas são um rateio só do ``line_total_q`` pelos pesos
    acima — sem desconto, cada linha recebe exatamente o seu peso.

    Cada fatia é arredondada para baixo e o resto de centavos vai na ÚLTIMA
    linha: a soma fecha o total cobrado da linha original centavo a centavo,
    que é o que a SEFAZ confere contra o pagamento. O desconto do PEDIDO o
    adapter rateia depois, sobre estas linhas, como sobre qualquer outra.

    **Valor unitário**: ``total ÷ qty`` arredondado; quando não fecha, o
    adapter deriva ``vUnCom`` de ``vProd/qCom`` (até 10 casas).
    **Fiscal**: do produto componente. Um ``meta['fiscal']`` na linha do kit
    (override manual, raro) vale para todas as linhas abertas.
    ``meta['kit']`` guarda de qual linha a linha veio (``sku``, ``name``,
    ``qty``), para quem reconciliar a nota com o pedido.
    """
    from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

    line_qty = Decimal(str(item.qty))
    charged_q = int(item.line_total_q)
    list_unit_q = (item.meta or {}).get("_list_q")
    if list_unit_q is None:
        list_unit_q = item.unit_price_q
    full_q = int((Decimal(int(list_unit_q or 0)) * line_qty).to_integral_value(rounding=ROUND_HALF_UP))

    packaging = [pc for pc in components if _is_kit_packaging(pc.component)]
    goods = [pc for pc in components if not _is_kit_packaging(pc.component)]
    goods_weights = [
        Decimal(int(pc.component.base_price_q or 0)) * Decimal(str(pc.qty)) * line_qty for pc in goods
    ]
    goods_sum = sum(goods_weights, Decimal(0))

    if packaging and Decimal(full_q) > goods_sum:
        # Ágio: avulsos pelo preço de lista, a diferença na caixa.
        lines_to_emit = [*goods, packaging[0]]
        weights = [*goods_weights, Decimal(full_q) - goods_sum]
    else:
        # Desconto (ou kit sem embalagem declarada): sem linha de caixa.
        lines_to_emit = goods or components  # kit só com a caixa: ela leva tudo
        weights = goods_weights if goods else [Decimal(0)] * len(components)
        if sum(weights, Decimal(0)) <= 0:
            weights = [Decimal(1)] * len(lines_to_emit)
    weight_sum = sum(weights, Decimal(0))

    lines = []
    allocated = 0
    kit_meta = {"sku": item.sku, "name": item.name, "qty": str(line_qty.normalize())}
    for idx, (pc, weight) in enumerate(zip(lines_to_emit, weights, strict=True)):
        if idx == len(lines_to_emit) - 1:
            share_q = charged_q - allocated
        else:
            share_q = int((Decimal(charged_q) * weight / weight_sum).to_integral_value(rounding=ROUND_DOWN))
        allocated += share_q
        qty = line_qty * Decimal(str(pc.qty))
        unit_price_q = int((Decimal(share_q) / qty).to_integral_value(rounding=ROUND_HALF_UP)) if qty else 0
        lines.append(_fiscal_line(
            pc.component,
            sku=pc.component.sku,
            name=pc.component.name,
            qty=qty,
            unit_price_q=unit_price_q,
            total_q=share_q,
            meta={"kit": kit_meta},
            override=override,
        ))
    return lines


def _is_kit_packaging(product) -> bool:
    """A caixa física do kit (``metadata['kit_packaging']``): recebe o ágio."""
    metadata = getattr(product, "metadata", None)
    return isinstance(metadata, dict) and metadata.get("kit_packaging") is True


def _kit_components_by_sku(skus: list[str]) -> dict[str, list]:
    """Componentes (``ProductComponent``) por SKU do kit, em ordem estável.

    A ordem decide quem recebe o resto de centavos do rateio (a última linha),
    então é a de cadastro (``pk``), nunca a do banco. Falha de leitura SOBE,
    pelo mesmo motivo de :func:`_products_by_sku`.
    """
    if not skus:
        return {}
    from shopman.offerman.models import ProductComponent

    by_sku: dict[str, list] = {}
    rows = (
        ProductComponent.objects.filter(parent__sku__in=set(skus))
        .select_related("parent", "component")
        .order_by("parent_id", "pk")
    )
    for pc in rows:
        by_sku.setdefault(pc.parent.sku, []).append(pc)
    return by_sku


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

    - produto SEM a marca ``metadata['gtin_nf_rejected']``: a SEFAZ já
      recusou o GTIN dele numa nota (``mark_gtin_rejected``). Daí em diante o
      produto sai ``"SEM GTIN"`` até alguém conferir a embalagem e limpar a
      marca — a venda nunca espera pelo GTIN.

    Produto da casa não tem GTIN. Nos casos sem GTIN confiável o adapter
    escreve o literal ``"SEM GTIN"``, que é o que o leiaute 4.0 exige.
    """
    from shopman.offerman import get_social_attributes, gtin_is_valid

    if metadata.get(GTIN_NF_REJECTED_KEY):
        return ""
    gtin = get_social_attributes(metadata).gtin.strip()
    if not gtin or not gtin_is_valid(gtin):
        return ""
    source = str(metadata.get("gtin_source") or "").strip().lower()
    if source.startswith("web"):
        return ""
    return gtin


# Rejeições da SEFAZ que dizem "o GTIN deste item está errado" e que a nota
# CURA saindo com "SEM GTIN" nas duas tags (cEAN e cEANTrib). Textos do Manual
# de Orientação do Contribuinte e da NT 2021.003 (Cadastro Centralizado de GTIN,
# CCG), conferidos em 24/09/2026 em:
#   - https://focusnfe.com.br/blog/nota-tecnica-2021-003/ (NT 2021.003: 883,
#     888, 890, 891, 892, 894, 897)
#   - https://cstat.vinco.com.br/help/cstat-800-899 (tabela cStat 882–896)
#   - https://oobj.com.br/bc/rejeicao-611-como-resolver/ (611)
#   - https://oobj.com.br/bc/rejeicao-882-como-resolver/ (882)
#   - https://ajuda.omie.com.br/pt-BR/articles/6173400 (889)
#
#   611 GTIN (cEAN) inválido — dígito verificador GS1
#   612 GTIN da unidade tributável (cEANTrib) inválido
#   882 GTIN (cEAN) com prefixo inválido
#   884 GTIN da unidade tributável (cEANTrib) com prefixo inválido
#   885 GTIN informado, mas não informado o GTIN da unidade tributável
#   886 GTIN da unidade tributável informado, mas não informado o GTIN
#   887 GTIN-14 de agrupamento no cEANTrib / item de serviço com GTIN (o texto
#       varia entre as fontes; nos dois casos a cura é "SEM GTIN")
#   890 GTIN inexistente no Cadastro Centralizado de GTIN (CCG)
#   891 GTIN incompatível com a NCM
#   892 GTIN incompatível com o CEST
#   893 GTIN da unidade tributável diverge do GTIN de nível inferior no CCG
#   894 GTIN da unidade tributável inexistente no CCG
#   895 GTIN da unidade tributável incompatível com a NCM
#   896 GTIN da unidade tributável incompatível com o CEST
#   897 Item de serviço com GTIN diferente de "SEM GTIN"
#
# FORA de propósito, porque "SEM GTIN" não cura (ou é a própria causa):
#   883 GTIN (cEAN) sem informação · 888 cEANTrib sem informação — tag vazia;
#       o adapter nunca manda vazio (``fiscal_focusnfe.NO_GTIN``).
#   889 Obrigatória a informação do GTIN para o produto — a SEFAZ QUER o GTIN;
#       reenviar "SEM GTIN" repetiria a rejeição. Segue terminal, para gente.
SEFAZ_GTIN_REJECTION_CODES = frozenset({
    "611", "612", "882", "884", "885", "886", "887",
    "890", "891", "892", "893", "894", "895", "896", "897",
})
# Prefixo do ``error_code`` que o adapter devolve para rejeição da SEFAZ
# (``fiscal_focusnfe._document_result``: ``sefaz_<cStat>``).
SEFAZ_REJECTION_PREFIX = "sefaz_"
GTIN_NF_REJECTED_KEY = "gtin_nf_rejected"


def sefaz_gtin_rejection_code(error_code: str | None) -> str:
    """cStat da rejeição quando ela é de GTIN curável com "SEM GTIN"; senão ``""``."""
    code = str(error_code or "")
    if not code.startswith(SEFAZ_REJECTION_PREFIX):
        return ""
    cstat = code[len(SEFAZ_REJECTION_PREFIX):]
    return cstat if cstat in SEFAZ_GTIN_REJECTION_CODES else ""


def mark_gtin_rejected(sku: str, *, gtin: str, code: str, reason: str, order_ref: str) -> bool:
    """Grava ``metadata['gtin_nf_rejected']`` no produto; ``True`` quando gravou.

    Relê a linha sob lock: ``Product.metadata`` tem muitos donos (fiscal,
    social, enriquecimento) e gravar o dicionário lido antes seria
    last-write-wins sobre eles. A marca só sai à mão, depois de alguém conferir
    o código na embalagem — é o que devolve o GTIN à nota.
    """
    from django.db import transaction
    from django.utils import timezone
    from shopman.offerman.models import Product

    with transaction.atomic():
        product = Product.objects.select_for_update().filter(sku=sku).first()
        if product is None:
            return False
        metadata = dict(product.metadata or {})
        metadata[GTIN_NF_REJECTED_KEY] = {
            "at": timezone.now().isoformat(),
            "code": code,
            "reason": str(reason or "")[:500],
            "gtin": gtin,
            "order_ref": order_ref,
        }
        product.metadata = metadata
        product.save(update_fields=["metadata", "updated_at"])
    return True


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
