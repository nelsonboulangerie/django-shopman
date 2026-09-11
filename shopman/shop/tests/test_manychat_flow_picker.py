"""Flow catalog states and containment of the legacy Admin write path."""

from __future__ import annotations

import pytest
from django.core.cache import cache

from shopman.shop.admin.shop import NotificationTemplateAdmin, NotificationTemplateForm
from shopman.shop.models import NotificationTemplate
from shopman.shop.services import manychat_flows

pytestmark = pytest.mark.django_db

FLOWS = (
    ("content20240614222050_512341", "Teste Webhook API Manychat"),
    ("content20210201131015_377918", "Arrays"),
)


@pytest.fixture(autouse=True)
def clean_cache():
    cache.delete("shopman.manychat.flows.v1")
    cache.delete("shopman.manychat.flows.v2")
    cache.delete("shopman.manychat.flows.last-good.v2")
    yield
    cache.delete("shopman.manychat.flows.v1")
    cache.delete("shopman.manychat.flows.v2")
    cache.delete("shopman.manychat.flows.last-good.v2")


def _template(ns: str = "") -> NotificationTemplate:
    return NotificationTemplate.objects.create(
        event="announcement_published", subject="", body="oi", whatsapp_flow_ns=ns
    )


def test_the_legacy_admin_field_is_read_only_even_when_provider_is_unavailable():
    form = NotificationTemplateForm(instance=_template())
    field = form.fields["whatsapp_flow_ns"]

    assert field.disabled is True
    assert "Marketing → Plataformas" in field.help_text


def test_posting_an_arbitrary_ref_to_legacy_form_cannot_change_it():
    template = _template(FLOWS[1][0])
    form = NotificationTemplateForm(
        data={
            "event": template.event,
            "subject": "Novidade na padaria",
            "body": "oi",
            "whatsapp_flow_ns": FLOWS[0][0],
            "is_active": True,
        },
        instance=template,
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.whatsapp_flow_ns == FLOWS[1][0]


def test_posting_empty_to_legacy_form_cannot_clear_the_flow():
    template = _template(FLOWS[0][0])
    form = NotificationTemplateForm(
        data={"event": template.event, "subject": "Novidade na padaria", "body": "oi",
              "whatsapp_flow_ns": "", "is_active": True},
        instance=template,
    )
    assert form.is_valid(), form.errors
    assert form.save().whatsapp_flow_ns == FLOWS[0][0]


def test_notification_template_admin_has_no_flow_or_activation_quick_write():
    assert "whatsapp_flow_ns" in NotificationTemplateAdmin.readonly_fields
    assert "is_active" in NotificationTemplateAdmin.readonly_fields
    assert not getattr(NotificationTemplateAdmin, "list_editable", ())


# ── O serviço por baixo ──────────────────────────────────────────────


def test_no_token_means_empty_not_an_exception(monkeypatch):
    monkeypatch.setattr("django.conf.settings.MANYCHAT_API_TOKEN", "", raising=False)
    assert manychat_flows.list_flows(force=True) == ()


def test_the_list_is_cached(monkeypatch):
    calls = {"n": 0}

    def _fake():
        calls["n"] += 1
        return FLOWS

    monkeypatch.setattr(manychat_flows, "_fetch", _fake)
    manychat_flows.list_flows(force=True)
    manychat_flows.list_flows()
    manychat_flows.list_flows()

    assert calls["n"] == 1, "o Admin renderiza muito; uma chamada de rede por render não"


def test_flow_name_resolves_and_admits_ignorance(monkeypatch):
    monkeypatch.setattr(manychat_flows, "_fetch", lambda: FLOWS)
    manychat_flows.list_flows(force=True)

    assert manychat_flows.flow_name(FLOWS[0][0]) == "Teste Webhook API Manychat"
    assert manychat_flows.flow_name("content20200101000000_000000") == ""
    assert manychat_flows.flow_name("") == ""


def test_successful_empty_catalog_is_known_not_an_outage(monkeypatch):
    monkeypatch.setattr(manychat_flows, "_fetch", lambda: ())

    catalog = manychat_flows.flow_catalog(force=True)

    assert catalog.state == "fresh"
    assert catalog.flows == ()
    assert catalog.mutation_safe is True


def test_outage_without_history_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        manychat_flows,
        "_fetch",
        lambda: manychat_flows._FetchResult(
            state="unavailable",
            reason_code="manychat_catalog_unreachable",
        ),
    )

    catalog = manychat_flows.flow_catalog(force=True)

    assert catalog.state == "unavailable"
    assert catalog.mutation_safe is False


def test_outage_retains_last_known_catalog_only_for_diagnosis(monkeypatch):
    monkeypatch.setattr(manychat_flows, "_fetch", lambda: FLOWS)
    assert manychat_flows.flow_catalog(force=True).mutation_safe is True
    monkeypatch.setattr(
        manychat_flows,
        "_fetch",
        lambda: manychat_flows._FetchResult(
            state="unavailable",
            reason_code="manychat_catalog_unreachable",
        ),
    )

    catalog = manychat_flows.flow_catalog(force=True)

    assert catalog.state == "stale"
    assert catalog.flows == FLOWS
    assert catalog.mutation_safe is False
    assert manychat_flows.list_flows() == ()


def test_explicitly_inactive_provider_rows_are_not_selectable():
    assert manychat_flows._row_is_active({"is_active": False}) is False
    assert manychat_flows._row_is_active({"status": "archived"}) is False
    assert manychat_flows._row_is_active({}) is True
