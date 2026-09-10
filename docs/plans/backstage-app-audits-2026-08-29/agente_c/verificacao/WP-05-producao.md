# Verificação WP-05 — Produção

Base verificada: worktree `coordenar-sessoes-deploys-b9cdac`, HEAD `9469c92a2` (descendente do main de 29/08).
Todas as linhas abaixo foram abertas e lidas na função inteira. Onde a linha do WP mudou de lugar, registro a atual.

## A. Superfície real (o que existe hoje)

### Backend — API (`shopman/backstage/api/operations.py`)

| Linha | View | Gate | Nota |
|---|---|---|---|
| 712 | `ProductionBoardView` GET | `backstage.operate_production` | board do planejamento; **não passa `access`** |
| 733 | `ProductionForecastView` GET | `backstage.operate_production` | painel Solari (`build_production_forecast` nem aceita `access`) |
| 750 | `ProductionKDSView` GET | `backstage.operate_production` | **não passa `access`** |
| 771 | `ProductionQCView` GET | `backstage.operate_production` | `build_qc_kiosk` **não tem parâmetro `access`** (:1272) |
| 788 | `ProductionMiseEnPlaceView` GET | `backstage.operate_production` | `expand` parseado por `in ("1","true","yes")` |
| 809 | `ProductionWeighingView` GET | `backstage.operate_production` | tickets de pesagem cega |
| 849 | `ProductionReportsView` GET | `backstage.view_production_reports` | + renderer CSV |
| 877 | `ProductionManagementView` GET | `backstage.view_production_reports` | KPIs do dia |
| 899 | `ProductionBlindMapView` GET | `backstage.view_production_reports` | mapa código-cego ↔ preparo (gestor) |
| 1605 | `_ProductionActionBase` | `backstage.operate_production` | gate ÚNICO das 8 mutations |
| 1619 / 1665 / 1693 / 1727 / 1746 / 1785 / 1807 / 1828 | plan / start / finish / advance-step / quick-finish / void / oven-arm / oven-conclude | idem | |

### Backend — projections (`shopman/backstage/projections/production.py`, 2611 linhas)

`build_production_board`:620 · `build_production_dashboard`:1186 · `build_production_kds`:1240 ·
`build_qc_kiosk`:1272 · `build_production_reports`:1436 · `build_production_weighing`:745 ·
`build_production_blind_map`:834 · `build_production_mise_en_place`:867 · `build_production_forecast`:2533 ·
`resolve_production_access`:2358 · `_full_access`:2384 · `_can_view_card`:2400 · `_wo_started_qty`:2410 ·
`_work_order_recipe_items`:2314 (lê `meta["_recipe_snapshot"]`).

### Backend — serviços e cadeia de escrita

- `shopman/backstage/services/production.py` — `apply_void`:105, `apply_quick_finish`:123, `apply_planned`:161,
  `apply_start`:198, `apply_oven_arm`:226, `apply_oven_conclude`:267, `resolve_partition`:295, `apply_finish`:386,
  `_finish_idempotency_key`:435, `apply_advance_step`:467, `_check_linked_order_coverage`:605,
  `check_finish_materials`:671, `_material_needs_for_work_order`:709, `_record_batch_traceability`:741.
- `shopman/shop/services/production.py` — `void_work_order`:166, `quick_plan`:181, `set_planned_quantity`:208,
  `start_work_order`:300, `finish_work_order`:328, `_ensure_stock_ledger_closed`:375, `_target_date_or_today`:494.
- `packages/craftsman/.../services/scheduling.py` — `_check_rev`:17, `CraftPlanning.adjust`:189, `.start`:265.
- `packages/craftsman/.../services/execution.py` — `CraftExecution.finish`:45 (`expected_rev` na assinatura :52,
  `_check_rev` :99), `.void`:336 (`_check_rev` :352).
- **Ledger (o que os WPs não mapearam):** `packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py` —
  `handle_production_changed` despacha `planned/adjusted/started/voided/finished`; `_leg_lock` + marcadores
  duráveis `stock_consumed_at`/`stock_realized_at` em `WorkOrder.meta` guardam a reexecução das duas pernas
  (`kind=MAKE`). O duplo-toque que creditava a vitrine em dobro **já está fechado** ali, sob trava de linha.

### Superfície Nuxt (`surfaces/production-nuxt`)

Páginas: `index`, `plan`, `board`, `expedite`, `mise-en-place`, `menuboard`, `reports`.
Composables de escrita: `useProductionBoard.ts` (plan/start, guard `busy` por `output_sku`),
`useProductionKds.ts` (advance-step/void, guard `busy` por pk), `useQcKiosk.ts` (finish/quick-finish, guard
`submitting` global), `useOvenFacts.ts` (arm/conclude).
Contrato gerado: `app/generated/productionContract.ts` — `ProductionSurfaceAccess`:132-145, `can_finish`:190;
regerado por `manage.py export_production_schema`, com **teste de drift** em
`shopman/backstage/tests/test_production_schema_export.py`.

### Não mencionado por G nem por D

- `ProductionForecastView` (:733) e `build_production_forecast` (:2533) — o menuboard/Solari, sem `access` e sem
  qualquer noção de permissão por coluna.
