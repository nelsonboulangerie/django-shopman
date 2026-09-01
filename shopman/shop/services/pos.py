"""POS mutation facade.

Backstage POS views own permissions, HTTP parsing, and HTML responses. This
module owns the Orderman session writes and POS order mutations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from shopman.cashman import services as cash_ledger
from shopman.orderman.models import Order, Session
from shopman.utils.monetary import format_money

from shopman.shop.adapters import pos as pos_adapter
from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel
from shopman.shop.services import payment as payment_service
from shopman.shop.services import sessions as session_service
from shopman.shop.services.cancellation import cancel
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION, PosIntentError, parse_pos_sale_intent

logger = logging.getLogger(__name__)


class PosRecentSaleNotFound(ValueError):
    """Ação de venda recente referenciou um pedido que não existe.

    Tipo distinto para a camada HTTP mapear para 404 sem inspecionar a
    mensagem; as demais violações de janela/estado seguem como ``ValueError``.
    """


_TAB_REF_MAX_LENGTH = 64
_TAB_REF_DISALLOWED = set('/\\?#%\r\n\t')


@dataclass(frozen=True)
class PosSaleResult:
    order_ref: str
    total_q: int
    fiscal_hint: str = ""
    payment: dict | None = None


@dataclass(frozen=True)
class PosSaleReview:
    intent_version: str
    tab_ref: str
    subtotal_q: int
    discount_q: int
    delivery_fee_q: int
    total_q: int
    payment_method: str
    payment_collection: str
    tender_total_q: int
    tender_count: int
    tendered_q: int
    change_q: int
    requires_manager_approval: bool
    manager_approval_threshold_q: int
    receipt_channels: tuple[str, ...]
    #: Vai sair nota com CPF? (o consumidor pediu o documento nesta venda)
    fiscal_tax_id_requested: bool
    # POR QUE o gerente foi chamado. O servidor conhece os gatilhos
    # (teto de desconto, preço alterado); sem publicá-los
    # a tela chutava "descontos acima de R$ X" mesmo quando o gatilho tinha sido
    # outro, e o gerente autorizava sem saber o que estava autorizando.
    approval_reasons: tuple[str, ...] = ()
    warnings: tuple[dict, ...] = ()
    # ENTREGA — o que a tela precisa para PERGUNTAR, em vez de pedir que o
    # operador invente. A taxa vem resolvida (ver `_resolve_delivery_fee`); os
    # horários são as janelas de meia hora que o expediente do dia comporta.
    #: "" · "zone" · "distance" · "default" · "manual" · "blocked"
    delivery_fee_source: str = ""
    delivery_distance_km: float | None = None
    #: A data que o servidor usou — em branco no pedido, é HOJE (o relógio da
    #: loja, não o do dispositivo do balcão).
    delivery_date: str = ""
    #: ``({"ref", "label", "enabled", "reason"}, …)``. Vazio = não há janela
    #: combinável nesse dia (fechado, feriado, ou o expediente já acabou) — bem
    #: diferente de "todas desabilitadas", que é "há expediente, mas ESTE
    #: carrinho não cabe neste dia".
    delivery_slots: tuple[dict, ...] = ()
    #: A primeira janela oferecível deste dia para este carrinho, ou "". A tela
    #: usa para pré-selecionar sem ter que refazer a conta do servidor.
    delivery_earliest_slot: str = ""


@dataclass(frozen=True)
class PosTabResult:
    tab_ref: str
    tab_display: str
    session_key: str


@dataclass(frozen=True)
class PosMoveResult:
    """Outcome of a move-lines command (transfer/split/merge).

    Carries the mutated sessions; the surface reads each comanda's payload via
    the projection. ``source`` is ``None`` when the emptied source was closed.
    """

    target: Session
    source: Session | None
    source_closed: bool


@dataclass(frozen=True)
class PosFireResult:
    """Outcome of a fire-to-kitchen command: the mutated session + effects."""

    session: Session
    fired_count: int
    fired_lines: tuple[str, ...]


@dataclass(frozen=True)
class PosUnfireResult:
    """Outcome of a cancel-fire command: the mutated session + effects."""

    session: Session
    cancelled: int
    trimmed: int
    fired_lines: tuple[str, ...]


#: Quantos dígitos uma comanda NUMÉRICA tem, no máximo. Acima disso o valor não é
#: número de comanda — é outra coisa que por acaso só tem dígitos (telefone, CPF).
#: A distinção não é cosmética: o painel público de retirada decide o que pode ir
#: para a TV a partir dela (ver `_public_comanda_code`).
MAX_NUMERIC_TAB_REF_DIGITS = 8


def is_numeric_tab_ref(value: str) -> bool:
    """O valor tem a cara de uma comanda numérica desta casa?

    ``isdigit()`` sozinho NÃO responde isso, e a diferença vazou PII: um telefone
    de 11 dígitos é `isdigit()` e não é comanda. Quem precisa saber "isto é um
    número de comanda" pergunta aqui, e não ao `str`.
    """
    text = str(value or "").strip()
    return text.isdigit() and len(text) <= MAX_NUMERIC_TAB_REF_DIGITS


def normalize_tab_ref(value: str) -> str:
    """Normalize a POS tab reference.

    Numeric references keep the legacy 8-digit storage shape. Text references
    are accepted as operator-facing identifiers and normalized to uppercase for
    stable lookup across surfaces.
    """
    raw = _clean_tab_ref(value)
    if is_numeric_tab_ref(raw):
        return raw.zfill(MAX_NUMERIC_TAB_REF_DIGITS)
    return raw.upper()


def display_tab_ref(tab_ref: str) -> str:
    value = str(tab_ref or "").strip()
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def _clean_tab_ref(value: str) -> str:
    raw = re.sub(r"\s+", " ", str(value or "").strip())
    if not raw:
        raise ValueError("Informe uma referência de comanda.")
    if len(raw) > _TAB_REF_MAX_LENGTH:
        raise ValueError(f"Informe uma comanda com até {_TAB_REF_MAX_LENGTH} caracteres.")
    if any(ch in _TAB_REF_DISALLOWED or ord(ch) < 32 for ch in raw):
        raise ValueError("A referência da comanda não pode conter barras ou caracteres de URL.")
    return raw


def _tab_label_from_input(value: str, ref: str) -> str:
    try:
        raw = _clean_tab_ref(value)
    except ValueError:
        return display_tab_ref(ref)
    if raw.isdigit() and len(raw) <= 8:
        return display_tab_ref(ref)
    return raw


def register_pos_tab(*, tab_ref: str, label: str = "") -> dict:
    """Register or reactivate a POS tab without opening a sale session."""
    ref = normalize_tab_ref(tab_ref)
    display = _tab_label_from_input(tab_ref, ref)
    label = str(label or "").strip() or display
    return pos_adapter.upsert_tab(ref=ref, label=label, display=display)


def resolve_customer(phone: str):
    """Look up a customer by phone for POS display and pricing modifiers."""
    if not phone:
        return None
    try:
        from shopman.guestman.services import customer as customer_service

        return customer_service.get_by_phone(phone)
    except Exception:
        logger.exception("pos_resolve_customer_failed phone=%s", phone)
        return None


# ----------------------------------------------------------------- audit trail
# Anti-fraud trail of session-phase actions, emitted by this orchestration layer
# (the kernel SessionEvent stays vocabulary-free). Anchored on session_key, so it
# is durable (survives clear/delete) and continuous into the Order (same key);
# post-commit actions like cancellation are covered by OrderEvent.


def _audit_qty(item: dict):
    try:
        qty = Decimal(str(item.get("qty", 0)))
    except (InvalidOperation, TypeError):
        return 0
    return int(qty) if qty == qty.to_integral_value() else float(qty)


def _audit_item_index(items: list[dict]) -> dict:
    # Key by SKU (stable operator-meaningful identity), not line_id — line_ids are
    # reassigned on reload/persist and would produce false add/remove churn.
    index: dict = {}
    for item in items or []:
        if _is_delivery_fee_item(item):
            continue
        index[str(item.get("sku") or "")] = item
    return index


def _audit_line_diff(session: Session, *, before: list[dict], after: list[dict], actor: str) -> None:
    """Emit add/remove/qty events for the net change between two item snapshots."""
    old = _audit_item_index(before)
    new = _audit_item_index(after)
    for key, item in new.items():
        if key not in old:
            session.emit_event("line_added", actor=actor, payload={
                "sku": item.get("sku"), "name": item.get("name"), "qty": _audit_qty(item),
            })
        elif _audit_qty(item) != _audit_qty(old[key]):
            session.emit_event("qty_changed", actor=actor, payload={
                "sku": item.get("sku"), "name": item.get("name"),
                "qty_before": _audit_qty(old[key]), "qty_after": _audit_qty(item),
            })
    for key, item in old.items():
        if key not in new:
            session.emit_event("line_removed", actor=actor, payload={
                "sku": item.get("sku"), "name": item.get("name"), "qty": _audit_qty(item),
            })


def close_sale(
    *,
    channel_ref: str,
    payload: dict,
    actor: str,
    operator_username: str,
) -> PosSaleResult:
    """Create and commit a POS sale from a parsed cart payload."""
    payload = parse_pos_sale_intent(payload, for_commit=True).payload
    channel, config = _channel_and_config(channel_ref)
    derive_price_overrides(payload, channel=channel)
    # A etiqueta que o KERNEL carimbou vale mais que a que o cliente mandou, e o
    # GATE precisa dela tanto quanto a review: sem carimbo, ``_payload_discount_q``
    # media o desconto de linha contra o preco JA descontado. Duas consequencias,
    # as duas ruins. A conta inflada podia exigir gerente logo depois de uma review
    # que dissera que nao precisava; e, num controle ANTI-FRAUDE, quem decidia o
    # limiar passava a ser a etiqueta declarada pelo navegador. O carimbo tem de
    # vir antes de ``validate_manager_approval`` e antes da taxa de entrega, que
    # tambem le a mesma soma para dispensar o frete.
    _stamp_list_prices_from_session(
        payload, _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
    )
    _ensure_resolved_prices(payload)
    # Guardado, não descartado: é este nome — o VERIFICADO — que assina a linha do
    # desconto lá embaixo. Ver `build_session_ops`.
    approver = validate_manager_approval(payload, operator_username=operator_username)
    approved_by = approver.get_username() if approver is not None else ""
    _validate_fiscal_delivery_fee(payload)
    _validate_schedule(payload)
    _validate_payment_completion(payload)
    _require_house_account_if_on_account(
        payload,
        payment_method=_normalize_payment_method(payload.get("payment_method") or "cash"),
        tenders=[t for t in (payload.get("payment_tenders") or []) if isinstance(t, dict)],
    )
    # A partir daqui é uma transação só, e ela existe por causa de um defeito:
    # ``client_request_id`` era conferido com um SELECT solto e os ops eram
    # montados de um estado lido antes. Duas requests com a MESMA chave passavam
    # as duas pelo `existing is None` e reconstruíam a sessão em cima do mesmo
    # snapshot — carrinho dobrado (R$ 76 numa compra de R$ 38) ou dois pedidos,
    # 15 vezes em 15 rodadas. A projection publica
    # ``idempotent_replay: safe_for_offline_queue``, e uma fila offline reenvia
    # exatamente assim.
    #
    # O remédio é o mesmo que o livro-caixa já usa para a venda por pedido:
    # unicidade no BANCO, não na leitura. ``_claim_sale_request`` trava a linha
    # única ``(scope, key)`` de ``IdempotencyKey``, e a segunda request só volta
    # a andar quando a primeira commitou. Ao voltar ela lê o ``order_ref`` NA
    # PRÓPRIA TRAVA (``_answer_sale_claim`` o escreveu dentro da transação) e
    # devolve a mesma venda, em vez de criar a segunda.
    with transaction.atomic():
        claim = _claim_sale_request(channel_ref=channel.ref, payload=payload)
        session = _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
        existing = _claimed_sale(claim) or _existing_sale_by_client_request_id(
            channel_ref=channel.ref, payload=payload
        )
        if existing is not None:
            # Vale com comanda também: ``client_request_id`` identifica ESTE
            # envio, e o segundo envio do mesmo é replay, não venda nova.
            # Reancora a resposta: se a trava anterior expirou e esta é nova, ela
            # nasce sabendo qual venda responde por esta chave.
            _answer_sale_claim(claim, order_ref=existing.ref)
            return PosSaleResult(
                order_ref=existing.ref, total_q=existing.total_q, fiscal_hint=_sale_fiscal_hint(existing)
            )
        # A venda do terminal acontece DENTRO de um turno de caixa: é no livro dele
        # que a linha `sale` vai nascer. Sem turno aberto não há onde registrar, e
        # a recusa tem de vir ANTES do commit do pedido, não depois.
        shift = _require_open_shift(payload)
        if session is None:
            if _payload_has_tab_identity(payload):
                raise ValueError("Abra um POS tab antes de finalizar.")
            session = _create_direct_checkout_session(
                channel_ref=channel.ref,
                payload=payload,
                operator_username=operator_username,
            )
            direct_checkout = True
        else:
            # A comanda é relida SOB LOCK: os ops de troca (remove_line dos itens
            # atuais + add_line dos novos) só valem para o estado que travamos.
            session = _locked_session(session)
            direct_checkout = False

        result, session, tab_ref = _commit_sale_session(
            session=session,
            channel=channel,
            config=config,
            payload=payload,
            actor=actor,
            operator_username=operator_username,
            direct_checkout=direct_checkout,
            approved_by=approved_by,
        )
        _answer_sale_claim(claim, order_ref=result.order_ref)

    # Fora da transação, e a ordem importa: os callbacks de ``on_commit`` do
    # lifecycle já rodaram e já reescreveram ``order.data``. Escrever o carimbo
    # da comanda ANTES deles fazia a reescrita apagar o ``client_request_id``, e
    # sem essa chave o replay do mesmo envio não encontra a venda — cria a
    # segunda. Medido: no ``main`` o pedido sai com a chave; com o carimbo dentro
    # da transação, sai sem.
    _mark_tab_committed(
        order_ref=result.order_ref,
        tab_ref=tab_ref,
        operator_username=operator_username,
        session_data=session.data,
    )
    # Marcador de transição na trilha da sessão; o mesmo ``session_key`` agora
    # resolve para o Order, cujo lifecycle é auditado pelo OrderEvent.
    session.emit_event("sale_committed", actor=operator_username, payload={
        "order_ref": result.order_ref, "total_q": int(result.total_q),
    })
    logger.info("pos_close_tab order=%s tab=%s session=%s total=%s", result.order_ref, tab_ref, session.session_key, result.total_q)
    order = Order.objects.filter(ref=result.order_ref).first()
    payment_result = {}
    if order is not None:
        order = _reconcile_order_payment_to_total(order)
        payment_result = _settle_pos_sale(order, shift=shift, operator_username=operator_username)
        # A nota segue o primeiro dos dois fatos: o pagamento se liquidar ou a
        # mercadoria sair. No balcão os dois acontecem AQUI — a venda direta
        # fechou paga, a entrega/encomenda sai com a sacola (e a DANFE vai
        # junto). Para a venda presencial que o lifecycle já concluiu, isto é
        # dedupe-hit; para as demais, é o gatilho que ``on_completed`` (fim da
        # jornada) demoraria dias a alcançar. Idempotente e deduplicado no banco.
        try:
            from shopman.shop.services import fiscal as fiscal_service

            fiscal_service.emit(order)
        except Exception:
            logger.warning("pos_close_fiscal_emit_failed order=%s", result.order_ref, exc_info=True)
    return PosSaleResult(
        order_ref=result.order_ref,
        total_q=int(order.total_q if order is not None else result.total_q),
        fiscal_hint=_sale_fiscal_hint(order),
        payment=payment_result,
    )


def _locked_session(session: Session) -> Session:
    """A sessão relida sob ``select_for_update``: quem chegou depois espera aqui."""
    return Session.objects.select_for_update().get(pk=session.pk)


def _sale_claim_scope(channel_ref: str) -> str:
    return f"pos_sale:{channel_ref}"[:64]


def _claim_sale_request(*, channel_ref: str, payload: dict):
    """Trava a chave do submit no banco, para dois envios simultâneos virarem um.

    Usa a ``IdempotencyKey`` do orderman, que já tem a ``UniqueConstraint``
    ``(scope, key)`` — o mesmo mecanismo do commit de sessão e do replay de
    webhook, e por isso nenhuma migração nova. O escopo é o CANAL (e não a
    sessão, como no commit): duas finalizações de balcão direto nascem em
    sessões diferentes, então um escopo por sessão não as encontraria.

    Duas coisas acontecem aqui, e as duas importam:

    1. **A espera.** Quem chega segundo não enxerga a linha da primeira (READ
       COMMITTED esconde INSERT não commitado), tenta inserir a sua e bloqueia
       no índice único até a transação vencedora terminar. Aí volta, relê SOB
       LOCK e continua. O ``select_for_update`` sozinho não bastaria: sobre uma
       linha invisível ele não trava nada.
    2. **A resposta.** A linha travada é onde o vencedor escreve o ``order_ref``
       (ver ``_answer_sale_claim``), e é por isso que ela é devolvida em vez de
       descartada. Perguntar ao pedido no lugar dela não funciona: o
       ``client_request_id`` só chega em ``order.data`` no ``_mark_tab_committed``,
       que roda DEPOIS da transação — no instante em que o perdedor desbloqueia,
       o pedido do vencedor já existe mas ainda está sem a chave. Foi exatamente
       assim que a primeira versão desta trava serializou direitinho e mesmo
       assim criou o segundo pedido.

    Sem ``client_request_id`` não há o que travar — a tela sempre manda um, e
    quem chama a API crua sem chave está dizendo que cada envio é uma venda.
    """
    key = _payload_client_request_id(payload)
    if not key:
        return None
    from shopman.orderman.models import IdempotencyKey

    scope = _sale_claim_scope(channel_ref)
    for _attempt in range(2):
        claim = IdempotencyKey.objects.select_for_update().filter(scope=scope, key=key).first()
        if claim is not None:
            return claim
        try:
            # Savepoint próprio: a violação de unicidade é o resultado ESPERADO
            # do perdedor, e sem ele o erro envenenaria a transação inteira.
            with transaction.atomic():
                # Nasce ``in_progress`` e vira ``done`` quando a venda commita —
                # mesmo ciclo do claim de webhook. O ``expires_at`` é marca de
                # faxina futura, não semântica: hoje nada recolhe a tabela, e a
                # trava fica. Se um dia recolher, o replay tardio ainda acha a
                # venda pelo ``client_request_id`` em ``order.data``.
                return IdempotencyKey.objects.create(
                    scope=scope,
                    key=key,
                    status="in_progress",
                    expires_at=timezone.now() + timedelta(days=1),
                )
        except IntegrityError:
            # Perdemos a corrida do insert — e, por termos bloqueado nele, a
            # vencedora já commitou. A próxima volta do laço enxerga a linha.
            continue
    return IdempotencyKey.objects.select_for_update().filter(scope=scope, key=key).first()


def _claimed_sale(claim) -> Order | None:
    """O pedido que a trava aponta, se o envio anterior já virou venda."""
    if claim is None:
        return None
    order_ref = str(((claim.response_body or {}) if isinstance(claim.response_body, dict) else {}).get("order_ref") or "")
    if not order_ref:
        return None
    return Order.objects.filter(ref=order_ref).first()


def _answer_sale_claim(claim, *, order_ref: str) -> None:
    """Escreve o ``order_ref`` na trava, ainda DENTRO da transação da venda.

    É isto que faz o segundo envio devolver a mesma venda em vez de criar outra:
    quando ele desbloqueia, a linha já traz a resposta. Se a venda falhar, o
    rollback leva a linha junto e a chave volta a estar livre — que é o certo,
    porque não houve venda para replicar.
    """
    if claim is None:
        return
    claim.status = "done"
    claim.response_code = 200
    claim.response_body = {"order_ref": order_ref}
    claim.save(update_fields=["status", "response_code", "response_body"])


def _commit_sale_session(
    *,
    session: Session,
    channel: Channel,
    config: ChannelConfig,
    payload: dict,
    actor: str,
    operator_username: str,
    direct_checkout: bool,
    approved_by: str = "",
):
    """Troca o conteúdo da sessão pelo carrinho do PDV e a commita. Roda sob a trava.

    ``approved_by`` é o gerente que o ``close_sale`` VERIFICOU nesta request — a única
    assinatura que pode ir para a linha do desconto.
    """
    tab_ref = "" if direct_checkout else _session_tab_ref(session)
    tab_display = "" if direct_checkout else _session_tab_display(session)
    fulfillment_type = _payload_fulfillment_type(payload)
    ops = _replace_session_ops(session, payload, operator_username, approved_by=approved_by)
    ops.extend([
        {"op": "set_data", "path": "origin_channel", "value": "pos"},
        {"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type},
        {"op": "set_data", "path": "pos_operator", "value": operator_username},
        {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
    ])
    if direct_checkout:
        ops.append({"op": "set_data", "path": "pos.direct_checkout", "value": True})
    else:
        ops.extend([
            {"op": "set_data", "path": "tab_ref", "value": tab_ref},
            {"op": "set_data", "path": "tab_display", "value": tab_display},
        ])
    client_request_id = _payload_client_request_id(payload)
    if client_request_id:
        ops.extend([
            {"op": "set_data", "path": "client_request_id", "value": client_request_id},
            {"op": "set_data", "path": "pos.client_request_id", "value": client_request_id},
        ])

    session = session_service.modify_session(
        session_key=session.session_key,
        channel_ref=channel.ref,
        ops=ops,
        ctx={"actor": actor},
        channel_config=config.to_dict(),
    )

    result = session_service.commit_session(
        session_key=session.session_key,
        channel_ref=channel.ref,
        idempotency_key=_payload_client_request_id(payload) or session_service.new_idempotency_key(),
        ctx={"actor": actor},
        channel_config=config.to_dict(),
    )
    # ⚠️ O carimbo da comanda e o marcador de trilha saíram daqui de propósito —
    # ver `close_sale`, que os chama DEPOIS de fechar a transação. Escrevê-los
    # aqui dentro os põe antes dos callbacks de `on_commit` do lifecycle, que
    # reescrevem `order.data` inteiro a partir do estado que leram e apagam o
    # `client_request_id`. Sem essa chave o replay não acha a venda e cria a
    # segunda — exatamente o duplo pedido que o claim de idempotência existe
    # para impedir.
    return result, session, tab_ref


def review_sale(
    *,
    channel_ref: str,
    payload: dict,
    operator_username: str,
) -> PosSaleReview:
    """Validate a POS checkout intent without committing the Orderman session."""
    payload = parse_pos_sale_intent(payload, for_commit=True).payload
    channel, _config = _channel_and_config(channel_ref)
    derive_price_overrides(payload, channel=channel)
    session = _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
    if session is None and _payload_has_tab_identity(payload):
        raise ValueError("Abra um POS tab antes de finalizar.")
    # A etiqueta que o KERNEL carimbou vale mais que a que o cliente mandou.
    _stamp_list_prices_from_session(payload, session)
    _ensure_resolved_prices(payload)

    fulfillment_type = _payload_fulfillment_type(payload)
    payment_collection = _payload_payment_collection(payload, fulfillment_type)
    subtotal_q = _payload_subtotal_q(payload)
    discount_q = _payload_discount_q(payload)
    delivery = _resolve_delivery_fee(payload)
    delivery_fee_q = delivery.fee_q
    delivery_day, delivery_slots, delivery_earliest_slot = _schedule_review_context(payload)
    total_q = _payload_total_q(payload)
    tenders = _payload_tenders(
        payload,
        payment_collection=payment_collection,
        total_q=total_q,
        pos_terminal_ref=str(payload.get("pos_terminal_ref") or "").strip(),
        require_complete=False,
    )
    payment_method = _legacy_payment_method(payload, tenders)
    _require_house_account_if_on_account(payload, payment_method=payment_method, tenders=tenders)
    tender_total_q = sum(_int_q(tender.get("amount_q")) for tender in tenders)
    cash_tender_total_q = sum(
        _int_q(tender.get("amount_q")) for tender in tenders if _is_cash_tender(tender)
    )
    tendered_q = _int_q(payload.get("tendered_q"))
    threshold_q = discount_approval_threshold_q()
    warnings: list[dict] = []
    # Fora da área é fato do ENDEREÇO, e o balcão precisa saber antes de
    # prometer a entrega — não bloqueia (o combinado da porta é do operador),
    # mas nunca acontece calado.
    if delivery.blocked:
        distancia = f" ({delivery.distance_km:g} km)" if delivery.distance_km is not None else ""
        warnings.append({
            "code": "delivery_out_of_area",
            "field": "delivery_address",
            "message": (
                f"Este endereço está fora da área de entrega{distancia}. "
                "Confira o combinado antes de finalizar."
            ),
        })
    # Excesso que NÃO é dinheiro não vira troco (ver `change_q`); avisa para o
    # operador corrigir a linha antes de finalizar, em vez de descobrir depois.
    non_cash_excess_q = max(0, tender_total_q - total_q) - min(
        max(0, tender_total_q - total_q), cash_tender_total_q
    )
    if non_cash_excess_q > 0:
        warnings.append({
            "code": "tender_overpaid_non_cash",
            "field": "payment_tenders",
            "message": (
                f"Pagamento sem dinheiro acima do total em R$ {format_money(non_cash_excess_q)}. "
                "Não há troco para cartão ou Pix; ajuste o valor da linha."
            ),
        })
    if payment_method == "cash" and payment_collection == "terminal" and tendered_q <= 0:
        warnings.append({
            "code": "cash_tendered_amount_blank",
            "field": "tendered_q",
            "message": "Valor recebido em dinheiro não informado; o fechamento assumirá valor exato.",
        })
    if payment_method == "cash" and payment_collection == "terminal" and 0 < tendered_q < total_q:
        warnings.append({
            "code": "cash_tendered_amount_too_low",
            "field": "tendered_q",
            "message": "Valor recebido em dinheiro menor que o total da venda.",
        })
    # "Troco para" menor que o total não paga a entrega: avisa na revisão (não
    # bloqueia — o combinado da porta pode mudar; quem manda é o operador).
    change_for_q = _int_q(payload.get("change_for_q"))
    if payment_collection == "on_delivery" and 0 < change_for_q < total_q:
        warnings.append({
            "code": "change_for_below_total",
            "field": "change_for_q",
            "message": (
                f"Troco para R$ {format_money(change_for_q)} é menor que o total "
                f"de R$ {format_money(total_q)}. Confira o combinado com o cliente."
            ),
        })
    if payment_method == "mixed" and total_q > 0 and tender_total_q <= 0:
        warnings.append({
            "code": "payment_tenders_required",
            "field": "payment_tenders",
            "message": "Adicione as linhas do pagamento misto antes de finalizar.",
        })
    elif payment_method == "mixed" and total_q > 0 and tender_total_q < total_q:
        warnings.append({
            "code": "payment_tenders_total_mismatch",
            "field": "payment_tenders",
            "message": "Os pagamentos informados não cobrem o total da venda.",
        })

    approval_reasons = _approval_reasons(payload, discount_q=discount_q, threshold_q=threshold_q)

    # Aviso não-bloqueante de disponibilidade (Q1): no balcão a venda vale mesmo
    # sem estoque (a mercadoria já saiu da vitrine e o canal não auto-rejeita),
    # mas o operador deve VER a falta em vez de descobrir depois.
    from shopman.shop.services import availability

    for item in payload.get("items", []):
        if _is_delivery_fee_item(item):
            continue
        sku = str(item.get("sku") or "")
        try:
            qty = int(item.get("qty", 1))
        except (TypeError, ValueError):
            continue
        if not sku or qty <= 0:
            continue
        decision = availability.decide(sku, qty, channel_ref=channel.ref)
        if decision.get("approved"):
            continue
        try:
            available = int(decision.get("available_qty") or 0)
        except (TypeError, ValueError):
            available = 0
        name = str(item.get("name") or sku)
        warnings.append({
            "code": "item_low_stock",
            "field": "items",
            "message": f"{name}: só {available} em estoque. A venda de balcão vale; confira o estoque depois.",
        })

    return PosSaleReview(
        intent_version=POS_SALE_INTENT_VERSION,
        tab_ref=_session_tab_ref(session) if session is not None else "",
        subtotal_q=subtotal_q,
        discount_q=discount_q,
        delivery_fee_q=delivery_fee_q,
        total_q=total_q,
        payment_method=payment_method,
        payment_collection=payment_collection,
        tender_total_q=tender_total_q,
        tender_count=len(tenders),
        tendered_q=tendered_q,
        # Troco só sai da gaveta, então só o DINHEIRO recebido a mais vira troco.
        # No misto, o excedente é limitado à parcela em espécie: um cartão digitado
        # a mais não é troco (a maquininha cobra o que foi passado), e tratá-lo como
        # troco mandava o operador devolver dinheiro de verdade por um erro de
        # digitação. No dinheiro simples, o troco vem do valor recebido.
        change_q=(
            min(max(0, tender_total_q - total_q), cash_tender_total_q)
            if payment_method == "mixed"
            else (max(0, tendered_q - total_q) if tendered_q else 0)
        ),
        requires_manager_approval=bool(approval_reasons),
        manager_approval_threshold_q=threshold_q,
        receipt_channels=tuple(payload.get("receipt_channels") or ()),
        fiscal_tax_id_requested=bool(str(payload.get("fiscal_tax_id") or "").strip()),
        approval_reasons=tuple(approval_reasons),
        warnings=tuple(warnings),
        delivery_fee_source=delivery.source,
        delivery_distance_km=delivery.distance_km,
        delivery_date=delivery_day.isoformat() if delivery_day else "",
        delivery_slots=delivery_slots,
        delivery_earliest_slot=delivery_earliest_slot,
    )


def _schedule_review_context(payload: dict):
    """A data e as janelas que a tela vai oferecer para este pedido.

    Data em branco no pedido é HOJE — e hoje é o dia da LOJA, lido do relógio do
    servidor. Deixar o dispositivo do balcão decidir parecia inofensivo até se
    lembrar de que um tablet com fuso errado agenda a entrega para ontem.

    ⚠️ **Retirada responde também.** Isto já foi ``_delivery_review_context`` e
    devolvia ``(None, ())`` para retirada, porque a data nasceu dentro do
    formulário de entrega. Mas *quando* é fato do PEDIDO: a casa recebe encomenda
    por telefone para retirar na quinta, e o balcão não tinha onde escrever isso.
    A tela não oferecia porque o servidor não respondia.

    As janelas vêm anotadas com a prontidão do carrinho: a que não cabe volta
    desabilitada e com o motivo, nunca some da lista (ver ``fulfillment_window``).
    """
    from datetime import date as _date

    from shopman.shop.services import fulfillment_window

    raw = str(payload.get("delivery_date") or "").strip()
    if raw:
        try:
            day = _date.fromisoformat(raw)
        except ValueError:
            return None, (), ""
    else:
        day = timezone.localdate()

    # ⚠️ A venda comum de balcão NÃO paga por esta pergunta.
    #
    # `annotate` consulta a prontidão, e a metade observada varre 30 dias de
    # WorkOrder com `django_datetime_cast_date(finished_at)` — não-sargável e
    # sem cache. Medido: +2 queries em toda review, inclusive nas vendas de
    # retirada para agora, que são a esmagadora maioria e nunca vão agendar.
    #
    # Sem data e sem horário no payload não há agendamento em jogo: devolve o
    # dia e uma grade vazia. Quem abre o diálogo busca em `/pos/schedule/`.
    if not raw and not str(payload.get("delivery_time_slot") or "").strip():
        return day, (), ""

    context = fulfillment_window.annotate(day, _payload_skus(payload))
    return day, tuple(context["windows"]), context["earliest_ref"]


def _validate_schedule(payload: dict) -> None:
    """A DATA e a JANELA combinadas têm que ser cumpríveis. Falha FECHADO.

    A review já anota o que não cabe, mas review é tela: quem chega aqui é o
    payload, e payload não passa por tela. Uma fila offline que reenvia um
    rascunho de ontem, um relógio de tablet fora de hora, um operador que trocou o
    item depois de escolher o horário — nos três a promessa impossível entraria
    calada, e quem descobria era o cliente na porta.

    ⚠️ **A data é conferida SEMPRE, mesmo sem horário escolhido**, e é a metade
    que mais custa. Antes ela não era conferida em lugar nenhum: `pos_intent` a
    trata como texto livre de 32 caracteres, e o commit a gravava como viesse.
    Um dígito errado em "Outra data" — `2027` no lugar de `2026` — e o pedido
    nascia `accepted` para daqui a um ano: sem ticket de cozinha, sem baixa de
    estoque, sem fidelidade, sem notificação, e sem nada que alertasse ninguém.
    O cliente tinha pago em dinheiro e ido embora com o comprovante.

    A loja sempre guardou contra isso (`storefront/intents/checkout.py`); o
    balcão era estritamente mais fraco. `max_preorder_days` até viajava na
    projection do agendamento — e ninguém o aplicava, dos dois lados.

    Janela em branco continua passando: "a combinar" é resposta legítima do
    balcão, e exigir hora aqui inventaria fricção que a casa não tem.
    """
    from datetime import date as _date
    from datetime import timedelta as _timedelta

    from shopman.shop.services import fulfillment_window

    raw = str(payload.get("delivery_date") or "").strip()
    hoje = timezone.localdate()
    if raw:
        try:
            day = _date.fromisoformat(raw)
        except ValueError:
            raise ValueError("Data combinada inválida. Escolha uma data da lista.") from None
        if day < hoje:
            raise ValueError("A data combinada já passou. Escolha hoje ou uma data futura.")
        teto = hoje + _timedelta(days=_max_preorder_days())
        if day > teto:
            raise ValueError(
                f"A casa aceita encomenda até {teto.strftime('%d/%m/%Y')}. Escolha uma data mais próxima."
            )
    else:
        day = hoje

    window_ref = str(payload.get("delivery_time_slot") or "").strip()
    if not window_ref:
        return

    error = fulfillment_window.validate(day, window_ref, _payload_skus(payload))
    if error:
        raise ValueError(error)


def _max_preorder_days() -> int:
    """Até quantos dias à frente a casa aceita encomenda (Admin, default 30)."""
    try:
        from shopman.shop.projections import checkout_context

        return max(0, int(checkout_context.preorder_config()[0]))
    except Exception:
        logger.warning("pos: could not read max_preorder_days; using 30", exc_info=True)
        return 30


def _payload_skus(payload: dict) -> list[str]:
    """Os SKUs do carrinho — a pergunta que a prontidão responde."""
    return [
        sku
        for item in (payload.get("items") or [])
        if isinstance(item, dict) and (sku := str(item.get("sku") or "").strip())
    ]


def open_pos_tab(
    *,
    channel_ref: str,
    tab_ref: str,
    actor: str,
    operator_username: str,
) -> Session:
    """Open or load the current order for a POS tab (returns the open session)."""
    channel, config = _channel_and_config(channel_ref)
    ref = normalize_tab_ref(tab_ref)
    tab_display = _ensure_pos_tab(ref, display=_tab_label_from_input(tab_ref, ref))
    session = _get_open_pos_tab_session(channel_ref=channel.ref, tab_ref=ref)
    if session is None:
        session = session_service.create_session(
            channel.ref,
            handle_type="pos_tab",
            handle_ref=ref,
            data={
                "origin_channel": "pos",
                "fulfillment_type": "pickup",
                "tab_ref": ref,
                "tab_display": tab_display,
                "pos_operator": operator_username,
                "last_touched_at": timezone.now().isoformat(),
            },
        )
    else:
        session_service.assign_handle(
            session_key=session.session_key,
            channel_ref=channel.ref,
            handle_type="pos_tab",
            handle_ref=ref,
        )
        session_service.modify_session(
            session_key=session.session_key,
            channel_ref=channel.ref,
            ops=[
                {"op": "set_data", "path": "tab_ref", "value": ref},
                {"op": "set_data", "path": "tab_display", "value": tab_display},
                {"op": "set_data", "path": "pos_operator", "value": operator_username},
                {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
            ],
            ctx={"actor": actor},
            channel_config=config.to_dict(),
        )
        session.refresh_from_db()

    logger.info("pos_open_tab tab=%s session=%s operator=%s", ref, session.session_key, operator_username)
    return session


def save_pos_tab(
    *,
    channel_ref: str,
    payload: dict,
    actor: str,
    operator_username: str,
) -> PosTabResult:
    """Save the current POS cart on its tab and return to the tab grid."""
    payload = parse_pos_sale_intent(payload, for_commit=False).payload
    channel, config = _channel_and_config(channel_ref)
    derive_price_overrides(payload, channel=channel)
    session = _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
    if session is None:
        raise ValueError("Abra um POS tab antes de deixar em espera.")

    before_items = session.items
    tab_ref = _session_tab_ref(session)
    tab_display = _ensure_pos_tab(tab_ref, display=_session_tab_display(session))
    fulfillment_type = _payload_fulfillment_type(payload)
    ops = _replace_session_ops(session, payload, operator_username)
    ops.extend([
        {"op": "set_data", "path": "origin_channel", "value": "pos"},
        {"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type},
        {"op": "set_data", "path": "tab_ref", "value": tab_ref},
        {"op": "set_data", "path": "tab_display", "value": tab_display},
        {"op": "set_data", "path": "pos_operator", "value": operator_username},
        {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
    ])
    client_request_id = _payload_client_request_id(payload)
    if client_request_id:
        ops.extend([
            {"op": "set_data", "path": "client_request_id", "value": client_request_id},
            {"op": "set_data", "path": "pos.client_request_id", "value": client_request_id},
        ])

    with transaction.atomic():
        session_service.modify_session(
            session_key=session.session_key,
            channel_ref=channel.ref,
            ops=ops,
            ctx={"actor": actor},
            channel_config=config.to_dict(),
        )
        # Audit the net change vs the previously-saved snapshot (catches
        # "saved with N items, later saved with fewer"). Emitted atomically.
        _audit_line_diff(session, before=before_items, after=payload.get("items", []), actor=operator_username)
    logger.info("pos_save_tab tab=%s session=%s operator=%s", tab_ref, session.session_key, operator_username)
    return PosTabResult(tab_ref=tab_ref, tab_display=tab_display, session_key=session.session_key)


def clear_pos_tab(*, channel_ref: str, session_key: str, operator_username: str) -> bool:
    """Abandon the open POS tab session, making the tab empty again."""
    session = _get_open_pos_tab_session_by_key(channel_ref=channel_ref, session_key=session_key)
    if session is None:
        return False
    discarded = [
        {"sku": i.get("sku"), "name": i.get("name"), "qty": _audit_qty(i)}
        for i in session.items if not _is_delivery_fee_item(i)
    ]
    fired = bool((session.data or {}).get("fired_lines"))
    with transaction.atomic():
        # Audit BEFORE abandoning: record what was on the tab when discarded.
        # A tab that was fired to the kitchen and then cleared without a sale is
        # the canonical anti-fraud red flag.
        session.emit_event("tab_cleared", actor=operator_username, payload={
            "items": discarded, "item_count": len(discarded), "was_fired": fired,
        })
        cleared = session_service.abandon_session(session_key=session.session_key, channel_ref=channel_ref)
        if cleared and fired:
            # A cozinha não pode continuar produzindo uma comanda descartada.
            from shopman.shop.adapters import kds as kds_adapter

            cancelled = kds_adapter.cancel_open_tickets_for_session(session.session_key)
            if cancelled:
                logger.info(
                    "pos_clear_tab: %d ticket(s) de cozinha cancelados session=%s",
                    cancelled, session.session_key,
                )
    if cleared:
        logger.info("pos_clear_tab tab=%s session=%s operator=%s", _session_tab_ref(session), session.session_key, operator_username)
    return cleared


def rename_pos_tab(
    *,
    channel_ref: str,
    session_key: str,
    new_tab_ref: str,
    actor: str,
    operator_username: str,
) -> Session:
    """Rename an open comanda's handle (e.g. ``Mesa 5`` → ``João``).

    Respects the open-session handle uniqueness constraint
    (``ord_uniq_open_session_handle``): a ref already held by another open
    comanda is rejected before the write. Updates both the session handle and
    the ``tab_ref``/``tab_display`` markers the surface reads — written directly
    (no re-pricing of the open comanda).
    """
    channel, _config = _channel_and_config(channel_ref)
    session = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=session_key)
    if session is None:
        raise PosIntentError(
            code="tab_not_found",
            message="Comanda não encontrada.",
            field="session_key",
            focus="cart",
        )

    try:
        ref = normalize_tab_ref(new_tab_ref)
    except ValueError as exc:
        raise PosIntentError(
            code="invalid_tab_ref",
            message=str(exc) or "Referência de comanda inválida.",
            field="new_tab_ref",
            focus="cart",
        ) from exc

    if ref == _session_tab_ref(session):
        return session

    existing = _get_open_pos_tab_session(channel_ref=channel.ref, tab_ref=ref)
    if existing is not None and existing.session_key != session.session_key:
        raise PosIntentError(
            code="tab_in_use",
            message="Já existe uma comanda aberta com essa referência.",
            field="new_tab_ref",
            focus="cart",
        )

    old_ref = _session_tab_ref(session)
    tab_display = _ensure_pos_tab(ref, display=_tab_label_from_input(new_tab_ref, ref))
    session_service.assign_handle(
        session_key=session.session_key,
        channel_ref=channel.ref,
        handle_type="pos_tab",
        handle_ref=ref,
    )
    session.refresh_from_db()
    session.data = {**(session.data or {}), "tab_ref": ref, "tab_display": tab_display}
    session.save(update_fields=["data"])

    session.emit_event("tab_renamed", actor=operator_username, payload={"from_ref": old_ref, "to_ref": ref})

    logger.info(
        "pos_rename_tab session=%s new_ref=%s operator=%s",
        session.session_key, ref, operator_username,
    )
    return session


def move_pos_tab_lines(
    *,
    channel_ref: str,
    from_session_key: str,
    line_ids: list[str],
    to_session_key: str = "",
    to_tab_ref: str = "",
    close_source_when_empty: bool = False,
    actor: str,
    operator_username: str,
) -> PosMoveResult:
    """Move lines between POS comandas (transfer / split / merge), freezing price.

    - transfer: ``to_session_key`` points at an existing open comanda.
    - split: ``to_tab_ref`` names a new comanda; it is created, then the lines
      move into it (suggested child handle is editable on the surface).
    - merge: pass every ``line_id`` plus ``close_source_when_empty`` so the
      emptied source comanda is released.

    Prices carry over verbatim via the kernel ``move_lines`` op.
    """
    channel, _config = _channel_and_config(channel_ref)
    line_ids = [str(line_id) for line_id in (line_ids or []) if str(line_id).strip()]
    if not line_ids:
        raise PosIntentError(
            code="no_line_ids",
            message="Selecione ao menos um item para mover.",
            field="line_ids",
            focus="cart",
        )

    source = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=from_session_key)
    if source is None:
        raise PosIntentError(
            code="tab_not_found",
            message="Comanda de origem não encontrada.",
            field="from_session_key",
            focus="cart",
        )

    target_created = False
    if to_session_key:
        target = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=to_session_key)
        if target is None:
            raise PosIntentError(
                code="tab_not_found",
                message="Comanda de destino não encontrada.",
                field="to_session_key",
                focus="cart",
            )
    elif to_tab_ref:
        ref = normalize_tab_ref(to_tab_ref)
        if not ref:
            raise PosIntentError(
                code="invalid_tab_ref",
                message="Referência de comanda inválida.",
                field="to_tab_ref",
                focus="cart",
            )
        if _get_open_pos_tab_session(channel_ref=channel.ref, tab_ref=ref) is not None:
            raise PosIntentError(
                code="tab_in_use",
                message="Já existe uma comanda aberta com essa referência.",
                field="to_tab_ref",
                focus="cart",
            )
        tab_display = _ensure_pos_tab(ref, display=_tab_label_from_input(to_tab_ref, ref))
        target = session_service.create_session(
            channel.ref,
            handle_type="pos_tab",
            handle_ref=ref,
            data={
                "origin_channel": "pos",
                "fulfillment_type": "pickup",
                "tab_ref": ref,
                "tab_display": tab_display,
                "pos_operator": operator_username,
                "last_touched_at": timezone.now().isoformat(),
            },
        )
        target_created = True
    else:
        raise PosIntentError(
            code="missing_target",
            message="Informe a comanda de destino.",
            field="to_session_key",
            focus="cart",
        )

    if target.session_key == source.session_key:
        raise PosIntentError(
            code="same_tab",
            message="Origem e destino não podem ser a mesma comanda.",
            field="to_session_key",
            focus="cart",
        )

    try:
        session_service.move_session_lines(
            from_session_key=source.session_key,
            to_session_key=target.session_key,
            channel_ref=channel.ref,
            line_ids=line_ids,
        )
    except Exception as exc:  # noqa: BLE001 - surface kernel errors as a recoverable POS error
        logger.warning(
            "pos_move_tab_lines_failed from=%s to=%s: %s",
            source.session_key, target.session_key, exc,
        )
        if target_created:
            # Roll back the freshly-created split target so no empty comanda lingers.
            # Guard the cleanup: a failure abandoning the target must not mask the
            # original move error the operator needs to see.
            try:
                session_service.abandon_session(session_key=target.session_key, channel_ref=channel.ref)
            except Exception:  # noqa: BLE001 - cleanup is best-effort; original error wins
                logger.exception(
                    "pos_move_tab_lines_rollback_failed target=%s", target.session_key
                )
        raise PosIntentError(
            code="move_failed",
            message=str(exc) or "Falha ao mover itens entre comandas.",
            field="line_ids",
            focus="cart",
        ) from exc

    source.refresh_from_db()
    target.refresh_from_db()

    source_closed = False
    if close_source_when_empty and not source.items:
        source_closed = session_service.abandon_session(
            session_key=source.session_key,
            channel_ref=channel.ref,
        )

    logger.info(
        "pos_move_tab_lines from=%s to=%s count=%s split=%s closed=%s operator=%s",
        source.session_key,
        target.session_key,
        len(line_ids),
        target_created,
        source_closed,
        operator_username,
    )
    return PosMoveResult(
        target=target,
        source=None if source_closed else source,
        source_closed=bool(source_closed),
    )


def _session_to_fire_lines(session: Session) -> list[dict]:
    """Normalize an open comanda's items to source-agnostic KDS fire lines."""
    lines = []
    for item in (session.items or []):
        meta = item.get("meta") or {}
        lines.append({
            "line_id": item.get("line_id", ""),
            "sku": item.get("sku", ""),
            "name": item.get("name") or item.get("sku", ""),
            "qty": int(item.get("qty", 1)),
            "notes": meta.get("notes", ""),
            "meta": meta,
        })
    return lines


