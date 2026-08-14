"""BIView — cenário salvo do explorador de B.I. (F9).

Um cenário é CONFIG, zero código: `{metric, by, by2, window}` validado pela
MESMA gramática do explorador na borda da API (config fora da gramática não
salva — regra da casa). Favorito sobe no menu; o dono é quem salvou.
"""

from __future__ import annotations

from django.db import models


class BIView(models.Model):
    owner = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="bi_views", verbose_name="dono"
    )
    name = models.CharField("nome", max_length=80)
    config = models.JSONField(
        "configuração",
        help_text="{metric, by, by2, window} — validado pela gramática do explorador.",
    )
    is_favorite = models.BooleanField("favorito", default=False)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "cenário de B.I."
        verbose_name_plural = "cenários de B.I."
        ordering = ["-is_favorite", "name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="backstage_biview_owner_name"),
        ]

    def __str__(self):
        return f"{self.name} ({self.owner})"
