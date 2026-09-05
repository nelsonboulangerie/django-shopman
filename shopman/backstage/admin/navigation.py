"""Admin/Unfold navigation tuned for operational backoffice.

The sidebar is intentionally split between live operation shortcuts and
backoffice/audit tools. Operator cockpit links go to Backstage; CRUD/audit links
stay in Admin.
"""

from __future__ import annotations

import logging

from django.apps import apps
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from shopman.backstage import permissions
from shopman.backstage.admin.gates import can_open_changelist, can_open_view
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


def _purchase_base_url() -> str:
    """Base absoluta do Compras (surfaces/purchase-nuxt). Vazio ⇒ oculto."""
    return (getattr(settings, "SHOPMAN_PURCHASE_BASE_URL", "") or "").rstrip("/")


def get_sidebar_navigation(request):
    """Return the canonical Admin sidebar for this Shopman installation.

    Pedidos/POS/KDS são apps Nuxt headless dedicados (sem rota Django): só
    aparecem quando a base URL do deployment está configurada (evita link morto).
    O histórico/CRUD de pedidos segue no grupo "Pedidos".
    """
    from shopman.backstage.admin_console.cash_receipt import CashReceiptVerifyView
    from shopman.backstage.admin_console.diagnostics import DiagnosticsView
    from shopman.backstage.admin_console.settings_hub import SettingsHubView

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
    purchase_url = _purchase_base_url()
    if purchase_url:
        live_items.append(_item("Compras", "package_check", purchase_url, permission=_can_operate_purchase))
    return [
        # O alarme não tem item no menu: a home do Admin já mostra os alertas numa
        # seção, com severidade, mensagem e pedido. Um link destacado aqui era a
        # mesma pergunta com dois donos — e um badge permanente pedindo atenção
        # numa tela onde a atenção já está posta. A LISTA continua alcançável em
        # Auditoria, que é o que ela é: a trilha do que foi alertado.
        #
        # Só os apps do operador, que são links para FORA do Admin e dependem da
        # URL do deployment. Sem nenhuma configurada (dev, por exemplo) a lista
        # fica vazia e o Unfold não desenha o grupo: melhor sumir do que anunciar
        # aplicativos que não existem aqui.
        _group("Aplicativos", "apps", live_items, collapsible=False),
        _group("Catálogo", "store", [
            _model_item("Produtos", "bakery_dining", "offerman.Product"),
            _model_item("Coleções", "category", "offerman.Collection"),
            _model_item("Vitrines", "shoppingmode", "offerman.Listing"),
        ]),
        _group("Clientes", "people", [
            _model_item("Clientes", "person_search", "guestman.Customer"),
            _model_item("Contas de fidelidade", "loyalty", "customer_loyalty.LoyaltyAccount"),
            _model_item("Avisos de reposição", "notifications_active", "storefront.StockAlertSubscription"),
            # Concierge de WhatsApp: a transcrição de cada conversa e a volta ao bot.
            _model_item("Conversas do WhatsApp", "chat", "shop.Conversation"),
        ]),
        # O que se fabrica e com o quê. A régua de qualidade e o planejamento do dia
        # são ajuste, não operação: moram na Configuração.
        _group("Produção", "factory", [
            _model_item("Fichas técnicas", "menu_book", "craftsman.Recipe"),
            _model_item("Ordens de produção", "assignment", "craftsman.WorkOrder"),
            _model_item("Insumos", "grocery", "buyman.Material"),
            _model_item("Fornecedores", "local_shipping", "buyman.Supplier"),
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
            _model_item("Saldos", "point_scan", "stockman.Quant"),
            _model_item("Reservas", "keep", "stockman.Hold"),
            _model_item("Movimentos", "swap_horiz", "stockman.Move"),
            _model_item("Lotes", "inventory", "stockman.Batch"),
        ]),
        # Trilha: o que já aconteceu. Nada aqui se opera, tudo aqui se confere.
        _group("Auditoria", "history", [
            _model_item("Histórico de pedidos", "receipt_long", "orderman.Order"),
            _model_item("Sessões de venda", "shopping_bag", "orderman.Session"),
            _model_item("Ações pendentes", "playlist_add_check", "orderman.Directive", query="?status__exact=queued"),
            _model_item("Cobranças", "credit_card", "payman.PaymentIntent"),
            # A movimentação (sangria, suprimento) é linha do turno, não tela: o
            # livro inteiro se lê de dentro do turno, em ordem. Um item próprio
            # seria a mesma pergunta com dois donos.
            # Quem decide é o ``ShiftAdmin``, que exige ``audit_shift`` e não
            # ``operate_pos``: a tela do turno mostra esperado, contado e
            # diferença, e oferecê-la a quem opera o caixa é entregar o gabarito
            # da contagem cega.
            _model_item("Turnos de caixa", "payments", "cashman.Shift"),
            _model_item("Fechamentos do dia", "event_available", "backstage.DayClosing"),
            _model_item("Execuções de checklist", "checklist", "backstage.OperationChecklistRun"),
            _model_item("Episódios de operação", "report_problem", "backstage.OperationEpisode"),
            # Sem esta entrada, a conferência só existiria para quem tem um QR
            # legível na mão — e o comprovante amassado, que é justamente o
            # caso em que alguém quer conferir, não teria porta nenhuma.
            _view_item("Conferir comprovante", "qr_code_scanner", "admin_console_cash_receipt_lookup", CashReceiptVerifyView),
            _model_item("Alertas do operador", "warning", "backstage.OperatorAlert"),
            # O crachá é a credencial que se perde no chão: posse pura, sem
            # segundo fator. A EMISSÃO já deixava rastro no histórico do
            # Admin; o USO não deixava nenhum. Esta é a outra metade.
            _model_item("Acessos de operador", "login", "backstage.SignInEvent"),
        ]),
        # O que entrou de fora no B.I. — trilha, como Auditoria, mas com dono
        # próprio: Auditoria está no teto que ainda se escaneia, e o B.I. vai
        # ganhar mais telas desta família (de-paras, cenários). Nasce aqui para
        # não dividir Auditoria depois. Só quem vê o B.I. vê o que o alimenta.
        _group("B.I.", "query_stats", [
            _model_item("Importações", "upload_file", "backstage.ImportBatch"),
            _model_item("Vendas históricas", "history_edu", "backstage.HistoricalSale"),
            _model_item("Vendas por dia", "calendar_month", "backstage.DailySalesFact"),
            # A curadoria: o que veio de fora se traduz no vocabulário da casa.
            # A máquina propõe, a pessoa confirma aqui; só o confirmado lê.
            _model_item("De-para de produtos", "swap_horiz", "backstage.ProductAlias"),
            _model_item("De-para de categorias", "category", "backstage.CategoryAlias"),
            _model_item("De-para de pagamentos", "payments", "backstage.PaymentMethodAlias"),
            # O B.I. avisa: a régua é do gestor, o disparo é trilha.
            _model_item("Alarmes", "notifications_active", "backstage.BIAlertRule"),
            _model_item("Disparos de alarme", "campaign", "backstage.BIAlertEvent"),
            _model_item("Cenários da IA", "auto_awesome", "backstage.BIScenarioReport"),
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
            _view_item(
                "Todos os ajustes",
                "tune",
                "admin_console_settings_hub",
                SettingsHubView,
                active=_exactly(_url("admin_console_settings_hub")),
            ),
            *[
                _item(
                    section["title"],
                    section["icon"],
                    reverse("admin_console_settings_scope", args=[section["slug"]]),
                    permission=_opens_view(SettingsHubView),
                    # Destaca o escopo TAMBÉM quando se está dentro de uma tela dele:
                    # "Zonas de entrega" é alcançada pela Configuração e não tem item
                    # próprio, então sem isto o menu não acenderia nada e a pessoa
                    # perderia a noção de onde está.
                    active=_scope_active(section["slug"]),
                )
                for section in settings_nav_sections()
            ],
            # Fora da lista de escopos de propósito: os itens acima ajustam a
            # loja, este PERGUNTA se as integrações estão de pé. A prontidão já
            # era calculada e não tinha porta — o único jeito de consultá-la era
            # um comando que exige o console, e o console não recebe segredo.
            _view_item(
                "Diagnóstico",
                "cable",
                "admin_console_diagnostics",
                DiagnosticsView,
                active=_exactly(_url("admin_console_diagnostics")),
            ),
        ]),
    ]


