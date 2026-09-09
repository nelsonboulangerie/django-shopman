"""Generic copy transport plus the MKT-038 automatic-generation tombstone."""

from __future__ import annotations

import pytest
from shopman.offerman.models import Product

from shopman.shop.models import AnnouncementTemplate, Campaign, Shop, Trigger
from shopman.shop.services import campaign as campaign_service
from shopman.shop.services import copy_assist

pytestmark = pytest.mark.django_db


@pytest.fixture
def configured(settings):
    settings.AI_ASSIST_API_KEY = "sk-teste"
    settings.AI_ASSIST_PROVIDER = "anthropic"
    return settings


@pytest.fixture
def product():
    return Product.objects.create(
        sku="CRO-001",
        name="Croissant",
        base_price_q=1200,
        is_published=True,
        is_sellable=True,
    )


@pytest.fixture
def template():
    return AnnouncementTemplate.objects.create(
        name="Fornada",
        body="{{product_name}} saiu do forno!",
        use_ai_generation=True,
        ai_prompt="Fale do cheiro.",
    )


def _rule(template, *, requires_approval=True) -> Campaign:
    return Campaign.objects.create(
        name="Fornada",
        trigger=Trigger.PRODUCTION_FINISHED,
        template=template,
        platforms=["instagram"],
        requires_approval=requires_approval,
    )


def test_the_shop_voice_wins_when_configured():
    Shop.objects.create(name="Nelson", brand_voice="Fale como a Nelson fala.")
    assert copy_assist.brand_voice() == "Fale como a Nelson fala."


def test_an_empty_voice_falls_back_to_the_system_voice():
    Shop.objects.create(name="Nelson", brand_voice="")
    assert copy_assist.brand_voice() == copy_assist.DEFAULT_VOICE


def test_the_voice_survives_a_missing_shop():
    assert copy_assist.brand_voice() == copy_assist.DEFAULT_VOICE


def test_catalog_reads_the_canonical_shop_voice(configured, monkeypatch):
    Shop.objects.create(name="Nelson", brand_voice="A VOZ DA CASA")
    seen: list[str] = []

    def _capture(prompt, *, max_tokens=400, voice="", timeout=None):
        seen.append(voice or copy_assist.brand_voice())
        return "texto"

    monkeypatch.setattr(copy_assist, "suggest", _capture)
    Product.objects.create(sku="CRO-002", name="Croissant", base_price_q=1200)

    from shopman.backstage.services import catalog as catalog_service

    catalog_service.ai_assist_field("CRO-002", "short_description")
    assert seen == ["A VOZ DA CASA"]


def test_without_a_key_nothing_is_offered(settings):
    settings.AI_ASSIST_API_KEY = ""
    assert copy_assist.is_configured() is False


def test_without_a_key_asking_says_it_is_configuration_not_failure(settings):
    settings.AI_ASSIST_API_KEY = ""
    with pytest.raises(copy_assist.CopyAssistNotConfigured):
        copy_assist.suggest("escreva algo")


def test_an_unknown_provider_is_refused(settings):
    settings.AI_ASSIST_API_KEY = "sk-teste"
    settings.AI_ASSIST_PROVIDER = "papagaio"
    with pytest.raises(copy_assist.CopyAssistError):
        copy_assist.suggest("escreva algo")


def test_ai_opt_in_never_changes_announcement_birth(configured, monkeypatch, template, product):
    called: list[int] = []
    monkeypatch.setattr(
        copy_assist,
        "suggest",
        lambda *a, **k: called.append(1) or "TEXTO DA IA",
    )

    announcement = campaign_service._create_announcement(_rule(template), {"sku": product.sku})

    assert announcement.content["body"] == "Croissant saiu do forno!"
    assert called == []


def test_ai_can_never_inherit_no_approval_auto_dispatch(configured, monkeypatch, template, product):
    provider_calls: list[int] = []
    dispatches: list[int] = []
    monkeypatch.setattr(
        copy_assist,
        "suggest",
        lambda *a, **k: provider_calls.append(1) or "TEXTO DA IA",
    )
    monkeypatch.setattr(
        campaign_service,
        "dispatch",
        lambda announcement: dispatches.append(announcement.pk),
    )

    announcement = campaign_service._create_announcement(
        _rule(template, requires_approval=False),
        {"sku": product.sku},
    )

    assert announcement.content["body"] == "Croissant saiu do forno!"
    assert provider_calls == []
    assert dispatches == [announcement.pk]


def test_a_reply_cut_at_the_token_ceiling_is_a_failure_not_a_suggestion(configured, monkeypatch):
    import sys
    import types

    class _Message:
        stop_reason = "max_tokens"
        content = [types.SimpleNamespace(type="text", text='{"body":"cort')]

    class _Client:
        def __init__(self, **kwargs):
            self.messages = types.SimpleNamespace(create=lambda **kw: _Message())

    fake = types.ModuleType("anthropic")
    fake.Anthropic = _Client
    fake.APIError = Exception
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    with pytest.raises(copy_assist.CopyAssistError, match="limite de 50 tokens"):
        copy_assist.suggest("qualquer coisa", max_tokens=50, voice="voz", timeout=3)
