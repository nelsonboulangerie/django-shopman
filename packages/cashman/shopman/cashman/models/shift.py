"""Shift — a custódia da GAVETA: qual gaveta esteve aberta, de quando até quando.

A custódia é do terminal, não da pessoa. Um balcão é uma gaveta com várias mãos:
o turno abre na abertura da loja e fecha no fim do expediente, e quem opera troca
quantas vezes for preciso no meio — sem fechar, sem contar, sem ritual.

Quem fez cada coisa não se guarda aqui: se guarda em ``Entry.operator``, uma linha
por ato. É por isso que este model não precisa saber de gente para responder "quem
abriu a gaveta às 15h sem venda" — o livro responde melhor, e por lançamento.

O que se perde, e é escolha consciente: quando falta dinheiro, a nota que sumiu
**não deixa lançamento**. Uma diferença no fechamento não tem um dono; tem a lista
de quem passou. Custódia por pessoa compraria esse dono ao preço de uma contagem
cega a cada troca de operador — inviável num balcão onde se revezam várias vezes
ao dia. Ver ADR-011 (emendada) e a decisão de 21/08/2026.

Este model NÃO tem coluna de dinheiro. Nem fundo de troco, nem contagem, nem
esperado, nem diferença, nem cache de saldo. Tudo isso é lançamento no livro
(``Entry``) e se prova por soma. Duas razões, e as duas são de propósito:

1. **Fechamento cego por construção** (ADR-011 §4). Se o turno não tem número,
   não há número para a projection do terminal vazar. O ``Quant`` do estoque
   cacheia saldo porque disponibilidade é leitura quente do checkout; saldo de
   gaveta é lido no fechamento e na auditoria, e ``Σ amount_q`` com índice por
   turno resolve.
2. **Uma pergunta, um dono.** Antes, esperado e diferença moravam numa coluna
   escrita por um algoritmo e reproduzidos por um espelho; divergiam. Agora a
   pergunta "quanto era para ter" tem uma resposta só: o livro.

O que sobra é o que só uma linha de estado garante: **um turno aberto por
terminal**, por ``UniqueConstraint``. É por isso que o turno não é absorvido pelo
livro: custódia é estado, história é livro.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Shift(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Aberto")
        CLOSED = "closed", _("Fechado")

    terminal = models.ForeignKey(
        "cashman.Terminal",
        on_delete=models.PROTECT,
        related_name="shifts",
        verbose_name=_("terminal"),
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shifts_opened",
        verbose_name=_("aberto por"),
        help_text=_(
            "Quem abriu a gaveta e declarou o fundo de troco. NÃO é dono da custódia "
            "nem responde sozinho pela diferença: quem agiu está em cada Entry."
        ),
    )
    opened_at = models.DateTimeField(_("aberto em"), default=timezone.now)
    closed_at = models.DateTimeField(_("fechado em"), null=True, blank=True)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        app_label = "cashman"
        ordering = ["-opened_at"]
        verbose_name = _("turno de caixa")
        verbose_name_plural = _("turnos de caixa")
        permissions = [
            ("operate_pos", "Pode operar o PDV (abrir/fechar caixa, sangria, balcão)"),
            ("audit_shift", "Pode auditar turnos de caixa (esperado, diferença)"),
            ("adjust_shift", "Pode autorizar exceções do caixa (retirada, destrave, correção)"),
            ("manage_operators", "Pode gerir operadores (resetar PIN, provisionar)"),
        ]
        constraints = [
            # Uma gaveta, um turno. NÃO existe "um turno por operador": o balcão
            # se reveza sem fechar o caixa, e a constraint por pessoa era o que
            # mandava o segundo operador do dia para a antessala.
            models.UniqueConstraint(
                fields=["terminal"],
                condition=models.Q(status="open"),
                name="cashman_shift_open_terminal_uq",
            ),
        ]
        indexes = [
            models.Index(fields=["opened_at"], name="cashman_shift_opened_idx"),
            models.Index(fields=["closed_at"], name="cashman_shift_closed_idx"),
        ]

    def __str__(self) -> str:
        # O terminal primeiro: a custódia é da gaveta, e é assim que o gerente a
        # procura ("o caixa do balcão"), não pelo nome de quem abriu.
        return f"Caixa {self.terminal} · {self.opened_at:%d/%m/%Y %H:%M} [{self.get_status_display()}]"

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.OPEN
