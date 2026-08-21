"""OperatorAlert model."""

from __future__ import annotations

from django.db import models


class OperatorAlert(models.Model):
    """Alerta operacional — falhas, estoque baixo, pagamentos pendentes."""

    TYPE_CHOICES = [
        ("notification_failed", "Notificação falhou"),
        ("payment_failed", "Pagamento falhou"),
        ("payment_insufficient", "Pagamento abaixo do total"),
        ("payment_reconciliation_failed", "Reconciliação de pagamento falhou"),
        ("payment_disputed", "Cartão contestado (disputa)"),
        ("webhook_failed", "Webhook falhou"),
        ("stock_discrepancy", "Discrepância de estoque"),
        ("payment_after_cancel", "Pagamento após cancelamento"),
        ("stock_low", "Estoque baixo"),
        ("marketplace_rejected_unavailable", "Marketplace rejeitado: indisponível"),
        ("marketplace_rejected_oos", "Marketplace rejeitado: sem estoque"),
        ("coupon_over_redeemed", "Cupom resgatado acima do limite"),
        ("pos_rejected_unavailable", "POS rejeitado: produto indisponível"),
        ("stale_new_order", "Pedido parado aguardando confirmação"),
        ("production_late", "Produção atrasada"),
        ("production_low_yield", "Produção com yield baixo"),
        ("production_stock_short", "Produção sem insumo suficiente"),
        ("directive_failed_spike", "Tarefas de fundo falhando"),
        ("directive_backlog", "Fila de tarefas de fundo acumulada"),
        ("directive_worker_stale", "Processador de tarefas de fundo parado"),
        ("lifecycle_phase_stuck", "Fase do pedido travada"),
        ("low_rating", "Avaliação baixa recebida"),
        ("cash_shift_open_at_closing", "Caixa aberto no fechamento do dia"),
        # A venda foi criada e cobrada, mas o turno fechou entre o commit do
        # pedido e a linha do livro, e o livro-caixa é append-only num turno
        # ABERTO: o dinheiro fica sem linha. Nenhum tipo existente serve —
        # `payment_failed` é cobrança que não passou (esta passou) e
        # `payment_reconciliation_failed` é divergência achada no dia seguinte.
        # Este é o aviso do instante, com o pedido no nome, para alguém conferir
        # a gaveta ANTES de o dinheiro virar diferença anônima.
        ("cash_sale_after_shift_close", "Venda entrou depois do fechamento do turno"),
        # Alarmes do B.I. (BIAlertRule): o B.I. avisa quando o que aconteceu foge
        # do esperado. O aviso chega pelo mesmo bus, com reconhecimento.
        ("bi_import_silence", "B.I.: importação esperada não chegou"),
        ("bi_below_baseline", "B.I.: movimento abaixo do esperado"),
        ("bi_source_conflict", "B.I.: pedido nativo apagou histórico"),
        ("bi_cash_variance", "B.I.: quebra de caixa acumulada passou da régua"),
        ("bi_curation_pending", "B.I.: de-para de produto pendente"),
    ]
    SEVERITY_CHOICES = [
        ("warning", "Aviso"),
        ("error", "Erro"),
        ("critical", "Crítico"),
    ]

    type = models.CharField("tipo", max_length=50, choices=TYPE_CHOICES)
    severity = models.CharField("severidade", max_length=10, choices=SEVERITY_CHOICES, default="warning")
    message = models.TextField("mensagem")
    order_ref = models.CharField("ref do pedido", max_length=50, blank=True)
    acknowledged = models.BooleanField("reconhecido", default=False)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "alerta operacional"
        verbose_name_plural = "alertas operacionais"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.message[:80]}"
