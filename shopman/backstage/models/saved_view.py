"""SavedView — a leitura salva de uma tela de operador (o "favorito" do painel de filtros).

Generaliza o antigo ``BIView`` (os cenários do explorador do B.I.) para qualquer
superfície e tela (WP-FASE2-UX-OPERADOR, K4): o recorte que a pessoa montou numa tela
(filtros, período, agrupamento; no explorador do B.I., a métrica e os eixos) ganha um
nome e volta com um toque. É CONFIG, zero código: a borda da API valida o ``query``
pela gramática da tela (``api/saved_views.py``); recorte fora dela não salva.

Por pessoa (decisão do dono, 09/10/2026, pergunta 2: "por pessoa, e o gerente publica
para a equipe", podendo nascer só por pessoa). ``pinned`` põe o favorito entre os
filtros rápidos da tela (no B.I., no topo do menu de cenários).
"""

from __future__ import annotations

from django.db import models


class SavedView(models.Model):
    owner = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="saved_views", verbose_name="dono"
    )
    surface = models.CharField(
        "superfície", max_length=32, help_text="O app de operador: orders, bi, …"
    )
    screen = models.CharField(
        "tela", max_length=40, help_text="A tela do app: queue, history, catalog, explore, …"
    )
    name = models.CharField("nome", max_length=80)
    query = models.JSONField(
        "recorte", help_text="O recorte da tela, validado pela gramática dela na borda da API."
    )
    pinned = models.BooleanField(
        "fixado", default=False, help_text="Aparece entre os filtros rápidos da tela."
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "leitura salva"
        verbose_name_plural = "leituras salvas"
        ordering = ["-pinned", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "surface", "screen", "name"],
                name="backstage_savedview_owner_screen_name",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "surface", "screen"], name="backstage_savedview_screen"),
        ]

    def __str__(self):
        return f"{self.name} ({self.surface}/{self.screen}, {self.owner})"
