"""Django AppConfig for the Shopman storefront (customer-facing surface)."""

from __future__ import annotations

from django.apps import AppConfig


class StorefrontConfig(AppConfig):
    name = "shopman.storefront"
    label = "storefront"
    verbose_name = "Loja online"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # System check do Concierge (SHOPMAN_W022/W023): o que ele precisa para
        # responder, conferido na subida. Mora aqui porque o shop não importa
        # superfície.
        # Concierge de WhatsApp: o turno roda no worker de diretivas. O handler é
        # desta superfície (fala com o cliente), então é registrado daqui, não pelo
        # `shop.handlers` — o shop não importa superfície.
        from shopman.orderman import registry

        import shopman.storefront.checks  # noqa: F401
        from shopman.storefront.concierge.handler import ConciergeTurnHandler
        from shopman.storefront.concierge.intent_pilot import IntentPilotMeasureHandler
        from shopman.storefront.stock_alert_delivery import StockAlertDeliveryHandler

        registry.register_directive_handler(ConciergeTurnHandler())
        registry.register_directive_handler(StockAlertDeliveryHandler())
        # "Medir agora" do placar das intenções (Admin): a medição roda no worker.
        registry.register_directive_handler(IntentPilotMeasureHandler())

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

        # Continuum 0.2: só marca a read model pública como suja. A reconstrução
        # continua usando ``build_catalog`` e acontece no próximo shadow/snapshot;
        # falha do cache nunca muda a resposta canônica do menu.
        from django.db.models.signals import m2m_changed, post_delete
        from shopman.offerman.models import (
            Collection,
            CollectionItem,
            Listing,
            ListingItem,
            Product,
        )

        from shopman.shop.models import AttributeDefinition, OmotenashiCopy
        from shopman.storefront.continuum import schedule_catalog_structure_dirty

        for model in (
            Product,
            Listing,
            ListingItem,
            Collection,
            CollectionItem,
            AttributeDefinition,
            OmotenashiCopy,
        ):
            for signal in (post_save, post_delete):
                signal.connect(
                    schedule_catalog_structure_dirty,
                    sender=model,
                    dispatch_uid=(
                        f"storefront.continuum.catalog_structure."
                        f"{model._meta.label_lower}.{signal is post_save}"
                    ),
                    weak=False,
                )
        m2m_changed.connect(
            schedule_catalog_structure_dirty,
            sender=Product.keywords.through,
            dispatch_uid="storefront.continuum.catalog_structure.product_keywords",
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
