"""O "Separado" da Preparação: a marca de conferência que vale para a bancada inteira.

Quem separa os insumos do dia marca cada um como separado. Até o WP-F09a a marca
vivia no ``localStorage`` do tablet, presa ao hash da projeção inteira: outro
tablet não via, e qualquer mudança na tela (ligar "Mostrar ingredientes dos
pré-preparos", uma entrada de estoque) apagava tudo. Decisão do dono (D-042, item
5): a marca mora no servidor e vale para todos os tablets do dia.

A chave é o **item e a data**, nunca a tela:

* ``<sku>`` é uma linha da lista de separação ("Por insumo");
* ``<recipe_ref>/<sku>`` é o ingrediente de um preparo ("Por preparo").

A marca guarda a **quantidade** que a pessoa separou, como a tela mostrou. Ela vale
enquanto essa quantidade for a do momento; quando a quantidade daquele item muda
(o plano cresceu, um lote saiu), a marca cai, e só então. Quem decide se ainda vale
é ``services.prep_checklist``, que lê a Preparação atual.

Uma linha por (dia, item). Desmarcar grava (``checked=False``) e a história de cada
gesto fica em ``history``: quem marcou, quem desmarcou, a quantidade e a hora.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class PrepChecklistMark(models.Model):
    prep_date = models.DateField("dia da preparação", db_index=True)
    item_ref = models.CharField("item", max_length=220)
    #: A quantidade separada, exatamente como a Preparação a mostrou ("1,250 kg").
    quantity = models.CharField("quantidade separada", max_length=60)
    checked = models.BooleanField("separado", default=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="último gesto de",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: O nome de quem fez o último gesto, como a tela o mostra. Fica gravado para que
    #: a marca continue dizendo quem separou mesmo depois que a conta sair.
    marked_by_name = models.CharField("nome de quem fez o último gesto", max_length=150, blank=True)
    marked_at = models.DateTimeField("último gesto em")
    #: Cada gesto, do mais antigo ao mais novo: ``{"checked", "quantity", "by", "at"}``.
    history = models.JSONField("história", default=list, blank=True)

    class Meta:
        verbose_name = "marca de separado da preparação"
        verbose_name_plural = "marcas de separado da preparação"
        ordering = ["-prep_date", "item_ref"]
        constraints = [
            models.UniqueConstraint(
                fields=["prep_date", "item_ref"],
                name="backstage_prep_checklist_one_per_item_day",
            ),
        ]

    def __str__(self) -> str:
        state = "separado" if self.checked else "desmarcado"
        return f"{self.item_ref} em {self.prep_date:%d/%m/%Y}: {state} ({self.quantity})"
