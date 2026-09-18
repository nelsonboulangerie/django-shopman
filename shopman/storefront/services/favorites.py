"""Customer favorites service — add/remove/toggle/list (per customer).

Favorites is the customer-scoped dynamic collection ("Seus favoritos"). Resolved
on the account axis (not the global channel registry). Surfaces compose catalog
cards from ``skus_for()`` via the catalog presentation.

Favoritar um produto esgotado de verdade, com opt-in de WhatsApp e maioridade
provada, também anota o aviso do "Me avise" (:func:`add_noting_stock_alert`).
Desfavoritar nunca cancela aviso.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def add(customer_ref: str, sku: str) -> bool:
    """Mark a SKU as favorite. Idempotent. Returns True (is favorite)."""
    from django.db import transaction

    from shopman.shop.services import account as account_service
    from shopman.storefront.models import CustomerFavorite

    if not customer_ref or not sku:
        return False
    with transaction.atomic():
        locked = account_service.lock_active_customer(customer_ref=customer_ref)
        CustomerFavorite.objects.get_or_create(customer_ref=locked.ref, sku=sku)
    return True


def remove(customer_ref: str, sku: str) -> bool:
    """Unfavorite a SKU. Idempotent. Returns False (not favorite).

    Desfavoritar NÃO cancela o aviso que o favorito anotou: são intenções
    separadas, e o aviso tem gestão própria em Conta › Preferências.
    """
    from django.db import transaction

    from shopman.shop.services import account as account_service
    from shopman.storefront.models import CustomerFavorite

    if customer_ref and sku:
        with transaction.atomic():
            locked = account_service.lock_active_customer(customer_ref=customer_ref)
            CustomerFavorite.objects.filter(customer_ref=locked.ref, sku=sku).delete()
    return False


def toggle(customer_ref: str, sku: str) -> bool:
    """Flip favorite state. Returns the new state (True = now favorite)."""
    from django.db import transaction

    from shopman.shop.services import account as account_service
    from shopman.storefront.models import CustomerFavorite

    if not customer_ref or not sku:
        return False
    with transaction.atomic():
        locked = account_service.lock_active_customer(customer_ref=customer_ref)
        existing = CustomerFavorite.objects.filter(customer_ref=locked.ref, sku=sku).first()
        if existing:
            existing.delete()
            return False
        CustomerFavorite.objects.create(customer_ref=locked.ref, sku=sku)
        return True


def skus_for(customer_ref: str) -> list[str]:
    """Favorite SKUs for a customer, most-recent first."""
    from shopman.storefront.models import CustomerFavorite

    if not customer_ref:
        return []
    return list(
        CustomerFavorite.objects.filter(customer_ref=customer_ref).values_list("sku", flat=True)
    )


def favorite_sku_set(customer_ref: str) -> set[str]:
    """Set form for cheap membership checks (heart state on cards/PDP)."""
    return set(skus_for(customer_ref))


# ── Favoritar um esgotado anota o aviso (decisão do Pablo, 17/09) ────────────

#: Base registrada na inscrição que nasce do favorito. Não é um texto que a
#: pessoa leu nesta hora — é a descrição honesta do que a autoriza: o gesto de
#: favoritar um produto esgotado, somado ao opt-in de WhatsApp e à maioridade
#: que ela já tinha provado na conta. Mudou a frase, sobe a versão.
FAVORITE_STOCK_ALERT_BASIS_VERSION = "favorite-sold-out-whatsapp-opt-in-pt-BR-v1"
FAVORITE_STOCK_ALERT_BASIS = (
    "Favoritou este produto enquanto estava esgotado, com consentimento de "
    "WhatsApp ativo e maioridade confirmada na conta. O aviso continua ativo "
    "até pausar ou cancelar."
)


@dataclass(frozen=True)
class FavoriteOutcome:
    """O que a tela precisa saber depois do coração.

    ``is_notify_subscribed`` é o estado do sino DEPOIS do gesto (a mesma leitura
    da projeção); ``stock_alert_noted`` diz se ESTE favorito criou o aviso — só
    ele justifica contar ao cliente que vamos avisar.
    """

    is_favorite: bool
    is_notify_subscribed: bool
    stock_alert_noted: bool = False


def add_noting_stock_alert(
    customer,
    sku: str,
    *,
    channel_ref: str = "",
    session_key: str = "",
) -> FavoriteOutcome:
    """Favorita e, se o produto está esgotado de verdade, anota o aviso.

    Regras (Pablo, 17/09):

    1. Produto notificável (a MESMA régua do sino no card) + opt-in de WhatsApp
       verificado + maioridade provada → cria a inscrição do "Me avise".
    2. Sem consentimento ou sem prova de maioridade → só favorito; o card segue
       oferecendo "Me avise", que carrega o próprio opt-in.
    3. Desfavoritar não cancela aviso (ver :func:`remove`).
    4. Inscrição que já existiu para este SKU — ativa, pausada ou cancelada —
       NÃO é criada de novo nem retomada pelo favorito: a escolha dele manda.

    O favorito nunca quebra por causa do aviso: ele é salvo (e confirmado)
    antes, e toda falha do aviso termina em "sem inscrição", relatada.
    """
    from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

    channel_ref = channel_ref or STOREFRONT_CHANNEL_REF
    customer_ref = (getattr(customer, "ref", "") or "").strip()
    is_favorite = add(customer_ref, sku)
    noted = False
    if is_favorite:
        noted = _note_stock_alert(
            customer_ref, sku, channel_ref=channel_ref, session_key=session_key
        )
    return FavoriteOutcome(
        is_favorite=is_favorite,
        is_notify_subscribed=notify_subscribed(customer, sku),
        stock_alert_noted=noted,
    )


def notify_subscribed(customer, sku: str) -> bool:
    """Estado do sino para este cliente, pela mesma leitura da projeção."""
    from shopman.storefront.services import stock_alerts

    if customer is None or not sku:
        return False
    return sku in stock_alerts.subscribed_skus(customer=customer)


def _note_stock_alert(customer_ref: str, sku: str, *, channel_ref: str, session_key: str) -> bool:
    from django.db import transaction

    from shopman.shop.services import account as account_service
    from shopman.shop.services.communication_consent import customer_is_opted_in
    from shopman.shop.services.marketing_age import is_proved_adult
    from shopman.storefront.presentation.catalog import notifiable_skus
    from shopman.storefront.services import stock_alerts

    try:
        if sku not in notifiable_skus([sku], channel_ref=channel_ref, session_key=session_key):
            return False
    except Exception:
        # Sem a régua da disponibilidade não há como saber se o sino seria
        # oferecido: falha fechada (sem inscrição) e o favorito já está salvo.
        logger.warning(
            "favorites.stock_alert_skipped reason=availability_unreadable sku=%s",
            sku,
            exc_info=True,
        )
        return False

    try:
        with transaction.atomic():
            customer = account_service.lock_active_customer(customer_ref=customer_ref)
            if not is_proved_adult(customer.birthday, customer.metadata):
                return False
            # Falha de leitura já é relatada (e vira False) em customer_is_opted_in.
            if not customer_is_opted_in(customer.ref, "whatsapp"):
                return False
            if _had_stock_alert(customer, sku):
                return False
            outcome = stock_alerts.subscribe_with_outcome(
                sku,
                channel_ref=channel_ref,
                customer=customer,
                disclosure_text=FAVORITE_STOCK_ALERT_BASIS,
                disclosure_version=FAVORITE_STOCK_ALERT_BASIS_VERSION,
                adult_declared=True,
                resume_existing=False,
            )
            return outcome.created
    except account_service.AccountUnavailable:
        # silêncio-deliberado: a exclusão da conta venceu a corrida; não há
        # titular para anotar aviso, e o favorito já não existe para ninguém.
        return False
    except Exception:
        logger.warning(
            "favorites.stock_alert_skipped reason=subscribe_failed sku=%s",
            sku,
            exc_info=True,
        )
        return False


def _had_stock_alert(customer, sku: str) -> bool:
    """Já houve inscrição deste titular para o SKU, em QUALQUER estado?

    Ativa: nada a fazer. Pausada ou cancelada: foi escolha dele, e o favorito
    não a desfaz. Mesma noção de titular de ``active_subscription_for_sku_owner``:
    a conta, ou uma linha antiga só com o telefone dela.
    """
    from django.db.models import Q
    from shopman.utils.phone import normalize_user_phone

    from shopman.storefront.models import StockAlertSubscription

    owner = Q(customer_ref=customer.ref)
    contact = normalize_user_phone(getattr(customer, "phone", "") or "")
    if contact:
        owner |= Q(customer_ref="", contact_phone=contact)
    return StockAlertSubscription.objects.filter(
        owner, sku=sku, purpose="stock_availability"
    ).exists()

