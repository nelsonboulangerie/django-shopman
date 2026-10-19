"""O Happy Hour passa a exigir janela e percentual no ``RuleConfig.params`` (A7-2).

Até aqui ``modifiers.py`` completava o que faltasse nos params com 25%, 17:30 e
18:00 (e um horário ilegível também virava 17:30/18:00). O código não completa
mais nada: sem params a regra falha fechada. Esta migração grava no banco, de uma
vez, exatamente o que o fallback fazia valer, para que o comportamento não mude:
chave ausente ou horário ilegível recebe o valor que estava em vigor.

Idempotente: params que já têm as três chaves válidas não são tocados. Os valores
abaixo são a cópia congelada do fallback retirado (migração representa um momento
do banco, não muda de sentido quando o código muda). O reverse é inerte.
"""

from datetime import time

from django.db import migrations

RULE_REF = "happy_hour"
FROZEN_FALLBACK = {"discount_percent": 25, "start": "17:30", "end": "18:00"}


def _valid_time(value) -> bool:
    try:
        h, m = map(int, str(value).split(":"))
        time(h, m)
    except (ValueError, TypeError):
        return False
    return True


def _hhmm(value) -> str:
    h, m = map(int, str(value).split(":"))
    return f"{h:02d}:{m:02d}"


def forwards(apps, schema_editor):
    RuleConfig = apps.get_model("shop", "RuleConfig")
    for rule in RuleConfig.objects.filter(ref=RULE_REF):
        params = dict(rule.params or {})
        changed = dict(params)
        if "discount_percent" not in changed:
            changed["discount_percent"] = FROZEN_FALLBACK["discount_percent"]
        for key in ("start", "end"):
            raw = changed.get(key)
            # O fallback antigo: vazio ou ilegível valia o horário congelado.
            changed[key] = _hhmm(raw) if raw and _valid_time(raw) else FROZEN_FALLBACK[key]
        if changed != params:
            rule.params = changed
            rule.save(update_fields=["params"])
    # O motor guarda as regras em cache (``rules.engine.CACHE_KEY``); o modelo
    # histórico não dispara o sinal que o invalida.
    from django.core.cache import cache

    cache.delete("shopman_rules")


class Migration(migrations.Migration):
    dependencies = [("shop", "0098_instance_apply_record")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
