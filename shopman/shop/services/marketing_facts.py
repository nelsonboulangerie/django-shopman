"""Canonical, content-addressed facts used by Marketing content.

Campaign owns neither catalog, price, availability, promotion nor storefront
links.  This module reads each owner and seals only the facts used by content so
approval and dispatch can prove the message is still true without re-rendering it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from shopman.shop.services.marketing_contracts import MarketingContractError

SCHEMA_VERSION = 1
CHANNEL_REF = "web"
FRESHNESS_TTL = timedelta(minutes=5)
_PLACEHOLDER = re.compile(r"\{\{\s*([\w_]+)\s*\}\}")
_FACT_VARIABLES = frozenset({
    "available_qty",
    "availability_phrase",
    "link",
    "price",
    "product_image_url",
    "product_name",
    "product_sku",
})
_AVAILABILITY_VARIABLES = frozenset({"available_qty", "availability_phrase"})
_PRODUCT_REQUIRED_VARIABLES = _FACT_VARIABLES - {"link"}


@dataclass(frozen=True, slots=True)
class MarketingFactSnapshot:
    as_of: datetime
    fresh_until: datetime
    source_hash: str
    sku: str
    promotion_ref: str
    referenced_variables: tuple[str, ...]
    variables: tuple[tuple[str, str], ...]
    product: tuple[tuple[str, Any], ...] = ()
    price: tuple[tuple[str, Any], ...] = ()
    availability: tuple[tuple[str, Any], ...] = ()
    promotion: tuple[tuple[str, Any], ...] = ()
    link: tuple[tuple[str, Any], ...] = ()

    def variable_values(self) -> dict[str, str]:
        return dict(self.variables)

    def source_payload(self) -> dict[str, Any]:
        return {
            "availability": dict(self.availability),
            "channel_ref": CHANNEL_REF,
            "link": dict(self.link),
            "price": dict(self.price),
            "product": dict(self.product),
            "promotion": dict(self.promotion),
            "promotion_ref": self.promotion_ref,
            "referenced_variables": list(self.referenced_variables),
            "sku": self.sku,
            "variables": dict(self.variables),
        }

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "as_of": self.as_of.isoformat(),
            "fresh_until": self.fresh_until.isoformat(),
            "source_hash": self.source_hash,
            **self.source_payload(),
        }


def referenced_variables(*values: object) -> tuple[str, ...]:
    """Return the stable set of template variables found in strings/lists/maps."""

    found: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, str):
            found.update(match.group(1).strip() for match in _PLACEHOLDER.finditer(value))
        elif isinstance(value, Mapping):
            for nested in value.values():
                visit(nested)
        elif isinstance(value, Sequence) and not isinstance(value, bytes):
            for nested in value:
                visit(nested)

    for value in values:
        visit(value)
    return tuple(sorted(found))


def requires_product(referenced: Sequence[str]) -> bool:
    """Return whether these canonical variables require a product occurrence."""

    return bool({str(value).strip() for value in referenced} & _PRODUCT_REQUIRED_VARIABLES)


def resolve_facts(
    *,
    sku: str,
    promotion_ref: str = "",
    referenced: Sequence[str] = (),
    seed_variables: Mapping[str, Any] | None = None,
    scheduled_for: datetime | None = None,
    now: datetime | None = None,
) -> MarketingFactSnapshot:
    """Read current facts from their owners and validate schedule validity."""

    clock = _aware(now or timezone.now(), field="as_of")
    schedule = _aware(scheduled_for, field="publish_at") if scheduled_for else None
    safe_sku = str(sku or "").strip()
    safe_promotion_ref = str(promotion_ref or "").strip()
    refs = tuple(sorted({str(value).strip() for value in referenced if str(value).strip()}))
    seeds = {str(key): str(value or "") for key, value in (seed_variables or {}).items()}
    product = _product(
        safe_sku,
        required=requires_product(refs),
    )
    promotion = _promotion(
        safe_promotion_ref,
        sku=safe_sku,
        scheduled_for=schedule,
        now=clock,
    )

    product_payload: dict[str, Any] = {}
    if product is not None:
        product_payload = {
            "is_published": bool(product.is_published),
            "is_sellable": bool(product.is_sellable),
            "name": str(product.name or ""),
            "sku": str(product.sku),
        }
        if not product_payload["is_published"] or not product_payload["is_sellable"]:
            raise MarketingContractError(
                code="marketing_product_unavailable",
                detail="O produto do anúncio não está publicável e vendável.",
                field_errors={"content.facts.product": ("Atualize o produto antes de publicar.",)},
            )

    price_payload: dict[str, Any] = {}
    if "price" in refs:
        price_payload = _price(product, promotion=promotion)

    availability_payload: dict[str, Any] = {}
    if set(refs) & _AVAILABILITY_VARIABLES:
        availability_payload = _availability(product)

    link_payload = _link(safe_sku, safe_promotion_ref, required="link" in refs)
    promotion_payload = _promotion_payload(promotion)
    variables = dict(seeds)
    if product is not None:
        variables.update({
            "product_name": str(product.name or product.sku),
            "product_sku": str(product.sku),
            "product_image_url": _product_image_url(product),
        })
    if price_payload:
        variables["price"] = price_payload["display"]
    if availability_payload:
        from shopman.shop.services.availability_copy import availability_phrase

        qty = availability_payload.get("available_qty")
        variables["available_qty"] = "" if qty is None else str(qty)
        variables["availability_phrase"] = availability_phrase(qty)
    if link_payload:
        variables["link"] = str(link_payload["url"])

    used_variables = tuple(sorted(
        (name, variables[name]) for name in refs if name in variables
    ))
    used = dict(used_variables)
    missing = [name for name in refs if name in _FACT_VARIABLES and not used.get(name)]
    if missing:
        raise MarketingContractError(
            code="marketing_fact_missing",
            detail="Falta um fato necessário para renderizar o conteúdo.",
            field_errors={
                "content.facts": (f"Sem valor canônico para: {', '.join(missing)}.",)
            },
        )

    fresh_until = clock + FRESHNESS_TTL
    if promotion is not None:
        fresh_until = min(fresh_until, promotion.valid_until)
    source = {
        "availability": availability_payload,
        "channel_ref": CHANNEL_REF,
        "link": link_payload,
        "price": price_payload,
        "product": product_payload,
        "promotion": promotion_payload,
        "promotion_ref": safe_promotion_ref,
        "referenced_variables": list(refs),
        "sku": safe_sku,
        "variables": dict(used_variables),
    }
    return MarketingFactSnapshot(
        as_of=clock,
        fresh_until=fresh_until,
        source_hash=_hash(source),
        sku=safe_sku,
        promotion_ref=safe_promotion_ref,
        referenced_variables=refs,
        variables=used_variables,
        product=tuple(sorted(product_payload.items())),
        price=tuple(sorted(price_payload.items())),
        availability=tuple(sorted(availability_payload.items())),
        promotion=tuple(sorted(promotion_payload.items())),
        link=tuple(sorted(link_payload.items())),
    )


def refresh_for_approval(
    announcement,
    content: Mapping[str, Any],
    *,
    scheduled_for: datetime | None,
    now: datetime,
) -> MarketingFactSnapshot | None:
    """Revalidate every approved factual value without changing reviewed bytes."""

    raw = content.get("facts")
    promotion_ref = str(
        getattr(getattr(announcement, "rule", None), "promotion_ref", "") or ""
    )
    if raw is None:
        if promotion_ref:
            raise MarketingContractError(
                code="marketing_facts_unverified",
                detail="A oferta precisa ser atualizada antes da aprovação.",
                field_errors={"content.facts": ("Atualize a prévia desta oferta.",)},
            )
        return None

    stored = from_payload(raw)
    expected_sku = str((announcement.trigger_context or {}).get("sku") or "")
    if stored.sku != expected_sku or stored.promotion_ref != promotion_ref:
        raise MarketingContractError(
            code="marketing_facts_context_mismatch",
            detail="Os fatos não pertencem ao anúncio em revisão.",
            field_errors={"content.facts": ("Atualize a prévia antes de aprovar.",)},
        )
    persisted = (announcement.content or {}).get("facts")
    if persisted is not None and persisted != raw:
        raise MarketingContractError(
            code="marketing_facts_tampered",
            detail="Os fatos recebidos divergem do rascunho salvo.",
            field_errors={"content.facts": ("Reabra a versão atual do anúncio.",)},
        )
    # Expiry means "read the canonical owners again", not "reject regardless".
    # Keep the sealed snapshot after an equal read so the confirmation challenge
    # remains bound to the exact bytes reviewed by the operator.  The command
    # timestamp proves this revalidation and dispatch performs the same guard again.
    current = resolve_facts(
        sku=stored.sku,
        promotion_ref=stored.promotion_ref,
        referenced=stored.referenced_variables,
        seed_variables=stored.variable_values(),
        scheduled_for=scheduled_for,
        now=now,
    )
    if current.source_hash != stored.source_hash:
        raise MarketingContractError(
            code="marketing_facts_changed",
            detail="Preço, disponibilidade, produto, oferta ou link mudou durante a revisão.",
            field_errors={"content.facts": ("Atualize a prévia e revise novamente.",)},
        )
    return stored


def validate_for_dispatch(artifact, *, now: datetime | None = None) -> None:
    """Fail before the provider when a new artifact's factual claim drifted."""

    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
    raw = payload.get("facts")
    if raw is None:
        return  # Explicit compatibility window for pre-MKT-027 approvals.
    stored = from_payload(raw)
    current = resolve_facts(
        sku=stored.sku,
        promotion_ref=stored.promotion_ref,
        referenced=stored.referenced_variables,
        seed_variables=stored.variable_values(),
        now=now,
    )
    if current.source_hash != stored.source_hash:
        raise MarketingContractError(
            code="marketing_facts_changed_before_send",
            detail="Os fatos aprovados mudaram antes do envio.",
        )


