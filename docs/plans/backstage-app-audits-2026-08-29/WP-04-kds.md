# WP-04 - KDS

**Status:** pronto para implementacao  
**Superficie:** `surfaces/kds-nuxt` + endpoints KDS/cozinha/expedicao  
**Objetivo:** tornar a cozinha impossivel de confundir: ticket certo, estacao certa, item certo, undo rapido, tempo real honesto e payload minimo.

## Fronteira Natural

KDS executa trabalho ja autorizado: preparar, separar, marcar item, finalizar ticket, recall, acknowledge e handoff de expedicao. POS/Gestor decidem venda, pagamento, confirmacao/cancelamento e fire/unfire. Producao decide WO. Pickup publico mostra somente codigo/status sem PII.

## Evidencias Principais

- Projection de item nao expoe `line_id`: `surfaces/kds-nuxt/app/generated/kdsContract.ts:5`.
- UI envia `index`: `surfaces/kds-nuxt/app/composables/useKdsBoard.ts:164`.
- API parseia `index` e `bool(...)`: `shopman/backstage/api/kds.py:86`, `:88`.
- Core muta `ticket.items[index]`: `shopman/shop/services/kds.py:452`.
- Ticket nasce com `line_id`: `shopman/shop/services/kds.py:232`.
- Board usa `ref` da URL: `surfaces/kds-nuxt/app/pages/[ref].vue:14`.
- API exige apenas `backstage.operate_kds`: `shopman/backstage/api/kds.py:47`.
- SSE autoriza por tipo de canal, nao por ref: `shopman/shop/eventstream.py:57`, `:128`.

## Achados Priorizados

### P1 - Item status usa indice mutavel

Se itens forem reordenados, removidos ou reconstruidos, `index` pode marcar item errado.

Proposta:

- Expor `item_ref` ou `line_id` em `KDSItemProjection`.
- POST deve usar `{ item_ref, checked, version }`.
- Retornar 409 se versao/ticket mudou.

Aceite:

- Reordenar itens nao muda qual item sera marcado.
- Teste backend cobre item inexistente, versao stale e payload antigo.

### P1 - `checked = bool("false")` marca verdadeiro

String `"false"` vira `True` em Python.

Proposta:

- Aceitar somente boolean JSON real.
- `string`, `null`, numero e ausencia retornam 400 de campo.

Aceite:

- Teste API: `"false"` retorna 400 e nao altera ticket.

### P1 - Estacao nao esta fortemente vinculada ao board/action/SSE

Qualquer operador com `operate_kds` consegue abrir ref de outra estacao e agir por `ticket_pk`.

Proposta:

- Vincular `KDSInstance` a `Terminal/station_ref` ou allowlist de estacoes.
- Board, actions e SSE validam estacao.
- Override de supervisor exige permissao separada e motivo.

Aceite:

- Estacao A nao le board B, nao opera ticket B e nao assina SSE B.

### P1 - Operador KDS pode administrar configuracao KDS

`KDSInstanceAdmin` usa `backstage.operate_kds` para add/change/delete/view.

Proposta:

- Separar `backstage.operate_kds` de `backstage.manage_kds_config`.
- Operador abre estacao; gerente configura roteamento/SLA/som.

Aceite:

- Usuario operador nao consegue alterar KDSInstance no Admin.

### P2 - Envelopes de mutacao inconsistentes

Check item retorna ticket; done/recall/ack/expedition retornam apenas `{ok}`.

Proposta:

- Padronizar resposta com estado resultante, `updated_at`, `version`, `blocked_reason`.
- UI pode otimizar, mas reconcilia por contrato.

Aceite:

- Todas as mutacoes retornam envelope comum.

## Melhorias UX

1. **Estacao lacrada:** URL errada vira bloqueio com cor/codigo da estacao correta.
2. **Identidade gigante da estacao:** nome/cor/codigo fixos, legiveis a distancia.
3. **Done seguro:** finalizar sem todos os itens exige long press ou confirmacao clara.
4. **Undo imediato:** barra de 5s para check/done/ack quando reversivel.
5. **Expedicao por checklist:** volumes, itens, etiqueta, courier, troco/equipamento antes de liberar.
6. **Estado live/polling/stale:** operador ve ultima atualizacao, nao so pickup publico.
7. **Sons semanticos:** novo ticket, atraso, cancelamento, recall, com cooldown.
8. **Codigo ambiguo:** se sufixos visualmente iguais, promover prefixo/origem/cor.

## Testes

- Backend: estacao A nao toca B.
- API: boolean estrito.
- Contract: `KDSItemProjection` tem identity estavel.
- SSE: payload minimo sem `session_key` salvo justificativa.
- E2E duas estacoes.
- Visual regression: TV/tablet/mobile, nomes longos, notas longas, muitos itens, offline/stale.
- Pickup publico: assert negativo para nome, telefone, endereco, total, `session_key`.

## Fora De Escopo

Pagamento, desconto, preco, caixa, troco contabil, cancelamento comercial, edicao de comanda POS, configuracao runtime de KDS, planejamento produtivo e BI.

## Prompt Para Agente Executor

```text
Execute WP-04 KDS.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/WP-04-kds.md
- surfaces/kds-nuxt/app/composables/useKdsBoard.ts
- surfaces/kds-nuxt/app/pages/[ref].vue
- shopman/backstage/api/kds.py
- shopman/backstage/projections/kds.py
- shopman/backstage/services/kds.py
- shopman/shop/services/kds.py
- shopman/shop/eventstream.py

Fases:
1. Trocar index por item_ref/line_id + version.
2. Parser boolean estrito.
3. Validacao de estacao em board/action/SSE.
4. Permissao separada para config.
5. UX de estacao lacrada, undo e live/stale.

Nao mexa em pagamento, POS ou Producao alem dos contratos de fronteira.
```

