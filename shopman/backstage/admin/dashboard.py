"""Unfold admin dashboard callback — landing de configuração e auditoria.

O Admin é CRUD mínimo + configurações: a operação ao vivo mora nos apps Nuxt
(Gestor/PDV/KDS/Produção). O dashboard reúne atalhos de configuração, trilhas
de auditoria, saúde da copy omotenashi e os dados de atenção (alertas de
estoque, alertas do operador).

Data is built by ``shopman.backstage.projections.dashboard.build_dashboard()``.
This module only handles admin-specific table formatting (``format_html``).
"""

from __future__ import annotations

import logging

from django.contrib import admin
from django.contrib.admin.exceptions import NotRegistered
from django.urls import reverse
from django.utils.html import format_html
from shopman.utils import table_badge

from shopman.backstage.projections.dashboard import build_dashboard

logger = logging.getLogger(__name__)


def _omotenashi_health() -> dict:
    """Compute Omotenashi copy health stats for the admin dashboard widget.

    A superfície do cliente é o storefront Nuxt (headless): o sinal de saúde
    aqui é o registro de copy (overrides ativos + alterações recentes).
    """
    try:
        from shopman.shop.models import OmotenashiCopy

        active_overrides = OmotenashiCopy.objects.filter(active=True).count()
        recent_changes = list(
            OmotenashiCopy.history.order_by("-history_date")
            .values("key", "history_type", "history_date", "history_user__username")[:5]
        )
    except Exception:
        logger.debug("omotenashi_health_query_failed", exc_info=True)
        active_overrides = 0
        recent_changes = []

    return {
        "active_overrides": active_overrides,
        "recent_changes": recent_changes,
    }


def _card(label: str, icon: str, url: str) -> dict:
    return {"label": label, "url": url, "icon": icon}


