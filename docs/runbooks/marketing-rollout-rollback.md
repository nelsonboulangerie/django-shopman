# Marketing — rollback e rollout interrompido

**Owner:** Release Manager + SRE/Platform. **Severidade:** conforme burn/P0.
**Invariante:** rollback de software não desfaz commands nem efeitos in-flight.

## Quando abrir

- canary/piloto excede error budget ou apresenta P0;
- board burn, queue lag, partial/unknown ou regressão após estágio;
- decisão no-go/freeze em 5→25→50→100%;
- versão precisa voltar sem perder reconciliação.

## Primeiros 2 minutos

1. Pare o avanço do estágio e preserve a versão/percentual atual.
2. Se houver opt-out/duplicidade/PII, aplique freeze e use o runbook crítico indicado.
3. Rode `make marketing-diagnose` e capture health live/ready de API e BFF.
4. Inventarie receipts/outboxes/targets in-flight antes de autorizar qualquer rollback.

## Diagnóstico read-only

Registre versão, estágio, janela, SLO queimado, contagens agregadas e estado das flags.
O diagnóstico não chama provider. Compare com baseline autorizado e diferencie falha
de BFF, API, DB/cache/fila e canal.

## Onde a entrega roda

Não existe componente próprio de entrega de Marketing: `process_marketing_delivery` roda
dentro do `maintenance-worker`, uma passada por ciclo de 300 s, logo depois de
`process_marketing_outbox` (ver
[Entrega sem componente próprio](../reference/marketing-surface-contract.md#entrega-sem-componente-próprio)).
Consequências para este runbook:

- não procure nem crie um worker de entrega no spec; pausar a entrega é desligar
  `SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED` (a passada volta calada) ou aplicar freeze;
- **não reinicie nem pare o `maintenance-worker` para segurar Marketing**: ele também
  roda reconciliação de pagamentos, holds, pedidos presos e as demais manutenções;
- não rode `process_marketing_delivery --watch` à mão ao lado dele sem autorização SRE:
  seria um segundo executor sobre o mesmo ledger;
- depois de uma aprovação, a entrega começa em até ~7 minutos; ausência de efeito antes
  disso é espera normal, não travamento.

## Freeze/circuit

Freeze Marketing e pause o rollout; não desligue reconciler/lookup necessário para
fechar unknown. Rollback/deploy só pode ocorrer com autorização G-H09/G-H10 do Release
Manager — este runbook não concede essa permissão.

## Decisões proibidas

- não executar deploy/rollback, push, merge ou escrita de provider sem gate explícito;
- não apagar filas ou banco para “voltar limpo”;
- não reabrir percentual porque liveness está verde;
- não trocar para caminho legacy que não entende os receipts novos.

## Comunicação

Informe versão, estágio, métrica/threshold, health por camada, volume in-flight, freeze,
decisor e checkpoint. Use status `go`, `hold`, `rollback autorizado` ou `no-go`.

## Recuperação idempotente

Com autorização de release, siga `rollback-de-deploy.md`, mantendo contratos compatíveis
e workers de reconciliação. Revalide cada receipt in-flight após a versão voltar. A
reativação começa no menor estágio e exige novo gate, não retoma automaticamente.

## Fechamento e reconciliação

Feche somente com versão confirmada, health ready verde, receipts reconciliados, zero
P0/mismatch/unknown sem owner, SLO dentro do budget e decisão registrada por estágio.

## Drill local

`make marketing-drills` prova que `--force` não atravessa a trava de produção. O
operador não autor deve escolher hold/freeze e recusar rollback sem G-H09/G-H10.
