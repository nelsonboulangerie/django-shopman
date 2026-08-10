"""W010 — campanha com WhatsApp e sem template aprovado alcança só 24h.

Este check nasceu do jeito caro: um disparo real para um número frio devolveu
`code 3011` da Meta ("Content can't be sent... last interaction was over 18963h ago"),
e nada no sistema tinha avisado que aquilo ia acontecer. A configuração faltando só
aparecia no dia em que importava.

O aviso é Warning e não Error de propósito: campanha que alcança apenas a janela de 24h
ainda é campanha válida — quem conversou hoje recebe. O que não pode é a surpresa.
"""

from __future__ import annotations

import pytest

from shopman.shop.checks import check_whatsapp_flow_coverage

pytestmark = pytest.mark.django_db

EVENT = "announcement_published"


def _campaign(name: str, *, platforms, active: bool = True):
    from shopman.shop.models import AnnouncementTemplate, Campaign, Trigger

    template = AnnouncementTemplate.objects.create(name=f"T-{name}", body="oi")
    return Campaign.objects.create(
        name=name,
        trigger=Trigger.MANUAL,
        template=template,
        platforms=list(platforms),
        is_active=active,
    )


def _ids(warnings) -> list[str]:
    return [w.id for w in warnings]


def test_no_campaign_no_warning(db):
    assert check_whatsapp_flow_coverage(None) == []


def test_a_whatsapp_campaign_without_a_flow_warns(db):
    _campaign("Fornada", platforms=["whatsapp"])
    assert _ids(check_whatsapp_flow_coverage(None)) == ["SHOPMAN_W010"]


def test_the_warning_names_the_campaigns_so_the_fix_is_obvious(db):
    _campaign("Fornada pronta", platforms=["whatsapp"])
    _campaign("Recado", platforms=["whatsapp", "instagram"])

    (warning,) = check_whatsapp_flow_coverage(None)
    assert "Fornada pronta" in warning.msg
    assert "Recado" in warning.msg
    assert "manychat_flows" in warning.hint, "o aviso tem de dizer como consertar"


def test_a_configured_flow_silences_it(db):
    from shopman.shop.models import NotificationTemplate

    _campaign("Fornada", platforms=["whatsapp"])
    NotificationTemplate.objects.create(
        event=EVENT, subject="", body="oi", whatsapp_flow_ns="content20260101120000_1"
    )

    assert check_whatsapp_flow_coverage(None) == []


def test_an_empty_flow_ns_does_not_count_as_configured(db):
    """Registro existindo com campo vazio é o caso que mais engana."""
    from shopman.shop.models import NotificationTemplate

    _campaign("Fornada", platforms=["whatsapp"])
    NotificationTemplate.objects.create(event=EVENT, subject="", body="oi", whatsapp_flow_ns="")

    assert _ids(check_whatsapp_flow_coverage(None)) == ["SHOPMAN_W010"]


def test_a_campaign_without_whatsapp_is_not_the_subject(db):
    """Instagram e Google não têm janela de 24h; o aviso é só do WhatsApp."""
    _campaign("Só Instagram", platforms=["instagram", "google_business"])
    assert check_whatsapp_flow_coverage(None) == []


def test_an_inactive_campaign_is_not_the_subject(db):
    _campaign("Desligada", platforms=["whatsapp"], active=False)
    assert check_whatsapp_flow_coverage(None) == []
