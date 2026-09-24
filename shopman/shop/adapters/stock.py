"""
Internal stock adapter — delegates to Stockman (Core).

Core: StockService (holds, movements, queries)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_product(sku: str):
    """Resolve SKU to Product via Offerman."""
    from shopman.offerman.models import Product

    return Product.objects.get(sku=sku)


def check_availability(
    sku: str,
    qty: Decimal,
    target_date: date | None = None,
    *,
    safety_margin: int = 0,
    allowed_positions: list[str] | None = None,
) -> dict:
    """
    Check stock availability for a SKU.

    Returns:
        {"available": bool, "available_qty": Decimal, "message": str | None}
    """
    from shopman.stockman.service import Stock as stock

    try:
        product = _get_product(sku)
    except ObjectDoesNotExist:
        return {
            "available": False,
            "available_qty": Decimal("0"),
            "message": f"Produto não encontrado: {sku}",
        }

    if allowed_positions is not None:
        from shopman.stockman.models import Position

        total = Decimal("0")
        positions = Position.objects.filter(ref__in=allowed_positions)
        for pos in positions:
            total += stock.available(product, target_date=target_date, position=pos)
        available = total
    else:
        available = stock.available(product, target_date=target_date)

    if target_date and target_date > timezone.localdate() and safety_margin > 0:
        available = max(Decimal("0"), available - Decimal(str(safety_margin)))

    return {
        "available": qty <= available,
        "available_qty": Decimal(str(available)),
        "message": None if qty <= available else f"Disponível: {available}",
    }


def create_hold(
    sku: str,
    qty: Decimal,
    ttl_minutes: int = 30,
    *,
    target_date: date | None = None,
    reference: str | None = None,
    channel_ref: str | None = None,
    apply_safety_margin: bool = True,
    allow_demand: bool = False,
    **metadata,
) -> dict:
    """
    Create a stock hold for a SKU.

    When ``channel_ref`` is provided, the channel's stock scope
    (``allowed_positions`` / ``excluded_positions`` from ``ChannelConfig.stock``)
    is resolved and passed through to the Stockman hold so eligibility matches
    the availability read.

    ``apply_safety_margin`` liga a margem de segurança do canal. É True na
    RESERVA de carrinho (a margem protege a vitrine do oversell), mas deve ser
    False no hold de COMMIT: um pedido já colocado pode consumir o buffer —
    bloqueá-lo sub-reservaria uma venda real.

    ``allow_demand=True`` autoriza o fallback de DEMANDA do Stockman
    (hold ``quant=None``) quando nenhum quant satisfaz — encomenda para data
    sem plano registra a demanda em vez de recusar. Produto pausado continua
    recusando.

    Returns:
        {"success": bool, "hold_id": str | None, "error_code": str | None,
         "message": str | None, "expires_at": datetime | None, "is_planned": bool}
    """
    from shopman.stockman.exceptions import StockError
    from shopman.stockman.service import Stock as stock

    try:
        product = _get_product(sku)
    except ObjectDoesNotExist:
        return {
            "success": False,
            "hold_id": None,
            "error_code": "product_not_found",
            "message": f"Produto não encontrado: {sku}",
            "expires_at": None,
            "is_planned": False,
        }

    expires_at = timezone.now() + timedelta(minutes=ttl_minutes)

    hold_kwargs = dict(metadata)
    if reference:
        hold_kwargs["reference"] = reference

    scope = get_channel_scope(channel_ref) if channel_ref else {}
    allowed_positions = scope.get("allowed_positions")
    excluded_positions = scope.get("excluded_positions")
    safety_margin = int(scope.get("safety_margin") or 0) if apply_safety_margin else 0

    try:
        hold_id = stock.hold(
            qty,
            product,
            target_date=target_date or timezone.localdate(),
            expires_at=expires_at,
            allowed_positions=allowed_positions,
            excluded_positions=excluded_positions,
            safety_margin=safety_margin,
            # Gates de LOTE do canal (C2): a reserva respeita o mesmo escopo
            # da leitura — vitrine e hold nunca discordam.
            expiry_margin_days=scope.get("expiry_margin_days", 0),
            include_nonconforming=scope.get("sells_nonconforming", True),
            allowed_quality_grade_refs=scope.get("allowed_quality_grade_refs"),
            allow_demand=allow_demand,
            **hold_kwargs,
        )

        from shopman.stockman.models import Hold

        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)

        # Duas reservas SEM PRAZO, e elas não são a mesma coisa (AVAILABILITY-PLAN §8):
        #
        #   • **fornada planejada** (``quant.target_date`` preenchido) — o pão ainda
        #     não existe; a pessoa espera o lote sair. Isto É fila de espera.
        #   • **demanda** (``quant is None``, política ``demand_ok``) — café,
        #     Jambon-Beurre, croque: montado na hora, não sai de lote nenhum. Não
        #     existe fila em que entrar, porque não existe lote a esperar.
        #
        # Nas duas o TTL fica desligado (a fornada porque o relógio só começa na
        # materialização, a demanda porque não há o que materializar), e por isso
        # elas pareciam iguais. Mas só a primeira é fila.
        #
        # ⚠️ Enquanto ``metadata.planned`` carimbava as DUAS, um café na sacola lia
        # "Lista de espera", a revisão do pedido dizia "avisamos quando ficarem
        # prontos", e o acompanhamento abria o painel de fila (``state_for`` →
        # ``fermata``) — três telas mentindo a partir de um carimbo só. E o próprio
        # código já sabia distinguir: ``is_planned`` saía ``False`` para a demanda, e
        # a distinção era jogada fora na linha seguinte.
        #
        # Agora cada uma tem a sua marca. Quem pergunta "isto é fila?" lê
        # ``planned``; quem pergunta "isto é preparado na hora?" lê ``on_demand``.
        is_planned = False
        is_on_demand = hold.quant is None
        is_indefinite = is_on_demand or hold.quant.target_date is not None
        if is_indefinite:
            is_planned = not is_on_demand
            marker = "on_demand" if is_on_demand else "planned"
            hold.expires_at = None
            hold.metadata = {**(hold.metadata or {}), marker: True}
            hold.save(update_fields=["expires_at", "metadata"])

        return {
            "success": True,
            "hold_id": hold_id,
            "error_code": None,
            "message": None,
            "expires_at": hold.expires_at,
            "is_planned": is_planned,
        }
    except StockError as e:
        return {
            "success": False,
            "hold_id": None,
            "error_code": e.code if hasattr(e, "code") else "hold_failed",
            "message": str(e),
            "expires_at": None,
            "is_planned": False,
        }
    except Exception as e:
        logger.warning("create_hold failed for SKU %s: %s", sku, e, exc_info=True)
        return {
            "success": False,
            "hold_id": None,
            "error_code": "hold_failed",
            "message": str(e),
            "expires_at": None,
            "is_planned": False,
        }


def create_holds_up_to(
    sku: str,
    qty: Decimal,
    ttl_minutes: int = 30,
    *,
    target_date: date | None = None,
    reference: str | None = None,
    channel_ref: str | None = None,
    apply_safety_margin: bool = True,
    **metadata,
) -> list[tuple[str, Decimal]]:
    """Reserva ATÉ ``qty``, em quantas reservas forem precisas.

    O Stockman ancora cada reserva em UM quant (1:1 por desenho), e
    ``create_hold`` falha quando nenhum quant sozinho cobre o pedido inteiro.
    Aqui a reserva vai em pedaços: a cada volta, o maior saldo livre de um
    quant elegível (no escopo do canal) vira uma reserva, até cobrir ``qty``
    ou acabar o livre. Nunca reserva além do que está livre — reserva alheia
    continua valendo.

    Cada volta precisa PROVAR progresso: a reserva tem de cair num quant (não
    em demanda, ``quant=None``) e o livre do escopo tem de baixar. Se não
    baixou, a reserva não segura nada — é desfeita e o laço para. Mais um teto
    de voltas, para que nenhum desencontro entre a leitura do livre e a
    escolha do quant no Stockman vire laço longo.

    Returns:
        ``[(hold_id, qty), ...]`` do que foi reservado (vazia se nada coube).
    """
    from shopman.stockman.models import Hold

    def _free_by_quant() -> dict[int, Decimal]:
        return _free_by_eligible_quant(sku, target_date=target_date, channel_ref=channel_ref)

    reserved: list[tuple[str, Decimal]] = []
    remaining = Decimal(str(qty))
    free = _free_by_quant()
    for _ in range(_MAX_PARTIAL_HOLDS):
        if remaining <= 0:
            break
        largest_free = max(free.values(), default=Decimal("0"))
        piece = min(largest_free, remaining)
        if piece <= 0:
            break
        result = create_hold(
            sku,
            piece,
            ttl_minutes,
            target_date=target_date,
            reference=reference,
            channel_ref=channel_ref,
            apply_safety_margin=apply_safety_margin,
            **metadata,
        )
        if not result.get("success"):
            break
        hold = Hold.objects.filter(pk=int(result["hold_id"].split(":")[1])).only("quant").first()
        free_after = _free_by_quant()
        consumed = sum(free.values(), Decimal("0")) - sum(free_after.values(), Decimal("0"))
        if hold is None or hold.quant_id is None or consumed < piece:
            # Sem progresso real (demanda, ou o livre não baixou): a reserva não
            # garante baixa nenhuma. Desfaz e para — o resto vira alerta.
            logger.warning(
                "create_holds_up_to: reserva sem progresso sku=%s hold=%s piece=%s consumed=%s",
                sku, result["hold_id"], piece, consumed,
            )
            release_holds([result["hold_id"]])
            break
        reserved.append((result["hold_id"], piece))
        remaining -= piece
        free = free_after
    return reserved


def _free_by_eligible_quant(sku: str, *, target_date: date | None, channel_ref: str | None) -> dict[int, Decimal]:
    """Livre de cada quant elegível no escopo do canal (a mesma régua da reserva)."""
    from shopman.stockman.services.scope import quants_eligible_for

    scope = get_channel_scope(channel_ref) if channel_ref else {}
    eligible = quants_eligible_for(
        sku,
        target_date=target_date or timezone.localdate(),
        allowed_positions=scope.get("allowed_positions"),
        excluded_positions=scope.get("excluded_positions"),
        expiry_margin_days=scope.get("expiry_margin_days", 0),
        include_nonconforming=scope.get("sells_nonconforming", True),
        allowed_quality_grade_refs=scope.get("allowed_quality_grade_refs"),
    )
    return {quant.pk: quant.available for quant in eligible}


# Teto de reservas parciais por item: cada uma exige um quant com livre, e uma
# vitrine real tem poucos. 20 é folga larga e ainda mantém o pior caso barato.
_MAX_PARTIAL_HOLDS = 20


# Carimbos que o Stockman e o ciclo do hold escrevem no metadata; a reserva que
# devolve o troco ao carrinho nasce com os seus próprios, nunca com os da cedida.
_HOLD_LIFECYCLE_METADATA = frozenset({
    "reference", "release_reason", "released_by", "confirmed_by", "ceded_to", "ceded_remainder_of",
})


def is_cart_hold(hold) -> bool:
    """A reserva é de CARRINHO — pode ceder à venda já consumada?

    O critério é o que a casa já usa para ordenar quem sai primeiro quando a
    fornada encolhe (``handlers/_stock_receivers``) e para varrer órfãos
    (``sweep_orphan_holds``): a ``reference`` do hold. Sacola é a chave da
    sessão; pedido é ``order:<ref>`` desde o commit (``_retag_hold_for_order``
    ou a reserva nascida no pedido). Não há campo novo.

    Ficam de fora, por serem promessa e não intenção de compra:

    - pedido (``order:``) — comprometido/pago, nunca cede;
    - hold sem referência — reserva manual do operador, decisão humana;
    - reserva de produção (``purpose=workorder``) — insumo, não venda;
    - fila de fornada e demanda (``planned``/``on_demand``) e todo hold sem
      prazo: quem está na fila recebeu a palavra da casa, inclusive nos 15 min
      de confirmação depois que o lote sai.
    """
    metadata = hold.metadata or {}
    reference = str(metadata.get("reference") or "")
    if not reference or reference.startswith("order:"):
        return False
    if metadata.get("purpose") == "workorder":
        return False
    if metadata.get("planned") or metadata.get("on_demand"):
        return False
    return hold.expires_at is not None


def reserve_ceding_cart_holds(
    sku: str,
    qty: Decimal,
    ttl_minutes: int = 30,
    *,
    beneficiary: str,
    target_date: date | None = None,
    reference: str | None = None,
    channel_ref: str | None = None,
    exclude_references: tuple[str, ...] = (),
    **metadata,
) -> tuple[list[tuple[str, Decimal]], list[dict]]:
    """Reserva ``qty`` para uma venda já consumada, cedendo reservas de CARRINHO.

    Para o caminho otimista (balcão, marketplace pago): o pão já saiu pela
    porta, e a sacola de alguém na loja online é só intenção de compra. Quando
    o livre não basta, cedem as reservas de carrinho (``is_cart_hold``) nos
    quants elegíveis da venda — as mais recentes primeiro, e só o que falta.
    Reserva de pedido não cede: o que nem assim couber volta ao chamador, que
    alerta o operador.

    Uma reserva maior que a falta é solta inteira (o Stockman não parte hold)
    e o troco volta ao carrinho numa reserva nova, na mesma sessão e com o
    mesmo prazo, DEPOIS que a venda reservou a sua parte.

    Concorrência: tudo numa transação. Os holds candidatos são travados
    (``select_for_update``) antes de qualquer quant — a mesma ordem hold→quant
    do commit da loja, que trava o hold no ``retag`` e o quant ao reservar o
    resto. Um hold que o checkout adotou no mesmo instante já tem
    ``order:<ref>`` quando o lock sai e não cede; um hold que cedeu primeiro
    deixa de estar ativo, e o ``retag`` do checkout devolve ``False``.

    Returns:
        ``(reserved, ceded)`` — ``reserved`` como em ``create_holds_up_to``;
        ``ceded`` com uma entrada por reserva cedida: ``{hold_id, reference,
        qty, ceded_qty, remainder_hold_id}``.
    """
    from django.db import transaction
    from shopman.stockman.models import Hold
    from shopman.stockman.service import Stock as stock

    qty = Decimal(str(qty))
    ceded: list[dict] = []
    remainders: list[tuple[Hold, Decimal, dict]] = []
    with transaction.atomic():
        quant_ids = list(_free_by_eligible_quant(sku, target_date=target_date, channel_ref=channel_ref))
        # Trava os candidatos ANTES de medir o livre: a medida vale até o fim.
        candidates = list(
            Hold.objects.select_for_update()
            .filter(quant_id__in=quant_ids)
            .active()
            .exclude(metadata__reference__startswith="order:")
            .order_by("-created_at", "-pk")
        ) if quant_ids else []
        free = _free_by_eligible_quant(sku, target_date=target_date, channel_ref=channel_ref)
        shortfall = qty - sum(free.values(), Decimal("0"))
        for hold in candidates:
            if shortfall <= 0:
                break
            cart_reference = str((hold.metadata or {}).get("reference") or "")
            if not is_cart_hold(hold) or cart_reference in exclude_references:
                continue
            take = min(hold.quantity, shortfall)
            released = stock.release(hold.hold_id, reason=f"Cedida à venda {beneficiary}")
            # O destino fica no próprio hold, para quem abrir a reserva depois.
            released.metadata = {**(released.metadata or {}), "ceded_to": beneficiary}
            released.save(update_fields=["metadata"])
            logger.info(
                "stock.cart_hold_ceded hold=%s session=%s qty=%s ceded=%s to=%s",
                hold.hold_id, cart_reference, hold.quantity, take, beneficiary,
            )
            shortfall -= take
            entry = {
                "hold_id": hold.hold_id,
                "reference": cart_reference,
                "qty": float(hold.quantity),
                "ceded_qty": float(take),
                "remainder_hold_id": None,
            }
            ceded.append(entry)
            if hold.quantity > take:
                remainders.append((hold, hold.quantity - take, entry))

        reserved = create_holds_up_to(
            sku,
            qty,
            ttl_minutes,
            target_date=target_date,
            reference=reference,
            channel_ref=channel_ref,
            **metadata,
        )

        for hold, remainder, entry in remainders:
            entry["remainder_hold_id"] = _return_remainder_to_cart(hold, remainder)
    return reserved, ceded


def _return_remainder_to_cart(hold, remainder: Decimal) -> str | None:
    """Devolve à sacola o que a reserva cedida tinha além da falta."""
    from shopman.orderman.models import Session

    cart_reference = str((hold.metadata or {}).get("reference") or "")
    session_channel = (
        Session.objects.filter(session_key=cart_reference).values_list("channel_ref", flat=True).first()
    )
    carried = {
        key: value
        for key, value in (hold.metadata or {}).items()
        if not key.startswith("_") and key not in _HOLD_LIFECYCLE_METADATA
    }
    result = create_hold(
        hold.sku,
        remainder,
        target_date=hold.target_date,
        reference=cart_reference,
        channel_ref=session_channel,
        # Não é reserva nova: é a sacola recebendo de volta o que já era dela.
        # A margem da vitrine barraria justamente esta devolução.
        apply_safety_margin=False,
        ceded_remainder_of=hold.hold_id,
        **carried,
    )
    if not result.get("success"):
        # A sacola descobre na revalidação/checkout, como numa reserva vencida.
        logger.warning(
            "stock.cart_hold_remainder_lost hold=%s session=%s qty=%s code=%s",
            hold.hold_id, cart_reference, remainder, result.get("error_code"),
        )
        return None
    extend_hold(result["hold_id"], expires_at=hold.expires_at)
    return result["hold_id"]


def fulfill_hold(hold_id: str, *, qty: Decimal | None = None) -> dict:
    """
    Fulfill a confirmed hold (decrements stock).

    Handles PENDING → CONFIRMED → FULFILLED transition automatically.

    `qty` overrides the hold's reserved quantity for the Move delta, allowing
    partially-adopted holds (where the session hold exceeded the ordered qty)
    to consume only the needed amount.

    Returns:
        {"success": bool, "error_code": str | None, "message": str | None}
    """
    from shopman.stockman import Hold, HoldStatus, Move, StockError
    from shopman.stockman.service import Stock as stock

    pk = int(hold_id.split(":")[1])
    try:
        hold = Hold.objects.get(pk=pk)
    except Hold.DoesNotExist:
        return {
            "success": False,
            "error_code": "hold_not_found",
            "message": f"Hold {hold_id} não encontrado",
        }

    if hold.status == HoldStatus.FULFILLED:
        return {"success": True, "error_code": None, "message": None}

    try:
        if hold.status == HoldStatus.PENDING:
            try:
                stock.confirm(hold_id)
            except StockError:
                hold.refresh_from_db()
                if hold.status not in (HoldStatus.CONFIRMED, HoldStatus.FULFILLED):
                    raise

        stock.fulfill(hold_id, quantity=qty, kind=Move.Kind.SELL)
        return {"success": True, "error_code": None, "message": None}
    except StockError as e:
        return {
            "success": False,
            "error_code": e.code if hasattr(e, "code") else "fulfill_failed",
            "message": str(e),
        }
    except DatabaseError as e:
        # Saldo do sistema ACIMA do físico: o exato caso para o qual o alerta
        # ``stock_fulfill_failed`` foi escrito ("o estoque do sistema está acima
        # do físico") — e o único que nunca chegava nele.
        #
        # ``Move.save()`` tem um guarda Python que levanta
        # ``StockError('INSUFFICIENT_QUANTITY')`` quando o saldo fica negativo,
        # mas ele é CÓDIGO MORTO para o caso negativo: quem estoura primeiro é o
        # ``CheckConstraint`` ``stk_quant_quantity_non_negative``, no próprio
        # UPDATE, uma linha antes. O ``IntegrityError`` não é ``StockError``,
        # atravessava ``fulfill_hold`` e ``stock.fulfill``, e o
        # ``create_operator_alert(severity="critical")`` nunca executava. Pedido
        # pago, sem baixa, sem alerta — e o ``sweep_stuck_orders`` re-despachava
        # a cada 5 min falhando de novo, para sempre.
        #
        # ``DatabaseError`` cobre ``IntegrityError`` (é subclasse) e o resto do
        # que o banco pode recusar aqui. O ``atomic`` de ``StockHolds.fulfill``
        # já desfez o savepoint quando a exceção chega até este ponto, então
        # transformar em resultado (e não em exceção) é seguro.
        logger.error("fulfill_hold: banco recusou a baixa de %s: %s", hold_id, e, exc_info=True)
        return {
            "success": False,
            "error_code": "insufficient_quantity",
            "message": (f"O banco recusou a baixa: o saldo do sistema está acima do físico. ({e})"),
        }


def release_holds(hold_ids: list[str]) -> None:
    """Release multiple holds (cancel reservations)."""
    from shopman.stockman import StockError
    from shopman.stockman.service import Stock as stock

    for hold_id in hold_ids:
        try:
            stock.release(hold_id, reason="Liberado via Shopman")
        except StockError as exc:
            if exc.code == "INVALID_STATUS":
                logger.info("release_holds: Hold %s already terminal", hold_id)
                continue
            # INVALID_HOLD e demais falhas não são idempotência comprovada. O
            # caller decide se pode compensar; a fila depende desta exceção
            # para desfazer atomicamente uma liberação multi-item.
            raise


def release_holds_for_reference(reference: str) -> int:
    """Release all active holds for a given reference (e.g. order ref)."""
    from shopman.stockman import StockError, StockHolds
    from shopman.stockman.service import Stock as stock

    try:
        holds = StockHolds.find_active_by_reference(reference)
        count = 0
        for hold in holds:
            try:
                stock.release(hold.hold_id, reason="Idempotency cleanup")
                count += 1
            except StockError as exc:
                if exc.code != "INVALID_STATUS":
                    raise
                logger.info(
                    "release_holds_for_reference: Hold %s already terminal",
                    hold.hold_id,
                )
        return count
    except Exception:
        logger.warning("release_all_holds: unexpected error", exc_info=True)
        return 0


def receive_return(
    sku: str,
    qty: Decimal,
    *,
    reference: str | None = None,
    reason: str = "Devolução",
) -> None:
    """Receive returned stock back into inventory."""
    from shopman.stockman import Move
    from shopman.stockman.services.movements import StockMovements

    full_reason = f"{reason} (ref: {reference})" if reference else reason
    StockMovements.receive(quantity=qty, sku=sku, reason=full_reason, kind=Move.Kind.RETURN)


# ── Session hold queries ─────────────────────────────────────────────


def find_holds_by_reference(
    reference: str,
    *,
    sku: str | None = None,
    metadata_filters: dict[str, object] | None = None,
) -> list[tuple[str, str, Decimal]]:
    """Find active holds (PENDING/CONFIRMED, não expirados) tagged with `reference`.

    Um hold expirado não protege mais nada — adotá-lo no commit criaria um
    pedido "coberto" por uma reserva que outro cliente já pode ter consumido.

    Returns:
        List of (hold_id, sku, qty) tuples ordered by pk (FIFO).
    """
    from shopman.stockman import StockHolds

    holds = StockHolds.find_active_by_reference(reference)
    if sku:
        holds = holds.filter(sku=sku)
    for key, value in (metadata_filters or {}).items():
        holds = holds.filter(**{f"metadata__{key}": value})
    return [(h.hold_id, h.sku, Decimal(str(h.quantity))) for h in holds]


def retag_hold_reference(hold_id: str, new_reference: str, **extra_metadata) -> bool:
    """Update hold's reference tag (e.g. session_key → order ref).

    Extra metadata (e.g. ``priority``) is merged in the same write.

    Returns True if updated, False if hold not found.
    """
    from shopman.stockman import StockHolds

    return StockHolds.retag_reference(hold_id, new_reference, **extra_metadata)


def extend_hold(hold_id: str, *, expires_at=None) -> bool:
    """Redefine a expiração de um hold ativo (``None`` = nunca expira)."""
    from shopman.stockman import StockHolds

    return StockHolds.extend(hold_id, expires_at=expires_at)


def return_fulfilled_hold(hold_id: str, qty: Decimal, *, reference: str, reason: str) -> bool:
    """Devolve ao ledger o estoque de um hold FULFILLED (cancelamento tardio).

    A devolução entra na MESMA posição de onde o fulfill baixou — devolver
    "sem posição" sumiria da vitrine.

    Returns:
        True se devolveu; False se o hold não está FULFILLED.
    """
    from shopman.stockman import Hold, HoldStatus, Move
    from shopman.stockman.services.movements import StockMovements

    try:
        pk = int(hold_id.split(":")[1])
    except (IndexError, ValueError):
        return False
    hold = Hold.objects.select_related("quant__position").filter(pk=pk, status=HoldStatus.FULFILLED).first()
    if hold is None:
        return False

    StockMovements.receive(
        quantity=qty,
        sku=hold.sku,
        position=hold.quant.position if hold.quant else None,
        reason=f"{reason} (ref: {reference})",
        kind=Move.Kind.RETURN,
    )
    return True


# ── Availability queries ─────────────────────────────────────────────


def get_availability(
    sku: str,
    *,
    target_date: date | None = None,
    safety_margin: int = 0,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
    expiry_margin_days: int = 0,
    include_nonconforming: bool = True,
    allowed_quality_grade_refs: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Return availability info for a SKU.

    Delegates to Stockman's availability_for_sku(). Returns a dict with
    keys: sku, total_available, total_promisable, total_reserved,
    breakdown, is_planned, is_paused, is_tracked, positions.
    """
    from shopman.stockman.services.availability import availability_for_sku

    return availability_for_sku(
        sku,
        target_date=target_date,
        safety_margin=safety_margin,
        allowed_positions=allowed_positions,
        excluded_positions=excluded_positions,
        expiry_margin_days=expiry_margin_days,
        include_nonconforming=include_nonconforming,
        allowed_quality_grade_refs=allowed_quality_grade_refs,
    )


