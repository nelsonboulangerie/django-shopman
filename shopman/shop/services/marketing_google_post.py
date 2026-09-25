"""Regras do post do Google Meu Negócio: botão, tipo de postagem e travas.

Uma fonte só para a prévia, a aprovação, o artefato selado e o adapter. O botão é
sempre ESCOLHA do operador (``call_to_action``, padrão ``none``): link no conteúdo
nunca vira botão por conta própria — em 25/09/2026 o adapter punha "Pedir on-line"
em todo post com link, rótulo que mente quando o link não é de compra.

Limites conferidos na documentação oficial do Google em 25/09/2026:

- ``CallToAction.url`` "should be left unset for Call CTA" e ``ActionType`` só tem
  ``BOOK``/``ORDER``/``SHOP``/``LEARN_MORE``/``SIGN_UP``/``CALL`` — "Como chegar"
  não existe (developers.google.com/my-business/reference/rest/v4/accounts.locations.localPosts);
- ``EVENT`` pede título, início e fim; ``OFFER`` é "an event and offer related
  content" (mesma referência);
- foto: "JPG or PNG", "Between 10 KB and 5 MB", "Minimum resolution: 250 px tall,
  250 px wide" (support.google.com/business/answer/6103862);
- telefone no texto: posts "might get rejected if they cannot be verified as being
  connected to the business" (support.google.com/business/answer/7342169);
- texto: 1.500 caracteres. A referência da API não traz o número; ele é a
  validação do próprio formulário do Google ("Enter details no longer than 1500
  characters"), a mesma que a API aplica ao ``summary``.

Este módulo é puro, exceto ``prepare_platform_content`` (relógio e sonda da foto),
que só roda na prévia e na aprovação — nunca ao reler um artefato selado.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

from shopman.shop.services.marketing_contracts import MarketingContractError

PLATFORM = "google_business"

#: Ref do botão (identificador estável) → ``ActionType`` da API. O rótulo pt-BR que o
#: Google mostra mora no Nuxt (`presentation/googleBusinessPost.ts`).
CALL_TO_ACTIONS: Mapping[str, str] = {
    "book": "BOOK",
    "order": "ORDER",
    "shop": "SHOP",
    "learn_more": "LEARN_MORE",
    "sign_up": "SIGN_UP",
    "call": "CALL",
}
NO_CALL_TO_ACTION = "none"
CALL_TO_ACTION_REFS = frozenset({NO_CALL_TO_ACTION, *CALL_TO_ACTIONS})
#: "Ligar agora" usa o telefone do perfil: a API recusa URL nesse botão.
_WITHOUT_URL = frozenset({"call"})
#: Pedir/Comprar só levam a um produto ou a uma oferta da loja.
_PURCHASE = frozenset({"order", "shop"})

TOPIC_TYPES: Mapping[str, str] = {
    "standard": "STANDARD",
    "event": "EVENT",
    "offer": "OFFER",
}

SUMMARY_MAX_CHARS = 1500
PHOTO_FORMATS = frozenset({"jpeg", "png"})
PHOTO_MIN_BYTES = 10 * 1024
PHOTO_MAX_BYTES = 5 * 1024 * 1024
PHOTO_MIN_SIDE_PX = 250

_LOCAL_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
_PRODUCT_OR_OFFER_PATH = re.compile(r"^/(?:produto|oferta)/[^/]+/?$")
_OFFER_PATH = re.compile(r"^/oferta/[^/]+/?$")
# Telefone brasileiro: 8 ou 9 dígitos no fim, com DDD e +55 opcionais. Preço
# ("R$ 12,90"), data ("25/09/2026"), hora e CEP ("86010-000") não fecham o padrão.
_PHONE = re.compile(
    r"(?<![\d/])(?:\+?\s?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?[\s.-]?\d{4}[\s.-]?\d{4}(?![\d/])"
)
_KNOWN_EXTENSIONS = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "webp": "webp",
    "gif": "gif",
    "avif": "avif",
    "svg": "svg",
    "heic": "heic",
}


def summary(body: str, hashtags) -> str:
    tags = " ".join(f"#{tag}" for tag in hashtags)
    return "\n\n".join(part for part in (body, tags) if part)


def call_to_action(provider_fields: Mapping[str, Any]) -> str:
    return str(provider_fields.get("call_to_action") or NO_CALL_TO_ACTION).strip().lower()


def validate_artifact(
    *,
    provider_fields: Mapping[str, Any],
    body: str,
    hashtags,
    link: str,
    image_url: str,
) -> None:
    """Travas puras do post; valem na prévia, na aprovação e ao reler o selado."""

    publication_format = str(provider_fields.get("publication_format") or "").strip().lower()
    text = summary(body, hashtags)
    if len(text) > SUMMARY_MAX_CHARS:
        _reject(
            "google_summary_too_long",
            f"O Google aceita até {SUMMARY_MAX_CHARS} caracteres no texto do post "
            f"(este tem {len(text)}, contando as hashtags).",
            "content.body",
            f"Corte {len(text) - SUMMARY_MAX_CHARS} caracteres.",
        )
    if _PHONE.search(text):
        _reject(
            "google_summary_has_phone",
            "O Google pode recusar post com telefone no texto. O telefone do perfil já "
            "aparece para o cliente; para ele ligar, use o botão “Ligar agora”.",
            "content.body",
            "Tire o telefone do texto.",
        )
    photo_format = photo_format_from_url(image_url)
    if photo_format and photo_format not in PHOTO_FORMATS:
        _reject(
            "google_media_format_unsupported",
            f"O Google só aceita foto JPEG ou PNG, e esta imagem é {photo_format.upper()}.",
            "content.image_url",
            "Escolha uma imagem JPEG ou PNG.",
        )

    action = call_to_action(provider_fields)
    if action not in CALL_TO_ACTION_REFS:
        _reject(
            "google_call_to_action_invalid",
            "Esse botão não existe no Google.",
            "platform_content.google_business.call_to_action",
            "Escolha um dos botões da lista, ou Nenhum.",
        )
    if action != NO_CALL_TO_ACTION and action not in _WITHOUT_URL:
        path = _link_path(link)
        if not path:
            _reject(
                "google_call_to_action_link_required",
                "Esse botão leva o cliente a um link, e este anúncio não tem link.",
                "platform_content.google_business.call_to_action",
                "Escolha “Ligar agora” ou Nenhum, ou use um modelo com link.",
            )
        if action in _PURCHASE and not _PRODUCT_OR_OFFER_PATH.fullmatch(path):
            _reject(
                "google_call_to_action_link_not_purchase",
                "“Pedir on-line” e “Comprar” só levam a um produto ou a uma oferta da loja.",
                "platform_content.google_business.call_to_action",
                "Use “Saiba mais”, ou um link de produto ou oferta.",
            )

    if publication_format == "event":
        title = str(provider_fields.get("event_title") or "").strip()
        if not title:
            _reject(
                "google_event_title_required",
                "Evento no Google precisa de título.",
                "platform_content.google_business.event_title",
                "Dê um nome ao evento.",
            )
        start = _local_datetime(provider_fields.get("event_start"), field="event_start")
        end = _local_datetime(provider_fields.get("event_end"), field="event_end")
        if end <= start:
            _reject(
                "google_event_period_invalid",
                "O evento termina antes de começar.",
                "platform_content.google_business.event_end",
                "Escolha um fim depois do início.",
            )
    if publication_format == "offer":
        if not str(provider_fields.get("offer_title") or "").strip():
            _offer_without_promotion()
        start = _local_datetime(provider_fields.get("offer_start"), field="offer_start")
        end = _local_datetime(provider_fields.get("offer_end"), field="offer_end")
        if end <= start:
            _offer_without_promotion()
        if not _OFFER_PATH.fullmatch(_link_path(link)):
            _reject(
                "google_offer_link_required",
                "Oferta no Google leva o cliente à página da oferta, e este anúncio não "
                "tem esse link.",
                "platform_content.google_business.publication_format",
                "Use um modelo com [Link] numa campanha com oferta, ou escolha Atualização.",
            )


def prepare_platform_content(
    platform_content: Mapping[str, Any],
    *,
    facts: Mapping[str, Any] | None,
    image_url: str,
    timezone_name: str,
    now: datetime,
) -> dict[str, Any]:
    """Sela a oferta a partir da promoção e confere o que depende do mundo.

    Roda na prévia e na aprovação. A oferta não tem cadastro paralelo: título e
    período vêm da ``Promotion`` da campanha, gravada nos fatos. Cupom não existe
    aqui porque promoção com cupom não pode ser anunciada pelo Marketing
    (``marketing_promotion_requires_coupon``). O que o operador mandar nesses campos
    é sobrescrito — a oferta anunciada é a da loja, não a digitada.
    """

    variants = {key: dict(value) for key, value in platform_content.items()}
    variant = variants.get(PLATFORM)
    if variant is None:
        return variants
    publication_format = str(variant.get("publication_format") or "").strip().lower()
    zone = ZoneInfo(timezone_name)
    if publication_format == "offer":
        promotion = dict((facts or {}).get("promotion") or {})
        if not promotion.get("name") or not promotion.get("valid_until"):
            _offer_without_promotion()
        valid_from = datetime.fromisoformat(str(promotion["valid_from"]))
        valid_until = datetime.fromisoformat(str(promotion["valid_until"]))
        variant["offer_title"] = str(promotion["name"]).strip()
        variant["offer_start"] = _as_local(max(valid_from, now), zone)
        variant["offer_end"] = _as_local(valid_until, zone)
    else:
        for key in ("offer_title", "offer_start", "offer_end", "offer_terms"):
            variant.pop(key, None)
    if publication_format == "event":
        end_raw = str(variant.get("event_end") or "")
        if _LOCAL_DATETIME.fullmatch(end_raw):
            end = datetime.fromisoformat(end_raw).replace(tzinfo=zone)
            if end <= now:
                _reject(
                    "google_event_already_ended",
                    "Esse evento já terminou.",
                    "platform_content.google_business.event_end",
                    "Escolha um fim no futuro.",
                )
    effective_image = str(variant.get("image_url") or image_url or "").strip()
    if effective_image:
        from shopman.shop.services import marketing_media_probe

        marketing_media_probe.check_google_photo(
            effective_image,
            field=(
                "platform_content.google_business.image_url"
                if variant.get("image_url")
                else "content.image_url"
            ),
        )
    variants[PLATFORM] = variant
    return variants


#: O que a revisão escolhe no post. Título e período da oferta ficam de fora: vêm da
#: promoção da campanha, selados por ``prepare_platform_content``.
REVIEW_OPTION_KEYS = frozenset({
    "publication_format",
    "call_to_action",
    "event_title",
    "event_start",
    "event_end",
    "offer_terms",
})


def with_review_options(
    platform_content: Mapping[str, Any], options: Mapping[str, str]
) -> dict[str, Any]:
    """A escolha da revisão substitui as opções do modelo; campo vazio sai.

    Um caminho só para a prévia da revisão e para a aprovação: a prévia não pode
    montar o post de um jeito e a aprovação de outro.
    """

    merged = dict(platform_content)
    variant = {
        key: value
        for key, value in dict(merged.get(PLATFORM) or {}).items()
        if key not in REVIEW_OPTION_KEYS
    }
    variant.update({key: value for key, value in options.items() if value})
    merged[PLATFORM] = variant
    return merged


def request_payload(artifact) -> dict[str, Any]:
    """O corpo do ``localPosts.create`` — só a partir do artefato aprovado."""

    fields = dict(artifact.provider_fields)
    publication_format = str(fields.get("publication_format") or "")
    payload: dict[str, Any] = {
        "languageCode": "pt-BR",
        "summary": summary(artifact.body, artifact.hashtags),
        "topicType": TOPIC_TYPES[publication_format],
    }
    action = call_to_action(fields)
    if action != NO_CALL_TO_ACTION:
        cta: dict[str, str] = {"actionType": CALL_TO_ACTIONS[action]}
        if action not in _WITHOUT_URL:
            cta["url"] = artifact.link
        payload["callToAction"] = cta
    if publication_format == "event":
        payload["event"] = {
            "title": str(fields["event_title"]).strip(),
            "schedule": _schedule(fields["event_start"], fields["event_end"]),
        }
    if publication_format == "offer":
        payload["event"] = {
            "title": str(fields["offer_title"]).strip(),
            "schedule": _schedule(fields["offer_start"], fields["offer_end"]),
        }
        offer: dict[str, str] = {"redeemOnlineUrl": artifact.link}
        terms = str(fields.get("offer_terms") or "").strip()
        if terms:
            offer["termsConditions"] = terms
        payload["offer"] = offer
    if artifact.image_url:
        payload["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": artifact.image_url}]
    return payload


def photo_format_from_url(value: str) -> str:
    """Formato declarado pela URL (``fm=`` ou extensão); vazio quando não diz."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    for key, item in parse_qsl(parsed.query):
        if key == "fm" and item:
            return _KNOWN_EXTENSIONS.get(item.lower(), item.lower())
    name = parsed.path.rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return _KNOWN_EXTENSIONS.get(name.rsplit(".", 1)[-1].lower(), "")


