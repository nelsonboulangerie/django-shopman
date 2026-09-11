"""MKT-027 — canonical facts, validity and pre-provider revalidation."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.marketing_v2 import (
    build_announcement as build_marketing_announcement,
)
from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    DeliveryTarget,
    MarketingOutbox,
    Promotion,
)
from shopman.shop.services import campaign, marketing_facts
from shopman.shop.services.marketing_approval import approve_command
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.shop.services.marketing_delivery_attempts import queue_target
from shopman.shop.services.marketing_delivery_worker import (
    claim_due_targets,
    fanout_in_chunks,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def product():
    return Product.objects.create(
        sku="croissant-facts",
        name="Croissant Tradicional",
        base_price_q=850,
        is_published=True,
        is_sellable=True,
    )


@pytest.fixture
def promotion():
    now = timezone.now()
    return Promotion.objects.create(
        ref="fornada-10",
        name="Fornada 10%",
        type=Promotion.PERCENT,
        value=10,
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=2),
        skus=["croissant-facts"],
    )


def test_facts_replace_stale_event_values_with_canonical_owner_reads(product, monkeypatch):
    from shopman.shop.projections import catalog_context

    monkeypatch.setattr(
        catalog_context,
        "availability_for_sku",
        lambda *args, **kwargs: {
            "availability_policy": "stock_only",
            "total_promisable": 3,
        },
    )
    now = timezone.now()
    facts = marketing_facts.resolve_facts(
        sku=product.sku,
        referenced=("available_qty", "link", "price", "product_name"),
        seed_variables={"available_qty": "99", "price": "R$ 1,00"},
        now=now,
    )
    later = marketing_facts.resolve_facts(
        sku=product.sku,
        referenced=("available_qty", "link", "price", "product_name"),
        seed_variables={"available_qty": "99", "price": "R$ 1,00"},
        now=now + timedelta(minutes=1),
    )

    assert facts.variable_values()["price"] == "R$ 8,50"
    assert facts.variable_values()["available_qty"] == "3"
    assert facts.variable_values()["link"].endswith("/produto/croissant-facts")
    assert facts.source_hash == later.source_hash
    assert facts.as_of != later.as_of


def test_operator_override_resolves_new_fact_placeholder_canonically(product):
    template = AnnouncementTemplate.objects.create(
        name="Texto sem preço",
        body="{{product_name}} disponível",
    )

    content = campaign.resolve_content(
        template,
        {"sku": product.sku},
        override_body="Oferta revisada: {{price}}",
    )

    assert content["body"] == "Oferta revisada: R$ 8,50"
    assert content["facts"]["referenced_variables"] == ["price"]


def test_schedule_at_or_after_promotion_expiry_is_rejected(product, promotion):
    template = AnnouncementTemplate.objects.create(
        name="Oferta factual",
        body="{{product_name}} por {{price}}: {{link}}",
    )
    rule = Campaign.objects.create(
        name="Oferta factual",
        trigger="production_finished",
        template=template,
        platforms=["instagram"],
        promotion_ref=promotion.ref,
    )
    content = campaign.resolve_content(
        template,
        {"sku": product.sku},
        promotion_ref=promotion.ref,
    )
    assert "R$ 7,65" in content["body"]
    assert content["variables"]["link"].endswith("/oferta/fornada-10")
    announcement = Announcement.objects.create(
        rule=rule,
        template=template,
        status=AnnouncementStatus.PENDING_REVIEW,
        content=content,
        platform_content={},
        platforms=["instagram"],
        trigger_context={"sku": product.sku},
    )

    with pytest.raises(MarketingContractError) as caught:
        approve_command(
            announcement.pk,
            actor=get_user_model().objects.create_user(username="facts-schedule"),
            idempotency_key="facts-schedule-expiry-0001",
            base_version=1,
            publish_mode="scheduled",
            publish_at=promotion.valid_until,
            content=content,
            platform_content={},
            platforms=["instagram"],
        )

    assert caught.value.code == "marketing_schedule_outlives_promotion"
    assert "publish_at" in caught.value.field_errors
    assert not MarketingOutbox.objects.filter(announcement=announcement).exists()


def test_approval_rejects_changed_price_and_preserves_the_draft(product):
    template = AnnouncementTemplate.objects.create(
        name="Preço factual",
        body="{{product_name}} por {{price}}",
    )
    content = campaign.resolve_content(template, {"sku": product.sku})
    announcement = Announcement.objects.create(
        template=template,
        status=AnnouncementStatus.PENDING_REVIEW,
        content=content,
        platforms=["instagram"],
        trigger_context={"sku": product.sku},
    )
    Product.objects.filter(pk=product.pk).update(base_price_q=900)

    with pytest.raises(MarketingContractError) as caught:
        approve_command(
            announcement.pk,
            actor=get_user_model().objects.create_user(username="facts-review"),
            idempotency_key="facts-review-price-0001",
            base_version=1,
            publish_mode="now",
            content=content,
            platform_content={},
            platforms=["instagram"],
        )

    assert caught.value.code == "marketing_facts_changed"
    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW
    assert announcement.version == 1


def test_approval_revalidates_expired_facts_when_canonical_values_are_unchanged(product):
    captured_at = timezone.now() - timedelta(minutes=6)
    template = AnnouncementTemplate.objects.create(
        name="Preço factual vencido",
        body="{{product_name}} por {{price}}",
    )
    facts = marketing_facts.resolve_facts(
        sku=product.sku,
        referenced=("price", "product_name"),
        seed_variables={},
        now=captured_at,
    )
    content = {"facts": facts.as_payload()}
    announcement = Announcement.objects.create(
        template=template,
        status=AnnouncementStatus.PENDING_REVIEW,
        content=content,
        platforms=["instagram"],
        trigger_context={"sku": product.sku},
    )
    stored = marketing_facts.from_payload(content["facts"])
    checked_at = timezone.now()

    revalidated = marketing_facts.refresh_for_approval(
        announcement,
        content,
        scheduled_for=None,
        now=checked_at,
    )

    assert stored.fresh_until < checked_at
    assert revalidated == stored
    assert revalidated.source_hash == stored.source_hash


def test_approval_still_rejects_expired_facts_when_canonical_values_changed(product):
    captured_at = timezone.now() - timedelta(minutes=6)
    facts = marketing_facts.resolve_facts(
        sku=product.sku,
        referenced=("price",),
        seed_variables={},
        now=captured_at,
    )
    content = {"facts": facts.as_payload()}
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content=content,
        platforms=["instagram"],
        trigger_context={"sku": product.sku},
    )
    Product.objects.filter(pk=product.pk).update(base_price_q=900)

    with pytest.raises(MarketingContractError) as caught:
        marketing_facts.refresh_for_approval(
            announcement,
            content,
            scheduled_for=None,
            now=timezone.now(),
        )

    assert caught.value.code == "marketing_facts_changed"


def test_pre_send_price_drift_expires_target_without_provider_boundary(product):
    template = AnnouncementTemplate.objects.create(
        name="Preço antes do envio",
        body="{{product_name}} por {{price}}",
    )
    content = campaign.resolve_content(template, {"sku": product.sku})
    announcement = Announcement.objects.create(
        template=template,
        status=AnnouncementStatus.PENDING_REVIEW,
        content=content,
        platforms=["instagram"],
        trigger_context={"sku": product.sku},
    )
    result = approve_command(
        announcement.pk,
        actor=get_user_model().objects.create_user(username="facts-dispatch"),
        idempotency_key="facts-dispatch-price-0001",
        base_version=1,
        publish_mode="now",
        content=content,
        platform_content={},
        platforms=["instagram"],
    )
    projected = projection_data(
        build_marketing_announcement(
            Announcement.objects.select_related("rule", "template").get(pk=announcement.pk)
        )
    )["data"]["announcement"]["facts"]
    assert projected["content_facts_hash"] == content["facts"]["source_hash"]
    assert datetime.fromisoformat(projected["content_as_of"]) == datetime.fromisoformat(
        content["facts"]["as_of"]
    )
    assert projected["link_ref"] == f"product:{product.sku}"
    now = timezone.now()
    outbox = result.outbox[0]
    MarketingOutbox.objects.filter(pk=outbox.pk).update(
        state=MarketingOutbox.State.DISPATCHED,
        dispatch_ref="directive:facts-drift",
        dispatched_at=now,
    )
    fanout_in_chunks(outbox.ref, now=now)
    target = DeliveryTarget.objects.get(outbox=outbox)
    queue_target(target.ref, now=now)
    Product.objects.filter(pk=product.pk).update(base_price_q=950)

    report = claim_due_targets(worker_id="facts-worker", now=now)

    assert report.targets == ()
    assert report.expired == 1
    target.refresh_from_db()
    assert target.state == DeliveryTarget.State.EXPIRED
    assert target.last_error_code == "marketing_facts_changed_before_send"


def test_fact_payload_hash_rejects_tampering(product):
    facts = marketing_facts.resolve_facts(
        sku=product.sku,
        referenced=("price",),
        seed_variables={},
    ).as_payload()
    facts["variables"]["price"] = "R$ 0,01"

    with pytest.raises(MarketingContractError) as caught:
        marketing_facts.from_payload(facts)

    assert caught.value.code == "marketing_facts_hash_mismatch"
