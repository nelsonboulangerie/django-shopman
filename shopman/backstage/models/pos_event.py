"""POSEvent — o log de eventos do PDV. Append-only, um só, em ordem.

Antes disto havia cinco rastros parciais do caixa, cada um num lugar: aberturas
de gaveta e pedidos de troco em ``CashShift.metadata``, sangria/suprimento em
``CashMovement``, falhas em ``OperatorAlert``, fechamento em ``DayClosing.data``.
Nenhum respondia "o que aconteceu no caixa hoje, em ordem". A regra "dado
contextual vai em JSONField" vale para ESTADO (como está o turno) e falha para
EVENTO (o que aconteceu, quando, por quem): cada feature acrescentava sua
listinha, com teto, e a linha do tempo se perdia entre elas.

Aqui a regra é a mesma do ``Move`` do stockman: nunca ``update()``, nunca
``delete()``; quem errou lança evento novo dizendo o que corrigiu. Este é o
ÚNICO lugar em que se pergunta "o que aconteceu no caixa" — o ``CashMovement``
continua sendo a tabela do DINHEIRO (o valor mora lá, não se duplica), mas todo
movimento gera o seu evento aqui.

⚠️ Limite honesto de "imutável": a guarda vale no app. Quem tem acesso ao banco
edita o que quiser — imutabilidade real exigiria trigger ou permissão no
Postgres, e nem o ``Move`` tem isso. Não prometa mais do que isto entrega.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class POSEventQuerySet(models.QuerySet):
    """Guarda do log: protege do acidente e do descuido, não do DBA."""

    def update(self, **kwargs):
        raise ValueError(
            "Eventos do PDV são imutáveis. "
            "Para corrigir, registre um novo evento dizendo o que foi corrigido."
        )

    def delete(self):
        raise ValueError(
            "Eventos do PDV são imutáveis. "
            "Para desfazer, registre um novo evento dizendo o que foi desfeito."
        )


class POSEvent(models.Model):
    """Uma coisa que aconteceu no caixa: quem, quando, o quê.

    Regras:
    - NUNCA update() ou delete() — correção é evento novo.
    - ``payload`` guarda o específico de cada tipo (schema em
      docs/reference/data-schemas.md); os campos fixos são o que toda pergunta
      de gerente filtra: dia, operador, turno, tipo.
    - ``movement`` liga ao dinheiro quando o evento é sangria/suprimento; o
      valor NÃO se copia para cá — a tabela do dinheiro é uma só.
    """

    class Kind(models.TextChoices):
        SHIFT_OPENED = "shift_opened", "Caixa aberto"
        SHIFT_CLOSED = "shift_closed", "Caixa fechado"
        CASH_IN = "cash_in", "Entrada de caixa"
        CASH_OUT = "cash_out", "Saída de caixa"
        DRAWER_OPENED = "drawer_opened", "Gaveta aberta sem venda"
        DRAWER_UNLOCKED = "drawer_unlocked", "Trava da gaveta liberada"
        CHANGE_REQUESTED = "change_requested", "Troco pedido"
        CHANGE_SERVED = "change_served", "Troco atendido"
        CHANGE_CANCELLED = "change_cancelled", "Pedido de troco cancelado"
        DAY_CLOSED = "day_closed", "Dia fechado"
        RECONCILIATION_FAILED = "reconciliation_failed", "Reconciliação com divergência"

    at = models.DateTimeField("quando", default=timezone.now)
    shift = models.ForeignKey(
        "backstage.CashShift",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="turno",
    )
    terminal = models.ForeignKey(
        "backstage.POSTerminal",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="terminal",
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pos_events",
        verbose_name="operador",
        help_text="Quem causou o evento. Vazio quando foi o sistema (reconciliação, varredura).",
    )
    kind = models.CharField("tipo", max_length=32, choices=Kind.choices)
    payload = models.JSONField(
        "detalhe",
        default=dict,
        blank=True,
        help_text="O específico de cada tipo. Schema em docs/reference/data-schemas.md.",
    )
    movement = models.ForeignKey(
        "backstage.CashMovement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="movimentação",
        help_text="A linha do dinheiro, quando o evento é sangria ou suprimento.",
    )
    order_ref = models.CharField("ref do pedido", max_length=50, blank=True, default="")

    objects = POSEventQuerySet.as_manager()

    class Meta:
        verbose_name = "evento do PDV"
        verbose_name_plural = "eventos do PDV"
        # `id` desempata dois eventos no mesmo instante: a ordem em que foram
        # gravados é a ordem em que aconteceram.
        ordering = ["at", "id"]
        indexes = [
            # As duas perguntas do gerente: "o que houve HOJE" e "o que ESTE
            # operador fez". Turno e tipo cobrem a tela do turno e o B.I.
            models.Index(fields=["at"], name="posevent_at_idx"),
            models.Index(fields=["operator", "at"], name="posevent_op_at_idx"),
            models.Index(fields=["shift", "at"], name="posevent_shift_at_idx"),
            models.Index(fields=["kind", "at"], name="posevent_kind_at_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError(
                "Eventos do PDV são imutáveis. "
                "Para corrigir, registre um novo evento dizendo o que foi corrigido."
            )
        # O terminal vem do turno quando não foi dito: é ele que responde "em
        # qual caixa" sem precisar do join.
        if self.shift_id and not self.terminal_id:
            self.terminal_id = self.shift.terminal_id
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            "Eventos do PDV são imutáveis. "
            "Para desfazer, registre um novo evento dizendo o que foi desfeito."
        )

    def __str__(self) -> str:
        who = self.operator.get_username() if self.operator_id else "sistema"
        return f"{self.at:%d/%m %H:%M} {self.get_kind_display()} · {who}"
