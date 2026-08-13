"""Handlers de campanha — receivers de evento e handlers de directive.

Dois contratos: (1) marketing nunca derruba a operação que o disparou; (2) a
audiência é resolvida no despacho, não na criação do announcement.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from shopman.offerman.models import Product

from shopman.shop.handlers import campaign as handlers
from shopman.shop.models import Announcement, AnnouncementStatus, AnnouncementTemplate, Campaign

pytestmark = pytest.mark.django_db

SKU = "croissant-trad"


@pytest.fixture
def product():
    return Product.objects.create(sku=SKU, name="Croissant", base_price_q=850, is_sellable=True)


@pytest.fixture
def rule():
    template = AnnouncementTemplate.objects.create(name="T", body="{{product_name}} saiu do forno")
    return Campaign.objects.create(
        name="Fornada", trigger="production_finished",
        template=template, platforms=["instagram"],
    )


def _work_order(**overrides):
    fields = {
        "ref": "WO-2026-00001",
        "meta": {"quality": "excellent"},
        "finished": 40,
        "finished_at": None,
        "output_sku": SKU,
    }
    return SimpleNamespace(**{**fields, **overrides})


# ── Receiver de produção ─────────────────────────────────────────────


class TestProductionReceiver:
    def _fire(self, *, action="finished", work_order=None):
        with patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()):
            handlers.on_production_changed(
                sender=None, product_ref=SKU, date=None, action=action,
                work_order=work_order or _work_order(),
            )

    def test_finished_bake_creates_a_post(self, product, rule):
        self._fire()
        assert Announcement.objects.count() == 1

    def test_other_actions_are_ignored(self, product, rule):
        for action in ("planned", "started", "adjusted", "voided"):
            self._fire(action=action)
        assert Announcement.objects.count() == 0

    def test_quality_flows_from_work_order_meta(self, product, rule):
        self._fire()
        assert Announcement.objects.get().trigger_context["quality"] == "excellent"

    def test_missing_quality_defaults_to_catalog_default(self, product, rule):
        self._fire(work_order=_work_order(meta={}))
        assert Announcement.objects.get().trigger_context["quality"] == "standard"

    def test_evaluation_failure_never_breaks_the_bake(self, product, rule):
        """Marketing quebrado não pode impedir o operador de fechar a fornada."""
        with patch(
            "shopman.shop.services.campaign.evaluate", side_effect=RuntimeError("boom")
        ):
            self._fire()  # não levanta

    def test_evaluation_waits_for_commit(self, product, rule):
        """Avaliar dentro da transação leria estoque que ainda não existe."""
        with patch("django.db.transaction.on_commit") as on_commit:
            handlers.on_production_changed(
                sender=None, product_ref=SKU, date=None,
                action="finished", work_order=_work_order(),
            )
        on_commit.assert_called_once()
        assert Announcement.objects.count() == 0


# ── Receiver de disponibilidade ──────────────────────────────────────


class TestAvailabilityReceiver:
    def _fire(self, *, available, was_out=False):
        with (
            patch.object(handlers, "_available_qty", return_value=available),
            patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
        ):
            handlers.on_availability_changed(sender=None, sku=SKU, was_out_of_stock=was_out)

    def _rule(self, trigger: str):
        template = AnnouncementTemplate.objects.create(name=trigger, body="{{product_name}}")
        return Campaign.objects.create(
            name=trigger, trigger=trigger, template=template, platforms=["instagram"]
        )

    def test_scarce_stock_triggers_low_stock(self, product):
        self._rule("low_stock")
        self._fire(available=2)
        assert Announcement.objects.count() == 1

    def test_healthy_stock_triggers_nothing(self, product):
        self._rule("low_stock")
        self._fire(available=50)
        assert Announcement.objects.count() == 0

    def test_sold_out_announces_nothing(self, product):
        """Sem estoque não há o que anunciar."""
        self._rule("low_stock")
        self._fire(available=0)
        assert Announcement.objects.count() == 0

    def test_coming_back_triggers_stock_back(self, product):
        self._rule("stock_back")
        self._fire(available=20, was_out=True)
        assert Announcement.objects.count() == 1

    def test_missing_sku_is_ignored(self, product):
        self._rule("low_stock")
        handlers.on_availability_changed(sender=None, sku="")
        assert Announcement.objects.count() == 0


# ── Directive: announcement.publish ────────────────────────────────────────


class TestPostHandler:
    def _announcement(self, rule) -> Announcement:
        return Announcement.objects.create(
            rule=rule, template=rule.template, status=AnnouncementStatus.PUBLISHING,
            content={"body": "Croissant saiu do forno"}, platforms=["instagram"],
        )

    def _handle(self, announcement, platform="instagram"):
        message = SimpleNamespace(pk=1, payload={"announcement_id": announcement.pk, "platform": platform})
        handlers.AnnouncementHandler().handle(message=message, ctx={})

    def test_without_an_adapter_the_post_waits_for_manual_publishing(self, rule):
        """Sem credencial (F5/F6), o conteúdo fica pronto e o gestor copia."""
        announcement = self._announcement(rule)
        self._handle(announcement)
        announcement.refresh_from_db()
        assert announcement.platform_results["instagram"]["status"] == "pending_manual"

    def test_manual_publishing_still_closes_the_post(self, rule):
        announcement = self._announcement(rule)
        self._handle(announcement)
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PUBLISHED
        assert announcement.published_at is not None

    def test_a_working_adapter_publishes(self, rule):
        announcement = self._announcement(rule)
        adapter = MagicMock()
        adapter.publish.return_value = {"post_id": "ig_123", "url": "https://ig/p/123"}
        with patch.object(handlers, "_posting_adapter", return_value=adapter):
            self._handle(announcement)
        announcement.refresh_from_db()
        # A chave `post_id` aqui é do INSTAGRAM, não nossa: o adapter devolve o dicionário
        # dele e o handler o repassa opaco. Renomear seria inventar vocabulário na
        # plataforma alheia.
        assert announcement.platform_results["instagram"]["post_id"] == "ig_123"
        assert announcement.status == AnnouncementStatus.PUBLISHED

    def test_adapter_failure_marks_the_post_and_reraises_for_retry(self, rule):
        announcement = self._announcement(rule)
        adapter = MagicMock()
        adapter.publish.side_effect = RuntimeError("meta fora do ar")
        with (
            patch.object(handlers, "_posting_adapter", return_value=adapter),
            pytest.raises(RuntimeError),
        ):
            self._handle(announcement)
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.FAILED

    def test_a_post_is_only_settled_once_every_platform_answered(self, rule):
        announcement = self._announcement(rule)
        announcement.platforms = ["instagram", "google_business"]
        announcement.save()
        self._handle(announcement)
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PUBLISHING

        self._handle(announcement, platform="google_business")
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PUBLISHED

    def test_missing_post_is_a_no_op(self):
        message = SimpleNamespace(pk=1, payload={"announcement_id": 9999, "platform": "instagram"})
        handlers.AnnouncementHandler().handle(message=message, ctx={})


# ── Directive: announcement.notify ──────────────────────────────────────


class TestNotifyHandler:
    def _announcement(self) -> Announcement:
        template = AnnouncementTemplate.objects.create(name="T", body="{{product_name}}")
        rule = Campaign.objects.create(
            name="Audiência", trigger="production_finished", template=template,
            platforms=["whatsapp"], audience_rules={"favorites": True},
        )
        return Announcement.objects.create(
            rule=rule, template=template, status=AnnouncementStatus.PUBLISHING,
            content={"body": "Saiu do forno", "link": "https://loja/p/x"},
            platforms=["whatsapp"], trigger_context={"sku": SKU},
        )

    def _handle(self, announcement, wave="all"):
        message = SimpleNamespace(pk=1, payload={"announcement_id": announcement.pk, "wave": wave})
        handlers.AnnouncementNotifyHandler().handle(message=message, ctx={})

    def test_audience_is_resolved_at_dispatch_not_at_creation(self):
        """Entre a fornada e a aprovação, favoritos e alertas mudam."""
        announcement = self._announcement()
        with patch("shopman.shop.services.audience.resolve") as resolve:
            resolve.return_value.all_recipients.return_value = ()
            self._handle(announcement)
        resolve.assert_called_once()
        # `sku` é keyword desde a F8: campanha manual não tem evento nem SKU, então a
        # assinatura virou `resolve(rules, *, sku="")`.
        assert resolve.call_args.kwargs["sku"] == SKU

    def test_each_recipient_gets_the_message(self):
        announcement = self._announcement()
        recipients = (
            SimpleNamespace(phone="+5543999990001"),
            SimpleNamespace(phone="+5543999990002"),
        )
        with (
            patch("shopman.shop.services.audience.resolve") as resolve,
            patch("shopman.shop.notifications.notify") as notify,
        ):
            resolve.return_value.all_recipients.return_value = recipients
            notify.return_value = SimpleNamespace(success=True)
            self._handle(announcement)
        assert notify.call_count == 2
        announcement.refresh_from_db()
        assert announcement.platform_results["whatsapp"]["sent"] == 2

    def test_a_failed_send_is_counted_not_swallowed(self):
        announcement = self._announcement()
        with (
            patch("shopman.shop.services.audience.resolve") as resolve,
            patch("shopman.shop.notifications.notify", side_effect=RuntimeError("wa off")),
        ):
            resolve.return_value.all_recipients.return_value = (
                SimpleNamespace(phone="+5543999990001"),
            )
            self._handle(announcement)
        announcement.refresh_from_db()
        assert announcement.platform_results["whatsapp"]["failed"] == 1

    def test_the_vip_wave_only_reaches_vips(self):
        announcement = self._announcement()
        with (
            patch("shopman.shop.services.audience.resolve") as resolve,
            patch("shopman.shop.notifications.notify") as notify,
        ):
            resolve.return_value.vip = (SimpleNamespace(phone="+5543999990010"),)
            resolve.return_value.general = (
                SimpleNamespace(phone="+5543999990011"),
                SimpleNamespace(phone="+5543999990012"),
            )
            notify.return_value = SimpleNamespace(success=True)
            self._handle(announcement, wave="vip")
        assert notify.call_count == 1

    def test_empty_audience_still_closes_the_post(self):
        announcement = self._announcement()
        with patch("shopman.shop.services.audience.resolve") as resolve:
            resolve.return_value.all_recipients.return_value = ()
            self._handle(announcement)
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PUBLISHED
