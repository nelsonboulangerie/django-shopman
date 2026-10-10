"""Sugestão explicável — o número explica a si mesmo (WP-PE4, UX-P2).

O basis que o Core já entrega (média, amostra, committed, margem, estação,
reforço, perda, dias esgotados) chega estruturado na projection: a superfície
monta a conta ``projeção + encomendas + margem = sugestão`` e escolhe o sinal da
linha sem reinterpretar frase. A falta de insumo da sugestão é lida antes de
planejar, com a mesma régua do guardrail do fechamento.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.craftsman.services.queries import Suggestion
from shopman.stockman import stock
from shopman.stockman.models import Move, Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.models import DayClosing
from shopman.backstage.projections import production as production_projection
from shopman.backstage.projections.hub import purchase_surface_url
from shopman.backstage.projections.production import (
    _build_suggestion,
    _suggestion_material_checks,
    build_production_board,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(ref="baguete", name="Baguete", output_sku="BAGUETE", batch_size=1)


def _suggestion(recipe, quantity="49", **basis_overrides):
    basis = {
        "avg_demand": Decimal("28.5"),
        "committed": Decimal("12"),
        "safety_pct": Decimal("0.20"),
        "historical_days": 28,
        "same_weekday": True,
        "sample_size": 4,
        "confidence": "medium",
        "season": None,
        "waste_rate": None,
        "high_demand_applied": False,
        "soldout_days": 0,
    }
    basis.update(basis_overrides)
    return Suggestion(recipe=recipe, quantity=Decimal(quantity), basis=basis)


class TestSuggestionExplainability:
    def test_a_conta_fecha_em_unidades_inteiras(self, recipe):
        projection = _build_suggestion(_suggestion(recipe))
        # 28,5 arredonda para 29 (meio para cima); 29 + 12 + 8 = 49.
        assert (projection.projected, projection.committed, projection.margin) == ("29", "12", "8")
        assert projection.quantity == "49"
        assert projection.safety_percent == 20
        assert projection.same_weekday is True
        assert projection.sample_size == 4
        assert projection.confidence == "Média"

    def test_margem_negativa_mantem_o_sinal(self, recipe):
        projection = _build_suggestion(_suggestion(recipe, quantity="40"))
        assert projection.margin == "-1"

    def test_esgotamento_sobra_e_estacao(self, recipe):
        projection = _build_suggestion(
            _suggestion(
                recipe,
                soldout_days=3,
                waste_rate=Decimal("0.18"),
                season="hot",
                high_demand_applied=True,
            )
        )
        assert projection.soldout_days == 3
        assert projection.waste_percent == 18
        assert projection.waste_discounted is True
        assert projection.season_label == "estação quente"
        assert projection.high_demand_applied is True

    def test_comeco_de_estacao_usa_a_anterior_e_diz_qual(self, recipe):
        projection = _build_suggestion(
            _suggestion(recipe, season="mild", season_fallback=True, current_season="hot")
        )
        assert projection.season_fallback is True
        assert projection.season_label == "estação amena"
        assert projection.current_season_label == "estação quente"

    def test_sobra_abaixo_do_teto_nao_desconta(self, recipe):
        projection = _build_suggestion(_suggestion(recipe, waste_rate=Decimal("0.08")))
        assert projection.waste_percent == 8
        assert projection.waste_discounted is False

    def test_basis_vazio_degrada_quieto(self, recipe):
        projection = _build_suggestion(Suggestion(recipe=recipe, quantity=Decimal("10"), basis={}))
        assert projection.sample_size == 0
        assert projection.soldout_days == 0
        assert projection.waste_percent == 0
        assert projection.season_label == ""
        assert projection.season_fallback is False
        assert projection.current_season_label == ""
        assert projection.material_shortages == ()
        assert projection.fits_quantity == ""


@pytest.fixture
def deposito(db):
    return Position.objects.create(ref="deposito", name="Depósito", kind=PositionKind.PHYSICAL, is_default=True)


@pytest.fixture
def croissant(db):
    receita = Recipe.objects.create(ref="croissant", name="Croissant", output_sku="CROISSANT", batch_size=10)
    # 10 croissants levam 1 kg de manteiga e 2 kg de farinha.
    RecipeItem.objects.create(recipe=receita, input_sku="MANTEIGA", quantity=Decimal("1"), unit="kg", sort_order=1)
    RecipeItem.objects.create(recipe=receita, input_sku="FARINHA", quantity=Decimal("2"), unit="kg", sort_order=2)
    RecipeItem.objects.create(
        recipe=receita, input_sku="GERGELIM", quantity=Decimal("1"), unit="kg", sort_order=3, is_optional=True
    )
    return receita


def _recipes():
    return tuple(Recipe.objects.filter(is_active=True).prefetch_related("items"))


class TestSuggestionMaterialCheck:
    def test_falta_de_insumo_e_o_que_cabe(self, croissant, deposito):
        stock.receive(Decimal("4"), "MANTEIGA", position=deposito, reason="seed", kind=Move.Kind.BUY)
        stock.receive(Decimal("50"), "FARINHA", position=deposito, reason="seed", kind=Move.Kind.BUY)

        checks = _suggestion_material_checks([_suggestion(croissant, quantity="52")], _recipes(), skip_skus=set())

        shortages, fits = checks["CROISSANT"]
        assert fits == "40"
        assert len(shortages) == 1
        assert shortages[0].sku == "MANTEIGA"
        assert shortages[0].fits_quantity == "40"
        assert shortages[0].missing_display == "1200 g"

    def test_estoque_que_cobre_nao_avisa(self, croissant, deposito):
        stock.receive(Decimal("10"), "MANTEIGA", position=deposito, reason="seed", kind=Move.Kind.BUY)
        stock.receive(Decimal("50"), "FARINHA", position=deposito, reason="seed", kind=Move.Kind.BUY)

        assert _suggestion_material_checks([_suggestion(croissant, quantity="52")], _recipes(), skip_skus=set()) == {}

    def test_linha_ja_planejada_nao_e_conferida(self, croissant):
        checks = _suggestion_material_checks(
            [_suggestion(croissant, quantity="52")], _recipes(), skip_skus={"CROISSANT"}
        )
        assert checks == {}

    def test_sem_backend_de_insumo_nao_ha_aviso(self, croissant, settings):
        settings.CRAFTSMAN = {**settings.CRAFTSMAN, "INVENTORY_BACKEND": None}
        assert _suggestion_material_checks([_suggestion(croissant, quantity="52")], _recipes(), skip_skus=set()) == {}

    def test_a_grade_entrega_a_falta_na_sugestao_da_linha(self, croissant, deposito, monkeypatch):
        stock.receive(Decimal("4"), "MANTEIGA", position=deposito, reason="seed", kind=Move.Kind.BUY)
        monkeypatch.setattr(
            production_projection,
            "_production_suggestions",
            lambda selected_date: [_suggestion(croissant, quantity="52")],
        )

        board = build_production_board(selected_date=date(2026, 10, 3), purchase_url="https://compras.example/")

        row = next(row for row in board.matrix_rows if row.output_sku == "CROISSANT")
        assert row.suggestion is not None
        assert row.suggestion.fits_quantity == "0"
        assert {item.sku for item in row.suggestion.material_shortages} == {"MANTEIGA", "FARINHA"}
        assert board.purchase_url == "https://compras.example/"

    def test_linha_com_lote_na_data_nao_recebe_aviso(self, croissant, monkeypatch):
        WorkOrder.objects.create(
            ref="WO-CROISSANT-1",
            recipe=croissant,
            output_sku="CROISSANT",
            quantity=Decimal("30"),
            target_date=date(2026, 10, 3),
        )
        monkeypatch.setattr(
            production_projection,
            "_production_suggestions",
            lambda selected_date: [_suggestion(croissant, quantity="52")],
        )

        board = build_production_board(selected_date=date(2026, 10, 3))

        row = next(row for row in board.matrix_rows if row.output_sku == "CROISSANT")
        assert row.suggestion is not None
        assert row.suggestion.material_shortages == ()


def _operate_purchase() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_purchase",
    )


class TestPurchaseShortcut:
    @override_settings(SHOPMAN_SURFACE_URLS={"purchase": "https://compras.example/"})
    def test_quem_opera_compras_recebe_o_atalho(self):
        user = User.objects.create_user("comprador", password="pw", is_staff=True)
        user.user_permissions.add(_operate_purchase())
        assert purchase_surface_url(User.objects.get(pk=user.pk)) == "https://compras.example/"

    @override_settings(SHOPMAN_SURFACE_URLS={"purchase": "https://compras.example/"})
    def test_quem_nao_opera_compras_nao_recebe(self):
        user = User.objects.create_user("padeiro", password="pw", is_staff=True)
        assert purchase_surface_url(user) == ""
