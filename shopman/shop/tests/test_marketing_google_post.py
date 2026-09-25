"""Post do Google Meu Negócio: botão escolhido, tipo de postagem e travas.

As travas valem na prévia e na aprovação, com a mensagem no campo — o gestor
descobre ANTES de aprovar o que o Google recusaria. Limites conferidos na
documentação oficial em 25/09/2026 (ver ``marketing_google_post``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from shopman.shop.models import DeliveryTarget
from shopman.shop.services import marketing_google_post as google_post
from shopman.shop.services import marketing_media_probe as probe
from shopman.shop.services.marketing_artifacts import (
    normalize_platform_content,
    resolve_dispatch_artifact,
)
from shopman.shop.services.marketing_contracts import (
    MarketingContractError,
    ProviderOutcome,
    ProviderOutcomeKind,
)
from shopman.shop.services.marketing_publication_confirmation import (
    confirm_accepted_publications,
)

NOW = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)


def resolve(body="Pão de fermentação natural saindo agora.", link="/produto/pao", image="", **variant):
    return resolve_dispatch_artifact(
        platform="google_business",
        content={"body": body, "hashtags": ["padaria"], "link": link, "image_url": image},
        platform_content={
            "google_business": {"publication_format": "standard", **variant}
        },
        content_version=1,
    )


def field_of(exc: pytest.ExceptionInfo) -> str:
    return next(iter(exc.value.field_errors))


# ── botão ────────────────────────────────────────────────────────────


def test_without_choice_the_post_has_no_button_even_with_link():
    artifact = resolve()

    assert "callToAction" not in google_post.request_payload(artifact)


@pytest.mark.parametrize("choice", sorted(google_post.CALL_TO_ACTION_REFS))
def test_every_button_is_accepted_with_a_product_link(choice):
    artifact = resolve(call_to_action=choice)

    assert dict(artifact.provider_fields)["call_to_action"] == choice


def test_link_button_without_link_is_refused_on_the_field():
    with pytest.raises(MarketingContractError) as exc:
        resolve(link="", call_to_action="learn_more")

    assert exc.value.code == "google_call_to_action_link_required"
    assert field_of(exc) == "platform_content.google_business.call_to_action"


def test_call_button_needs_no_link():
    artifact = resolve(link="", call_to_action="call")

    assert google_post.request_payload(artifact)["callToAction"] == {"actionType": "CALL"}


@pytest.mark.parametrize("choice", ["order", "shop"])
def test_purchase_buttons_only_lead_to_product_or_offer(choice, settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://loja.example.test"
    with pytest.raises(MarketingContractError) as exc:
        google_post.validate_artifact(
            provider_fields={"publication_format": "standard", "call_to_action": choice},
            body="Conheça a casa",
            hashtags=(),
            link="https://loja.example.test/sobre",
            image_url="",
        )

    assert exc.value.code == "google_call_to_action_link_not_purchase"


def test_unknown_button_is_refused():
    with pytest.raises(MarketingContractError) as exc:
        resolve(call_to_action="directions")

    assert exc.value.code == "google_call_to_action_invalid"


def test_button_is_not_an_option_of_the_offer():
    with pytest.raises(MarketingContractError) as exc:
        normalize_platform_content(
            platforms=["google_business"],
            platform_content={
                "google_business": {"publication_format": "offer", "call_to_action": "call"}
            },
        )

    assert exc.value.code == "unsupported_provider_field"


# ── texto ────────────────────────────────────────────────────────────


def test_summary_over_the_google_limit_is_refused_counting_hashtags():
    body = "a" * (google_post.SUMMARY_MAX_CHARS - len("\n\n#padaria") + 1)

    with pytest.raises(MarketingContractError) as exc:
        resolve(body=body)

    assert exc.value.code == "google_summary_too_long"
    assert field_of(exc) == "content.body"


def test_summary_exactly_at_the_limit_passes():
    resolve(body="a" * (google_post.SUMMARY_MAX_CHARS - len("\n\n#padaria")))


@pytest.mark.parametrize(
    "body",
    [
        "Ligue (43) 3322-1100 e encomende",
        "WhatsApp 43 99988-7766",
        "+55 43 99988 7766",
        "Encomendas: 3322-1100",
        "Chame no 43999887766",
    ],
)
def test_phone_in_text_is_refused(body):
    with pytest.raises(MarketingContractError) as exc:
        resolve(body=body)

    assert exc.value.code == "google_summary_has_phone"


@pytest.mark.parametrize(
    "body",
    [
        "Croissant por R$ 12,90 até 25/09/2026",
        "Aberto das 07:00 às 19:30",
        "Entrega no CEP 86010-000",
        "Fornada de 1.500 pães no sábado",
        "Desde 1998, com 25 anos de casa",
    ],
)
def test_prices_dates_hours_and_zip_are_not_phones(body):
    resolve(body=body)


# ── foto ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "declared"),
    [
        ("https://img.example.test/p/pao.webp", "webp"),
        ("https://img.example.test/p/pao?fm=webp", "webp"),
        ("https://img.example.test/p/anim.gif", "gif"),
    ],
)
def test_photo_declared_outside_jpeg_or_png_is_refused(url, declared, settings):
    settings.SHOPMAN_MARKETING_MEDIA_HOSTS = ("img.example.test",)
    with pytest.raises(MarketingContractError) as exc:
        resolve(image=url)

    assert exc.value.code == "google_media_format_unsupported"
    assert declared.upper() in exc.value.detail


def _image_bytes(fmt: str, size: tuple[int, int], *, pad_to: int = 0) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (200, 150, 100)).save(buffer, format=fmt)
    data = buffer.getvalue()
    return data + b"\0" * max(0, pad_to - len(data))


class _ProbeResponse:
    def __init__(self, data: bytes, *, total: int | None = None):
        self.status = 206
        self.headers = {"Content-Range": f"bytes 0-{len(data) - 1}/{total or len(data)}"}
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, limit):
        return self._data[:limit]


@pytest.fixture
def probing(settings, monkeypatch):
    settings.SHOPMAN_MARKETING_MEDIA_PROBE_ENABLED = True
    settings.SHOPMAN_MARKETING_MEDIA_HOSTS = ("img.example.test",)
    cache.clear()

    def serve(data: bytes, *, total: int | None = None):
        opener = Mock()
        opener.open.return_value = _ProbeResponse(data, total=total)
        monkeypatch.setattr(probe, "_OPENER", opener)
        return opener

    return serve


def test_probe_accepts_jpeg_within_google_limits(probing):
    opener = probing(_image_bytes("JPEG", (1200, 900), pad_to=40_000))

    facts = probe.check_google_photo("https://img.example.test/home/facade2.jpg")

    assert (facts.format, facts.width, facts.height) == ("jpeg", 1200, 900)
    request = opener.open.call_args.args[0]
    assert request.get_header("Range") == f"bytes=0-{probe.PROBE_BYTES - 1}"


def test_probe_reads_the_real_format_not_the_extension(probing):
    probing(_image_bytes("WEBP", (1200, 900), pad_to=40_000))

    with pytest.raises(MarketingContractError) as exc:
        probe.check_google_photo("https://img.example.test/home/facade.jpg")

    assert exc.value.code == "google_media_format_unsupported"
    assert "WEBP" in exc.value.detail


@pytest.mark.parametrize(
    ("size", "total", "code"),
    [
        ((1200, 900), 6 * 1024 * 1024, "google_media_too_heavy"),
        ((1200, 900), 9 * 1024, "google_media_too_light"),
        ((240, 900), 40_000, "google_media_too_small"),
    ],
)
def test_probe_refuses_what_google_refuses(probing, size, total, code):
    probing(_image_bytes("PNG", size, pad_to=20_000), total=total)

    with pytest.raises(MarketingContractError) as exc:
        probe.check_google_photo("https://img.example.test/p.png", field="content.image_url")

    assert exc.value.code == code
    assert field_of(exc) == "content.image_url"


def test_probe_never_leaves_the_trusted_media_hosts(probing):
    opener = probing(_image_bytes("JPEG", (1200, 900), pad_to=40_000))

    with pytest.raises(MarketingContractError) as exc:
        probe.check_google_photo("https://evil.example.test/p.jpg")

    assert exc.value.code == "marketing_media_host_not_allowed"
    opener.open.assert_not_called()


def test_probe_outage_is_retryable(probing, monkeypatch):
    opener = Mock()
    opener.open.side_effect = TimeoutError()
    monkeypatch.setattr(probe, "_OPENER", opener)

    with pytest.raises(MarketingContractError) as exc:
        probe.check_google_photo("https://img.example.test/p.jpg")

    assert exc.value.code == "google_media_unreachable"
    assert exc.value.retryable is True


# ── evento e oferta ──────────────────────────────────────────────────


def test_event_needs_title_and_a_forward_period():
    with pytest.raises(MarketingContractError) as exc:
        resolve(
            publication_format="event",
            event_title="Semana do Pão",
            event_start="2026-10-05T10:00",
            event_end="2026-10-05T09:00",
        )

    assert exc.value.code == "google_event_period_invalid"
    assert field_of(exc) == "platform_content.google_business.event_end"


def test_event_fields_are_required_by_the_catalog():
    with pytest.raises(MarketingContractError) as exc:
        normalize_platform_content(
            platforms=["google_business"],
            platform_content={"google_business": {"publication_format": "event"}},
        )

    assert exc.value.code == "provider_field_required"


def test_ended_event_is_refused_before_approval():
    with pytest.raises(MarketingContractError) as exc:
        google_post.prepare_platform_content(
            {
                "google_business": {
                    "publication_format": "event",
                    "event_title": "Semana do Pão",
                    "event_start": "2026-09-20T08:00",
                    "event_end": "2026-09-21T08:00",
                }
            },
            facts=None,
            image_url="",
            timezone_name="America/Sao_Paulo",
            now=NOW,
        )

    assert exc.value.code == "google_event_already_ended"


PROMOTION = {
    "name": "Semana do Pão",
    "ref": "semana-do-pao",
    "type": "percent",
    "value": 10,
    "min_order_q": 0,
    "valid_from": "2026-09-20T03:00:00+00:00",
    "valid_until": "2026-10-12T02:59:00+00:00",
}


def test_offer_is_sealed_from_the_campaign_promotion():
    sealed = google_post.prepare_platform_content(
        {
            "google_business": {
                "publication_format": "offer",
                "offer_title": "Digitado pelo operador",
                "offer_terms": "Só na loja on-line.",
            }
        },
        facts={"promotion": PROMOTION},
        image_url="",
        timezone_name="America/Sao_Paulo",
        now=NOW,
    )["google_business"]

    # A oferta anunciada é a da loja: título e validade vêm da Promotion; a oferta
    # que já está valendo começa agora, não no passado.
    assert sealed["offer_title"] == "Semana do Pão"
    assert sealed["offer_start"] == "2026-09-25T12:00"
    assert sealed["offer_end"] == "2026-10-11T23:59"
    assert sealed["offer_terms"] == "Só na loja on-line."

    artifact = resolve_dispatch_artifact(
        platform="google_business",
        content={"body": "Semana do Pão", "link": "/oferta/semana-do-pao"},
        platform_content={"google_business": sealed},
        content_version=1,
    )
    assert artifact.format == "offer"


def test_offer_without_promotion_is_refused_on_the_type():
    with pytest.raises(MarketingContractError) as exc:
        google_post.prepare_platform_content(
            {"google_business": {"publication_format": "offer"}},
            facts={"promotion": {}},
            image_url="",
            timezone_name="America/Sao_Paulo",
            now=NOW,
        )

    assert exc.value.code == "google_offer_promotion_required"
    assert field_of(exc) == "platform_content.google_business.publication_format"


def test_offer_needs_the_offer_page_link():
    with pytest.raises(MarketingContractError) as exc:
        resolve(
            link="/produto/pao",
            publication_format="offer",
            offer_title="Semana do Pão",
            offer_start="2026-09-25T12:00",
            offer_end="2026-10-11T23:59",
        )

    assert exc.value.code == "google_offer_link_required"


def test_switching_away_from_offer_drops_the_sealed_offer_fields():
    prepared = google_post.prepare_platform_content(
        {
            "google_business": {
                "publication_format": "standard",
                "offer_title": "Resto de uma oferta",
            }
        },
        facts=None,
        image_url="",
        timezone_name="America/Sao_Paulo",
        now=NOW,
    )

    assert prepared["google_business"] == {"publication_format": "standard"}


# ── depois de publicar ───────────────────────────────────────────────


class _StateProvider:
    CONFIRMS_PUBLICATION_STATE = True

    def __init__(self, kind, code):
        self.outcome = ProviderOutcome(
            kind=kind, code=code, retryable=False, provider_receipt_ref="gbp:post-3"
        )
        self.lookups = []

    def lookup(self, **kwargs):
        self.lookups.append(kwargs)
        return self.outcome

    def send(self, **_kwargs):  # pragma: no cover - a consulta nunca publica
        raise AssertionError("confirmation must never send")


def _accepted_google_target(*, suffix: str, attempted_at=None):
    from shopman.shop.tests.test_marketing_delivery_recovery import _targets

    _announcement, targets = _targets(
        suffix=suffix, states=(DeliveryTarget.State.ACCEPTED,)
    )
    target = targets[0]
    DeliveryTarget.objects.filter(pk=target.pk).update(
        platform="google_business",
        delivery_kind="publication",
        format="standard",
        provider_receipt_ref="gbp:post-3",
        last_attempt_at=attempted_at or timezone.now(),
    )
    target.refresh_from_db()
    return target


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "code", "state", "error"),
    [
        (ProviderOutcomeKind.CONFIRMED, "google_post_live", "confirmed", ""),
        (ProviderOutcomeKind.FAILED_FINAL, "google_post_rejected", "failed_final", "google_post_rejected"),
        (ProviderOutcomeKind.ACCEPTED_UNCONFIRMED, "google_post_processing", "accepted", ""),
    ],
)
def test_accepted_google_post_follows_the_real_state(kind, code, state, error):
    target = _accepted_google_target(suffix=f"gbp-{state}")
    provider = _StateProvider(kind, code)

    outcomes = confirm_accepted_publications(
        providers={"google_business": provider}, now=timezone.now()
    )

    target.refresh_from_db()
    assert target.state == state
    assert target.last_error_code == error
    assert provider.lookups[0]["provider_receipt_ref"] == "gbp:post-3"
    assert sum(outcomes.values()) == 1


@pytest.mark.django_db
def test_confirmation_skips_adapters_that_do_not_report_state_and_old_targets():
    target = _accepted_google_target(
        suffix="gbp-old", attempted_at=timezone.now() - timedelta(days=3)
    )
    provider = _StateProvider(ProviderOutcomeKind.CONFIRMED, "google_post_live")
    silent = Mock(spec=["lookup"])

    confirm_accepted_publications(
        providers={"google_business": provider, "facebook": silent},
        now=timezone.now(),
    )

    target.refresh_from_db()
    assert target.state == "accepted"
    assert provider.lookups == []
    silent.lookup.assert_not_called()


@override_settings(SHOPMAN_MARKETING_MEDIA_PROBE_ENABLED=False)
def test_probe_can_be_switched_off_where_there_is_no_network():
    assert probe.check_google_photo("https://anything.example.test/x.jpg") is None
