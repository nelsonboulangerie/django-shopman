"""G-H07/MKT-048: o Admin audita; somente o Marketing Nuxt opera."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory, override_settings
from django.urls import reverse

from shopman.backstage.admin.navigation import get_sidebar_navigation
from shopman.shop.admin.campaign import (
    AnnouncementTemplateAdmin,
    CampaignAdmin,
)
from shopman.shop.models import (
    Announcement,
    AnnouncementTemplate,
    AudienceSnapshot,
    AudienceSnapshotMember,
    Campaign,
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
    MarketingAuditEvent,
    MarketingCommandReceipt,
    MarketingOutbox,
    MarketingPlatformAuditEvent,
    MarketingSecurityEvent,
    Shop,
)

AUDIT_MODELS = (
    Announcement,
    MarketingCommandReceipt,
    AudienceSnapshot,
    MarketingAuditEvent,
    MarketingPlatformAuditEvent,
    MarketingSecurityEvent,
)


def _request(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_nuxt_owned_configuration_has_no_admin_write_path():
    assert Campaign not in admin.site._registry
    assert AnnouncementTemplate not in admin.site._registry

    isolated_site = AdminSite(name="marketing-ownership-test")
    for model, admin_class in (
        (Campaign, CampaignAdmin),
        (AnnouncementTemplate, AnnouncementTemplateAdmin),
    ):
        model_admin = admin_class(model, isolated_site)
        request = _request(User(username="auditor", is_staff=True))
        assert model_admin.list_editable == ()
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False


def test_audit_is_registered_but_protected_delivery_identity_is_not():
    assert all(model in admin.site._registry for model in AUDIT_MODELS)
    assert all(
        model not in admin.site._registry
        for model in (
            AudienceSnapshotMember,
            MarketingOutbox,
            DeliveryTarget,
            DeliveryAttempt,
            DeliveryReconciliation,
        )
    )


def test_every_marketing_audit_admin_is_strictly_read_only():
    request = _request(User(username="audit", is_staff=True, is_superuser=True))

    for model in AUDIT_MODELS:
        model_admin = admin.site.get_model_admin(model)
        assert model_admin.has_view_permission(request) is True
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False
        assert model_admin.actions == ()


def test_audit_capability_opens_lists_without_granting_model_write(client, django_user_model):
    Shop.objects.create(name="Loja")
    auditor = django_user_model.objects.create_user(
        username="marketing-auditor",
        password="safe-test-password",
        is_staff=True,
    )
    auditor.user_permissions.add(Permission.objects.get(content_type__app_label="shop", codename="audit_marketing"))
    client.force_login(auditor)

    for model in AUDIT_MODELS:
        opts = model._meta
        response = client.get(reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist"))
        assert response.status_code == 200, opts.label


def test_staff_without_audit_capability_cannot_open_marketing_audit(client, django_user_model):
    Shop.objects.create(name="Loja")
    staff = django_user_model.objects.create_user(
        username="ordinary-staff",
        password="safe-test-password",
        is_staff=True,
    )
    client.force_login(staff)

    response = client.get(reverse("admin:shop_marketingcommandreceipt_changelist"))

    assert response.status_code == 403


@override_settings(SHOPMAN_MARKETING_BASE_URL="https://marketing.example.com")
def test_sidebar_separates_cockpit_from_read_only_audit():
    user = User(username="nav-admin", is_staff=True, is_superuser=True)
    groups = get_sidebar_navigation(_request(user))

    apps = next(group for group in groups if group["title"] == "Aplicativos")
    marketing_app = next(item for item in apps["items"] if item["title"] == "Marketing")
    assert marketing_app["link"] == "https://marketing.example.com"

    audit = next(group for group in groups if group["title"] == "Marketing — auditoria")
    assert [item["title"] for item in audit["items"]] == [
        "Anúncios",
        "Comprovantes",
        "Públicos selados",
        "Decisões",
        "Configurações de plataforma",
        "Segurança",
    ]
