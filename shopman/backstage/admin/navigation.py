"""Admin/Unfold navigation tuned for operational backoffice.

The sidebar is intentionally split between live operation shortcuts and
backoffice/audit tools. Operator cockpit links go to Backstage; CRUD/audit links
stay in Admin.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from shopman.backstage import permissions
from shopman.shop.services import pos_links

logger = logging.getLogger(__name__)


def _pos_base_url() -> str:
    """Base absoluta do PDV (superfície Nuxt). Vazio ⇒ item de PDV oculto.

    O PDV migrou para Nuxt (surfaces/pos-nuxt, headless via
    api/v1/backstage/pos/*); não há rota Django. O link do operador aponta para a
    superfície Nuxt, configurável por deployment (como SHOPMAN_STOREFRONT_BASE_URL).
    """
    return (getattr(settings, "SHOPMAN_POS_BASE_URL", "") or "").rstrip("/")


def _orders_base_url() -> str:
    """Base absoluta do Gestor de Pedidos (surfaces/orders-nuxt). Vazio ⇒ oculto."""
    return (getattr(settings, "SHOPMAN_ORDERS_BASE_URL", "") or "").rstrip("/")


def _kds_base_url() -> str:
    """Base absoluta do KDS (surfaces/kds-nuxt). Vazio ⇒ oculto."""
    return (getattr(settings, "SHOPMAN_KDS_BASE_URL", "") or "").rstrip("/")


def _production_base_url() -> str:
    """Base absoluta da Produção (surfaces/production-nuxt). Vazio ⇒ oculto."""
    return (getattr(settings, "SHOPMAN_PRODUCTION_BASE_URL", "") or "").rstrip("/")


def get_sidebar_navigation(request):
    """Return the canonical Admin sidebar for this Shopman installation.

    Pedidos/POS/KDS são apps Nuxt headless dedicados (sem rota Django): só
    aparecem quando a base URL do deployment está configurada (evita link morto).
    O histórico/CRUD de pedidos segue no grupo "Pedidos".
    """
    live_items = []
    orders_url = _orders_base_url()
    if orders_url:
        live_items.append(
            _item(
                "Pedidos",
                "receipt_long",
                orders_url,
                permission=_can_manage_orders,
                badge="shopman.backstage.admin.navigation.badge_new_orders",
                badge_variant="warning",
            )
        )
    pos_url = _pos_base_url()
    if pos_url:
        # O fechamento do DIA migrou para a antesala do PDV (pos-nuxt
        # /session/closing, ADMIN-ROLE-PLAN WP-ADM-3). Sem URL configurada o
        # item some (sem link morto), como PDV/KDS.
        live_items.append(
            _item(
                "Fechamento",
                "fact_check",
                pos_links.pos_url(pos_links.path_day_closing()),
                permission=_can_close_day,
            )
        )
        live_items.append(_item("PDV", "point_of_sale", pos_url, permission=_can_operate_pos))
    kds_url = _kds_base_url()
    if kds_url:
        live_items.append(_item("KDS", "tv", kds_url, permission=_can_operate_kds))
    production_url = _production_base_url()
    if production_url:
        live_items.append(
            _item(
                "Produção ao vivo",
                "factory",
                production_url,
                permission=_can_operate_production,
                badge="shopman.backstage.admin.navigation.badge_started_work_orders",
                badge_variant="info",
            )
        )
    live_items.append(
        _item(
            "Alertas ativos",
            "warning",
            _url("admin:backstage_operatoralert_changelist") + "?acknowledged__exact=0",
            permission=_can_view_operator_alerts,
            badge="shopman.backstage.admin.navigation.badge_operator_alerts",
            badge_variant="danger",
            badge_style="solid",
        )
    )
    return [
        _group("Operação ao vivo", "bolt", live_items, collapsible=False),
        _group("Catálogo", "store", [
            _item("Produtos", "bakery_dining", _url("admin:offerman_product_changelist"), permission=_is_staff),
            _item("Coleções", "category", _url("admin:offerman_collection_changelist"), permission=_is_staff),
            _item("Vitrines", "shoppingmode", _url("admin:offerman_listing_changelist"), permission=_is_staff),
        ]),
        # Como se cobra e como se entrega. Preço e entrega andam juntos porque a
        # pergunta do gestor é uma só: "quanto essa pessoa paga por isso, aqui?".
        _group("Vendas e entrega", "sell", [
            _item("Canais", "storefront", _url("admin:shop_channel_changelist"), permission=_is_staff),
            _item("Regras de preço", "price_change", _url("admin:shop_ruleconfig_changelist"), permission=_is_staff),
            _item("Promoções", "campaign", _url("admin:shop_promotion_changelist"), permission=_is_staff),
            _item("Cupons", "confirmation_number", _url("admin:shop_coupon_changelist"), permission=_is_staff),
            _item("Faixas de preço", "groups", _url("admin:guestman_pricetier_changelist"), permission=_is_staff),
            _item("Zonas de entrega", "pin_drop", _url("admin:shop_deliveryzone_changelist"), permission=_is_staff),
            _item("Faixas de distância", "straighten", _url("admin:shop_deliverydistanceband_changelist"), permission=_is_staff),
        ]),
        _group("Clientes", "people", [
            _item("Clientes", "person_search", _url("admin:guestman_customer_changelist"), permission=_is_staff),
            _item("Contas de fidelidade", "loyalty", _url("admin:customer_loyalty_loyaltyaccount_changelist"), permission=_is_staff),
            _item("Avisos de reposição", "notifications_active", _url("admin:storefront_stockalertsubscription_changelist"), permission=_is_staff),
        ]),
        # Painel/planejamento migraram para o Produção (WP-ADM-7d); aqui fica o que
        # se cadastra uma vez e se consulta depois — mais os insumos, que são a
        # entrada da receita.
        _group("Produção", "factory", [
            _item("Fichas técnicas", "menu_book", _url("admin:craftsman_recipe_changelist"), permission=_can_access_production),
            _item("Ordens de produção", "assignment", _url("admin:craftsman_workorder_changelist"), permission=_can_access_production),
            _item("Defeitos de fornada", "report", _url("admin:shop_qualitydefect_changelist"), permission=_can_access_production),
            _item("Graus de qualidade", "grade", _url("admin:shop_qualitygrade_changelist"), permission=_can_access_production),
            _item("Motivos de episódio", "help_center", _url("admin:backstage_operationepisodekind_changelist"), permission=_is_staff),
            _item("Insumos", "grocery", _url("admin:buyman_material_changelist"), permission=_is_staff),
            _item("Fornecedores", "local_shipping", _url("admin:buyman_supplier_changelist"), permission=_is_staff),
            *(
                [
                    _item(
                        "Relatórios",
                        "table_chart",
                        f"{production_url}/reports",
                        permission=_can_view_production_reports,
                    )
                ]
                if production_url
                else []
            ),
        ]),
        _group("Estoque", "inventory_2", [
            _item("Saldos", "point_scan", _url("admin:stockman_quant_changelist"), permission=_is_staff),
            _item("Reservas", "keep", _url("admin:stockman_hold_changelist"), permission=_is_staff),
            _item("Movimentos", "swap_horiz", _url("admin:stockman_move_changelist"), permission=_is_staff),
            _item("Lotes", "inventory", _url("admin:stockman_batch_changelist"), permission=_is_staff),
            _item("Posições", "domain", _url("admin:stockman_position_changelist"), permission=_is_staff),
            _item("Alertas de estoque", "notification_important", _url("admin:stockman_stockalert_changelist"), permission=_is_staff),
        ]),
        # As nove telas da configuração da loja, e nada além delas: o grupo tem uma
        # intenção só, "configurar a loja", e por isso é previsível. O que virava
        # gaveta de tudo (o antigo "Configurações", com vinte itens de sete
        # assuntos) é justamente onde ninguém achava nada.
        _group("Loja", "settings", [
            _item("Loja e contato", "store", _url("admin:shop_shop_changelist"), permission=_is_staff),
            _item("Marca e aparência", "palette", _url("admin:shop_shopappearance_changelist"), permission=_is_staff),
            _item("Horários e operação", "schedule", _url("admin:shop_shopoperation_changelist"), permission=_is_staff),
            _item("Cardápio", "restaurant_menu", _url("admin:shop_shopmenu_changelist"), permission=_is_staff),
            _item("Pedidos e entrega", "local_shipping", _url("admin:shop_shopordering_changelist"), permission=_is_staff),
            _item("Fidelidade", "loyalty", _url("admin:shop_shoployalty_changelist"), permission=_is_staff),
            _item("PDV e alertas", "point_of_sale", _url("admin:shop_shoppos_changelist"), permission=_is_staff),
            _item("Produção", "manufacturing", _url("admin:shop_shopproduction_changelist"), permission=_is_staff),
            _item("Integrações", "extension", _url("admin:shop_shopintegrations_changelist"), permission=_is_staff),
        ]),
        # O que a loja diz — na tela e nas mensagens que ela manda.
        _group("Textos e mensagens", "format_quote", [
            _item("Textos da interface", "format_quote", _url("admin_console_copy_catalog"), permission=_is_staff),
            _item("Modelos de mensagem", "mail", _url("admin:shop_notificationtemplate_changelist"), permission=_is_staff),
        ]),
        # Trilha: o que já aconteceu. Nada aqui se opera, tudo aqui se confere.
        _group("Auditoria", "history", [
            _item("Histórico de pedidos", "receipt_long", _url("admin:orderman_order_changelist"), permission=_can_manage_orders),
            _item("Sessões de venda", "shopping_bag", _url("admin:orderman_session_changelist"), permission=_can_manage_orders),
            _item("Ações pendentes", "playlist_add_check", _url("admin:orderman_directive_changelist") + "?status__exact=queued", permission=_can_manage_orders),
            _item("Cobranças", "credit_card", _url("admin:payman_paymentintent_changelist"), permission=_can_manage_orders),
            _item("Turnos de caixa", "payments", _url("admin:backstage_cashshift_changelist"), permission=_can_operate_pos),
            _item("Movimentações de caixa", "currency_exchange", _url("admin:backstage_cashmovement_changelist"), permission=_can_operate_pos),
            # Sem esta entrada, a conferência só existiria para quem tem um QR
            # legível na mão — e o comprovante amassado, que é justamente o
            # caso em que alguém quer conferir, não teria porta nenhuma.
            _item("Conferir comprovante", "qr_code_scanner", _url("admin_console_cash_receipt_lookup"), permission=_can_view_cash_movement),
            _item("Fechamentos do dia", "event_available", _url("admin:backstage_dayclosing_changelist"), permission=_can_close_day),
            _item("Execuções de checklist", "checklist", _url("admin:backstage_operationchecklistrun_changelist"), permission=_is_staff),
            _item("Episódios de operação", "report_problem", _url("admin:backstage_operationepisode_changelist"), permission=_can_close_day),
        ]),
        # A gaveta do "raramente, mas quando precisa é aqui": equipamento da casa,
        # quem entra e com o quê, e a infraestrutura de referências.
        _group("Sistema", "admin_panel_settings", [
            _item("Estações KDS", "settings_input_component", _url("admin:backstage_kdsinstance_changelist"), permission=_can_operate_kds),
            _item("Comandas do PDV", "receipt", _url("admin:backstage_postab_changelist"), permission=_can_operate_pos),
            _item("Terminais do PDV", "point_of_sale", _url("admin:backstage_posterminal_changelist"), permission=_can_operate_pos),
            _item("Modelos de checklist", "fact_check", _url("admin:backstage_operationchecklisttemplate_changelist"), permission=_is_staff),
            _item("Modelos de tarefa", "task_alt", _url("admin:backstage_operationtasktemplate_changelist"), permission=_is_staff),
            _item("Usuários", "person", _url("admin:auth_user_changelist"), permission=_is_superuser),
            _item("Grupos", "group", _url("admin:auth_group_changelist"), permission=_is_superuser),
            _item("Operadores e PIN", "badge", _url("admin:doorman_pincredential_changelist"), permission=_is_superuser),
            _item("Dispositivos confiáveis", "devices", _url("admin:doorman_trusteddevice_changelist"), permission=_is_superuser),
            _item("Verificação em duas etapas", "security", _url("admin:otp_totp_totpdevice_changelist"), permission=_is_superuser),
            _item("Referências", "tag", _url("admin:refs_ref_changelist"), permission=_is_superuser),
        ]),
    ]


def badge_new_orders(request) -> str:
    from shopman.orderman.models import Order

    return str(Order.objects.filter(status=Order.Status.NEW).count())


def badge_started_work_orders(request) -> str:
    from shopman.craftsman.models import WorkOrder

    today = timezone.localdate()
    return str(WorkOrder.objects.filter(target_date=today, status=WorkOrder.Status.STARTED).count())


def badge_operator_alerts(request) -> str:
    from shopman.backstage.models import OperatorAlert

    return str(OperatorAlert.objects.filter(acknowledged=False).count())


def _group(title: str, icon: str, items: list[dict], *, collapsible: bool = True) -> dict:
    return {
        "title": title,
        "icon": icon,
        "separator": True,
        "collapsible": collapsible,
        "items": items,
    }


def _item(
    title: str,
    icon: str,
    link: str,
    *,
    permission,
    badge: str | None = None,
    badge_variant: str = "primary",
    badge_style: str = "soft",
) -> dict:
    item = {
        "title": title,
        "icon": icon,
        "link": link,
        "permission": permission,
    }
    if badge:
        item.update({
            "badge": badge,
            "badge_variant": badge_variant,
            "badge_style": badge_style,
        })
    return item


def _url(name: str) -> str:
    """Resolve uma rota do menu, ou levanta.

    Um item de menu que não resolve é bug, não estado válido: por meses o menu
    serviu ``href="#"`` para Promoções, Cupons e Zonas de entrega (os models
    migraram de storefront para shop e o link ficou para trás) sem que nada
    reclamasse. A falha agora GRITA no boot do menu e o teste
    ``test_admin_navigation`` cobre cada rota declarada.
    """
    return reverse(name)


# Request-oriented adapters over the canonical predicates. The sidebar speaks
# ``request``; the rules live once in shopman.backstage.permissions.
def _is_staff(request) -> bool:
    return permissions.is_staff(request.user)


def _is_superuser(request) -> bool:
    return permissions.is_superuser(request.user)


def _can_manage_orders(request) -> bool:
    return permissions.can_manage_orders(request.user)


def _can_access_production(request) -> bool:
    return permissions.can_access_production(request.user)


def _can_view_production_reports(request) -> bool:
    return permissions.can_view_production_reports(request.user)


def _can_close_day(request) -> bool:
    return permissions.can_close_day(request.user)


def _can_operate_pos(request) -> bool:
    return permissions.can_operate_pos(request.user)


def _can_view_cash_movement(request) -> bool:
    """Espelha o gate da própria tela — link que aparece e depois nega é pior que link que falta."""
    return request.user.has_perm("backstage.view_cashmovement")


def _can_operate_kds(request) -> bool:
    return permissions.can_operate_kds(request.user)


def _can_operate_production(request) -> bool:
    return permissions.can_operate_production(request.user)


def _can_view_operator_alerts(request) -> bool:
    return permissions.can_view_operator_alerts(request.user)
