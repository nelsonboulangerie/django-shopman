# Cenários salvos do B.I. com a métrica de aproveitamento passam a se chamar assim.
#
# O UX-PROD-AF2 (PR #1439) trocou a métrica ``yield_percent`` do explorador de
# "Rendimento" (realizado ÷ planejado) para "Aproveitamento" (realizado ÷ previsto), e o
# exemplo do bi-nuxt virou "Aproveitamento por receita". Decisão do dono (03/10/2026): os
# cenários que os gestores já salvaram (``BIView``) acompanham o vocabulário novo.
#
# Critério, o mesmo nos dois sentidos:
# - só cenários cuja ``config.metric`` é ``yield_percent``; os de outra métrica ficam
#   como estão, mesmo que digam "rendimento";
# - troca só a palavra inteira ("Rendimento"/"rendimento", e o plural), preservando a
#   maiúscula inicial; o resto do nome é do gestor e não muda;
# - pula o cenário quando o nome novo colide com outro do mesmo dono (a restrição
#   ``backstage_biview_owner_name``) ou passa de 80 caracteres: renomear não pode
#   apagar nem truncar o que o gestor salvou.
#
# A volta desfaz pela mesma regra (aproveitamento → rendimento, só em ``yield_percent``).
# "Rendimento" da ficha técnica e da massa não mora em ``BIView`` e não é tocado.

import re

from django.db import migrations

METRIC = "yield_percent"
NAME_MAX_LENGTH = 80


def _word_swap(old: str, new: str):
    pattern = re.compile(rf"\b([{old[0].upper()}{old[0]}]){old[1:]}(s?)\b")

    def replace(text: str) -> str:
        def sub(match):
            head = new[0].upper() if match.group(1).isupper() else new[0]
            return f"{head}{new[1:]}{match.group(2)}"

        return pattern.sub(sub, text)

    return replace


FORWARDS = _word_swap("rendimento", "aproveitamento")
BACKWARDS = _word_swap("aproveitamento", "rendimento")


def _rename(apps, swap):
    BIView = apps.get_model("backstage", "BIView")
    for view in BIView.objects.filter(config__metric=METRIC).order_by("pk"):
        name = swap(view.name)
        if name == view.name or len(name) > NAME_MAX_LENGTH:
            continue
        if BIView.objects.filter(owner_id=view.owner_id, name=name).exclude(pk=view.pk).exists():
            continue
        view.name = name
        view.save(update_fields=["name"])


def forwards(apps, schema_editor):
    _rename(apps, FORWARDS)


def backwards(apps, schema_editor):
    _rename(apps, BACKWARDS)


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0081_workstation"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