- O item de nav do Admin "Relatórios" (`shopman/backstage/admin/navigation.py`:141-146) aponta para
  `<production_url>/reports` e é gateado por `permissions.can_view_production_reports` (:49) — predicado
  **diferente** do gate da API. Ver achado N1.
- `shopman/shop/eventstream.py`:130 — canal SSE `production` gateado por `backstage.operate_production`
  (a linha 118 que D citou como "terceiro ponto conectado" é um **comentário**, não uma chamada).
- `docs/plans/OPERATION-DOMAIN-PLAN.md`:105-150 — a especificação da superfície de chão, incluindo a régua da
  pesagem e a lista canônica das 10 permissões por coluna. Nenhum dos dois WPs cita este documento.

## B. Evidências dos WPs, veredito uma a uma

| # | Afirmação (de quem) | Arquivo:linha ATUAL | Veredito | Nota |
|---|---|---|---|---|
| 1 | `ProductionSurfaceAccess` existe no contrato TS (G) | `surfaces/production-nuxt/app/generated/productionContract.ts:132-145` | CONFIRMADO | Dataclass em `projections/production.py:314-347`; a grid lê `can_view_*`/`can_edit_*` em `ProductionStageGrid.vue:87,92,93,101,106,107,1028`. |
| 2 | `build_production_board` usa `_full_access()` quando `access=None` (G, D) | `projections/production.py:620` | CONFIRMADO | `access = access or _full_access()`; `_full_access` :2384 devolve tudo True, inclusive `can_manage_all`. |
| 3 | API chama o builder com permissão ampla (G, D) | `api/operations.py:716-723` | CONFIRMADO | `build_production_board(selected_date=…, position_ref=…)` — sem `access`. D citou `:712-722`, o corpo do `get` é 716-723. |
| 4 | Mutations não carregam `expected_rev` (G, D) | `api/operations.py:1619,1665,1693,1727,1746,1785`; `backstage/services/production.py:161,198,386,467`; `shop/services/production.py:208,300,328` | CONFIRMADO | Nenhuma das três camadas repassa. G citou `:1619,:1665,:1693` — corretas; faltam advance-step (:1727), quick-finish (:1746) e void (:1785). |
| 5 | Core suporta `expected_rev` (G: `scheduling.py:189,264`; D: + `execution.py:45`) | `scheduling.py:189` (adjust), `:265-270` (start), `execution.py:45/52` (finish), `:336` (void); `_check_rev`:17 | PARCIAL | Substância confirmada; as linhas `264` (G) e `45` (D, como sendo o kwarg) estão fora por 1-7 linhas. `rev` no model: `packages/craftsman/.../models/work_order.py:86`. |
| 6 | Weighing usa `work_order.quantity` (G, D) | `projections/production.py:791,798,810` | CONFIRMADO no fato, **REFUTADO na conclusão** | O número é o planejado, sim. Mas `docs/plans/OPERATION-DOMAIN-PLAN.md:138-146` ancora a pesagem no **planejado do dia** de propósito, e `test_production_blind_prep.py:1-9` fixa a estabilidade da etiqueta ("reimpressão às 10h bate com a etiqueta das 6h"). Trocar para `started_qty` quebra a reimpressão. Ver E1. |
| 7 | Helper `_wo_started_qty` existe (G, D) | `projections/production.py:2410` | CONFIRMADO | Usado em 7 pontos (1323, 1467, 1620, 1764, 1798, 1898, 2571). Duplica a property `WorkOrder.started_qty` (`work_order.py:212`) — o core já expõe o mesmo. |
| 8 | `force` vem como boolean do cliente (G, D) | `api/operations.py:1639,1701,1768` | CONFIRMADO | `force=bool(request.data.get("force"))`. O cliente manda boolean JSON real (`useQcKiosk.ts:57,74`; `expedite.vue:98-105`), então D está certo: hoje não é bug ativo, é contrato frouxo + ausência de trilha. |
| 9 | `check_finish_materials` faz fail-open (G) | `backstage/services/production.py:685-694` | REFUTADO | É fail-**closed** com `CRAFTSMAN_MODE=strict` (:691-693 levanta `ProductionError`); o retorno `[]` sem `INVENTORY_BACKEND` (:681-683) é degradação documentada. D acertou a recalibração. |
| 10 | `_check_linked_order_coverage` é fail-open incondicional (D) | `backstage/services/production.py:648-649` | CONFIRMADO | `except Exception: logger.debug(...)` engole tudo, inclusive `ImportError` da linha 619. Mas D perdeu a falha maior — ver N2, o filtro que nunca casa. |
| 11 | Perms `edit_production_*` nunca consultadas na escrita (D) | `_ProductionActionBase` `api/operations.py:1605-1609` | CONFIRMADO | Único gate = `backstage.operate_production`. `grep -rn edit_production shopman/` só devolve `resolve_production_access` (:2374-2379), `operator/context.py:136`, `setup_groups.py` e testes. Nenhuma mutation consulta. |
| 12 | `can_finish=access.can_edit_finished` é sempre True na API (D) | `projections/production.py:1551` | CONFIRMADO, mas inócuo | `grep -rn can_finish surfaces/production-nuxt/app tests` → só `productionContract.ts:190`. **Nenhum componente lê a chave.** É contrato morto, não capability enganosa. |
| 13 | Race no board: WO **voidada** entre `craft.queue()` e `get(ref=)` → 500 (D) | `projections/production.py:657,664` | REFUTADO como descrito | `void` muda `status`, não apaga a linha (`execution.py:336-…`), e `ref` é `unique=True` (`work_order.py:44-48`), logo nem `DoesNotExist` nem `MultipleObjectsReturned` por void. Só um DELETE real (superusuário no Admin) dispararia. O que sobra de verdade é N+1 — ver N5. |
| 14 | `apply_advance_step` grava `meta` sem `_check_rev` (D) | `backstage/services/production.py:467-499` (`save` em :498) | CONFIRMADO | `save(update_fields=["meta","updated_at"])` sem trava nem revisão; dois avanços simultâneos = last-write-wins silencioso. Gravidade baixa: o ponteiro é ornamental (nenhuma escrita de estoque depende dele). |
| 15 | `resolve_production_access` já conectado em **três** lugares (D) | `backstage/permissions.py:36-38`; `backstage/operator/context.py:134-136`; `shop/eventstream.py:118` | PARCIAL | Dois lugares reais. `eventstream.py:118` é **comentário** explicando por que o predicado dinâmico NÃO cabe no mapa de canais; a regra efetiva é `_BACKSTAGE_CHANNEL_RULES["production"] = ("backstage.operate_production",)` (:130). E `permissions.py:36` é `can_access_production` (gate do hub), não "Admin console". |
| 16 | As 10 perms por coluna já existem e são concedidas no `setup_groups` (D) | `setup_groups.py:116-121` (Cozinha), `:180-189` (Gerente); paridade em `shop/tests/test_group_permission_parity.py:88-97` | CONFIRMADO | Existem, são concedidas e têm teste de paridade. G propor ~11 permissões novas é dívida inventada. |
| 17 | "Separar reports, management, blind map" (G) | `api/operations.py:853,881,903` | JÁ CORRIGIDO | As três já usam `backstage.view_production_reports`, separada do gate de chão, com teste dedicado (`test_api_production_reports.py`). G propõe o que já existe. |
| 18 | "Bancada cega verdadeira: mapa fica em reports/management" (G) | `api/operations.py:899-919`; `projections/production.py:834` | JÁ CORRIGIDO | `ProductionBlindMapView` já é gestor-only, com docstring explícita ("as telas de chão são cegas"). |
| 19 | `_operator_error` traduz `STALE_REVISION` → 409 (D) | `backstage/services/production.py:57-61` | CONFIRMADO | `INVALID_STATUS`/`STALE_REVISION`/`IDEMPOTENCY_CONFLICT` → `ProductionConflict` → 409 em `_production_error_response` (`api/operations.py:152-156`). A infra de 409 já está pronta para receber `expected_rev`. |
| 20 | "force/quick/void precisam de trilha" — implícito de que não há nenhuma (G) | `execution.py:336-…`, `WorkOrderEvent` | PARCIAL | Existe trilha de evento (`WorkOrderEvent` com `actor`) e o void carrega `reason` (`api/operations.py:1787`). O que **não** existe é motivo/aprovador para o `force`. |

