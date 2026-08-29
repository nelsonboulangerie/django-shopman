# WP-03 - Gestor De Pedidos

**Status:** pronto para implementacao  
**Superficie:** `surfaces/orders-nuxt` + endpoints orders/courier/feeds/catalog usados pelo Gestor  
**Objetivo:** reduzir erro operacional na fila: nenhuma acao errada por contrato incompleto, nenhum despacho sem preflight, nenhuma excecao fiscal/courier/dinheiro escondida.

## Fronteira Natural

O Gestor e a mesa de decisao operacional de pedidos: triagem, aceite/recusa, avanco fisico, despacho, acerto COD, contexto para cozinha/KDS, courier, fiscal visivel e excecoes. Ele nao abre caixa, nao opera KDS, nao altera WO, nao configura fiscal e nao vira BI.

Contratos naturais:

- POS: apenas acerto de dinheiro de entrega e estado de caixa necessario.
- KDS/Producao: mostra dependencias, nao executa.
- Courier: cotar, chamar, cancelar corrida e acompanhar.
- Fiscal: mostrar status e pedir reprocessamento permitido.
- Storefront/marketplaces: origem, cliente, pagamento, motivo.

## Evidencias Principais

- UI monta action URL manualmente: `surfaces/orders-nuxt/app/composables/useOrdersBoard.ts:116`, `:194`.
- Bulk advance manda `{}`: `surfaces/orders-nuxt/app/composables/useOrdersBoard.ts:185`.
- Backend `advance` espera `change_out` e `equipment`: `shopman/backstage/api/operations.py:1054`.
- `_OrderActionBase` usa permissao unica: `shopman/backstage/api/operations.py:1026`.
- `ACTIVE_STATUSES` inclui `accepted`: `shopman/backstage/projections/order_queue.py:41`.
- Frontend nao mapeia `accepted`: `surfaces/orders-nuxt/app/presentation/board.ts:16`.
- Cancelar no detalhe e incondicional: `surfaces/orders-nuxt/app/pages/[ref].vue:222`.

## Achados Priorizados

### P1 - Contrato gerado cobre read model, nao actions

Rotas, payloads e error codes ficam espalhados entre UI e API.

Proposta:

- Gerar manifest de acoes por pedido: `href`, `method`, `label`, `danger`, `requires_input`, `payload_schema`, `error_codes`.
- UI renderiza botao a partir de capacidade projetada.

Aceite:

- Nao ha botao ativo sem capability do backend.
- Drift de rota/payload quebra teste de contrato.

### P1 - Bulk advance pode despachar entrega com maquininha sem custodia

Fluxo individual pergunta equipamento; bulk manda corpo vazio.

Proposta:

- Excluir do lote qualquer pedido com `dispatchAsks`: troco, equipamento, pendencia fiscal/courier.
- Ou abrir preflight de lote com pergunta por pedido.

Aceite:

- Selecionar 10 pedidos mostra “7 avancam, 2 precisam troco, 1 precisa maquininha”.
- Nenhum pedido com equipamento sai em bulk sem `equipment`.

### P1 - Cancelamento nao e capability projetada

Detalhe mostra `Cancelar pedido` sem `can_cancel`, e backend falha depois.

Proposta:

- Adicionar `can_cancel`, `cancel_block_label`, `cancel_requires_reason_code`.
- Motivo estruturado obrigatorio pos-aceite e em marketplace.

Aceite:

- UI nao oferece cancelamento proibido.
- Cancelamento pos-aceite sem motivo retorna erro de campo.

### P1 - Permissao unica cobre dinheiro, fiscal, cancelamento e courier

`shop.manage_orders` cobre acoes com impactos diferentes.

Proposta:

- Separar permissoes para `settle_delivery_cash`, `requeue_fiscal`, cancelamento pos-aceite e courier cancel/redispatch.
- Manter leitura/avanco simples em `shop.manage_orders`.

Aceite:

- Matriz de permissao por endpoint sensivel.

### P2 - Courier e fiscal sao heuristicas locais

Courier e `Record<string, unknown>` e requeue fiscal depende de string `failed`.

Proposta:

- Criar `CourierBlockProjection`.
- Projetar `can_requeue_fiscal` e `requeue_fiscal_block_reason`.

Aceite:

- UI nao infere dispatch/cancel/requeue so por string.

## Melhorias UX

1. **Faixa “Excecoes agora”:** fiscal falhou, courier falhou, COD pendente, maquininha na rua, pagamento bloqueando.
2. **Acoes courier no board:** pedidos prontos/falhados nao exigem abrir detalhe para agir.
3. **Preflight de despacho:** endereco, instrucoes, troco, equipamento, cotacao, bloqueios.
4. **Dono da espera:** cliente, pagamento, cozinha, courier, fiscal ou operador.
5. **Passagem de turno:** resumo por pedido: ultimos eventos, nota, dono, pendencias e proxima acao.

## Testes

- Contract test de actions/payloads.
- Frontend: `statusTone` cobre `ACTIVE_STATUSES`.
- Bulk advance exclui troco/equipamento.
- Permissoes: cash, fiscal, courier cancel, cancel pos-aceite.
- Auditoria: `kitchen_note_updated` com ator/diff.
- Courier cancel exige motivo.
- E2E: aceite -> preparo -> pronto -> entrega com troco/maquininha -> falha courier -> requeue fiscal.

## Fora De Escopo

Configurar courier provider, abrir/fechar caixa, operar KDS/WO, regra fiscal profunda, criar feed novo, atendimento self-service, BI/forecast/compras.

## Prompt Para Agente Executor

```text
Execute WP-03 Gestor de Pedidos.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/WP-03-gestor-pedidos.md
- surfaces/orders-nuxt/app/composables/useOrdersBoard.ts
- surfaces/orders-nuxt/app/composables/useOrderDetail.ts
- surfaces/orders-nuxt/app/pages/index.vue
- surfaces/orders-nuxt/app/pages/[ref].vue
- shopman/backstage/projections/order_queue.py
- shopman/backstage/api/operations.py
- shopman/backstage/services/orders.py
- shopman/shop/services/operator_orders.py

Fases:
1. Manifest de actions e capabilities.
2. Preflight de bulk advance/dispatch.
3. Cancelamento e fiscal como affordance projetada.
4. Permissoes finas.
5. UX de excecoes e dono da espera.

Nao invada POS, KDS, Producao ou Fiscalman.
```

