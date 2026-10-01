"""Receita favorita do operador: a estrela no inventário do app de Produção.

O molde é o favorito do cliente (``storefront.CustomerFavorite``) com os eixos
trocados: quem marca é o operador (``operator_ref`` = o ``username`` dele, o
mesmo identificador que o inventário grava em ``RecipeVersion.created_by``) e
o que se marca é a receita do inventário (``entry_ref`` = ``RecipeEntry.ref``).

É preferência de quem usa a tela, não curadoria da casa: não muda nada na
receita, não aparece para outro operador e não entra no cofre de dados
(``shop/backup/resources.py``). Perder estas linhas custa refazer meia dúzia de
toques, não conhecimento.
"""

from __future__ import annotations

from django.db import models


class OperatorRecipeFavorite(models.Model):
    operator_ref = models.CharField("operador", max_length=150, db_index=True)
    entry_ref = models.CharField("receita", max_length=50)
    created_at = models.DateTimeField("marcada em", auto_now_add=True)

    class Meta:
        app_label = "backstage"
        verbose_name = "receita favorita"
        verbose_name_plural = "receitas favoritas"
        constraints = [
            models.UniqueConstraint(
                fields=["operator_ref", "entry_ref"], name="uniq_operator_recipe_favorite"
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"{self.operator_ref} · {self.entry_ref}"
