"""Rascunho de pergunta frequente vindo de conversa vira aviso no topo do Gestor (WP-15).

O dono perguntou "o gestor é avisado?": o rascunho que a equipe promove de um "vou
verificar" não pode dormir no Admin. Um aviso só, com a contagem, no topo do Gestor, com o
botão que leva a ele; some quando não sobra rascunho.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import FAQEntry, Shop
from shopman.shop.services import faq_drafts

pytestmark = pytest.mark.django_db


def _open():
    return OperatorAlert.objects.filter(type=faq_drafts.ALERT_TYPE, resolved_at__isnull=True)


def _draft(ref: str, *, published=False) -> FAQEntry:
    return FAQEntry.objects.create(ref=ref, question=f"Pergunta {ref}?", answer="Resposta.", is_published=published)


def test_a_promoted_draft_opens_one_alert_that_counts_and_goes_away():
    first = _draft("concierge-1-aaaaaaaaaaaa")
    assert [a.message for a in _open()] == ["1 pergunta frequente espera publicação."]

    second = _draft("concierge-2-bbbbbbbbbbbb")
    assert [a.message for a in _open()] == ["2 perguntas frequentes esperam publicação."], "o mesmo aviso, contagem nova"

    first.is_published = True
    first.save()
    assert [a.message for a in _open()] == ["1 pergunta frequente espera publicação."]

    second.delete()
    assert not _open().exists(), "sem rascunho, o aviso some"


def test_a_draft_written_in_the_admin_does_not_alert():
    _draft("pergunta-do-admin")
    assert not _open().exists()


def test_the_alert_asks_for_the_top_and_its_button_opens_the_draft(settings):
    from shopman.backstage.alert_specs import spec_for
    from shopman.backstage.projections.alerts import _home_for

    settings.SHOPMAN_ADMIN_HOST = "admin.exemplo.com.br"
    only = _draft("concierge-1-aaaaaaaaaaaa")
    alert = _open().get()

    assert spec_for(alert.type).on_screen
    assert alert.audience == "orders", "aparece no Gestor"
    assert _home_for(alert, target_date="") == (
        "admin", reverse("admin:shop_faqentry_change", args=[only.pk]), "Revisar no Admin",
    )

    _draft("concierge-2-bbbbbbbbbbbb")
    surface, path, label = _home_for(alert, target_date="")
    assert (surface, label) == ("admin", "Revisar no Admin")
    assert path.startswith(reverse("admin:shop_faqentry_changelist"))
    assert "origem=concierge" in path and "is_published__exact=0" in path


def test_the_admin_list_filters_by_origin(admin_client):
    Shop.objects.get_or_create(name="Casa") if not Shop.objects.exists() else None
    _draft("concierge-1-aaaaaaaaaaaa")
    _draft("pergunta-do-admin")

    page = admin_client.get(reverse("admin:shop_faqentry_changelist") + "?is_published__exact=0&origem=concierge")

    assert page.status_code == 200
    body = page.content.decode()
    assert "concierge-1-aaaaaaaaaaaa" in body or "Pergunta concierge-1-aaaaaaaaaaaa?" in body
    assert "Pergunta pergunta-do-admin?" not in body