def _schedule(start: str, end: str) -> dict[str, Any]:
    first = datetime.fromisoformat(str(start))
    last = datetime.fromisoformat(str(end))
    return {
        "startDate": {"year": first.year, "month": first.month, "day": first.day},
        "startTime": {"hours": first.hour, "minutes": first.minute},
        "endDate": {"year": last.year, "month": last.month, "day": last.day},
        "endTime": {"hours": last.hour, "minutes": last.minute},
    }


def _as_local(value: datetime, zone: ZoneInfo) -> str:
    return value.astimezone(zone).strftime("%Y-%m-%dT%H:%M")


def _local_datetime(value: object, *, field: str) -> datetime:
    raw = str(value or "").strip()
    try:
        if not _LOCAL_DATETIME.fullmatch(raw):
            raise ValueError(raw)
        return datetime.fromisoformat(raw)
    except ValueError:
        _reject(
            "google_post_datetime_invalid",
            "Data e hora do post no Google estão incompletas.",
            f"platform_content.google_business.{field}",
            "Escolha a data e a hora.",
        )
        raise  # pragma: no cover - _reject sempre levanta


def _link_path(link: str) -> str:
    raw = str(link or "").strip()
    if not raw:
        return ""
    try:
        return urlsplit(raw).path
    except ValueError:
        return ""


def _offer_without_promotion() -> None:
    _reject(
        "google_offer_promotion_required",
        "Oferta no Google nasce de uma promoção vigente da campanha, e esta campanha "
        "não anuncia promoção.",
        "platform_content.google_business.publication_format",
        "Escolha a promoção na campanha, ou publique como Atualização.",
    )


def _reject(code: str, detail: str, field: str, message: str) -> None:
    raise MarketingContractError(
        code=code,
        detail=detail,
        field_errors={field: (message,)},
    )
