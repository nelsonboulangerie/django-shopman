# WP-06 - Compras / Recebimento

**Status:** pronto para implementacao  
**Superficie:** `surfaces/purchase-nuxt` + endpoints purchase  
**Objetivo:** eliminar duplicacao de estoque, spoof de NF/material/custo e divergencia de unidade no recebimento, preservando uma UX rapida de loja.

## Fronteira Natural

Compras decide o que comprar, confere o que chegou, registra entrada fisica e captura custo/conversao observados. Deve consumir Stockman, Producao/receitas e Buyman. Nao deve virar fiscal, pricing, inventario geral, MDM completo ou BI.

## Evidencias Principais

- `confirm_receipt` confia em payload do browser: `shopman/backstage/services/purchase.py:112`.
- NF/supplier/lines vem do payload: `shopman/backstage/services/purchase.py:123`, `:131`, `:138`.
- Loop grava estoque via `stock.receive`: `shopman/backstage/services/purchase.py:147`.
- Aprende mapa fiscal no confirm: `shopman/backstage/services/purchase.py:874`.
- UI recalcula reposicao localmente: `surfaces/purchase-nuxt/app/composables/usePurchaseDesk.ts:548`.
- Backend tem `_suggested_qty`: `shopman/backstage/projections/purchase.py:305`.
- Todas as views usam `backstage.operate_purchase`: `shopman/backstage/api/purchase.py:36`, `:49`, `:66`, `:100`, `:117`, `:155`.

## Achados Priorizados

### P0 - Recebimento por NF confia no payload do cliente

Operador autorizado pode postar supplier, chave e linhas arbitrarias e ainda ensinar de-para fiscal.

Proposta:

- Criar `ReceiptDraft` servidor-side no scan.
- Draft guarda `draft_id`, hash/XML/fonte, CNPJ emissor, linhas originais, fornecedor sugerido e decisoes do operador.
- Confirmacao aceita `draft_id` e deltas de conferencia, nao linhas livres.
- Troca de material/conversao exige override auditado.

Aceite:

- Confirmar linha/material fora do draft falha sem override.
- Mapa fiscal so aprende de draft valido.

### P0 - Recebimento nao e idempotente

Mesmo invoice/access key pode gerar multiplos `Move`.

Proposta:

- Entidade `PurchaseReceipt` ou chave unica `invoiceAccessKey + supplier + lineId/material/qty`.
- Reenvio identico retorna receipt existente ou 409 com explicacao.

Aceite:

- Confirmar mesma NF duas vezes nao duplica estoque.

### P1 - Sugestao de reposicao diverge entre backend e UI

Backend calcula com lead time, ciclo, safety e shelf-life; UI usa regra fixa.

Proposta:

- Projection traz `suggestedQty`, `suggestedReason`, `replenishAtDays`, `coverageDays`.
- UI renderiza e ordena pela projection.

Aceite:

- Teste frontend garante `reorderRows` nao recalcula alvo localmente.

### P1 - Estado `approved` existe mas UI envia direto

API tem approve/send; service aceita `sent` diretamente e UI chama send sem approval.

Proposta:

- Escolher uma semantica: ou remover `approved`, ou impor `review -> approved -> sent`.
- Se compras reais dependem de aprovacao, separar permissoes.

Aceite:

- Usuario sem `approve_purchase` nao consegue enviar compra acima da politica.

### P1 - Conversao divergente e custo viram aviso/overwrite

Conversao divergente e `watch`; custo preferido e sobrescrito sem historico forte.

Proposta:

- Conversao divergente bloqueia ate escolher: manter antiga, aceitar nova, justificar.
- Criar `SupplierCostObservation` append-only.
- Promover custo preferido por regra controlada.

Aceite:

- Custo recebido gera observacao historica.
- Conversao divergente sem justificativa nao confirma estoque.

## Melhorias UX

1. **Recebimento por excecao:** apos scan, linhas sem material, conversao divergente, custo ausente e validade faltante no topo.
2. **Comprar por risco de ruptura:** dias ate zerar, lead time, producao afetada e sugestao backend.
3. **Scanner real de loja:** bipar SKU/GTIN por linha para confirmar material fisico.
4. **Tres colunas por item:** Nota, Contagem, Entrada no estoque.
5. **Conferencia de nota:** total NF vs conferido, linhas faltantes/extras, CNPJ emissor, validade/lote.
6. **Relogio de ruptura:** entrada cobre X dias e destrava receitas Y/Z.

## Testes

- Backend: mesma NF nao duplica `Move`.
- Backend: confirmacao por draft nao aceita supplier/material/linha fora do draft.
- Backend: conversao divergente bloqueia sem justificativa/permissao.
- Backend: custo gera observacao historica.
- Permissoes: scan, receive, cost, conversion, approve, send.
- Frontend: usa `suggestedQty` da projection.
- Contrato: checksum NF-e igual TS/Python ou validacao server-side.

## Fora De Escopo

Preco de venda, emissao/cancelamento fiscal de venda, planejamento de producao, merge amplo de cadastro mestre, inventario ciclico, perdas/ajustes gerais, comunicacao com cliente.

## Prompt Para Agente Executor

```text
Execute WP-06 Compras / Recebimento.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/WP-06-compras.md
- surfaces/purchase-nuxt/app/composables/usePurchaseDesk.ts
- surfaces/purchase-nuxt/app/presentation/purchase.ts
- shopman/backstage/api/purchase.py
- shopman/backstage/services/purchase.py
- shopman/backstage/projections/purchase.py
- packages/buyman/shopman/buyman/models/*
- packages/stockman/shopman/stockman/services/movements.py

Fases:
1. Modelar ReceiptDraft/PurchaseReceipt e idempotencia.
2. Vincular confirmacao ao draft.
3. Separar permissoes de compra/recebimento/custo/conversao.
4. Remover recalculo local de reposicao.
5. UX de conferencia por excecao.

Este WP tem P0. Nao adicione novas entradas de estoque sem idempotencia.
```

