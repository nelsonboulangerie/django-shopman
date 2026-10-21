from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("shop", "0104_fichas_na_hora_vigentes")]
    operations = [migrations.DeleteModel(name="RetiredProduct")]
