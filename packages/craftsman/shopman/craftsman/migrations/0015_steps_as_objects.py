"""Etapas passam de texto para objeto: ``"Mistura"`` vira ``{"name": "Mistura"}``.

``Recipe.steps`` e ``RecipeVersion.steps`` ganham forma única
(``shopman.craftsman.recipe_steps``): ``{name, instructions?, target_seconds?,
note?}``. O que já está gravado é lista de textos; esta migração reescreve cada
texto como ``{"name": texto}`` para que o banco tenha UMA forma e nenhum leitor
precise aceitar as duas. Texto vazio sai (o ``Recipe.clean`` antigo já o
recusava; a versão não conferia). Elemento que não seja texto nem objeto para a
migração gritando, em vez de virar uma etapa inventada.

``updated_at`` não muda: é a mesma etapa em outra forma, não uma edição.

A volta reescreve cada objeto como o seu ``name`` (perde instruções, tempo e
anotação, que não existiam antes desta migração).

Fora daqui, de propósito: ``WorkOrder.meta["_recipe_snapshot"]["production"]["steps"]``.
É cópia congelada no plano da fornada, ninguém a lê, e regravar o ``meta`` de
fornada viva disputaria escrita com o worker. Ordens planejadas antes desta
migração carregam a lista de textos; as novas copiam a ficha já em objeto.
"""

from django.db import migrations, models

BATCH_SIZE = 500


def _as_objects(steps, *, label):
    if steps is None:
        return []
    if not isinstance(steps, list):
        # Texto solto aqui viraria uma etapa por LETRA no laço abaixo; objeto,
        # uma etapa por chave. Nenhum dos dois é etapa: para gritando.
        raise ValueError(f"{label}: etapas não são lista ({type(steps).__name__}: {steps!r}).")
    out = []
    for index, step in enumerate(steps):
        if isinstance(step, dict):
            out.append(step)
        elif isinstance(step, str):
            if step.strip():
                out.append({"name": step.strip()})
        else:
            raise ValueError(f"{label}: etapa {index + 1} não é texto nem objeto ({step!r}).")
    return out


def _as_names(steps, *, label):
    out = []
    for step in steps or []:
        out.append(step["name"] if isinstance(step, dict) else step)
    return out


def _rewrite(apps, model_name, convert):
    Model = apps.get_model("craftsman", model_name)
    pending = []
    for row in Model.objects.only("pk", "steps").iterator(chunk_size=BATCH_SIZE):
        new = convert(row.steps, label=f"{model_name} {row.pk}")
        if new == row.steps:
            continue
        row.steps = new
        pending.append(row)
        if len(pending) >= BATCH_SIZE:
            Model.objects.bulk_update(pending, ["steps"])
            pending = []
    if pending:
        Model.objects.bulk_update(pending, ["steps"])


def forwards(apps, schema_editor):
    for model_name in ("Recipe", "RecipeVersion"):
        _rewrite(apps, model_name, _as_objects)


def backwards(apps, schema_editor):
    for model_name in ("Recipe", "RecipeVersion"):
        _rewrite(apps, model_name, _as_names)


class Migration(migrations.Migration):

    dependencies = [
        ("craftsman", "0014_default_unit_gram"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recipe",
            name="steps",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    'Etapas de produção. Ex: [{"name": "Fermentação", "instructions": "Até dobrar de volume.", '
                    '"target_seconds": 5400}]'
                ),
                verbose_name="Etapas",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
