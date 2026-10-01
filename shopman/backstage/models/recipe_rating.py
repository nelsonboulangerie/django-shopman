"""Nota de 0 a 5 que o operador dá a uma versão de receita, por critério.

Dois desenhos da casa, juntos:

- Os **critérios** são catálogo editável no Admin, no molde do ``QualityGrade``
  (``shop/models/quality.py``): nome, descrição, ordem e ativo, sem critério fixo
  em código. A migração ``backstage.0080`` semeia "Sabor", "Textura" e
  "Aparência"; o gestor renomeia, reordena ou desativa. Critério não se apaga
  (há notas apontando para ele): desativa-se, e a nota antiga fica no histórico.
- A **nota** é de uma VERSÃO, como a reputação por versão (#1310): a receita
  muda entre versões, e a nota da v1 não diz nada da v2. É um registro SEPARADO
  que aponta para ela, nunca um campo dela (o Core não conhece nota). O
  apontamento é por ``entry_ref`` + ``version_number`` (o carimbo ``<ref>@<n>``),
  como a Favorita (#1319) aponta por ``entry_ref``. Rascunho também recebe nota
  (D24). Apagar a versão apaga as notas dela
  (``services.recipe_ratings.forget_deleted_version``, ligado no ``apps.py``), para que o próximo rascunho, que pode herdar o mesmo número, não
  nasça com a nota de outra fórmula.

Uma nota por operador e versão: avaliar de novo substitui a anterior (a
conta da média não pesa quem avalia mais vezes). Quem avaliou e quando ficam
gravados (``operator_ref``, ``created_at``, ``updated_at``).
"""

from __future__ import annotations

from django.db import models

#: A escala da nota: inteira, de 0 a 5.
RATING_MIN = 0
RATING_MAX = 5


class RecipeRatingCriterion(models.Model):
    """Um eixo da nota de receita ("Sabor", "Textura", "Aparência")."""

    name = models.CharField("nome", max_length=60, unique=True)
    description = models.CharField(
        "descrição",
        max_length=200,
        blank=True,
        default="",
        help_text="O que o operador olha para dar a nota. Aparece embaixo do nome, na tela de avaliar.",
    )
    position = models.IntegerField("ordem", default=0)
    is_active = models.BooleanField(
        "ativo",
        default=True,
        help_text="Critério inativo sai da tela de avaliar e das médias; as notas antigas ficam guardadas.",
    )

    class Meta:
        app_label = "backstage"
        verbose_name = "critério da nota de receita"
        verbose_name_plural = "critérios da nota de receita"
        ordering = ("position", "name")

    def __str__(self) -> str:
        return self.name


class RecipeVersionRating(models.Model):
    """A avaliação de UM operador sobre UMA versão fechada de receita."""

    entry_ref = models.CharField("receita", max_length=50, db_index=True)
    version_number = models.PositiveIntegerField("versão")
    operator_ref = models.CharField("operador", max_length=150)
    created_at = models.DateTimeField("avaliada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        app_label = "backstage"
        verbose_name = "nota de receita"
        verbose_name_plural = "notas de receita"
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["entry_ref", "version_number", "operator_ref"],
                name="uniq_recipe_version_rating_per_operator",
            ),
        ]

    @property
    def version_ref(self) -> str:
        return f"{self.entry_ref}@{self.version_number}"

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"{self.version_ref} · {self.operator_ref}"


class RecipeVersionRatingScore(models.Model):
    """A nota de um critério dentro de uma avaliação."""

    rating = models.ForeignKey(
        RecipeVersionRating, on_delete=models.CASCADE, related_name="scores", verbose_name="avaliação",
    )
    criterion = models.ForeignKey(
        RecipeRatingCriterion, on_delete=models.PROTECT, related_name="scores", verbose_name="critério",
    )
    score = models.PositiveSmallIntegerField("nota")

    class Meta:
        app_label = "backstage"
        verbose_name = "nota por critério"
        verbose_name_plural = "notas por critério"
        ordering = ("criterion__position", "criterion__name")
        constraints = [
            models.UniqueConstraint(fields=["rating", "criterion"], name="uniq_recipe_rating_score_per_criterion"),
            models.CheckConstraint(
                condition=models.Q(score__gte=RATING_MIN, score__lte=RATING_MAX),
                name="recipe_rating_score_between_0_and_5",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"{self.criterion} {self.score}"
