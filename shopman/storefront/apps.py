"""Django AppConfig for the Shopman storefront (customer-facing surface)."""

from __future__ import annotations

from django.apps import AppConfig


class StorefrontConfig(AppConfig):
    name = "shopman.storefront"
    label = "storefront"
    verbose_name = "Loja online"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Concierge de WhatsApp: o turno roda no worker de diretivas. O handler é
        # desta superfície (fala com o cliente), então é registrado daqui, não pelo
        # `shop.handlers` — o shop não importa superfície.
        from shopman.orderman import registry

        from shopman.storefront.concierge.handler import ConciergeTurnHandler

        registry.register_directive_handler(ConciergeTurnHandler())

        # Stock-back alerts: react to Stockman Move arrivals to notify waiters.
        from django.db.models.signals import post_save
        from shopman.stockman.models import Move

        from shopman.storefront.handlers import on_move_for_stock_alerts

        post_save.connect(
            on_move_for_stock_alerts,
            sender=Move,
            dispatch_uid="storefront.stock_alerts.on_move",
            weak=False,
        )

        # "Me avise quando sair do forno": o gatilho é a fornada, não a reposição.
        from shopman.craftsman.signals import production_changed

        from shopman.storefront.handlers import on_production_finished_for_stock_alerts

        production_changed.connect(
            on_production_finished_for_stock_alerts,
            dispatch_uid="storefront.stock_alerts.on_production_finished",
            weak=False,
        )

        # Exclusão de conta (LGPD art. 18): o shop anuncia, a loja apaga o que
        # é dela. Ver `shopman/shop/signals.py`.
        from shopman.shop.signals import customer_anonymized
        from shopman.storefront.handlers import on_customer_anonymized

        customer_anonymized.connect(
            on_customer_anonymized,
            dispatch_uid="storefront.privacy.on_customer_anonymized",
            weak=False,
        )
