# Aviso de estoque/fornada preso ou incerto

1. Rode `python manage.py check_stock_alert_delivery_sla --minutes 10`.
2. No Admin, abra **Entregas de aviso de estoque** e filtre por situação.
3. Para `queued`/`retryable`, confirme que `process_directives --watch` está ativo; o mesmo `directive_id` e a mesma chave semântica devem ser retomados.
4. Para `indeterminate`, consulte o provedor pelo `provider_receipt_ref` e pelo horário. Não reenvie enquanto o efeito não for reconciliado.
5. Para `suppressed`, leia `last_error_code`. Pausa, cancelamento, opt-out, expiração, QC inelegível e indisponibilidade são finais para aquela ocorrência; a assinatura continua ativa quando aplicável.
6. Para ocorrência de fornada em `pending` com `awaiting_quality_review`, abra **Produção → Expedição**. O gestor deve confirmar a partição exibida ou corrigi-la; não altere a ocorrência nem crie uma `Directive` manualmente.

O objetivo de resposta operacional é 10 minutos. A rotina só lê estado e cria alerta interno; não envia mensagem ao cliente.
