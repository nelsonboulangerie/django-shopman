"""
Fila de espera — quanto da fornada AINDA NÃO ASSADA a loja promete (WP-P2E).

O Stockman sempre soube somar fornada planejada: ``total_promisable`` é
``expected + planned`` para a política ``planned_ok``. O que faltava era a
PERGUNTA. Toda leitura da loja pergunta "e para HOJE?", e fornada de amanhã,
por construção, não conta para hoje — ``quants_eligible_for`` corta
``target_date > target`` e ``_planned_supply_for_target`` exige ``target >
today``. Resultado: o balde ``planned`` chega zerado em toda leitura de
cliente, o item lê "Esgotado" e não há fila em que entrar, mesmo com a
fornada de amanhã já planejada.

Este módulo é a pergunta certa, num lugar só: até que DIA de fornada
planejada este canal promete. As leituras (sacola, cardápio, PDP) passam
:func:`promise_horizon` como ``target_date``; a reserva passa
:func:`reserve_target_date`, que é a data da fornada de verdade — o hold
precisa ancorar no lote certo para que a sacola diga "Previsto para
<dia>" sem mentir.

Desligado (``waitlist.enabled=False``, o default) tudo devolve hoje: o
comportamento é exatamente o de sempre.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from shopman.stockman.services.holds import (
    QUALITY_GRADE_ALLOWLIST_METADATA_KEY,
    QUALITY_GRADE_POLICY_VERSION,
    QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
)

logger = logging.getLogger(__name__)


def config(channel_ref: str | None = None):
    """Resolve o aspecto ``waitlist`` na cascata canal ← loja ← hardcoded."""
    from shopman.shop.config import ChannelConfig

    try:
        if channel_ref:
            return ChannelConfig.for_channel(channel_ref).waitlist
        return ChannelConfig().waitlist
    except Exception:
        logger.debug("waitlist.config degraded; using hardcoded defaults", exc_info=True)
        return ChannelConfig().waitlist


def is_enabled(channel_ref: str | None = None) -> bool:
    cfg = config(channel_ref)
    return bool(cfg.enabled and cfg.horizon_days > 0)


def promise_horizon(channel_ref: str | None = None) -> date:
    """Última data de fornada planejada que este canal promete.

    Fila desligada devolve HOJE — que é o que toda leitura já usava, então
    passar isto adiante não muda nada até alguém ligar a fila.
    """
    from django.utils import timezone

    today = timezone.localdate()
    cfg = config(channel_ref)
    if not (cfg.enabled and cfg.horizon_days > 0):
        return today
    return today + timedelta(days=cfg.horizon_days)


def next_batch_availability_for_skus(
    skus: list[str],
    *,
    channel_ref: str | None = None,
) -> dict[str, tuple[date, dict]]:
    """Próxima fornada elegível e sua capacidade reservável, por SKU.

    A data não pode nascer de ``Quant`` cru: posição, validade, lote e QC fazem
    parte da promessa do canal. Avaliamos as datas candidatas em ordem com a
    mesma leitura canônica usada pelo hold e paramos na primeira em que ainda há
    quantidade planejada líquida. O ``dict`` retornado é a capacidade inteira
    reservável naquela data — nunca a soma de fornadas incompatíveis.
    """
    unique_skus = list(dict.fromkeys(sku for sku in skus if sku))
    if not unique_skus:
        return {}
    horizon = promise_horizon(channel_ref)
    from django.utils import timezone

    today = timezone.localdate()
    if horizon <= today:
        return {}
    try:
        from shopman.stockman.models import Quant
        from shopman.stockman.services.availability import availability_for_skus

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref) if channel_ref else {}
        kwargs = {
            "safety_margin": int(scope.get("safety_margin") or 0),
            "allowed_positions": scope.get("allowed_positions"),
            "excluded_positions": scope.get("excluded_positions"),
            "expiry_margin_days": int(scope.get("expiry_margin_days") or 0),
            "include_nonconforming": bool(scope.get("sells_nonconforming", True)),
            "allowed_quality_grade_refs": scope.get("allowed_quality_grade_refs"),
        }

        candidate_dates = list(
            Quant.objects.filter(
                sku__in=unique_skus,
                _quantity__gt=0,
                target_date__gt=today,
                target_date__lte=horizon,
            )
            .order_by("target_date")
            .values_list("target_date", flat=True)
            .distinct()
        )
        remaining = set(unique_skus)
        result: dict[str, tuple[date, dict]] = {}
        for candidate in candidate_dates:
            if not remaining:
                break
            infos = availability_for_skus(
                sorted(remaining),
                target_date=candidate,
                **kwargs,
            )
            for sku in tuple(remaining):
                info = infos.get(sku) or {}
                if Decimal(str(info.get("planned") or 0)) <= 0:
                    continue
                result[sku] = (candidate, info)
                remaining.remove(sku)
        return result
    except Exception:
        logger.debug(
            "waitlist.next_batch_availability degraded; returning empty",
            exc_info=True,
        )
        return {}


def next_batch_availability(
    sku: str,
    *,
    channel_ref: str | None = None,
) -> tuple[date, dict] | None:
    """Próxima fornada elegível e capacidade, para um SKU."""
    return next_batch_availability_for_skus(
        [sku],
        channel_ref=channel_ref,
    ).get(sku)


def next_batch_date(sku: str, *, channel_ref: str | None = None) -> date | None:
    """Data da próxima fornada elegível no scope/QC deste canal."""
    next_batch = next_batch_availability(sku, channel_ref=channel_ref)
    return next_batch[0] if next_batch else None


def reserve_target_date(
    sku: str,
    qty: Decimal,
    *,
    channel_ref: str | None = None,
) -> date | None:
    """Data que a reserva deve carregar para entrar na fila deste SKU.

    ``None`` = nada a fazer, siga com o comportamento de hoje. Só devolve a
    data da fornada quando o que existe para hoje NÃO cobre o pedido: a
    pronta-entrega continua sendo servida primeiro, e a fila só é acionada
    quando ela acaba (FCFS — quem chega antes leva o que já existe).
    """
    if not is_enabled(channel_ref) or not sku:
        return None
    try:
        from shopman.stockman.services.availability import availability_for_sku

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref) if channel_ref else {}
        info = availability_for_sku(
            sku,
            safety_margin=int(scope.get("safety_margin") or 0),
            allowed_positions=scope.get("allowed_positions"),
            excluded_positions=scope.get("excluded_positions"),
            expiry_margin_days=int(scope.get("expiry_margin_days") or 0),
            include_nonconforming=bool(scope.get("sells_nonconforming", True)),
            allowed_quality_grade_refs=scope.get("allowed_quality_grade_refs"),
        )
    except Exception:
        logger.debug("waitlist.reserve_target_date degraded; returning None", exc_info=True)
        return None

    if info.get("is_paused"):
        return None
    promisable = Decimal(str(info.get("total_promisable") or 0))
    if promisable >= Decimal(str(qty)):
        return None
    return next_batch_date(sku, channel_ref=channel_ref)


# ──────────────────────────────────────────────────────────────────────
# Ciclo de vida da reserva (WP-P2E F2)
#
# A fila é uma compra em DUAS fases. A reserva (fermata) não cobra nada e
# não corre relógio: ela espera a fornada. Quando a fornada sai, a vaga não
# vira pedido sozinha — o cliente confirma, dentro de um prazo. Quem não
# confirma perde a vaga para o próximo da fila, e nem o cliente nem a loja
# ficam sabendo por acaso: liberação é sempre anunciada dos dois lados.
# ──────────────────────────────────────────────────────────────────────

NONE = "none"
FERMATA = "fermata"
CONFIRMING = "confirming"
CONFIRMED = "confirmed"
RELEASED = "released"

WAITLIST_KEY = "waitlist"


# ── "Isto é fila?" — a pergunta se responde no DADO, não só no carimbo ──
#
# Reserva de fila espera um LOTE, e por isso sempre aponta para o quant desse
# lote (``next_batch_date`` só devolve data onde existe quant planejado, e o
# hold ancora nele). Reserva de DEMANDA (política ``demand_ok``: café,
# Jambon-Beurre, croque) não aponta para lote nenhum — ``quant`` é nulo —
# porque não existe lote a esperar.
#
# ⚠️ O carimbo sozinho não basta, e a razão está no banco. Até 29/08 o
# ``metadata.planned`` marcava as DUAS, e holds indefinidos não expiram nunca:
# os que foram gravados antes da separação continuam vivos lá, dizendo "fila"
# sobre um café. Sem esta cláusula eles seguiriam abrindo "Lista de espera" na
# sacola, "avisamos quando ficarem prontos" na revisão e o painel de fila no
# acompanhamento — o mesmo bug de três telas, agora só para quem já era
# cliente. Perguntar pelo quant conserta os dois tempos de uma vez, sem
# migração de dado.
WAITLIST_HOLD_FILTER = {
    "metadata__planned": True,
    f"metadata__{QUALITY_GRADE_POLICY_VERSION_METADATA_KEY}": QUALITY_GRADE_POLICY_VERSION,
    "quant__isnull": False,
}


def is_waitlist_hold(hold) -> bool:
    """True quando este hold é uma reserva de fila sob a política vigente.

    A versão congelada não é detalhe de implementação: ``StockPlanning.realize``
    recusa materializar um hold legado porque não sabe quais graus de qualidade o
    canal aceitava quando a promessa foi feita. Se a fila o aceitasse mesmo assim,
    o fim da produção chamaria o cliente para confirmar estoque que nunca foi
    reservado para ele.
    """
    metadata = hold.metadata or {}
    return (
        bool(metadata.get("planned"))
        and metadata.get(QUALITY_GRADE_POLICY_VERSION_METADATA_KEY)
        == QUALITY_GRADE_POLICY_VERSION
        and hold.quant_id is not None
    )


def _quant_reservation_is_sound(hold, *, available: Decimal | None = None) -> bool:
    """A reserva cabe de fato no Quant ao qual está ligada.

    ``Quant.available`` desconta todos os holds vivos. Validar o saldo agregado,
    e não apenas ``quantity >= hold.quantity``, fecha o caso em que dois holds
    individualmente parecem caber mas juntos deixam o Quant negativo. Quando o
    Quant já é físico, a promessa também precisa continuar dentro da allowlist de
    QC congelada no hold: uma reclassificação posterior do lote não pode chamar o
    cliente remoto para um produto que o canal jamais poderia oferecer.
    """
    try:
        quant = hold.quant
        if quant.quantity < 0 or (quant.available if available is None else available) < 0:
            return False

        metadata = hold.metadata or {}
        allowed_grades = metadata.get(QUALITY_GRADE_ALLOWLIST_METADATA_KEY)
        if quant.target_date is None and allowed_grades is not None and quant.batch:
            from shopman.stockman.models import Batch

            grade_ref = (
                Batch.objects.filter(sku=hold.sku, ref=quant.batch)
                .values_list("quality_grade_ref", flat=True)
                .first()
            )
            if not grade_ref or grade_ref not in set(allowed_grades):
                return False
        return True
    except (AttributeError, TypeError):
        return False


def _is_waiting_hold(hold, *, available: Decimal | None = None) -> bool:
    """Reserva válida ainda ancorada no lote planejado (fermata)."""
    return (
        is_waitlist_hold(hold)
        and hold.expires_at is None
        and hold.quant.target_date is not None
        and _quant_reservation_is_sound(hold, available=available)
    )


def _is_materialized_hold(hold) -> bool:
    """Reserva válida transferida por ``StockPlanning.realize`` ao físico.

    O realize troca o Quant planejado por um Quant físico e inicia o TTL. Os dois
    fatos são exigidos: somente mudar um carimbo não basta para abrir a janela.
    """
    from django.utils import timezone

    return (
        is_waitlist_hold(hold)
        and hold.expires_at is not None
        and hold.expires_at >= timezone.now()
        and hold.quant.target_date is None
        and _quant_reservation_is_sound(hold)
    )


def _order_holds(
    order,
    *,
    sku: str | None = None,
    include_expired: bool = False,
    for_update: bool = False,
):
    """Holds deste pedido (por padrão somente os ainda vivos)."""
    try:
        from django.db.models import Q
        from django.utils import timezone
        from shopman.stockman.models import Hold, HoldStatus
    except Exception:
        logger.debug("waitlist._order_holds degraded", exc_info=True)
        return []

    qs = Hold.objects.filter(
        metadata__reference=f"order:{order.ref}",
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
    )
    if not include_expired:
        qs = qs.filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
    if sku:
        qs = qs.filter(sku=sku)
    if for_update:
        qs = qs.select_for_update()
    return list(qs.order_by("created_at"))


def state_for(order, *, holds=None, quant_available: dict | None = None) -> str:
    """Estado da fila deste pedido.

    ``fermata`` é DERIVADO do hold, não gravado: enquanto existir reserva
    planejada sem prazo, o pedido está esperando a fornada, e não há dois
    lugares para essa verdade divergirem. Os estados que carregam decisão e
    prazo (``confirming``/``confirmed``/``released``) ficam em
    ``Order.data['waitlist']``, porque deles não dá para derivar o relógio.
    """
    stored = ((order.data or {}).get(WAITLIST_KEY) or {}).get("state")
    if stored in (CONFIRMING, CONFIRMED, RELEASED):
        return stored
    for hold in (_order_holds(order) if holds is None else holds):
        available = quant_available.get(hold.quant_id) if quant_available is not None else None
        if _is_waiting_hold(hold, available=available):
            return FERMATA
    return NONE


def states_for(orders) -> dict[str, str]:
    """One Hold query for the board, including other reservations on its quants.

    The shared predicate still decides fermata. The batch's available balance
    includes every active hold on relevant quants, not just the visible orders.
    No cache survives this projection.
    """
    from collections import defaultdict

    from django.db.models import Q, Subquery
    from shopman.stockman.models import Hold

    orders = list(orders)
    refs = [f"order:{order.ref}" for order in orders]
    if not refs:
        return {}
    relevant_quants = Hold.objects.active().filter(metadata__reference__in=refs).values("quant_id")
    holds = list(Hold.objects.active().filter(
        Q(metadata__reference__in=refs) | Q(quant_id__in=Subquery(relevant_quants)),
    ).select_related("quant").order_by("created_at"))
    grouped = defaultdict(list)
    held = defaultdict(lambda: Decimal("0"))
    quantities = {}
    for hold in holds:
        grouped[(hold.metadata or {}).get("reference")].append(hold)
        if hold.quant_id is not None:
            held[hold.quant_id] += hold.quantity
            quantities[hold.quant_id] = hold.quant.quantity
    available = {pk: quantity - held[pk] for pk, quantity in quantities.items()}
    return {order.ref: state_for(order, holds=grouped[f"order:{order.ref}"], quant_available=available) for order in orders}


def planned_batch_date(order) -> date | None:
    """A fornada que este pedido espera, lida do hold.

    Enquanto o lote não sai, a data que interessa ao cliente é a DELE — e é o
    hold que a carrega, não o bloco gravado.
    """
    for hold in _order_holds(order):
        if is_waitlist_hold(hold) and hold.target_date:
            return hold.target_date
    return None


def _write_state(order, **fields) -> None:
    data = dict(order.data or {})
    block = dict(data.get(WAITLIST_KEY) or {})
    block.update({k: v for k, v in fields.items() if v is not None})
    data[WAITLIST_KEY] = block
    order.data = data
    order.save(update_fields=["data"])


def queue_for(sku: str, target_date: date | None = None) -> list:
    """Pedidos em fermata para este SKU, em ordem FCFS.

    A ordem é a de criação do HOLD, não a do pedido: quem reservou primeiro
    entrou primeiro na fila, mesmo que tenha fechado o pedido depois.
    """
    try:
        from shopman.stockman.models import Hold, HoldStatus
    except Exception:
        logger.debug("waitlist.queue_for degraded", exc_info=True)
        return []

    holds = Hold.objects.filter(
        sku=sku,
        expires_at__isnull=True,
        quant__target_date__isnull=False,
        metadata__reference__startswith="order:",
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        **WAITLIST_HOLD_FILTER,
    ).select_related("quant")
    if target_date is not None:
        holds = holds.filter(target_date__lte=target_date)
    holds = [hold for hold in holds.order_by("created_at") if _is_waiting_hold(hold)]

    return _orders_from_holds(holds, require_state=FERMATA)


def _materialized_queue_for(sku: str, target_date: date | None = None) -> list:
    """Pedidos cujas reservas o realize transferiu ao estoque físico.

    Esta fila curta existe entre ``StockPlanning.realize`` e ``open_window``.
    Separá-la da fermata é essencial: antes do realize o hold tem Quant planejado
    e nenhum prazo; depois dele tem Quant físico e TTL vivo.
    """
    from django.utils import timezone
    from shopman.stockman.models import Hold, HoldStatus

    holds = Hold.objects.filter(
        sku=sku,
        expires_at__gte=timezone.now(),
        quant__target_date__isnull=True,
        metadata__reference__startswith="order:",
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        **WAITLIST_HOLD_FILTER,
    ).select_related("quant")
    if target_date is not None:
        holds = holds.filter(target_date__lte=target_date)
    holds = [hold for hold in holds.order_by("created_at") if _is_materialized_hold(hold)]
    return _orders_from_holds(holds)


def _orders_from_holds(holds, *, require_state: str | None = None) -> list:
    """Converte holds FCFS em pedidos, preservando a ordem do primeiro hold."""
    from shopman.orderman.models import Order

    seen: set[str] = set()
    refs: list[str] = []
    for hold in holds:
        ref = str((hold.metadata or {}).get("reference") or "")[len("order:"):]
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    if not refs:
        return []

    by_ref = {
        o.ref: o
        for o in Order.objects.filter(ref__in=refs).exclude(
            status__in=("cancelled", "rejected", "returned"),
        )
    }
    orders = [by_ref[ref] for ref in refs if ref in by_ref]
    if require_state is not None:
        orders = [order for order in orders if state_for(order) == require_state]
    return orders


def _held_qty(order, sku: str) -> Decimal:
    return sum(
        (h.quantity for h in _order_holds(order, sku=sku)),
        Decimal("0"),
    )


def _materialized_holds_for_order(order, sku: str, *, for_update: bool = False) -> list:
    """Holds materializados somente quando TODA a reserva de fila está pronta.

    Uma linha pode ter sido coberta por mais de um hold e um pedido pode esperar
    mais de um SKU. A CTA confirma o PEDIDO inteiro; portanto, abrir a janela
    quando apenas o SKU que disparou esta chamada saiu do forno prometeria os
    demais sem reserva física. Qualquer hold marcado como fila mas
    legado/inválido também bloqueia fechado.
    """
    from django.utils import timezone

    all_holds = _order_holds(
        order,
        include_expired=True,
        for_update=for_update,
    )
    # ``_order_holds`` traz apenas statuses vivos. Isso é correto para saldo,
    # mas insuficiente como prova do pedido inteiro: se o sweeper já marcou a
    # reserva pronta de outra linha como RELEASED, ela desaparece da query. Os
    # IDs adotados no commit são o manifesto canônico; qualquer um ausente do
    # conjunto vivo significa que a CTA não pode mais prometer o pedido todo.
    tracked_hold_ids = {
        str(entry.get("hold_id"))
        for entry in ((order.data or {}).get("hold_ids") or [])
        if isinstance(entry, dict) and entry.get("hold_id")
    }
    active_hold_ids = {str(hold.hold_id) for hold in all_holds}
    if tracked_hold_ids and not tracked_hold_ids.issubset(active_hold_ids):
        return []
    marked = [
        hold
        for hold in all_holds
        if bool((hold.metadata or {}).get("planned"))
    ]
    if not marked or any(not is_waitlist_hold(hold) for hold in marked):
        return []
    if not all(_is_materialized_hold(hold) for hold in marked):
        return []
    # A confirmação é do pedido inteiro. Itens que já estavam prontos também
    # precisam conservar uma reserva viva até a fornada pendente sair; aceitar
    # apenas os holds ``planned`` poderia chamar o cliente depois que outro item
    # do mesmo pedido já expirou. Demanda preparada sob pedido é válida sem Quant,
    # mas ainda precisa carregar a política atual e um prazo vivo.
    for hold in all_holds:
        if hold in marked:
            continue
        metadata = hold.metadata or {}
        if metadata.get(QUALITY_GRADE_POLICY_VERSION_METADATA_KEY) != QUALITY_GRADE_POLICY_VERSION:
            return []
        if hold.expires_at is not None and hold.expires_at < timezone.now():
            return []
        if hold.quant_id is None:
            if not metadata.get("on_demand"):
                return []
            continue
        if hold.quant.target_date is not None or not _quant_reservation_is_sound(hold):
            return []
    return [hold for hold in marked if hold.sku == sku]


def open_window(
    sku: str,
    *,
    qty_available: Decimal,
    channel_ref: str | None = None,
) -> list[str]:
    """A fornada saiu: abre a janela de confirmação para os primeiros da fila.

    Serve FCFS até a quantidade materializada acabar. Pedido que não cabe
    inteiro na sobra NÃO é servido pela metade — fica na fermata esperando a
    próxima fornada, porque meia reserva não é uma promessa que dê para
    cumprir.

    Devolve os refs dos pedidos que entraram em confirmação.
    """
    from django.db import transaction
    from django.utils import timezone
    from shopman.orderman.models import Order

    remaining = Decimal(str(qty_available))
    if remaining <= 0:
        return []

    opened: list[str] = []

    for candidate in _materialized_queue_for(sku):
        if remaining <= 0:
            break
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=candidate.pk)
            if state_for(order) != NONE:
                continue
            materialized = _materialized_holds_for_order(
                order,
                sku,
                for_update=True,
            )
            needed = sum((hold.quantity for hold in materialized), Decimal("0"))
            if needed <= 0 or needed > remaining:
                continue
            # ``production.emit_goods`` não tem um canal: a mesma fornada atende a
            # fila FCFS de todos eles. O prazo, porém, é a promessa do canal em que
            # cada pedido nasceu. ``channel_ref`` explícito preserva o override dos
            # callers antigos; sem ele, cada pedido resolve o próprio canal.
            order_cfg = config(channel_ref or order.channel_ref)
            now = timezone.now()
            deadline = now + timedelta(minutes=order_cfg.confirmation_minutes)
            _write_state(
                order,
                state=CONFIRMING,
                sku=sku,
                opened_at=now.isoformat(),
                deadline=deadline.isoformat(),
                qty=str(needed),
            )
            # A janela e sua outbox são um fato só. Se não for possível gravar
            # o aviso, esta transação volta e o prazo não começa em silêncio.
            _notify_customer(order, "waitlist_available", deadline=deadline.isoformat())
            remaining -= needed
            opened.append(order.ref)

    if opened:
        logger.info(
            "waitlist.open_window sku=%s served=%s remaining=%s",
            sku, len(opened), remaining,
        )
    return opened


def confirm(order) -> bool:
    """O cliente confirmou dentro do prazo: a reserva vira pedido de verdade.

    A cobrança acontece AQUI (``charge_at=confirmation``) — nada foi cobrado
    na reserva, então quem desiste não precisa de estorno. Fora do prazo a
    confirmação é recusada: a vaga já é de outro.
    """
    from django.db import transaction
    from django.utils import timezone
    from shopman.orderman.models import Order

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if state_for(locked) != CONFIRMING:
            return False
        block = (locked.data or {}).get(WAITLIST_KEY) or {}
        deadline = _parse_iso(block.get("deadline"))
        if deadline is not None and timezone.now() > deadline:
            _release_locked(locked, reason="confirmation_timeout")
            return False
        sku = str(block.get("sku") or "")
        if not sku or not _materialized_holds_for_order(
            locked,
            sku,
            for_update=True,
        ):
            _release_locked(locked, reason="reservation_invalid")
            return False

        _write_state(locked, state=CONFIRMED, confirmed_at=timezone.now().isoformat())
        # Gateway fora do lock: a reserva confirmada já está durável e o
        # idempotency key do pagamento protege replay do callback.
        transaction.on_commit(lambda order_pk=locked.pk: _charge_by_pk(order_pk))
        logger.info("waitlist.confirm order=%s", locked.ref)
        return True


def _charge_by_pk(order_pk: int) -> None:
    from shopman.orderman.models import Order

    try:
        order = Order.objects.get(pk=order_pk)
    except Order.DoesNotExist:
        logger.warning("waitlist._charge skipped missing order pk=%s", order_pk)
        return
    _charge(order)


def _charge(order) -> None:
    """A cobrança da fila acontece AQUI, e só aqui (``charge_at=confirmation``).

    Nada foi cobrado na reserva — é o que torna desistir barato para os dois
    lados: quem sai da fila não precisa de estorno, e a loja não segura
    dinheiro de pedido que pode não acontecer. Quem confirma e não paga cai no
    payment-timeout que já existe, e a vaga volta pela mesma porta do
    ``release``.
    """
    try:
        from shopman.shop.services import notification, payment

        # Callback e sweep podem disputar com cancelamento/liberação. Releia o
        # fato antes de falar com o gateway: uma instância stale nunca autoriza
        # cobrar um pedido que já saiu da confirmação.
        order.refresh_from_db()
        if state_for(order) != CONFIRMED or order.status in (
            "cancelled",
            "rejected",
            "returned",
        ):
            return
        if config(order.channel_ref).charge_at != "confirmation":
            return
        payment.initiate(order)
        order.refresh_from_db()
        payment_data = (order.data or {}).get("payment") or {}
        method = str(payment_data.get("method") or "").strip().lower()
        if not method:
            # O meio pode ser escolhido depois da confirmação. Não consumir a
            # identidade permanente do aviso antes de haver o que cobrar.
            logger.warning(
                "waitlist._charge pending retry without method order=%s",
                order.ref,
            )
            return
        if (
            not payment.settles_without_gateway(method)
            and not payment_data.get("intent_ref")
        ):
            # ``payment.initiate`` já gravou/avisou a falha. Não consumir o
            # dedupe permanente de payment_requested antes de existir QR/link;
            # o reconciliador tentará de novo com a mesma chave estável.
            logger.warning(
                "waitlist._charge pending retry without intent order=%s",
                order.ref,
            )
            return
        notification.send(order, "payment_requested")
    except Exception:
        logger.warning("waitlist._charge failed order=%s", order.ref, exc_info=True)


def release(order, *, reason: str) -> list[str]:
    """Devolve a vaga e conta para os dois lados.

    Liberação NUNCA é silenciosa: o cliente é avisado de que saiu da fila e
    a loja recebe alerta, porque a vaga que volta é decisão dela (servir o
    próximo ou pôr na gôndola). Com ``release_policy=serve_next`` a fila tem
    preferência e o próximo é servido na hora.
    """
    from django.db import transaction
    from shopman.orderman.models import Order

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        return _release_locked(locked, reason=reason)


def _release_locked(order, *, reason: str) -> list[str]:
    """Libera uma vez sob lock da Order; caller já está em ``atomic``."""
    from django.db import transaction
    from django.utils import timezone

    current_state = state_for(order)
    if current_state == RELEASED:
        return []
    if reason == "confirmation_timeout":
        block = (order.data or {}).get(WAITLIST_KEY) or {}
        deadline = _parse_iso(block.get("deadline"))
        if current_state != CONFIRMING or deadline is None or timezone.now() <= deadline:
            return []

    block = (order.data or {}).get(WAITLIST_KEY) or {}
    sku = block.get("sku") or ""
    qty = Decimal(str(block.get("qty") or 0))
    if not sku:
        for hold in _order_holds(order):
            if is_waitlist_hold(hold):
                sku, qty = hold.sku, hold.quantity
                break

    # A CTA é do PEDIDO inteiro. Se ele esperava duas fornadas, expirar a
    # confirmação precisa devolver as duas reservas; soltar só o SKU que abriu
    # a janela deixaria o outro estoque físico preso para sempre.
    freed_by_sku = _release_holds(order)
    _write_state(
        order,
        state=RELEASED,
        released_at=timezone.now().isoformat(),
        release_reason=reason,
    )
    _notify_customer(order, "waitlist_released", reason=reason)
    alert_rows = list(freed_by_sku.items()) or [(sku, qty)]
    for released_sku, released_qty in alert_rows:
        _alert_store(
            order,
            sku=released_sku,
            qty=released_qty,
            reason=reason,
        )
    logger.info("waitlist.release order=%s sku=%s reason=%s", order.ref, sku, reason)

    if not freed_by_sku:
        return []
    cfg = config(order.channel_ref)
    if cfg.release_policy != "serve_next":
        return []
    # Não adquirir a próxima Order enquanto ainda seguramos esta Order e seus
    # Holds. Duas expirações simultâneas poderiam formar A→B / B→A e deadlockar.
    # O retorno é deliberadamente vazio: servir o próximo virou trabalho
    # pós-commit, e portanto seu resultado não é síncrono com ``release``.
    budgets = tuple(freed_by_sku.items())
    transaction.on_commit(lambda: _serve_next_after_commit(budgets))
    return []


def _serve_next_after_commit(budgets: tuple[tuple[str, Decimal], ...]) -> None:
    """Serve os próximos somente depois que os locks da liberação caíram.

    Falha transitória não perde o fato: ``reconcile_materialized_windows`` lê os
    holds físicos ainda sem janela na próxima varredura.
    """
    for released_sku, released_qty in budgets:
        try:
            # Sem override: cada próximo pedido recebe o prazo do próprio canal.
            open_window(released_sku, qty_available=released_qty)
        except Exception:
            logger.exception(
                "waitlist.serve_next failed sku=%s; durable sweep will retry",
                released_sku,
            )


def reconcile_materialized_windows() -> int:
    """Abre janelas perdidas depois que o estoque já materializou os holds.

    O callback de uma signal não é uma outbox: o processo pode cair ou a fila de
    Directives pode estar indisponível depois do commit do ``realize``. O próprio
    hold físico é o receipt durável. Esta varredura encontra pedidos ainda em
    ``NONE`` e entrega cada SKU ao mesmo ``open_window`` que revalida Order e
    Holds sob lock, preservando FCFS e idempotência entre workers concorrentes.
    """
    from django.utils import timezone
    from shopman.stockman.models import Hold, HoldStatus

    skus = (
        Hold.objects.filter(
            expires_at__gte=timezone.now(),
            quant__target_date__isnull=True,
            metadata__reference__startswith="order:",
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            **WAITLIST_HOLD_FILTER,
        )
        .order_by()
        .values_list("sku", flat=True)
        .distinct()
    )
    opened: set[str] = set()
    for sku in skus.iterator():
        # O budget inclui apenas holds do próprio SKU em pedidos integralmente
        # materializados. ``open_window`` repete esta prova sob lock antes de
        # iniciar qualquer prazo.
        budget = Decimal("0")
        for order in _materialized_queue_for(sku):
            if state_for(order) != NONE:
                continue
            budget += sum(
                (hold.quantity for hold in _materialized_holds_for_order(order, sku)),
                Decimal("0"),
            )
        if budget <= 0:
            continue
        try:
            opened.update(open_window(sku, qty_available=budget))
        except Exception:
            logger.exception(
                "waitlist.reconcile_materialized failed sku=%s; next sweep will retry",
                sku,
            )
    if opened:
        logger.info("waitlist.reconcile_materialized opened=%s", len(opened))
    return len(opened)


def reconcile_confirmed_charges() -> int:
    """Recupera cobrança/outbox cujo callback pós-confirmação não terminou.

    ``transaction.on_commit`` impede gateway sob lock, mas não é uma fila
    durável: o processo pode morrer depois do commit e antes do callback. O
    estado ``CONFIRMED`` é o receipt da decisão do cliente. A varredura repõe
    tanto o intent ausente quanto a Directive ausente depois de um crash entre
    esses dois commits. Os dois efeitos usam identidades permanentes e estáveis.
    """
    from shopman.orderman.models import Order

    from shopman.shop.services import payment

    recovered = 0
    candidates = Order.objects.filter(
        data__waitlist__state=CONFIRMED,
    ).exclude(status__in=("cancelled", "rejected", "returned"))
    for order in candidates.order_by("pk").iterator():
        payment_data = (order.data or {}).get("payment") or {}
        method = str(payment_data.get("method") or "").strip().lower()
        if not method:
            continue
        if config(order.channel_ref).charge_at != "confirmation":
            continue
        requires_intent = not payment.settles_without_gateway(method)
        has_intent = bool(payment_data.get("intent_ref"))
        has_notice = _payment_request_is_recorded(order)
        if (has_intent or not requires_intent) and has_notice:
            continue
        _charge(order)
        order.refresh_from_db()
        payment_data = (order.data or {}).get("payment") or {}
        has_intent = bool(payment_data.get("intent_ref"))
        if (has_intent or not requires_intent) and _payment_request_is_recorded(order):
            recovered += 1
    if recovered:
        logger.info("waitlist.reconcile_confirmed_charges recovered=%s", recovered)
    return recovered


def _payment_request_is_recorded(order) -> bool:
    """True quando a outbox original existe ou já existiu permanentemente."""
    from shopman.orderman.models import Directive, IdempotencyKey

    from shopman.shop.directives import (
        NOTIFICATION_ORIGINAL_RECEIPT_SCOPE,
        NOTIFICATION_SEND,
    )

    dedupe_key = f"{NOTIFICATION_SEND}:{order.ref}:payment_requested"
    return IdempotencyKey.objects.filter(
        scope=NOTIFICATION_ORIGINAL_RECEIPT_SCOPE,
        key=dedupe_key,
    ).exists() or Directive.objects.filter(
        topic=NOTIFICATION_SEND,
        dedupe_key=dedupe_key,
    ).exists()


def sweep_expired() -> int:
    """Libera as janelas de confirmação vencidas. Chamado pelo maintenance worker."""
    from django.utils import timezone
    from shopman.orderman.models import Order

    # Recupera primeiro a janela que uma falha/crash entre o realize e a outbox
    # deixou sem abrir. O estado físico é durável e a operação é idempotente.
    reconcile_materialized_windows()
    # A decisão CONFIRMED também é um fato durável. Se o processo caiu antes do
    # callback pós-commit, a chave estável de payment.initiate converge o replay.
    reconcile_confirmed_charges()

    now = timezone.now()
    released = 0
    candidates = Order.objects.filter(
        data__waitlist__state=CONFIRMING,
    ).exclude(status__in=("cancelled", "rejected", "returned"))
    for order in candidates:
        deadline = _parse_iso(((order.data or {}).get(WAITLIST_KEY) or {}).get("deadline"))
        if deadline is not None and now > deadline:
            release(order, reason="confirmation_timeout")
            released += 1
    if released:
        logger.info("waitlist.sweep_expired released=%s", released)
    return released


# ── Colaboradores: prazo, holds, aviso ao cliente, alerta à loja ──


def _parse_iso(value):
    if not value:
        return None
    try:
        from django.utils.dateparse import parse_datetime

        return parse_datetime(str(value))
    except Exception:
        logger.debug("waitlist._parse_iso degraded value=%s", value, exc_info=True)
        return None


def _release_holds(order, sku: str | None = None) -> dict[str, Decimal]:
    """Solta todos os holds do pedido e devolve a quantidade por SKU.

    A vaga confirma o pedido, não uma linha. Desistir/expirar precisa devolver
    também os itens que já estavam prontos e ficaram reservados enquanto outra
    fornada era aguardada.
    """
    from shopman.shop.adapters import get_adapter

    adapter = get_adapter("stock")
    holds = _order_holds(
        order,
        sku=sku or None,
        include_expired=True,
        for_update=True,
    )
    if not holds:
        return {}
    try:
        adapter.release_holds([hold.hold_id for hold in holds])
    except Exception:
        # O caller segura uma transação da Order e de todos os Holds. Propagar é
        # o que desfaz inclusive uma liberação parcial já feita pelo adapter;
        # marcar RELEASED depois de engolir deixaria estoque preso em silêncio.
        logger.exception("waitlist._release_holds failed order=%s", order.ref)
        raise
    freed_by_sku: dict[str, Decimal] = {}
    for hold in holds:
        # Demanda (quant=None) também é encerrada, mas não devolve capacidade
        # física/planejada e portanto jamais vira budget para ``serve_next``.
        if hold.quant_id is None:
            continue
        freed_by_sku[hold.sku] = freed_by_sku.get(hold.sku, Decimal("0")) + hold.quantity
    return freed_by_sku


def _notify_customer(order, template: str, **extra) -> None:
    """Aviso ativo ao cliente. Nunca silencioso — nem para dar, nem para tirar."""
    from shopman.shop.services import notification

    notification.send(order, template, **extra)


def _alert_store(order, *, sku: str, qty: Decimal, reason: str) -> None:
    """Alerta no Gestor: a vaga voltou e alguém precisa saber disso.

    A loja não descobre por acaso que abriu vaga — ela decide o que fazer
    com ela (a fila serve o próximo sozinha, mas a gôndola é decisão humana).
    """
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type="waitlist_released",
        severity="warning",
        message=(
            f"Pedido {order.ref} saiu da fila de espera ({reason}). "
            f"{qty} un. de {sku or 'item'} voltaram a ficar disponíveis — "
            f"a fila serve o próximo; a gôndola é decisão sua."
        ),
        order_ref=order.ref,
        dedupe_key=f"waitlist_released:{order.ref}:{sku}",
    )


def _qty_display(value: Decimal) -> str:
    """Quantidade sem cauda de zeros: o relatório é lido por gente, e "5.000"
    numa fila de 5 pães parece milhar."""
    normalized = Decimal(str(value)).normalize()
    if normalized == normalized.to_integral_value():
        normalized = normalized.to_integral_value()
    return format(normalized, "f")


def report() -> list[dict]:
    """Retrato da fila viva, por SKU e em ordem FCFS (WP-P2E F3).

    Quem decide pôr a vaga na gôndola precisa saber quanta gente está
    esperando e há quanto tempo — o selo do card conta um pedido de cada vez,
    e essa é a pergunta do outro lado: "vale abrir a fornada extra?".
    """
    from django.utils import timezone
    from shopman.stockman.models import Hold, HoldStatus

    now = timezone.now()
    skus = (
        Hold.objects.filter(
            expires_at__isnull=True,
            metadata__reference__startswith="order:",
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            **WAITLIST_HOLD_FILTER,
        )
        .values_list("sku", flat=True)
        .distinct()
    )

    rows: list[dict] = []
    for sku in sorted(set(skus)):
        entries = []
        for position, order in enumerate(queue_for(sku), start=1):
            batch_date = planned_batch_date(order)
            entries.append({
                "position": position,
                "order_ref": order.ref,
                "state": state_for(order),
                "qty": _qty_display(_held_qty(order, sku)),
                "batch_date": batch_date.isoformat() if batch_date else None,
                "waiting_minutes": int((now - order.created_at).total_seconds() // 60),
            })
        if entries:
            rows.append({
                "sku": sku,
                "waiting": len(entries),
                "qty_reserved": _qty_display(sum((Decimal(e["qty"]) for e in entries), Decimal("0"))),
                "queue": entries,
            })
    return rows
