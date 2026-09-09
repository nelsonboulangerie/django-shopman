"""
Canonical quant scope — single source of truth for "which quants are eligible
for this SKU × channel × date".

Both availability reads (``availability.check``) and physical holds
(``availability.reserve`` → ``StockHolds.hold``) consume
:func:`quants_eligible_for` so they can never disagree about which quants
count toward promise decisions and which do not.

Filters applied, in order:

1. ``sku`` match + ``_quantity > 0``
2. ``target_date`` gate combined with shelflife window
   (``product.shelf_life_days``) via :func:`shelflife.filter_valid_quants`
3. Position scope: ``allowed_positions`` (allowlist) and/or
   ``excluded_positions`` (denylist). When a ``channel_ref`` is provided and
   neither list is given explicitly, the function resolves them from
   :func:`availability_scope_for_channel`.
4. Batch expiry: quants whose batch expires before ``target`` plus the
   caller's ``expiry_margin_days`` are excluded (0 = only already-expired).
5. Batch quality: ``allowed_quality_grade_refs`` is an opaque allowlist
   resolved by channel policy. Motivo remains orthogonal and is never used
   to infer a grade. ``include_nonconforming`` remains a compatibility gate
   for callers not yet carrying the explicit policy.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from django.db.models import QuerySet
from django.utils import timezone
from shopman.stockman.models.quant import Quant
from shopman.stockman.services.queries import _resolve_stock_profile
from shopman.stockman.shelflife import filter_valid_quants


def quants_eligible_for(
    sku: str,
    *,
    channel_ref: str | None = None,
    target_date: date | None = None,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
    expiry_margin_days: int = 0,
    include_nonconforming: bool = True,
    allowed_quality_grade_refs: list[str] | tuple[str, ...] | None = None,
) -> QuerySet[Quant]:
    """Return the canonical queryset of quants eligible for this SKU/scope.

    Args:
        sku: Product SKU.
        channel_ref: Channel whose ``ChannelConfig.stock`` determines the
            position scope when ``allowed_positions``/``excluded_positions``
            are not passed explicitly.
        target_date: Date the caller wants to sell/hold for. Defaults to
            today. Planned quants beyond this date are excluded; shelflife
            validity is evaluated against it.
        allowed_positions: If set, only quants at these position refs are
            considered. Takes precedence over the channel's configuration.
        excluded_positions: Position refs to exclude regardless of the
            allowlist. Applied after ``allowed_positions``.
        expiry_margin_days: Also exclude lots expiring within this many days
            AFTER ``target_date`` (near-expiry). 0 keeps the historical gate
            (only lots already expired at ``target_date`` are out).
        include_nonconforming: Compatibility gate. When ``False`` and no
            explicit grade allowlist is supplied, lots with a frozen markdown
            percentage are excluded. A reason alone is informational and
            never becomes commercial policy.
        allowed_quality_grade_refs: Opaque grade refs accepted by the caller.
            ``None`` means no grade restriction. Known batches with a blank or
            different grade are excluded; batchless planned supply is kept.

    Returns:
        QuerySet[Quant] filtered and ``select_related("position")``. Callers
        apply their own bucketing (``ready``/``planned``/...) or FIFO on top.
    """
    from shopman.stockman.models import Batch

    target = target_date or timezone.localdate()

    profile = _resolve_stock_profile(sku)
    product_ns = SimpleNamespace(sku=sku, shelf_life_days=profile.get("shelflife"))

    if channel_ref is not None and allowed_positions is None and excluded_positions is None:
        from shopman.stockman.services.availability import (
            availability_scope_for_channel,
        )

        scope = availability_scope_for_channel(channel_ref)
        allowed_positions = scope.get("allowed_positions")
        excluded_positions = scope.get("excluded_positions")
        expiry_margin_days = int(scope.get("expiry_margin_days") or 0)
        include_nonconforming = bool(scope.get("sells_nonconforming", True))
        allowed_quality_grade_refs = scope.get("allowed_quality_grade_refs")

    qs = Quant.objects.filter(sku=sku, _quantity__gt=0)
    # Validity precedence: shelf_life_days (relative window) and Batch.expiry_date
    # (absolute lot date) are applied as an AND — a quant must pass both. The most
    # restrictive signal wins. Locked by TestShelflifeBatchPrecedence.
    qs = filter_valid_quants(qs, product_ns, target)

    if allowed_positions is not None:
        qs = qs.filter(position__ref__in=allowed_positions)
    if excluded_positions:
        qs = qs.exclude(position__ref__in=excluded_positions)

    expiry_cutoff = target + timedelta(days=max(0, expiry_margin_days))
    expired_refs = list(
        Batch.objects.filter(sku=sku, expiry_date__lt=expiry_cutoff).values_list(
            "ref",
            flat=True,
        )
    )
    if expired_refs:
        qs = qs.exclude(batch__in=expired_refs)

    if allowed_quality_grade_refs is not None:
        disallowed_refs = list(
            Batch.objects.for_sku(sku)
            .exclude(quality_grade_ref__in=tuple(allowed_quality_grade_refs))
            .values_list("ref", flat=True)
        )
        if disallowed_refs:
            qs = qs.exclude(batch__in=disallowed_refs)
    elif not include_nonconforming:
        nonconforming_refs = list(Batch.objects.for_sku(sku).nonconforming().values_list("ref", flat=True))
        if nonconforming_refs:
            qs = qs.exclude(batch__in=nonconforming_refs)

    return qs.select_related("position")