## C. Achados confirmados, com gravidade recalibrada

### C1 — Escrita da produção não consulta permissão por coluna (P1)

**Risco × esforço:** risco alto (qualquer conta com `backstage.operate_production` planeja, inicia, fecha e
estorna fornada — e fechar fornada escreve no ledger de estoque), esforço baixo (o resolvedor já existe e já é
testado). P1, não P0, porque os dois grupos que hoje recebem `operate_production` (Cozinha e Gerente) também
recebem as perms de coluna: o buraco é de **arquitetura de gate**, não de exposição ativa no alpha de hoje.

**Mecanismo:** o operador toca "Planejar" → `POST /api/v1/backstage/production/plan/` →
`_ProductionActionBase` (`api/operations.py:1605-1609`) confere só `backstage.operate_production` →
`apply_planned` → `set_planned_quantity` → `CraftPlanning.plan/adjust` → sinal `production_changed` →
`craftsman/contrib/stockman/handlers.py::_handle_planned` cria o Quant planejado. Nenhum ponto da cadeia
pergunta por `shop.edit_production_planned`. O mesmo vale para start (`edit_production_started`) e
finish/quick-finish (`edit_production_finished`, que é a escrita `kind=MAKE` no ledger).

**Fix mínimo:** `_ProductionActionBase` ganha um helper que resolve `resolve_production_access(request.user)`
uma vez e cada view declara a coluna que exige; 403 nomeando a permissão faltante. Sem permissão nova.

### C2 — Leitura: board, KDS, QC e forecast nascem com acesso total (P2)

**Risco × esforço:** risco baixo hoje (é leitura, e os dois grupos já têm as colunas), esforço muito baixo.
Foi P1 nos dois WPs; recalibro para P2 porque a consequência isolada é *ver demais*, não *escrever demais* —
e o C1 é a metade que importa.

**Mecanismo:** `ProductionBoardView.get` (:716-723) chama o builder sem `access`; `build_production_board:620`
cai em `_full_access()`; a projection devolve `access` com tudo True; `ProductionStageGrid.vue:87-107,1028`
renderiza todas as colunas editáveis. Idem `ProductionKDSView` (:754-761) e `ProductionQCView` (:775-782 —
`build_qc_kiosk:1272` **nem aceita** o parâmetro, precisa ganhá-lo).

