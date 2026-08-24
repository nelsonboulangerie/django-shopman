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
        from shopman.cashman.signals import entry_recorded, shift_closed, shift_opened
        from shopman.stockman.models import Hold, Move

        from shopman.backstage.handlers import (
            on_entry_for_pos_event,
            on_hold_for_shelf_outage,
            on_move_for_shelf_outage,
            on_shift_closed,
            on_shift_opened,
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

        # Os fatos de caixa que outra estação precisa ver (pedido de troco,
        # devolução entregue, turno aberto/fechado) são anunciados por quem OUVE
        # o livro, e não por quem grava: o `cashman` não sabe o que é SSE, e o
        # balcão não deve precisar lembrar de anunciar. Os sinais já saem no
        # commit; o publish ainda espera o `on_commit` (ADR-016).
        entry_recorded.connect(
            on_entry_for_pos_event,
            dispatch_uid="backstage.pos_event.on_entry",
            weak=False,
        )
        shift_opened.connect(
            on_shift_opened,
            dispatch_uid="backstage.pos_event.on_shift_opened",
            weak=False,
        )
        shift_closed.connect(
            on_shift_closed,
            dispatch_uid="backstage.pos_event.on_shift_closed",
            weak=False,
        )
