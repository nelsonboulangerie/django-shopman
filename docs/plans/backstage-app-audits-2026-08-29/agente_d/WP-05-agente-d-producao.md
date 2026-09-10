# WP-05-agente-d — Producao

**Status:** pronto para implementação · **Autor:** Agente D (revisão do WP-05 do Agente G)
**Superfície:** 'surfaces/production-nuxt' + endpoints production/work orders/QC/weighing/reports
**Objetivo:** impedir erro humano escondido em lote, peso, forno, QC, force/void e concorrência entre bancadas — **na leitura E na escrita**.

## Diferenças vs. WP original (Agente G)

**Mantidos (validados):** board nasce com acesso total ('build_production_board' usa '_full_access()' quando 'access=None' — 'production.py:620' — e a API não passa access em 'operations.py:719-722'); mutations não usam 'expected_rev' (core suporta e o backstage ignora); pesagem usa 'work_order.quantity' mesmo para WO started; 'force' é boolean do cliente; fail-open em falhas de estoque/Orders.

**Recalibrados / agravados:**
- **P1 board full access** — o mecanismo de permissões finas **já existe e já está conectado em três lugares** (Admin console 'permissions.py:32-41', hub 'operator/context.py:136-141', SSE 'eventstream.py:118'); só a API do production-nuxt não o usa. A correção é conectar 'resolve_production_access(request.user)' nas views — não construir nada novo. **E o buraco maior está na escrita**: as mutations (plan/start/finish/quick/void/advance) passam só pelo gate coarse 'backstage.operate_production' — as perms 'shop.edit_production_*' **nunca** são consultadas; um usuário com só 'view_planned' consegue plan/start/finish via API. Achado novo, mais grave que o E3 do WP.
- **P1 mutations sem expected_rev** — mantido, com fronteira multi-dono declarada: para a mutation repassar 'expected_rev', a cadeia atravessa backstage → orquestrador ('shop/services/production.py': 'set_planned_quantity':184, 'start_work_order':276, 'finish_work_order':304) → craftsman core (que já suporta, 'scheduling.py:189,264', 'execution.py:45'). **E o 'rev' não existe no contrato** ('WorkOrderCardProjection' sem 'rev'; 'productionContract.ts') — exige dataclass + regeração via 'export_production_schema' + cliente Nuxt. Não tornar 'expected_rev' obrigatório no craftsman (dono documenta last-write-wins como aceitável — 'scheduling.py:194').
- **P1 fail-open** — recalibrado: 'check_finish_materials' **já é fail-closed com 'MODE=strict'** ('production.py:692-694'; graceful sem backend é design intencional, ':672-678'). O fail-open real é '_check_linked_order_coverage', **incondicional** (engole até falha de import — ':648-649').
- **P1 force boolean** — parcial: o cliente Nuxt envia boolean JSON real hoje ('useQcKiosk.ts:57-58'); o problema é o contrato de entrada lenient ('bool("false")' = True) + ausência de trilha/motivo. A proposta correta: parser estrito + 'override_reason'/'override_kind'/'manager_approval' — sem chamar de "bug ativo".
- **Permissões novas** — o WP propunha ~11; **não criar**: as perms por coluna ('shop.view/edit_production_{suggested,planned,started,finished,unsold}') já existem e resolvem 90%; separar só o que falta (force/void/quick como override auditado, não como permissão de coluna).

**Novos (achados da verificação):**
- **Mutations sem perms finas de edição** (acima) — o buraco mais grave do app.
- **'ProductionKDSView' também sem access** ('operations.py:750-761'): 'can_finish=access.can_edit_finished' é **sempre True** na API ('production.py:1551').
- **Race no board**: 'production.py:657,664' — 'WorkOrder.objects.get(ref=item.ref)' sem try/except após 'craft.queue()'; WO voidada entre as duas chamadas → 500 no kiosk.
- **'apply_advance_step' sem conflito**: grava 'meta["steps_progress"]' com 'save(update_fields=["meta"])' sem '_check_rev' ('services/production.py:467-498').

## Fronteira Natural

Produção transforma previsão/pedidos em lotes físicos. Cadastro de receita/fórmula/SKU/qualidade/permissão pertence ao Admin/Craftsman/Stockman. **'expected_rev' atravessa backstage + orquestrador (shop) + craftsman core + contrato TS** — o WP-05 é o coordenador, mas cada dono assina sua camada. As perms 'shop.*_production_*' já existem e são cobertas por 'test_group_permission_parity.py' — nada novo em shop.

