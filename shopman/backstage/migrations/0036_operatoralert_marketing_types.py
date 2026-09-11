from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0035_purchase_operator_permission"),
    ]

    operations = [
        migrations.AlterField(
            model_name="operatoralert",
            name="type",
            field=models.CharField(
                choices=[
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
                    ("cash_sale_after_shift_close", "Venda entrou depois do fechamento do turno"),
                    ("bi_import_silence", "B.I.: importação esperada não chegou"),
                    ("bi_below_baseline", "B.I.: movimento abaixo do esperado"),
                    ("bi_source_conflict", "B.I.: pedido nativo apagou histórico"),
                    ("bi_cash_variance", "B.I.: quebra de caixa acumulada passou da régua"),
                    ("bi_curation_pending", "B.I.: de-para de produto pendente"),
                    ("marketing_consent_violation", "Marketing: envio após opt-out/expiração"),
                    ("marketing_duplicate_confirmed", "Marketing: efeito duplicado confirmado"),
                    ("marketing_outbox_stuck", "Marketing: fila ou tentativa travada"),
                    ("marketing_reconciliation_mismatch", "Marketing: divergência de reconciliação"),
                    ("marketing_unknown_stale", "Marketing: resultado desconhecido sem resolução"),
                    ("marketing_partial_without_action", "Marketing: parcial sem ação de recuperação"),
                    ("marketing_readiness_stale", "Marketing: prontidão do canal vencida"),
                ],
                max_length=50,
                verbose_name="tipo",
            ),
        ),
    ]
