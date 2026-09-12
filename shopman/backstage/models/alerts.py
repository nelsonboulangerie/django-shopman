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
        # Estorno é a única operação que tira dinheiro da casa sem ninguém
        # olhando, e ela falha de dois jeitos diferentes: o que não saiu (o
        # cliente segue sem o dinheiro) e o que saiu no gateway e não virou
        # linha no Payman. O segundo é o pior — o saldo reembolsável local
        # continua de pé e um próximo estorno devolve duas vezes.
        ("payment_refund_failed", "Estorno falhou no gateway"),
        ("payment_ledger_drift", "Estorno saiu do gateway sem registro no livro"),
        ("webhook_failed", "Webhook falhou"),
        # Integração externa de SAÍDA (Google Geocoding, etc.) falhando. O
        # webhook é o lado de entrada; este é o de saída — que até aqui morria
        # em `logger.warning` e ninguém ficava sabendo.
        ("integration_failed", "Integração externa falhou"),
        # Erro de programação (500) que morria no log do App Platform. O
        # traceback sempre existiu; o que faltava era um caminho até alguém que
        # não seja o cliente reclamando. Dedupe por (exceção + arquivo:linha).
        ("unhandled_exception", "Erro não tratado no sistema (500)"),
        # A tela de prontidão SABE que a NFC-e está em homologação e que o Pix
        # está no simulador — e esperava alguém abrir /admin/diagnostics/ para
        # contar. Este tipo é a mesma verdade, empurrada em vez de puxada.
        ("integration_config_drift", "Integração em configuração degradada"),
        ("concierge_identity_conflict", "Concierge encontrou identidade divergente"),
        ("stock_discrepancy", "Discrepância de estoque"),
        ("payment_after_cancel", "Pagamento após cancelamento"),
        # A gêmea do `payment_after_cancel`: o dinheiro chegou com o pedido
        # ainda em NEW, antes de alguém confirmar. Não é falha — é o aviso de
        # que existe pedido PAGO esperando decisão do balcão.
        ("payment_awaiting_confirmation", "Pagamento chegou antes da confirmação"),
        ("stock_low", "Estoque baixo"),
        # Estoque do sistema acima do físico, pelos três caminhos: a baixa que
        # não saiu na entrega, o pedido que passou sem reserva, e o item fora
        # do catálogo em canal que exige reserva. O fechamento não enxerga
        # nenhum dos três — por isso cada um grita na hora.
        ("stock_fulfill_failed", "Baixa de estoque falhou"),
        ("stock_hold_gap", "Pedido commitado sem reserva de estoque"),
        ("stock_unknown_sku", "Pedido com SKU fora do catálogo"),
        # O contrário: reserva presa sem dono, que a varredura devolveu. A
        # vitrine ganhou disponibilidade de volta e a loja precisa saber por quê.
        ("orphan_holds_released", "Reservas órfãs devolvidas ao estoque"),
        ("marketplace_rejected_unavailable", "Marketplace rejeitado: indisponível"),
        ("marketplace_rejected_oos", "Marketplace rejeitado: sem estoque"),
        # Os dois acima nasceram com nome de marketplace e nunca chegaram a ser
        # gravados: a recusa por disponibilidade no commit vale para QUALQUER
        # canal, e é com estes dois nomes que o lifecycle escreve.
        ("rejected_unavailable", "Pedido recusado: item indisponível"),
        ("rejected_oos", "Pedido recusado: reserva não confirmada"),
        ("coupon_over_redeemed", "Cupom resgatado acima do limite"),
        ("pos_rejected_unavailable", "POS rejeitado: produto indisponível"),
        # O cardápio agrupa por coleção ATIVA e recolhe no fim quem não tem
        # coleção nenhuma. Quem tem só coleção DESATIVADA não cabe em nenhum dos
        # dois: some da loja inteira, publicado e com estoque, sem ninguém ter
        # escondido nada. É o único estado "fora do ar" que não veio de um
        # switch — e, por não ter dono, ficava invisível até um cliente reclamar.
        ("catalog_hidden_by_inactive_collection", "Produto fora do cardápio: categoria desativada"),
        ("stale_new_order", "Pedido parado aguardando confirmação"),
        ("checkout_convenience_pending", "Conveniência do checkout pendente"),
        # Pedido fechado sem dono: nesta loja o telefone É a identidade, e sem
        # o vínculo o cliente fica sem histórico, fidelidade e rastreio.
        ("checkout_customer_unlinked", "Pedido fechou sem vínculo com cadastro"),
        # Encomenda não paga barrada antes da cozinha: a fornada não sai, e
        # quem cobra é gente.
        ("preorder_activation_blocked_unpaid", "Encomenda não paga barrada antes da cozinha"),
        # Exclusão de conta que não terminou. Dado de titular que continua no
        # banco é obrigação legal em aberto, não um 500 qualquer.
        ("account_deletion_incomplete", "Exclusão de conta incompleta"),
        # Item que a cozinha NUNCA vai ver: sem estação casada, o pedido chega a
        # pronto com o item nunca preparado.
        ("kds_unrouted_item", "Item sem estação no KDS"),
        # Entrega por central: a corrida que não abriu, a que ninguém aceitou e
        # a que a central cancelou. Nos três o pedido fica parado esperando um
        # entregador que não vem, e re-despachar ou levar por conta da casa é
        # decisão humana.
        ("courier_dispatch_failed", "Corrida não abriu na central"),
        ("courier_not_attended", "Nenhum entregador aceitou a corrida"),
        ("courier_ride_cancelled", "A central cancelou a corrida"),
        # Fiscal: nota prometida ao cliente e recusada pela regra; NFC-e barrada
        # porque o pagamento gravado é menor que o total; nota autorizada cujo
        # e-mail não saiu; cancelamento que falhou (nota válida em pé para venda
        # cancelada é passivo); e devolução parcial com a nota inteira de pé.
        # Nenhum desses se resolve com retry — todos terminam em alguém.
        ("fiscal_receipt_promised", "Nota prometida ao cliente e não emitida"),
        ("fiscal_payment_mismatch", "NFC-e barrada: pagamento abaixo do total"),
        ("fiscal_email_failed", "NFC-e autorizada mas o e-mail não saiu"),
        ("fiscal_cancel_failed", "Cancelamento da NFC-e falhou"),
        ("fiscal_partial_return", "Devolução parcial com NFC-e em pé"),
        # O desconto de pontos já entrou no total e a baixa no saldo não passou:
        # receita perdida que some sem ninguém ver.
        ("loyalty_redeem_uncovered", "Desconto de pontos sem baixa no saldo"),
        ("production_late", "Produção atrasada"),
        ("production_low_yield", "Produção com yield baixo"),
        ("production_stock_short", "Produção sem insumo suficiente"),
        # Falta PREVISTA (production_stock_short) vs. falta REAL: esta é a
        # sub-baixa já commitada — o fechamento consumiu menos insumo que a ficha
        # pede (sem pré-checagem, ou divergência de concorrência). A fornada não
        # falha, mas o livro de insumo ficou acima do real e precisa gritar.
        ("production_stock_shortfall", "Produção baixou menos insumo que a ficha"),
        # As três faltas de fornada que não são de insumo: a planejada que nunca
        # começou, a começada que nunca fechou (estoque preso em produção) e a
        # fechada sem gravar os lotes — sem lote, some o desconto de validade e
        # a rastreabilidade da partida (ADR-017).
        ("production_forgotten", "Produção planejada nunca iniciada"),
        ("production_unfinished", "Produção iniciada nunca concluída"),
        ("production_batch_traceability", "Produção concluída sem gravar os lotes"),
        (
            "production_quality_communication",
            "Qualidade corrigida após comunicação da fornada",
        ),
        (
            "production_quality_hold_risk",
            "Correção de qualidade aguarda proteção ao cliente",
        ),
        (
            "order_production_quality_risk",
            "Pedido protegido de uma correção de qualidade",
        ),
        ("directive_failed_spike", "Tarefas de fundo falhando"),
        ("directive_backlog", "Fila de tarefas de fundo acumulada"),
        ("directive_worker_stale", "Processador de tarefas de fundo parado"),
        ("lifecycle_phase_stuck", "Fase do pedido travada"),
        ("low_rating", "Avaliação baixa recebida"),
        ("cash_change_requested", "Troco solicitado no PDV"),
        ("cash_shift_open_at_closing", "Caixa aberto no fechamento do dia"),
        # A venda foi criada e cobrada, mas o turno fechou entre o commit do
        # pedido e a linha do livro, e o livro-caixa é append-only num turno
        # ABERTO: o dinheiro fica sem linha. Nenhum tipo existente serve —
        # `payment_failed` é cobrança que não passou (esta passou) e
        # `payment_reconciliation_failed` é divergência achada no dia seguinte.
        # Este é o aviso do instante, com o pedido no nome, para alguém conferir
        # a gaveta ANTES de o dinheiro virar diferença anônima.
        ("cash_sale_after_shift_close", "Venda entrou depois do fechamento do turno"),
        # A trava da gaveta caiu numa estação que TINHA medição. Ela falha
        # aberta de propósito (fila de cliente nunca para por sensor ruim), e
        # por isso mesmo precisa gritar: sem este aviso, desligar a proteção era
        # mais fácil que burlá-la — puxa o cabo da gaveta uma vez e a trava some
        # para sempre, sem nada em lugar nenhum registrando que ela sumiu.
        ("pos_drawer_sensor_blind", "Sensor da gaveta parou de responder"),
        # Gaveta que ficou aberta ENTRE vendas. A trava cobre o instante em que
        # a venda começa; a hora morta ficava descoberta — ninguém inicia venda,
        # ninguém vê a gaveta, e ela passa a tarde aberta.
        ("pos_drawer_left_open", "Gaveta ficou aberta sem ninguém vender"),
        # Fila de espera: a vaga que volta é decisão da loja (servir o próximo
        # ou pôr na gôndola), e por isso a liberação NUNCA é silenciosa — o
        # cliente recebe aviso e a loja recebe este alerta. O tipo existia no
        # código do ``waitlist.release`` e não existia aqui: gravava, mas o
        # crachá do Admin mostrava o slug cru em vez de uma frase em português.
        ("waitlist_released", "Fila: vaga liberada"),
        # Alarmes do B.I. (BIAlertRule): o B.I. avisa quando o que aconteceu foge
        # do esperado. O aviso chega pelo mesmo bus, com reconhecimento.
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
        ("stock_alert_delivery_stuck", "Entrega de aviso de produto atrasada"),
        ("stock_alert_dispatch_unknown", "Resultado de envio de aviso incerto"),
        # Concierge de WhatsApp: o cliente pediu gente (o bot calou e a conversa
        # espera a equipe), ou o modelo falhou três vezes seguidas numa conversa.
        ("concierge_handoff", "WhatsApp: cliente pediu a equipe"),
        ("concierge_unavailable", "WhatsApp: concierge fora do ar"),
        ("concierge_empty_output", "WhatsApp: resposta automática vazia"),
        ("concierge_handoff_sync", "WhatsApp: sincronização do atendimento pendente"),
        ("concierge_output_blocked", "WhatsApp: resposta automática bloqueada"),
        ("concierge_output_pending", "WhatsApp: resultado do envio pendente"),
        # ⚠️ Vai para o GESTOR, não para o CI. Teste vermelho é visto por quem
        # programa; a obrigação de cumprir a norma é de quem opera — então o
        # vencimento de um parâmetro legal precisa aparecer na tela dele.
        ("legal_parameter_stale", "Parâmetro de lei sem conferência"),
    ]
    SEVERITY_CHOICES = [
        ("warning", "Aviso"),
        ("error", "Erro"),
        ("critical", "Crítico"),
    ]
    AUDIENCE_CHOICES = [
        ("production", "Produção"),
        ("orders", "Pedidos"),
        ("finance", "Financeiro"),
        ("operations", "Operação geral"),
    ]
    PRODUCTION_TYPES = {
        "production_late",
        "production_low_yield",
        "production_stock_short",
        "production_stock_shortfall",
        "production_forgotten",
        "production_unfinished",
        "production_batch_traceability",
        "production_quality_communication",
        "production_quality_hold_risk",
        "stock_discrepancy",
        "stock_low",
    }
    FINANCE_TYPES = {
        "payment_failed",
        "payment_insufficient",
        "payment_reconciliation_failed",
        "payment_disputed",
        "payment_after_cancel",
        "cash_shift_open_at_closing",
        "cash_sale_after_shift_close",
        "bi_cash_variance",
    }
    ORDER_TYPES = {
        "marketplace_rejected_unavailable",
        "marketplace_rejected_oos",
        "pos_rejected_unavailable",
        "stale_new_order",
        "lifecycle_phase_stuck",
        "order_production_quality_risk",
    }

    type = models.CharField("tipo", max_length=50, choices=TYPE_CHOICES)
    severity = models.CharField("severidade", max_length=10, choices=SEVERITY_CHOICES, default="warning")
    audience = models.CharField(
        "público operacional",
        max_length=20,
        choices=AUDIENCE_CHOICES,
        default="operations",
        db_index=True,
    )
    message = models.TextField("mensagem")
    order_ref = models.CharField("ref do pedido", max_length=50, blank=True)
    rev = models.PositiveBigIntegerField("revisão", default=0)
    acknowledged = models.BooleanField("reconhecido", default=False)
    acknowledged_at = models.DateTimeField(
        "reconhecido em",
        null=True,
        blank=True,
        help_text="Vazio em registros legados reconhecidos antes da trilha nominal.",
    )
    acknowledged_by = models.CharField(
        "reconhecido por",
        max_length=100,
        blank=True,
        help_text="Identidade operacional que reconheceu o alerta.",
    )
    resolved_at = models.DateTimeField(
        "resolvido em",
        null=True,
        blank=True,
        help_text="Momento em que o sistema confirmou que a causa deixou de existir.",
    )
    resolved_by = models.CharField(
        "resolvido por",
        max_length=100,
        blank=True,
        help_text="Processo ou identidade que confirmou a resolução da causa.",
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "alerta operacional"
        verbose_name_plural = "alertas operacionais"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.message[:80]}"

    def save(self, *args, **kwargs):
        # Direct ORM writers predate the service/adapter boundary.  Keep them
        # safe: a typed production/finance/order alert cannot silently inherit
        # the generic audience merely because the caller omitted the field.
        if self._state.adding and self.audience == "operations":
            self.audience = self.audience_for_type(self.type)
        super().save(*args, **kwargs)

    @classmethod
    def audience_for_type(cls, alert_type: str) -> str:
        if alert_type in cls.PRODUCTION_TYPES:
            return "production"
        if alert_type in cls.FINANCE_TYPES:
            return "finance"
        if alert_type in cls.ORDER_TYPES:
            return "orders"
        return "operations"
