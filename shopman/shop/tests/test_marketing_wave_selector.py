"""MKT-018 — approved wave keys select one stable sealed cohort partition."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shopman.shop.handlers.campaign import AnnouncementNotifyHandler
from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    DeliveryTarget,
    MarketingOutbox,
)
from shopman.shop.services import campaign as campaign_service
from shopman.shop.services.audience import AudienceResult, Recipient, Wave
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.shop.services.marketing_delivery_worker import fanout_in_chunks
from shopman.shop.services.marketing_outbox import _directive_payload
from shopman.shop.services.marketing_wave_selector import select_partition
from shopman.shop.tests.test_marketing_delivery_ledger import _graph

pytestmark = pytest.mark.django_db


def _lanes(*, suffix: str, keys: tuple[str, ...], member_traits):
    outbox, members = _graph(
        suffix=suffix,
        target_keys=tuple(f"member-{index}" for index in range(len(member_traits))),
    )
    outbox.wave_key = keys[0]
    outbox.save(update_fields=["wave_key"])
    lanes = [outbox]
    for index, key in enumerate(keys[1:], start=1):
        lanes.append(
            MarketingOutbox.objects.create(
                command=outbox.command,
                announcement=outbox.announcement,
                snapshot=outbox.snapshot,
                artifact=outbox.artifact,
                platform="whatsapp",
                wave_key=key,
                state=MarketingOutbox.State.DISPATCHED,
                available_at=outbox.available_at,
                dispatch_ref=f"directive:wave:{suffix}:{index}",
                dispatched_at=outbox.dispatched_at,
            )
        )
    for member, (is_vip, preferred_hour) in zip(
        members,
        member_traits,
        strict=True,
    ):
        member.is_vip = is_vip
        member.preferred_hour = preferred_hour
    type(members[0]).objects.bulk_update(
        members,
        ["is_vip", "preferred_hour"],
    )
    return tuple(lanes), members


def _materialized_members(lanes):
    result = {}
    for lane in lanes:
        fanout_in_chunks(lane.ref)
        result[lane.wave_key] = set(
            DeliveryTarget.objects.filter(outbox=lane).values_list(
                "member_id",
                flat=True,
            )
        )
    return result


def test_all_at_nine_selects_only_approved_members_for_that_hour():
    lanes, members = _lanes(
        suffix="all-at-nine",
        keys=("all", "all@9"),
        member_traits=((False, 9), (True, 9), (False, 10), (False, None)),
    )

    selected = _materialized_members(lanes)

    assert selected["all@9"] == {members[0].pk, members[1].pk}
    assert selected["all"] == {members[2].pk, members[3].pk}
    assert selected["all"].isdisjoint(selected["all@9"])
    assert selected["all"] | selected["all@9"] == {member.pk for member in members}


def test_vip_at_nine_and_general_at_nine_stay_in_their_own_groups():
    lanes, members = _lanes(
        suffix="vip-at-nine",
        keys=("vip", "vip@9", "general", "general@9"),
        member_traits=((True, 9), (True, None), (False, 9), (False, None)),
    )

    selected = _materialized_members(lanes)

    assert selected == {
        "vip": {members[1].pk},
        "vip@9": {members[0].pk},
        "general": {members[3].pk},
        "general@9": {members[2].pk},
    }
    assert DeliveryTarget.objects.count() == len(members)
    for lane in lanes:
        payload = _directive_payload(lane)
        assert payload["wave"] == lane.wave_key
        assert payload["wave_keys"] == [
            "vip",
            "vip@9",
            "general",
            "general@9",
        ]
        assert payload["waves_expected"] == 4


def test_hour_without_approved_lane_falls_into_base_instead_of_disappearing():
    members = (
        SimpleNamespace(is_vip=False, preferred_hour=9),
        SimpleNamespace(is_vip=False, preferred_hour=11),
    )

    base = select_partition(
        members,
        wave_key="all",
        available_wave_keys=("all", "all@9"),
    )

    assert base == (members[1],)


def test_invalid_or_mixed_wave_graph_fails_before_materializing_targets():
    lanes, _members = _lanes(
        suffix="invalid-wave",
        keys=("all", "vip@9"),
        member_traits=((True, 9),),
    )

    with pytest.raises(MarketingContractError) as caught:
        fanout_in_chunks(lanes[0].ref)

    assert caught.value.code == "delivery_wave_graph_invalid"
    assert DeliveryTarget.objects.count() == 0


def test_legacy_handler_uses_frozen_wave_keys_even_when_hour_has_arrived():
    template = AnnouncementTemplate.objects.create(name="T", body="Novidade")
    rule = Campaign.objects.create(
        name="Hora preferida",
        trigger="manual",
        template=template,
        platforms=["whatsapp"],
        audience_rules={"favorites": True, "preferred_hour_window_hours": 4},
    )
    announcement = Announcement.objects.create(
        rule=rule,
        template=template,
        status=AnnouncementStatus.PUBLISHING,
        content={"body": "Novidade"},
        platforms=["whatsapp"],
    )
    preferred = Recipient(phone="+5543999990001", preferred_hour=9)
    base = Recipient(phone="+5543999990002")
    resolution = AudienceResult(general=(preferred, base))
    message = SimpleNamespace(
        pk=1,
        payload={
            "announcement_id": announcement.pk,
            "wave": "all@9",
            "wave_keys": ["all", "all@9"],
            "waves_expected": 2,
        },
    )

    with (
        patch("shopman.shop.services.audience.resolve", return_value=resolution),
        patch(
            "shopman.shop.handlers.campaign._send_to",
            return_value=(1, 0),
        ) as send,
    ):
        AnnouncementNotifyHandler().handle(message=message, ctx={})

    assert send.call_args.args[0] == (preferred,)


def test_new_directive_with_invalid_wave_plan_fails_instead_of_sending_zero():
    template = AnnouncementTemplate.objects.create(name="T-invalid", body="Novidade")
    rule = Campaign.objects.create(
        name="Plano inválido",
        trigger="manual",
        template=template,
        platforms=["whatsapp"],
        audience_rules={"favorites": True},
    )
    announcement = Announcement.objects.create(
        rule=rule,
        template=template,
        status=AnnouncementStatus.PUBLISHING,
        content={"body": "Novidade"},
        platforms=["whatsapp"],
    )
    resolution = AudienceResult(
        general=(Recipient(phone="+5543999990003", preferred_hour=9),)
    )
    message = SimpleNamespace(
        pk=2,
        payload={
            "announcement_id": announcement.pk,
            "wave": "all@9",
            "wave_keys": ["all", "vip@9"],
        },
    )

    with (
        patch("shopman.shop.services.audience.resolve", return_value=resolution),
        patch("shopman.shop.handlers.campaign._send_to") as send,
        pytest.raises(MarketingContractError) as caught,
    ):
        AnnouncementNotifyHandler().handle(message=message, ctx={})

    assert caught.value.code == "delivery_wave_not_approved"
    send.assert_not_called()


def test_legacy_queue_carries_the_full_partition_plan_on_every_directive():
    template = AnnouncementTemplate.objects.create(name="T2", body="Novidade")
    rule = Campaign.objects.create(
        name="Plano horário",
        trigger="manual",
        template=template,
        platforms=["whatsapp"],
        audience_rules={"favorites": True},
    )
    announcement = Announcement.objects.create(
        rule=rule,
        template=template,
        content={"body": "Novidade"},
        platforms=["whatsapp"],
    )
    resolution = SimpleNamespace(
        degraded_sources=(),
        waves=lambda: (
            Wave(key="all"),
            Wave(key="all@9", delay_minutes=30),
        ),
    )

    with (
        patch.object(campaign_service.audience_service, "resolve", return_value=resolution),
        patch.object(
            campaign_service,
            "create_deduped",
            return_value=SimpleNamespace(pk=1),
        ) as create,
    ):
        created = campaign_service._queue_notify(announcement)

    assert created == 2
    assert [call.kwargs["payload"]["wave_keys"] for call in create.call_args_list] == [
        ["all", "all@9"],
        ["all", "all@9"],
    ]
