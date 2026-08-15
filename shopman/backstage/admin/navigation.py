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
from shopman.backstage.projections.settings_hub import settings_nav_sections
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
        _group("Clientes", "people", [
            _item("Clientes", "person_search", _url("admin:guestman_customer_changelist"), permission=_is_staff),
            _item("Contas de fidelidade", "loyalty", _url("admin:customer_loyalty_loyaltyaccount_changelist"), permission=_is_staff),
            _item("Avisos de reposição", "notifications_active", _url("admin:storefront_stockalertsubscription_changelist"), permission=_is_staff),
        ]),
        # O que se fabrica e com o quê. A régua de qualidade e o planejamento do dia
        # são ajuste, não operação: moram na Configuração.
        _group("Produção", "factory", [
            _item("Fichas técnicas", "menu_book", _url("admin:craftsman_recipe_changelist"), permission=_can_access_production),
            _item("Ordens de produção", "assignment", _url("admin:craftsman_workorder_changelist"), permission=_can_access_production),
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
        ]),
        # Trilha: o que já aconteceu. Nada aqui se opera, tudo aqui se confere.
        _group("Auditoria", "history", [
            _item("Histórico de pedidos", "receipt_long", _url("admin:orderman_order_changelist"), permission=_can_manage_orders),
            _item("Sessões de venda", "shopping_bag", _url("admin:orderman_session_changelist"), permission=_can_manage_orders),
            _item("Ações pendentes", "playlist_add_check", _url("admin:orderman_directive_changelist") + "?status__exact=queued", permission=_can_manage_orders),
            _item("Cobranças", "credit_card", _url("admin:payman_paymentintent_changelist"), permission=_can_manage_orders),
            _item("Turnos de caixa", "payments", _url("admin:backstage_cashshift_changelist"), permission=_can_operate_pos),
            _item("Movimentações de caixa", "currency_exchange", _url("admin:backstage_cashmovement_changelist"), permission=_can_operate_pos),
            _item("Fechamentos do dia", "event_available", _url("admin:backstage_dayclosing_changelist"), permission=_can_close_day),
            _item("Execuções de checklist", "checklist", _url("admin:backstage_operationchecklistrun_changelist"), permission=_is_staff),
        ]),
        # Configuração expande como os outros grupos — o menu tem UM comportamento,
        # não dois. Os subitens são os sete ESCOPOS, não as 33 telas: o Unfold só tem
        # dois níveis, então listar as telas aqui recriaria a gaveta que este trabalho
        # desmontou, e sem descrição nem busca.
        #
        # Cada escopo é âncora da seção correspondente. Assim o número de cliques até
        # uma tela não muda (o cartão continua a um clique da página), e em troca o
        # menu passa a mostrar a estrutura de onde as coisas moram sem precisar sair
        # da tela em que se está. A lista vem da projection, então escopo novo nasce
        # nos dois lugares de uma vez.
        _group("Configuração", "settings", [
            _item("Todos os ajustes", "tune", _url("admin_console_settings_hub"), permission=_is_staff),
            *[
                _item(
                    section["title"],
                    section["icon"],
                    f"{_url('admin_console_settings_hub')}#{section['slug']}",
                    permission=_is_staff,
                )
                for section in settings_nav_sections()
            ],
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


def _can_operate_kds(request) -> bool:
    return permissions.can_operate_kds(request.user)


def _can_operate_production(request) -> bool:
    return permissions.can_operate_production(request.user)


def _can_view_operator_alerts(request) -> bool:
    return permissions.can_view_operator_alerts(request.user)
