"""Audience adapter — encapsula o acesso às fontes de audiência do storefront.

Mesmo papel do ``adapters/promotion.py``: os favoritos e as assinaturas de
alerta são models do storefront, e ``shop/services/`` não importa superfície
direto (ADR-001). O adapter é a única porta.

Devolve dados crus (refs, telefones) — quem decide quem recebe é o
``services/audience.py``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ActiveAlertSubscription:
    ref: object
    contact_phone: str


def favorite_customer_refs(sku: str) -> list[str]:
    """Refs de clientes que favoritaram este SKU."""
    from shopman.storefront.models import CustomerFavorite

    return list(
        CustomerFavorite.objects.filter(sku=sku)
        .values_list("customer_ref", flat=True)
        .distinct()
    )


def pending_alert_count(sku: str) -> int:
    """Quantas pessoas estão na fila de "me avise" deste SKU, ainda não avisadas.

    É a contagem por trás do badge "X pessoas querem" (F16): o número conta
    exatamente a fila em que o botão "Me avise" convida a entrar. Contar
    intenção de outra fonte (ex.: demand holds) faria a copy prometer uma fila
    e mostrar outra.

    Dedupe por telefone: a mesma pessoa pode assinar os dois gatilhos
    (``stock_back`` e ``production_ready``) do mesmo produto, e ela é UMA
    pessoa querendo, não duas.
    """
    from shopman.storefront.models import StockAlertSubscription

    return (
        StockAlertSubscription.objects.active().filter(sku=sku)
        .values("contact_phone")
        .distinct()
        .count()
    )


def pending_alert_contacts(sku: str) -> list[tuple[str, str, object]]:
    """``(telefone, customer_ref, ref)`` de cada assinatura pendente deste SKU.

    Inclui os dois gatilhos (``stock_back`` e ``production_ready``): quem pediu
    para ser avisado sobre o produto quer saber, seja qual for o motivo.
    """
    from shopman.storefront.models import StockAlertSubscription

    return list(
        StockAlertSubscription.objects.active()
        .filter(sku=sku)
        .values_list("contact_phone", "customer_ref", "ref")
    )


def active_alert_subscriptions(
    refs: Iterable[object], *, now: datetime
) -> tuple[ActiveAlertSubscription, ...]:
    """Minimal late-bound contact facts for protected snapshot members."""

    from shopman.storefront.models import StockAlertSubscription

    rows = (
        StockAlertSubscription.objects.active(now=now)
        .filter(ref__in=tuple(refs))
        .values_list("ref", "contact_phone")
    )
    return tuple(
        ActiveAlertSubscription(ref=ref, contact_phone=phone)
        for ref, phone in rows
    )


def active_alert_subscription_refs(
    refs: Iterable[object], *, now: datetime
) -> set[object]:
    """Active refs only, without returning a storefront model into the core."""

    from shopman.storefront.models import StockAlertSubscription

    return set(
        StockAlertSubscription.objects.active(now=now)
        .filter(ref__in=tuple(refs))
        .values_list("ref", flat=True)
    )
