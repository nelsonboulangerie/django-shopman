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


def _config_links() -> list[dict]:
    """Os começos de caminho mais frequentes — não um índice do Admin.

    O menu já lista tudo; repetir a lista inteira aqui não ajudaria ninguém. Estes
    são os pontos de partida do dia a dia: o que a loja é, o que ela vende, quanto
    cobra e o que diz.
    """
    return [
        {
            "label": "Loja e contato",
            "url": reverse("admin:shop_shop_changelist"),
            "icon": "storefront",
        },
        {
            "label": "Produtos",
            "url": reverse("admin:offerman_product_changelist"),
            "icon": "bakery_dining",
        },
        {
            "label": "Regras de preço",
            "url": reverse("admin:shop_ruleconfig_changelist"),
            "icon": "rule",
        },
        {
            "label": "Promoções",
            "url": reverse("admin:shop_promotion_changelist"),
            "icon": "campaign",
        },
        {
            # A tela própria do catálogo (navegação chave↔tela, PR #110) — não a
            # changelist crua do model.
            "label": "Textos da interface",
            "url": reverse("admin_console_copy_catalog"),
            "icon": "edit_note",
        },
        {
            "label": "Canais",
            "url": reverse("admin:shop_channel_changelist"),
            "icon": "hub",
        },
    ]


def _audit_links() -> list[dict]:
    """Trilhas readonly de auditoria (pedidos, cobranças, caixa, fechamentos)."""
    return [
        {
            "label": "Histórico de pedidos",
            "url": reverse("admin:orderman_order_changelist"),
            "icon": "receipt_long",
        },
        {
            "label": "Cobranças",
            "url": reverse("admin:payman_paymentintent_changelist"),
            "icon": "payments",
        },
        {
            "label": "Turnos de caixa",
            "url": reverse("admin:backstage_cashshift_changelist"),
            "icon": "point_of_sale",
        },
        {
            "label": "Fechamentos do dia",
            "url": reverse("admin:backstage_dayclosing_changelist"),
            "icon": "event_available",
        },
    ]


# ── Main callback ────────────────────────────────────────────────────


def dashboard_callback(request, context):
    """Populate admin dashboard with config shortcuts, audit trails and alerts."""
    proj = build_dashboard()

    context.update({
        # Config + auditoria
        "config_links": _config_links(),
        "audit_links": _audit_links(),
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