def from_payload(value: object) -> MarketingFactSnapshot:
    if not isinstance(value, Mapping):
        raise MarketingContractError(
            code="invalid_marketing_facts",
            detail="O snapshot factual é inválido.",
        )
    payload = dict(value)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise MarketingContractError(
            code="unsupported_marketing_facts",
            detail="A versão do snapshot factual não é suportada.",
        )
    try:
        snapshot = MarketingFactSnapshot(
            as_of=_parse_datetime(payload.get("as_of"), field="facts.as_of"),
            fresh_until=_parse_datetime(
                payload.get("fresh_until"), field="facts.fresh_until"
            ),
            source_hash=str(payload.get("source_hash") or ""),
            sku=str(payload.get("sku") or ""),
            promotion_ref=str(payload.get("promotion_ref") or ""),
            referenced_variables=tuple(_strings(payload.get("referenced_variables"))),
            variables=tuple(sorted(_mapping(payload.get("variables"), "facts.variables").items())),
            product=tuple(sorted(_mapping(payload.get("product"), "facts.product").items())),
            price=tuple(sorted(_mapping(payload.get("price"), "facts.price").items())),
            availability=tuple(
                sorted(_mapping(payload.get("availability"), "facts.availability").items())
            ),
            promotion=tuple(
                sorted(_mapping(payload.get("promotion"), "facts.promotion").items())
            ),
            link=tuple(sorted(_mapping(payload.get("link"), "facts.link").items())),
        )
    except (TypeError, ValueError) as exc:
        raise MarketingContractError(
            code="invalid_marketing_facts",
            detail="O snapshot factual contém valores inválidos.",
        ) from exc
    if snapshot.source_hash != _hash(snapshot.source_payload()):
        raise MarketingContractError(
            code="marketing_facts_hash_mismatch",
            detail="O snapshot factual diverge do próprio hash.",
        )
    if (
        snapshot.fresh_until < snapshot.as_of
        or snapshot.fresh_until > snapshot.as_of + FRESHNESS_TTL
    ):
        raise MarketingContractError(
            code="invalid_marketing_facts_freshness",
            detail="A janela de frescor do snapshot factual é inválida.",
        )
    return snapshot


