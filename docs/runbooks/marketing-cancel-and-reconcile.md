# Marketing — cancelamento, duplicidade e reconciliação

**Owner:** SRE/Platform + Marketing Ops. **Severidade:** crítica para duplicidade.
**Invariante:** cancelamento impede trabalho reversível; não apaga efeito confirmado.

## Quando abrir

- cancel compete com worker/dispatch;
- alerta `marketing_duplicate_confirmed` ou `marketing_reconciliation_mismatch`;
- operador precisa saber o que o cancelamento ainda consegue impedir;
- tombstone, outbox, Directive e ledger não fecham.

## Primeiros 2 minutos

1. Em duplicidade confirmada ou escopo incerto, aplique freeze global imediatamente.
2. Copie receipt/plataforma/attempt refs técnicas e preserve timestamps/hashes.
3. Rode `make marketing-diagnose receipt=<receipt_ref> platform=<platform>`.
4. Separe efeitos não iniciados, incertos, aceitos e confirmados antes de decidir.

## Diagnóstico read-only

O relatório agrega outbox/targets/attempts/reconciliation. Compare command receipt,
tombstone e estados derivados; uma contagem legacy não pode sobrepor o ledger.

## Freeze/circuit

Freeze global para duplicidade; por receipt/plataforma para corrida de cancelamento
delimitada. Mantenha lookup/reconciliation disponível, pois ele não envia.

## Decisões proibidas

- não apagar target/attempt duplicado nem reescrever o estado para “corrigir painel”;
- não retry de unknown/accepted/confirmed;
- não prometer retract de mensagem/post já aceito;
- não criar cancel/retry direto no banco ou provider.

## Comunicação

Informe receipt, plataforma, quantos foram impedidos, unknown/accepted/confirmed,
estado do freeze e owner da reconciliação. Diga claramente o limite do cancelamento.

## Recuperação idempotente

Use Action `cancel` com base_version; concorrência tem um vencedor e replay retorna o
mesmo receipt. Depois use `reconcile_delivery` para unknown/mismatch. Retry fica
restrito a `failed_retryable`. Duplicidade preserva ambos os efeitos como evidência.

## Fechamento e reconciliação

Exija tombstone para lanes reversíveis, ledger terminal, unknown=0 ou owner/prazo,
agregado igual à soma e causa da duplicidade fechada antes do unfreeze independente.

## Drill local

`make marketing-drills` prova cancel idempotente e vencedor único. O operador não autor
deve ordenar freeze em duplicidade e nunca confundir cancelamento com retract.
