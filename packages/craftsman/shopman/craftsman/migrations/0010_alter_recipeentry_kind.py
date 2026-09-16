from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("craftsman", "0009_alter_workorderevent_kind")]

    operations = [
        migrations.AlterField(
            model_name="recipeentry",
            name="kind",
            field=models.CharField(
                choices=[
                    ("bread", "Pão"),
                    ("viennoiserie", "Viennoiserie"),
                    ("sweet_dough", "Massa doce"),
                    ("cookie", "Biscoito"),
                    ("filling", "Recheio"),
                    ("cream", "Creme"),
                    ("sauce", "Molho"),
                    ("beverage", "Bebida"),
                    ("other", "Outra"),
                ],
                default="other",
                max_length=20,
                verbose_name="Tipo",
            ),
        ),
    ]
