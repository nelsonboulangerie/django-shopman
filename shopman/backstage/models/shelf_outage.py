"""Períodos em que a casa não teve o produto para oferecer.

O que o cliente encontra não é o saldo físico: é o saldo **menos o reservado**
para carrinhos abertos e pedidos aceitos que ainda não saíram. Um produto pode
sumir do cardápio com dez unidades ainda na loja, e reaparecer quando uma
reserva expira. Nenhum dos dois momentos deixa rastro no ledger de estoque, que
só registra a saída física.

Este model registra exatamente o que faltava: **de que hora a que hora o
produto não estava disponível para oferecer**, por canal — porque a
disponibilidade é por canal (o balcão enxerga posições que o delivery não vê).

Não é fonte de verdade de estoque: é a observação de uma transição que a
disponibilidade — cujo dono segue sendo o stockman — produziu. Recomputável a
partir do estado atual (ver ``reconcile_outages``), e o passado anterior à
primeira medição simplesmente não existe, em vez de aparecer como zero.

Só conta falta: produto **pausado** não entra. Pausar é decisão comercial, não
ruptura de abastecimento, e misturar as duas mentiria sobre a produção.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class ShelfOutage(models.Model):
    sku = models.CharField("sku", max_length=100, db_index=True)
    channel_ref = models.CharField("canal", max_length=64, db_index=True)
    started_at = models.DateTimeField("ficou indisponível em")
    ended_at = models.DateTimeField(
        "voltou em", null=True, blank=True,
        help_text="Vazio = ainda indisponível agora.",
    )
    metadata = models.JSONField("metadata", default=dict, blank=True)

    class Meta:
        verbose_name = "indisponibilidade"
        verbose_name_plural = "indisponibilidades"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["sku", "started_at"], name="backstage_outage_sku_start"),
            models.Index(fields=["channel_ref", "started_at"], name="backstage_outage_ch_start"),
        ]
        constraints = [
            # Um período aberto por (sku, canal): não existem duas faltas
            # simultâneas do mesmo produto no mesmo canal.
            models.UniqueConstraint(
                fields=["sku", "channel_ref"],
                condition=models.Q(ended_at__isnull=True),
                name="backstage_outage_one_open_per_sku_channel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku}@{self.channel_ref} desde {self.started_at}"

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    def minutes_within(self, start, end) -> float:
        """Minutos desta falta dentro da janela ``[start, end]``.

        Falta em curso conta até o fim da janela (ou agora, o que vier antes):
        o produto segue faltando, e parar de contar fingiria que voltou.
        """
        began = max(self.started_at, start)
        finished = min(self.ended_at or timezone.now(), end)
        if finished <= began:
            return 0.0
        return (finished - began).total_seconds() / 60