def fire_pos_tab(
    *,
    channel_ref: str,
    session_key: str,
    line_ids: list[str] | None = None,
    client_request_id: str = "",
    actor: str,
    operator_username: str,
) -> PosFireResult:
    """Send an open comanda's not-yet-fired courses to the kitchen (KDS).

    Progressive (course-by-course): only the unfired delta is dispatched.
    ``line_ids`` (optional) limits the fire to specific lines; omitted means
    "fire the whole tab" (every still-unfired line). Idempotent — the kitchen
    ticket ledger keyed by ``session_key`` is authoritative, so re-sending a
    course is a no-op and a cancelled course may re-fire (reprint).

    Payment is never stored on the comanda: an open tab is unpaid by nature, so
    "fired + unpaid" is derived downstream (``session_key → Order → payman``) as
    a free anti-fraud signal.
    """
    from shopman.shop.services import kds as kds_service

    channel, _config = _channel_and_config(channel_ref)
    session = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=session_key)
    if session is None:
        raise PosIntentError(
            code="tab_not_found",
            message="Comanda não encontrada.",
            field="session_key",
            focus="cart",
        )

    requested = {str(lid).strip() for lid in (line_ids or []) if str(lid).strip()}
    lines = _session_to_fire_lines(session)
    if requested:
        lines = [ln for ln in lines if ln["line_id"] in requested]
    if not lines:
        raise PosIntentError(
            code="no_lines",
            message="Não há itens para enviar à cozinha.",
            field="line_ids",
            focus="cart",
        )

    tickets = kds_service.fire_lines(session_key=session.session_key, lines=lines)

    # Mirror the fired-line ledger onto the comanda for the cart UI. The kitchen
    # tickets stay authoritative; this marker is a cheap read for the projection
    # and is written directly (no re-pricing of the open comanda).
    fired = sorted(kds_service.fired_line_ids(session.session_key))
    session.data = {**(session.data or {}), "fired_lines": fired}
    session.save(update_fields=["data"])

    session.emit_event("fired", actor=operator_username, payload={
        "lines": [{"sku": ln["sku"], "name": ln["name"], "qty": ln["qty"]} for ln in lines],
        "count": len(tickets),
    })

    logger.info(
        "pos_fire_tab tab=%s session=%s fired_now=%d total_fired=%d operator=%s req=%s",
        _session_tab_ref(session), session.session_key, len(tickets), len(fired),
        operator_username, client_request_id or "-",
    )
    return PosFireResult(session=session, fired_count=len(tickets), fired_lines=tuple(fired))


