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
"""

from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone


def _production_floors(shelflife: int, target_date: date, margin_days: int) -> tuple[date, date]:
    """Dia de produção mais antigo que ainda vale: ``(saldo físico, fornada planejada)``.

    O saldo vale enquanto ``produção + shelf_life_days >= alvo + margem``. A
    fornada planejada para a própria data-alvo nunca cai pela margem.
    """
    floor = target_date - timedelta(days=shelflife) + timedelta(days=max(0, margin_days))
    return floor, min(floor, target_date)


def is_valid_for_date(quant, product, target_date: date, *, margin_days: int = 0) -> bool:
    """
    Check if a specific quant is still valid for the target date.

    Args:
        quant: Quant instance (needs .target_date, .created_at)
        product: Product instance (needs .shelf_life_days attribute or None)
        target_date: The date we want to use/sell the product
        margin_days: Days of validity the quant must still have AFTER
            ``target_date`` (0 = valid on the target date is enough). Planned
            production for the target date itself always qualifies.

    Returns:
        True if the quant is still valid for the target date
    """
    shelflife = getattr(product, 'shelf_life_days', None)

    if shelflife is None:
        # No expiration — physical stock or planned up to target
        if quant.target_date is None:
            return True
        return quant.target_date <= target_date

    min_production, min_planned = _production_floors(shelflife, target_date, margin_days)

    if quant.target_date is None:
        # Physical stock: check creation date
        # ``created_at`` is stored in UTC while the production day is local.
        # Around 21h in Brazil, ``.date()`` already points at tomorrow and can
        # make same-day bread survive one extra day in the batch read path.
        return timezone.localdate(quant.created_at) >= min_production

    # Planned stock: must be within shelflife window
    return min_planned <= quant.target_date <= target_date


def filter_valid_quants(quants, product, target_date: date, *, margin_days: int = 0):
    """
    Filter a Quant queryset to only include quants valid for the target date.

    This is the queryset-level version of is_valid_for_date — used for
    bulk queries (available(), hold(), etc.).

    Args:
        quants: Quant QuerySet
        product: Product instance (needs .shelf_life_days attribute or None)
        target_date: The date we want to check validity for
        margin_days: Same as :func:`is_valid_for_date`.

    Returns:
        Filtered QuerySet
    """
    shelflife = getattr(product, 'shelf_life_days', None)

    if shelflife is not None:
        min_production, min_planned = _production_floors(shelflife, target_date, margin_days)
        return quants.filter(
            Q(target_date__isnull=True, created_at__date__gte=min_production)
            | Q(target_date__gte=min_planned, target_date__lte=target_date)
        )

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
