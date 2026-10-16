"""A Hora da Xepa passa a valer só no balcão (decisão do dono, 14/10/2026, L3=1).

O seed cobre bancos novos; este é o banco vivo. A regra ``happy_hour`` fica
listada só no canal ``pdv``: sai do WhatsApp, e do site e do iFood se algum dia
tiverem entrado. Sem canal ``pdv`` no banco, a regra fica sem canal, e sem canal
ela não vale em lugar nenhum (``HappyHourRule.channels_required``).

Só toca a regra ``happy_hour``. O reverse é inerte: voltar o código não devolve
a Xepa ao WhatsApp.
"""

from django.db import migrations

RULE_REF = "happy_hour"
COUNTER_CHANNEL_REF = "pdv"


def forwards(apps, schema_editor):
    RuleConfig = apps.get_model("shop", "RuleConfig")
    Channel = apps.get_model("shop", "Channel")
    rule = RuleConfig.objects.filter(ref=RULE_REF).first()
    if rule is None:
        return
    rule.channels.set(Channel.objects.filter(ref=COUNTER_CHANNEL_REF))
    # O motor guarda as regras em cache por uma hora (``rules.engine.CACHE_KEY``);
    # o modelo histórico não dispara o sinal que o invalida.
    from django.core.cache import cache

    cache.delete("shopman_rules")


class Migration(migrations.Migration):
    dependencies = [("shop", "0092_avisos_de_estorno_e_devolucao")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