def get_channel_scope(channel_ref: str | None) -> dict:
    """Return stock scope for a channel.

    Keys: ``safety_margin`` (int), ``allowed_positions`` (list[str] | None),
    ``excluded_positions`` (list[str] | None), ``expiry_margin_days`` (int),
    ``sells_nonconforming`` (compatibilidade) e a política resolvida
    ``allowed_quality_grade_refs`` — os dois gates de LOTE do C2: a
    posição diz onde o estoque conta; o lote diz o que pode ser oferecido
    (near-expiry fora com margem; não conforme só com decisão explícita).

    The scope is resolved from ``ChannelConfig.stock`` (cascade: defaults →
    Shop.defaults → Channel.config). When no ``channel_ref`` is given the
    Stockman stub is returned so non-channel-scoped callers keep working.
    """
    if not channel_ref:
        from shopman.stockman.services.availability import (
            availability_scope_for_channel,
        )

        return availability_scope_for_channel(channel_ref)

    from shopman.shop.config import ChannelConfig, quality_grade_refs_for_channel

    cfg = ChannelConfig.for_channel(channel_ref)
    allowed_quality_grade_refs = quality_grade_refs_for_channel(
        channel_ref,
        sells_nonconforming=cfg.stock.sells_nonconforming,
    )
    sells_nonconforming = allowed_quality_grade_refs is None
    return {
        "safety_margin": cfg.stock.safety_margin,
        "allowed_positions": cfg.stock.allowed_positions,
        "excluded_positions": cfg.stock.excluded_positions,
        "expiry_margin_days": cfg.stock.expiry_margin_days,
        "sells_nonconforming": sells_nonconforming,
        # A configuração continua binária e simples. O orquestrador traduz a
        # política em refs opacas antes de atravessar a fronteira do Stockman.
        # Canais que não permitem markdown aceitam exclusivamente qualidade OK.
        "allowed_quality_grade_refs": (
            None if allowed_quality_grade_refs is None else list(allowed_quality_grade_refs)
        ),
    }


