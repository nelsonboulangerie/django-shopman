# WP04/H01 — processo encerrado depois do aceite, retomada em processo novo

`crash_worker.py` roda apenas no Postgres próprio 127.0.0.1:55439,
`orders_notification_crash_lab_v2`. Recusa destino/journal existente; não apaga nada.
Runtime Python do laboratório. Schema vazio migrado, Shop/Order/Directive sintéticos,
callback automático suspenso somente no seed. O dispatcher e handler são reais.

```
python docs/reports/execution/orders-20260910/notification_unknown/crash_worker.py
```

O primeiro processo reclama a Directive e persiste `notification_delivery.started`.
A fronteira de transporte simulada grava um aceite em journal externo ao banco,
flush + fsync, e chama **os._exit(17)**; não executa finally nem grava resultado no
pedido. A fronteira verifica que não existe transação/lock aberto no transporte.
O processo pai exige exit code 17 e inicia outro Python/Django. Com relógio de
reap avançado 10 minutos, o recuperador canônico `_reap_stuck_directives` põe a
Directive na fila; o dispatcher real a reclama e o handler bloqueia pelo marcador.

Resultado V2: um aceite no journal, **zero envio cego**, tentativas=2, Directive
failed/receipt started preservado como incerteza; evento `operator.effect.state`
unknown e **um OperatorAlert existente** com mensagem honesta. Nenhuma rede de
fornecedor real foi utilizada; este é fake de efeito remoto durável, não homologação.

V1 já provava a ausência de reenvio, mas não gerava alerta na recuperação de crash.
Teste antes da correção falhou nessa ausência. O handler passou a emitir a
classificação e escalar depois de liberar a transação de claim, conservando o
fence/aceite monotônico. A audiência, dedupe até resolução e separação ack/resolução
são as existentes. 157 testes PostgreSQL passaram/6,42s, inclusive concorrência,
consentimento, serviços e produção; dois replays geram só um alerta. Ruff aprovado.

Sem DDL no produto: migrações aqui apenas preparam banco de ensaio vazio.
Rollback deve preservar receipts e impedir consumidor antigo (ver restore_lab),
sem resetar estado para forçar retry. Unknown permanece pendente de verificação
homologada/autorizada G03; alerta não é entrega, leitura ou resolução. O journal e
os bancos V1/V2 permanecem isolados para auditoria, sem cleanup automático.