**Fix mínimo:** `access=resolve_production_access(request.user)` nas três views; `build_qc_kiosk` ganha o kwarg
com o mesmo default. `build_production_forecast` (:2533) fica de fora: é painel público de salão.

### C3 — Concorrência otimista existe no core e é descartada na borda (P1)

**Risco × esforço:** risco médio-alto (duas bancadas na mesma fornada; last-write-wins em quantidade
planejada), esforço médio-alto — atravessa 4 camadas + contrato TS. P1.

**Mecanismo:** `WorkOrder.rev` existe (`work_order.py:86`) e `_check_rev` (`scheduling.py:17-35`) faz
compare-and-swap atômico. `CraftPlanning.adjust`/`start` e `CraftExecution.finish`/`void` todos aceitam
`expected_rev`. Nenhum caller do backstage passa: `shop/services/production.py:208,300,328` não têm o
parâmetro na assinatura, `backstage/services/production.py:161,198,386` idem, as views idem. Resultado: a
bancada A ajusta o planejado para 40 enquanto a bancada B ajusta para 25 sobre um board de 60 segundos de
idade; o último POST vence, sem 409 e sem aviso.

**Fix mínimo:** (a) `WorkOrderCardProjection` ganha `rev`; regerar `productionContract.ts` (o drift test
`test_production_schema_export.py` cobre); (b) `expected_rev` opcional atravessa backstage → shop → core;
(c) o cliente envia o `rev` do card em plan/start/finish/void. **Não** tornar obrigatório no craftsman —
`scheduling.py:194` documenta last-write-wins como aceitável para uso standalone.

### C4 — `force` sem motivo, sem aprovador, sem parser estrito (P2)

**Risco × esforço:** risco médio (o `force` do finish ignora falta de insumo e ainda assim escreve o consumo
`kind=MAKE`, gerando saldo negativo/alerta), esforço baixo. P2, não P1: o alerta `_create_stock_short_alert`
(:657-668) já registra o override, e o cliente hoje manda boolean real.

**Mecanismo:** shortage → `ShortageDialog` → um único botão → `retryWithForce()` (`expedite.vue:472-476`) →
mesmo POST com `force: true` → `apply_finish:409-414` pula o `raise` e só cria alerta. Quem forçou fica no
`actor`, mas o **porquê** não existe em lugar nenhum. E `bool("false") is True`: um cliente que serialize
query-string em vez de JSON força sem querer.

**Fix mínimo:** parser estrito de boolean nas três linhas (`:1639`, `:1701`, `:1768`) e exigir
`override_reason` não-vazio quando `force` for verdadeiro, gravado no `WorkOrderEvent`/alerta. O
`manager_approval` (PIN de gerente, como no PDV) é decisão de produto — ver H2.

### C5 — Seleção implícita quando há várias WOs do mesmo SKU (P2)

**Mecanismo:** `startableWorkOrder` (`app/presentation/production.ts:192-196`) devolve `row.planned_orders[0]`
e `confirmVoid` (`ProductionStageGrid.vue:286-290`) usa `row.started_orders[0]`. Com dois lotes do mesmo pão
no dia, o operador estorna um lote e o sistema estorna outro — sem tela que mostre qual.
**Fix mínimo:** quando `length > 1`, abrir seletor com ref + horário + posição em vez de agir.

## D. Achados NOVOS (que G e D perderam)

### N1 — Relatórios de produção são inalcançáveis para toda persona não-superusuário (P1)

**Risco × esforço:** risco médio-alto (uma tela inteira do app morta para o dono do negócio), esforço mínimo
(uma linha em `setup_groups` ou trocar o gate pelo predicado canônico). P1 por ser um recurso publicado e
inoperante — e porque a trava do teste de paridade *documenta o oposto do que o código faz*.

**Mecanismo, do clique até o efeito:**
1. `ProductionReportsView` / `ProductionManagementView` / `ProductionBlindMapView` declaram
   `required_permission = "backstage.view_production_reports"` (`api/operations.py:853,881,903`), avaliado
   literalmente por `HasBackstagePermission.has_permission` (`api/permissions.py:129-133`).
2. `setup_groups.py` **não concede** essa permissão a grupo nenhum — a única ocorrência do nome no arquivo é
   um comentário (`:77`) explicando por que ela não deve ser varrida por prefixo.
3. Logo: Cozinha 403, Gerente 403, Caixa 403. Só superusuário abre.
4. `useReportsAccess.ts` sonda `/production/management/` e esconde a nav no 403 — então o gestor **nem vê**
   que existe uma tela de relatórios de produção.
5. Ao mesmo tempo, `admin/navigation.py:141-146` mostra o item "Relatórios" usando o predicado
   `permissions.can_view_production_reports` (:49-54), que aceita **`shop.manage_production` OR
   `backstage.view_production_reports`**. Cozinha tem `manage_production` (`setup_groups.py:115`) → o
   padeiro vê o link no Admin, clica, e a página responde 403. Gerente não tem nenhum dos dois → não vê o
   link e também não teria acesso.
