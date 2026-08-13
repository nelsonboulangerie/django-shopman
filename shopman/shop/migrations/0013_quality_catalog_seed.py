# Catálogo inicial de qualidade (ADR-017 §6 / QC-FORNADA §2-§3).
#
# Data migration, não seed: os catálogos são POLÍTICA do deployment e precisam
# existir em qualquer banco migrado (o finish resolve markdown_percent a partir
# deles). O seed pode complementar; o chão não pode depender dele.
#
# Graus: a ordem tem que ser óbvia num relance (rank maior = melhor). O
# percentual é resolvido no finish e congela no lote — editar aqui não
# reescreve lote antigo.
#
# Defeitos: um 2x2 mais três — dois processos (fermentação, forno), cada um com
# dois sentidos. Nenhum carrega severidade: "escuro" e "queimado" são o mesmo
# `overbaked` em graus diferentes. Só `contaminated` veta (segurança alimentar);
# defeito cosmético vende com desconto.

from django.db import migrations

GRADES = [
    # (ref, label, rank, markdown_percent, is_default)
    ("excellent", "Ótima", 40, 0, False),
    ("standard", "Normal", 30, 0, True),
    ("fair", "Razoável", 20, 20, False),
    ("minimal", "Mínima", 10, 50, False),
]

DEFECTS = [
    # (ref, label, hint, forces_discard, position)
    ("underproofed", "Fermentou pouco", "pequeno, denso, rasgou", False, 10),
    ("overproofed", "Fermentou demais", "esparramado, ácido, colapsou", False, 20),
    ("underbaked", "Assou pouco", "pálido, miolo cru", False, 30),
    ("overbaked", "Assou demais", "escuro, casca amarga", False, 40),
    ("misshapen", "Deformado", "torto, colado, fora do padrão", False, 50),
    ("scorch_marks", "Marcas de forno", "fuligem, sujeira de lastro", False, 60),
    ("contaminated", "Contaminado", "matéria estranha — não vende", True, 70),
]


def forwards(apps, schema_editor):
    QualityGrade = apps.get_model("shop", "QualityGrade")
    QualityDefect = apps.get_model("shop", "QualityDefect")
    for ref, label, rank, markdown, is_default in GRADES:
        QualityGrade.objects.update_or_create(
            ref=ref,
            defaults={
                "label": label,
                "rank": rank,
                "markdown_percent": markdown,
                "is_default": is_default,
            },
        )
    for ref, label, hint, forces_discard, position in DEFECTS:
        QualityDefect.objects.update_or_create(
            ref=ref,
            defaults={
                "label": label,
                "hint": hint,
                "forces_discard": forces_discard,
                "position": position,
                "is_active": True,
            },
        )


def backwards(apps, schema_editor):
    QualityGrade = apps.get_model("shop", "QualityGrade")
    QualityDefect = apps.get_model("shop", "QualityDefect")
    QualityGrade.objects.filter(ref__in=[g[0] for g in GRADES]).delete()
    QualityDefect.objects.filter(ref__in=[d[0] for d in DEFECTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0012_qualitydefect_qualitygrade"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