def cancel_fired_pos_tab_lines(
    *,
    channel_ref: str,
    session_key: str,
    line_ids: list[str],
    actor: str,
    operator_username: str,
) -> PosUnfireResult:
    """Cancel the kitchen fire for specific comanda lines (course returned/wrong).

    The targeted lines leave their live KDS tickets (a ticket is cancelled when
    it empties), drop from ``Session.data["fired_lines"]`` and become re-fireable
    — so a reprint is simply cancel + fire again. The kitchen sees the change via
    the ticket's SSE event.
    """
    from shopman.shop.services import kds as kds_service

    channel, _config = _channel_and_config(channel_ref)
    session = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=session_key)
    if session is None:
        raise PosIntentError(
            code="tab_not_found",
            message="Comanda não encontrada.",
            field="session_key",
            focus="cart",
        )

    targets = [str(lid).strip() for lid in (line_ids or []) if str(lid).strip()]
    if not targets:
        raise PosIntentError(
            code="no_lines",
            message="Selecione itens para cancelar o envio.",
            field="line_ids",
            focus="cart",
        )

    target_set = set(targets)
    unfired_lines = [
        {"sku": i.get("sku"), "name": i.get("name"), "qty": _audit_qty(i)}
        for i in session.items if i.get("line_id") in target_set
    ]
    result = kds_service.unfire_lines(session_key=session.session_key, line_ids=targets)
    fired = sorted(kds_service.fired_line_ids(session.session_key))
    session.data = {**(session.data or {}), "fired_lines": fired}
    session.save(update_fields=["data"])

    session.emit_event("unfired", actor=operator_username, payload={
        "lines": unfired_lines, "line_ids": targets, "cancelled": result["cancelled"],
    })

    logger.info(
        "pos_unfire_tab tab=%s session=%s cancelled=%d trimmed=%d total_fired=%d operator=%s",
        _session_tab_ref(session), session.session_key,
        result["cancelled"], result["trimmed"], len(fired), operator_username,
    )
    return PosUnfireResult(
        session=session,
        cancelled=result["cancelled"],
        trimmed=result["trimmed"],
        fired_lines=tuple(fired),
    )


# A janela do "desfazer venda" do balcão, em minutos. Uma constante só: a
# projection anuncia (capabilities + `can_cancel` das últimas vendas) e o
# cancel impõe — dois números divergindo aqui seriam um botão que promete o
# que o servidor recusa.
RECENT_SALE_MAX_AGE_MINUTES = 5


def _recent_sale_status_allows_cancel(order) -> bool:
    """Se o STATUS do pedido ainda admite o desfazer do balcão.

    `preparing` entra (venda com fire nasce em preparo) e `completed` só quando
    o canal declarou completed→cancelled no lifecycle — os mesmos porquês do
    `cancel_recent_order`, que usa este mesmo predicado.
    """
    allowed = (Order.Status.NEW, Order.Status.ACCEPTED, Order.Status.PREPARING)
    return order.status in allowed or (
        order.status == Order.Status.COMPLETED
        and order.can_transition_to(Order.Status.CANCELLED)
    )


def recent_sale_cancellable(order, *, now=None) -> bool:
    """A janela do desfazer como PERGUNTA (a projection lista; o cancel impõe)."""
    now = now or timezone.now()
    if (now - order.created_at) > timedelta(minutes=RECENT_SALE_MAX_AGE_MINUTES):
        return False
    return _recent_sale_status_allows_cancel(order)