6. `shop/tests/test_group_permission_parity.py:111-114` isenta a permissão com a justificativa
   *"OR-alternative in can_view_production_reports; covered by shop.manage_production on Cozinha/Gerente"*.
   A premissa é falsa para a API (que não usa o predicado) e falsa para o Gerente (que não tem
   `manage_production` — o próprio comentário :79-83 diz isso). **A suíte fica verde por causa da isenção.**

Duas decisões documentadas colidem: `docs/guides/rbac-personas.md:32` diz que a permissão é do fluxo
`Produção /reports`; a docstring de `test_api_production_reports.py:6-9` diz que o gate grosso NÃO deve abrir
esses endpoints ("so the kiosk screens stay blind by design"). As duas podem valer ao mesmo tempo — falta só
conceder a permissão a quem deve tê-la.

**Fix mínimo (uma linha):** em `setup_groups.py`, no bloco "Gerente", adicionar
`shop_dclo("view_production_reports"),` e remover a entrada de `UNGRANTED_BY_DESIGN` em
`test_group_permission_parity.py:111-114`. Corolário barato: alinhar o item de nav do Admin ao mesmo gate da
API (trocar `_can_view_production_reports` pelo `has_perm` literal), senão a Cozinha continua vendo um link
que responde 403.

### N2 — O guardrail de cobertura de encomendas nunca dispara no caminho real da tela (P1)

**Risco × esforço:** risco alto (reduzir o planejado abaixo do que já foi vendido, calado — é encomenda de
cliente que não vai existir), esforço mínimo (alinhar o filtro). P1.

**Mecanismo:** o filtro do guardrail e o filtro de quem realmente escreve **não casam**.

`_check_linked_order_coverage` (`backstage/services/production.py:623-632`):
```python
WorkOrder.objects.filter(
    recipe=recipe,
    target_date=target_date_value,     # string crua
    status=WorkOrder.Status.PLANNED,
    position_ref=position_ref or "",   # "" quando o cliente não manda
    operator_ref=operator_ref or "",   # filtro que o escritor NÃO aplica
).first()
```

`set_planned_quantity` (`shop/services/production.py:226-241`):
```python
target_date = _target_date_or_today(target_date_value)
position = str(position_ref or "").strip() or _default_position_ref()
planned_orders = WorkOrder.objects.filter(
    recipe=recipe, target_date=target_date, position_ref=position,
    status=WorkOrder.Status.PLANNED,
).order_by("created_at")
```

Três divergências, e a primeira é fatal no uso normal:
1. **`position_ref`.** `ProductionStageGrid.vue:241` envia `position_ref: board.selected_position_ref ||
   undefined` — ou seja, **nada**, que é o estado padrão do board (sem filtro de posição). O guardrail
   procura `position_ref=""`; o escritor procura `_default_position_ref()`, que no seed vivo é `"massa"`
   (`config/management/commands/seed.py:2542`, único `is_default=True`). O guardrail não acha nada,
   `if not work_order: return` (:633-634), e o planejado é reduzido sem checagem.
2. **`operator_ref`.** O guardrail filtra por operador; o escritor não. WO com `operator_ref="ana"` +
   POST sem operador = guardrail cego, escritor ativo.
3. **Data.** O guardrail usa a string crua; o escritor usa `_target_date_or_today` (:494-498), que **cai
   silenciosamente para hoje** em qualquer string não-ISO. Data malformada = guardrail engolido pelo
   `except Exception` (:648) e planejamento aterrissando no dia errado.

**Por que ninguém viu:** o único teste do assunto,
`test_api_production_surface.py:271-301`, faz `monkeypatch` do `apply_planned` inteiro e passa
`"position_ref": "forno"` explícito. Ele testa o **envelope de erro**, nunca a lógica do guardrail. Cobertura
real de `_check_linked_order_coverage`: zero.

**Fix mínimo:** o guardrail para de refazer a busca e passa a receber a WO de quem escreve — ou, na versão de
uma linha, replica exatamente a régua do escritor:
`position_ref=str(position_ref or "").strip() or _default_position_ref()`, sem `operator_ref`, com
`target_date=_target_date_or_today(target_date_value)`. E o `except Exception` (:648-649) vira fail-closed com
`CRAFTSMAN_MODE=strict`, como D propôs.

### N3 — Pesagem mistura ficha congelada com rendimento vivo (P1)

**Risco × esforço:** risco alto (peso errado de insumo na balança, silencioso, e é exatamente o hazard que o
plano de domínio nomeia), esforço trivial. P1.

**Mecanismo:** em `build_production_weighing` (`projections/production.py:790-791`):
```python
items = _work_order_recipe_items(work_order)              # ← do snapshot (meta["_recipe_snapshot"])
coefficient = Decimal(str(work_order.quantity)) / recipe.batch_size   # ← da receita VIVA
```
O snapshot é gravado no plan com `batch_size` **e** itens (`scheduling.py:118-127`). Se alguém editar o
`batch_size` da ficha entre o planejamento e a pesagem — a mesma manhã basta — o ticket usa as quantidades
congeladas divididas pelo rendimento novo. Um `batch_size` que vai de 10 para 20 corta todos os pesos pela
metade, e a etiqueta cega não dá pista nenhuma: o padeiro pesa 300 g onde a ficha manda 600 g.

