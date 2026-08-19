"""Lote de importação — a camada de ingestão do B.I. tem memória.

Toda fonte externa entra por lote: um arquivo, um hash, uma data, uma contagem.
Sem isto o histórico é idempotente por chave natural mas amnésico — ninguém
sabe **qual** arquivo entrou, **quando**, com **quantas** linhas, nem se o export
mudou de forma entre versões (BI-DATA-FOUNDATION-PLAN §2.1, P0).

Duas regras que este model impõe e o importador obedece:

- **O mesmo arquivo não entra duas vezes.** A restrição vale entre lotes
  concluídos (``status=done``): reimportar o mesmo hash é recusa declarada, não
  silêncio nem duplicação. Um lote que falhou não trava a nova tentativa.
- **Fonte externa aterrissa; ledger nativo é lido no lugar.** Só o que vem de
  fora tem lote: `Order`, `Move`, `cashman.Entry` nunca passam por aqui.

⚠️ O lote registra o que aconteceu, inclusive quando deu errado (``failed`` +
``error``): importação que falha em silêncio é a origem de "o número está
estranho" três semanas depois.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        DONE = "done", "concluído"
        FAILED = "failed", "falhou"

    source = models.CharField(
        "origem", max_length=16, db_index=True,
        help_text="Mesmo valor carimbado nas linhas importadas (ex.: yooga).",
    )
    file_name = models.CharField("arquivo", max_length=200, blank=True)
    file_sha256 = models.CharField(
        "hash do arquivo (sha256)", max_length=64, blank=True,
        help_text="Identidade do arquivo. O mesmo hash não entra duas vezes na mesma origem.",
    )
    imported_at = models.DateTimeField("importado em", auto_now_add=True, db_index=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="import_batches",
        verbose_name="importado por",
        help_text="Vazio quando veio de comando no console (sem sessão de usuário).",
    )
    status = models.CharField("estado", max_length=8, choices=Status.choices, default=Status.DONE)
    rows_read = models.PositiveIntegerField("linhas lidas", default=0)
    sales_created = models.PositiveIntegerField("vendas novas", default=0)
    sales_skipped = models.PositiveIntegerField(
        "vendas já existentes", default=0,
        help_text="Chave natural já conhecida: a linha foi lida e não duplicou.",
    )
    sales_completed = models.PositiveIntegerField(
        "vendas completadas", default=0,
        help_text="Vendas que já existiam e ganharam dado que faltava (metadados).",
    )
    items_created = models.PositiveIntegerField("itens novos", default=0)
    error = models.TextField("erro", blank=True)
    notes = models.CharField("observação", max_length=200, blank=True)

    class Meta:
        verbose_name = "lote de importação"
        verbose_name_plural = "lotes de importação"
        ordering = ["-imported_at"]
        constraints = [
            # Só entre lotes concluídos: um lote que falhou pelo caminho não pode
            # impedir a tentativa seguinte do mesmo arquivo — e precisa ficar
            # registrado, senão a falha some junto com a transação.
            models.UniqueConstraint(
                fields=["source", "file_sha256"],
                condition=models.Q(status="done") & ~models.Q(file_sha256=""),
                name="backstage_importbatch_source_sha_done",
            ),
        ]

    def __str__(self):
        return f"{self.source} · {self.file_name or 'sem arquivo'} · {self.imported_at:%d/%m/%Y %H:%M}"
