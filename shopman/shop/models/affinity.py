"""O que a casa vende junto — co-ocorrência do histórico, calculada de noite.

A regra de adicional que estava no ar ("o item mais popular que não está na
sacola") ofereceu **Água** a quem levava pão. Popularidade não é afinidade: a
água é o item mais vendido da casa e por isso seria oferecida a todo mundo, o
dia inteiro, para sempre.

O sinal que responde "o que combina com isto" é a cesta: dois anos de vendas
dizem que quem leva Baguette leva café, e nenhum humano precisou escrever essa
regra. Esta tabela guarda esse aprendizado, e **nada dela é calculado na hora do
pedido** — quem escreve é o ``compute_product_affinity``, no worker de
manutenção.

⚠️ **Lift, não contagem.** A contagem crua elegeria a água de novo: ela aparece
com tudo porque aparece com tudo. O *lift* pergunta outra coisa — "este par
acontece mais do que aconteceria por acaso?" — e é isso que separa
"combina com" de "vende muito".

⚠️ **Par raro não vira regra.** Duas cestas com o mesmo par produzem um lift
altíssimo e sem sentido. O piso de suporte (``together_count``) existe para que
ruído não vire sugestão.

O par é gravado nos dois sentidos (a→b e b→a). Custa o dobro de linhas num
catálogo de centenas de SKUs — nada — e poupa toda leitura de um ``OR`` sobre
duas colunas.
"""

from __future__ import annotations

from django.db import models


class ProductAffinity(models.Model):
    """Quanto ``sku_b`` combina com ``sku_a``, segundo o histórico."""

    sku_a = models.CharField("sku", max_length=64, db_index=True)
    sku_b = models.CharField("sku par", max_length=64)

    together_count = models.PositiveIntegerField(
        "cestas em comum",
        help_text="Cestas cruas que trazem os dois. É o piso de suporte, não o peso.",
    )
    score = models.FloatField(
        "co-ocorrência com peso",
        help_text="Cestas em comum, com a cesta de ontem pesando mais que a do ano passado.",
    )
    lift = models.FloatField(
        "lift",
        help_text=(
            "Quantas vezes o par acontece mais do que aconteceria por acaso. "
            "Acima de 1 é afinidade; perto de 1 é coincidência."
        ),
    )

    window_days = models.PositiveIntegerField("janela (dias)")
    computed_at = models.DateTimeField("calculado em", db_index=True)

    class Meta:
        verbose_name = "afinidade entre produtos"
        verbose_name_plural = "afinidades entre produtos"
        ordering = ["sku_a", "-lift"]
        constraints = [
            models.UniqueConstraint(fields=["sku_a", "sku_b"], name="shop_affinity_pair"),
        ]
        indexes = [
            models.Index(fields=["sku_a", "-lift"], name="shop_affinity_a_lift_idx"),
        ]

    def __str__(self):
        return f"{self.sku_a} → {self.sku_b} (lift {self.lift:.2f})"