Os dois outros consumidores do snapshot fazem certo:
`_material_needs_for_work_order` (`backstage/services/production.py:715-720`) e `CraftExecution.finish`
(`execution.py:127-133`) leem `snapshot["batch_size"]`. A pesagem é a única que mistura.
`docs/plans/OPERATION-DOMAIN-PLAN.md:148-150` manda literalmente preferir o snapshot "evitando que uma edição
posterior da receita altere silenciosamente a pesagem".

**Fix mínimo (uma linha, na prática duas):** extrair o `batch_size` junto com os itens em
`_work_order_recipe_items` (:2314-2322) e usar
`coefficient = Decimal(str(work_order.quantity)) / snapshot_batch_size`.
`build_production_mise_en_place` (:898) tem a mesma origem de erro — usa `recipe.batch_size` com
`_recipe_items(recipe)` (itens vivos): internamente coerente, mas ignora o snapshot; vale o mesmo tratamento
no mesmo PR.

### N4 — Erro de estado inexistente chega ao kiosk como 500 cru (P2)

**Risco × esforço:** risco baixo-médio (probabilidade pequena, impacto de "tela morta com stacktrace" num
kiosk sem teclado), esforço trivial. P2.

**Mecanismo:** `apply_finish` (:394) e `apply_advance_step` (:477) chamam `_get_work_order` (:822-826) sem
try; `apply_start`/`apply_void` delegam a `shop/services/production.py:175,314`, que fazem
`WorkOrder.objects.get(pk=…)` — e o `except Exception` de `apply_start`/`apply_void` devolve a exceção
intacta quando ela não é `CraftError`/`StockError` (`_operator_error:50-51`). `WorkOrder.DoesNotExist` é
`ObjectDoesNotExist`, que o `drf_exception_handler` não converte (`shop/api_errors.py:56-58` devolve `None`)
→ 500. As views só capturam `ProductionError` e `ValueError`.

**Contraste que prova ser lapso e não decisão:** `apply_oven_arm` (:246-249) e `apply_oven_conclude`
(:275-278) tratam `WorkOrder.DoesNotExist` explicitamente → "Ordem de produção não encontrada." Os dois
endpoints de forno acertam; os quatro que escrevem estado, não.

**Fix mínimo:** mover o `try/except WorkOrder.DoesNotExist → ProductionError("Ordem de produção não
encontrada.")` para dentro de `_get_work_order` (:822).

### N5 — Board faz uma query por item da fila (P2, desempenho)