## Evidências (verificadas)

- 'access = access or _full_access()': 'shopman/backstage/projections/production.py:620'; '_full_access()': ':2384'.
- 'resolve_production_access(user)' existe e deriva perms finas: 'production.py:2358-2381'.
- 'ProductionBoardView' chama builder sem access: 'shopman/backstage/api/operations.py:712-722'; 'ProductionKDSView' idem: ':750-761'.
- Mutations sem 'expected_rev': 'operations.py:1619,1665,1693'; cadeia omite: 'services/production.py:161,198,386', 'shop/services/production.py:184,276,304'.
- Core suporta 'expected_rev': 'packages/craftsman/.../scheduling.py:189,264', 'execution.py:45'; 'rev' no model: 'work_order.py:86'.
- Pesagem usa 'work_order.quantity': 'production.py:786-791,810'; helper '_wo_started_qty' existe e não é usado aqui: ':2410' (usado em 7 outros pontos).
- 'force=bool(request.data.get("force"))': 'operations.py:1639,1701,1768'.
- '_check_linked_order_coverage' fail-open incondicional: 'services/production.py:605-649' (':648-649'); 'check_finish_materials' com 'MODE=strict': ':671-706'.
- Perms finas de edição nunca consultadas na escrita: grep 'edit_production' só em 'resolve_production_access' e Admin console.
- 'can_finish=access.can_edit_finished' sempre True na API: 'production.py:1551' + view sem access.

## Achados Priorizados

### P1 — Board e KDS com acesso total na leitura; mutations sem perms finas na escrita

Proposta:
- Leitura: 'ProductionBoardView'/'ProductionKDSView'/'ProductionQCView' passam 'access=resolve_production_access(request.user)'.
- Escrita: as 6 mutations checam 'can_edit_<coluna>' do 'ProductionSurfaceAccess' resolvido (plan→'can_edit_planned', start→'can_edit_started', finish/quick→'can_edit_finished', void→'can_manage_all' ou permissão de override).
- 403 com o bloco e a permissão faltante (nunca 200 para escrita negada).

Aceite:
- Usuário com 'view_planned' vê o board mas recebe 403 em plan/start/finish (teste por mutation).
- Usuário com 'edit_planned' planeja e não inicia (colunas independentes).
- 'can_finish' do KDS card reflete a permissão real (teste).

### P1 — Mutations não usam concorrência otimista (expected_rev)

Proposta (multi-dono):
- Contrato: 'WorkOrderCardProjection' ganha 'rev'; regerar 'productionContract.ts' via 'export_production_schema' + teste de drift.
- Cliente: envia 'expected_rev' nas mutations mutáveis.
- Backstage: repassa para os 3 pontos do orquestrador ('shop/services/production.py' — coordenação com o dono).
- Core: manter 'expected_rev' opcional (last-write-wins documentado); nunca torná-lo obrigatório.
- Resposta: 409 com estado atual e mensagem operacional ('_operator_error' já traduz 'STALE_REVISION' → 409 — 'services/production.py:58-61').

Aceite:
- Duplo start/finish/void em rev stale retorna 409 limpo (teste E2E duas bancadas).
- Plano vs início concorrentes não silenciam (antes: last-write-wins).

### P1 — Pesagem de WO iniciada usa quantidade planejada

Proposta:
- 'build_production_weighing' usa '_wo_started_qty(wo)' (helper pronto) para WOs 'started'.
- Mostrar divergência planejado vs iniciado.
- Fallback explícito: WO 'planned' (sem evento started) usa a planejada (comportamento já implementado em ':2418').

Aceite:
- Teste com WO planejada 100, iniciada 80, pesa por 80.
- WO planned pesa pela planejada (sem quebrar).

### P1 — Falhas de estoque/Orders: fail-closed com override auditado

Proposta:
- '_check_linked_order_coverage' ganha a régua 'MODE=strict' do 'check_finish_materials' (fail-closed em superfície operacional; não engolir falha de import).
- Override exige permissão, motivo e evento.
- 'check_finish_materials': manter o design atual (fail-closed com 'MODE=strict'; graceful sem backend é intencional).

Aceite:
- Falha simulada de backend de estoque/order coverage bloqueia reduzir/finalizar (teste).
- Override gera auditoria com motivo/aprovador.
- Craftsman standalone continua funcionando sem 'INVENTORY_BACKEND' (não quebrar o graceful).

