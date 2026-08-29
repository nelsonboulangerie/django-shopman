# WP-03-agente-d — Gestor De Pedidos

**Status:** pronto para implementação · **Autor:** Agente D (revisão do WP-03 do Agente G)
**Superfície:** 'surfaces/orders-nuxt' + endpoints orders/courier/feeds/catalog usados pelo Gestor
**Objetivo:** reduzir erro operacional na fila: nenhuma ação errada por contrato incompleto, nenhum despacho sem preflight, nenhuma exceção fiscal/courier/dinheiro escondida — e **nenhum falso-sucesso**.

## Diferenças vs. WP original (Agente G)

**Mantidos (validados):** UI monta action URL manualmente ('useOrdersBoard.ts:116,194'); bulk advance manda corpo vazio; backend 'advance' espera 'change_out'/'equipment' ('operations.py:1054-1066'); permissão única 'shop.manage_orders' em 11+ actions ('_OrderActionBase', 'operations.py:1026-1030'); 'ACTIVE_STATUSES' inclui 'accepted' ('order_queue.py:41') e o frontend não mapeia ('board.ts:16-26'); courier 'Record<string, unknown>' e requeue fiscal por string 'failed'.

**Recalibrados / agravados:**
- **P1 cancelamento** — o WP dizia "backend falha depois"; a verdade é **falso-sucesso**: 'cancellation.cancel' retorna 'False' sem levantar ('cancellation.py:49-54'), 'cancel_order' descarta o retorno ('operator_orders.py:534') e a view responde **'200 {"ok": True}'** ('operations.py:1162'). O operador vê sucesso, o pedido continua ativo e o callback iFood não dispara. Este é o achado mais grave do app — promovido a **P0**.
- **P1 bulk advance** — o WP acertou (bulk exclui troco mas não equipamento — 'bulkableRefs' em 'board.ts:474-478'); agravante confirmado: o servidor aceita 'equipment' vazio no bulk ('_clean_equipment' com lista vazia, 'operator_orders.py:318-326') → **custódia vazia registrada**.
- **P1 permissão única** — mantido, com nota RBAC: o grupo **Caixa já recebe 'manage_orders' + 'operate_pos'** ('setup_groups.py:102-105') — separar 'settle_delivery_cash'/'requeue_fiscal'/courier tem blast radius nas personas; a matriz vai em §RBAC.
- **P2 courier/fiscal heurísticas** — mantido.

**Novos (achados da verificação):**
- **Resíduo de rename no frontend**: 'STATUS_TONE["confirmed"]' ('board.ts:18') é status que **não existe no model** (o backend tem 'ORDER_STATUS_TONES["accepted"]' em 'shop/projections/types.py:65-67') — viola zero-residuals; cards 'accepted' renderizam tom neutro.
- **iFood sem código quando reasons falha**: 'fetchCancellationReasons' retorna '[]' em erro ('useOrdersBoard.ts:176-178'); 'OrderReasonDialog.vue:37-42' exige código só se 'reasons.length > 0' → diálogo vira free-text → 'request_cancellation' falha ('ifood_callbacks.py:128-133') e o pedido fica vivo no marketplace.
- **'save_kitchen_note' sem auditoria** ('operator_orders.py:681-691'): não emite evento nem registra ator — o WP pedia o teste "kitchen_note_updated com ator/diff" sem listar a correção como achado.
- **'OrderCourierCancelView' aceita 'reason_id' opcional** ('operations.py:1505-1511').

## Fronteira Natural

O Gestor é a mesa de decisão operacional de pedidos: triagem, aceite/recusa, avanço físico, despacho, acerto COD, courier, fiscal visível e exceções. Não abre caixa, não opera KDS, não altera WO, não configura fiscal e não vira BI. A matriz de permissões finas toca 'setup_groups' (app shop) — coordenar sem destravar/estravar ações legítimas de caixa.

## Evidências (verificadas)