def cancel_recent_order(
    *,
    order_ref: str,
    actor: str,
    max_age_minutes: int = RECENT_SALE_MAX_AGE_MINUTES,
    channel_ref: str | None = None,
    approved_by_username: str = "",
) -> None:
    """Cancel the last POS order if it is still inside the operator window.

    Escopo: SÓ vendas do canal POS. Pedido de outro canal (web/iFood) tem
    fluxo próprio no gestor, com permissão ``manage_orders`` e, no iFood,
    ``cancellation_code`` — a janela de 5 min do PDV não é um atalho.

    O dinheiro devolvido sai da gaveta de AGORA: a devolução é um lançamento
    ``refund`` no turno aberto de quem devolve, apontando para a linha ``sale``
    original. Por isso não importa se o turno da venda já fechou; o que importa
    é que quem devolve tenha um turno aberto para o dinheiro sair de algum lugar.

    ``channel_ref=None`` resolve o canal POS do deployment
    (``SHOPMAN_POS_CHANNEL_REF``) — nunca hardcodar "pdv", senão um deployment
    que renomeia o canal rejeita todo cancelamento legítimo.
    """
    if channel_ref is None:
        from django.conf import settings

        channel_ref = getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv")
    try:
        order = Order.objects.get(ref=order_ref)
    except Order.DoesNotExist as exc:
        raise PosRecentSaleNotFound(f"Pedido {order_ref} não encontrado") from exc

    if channel_ref and order.channel_ref != channel_ref:
        raise ValueError(
            f"Pedido {order_ref} não é do PDV — cancele pelo gestor de pedidos."
        )

    age = timezone.now() - order.created_at
    if age > timedelta(minutes=max_age_minutes):
        raise ValueError(
            f"Pedido {order_ref} criado há mais de {max_age_minutes} minutos — cancelamento não permitido"
        )
    # Os status admitidos vivem em `_recent_sale_status_allows_cancel` — o
    # mesmo predicado que a projection usa para anunciar `can_cancel`. O cancel
    # já cancela os tickets do KDS, reverte estoque e desfaz NFC-e autorizada
    # (_on_cancelled), então a cozinha vê sumir.
    if not _recent_sale_status_allows_cancel(order):
        raise ValueError(f"Pedido {order_ref} não pode ser cancelado (status: {order.status})")
    refund_shift = _shift_for_refund(order, actor=actor)

    # No balcão, dentro da janela, o cliente está na frente: cancelar e devolver
    # são o mesmo gesto. Fora daqui (gestor, de noite) cancelar NÃO devolve: o
    # dinheiro fica pendente até alguém com turno aberto entregá-lo
    # (`payment.refund_cash`), e é isso que o livro e o Payman registram.
    with transaction.atomic():
        cancel(order, reason="pos_operator", actor=actor)
        if refund_shift is not None:
            payment_service.refund_cash(
                order,
                shift=refund_shift,
                actor=_user_for_actor(actor) or refund_shift.operator,
                approved_by=_user_for_actor(approved_by_username) if approved_by_username else None,
                reason="cancelamento no PDV",
            )
    logger.info("pos_cancel_last order=%s actor=%s", order_ref, actor)


def _shift_for_refund(order, *, actor: str):
    """O turno aberto de quem devolve, quando a venda tinha dinheiro no terminal.

    Venda sem dinheiro (pix/cartão) não mexe na gaveta: cancela sem turno. Com
    dinheiro, exige turno aberto de quem está devolvendo: senão o dinheiro
    sairia da gaveta sem linha no livro, que é o buraco de antes.
    """
    if _terminal_cash_amount_q(order) <= 0:
        return None
    # A gaveta que devolve é a do TERMINAL onde a venda foi feita — não "o turno
    # de quem está devolvendo", que deixou de existir quando a custódia virou da
    # gaveta. O `shop` fala com o `cashman` direto: importar o `backstage` daqui
    # inverteria a regra de dependência (backstage ──> shop, nunca o contrário).
    from shopman.cashman.models import Terminal

    ref = str(((order.data or {}).get("pos") or {}).get("terminal_ref") or "").strip()
    terminal = Terminal.objects.filter(ref=ref, is_active=True).first() if ref else None
    if terminal is None:
        terminal = Terminal.objects.filter(is_active=True).order_by("ref").first()
    shift = cash_ledger.open_shift_for_terminal(terminal) if terminal is not None else None
    if shift is None:
        raise ValueError(f"Abra o caixa para devolver o dinheiro da venda {order.ref}.")
    return shift