def _product(sku: str, *, required: bool):
    if not required:
        return None
    if not sku:
        raise MarketingContractError(
            code="marketing_product_required",
            detail="O conteúdo exige um produto, mas nenhum SKU foi informado.",
            field_errors={"sku": ("Escolha um produto para a prévia.",)},
        )
    try:
        from shopman.shop.projections import catalog_context

        product = catalog_context.get_product(sku)
    except Exception as exc:
        raise MarketingContractError(
            code="marketing_facts_unavailable",
            detail="Não foi possível conferir o produto agora.",
            retryable=True,
        ) from exc
    if product is None:
        raise MarketingContractError(
            code="marketing_product_not_found",
            detail="O produto do anúncio não existe mais.",
            field_errors={"sku": ("Escolha um produto existente.",)},
        )
    return product


def _promotion(ref: str, *, sku: str, scheduled_for: datetime | None, now: datetime):
    if not ref:
        return None
    try:
        from shopman.shop.services import offers

        promotion = offers.get_offer(ref, channel_ref=CHANNEL_REF, now=now)
    except offers.OfferUnavailable as exc:
        raise MarketingContractError(
            code="marketing_promotion_unavailable",
            detail="A oferta não está vigente no canal da loja.",
            field_errors={"promotion_ref": ("Escolha uma oferta vigente para web.",)},
        ) from exc
    except Exception as exc:
        raise MarketingContractError(
            code="marketing_facts_unavailable",
            detail="Não foi possível conferir a oferta agora.",
            retryable=True,
        ) from exc
    if now >= promotion.valid_until:
        raise MarketingContractError(
            code="marketing_promotion_unavailable",
            detail="A oferta não está mais vigente no canal da loja.",
            field_errors={"promotion_ref": ("Escolha uma oferta vigente para web.",)},
        )
    if promotion.coupons.exists():
        raise MarketingContractError(
            code="marketing_promotion_requires_coupon",
            detail="Uma oferta anunciada não pode depender de cupom oculto.",
            field_errors={"promotion_ref": ("Use uma promoção automática.",)},
        )
    if promotion.customer_segments or promotion.birthday_only:
        raise MarketingContractError(
            code="marketing_promotion_has_private_eligibility",
            detail="A oferta depende de uma condição individual não visível no anúncio.",
            field_errors={"promotion_ref": ("Use uma oferta pública para esta campanha.",)},
        )
    from shopman.shop.services.offers import offer_skus

    applicable = offer_skus(promotion)
    if sku and applicable and sku not in applicable:
        raise MarketingContractError(
            code="marketing_promotion_product_mismatch",
            detail="A oferta não alcança o produto do anúncio.",
            field_errors={"promotion_ref": ("Escolha uma oferta deste produto.",)},
        )
    if scheduled_for is not None and scheduled_for >= promotion.valid_until:
        raise MarketingContractError(
            code="marketing_schedule_outlives_promotion",
            detail="A oferta termina antes do horário agendado.",
            field_errors={"publish_at": ("Agende antes da validade ou troque a oferta.",)},
        )
    return promotion