`projections/production.py:655-668`: para cada item de `craft.queue()` roda um
`WorkOrder.objects.select_related(...).get(ref=item.ref)`. Trinta fornadas no dia = 30 queries extras, num
board que refaz o fetch a cada 60 s em kiosk. Não é a race que D descreveu (ver B#13) — é N+1.
**Fix mínimo:** os cards já foram construídos em `wo_cards` (:635-639); indexar por `ref` e reaproveitar,
em vez de reconsultar.

### N6 — A data do planejamento vem do relógio do cliente (P2)

`useProductionBoard.ts:16-20`: `defaultPlanningDate(now = new Date())` decide "hoje ou amanhã" pelo horário
**local do kiosk**, e esse valor viaja como `target_date` no POST de plan (`ProductionStageGrid.vue:240`).
O servidor usa `timezone.localdate()` para tudo o mais. Kiosk com fuso ou relógio errado planeja no dia
errado, e `_target_date_or_today` (`shop/services/production.py:494-498`) não reclama de nada que seja ISO
válido. É a armadilha "uma âncora só de relógio" que a casa já pagou.
**Fix mínimo:** a projection do board já devolve `selected_date`; o default do cliente deve sair de um campo
do servidor (`board.suggested_planning_date`), não de `new Date()`.

### N7 — Sem teto de plausibilidade no servidor para a quantidade fechada (P2)

`resolve_partition` (:295-383) repassa `group.get("quantity")` sem validar; o core só exige `> 0`
(`execution.py:207`, `_positive_decimal`). Não há comparação com `started_qty`. A defesa contra o dígito a
mais é **inteiramente do cliente**: `overshootQty`/`pendingQuestions` (`presentation/qc.ts:137-156`) e o teto
`max = 9999` de `typeDigit` (:196-200). Qualquer POST direto — ou um cliente com bug — credita a vitrine com
o número que mandar, via `kind=MAKE`.
**Fix mínimo:** rejeitar com 400 quando `sum(finished+wasted) > started_qty * K` (K definido pelo dono, ver H3)
sem `override_reason`. Isto é a mesma régua do C4, aplicada à quantidade em vez de ao insumo.

## E. Achados a DESCARTAR (de G ou D)

**E1 — "Pesagem de WO iniciada deve usar `started_qty`" (P1 em G e em D).** Descartar como está escrito.
A pesagem é a preparação que acontece **antes** de iniciar; a etiqueta cega é explicitamente estável no dia
(`test_production_blind_prep.py:1-9` — "reimpressão às 10h bate com a etiqueta das 6h, sempre"), e
`OPERATION-DOMAIN-PLAN.md:138-146` ancora o relatório no planejado do dia. Trocar o número faria uma
reimpressão discordar da etiqueta já colada no pote. O que sobra de legítimo é a segunda metade da proposta
de D: **mostrar** planejado vs. iniciado quando divergem. O bug real de pesagem é o N3, e é outro.

**E2 — "~11 permissões novas" (G).** Descartar. `docs/plans/OPERATION-DOMAIN-PLAN.md:126-135` lista as 10
permissões canônicas por coluna; todas existem, são concedidas em `setup_groups.py:116-121` e `:180-189`, e
têm teste de paridade (`test_group_permission_parity.py:88-97`). D está certo. Não criar nada — exceto,
talvez, uma única `shop.override_production` se a decisão de H2 for separar force/void de `edit_finished`.

**E3 — "Separar reports/management/blind map" e "bancada cega verdadeira" (G).** Já feito
(`api/operations.py:853,881,903` + `ProductionBlindMapView:899`, com docstrings dizendo o porquê e teste em
`test_api_production_reports.py`). O problema desse eixo hoje é o oposto do que G descreve: a separação
existe e a permissão não foi concedida a ninguém (N1).

**E4 — "`check_finish_materials` faz fail-open" (G).** Refutado: `:691-693` levanta com `MODE=strict`.
Manter o comportamento gracioso sem `INVENTORY_BACKEND` (:681-683) — é o que permite o craftsman rodar
standalone, e está documentado na própria docstring.

**E5 — "Race no board: void entre `queue()` e `get()` derruba o kiosk" (D, P2).** Refutado: void não apaga
linha e `ref` é único. Reescrever como N5 (N+1) ou não incluir.

**E6 — "`can_finish` sempre True é capability enganosa" (D).** Rebaixar a nota de rodapé: nenhum arquivo de
`surfaces/production-nuxt/app` lê `can_finish`. Consertar junto com C2 (é uma linha), sem tratar como achado.

**E7 — "Duplo toque no finalizar credita a vitrine em dobro".** Nenhum dos dois afirmou isso, mas é a
suspeita natural de quem lê a superfície — e **já está resolvido**: `_leg_lock` + marcadores
`stock_consumed_at`/`stock_realized_at` em `craftsman/contrib/stockman/handlers.py`, mais
`_finish_idempotency_key` (`backstage/services/production.py:435-466`) e o 409 de
`a88ecabf5 fix(qc): dois quiosques fechando a mesma fornada agora é 409 limpo`. Não reabrir.

## F. Aceites verificáveis

| # | Critério | Como se prova |
|---|---|---|
| F1 | Usuário com `shop.view_production_planned` e `backstage.operate_production`, **sem** `edit_production_planned`, recebe 403 em `POST /production/plan/` | teste de backend, um por mutation (6 asserts), no molde de `test_api_production_surface.py:84-115` |
| F2 | Usuário com `edit_production_planned` planeja (200) e **não** inicia (403 em `/start/`) | teste de backend — prova que as colunas são independentes |
| F3 | `GET /production/` de um usuário sem `view_production_started` devolve `board.access.can_view_started == false` e `started_queue` vazia | assert-negativo de payload |
| F4 | `build_qc_kiosk` aceita `access` e a view o passa | teste de projection + assinatura |
| F5 | Grupo "Gerente" recém-criado por `setup_groups` abre `GET /production/reports/` com 200 | teste de backend usando o próprio `setup_groups` (o padrão de `test_group_permission_parity.py`) |
| F6 | Nenhuma permissão de produção fica em `UNGRANTED_BY_DESIGN` com justificativa falsa | o próprio `test_group_permission_parity.py`, depois de remover a isenção |
| F7 | Plano que reduz quantidade abaixo de encomendas comprometidas devolve 409 `order_shortage` **sem** enviar `position_ref` no POST | teste de backend end-to-end no `apply_planned` real (sem monkeypatch) — é o teste que hoje não existe |
| F8 | Falha do backend de estoque com `CRAFTSMAN_MODE=strict` bloqueia o plan (não só o finish) | teste de backend com backend que levanta |
| F9 | `INVENTORY_BACKEND` ausente continua permitindo finish (não regredir o standalone) | teste de backend existente deve continuar verde |
| F10 | Ticket de pesagem de uma WO planejada com `batch_size` da receita alterado depois usa o `batch_size` do snapshot | teste de projection: planeja, muda `recipe.batch_size`, assere o peso |
| F11 | `force="false"` (string) devolve 400 | teste de backend, três endpoints |
| F12 | `force=true` sem `override_reason` devolve 400; com motivo, grava `WorkOrderEvent`/alerta contendo o motivo | teste de backend |
| F13 | `WorkOrderCardProjection` expõe `rev`; `productionContract.ts` regenerado bate | `test_production_schema_export.py` (drift test já existe) |
| F14 | Segundo `start`/`finish`/`void` com `expected_rev` defasado devolve 409 `state_conflict` | teste de backend simulando duas bancadas |
| F15 | `POST /production/<id_inexistente>/finish/` devolve 400 com "Ordem de produção não encontrada.", nunca 500 | teste de backend, quatro endpoints |
| F16 | Board com N fornadas na fila executa número constante de queries | `django_assert_num_queries` |
| F17 | Linha com 2 WOs iniciadas exige seleção antes de estornar | vitest de `presentation/production.ts` (`startableWorkOrder` devolve lista ou null) + e2e |
| F18 | Fechar com quantidade acima do iniciado sem `override_reason` devolve 400 | teste de backend (assert-negativo de payload) |

Nenhum destes depende de infra inexistente: todos rodam em `make test-framework` / vitest do
`surfaces/production-nuxt`.

## G. Fronteiras e colisões

### Arquivos que este WP precisa tocar

**Backstage (dono deste WP)**
- `shopman/backstage/api/operations.py` — views 712-919 e 1605-1849. ⚠️ arquivo de 2761 linhas **compartilhado
  com PDV, pedidos, fechamento e caixa**: colisão alta com WP-02/03/04/06. Editar só os blocos de produção.
- `shopman/backstage/projections/production.py` — 620, 655-668, 745-833, 867-905, 1240-1272, 1551, 2314-2322.
- `shopman/backstage/services/production.py` — 386-434, 467-499, 605-649, 822-826.
- `shopman/backstage/tests/test_api_production_surface.py`, `test_production_operational.py`,
  `test_production_blind_prep.py`, `test_production_schema_export.py`; **novo** teste de perms na escrita.

**Superfície Nuxt (dono deste WP)**
- `surfaces/production-nuxt/app/generated/productionContract.ts` (regenerado, não editado à mão)
- `app/types/production.ts`, `app/composables/useProductionBoard.ts`, `useProductionKds.ts`, `useQcKiosk.ts`
- `app/components/ProductionStageGrid.vue` (241, 286-296), `ShortageDialog.vue`
- `app/presentation/production.ts` (192-196)

**Fora do backstage — precisa da assinatura do dono**
- `shopman/shop/services/production.py` (208, 300, 328, 494) — `expected_rev` e a régua de data/posição.
  ⚠️ **Este arquivo é o ponto de colisão do C3 e do N2 ao mesmo tempo. Um PR só.**
- `shopman/shop/management/commands/setup_groups.py` — bloco "Gerente" (:180-189), uma linha (N1).
- `shopman/shop/tests/test_group_permission_parity.py:111-114` — remover a isenção.
- `shopman/backstage/admin/navigation.py:141-146` — alinhar o gate do link (N1, corolário).

**Não tocar**
- `packages/craftsman/**` — o core já faz tudo o que é preciso (`_check_rev`, snapshot, idempotência).
  Nenhuma mudança de core neste WP.
- `packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py` — a perna do ledger está correta e a
  proteção de duplo-toque é recente e cara. Fora de escopo.

### Permissões novas e impacto em `setup_groups.py`

Li o arquivo. Hoje concede, em produção: `backstage.operate_production` (Cozinha :114, Gerente :158),
`shop.manage_production` (só Cozinha :115), e as 10 colunas — Cozinha recebe 6
(planned/started/finished × view/edit, :116-121), Gerente recebe 10 (:180-189).
`backstage.view_production_reports` **não é concedida a ninguém** (N1).

- **Nenhuma permissão nova é necessária para C1, C2, C3.** O resolvedor e as colunas já existem.
- **Uma linha é necessária:** `shop_dclo("view_production_reports")` no bloco "Gerente" (N1).
- **Opcional, só se o dono decidir (H2):** `shop.override_production`, para separar force/void de
  `edit_production_finished`. Exigiria migração de `Meta.permissions` em `shop.Shop` + linha no `setup_groups`
  + entrada no `test_group_permission_parity`. Começar sem.

### O que pertence a outro dono

- **craftsman** — `expected_rev`, snapshot da ficha, idempotência do finish: já implementados, não mexer.
- **stockman** — as pernas `kind=MAKE`, o `_leg_lock` e os marcadores: fora de escopo.
- **orquestrador (shop)** — assinatura de `set_planned_quantity`/`start_work_order`/`finish_work_order`,
  `_target_date_or_today`, `_default_position_ref` e o `setup_groups`. C3 e N2 dependem dele.
- **WP-02 (contrato de actions)** — o parser estrito de boolean deve sair de lá, compartilhado; C4 consome.
- **WP-01 (hub)** — o tile de Produção usa `can_access_production`/`resolve_production_access`; se C1 mudar a
  régua de escrita, o hub não muda (ele já é leitura por coluna).

## H. Perguntas abertas para o dono do produto

1. **Relatórios de produção são do Gerente ou do Dono?** (N1) A tela existe, está gateada por
   `backstage.view_production_reports` e ninguém tem a permissão. `rbac-personas.md:32` sugere que é o fluxo do
   gestor; a docstring do teste sugere que a exclusão da Cozinha é deliberada. Concedo ao Gerente, crio um
   grupo "Dono", ou é intencional que seja superusuário-only?

2. **Forçar o fechamento com insumo faltando exige aprovação de gerente, ou só motivo escrito?** (C4) O PDV já
   tem o padrão de PIN de segunda assinatura (`cashman.adjust_shift`). Motivo obrigatório eu implemento
   lendo código; PIN muda o fluxo do kiosk (o padeiro está com as mãos na massa) e é decisão sua.

3. **Qual é o teto de plausibilidade do fechamento?** (N7) Hoje o servidor aceita qualquer número positivo e a
   única defesa é o cliente. Aceitar até quanto acima do iniciado sem override — 10%, 20%, qualquer coisa com
   motivo? Preciso do número para escrever o assert.
