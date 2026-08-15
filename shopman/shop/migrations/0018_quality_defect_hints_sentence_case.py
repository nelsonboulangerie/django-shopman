# Sentence case nas dicas dos defeitos de QC.
#
# O ``hint`` é a segunda linha do botão no fechamento de QC (production-nuxt): abre
# uma linha visual sozinho, então começa com maiúscula, como todo copy de UI que
# abre linha. A 0013 é intocável (migrações são append-only desde o reset de
# 2026-08); esta só reescreve as linhas que ainda carregam o texto original — o
# que o operador editou no Admin fica como está.

from django.db import migrations

HINTS = {
    # ref: (antes, depois)
    "underproofed": ("pequeno, denso, rasgou", "Pequeno, denso, rasgou"),
    "overproofed": ("esparramado, ácido, colapsou", "Esparramado, ácido, colapsou"),
    "underbaked": ("pálido, miolo cru", "Pálido, miolo cru"),
    "overbaked": ("escuro, casca amarga", "Escuro, casca amarga"),
    "misshapen": ("torto, colado, fora do padrão", "Torto, colado, fora do padrão"),
    "scorch_marks": ("fuligem, sujeira de lastro", "Fuligem, sujeira de lastro"),
    "contaminated": ("matéria estranha — não vende", "Matéria estranha — não vende"),
}


def _rewrite(apps, direction):
    QualityDefect = apps.get_model("shop", "QualityDefect")
    for ref, (old, new) in HINTS.items():
        source, target = (old, new) if direction == "forwards" else (new, old)
        QualityDefect.objects.filter(ref=ref, hint=source).update(hint=target)


def forwards(apps, schema_editor):
    _rewrite(apps, "forwards")


def backwards(apps, schema_editor):
    _rewrite(apps, "backwards")


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0017_ruleconfig_help_text_example"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