def _price(product, *, promotion) -> dict[str, Any]:
    if product is None:
        raise MarketingContractError(
            code="marketing_product_required",
            detail="Preço exige um produto.",
        )
    try:
        from shopman.offerman.service import CatalogService
        from shopman.utils.monetary import format_money

        context = {"active_promotions": [promotion] if promotion is not None else []}
        quote = CatalogService.get_price(
            product.sku,
            qty=Decimal("1"),
            channel=CHANNEL_REF,
            context=context,
        )
    except Exception as exc:
        raise MarketingContractError(
            code="marketing_facts_unavailable",
            detail="Não foi possível conferir o preço agora.",
            retryable=True,
        ) from exc
    final_q = int(quote.final_unit_price_q)
    return {
        "currency": "BRL",
        "display": f"R$ {format_money(final_q)}",
        "final_unit_price_q": final_q,
        "list_unit_price_q": int(quote.list_unit_price_q),
    }


def _availability(product) -> dict[str, Any]:
    if product is None:
        raise MarketingContractError(
            code="marketing_product_required",
            detail="Disponibilidade exige um produto.",
        )
    try:
        from shopman.shop.projections import catalog_context

        raw = catalog_context.availability_for_sku(product.sku, channel_ref=CHANNEL_REF)
    except Exception as exc:
        raise MarketingContractError(
            code="marketing_facts_unavailable",
            detail="Não foi possível conferir a disponibilidade agora.",
            retryable=True,
        ) from exc
    if raw is None:
        raise MarketingContractError(
            code="marketing_facts_unavailable",
            detail="A fonte de disponibilidade não respondeu.",
            retryable=True,
        )
    policy = str(raw.get("availability_policy") or "planned_ok")
    qty = raw.get("total_promisable")
    normalized_qty = None if policy == "demand_ok" else int(Decimal(str(qty or 0)))
    if raw.get("is_paused") or (normalized_qty == 0 and not raw.get("is_planned")):
        raise MarketingContractError(
            code="marketing_product_unavailable",
            detail="O produto não está disponível para o anúncio.",
            field_errors={"content.facts.availability": ("Aguarde reposição ou ajuste o texto.",)},
        )
    return {
        "available_qty": normalized_qty,
        "is_planned": bool(raw.get("is_planned")),
        "policy": policy,
    }


