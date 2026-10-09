# A leitura salva de qualquer tela de operador (``SavedView``) toma o lugar do ``BIView``.
#
# WP-FASE2-UX-OPERADOR, K4: o favorito do painel de filtros é por pessoa, por superfície
# e por tela. O B.I. já tinha favoritos (os cenários do explorador, ``BIView``); eles
# passam para o modelo genérico sem perder nenhum: cada cenário vira uma leitura salva
# de ``bi``/``explore``, com o mesmo dono, o mesmo nome, a config como ``query`` e o
# favorito como ``pinned``. Depois o ``BIView`` sai (pré go-live, sem legado).
#
# A volta recria os cenários a partir das leituras de ``bi``/``explore``.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

SURFACE = "bi"
SCREEN = "explore"


def bi_views_to_saved_views(apps, schema_editor):
    BIView = apps.get_model("backstage", "BIView")
    SavedView = apps.get_model("backstage", "SavedView")
    SavedView.objects.bulk_create(
        [
            SavedView(
                owner_id=view.owner_id,
                surface=SURFACE,
                screen=SCREEN,
                name=view.name,
                query=view.config,
                pinned=view.is_favorite,
            )
            for view in BIView.objects.order_by("pk")
        ]
    )


def saved_views_to_bi_views(apps, schema_editor):
    BIView = apps.get_model("backstage", "BIView")
    SavedView = apps.get_model("backstage", "SavedView")
    BIView.objects.bulk_create(
        [
            BIView(
                owner_id=view.owner_id,
                name=view.name,
                config=view.query,
                is_favorite=view.pinned,
            )
            for view in SavedView.objects.filter(surface=SURFACE, screen=SCREEN).order_by("pk")
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("backstage", "0089_alerta_responder_ate"),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("surface", models.CharField(help_text="O app de operador: orders, bi, …", max_length=32, verbose_name="superfície")),
                ("screen", models.CharField(help_text="A tela do app: queue, history, catalog, explore, …", max_length=40, verbose_name="tela")),
                ("name", models.CharField(max_length=80, verbose_name="nome")),
                ("query", models.JSONField(help_text="O recorte da tela, validado pela gramática dela na borda da API.", verbose_name="recorte")),
                ("pinned", models.BooleanField(default=False, help_text="Aparece entre os filtros rápidos da tela.", verbose_name="fixado")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_views",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="dono",
                    ),
                ),
            ],
            options={
                "verbose_name": "leitura salva",
                "verbose_name_plural": "leituras salvas",
                "ordering": ["-pinned", "name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("owner", "surface", "screen", "name"),
                        name="backstage_savedview_owner_screen_name",
                    )
                ],
                "indexes": [
                    models.Index(fields=["owner", "surface", "screen"], name="backstage_savedview_screen"),
                ],
            },
        ),
        migrations.RunPython(bi_views_to_saved_views, saved_views_to_bi_views),
        migrations.DeleteModel(name="BIView"),
    ]
