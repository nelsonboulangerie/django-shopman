"""Casamento ingrediente ↔ insumo (``services/recipe_matching.py``).

Insumos reais no banco (os SKUs do seed), nome da fonte em francês, japonês,
inglês e português com qualificador, e uma ``extra_option`` que o módulo não
conhece (o levain, saída de uma receita-parte).
"""

from __future__ import annotations

import pytest
from shopman.buyman.models import Material

from shopman.backstage.services import recipe_matching
from shopman.backstage.services.recipe_matching import (
    IngredientCandidate,
    best_match,
    candidates_for,
    canonical_query,
    normalize_name,
    role_for,
    search_ingredients,
)

pytestmark = pytest.mark.django_db

LEVAIN = IngredientCandidate(sku="LEVAIN", name="Levain", unit="kg", role="yeast", score=0)


@pytest.fixture
def materials():
    rows = [
        ("FARINHA-T55", "Farinha de trigo T55", "kg"),
        ("FARINHA-INT", "Farinha de trigo integral", "kg"),
        ("AGUA-FILTRADA", "Água filtrada", "l"),
        ("MANTEIGA-FR", "Manteiga francesa", "kg"),
        ("OVOS", "Ovos", "kg"),
        ("SAL", "Sal", "kg"),
        ("FERMENTO-BIO", "Fermento biológico", "kg"),
    ]
    created = {sku: Material.objects.create(sku=sku, name=name, unit=unit) for sku, name, unit in rows}
    Material.objects.create(sku="FARINHA-VELHA", name="Farinha de trigo antiga", unit="kg", is_active=False)
    return created


# ── Casamento ───────────────────────────────────────────────────────────────


def test_french_flour_with_its_type_lands_on_the_right_sku(materials):
    ranked = candidates_for("farine T55")

    assert ranked[0].sku == "FARINHA-T55"
    assert ranked[0].score >= 90
    assert ranked[0].unit == "kg"
    assert ranked[0].role == "flour"


def test_japanese_bread_flour_finds_a_wheat_flour(materials):
    ranked = candidates_for("強力粉")

    assert ranked, "強力粉 é farinha de trigo forte; alguma FARINHA-* precisa aparecer"
    assert ranked[0].sku.startswith("FARINHA-")


def test_french_water_finds_the_filtered_water(materials):
    assert best_match("eau").sku == "AGUA-FILTRADA"


def test_a_qualifier_does_not_pull_the_wrong_ingredient(materials):
    """"manteiga sem sal" é manteiga; o "sal" da frase não pode vencer."""
    match = best_match("manteiga sem sal")

    assert match is not None
    assert match.sku == "MANTEIGA-FR"


def test_an_extra_option_the_module_does_not_know_can_win(materials):
    """O levain é saída de uma receita-parte, não insumo: quem sabe dele injeta."""
    assert best_match("levain") is None, "sem a opção injetada, o sistema não conhece levain"

    match = best_match("levain", extra_options=[LEVAIN])

    assert match is not None
    assert match.sku == "LEVAIN"
    assert match.score == 100


def test_nonsense_has_no_best_match_and_no_noisy_candidates(materials):
    assert best_match("unicórnio") is None
    assert candidates_for("unicórnio") == ()


def test_liquid_unit_is_spelled_the_way_the_ficha_spells_it(materials):
    assert candidates_for("água")[0].unit == "L"


def test_ties_prefer_the_shorter_name(materials):
    """"far" cabe em todas as farinhas; a mais curta é a genérica, e a genérica é a aposta segura."""
    ranked = candidates_for("far")

    assert ranked[0].sku == "FARINHA-T55"
    assert ranked[0].score == ranked[1].score


def test_without_any_material_nothing_explodes():
    assert candidates_for("farinha") == ()
    assert best_match("farinha") is None
    assert search_ingredients("") == ()


def test_a_blank_name_yields_nothing(materials):
    assert candidates_for("   ") == ()
    assert best_match("") is None


# ── Autocomplete ────────────────────────────────────────────────────────────


def test_an_empty_search_lists_the_active_materials_by_name_limited(materials):
    listed = search_ingredients("", limit=3)

    assert [c.name for c in listed] == ["Farinha de trigo T55", "Farinha de trigo integral", "Fermento biológico"]
    assert all(c.score == 0 for c in listed)


def test_an_inactive_material_never_shows_up(materials):
    assert "FARINHA-VELHA" not in {c.sku for c in search_ingredients("")}
    assert "FARINHA-VELHA" not in {c.sku for c in search_ingredients("farinha antiga")}
    assert "FARINHA-VELHA" not in {c.sku for c in candidates_for("farinha de trigo antiga", limit=10)}


def test_a_typed_prefix_ranks_like_a_match(materials):
    assert search_ingredients("ferm")[0].sku == "FERMENTO-BIO"


# ── Normalização, sinônimos e papel (puros) ─────────────────────────────────


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Farine de seigle", "farinha de centeio"),
        ("farine", "farinha de trigo"),
        ("whole wheat flour", "farinha de trigo integral"),
        ("ライ麦粉", "farinha de centeio"),
        ("eau tiède", "agua"),
        ("œufs", "ovos"),
        ("huile d'olive", "azeite"),
        ("levure fraîche", "fermento biologico"),
        ("生クリーム", "creme de leite"),
        ("raisins secs", "passas"),
        ("Manteiga SEM SAL", "manteiga"),
        ("Farinha integral", "farinha de trigo integral"),
    ],
)
def test_synonyms_translate_the_source_to_the_house_term(source, expected):
    assert canonical_query(source) == expected


def test_normalization_drops_latin_accents_but_keeps_japanese_letters():
    assert normalize_name("Açúcar, mascavo!") == "acucar mascavo"
    assert normalize_name("ごま") == "ごま", "o dakuten é parte da letra, não acento"


@pytest.mark.parametrize(
    ("name", "sku", "role"),
    [
        ("Farinha de trigo T55", "FARINHA-T55", "flour"),
        ("Água filtrada", "AGUA-FILTRADA", "liquid"),
        ("Sal marinho", "SAL", "salt"),
        ("Salsicha vienna", "SALSICHA-VIENNA", "inclusion"),
        ("Manteiga francesa", "MANTEIGA-FR", "fat"),
        ("Creme de leite fresco", "CREME-DE-LEITE", "dairy"),
        ("Fermento natural (levain)", "FERMENTO-NAT", "yeast"),
        ("Ovos", "OVOS", "egg"),
        ("Gotas de chocolate", "GOTAS-CHOCOLATE", "inclusion"),
        ("Malte", "MALTE", "sugar"),
        ("Cebola roxa", "CEBOLA-ROXA", "inclusion"),
        ("Coisa nenhuma", "X", "other"),
    ],
)
def test_role_comes_from_the_name_when_metadata_is_silent(name, sku, role):
    assert role_for(name, sku) == role


def test_a_declared_role_in_metadata_wins_over_the_keyword():
    assert role_for("Farinha de trigo", "FARINHA", {"role": "inclusion"}) == "inclusion"
    assert role_for("Farinha de trigo", "FARINHA", {"role": "papel inventado"}) == "flour"


def test_the_role_table_only_uses_known_roles():
    assert {role for role, _ in recipe_matching._ROLE_KEYWORDS} <= set(recipe_matching.ROLES)
