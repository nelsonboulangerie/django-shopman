from types import SimpleNamespace

from shopman.backstage.admin import dashboard


def test_dashboard_table_builders_render_rows():
    stock_alerts = [
        SimpleNamespace(sku="SKU", current=1, minimum=3, deficit=2, position="loja")
    ]
    d1 = [
        SimpleNamespace(sku="SKU-D1", name="Produto", qty=2, entry_date_display="28/04")
    ]
    operator_alerts = [
        SimpleNamespace(severity="warning", message="Atenção" * 20, order_ref="", created_at_display="agora")
    ]

    ratings = [
        SimpleNamespace(rating=2, stars="★★☆☆☆", comment="Pão frio", order_ref="R-1",
                        submitted_at_display="28/04 10:00", is_low=True),
        SimpleNamespace(rating=5, stars="★★★★★", comment="", order_ref="R-2",
                        submitted_at_display="28/04 11:00", is_low=False),
    ]

    assert dashboard._build_alerts_table(stock_alerts)["rows"][0][0] == "SKU"
    assert dashboard._build_d1_table(d1)["rows"][0][1] == "Produto"
    assert dashboard._build_operator_alerts_table(operator_alerts)["rows"][0][2] == "—"
    ratings_table = dashboard._build_ratings_table(ratings)
    assert ratings_table["rows"][0][1] == "Pão frio"
    assert ratings_table["rows"][0][2] == "R-1"
    # Comentário vazio cai para o traço.
    assert ratings_table["rows"][1][1] == "—"


def test_omotenashi_health_handles_copy_model_errors():
    health = dashboard._omotenashi_health()

    assert "active_overrides" in health
    assert "recent_changes" in health


def test_dashboard_callback_populates_context(monkeypatch):
    proj = SimpleNamespace(
        kpi_stock_alerts=0,
        kpi_operator_alerts=0,
        stock_alerts=[],
        d1_stock=[],
        operator_alerts=[],
        rating_average="—",
        rating_count=0,
        rating_low_count=0,
        recent_ratings=[],
    )
    monkeypatch.setattr(dashboard, "build_dashboard", lambda: proj)
    monkeypatch.setattr(dashboard, "reverse", lambda name: f"/{name}/")
    monkeypatch.setattr(dashboard, "_omotenashi_health", lambda: {"active_overrides": 2})

    context = dashboard.dashboard_callback(None, {})

    assert context["kpi_stock_alerts"] == 0
    assert context["table_estoque_baixo"]["rows"] == []
    assert context["table_d1"] is None
    assert context["omotenashi_health"]["active_overrides"] == 2
    assert context["rating_average"] == "—"
    assert context["rating_count"] == 0
    assert context["table_ratings"]["rows"] == []
    # Começos de caminho do dia a dia — não um índice do Admin (o menu já é isso).
    labels = [link["label"] for link in context["config_links"]]
    assert labels == [
        "Loja e contato",
        "Produtos",
        "Regras de preço",
        "Promoções",
        "Textos da interface",
        "Canais",
    ]
    audit_labels = [link["label"] for link in context["audit_links"]]
    assert audit_labels == [
        "Histórico de pedidos",
        "Cobranças",
        "Turnos de caixa",
        "Fechamentos do dia",
    ]
    # Operação ao vivo saiu do dashboard: mora nos apps Nuxt.
    for gone in ("order_summary", "revenue", "production", "table_pedidos_pendentes",
                 "recent_orders", "chart_pedidos_status", "table_sugestao_producao"):
        assert gone not in context
