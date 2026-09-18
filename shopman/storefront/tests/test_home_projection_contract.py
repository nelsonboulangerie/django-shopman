"""Home projection contract guardrails."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_home_projection_exposes_browser_key_but_never_server_key(rf, settings):
    from shopman.shop.models import Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.home import build_home

    Shop.load() or Shop.objects.create(name="Test Padaria")
    settings.GOOGLE_MAPS_API_KEY = "legacy-key"
    settings.GOOGLE_MAPS_BROWSER_API_KEY = "browser-key"
    settings.GOOGLE_MAPS_SERVER_API_KEY = "server-secret-key"

    payload = projection_data(build_home(rf.get("/api/v1/storefront/home/")))

    assert payload["public_config"]["google_maps_api_key"] == "browser-key"
    assert "server-secret-key" not in repr(payload)


def test_home_projection_keeps_operational_status_single_sourced(rf):
    from shopman.shop.models import FAQEntry, Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.home import build_home

    shop = Shop.load() or Shop.objects.create(name="Test Padaria")
    shop.opening_hours = {
        day: {"open": "07:00", "close": "19:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    }
    shop.save()
    FAQEntry.objects.create(
        question="Posso encomendar para amanhã?",
        answer="Sim. A disponibilidade e os horários aparecem no cardápio.",
        search_terms="encomenda, pedido futuro",
        is_published=True,
    )
    FAQEntry.objects.create(
        question="Resposta em revisão",
        answer="Ainda não deve aparecer.",
    )
    from django.core.cache import cache as django_cache

    from shopman.shop.models.shop import SHOP_CACHE_KEY

    django_cache.delete(SHOP_CACHE_KEY)

    payload = projection_data(build_home(rf.get("/api/v1/storefront/home/")))

    assert {"is_open", "opens_at", "closes_at"}.isdisjoint(payload["omotenashi"])
    assert set(payload["shop_status"]) == {"is_open", "label", "message", "opens_at", "closes_at"}
    assert payload["shop"]["short_name"] == shop.short_name
    assert payload["pwa_copy"]["install_cta"]["title"] == "Instalar"
    assert payload["pwa_copy"]["offline_message"]["message"].startswith("Sem conexão agora")
    assert "notices" in payload
    faq_by_ref = {item["ref"]: item for item in payload["faq"]}
    assert {"delivery", "hours", "curated-posso-encomendar-para-amanha"} <= faq_by_ref.keys()
    assert "curated-resposta-em-revisao" not in faq_by_ref
    assert faq_by_ref["delivery"]["answer"].startswith("Sim. Fazemos entrega")
    assert set(faq_by_ref["curated-posso-encomendar-para-amanha"]) == {
        "ref",
        "question",
        "answer",
    }
    assert all(
        {"ref", "tone", "title", "message", "priority", "actions"} <= set(notice)
        for notice in payload["notices"]
    )
    assert payload["shop_status"]["is_open"] in {True, False}
    # Label é copy do registro (`SHOP_STATUS_*`), granular e dependente da HORA:
    # "Aberto até 19h", "Últimos pedidos até 19h" na última hora antes de fechar,
    # "Fechado agora. Abrimos amanhã às 7h".
    #
    # ⚠️ O contrato é "o rótulo é uma das copies DESTE estado", e ele se lê do mesmo
    # registro que a projection usa. Comparar com literal (`startswith("Aberto")`)
    # transformava este teste em bomba-relógio: das 18h às 19h a loja está ABERTA e o
    # rótulo começa com "Últimos pedidos" — e nessa uma hora do dia todo PR do
    # repositório parava num check obrigatório que nada tinha a ver com ele.
    from shopman.storefront.presentation import shop_status as shop_status_copy

    esperadas = (
        ("SHOP_STATUS_OPEN", "SHOP_STATUS_OPEN_UNTIL", "SHOP_STATUS_OPEN_CLOSING_SOON")
        if payload["shop_status"]["is_open"]
        else ("SHOP_STATUS_CLOSED", "SHOP_STATUS_CLOSED_OPENS_AT")
    )
    status_label = payload["shop_status"]["label"]
    assert status_label
    assert any(status_label.startswith(shop_status_copy._copy(chave)) for chave in esperadas), status_label


def test_curated_faq_starts_as_draft_and_cannot_shadow_operational_answers():
    from django.core.exceptions import ValidationError

    from shopman.shop.models import FAQEntry

    draft = FAQEntry(question="Aceitam encomendas?", answer="Sim.")
    assert draft.is_published is False

    duplicate = FAQEntry(
        question="Vocês fazem entrega?",
        answer="Não.",
        is_published=True,
    )
    with pytest.raises(ValidationError, match="configuração canônica"):
        duplicate.full_clean()
    with pytest.raises(ValidationError, match="configuração canônica"):
        duplicate.save()


def test_home_projection_does_not_promote_whatsapp_origin_without_cart(rf):
    from shopman.shop.models import Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.home import build_home

    Shop.load() or Shop.objects.create(name="Test Padaria")

    request = rf.get("/api/v1/storefront/home/")
    request.session = {"origin_channel": "whatsapp"}

    payload = projection_data(build_home(request))
    notices = {notice["ref"]: notice for notice in payload["notices"]}

    assert "origin_whatsapp" not in notices


def test_home_projection_promotes_whatsapp_origin_only_with_real_cart(rf):
    from shopman.orderman.models import Session

    from shopman.shop.models import Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
    from shopman.storefront.presentation.home import build_home

    Shop.load() or Shop.objects.create(name="Test Padaria")
    cart = Session.objects.create(
        session_key="home-cart-whatsapp",
        channel_ref=STOREFRONT_CHANNEL_REF,
        state="open",
        items=[{"line_id": "L1", "sku": "PAO-FRANCES", "qty": 1, "unit_price_q": 100}],
    )

    request = rf.get("/api/v1/storefront/home/")
    request.session = {"origin_channel": "whatsapp", "cart_session_key": cart.session_key}

    payload = projection_data(build_home(request))
    notices = {notice["ref"]: notice for notice in payload["notices"]}

    assert notices["origin_whatsapp"]["priority"] == "contextual"
    assert notices["origin_whatsapp"]["tone"] == "info"
    assert notices["origin_whatsapp"]["title"] == "Sua sacola está aqui"
    assert notices["origin_whatsapp"]["actions"][0]["href"] == "/finalizar"


# ── A pergunta de novidades chega pela HOME ──────────────────────────────
#
# Quem volta com aparelho reconhecido raramente passa pelo login, então o sheet
# de novidades da loja não pode depender do payload de sessão do login: ele lê
# `omotenashi.marketing_prompt_pending`, que a home devolve em toda visita.


def _login_home_customer(client, *, ref: str, phone: str, **extra):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer
    from shopman.guestman.models import Customer

    from shopman.shop.models import Shop

    Shop.load() or Shop.objects.create(name="Test Padaria")
    customer = Customer.objects.create(ref=ref, first_name="Ana", last_name="Silva", phone=phone, **extra)
    info = AuthCustomerInfo(uuid=customer.uuid, name=customer.name, phone=customer.phone, email=None, is_active=True)
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return customer


def test_home_marks_the_marketing_question_pending_for_a_customer_who_never_answered(client, settings):
    settings.RATELIMIT_ENABLE = False
    _login_home_customer(client, ref="CUS-HOME-MKT-ASK", phone="+5543999990040")

    omotenashi = client.get("/api/v1/storefront/home/").json()["home"]["omotenashi"]

    assert omotenashi["audience"] != "anon"
    assert omotenashi["marketing_prompt_pending"] is True


def test_home_does_not_ask_again_once_the_question_was_answered(client, settings):
    settings.RATELIMIT_ENABLE = False
    _login_home_customer(
        client,
        ref="CUS-HOME-MKT-DONE",
        phone="+5543999990041",
        metadata={"marketing_prompt_answered_at": "2026-09-16T10:00:00+00:00"},
    )

    omotenashi = client.get("/api/v1/storefront/home/").json()["home"]["omotenashi"]

    assert omotenashi["audience"] != "anon"
    assert omotenashi["marketing_prompt_pending"] is False


def test_home_never_asks_an_anonymous_visitor(client, settings):
    from shopman.shop.models import Shop

    settings.RATELIMIT_ENABLE = False
    Shop.load() or Shop.objects.create(name="Test Padaria")

    omotenashi = client.get("/api/v1/storefront/home/").json()["home"]["omotenashi"]

    assert omotenashi["audience"] == "anon"
    assert omotenashi["marketing_prompt_pending"] is False


def test_home_fails_closed_and_says_why_when_the_lookup_breaks(rf, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from shopman.storefront import identity
    from shopman.storefront.presentation import home

    def boom(_request):
        raise RuntimeError("consent source down")

    # O logger `shopman` não propaga para o root: espiar o do módulo é o que
    # prova a razão escrita, sem depender da configuração de logging.
    spy = MagicMock()
    monkeypatch.setattr(home, "logger", spy)
    monkeypatch.setattr(identity, "get_authenticated_customer", boom)
    request = rf.get("/api/v1/storefront/home/")
    request.customer = SimpleNamespace(uuid="00000000-0000-0000-0000-000000000000")

    assert home._marketing_prompt_pending(request) is False

    spy.warning.assert_called_once()
    assert "home.marketing_prompt_pending_unavailable" in spy.warning.call_args.args[0]
