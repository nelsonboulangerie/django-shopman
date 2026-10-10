> Anexo do [WP-OPERADOR-NUXTUI-ONDAS](../WP-OPERADOR-NUXTUI-ONDAS.md). Leitura de código em 08/10/2026 sobre `e79ed522d` (pilha do Gestor #1528 + #1521), sem build nem navegador. Vale como mapa de arquivo:linha; o que foi visto em tela está no corpo do plano e nos PRs.

# Inventário da Produção (production-nuxt) para a migração ao cânone Nuxt UI

Auditoria de leitura, sem build e sem teste. Branch `claude/operador-nuxtui-onda0-base` (HEAD `e79ed522d`).
Todo caminho é relativo a `surfaces/production-nuxt/` salvo quando começa por `operator-kit/` ou `scripts/`.
O laudo citado (`docs/plans/WP-GESTOR-CANON-LAUDO.md`) não está nesta árvore: foi lido do commit `2ef7e958b`.

## 0. Números de cabeça

| Medida | Valor |
|---|---|
| Páginas (rotas) | 14 arquivos, 14 rotas (`/`, `/plan`, `/mise-en-place`, `/close`, `/quality`, `/timers`, `/settings`, `/board`, `/reports`, `/recipes`, `/recipes/new`, `/recipes/:ref`, `/recipes/:ref/edit`, `/recipes/compare`) |
| Componentes locais | 19 (`app/components`), 6.900 linhas; o maior é `ProductionStageGrid.vue` com 2.442 |
| Composables locais | 27 |
| Diálogos `UiDialog` | 14 instâncias; `UiSheet` 3; `UiPopover` 5 |
| `Nuxt*` de Nuxt UI usados direto no app | 0 (só `NuxtLink`, `NuxtPage`, `NuxtRouteAnnouncer`, que são do Nuxt) |
| `Ui*` (camada ui-thing do kit) | `UiButton` 96, `UiInput` 23, `UiBadge` 19, `UiNativeSelect` 18, `UiDialog*` 14 famílias, `UiTextarea` 9, `UiCheckbox` 7, `UiPopover` 5, `UiTabs` 3, `UiSheet` 3, `UiFilterChip` 2, `UiIconButton` 1, `UiAlert` 1 |
| HTML cru | `<button>` 90 (+2 `component :is` que viram botão), `<input>` 5, `<select>` 1, `<table>` 14, `<form>` 4, `<label>` 40, `<kbd>` 2 |
| `:ui=` por instância | 0 |
| `type="date|time|..."` no app | 0; herdado do kit em 6 usos de `OperatorPeriodPicker` |
| Valores arbitrários `[...]` | 74 ocorrências em 17 arquivos (30 só no `ProductionStageGrid.vue`) |
| Travessão (U+2014) | 165 no app: 3 no código gerado, ~136 em comentário, 26 visíveis como marcador de valor vazio |
| SSE | nenhum: só poll (8 projeções) |
| Endpoints `/api/v1` | 12 GET de projeção + 11 POST de mutação + 13 do livro de receitas + 4 de impressão |
| Testes vitest | ~465 casos (139 de componente); Playwright 19 testes × 7 projetos |
| Teto do ledger (`native_control_occurrences`) | 96; medido hoje 91 (`python scripts/check_operator_component_ledger.py --json`) |

## 1. Telas

O shell é `app/app.vue`. Ele monta `OperatorSessionUnavailable` (`app.vue:52`), `OperatorLogin` (`:53`), `OperatorLock` (`:54`), `OperatorStationSetup` (`:55`), `OperatorSonner` (`:61`), `OperatorPwaRuntime` (`:62`) e `OfflineBanner` (`:30`). A permissão do gate é `backstage.operate_production` (`app.vue:10`).

Há duas classes de tela:

- **Telas de operador:** ficam no rail da suíte (`ProductionNav place="rail"`, `app.vue:38`) e na barra do polegar (`ProductionNav place="bar"`, `app.vue:47`).
- **Kiosk:** é a rota `/board`. Fica fora do rail e dentro do gate (`app.vue:14,32`).

Cada tela de operador usa um de dois cabeçalhos: `ProductionHeader` (wrapper de `OperatorPageHeader`) ou `RecipeHeader` (outro wrapper do mesmo `OperatorPageHeader`).

| Rota | Arquivo | O que mostra | Cabeçalho / shell |
|---|---|---|---|
| `/` | `pages/index.vue:8` | Abertura: lente `open` da grade (Planejado → Previsto, "Confirmar") | `ProductionStageGrid stage="open"` → `ProductionHeader` |
| `/plan` | `pages/plan.vue:7` | Planejamento: lente `plan` (Sugerido → Planejado, "Planejar N", conjunto "sem ressalva", "sem sugestão", linha de planejados) | `ProductionStageGrid stage="plan"` → `ProductionHeader` |
| `/mise-en-place` | `pages/mise-en-place.vue` | Preparação: "Por preparo" (fichas de pesagem com código cego) e "Por insumo" (tabela com checklist local por posto) + impressão de etiquetas | `ProductionHeader` (`:169`), conteúdo `print:hidden` |
| `/close` | `pages/close.vue` | Fechamento: cartões dos lotes abertos do dia, timer do forno por lote, "Finalizar" → `QcCloseScreen`, leitor de etiqueta, lote avulso | `ProductionHeader` (`:408`) |
| `/quality` | `pages/quality.vue` | Qualidade: abas "Para confirmar"/"Confirmados" (`QualityGatePanel`), confirmação em lote, correção via `QcCloseScreen mode="correct"` | `ProductionHeader` (`:219`) com `#menu` (dia anterior/seguinte) e `#actions` (abas) |
| `/timers` | `pages/timers.vue` | Timers da bancada: fileira de etiquetas (servidor) + timers em andamento (localStorage) | `ProductionHeader` (`:66`) |
| `/settings` | `pages/settings.vue` | Ajustes: lista de links para Receitas, Relatórios e Letreiro | `ProductionHeader searchable=false` (`:20`) |
| `/board` | `pages/board.vue` | Letreiro Solari (kiosk de TV): palhetas, relógio, paginação, som, tela cheia | sem rail, sem `OperatorPageHeader`; `<main class="board">` com pele própria (`:111`, CSS `:270-438`) |
| `/reports` | `pages/reports.vue` | Gestão do dia (4 cartões, atrasos, mapa cego) + relatórios (histórico, operador, qualidade, desperdício) com filtros, paginação por cursor e CSV | `ProductionHeader searchable=false` (`:129`) |
| `/recipes` | `pages/recipes/index.vue` | Inventário de receitas: filtro por tipo, 4 checkboxes, cartões com estrela | `RecipeHeader` (`:54`) |
| `/recipes/new` | `pages/recipes/new.vue` | Nova receita: abas "porta" (nota, foto, manual), captura por IA, tabela de candidatos | `RecipeHeader` (`:188`) |
| `/recipes/:ref` | `pages/recipes/[ref]/index.vue` | Detalhe: SKU, favorita, detalhes, arquivar, versões, lente da fórmula, avaliação, referências externas, publicar | `RecipeHeader` (`:189`) |
| `/recipes/:ref/edit` | `pages/recipes/[ref]/edit.vue` | Editor da versão rascunho: âncora, itens, partes, padronizar, origem | `RecipeHeader` (`:282`) |
| `/recipes/compare` | `pages/recipes/compare.vue` | Compara duas versões (2 tabelas) | `RecipeHeader` (`:67`) |

Observação: o `README.md:31-35,65-68` ainda descreve `/` como "Chão ao vivo". Hoje `/` é a Abertura (`pages/index.vue:2`). O README está desatualizado.

## 2. Gestos (inventário de zero regressão)

Convenções da tabela:

- "POST X" é a função de `app/generated/productionContract.ts`.
- Toda mutação de produção passa por `useProductionMutationGuard`, que exige estação online e projeção fresca e envia `idempotency_key` e `expected_rev`.

### 2.1 Cabeçalho (`components/ProductionHeader.vue`), em toda tela de operador

| Gesto | Disparo | Efeito |
|---|---|---|
| ⋯ abre menu | `ProductionHeader.vue:194-205` (UiPopover + `<button data-header-menu>`) | painel `role="menu"` à mão (`:212`) |
| Atualizar | `:222-242` (`data-header-refresh`, tecla R) | `emit("refresh")` → cada página refaz o fetch |
| Abrir timers | `:243-254` (NuxtLink) | `/timers` |
| Slot `#menu` da página | `:255` | Fechamento: "Lote avulso" (`close.vue:433-447`); Qualidade: dia anterior/seguinte/hoje/relatórios (`quality.vue:230-281`) |
| Ferramentas no celular | `:256-268` | links Receitas, Relatórios, Letreiro (`md:hidden`) |
| Atalhos desta tela | `:270-285` (tecla ?) | abre a ajuda do kit (`useOperatorShortcuts`) |
| Lupa do tablet de toque | `:319-328` (`touchTablet && !tabletSearchOpen`) | `openTabletSearch` → `searchInput.focus()` |
| Busca | `:329-338` `OperatorSuiteSearch v-model=query`, `@focusout=closeTabletSearchIfEmpty` | filtra a lista da tela |
| Teclado global | `onGlobalKeydown` `:115-137`, montado em `:142` | Alt+1..5 navegam (`SHORTCUT_ROUTES :107`); `/` foca a busca; R atualiza; ? abre a ajuda |
| Ao vivo | `:308-317` `OperatorLiveStatus tone=liveTone` (`:102`: `stale ? "late" : "live"`) | só leitura |
| Progresso do dia | `:347-370` (`role="progressbar"` à mão) | só leitura |

### 2.2 Grade (`components/ProductionStageGrid.vue`), em `/` e `/plan`

| Gesto | Disparo | Endpoint / composable |
|---|---|---|
| Trocar o dia (‹ › e popover) | `OperatorPeriodPicker` `:1001-1008` | `useProductionBoard` refaz o GET `/api/v1/backstage/production/?date=` |
| Filtros Plan: Todos/A planejar/Com ressalva/Planejados | `UiFilterChip` `:1012-1035` | local (`planFilter`) |
| Filtros Open: Todos/A confirmar/Abertos | `UiFilterChip` `:1038-1061` | local (`openFilter`) |
| Filtro por ficha-base | `<select>` transparente sobre um `<label>` estilizado, `:1065-1086` | local (`baseFilter`) |
| Tentar de novo (erro sem dado) | `UiButton` `:1116-1124` | `refresh()` |
| Ir para o Planejamento (vazio) | NuxtLink `:1145-1151` | `/plan` |
| Chip de encomendas da linha | `<button data-commitment-chip>` `:1193-1203` (plan), `:1699-1709` (open) | abre o diálogo de encomendas (`commitmentsRow`) |
| "Por quê" da sugestão | `<button data-plan-reason-trigger>` `:1260-1277` dentro de `UiPopover` ancorado `:1212-1307`; `@interact-outside=onReasonOutside` `:1287`, `@close-auto-focus` `:1288` | `PlanReasonCard` |
| "voltar" (desfaz o rascunho da linha) | `<button>` `:1238-1244` | `resetDraft` |
| Stepper − / + da linha | `<button>` `:1325-1333`, `:1346-1354` | `bumpDraft` |
| Digitar a quantidade da linha | `<input type=text inputmode=decimal>` `:1334-1345`; Enter → `planInline` | |
| "Planejar N" da linha | `<button data-plan-inline>` `:1366-1385` | `submitPlan` → POST `planProduction` (`/production/plan/`) |
| "Ver um a um" (sem ressalva) | `<button data-plan-clean-expand>` `:1414-1422` | local |
| "Planejar os N como sugerido" | `<button data-plan-clean-all>` `:1423-1439` | `planCleanSet` (um POST `plan` por linha, `:879-902`) |
| "Ver um a um" (sem sugestão) | `<button data-plan-manual-expand>` `:1468-1476` | local |
| Toque num planejado (popover) | `<button data-planned-row>` `:1517-1533` em `UiPopover` `:1512-1586` | menu: "Corrigir quantidade"/"Planejar novo lote" `:1552-1572` → `onAction` → diálogo de planejar; "Ver encomendas" `:1573-1584` |
| ⋮ da linha de planejados | `<button data-planned-line-menu>` `:1604-1611` em `UiPopover` `:1602-1637` | lista "Corrigir um planejado" `:1621-1635` → `onAction` |
| Confirmar (Abertura) | `<button data-open-confirm>` `:1770-1786` | `openStart` → diálogo ou painel encaixado |
| "Confirmando ›" (fecha o painel encaixado) | `<button data-open-confirming>` `:1760-1769` | `startRow = null` |
| Ver lançamento | `<button data-open-view-launch>` `:1788-1798` | `openStarted` + `kds.refresh()` (GET `/production/kds/`) |
| ⋯ da linha aberta | `<button data-open-row-menu>` `:1801-1809`, painel `role="menu"` `:1814-1863` | Ver lançamento `:1818`; Confirmar previsto `:1828`; Ver encomendas `:1838`; Cancelar lote… `:1852` → `openVoid` |
| Pressionar e segurar a linha (toque, 550 ms) | `@pointerdown/up/leave/cancel` `:1682-1685` → `onRowPress` `:647-659` | abre o ⋯ da linha |
| Clique direito (tablet deitado) | `@contextmenu` `:1686` → `onRowContextMenu` `:660-664` | abre o ⋯ da linha |
| Painel encaixado: fechar | `<button>` `:1909-1919` | `startRow = null` |
| Painel encaixado: escolher o lote | `<button aria-pressed>` `:1925-1949` | `selectStartWorkOrder` |
| Painel encaixado: − / + | `<button>` `:1957-1964`, `:1974-1981` | `bump('start', ±1)` |
| Painel encaixado: campo | `<input inputmode="none">` `:1965-1973`; Enter → `confirmStart` | |
| Painel encaixado: numpad | `OperatorNumpad` `:1986-1992` | `startDigit`, `startBackspace`, `startClear` |
| Painel encaixado: Cancelar / Confirmar N | `UiButton` `:1996-2020` | `confirmStart` → POST `startProductionWorkOrder` (`/production/<id>/start/`) |
| Diálogo Planejar: escolher o lote | `<button>` `:2062-2073` | `selectPlannedWorkOrder` |
| Diálogo Planejar: − / campo / + | `:2098-2125`; Enter → `confirmPlan` | POST `plan` |
| Diálogo Planejar: Cancelar / Confirmar | `UiButton` `:2128-2154` | |
| Diálogo Confirmar (não encaixado) | `UiDialog` `:2160-2264`: lote `:2194`, − / campo / + `:2213-2237`, Cancelar/Confirmar `:2247-2261` | POST `start` |
| Diálogo do lote aberto | `UiDialog` `:2267-2375`: escolher o lote `:2310`; "Cancelar lote…" `:2344`; motivo `UiTextarea` `:2335`; "Confirmar cancelamento" `:2353` → `confirmVoid` `:620` | POST `voidProductionWorkOrder` (`/production/<id>/void/`) via `useProductionKds` |
| Diálogo de encomendas: Fechar | `UiDialog` `:2378-2429`, `:2420` | |
| Falta (shortage) | `ShortageDialog` `:2431-2440` | Confirmar com motivo → `retryPlanWithForce` (`plan` com `force`, `override_proof`); Revisar quantidade → `reviewShortage` `:569` |

### 2.3 `PlanReasonCard.vue`

- **Fechar:** `:72-76`, com a dica visual `OperatorKbd` "Esc" em `:71`.
- **Planejar a alternativa (manual):** `:213-218`.
- **Planejar como sugerido:** `:223-228`.
- **Fechar (rodapé):** `:233-237`.
- **Esc:** quem fecha é o popover.

### 2.4 `ShortageDialog.vue`

- **Cancelar:** `:132`.
- **Revisar quantidade:** `:139`, emite `review`.
- **Confirmar override:** `:147`, emite `confirm(reason, proof)`. Exige o `UiTextarea` de motivo (`:120`).

### 2.5 Fechamento (`pages/close.vue`)

| Gesto | Disparo | Endpoint / composable |
|---|---|---|
| Dia (só para trás, `:max=today`) | `OperatorPeriodPicker` `:423-431` | GET `/production/qc/?date=` (`useQcKiosk`) |
| Lote avulso (no ⋯) | `<button data-close-off-plan>` `:434-446` | abre o `UiSheet` `:670-691` → tiles de receita `:678-687` → `openOffPlan` |
| Lotes de dias anteriores | `<button>` aviso inteiro `:483-498` | `selectedDate = previous_open_date` |
| Toque no cartão: timer do forno | `<component :is="button">` `:539-613` → `openOven` `:308` | só abre o diálogo |
| Finalizar (tile de 80 px) | `<button>` `:618-646` → `openOrder` `:119` | se houver `oven_conclude`: POST `concludeProductionOven` (`/production/<id>/oven/conclude/`) e depois abre o `QcCloseScreen` |
| Ler etiqueta do lote | `<button data-close-scan-label>` `:657-665` | `LotLabelScanner` `:667` → `onLotCode` `:145` (`matchLotCode`) |
| Diálogo do timer: X grande | `UiDialogClose` `:719-724` (`hide-close` `:715`) | |
| Timer: dígitos, +1/+5/+10, C, 0, ⌫ | `<button>` `:797-840` | `ovenDigit`, `ovenAdd`, `clearOvenMinutes`, `ovenBackspace` |
| Timer: Iniciar | `<button>` `:841-849` → `startOven` `:338` | POST `armProductionOven` (`/production/<id>/oven/arm/`) + `useFloorTimers.arm` (localStorage) |
| Timer correndo: +1/+5/+10 | `<button>` `:859-867` | `oven.extend` (local) |
| Timer tocando: Visto | `<button>` `:868-876` → `markOvenSeen` | local (nunca mede o forno) |
| Teclado do timer | `onTimerKeydown` `:370-403`, montado em `:286` | 0-9, ⌫, C/Delete, Enter (Iniciar); tocando, Enter = Visto |
| Fechar o lote | `QcCloseScreen @confirm` `:462` → `onConfirm` `:178` | POST `finishProductionWorkOrder` (`/production/<id>/finish/`) ou `quickFinishProduction` (`/production/quick-finish/`) |
| Falta no fechamento | `ShortageDialog` `:693-701` → `retryWithForce` | o mesmo POST com `force` |

### 2.6 `QcCloseScreen.vue` (Fechamento e correção da Qualidade)

- **Voltar:** `UiButton` `:577-584` → `requestBack` `:498`. Se houver alteração, pergunta com `useConfirm` (`:496`, diálogo do kit `OperatorConfirmDialog`, já em NuxtModal).
- **Grau:** `<button>` `:665-672` → `activateGrade` `:294`. Dois toques em até 600 ms (`DOUBLE_ACTIVATION_MS` `:277`) tomam o saldo disponível.
- **Motivo do grau:** `<button>` `:696-718`.
- **Perda:** `<button>` `:728-733` → `pickLoss`.
- **Motivo da perda:** `<button>` `:757-764`.
- **Numpad:** `OperatorNumpad` `:636-643`.
- **Confirmar:** `UiButton` `:775-784`.
- **Sheet de perguntas:** `UiSheet` `:797`.
  - excedente: textarea `:818`, "corrigir" `:829` e "confirmar" `:838`;
  - presets de motivo da correção: `<button aria-pressed>` `:860-872`;
  - textarea `:881`, confirmar `:891`;
  - defeitos: `<button>` `:903-908` → `answerDefect`.
- **Teclado físico:** `onKeydown` `:523-562`, montado em `:564`.
  - Esc fecha a sheet ou volta;
  - 0-9, ⌫ e C/Delete digitam no grau ativo;
  - Enter do numpad confirma.
  - O escopo é `data-production-shortcut-scope="exclusive"` (`:574`).

### 2.7 Qualidade (`pages/quality.vue` + `components/QualityGatePanel.vue`)

**Na página:**

- Dia anterior: `quality.vue:232-244`.
- Dia seguinte: `:245-257`.
- Voltar para hoje: `:258-270`.
- Relatórios de qualidade: `:271-279`.
- Abas "Para confirmar"/"Confirmados": `UiTabs` `:283-298`.

**No painel (`QualityGatePanel.vue`):**

- Abas próprias (escondidas aqui por `hide-tabs`): `:119-133`.
- Mostrar todos os limpos: `:191-197`.
- Confirmar em lote: `:247-254` → `reviewQualityBatch`, POST `/production/quality-review/batch/`.
- Ir ao Fechamento: `:294-298` → `goClose`.
- Corrigir: `:377-383` e `:450-456` → `openCorrection`. Depois, `QcCloseScreen mode=correct` (`quality.vue:302-316`) → `correctQuality`, POST `/production/<id>/quality-correction/`.
- Confirmar um: `:388-394` → `reviewQuality`, POST `/production/<id>/quality-review/`.

### 2.8 Preparação (`pages/mise-en-place.vue`)

| Gesto | Disparo | Efeito |
|---|---|---|
| Dia | `OperatorPeriodPicker` `:178-185` | GET `/production/mise-en-place/` e `/production/weighing/` |
| Por preparo / Por insumo | segmento à mão, `<button aria-pressed>` `:198-223` | local |
| Explodir até matéria-prima | `UiCheckbox` `:242-247` | refaz o GET com `expand` |
| Etiquetas de pesagem / Identificação interna | `UiButton` `:249-262` | abre o `ProductionLabelPrintDialog` |
| Tentar de novo | `UiButton` `:292-300`, `:529-535` | refresh |
| Marcar separado | `UiCheckbox` `:369-372` → `toggleChecked` | localStorage escopado por posto (`useMiseEnPlace.ts:33,112`) |
| Ver receitas que usam o insumo | `<button>` `:447-453` → `toggleBreakdown` | local |
| Imprimir etiquetas de um preparo | `UiButton size=icon` `:610-620` | abre o diálogo de impressão |
| Planejar produção (vazio) | NuxtLink `:309`, `:548` | `/plan` |

### 2.9 Impressão de etiquetas (`ProductionLabelPrintDialog.vue` + `useProductionLabelPrinting.ts`)

**Diálogo:** `UiDialog` `:390`, com `UiAlert` (`:404`). As ações:

- Atualizar a fonte: `:582-587`.
- Reconciliar: `:591-597`.
- "Saíram" / "Não saíram": `:628-643` → `printing.confirm(true|false)`.
- Imprimir N etiquetas: `:653-663` → `printBestAvailable` (relay ou agente local).
- Abrir impressão do navegador: `:668-675` → `window.print()` (`:270-290`).
- Tentar de novo: `:681-687`.
- Reimprimir: `:691-698`.
- Fechar: `:707`.

**Endpoints:** `/api/v1/backstage/production/weighing/print-jobs/` (POST e GET de acompanhamento), com poll adaptativo (`useProductionLabelPrinting.ts:96,192`).

**Papel:** o payload congelado fica fora do diálogo (`:716-731`, `WeighingLabels`). O `@media print` esconde `[data-slot="dialog-overlay"]` (`:743-747`).

### 2.10 Timers (`pages/timers.vue`, `FloorTimerCard.vue`, `FloorTimerCreateDialog.vue`)

- **Disparar etiqueta:** `<button>` `timers.vue:81-95` → `fireTag`. Cria o timer em `useFloorTimers` (localStorage `producao.timers`) e mostra um toast.
- **Novo timer:** `timers.vue:97-106` → `FloorTimerCreateDialog` (`:156`).
  - numpad à mão: `:148-197`;
  - nome `UiInput` (`:203`), Enter inicia;
  - "Guardar como etiqueta" `UiCheckbox` (`:215`) → POST `/production/timer-tags/` (`useTimerTags.ts:59`);
  - teclado `onKeydown` `:79-104`.
- **Cartão:** toque no corpo `FloorTimerCard.vue:68-79` → Visto ou Encerrar, com janela anti-quique `FLOOR_TIMER_ARM_MS` (`:33-46`); +5 min `:108-115`; Encerrar `:116-123`.

### 2.11 Letreiro (`pages/board.vue`)

- **Dia:** `OperatorPeriodPicker` `:127-134`. O setter destrava o som (`:55`).
- **Som:** `<button class="board-key">` `:137-153` → `sound.toggle()` (`useFlapClack`, AudioContext + localStorage).
- **Tela cheia:** `:154-164` → `toggleFullscreen` (`useKioskMode` `:89-95`).
- **Ponto de página:** `<button>` `:251-263` → `pages.goTo`.
- **Timers sem gesto:**
  - relógio de 1 s com virada do dia à meia-noite (`:67-80`, `resolveDayRollover`);
  - re-giro do atrasado a cada 25 s (`:77`);
  - rotação de página a cada 12 s (`useBoardPages.ts:7,40`);
  - poll de 30 s (`useProductionForecast.ts:21`).

### 2.12 Relatórios (`pages/reports.vue`)

- **Data da gestão:** `OperatorPeriodPicker` `:160-167`, que dispara GET `/production/management/` e `/production/weighing/blind-map/`.
- **Tipo de relatório:** segmento à mão `:292-306` → `changeReportKind`.
- **CSV:**
  - Baixar CSV: `:308-324` → `downloadCsv` (`$fetch` blob, `useProductionReports.ts:102`);
  - Cancelar a exportação: `:326-334`.
- **Período do relatório:** `OperatorPeriodPicker` com `custom` e presets `day/week/month/7d/28d` (`:355-364`).
- **Filtros:**
  - ficha técnica: `UiNativeSelect` `:368`;
  - posto: `:381`;
  - operador: `UiInput` `:394`;
  - ordenar: `UiNativeSelect` `:403`;
  - Aplicar: `:423-429`.
- **Recuperação:**
  - Reconciliar relatório: `:454-460`;
  - Tentar de novo: `:495-501`.
- **Paginação:** Anterior `:718-724`, Próxima `:728-734`, ambas por `openCursor`.

### 2.13 Receitas

**`recipes/index.vue`:**

- Nova receita: NuxtLink com cara de botão, `:63-70`.
- Tipo: segmento `<button aria-pressed>` `:98-120`.
- 4 `UiCheckbox` (Favoritas, Sem SKU, Com rascunho, Arquivadas): `:127-130`.
- Tentar de novo: `:152`.
- Limpar filtros: `:181`.
- Cartão: NuxtLink `:189-241`.
- Estrela: `<button>` `:242-250` → `toggleFavorite`, POST/DELETE `/recipes/<ref>/favorite/`.

**`recipes/[ref]/index.vue`:**

- SKU:
  - editar: `:253-259`;
  - form salvar: `:264`;
  - salvar: `:274`;
  - cancelar: `:281`.
- Favorita: `:298-305`.
- Detalhes: `:314-319`, abre `UiDialog` `:545` com nome, tipo e notas; salvar em `:572`.
- Arquivar: `:323-328`, abre `UiDialog` `:584`; confirmar em `:600-609`.
- Versão:
  - editar rascunho: `:359`;
  - publicar: `:368`, abre `UiDialog` `:479` com tabela `:510`; confirmar em `:533`;
  - nova versão: `:376`;
  - comparar: `:385`, `:394`;
  - escolher versão: `<button aria-pressed>` `:430-439`.
- Peças:
  - `RecipeVersionRating`: abrir `:64`; notas `:107-117`; enviar `:131`;
  - `RecipeExternalReferences`: adicionar `:61`, remover `:89`, form `:112`, confirmar remoção `:164`.
- Endpoints: PATCH, POST e PUT em `/recipes/<ref>/…` (`useRecipeEntry.ts:80-122`).

**`recipes/[ref]/edit.vue`:**

- Salvar: `:290`.
- Salvar e publicar: `:300`.
- Começar rascunho: `:360`.
- Âncora: `:391`, `:399`.
- Itens:
  - adicionar: `:419`;
  - nome: `:441`;
  - insumo: `IngredientPicker` `:445`;
  - quantidade: `:459`;
  - unidade: `:464`;
  - papel: `:470`;
  - subir, descer, remover: `<button size-9>` `:479-487`;
  - g/un: `:496`.
- Partes:
  - adicionar: `:508`;
  - campos: `:523-553`;
  - remover: `<button size-9>` `:562`.
- Padronizar: `:588`, POST `/recipes/standardize/`.
- Desfazer: `:608`.
- Origem: disclosure à mão `:615-619`.
- Lente: GET `/recipes/lens/` com debounce (`useFormulaLens.ts:27`).

**`recipes/new.vue`:**

- Porta: `UiTabs` `:205`.
- Ir para manual: `:228`, `:319`.
- Ler nota: `:258`, que faz POST `/recipes/capture/`.
- Foto: `<input type=file capture=environment>` `:274-280`.
- Ler foto: `:301`.
- Refazer: `:333`.
- Candidato: `UiNativeSelect` `:401-411`.
- Papel: `UiNativeSelect` `:418-426`.
- Continuar: `:445`.
- Manual:
  - Enter: `:470`;
  - começar: `:496`, que faz POST `/recipes/`.

**`recipes/compare.vue`:**

- Escolher a receita: `UiNativeSelect` `:76`.
- Número: `UiInput` `:89`.
- Tentar de novo: `:121`.

**`IngredientPicker.vue`:** combobox à mão.

- Campo: `UiInput` `:82-93`, com Esc em `:92`.
- Lista: `<ul role=listbox>` `:94`.
- Opção: `<button @mousedown.prevent>` `:103-112`.
- Limpar: `<button size-6>` `:70-78`.
- Busca: GET `/recipes/ingredients/` com debounce.

### 2.14 Leitor de etiqueta (`LotLabelScanner.vue` + `useCodeScanner.ts`)

- **Câmera:** `UiSheet` `:36` com `<video>` `:43-49` (zxing).
- **Lanterna:** `<button>` `:54-62`.
- **Código digitado:** `<form>` `:68`, `UiInput` `:69`, Abrir `:76`.

### 2.15 Navegação e avisos (`ProductionNav.vue`)

- **Rail:** `OperatorSuiteRail` `:43-51`. Leva o ciclo (Alt+1..5 impressos), Timers com selo e ponto de "tocando", e Ajustes.
- **Pé do rail (kit):** Avisos, Atalhos, Bloquear, operador.
- **Barra do polegar:** `OperatorSectionBar` `:52-59`.
- **Avisos:** `provideOperatorInboxAlerts` `:28-38` com `useAlerts`. GET `/api/v1/backstage/alerts/`; "Visto" faz POST `/alerts/<id>/ack/` (`useAlerts.ts:37-68`).
- **Selo da Qualidade:** `useProductionRail` (`useProductionSections.ts:5`, escrito em `quality.vue:116-126`).

## 3. Atalhos de teclado, SSE e poll

### 3.1 Atalhos

| Tecla | Onde | Arquivo |
|---|---|---|
| Alt+1 a Alt+5 (etapas) | toda tela com `ProductionHeader` | `presentation/keyboard.ts:64-85`, `ProductionHeader.vue:115-137` |
| `/` foca a busca; R atualiza; ? ajuda | idem | idem |
| 0-9, Backspace, C/Delete, Enter, NumpadEnter | `QcCloseScreen`, diálogo do timer do forno, `FloorTimerCreateDialog` | `keyboard.ts:87-100`; `QcCloseScreen.vue:523`; `close.vue:370`; `FloorTimerCreateDialog.vue:79` |
| Esc | volta/fecha no QC (`QcCloseScreen.vue:526`); fecha o picker (`IngredientPicker.vue:92`) | |
| Enter nos campos de quantidade | `ProductionStageGrid.vue:1344, 1972, 2115, 2228`; `recipes/new.vue:470`; `FloorTimerCreateDialog.vue:209` | |

**Bloqueios que a migração precisa preservar:**

- `productionGlobalKeysBlocked` (`keyboard.ts:118-125`) procura `[data-operator-lock]`, `[data-production-shortcut-scope='exclusive']`, `[role='dialog'][data-state='open']` e `[role='alertdialog'][data-state='open']`.
- `hasOpenDialogOutside("[data-production-timer-dialog]")` (`keyboard.ts:134-142`) exige que o MESMO elemento `role=dialog` aberto carregue `data-production-timer-dialog`. Isso vale para `close.vue:714` e `FloorTimerCreateDialog.vue:116`.

A ajuda lista os grupos `PRODUCTION_SHORTCUT_GROUPS` (`keyboard.ts:11-38`).

### 3.2 SSE

Nenhum. Não há `EventSource`, `useBackstageEvents` nem `/events/` no app. A decisão está escrita em `useAdaptivePoll.ts:6-8` (WP-PE4). Isso contraria a regra site-wide do ADR-016, mas é decisão registrada, não esquecimento.

### 3.3 Poll

`useAdaptivePoll` pula aba oculta, refaz ao voltar e tem backoff até 8× com jitter.

| Projeção | Cadência | Arquivo |
|---|---|---|
| `/production/` (grade) | 60 s | `useProductionBoard.ts:64` |
| `/production/kds/` | 30 s; 10 s com atraso | `useProductionKds.ts:39` |
| `/production/qc/` | 30 s | `useQcKiosk.ts:54` |
| `/production/mise-en-place/` | 60 s | `useMiseEnPlace.ts:85` |
| `/production/weighing/` | 60 s | `useWeighing.ts:30` |
| `/production/forecast/` (Letreiro) | 30 s | `useProductionForecast.ts:21` |
| `/production/timer-tags/` | 5 min | `useTimerTags.ts:48` |
| `/backstage/alerts/` | 60 s | `useAlerts.ts:35` |
| print-jobs | adaptativo (`poll_after_ms`) | `useProductionLabelPrinting.ts:96,192` |

Há ainda a renovação de frescor da projeção, que é timer próprio: `useProductionMutationGuard.ts:358-394`.

## 4. Peças do operator-kit usadas

| Peça | Usos | Onde |
|---|---|---|
| `OperatorPageHeader` | 2 | `ProductionHeader.vue:291`, `RecipeHeader.vue:30` |
| Slots do `OperatorPageHeader` | `#lead` (`ProductionHeader.vue:292`, `RecipeHeader.vue:31`), `#subtitle` (`:293`), `#status` (`:308`), `#search` (`:318`, `RecipeHeader.vue:41`), `#phone-actions` (`:340`), `#actions` (`:343`, `RecipeHeader.vue:50`), `#filters` (`:374`), `#below` (`:375`) | o kit declara todos hoje (`operator-kit/app/components/OperatorPageHeader.vue:111-197`; `#below` em `:188`, restaurado pelo #1521). Ninguém passa `#below` à Produção: o slot é repasse sem consumidor. |
| `OperatorLiveStatus` | 1 | `ProductionHeader.vue:310`, com `tone="late"` quando `stale` (`:102`). O kit hoje pinta todo tom não `off` de verde "On" (`OperatorLiveStatus.vue:24-26,37`). Leitura vencida sai verde, e o ponto do `#subtitle` na mesma tela sai âmbar (`ProductionHeader.vue:302`): duas leituras opostas no mesmo cabeçalho. |
| `OperatorSuiteSearch` | 2 | `ProductionHeader.vue:329`, `RecipeHeader.vue:42`. Agora é `NuxtDashboardSearchButton` + `NuxtModal` (`OperatorSuiteSearch.vue:280,292`); `focus()` = abrir o modal (`:265`). |
| `OperatorPeriodPicker` | 6 | `ProductionStageGrid.vue:1001` (atende `/` e `/plan`), `board.vue:127`, `close.vue:423`, `mise-en-place.vue:178`, `reports.vue:160`, `reports.vue:355` (o único com `custom`). O kit usa `NuxtInput type="date"` em `OperatorPeriodPicker.vue:248,259,294`. |
| `OperatorNumpad` | 2 | `ProductionStageGrid.vue:1986`, `QcCloseScreen.vue:636` |
| `OperatorKbd` | 1 | `PlanReasonCard.vue:71` |
| `OperatorSuiteRail` / `OperatorSectionBar` | 1 / 1 | `ProductionNav.vue:43`, `:52` |
| `OperatorSessionUnavailable`, `OperatorLogin`, `OperatorLock`, `OperatorStationSetup`, `OperatorSonner`, `OperatorPwaRuntime`, `OfflineBanner` | 1 cada | `app.vue:52,53,54,55,61,62,30` |
| `UiFilterChip` | 2 | `ProductionStageGrid.vue:1012,1038`. Hoje é `NuxtButton` + `NuxtBadge`; perdeu o alvo de 44 px (laudo, anexo D). |
| `UiNativeSelect` | 18 | `reports.vue` 3, `recipes/[ref]/edit.vue` 7, `recipes/new.vue` 6, `recipes/[ref]/index.vue` 1, `recipes/compare.vue` 1 |
| `UiButton` | 96 | por arquivo: `recipes/[ref]/index` 18, `ProductionStageGrid` 11, `ProductionLabelPrintDialog` 9, `recipes/[ref]/edit` 8, `reports` 7, `recipes/new` 7, `QualityGatePanel` 6, `RecipeExternalReferences` 6, `QcCloseScreen` 5, `mise-en-place` 5, `RecipeVersionRating` 4, `PlanReasonCard` 3, `ShortageDialog` 3, `recipes/index` 2, `LotLabelScanner` 1, `recipes/compare` 1. Já embrulha `NuxtButton` (`operator-kit/app/components/UiButton.vue:106`). 74 instâncias passam `class`, a maioria `min-h-11`/`h-auto min-h-14` para alvo de toque. |
| `UiDialog*` | 14 diálogos | `ShortageDialog:50`, `RecipeExternalReferences:106,154`, `ProductionStageGrid:2026,2160,2267,2378`, `ProductionLabelPrintDialog:390`, `RecipeVersionRating:94`, `FloorTimerCreateDialog:115`, `recipes/[ref]/index:479,545,584`, `close:704`. É reka cru do ui-thing (`operator-kit/app/components/Ui/Dialog/Content.vue:42`), com `data-slot="dialog-content"`, `hide-close` e slot `#close`. |
| `UiPopover*` | 5 | `ProductionHeader:194`, `ProductionStageGrid:1212,1512,1602,1745` |
| `UiSheet*` | 3 | `QcCloseScreen:797`, `LotLabelScanner:36`, `close:670` |
| `UiTabs*` | 3 | `quality:283`, `QualityGatePanel:119`, `recipes/new:205` |
| `UiBadge` | 19 | `FormulaLens:67,70,162`, `IngredientPicker:109`, `ProductionStageGrid:2410`, `ProductionLabelPrintDialog:425`, `reports:745`, `mise-en-place:392`, `recipes/index:199,229,232,233`, `recipes/[ref]/index:242,243,351,352,443,444`, `recipes/new:330` |
| `UiCheckbox` | 7 | `FloorTimerCreateDialog:215`, `mise-en-place:242,369`, `recipes/index:127-130` |
| `UiInput` / `UiTextarea` | 23 / 9 | ver 2.13 e 6 |
| `UiIconButton` / `UiAlert` | 1 / 1 | `RecipeHeader:52` / `ProductionLabelPrintDialog:404` |
| `UiDate*` / `UiTime*` | 0 direto | o único caminho de data é o `OperatorPeriodPicker` (6 usos) |
| `FilterBar`, `RailSection`, `ColumnPicker`, `MoreBelow`, `OperatorSplitter`, `OperatorPage*Shell` | 0 | |

**Composables e utilitários do kit:**

- `useOperatorLock`: `app.vue:12`, `mise-en-place.vue:35`.
- `useStationSetupOffer`: `app.vue:17`.
- `useOperatorWindowTitle`: `app.vue:21`.
- `useOperatorShortcuts` + `provideOperatorShortcuts`: `ProductionHeader.vue:71-72`.
- `provideOperatorInboxAlerts`: `ProductionNav.vue:28`.
- `useConfirm`: `QcCloseScreen.vue:496`.
- `useKioskMode`: `board.vue:89`.
- `useConnectivity`: `useProductionMutationGuard.ts:167`, `useProductionLabelPrinting.ts:117`.
- `retryWithBackoff`: `useAlerts.ts:49`, `useOvenFacts.ts:64`.
- `httpError`, `httpErrorMessage`, `httpErrorCode`: 12 composables.
- `reportClientError`: `useOvenFacts.ts`.
- Presentation importada por caminho relativo:
  - `dates` (`periodAnchor`, `periodOfDay`): grade, board, close, mise, reports;
  - `appBar.activeSectionKey`: `ProductionNav.vue:12`;
  - `suiteChrome.operatorAlertToInbox`: `ProductionNav.vue:13`.

**Toast:**

- `useSonner` (vue-sonner, `nuxt.config.ts:56,86-89`) tem 36 chamadas em 18 arquivos.
- Uma delas tem ação "Atualizar": `useProductionMutationGuard.ts:214-226`.
- O Gestor usa `useToast`. Para a Produção, migrar o toaster exige `useToast` com `actions`.

## 5. Componentes locais

| Componente | Linhas | Papel | Destino sugerido |
|---|---|---|---|
| `ProductionStageGrid.vue` | 2.442 | motor das lentes Plan/Open: linhas, popovers, painel encaixado, 4 diálogos | fica local, mas **fatiar** antes de migrar: `PlanTable`, `OpenTable`, `PlanDialog`, `StartPanel` (diálogo e encaixado compartilham stepper e numpad), `StartedDialog`, `CommitmentsDialog`. Hoje são 34 `<button>`, 4 `<input>` e 30 arbitrários num arquivo só. |
| `QcCloseScreen.vue` | 920 | fechamento por grau, numpad, sheet de perguntas | local (domínio) |
| `ProductionLabelPrintDialog.vue` | 748 | fluxo de impressão (relay, agente, navegador), confirmação física | local; o padrão PrintJob poderia ir ao kit se o PDV convergir (não verificado) |
| `QualityGatePanel.vue` | 464 | portão da Qualidade | local |
| `ProductionHeader.vue` | 378 | wrapper do `OperatorPageHeader` com ⋯, progresso, ao vivo, atalhos | candidato a **morrer** no kit: ⋯ = `NuxtDropdownMenu`, progresso = `NuxtProgress`, os atalhos sobem para uma capability do cabeçalho do kit |
| `PlanReasonCard.vue` | 243 | o "Por quê" da sugestão | local |
| `FloorTimerCreateDialog.vue` | 241 | novo timer com numpad próprio | local; o numpad deveria ser o `OperatorNumpad` (é o terceiro numpad: `close.vue:789-849`, este e o do kit) |
| `FormulaLens.vue` | 210 | lente da fórmula (3 tabelas) | local; tabelas → `NuxtTable` |
| `SplitFlap.vue` | 188 | palheta Solari | local (Letreiro), não migrar |
| `WeighingLabels.vue` | 182 | papel da etiquetadora (mm fixos, isento da trava tipográfica) | local, não migrar (impressão) |
| `RecipeExternalReferences.vue` | 171 | referências + 2 diálogos | local |
| `ShortageDialog.vue` | 159 | recusa por falta, com override | local |
| `FloorTimerCard.vue` | 151 | cartão de timer com anti-quique | local |
| `RecipeVersionRating.vue` | 139 | avaliação da versão | local |
| `IngredientPicker.vue` | 116 | combobox à mão | **morre** → `NuxtInputMenu` |
| `LotLabelScanner.vue` | 84 | câmera zxing + digitado | candidato a **subir** com `useCodeScanner.ts`, que está duplicado em `purchase-nuxt/app/composables/useCodeScanner.ts` |
| `RecipeHeader.vue` | 61 | segundo wrapper do mesmo cabeçalho | **morre**, unido ao cabeçalho único |
| `ProductionNav.vue` | 60 | rail + barra do polegar + avisos | local fino |
| `useAdaptivePoll.ts` | 67 | poll com visibilidade e backoff | candidato a subir (é o fallback que o ADR-016 pede em todo app) |

**Mortos ou suspeitos:**

- `ui-thing.config.ts` aponta para `app/components/Ui`, que não existe no app.
- Os stubs `UiStubs` em `tests/support/nativeUiStubs.ts` duplicam os do Gestor.

## 6. Escapes do cânon

### 6.1 Contagens por categoria

| Categoria | Contagem | Componente oficial |
|---|---|---|
| (a) `:ui=` por instância | 0 | não se aplica |
| (b) HTML cru que imita componente | `<button>` 90 + 2 dinâmicos; `<input>` 4 (exceto o `type=file`); `<select>` 1; `<table>` 14; `role="menu"` à mão 2; `role="progressbar"` à mão 1; `role="listbox"` à mão 1; `<kbd>` 2; `<form>` 4 (legítimos); Teleport/`<dialog>`/overlay `fixed inset-0`: 0 | `NuxtButton`, `NuxtInputNumber`, `NuxtSelect`/`NuxtSelectMenu`, `NuxtTable`, `NuxtDropdownMenu`, `NuxtProgress`, `NuxtInputMenu`, `NuxtKbd` |
| (c) data/hora nativa | 0 no app; 6 herdados do `OperatorPeriodPicker` (P1-1 do laudo) | `UiDateField`/`UiDateRangeField` (que já compõem `NuxtInputDate` + `NuxtCalendar`) dentro do picker |
| (d) Tailwind que imita componente | alerta/aviso à mão ~17; vazio tracejado 46 (`border-dashed`); "Carregando…" em texto 10; segmentos à mão 4; chips de status/sinal 3; link vestido de botão 1; stepper à mão 4 | `NuxtAlert`, `NuxtEmpty`, `NuxtSkeleton`, `NuxtTabs`, `NuxtBadge`, `NuxtButton :to`, `NuxtInputNumber` |
| (e) arbitrários `[...]` | 74 em 17 arquivos. Com motivo escrito: os mm do papel (`WeighingLabels`, 9), a grade de colunas fixas do quadro (comentários em `ProductionStageGrid.vue:680-695`). Sem motivo: sombras e alturas da grade, `w-[33rem]`, `w-[392px]`, `h-[42px]`, `px-[9px]`, `gap-[5px]` | tokens do tema (`app.config.ts`) ou classes padrão |
| (f) primitivas paralelas | toda a família ui-thing do kit em uso (14 diálogos reka crus, 5 popovers, 3 sheets, 3 tabs, 19 badges, 23 inputs, 9 textareas, 7 checkboxes, 18 selects nativos); 3 numpads; spinners à mão 4; toaster vue-sonner (36 chamadas + `OperatorSonner`) no lugar de `useToast` | `NuxtModal`, `NuxtPopover`, `NuxtSlideover`/`NuxtDrawer`, `NuxtTabs`, `NuxtBadge`, `NuxtInput`, `NuxtTextarea`, `NuxtCheckbox`, `NuxtSelect`; `loading` do `NuxtButton`; `useToast` |
| (g) travessão em copy | 26 visíveis, todos como marcador de valor vazio (`FormulaLens.vue:120,140,185`; `ProductionStageGrid.vue:746,1727`; `reports.vue:181,198,277,549,554,565,571,573,575,625,628,660,699`; `mise-en-place.vue:435`; `recipes/compare.vue:160-163,175-177`). A trava `guardrails.noEmDash.test.ts` deixa passar "célula vazia", mas o caractere aparece na tela. Em frase: 0. | `NuxtTable` com `empty` ou o texto "sem dado" |

### 6.2 Os 40 mais relevantes

1. `ProductionHeader.vue:194-289`: ⋯ com `UiPopover` + `<div role="menu">` + `<button role="menuitem">` à mão. Vira `NuxtDropdownMenu`, o mesmo do P1 do laudo ("um ⋯ só").
2. `ProductionStageGrid.vue:1745-1865`: ⋯ da linha aberta, também `role="menu"` à mão. Vira `NuxtDropdownMenu`, mantendo o pressionar-e-segurar.
3. `ProductionStageGrid.vue:1512-1586`: menu do planejado em `UiPopover`. Vira `NuxtDropdownMenu`.
4. `ProductionStageGrid.vue:1602-1637`: ⋮ dos planejados, com o ícone `ellipsis-vertical`, o mesmo desvio do Catálogo do Gestor. Vira `NuxtDropdownMenu` com ⋯.
5. `ProductionStageGrid.vue:1065-1086`: `<select>` invisível sobre um `<label>` pílula. Vira `NuxtSelect` (ou `UiNativeSelect`, se o Pablo mantiver a decisão de 10/09).
6. `ProductionStageGrid.vue:1319-1355`: stepper da linha com `h-[42px] w-[150px]` e input cru. Vira `NuxtInputNumber`.
7. `ProductionStageGrid.vue:2098-2125`: stepper do diálogo Planejar. Vira `NuxtInputNumber`.
8. `ProductionStageGrid.vue:2213-2237`: stepper do diálogo Confirmar. Vira `NuxtInputNumber`.
9. `ProductionStageGrid.vue:1957-1981`: stepper de 56 px do painel encaixado, com `inputmode="none"`. Vira `NuxtInputNumber` + `OperatorNumpad`, mantendo o `inputmode`.
10. `ProductionStageGrid.vue:1366-1385`: "Planejar N" em `<button>` com classes de botão primário. Vira `NuxtButton`.
11. `ProductionStageGrid.vue:1414-1439`, `:1468-1476`: "Ver um a um" e "Planejar os N". Viram `NuxtButton`.
12. `ProductionStageGrid.vue:1770-1798`: Confirmar e Ver lançamento em `<button>` com variação `docked`. Viram `NuxtButton` com `size`.
13. `ProductionStageGrid.vue:1893-2022`: `<aside>` encaixado (painel lateral). Decidir entre o `NuxtCard`/painel do kit e o `NuxtSlideover` sem overlay. Não pode cobrir a lista: hoje não cobre.
14. `ProductionStageGrid.vue:2026-2429`: 4 `UiDialog`. Viram `NuxtModal`.
15. `ProductionStageGrid.vue:1129-1137`: chip "Sem atualizar" à mão. Vira `NuxtAlert` ou `NuxtBadge`; o mesmo padrão está em `close.vue:470-478`, `quality.vue:322-330` e `mise-en-place.vue:321,560`.
16. `ProductionStageGrid.vue:1107-1125`, `:1139-1152`: erro e vazio à mão. Viram `NuxtEmpty`.
17. `ProductionStageGrid.vue:1246-1259`, `:1712-1722`, `:1495-1502`: chips de sinal e de situação, com `h-[26px] px-[9px] gap-[5px]`. Viram `NuxtBadge`.
18. `ProductionStageGrid.vue:1173,1176,1267,1285,1677`: sombras arbitrárias (`shadow-[inset_0_0_0_2px_var(--primary)]`, `shadow-[0_18px_48px…]`). Viram token do tema.
19. `ProductionStageGrid.vue:1012-1061`: `UiFilterChip` com `aria-pressed`. Vira `NuxtTabs` (como o Gestor) ou `UiFilterChip` corrigido para 44 px.
20. `ProductionHeader.vue:319-338`: lupa à mão para tablet de toque antes do `OperatorSuiteSearch`. Com a busca do kit agora em modal, viram dois toques para abrir; a lupa morre.
21. `ProductionHeader.vue:347-370`: barra de progresso à mão. Vira `NuxtProgress`.
22. `ProductionHeader.vue:237,280`: `<kbd>` cru. Vira `NuxtKbd`/`OperatorKbd`.
23. `ProductionHeader.vue:300-305`: ponto âmbar/verde ao lado do `OperatorLiveStatus`. Fica uma leitura só, depois da frente F3.
24. `close.vue:539-613`: `component :is="button"` como cartão tocável + `p` com a pílula do timer. Vira `NuxtCard` com `NuxtButton` de corpo inteiro (decisão de anatomia).
25. `close.vue:618-646`: tile "Finalizar" de 80 px. Vira `NuxtButton` com bloco de conteúdo, e o tamanho fica como exceção registrada.
26. `close.vue:789-849`: numpad do forno, 4×4 à mão. Vira `OperatorNumpad` com a coluna +N, se o kit aceitar slot.
27. `close.vue:704-879`: `UiDialog` do timer com `UiDialogClose` grande. Vira `NuxtModal` com `close` de 44 px; preservar `data-production-timer-dialog` no elemento `role=dialog`.
28. `close.vue:670-691`, `QcCloseScreen.vue:797`, `LotLabelScanner.vue:36`: `UiSheet side=bottom`. Viram `NuxtDrawer`/`NuxtSlideover side=bottom`.
29. `QcCloseScreen.vue:654-770`: cartões de grau com dois botões sobrepostos (`absolute inset-0` + `mt-14 w-[calc(100%-1.25rem)]`). Teste trava as classes (ver 7). Exige redesenho com `NuxtButton`/`NuxtCard`.
30. `QcCloseScreen.vue:860-872`: presets de motivo em `<button aria-pressed>`. Vira `NuxtRadioGroup variant="card"`/`NuxtTabs`.
31. `FloorTimerCreateDialog.vue:137-197`: o segundo numpad à mão. Vira `OperatorNumpad`.
32. `FloorTimerCard.vue:68-123`: cartão `component :is` + 2 botões. Viram `NuxtCard` + `NuxtButton`.
33. `timers.vue:81-106`: tiles de etiqueta em `<button>`. Viram `NuxtButton` em bloco ou `NuxtCard` clicável.
34. `mise-en-place.vue:192-224`, `reports.vue:286-306`, `recipes/index.vue:94-120`: segmentos `<button aria-pressed>`. Viram `NuxtTabs :content="false"`.
35. `mise-en-place.vue:337`, `reports.vue:246,520,595,640,672,761`, `FormulaLens.vue:88,180,196`, `recipes/compare.vue:139,171`, `recipes/new.vue:377`, `recipes/[ref]/index.vue:510`: 14 `<table>` crus. Viram `NuxtTable`.
36. `IngredientPicker.vue:60-116`: combobox com `<ul role=listbox>` e `@mousedown.prevent`. Vira `NuxtInputMenu`.
37. `recipes/[ref]/edit.vue:479-487,562`: botões de 36 px (`size-9`). Viram `NuxtButton square` com alvo de 44 px.
38. `recipes/[ref]/edit.vue:615-619`: disclosure à mão. Vira `NuxtCollapsible`.
39. `recipes/index.vue:63-70`: NuxtLink vestido de botão primário. Vira `NuxtButton :to`.
40. Spinners à mão:
    - `ProductionHeader.vue:234` (`animate-spin`);
    - `ProductionLabelPrintDialog.vue:535` (`line-md:loading-loop`);
    - `recipes/[ref]/edit.vue:587`;
    - `recipes/new.vue:264,307`.

    Viram o prop `loading`.

## 7. Testes e travas que vão quebrar ou mudar

### 7.1 No app

- **`tests/presentation/v6Conformity.test.ts`:** lê o fonte e trava strings literais.
  - `:100` exige `class="pl-0.5 text-muted-foreground max-sm:hidden" aria-hidden="true" data-planned-separator`;
  - `:198` exige `class="[&_[data-period-today]]:hidden"` na grade e no Fechamento;
  - `:206` proíbe `<OperatorPeriodPicker` na Qualidade;
  - `:211-212` exige `data-header-subtitle` e `menuInPhoneBar` no `ProductionHeader`.

  Qualquer reescrita do cabeçalho ou da linha de planejados reprova aqui.
- **`tests/components/QcCloseScreen.test.ts:480-505`:** trava classes Tailwind (`h-11`, `rounded-md`, `ml-3`, `mr-2`, `w-[calc(100%-1.25rem)]`, `mt-14`, `z-20`, `absolute`, `inset-0`, `items-start` em `[data-qc-layout]`). A troca por `NuxtButton` quebra os 13 asserts de classe.
- **`tests/components/ProductionHeader.test.ts`:**
  - dublê próprio de `OperatorPageHeader` com `data-phone`/`data-actions` (`:35-36`);
  - de `OperatorLiveStatus` com `data-tone` (`:68`), que assere `late` em `:249`;
  - de `UiPopoverContent` como `data-menu` (`:83`);
  - assere `input[type="search"]` com `aria-keyshortcuts` (`:193`), que não existe mais no `OperatorSuiteSearch` em modal; `[data-header-refresh]` (`:196,213`); `[data-menu] a` (`:226`); `[role="progressbar"]` (`:242`).
- **`tests/support/nativeUiStubs.ts`:** dublês à mão de `UiButton`, `UiInput`, `UiTextarea` e `UiNativeSelect`. São usados por `ProductionStageGrid.test.ts:13-17`, `QcCloseScreen.test.ts`, `MiseEnPlacePage.test.ts`, `PlanReasonCard.test.ts`, `QualityGatePanel.test.ts`. É a mesma classe de risco do P0-1 do laudo (dublê mais permissivo que o real). Com `Nuxt*`, todos os stubs mudam de nome e de contrato.
- **`tests/support/uiPrimitives.ts:6-15`:** registra os `UiTabs` reais do kit como globais. Quebra se `UiTabs` morrer.
- **`tests/components/ProductionLabelPrintDialog.test.ts`:** monta a família `UiDialog*`, `UiAlert`, `UiBadge`.
- **`tests/components/ProductionStageGrid.test.ts`:** 1.059 linhas. Usa 52 seletores `[data-*]` de contrato (`data-plan-row`, `data-plan-inline`, `data-plan-reason-trigger`, `data-planned-row`, `data-open-row-menu`…). Preservar os `data-*` é o caminho barato.

### 7.2 Playwright (`tests/e2e`)

- **`accessibility.spec.ts:45-97`:** exige alvo ≥ 44 px em `button`, `a[href]`, `input`, `select`, `textarea`, `[role=button]` e `[role=switch]`, nas 5 viewports de toque. O kit perdeu os 48 px de `pointer: coarse` e o `UiFilterChip` perdeu os 44 px (laudo P1-9). É provável que esta seja a causa do vermelho "Produção · matriz Playwright AA", mas não foi verificado.
- **`accessibility.spec.ts:270-315`:** espera `[data-period-next]`/`[data-period-prev]` (o kit mantém) e `showPicker` nunca chamado.
- **`accessibility.spec.ts:219-268`:** depende de `.flap-word`, `.flap-cell` e `data-pulse` (`SplitFlap`).
- **`guards.spec.ts:61-99,116-135`:** depende de `[data-operator-lock]` e dos atalhos Alt+1..5.

### 7.3 Travas do kit e do repositório que leem a Produção

- **`scripts/check_operator_component_ledger.py:32-39,276-306`:**
  - teto `native_control_occurrences` 96 (hoje 91; só pode descer);
  - proíbe `<NuxtPageHeader>`, `<NuxtDashboard*>`, `<NuxtMain>`, `<NuxtContainer>`, `<NuxtSplitter>`, `<NuxtNavigationMenu>` no app ("layout Nuxt UI canônico usado fora do operator-kit");
  - proíbe import direto de `reka-ui` e `@nuxt/ui`.

  As 14 telas estão `pending` em `docs/reference/operator-component-ledger.json`.
- **`operator-kit/tests/guardrails.pendingAction.test.ts:181-182`:** `KNOWN_INERT` exato (`toEqual`) com `ProductionStageGrid.vue: confirmVoid` e `board.vue: toggleFullscreen`. Corrigir o clique inerte obriga a encolher a lista no mesmo PR.
- **`operator-kit/tests/guardrails.test.ts:163-200`:** trava tipográfica (`text-2xl`, `text-[..]`) na Produção. `WeighingLabels.vue` é isento. O walker pula diretórios `Ui`.
- **`operator-kit/tests/guardrails.suiteSearch.test.ts:74-101`:** o `#search` do cabeçalho tem de ter exatamente uma busca da suíte. A lupa à mão do `ProductionHeader.vue:319` mora no mesmo slot; conferir.
- **Outras travas que varrem a Produção:**
  - `guardrails.phoneBar.test.ts` (sem Atualizar solto na barra de 56 px);
  - `guardrails.a11y.test.ts` (botão de ícone tem nome);
  - `guardrails.copyNeverTruncates.test.ts`;
  - `guardrails.noEmDash.test.ts`;
  - `guardrails.vocabulary.test.ts:283-315`;
  - `guardrails.appBar.test.ts:92,125` (`ProductionNav.vue`);
  - `kitOwnership.guardrails.test.ts` (não redeclarar primitivas do kit).
- **`operator-kit/tests/kitOwnership.guardrails.test.ts:254`:** pela leitura do laudo, só procura `<input` cru e não pega `NuxtInput type=date`.

## 8. Mock visual e build local

### 8.1 O que existe

- **Mock:** `tests/e2e/mockBackend.mjs` (291 linhas), na porta 8797. Ramifica pelo cookie:
  - `e2e_session=authed`: sessão autenticada;
  - `e2e_session=locked`: lock;
  - `e2e_scenario=long-copy`: uma linha longa na grade;
  - `e2e_scenario=reports-populated`: relatórios com cursor e CSV lento de 1 s.
- **`playwright.config.ts:89-111`:** sobe o mock e faz `nuxt build && node .output/server/index.mjs` na porta 3105, com `NUXT_DJANGO_BASE_URL=http://127.0.0.1:8797`, `SHOPMAN_ENVIRONMENT=test` e `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1`.
- **README do e2e:** `tests/e2e/README.md`.
- **CI (`.github/workflows/surfaces-gate.yml`):**
  - build hermético em `:283-290`, com `NUXT_SHOPMAN_ENVIRONMENT=test`, `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1` e `NUXT_DJANGO_BASE_URL=http://127.0.0.1:1`;
  - job "Produção · matriz Playwright AA" em `:389-435`.

### 8.2 Por que o build falhou no laudo, e o contorno

`operator-kit/server/utils/djangoBaseUrl.ts:81-89` lança "Shopman environment is not configured" quando:

- `NODE_ENV=production`, que o `nuxt build` define; e
- não há `NUXT_SHOPMAN_ENVIRONMENT`/`SHOPMAN_ENVIRONMENT`; e
- falta a exceção explícita de teste (`isExplicitTestRuntime`, `:35-38`: ambiente `test|testing|e2e` **e** `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1`).

O `nuxt.config.ts:6` chama `configuredDjangoBaseUrl()` já no build. O boot do Nitro repete a checagem (`operator-kit/server/plugins/upstream-guard.ts:12-13`), com a mesma exceção.

Receita local, a mesma do Playwright:

```bash
cd surfaces/production-nuxt
node tests/e2e/mockBackend.mjs &                      # :8797
SHOPMAN_ENVIRONMENT=test SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 \
NUXT_DJANGO_BASE_URL=http://127.0.0.1:8797 NUXT_APP_BASE_URL=/ npx nuxt build
SHOPMAN_ENVIRONMENT=test SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 \
NUXT_DJANGO_BASE_URL=http://127.0.0.1:8797 HOST=127.0.0.1 PORT=3105 node .output/server/index.mjs
# no browser: cookie e2e_session=authed em 127.0.0.1 (e e2e_scenario=… se quiser)
```

Ou simplesmente `npm run test:e2e`, que faz tudo. `production-nuxt/node_modules` existe nesta worktree; o `operator-kit` também precisa de `npm ci`.

### 8.3 Cobertura de telas e completude das projections

O mock responde `{}` para todo endpoint que não conhece (`mockBackend.mjs:285`).

| Rota | Fixture | Estado que renderiza |
|---|---|---|
| `/` e `/plan` | `BOARD` vazio (`:41-51`); `LONG_COPY_BOARD` com 1 linha sem `planned_orders`, `started_orders` nem `positions` | só vazio, ou 1 linha de plano. **Sem:** grupos focus/clean/manual/planned, linha aberta, painel encaixado, diálogos Planejar/Confirmar/Lote aberto/Encomendas, falta, "Por quê" completo |
| `/mise-en-place` | `MISE` vazio; `weighing` → `{}` | vazio; **sem** fichas, tabela, checklist nem diálogo de impressão |
| `/close` | `QC` com 1 lote aberto e ação `finish:42` | painel + `QcCloseScreen`; **sem** `oven_arm`/`oven_conclude` (timer do forno inacessível), `recipes: []` (lote avulso vazio), sem lote de dia anterior |
| `/quality` | mesmo `QC` (lote não fechado) | "Para confirmar" vazio; **sem** limpos, exceções, confirmados nem correção |
| `/reports` | vazio, ou `REPORTS` populado só com histórico; `management` → `{}` | histórico + paginação + CSV; **sem** operador, qualidade, desperdício, gestão do dia, atrasos, mapa cego |
| `/board` | `FORECAST` com 1 linha atrasada | Letreiro com 1 palheta; **sem** paginação (precisa de mais linhas) |
| `/timers` | `timer-tags` → `{}` | só "Nenhuma etiqueta"; **sem** fileira nem timers |
| `/settings` | sondas de acesso → `{}` | só "Letreiro" (Receitas e Relatórios dependem das sondas) |
| `/recipes`, `/recipes/new`, `/recipes/:ref`, `/recipes/:ref/edit`, `/recipes/compare` | **nenhuma** | não há fixture do livro de receitas |
| Alertas | `ALERTS` vazio | caixa vazia |

**Telas e estados sem fixture, que viram retrato cego na migração:**

- os 5 de receitas;
- timers com estado;
- impressão de etiquetas;
- timer do forno;
- leitor de etiqueta (câmera);
- toda a gama de diálogos da grade;
- Qualidade com lotes fechados.

## 9. Riscos específicos que a migração não pode quebrar

1. **Bloqueio de teclado por atributo.** `keyboard.ts:118-142` depende de três coisas: `[role=dialog][data-state=open]`; `data-production-timer-dialog` no mesmo elemento do diálogo (`close.vue:714`, `FloorTimerCreateDialog.vue:116`); e `data-production-shortcut-scope="exclusive"` (`QcCloseScreen.vue:574`). Um `NuxtModal` que ponha o atributo no wrapper errado libera Alt+N e os dígitos por baixo do diálogo, ou cala o numpad do timer.
2. **Toque.**
   - Pressionar e segurar por 550 ms só com `pointerType === "touch"`, ignorando `button, a, input` (`ProductionStageGrid.vue:647-659`);
   - clique direito só encaixado (`:660-664`);
   - dois toques em 600 ms no grau (`QcCloseScreen.vue:277-302`, por ativações, não `dblclick`);
   - janela anti-quique do timer (`FloorTimerCard.vue:33-46`).

   Trocar `<button>` por `NuxtButton` não pode mudar a ordem `pointerdown`/`click`.
3. **Painel encaixado x diálogo.** No tablet deitado de toque (`(pointer: coarse) and (min-width: 1024px)`, `ProductionStageGrid.vue:684-689`), o mesmo `startRow` abre o `<aside>` em vez do `UiDialog` (`:2161`, `open = startRow && !docked`). A hidratação é cuidada (`gridMounted`). `inputmode="none"` no encaixado evita o teclado virtual.
4. **Timers.**
   - `useFloorTimers` vive em localStorage (`producao.timers`, chaves legadas em `useFloorTimers.ts:49-52`), com um ticker de 1 s e AudioContext;
   - a contagem só aparece depois de montar, para não haver mismatch (`ProductionHeader.vue:78-82`, `useProductionSections.ts:17-23`, `close.vue:283-297`, `timers.vue:29-32`);
   - o alarme pisca o cartão inteiro via CSS com `var(--card)`/`var(--destructive)` (`close.vue:883-904`, `FloorTimerCard.vue:128-151`). Se o `NuxtCard` desenhar o fundo com `--ui-bg`, a animação some.
5. **Wake lock e kiosk.**
   - `definePwaCapability({ wakeLock: true, kiosk: true, idleReloadPaths: ["/board"] })` (`nuxt.config.ts:38-49`) liga `useWakeLock` no app inteiro e `useKioskMode` com 60 s de ociosidade (`operator-kit/app/components/OperatorPwaRuntime.vue:30,36`);
   - o Letreiro pede tela cheia por gesto (`board.vue:89-95`);
   - virada do dia à meia-noite: `board.vue:44-50,73`;
   - rotação de página: 12 s;
   - re-giro: 25 s.
6. **Pele do Letreiro.** `.board-period` (`board.vue:322-335`) redefine `--background`, `--card` etc. Mas o tema traduz `--ui-bg: var(--background)` em `:root` (`operator-kit/app/assets/css/operator-theme.css:122-130`): a variável já chega resolvida e a troca local não alcança o `NuxtButton`/`NuxtPopover` do `OperatorPeriodPicker`, e o popover ainda é portado para fora do `.board`. É provável que o seletor de data do Letreiro já esteja claro sobre a TV escura. Não verificado em tela.
7. **Posto (estação).**
   - A sessão é perguntada em `/api/v1/backstage/production/session/` (`nuxt.config.ts:33`), uma trava de servidor para o painel autônomo;
   - o checklist da Preparação é escopado por `stationRef` (`mise-en-place.vue:35`, `useMiseEnPlace.ts:33`);
   - a oferta de vincular posto fica fora do kiosk (`app.vue:55-60`).
8. **Frescor das mutações.**
   - `useProductionMutationGuard` recusa projeção vencida e oferece "Atualizar" num toast com ação (`:214-226`). O `useToast` do Nuxt UI precisa entregar a ação;
   - o poll troca a projeção sob o diálogo aberto, e a revisão vista é comparada (`useProductionBoard.ts:127-139`).
9. **Impressão.**
   - `@media print` esconde `[data-slot="dialog-overlay"]` (`ProductionLabelPrintDialog.vue:743-747`), que é o slot do ui-thing; o `NuxtModal` usa outros nomes;
   - o papel congelado fica fora do diálogo (`:716-731`);
   - a Preparação usa `print:hidden` (`mise-en-place.vue:168,190`).
10. **Busca.** O `OperatorSuiteSearch` agora é modal. A lupa de 48 px do tablet (`ProductionHeader.vue:319-328`) passa a exigir dois toques, e `@focusout` (`:337`) perde o sentido. "Filtrar a lista enquanto a vê" virou "filtrar dentro de um modal que cobre a lista" (laudo, anexo D, busca inline que virou modal).
11. **Ao vivo.** O tom `late` sai verde "On" hoje (P0-5). Na Produção isso é dado de forno e de fechamento vencido mostrado como vivo, ao lado do ponto âmbar do subtítulo.
12. **Alvos de 44/48 px.** A matriz Playwright mede 44 px em 5 viewports de toque. As peças do kit encolheram (P1-9). Na Produção, ficam abaixo de 44 px:
    - `UiFilterChip` da grade;
    - o `size-9` do editor de receitas;
    - o `size-6` do `IngredientPicker`;
    - o stepper de 42 px da linha (`ProductionStageGrid.vue:1320-1327`).
13. **"Por quê" ancorado.** O popover alterna pelo próprio gatilho graças a `@interact-outside` com `preventDefault` (`:1287`, `:356-364`) e devolve o foco ao gatilho (`:368-373`). O `NuxtPopover` precisa expor os mesmos eventos via `content`.
14. **Escala tipográfica `op-*`.** São as classes da suíte (`op-title`, `op-label`, `op-figure`…). O `NuxtButton` tem escala própria; o laudo registra a dupla escala (44 x 48) nos 7 apps não migrados.

## Anexo: endpoints que a tela chama (para conferir paridade depois)

**GET:**

- `/api/v1/backstage/production/`;
- `production/kds/`;
- `production/qc/`;
- `production/mise-en-place/`;
- `production/weighing/`;
- `production/weighing/blind-map/`;
- `production/forecast/`;
- `production/management/` (também sonda de acesso);
- `production/reports/` (+ `format=csv`);
- `production/timer-tags/`;
- `production/weighing/print-jobs/…`;
- `backstage/alerts/`;
- `recipes/`, `recipes/access/`, `recipes/<ref>/`, `recipes/compare/`, `recipes/reference/`, `recipes/lens/`, `recipes/ingredients/`.

**POST:**

- `production/plan/`;
- `production/<id>/start/`, `finish/`, `void/`, `quality-review/`, `quality-correction/`, `oven/arm/`, `oven/conclude/`;
- `production/quality-review/batch/`;
- `production/quick-finish/`;
- `alerts/<id>/ack/` (`generated/productionContract.ts:1103-1144`);
- `production/timer-tags/`;
- `production/weighing/print-jobs/`;
- `recipes/`, `recipes/capture/`, `recipes/standardize/`, `recipes/<ref>/versions/`, `…/publish/`.

**Outros métodos:**

- PATCH: `recipes/<ref>/`, `…/versions/<n>/`;
- PUT: `…/versions/<n>/rating/`;
- POST/DELETE: `recipes/<ref>/favorite/`.