def reopen_recent_order_for_correction(
    *,
    order_ref: str,
    actor: str,
    reason: str,
    max_age_minutes: int = RECENT_SALE_MAX_AGE_MINUTES,
    approved_by_username: str = "",
) -> None:
    """Cancel a recent POS order with an explicit correction reason."""
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("Informe o motivo da correção.")
    cancel_recent_order(
        order_ref=order_ref,
        actor=actor,
        max_age_minutes=max_age_minutes,
        approved_by_username=approved_by_username,
    )
    order = Order.objects.filter(ref=order_ref).first()
    if order is None:
        return
    data = dict(order.data or {})
    data["pos_correction_reason"] = reason
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def build_session_ops(payload: dict, operator_username: str, *, approved_by: str = "") -> list[dict]:
    """Build canonical Orderman session ops from a POS cart payload.

    ⚠️ ``approved_by`` é o aprovador VERIFICADO, e chega por parâmetro justamente por
    isso. Antes saía de ``payload["manager_approval"]["username"]``, lido
    incondicionalmente: como o validador retorna cedo quando nada exige desafio, um
    corpo com ``{"username": "joyce", "pin": ""}`` gravava no pedido que a Joyce
    aprovou um desconto que ela nunca viu. O padrão coincidia com o verificado só
    quando havia desafio — por isso o defeito era invisível nos testes.

    Vazio é a resposta certa quando ninguém assinou. É o mesmo remédio que o
    cancelamento de venda recente já aplicou: persistir o resolvido, nunca o declarado.
    """
    ops = []
    for item in payload.get("items", []):
        op = {
            "op": "add_line",
            "sku": item["sku"],
            "qty": int(item.get("qty", 1)),
            "unit_price_q": int(item["unit_price_q"]),
        }
        name = str(item.get("name", "") or "").strip()
        if name:
            op["name"] = name
        meta: dict = {}
        notes = str(item.get("notes", "") or "").strip()
        if notes:
            meta["notes"] = notes
        if item.get("price_overridden"):
            # Freeze the operator's unit price: the pricing modifier honors this
            # flag and skips re-pricing. The flag is server-derived
            # (``derive_price_overrides``) — an operator hand-fixed price off the
            # catalog anchor, not an automatic promotion discount — so only a
            # genuine override freezes. Stamp who approved (manager PIN gate).
            meta["price_overridden"] = True
            if approved_by:
                meta["price_approved_by"] = approved_by
        line_discount = _normalize_line_discount(item.get("discount"))
        if line_discount:
            if approved_by:
                line_discount["approved_by"] = approved_by
            meta["manual_discount"] = line_discount
        # O preco de ETIQUETA viaja com a linha da comanda, como o modifier
        # de pricing carimba na venda: sem _list_q na sessao, a review fica
        # sem regua para o "maior desconto ganha" e sem preco para carimbar.
        meta["_list_q"] = int(item["unit_price_q"])
        if meta:
            op["meta"] = meta
        ops.append(op)

    customer_name = str(payload.get("customer_name", "") or "").strip()
    customer_phone = str(payload.get("customer_phone", "") or "").strip()
    customer_tax_id = str(payload.get("customer_tax_id", "") or "").strip()
    # O CPF PEDIDO para esta nota. Campo próprio, e não o do cadastro: ter CPF no
    # CRM não é pedir CPF na nota, e o checkout pode pedir OUTRO documento (o do
    # marido, o da empresa) sem que isso vire identidade de ninguém.
    requested_tax_id = str(payload.get("fiscal_tax_id", "") or "").strip()
    # `customer.email` é o e-mail DO CLIENTE; o endereço para onde ESTA nota vai
    # mora em `receipt.email` e não sobe para cá (o cliente pode pedir que vá para
    # outro endereço, e isso não o redefine).
    customer_email = str(payload.get("customer_email", "") or "").strip()
    persisted_customer = _persist_customer_from_payload(payload, operator_username=operator_username)
    if persisted_customer:
        customer_name = customer_name or persisted_customer.get("name", "")
        customer_phone = customer_phone or persisted_customer.get("phone", "")
        customer_tax_id = customer_tax_id or persisted_customer.get("tax_id", "")
        customer_email = customer_email or persisted_customer.get("email", "")

    if customer_name:
        ops.append({"op": "set_data", "path": "customer.name", "value": customer_name})
    if customer_phone:
        ops.append({"op": "set_data", "path": "customer.phone", "value": customer_phone})
    if customer_tax_id:
        ops.append({"op": "set_data", "path": "customer.tax_id", "value": customer_tax_id})
    if customer_email:
        ops.append({"op": "set_data", "path": "customer.email", "value": customer_email})

    if persisted_customer:
        ops.append({"op": "set_data", "path": "customer.ref", "value": persisted_customer["ref"]})
        ops.append({"op": "set_data", "path": "customer_ref", "value": persisted_customer["ref"]})
        if persisted_customer.get("price_tier"):
            ops.append({
                "op": "set_data", "path": "customer.price_tier",
                "value": persisted_customer["price_tier"],
            })
    else:
        customer = resolve_customer(customer_phone)
        if customer:
            ops.append({"op": "set_data", "path": "customer.ref", "value": customer.ref})
            ops.append({"op": "set_data", "path": "customer_ref", "value": customer.ref})
            if customer.price_tier_id:
                ops.append({
                    "op": "set_data", "path": "customer.price_tier",
                    "value": customer.price_tier.ref,
                })

    fulfillment_type = _payload_fulfillment_type(payload)
    ops.append({"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type})
    # Observações do pedido valem para QUALQUER recebimento (retirada incluída):
    # ficavam presas ao bloco de entrega e a venda de balcão as perdia.
    order_notes = str(payload.get("order_notes") or "").strip()
    if order_notes:
        ops.append({"op": "set_data", "path": "order_notes", "value": order_notes})
    # QUANDO é fato do pedido — retirada agenda como entrega agenda. Ficava
    # dentro do bloco de entrega, e por isso a encomenda de retirada combinada no
    # telefone nascia para hoje, calada.
    _append_schedule_ops(ops, payload)
    if fulfillment_type == "delivery":
        _append_delivery_ops(ops, payload)
        # A LINHA é a cobrança (``Order.total_q`` é a soma das linhas), então ela
        # nasce da taxa RESOLVIDA — a mesma que a review mostrou ao operador.
        delivery_fee_q = _payload_delivery_fee_q(payload)
        if delivery_fee_q > 0:
            ops.append({
                "op": "add_line",
                "sku": "__DELIVERY_FEE__",
                "name": "Taxa de entrega",
                "qty": 1,
                "unit_price_q": delivery_fee_q,
                "meta": {"type": "delivery_fee", "non_production": True},
            })

    payment_collection = _payload_payment_collection(payload, fulfillment_type)
    total_q = _payload_total_q(payload)

    # O turno da venda NÃO é etiqueta no pedido: é a linha `sale` no livro do
    # turno (cashman). O terminal fica, porque é dado do pedido (recibo, fiscal).
    pos_terminal_ref = str(payload.get("pos_terminal_ref") or "").strip()
    if pos_terminal_ref:
        ops.append({"op": "set_data", "path": "pos.terminal_ref", "value": pos_terminal_ref})
    intent_version = str(payload.get("intent_version") or "").strip()
    if intent_version:
        ops.append({"op": "set_data", "path": "pos.intent_version", "value": intent_version})
    memory_action = str(payload.get("customer_memory_action") or "").strip()
    if memory_action:
        ops.append({"op": "set_data", "path": "pos.customer_memory_action", "value": memory_action})

    tenders = _payload_tenders(
        payload,
        payment_collection=payment_collection,
        total_q=total_q,
        pos_terminal_ref=pos_terminal_ref,
    )
    payment_method = _legacy_payment_method(payload, tenders)
    ops.append({"op": "set_data", "path": "payment.method", "value": payment_method})
    ops.append({"op": "set_data", "path": "payment.collection", "value": payment_collection})
    ops.append({"op": "set_data", "path": "payment.amount_q", "value": total_q})

    tendered_q = payload.get("tendered_q")
    if tendered_q and payment_method == "cash":
        tendered_q = int(tendered_q)
        ops.append({"op": "set_data", "path": "payment.tendered_q", "value": tendered_q})
        ops.append({"op": "set_data", "path": "payment.change_q", "value": max(0, tendered_q - total_q)})
    # "Troco para quanto?" do dinheiro NA ENTREGA — a chave canônica que o
    # despacho já lê (operator_orders.change_out_suggested_q → courier_out no
    # livro do caixa) e o card do gestor exibe. O intent só a mantém no COD.
    change_for_q = _int_q(payload.get("change_for_q"))
    if payment_collection == "on_delivery" and change_for_q > 0:
        ops.append({"op": "set_data", "path": "payment.change_for_q", "value": change_for_q})
    if tenders:
        ops.append({"op": "set_data", "path": "payment.tenders", "value": tenders})
    cash_received_q = _cash_received_q(tenders)
    if cash_received_q > 0:
        ops.append({"op": "set_data", "path": "payment.cash_received_q", "value": cash_received_q})

    # EMITIR OU NÃO NÃO É ESCOLHA DE QUEM ESTÁ NO CAIXA. Havia um toggle "Emitir
    # nota fiscal" na tela, e ele não era só ruído: como o CPF só virava
    # `fiscal.tax_id` quando o toggle estava ligado, um operador que digitava o
    # CPF com o toggle desligado via a nota sair mesmo assim (o resolver emite
    # por forma de pagamento) e sair como CONSUMIDOR NÃO IDENTIFICADO. Duas
    # chaves para uma intenção, discordando em silêncio, com o cliente achando
    # que tinha CPF na nota.
    #
    # Quem decide é a REGRA (`SHOPMAN_FISCAL_EMISSION_RESOLVER`): forma de
    # pagamento, liquidação diferida, e o pedido do consumidor. O único sinal que
    # vem do balcão é este: pedir CPF na nota. Digitar o documento É o pedido.
    if requested_tax_id:
        ops.append({"op": "set_data", "path": "fiscal.tax_id", "value": requested_tax_id})

    receipt_channels = list(payload.get("receipt_channels") or [])
    receipt_email = str(payload.get("receipt_email", "") or "").strip()
    ops.append({"op": "set_data", "path": "receipt.channels", "value": receipt_channels})
    if receipt_email:
        ops.append({"op": "set_data", "path": "receipt.email", "value": receipt_email})

    manual_discount = _payload_manual_discount(payload)
    if manual_discount:
        ops.extend([
            {"op": "set_data", "path": "manual_discount.type", "value": manual_discount.get("type", "percent")},
            {"op": "set_data", "path": "manual_discount.value", "value": manual_discount.get("value", 0)},
            {"op": "set_data", "path": "manual_discount.discount_q", "value": int(manual_discount.get("discount_q", 0))},
            {"op": "set_data", "path": "manual_discount.reason", "value": manual_discount.get("reason", "")},
        ])
        if approved_by:
            ops.append({"op": "set_data", "path": "manual_discount.approved_by", "value": approved_by})
    return ops


def _bare_username(value: str) -> str:
    """O username por trás de um actor: ``"pos:joyce"``, ``"gestor:joyce"`` ou ``"joyce"``."""
    raw = str(value or "").strip()
    return raw.split(":", 1)[1] if ":" in raw else raw


def _verify_manager_pin(username: str, pin: str, *, operator_username: str = ""):
    """Resolve a manager by username and verify their override PIN.

    A short, rate-limited PIN challenge replaces account passwords in the sale
    payload. Reuses doorman's generic ``PinCredential`` (HMAC hash + lockout)
    and the same ``cashman.adjust_shift`` permission the override gates
    require. Returns the authorizing user, or ``None`` if the challenge fails.

    ⚠️ ``operator_username`` é o que faz da segunda assinatura uma SEGUNDA
    pessoa. Antes bastava ter ``is_staff`` + ``adjust_shift``, e o gerente que
    também opera o balcão (a Joyce do seed tem os dois) se autorizava: escolhia
    o próprio nome em "Quem autoriza?", digitava o próprio PIN e a exceção saía
    com quem faz e quem autoriza sendo a mesma pessoa. Isso não é aprovação, é
    um passo a mais no mesmo ato — e era exatamente a fraude que o fluxo de
    exceção do caixa existe para impedir.
    """
    from django.contrib.auth import get_user_model
    from shopman.doorman.models import PinCredential

    user_model = get_user_model()
    try:
        user = user_model.objects.get(username=username, is_active=True, is_staff=True)
    except user_model.DoesNotExist:
        return None
    if not user.has_perm("cashman.adjust_shift"):
        return None
    operator = _bare_username(operator_username)
    if operator and _bare_username(username) == operator:
        logger.warning("pos_manager_self_approval_refused operator=%s", operator)
        return None
    try:
        credential = user.pin_credential
    except PinCredential.DoesNotExist:
        return None
    return user if credential.verify(pin) else None


def _verify_manager_badge(badge: str, *, operator_username: str = ""):
    """Resolve o gerente pelo CRACHÁ, com a mesma permissão que o PIN exige.

    A sangria e o pedido de troco são a hora em que o gerente mais aparece no
    balcão, e era justamente onde o crachá não valia: o desafio só aceitava
    username + PIN, então quem tinha o crachá no pescoço digitava mesmo assim.

    ⚠️ Crachá e PIN são o mesmo nível de prova aqui, e isso é decisão, não
    descuido. Os dois identificam a MESMA pessoa contra a mesma credencial
    (`PinCredential`), os dois exigem `cashman.adjust_shift`, e a assinatura que
    vai para `Entry.approved_by` é a mesma. O crachá é posse, o PIN é
    conhecimento; num balcão onde o gerente é chamado com a fila andando, exigir
    os dois trocaria segurança real por atrito — e atrito é o que faz o balcão
    inventar jeito de não chamar ninguém.

    ⚠️ Resolve pelo `doorman` direto, e não pelo helper equivalente do
    `backstage`: o `shop` não importa superfície (regra de dependência do
    projeto, com teste que trava). É a mesma escolha que o `_verify_manager_pin`
    aqui do lado já fazia, pelo mesmo motivo.

    ⚠️ ``operator_username`` recusa a autoassinatura, exatamente como no PIN. O
    gerente que também opera o balcão (a Joyce do seed tem ``operate_pos`` E
    ``adjust_shift``) encostaria o próprio crachá e a exceção sairia com quem faz
    e quem autoriza sendo a mesma pessoa — o que não é aprovação, é um passo a
    mais no mesmo ato. Se o crachá ficasse de fora, ele seria a porta por onde a
    fraude voltaria.
    """
    from shopman.doorman.models import PinCredential

    user = PinCredential.resolve_by_badge(badge)
    if user is None or not user.is_active or not user.is_staff:
        return None
    if not user.has_perm("cashman.adjust_shift"):
        return None
    operator = _bare_username(operator_username)
    if operator and _bare_username(user.get_username()) == operator:
        logger.warning("pos_manager_self_approval_refused operator=%s via=badge", operator)
        return None
    return user


def _approval_reasons(payload: dict, *, discount_q: int, threshold_q: int) -> list[str]:
    """Os gatilhos que chamaram o gerente, na ordem em que a tela deve contá-los.

    Publicado na review para o diálogo de autorização dizer o que está sendo
    autorizado. Sem isto a tela só sabia QUE precisava de gerente, e a copy
    falava de desconto mesmo quando o gatilho era preço alterado.
    """
    reasons: list[str] = []
    if threshold_q > 0 and discount_q > threshold_q:
        reasons.append("discount_over_threshold")
    if _payload_has_price_override(payload):
        reasons.append("price_override")
    return reasons


def validate_manager_approval(payload: dict, *, operator_username: str):
    """O desafio gerencial do desconto. Devolve o ``User`` que assinou, ou ``None``.

    Devolve, e não apenas valida, porque **quem assina a linha é o aprovador
    verificado** — nunca o nome que veio no corpo. Ver ``build_session_ops``: era de lá
    que o carimbo saía, lendo ``manager_approval.username`` sem nenhuma verificação.

    Delega ao ``validate_manager_override``, que é a versão madura do MESMO desafio:
    aceita crachá **ou** usuário+PIN, recusa autoassinatura nas duas portas e devolve o
    usuário verificado. Eram dois validadores para uma regra só, e o de desconto era o
    atrasado — pedia PIN mesmo de quem estava com o crachá na mão.

    ``None`` quando não houve motivo para desafio: sem desafio não há assinatura, e é
    justamente esse o caso em que o carimbo era fabricado.
    """
    threshold_q = discount_approval_threshold_q()
    discount_q = _payload_discount_q(payload)
    reasons = _approval_reasons(payload, discount_q=discount_q, threshold_q=threshold_q)
    if not reasons:
        return None

    # A copy viaja junto com a delegação. O desafio é o mesmo, mas o que o operador
    # pode FAZER a respeito não é: no caixa ele chama o gerente; aqui ele também pode
    # reduzir o desconto. Delegar sem levar o texto trocaria uma saída por um beco.
    approver = validate_manager_override(
        payload.get("manager_approval"),
        operator_username=operator_username,
        action="discount",
        message="Esta venda exige aprovação gerencial.",
        recovery_required=(
            "Peça a um gerente autorizado para aprovar com o crachá ou o PIN antes de finalizar."
        ),
        recovery_invalid="Revise o gerente e o PIN, ou reduza o desconto / ajuste o preço.",
    )
    logger.info(
        "pos_manager_approval operator=%s approved_by=%s discount_q=%s reasons=%s",
        operator_username,
        approver.get_username(),
        discount_q,
        ",".join(reasons),
    )
    return approver


def validate_manager_override(
    approval: dict | None,
    *,
    operator_username: str,
    action: str,
    message: str = "Esta operação exige aprovação gerencial.",
    recovery_required: str = "Peça a um gerente autorizado para aprovar com o crachá ou o PIN.",
    recovery_invalid: str = "Revise o gerente e o PIN.",
):
    """Gate an exceptional POS operation behind the manager PIN challenge.

    Cancelar uma venda fechada é exceção auditada (anti-fraude), não fluxo do
    operador: exige o mesmo desafio de PIN gerencial do desconto acima do teto
    (``cashman.adjust_shift``), sempre — não há limiar.

    Devolve o ``User`` AUTORIZADO, e é ele que vai para o ``approved_by`` da
    linha do livro. Antes o validador conferia username+PIN+permissão e jogava o
    User fora; quem persistia era uma segunda consulta pelo mesmo username,
    exigindo só ``is_active + is_staff`` — sem re-checar ``adjust_shift``.
    Validar A e persistir B dá o mesmo resultado enquanto os dois momentos ficam
    na mesma request, e vira buraco pronto no primeiro refactor que os separar.
    """
    approval = approval or {}
    username = str(approval.get("username") or "").strip()
    pin = str(approval.get("pin") or "")
    # O crachá é a segunda porta do MESMO desafio. Ver `_verify_manager_badge`.
    badge = str(approval.get("badge") or "").strip()

    if not badge and (not username or not pin):
        raise PosIntentError(
            code="manager_approval_required",
            message=message,
            field="manager_approval",
            focus="approval",
            recovery=recovery_required,
        )
    # As duas portas recebem quem OPERA, e pelo mesmo motivo: a segunda
    # assinatura existe para haver duas pessoas. Passar o operador só no PIN
    # deixaria o crachá como a porta por onde o gerente-que-opera continua se
    # autorizando — e a porta nova seria a fraude de novo.
    approver = (
        _verify_manager_badge(badge, operator_username=operator_username)
        if badge
        else _verify_manager_pin(username, pin, operator_username=operator_username)
    )
    if approver is None:
        raise PosIntentError(
            code="manager_approval_invalid",
            message="Aprovação gerencial inválida.",
            field="manager_approval",
            focus="approval",
            recovery=recovery_invalid,
        )
    # Quem assina é o APROVADOR resolvido, não o que veio no corpo: com crachá o
    # `username` chega vazio, e a linha de auditoria saía `approved_by=` em
    # branco — justamente a informação pela qual ela existe. Mesmo erro que o
    # cancelamento tinha ao persistir a assinatura; este ficou no log e passou.
    logger.info(
        "pos_manager_override action=%s operator=%s approved_by=%s via=%s",
        action,
        operator_username,
        approver.get_username(),
        "badge" if badge else "pin",
    )
    return approver


def _replace_session_ops(
    session: Session, payload: dict, operator_username: str, *, approved_by: str = ""
) -> list[dict]:
    """Build ops that replace mutable POS payload fields on an existing session.

    Preserva o ``line_id`` por SKU ao reconstruir as linhas: o PDV tem uma linha por
    SKU, então o remove+readd do fechamento pode manter a identidade durável de cada
    linha. Sem isso, os line_ids são regerados e o pedido committado dispara DE NOVO
    pra cozinha (o ledger de fire é por line_id) — comanda preparada em dobro.
    """
    line_id_by_sku: dict[str, str] = {}
    for item in (session.items or []):
        sku = item.get("sku")
        line_id = item.get("line_id")
        if sku and line_id and sku not in line_id_by_sku:
            line_id_by_sku[sku] = line_id

    ops = [
        {"op": "remove_line", "line_id": item["line_id"]}
        for item in (session.items or [])
        if item.get("line_id")
    ]
    ops.extend([
        {"op": "set_data", "path": "customer", "value": {}},
        {"op": "set_data", "path": "payment", "value": {}},
        {"op": "set_data", "path": "fiscal", "value": {}},
        {"op": "set_data", "path": "receipt", "value": {}},
        {"op": "set_data", "path": "manual_discount", "value": {}},
        {"op": "set_data", "path": "client_request_id", "value": ""},
        {"op": "set_data", "path": "pos.client_request_id", "value": ""},
        {"op": "set_data", "path": "delivery_address", "value": ""},
        {"op": "set_data", "path": "delivery_address_structured", "value": {}},
        {"op": "set_data", "path": "delivery_date", "value": ""},
        {"op": "set_data", "path": "delivery_time_slot", "value": ""},
        {"op": "set_data", "path": "delivery_fee_q", "value": 0},
        {"op": "set_data", "path": "delivery_fee_override_q", "value": None},
        {"op": "set_data", "path": "order_notes", "value": ""},
    ])
    add_ops = build_session_ops(payload, operator_username, approved_by=approved_by)
    for op in add_ops:
        if op.get("op") == "add_line":
            preserved = line_id_by_sku.pop(op.get("sku"), None)  # consome (1 linha/SKU)
            if preserved:
                op["line_id"] = preserved
    ops.extend(add_ops)
    return ops


def _payload_fulfillment_type(payload: dict) -> str:
    value = str(payload.get("fulfillment_type") or "pickup").strip().lower()
    if value == "delivery":
        return "delivery"
    return "pickup"


def _payload_payment_collection(payload: dict, fulfillment_type: str) -> str:
    value = str(payload.get("payment_collection") or "terminal").strip().lower()
    if fulfillment_type == "delivery" and value == "on_delivery":
        return "on_delivery"
    return "terminal"


def _payload_total_q(payload: dict) -> int:
    return max(0, _payload_subtotal_q(payload) - _payload_discount_q(payload) + _payload_delivery_fee_q(payload))


def _payload_subtotal_q(payload: dict) -> int:
    subtotal_q = 0
    for item in payload.get("items", []):
        try:
            subtotal_q += int(item.get("qty", 1)) * int(item.get("unit_price_q", 0))
        except (TypeError, ValueError):
            continue
    return max(0, subtotal_q)


def _ensure_resolved_prices(payload: dict) -> None:
    """A review nao pode prometer troco de um total que ela nao conseguiu somar.

    Com itens no payload e subtotal zerado, o preco nao foi resolvido (item sem
    unit_price_q e sem sessao para carimbar). Recusa clara, em vez de revisao
    que devolve total 0 e troco do valor inteiro entregue — o fechamento real
    precifica no kernel, e a tela mentiria para o operador.
    """
    if payload.get("items") and _payload_subtotal_q(payload) <= 0:
        raise PosIntentError(
            code="price_not_resolved",
            message="Nao foi possivel resolver o preco dos itens do carrinho.",
            field="items",
            focus="search",
            recovery="Reabra a comanda para o servidor reaplicar os precos de tabela.",
        )


def _payload_discount_q(payload: dict) -> int:
    order_discount_q = int(_payload_manual_discount(payload).get("discount_q", 0) or 0)
    return order_discount_q + _payload_line_discounts_q(payload)


def _normalize_line_discount(raw) -> dict:
    """Normalize an operator per-line discount (percent only) from the intent."""
    if not isinstance(raw, dict):
        return {}
    try:
        value = float(raw.get("value") or 0)
    except (TypeError, ValueError):
        return {}
    if value <= 0:
        return {}
    reason = str(raw.get("reason") or "cortesia").strip()[:120] or "cortesia"
    return {"type": "percent", "value": value, "reason": reason}


def _stamp_list_prices_from_session(payload: dict, session) -> None:
    """Carimba no payload o preço de ETIQUETA que a sessão guarda, por SKU.

    O ``meta._list_q`` é escrito pelos modifiers de pricing e é a mesma fonte que
    o "maior desconto ganha" consulta. Vindo da sessão, não do navegador, a
    review mede o desconto de linha contra o mesmo número que o kernel — e o
    campo do intent fica sendo só o fallback da venda sem comanda.
    """
    if session is None:
        return
    # O preco de referencia da sessao: o _list_q que o kernel carimba, ou —
    # antes do carimbo (comanda salva direto no balcao) — o proprio
    # unit_price_q da linha, que e o preco que a tela mostrou.
    price_by_sku: dict[str, int] = {}
    for item in (session.items or []):
        sku = str(item.get("sku") or "")
        if not sku:
            continue
        list_q = _int_q((item.get("meta") or {}).get("_list_q"))
        price_q = _int_q(item.get("unit_price_q"))
        price_by_sku[sku] = list_q or price_q
    if not price_by_sku:
        return
    for item in payload.get("items", []):
        sku = str(item.get("sku") or "")
        price_q = price_by_sku.get(sku)
        if not price_q:
            continue
        # So preenche o cobrado quando o payload nao declarou preco (o override
        # do operador viaja declarado e nao pode ser sobrescrito). A etiqueta
        # sempre e devolvida: e a regua do "maior desconto ganha".
        if _int_q(item.get("unit_price_q")) <= 0:
            item["unit_price_q"] = price_q
        item["list_price_q"] = price_q


def _payload_line_discounts_q(payload: dict) -> int:
    """Quanto os descontos manuais de LINHA tiram do subtotal — pela regra do kernel.

    A política é "maior desconto ganha, um por item" (``DiscountModifier``): o
    manual da linha é medido contra o preço de ETIQUETA e só vale se for MAIOR
    que o desconto automático que já venceu aquela linha; vencendo, ele
    SUBSTITUI o automático, não se soma a ele.

    Esta função media o mesmo número duas vezes errado. Contava o percentual
    sobre o preço JÁ descontado (não sobre a etiqueta) e contava SEMPRE, mesmo
    quando o kernel ia descartar o manual. O efeito na tela: uma cortesia de 10%
    numa Tabatière que já levava "Semana do Pão −15%" prometia R$ 1,02 de
    desconto que a venda não dava. Provado numa venda real (PDV-260826-V03): o
    checkout exibiu total R$ 44,78 e TROCO R$ 25,22, o pedido selou R$ 45,80 e
    registrou troco R$ 24,20 — o operador devolveria R$ 1,02 a mais do que a
    gaveta contava, em toda venda com desconto de linha perdedor.

    O subtotal da review é a soma dos ``unit_price_q`` (já pós-automático), então
    o que este desconto ainda tira é só a DIFERENÇA entre o manual e o automático
    que ele substitui — zero quando perde.
    """
    total = 0
    for item in payload.get("items", []):
        line_discount = _normalize_line_discount(item.get("discount"))
        if not line_discount:
            continue
        try:
            unit_price_q = int(item.get("unit_price_q", 0))
            qty = int(item.get("qty", 1))
        except (TypeError, ValueError):
            continue
        # Sem etiqueta declarada, a linha não tem desconto automático a bater:
        # etiqueta e preço cobrado são o mesmo número.
        list_price_q = _int_q(item.get("list_price_q")) or unit_price_q
        auto_per_unit = max(0, list_price_q - unit_price_q)
        manual_per_unit = min(
            int(round(list_price_q * line_discount["value"] / 100)),
            list_price_q,
        )
        gain_per_unit = max(0, manual_per_unit - auto_per_unit)
        total += min(gain_per_unit, unit_price_q) * max(0, qty)
    return total


def _payload_has_price_override(payload: dict) -> bool:
    """True if any line carries a unit-price override requiring manager approval.

    Reads the ``price_overridden`` flag DERIVED server-side by
    ``derive_price_overrides`` (a comparison of the declared ``unit_price_q``
    against the canonical POS catalog price). The client's advisory flag is never
    trusted here — derive first, then gate on the derivation."""
    return any(item.get("price_overridden") for item in payload.get("items", []))


def _canonical_pos_unit_price_q(sku: str, channel: Channel, qty: int) -> int | None:
    """Resolve the catalog price the POS channel would charge for a line.

    Mirrors the ``pricing.item`` modifier that reprices every non-frozen line on
    commit: the same customer-agnostic, qty-aware cascade (customer tier is not
    resolved at commit — POS ``ctx`` carries no customer — so employee pricing
    stays a post-pricing modifier). This is the price a *legitimate* line already
    carries in the payload, because happy-hour and employee discounts are
    applied by later modifiers on commit, never baked into the quoted
    ``unit_price_q``. Returns ``None`` when the SKU has no catalog anchor.
    """
    from shopman.shop.handlers.pricing import OffermanPricingBackend

    try:
        return OffermanPricingBackend().get_price(sku, channel, qty=max(1, int(qty)))
    except Exception:
        logger.debug("pos_canonical_price_lookup_failed sku=%s", sku, exc_info=True)
        return None


def derive_price_overrides(payload: dict, *, channel: Channel) -> None:
    """Stamp ``price_overridden`` on lines the OPERATOR fixed off the catalog.

    Server-side authority over the price-trust gate. ``price_overridden`` marks the
    one manual action that both freezes a line (the pricing modifier honors it and
    skips re-pricing — see ``build_session_ops``) and needs a manager PIN: the
    operator fixing a unit price by hand (numpad "Preço") away from the catalog
    anchor. It is DERIVED, never taken raw — stamped only when the client declared
    that override intent AND the fixed price differs from the canonical POS catalog
    price (or the SKU has no catalog anchor, so there is no trusted price to charge
    against, and the line needs manager sign-off).

    Why the intent gate, not a bare catalog comparison:

    * Automatic system discounts (happy-hour, promotion) are NOT operator
      overrides. They are applied by later modifiers on commit; a previous persist
      bakes the discounted price into ``unit_price_q`` and the reload echoes it
      back, so a plain catalog comparison read every promotion line as an
      override and demanded a manager for a cart nobody discounted (the seed bug
      B1-2). Those lines carry no override intent, so they no longer read as one.
    * A crafted request that lowers a price WITHOUT the intent flag cannot
      undercharge, so it needs no gate here: without the flag the line is never
      frozen, and the ``internal`` pricing modifier (POS is always internal)
      reprices it back to catalog − legitimate discounts on commit. The only
      undercharge vector is a frozen override, and that is exactly what this catches
      — a flagged line below (or above) the anchor still fires the manager gate.
    """
    for item in payload.get("items", []):
        if _is_delivery_fee_item(item):
            continue
        operator_fixed_price = bool(item.get("price_overridden"))
        try:
            unit_price_q = int(item.get("unit_price_q", 0))
            qty = int(item.get("qty", 1))
        except (TypeError, ValueError):
            item["price_overridden"] = True
            continue
        canonical_q = _canonical_pos_unit_price_q(str(item.get("sku") or ""), channel, qty)
        item["price_overridden"] = canonical_q is None or (
            operator_fixed_price and unit_price_q != canonical_q
        )


def _payload_manual_discount(payload: dict) -> dict:
    manual_discount = payload.get("manual_discount") or {}
    if not isinstance(manual_discount, dict):
        return {}

    subtotal_q = _payload_subtotal_q(payload)
    if subtotal_q <= 0:
        return {}

    type_ref = str(manual_discount.get("type") or "percent").strip().lower()
    if type_ref not in {"percent", "fixed"}:
        type_ref = "percent"

    value = _decimal_discount_value(manual_discount.get("value"))
    fallback_q = _int_q(manual_discount.get("discount_q"))
    if value > 0:
        if type_ref == "fixed":
            discount_q = int((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            discount_q = int((Decimal(subtotal_q) * value / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        discount_q = fallback_q
        value = _decimal_discount_value(manual_discount.get("value") or 0)

    discount_q = min(subtotal_q, max(0, discount_q))
    if discount_q <= 0:
        return {}

    reason = str(manual_discount.get("reason") or "cortesia").strip()[:120] or "cortesia"
    return {
        "type": type_ref,
        "value": float(value) if value > 0 else manual_discount.get("value", 0),
        "discount_q": discount_q,
        "reason": reason,
    }


def _decimal_discount_value(value) -> Decimal:
    if isinstance(value, str):
        raw = value.strip()
        raw = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    else:
        raw = str(value or "0")
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return max(Decimal("0"), parsed)


@dataclass(frozen=True)
class DeliveryFeeResolution:
    """A taxa de entrega desta venda, e de onde ela veio."""

    fee_q: int
    #: "" (endereço ainda em branco) · "zone" · "distance" · "default" ·
    #: "manual" (exceção digitada pelo operador) · "blocked" (fora da área).
    source: str = ""
    distance_km: float | None = None
    blocked: bool = False


#: Onde a resolução fica guardada DENTRO do payload. O payload atravessa a
#: review e o commit sendo lido várias vezes, e resolver de novo custaria
#: consulta ao banco e — no pior caso — uma chamada de geocodificação por
#: leitura. Mesma técnica do `derive_price_overrides`, que também escreve no
#: payload em vez de devolver um segundo dado para alguém carregar.
_DELIVERY_FEE_RESOLUTION_KEY = "_resolved_delivery_fee"


def _resolve_delivery_fee(payload: dict) -> DeliveryFeeResolution:
    """A taxa vem do MOTOR (zona/faixa), não da digitação do operador.

    O balcão digitava a taxa num campo livre, e um número digitado é um segundo
    dono do preço: a zona de CEP, a faixa de distância e o frete grátis acima de
    um valor — tudo configurado no Admin e tudo já aplicado na loja — passavam
    ao largo. Duas vendas do mesmo endereço saíam com taxas diferentes conforme
    quem estava no caixa.

    Agora é o mesmo caminho da loja: ``DeliveryFeeModifier._resolve`` (zona de
    exceção → faixa de distância → taxa-padrão) sobre o endereço estruturado que
    o PDV já captura, com a renúncia de frete grátis por valor de compra por
    cima. Um motor, duas superfícies.

    Resta UMA porta para a digitação, e ela é explícita: ``delivery_fee_override_q``
    é a exceção que o operador assume (combinado de porta, cortesia). Ela nunca
    acontece por omissão — o campo em branco não vira zero, vira "resolva".
    """
    cached = payload.get(_DELIVERY_FEE_RESOLUTION_KEY)
    if isinstance(cached, DeliveryFeeResolution):
        return cached

    resolution = _compute_delivery_fee(payload)
    payload[_DELIVERY_FEE_RESOLUTION_KEY] = resolution
    return resolution


def _compute_delivery_fee(payload: dict) -> DeliveryFeeResolution:
    if _payload_fulfillment_type(payload) != "delivery":
        return DeliveryFeeResolution(fee_q=0)

    override = payload.get("delivery_fee_override_q")
    if override not in (None, ""):
        return DeliveryFeeResolution(fee_q=max(0, _int_q(override)), source="manual")

    address = payload.get("delivery_address_structured")
    address = address if isinstance(address, dict) else {}
    postal_code = str(address.get("postal_code") or "").strip()
    neighborhood = str(address.get("neighborhood") or "").strip()
    lat, lng = address.get("latitude"), address.get("longitude")
    if not postal_code and not neighborhood and lat in (None, "") and lng in (None, ""):
        # Endereço ainda em branco: não há o que resolver, e zero aqui é
        # "pendente", não "grátis" — quem lê distingue pelo `source` vazio.
        return DeliveryFeeResolution(fee_q=0)

    from shopman.shop.modifiers import DeliveryFeeModifier

    base_fee_q, distance_km, blocked = DeliveryFeeModifier._resolve(
        postal_code, neighborhood, lat, lng, address_text=_delivery_address_text(payload, address)
    )
    if blocked:
        return DeliveryFeeResolution(fee_q=0, source="blocked", distance_km=distance_km, blocked=True)

    source = "zone" if postal_code or neighborhood else "distance"
    if distance_km is None and not (postal_code or neighborhood):
        source = "default"
    fee_q = _waive_delivery_fee_if_due(base_fee_q, _payload_subtotal_q(payload) - _payload_discount_q(payload))
    return DeliveryFeeResolution(fee_q=fee_q, source=source, distance_km=distance_km)


def _delivery_address_text(payload: dict, address: dict) -> str:
    return str(
        address.get("formatted_address")
        or payload.get("delivery_address")
        or ""
    ).strip()


def _waive_delivery_fee_if_due(base_fee_q: int, merchandise_q: int) -> int:
    """Frete grátis acima de um valor — o limiar permanente da loja.

    A promoção `free_delivery` (que depende de cupom e de canal) fica de fora de
    propósito: ela mora na sessão, é reavaliada no kernel, e trazê-la para cá
    criaria a segunda opinião que este trabalho está justamente removendo. O que
    entra aqui é a política que não depende de contexto nenhum.
    """
    if base_fee_q <= 0:
        return base_fee_q
    from shopman.shop.projections.cart import shop_rule_q

    free_above_q = shop_rule_q("free_delivery_above_q")
    if free_above_q and merchandise_q >= free_above_q:
        return 0
    return base_fee_q


def _payload_delivery_fee_q(payload: dict) -> int:
    return _resolve_delivery_fee(payload).fee_q


def _validate_fiscal_delivery_fee(payload: dict) -> None:
    """Nota fiscal + taxa de entrega ainda pede conferência no gestor.

    A regra é a de sempre; mudou o lugar. Enquanto a taxa era digitada, o
    parser do intent conseguia vê-la sem tocar no banco. Agora ela é RESOLVIDA
    pelo motor de entrega, e só quem resolveu sabe se existe — então a porta
    mora aqui, ao lado da resolução, em vez de olhar para um campo que o PDV
    não preenche mais.
    """
    if not str(payload.get("fiscal_tax_id") or "").strip():
        return
    if _resolve_delivery_fee(payload).fee_q <= 0:
        return
    raise PosIntentError(
        code="fiscal_delivery_fee_pending",
        message="Fiscal com taxa de entrega ainda exige revisão no gestor.",
        field="delivery_fee_q",
        focus="delivery_address",
        recovery="Finalize sem taxa, ou finalize sem fiscal e reprocesse no gestor após conferência.",
    )


def _validate_payment_completion(payload: dict) -> None:
    total_q = _payload_total_q(payload)
    fulfillment_type = _payload_fulfillment_type(payload)
    payment_collection = _payload_payment_collection(payload, fulfillment_type)
    tenders = _payload_tenders(
        payload,
        payment_collection=payment_collection,
        total_q=total_q,
        pos_terminal_ref=str(payload.get("pos_terminal_ref") or "").strip(),
        require_complete=True,
    )
    payment_method = _legacy_payment_method(payload, tenders)
    tendered_q = _int_q(payload.get("tendered_q"))
    if payment_method == "cash" and payment_collection == "terminal" and tendered_q and tendered_q < total_q:
        raise PosIntentError(
            code="cash_tendered_amount_too_low",
            message="Valor recebido em dinheiro menor que o total da venda.",
            field="tendered_q",
            focus="payment",
            recovery="Informe o valor recebido ou use dinheiro exato.",
        )


def discount_approval_threshold_q() -> int:
    """Teto (centavos) acima do qual um desconto do PDV exige PIN do gerente.

    DONO ÚNICO da política. Quem cobra o PIN mora aqui (``validate_manager_approval``),
    então a política mora aqui também: a projection do backstage lê desta função em
    vez de reimplementá-la. Antes eram duas leituras — a projection consultava
    ``Shop.defaults`` (editável no Admin) e o gate lia só o env, então mudar o teto
    no Admin não mudava quem precisava de gerente: a loja via um número e o balcão
    obedecia outro.

    Política da loja em ``Shop.defaults["pos"]["discount_approval_threshold_q"]``
    (editada em Reais no Admin). Ausente = herda o padrão do deploy
    (``SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q``). ``0`` DESLIGA o teto — nenhum
    desconto passa a exigir aprovação por valor (a exceção auditada de
    preço alterado segue exigindo, independentemente deste número).
    """
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        pos_cfg = (shop.defaults.get("pos") or {}) if shop and shop.defaults else {}
        raw = pos_cfg.get("discount_approval_threshold_q")
        if raw is not None:
            return max(0, int(raw))
    except Exception:
        logger.debug("pos_discount_threshold_lookup_failed", exc_info=True)
    return max(0, int(getattr(settings, "SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q", 0) or 0))


def fiscal_toggle_enabled() -> bool:
    """A loja OFERECE emissão de NFC-e no balcão?

    DONO ÚNICO da pergunta. Flag de negócio por estabelecimento, editável no
    Admin em ``Shop.defaults["pos"]["fiscal_toggle"]`` — ausente = desligado
    (mesma semântica que o Admin grava: desligar remove a chave).

    Duas coisas leem daqui, e é por isso que ela mora numa função só: a
    projection do PDV, para decidir se o toggle "Nota fiscal" aparece
    (``backstage/projections/pos._pos_fiscal_toggle_enabled``), e o deploy check
    ``SHOPMAN_W003``, para avisar quando a loja oferece NFC-e e não há adapter
    fiscal configurado — o caso em que o gestor liga o toggle no Admin e nada
    acontece no balcão, em silêncio.
    """
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        defaults = (getattr(shop, "defaults", None) or {}) if shop else {}
        pos_cfg = defaults.get("pos") if isinstance(defaults, dict) else {}
        return bool((pos_cfg or {}).get("fiscal_toggle", False))
    except Exception:
        logger.debug("pos_fiscal_toggle_lookup_failed", exc_info=True)
        return False


def _payload_tenders(
    payload: dict,
    *,
    payment_collection: str,
    total_q: int,
    pos_terminal_ref: str,
    require_complete: bool = False,
) -> list[dict]:
    raw = payload.get("payment_tenders")
    payment_method = _normalize_payment_method(payload.get("payment_method") or "cash")
    if isinstance(raw, list) and raw:
        tenders = []
        for tender in raw:
            method = _normalize_payment_method(tender.get("method"))
            try:
                amount_q = int(tender.get("amount_q") or 0)
            except (TypeError, ValueError):
                amount_q = 0
            if amount_q <= 0:
                continue
            collection = str(tender.get("collection") or payment_collection).strip().lower()
            if collection not in {"terminal", "on_delivery"}:
                collection = payment_collection
            if collection == "on_delivery" and method != "cash":
                raise PosIntentError(
                    code="invalid_on_delivery_tender_payment",
                    message="Pagamento na entrega só é permitido em dinheiro.",
                    field=f"payment_tenders.{len(tenders)}.collection",
                    focus="payment",
                    recovery="Altere a linha para dinheiro ou receba esse valor no caixa.",
                )
            entry = {
                "method": method,
                "amount_q": amount_q,
                "collection": collection,
                "status": "pending" if collection == "on_delivery" else "received",
            }
            reference = str(tender.get("reference") or "").strip()
            if reference:
                entry["reference"] = reference[:120]
            if pos_terminal_ref and entry["collection"] == "terminal":
                entry["terminal_ref"] = pos_terminal_ref
            if entry["collection"] == "terminal":
                entry["received_at"] = timezone.now().isoformat()
            tenders.append(entry)
        paid_q = sum(int(tender["amount_q"]) for tender in tenders)
        if require_complete and total_q > 0 and paid_q < total_q:
            raise PosIntentError(
                code="payment_tenders_total_mismatch",
                message="Os pagamentos informados não cobrem o total da venda.",
                field="payment_tenders",
                focus="payment",
                recovery="Ajuste as linhas do pagamento até cobrirem o total revisado (o excedente vira troco).",
            )
        return tenders

    if total_q <= 0:
        return []
    if require_complete and payment_method == "mixed":
        raise PosIntentError(
            code="payment_tenders_required",
            message="Informe as linhas do pagamento misto.",
            field="payment_tenders",
            focus="payment",
            recovery="Adicione ao menos uma linha e confira se a soma fecha o total.",
        )
    if payment_method == "mixed":
        return []
    tender = {
        "method": payment_method,
        "amount_q": total_q,
        "collection": payment_collection,
        "status": "pending" if payment_collection == "on_delivery" else "received",
    }
    if pos_terminal_ref and payment_collection == "terminal":
        tender["terminal_ref"] = pos_terminal_ref
    if payment_collection == "terminal":
        tender["received_at"] = timezone.now().isoformat()
    return [tender]


def _legacy_payment_method(payload: dict, tenders: list[dict]) -> str:
    requested = _normalize_payment_method(payload.get("payment_method") or "cash")
    if requested == "mixed" and tenders:
        return "mixed"
    methods = {str(tender.get("method") or "").strip() for tender in tenders if tender.get("amount_q")}
    methods.discard("")
    if len(methods) > 1:
        return "mixed"
    if len(methods) == 1:
        return next(iter(methods))
    return requested


def _normalize_payment_method(value) -> str:
    method = str(value or "cash").strip().lower() or "cash"
    if method in {"cash", "pix", "card", "external", "account", "mixed"}:
        return method
    return "external"


def _is_cash_tender(tender: dict) -> bool:
    """A linha é dinheiro em espécie (a única que pode gerar troco)."""
    return str(tender.get("method") or "").lower() == "cash"


def _cash_received_q(tenders: list[dict]) -> int:
    total = 0
    for tender in tenders:
        if tender.get("method") != "cash":
            continue
        if tender.get("collection", "terminal") != "terminal":
            continue
        if tender.get("status") not in {"received", "captured", "paid", ""}:
            continue
        total += int(tender.get("amount_q") or 0)
    return total


def _reconcile_order_payment_to_total(order: Order) -> Order:
    """Align POS payment metadata with the final committed Orderman total."""
    final_total_q = int(order.total_q or 0)
    data = dict(order.data or {})
    payment = dict(data.get("payment") or {})
    if not payment:
        return order

    original_amount_q = _int_q(payment.get("amount_q"))
    tenders = [dict(tender) for tender in payment.get("tenders") or [] if isinstance(tender, dict)]
    original_tender_total_q = sum(_int_q(tender.get("amount_q")) for tender in tenders)
    if original_amount_q == final_total_q and (not tenders or original_tender_total_q == final_total_q):
        return order

    payment["amount_q"] = final_total_q
    if original_amount_q != final_total_q:
        payment["pos_reconciled_from_amount_q"] = original_amount_q

    # O dinheiro em mão ANTES do acerto: é ele que vira `tendered_q`. Depois do
    # `_reconcile_tenders_to_total` a linha de dinheiro já está líquida (o que
    # sobra na gaveta), e a diferença entre os dois é o troco que o operador
    # devolveu — o único lugar onde esse fato ainda existe.
    cash_handed_q = _cash_received_q(tenders) if tenders else 0
    if tenders:
        _reconcile_tenders_to_total(tenders, final_total_q)
        payment["tenders"] = tenders
        cash_received_q = _cash_received_q(tenders)
        if cash_received_q > 0:
            payment["cash_received_q"] = cash_received_q
        else:
            payment.pop("cash_received_q", None)

    # `tendered_q` = dinheiro que veio na mão; `change_q` = o que voltou pro
    # cliente. Numa venda MISTA o troco sai da nota em dinheiro (cartão captura
    # o valor inteiro), então o troco é o que a linha de dinheiro perdeu no
    # acerto — nunca `tendered − total`, que daria zero e apagaria o troco do
    # registro. Em dinheiro puro as duas contas coincidem, porque ali a parcela
    # em dinheiro É o total.
    cash_settled_q = _cash_received_q(tenders) if tenders else final_total_q
    tendered_q = max(_int_q(payment.get("tendered_q")), cash_handed_q)
    if tendered_q > cash_settled_q:
        payment["tendered_q"] = tendered_q
        payment["change_q"] = max(0, tendered_q - cash_settled_q)
    elif _int_q(payment.get("tendered_q")) > 0:
        # Acerto para CIMA (o total selado subiu): não houve troco, e o valor
        # em mão não é mais o que a venda cobrou — o registro não inventa nada.
        payment["change_q"] = 0

    data["payment"] = payment
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    return order


def _settle_pos_sale(order: Order, *, shift, operator_username: str) -> dict:
    """Liquida no Payman e escreve a venda no livro do turno. Devolve o que o PDV exibe.

    Roda DEPOIS de ``_reconcile_order_payment_to_total``: o valor dos tenders
    só é definitivo com o total selado, e tanto o intent quanto a linha do
    livro têm de nascer com o valor final (o que ficou na gaveta depois do
    troco), não com o que o operador digitou.

    Uma linha ``sale`` por venda, sempre: ``amount_q`` é o EFEITO EM DINHEIRO
    na gaveta (a soma dos tenders em dinheiro no terminal; zero para pix,
    cartão, external, e para a entrega paga na porta), ``payment_ref`` aponta
    o intent do dinheiro (ou o único intent), e o payload guarda método,
    recebido, troco e os intents por método. É assim que a leitura Z sabe
    "vendas deste turno" sem algoritmo, e o saldo da gaveta é ``Σ``.

    Ordem e atomicidade: métodos sem gateway (dinheiro, external, e pix/cartão
    atestados numa venda mista) liquidam no Payman e gravam a linha na MESMA
    transação: ou o dinheiro consta nos dois livros, ou em nenhum. Pix/cartão
    sozinhos vão ao gateway (rede) fora de transação, como sempre; a linha da
    venda nasce depois, com efeito zero, e leva o intent se o gateway aceitou.
    """
    from shopman.cashman import CashError

    payment = dict((order.data or {}).get("payment") or {})
    method = str(payment.get("method") or "").strip().lower()
    collection = str(payment.get("collection") or "terminal").strip().lower()
    operator = _user_for_actor(operator_username) or shift.opened_by

    if collection != "terminal":
        # Entrega paga na porta: a venda é deste turno, o dinheiro vem no acerto.
        try:
            _record_sale(order, shift=shift, operator=operator, cash_q=0, payment_ref="", intents={})
        except CashError as exc:
            if exc.code != "SHIFT_NOT_OPEN":
                raise
            _settle_after_shift_closed(order, shift=shift, operator=operator, resettle=False)
        return {}

    gateway_only = method in {"pix", "card"}
    payment_result: dict = {}
    if gateway_only:
        # Rede fora de transação: gateway primeiro, linha depois.
        try:
            payment_service.initiate(order)
        except Exception as exc:
            logger.warning("pos_payment_initiate_failed order=%s method=%s", order.ref, method, exc_info=True)
            payment_result = {
                "method": method,
                "amount_q": int(payment.get("amount_q") or order.total_q or 0),
                "amount_display": f"R$ {format_money(int(payment.get('amount_q') or order.total_q or 0))}",
                "status": "error",
                "error": str(exc),
                "message": "Pagamento não foi criado no gateway. Revise a configuração e use recuperação operacional.",
            }
        order = Order.objects.get(ref=order.ref)
        payment = dict((order.data or {}).get("payment") or {})
        intents = {method: payment["intent_ref"]} if payment.get("intent_ref") else {}
        try:
            _record_sale(order, shift=shift, operator=operator, cash_q=0, payment_ref=intents.get(method, ""), intents=intents)
        except CashError as exc:
            if exc.code != "SHIFT_NOT_OPEN":
                raise
            _settle_after_shift_closed(order, shift=shift, operator=operator, resettle=False)
        return payment_result or _pos_payment_response(order)

    try:
        with transaction.atomic():
            intents = payment_service.settle_terminal_tenders(order)
            order = Order.objects.get(ref=order.ref)
            cash_q = _terminal_cash_amount_q(order)
            _record_sale(
                order,
                shift=shift,
                operator=operator,
                cash_q=cash_q,
                payment_ref=intents.get("cash") or (next(iter(intents.values())) if len(intents) == 1 else ""),
                intents=intents,
            )
    except CashError as exc:
        if exc.code != "SHIFT_NOT_OPEN":
            raise
        # O turno fechou ENTRE o começo desta venda e a linha do livro. O
        # `atomic` acima é o certo (ou o dinheiro consta nos dois livros, ou em
        # nenhum), mas ele também desfez a liquidação no Payman — e a venda em
        # si já commitou. Liquidar de novo, sozinho, e deixar a marca de que
        # este dinheiro existe fora do turno.
        _settle_after_shift_closed(order, shift=shift, operator=operator)
    # A venda já commitou e o dinheiro já está na gaveta: não há o que desfazer
    # no pedido. O acusador do dia seguinte existe (o check `cash_ledger_mismatch`
    # da reconciliação diária, em
    # `backstage/services/financial_reconciliation.py::_check_cash_ledger`), mas
    # "amanhã" não serve para quem está com o cliente na frente: o erro sobe.
    except Exception:
        logger.exception("pos_sale_settlement_failed order=%s", order.ref)
        raise PosIntentError(
            code="sale_settlement_failed",
            message=f"Venda {order.ref} criada, mas a cobrança não foi registrada.",
            field="payment",
            focus="payment",
            status=409,
            recovery="NÃO refaça a venda. Chame o gerente e confira o pedido no gestor antes de continuar.",
        ) from None
    return {}


def _settle_after_shift_closed(order: Order, *, shift, operator, resettle: bool = True) -> None:
    """Venda que chegou depois do fechamento: liquidar, marcar e gritar.

    Este é o buraco que o ``except Exception`` engolia. A sequência real: o PDV
    valida o turno no começo de ``close_sale`` e a linha do livro só nasce
    centenas de milissegundos depois, com o pedido já commitado. Se o gerente
    fecha o turno nesse intervalo, ``cash_ledger.record`` recusa com
    ``SHIFT_NOT_OPEN`` (de propósito: o ``count`` congela "contado − esperado no
    instante do fechamento", e uma linha posterior faria o livro provar um saldo
    que a gaveta nunca teve) — e antes daqui o pedido saía confirmado na tela,
    ausente do livro E do Payman, com zero issues na reconciliação do dia.

    O comentário antigo prometia que "vira uma sobra na conferência" e que "dois
    acusadores existem". As duas afirmações são falsas NESTE caminho: a contagem
    já foi gravada quando o dinheiro entrou, então não sobra nada para acusar, e
    a reconciliação não vê divergência porque o Payman também ficou vazio.

    O que fica no lugar:

    - **a cobrança**, liquidada agora numa transação própria: o dinheiro está na
      gaveta e o pedido tem de dizer que foi pago;
    - **uma ``note`` no turno fechado** — o único tipo que o livro aceita depois
      do fechamento junto com a correção da contagem, e é honesto que seja ele:
      não move saldo (o ``count`` está congelado), só nomeia o pedido, o valor e
      a hora para quem for conferir a gaveta;
    - **um alerta crítico**, porque ninguém lê o livro de um turno fechado por
      acaso;
    - **o erro na tela do PDV**, levantado por quem chamou.
    """
    from shopman.cashman import CashError

    # Relê o pedido: a tentativa que falhou rodou dentro do ``atomic`` desfeito e
    # deixou ``order.data`` em memória apontando intents que o rollback apagou.
    # Reaproveitar essa instância faria ``settle_terminal_tenders`` achar que já
    # liquidou e devolver refs de intents que não existem mais.
    order = Order.objects.get(ref=order.ref)
    cash_q = 0
    intents: dict = {}
    if resettle:
        # Só o caminho do terminal precisa: lá a liquidação e a linha do livro
        # dividiam o mesmo `atomic`, então a recusa do livro desfez a cobrança.
        # No gateway e na entrega a cobrança acontece fora da transação e já
        # está de pé.
        try:
            with transaction.atomic():
                intents = payment_service.settle_terminal_tenders(order)
                fresh = Order.objects.get(ref=order.ref)
                cash_q = _terminal_cash_amount_q(fresh)
        except Exception:
            intents = {}
            logger.exception("pos_sale_settlement_failed order=%s shift=%s", order.ref, shift.pk)

    try:
        cash_ledger.record(
            "note",
            shift=shift,
            operator=operator,
            reason="Venda finalizada depois do fechamento do turno",
            payload={
                "text": (
                    f"Venda {order.ref} finalizada depois do fechamento do turno, "
                    f"com R$ {format_money(int(cash_q))} em dinheiro sem linha no livro."
                ),
                "order_ref": order.ref,
                "cash_q": int(cash_q),
                "intents": dict(intents),
            },
        )
    except CashError:
        logger.exception("pos_sale_after_close_note_failed order=%s shift=%s", order.ref, shift.pk)

    faltante = (
        f"R$ {format_money(int(cash_q))} em dinheiro ficaram fora do livro"
        if cash_q > 0
        else "a venda ficou fora do livro do turno"
    )
    message = f"Venda {order.ref} entrou depois do fechamento do turno {shift.pk}: {faltante}. Confira a gaveta."
    try:
        from shopman.shop.adapters import alert as alert_adapter

        alert_adapter.create("cash_sale_after_shift_close", "critical", message, order_ref=order.ref)
    except Exception:
        logger.exception("pos_sale_after_close_alert_failed order=%s", order.ref)

    logger.error("pos_sale_after_shift_close order=%s shift=%s cash_q=%s", order.ref, shift.pk, cash_q)
    raise PosIntentError(
        code="cash_shift_closed_mid_sale",
        message=message,
        field="cash_shift_id",
        focus="cash",
        status=409,
        recovery="NÃO refaça a venda: o pedido já existe. Chame o gerente para conferir a gaveta.",
    )


def _record_sale(order: Order, *, shift, operator, cash_q: int, payment_ref: str, intents: dict) -> None:
    """A linha ``sale`` da venda no livro do turno; idempotente por (turno, pedido).

    Quem GARANTE a unicidade é a ``UniqueConstraint`` parcial do pacote
    (``cashman_entry_one_sale_per_order_uq``): entre o ``exists()`` e o insert
    cabe o segundo submit de um retry de rede do PDV. O ``exists()`` fica como
    fast-path — evita a ida ao banco no caso comum e a exceção no log —, e um
    ``DUPLICATE_ENTRY`` que escape dele é o mesmo fato: a venda já está no livro,
    não há nada a fazer nem a avisar.
    """
    from shopman.cashman import Entry

    if Entry.objects.filter(shift=shift, kind=Entry.Kind.SALE, order_ref=order.ref).exists():
        return
    payment = dict((order.data or {}).get("payment") or {})
    payload = {
        "method": str(payment.get("method") or ""),
        "collection": str(payment.get("collection") or "terminal"),
        "intents": dict(intents),
    }
    tendered_q = _int_q(payment.get("tendered_q"))
    if tendered_q > 0:
        payload["received_q"] = tendered_q
        payload["change_q"] = _int_q(payment.get("change_q"))
    from shopman.cashman import CashError

    try:
        cash_ledger.record(
            "sale",
            shift=shift,
            operator=operator,
            amount_q=int(cash_q),
            order_ref=order.ref,
            payment_ref=str(payment_ref or ""),
            payload=payload,
        )
    except CashError as exc:
        if exc.code != "DUPLICATE_ENTRY":
            raise
        logger.info("pos_sale_already_in_ledger order=%s shift=%s", order.ref, shift.pk)


def _terminal_cash_amount_q(order: Order) -> int:
    """Quanto dinheiro em espécie desta venda entrou na gaveta (tenders cash no terminal)."""
    payment = dict((order.data or {}).get("payment") or {})
    tenders = [t for t in (payment.get("tenders") or []) if isinstance(t, dict)]
    if tenders:
        return _cash_received_q(tenders)
    if str(payment.get("method") or "").lower() == "cash" and str(payment.get("collection") or "terminal") == "terminal":
        return int(order.total_q or 0)
    return 0


def _require_house_account_if_on_account(payload: dict, *, payment_method: str, tenders: list[dict]) -> None:
    """Venda "em conta" só para cliente identificado e elegível; recusa ANTES do commit.

    A elegibilidade é do cliente (``Customer.metadata.house_account``, só o
    Admin liga); aqui é o porteiro. Sem isto, qualquer venda viraria dívida de
    alguém, e "em conta" é exatamente o método que não se divulga.
    """
    on_account = payment_method == "account" or any(
        str(t.get("method") or "").lower() == "account" for t in tenders
    )
    if not on_account:
        return
    from shopman.shop.services import house_account

    try:
        house_account.require_eligible(str(payload.get("customer_ref") or "").strip())
    except house_account.HouseAccountError as exc:
        raise PosIntentError(
            code="house_account_not_eligible",
            message=str(exc),
            field="payment_method",
            focus="payment",
            recovery="Identifique um cliente com conta na casa ou escolha outro meio de pagamento.",
        ) from exc


def _require_open_shift(payload: dict):
    """O turno aberto de quem vende, resolvido pelo servidor (``cash_shift_id`` vem do backstage, nunca do browser)."""
    from shopman.cashman import Shift

    shift_id = payload.get("cash_shift_id")
    shift = None
    if shift_id:
        shift = Shift.objects.filter(pk=shift_id).select_related("terminal", "opened_by").first()
    if shift is None or not shift.is_open:
        raise PosIntentError(
            code="cash_shift_required",
            message="Abra o caixa antes de finalizar uma venda.",
            field="cash_shift_id",
            focus="cash",
            status=409,
            recovery="Abra um turno de caixa neste terminal e tente novamente.",
        )
    return shift


def _user_for_actor(actor: str):
    """O User por trás de um ``operator_username``/``actor`` (``pos:<username>`` ou o próprio username)."""
    from django.contrib.auth import get_user_model

    username = str(actor or "").strip()
    if username.startswith("pos:"):
        username = username[4:]
    if not username:
        return None
    return get_user_model().objects.filter(username=username).first()


def _pos_payment_response(order: Order) -> dict:
    payment = dict((order.data or {}).get("payment") or {})
    method = str(payment.get("method") or "").strip().lower()
    if method not in {"pix", "card"}:
        return {}

    response = {
        "method": method,
        "amount_q": int(payment.get("amount_q") or order.total_q or 0),
        "amount_display": f"R$ {format_money(int(payment.get('amount_q') or order.total_q or 0))}",
    }
    for key in (
        "intent_ref",
        "qr_code",
        "copy_paste",
        "expires_at",
        "checkout_url",
        "error",
    ):
        value = payment.get(key)
        if value:
            response[key] = value
    if payment.get("intent_ref"):
        response["status"] = "pending"
        response["message"] = "Pagamento criado. Aguarde confirmação do gateway antes de tratar como recebido."
    elif payment.get("error"):
        response["status"] = "error"
        response["message"] = "Pagamento não foi criado no gateway. Revise a configuração e use recuperação operacional."
    else:
        response["status"] = "unavailable"
        response["message"] = "Pagamento digital não retornou dados exibíveis."
    return response


def _reconcile_tenders_to_total(tenders: list[dict], final_total_q: int) -> None:
    if not tenders:
        return
    if len(tenders) == 1:
        tenders[0]["amount_q"] = final_total_q
        return

    remaining_delta_q = final_total_q - sum(_int_q(tender.get("amount_q")) for tender in tenders)
    if remaining_delta_q == 0:
        return

    # Troco/ajuste sai do DINHEIRO: numa venda mista [cash 50, pix 20] p/ 60,
    # o excedente é o troco da nota de 50 — a maquininha capturou os 20
    # inteiros. Descontar da tender eletrônica erraria o caixa (falta falsa
    # no turno) e os totais do fechamento. Eletrônicas só em último caso.
    ordered = [t for t in reversed(tenders) if _is_cash_tender(t)] + [
        t for t in reversed(tenders) if not _is_cash_tender(t)
    ]
    for tender in ordered:
        if remaining_delta_q == 0:
            return
        current_q = _int_q(tender.get("amount_q"))
        next_q = max(0, current_q + remaining_delta_q)
        tender["amount_q"] = next_q
        remaining_delta_q -= next_q - current_q


def _int_q(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _append_schedule_ops(ops: list[dict], payload: dict) -> None:
    """A data e a janela combinadas — de QUALQUER recebimento.

    Irmãs de ``order_notes``, e pela mesma razão: ficavam presas ao bloco de
    entrega, e o balcão perdia as duas na retirada. *Quando* é fato do PEDIDO;
    só *onde* e *quanto* são fatos da entrega.
    """
    delivery_date = str(payload.get("delivery_date") or "").strip()
    if delivery_date:
        ops.append({"op": "set_data", "path": "delivery_date", "value": delivery_date})
    delivery_time_slot = str(payload.get("delivery_time_slot") or "").strip()
    if delivery_time_slot:
        ops.append({"op": "set_data", "path": "delivery_time_slot", "value": delivery_time_slot})


def _append_delivery_ops(ops: list[dict], payload: dict) -> None:
    structured_address = payload.get("delivery_address_structured") if isinstance(payload.get("delivery_address_structured"), dict) else {}
    address = str(payload.get("delivery_address") or structured_address.get("formatted_address") or "").strip()
    if address:
        ops.append({"op": "set_data", "path": "delivery_address", "value": address})
    structured = payload.get("delivery_address_structured") or {}
    if isinstance(structured, dict) and structured:
        ops.append({"op": "set_data", "path": "delivery_address_structured", "value": structured})
    # A taxa gravada é a RESOLVIDA (a mesma que a review mostrou e que entrou no
    # total), nunca um número solto do payload.
    delivery_fee_q = _payload_delivery_fee_q(payload)
    if delivery_fee_q > 0:
        ops.append({"op": "set_data", "path": "delivery_fee_q", "value": delivery_fee_q})
    # A exceção fica guardada por SI, ao lado da taxa que ela produziu: sem isso
    # o rascunho retomado perderia o combinado e voltaria à tabela da loja em
    # silêncio, cobrando do cliente um valor diferente do que foi prometido.
    override = payload.get("delivery_fee_override_q")
    if override not in (None, ""):
        ops.append({"op": "set_data", "path": "delivery_fee_override_q", "value": max(0, _int_q(override))})


def _payload_tab_session_key(payload: dict) -> str:
    return str(payload.get("tab_session_key") or "").strip()


def _payload_tab_ref(payload: dict) -> str:
    raw = str(payload.get("tab_ref") or "").strip()
    return normalize_tab_ref(raw) if raw else ""


def _payload_open_tab_session(*, channel_ref: str, payload: dict) -> Session | None:
    session_key = _payload_tab_session_key(payload)
    if session_key:
        return _get_open_pos_tab_session_by_key(channel_ref=channel_ref, session_key=session_key)
    tab_ref = _payload_tab_ref(payload)
    if tab_ref:
        return _get_open_pos_tab_session(channel_ref=channel_ref, tab_ref=tab_ref)
    return None


def _payload_has_tab_identity(payload: dict) -> bool:
    return bool(_payload_tab_session_key(payload) or _payload_tab_ref(payload))


def _create_direct_checkout_session(*, channel_ref: str, payload: dict, operator_username: str) -> Session:
    now = timezone.now().isoformat()
    return session_service.create_session(
        channel_ref,
        data={
            "origin_channel": "pos",
            "fulfillment_type": _payload_fulfillment_type(payload),
            "pos_operator": operator_username,
            "last_touched_at": now,
            "pos": {
                "direct_checkout": True,
            },
        },
    )


def _get_open_pos_tab_session_by_key(*, channel_ref: str, session_key: str) -> Session | None:
    return Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).first()


def _get_open_pos_tab_session(*, channel_ref: str, tab_ref: str) -> Session | None:
    return Session.objects.filter(
        Q(handle_type="pos_tab", handle_ref=tab_ref) | Q(data__tab_ref=tab_ref),
        channel_ref=channel_ref,
        state="open",
    ).order_by("-opened_at").first()


def _session_tab_ref(session: Session) -> str:
    data = session.data or {}
    raw = str(data.get("tab_ref") or session.handle_ref or "").strip()
    return normalize_tab_ref(raw)


def _session_tab_display(session: Session) -> str:
    data = session.data or {}
    display = str(data.get("tab_display") or "").strip()
    if display:
        return display
    return display_tab_ref(_session_tab_ref(session))


def _ensure_pos_tab(tab_ref: str, display: str = "") -> str:
    return pos_adapter.ensure_tab(ref=tab_ref, display=display or display_tab_ref(tab_ref))


def _mark_tab_committed(
    *,
    order_ref: str,
    tab_ref: str,
    operator_username: str,
    session_data: dict | None = None,
) -> None:
    now = timezone.now().isoformat()

    order = Order.objects.filter(ref=order_ref).first()
    if order is None:
        return
    order_data = dict(order.data or {})
    order_data["pos_operator"] = operator_username
    order_data["pos_committed_at"] = now
    session_data = session_data or {}
    if tab_ref:
        order_data["tab_ref"] = tab_ref
        order_data["tab_display"] = str(session_data.get("tab_display") or display_tab_ref(tab_ref))
    session_pos_data = dict(session_data.get("pos") or {})
    if session_pos_data:
        order_data["pos"] = {**dict(order_data.get("pos") or {}), **session_pos_data}
    client_request_id = session_data.get("client_request_id") or (session_data.get("pos") or {}).get("client_request_id")
    if client_request_id:
        order_data["client_request_id"] = client_request_id
        pos_data = dict(order_data.get("pos") or {})
        pos_data["client_request_id"] = client_request_id
        order_data["pos"] = pos_data
    # Retirada não tem ENDEREÇO nem TAXA — isso continua sendo limpo.
    #
    # ⚠️ Mas a DATA e a JANELA ficam. Elas estavam nesta lista, e por isso um
    # pedido de retirada agendado era literalmente impossível no balcão: o
    # operador combinava quinta-feira às 10h com o cliente no telefone, e o
    # commit apagava as duas coisas em silêncio — o pedido nascia para hoje.
    # *Quando* é fato do PEDIDO; só *onde* e *quanto* são fatos da entrega.
    if order_data.get("fulfillment_type") != "delivery":
        for key in ("delivery_address", "delivery_address_structured", "delivery_fee_q", "delivery_fee_override_q"):
            order_data.pop(key, None)

    fiscal = session_data.get("fiscal") or {}
    if fiscal.get("issue_document") or fiscal.get("tax_id"):
        order_data["fiscal"] = fiscal
    receipt = session_data.get("receipt") or {}
    if receipt.get("email") or receipt.get("channels"):
        order_data["receipt"] = receipt
    manual_discount = session_data.get("manual_discount") or {}
    if manual_discount.get("discount_q"):
        order_data["manual_discount"] = manual_discount

    order.data = order_data
    order.save(update_fields=["data"])


def _payload_client_request_id(payload: dict) -> str:
    raw = str(payload.get("client_request_id") or "").strip()
    if not raw:
        return ""
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in "-_:")
    if safe != raw or len(safe) > 128:
        return ""
    return safe


def _is_delivery_fee_item(item: dict) -> bool:
    meta = item.get("meta") or {}
    return item.get("sku") == "__DELIVERY_FEE__" or meta.get("type") == "delivery_fee"


def _existing_sale_by_client_request_id(*, channel_ref: str, payload: dict) -> Order | None:
    key = _payload_client_request_id(payload)
    if not key:
        return None
    return (
        Order.objects.filter(channel_ref=channel_ref)
        .filter(Q(data__client_request_id=key) | Q(data__pos__client_request_id=key))
        .order_by("-created_at")
        .first()
    )


def _sale_fiscal_hint(order: Order | None) -> str:
    if order is None:
        return ""
    # A regra fiscal, não o toggle: cartão/pix/fiado emitem sem o operador
    # marcar nada, e a dica de "fiscal pendente" tem que acompanhar a emissão
    # real — senão a nota nasce e a tela jura que não há fiscal nenhum.
    try:
        from shopman.shop.services import fiscal as fiscal_service

        if fiscal_service.emission_expected(order):
            return " · Fiscal pendente"
    except Exception:
        logger.debug("pos_sale_fiscal_hint_failed order=%s", order.ref, exc_info=True)
        if ((order.data or {}).get("fiscal") or {}).get("issue_document"):
            return " · Fiscal pendente"
    return ""


def resolve_or_create_customer(
    *, name: str = "", phone: str = "", tax_id: str = "", email: str = "", operator_username: str,
) -> dict:
    """Get-or-create a POS customer JUST-IN-TIME — when the operator defines them
    on the counter, not deferred to order commit. Resolves by phone/CPF/email or
    creates a fresh record, and returns the customer dict (ref/name/phone/tax_id/
    email/tier). Idempotent (same identifiers → same customer). Reuses the exact
    commit-time logic so the just-in-time customer is identical to the final one."""
    return _persist_customer_from_payload(
        {
            "customer_name": name,
            "customer_phone": phone,
            "customer_tax_id": tax_id,
            "customer_email": email,
        },
        operator_username=operator_username,
    )


def _persist_customer_from_payload(payload: dict, *, operator_username: str) -> dict:
    """Resolve/create/update a Guestman customer from any POS customer data."""
    name = str(payload.get("customer_name") or "").strip()
    phone = _normalize_phone(str(payload.get("customer_phone") or "").strip())
    # IDENTIDADE — com o que se ACHA o cliente.
    tax_id = _digits(str(payload.get("customer_tax_id") or "").strip())
    email = str(payload.get("customer_email") or "").strip().lower()
    # LACUNA — campo vazio no cadastro aprende; campo preenchido nunca muda
    # (``_merge_pos_customer_fields`` só completa). É o que faz o CPF do cliente
    # entrar uma vez e voltar pré-preenchido na próxima venda, sem que uma
    # edição pontual no checkout reescreva o cadastro de ninguém.
    fill_tax_id = tax_id or _digits(str(payload.get("fiscal_tax_id") or "").strip())
    fill_email = email or str(payload.get("receipt_email") or "").strip().lower()
    structured_address = payload.get("delivery_address_structured") if isinstance(payload.get("delivery_address_structured"), dict) else {}
    address = str(payload.get("delivery_address") or structured_address.get("formatted_address") or "").strip()
    raw_ref = str(payload.get("customer_ref") or "").strip()

    if not any((raw_ref, name, phone, fill_tax_id, fill_email, address)):
        return {}

    try:
        from shopman.guestman.models import ContactPoint, Customer
        from shopman.guestman.services import address as address_service
    except ImportError:
        logger.warning("pos_customer_persist_skipped_guestman_unavailable")
        return {}

    # O CPF PEDIDO PARA A NOTA só identifica quando não há mais nada.
    #
    # Se o operador já disse de quem é a venda (ref, telefone, e-mail do
    # cadastro), o documento da nota é FISCAL e mais nada: o cliente pode pedir a
    # nota no CPF da esposa, e deixar isso decidir o dono da venda mandaria para
    # ela os PONTOS de fidelidade, o HISTÓRICO, e — pior — traria a FAIXA DE
    # PREÇO e as RESTRIÇÕES ALIMENTARES dela para um pedido que não é dela. Duas
    # identificações discordando, com a silenciosa vencendo.
    #
    # Mas quando ninguém foi identificado, esse CPF é a única identidade que
    # existe, e ignorá-lo criaria um cliente DUPLICADO a cada venda de quem só
    # pede nota — que é a maioria. Aí ele resolve normalmente, igual ao
    # auto-cadastro por CPF que a busca de cliente já faz.
    identified = bool(raw_ref or phone or tax_id or email)
    resolve_tax_id = tax_id if identified else fill_tax_id

    with transaction.atomic():
        customer = _resolve_pos_customer(
            Customer,
            ref=raw_ref,
            phone=phone,
            tax_id=resolve_tax_id,
            email=email,
        )
        created = customer is None
        if customer is None:
            first_name, last_name = _split_name(name)
            fallback = _fallback_customer_name(phone=phone, tax_id=fill_tax_id, email=fill_email)
            customer = Customer.objects.create(
                ref=Customer.generate_ref(),
                first_name=first_name or fallback[0],
                last_name=last_name or fallback[1],
                phone=phone,
                email=fill_email,
                document=fill_tax_id,
                source_system="pdv",
                created_by=operator_username,
                metadata={
                    "pos": {
                        "created_from_pos": True,
                        "first_operator": operator_username,
                        "captured_at": timezone.now().isoformat(),
                    }
                },
            )
        else:
            _merge_pos_customer_fields(
                customer,
                name=name,
                phone=phone,
                tax_id=fill_tax_id,
                email=fill_email,
                operator_username=operator_username,
            )

        if phone:
            _ensure_contact_point(ContactPoint, customer, ContactPoint.Type.PHONE, phone)
        if fill_email:
            _ensure_contact_point(ContactPoint, customer, ContactPoint.Type.EMAIL, fill_email)
        if fill_tax_id:
            _ensure_customer_identifier(customer.ref, "cpf", fill_tax_id)
        if address:
            _ensure_customer_address(address_service, customer.ref, address, structured_address)
        _remember_fiscal_prefs(customer, payload)

        customer.refresh_from_db()
        return {
            "ref": customer.ref,
            "name": customer.name,
            "phone": customer.phone,
            "tax_id": customer.document,
            "email": customer.email,
            "price_tier": customer.price_tier.ref if customer.price_tier_id else "",
            # "criei agora" ≠ "achei": a tela distingue o cadastro recém-criado.
            "created": created,
        }


def _remember_fiscal_prefs(customer, payload: dict) -> None:
    """O cliente optou uma vez → a próxima venda já vem PRÉ-MARCADA (editável).

    Só grava opt-IN (marcou nesta venda → lembra). Desmarcar numa venda não
    apaga a preferência: pode ser só "hoje não" — esquecer de verdade é gesto
    de cadastro (Admin), não efeito colateral de uma venda. O PDV lê isto na
    lookup projection e pré-seta o toggle fiscal / o canal de e-mail.
    """
    # A preferência lembrada é sobre a NOTA, então lê o campo da nota.
    wants_fiscal = bool(str(payload.get("fiscal_tax_id") or "").strip())
    wants_email = "email" in (payload.get("receipt_channels") or [])
    if not (wants_fiscal or wants_email):
        return
    metadata = dict(customer.metadata or {})
    prefs = dict(metadata.get("fiscal_prefs") or {})
    changed = False
    if wants_fiscal and not prefs.get("cpf_na_nota"):
        prefs["cpf_na_nota"] = True
        changed = True
    if wants_email and not prefs.get("email_receipt"):
        prefs["email_receipt"] = True
        changed = True
    if changed:
        metadata["fiscal_prefs"] = prefs
        customer.metadata = metadata
        customer.save(update_fields=["metadata", "updated_at"])


def _resolve_pos_customer(Customer, *, ref: str, phone: str, tax_id: str, email: str):
    candidates: dict[int, object] = {}
    evidence: dict[int, set[str]] = {}

    def add(candidate, source: str) -> None:
        if candidate is None:
            return
        candidates[candidate.pk] = candidate
        evidence.setdefault(candidate.pk, set()).add(source)

    if ref:
        add(Customer.objects.filter(ref=ref, is_active=True).first(), "ref")
    if phone:
        from shopman.guestman.services import customer as customer_service

        add(customer_service.get_by_phone(phone), "phone")
    if tax_id:
        from shopman.guestman.services import customer as customer_service

        add(customer_service.get_by_document(tax_id), "document")
        add(_find_customer_identifier("cpf", tax_id), "cpf")
    if email:
        from shopman.guestman.services import customer as customer_service

        add(customer_service.get_by_email(email), "email")

    if not candidates:
        return None
    if len(candidates) == 1:
        return next(iter(candidates.values()))

    detail = ", ".join(
        f"{getattr(customer, 'ref', customer_id)} via {'/'.join(sorted(evidence.get(customer_id, ())))}"
        for customer_id, customer in candidates.items()
    )
    raise ValueError(
        "Dados do cliente apontam para cadastros diferentes. "
        f"Revise telefone, CPF/CNPJ ou e-mail antes de fechar. ({detail})"
    )


def _merge_pos_customer_fields(
    customer,
    *,
    name: str,
    phone: str,
    tax_id: str,
    email: str,
    operator_username: str,
) -> None:
    first_name, last_name = _split_name(name)
    updates: list[str] = []

    if first_name and _should_refresh_name(customer):
        customer.first_name = first_name
        updates.append("first_name")
        if last_name:
            customer.last_name = last_name
            updates.append("last_name")
    elif last_name and not customer.last_name:
        customer.last_name = last_name
        updates.append("last_name")

    if phone and not customer.phone:
        customer.phone = phone
        updates.append("phone")
    if email and not customer.email:
        customer.email = email
        updates.append("email")
    if tax_id and not customer.document:
        customer.document = tax_id
        updates.append("document")

    metadata = dict(customer.metadata or {})
    pos_meta = dict(metadata.get("pos") or {})
    pos_meta.update({
        "last_operator": operator_username,
        "last_capture_at": timezone.now().isoformat(),
    })
    captured = sorted(k for k, v in {
        "name": name,
        "phone": phone,
        "tax_id": tax_id,
        "email": email,
    }.items() if v)
    if captured:
        pos_meta["last_captured_fields"] = captured
    metadata["pos"] = pos_meta
    if metadata != (customer.metadata or {}):
        customer.metadata = metadata
        updates.append("metadata")

    if updates:
        customer.save(update_fields=sorted(set(updates + ["updated_at"])))


def _ensure_contact_point(ContactPoint, customer, contact_type: str, value: str) -> None:
    try:
        contact, created = ContactPoint.objects.get_or_create(
            type=contact_type,
            value_normalized=value,
            defaults={
                "customer": customer,
                "value_display": value,
                "is_primary": not ContactPoint.objects.filter(customer=customer, type=contact_type).exists(),
            },
        )
    except IntegrityError as exc:
        raise ValueError("Contato já pertence a outro cliente.") from exc
    if contact.customer_id != customer.pk:
        raise ValueError("Contato já pertence a outro cliente.")
    if created and contact.is_primary:
        contact._sync_to_customer()


def _ensure_customer_identifier(customer_ref: str, identifier_type: str, identifier_value: str) -> None:
    try:
        from shopman.guestman.contrib.identifiers import IdentifierService

        IdentifierService.ensure_identifier(
            customer_ref=customer_ref,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            is_primary=True,
            source_system="pdv",
        )
    except ValueError as exc:
        raise ValueError("Identificador fiscal já pertence a outro cliente.") from exc


def _find_customer_identifier(identifier_type: str, identifier_value: str):
    try:
        from shopman.guestman.contrib.identifiers import IdentifierService

        return IdentifierService.find_by_identifier(identifier_type, identifier_value)
    except Exception:
        logger.debug("pos_customer_identifier_lookup_failed type=%s", identifier_type, exc_info=True)
        return None


def _ensure_customer_address(address_service, customer_ref: str, formatted_address: str, structured: dict | None = None) -> None:
    structured = structured if isinstance(structured, dict) else {}
    place_id = str(structured.get("place_id") or "").strip()
    existing = address_service.find_by_place_id(customer_ref, place_id) if place_id else None
    if existing is None and address_service.has_address(customer_ref, formatted_address):
        return

    components = {
        key: str(structured.get(key) or "").strip()
        for key in (
            "route",
            "street_number",
            "neighborhood",
            "city",
            "state",
            "state_code",
            "postal_code",
            "country",
            "country_code",
        )
        if str(structured.get(key) or "").strip()
    }
    coordinates = _structured_coordinates(structured)
    complement = str(structured.get("complement") or "").strip()
    delivery_instructions = str(structured.get("delivery_instructions") or structured.get("reference") or "").strip()

    if existing is not None:
        updates = {
            "formatted_address": formatted_address,
            "place_id": place_id,
            **components,
        }
        if complement:
            updates["complement"] = complement
        if delivery_instructions:
            updates["delivery_instructions"] = delivery_instructions
        if coordinates:
            updates["latitude"] = coordinates[0]
            updates["longitude"] = coordinates[1]
        address_service.update_address(customer_ref, existing.id, **updates)
        return

    address_service.add_address(
        customer_ref=customer_ref,
        label="home",
        formatted_address=formatted_address,
        place_id=place_id or None,
        components=components,
        coordinates=coordinates,
        complement=complement,
        delivery_instructions=delivery_instructions,
        is_default=not address_service.has_any_address(customer_ref),
    )


def _structured_coordinates(structured: dict) -> tuple[float, float] | None:
    try:
        lat = float(structured.get("latitude"))
        lng = float(structured.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def _fallback_customer_name(*, phone: str, tax_id: str, email: str) -> tuple[str, str]:
    if phone:
        return "Cliente", phone[-4:]
    if tax_id:
        return "Cliente", f"Doc {tax_id[-4:]}"
    if email:
        return "Cliente", email.split("@", 1)[0][:40]
    return "Cliente", "POS"


def _should_refresh_name(customer) -> bool:
    current = f"{customer.first_name} {customer.last_name}".strip().lower()
    return not current or current.startswith("cliente ") or current == "cliente"


def _normalize_phone(value: str) -> str:
    if not value:
        return ""
    try:
        from shopman.utils.phone import normalize_phone

        return normalize_phone(value)
    except Exception:
        logger.debug("pos_phone_normalization_failed", exc_info=True)
        return value


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _channel_and_config(channel_ref: str) -> tuple[Channel, ChannelConfig]:
    try:
        channel = Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist as exc:
        raise ValueError(f"Canal {channel_ref} não configurado. Contacte o suporte.") from exc
    return channel, ChannelConfig.for_channel(channel)
