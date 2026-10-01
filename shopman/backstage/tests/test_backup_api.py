"""Download do cofre de dados curados — gate fino e conteúdo do arquivo.

Também prova que as entidades do backstage (de-paras, vocabulário de consumo,
salão, nota das receitas) entram no cofre pelo registro do shop e fazem o ciclo completo — a
direção backstage → shop registrando resource é o contrato de extensão do cofre.
"""

from __future__ import annotations

import io
from io import StringIO

import pytest
from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.urls import reverse
from openpyxl import load_workbook

from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag, SeatingSpot

pytestmark = pytest.mark.django_db


def _perm(codename: str) -> Permission:
    return Permission.objects.get(codename=codename, content_type__app_label="backstage")


@pytest.fixture
def manager(db):
    user = User.objects.create_user("backup-manager", password="pw", is_staff=True)
    user.user_permissions.add(_perm("export_backup"))
    return user


@pytest.fixture
def floor_operator(db):
    user = User.objects.create_user("backup-floor", password="pw", is_staff=True)
    user.user_permissions.add(_perm("operate_production"))
    return user


def test_floor_gate_does_not_open_backup(client, floor_operator):
    client.force_login(floor_operator)
    assert client.get(reverse("api-backstage-backup-export")).status_code == 403


def test_backup_download_is_a_real_workbook(client, manager):
    SeatingSpot.objects.create(ref="mesa-1", label="Mesa 1")
    client.force_login(manager)
    response = client.get(reverse("api-backstage-backup-export"))
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith('attachment; filename="backup-')
    book = load_workbook(io.BytesIO(response.content), read_only=True)
    sheets = set(book.sheetnames)
    assert {"products", "recipes", "seating_spots", "product_aliases"} <= sheets
    spots = book["seating_spots"]
    rows = list(spots.iter_rows(values_only=True))
    assert rows[0][0] == "ref"
    assert any(row[0] == "mesa-1" for row in rows[1:])


def test_backstage_entities_roundtrip_via_commands(tmp_path):
    role = ConsumptionRole.objects.create(ref="cafe", label="Café", reading="anchor")
    ProductConsumptionTag.objects.create(sku="CAFE-01", role=role)
    call_command("export_backup", "--out", str(tmp_path), stdout=StringIO())
    path = next(tmp_path.glob("backup-*.xlsx"))

    ProductConsumptionTag.objects.all().delete()
    ConsumptionRole.objects.all().update(label="Errado")

    call_command("import_backup", str(path), "--apply", stdout=StringIO())
    assert ConsumptionRole.objects.get(ref="cafe").label == "Café"
    assert ProductConsumptionTag.objects.get(sku="CAFE-01").role.ref == "cafe"


def test_recipe_ratings_criteria_and_sources_survive_the_vault(tmp_path):
    """D24 (dono, 01/10/2026): notas, critérios e fontes entram no cofre e voltam.

    Perda de verdade: a receita é apagada (as versões e as notas vão junto, D11) e
    os critérios também. O restore devolve a receita com as fontes no ``meta``, a
    versão, o critério renomeado no Admin e a avaliação com cada nota.
    """
    from shopman.craftsman.models import RecipeEntry, RecipeVersion
    from shopman.craftsman.services import recipe_book as craftsman

    from shopman.backstage.models import RecipeRatingCriterion, RecipeVersionRating, RecipeVersionRatingScore
    from shopman.backstage.services import recipe_ratings

    sources = [{"title": "Tartine Bread", "note": "página 48"}, {"title": "Vídeo", "url": "https://example.com/v"}]
    entry = craftsman.create_entry(ref="baguete", name="Baguete", kind="bread", output_sku="")
    RecipeEntry.objects.filter(pk=entry.pk).update(meta={"external_references": sources})
    draft = craftsman.create_version(
        entry, formula={"anchor": {"kind": "total"}, "items": [], "parts": []}, yield_quantity=1, yield_unit="g",
    )
    RecipeRatingCriterion.objects.filter(name="Aparência").update(name="Casca", description="Cor e estalo")
    criteria = {criterion.name: criterion for criterion in recipe_ratings.active_criteria()}
    scores = {str(criteria["Sabor"].pk): 5, str(criteria["Textura"].pk): 0, str(criteria["Casca"].pk): 4}
    recipe_ratings.rate("nota-ana", draft, scores)  # rascunho recebe nota (D24)

    call_command("export_backup", "--out", str(tmp_path), stdout=StringIO())
    path = next(tmp_path.glob("backup-*.xlsx"))

    RecipeEntry.objects.all().delete()
    assert not RecipeVersionRating.objects.exists()
    RecipeRatingCriterion.objects.all().delete()

    call_command("import_backup", str(path), "--apply", stdout=StringIO())

    restored = RecipeEntry.objects.get(ref="baguete")
    assert restored.meta["external_references"] == sources
    assert RecipeVersion.objects.filter(entry=restored, number=1).exists()
    assert list(RecipeRatingCriterion.objects.values_list("name", flat=True)) == ["Sabor", "Textura", "Casca"]
    assert RecipeRatingCriterion.objects.get(name="Casca").description == "Cor e estalo"
    rating = RecipeVersionRating.objects.get()
    assert (rating.entry_ref, rating.version_number, rating.operator_ref) == ("baguete", 1, "nota-ana")
    assert {
        score.criterion.name: score.score for score in RecipeVersionRatingScore.objects.select_related("criterion")
    } == {"Sabor": 5, "Textura": 0, "Casca": 4}


def test_a_lost_score_comes_back_even_with_the_rating_still_standing(tmp_path):
    """A avaliação de pé não esconde a nota perdida: o restore reescreve as notas da linha."""
    from shopman.craftsman.services import recipe_book as craftsman

    from shopman.backstage.models import RecipeVersionRatingScore
    from shopman.backstage.services import recipe_ratings

    entry = craftsman.create_entry(ref="brioche", name="Brioche", kind="sweet_dough", output_sku="")
    version = craftsman.create_version(
        entry, formula={"anchor": {"kind": "total"}, "items": [], "parts": []}, yield_quantity=1, yield_unit="g",
    )
    criteria = recipe_ratings.active_criteria()
    recipe_ratings.rate("nota-bia", version, {str(criterion.pk): 3 for criterion in criteria})
    call_command("export_backup", "--out", str(tmp_path), stdout=StringIO())
    path = next(tmp_path.glob("backup-*.xlsx"))

    RecipeVersionRatingScore.objects.all().delete()
    call_command("import_backup", str(path), "--apply", stdout=StringIO())

    assert sorted(RecipeVersionRatingScore.objects.values_list("score", flat=True)) == [3] * len(criteria)