def _model_card(request, label: str, icon: str, model) -> dict | None:
    """Um card por porta que ABRE — e quem responde isso é a própria porta.

    O card não repete a regra do ``ModelAdmin`` com outras palavras: pergunta ao
    ``ModelAdmin`` se ele abriria para este request. Repetir a regra aqui seria
    a mesma pergunta com dois donos, e o dono errado ganha calado — foi assim que
    esta lista passou meses oferecendo "Turnos de caixa" a quem opera o caixa,
    com o gate real morando em ``ShiftAdmin.has_view_permission``.
    """
    opts = model._meta
    try:
        model_admin = admin.site.get_model_admin(model)
    except NotRegistered:
        logger.warning("dashboard_card_model_nao_registrada", extra={"model": opts.label})
        return None
    if not model_admin.has_view_or_change_permission(request):
        return None
    return _card(label, icon, reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist"))


def _view_card(request, label: str, icon: str, url_name: str, view) -> dict | None:
    """Idem para tela custom do Admin: a permissão vem da view, não daqui."""
    required = view.permission_required
    required = (required,) if isinstance(required, str) else tuple(required)
    if not request.user.has_perms(required):
        return None
    return _card(label, icon, reverse(url_name))


def _config_links(request) -> list[dict]:
    """Os começos de caminho mais frequentes — não um índice do Admin.

    O menu já lista tudo; repetir a lista inteira aqui não ajudaria ninguém. Estes
    são os pontos de partida do dia a dia: o que a loja é, o que ela vende, quanto
    cobra e o que diz — dos quais cada pessoa vê o que de fato alcança.
    """
    from shopman.offerman.models import Product

    from shopman.backstage.admin_console.copy_catalog import CopyCatalogView
    from shopman.shop.models import Channel, Promotion, RuleConfig, Shop

    cards = [
        _model_card(request, "Loja e contato", "storefront", Shop),
        _model_card(request, "Produtos", "bakery_dining", Product),
        _model_card(request, "Regras de preço", "rule", RuleConfig),
        _model_card(request, "Promoções", "campaign", Promotion),
        # A tela própria do catálogo (navegação chave↔tela, PR #110) — não a
        # changelist crua do model.
        _view_card(request, "Textos da interface", "edit_note", "admin_console_copy_catalog", CopyCatalogView),
        _model_card(request, "Canais", "hub", Channel),
    ]
    return [card for card in cards if card is not None]


def _audit_links(request) -> list[dict]:
    """Trilhas readonly de auditoria (pedidos, cobranças, caixa, fechamentos)."""
    from shopman.cashman.models import Shift
    from shopman.orderman.models import Order
    from shopman.payman.models import PaymentIntent

    from shopman.backstage.models import DayClosing

    cards = [
        _model_card(request, "Histórico de pedidos", "receipt_long", Order),
        _model_card(request, "Cobranças", "payments", PaymentIntent),
        # ``audit_shift``, não ``operate_pos``: a tela do turno mostra esperado,
        # contado e diferença, e oferecê-la a quem opera o caixa é oferecer o
        # gabarito da contagem cega. Quem decide é o ``ShiftAdmin`` — inclusive
        # quando a estação está identificada por PIN e o operador ativo responde
        # pela tela, e não a conta do aparelho.
        _model_card(request, "Turnos de caixa", "point_of_sale", Shift),
        _model_card(request, "Fechamentos do dia", "event_available", DayClosing),
    ]
    return [card for card in cards if card is not None]


# ── Main callback ────────────────────────────────────────────────────


def dashboard_callback(request, context):
    """Populate admin dashboard with config shortcuts, audit trails and alerts."""
    proj = build_dashboard()

    context.update({
        # Config + auditoria
        "config_links": _config_links(request),
        "audit_links": _audit_links(request),
        "omotenashi_health": _omotenashi_health(),
        # Atenção (alertas)
        "kpi_stock_alerts": proj.kpi_stock_alerts,
        "kpi_operator_alerts": proj.kpi_operator_alerts,
        "table_estoque_baixo": _build_alerts_table(proj.stock_alerts),
        "operator_alerts": proj.operator_alerts,
        "table_operator_alerts": _build_operator_alerts_table(proj.operator_alerts),
        # Avaliações do cliente (fecha o loop): média móvel + últimos comentários.
        "rating_average": proj.rating_average,
        "rating_count": proj.rating_count,
        "rating_low_count": proj.rating_low_count,
        "table_ratings": _build_ratings_table(proj.recent_ratings),
    })
    return context


# ── Table builders ───────────────────────────────────────────────────
# These stay here: they produce format_html output for Unfold table widgets.

SEVERITY_LABEL = {"warning": "Aten\u00e7\u00e3o", "error": "Erro", "critical": "Cr\u00edtico"}
SEVERITY_BADGE_TYPE = {"warning": "orange", "error": "red", "critical": "red"}


def _build_alerts_table(alerts):
    """Stock alerts table with deficit highlighted."""
    rows = []
    for a in alerts:
        rows.append([
            a.sku,
            format_html('<span class="font-medium text-red-600 dark:text-red-400">{}</span>', a.current),
            a.minimum,
            format_html('<span class="font-medium text-red-600 dark:text-red-400">{}</span>', a.deficit),
            a.position,
        ])

    return {
        "headers": ["SKU", "Atual", "Mínimo", "Déficit", "Posição"],
        "rows": rows,
    }


def _build_ratings_table(rows):
    """Recent customer ratings table for the dashboard.

    Estrelas + comentário + pedido + quando. Notas baixas (≤2) em vermelho para
    pular aos olhos do gestor.
    """
    table_rows = []
    for r in rows:
        # Nota baixa (≤2) em vermelho canônico para pular aos olhos; as demais em
        # texto padrão (a coluna já se lê pelas estrelas).
        if r.is_low:
            stars_cell = format_html(
                '<span class="font-semibold text-red-600 dark:text-red-400">{}</span>', r.stars,
            )
        else:
            stars_cell = r.stars
        table_rows.append([
            stars_cell,
            r.comment or "—",
            r.order_ref or "—",
            r.submitted_at_display,
        ])
    return {
        "headers": ["Nota", "Comentário", "Pedido", "Quando"],
        "rows": table_rows,
    }


def _build_operator_alerts_table(alerts):
    """Operator alerts table for dashboard."""
    rows = []
    for alert in alerts:
        rows.append([
            table_badge(
                SEVERITY_LABEL.get(alert.severity, alert.severity),
                SEVERITY_BADGE_TYPE.get(alert.severity, "base"),
            ),
            alert.message[:100],
            alert.order_ref or "—",
            alert.created_at_display,
        ])
    return {
        "headers": ["Severidade", "Mensagem", "Pedido", "Data"],
        "rows": rows,
    }
