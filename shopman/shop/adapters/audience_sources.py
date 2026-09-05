"""Audience adapter — encapsula o acesso às fontes de audiência do storefront.

Mesmo papel do ``adapters/promotion.py``: os favoritos e as assinaturas de
alerta são models do storefront, e ``shop/services/`` não importa superfície
direto (ADR-001). O adapter é a única porta.

Devolve dados crus (refs, telefones) — quem decide quem recebe é o
``services/audience.py``.
"""

from __future__ import annotations


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
        StockAlertSubscription.objects.filter(sku=sku, notified_at__isnull=True)
        .values("contact_phone")
        .distinct()
        .count()
    )


def notified_alert_count(sku: str) -> int:
    """Quantas pessoas pediram aviso deste SKU e JÁ foram avisadas.

    Existe para o zero da tela do Marketing poder falar. "Ninguém para avisar"
    tem duas causas que na tela pareciam a mesma: ninguém pediu, ou pediram e a
    fila já foi servida. Foi exatamente o segundo caso que apareceu como bug —
    a inscrição existia, o estoque voltou 7 minutos depois, o aviso saiu, e o
    público virou zero sem nada explicar por quê.

    Dedupe por telefone, igual ao ``pending_alert_count``: é gente, não linha.
    """
    from shopman.storefront.models import StockAlertSubscription

    return (
        StockAlertSubscription.objects.filter(sku=sku, notified_at__isnull=False)
        .values("contact_phone")
        .distinct()
        .count()
    )


def pending_alert_contacts(sku: str) -> list[tuple[str, str]]:
    """``(telefone, customer_ref)`` de cada assinatura pendente deste SKU.

    Inclui os dois gatilhos (``stock_back`` e ``production_ready``): quem pediu
    para ser avisado sobre o produto quer saber, seja qual for o motivo.
    """
    from shopman.storefront.models import StockAlertSubscription

    return list(
        StockAlertSubscription.objects.filter(
            sku=sku, notified_at__isnull=True
        ).values_list("contact_phone", "customer_ref")
    )
