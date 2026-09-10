# WP-05 - Producao

**Status:** pronto para implementacao  
**Superficie:** `surfaces/production-nuxt` + endpoints production/work orders/QC/weighing/reports  
**Objetivo:** impedir erro humano escondido em lote, peso, forno, QC, force/void e concorrencia entre bancadas.

## Fronteira Natural

Producao transforma previsao/pedidos em lotes fisicos: planejar WO, preparar insumos, pesar, assar, fechar QC, registrar perdas e expor relatorios operacionais. Cadastro de receita, formula, SKU, qualidade e permissao pertence ao Admin/Craftsman/Stockman. BI historico nao deve ser reimplementado na tela operacional.

## Evidencias Principais

- `ProductionSurfaceAccess` existe no contrato: `surfaces/production-nuxt/app/generated/productionContract.ts:132`.
- `build_production_board` usa `_full_access()` quando nada e passado: `shopman/backstage/projections/production.py:620`.
- API chama builder com permissao ampla: `shopman/backstage/api/operations.py:712`.
- Mutations nao carregam `expected_rev`: `shopman/backstage/api/operations.py:1619`, `:1665`, `:1693`.
- Core suporta `expected_rev`: `packages/craftsman/shopman/craftsman/services/scheduling.py:189`, `:264`.
- Weighing usa `work_order.quantity`: `shopman/backstage/projections/production.py:786`.
- Helper de started qty existe: `shopman/backstage/projections/production.py:2410`.
- `force` vem como boolean do cliente: `shopman/backstage/api/operations.py:1639`, `:1701`, `:1768`.

## Achados Priorizados

### P1 - Permissoes finas existem no contrato, mas board nasce com acesso total

A UI ja respeita flags; backend precisa ser fonte da verdade.

Proposta:

- Derivar `ProductionSurfaceAccess` de permissoes reais.
- Passar access para board, KDS, QC, reports e management.
- Separar planejar, iniciar, fechar QC, force, void, quick/off-plan, oven facts, reports, management, blind map.

Aceite:

- Usuario sem permissao de force nao recebe capability nem consegue POSTar force.

### P1 - Mutations nao usam concorrencia otimista

Duas bancadas podem operar a mesma WO sem `expected_rev`.

Proposta:

- Projetar `rev` por card/WO.
- Exigir `expected_rev` em plan/start/finish/void/advance/oven ou `If-Match`.
- 409 com estado atual e mensagem operacional.

Aceite:

- Duplo start/finish/void em rev stale retorna 409 limpo.

### P1 - Pesagem de WO iniciada usa quantidade planejada

Para WO `started`, pesagem deve usar quantidade iniciada, nao plano original.

Proposta:

- Usar `_wo_started_qty` para status `started`.
- Mostrar divergencia planejado vs iniciado.

Aceite:

- Teste com WO planejada 100, iniciada 80, pesa por 80.

### P1 - Falhas de estoque/Orders podem passar silenciosamente

`check_finish_materials` e `_check_linked_order_coverage` fazem fail-open em alguns erros.

Proposta:

- Em superficie operacional, erro de leitura de estoque ou cobertura de pedido bloqueia.
- Override exige permissao, motivo e evento.

Aceite:

- Falha simulada de backend de estoque/order coverage nao permite reduzir ou finalizar sem override.

### P1 - `force` boolean confiado ao cliente

Force/quick/void precisam de trilha e aprovacao.

Proposta:

- Substituir `force: true` por `override_reason`, `override_kind`, `manager_approval` quando aplicavel.
- Backend decide se override e permitido.

Aceite:

- Force sem motivo/aprovador falha; com aprovador gera auditoria.

## Melhorias UX

1. **Bloqueio stale para acoes irreversiveis:** finalizar, void, force e quick exigem refresh valido.
2. **Tela QC com identidade completa:** WO ref, data, SKU, posicao, quantidade iniciada, horario, operador.
3. **Bancada cega verdadeira:** rota de pesagem mostra apenas codigo, ingrediente e peso; mapa fica em reports/management.
4. **Selecao explicita quando ha multiplas WOs do mesmo SKU:** nada de primeira planejada automaticamente.
5. **Impacto antes de force/void:** pedidos vinculados, consumo esperado, estoque faltante, lote gerado, aprovador.
6. **Checklist de mise com hash/plano:** `localStorage` por data nao e controle operacional suficiente.

## Ideias De Alto Impacto

1. **Passaporte da fornada:** QR/painel por WO com receita, lote, operador, posicao, oven run, QC, batch refs, pedidos e stock legs.
2. **Semaforo de confianca:** cada sugestao mostra fonte e confiabilidade.
3. **Close preview com token:** backend preve outputs/perdas/stock; confirmacao usa token curto.
4. **Radar forno x qualidade:** cruzar `OvenRun` com defeitos QC para tendencia.
5. **Modo aeroporto de producao:** proxima acao por bancada, com gargalo e bloqueio.

## Testes

- Permissoes finas para force, void, quick, reports, management, blind map.
- Contract/action URLs nao hardcoded sem schema.
- Grade/defeito desconhecido retorna 400.
- Falha de estoque/Orders bloqueia.
- Weighing usa `started_qty`.
- BI usa markdown congelado de Batch quando existir.
- E2E: stale bloqueia; force exige motivo; fluxo cego nao revela receita; multiplas WOs exigem escolha.

## Fora De Escopo

Cadastro de receita/formula/SKU/grade/defeito, ledger de estoque como fonte da verdade, pedido/pagamento/promessa ao cliente, KDS de venda, BI executivo.

## Prompt Para Agente Executor

```text
Execute WP-05 Producao.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/WP-05-producao.md
- surfaces/production-nuxt/app/*
- shopman/backstage/projections/production.py
- shopman/backstage/api/operations.py
- shopman/backstage/services/production.py
- packages/craftsman/shopman/craftsman/services/scheduling.py
- packages/craftsman/shopman/craftsman/services/execution.py

Fases:
1. Derivar ProductionSurfaceAccess real.
2. Adicionar rev/expected_rev em mutations.
3. Corrigir pesagem por started_qty.
4. Falhar fechado para estoque/Orders com override auditado.
5. UX QC/force/stale/bancada cega.

Nao mova cadastro canonico para Producao.
```

