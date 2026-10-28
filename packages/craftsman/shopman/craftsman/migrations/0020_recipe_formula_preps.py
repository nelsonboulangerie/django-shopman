from django.db import migrations


def rename_formula_collection(apps, schema_editor, *, source: str, target: str) -> None:
    RecipeVersion = apps.get_model("craftsman", "RecipeVersion")
    for version in RecipeVersion.objects.exclude(formula={}).iterator(chunk_size=200):
        formula = dict(version.formula or {})
        if source not in formula:
            continue
        formula[target] = formula.pop(source)
        version.formula = formula
        version.save(update_fields=["formula"])


def forwards(apps, schema_editor) -> None:
    rename_formula_collection(apps, schema_editor, source="parts", target="preps")


def backwards(apps, schema_editor) -> None:
    rename_formula_collection(apps, schema_editor, source="preps", target="parts")


class Migration(migrations.Migration):
    dependencies = [("craftsman", "0019_recipe_production_mode")]

    operations = [migrations.RunPython(forwards, backwards)]