- Action URL interpolada manualmente: 'surfaces/orders-nuxt/app/composables/useOrdersBoard.ts:116,194'.
- Bulk manda 'body: {}' e exclui só troco: 'useOrdersBoard.ts:185,209', 'surfaces/orders-nuxt/app/presentation/board.ts:474-478'.
- Backend 'advance' lê 'change_out'/'equipment': 'shopman/backstage/api/operations.py:1054-1066'.
- '_OrderActionBase' com 'required_permission = "shop.manage_orders"': 'operations.py:1026-1030'.
- 'ACTIVE_STATUSES = ("new", "accepted", ...)': 'shopman/backstage/projections/order_queue.py:41'.
- 'STATUS_TONE' sem 'accepted' e com 'confirmed' morto: 'surfaces/orders-nuxt/app/presentation/board.ts:16-26'.
- Cancelamento com 200 sem efeito: 'operations.py:1162' → 'operator_orders.py:534' → 'cancellation.py:49-54'.
- Courier 'Record<string, unknown>': 'ordersContract.ts:144'; requeue fiscal por 'directive.status == "failed"': 'order_queue.py:1011-1013'.

## Achados Priorizados

### P0 — Cancelamento falso-sucesso (200 ok sem efeito)

Proposta:
- 'cancel_order' verifica o retorno de 'cancellation.cancel'; status não-cancelável → resposta honesta (409 com o status atual e a próxima ação).
- 'can_cancel' projetado na projection do detalhe/board (com 'cancel_block_label').
- Motivo estruturado obrigatório pós-aceite e em marketplace; iFood com reasons indisponíveis **bloqueia** cancelamento/recusa (nunca free-text).

Aceite:
- Cancelar pedido READY/DISPATCHED/DELIVERED retorna 409 honesto (nunca 200 ok sem efeito).
- Cancelamento pós-aceite sem motivo retorna erro de campo.
- iFood: reasons falhou → cancelamento bloqueado com mensagem, não free-text.
- Teste cobre: cancel OK, cancel fora de status (409), cancel iFood sem reasons (bloqueio).

### P1 — Contrato gerado cobre read model, não actions

Proposta (formato herdado do WP-02 §"Contrato de actions"):
- Manifest de ações por pedido: 'href', 'method', 'label', 'danger', 'requires_input', 'payload_schema', 'error_codes' — gerado da projection.
- UI renderiza botão a partir de capability projetada ('can_advance'/'can_cancel'/'can_requeue_fiscal' etc.).

Aceite:
- Não há botão ativo sem capability do backend.
- Drift de rota/payload quebra teste de contrato.

### P1 — Bulk advance pode despachar entrega com maquininha sem custódia

Proposta:
- 'bulkableRefs' exclui **tudo** de 'dispatchAsks' (troco, equipamento, pendência fiscal/courier), não só troco.
- Preflight de lote: "7 avançam, 2 precisam troco, 1 precisa maquininha".
- Backend: bulk advance sem 'equipment' quando o canal exige → 409 (nunca custódia vazia).

Aceite:
- Nenhum pedido com equipamento sai em bulk sem 'equipment' (teste backend + frontend).
- Selecionar 10 pedidos mostra a contagem por pendência antes de avançar.

### P1 — Permissão única cobre dinheiro, fiscal, cancelamento e courier

Proposta:
- Separar: 'settle_delivery_cash', 'requeue_fiscal', cancelamento pós-aceite, courier cancel/redispatch — com 'setup_groups' atualizado (§RBAC).
- Manter leitura/avanço simples em 'shop.manage_orders'.

Aceite:
- Matriz de permissão por endpoint sensível (teste por endpoint).
- Caixa sem 'settle_delivery_cash' não acerta COD; caixa com continua acertando (paridade de persona preservada).

### P2 — Courier e fiscal são heurísticas locais

Proposta:
- 'CourierBlockProjection' tipada (estado, reason, can_cancel, can_redispatch).
- 'can_requeue_fiscal' + 'requeue_fiscal_block_reason' projetados (sem depender de string 'failed').

Aceite:
- UI não infere dispatch/cancel/requeue por string.

