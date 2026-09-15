# Contrato técnico L7 — etapa A passiva

Esta etapa materializa somente o inventário R01–R15. Ela não cria política,
migration, job ou caminho de descarte.

## Invariantes

- modo padrão e `--dry-run`: apenas `SELECT`/`WITH`, sem PII e zero mutações;
- `--apply`: falha antes de montar qualquer consulta;
- saída contém exclusivamente nomes fixos, estados e contagens agregadas;
- entrega pendente, retryable ou `unknown` nunca perde destino/recibo;
- `CatalogSnapshot.raw_json` (0055) é apenas contado; conteúdo não é carregado,
  classificado ou considerado candidato;
- R08 conta somente observações passivas vencidas exatamente como a rotina já
  existente em 0056; não a chama e não usa `Conversation.updated_at` como
  fechamento;
- R01 usa o marco terminal coerente com o estado (`completed_at`,
  `cancelled_at` ou `returned_at`), nunca a criação do pedido;
- R03, R04, R09 e R13 são inventários com `candidates=0` enquanto não houver
  marco canônico suficiente para provar descarte seguro;
- R05 também expõe `candidates=0`: `identity_retention_until` nasce na
  materialização e ainda não prova 90 dias desde o encerramento;
- R06 exclui recibos ligados a destinos ainda pendentes, repetíveis ou
  desconhecidos; aceite do provedor não é resultado final do concierge;
- arquivos legais permanentes são inventário, com `candidates=0`;
- `data_retention` e `purge_consent_ip` não entram no worker.

## Grafo real

O branch principal já contém a sequência linear:

`0053_marketing_delivery_identity → 0054_disable_remote_auto_confirmation →
0055_catalog_snapshot_binding → 0056_concierge_message_observation_controls`.

Não há `shop.0057` no grafo auditado. Uma futura expansão L7 deve nascer em
0057 sobre 0056, sem migration nominal/vazia e sem remover ou reescrever o
legado nesta etapa.

## Antes de qualquer aplicação

São obrigatórios: `closed_at` canônico; `legal hold` auditável; testes de
limites temporais, idempotência e concorrência em PostgreSQL; preservação de
entregas não reconciliadas; restore com reaplicação de tombstones; dry-run real
revisado; e autorizações separadas para expurgo e para cada job produtivo.
