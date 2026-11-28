from django.db import migrations


def _version_ref(entry) -> str:
    current = getattr(entry, "current_version", None)
    return "" if current is None else f"{entry.ref}@{current.number}"


def forwards(apps, schema_editor) -> None:
    RecipeEntry = apps.get_model("craftsman", "RecipeEntry")
    RecipeVersion = apps.get_model("craftsman", "RecipeVersion")
    by_ref = {entry.ref: entry for entry in RecipeEntry.objects.select_related("current_version")}
    by_sku = {
        entry.output_sku: entry
        for entry in RecipeEntry.objects.select_related("current_version")
        if entry.output_sku
    }
    for version in RecipeVersion.objects.select_related("entry").exclude(formula={}).iterator(chunk_size=200):
        formula = dict(version.formula or {})
        if "ingredients" in formula:
            continue
        ingredients = []
        for item in list(formula.pop("items", []) or []):
            item = dict(item)
            value, unit = item.pop("quantity", None), item.pop("unit", "g")
            entry = by_sku.get(str(item.get("sku") or ""))
            ingredients.append({
                "ref": f"ingredient-{len(ingredients) + 1}",
                **item,
                "recipe_version_ref": _version_ref(entry) if entry else "",
                "composition": "additional",
                "quantity": {
                    "kind": "fixed", "minimum": value, "target": value,
                    "maximum": value, "unit": unit,
                },
            })
        for prepared in list(formula.pop("preps", formula.pop("parts", [])) or []):
            prepared = dict(prepared)
            if prepared.get("kind") == "old_dough":
                value = prepared.get("cap_pct")
                ingredients.append({
                    "ref": f"ingredient-{len(ingredients) + 1}",
                    "sku": f"MASSA-VELHA-{version.entry.output_sku}"[:100],
                    "name": f"Massa velha de {version.entry.name}",
                    "role": "other",
                    "recipe_version_ref": f"{version.entry.ref}@{version.number}",
                    "composition": "included",
                    "quantity": {
                        "kind": "ratio", "minimum": None, "target": value,
                        "maximum": value, "basis": {"kind": "total"},
                    },
                })
                continue
            entry = by_ref.get(str(prepared.get("entry_ref") or "")) or by_sku.get(str(prepared.get("sku") or ""))
            percent = prepared.get("flour_pct")
            if percent not in (None, ""):
                quantity = {
                    "kind": "ratio", "minimum": percent, "target": percent,
                    "maximum": percent, "basis": {"kind": "flour"},
                }
            else:
                value, unit = prepared.get("quantity"), prepared.get("unit") or "g"
                quantity = {
                    "kind": "fixed", "minimum": value, "target": value,
                    "maximum": value, "unit": unit,
                }
            ingredients.append({
                "ref": f"ingredient-{len(ingredients) + 1}",
                "sku": str(prepared.get("sku") or ""),
                "name": str(prepared.get("name") or prepared.get("sku") or ""),
                "role": "other",
                "recipe_version_ref": _version_ref(entry) if entry else "",
                "composition": "included",
                "quantity": quantity,
            })
        formula["ingredients"] = ingredients
        version.formula = formula
        version.save(update_fields=["formula"])


def backwards(apps, schema_editor) -> None:
    RecipeVersion = apps.get_model("craftsman", "RecipeVersion")
    for version in RecipeVersion.objects.exclude(formula={}).iterator(chunk_size=200):
        formula = dict(version.formula or {})
        if "ingredients" not in formula:
            continue
        items, preps = [], []
        for ingredient in list(formula.pop("ingredients", []) or []):
            ingredient = dict(ingredient)
            ingredient.pop("ref", None)
            quantity = dict(ingredient.pop("quantity", {}) or {})
            composition = ingredient.pop("composition", "additional")
            recipe_ref = ingredient.pop("recipe_version_ref", "")
            if composition == "included":
                if str(ingredient.get("sku") or "").startswith("MASSA-VELHA-"):
                    preps.append({"kind": "old_dough", "cap_pct": quantity.get("maximum")})
                else:
                    prep = {
                        "sku": ingredient.get("sku", ""), "name": ingredient.get("name", ""),
                        "entry_ref": recipe_ref.rsplit("@", 1)[0] if "@" in recipe_ref else "",
                        "kind": "preferment",
                    }
                    if quantity.get("kind") == "ratio":
                        prep["flour_pct"] = quantity.get("target")
                    else:
                        prep.update(quantity=quantity.get("target"), unit=quantity.get("unit") or "g")
                    preps.append(prep)
            else:
                ingredient.update(quantity=quantity.get("target"), unit=quantity.get("unit") or "g")
                items.append(ingredient)
        formula["items"], formula["preps"] = items, preps
        version.formula = formula
        version.save(update_fields=["formula"])


class Migration(migrations.Migration):
    dependencies = [("craftsman", "0019_recipe_production_mode")]

    operations = [migrations.RunPython(forwards, backwards)]