### P2 — Auditoria e resíduos

Proposta:
- 'save_kitchen_note' emite evento com ator + diff (hoje: gravação muda sem trilha).
- Remover 'STATUS_TONE["confirmed"]' (resíduo de rename) e mapear 'accepted' (zero-residuals).
- 'OrderCourierCancelView' exige motivo (campo obrigatório).

Aceite:
- 'kitchen_note_updated' registra ator/diff (teste).
- 'statusTone' cobre 'ACTIVE_STATUSES' (teste).
- Courier cancel sem motivo retorna 400.

## Melhorias UX

1. **Faixa "Exceções agora":** fiscal falhou, courier falhou, COD pendente, maquininha na rua, pagamento bloqueando.
2. **Ações courier no board:** pedidos prontos/falhados não exigem abrir detalhe para agir.
3. **Preflight de despacho:** endereço, instruções, troco, equipamento, cotação, bloqueios.
4. **Dono da espera:** cliente, pagamento, cozinha, courier, fiscal ou operador.
5. **Passagem de turno:** resumo por pedido: últimos eventos, nota, dono, pendências e próxima ação.

## RBAC / setup_groups

Permissões novas: 'settle_delivery_cash', 'requeue_fiscal', 'cancel_order_post_accept', 'courier_cancel' (nomes a confirmar com o dono do shop). **Obrigatório atualizar 'setup_groups.py'**: o grupo Caixa tem 'manage_orders' + 'operate_pos' hoje; decidir quem mantém 'settle_delivery_cash' (caixa? gerente?) e quem ganha 'requeue_fiscal'/'courier_cancel'. Rodar 'tests/test_group_permission_parity.py' — permissão nova que gateia endpoint e não é concedida a ninguém falha a suíte.

## Pré-requisitos

- Bloco "Contrato de actions" do WP-02-agente-d (formato do manifest) — implementar antes do P1 de actions.

## Testes

- Contract test de actions/payloads.
- Frontend: 'statusTone' cobre 'ACTIVE_STATUSES'; 'confirmed' removido.
- Bulk advance exclui troco/equipamento; backend 409 sem equipamento exigido.
- Cancelamento: 200 real / 409 honesto / iFood sem reasons bloqueado.
- Permissões: cash, fiscal, courier cancel, cancel pós-aceite (matriz + paridade de persona).
- Auditoria: 'kitchen_note_updated' com ator/diff.
- E2E: aceite → preparo → pronto → entrega com troco/maquininha → falha courier → requeue fiscal.

## Fora De Escopo

Configurar courier provider, abrir/fechar caixa, operar KDS/WO, regra fiscal profunda, criar feed novo, atendimento self-service, BI/forecast/compras.

## Prompt Para Agente Executor

~~~text
Execute WP-03-agente-d (Gestor de Pedidos).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-03-agente-d-gestor-pedidos.md
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-02-agente-d-pos.md (bloco Contrato de actions)
- surfaces/orders-nuxt/app/composables/useOrdersBoard.ts, useOrderDetail.ts
- surfaces/orders-nuxt/app/pages/index.vue, [ref].vue
- surfaces/orders-nuxt/app/presentation/board.ts
- shopman/backstage/projections/order_queue.py
- shopman/backstage/api/operations.py (Order*View)
- shopman/backstage/services/orders.py
- shopman/shop/services/operator_orders.py, cancellation.py
- shopman/shop/management/commands/setup_groups.py (RBAC)

Fases:
1. P0 cancelamento honesto (409) + can_cancel + motivo estruturado + iFood sem free-text.
2. Manifest de actions/capabilities (formato do WP-02).
3. Bulk advance: bulkableRefs por dispatchAsks + 409 sem equipamento.
4. Permissoes finas com setup_groups e teste de paridade.
5. CourierBlockProjection + can_requeue_fiscal; auditoria de kitchen_note; remover residuo 'confirmed'.
6. UX de excecoes e dono da espera.

Nao invada POS, KDS, Producao ou Fiscalman.
~~~