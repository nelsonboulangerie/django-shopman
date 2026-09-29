"""Django AppConfig for the Shopman backstage (operator-facing surfaces)."""

from __future__ import annotations

from django.apps import AppConfig


class BackstageConfig(AppConfig):
    name = "shopman.backstage"
    label = "backstage"
    verbose_name = "Operação"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django.db.models.signals import pre_save
        from shopman.orderman.models import Fulfillment, Order

        from shopman.backstage.services.delivery_devices import guard_dispatch

        for model in (Order, Fulfillment):
            pre_save.connect(guard_dispatch, sender=model, weak=False,
                             dispatch_uid=f"backstage.delivery_device.{model.__name__}")

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

        # A DANFE da entrega sai pela impressora do despacho, pelo relay, sem
        # depender de onde o Gestor está aberto. Duas portas, porque a ordem
        # varia: a nota autoriza depois do despacho (o normal) ou o pedido é
        # despachado com a nota já autorizada. Ver services/order_danfe.py.
        from shopman.orderman.signals import order_changed

        from shopman.backstage.services.order_danfe import on_nfce_authorized, on_order_changed
        from shopman.shop.signals import nfce_authorized

        nfce_authorized.connect(
            on_nfce_authorized,
            dispatch_uid="backstage.order_danfe.on_nfce_authorized",
            weak=False,
        )
        order_changed.connect(
            on_order_changed,
            dispatch_uid="backstage.order_danfe.on_order_changed",
            weak=False,
        )

        # A Via Cozinha: o posto do KDS sem tela recebe cada ticket impresso na
        # impressora escolhida no posto, pelo relay. Receiver próprio, fora dos
        # emissores de SSE: imprimir e avisar a tela são efeitos independentes.
        # Ver services/kitchen_ticket_print.py.
        from django.db.models.signals import post_save

        from shopman.backstage.models import KDSTicket
        from shopman.backstage.services.kitchen_ticket_print import on_ticket_saved

        post_save.connect(
            on_ticket_saved,
            sender=KDSTicket,
            dispatch_uid="backstage.kitchen_ticket_print.on_ticket_saved",
            weak=False,
        )

        # Trilha de acesso: quem entrou, por qual porta, de onde. O sucesso vem
        # do signal do PRÓPRIO Django — os quatro caminhos de operador (senha do
        # Admin, senha do app, PIN, crachá) terminam todos em `login()`, então
        # um caminho de login escrito amanhã já nasce coberto e nenhuma view
        # precisa lembrar de gravar. Cliente não entra: o receiver filtra staff.
        from django.contrib.auth.signals import user_logged_in, user_login_failed

        from shopman.backstage.services.sign_in_audit import (
            on_user_logged_in,
            on_user_login_failed,
        )

        user_logged_in.connect(
            on_user_logged_in,
            dispatch_uid="backstage.sign_in_audit.on_logged_in",
            weak=False,
        )
        user_login_failed.connect(
            on_user_login_failed,
            dispatch_uid="backstage.sign_in_audit.on_login_failed",
            weak=False,
        )

        # A curadoria do backstage (de-paras, vocabulário de consumo, salão)
        # entra no cofre de dados curados do shop (shopman.shop.backup).
        from shopman.backstage.backup_resources import register_backstage_resources

        register_backstage_resources()

        # A revisão campo a campo da sugestão do GTIN entra por cima do Admin de
        # Produto que o Core registrou. Precisa ser aqui, no ready() do último
        # app: as abas fiscal e social também são compostas em ready(), e o
        # autodiscover do admin roda antes de todos eles.
        from shopman.backstage.admin.product_enrichment import install_enrichment_review

        install_enrichment_review()
