"""
Shelflife validation — isolated, testable, reusable.

Determines whether a Quant is still valid for a given target date,
based on the product's shelf_life_days (days the product remains usable).

Examples:
    - Croissant (shelf_life_days=0): only valid on production day
    - Bolo (shelf_life_days=3): valid for 3 days after production
    - Wine (shelf_life_days=None): no expiration

Margem de validade (``margin_days``): o chamador pode exigir que o saldo ainda
tenha N dias de validade DEPOIS da data-alvo. É a mesma margem que o escopo já
aplica ao lote datado (``Batch.expiry_date``, ``expiry_margin_days``); aqui ela
alcança a validade IMPLÍCITA do saldo sem lote (dia de produção +
``shelf_life_days``), que é o caso de toda fornada planejada. Sem isso, a
fornada de quinta de um pão de um dia contava inteira como lastro de uma
promessa para sexta. A fornada planejada PARA a própria data-alvo sempre conta:
na data dela o produto é o do dia, com qualquer validade (inclusive zero).

O dia de produção de um saldo físico é o do LOTE dele (``Batch.production_date``),
quando o lote o declara. O ``created_at`` do saldo é o dia em que ele entrou no
estoque: o lote de sexta fechado na quinta à noite é pão de sexta, e cobrar a
margem sobre o ``created_at`` o tratava como pão de quinta. Por isso a margem
de um saldo físico de lote é julgada na data de produção do lote, pela mesma
régua da fornada planejada; a janela histórica sobre o ``created_at`` (sem
margem) continua valendo para ele. Lote nomeado sem ``Batch``, ou com ``Batch``
sem data de produção, não declara nada: segue a margem sobre o ``created_at``.
"""

from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone


def _production_floors(shelflife: int, target_date: date, margin_days: int) -> tuple[date, date, date]:
    """Dia de produção mais antigo que ainda vale.

    ``(saldo físico, fornada planejada ou lote datado, janela sem margem)``. O
    saldo vale enquanto ``produção + shelf_life_days >= alvo + margem``. A
    fornada planejada para a própria data-alvo nunca cai pela margem, e o lote
    que declara a data de produção é julgado pela mesma régua dela.
    """
    unmargined = target_date - timedelta(days=shelflife)
    floor = unmargined + timedelta(days=max(0, margin_days))
    return floor, min(floor, target_date), unmargined


def lot_production_floor(shelflife: int, target_date: date, margin_days: int) -> date:
    """Data de produção mais antiga de um LOTE que ainda vale para a data-alvo.

    É o que a leitura em lote precisa para carregar só os lotes que podem
    fazer diferença (``lot_production_date`` em :func:`is_valid_for_date`).
    """
    return _production_floors(shelflife, target_date, margin_days)[1]


def is_valid_for_date(
    quant, product, target_date: date, *, margin_days: int = 0, lot_production_date: date | None = None,
) -> bool:
    """
    Check if a specific quant is still valid for the target date.

    Args:
        quant: Quant instance (needs .target_date, .created_at)
        product: Product instance (needs .shelf_life_days attribute or None)
        target_date: The date we want to use/sell the product
        margin_days: Days of validity the quant must still have AFTER
            ``target_date`` (0 = valid on the target date is enough). Planned
            production for the target date itself always qualifies.
        lot_production_date: ``Batch.production_date`` of this physical quant's
            lot, when the lot declares one. The margin is then judged on it,
            by the planned-batch rule, and ``created_at`` keeps only the
            unmargined window. ``None`` = no declared date: the margin falls
            on ``created_at``.

    Returns:
        True if the quant is still valid for the target date
    """
    shelflife = getattr(product, 'shelf_life_days', None)

    if shelflife is None:
        # No expiration — physical stock or planned up to target
        if quant.target_date is None:
            return True
        return quant.target_date <= target_date

    min_production, min_planned, min_unmargined = _production_floors(shelflife, target_date, margin_days)

    if quant.target_date is None:
        # Physical stock: check creation date
        # ``created_at`` is stored in UTC while the production day is local.
        # Around 21h in Brazil, ``.date()`` already points at tomorrow and can
        # make same-day bread survive one extra day in the batch read path.
        created = timezone.localdate(quant.created_at)
        if created >= min_production:
            return True
        return lot_production_date is not None and lot_production_date >= min_planned and created >= min_unmargined

    # Planned stock: must be within shelflife window
    return min_planned <= quant.target_date <= target_date


def filter_valid_quants(quants, product, target_date: date, *, margin_days: int = 0, lots=None):
    """
    Filter a Quant queryset to only include quants valid for the target date.

    This is the queryset-level version of is_valid_for_date — used for
    bulk queries (available(), hold(), etc.).

    Args:
        quants: Quant QuerySet
        product: Product instance (needs .shelf_life_days attribute or None)
        target_date: The date we want to check validity for
        margin_days: Same as :func:`is_valid_for_date`.
        lots: QuerySet of this product's lots (``ref``, ``production_date``).
            Physical quants of a lot that declares its production date are
            judged on it (``lot_production_date`` in :func:`is_valid_for_date`).
            ``None`` = no lot is consulted, the margin falls on ``created_at``.

    Returns:
        Filtered QuerySet
    """
    shelflife = getattr(product, 'shelf_life_days', None)

    if shelflife is not None:
        min_production, min_planned, min_unmargined = _production_floors(shelflife, target_date, margin_days)
        valid = (
            Q(target_date__isnull=True, created_at__date__gte=min_production)
            | Q(target_date__gte=min_planned, target_date__lte=target_date)
        )
        if lots is not None and min_unmargined < min_production:
            valid |= Q(
                target_date__isnull=True,
                created_at__date__gte=min_unmargined,
                batch__in=lots.filter(production_date__gte=min_planned).values("ref"),
            )
        return quants.filter(valid)

    return quants.filter(
        Q(target_date__isnull=True) | Q(target_date__lte=target_date)
    )


# ── Lot consistency (Batch.expiry_date × Product.shelf_life_days) ────────────


def shelf_life_days_for(sku: str) -> int | None:
    """Resolve a SKU's ``shelf_life_days`` via the injected SkuValidator.

    Uses the same dependency-injection seam as availability (no Offerman import —
    Core packages stay independent). ``None`` = non-perishable or unknown.
    """
    from shopman.stockman.adapters.sku_validation import get_sku_validator

    info = get_sku_validator().get_sku_info(sku)
    return getattr(info, "shelflife_days", None) if info is not None else None


def batch_window_check(sku: str, production_date, expiry_date) -> tuple[str | None, str | None]:
    """Check a lot's dates against the product's shelf life.

    Returns ``(error, warning)``:

    - ``error`` — an impossible date (expiry before production). Always blocks.
    - ``warning`` — the lot claims a longer life than ``shelf_life_days`` allows.
      Surfaced as a non-blocking warning by default; escalated to an error only
      when ``STOCKMAN['STRICT_SHELF_LIFE_WINDOW']`` is on.

    No-op when either date is missing or the product is non-perishable
    (``shelf_life_days is None``).
    """
    if not production_date or not expiry_date:
        return None, None
    if expiry_date < production_date:
        return "Validade não pode ser anterior à data de produção.", None
    shelf = shelf_life_days_for(sku)
    if shelf is None:
        return None, None
    max_expiry = production_date + timedelta(days=shelf)
    if expiry_date > max_expiry:
        return None, (
            f"Validade {expiry_date:%d/%m/%Y} excede a janela do produto "
            f"(produção + {shelf}d = {max_expiry:%d/%m/%Y})."
        )
    return None, None