def _link(sku: str, promotion_ref: str, *, required: bool) -> dict[str, Any]:
    if not sku and not promotion_ref:
        if required:
            raise MarketingContractError(
                code="marketing_link_target_required",
                detail="O conteúdo exige link, mas não há produto ou oferta.",
                field_errors={"content.link": ("Escolha um produto ou oferta.",)},
            )
        return {}
    from shopman.shop.services import storefront_links

    if promotion_ref:
        return {
            "kind": "offer",
            "ref": promotion_ref,
            "url": storefront_links.offer_url(promotion_ref),
        }
    return {
        "kind": "product",
        "ref": sku,
        "url": storefront_links.product_url(sku),
    }


def _promotion_payload(promotion) -> dict[str, Any]:
    if promotion is None:
        return {}
    return {
        "min_order_q": int(promotion.min_order_q),
        "name": str(promotion.name),
        "ref": str(promotion.ref),
        "type": str(promotion.type),
        "valid_from": promotion.valid_from.isoformat(),
        "valid_until": promotion.valid_until.isoformat(),
        "value": int(promotion.value),
    }


def _product_image_url(product) -> str:
    raw = str(getattr(product, "image_url", "") or "").strip()
    if not raw or raw.startswith(("http://", "https://")):
        return raw
    from shopman.shop.services import storefront_links

    base = storefront_links.storefront_base_url()
    return f"{base}/{raw.lstrip('/')}" if base else ""


def _hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MarketingContractError(
            code="invalid_marketing_facts",
            detail=f"{field} precisa ser um objeto.",
        )
    return dict(value)


def _strings(value: object) -> list[str]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise MarketingContractError(
            code="invalid_marketing_facts",
            detail="A lista de variáveis factuais é inválida.",
        )
    return sorted({str(item) for item in value})


def _parse_datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(field)
    return _aware(datetime.fromisoformat(value), field=field)


def _aware(value: datetime, *, field: str) -> datetime:
    if timezone.is_naive(value):
        raise MarketingContractError(
            code="invalid_marketing_facts_clock",
            detail=f"{field} precisa incluir timezone.",
            field_errors={field: ("Inclua o offset do horário.",)},
        )
    return value