def badge_new_orders(request) -> str:
    from shopman.orderman.models import Order

    return str(Order.objects.filter(status=Order.Status.NEW).count())


def badge_started_work_orders(request) -> str:
    from shopman.craftsman.models import WorkOrder

    today = timezone.localdate()
    return str(WorkOrder.objects.filter(target_date=today, status=WorkOrder.Status.STARTED).count())


def _group(title: str, icon: str, items: list[dict], *, collapsible: bool = True) -> dict:
    return {
        "title": title,
        "icon": icon,
        "separator": True,
        "collapsible": collapsible,
        "items": items,
    }


def _model_item(title: str, icon: str, label: str, *, query: str = "", badge: str | None = None, badge_variant: str = "primary"):
    """Item de changelist: a URL e a permissão saem os dois do mesmo model.

    A permissão é a da PORTA (``admin.gates``), não um palpite paralelo. O menu
    passou meses oferecendo 26 telas à Fran das quais 26 respondiam 403, porque
    aqui a pergunta era ``is_staff`` e lá era ``view_<model>``.

    O model chega por ``"app_label.Model"`` e não importado: este menu lista as
    telas do sistema INTEIRO, e uma delas ("Avisos de reposição") mora no
    storefront — que o backstage não pode importar. Label errado levanta
    ``LookupError`` no boot do menu, alto como o ``_url()`` faz com rota.
    """
    opts = apps.get_model(label)._meta
    return _item(
        title,
        icon,
        _url(f"admin:{opts.app_label}_{opts.model_name}_changelist") + query,
        permission=_opens(label),
        badge=badge,
        badge_variant=badge_variant,
    )


