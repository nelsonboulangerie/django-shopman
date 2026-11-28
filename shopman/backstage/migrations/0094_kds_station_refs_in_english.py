"""As estações do KDS do seed passam a ter ref em inglês (beta test, 07/11/2026).

O ref da estação é o caminho da bancada no kds-nuxt (``/<ref>``), e URL de
operador é em inglês (CLAUDE.md). O seed gravava ``lanches``, ``cafes``,
``encomendas`` e ``saida``; o NOME da estação (o que o operador lê) não muda.

Pré go-live, rota renomeada não ganha redirect: o endereço antigo morre junto.
Conservadora, como a ``0076``: só renomeia quando o ref novo ainda não existe
(se as duas existem, alguém criou a nova à mão, e apagar a antiga seria decisão
do gestor).
"""

from django.db import migrations

RENAMES = (
    ("lanches", "snacks"),
    ("cafes", "coffee"),
    ("encomendas", "preorders"),
    ("saida", "exit"),
)


def _rename(apps, pairs):
    KDSInstance = apps.get_model("backstage", "KDSInstance")
    for old_ref, new_ref in pairs:
        if KDSInstance.objects.filter(ref=new_ref).exists():
            continue
        KDSInstance.objects.filter(ref=old_ref).update(ref=new_ref)


def rename_to_english(apps, schema_editor):
    _rename(apps, RENAMES)


def restore_portuguese(apps, schema_editor):
    _rename(apps, tuple((new, old) for old, new in RENAMES))


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0093_kdsticket_inicio_do_preparo"),
    ]

    operations = [
        migrations.RunPython(rename_to_english, restore_portuguese),
    ]
