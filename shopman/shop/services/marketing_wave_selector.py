"""Canonical, time-stable partitioning for approved Marketing waves."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from shopman.shop.models import AudienceSnapshotMember, MarketingOutbox
from shopman.shop.services.marketing_contracts import MarketingContractError

_WAVE_RE = re.compile(r"^(all|vip|general)(?:@([0-9]|1[0-9]|2[0-3]))?$")


def select_partition[Member](
    members: Iterable[Member],
    *,
    wave_key: str,
    available_wave_keys: Sequence[str],
) -> tuple[Member, ...]:
    """Assign each member to exactly one of an already-approved set of waves.

    Wave keys are facts frozen while planning.  Selection therefore never
    recalculates whether hour H is still in the future; when the H worker runs,
    ``all@H`` must continue to mean "members assigned to H".
    """

    desired = str(wave_key or "")
    keys = tuple(dict.fromkeys(str(key or "") for key in available_wave_keys))
    parsed = {key: _parse_wave_key(key) for key in keys}
    if desired not in parsed:
        raise MarketingContractError(
            code="delivery_wave_not_approved",
            detail="A lane solicitada não pertence ao plano aprovado.",
        )
    bases = {base for base, _hour in parsed.values()}
    if "all" in bases:
        if bases != {"all"}:
            raise MarketingContractError(
                code="delivery_wave_graph_invalid",
                detail="O plano mistura partição geral e VIP.",
            )
        split_vip = False
    else:
        if bases != {"vip", "general"}:
            raise MarketingContractError(
                code="delivery_wave_graph_invalid",
                detail="O plano VIP precisa das lanes VIP e geral.",
            )
        split_vip = True
    if any(base not in parsed for base in bases):
        raise MarketingContractError(
            code="delivery_wave_graph_invalid",
            detail="Toda partição horária precisa de uma lane-base.",
        )

    selected: list[Member] = []
    approved = frozenset(parsed)
    for member in members:
        base = ("vip" if bool(getattr(member, "is_vip", False)) else "general") if split_vip else "all"
        preferred_hour = _preferred_hour(getattr(member, "preferred_hour", None))
        hourly = f"{base}@{preferred_hour}" if preferred_hour is not None else ""
        assigned = hourly if hourly in approved else base
        if assigned == desired:
            selected.append(member)
    return tuple(selected)


def select_snapshot_member_ids(outbox: MarketingOutbox) -> tuple[int, ...]:
    """Select one protected cohort partition without resolving contact data."""

    if outbox.platform != "whatsapp":
        raise MarketingContractError(
            code="delivery_wave_platform_invalid",
            detail="Somente uma lane WhatsApp possui membros de audiência.",
        )
    lanes = list(
        MarketingOutbox.objects.filter(
            command=outbox.command,
            platform="whatsapp",
        ).values("wave_key", "snapshot_id", "announcement_id")
    )
    if any(
        lane["snapshot_id"] != outbox.snapshot_id or lane["announcement_id"] != outbox.announcement_id for lane in lanes
    ):
        raise MarketingContractError(
            code="delivery_wave_graph_mismatch",
            detail="As lanes não compartilham o mesmo cohort aprovado.",
        )
    members: tuple[AudienceSnapshotMember, ...] = tuple(
        AudienceSnapshotMember.objects.filter(snapshot=outbox.snapshot)
        .only("pk", "is_vip", "preferred_hour")
        .order_by("pk")
    )
    selected = select_partition(
        members,
        wave_key=outbox.wave_key or "all",
        available_wave_keys=tuple(lane["wave_key"] or "all" for lane in lanes),
    )
    return tuple(member.pk for member in selected)


def _parse_wave_key(value: str) -> tuple[str, int | None]:
    match = _WAVE_RE.fullmatch(value)
    if match is None:
        raise MarketingContractError(
            code="delivery_wave_key_invalid",
            detail="A chave da lane aprovada é inválida.",
        )
    hour = int(match.group(2)) if match.group(2) is not None else None
    return match.group(1), hour


def _preferred_hour(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        hour = int(value)
    except (TypeError, ValueError):
        return None
    return hour if 0 <= hour <= 23 else None
