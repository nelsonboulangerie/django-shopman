"""Os atalhos da nota da cozinha, com o "vale para" de cada um.

O Caixa anexa um atalho com um toque à nota da cozinha de um pedido no Gestor ("Bem
assado", "Sem cebola"); a nota sai no ticket da Cozinha. Cada atalho diz a que
produtos se aplica, por coleção (a categoria do cardápio) e/ou por produto: o pedido
mostra só os atalhos que valem para algum item dele. Sem coleção e sem produto, vale
para todos (decisão do dono, 21/11/2026: "Sem cebola" num pedido de pão não ajuda
ninguém).
"""

from __future__ import annotations

from django.db import models


class KitchenNoteTag(models.Model):
    label = models.CharField("atalho", max_length=60, unique=True, help_text="O texto que entra na nota, como \"Bem assado\".")
    position = models.PositiveIntegerField("ordem", default=0, help_text="A ordem dos atalhos no pedido.")
    collections = models.ManyToManyField(
        "offerman.Collection",
        blank=True,
        related_name="+",
        verbose_name="categorias",
        help_text="O atalho aparece no pedido que tem algum produto destas categorias.",
    )
    products = models.ManyToManyField(
        "offerman.Product",
        blank=True,
        related_name="+",
        verbose_name="produtos",
        help_text="O atalho aparece no pedido que tem algum destes produtos. Sem categoria e sem produto, vale para todos.",
    )

    class Meta:
        app_label = "shop"
        ordering = ("position", "label")
        verbose_name = "atalho da nota da cozinha"
        verbose_name_plural = "atalhos da nota da cozinha"

    def __str__(self) -> str:
        return self.label