def _view_item(title: str, icon: str, url_name: str, view, *, active=None):
    """Item de tela custom do Admin: a permissão é a que a própria view declara."""
    return _item(title, icon, _url(url_name), permission=_opens_view(view), active=active)


def _opens(label: str):
    def _check(request) -> bool:
        return can_open_changelist(request, apps.get_model(label))

    return _check


def _opens_view(view):
    def _check(request) -> bool:
        return can_open_view(request, view)

    return _check


def _item(
    title: str,
    icon: str,
    link: str,
    *,
    permission,
    badge: str | None = None,
    badge_variant: str = "primary",
    badge_style: str = "soft",
    active=None,
) -> dict:
    item = {
        "title": title,
        "icon": icon,
        "link": link,
        "permission": permission,
    }
    if active is not None:
        item["active"] = active
    if badge:
        item.update({
            "badge": badge,
            "badge_variant": badge_variant,
            "badge_style": badge_style,
        })
    return item


def _exactly(path: str):
    """Ativo só nesta tela — sem o `in` que o Unfold usa por padrão."""

    def _check(request) -> bool:
        return request.path == path

    return _check


def _scope_active(slug: str):
    """Ativo na tela do escopo E em qualquer tela de configuração dele."""
    from shopman.backstage.projections.settings_hub import settings_scope_urls

    def _check(request) -> bool:
        scope_url = reverse("admin_console_settings_scope", args=[slug])
        if request.path == scope_url:
            return True
        return any(request.path.startswith(url) for url in settings_scope_urls(slug))

    return _check


def _url(name: str) -> str:
    """Resolve uma rota do menu, ou levanta.

    Um item de menu que não resolve é bug, não estado válido: por meses o menu
    serviu ``href="#"`` para Promoções, Cupons e Zonas de entrega (os models
    migraram de storefront para shop e o link ficou para trás) sem que nada
    reclamasse. A falha agora GRITA no boot do menu e o teste
    ``test_admin_navigation`` cobre cada rota declarada.
    """
    return reverse(name)


# Adaptadores de ``request`` para os predicados canônicos, e só para os itens que
# apontam para FORA do Admin (os apps Nuxt): lá a porta é o gate da API, não um
# ``ModelAdmin``. Tela do Admin não passa por aqui — ela responde por si em
# ``admin.gates``.
def _can_manage_orders(request) -> bool:
    return permissions.can_manage_orders(request.user)


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


def _can_operate_purchase(request) -> bool:
    return permissions.can_operate_purchase(request.user)
