"""Django AppConfig for the Shopman backstage (operator-facing surfaces)."""

from __future__ import annotations

from django.apps import AppConfig


class BackstageConfig(AppConfig):
    name = "shopman.backstage"
    label = "backstage"
    verbose_name = "Operação"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # "Não tenho o produto para oferecer": o que muda essa resposta é
        # estoque ou reserva. Reserva que expira por varredura em massa não
        # emite signal — quem cobre esse buraco é a reconciliação periódica
        # no maintenance_worker (services/shelf_outages.reconcile_outages).
        from django.db.models.signals import post_save
        from shopman.stockman.models import Hold, Move

        from shopman.backstage.handlers import (
            on_hold_for_shelf_outage,
            on_move_for_shelf_outage,
        )

        post_save.connect(
            on_move_for_shelf_outage,
            sender=Move,
            dispatch_uid="backstage.shelf_outage.on_move",
            weak=False,
        )
        post_save.connect(
            on_hold_for_shelf_outage,
            sender=Hold,
            dispatch_uid="backstage.shelf_outage.on_hold",
            weak=False,
        )