### P1 — 'force' boolean confiado ao cliente

Proposta:
- Parser estrito de boolean (mesmo padrão do WP-04).
- Substituir 'force: true' por 'override_reason' + 'override_kind' + 'manager_approval' quando aplicável.
- Backend decide se override é permitido; sem motivo/aprovador → 400.

Aceite:
- 'force="false"' (string) retorna 400 (teste).
- Force sem motivo/aprovador falha; com aprovador gera auditoria.

### P2 — Race no board e advance_step sem conflito

Proposta:
- Board: tratar 'DoesNotExist' no 'get(ref=item.ref)' pós-'craft.queue()' (pular o card em vez de 500).
- 'apply_advance_step': passar 'expected_rev' no mesmo esquema do P1 de concorrência.

Aceite:
- WO voidada entre queue e get não derruba o kiosk (teste).
- Dois operadores avançando passo não sobrescrevem em silêncio.

## Melhorias UX

1. **Bloqueio stale para ações irreversíveis:** finalizar, void, force e quick exigem refresh válido.
2. **Tela QC com identidade completa:** WO ref, data, SKU, posição, quantidade iniciada, horário, operador.
3. **Bancada cega verdadeira:** rota de pesagem mostra apenas código, ingrediente e peso; mapa fica em reports/management.
4. **Seleção explícita quando há múltiplas WOs do mesmo SKU:** nada de primeira planejada automaticamente.
5. **Impacto antes de force/void:** pedidos vinculados, consumo esperado, estoque faltante, lote gerado, aprovador.
6. **Checklist de mise com hash/plano:** 'localStorage' por data não é controle operacional suficiente.

## RBAC / setup_groups

**Nenhuma permissão nova necessária**: as perms 'shop.view/edit_production_*' já existem e são concedidas no 'setup_groups' (paridade coberta por 'test_group_permission_parity.py'). Se a decisão de produto exigir separar "force/void" de "edit_finished", criar 'shop.override_production' e atualizar 'setup_groups' — mas começar SEM permissão nova.

## Pré-requisitos

- Bloco "Contrato de actions" do WP-02-agente-d (payloads/mutations estritas).
- 'expected_rev' exige coordenação com o dono do orquestrador (shop) e regeração do contrato TS (teste de drift).

## Testes

- Permissões finas na escrita: 'view_planned' não plan/start/finish (por mutation).
- 'can_finish' do KDS card reflete permissão real.
- Contract/action URLs não hardcoded sem schema.
- Grade/defeito desconhecido retorna 400.
- Falha de estoque/Orders bloqueia (com e sem 'MODE=strict').
- Weighing usa 'started_qty' com fallback para planned.
- 'expected_rev': 409 stale; contrato com 'rev' (drift test).
- Race do board: void entre queue e get não 500a.
- E2E: stale bloqueia; force exige motivo; fluxo cego não revela receita; múltiplas WOs exigem escolha.

## Fora De Escopo

Cadastro de receita/fórmula/SKU/grade/defeito, ledger de estoque como fonte da verdade, pedido/pagamento/promessa ao cliente, KDS de venda, BI executivo, e **tornar 'expected_rev' obrigatório no craftsman core**.

## Prompt Para Agente Executor

~~~text
Execute WP-05-agente-d (Producao).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-05-agente-d-producao.md
- surfaces/production-nuxt/app/* (board, qc kiosk, expedite, weighing)
- shopman/backstage/projections/production.py (builders, resolve_production_access, _wo_started_qty)
- shopman/backstage/api/operations.py (Production*View, WorkOrder*View)
- shopman/backstage/services/production.py (apply_*, _check_linked_order_coverage, check_finish_materials)
- shopman/shop/services/production.py (set_planned_quantity, start_work_order, finish_work_order)
- packages/craftsman/shopman/craftsman/services/scheduling.py, execution.py

Fases:
1. Conectar resolve_production_access na leitura (board/KDS/QC) E checar can_edit_* nas 6 mutations.
2. rev no card + expected_rev fim a fim (contrato TS, cliente, orquestrador) com 409 stale.
3. Pesagem por started_qty com fallback planned.
4. _check_linked_order_coverage fail-closed com MODE=strict + override auditado.
5. Parser estrito de force + override_reason/manager_approval.
6. Race do board + advance_step com conflito.

Nao crie permissoes novas sem necessidade; nao torne expected_rev obrigatorio no craftsman; nao mova cadastro canonico para Producao.
~~~