def get_promise_decision(
    sku: str,
    qty,
    *,
    target_date: date | None = None,
    safety_margin: int = 0,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
    expiry_margin_days: int = 0,
    include_nonconforming: bool = True,
    allowed_quality_grade_refs: list[str] | tuple[str, ...] | None = None,
):
    """Return Stockman's explicit operational promise decision for a SKU."""
    from shopman.stockman.services.availability import promise_decision_for_sku

    return promise_decision_for_sku(
        sku,
        qty,
        target_date=target_date,
        safety_margin=safety_margin,
        allowed_positions=allowed_positions,
        excluded_positions=excluded_positions,
        expiry_margin_days=expiry_margin_days,
        include_nonconforming=include_nonconforming,
        allowed_quality_grade_refs=allowed_quality_grade_refs,
    )


def promise_decision_from_availability(
    sku: str,
    qty,
    info: dict,
    *,
    target_date: date | None = None,
):
    """Return the default promise decision from an already-loaded availability dict."""
    from shopman.stockman.protocols.sku import PromiseDecision

    qty_d = Decimal(str(qty))
    available_qty = Decimal(str(info.get("total_promisable", 0)))
    availability_policy = info.get("availability_policy", "planned_ok")
    is_paused = bool(info.get("is_paused", False))

    if is_paused:
        approved = False
        effective_available_qty = Decimal("0")
    elif availability_policy == "demand_ok":
        approved = True
        effective_available_qty = max(available_qty, qty_d)
    else:
        approved = qty_d <= available_qty
        effective_available_qty = available_qty

    reason_code = None
    if not approved:
        reason_code = "paused" if is_paused else "insufficient_supply"

    return PromiseDecision(
        approved=approved,
        sku=sku,
        requested_qty=qty_d,
        target_date=target_date,
        availability_policy=availability_policy,
        reason_code=reason_code,
        available_qty=effective_available_qty,
        available=Decimal(str(info.get("available", 0))),
        expected=Decimal(str(info.get("expected", 0))),
        planned=Decimal(str(info.get("planned", 0))),
        is_planned=bool(info.get("is_planned", False)),
        is_paused=is_paused,
    )
