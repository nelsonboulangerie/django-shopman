import re
from urllib.parse import urlparse

import django.core.validators
from django.conf import settings
from django.db import migrations, models

_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")


def _host_from_deploy(apps, schema_editor):
    """Uma vez só: a loja que já existe herda o host que o deploy usava para os links.

    Daqui em diante o host é dado da loja (ADR-042) e se edita no Admin; o settings
    não é mais lido para isto. Sem base de deploy, ou base sem domínio (localhost),
    o campo fica vazio e o SMS sai sem a linha do WebOTP.
    """
    base = (getattr(settings, "SHOPMAN_STOREFRONT_BASE_URL", "") or "").strip()
    host = (urlparse(base).hostname or "").lower() if base else ""
    if not _HOST.match(host):
        return
    Shop = apps.get_model("shop", "Shop")
    Shop.objects.filter(storefront_host="").update(storefront_host=host)


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0105_remove_retiredproduct"),
    ]

    operations = [
        migrations.AddField(
            model_name="shop",
            name="storefront_host",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Só o domínio onde o cliente abre a loja, sem https:// e sem barra. Ex.: "
                    "www.minhaloja.com.br. Vai no fim do SMS de código, para o celular do cliente "
                    "preencher o código sozinho."
                ),
                max_length=253,
                validators=[
                    django.core.validators.RegexValidator(
                        "^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$",
                        "Só o domínio, em minúsculas, sem https:// e sem barra. Ex.: www.minhaloja.com.br",
                    )
                ],
                verbose_name="endereço da loja na internet",
            ),
        ),
        migrations.RunPython(_host_from_deploy, migrations.RunPython.noop),
    ]
