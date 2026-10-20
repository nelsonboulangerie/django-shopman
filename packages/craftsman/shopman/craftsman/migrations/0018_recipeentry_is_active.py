from django.db import migrations, models


def invert_active(apps, schema_editor):
    recipe_entry = apps.get_model("craftsman", "RecipeEntry")
    table = schema_editor.quote_name(recipe_entry._meta.db_table)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET is_active = NOT is_active")


class Migration(migrations.Migration):
    dependencies = [("craftsman", "0017_abertura_fechamento_labels")]

    operations = [
        migrations.RenameField(
            model_name="recipeentry",
            old_name="is_archived",
            new_name="is_active",
        ),
        migrations.RunPython(invert_active, invert_active),
        migrations.AlterField(
            model_name="recipeentry",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="Ativa"),
        ),
    ]
