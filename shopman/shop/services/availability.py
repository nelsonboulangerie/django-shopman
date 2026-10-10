"""
Availability service — canonical sync API for stock checks and reservations.

This is the FIRST-CLASS service for "can the customer order this?" across all
channels (storefront cart, POS, totem, marketplace inbound). It wraps:

- Stockman.availability (read) — orderable/reserved/breakdown by SKU and channel
- adapters.stock.create_hold (write) — actual hold creation in Stockman
- services.substitutes.find (suggest) — fallback substitutes on shortage

Three verbs:

    check(sku, qty, *, channel_ref) -> dict
        Read-only. Returns whether `qty` of `sku` can be ordered now.

    reserve(sku, qty, *, session_key, channel_ref, ttl_minutes=30) -> dict
        Write. Checks first; if available, creates a hold tagged with session_key
        as `reference` so the order's CommitService can adopt it. On shortage,
        populates `substitutes` with suggested SKUs.

    reconcile(sku, new_qty, *, session_key, channel_ref, ttl_minutes=30) -> dict
        Write. Brings the total reserved quantity for `(session_key, sku)` to
        exactly `new_qty`. Grows by creating a fresh hold for the delta (may
        shortage); shrinks by releasing holds FIFO and returning any release
        overshoot to the session (never fails; keeps what still exists);
        `new_qty=0` releases everything.

All three return plain dicts so callers (cart UX, marketplace flow, API) can
react without coupling to Stockman internals.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from django.db import transaction

from shopman.shop.adapters import get_adapter
from shopman.shop.models import Channel

from . import substitutes, waitlist

logger = logging.getLogger(__name__)

CART_SOURCE_SKU_META = "cart_source_sku"
BUNDLE_PARENT_SKU_META = "cart_bundle_sku"


def _cart_hold_metadata(source_sku: str, *, bundle_parent_sku: str | None = None) -> dict[str, str]:
    """Metadata that scopes cart holds back to the cart line that created them."""
    metadata = {CART_SOURCE_SKU_META: source_sku}
    if bundle_parent_sku:
        metadata[BUNDLE_PARENT_SKU_META] = bundle_parent_sku
    return metadata


def bump_session_hold_expiry(session_key: str, *, ttl_minutes: int = 30) -> int:
    """Extend the TTL of every active hold tagged with ``session_key``.

    Called from the cart's write paths (add/update/set_qty) so the session's
    holds stay alive as long as the shopper is active. Orphaned holds from
    abandoned sessions still die naturally at their TTL — this just keeps
    the "active shopper" case alive.

    Indefinite holds (``expires_at IS NULL`` — planned holds) are untouched:
    their TTL only starts after materialization (AVAILABILITY-PLAN §8).

    Returns the number of holds whose ``expires_at`` was bumped.
    """
    if not session_key:
        return 0
    try:
        from datetime import timedelta

        from django.utils import timezone
        from shopman.stockman import Hold, HoldStatus
    except Exception:
        logger.debug("availability.bump_session_hold_expiry degraded; returning 0", exc_info=True)
        return 0

    new_expiry = timezone.now() + timedelta(minutes=ttl_minutes)
    return (
        Hold.objects.filter(
            metadata__reference=session_key,
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            expires_at__isnull=False,
            expires_at__lt=new_expiry,
        )
        .update(expires_at=new_expiry)
    )


def release_session_holds(session_key: str) -> int:
    """Release every active hold tagged with ``session_key``.

    A morte de uma sessão de sacola tem que devolver as reservas dela — em
    especial os holds PLANEJADOS (``expires_at=None``), que nunca expiram
    sozinhos e, órfãos, seguram a fornada do dia para sempre (WP-A do
    AVAILABILITY-SALE-PRODUCTION-PLAN). Chamado por quem encerra sessão:
    ``abandon_session``, ``assign_phone_handle(abandon_existing)`` e
    ``cleanup_stale_sessions``.

    Returns the number of holds released.
    """
    if not session_key:
        return 0
    try:
        adapter = get_adapter("stock")
        return adapter.release_holds_for_reference(session_key)
    except Exception:
        logger.warning(
            "availability.release_session_holds degraded session=%s", session_key, exc_info=True
        )
        return 0


def classify_planned_hold_for_session_sku(
    session_key: str, sku: str,
) -> dict:
    """Classify the planned-hold state of the session's holds for a SKU.

    Planned holds (AVAILABILITY-PLAN §8) are the "reservation without a
    running TTL" state that holds on planned production land on. The marker
    ``metadata.planned`` is stamped at hold creation by the stock adapter and
    survives the transition to the ready state — post-materialization the flag
    remains while ``expires_at`` goes from ``None`` (awaiting confirmation) to
    a concrete deadline set by ``StockPlanning.realize()``.

    ⚠️ O carimbo é condição necessária, não suficiente: reserva de DEMANDA
    (``demand_ok``: café, Jambon-Beurre) também nasce sem prazo, e até 29/08
    levava o mesmo carimbo. ``waitlist.WAITLIST_HOLD_FILTER`` acrescenta a
    pergunta que separa as duas — fila espera um LOTE, e lote tem quant.

    Returns:
        {
            "is_awaiting_confirmation": bool,   # any planned hold still pre-materialization
            "is_ready_for_confirmation": bool,  # all planned holds have materialized
            "deadline": datetime | None,        # earliest materialized deadline (min expires_at)
            "planned_for": date | None,         # earliest batch date the holds wait on
        }

    With multiple holds (split reservation, partial materialization) the
    rule is binary:
    - ``is_awaiting_confirmation`` = OR of every hold's pre-materialization state.
    - ``is_ready_for_confirmation`` = AND of every hold's ready state (ALL
      must have materialized before the badge flips to "Tudo pronto!").
    """
    if not session_key or not sku:
        return _empty_planned_hold()
    return classify_planned_holds_for_session(session_key, [sku]).get(sku) or _empty_planned_hold()


def classify_planned_holds_for_session(session_key: str, skus) -> dict[str, dict]:
    """``classify_planned_hold_for_session_sku`` para vários SKUs, numa consulta.

    ``{sku: classificação}`` só para os SKUs que têm reserva planejada ativa da
    sessão; quem não aparece no mapa tem a classificação vazia (nem aguardando,
    nem pronto, sem prazo, sem data). A sacola pergunta por todas as linhas de
    uma vez — perguntar por linha era uma consulta de ``Hold`` por item.
    """
    wanted = sorted({sku for sku in skus if sku})
    if not session_key or not wanted:
        return {}
    try:
        from django.db.models import Q
        from django.utils import timezone
        from shopman.stockman import Hold, HoldStatus
    except Exception:
        logger.debug("availability.classify_planned_hold degraded; returning empty", exc_info=True)
        return {}

    holds_by_sku: dict[str, list] = {}
    holds = (
        Hold.objects.filter(
            metadata__reference=session_key,
            sku__in=wanted,
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            **waitlist.WAITLIST_HOLD_FILTER,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
    )
    for hold in holds:
        holds_by_sku.setdefault(hold.sku, []).append(hold)
    return {sku: _classify_planned_holds(found) for sku, found in holds_by_sku.items()}


def _empty_planned_hold() -> dict:
    return {
        "is_awaiting_confirmation": False,
        "is_ready_for_confirmation": False,
        "deadline": None,
        "planned_for": None,
    }


def _classify_planned_holds(holds: list) -> dict:
    """A classificação de um SKU a partir das reservas planejadas dele (não vazias)."""
    any_awaiting = any(h.expires_at is None for h in holds)
    all_ready = all(h.expires_at is not None for h in holds)
    deadline = None
    if all_ready:
        deadline = min(h.expires_at for h in holds)
    planned_dates = [h.target_date for h in holds if h.target_date]

    return {
        "is_awaiting_confirmation": any_awaiting,
        "is_ready_for_confirmation": all_ready,
        "deadline": deadline,
        "planned_for": min(planned_dates) if planned_dates else None,
    }


def own_holds_by_sku(session_key: str, skus: list[str]) -> dict[str, Decimal]:
    """Sum this session's active hold quantity per SKU (single batch query).

    Canonical helper consumed by the storefront read paths (cart, PDP) that
    need to distinguish between "this SKU is unavailable to the public" and
    "this session already holds all of it". Without it, a customer who
    reserved the last N units sees "indisponível" on every surface — the
    hold is double-counted against them.

    Empty ``session_key`` or ``skus`` → ``{}`` (anonymous browsing, no cart).
    Returns ``{sku: held_qty}`` only for SKUs with active holds.
    """
    if not session_key or not skus:
        return {}
    try:
        from django.db.models import Q, Sum
        from django.utils import timezone
        from shopman.stockman import Hold, HoldStatus
    except Exception:
        logger.debug("availability.own_holds_by_sku degraded; returning {}", exc_info=True)
        return {}

    def read(missing: list[str]) -> dict[str, Decimal]:
        rows = (
            Hold.objects.filter(
                metadata__reference=session_key,
                sku__in=missing,
                status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
            .values("sku")
            .annotate(total=Sum("quantity"))
        )
        return {row["sku"]: row["total"] or Decimal("0") for row in rows}

    # No GET, o cardápio e a sacola perguntam pelos holds da MESMA sessão no
    # mesmo request: cada SKU vai ao banco uma vez (``None`` = sem hold ativo).
    from shopman.shop import request_memo

    bucket = request_memo.stock_bucket(("own_holds", session_key))
    if bucket is None:
        return read(list(skus))
    missing = [sku for sku in dict.fromkeys(skus) if sku not in bucket]
    if missing:
        fresh = read(missing)
        for sku in missing:
            bucket[sku] = fresh.get(sku)
    return {sku: bucket[sku] for sku in dict.fromkeys(skus) if bucket.get(sku) is not None}


def session_hold_dates_around(session_key: str, first_new_hold_id: str | None) -> tuple[set[date], set[date]]:
    """``(datas de antes, datas novas)`` das reservas vivas da sessão, numa consulta.

    "Novas" são as reservas criadas a partir de ``first_new_hold_id`` (a
    mutação corre sob o lock da sessão, então tudo o que ela criou tem chave
    igual ou maior; a reserva fatiada entre quants e a de combo criam várias,
    e só a primeira volta no resultado). "De antes" é o resto.

    Só conta reserva que aponta para um quant: pão pronto (a data é hoje) ou
    fornada planejada (a data é a do lote). Reserva de DEMANDA (``quant`` nulo,
    política ``demand_ok``: café, croque) não tem lote a esperar e cabe em
    qualquer data, e SKU que o Stockman não rastreia nem reserva tem; nenhum
    dos dois fixa a data da sacola.
    """
    if not session_key or not first_new_hold_id:
        return set(), set()
    try:
        first_pk = int(str(first_new_hold_id).split(":")[1])
    except (IndexError, ValueError):
        return set(), set()
    try:
        from django.db.models import Q
        from django.utils import timezone
        from shopman.stockman import Hold, HoldStatus
    except Exception:
        logger.debug("availability.session_hold_dates_around degraded; returning empty", exc_info=True)
        return set(), set()

    before: set[date] = set()
    new: set[date] = set()
    rows = (
        Hold.objects.filter(
            metadata__reference=session_key,
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            quant__isnull=False,
            target_date__isnull=False,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
        .order_by()
        .values_list("pk", "target_date")
    )
    for pk, target_date in rows:
        (new if pk >= first_pk else before).add(target_date)
    return before, new


def stock_on_dates(
    skus: list[str],
    dates: list[date],
    **scope,
) -> dict[date, dict[str, dict]]:
    """``stockman.availability_for_skus_on_dates`` com memo por request (GET/HEAD).

    O cardápio, as linhas da sacola e os portões do trilho de sugestão leem o
    estoque dos mesmos SKUs, no mesmo canal e nas mesmas datas, dentro de um
    request. Aqui cada par (SKU, data) vai ao Stockman uma vez por recorte de
    canal: quem pergunta depois recebe o que já foi lido e só lê o que falta.

    É a mesma resposta porque a leitura de um SKU numa data não depende dos
    outros SKUs nem das outras datas do lote (provado em
    ``stockman/tests/test_availability_on_dates.py``). A chave tem o recorte
    (tipo a tipo: ``0`` e ``0.0`` somam diferente), o dia de hoje e a data.
    Os holds da própria sessão NÃO entram aqui: a leitura do Stockman é a de
    todo mundo, e quem desconta o hold da sessão é o chamador
    (:func:`own_holds_by_sku`), depois.

    Devolve cópias: quem recebe pode mexer no ``dict`` sem tocar o memo.
    Fora do memo (comando, worker, request que muta) é a leitura direta.
    """
    from django.utils import timezone
    from shopman.stockman.services.availability import availability_for_skus_on_dates

    from shopman.shop import request_memo

    unique_dates = list(dict.fromkeys(dates))
    unique_skus = list(dict.fromkeys(skus))
    if not unique_skus or not unique_dates:
        return availability_for_skus_on_dates(skus, dates, **scope)
    try:
        base = ("stock_on_dates", _scope_key(scope), timezone.localdate())
        hash(base)
    except TypeError:
        return availability_for_skus_on_dates(skus, dates, **scope)
    buckets = {on: request_memo.stock_bucket((*base, on)) for on in unique_dates}
    if any(bucket is None for bucket in buckets.values()):
        return availability_for_skus_on_dates(skus, dates, **scope)

    missing = [sku for sku in unique_skus if any(sku not in buckets[on] for on in unique_dates)]
    if missing:
        fresh = availability_for_skus_on_dates(missing, unique_dates, **scope)
        for on in unique_dates:
            for sku, info in (fresh.get(on) or {}).items():
                buckets[on].setdefault(sku, info)
    return {
        on: {sku: _copy_reading(buckets[on][sku]) for sku in unique_skus if sku in buckets[on]}
        for on in unique_dates
    }


def _scope_key(scope: dict) -> tuple:
    def freeze(value):
        if isinstance(value, (list, tuple)):
            return (type(value).__name__, tuple(value))
        if isinstance(value, (set, frozenset)):
            return (type(value).__name__, tuple(sorted(value)))
        return (type(value).__name__, value)

    return tuple(sorted((key, freeze(value)) for key, value in scope.items()))


def _copy_reading(value):
    if isinstance(value, dict):
        return {key: _copy_reading(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_reading(item) for item in value]
    return value


def decide(
    sku: str,
    qty: Decimal,
    *,
    channel_ref: str | None = None,
    target_date: date | None = None,
    as_component: bool = False,
) -> dict:
    """Return a canonical promise decision for one SKU in context.

    ``as_component``: o SKU está sendo conferido como COMPONENTE de um kit. O
    portão da listagem é do que se vende — o kit, que já passou por ele —, não
    do que vai dentro: a caixa física da caixa presente não é vendável avulsa
    (não tem listagem) e mesmo assim é estoque limitado que restringe o kit.
    Só a AUSÊNCIA na listagem é perdoada: componente listado e pausado no
    canal recusa como antes, e estoque, pausa global e política de
    disponibilidade continuam valendo.
    """
    qty_d = Decimal(str(qty))
    if target_date is None:
        # A decisão sem data explícita segue a mesma escolha da reserva: usa a
        # pronta-entrega de hoje quando ela cobre a quantidade e só então ancora
        # na primeira fornada elegível. Perguntar pelo fim do horizonte fazia
        # perecíveis de validade zero parecerem vencidos ainda no dia da produção.
        from django.utils import timezone

        target_date = (
            waitlist.reserve_target_date(sku, qty_d, channel_ref=channel_ref)
            or timezone.localdate()
        )

    components = _expand_if_bundle(sku, qty_d)
    if components is not None:
        bundle_result = _check_bundle(
            sku,
            qty_d,
            components,
            channel_ref=channel_ref,
            target_date=target_date,
        )
        return {
            "approved": bundle_result["ok"],
            "sku": sku,
            "requested_qty": qty_d,
            "available_qty": bundle_result["available_qty"],
            "reason_code": bundle_result.get("error_code"),
            "is_paused": bundle_result.get("is_paused", False),
            "is_planned": bundle_result.get("is_planned", False),
            "target_date": target_date,
            "failed_sku": bundle_result.get("failed_sku"),
            "source": "availability.bundle_decision",
        }

    listing_item = _sku_in_channel_listing(sku, channel_ref)
    gate = _listing_gate_decision(
        sku, qty_d, listing_item, as_component=as_component, target_date=target_date,
    )
    if gate is not None:
        return gate

    adapter = get_adapter("stock")
    scope = adapter.get_channel_scope(channel_ref)
    info = adapter.get_availability(sku, target_date=target_date, **_availability_kwargs(scope))
    return _stock_decision(adapter, sku, qty_d, info, target_date=target_date)


def decide_many(
    lines,
    *,
    channel_ref: str | None = None,
    target_date: date | None = None,
) -> list[dict]:
    """``decide`` para várias linhas ``(sku, qty)`` com leituras em lote.

    Devolve, na ordem das linhas, exatamente o que ``decide(sku, qty,
    channel_ref=..., target_date=...)`` devolveria para cada uma. O que muda é o
    custo: ``decide`` vai ao banco umas quinze vezes por SKU (canal, vitrine,
    item da vitrine, bundle, recorte do canal, estoque, lotes, holds…), e a
    revisão da venda do PDV perguntava linha por linha. Aqui o canal, a vitrine,
    a detecção de bundle e a leitura do Stockman são feitas uma vez para todos os
    SKUs, e cada linha é decidida pelos MESMOS passos de ``decide``
    (``_listing_gate_decision`` e ``_stock_decision``).

    Ficam no caminho de ``decide``, um por um: linha sem ``target_date`` (a data
    ali depende do SKU e da quantidade, via fila de espera) e SKU que é bundle
    (a expansão é recursiva e rara no balcão).
    """
    items = [(str(sku), Decimal(str(qty))) for sku, qty in lines]
    if not items:
        return []
    if target_date is None:
        return [decide(sku, qty, channel_ref=channel_ref) for sku, qty in items]

    skus = list(dict.fromkeys(sku for sku, _qty in items))
    catalog = get_adapter("catalog")
    bulk_bundles = getattr(catalog, "bulk_bundle_skus", None)
    try:
        bundles = bulk_bundles(skus) if bulk_bundles else set(skus)
    except Exception:
        logger.debug("availability.decide_many: bundle lookup degraded; per-SKU path", exc_info=True)
        bundles = set(skus)
    simple = [sku for sku in skus if sku not in bundles]

    listing_items = _listing_items_for_skus(simple, channel_ref)
    adapter = get_adapter("stock")
    infos: dict[str, dict] = {}
    to_read = [
        sku for sku in simple
        if _listing_gate_decision(
            sku, Decimal("0"), listing_items[sku], as_component=False, target_date=target_date,
        ) is None
    ]
    if to_read:
        scope = adapter.get_channel_scope(channel_ref)
        kwargs = _availability_kwargs(scope)
        bulk_read = getattr(adapter, "get_availability_for_skus", None)
        if bulk_read is not None:
            infos = bulk_read(to_read, target_date=target_date, **kwargs)
        else:
            infos = {sku: adapter.get_availability(sku, target_date=target_date, **kwargs) for sku in to_read}

    decisions: list[dict] = []
    for sku, qty in items:
        if sku in bundles:
            decisions.append(decide(sku, qty, channel_ref=channel_ref, target_date=target_date))
            continue
        gate = _listing_gate_decision(
            sku, qty, listing_items[sku], as_component=False, target_date=target_date,
        )
        if gate is not None:
            decisions.append(gate)
            continue
        decisions.append(_stock_decision(adapter, sku, qty, infos[sku], target_date=target_date))
    return decisions


def _availability_kwargs(scope: dict) -> dict:
    """O recorte do canal nos argumentos da leitura de estoque do adapter."""
    return {
        "safety_margin": scope["safety_margin"],
        "allowed_positions": scope["allowed_positions"],
        "excluded_positions": scope.get("excluded_positions"),
        "expiry_margin_days": scope.get("expiry_margin_days", 0),
        "include_nonconforming": scope.get("sells_nonconforming", True),
        "allowed_quality_grade_refs": scope.get("allowed_quality_grade_refs"),
    }


def _listing_gate_decision(
    sku: str,
    qty_d: Decimal,
    listing_item: dict | bool,
    *,
    as_component: bool,
    target_date: date | None,
) -> dict | None:
    """A recusa do portão da vitrine, ou ``None`` quando o SKU passa por ele."""
    if listing_item is False and as_component:
        listing_item = True  # componente não precisa estar listado; pausado no canal, sim, recusa
    if listing_item is False:
        return {
            "approved": False,
            "sku": sku,
            "requested_qty": qty_d,
            "available_qty": Decimal("0"),
            "reason_code": "not_in_listing",
            "is_paused": False,
            "is_planned": False,
            "target_date": target_date,
            "failed_sku": None,
            "source": "availability.listing_gate",
        }
    if isinstance(listing_item, dict) and not listing_item.get("is_sellable", True):
        return {
            "approved": False,
            "sku": sku,
            "requested_qty": qty_d,
            "available_qty": Decimal("0"),
            "reason_code": "paused",
            "is_paused": True,
            "is_planned": False,
            "target_date": target_date,
            "failed_sku": None,
            "source": "availability.listing_gate",
        }
    # ``ListingItem.min_qty`` is kept in the model but not enforced at the
    # gate (AVAILABILITY-PLAN §10 — ``below_min_qty`` is YAGNI today).
    # Future B2B/MOQ scenarios should resurrect this with proper UX.
    return None


def _stock_decision(adapter, sku: str, qty_d: Decimal, info: dict, *, target_date: date | None) -> dict:
    """A decisão a partir da leitura de estoque já feita (passo final de ``decide``)."""
    if not info.get("is_paused", False) and not info.get("is_tracked", bool(info.get("positions"))):
        return {
            "approved": True,
            "sku": sku,
            "requested_qty": qty_d,
            "available_qty": Decimal("999999"),
            "reason_code": None,
            "is_paused": False,
            "is_planned": False,
            "target_date": target_date,
            "failed_sku": None,
            "source": "stock.untracked",
            "untracked": True,
        }

    decision = adapter.promise_decision_from_availability(
        sku,
        qty_d,
        info,
        target_date=target_date,
    )
    approved = decision.approved if isinstance(getattr(decision, "approved", None), bool) else qty_d <= info["total_promisable"]
    reason_code = getattr(decision, "reason_code", None)
    if not isinstance(reason_code, str | type(None)):
        reason_code = None if approved else ("paused" if info.get("is_paused", False) else "insufficient_stock")
    return {
        "approved": approved,
        "sku": getattr(decision, "sku", sku),
        "requested_qty": getattr(decision, "requested_qty", qty_d),
        "available_qty": getattr(decision, "available_qty", info["total_promisable"]),
        "reason_code": reason_code,
        "is_paused": getattr(decision, "is_paused", info.get("is_paused", False)),
        "is_planned": getattr(decision, "is_planned", info.get("is_planned", False)),
        "target_date": getattr(decision, "target_date", target_date),
        "failed_sku": None,
        "source": "stock.promise_decision",
    }


def check(
    sku: str,
    qty: Decimal,
    *,
    channel_ref: str | None = None,
    target_date: date | None = None,
    as_component: bool = False,
) -> dict:
    """
    Read-only availability check for a single SKU/qty in a channel scope.

    If the SKU is a bundle, expands it via CatalogService.expand() and runs
    check() recursively for each component. Returns ok=False at the first
    failing component (with failed_sku identifying it) or ok=True with
    available_qty = min constructable bundles if all components pass.

    Validations applied for simple SKUs (in order):
      1. Channel listing gate — if `channel_ref` is provided and the
         channel has a `listing_ref`, the SKU must belong structurally to that
         listing. If the listing item exists but is strategically not sellable,
         the result is ok=False with error_code="paused". If no listing item
         exists at all, ok=False with error_code="not_in_listing".
      2. Stockman availability — Offerman global pause (`is_paused`),
         per-channel safety_margin and allowed_positions, plus physical
         stock breakdown.

    Returns:
        {
            "ok": bool,                 # passes listing check AND stock check
            "available_qty": Decimal,   # total_promisable for this channel
            "is_paused": bool,          # product paused/unpublished
            "is_planned": bool,         # only future quants exist
            "breakdown": {ready, in_production},
            "error_code": str | None,   # set when ok=False
            "is_bundle": bool,          # True when SKU is a bundle
            "failed_sku": str | None,   # component that caused failure (bundles only)
        }
    """
    decision = decide(
        sku,
        qty,
        channel_ref=channel_ref,
        target_date=target_date,
        as_component=as_component,
    )
    return {
        "ok": decision["approved"],
        "available_qty": decision["available_qty"],
        "is_paused": decision["is_paused"],
        "is_planned": decision["is_planned"],
        "breakdown": {},
        "error_code": decision["reason_code"],
        "is_bundle": decision["source"] == "availability.bundle_decision",
        "failed_sku": decision.get("failed_sku"),
        "target_date": target_date,
        "untracked": decision.get("untracked", False),
    }


def _expand_if_bundle(sku: str, qty: Decimal) -> list[dict] | None:
    """Return component list if SKU is a bundle, None if it's a simple product.

    Returns None (not a bundle) when expand_bundle raises any error,
    including NOT_A_BUNDLE and SKU_NOT_FOUND — callers handle missing SKU
    via the Stockman gate.
    """
    try:
        catalog = get_adapter("catalog")
        components = catalog.expand_bundle(sku, qty)
        # Guard: if expand returns a single component with the same SKU, treat
        # as simple product (infinite recursion prevention).
        if len(components) == 1 and components[0]["sku"] == sku:
            return None
        return components
    except Exception:
        logger.debug("availability._expand_if_bundle degraded; returning None", exc_info=True)
        return None


def _check_bundle(
    bundle_sku: str,
    bundle_qty: Decimal,
    components: list[dict],
    *,
    channel_ref: str | None,
    target_date: date | None,
) -> dict:
    """Check availability of all bundle components recursively.

    Returns ok=False at the first failing component, or ok=True with
    available_qty = number of full bundles constructable from components.
    """
    min_constructable: Decimal | None = None

    for comp in components:
        comp_sku = comp["sku"]
        comp_qty = Decimal(str(comp["qty"]))

        result = check(comp_sku, comp_qty, channel_ref=channel_ref, target_date=target_date, as_component=True)

        if not result["ok"]:
            return {
                "ok": False,
                "available_qty": result["available_qty"],
                "is_paused": result.get("is_paused", False),
                "is_planned": result.get("is_planned", False),
                "breakdown": result.get("breakdown", {}),
                "error_code": result.get("error_code"),
                "is_bundle": True,
                "failed_sku": comp_sku,
                "target_date": target_date,
            }

        # Calculate how many bundles we can build from this component's stock.
        # comp["qty"] is already comp_qty_per_bundle * bundle_qty (because
        # CatalogService.expand multiplies by qty). To get per-bundle qty,
        # divide back: comp_qty_per_bundle = comp_qty / bundle_qty.
        comp_qty_per_bundle = comp_qty / bundle_qty if bundle_qty else comp_qty
        if comp_qty_per_bundle > 0:
            constructable = result["available_qty"] / comp_qty_per_bundle
        else:
            constructable = Decimal("0")

        if min_constructable is None or constructable < min_constructable:
            min_constructable = constructable

    return {
        "ok": True,
        "available_qty": min_constructable if min_constructable is not None else Decimal("0"),
        "is_paused": False,
        "is_planned": False,
        "breakdown": {},
        "error_code": None,
        "is_bundle": True,
        "failed_sku": None,
        "target_date": target_date,
    }


def _sku_in_channel_listing(sku: str, channel_ref: str | None) -> dict | bool:
    """Return listing item dict when the SKU belongs to the channel's listing.

    Returns True when the check is skipped (no channel_ref or no listing_ref),
    False when the SKU fails the listing gate.

    Callers treat True as "gate skipped", a dict as "gate passed with item data"
    (used for min_qty and sellability checks), and False as "gate failed".

    If the channel has no `listing_ref` configured, the check is skipped
    (returns True) — this preserves backward compatibility for channels that
    don't constrain their catalog (e.g. internal POS).
    """
    if not channel_ref:
        return True

    try:
        channel = Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist:
        return True

    listing_ref = channel.ref
    if not listing_ref:
        return True

    # Gate is only active when a Listing with this ref actually exists.
    # Convention: listing.ref == channel.ref, but listing may not be configured.
    catalog = get_adapter("catalog")
    if not catalog.listing_exists(listing_ref):
        return True

    item = catalog.get_listing_item(sku, listing_ref)
    if item is None:
        return False
    return item


def _listing_items_for_skus(skus: list[str], channel_ref: str | None) -> dict[str, dict | bool]:
    """``_sku_in_channel_listing`` para vários SKUs: canal e vitrine lidos uma vez.

    Mesmas respostas, SKU a SKU: ``True`` quando o portão não se aplica, o
    ``dict`` do item quando o SKU está na vitrine, ``False`` quando não está.
    """
    if not skus:
        return {}
    skipped = dict.fromkeys(skus, True)
    if not channel_ref:
        return skipped
    channel = Channel.objects.filter(ref=channel_ref).first()
    if channel is None or not channel.ref:
        return skipped
    listing_ref = channel.ref
    catalog = get_adapter("catalog")
    if not catalog.listing_exists(listing_ref):
        return skipped
    bulk_items = getattr(catalog, "bulk_listing_items", None)
    if bulk_items is None:
        return {sku: _sku_in_channel_listing(sku, channel_ref) for sku in skus}
    found = bulk_items(skus, listing_ref)
    return {sku: found.get(sku, False) for sku in skus}


def _channel_hold_ttl_minutes(channel_ref: str | None) -> int:
    """TTL de hold de carrinho do canal (config) — default seguro de 30 min."""
    if not channel_ref:
        return 30
    try:
        from shopman.shop.config import ChannelConfig
        from shopman.shop.models import Channel

        channel = Channel.objects.filter(ref=channel_ref).first()
        if channel is None:
            return 30
        configured = ChannelConfig.for_channel(channel).stock.hold_ttl_minutes
        return int(configured) if configured else 30
    except Exception:
        logger.debug("availability.hold_ttl_lookup_failed channel=%s", channel_ref, exc_info=True)
        return 30


def reserve(
    sku: str,
    qty: Decimal,
    *,
    session_key: str,
    channel_ref: str | None = None,
    target_date: date | None = None,
    ttl_minutes: int | None = None,
) -> dict:
    """
    Inline check + hold creation for the storefront/POS/marketplace flows.

    ``ttl_minutes=None`` resolve o TTL configurado no canal
    (``ChannelConfig.stock.hold_ttl_minutes``); sem configuração, 30 minutos.

    On success: creates a Stockman hold tagged with `reference=session_key` so
    the eventual CommitService can adopt the holds when the order is created.

    On shortage or pause: returns ok=False with `substitutes` populated via
    services.substitutes.find().

    Returns:
        {
            "ok": bool,
            "hold_id": str | None,
            "available_qty": Decimal,
            "is_paused": bool,
            "error_code": str | None,    # only when ok=False
            "substitutes": list[dict],  # only when ok=False
        }
    """
    qty_d = Decimal(str(qty))
    if ttl_minutes is None:
        ttl_minutes = _channel_hold_ttl_minutes(channel_ref)
    if target_date is None:
        # A pronta-entrega é servida primeiro; só quando ela não cobre o pedido
        # a reserva ancora na fornada planejada — e ancora na data DELA, não no
        # horizonte, senão a sacola prometeria um dia que não é o do lote.
        target_date = waitlist.reserve_target_date(sku, qty_d, channel_ref=channel_ref)

    listing_error = _reserve_listing_gate_error(
        sku,
        qty_d,
        channel_ref=channel_ref,
    )
    if listing_error is not None:
        return listing_error

    # Bundles need the existing component-aware path. Simple SKUs can let the
    # Stockman hold be the authoritative success-path validation; if it fails,
    # we run the richer read path below to explain the refusal to the customer.
    components = _expand_if_bundle(sku, qty_d)
    if components:
        status = check(sku, qty_d, channel_ref=channel_ref, target_date=target_date)
        return _reserve_checked_status(
            sku,
            qty_d,
            status,
            session_key=session_key,
            channel_ref=channel_ref,
            target_date=target_date,
            ttl_minutes=ttl_minutes,
        )

    adapter = get_adapter("stock")
    result = adapter.create_hold(
        sku=sku,
        qty=qty_d,
        ttl_minutes=ttl_minutes,
        reference=session_key,
        target_date=target_date,
        channel_ref=channel_ref,
        **_cart_hold_metadata(sku),
    )
    if result.get("success"):
        return {
            "ok": True,
            "hold_id": result["hold_id"],
            "available_qty": qty_d,
            "is_paused": False,
            "error_code": None,
            "substitutes": [],
        }

    status = check(sku, qty_d, channel_ref=channel_ref, target_date=target_date)
    return _reserve_checked_status(
        sku,
        qty_d,
        status,
        session_key=session_key,
        channel_ref=channel_ref,
        target_date=target_date,
        ttl_minutes=ttl_minutes,
        adapter=adapter,
        initial_hold_result=result,
        initial_hold_error_code=result.get("error_code"),
    )


def _reserve_listing_gate_error(
    sku: str,
    qty_d: Decimal,
    *,
    channel_ref: str | None,
) -> dict | None:
    listing_item = _sku_in_channel_listing(sku, channel_ref)
    if listing_item is False:
        return {
            "ok": False,
            "hold_id": None,
            "available_qty": Decimal("0"),
            "is_paused": True,
            "is_planned": False,
            "error_code": "not_in_listing",
            "substitutes": substitutes.find(sku, qty=qty_d, channel=channel_ref),
        }
    if isinstance(listing_item, dict) and not listing_item.get("is_sellable", True):
        return {
            "ok": False,
            "hold_id": None,
            "available_qty": Decimal("0"),
            "is_paused": True,
            "is_planned": False,
            "error_code": "paused",
            "substitutes": substitutes.find(sku, qty=qty_d, channel=channel_ref),
        }
    return None


def _reserve_checked_status(
    sku: str,
    qty_d: Decimal,
    status: dict,
    *,
    session_key: str,
    channel_ref: str | None,
    target_date: date | None,
    ttl_minutes: int,
    adapter=None,
    initial_hold_result: dict | None = None,
    initial_hold_error_code: str | None = None,
) -> dict:
    adapter = adapter or get_adapter("stock")

    # SKUs that are not tracked by Stockman: skip the hold (the order will
    # commit without stock reservation, same as the legacy noop path).
    if status.get("untracked"):
        return {
            "ok": True,
            "hold_id": None,
            "available_qty": status["available_qty"],
            "is_paused": False,
            "error_code": None,
            "substitutes": [],
        }

    if not status["ok"]:
        return {
            "ok": False,
            "hold_id": None,
            "available_qty": status["available_qty"],
            "is_paused": status["is_paused"],
            "is_planned": status.get("is_planned", False),
            "error_code": status.get("error_code") or (
                "paused" if status["is_paused"] else "insufficient_stock"
            ),
            "substitutes": substitutes.find(sku, qty=qty_d, channel=channel_ref),
        }

    # For bundles: create one hold per component (not one hold for the bundle SKU).
    if status.get("is_bundle"):
        components = _expand_if_bundle(sku, qty_d)
        if components:
            return _reserve_bundle_components(
                sku, qty_d, components,
                session_key=session_key,
                ttl_minutes=ttl_minutes,
                channel_ref=channel_ref,
                target_date=target_date,
                available_qty=status["available_qty"],
                adapter=adapter,
            )

    result = initial_hold_result or adapter.create_hold(
        sku=sku,
        qty=qty_d,
        ttl_minutes=ttl_minutes,
        reference=session_key,
        target_date=target_date,
        channel_ref=channel_ref,
        **_cart_hold_metadata(sku),
    )

    if not result.get("success"):
        # Stockman's Hold model pins each hold to a single Quant. When the
        # requested qty fits in the channel's total_promisable but not in any
        # single quant (stock fragmented across positions/batches), the hold
        # fails with INSUFFICIENT_AVAILABLE even though check() said ok.
        #
        # Split the request into multiple partial holds, one per quant, so
        # the caller receives the qty it legitimately has access to. All
        # partial holds share the same session_key reference so CommitService
        # adopts them together.
        error_code = initial_hold_error_code or result.get("error_code")
        if error_code == "INSUFFICIENT_AVAILABLE":
            partial = _reserve_across_quants(
                sku=sku, qty=qty_d,
                ttl_minutes=ttl_minutes,
                session_key=session_key,
                channel_ref=channel_ref,
                target_date=target_date,
                adapter=adapter,
                hold_metadata=_cart_hold_metadata(sku),
            )
            if partial["ok"]:
                return partial
            # Fall through to 422 with partial["available_qty"] reflecting what
            # we could actually hold (may be less than status.available_qty).
            return {
                "ok": False,
                "hold_id": None,
                "available_qty": partial["available_qty"],
                "is_paused": False,
                "is_planned": False,
                "error_code": "insufficient_stock",
                "substitutes": substitutes.find(sku, qty=qty_d, channel=channel_ref),
            }

        logger.info(
            "availability.reserve: hold failed sku=%s qty=%s code=%s",
            sku, qty_d, error_code,
        )
        return {
            "ok": False,
            "hold_id": None,
            "available_qty": status["available_qty"],
            "is_paused": False,
            "is_planned": False,
            "error_code": error_code or "hold_failed",
            "substitutes": substitutes.find(sku, qty=qty_d, channel=channel_ref),
        }

    return {
        "ok": True,
        "hold_id": result["hold_id"],
        "available_qty": status["available_qty"],
        "is_paused": False,
        "error_code": None,
        "substitutes": [],
    }


def _reserve_across_quants(
    *,
    sku: str,
    qty: Decimal,
    ttl_minutes: int,
    session_key: str,
    channel_ref: str | None,
    target_date: date | None,
    adapter,
    hold_metadata: dict[str, str] | None = None,
) -> dict:
    """Split a reservation across multiple quants/batches when no single quant
    fits the full qty. All partial holds share ``reference=session_key`` so
    Commit adopts them together.

    Returns the same shape as ``reserve()``; on partial success (stock covered
    exactly), ``hold_id`` carries the first hold id for compatibility and
    ``ok=True``. When the combined quant capacity is still short, returns
    ``ok=False`` with ``available_qty`` reflecting what actually fit.
    """
    remaining = Decimal(qty)
    reserved = Decimal("0")
    first_hold_id: str | None = None
    created_hold_ids: list[str] = []
    attempts = 0
    # Hard cap to avoid infinite loops if adapter misbehaves.
    while remaining > 0 and attempts < 32:
        attempts += 1
        # Binary search downward: try remaining, then half, etc., until the
        # adapter accepts a single-quant hold.
        current_try = remaining
        accepted = False
        while current_try > 0:
            r = adapter.create_hold(
                sku=sku,
                qty=current_try,
                ttl_minutes=ttl_minutes,
                reference=session_key,
                target_date=target_date,
                channel_ref=channel_ref,
                **(hold_metadata or {}),
            )
            if r.get("success"):
                if first_hold_id is None:
                    first_hold_id = r["hold_id"]
                created_hold_ids.append(r["hold_id"])
                reserved += current_try
                remaining -= current_try
                accepted = True
                break
            if r.get("error_code") != "INSUFFICIENT_AVAILABLE":
                break
            # Halve and retry. Decimal halving is exact enough for integer units.
            current_try = (current_try // 2)
        if not accepted:
            break

    if remaining > 0:
        # Roll back whatever we reserved so the cart does not end up with a
        # partial reservation that the customer did not consent to.
        if created_hold_ids:
            try:
                adapter.release_holds(created_hold_ids)
            except Exception:
                logger.warning(
                    "availability.reserve: failed to release partial holds %s",
                    created_hold_ids,
                )
        logger.info(
            "availability.reserve: split holds insufficient sku=%s asked=%s reserved=%s",
            sku, qty, reserved,
        )
        return {"ok": False, "available_qty": int(reserved)}

    logger.info(
        "availability.reserve: split across %d holds sku=%s qty=%s",
        len(created_hold_ids), sku, qty,
    )
    return {
        "ok": True,
        "hold_id": first_hold_id,
        "available_qty": int(qty),
        "is_paused": False,
        "error_code": None,
        "substitutes": [],
    }


def reconcile(
    sku: str,
    new_qty: Decimal,
    *,
    session_key: str,
    channel_ref: str | None = None,
    target_date: date | None = None,
    ttl_minutes: int = 30,
) -> dict:
    """
    Bring the total reserved qty for `(session_key, sku)` to exactly `new_qty`.

    Used by the cart's stepper and remove flows: while `reserve()` assumes a
    brand-new additive reservation, `reconcile()` computes the delta against
    the session's existing holds for the SKU and adjusts accordingly.

    Grow (`new_qty > current`):
        Runs `check()` first; creates a hold for `(new_qty - current)`. On
        shortage or hold failure, returns `ok=False` with substitutes and
        leaves existing holds untouched.

    Shrink (`new_qty < current`):
        Releases holds FIFO until the released qty covers the diff. If the
        last released hold overshoots, the overshoot goes back to the session
        through ``adapter.return_hold_remainder``: the same reservation when it
        lands on the original quant (date, expiry, kind markers, no shop-window
        margin), a regular cart reservation when it would land on another quant,
        and whatever still fits when the quant shrank. Shrinking never fails;
        when stock no longer covers the line, the session keeps what exists.

    Zero (`new_qty == 0`):
        Releases every hold for the SKU in this session.

    No-op (`new_qty == current`):
        Returns immediately with `ok=True`.

    Bundles are expanded via `CatalogService.expand()` and reconciled per
    component (each component is tracked as a separate hold).

    Returns:
        {
            "ok": bool,
            "hold_ids": list[str],       # newly created hold_ids (grow/shrink-overshoot)
            "released_ids": list[str],   # released hold_ids (shrink)
            "available_qty": Decimal,    # only meaningful on shortage
            "is_paused": bool,
            "error_code": str | None,
            "substitutes": list[dict],
        }
    """
    new_qty_d = Decimal(str(new_qty))
    if new_qty_d < 0:
        new_qty_d = Decimal("0")

    # Bundles are reconciled per component. Component holds are scoped by
    # cart-line metadata so a combo using CROIS-01 cannot consume/release a
    # shopper's separate CROIS-01 line.
    if new_qty_d > 0:
        components = _expand_if_bundle(sku, new_qty_d)
        if components is not None:
            return _reconcile_bundle_components(
                sku, new_qty_d, components,
                session_key=session_key,
                channel_ref=channel_ref,
                target_date=target_date,
                ttl_minutes=ttl_minutes,
            )
    else:
        # new_qty == 0 on a potential bundle: release the component holds this
        # session reserved for the bundle, surgically (FIFO, bounded by the
        # expected per-component qty). Previously this was deferred to
        # commit-time which left orphan holds when the shopper abandoned the
        # cart (AVAILABILITY-PLAN Gap D).
        probe = _expand_if_bundle(sku, Decimal("1"))
        if probe is not None:
            per_unit_components = _expand_if_bundle(sku, Decimal("1")) or []
            released_ids = _release_bundle_component_holds(
                session_key=session_key,
                bundle_sku=sku,
                components=per_unit_components,
            )
            logger.info(
                "availability.reconcile: bundle %s released %d component holds",
                sku, len(released_ids),
            )
            return {
                "ok": True,
                "hold_ids": [],
                "released_ids": released_ids,
                "available_qty": Decimal("0"),
                "is_paused": False,
                "error_code": None,
                "substitutes": [],
            }

    return _reconcile_simple(
        sku, new_qty_d,
        session_key=session_key,
        channel_ref=channel_ref,
        target_date=target_date,
        ttl_minutes=ttl_minutes,
        hold_metadata=_cart_hold_metadata(sku),
        metadata_filters=_cart_hold_metadata(sku),
    )


def _load_session_holds_for_sku(
    session_key: str,
    sku: str,
    *,
    metadata_filters: dict[str, str] | None = None,
) -> list[tuple[str, Decimal]]:
    """Return FIFO list of `(hold_id, qty)` for active session holds on `sku`."""
    adapter = get_adapter("stock")
    holds = adapter.find_holds_by_reference(
        session_key,
        sku=sku,
        metadata_filters=metadata_filters,
    )
    return [(hold_id, qty) for hold_id, _sku, qty in holds]


def session_line_held_qty(session_key: str, sku: str) -> Decimal:
    """Quanto a LINHA ``sku`` da sacola segura hoje (as mesmas reservas que o ``reconcile`` ajusta).

    Só as reservas da própria linha: a unidade de CROIS-01 que um combo da
    mesma sacola segura é do combo, não da linha de CROIS-01.
    """
    if not session_key or not sku:
        return Decimal("0")
    held = _load_session_holds_for_sku(
        session_key, sku, metadata_filters=_cart_hold_metadata(sku),
    )
    return sum((qty for _, qty in held), Decimal("0"))


def _reconcile_simple(
    sku: str,
    new_qty: Decimal,
    *,
    session_key: str,
    channel_ref: str | None,
    target_date: date | None,
    ttl_minutes: int,
    hold_metadata: dict[str, str] | None = None,
    metadata_filters: dict[str, str] | None = None,
) -> dict:
    """Reconcile a simple (non-bundle) SKU to `new_qty`."""
    existing = _load_session_holds_for_sku(
        session_key,
        sku,
        metadata_filters=metadata_filters,
    )
    current_total = sum((q for _, q in existing), Decimal("0"))

    if new_qty == current_total:
        return {
            "ok": True,
            "hold_ids": [],
            "released_ids": [],
            "available_qty": Decimal("0"),
            "is_paused": False,
            "error_code": None,
            "substitutes": [],
        }

    adapter = get_adapter("stock")

    # ── Grow ──
    if new_qty > current_total:
        delta = new_qty - current_total
        if target_date is None:
            # O acréscimo entra no MESMO dia que a linha já promete: a sacola
            # que está na fila da fornada de amanhã cresce dentro dela, e a de
            # pronta-entrega cresce dentro de hoje (uma linha, uma data). Sem
            # reserva viva, ancora como uma reserva nova (``reserve``). Sem
            # isto o hold nascia para HOJE e a linha da fila não crescia nunca.
            target_date = (
                adapter.hold_target_date(existing[-1][0])
                if existing
                else waitlist.reserve_target_date(sku, delta, channel_ref=channel_ref)
            )

        listing_error = _reserve_listing_gate_error(
            sku,
            delta,
            channel_ref=channel_ref,
        )
        if listing_error is not None:
            return {
                "ok": False,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": listing_error["available_qty"],
                "is_paused": listing_error["is_paused"],
                "is_planned": listing_error.get("is_planned", False),
                "error_code": listing_error["error_code"],
                "substitutes": listing_error["substitutes"],
            }

        result = adapter.create_hold(
            sku=sku,
            qty=delta,
            ttl_minutes=ttl_minutes,
            reference=session_key,
            target_date=target_date,
            channel_ref=channel_ref,
            **(hold_metadata or {}),
        )
        if result.get("success"):
            return {
                "ok": True,
                "hold_ids": [result["hold_id"]],
                "released_ids": [],
                "available_qty": delta,
                "is_paused": False,
                "error_code": None,
                "substitutes": [],
            }

        status = check(sku, delta, channel_ref=channel_ref, target_date=target_date)

        if status.get("untracked"):
            # SKU outside Stockman scope — no hold needed, treat as ok.
            return {
                "ok": True,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": status["available_qty"],
                "is_paused": False,
                "error_code": None,
                "substitutes": [],
            }

        if not status["ok"]:
            return {
                "ok": False,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": status["available_qty"],
                "is_paused": status.get("is_paused", False),
                "is_planned": status.get("is_planned", False),
                "error_code": status.get("error_code") or "insufficient_stock",
                "substitutes": substitutes.find(sku, qty=delta, channel=channel_ref),
            }

        # Fragmented stock: fall back to multi-quant split reservation.
        if result.get("error_code") == "INSUFFICIENT_AVAILABLE":
            split = _reserve_across_quants(
                sku=sku, qty=delta,
                ttl_minutes=ttl_minutes,
                session_key=session_key,
                channel_ref=channel_ref,
                target_date=target_date,
                adapter=adapter,
                hold_metadata=hold_metadata,
            )
            if split["ok"]:
                return {
                    "ok": True,
                    "hold_ids": [split["hold_id"]],
                    "released_ids": [],
                    "available_qty": status["available_qty"],
                    "is_paused": False,
                    "error_code": None,
                    "substitutes": [],
                }
            return {
                "ok": False,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": split["available_qty"],
                "is_paused": False,
                "error_code": "insufficient_stock",
                "substitutes": substitutes.find(sku, qty=delta, channel=channel_ref),
            }

        logger.info(
            "availability.reconcile: grow hold failed sku=%s delta=%s code=%s",
            sku, delta, result.get("error_code"),
        )
        return {
            "ok": False,
            "hold_ids": [],
            "released_ids": [],
            "available_qty": status["available_qty"],
            "is_paused": False,
            "error_code": result.get("error_code", "hold_failed"),
            "substitutes": substitutes.find(sku, qty=delta, channel=channel_ref),
        }

    # ── Shrink ──
    # Reduzir a sacola nunca falha, e nunca solta o que ainda cabe: soltar e
    # devolver a sobra vivem num savepoint (um erro no meio desfaz a soltura),
    # e a sobra volta pelo adapter, que devolve a mesma reserva quando pode,
    # uma reserva comum quando ela cairia em outro quant, e o que couber quando
    # o quant encolheu. Nesse último caso a linha fica com o que o cliente
    # pediu e a reserva com o que existe; a revalidação da sacola mostra a falta.
    diff = current_total - new_qty
    released_ids: list[str] = []
    released_qty = Decimal("0")
    for hid, hqty in existing:
        if released_qty >= diff:
            break
        released_ids.append(hid)
        released_qty += hqty

    overshoot = released_qty - diff
    created_ids: list[str] = []
    with transaction.atomic():
        if released_ids:
            adapter.release_holds(released_ids)
        if overshoot > 0:
            returned = adapter.return_hold_remainder(
                released_ids[-1], overshoot,
                channel_ref=channel_ref,
                ttl_minutes=ttl_minutes,
            )
            created_ids = [hold_id for hold_id, _qty in returned]
            returned_qty = sum((qty for _hold_id, qty in returned), Decimal("0"))
            if returned_qty < overshoot:
                logger.info(
                    "availability.reconcile: shrink kept less than the line sku=%s "
                    "line=%s reserved=%s (stock no longer covers it)",
                    sku, new_qty, new_qty - (overshoot - returned_qty),
                )

    return {
        "ok": True,
        "hold_ids": created_ids,
        "released_ids": released_ids,
        "available_qty": Decimal("0"),
        "is_paused": False,
        "error_code": None,
        "substitutes": [],
    }


def _release_bundle_component_holds(
    *,
    session_key: str,
    bundle_sku: str,
    components: list[dict],
) -> list[str]:
    """Release this session's holds for each bundle component tagged to a bundle.

    Surgical vs. "release every hold of this SKU for this session" — bundle
    holds carry ``cart_source_sku=<bundle_sku>`` metadata, so removing COMBO-A
    releases every component reservation for that cart line without touching a
    separate simple line that happens to use the same component SKU.

    Returns the list of released hold_ids.
    """
    adapter = get_adapter("stock")
    released: list[str] = []
    metadata_filters = _cart_hold_metadata(bundle_sku, bundle_parent_sku=bundle_sku)
    for comp in components:
        comp_sku = comp.get("sku")
        if not comp_sku:
            continue
        try:
            session_holds = adapter.find_holds_by_reference(
                session_key,
                sku=comp_sku,
                metadata_filters=metadata_filters,
            )
        except Exception as e:
            logger.warning(
                "release_bundle_components: find_holds failed sku=%s: %s",
                comp_sku, e, exc_info=True,
            )
            continue
        to_free = [hold_id for hold_id, _sku, _held_qty in session_holds]
        if to_free:
            try:
                adapter.release_holds(to_free)
                released.extend(to_free)
            except Exception as e:
                logger.warning(
                    "release_bundle_components: release_holds failed ids=%s: %s",
                    to_free, e, exc_info=True,
                )
    return released


def _reconcile_bundle_components(
    bundle_sku: str,
    bundle_qty: Decimal,
    components: list[dict],
    *,
    session_key: str,
    channel_ref: str | None,
    target_date: date | None,
    ttl_minutes: int,
) -> dict:
    """Reconcile each bundle component independently.

    If any grow-step fails, rolls back by releasing newly created holds
    (shrink-steps already applied are not undone — they freed stock that
    is now back in the pool).
    """
    created_ids: list[str] = []
    released_ids: list[str] = []
    adapter = get_adapter("stock")
    hold_metadata = _cart_hold_metadata(bundle_sku, bundle_parent_sku=bundle_sku)

    for comp in components:
        comp_sku = comp["sku"]
        comp_qty = Decimal(str(comp["qty"]))

        result = _reconcile_simple(
            comp_sku, comp_qty,
            session_key=session_key,
            channel_ref=channel_ref,
            target_date=target_date,
            ttl_minutes=ttl_minutes,
            hold_metadata=hold_metadata,
            metadata_filters=hold_metadata,
        )
        if not result["ok"]:
            # Rollback: release any new holds we've created for previous components.
            if created_ids:
                adapter.release_holds(created_ids)
            return {
                "ok": False,
                "hold_ids": [],
                "released_ids": released_ids,
                "available_qty": result["available_qty"],
                "is_paused": result.get("is_paused", False),
                "error_code": result.get("error_code", "hold_failed"),
                "substitutes": substitutes.find(
                    bundle_sku, qty=bundle_qty, channel=channel_ref,
                ),
            }
        created_ids.extend(result["hold_ids"])
        released_ids.extend(result["released_ids"])

    return {
        "ok": True,
        "hold_ids": created_ids,
        "released_ids": released_ids,
        "available_qty": Decimal("0"),
        "is_paused": False,
        "error_code": None,
        "substitutes": [],
    }


def _reserve_bundle_components(
    bundle_sku: str,
    bundle_qty: Decimal,
    components: list[dict],
    *,
    session_key: str,
    ttl_minutes: int,
    channel_ref: str | None,
    target_date: date | None,
    available_qty: Decimal,
    adapter,
) -> dict:
    """Create one hold per bundle component.

    On any failure, releases all previously created holds (atomic rollback)
    and returns ok=False.
    """
    created_hold_ids: list[str] = []
    hold_metadata = _cart_hold_metadata(bundle_sku, bundle_parent_sku=bundle_sku)

    for comp in components:
        comp_sku = comp["sku"]
        comp_qty = Decimal(str(comp["qty"]))

        result = adapter.create_hold(
            sku=comp_sku,
            qty=comp_qty,
            ttl_minutes=ttl_minutes,
            reference=session_key,
            target_date=target_date,
            channel_ref=channel_ref,
            **hold_metadata,
        )

        if not result.get("success"):
            logger.info(
                "availability.reserve: bundle hold failed sku=%s comp=%s qty=%s code=%s",
                bundle_sku, comp_sku, comp_qty, result.get("error_code"),
            )
            # Rollback: release holds already created for previous components.
            if created_hold_ids:
                adapter.release_holds(created_hold_ids)
            return {
                "ok": False,
                "hold_id": None,
                "hold_ids": [],
                "available_qty": available_qty,
                "is_paused": False,
                "error_code": result.get("error_code", "hold_failed"),
                "is_bundle": True,
                "substitutes": substitutes.find(bundle_sku, qty=bundle_qty, channel=channel_ref),
            }

        created_hold_ids.append(result["hold_id"])

    return {
        "ok": True,
        "hold_id": None,          # use hold_ids for bundles
        "hold_ids": created_hold_ids,
        "available_qty": available_qty,
        "is_paused": False,
        "error_code": None,
        "is_bundle": True,
        "substitutes": [],
    }
