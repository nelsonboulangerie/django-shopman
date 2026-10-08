> Anexo do [WP-OPERADOR-NUXTUI-ONDAS](../WP-OPERADOR-NUXTUI-ONDAS.md). Leitura de código em 08/10/2026 sobre `e79ed522d` (pilha do Gestor #1528 + #1521), sem build nem navegador. Vale como mapa de arquivo:linha; o que foi visto em tela está no corpo do plano e nos PRs.

# ONDA 0: grafo do operator-kit e o que muda por opt-in

- **Data:** 08/10/2026. Auditoria de leitura, nada editado no repositório, nada rodado (sem build, sem teste).
- **Base:** worktree `operador-nuxt-ui-migracao-16676a`, branch `claude/operador-nuxtui-onda0-base`, HEAD `e79ed522d` (pilha #1518 + #1519 + #1521 do Gestor). Comparação: `origin/main`.
- **Fonte do laudo:** `docs/plans/WP-GESTOR-CANON-LAUDO.md` só existe em `origin/main` (o arquivo não está nesta worktree); foi lido por `git show origin/main:docs/plans/WP-GESTOR-CANON-LAUDO.md`.
- **Como as contagens saíram:** `kitgraph.py` (nesta pasta) varre `surfaces/<app>/app/**/*.vue|ts` (sem `node_modules`, `.nuxt`, `.output`), conta tags `<Nome` e `<nome-kebab` seguidas de espaço, `/`, `>` ou fim de linha. Uso dinâmico (`<component :is>`) não entra. Testes não entram. Os slots saíram de `slots.py` (nesta pasta), que lê os `<template #x>` filhos diretos de cada `<OperatorPageHeader>`.
- **Fato que decide tudo:** os 9 apps fazem `extends: ["../operator-kit"]` por caminho relativo. Não há versão: toda mudança do kit chega aos 9 no mesmo merge.
- **O marcador de opt-in já existe:** os 7 apps não migrados vestem `data-suite="v3"` na raiz (`hub-nuxt/app/app.vue`, `pos-nuxt/app/components/PosOperatorShell.vue:91`, `kds-nuxt/app/app.vue:26`, `production-nuxt/app/app.vue`, `marketing-nuxt/app/app.vue:58`, `purchase-nuxt/app/app.vue`, `bi-nuxt/app/app.vue:22`), e o kit já tem a variante `suite:` (`operator-kit/app/assets/css/operator-suite.css:20`). O Gestor e o Kitchen Sink não vestem. Ou seja: "comportamento antigo dentro de `suite:`, cânone fora" é um opt-in que já está no chão. Limite: overlay teletransportado para o `body` (Popover, Modal) sai da subárvore `[data-suite]`; para valer neles, o marcador tem de subir para o `<html>` (ver E, PR 0.2).

## A. Grafo de dependência kit → app

Colunas: hub · pos · kds · ord (Gestor) · prod · mkt · purch · bi · ks (Kitchen Sink) · kit (usos dentro do próprio kit) · apps (quantos dos 9 consomem).

### A.1 Componentes

| peça | hub | pos | kds | ord | prod | mkt | purch | bi | ks | kit | apps |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ColumnPicker` |  |  |  | 1 |  |  |  |  |  |  | 1 |
| `FilterBar` |  | 1 |  | 2 |  |  |  |  |  | 1 | 2 |
| `MoreBelow` | 1 | 1 |  |  |  |  |  | 1 |  |  | 3 |
| `OfflineBanner` | 1 | 3 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 9 |
| `OperatorAppBar` |  |  |  |  |  |  |  |  |  |  | 0 |
| `OperatorAppRoot` |  |  |  | 1 |  |  |  |  | 1 |  | 2 |
| `OperatorAppSeal` | 1 | 1 |  |  |  |  |  |  |  | 2 | 2 |
| `OperatorCapacityStatus` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorConfirmDialog` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorDayPicker` |  | 1 |  |  |  |  | 2 |  |  |  | 2 |
| `OperatorIdentify` |  | 1 |  |  |  |  |  |  |  | 3 | 1 |
| `OperatorInbox` | 1 | 1 |  |  |  |  |  |  |  | 4 | 2 |
| `OperatorInstallSteps` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorKbd` |  | 23 |  |  | 1 |  |  |  |  | 1 | 2 |
| `OperatorKitchenSink` |  |  |  |  |  |  |  |  | 1 |  | 1 |
| `OperatorKitchenSinkChart` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorKitchenSinkDashboard` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorKitchenSinkExercises` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorLiveStatus` |  | 3 | 1 | 3 | 1 | 3 | 1 | 1 |  |  | 7 |
| `OperatorLock` | 1 | 3 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |  | 9 |
| `OperatorLogin` | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |  | 9 |
| `OperatorLoginForm` |  |  |  |  |  |  |  |  |  | 2 | 0 |
| `OperatorManagerAuth` |  | 6 |  | 2 |  |  |  |  |  |  | 2 |
| `OperatorMenuItems` |  |  |  |  |  |  |  |  |  | 4 | 0 |
| `OperatorNumpad` |  |  |  |  | 2 |  |  |  |  |  | 1 |
| `OperatorOfficeShell` |  |  |  |  |  |  |  |  |  | 2 | 0 |
| `OperatorOperationalShell` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorOrderContact` |  |  |  |  |  |  |  |  |  | 3 | 0 |
| `OperatorOrderDetail` |  | 1 |  | 1 |  |  |  |  |  |  | 2 |
| `OperatorOrderProfileLines` |  |  |  |  |  |  |  |  |  | 2 | 0 |
| `OperatorOrderTimeline` |  |  |  |  |  |  |  |  |  | 2 | 0 |
| `OperatorPage` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorPageHeader` |  | 4 | 2 | 11 | 2 | 1 | 1 | 8 |  |  | 7 |
| `OperatorPeriodPicker` |  | 1 |  | 1 | 6 |  |  | 2 |  |  | 4 |
| `OperatorPhoneMenu` | 1 |  |  |  |  |  |  |  |  | 2 | 1 |
| `OperatorPinChange` |  |  |  |  |  |  |  |  |  | 2 | 0 |
| `OperatorPushInvite` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorPushSettings` | 1 |  |  |  |  |  |  |  |  |  | 1 |
| `OperatorPwaInstallInvite` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorPwaRuntime` | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |  | 9 |
| `OperatorPwaUpdatePrompt` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `OperatorRail` |  |  |  |  |  |  |  |  |  |  | 0 |
| `OperatorReasonDialog` |  | 1 |  | 1 |  |  |  |  |  |  | 2 |
| `OperatorSectionBar` |  | 1 | 1 |  | 1 | 1 | 1 | 1 |  |  | 6 |
| `OperatorSessionUnavailable` |  | 1 | 1 | 1 | 1 |  | 1 | 1 | 1 |  | 7 |
| `OperatorShortcutsHelp` |  |  |  |  |  |  |  |  |  | 2 | 0 |
| `OperatorSonner` | 1 | 2 | 1 |  | 1 | 1 | 1 | 1 | 1 |  | 8 |
| `OperatorSplitter` |  |  |  | 1 |  |  |  |  |  | 1 | 1 |
| `OperatorStationSetup` | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |  | 1 | 8 |
| `OperatorSuiteRail` | 1 | 1 | 1 |  | 1 | 1 | 1 | 1 |  |  | 7 |
| `OperatorSuiteSearch` | 1 | 2 | 1 | 4 | 2 | 1 | 2 | 1 |  | 1 | 8 |
| `OperatorSuiteShell` |  |  |  | 1 |  |  |  |  |  |  | 1 |
| `OperatorUrgentAlert` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `QueueColumnResizeHandle` |  |  |  |  |  |  |  |  |  |  | 0 |
| `QueueColumnStrip` |  |  |  |  |  |  |  |  |  |  | 0 |
| `RailItem` |  |  |  |  |  |  |  |  |  | 3 | 0 |
| `RailSection` |  |  |  |  |  |  |  |  |  | 4 | 0 |
| `RailToggle` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiAlert` |  | 2 |  |  | 1 |  |  |  |  |  | 2 |
| `UiAlertDescription` |  | 2 |  |  |  |  |  |  |  | 1 | 1 |
| `UiAlertTitle` |  | 2 |  |  |  |  |  |  |  | 1 | 1 |
| `UiBadge` |  | 4 |  |  | 19 |  |  |  |  |  | 2 |
| `UiButton` |  | 187 |  |  | 96 | 82 |  | 3 |  |  | 4 |
| `UiCard` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiCardAction` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiCardContent` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiCardDescription` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiCardFooter` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiCardHeader` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiCardTitle` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiCheckbox` |  | 1 |  |  | 7 | 9 | 1 |  |  |  | 4 |
| `UiCheckboxGroup` |  |  |  |  |  | 14 |  |  |  | 1 | 1 |
| `UiDateField` |  |  |  |  |  |  |  | 3 |  | 2 | 1 |
| `UiDateRangeField` |  |  |  |  |  | 2 |  |  |  |  | 1 |
| `UiDateTimeField` |  |  |  |  |  | 4 |  |  |  |  | 1 |
| `UiDialog` |  | 33 | 3 |  | 14 | 8 | 2 |  |  |  | 5 |
| `UiDialogClose` |  | 2 |  |  | 1 | 1 |  |  |  | 1 | 3 |
| `UiDialogContent` |  | 33 | 3 |  | 14 | 8 | 2 |  |  |  | 5 |
| `UiDialogDescription` |  | 34 | 3 |  | 14 | 9 | 1 |  |  | 1 | 5 |
| `UiDialogFooter` |  | 17 |  |  | 12 | 6 |  |  |  |  | 3 |
| `UiDialogHeader` |  | 32 |  |  | 14 | 8 |  |  |  | 1 | 3 |
| `UiDialogOverlay` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiDialogPortal` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiDialogTitle` |  | 32 | 3 |  | 14 | 8 | 2 |  |  | 1 | 5 |
| `UiDialogTrigger` |  |  |  |  |  | 1 |  |  |  |  | 1 |
| `UiFilterChip` |  | 1 | 3 |  | 2 | 3 | 5 | 4 |  | 2 | 6 |
| `UiIconButton` |  | 1 |  |  | 1 | 5 | 1 | 2 |  |  | 5 |
| `UiInput` |  | 39 |  |  | 23 | 16 |  |  |  |  | 3 |
| `UiNativeSelect` |  | 4 |  |  | 18 | 4 | 9 | 8 |  |  | 5 |
| `UiPopover` |  | 5 |  |  | 5 | 1 | 1 | 3 |  |  | 5 |
| `UiPopoverAnchor` |  |  |  |  | 2 |  |  |  |  |  | 1 |
| `UiPopoverArrow` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiPopoverClose` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiPopoverContent` |  | 5 |  |  | 5 | 1 | 1 | 3 |  |  | 5 |
| `UiPopoverPortal` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiPopoverTrigger` |  | 5 |  |  | 4 | 1 | 1 | 3 |  |  | 5 |
| `UiPopoverX` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiRadio` |  |  |  |  |  | 4 |  |  |  | 1 | 1 |
| `UiRadioGroup` |  | 1 |  |  |  | 6 | 1 |  |  |  | 3 |
| `UiScrim` |  | 1 |  |  |  |  |  |  |  |  | 1 |
| `UiSearchInput` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiSelect` |  |  |  |  |  | 9 | 1 |  |  |  | 2 |
| `UiSeparator` |  | 1 |  |  |  |  |  |  |  |  | 1 |
| `UiSheet` |  | 3 | 1 |  | 3 |  | 4 |  |  |  | 4 |
| `UiSheetClose` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiSheetContent` |  | 3 | 1 |  | 3 |  | 4 |  |  |  | 4 |
| `UiSheetDescription` |  | 2 | 1 |  |  |  | 4 |  |  | 1 | 3 |
| `UiSheetFooter` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiSheetHeader` |  |  |  |  |  |  | 3 |  |  | 1 | 1 |
| `UiSheetOverlay` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiSheetPortal` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiSheetTitle` |  | 2 | 1 |  |  |  | 4 |  |  | 1 | 3 |
| `UiSheetTrigger` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiSheetX` |  |  |  |  |  |  | 4 |  |  | 1 | 1 |
| `UiSkeleton` |  | 5 |  |  |  | 10 |  |  |  |  | 2 |
| `UiStepper` |  |  |  |  |  | 1 |  |  |  |  | 1 |
| `UiSwitch` |  | 11 |  |  |  | 4 |  |  |  |  | 2 |
| `UiTabs` |  |  |  |  | 3 | 2 |  |  |  |  | 2 |
| `UiTabsContent` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiTabsList` |  |  |  |  | 3 | 2 |  |  |  |  | 2 |
| `UiTabsTrigger` |  |  |  |  | 5 | 2 |  |  |  |  | 2 |
| `UiTextarea` |  | 4 |  |  | 9 | 8 |  |  |  |  | 3 |
| `UiTimeField` |  |  |  |  |  | 1 |  |  |  | 1 | 1 |
| `UiTimeRangeField` |  |  |  |  |  | 1 |  |  |  |  | 1 |
| `UiToggleChip` |  |  |  |  |  | 1 |  |  |  |  | 1 |
| `UiTooltip` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiTooltipArrow` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiTooltipContent` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiTooltipPortal` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiTooltipProvider` |  |  |  |  |  |  |  |  |  | 1 | 0 |
| `UiTooltipTrigger` |  |  |  |  |  |  |  |  |  |  | 0 |
| `UiVerificationCodeInput` |  |  |  |  |  | 4 |  |  |  |  | 1 |

### A.2 Órfãs, internas e só do Gestor

**Órfãs (0 apps e 0 uso vivo no kit), com o teste que as mantém de pé:**

| Peça | Por que é órfã | Teste que ainda a monta |
|---|---|---|
| `OperatorAppBar` | 0 usos | `tests/components/OperatorAppBar.test.ts` |
| `RailToggle` | só dentro do `OperatorAppBar` (órfão) | idem |
| `OperatorRail` | 0 usos | `tests/components/OperatorRail.test.ts` |
| `RailItem` | só dentro do `OperatorRail` | `tests/components/RailItem.test.ts` |
| `OperatorCapacityStatus` | só dentro do `OperatorRail` | `tests/components/OperatorCapacityStatus.test.ts` |
| `QueueColumnStrip`, `QueueColumnResizeHandle` | 0 usos desde o #1518 (o Gestor era o único) | `tests/components/QueueColumn.test.ts` |
| `UiSearchInput` | 0 usos | `tests/components/UiToolbarPrimitives.test.ts` |
| `UiCard` e família, `UiTooltip` e família, `UiPopoverArrow/Close/X`, `UiSheetClose/Footer/Trigger`, `UiTabsContent` | 0 usos em app (só se compõem entre si) | nenhum dedicado |

Também morre junto: a função `queueViewLabel` saiu de `presentation/queueColumns.ts` na pilha (0 consumidores, verificado).

**Internas (0 apps, mas montadas por outra peça viva do kit):** `OperatorConfirmDialog` (por `OperatorPwaRuntime`, então chega aos 9), `OperatorPwaUpdatePrompt`, `OperatorPushInvite`, `OperatorPwaInstallInvite` → `OperatorInstallSteps` (idem, via `OperatorPwaRuntime`), `OperatorLoginForm` (por `OperatorLogin`, 9 apps), `OperatorPinChange` e `OperatorIdentify` (por `OperatorLock`, 9 apps), `OperatorMenuItems` (por `OperatorSuiteRail`, `OperatorSuiteShell`, `OperatorPhoneMenu`), `OperatorShortcutsHelp` (por `OperatorSuiteRail` e `OperatorSuiteShell`), `RailSection` (só por `OperatorSuiteRail`, 7 apps), `OperatorOrderContact/ProfileLines/Timeline` (por `OperatorOrderDetail`, PDV e Gestor), `OperatorOfficeShell` (por `OperatorSuiteShell` e pelo Kitchen Sink), `OperatorOperationalShell` e `OperatorPage` (só pelo `OperatorKitchenSink`: hoje são peças de catálogo, sem tela de produção).

**Só o Gestor usa (e portanto podem mudar sem tocar os outros 8):** `OperatorSuiteShell` (`orders-nuxt/app/app.vue:94`) e, através dele, `OperatorUrgentAlert` e o modo `rail` do `OperatorOfficeShell`; `ColumnPicker` (1); `OperatorSplitter` (1); `useRouteFilters` (3); `useOperatorAppName` (2). `OperatorAppRoot` é do Gestor e do Kitchen Sink. `FilterBar` é do Gestor (2) e do PDV (1, `PosPreorderFilters.vue:79`). `OperatorReasonDialog` e `OperatorManagerAuth` são do Gestor e do PDV.

**Peças que chegam aos 9 sem ninguém escolher:** `app.config.ts`, os três CSS (`operator-theme`, `operator-base`, `operator-suite`, importados no `tailwind.css` de cada app), os 3 plugins (`deviceActivity.client.ts`, `errorReporter.client.ts`, `visualViewport.client.ts`, registrados pela layer), `server/utils/djangoProxy.ts` e `operatorCookies.ts` (o BFF de todos), `OfflineBanner`, `OperatorLock`, `OperatorLogin`, `OperatorPwaRuntime` (9 de 9), `OperatorStationSetup` (8), `OperatorSuiteSearch` (8), `OperatorPageHeader` e `OperatorLiveStatus` (7), `OperatorSuiteRail` (7), `OperatorSectionBar` e `UiFilterChip` (6).

### A.3 Composables (exports contados por nome em `app/` e `server/` de cada app)

| arquivo | export | hub | pos | kds | ord | prod | mkt | purch | bi | ks | kit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| useAlertSound.ts | `HOUSE_VOICE` |  |  | 1 |  |  |  |  |  |  |  |
| useAlertSound.ts | `useAlertSound` |  | 2 | 1 | 1 |  |  |  |  |  |  |
| useApiPath.ts | `useApiPath` | 2 | 14 |  |  |  |  |  |  |  | 2 |
| useConfirm.ts | `CONFIRM_DEFAULTS` |  |  |  |  |  |  |  |  |  |  |
| useConfirm.ts | `requestConfirm` |  |  |  |  |  |  |  |  |  |  |
| useConfirm.ts | `answerConfirm` |  |  |  |  |  |  |  |  |  |  |
| useConfirm.ts | `useConfirmState` |  |  |  |  |  |  |  |  |  | 2 |
| useConfirm.ts | `useConfirm` |  | 3 |  | 6 | 1 |  |  |  |  | 3 |
| useConnectivity.ts | `useConnectivity` | 1 | 3 |  |  | 2 |  |  |  |  | 3 |
| useIdentityCapture.ts | `PICK_QUIET_MS` |  |  |  |  |  |  |  |  |  |  |
| useIdentityCapture.ts | `useIdentityCapture` |  |  |  |  |  |  |  |  |  | 5 |
| useKioskMode.ts | `useKioskMode` |  |  |  |  | 1 |  |  |  |  | 1 |
| useMoreBelow.ts | `useMoreBelow` |  |  |  |  |  |  |  |  |  | 2 |
| useNextFocus.ts | `measureBottomObstruction` |  |  |  |  |  |  |  |  |  | 2 |
| useNextFocus.ts | `useNextFocus` |  | 5 |  | 1 |  | 1 |  |  |  | 4 |
| useNotifications.ts | `useNotifications` |  |  |  |  |  |  |  |  |  | 3 |
| useOperatorAppLink.ts | `useOperatorAppLink` | 1 | 2 |  |  | 1 | 1 |  | 2 |  | 4 |
| useOperatorCapacity.ts | `CAPACITY_POLL_MS` |  |  |  |  |  |  |  |  |  |  |
| useOperatorCapacity.ts | `CAPACITY_ROUTE` |  |  |  |  |  |  |  |  |  |  |
| useOperatorCapacity.ts | `useOperatorCapacity` |  |  |  |  |  |  |  |  |  | 7 |
| useOperatorLock.ts | `useOperatorLock` |  | 9 | 1 | 1 | 2 | 1 | 1 | 1 | 1 | 8 |
| useOperatorReloadHold.ts | `useOperatorReloadHold` |  | 1 |  |  |  |  |  |  |  | 4 |
| useOperatorSession.ts | `useOperatorSession` | 2 | 2 |  |  |  |  |  |  |  | 9 |
| useOperatorShortcutMap.ts | `useOperatorShortcutMap` |  |  |  |  |  |  |  |  |  | 3 |
| useOperatorWindowTitle.ts | `useOperatorAppName` |  |  |  | 2 |  |  |  |  |  |  |
| useOperatorWindowTitle.ts | `useOperatorWindowTitle` | 1 | 1 | 1 | 2 | 1 | 2 | 1 | 1 | 1 |  |
| useOrientationLock.ts | `useOrientationLock` |  |  |  |  |  |  |  |  |  | 3 |
| usePendingAction.ts | `usePendingAction` | 1 |  |  | 2 |  |  |  | 2 |  | 4 |
| usePwaAutoUpdate.ts | `usePwaAutoUpdate` |  | 1 |  |  |  |  |  |  |  | 4 |
| usePwaInstall.ts | `usePwaInstall` |  |  |  |  |  |  |  |  |  | 1 |
| usePwaUpdate.ts | `bindPwaUpdateRegistration` |  |  |  |  |  |  |  |  |  |  |
| usePwaUpdate.ts | `usePwaUpdate` |  | 1 |  |  |  |  |  |  |  | 4 |
| useRailState.ts | `RAIL_STATES` |  |  |  |  |  |  |  |  |  |  |
| useRailState.ts | `useRailState` | 1 | 2 |  |  |  |  |  |  |  | 9 |
| useRouteFilters.ts | `useRouteFilters` |  |  |  | 3 |  |  |  |  |  | 1 |
| useStationLock.ts | `useStationLock` |  | 2 |  | 5 |  |  | 1 |  |  | 4 |
| useStationProvision.ts | `useStationProvision` |  |  |  |  |  |  |  |  |  | 1 |
| useStationSetupOffer.ts | `useStationSetupOffer` | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |  |  |
| useSuiteChrome.ts | `useSuiteRailShown` | 1 | 1 |  |  |  |  |  |  |  | 2 |
| useSuiteChrome.ts | `useSharedCapacity` |  |  |  |  |  |  |  |  |  | 4 |
| useSuiteChrome.ts | `useOperatorInboxAlerts` |  |  |  |  |  |  |  |  |  | 4 |
| useSuiteChrome.ts | `provideOperatorInboxAlerts` |  |  |  | 1 | 1 | 1 |  |  |  | 1 |
| useSuiteChrome.ts | `useOperatorShortcuts` |  | 1 |  |  | 1 |  |  |  |  | 3 |
| useSuiteChrome.ts | `provideOperatorShortcuts` |  | 1 |  |  | 1 |  |  |  |  | 1 |
| useSuiteSearch.ts | `useSuiteSearchRequest` |  |  |  |  |  |  |  |  |  | 2 |
| useSuiteSearch.ts | `useSuiteSearchOwnership` |  |  |  |  |  |  |  |  |  | 1 |
| useSuiteSearch.ts | `useSuiteSearchResults` |  |  |  |  |  |  |  |  |  | 1 |
| useUserNotifications.ts | `useUserNotifications` |  |  |  |  |  |  |  |  |  | 1 |
| useWakeLock.ts | `useWakeLock` |  |  |  |  |  |  |  |  |  | 2 |
| useWebPush.ts | `useWebPush` |  |  | 1 |  |  |  |  |  |  | 3 |

Plugins da layer (`app/plugins/deviceActivity.client.ts`, `errorReporter.client.ts`, `visualViewport.client.ts`): registrados em todos os 9, sem escolha. `app.config.ts`: mesclado em todos os 9.

> **Atenção, WIP vivo nesta worktree.** Durante a leitura, `git status` mostrou mudanças não commitadas em `operator-kit/app/app.config.ts`, `operator-theme.css`, `FilterBar.vue`, `UiFilterChip.vue`, `OperatorAppSeal.vue`, `OperatorKitchenSink.vue`, `OperatorLoginForm.vue`, `OperatorManagerAuth.vue`, `tests/components/OperatorLogin.test.ts`, `pos-nuxt/tests/pages/preorders.test.ts` e a remoção (staged) de `marketing-nuxt/tests/components/OperatorLogin.test.ts`. É trabalho de F1 em curso (volta do `pointer: coarse` 48 px, `min-h-control` opt-in no `FilterBar touch` e no `UiFilterChip`, `--primary-ink`, `data-state` do `OperatorManagerAuth`). **Todos os arquivo:linha deste documento são do HEAD commitado (`e79ed522d`)**, lidos com `git show HEAD:`. Quem abrir PR da ONDA 0 parte desse WIP, não do HEAD.

## B. Os candidatos da ONDA 0

### B.1 Shell e rail

**Quem usa qual shell hoje:**

| App | Shell | Rail | Barra do celular |
|---|---|---|---|
| Gestor | `OperatorAppRoot` > `OperatorSuiteShell` (`orders-nuxt/app/app.vue:87, :94`) | à mão dentro do `OperatorSuiteShell.vue:131-166` (Tooltip > Chip > Button por seção) | `NuxtDashboardToolbar` + `NuxtNavigationMenu` horizontal no próprio `OperatorSuiteShell.vue:252-270` |
| Central | `app.vue` próprio (`hub-nuxt/app/app.vue:239`) | `OperatorSuiteRail` | não monta `OperatorSectionBar`; `OperatorPhoneMenu variant="header"` na barra de 56 px (`:303`) |
| PDV | `PosOperatorShell.vue` (`data-suite="v3"`, `:91`) | `OperatorSuiteRail` em `PosFunctionRail.vue:74` | `OperatorSectionBar` em `PosFunctionRail.vue:99` |
| KDS, Produção, Marketing, Compras, B.I. | `app.vue` próprio com `data-suite="v3"` | `OperatorSuiteRail` em `KdsNav.vue:27`, `ProductionNav.vue:43`, `MarketingNav.vue:50`, `PurchaseNav.vue:72`, `BiNav.vue:23` | `OperatorSectionBar` no mesmo `*Nav.vue` (`:38`, `:52`, `:59`, `:82`, `:31`) |
| Kitchen Sink | `OperatorAppRoot` > `OperatorKitchenSink` | demonstra `OperatorOfficeShell` (`OperatorKitchenSink.vue:204`) e `OperatorOperationalShell` (`:972`) | n/a |

- `OperatorOperationalShell` e `OperatorOfficeShell` em modo não-rail **não têm tela de produção**: só o catálogo os monta. O `OperatorOfficeShell` ganhou na pilha as props `rail`, `navbar`, `sidebarSize` (`OperatorOfficeShell.vue:12-14`) e perdeu `min-w-0`, `:ui="{ body: 'p-0 sm:p-0 gap-0' }"` e a altura mínima da navbar; consumidores: o próprio `OperatorSuiteShell` e o Kitchen Sink. Nenhum dos 7 é afetado.
- `OperatorRail`, `RailItem`, `RailToggle`, `OperatorAppBar` são órfãos (A.2). O rail vivo dos 7 é `OperatorSuiteRail` + `RailSection`, com `PopoverRoot` do `reka-ui` importado direto (`OperatorSuiteRail.vue:25`) e `<button>` cru no menu das iniciais (`:271-273`).
- O `OperatorSuiteShell` diz por que abandonou o `NavigationMenu` recolhido (`OperatorSuiteShell.vue:93-96`): o Chip abraçava o ícone de 20 px e os itens empilhavam sem o espaço do pé. A anatomia oficial confirma a causa: em `@nuxt/ui` 4.11.3, o tema do `NavigationMenu` tem `compoundVariant { orientation: "vertical", collapsed: true } → linkLabel: "hidden"` (`operator-kit/node_modules/@nuxt/ui/dist/shared/ui.CNAeRcb0.mjs`, cerca de :4505) e o Chip do item é `linkLeadingChipSize: "sm"` em volta do `UIcon` (`dist/runtime/components/NavigationMenu.vue:127-135`). O rótulo está no DOM, escondido por classe; o tooltip do recolhido é nativo (`:232`, com `tooltip` no item ou na prop).

**Rail canônico opt-in (proposta):**

1. Peça nova `OperatorSuiteNavigation` no kit (ou prop `rail-navigation="menu"` no `OperatorSuiteShell`, padrão `buttons`), montando `<NuxtNavigationMenu orientation="vertical" collapsed tooltip :items>` com os mesmos `itemFor()` que a barra do celular já usa (`OperatorSuiteShell.vue:70-91`: `label`, `icon`, `to`, `active`, `chip`, `aria-label`, `onSelect`). Duas listas: seções de cima e seções do pé (`foot`), como hoje.
2. "Recolhido com rótulo" e o Chip do tamanho da casa saem do **tema**, não de `:ui` por instância (o `canonicalPilot` proíbe `:ui=`): um `compoundVariant` no `app.config.ts` para `navigationMenu` com `{ orientation: "vertical", collapsed: true, class: { link: "flex-col gap-0.5 py-1.5", linkLabel: "block text-[10px] leading-tight", linkLeadingChipSize: ... } }`. Hoje nenhum app monta `NavigationMenu` vertical recolhido (o `OperatorSectionBar` é horizontal, `OperatorSectionBar.vue:62-68`; o rail do Gestor é Button), então o variant só afeta quem pedir a peça nova: é opt-in de fato. O `tailwind-merge` resolve `hidden` contra `block` pela ordem (o compound do app vem depois); confirmar com um teste de componente montado, não com string.
3. Chip numérico: `chip: { text, size: "4xl", color: "warning" }` no item já funciona na barra (`:80-84`); no recolhido, ajustar `linkLeadingChipSize` no mesmo compound para o Chip não cobrir o ícone (é o defeito descrito em `:93-96`).
4. A caixa de Avisos, Atalhos, Bloquear e o menu do operador continuam no `#sidebar-footer` (`:169-241`), agora com rótulo também (P1-5: "Avisos" virou sino sem rótulo). O `OperatorInbox` precisa de uma forma de item de menu (ver B.8).
5. Os 7 migram um por vez, trocando `OperatorSuiteRail` + `OperatorSectionBar` pela peça nova; quando o último trocar, morrem `OperatorSuiteRail`, `RailSection` e o `reka-ui` direto. Antes disso nada deles muda.

### B.2 Toast

- **Hoje:** o Gestor reaponta o auto-import `useSonner` para `operatorToast` (`orders-nuxt/nuxt.config.ts:113-117`), um objeto `{ error, success, info, warning }` que só aceita título (`orders-nuxt/app/utils/operatorToast.ts:27-36`) e despacha para o `useToast` capturado no plugin (`orders-nuxt/app/plugins/operator-toast.client.ts:3-5`). O toaster é o do `<NuxtApp :toaster>` do `OperatorAppRoot.vue:11-15`. Os outros 7 (e o Kitchen Sink) declaram `vue-sonner/nuxt` e o import `toast as useSonner` no próprio `nuxt.config.ts` (hub `:55, :72`; pos `:120, :142-144`; kds `:45, :67-69`; prod `:56, :86-88`; mkt `:95, :110-112`; purch `:47, :60`; bi `:43, :58`; ks `:43, :61`) e montam `<OperatorSonner />` (hub `app.vue:635`, kds `:63`, prod `:61`, mkt `:170`, purch `:72`, bi `:51`, ks `:48`, pos `PosOperatorShell.vue:131`). O kit só declara o import no harness do catálogo (`operator-kit/nuxt.config.ts:57`) e deduplica `vue-sonner` (`:96`).
- **Chamadas a `useSonner.*` por app (só `app/`):** Gestor 41 (24 error, 16 success, 1 info), Produção 36, Marketing 31, Compras 25, B.I. 15, KDS 8, PDV 7, Central 0, Kitchen Sink 0; o kit 8 (`OperatorLock.vue:111, :124, :135`, `OperatorMenuItems.vue:52-53`, `OperatorRail.vue:83-84` (órfão), `useOperatorLock.ts:133`). `useToast()` direto: só `OperatorUrgentAlert.vue:24` e 2 no Gestor.
- **Chamadas com segundo argumento (o shim do Gestor ignoraria):** `production-nuxt/app/composables/useProductionMutationGuard.ts:219` (`action`), `:401` e `:407` (`description`); `purchase-nuxt/app/pages/index.vue:669` (`description` + `action`); `bi-nuxt/app/pages/index.vue:130` (`action`). Cinco pontos; sem eles o shim atual perde o botão "Ir até lá" e a segunda linha.
- **O `OperatorUrgentAlert` depende de toast:** sim. `remind()` chama `toast.add` com `description`, `duration` e `actions` (`OperatorUrgentAlert.vue:75-91`), e `useToast()` é o do Nuxt UI, que só desenha onde há `<NuxtApp>`/`UApp` com toaster. Nos 7 apps não há `UApp`: o lembrete sumiria sem erro.

**Subir o shim ao kit (opt-in):**

1. `operator-kit/app/utils/operatorToast.ts` com a API que os 9 já chamam: `error/success/info/warning(title, options?)` em que `options` aceita `description`, `action: { label, onClick }`, `duration`. Despacha para `useToast().add({ title, description, color, icon, actions: [{ label, onClick, color, variant: "outline" }] })` quando o app declarou o toaster do Nuxt UI, e para `vue-sonner` quando não.
2. Como o kit sabe: uma chave de app, `app.config.ts` do app com `operatorKit: { toaster: "nuxt-ui" | "sonner" }` (padrão `sonner`), no mesmo padrão que o `OperatorPageHeader` já usa para `operatorHeader.workstationBadge` (`OperatorPageHeader.vue:77-79`). Ou, mais simples, o plugin do kit (`operator-toast.client.ts`, subido do Gestor) se registra só se `useAppConfig().operatorKit?.toaster === "nuxt-ui"`. O auto-import `useSonner` continua o nome do contrato; o kit passa a declará-lo (`imports`) apontando para o shim, e cada app tira o seu `{ from: "vue-sonner" }` quando migrar.
3. O `OperatorUrgentAlert` passa a chamar o shim (`operatorToast.error(title, { description, action })`) e não `useToast` direto. Assim ele pode ser montado num app com Sonner.
4. A trava `catalog.guardrails.test.ts:168-170` (que exige `dedupe: ["reka-ui", "vue-sonner"]`) fica até o último app migrar; depois inverte para proibir o Sonner.

### B.3 OperatorPageHeader: slots

**Declarados no HEAD** (`OperatorPageHeader.vue`): `lead` (:111), `subtitle` (:126), `status` (:127), `search` (:132), `phone-actions` (:151), `actions` (:157), `filters` (:181), `below` (:188, devolvido pelo #1521), `feedback` (:197, novo, só o Gestor passa). No `main` eram os mesmos, sem `feedback`.

**Passados pelos consumidores** (filhos diretos `<template #x>`, saída de `slots.py`):

| Consumidor | Slots passados |
|---|---|
| `kds-nuxt/app/pages/[ref].vue:295` | status, search, actions |
| `kds-nuxt/app/pages/index.vue:34` | nenhum |
| `pos-nuxt/app/components/PosPreordersShell.vue:59` | search, status, actions |
| `pos-nuxt/app/components/PosSettingsShell.vue:39` | lead, status, actions, below (:51) |
| `pos-nuxt/app/pages/settings/seating.vue:283` | lead, status, actions, below (:369) |
| `pos-nuxt/app/pages/session/index.vue:567` | status, actions |
| `bi-nuxt/app/pages/index.vue:232` | search, actions, phone-actions, filters |
| `bi-nuxt/app/pages/{sales,profiles}.vue` | status, actions, phone-actions, filters |
| `bi-nuxt/app/pages/{scenarios,explore,forecast,cash,customers}.vue` | status, actions, phone-actions |
| `marketing-nuxt/app/components/MarketingPageHeader.vue:39` (o wrapper de 10 telas) | lead, status, search, actions, phone-actions, filters, below |
| `production-nuxt/app/components/ProductionHeader.vue:291` | lead, subtitle, status, search, phone-actions, actions, filters, below (:375) |
| `production-nuxt/app/components/RecipeHeader.vue:30` | lead, search, actions |
| `purchase-nuxt/app/pages/index.vue:1139` | lead, subtitle, status, search (duas vezes, :1203 e :1213, em `v-if`/`v-else`), phone-actions, actions, filters, below (:1332) |
| Gestor (11 telas) | status, search, actions, filters, feedback, lead, phone-actions |

**Passados e não declarados hoje: nenhum.** O único caso foi o `#below` (P0-2), já devolvido. O `#icon` que o anexo D do laudo atribui ao cabeçalho no B.I. e no Compras é do `UiFilterChip` (`bi-nuxt/app/pages/sales.vue:162`, `purchase-nuxt/app/pages/index.vue:1309`), que declara `<slot name="icon" />`: não é slot morto.

**Slots que sobrevivem, mas mudaram de lugar ou de efeito (sem opt-in):**
- `#phone-actions` agora fica em `#right` sem `md:hidden` (`OperatorPageHeader.vue:151`); no `main` morava num bloco `md:hidden`. B.I. (8 telas) e Compras passam a mostrar os dois seletores no desktop (H6 do laudo).
- `#actions` perdeu a faixa rolável do celular (`main` :138-139, `overflow-x-auto ... md:flex-wrap`); hoje é `flex items-center gap-2` (`:152-158`).
- `#subtitle` saiu de baixo do título e foi para `#trailing`, na mesma linha (`:125-128`); a Produção usa `#subtitle` para a linha de hora e contagem (`ProductionHeader.vue:293`).
- O componente tem 4 raízes (Navbar, Toolbar, `below`, feedback): `class` e atributos do consumidor deixam de cair no cabeçalho.

### B.4 OperatorLiveStatus

- **Diff main → HEAD** (`OperatorLiveStatus.vue`): o `main` era `<span>` com `live-dot` e `dotClass` por tom (`calm` neutro, `late` âmbar, `off` vermelho), hora visível e rótulo visível fora do `live` (`showLabel = tone !== "live" || !time`), rótulo em `font-semibold text-warning`/`text-destructive`. O HEAD é `<NuxtBadge>` com `badgeColor = tone === "off" ? "error" : "success"` (`:24-26`), texto visível `display` = `"On HH:MM"` ou `"Off"` (`:36-44`), o rótulo só no `aria-label`/`title` (`:27-35`, `:53-54`) e `NuxtChip size="xl"` (`:59`). Props idênticas.
- **Tons que cada app passa:**

| App | Onde | Tons possíveis |
|---|---|---|
| PDV | `pages/index.vue:1244`, `session/index.vue:569`, `session/closing.vue:243` (via `presentation/events.ts:30-46`) | live, calm, off |
| KDS | `pages/[ref].vue:137-139, :297` | live, calm |
| Produção | `ProductionHeader.vue:102, :310` | live, **late** |
| Marketing | `MarketingDecisionQueue.vue:146`, `history.vue:186`, `scheduled.vue:57` (`presentation/liveStatus.ts:11, :39-56`) | live, calm, off (o tipo admite late) |
| Compras | `pages/index.vue:762, :1160` | live, calm, off |
| B.I. | `BiLiveStatus.vue:25-26` | live, off |
| Gestor | `index.vue:108-115, :1233`, `catalog.vue:1049`, `[ref].vue:658` | live, **late**, calm, off |

  Resultado no HEAD: `late` da Produção e do Gestor e `calm` do PDV, KDS, Marketing e Compras saem verdes "On". Todo texto visível é inglês.
- **Contrato escrito:** `operator-kit/README.md:422` ("o ponto ao vivo com a hora; fora do ao vivo o estado se escreve por extenso") e `marketing-nuxt/app/presentation/liveStatus.ts:1-3`.
- **Travas que cristalizam o binário:** `orders-nuxt/tests/canonicalPilot.guardrails.test.ts:386-389` (`chipSizeOk`: "o On/Off é xl") e `operator-kit/tests/components/SuiteChrome.test.ts:608-656` (três testes: "On 22:03", "Off", e "poll automático continua On success"; a pilha apagou o teste "no menor celular, atualização calma vira ponto").
- **O que mudar:** é correção de defeito, não opt-in: os 9 têm de voltar ao contrato do README. Proposta concreta para a decisão do Pablo antes do teste: `NuxtBadge` (fica, é canônico) com cor por tom (`live` success, `calm` neutral, `late` warning, `off` error) e texto pt-BR: `live` mostra só a hora; os outros mostram o rótulo que o app já manda (`label`: "Atualiza a cada 60 s", "Sem atualizar", "Sem conexão"). O `max-[379px]` do `calm` volta como regra de largura. As duas travas passam a exigir os quatro tons e a proibir "On"/"Off" visíveis; a de vocabulário ganha "On"/"Off".

### B.5 Período

- **Diff main → HEAD** (`OperatorPeriodPicker.vue`): sai o popover feito à mão (`<div v-if="open" class="absolute ...">` com `onClickOutside`) e entram `NuxtFieldGroup` + `NuxtButton` + `NuxtPopover` (`:167-190`), presets em `NuxtTabs variant="pill"` (`:204-235`), erro em `NuxtAlert` (`:262-269`). Os três campos de data trocam `UiDateField` por `NuxtInput type="date"`: De (`:248`), Até (`:259`), Ir para o dia (`:294`). Também sai o `min-h-control` dos botões (setas e presets) e o rótulo do botão vira `:label` (o `aria-label` "Próximos 7 dias" dos presets agora vai como chave `"aria-label"` no item das Tabs, `:110-116`; não verificado se o `NuxtTabs` 4.11.3 o repassa).
- **Consumidores (10 em 5 apps):** PDV `preorders/index.vue:345`; B.I. `BiWindowPicker.vue:11`, `forecast.vue:69`; Produção `ProductionStageGrid.vue:1001`, `board.vue:127`, `mise-en-place.vue:178`, `reports.vue:160, :355`, `close.vue:423`; Gestor `history.vue:146`. O laudo diz "B.I. 2, PDV 1, Produção 6, Gestor 1" e confere.
- **`UiDateField`, `UiDateRangeField`, `UiTimeField`, `UiTimeRangeField`, `UiDateTimeField`:** não mudaram na pilha (fora do `git diff --stat`). Consumidores: `UiDateField` B.I. 3 + kit 2 (`UiDateTimeField`, `OperatorDayPicker:172`); `UiDateRangeField` Marketing 2; `UiTimeField` Marketing 1 + kit 1; `UiTimeRangeField` Marketing 1; `UiDateTimeField` Marketing 4. São camada fina sobre `NuxtInputDate`/`NuxtCalendar`/`NuxtInputTime` (anexo A do laudo, 1.1).
- **Bug do `UiDateTimeField`:** `:58-59` passam `min?.slice(0, 10)`/`max?.slice(0, 10)` ao `UiDateField`, e o `UiTimeField` (`:64-72`) não recebe limite nenhum. No dia do limite, a hora fica livre. Correção: quando `date === min.slice(0,10)`, passar `min.slice(11,16)` como `min` do `UiTimeField` (idem `max`), ou trocar a composição por `NuxtInputDate granularity="minute"` (não testado).
- **Trava cega:** `kitOwnership.guardrails.test.ts:249-261` só casa `<input ... type="date">` e só itera os apps, não o kit. E `tests/components/OperatorDatePickers.test.ts:147` e `:194` consultam `input[type="date"]`: o teste do kit hoje **exige** o nativo (o do `OperatorDayPicker`, `:68-93`, ainda usa `UiDateField`).
- **O que mudar:** correção para os 9, não opt-in: `OperatorPeriodPicker` volta a `UiDateRangeField` (De/Até com `min`/`max`) e `UiDateField` (Ir para o dia), mantendo o `NuxtPopover`/`NuxtTabs` novos. A trava passa a casar `<(input|NuxtInput|UInput|UiInput)` com `type="date|time|datetime-local|month|week"` e a varrer `operator-kit/app` também; o teste do picker volta a `findAllComponents(UiDateRangeField)`.

### B.6 UiNativeSelect, UiButton, UiFilterChip, FilterBar, UiSelect, UiSearchInput

| Peça | O que é | Consumidores | O que a pilha mudou |
|---|---|---|---|
| `UiNativeSelect` | **paralela**: `<select>` cru (`UiNativeSelect.vue:59`) + chevron global em `operator-theme.css` ("pedido Pablo 10/09"); o README a chama de "peça certa" para lista curta (`README.md:808`) | bi 8, mkt 4, pos 4, prod 18, purch 9 (43) | nada no arquivo; perdeu o `h-control` do `input`/`select` do tema, que não a afeta (é `<select>` com classes próprias) |
| `UiButton` | **fina com API paralela**: variantes shadcn traduzidas para `NuxtButton` (`:106-125`), `loadingIcon: "line-md:loading-loop"` (`:42`), `:ui` (`:125`) | pos 187, prod 96, mkt 82, bi 3 (368) | nada no arquivo; herda o tema do `button` do kit (o WIP acrescenta `--primary-ink` em `soft`) |
| `UiFilterChip` | era **paralela** (`<button class="min-h-control rounded-full ...">`), virou **fina**: `NuxtButton` + `NuxtBadge` (`:11-25`) | kds 3, prod 2, mkt 3, purch 5, bi 4, pos 1 (+2 no kit) | perdeu `min-h-control` (44 px), a pílula, o ativo sólido e o visual `suite:`; comentário vira "compatibilidade temporária". Quebrou `pos-nuxt/tests/pages/preorders.test.ts:858`. A trava `tests/components/UiToolbarPrimitives.test.ts:36` **exige** `not.toContain("min-h-control")`. O WIP já devolve `class="min-h-control"` |
| `FilterBar` | **composição fina**: `NuxtFieldGroup`, `NuxtPopover`, `NuxtButton`, `NuxtInput` | ord 2, pos 1 (`PosPreorderFilters.vue:79`, com `touch`) | o painel virou `NuxtPopover` (`:151-300`); `touch` virou só `size="md"` (`:48-50`) e perdeu o `min-h-control` (main `:51-66`); some o `data-filter-backdrop`; `date-range` virou `NuxtInput type="date"` (`:272, :285`, sem consumidor). O `[data-filter-dimension]` agora só existe com o popover aberto, o que quebrou `preorders.test.ts:566`. O WIP devolve o envelope por `touchTarget`/`itemTarget` |
| `UiSelect` | **fina**: `NuxtSelectMenu` (`:151`) + `:ui` (`:163`) com `z-[60]` (`:126`) | mkt 9, purch 1 | nada no arquivo; o kit tirou o `size md → h-control` do `selectMenu` no `app.config`, então o gatilho cai para a altura compacta do Nuxt UI |
| `UiSearchInput` | **paralela**: `<input>` (`:33`), `<kbd>` (`:44`), `<button>` (`:50`) | 0 | nada; órfã, apagar |

Diff relevante do tema (`app.config.ts`, HEAD `:157-165`): saíram os overrides `input`, `select`, `selectMenu`, `textarea` `size md → h-control` (44 px) e o `alert.defaultVariants: { variant: "subtle" }` com `title/description: text-default`. Do `operator-theme.css` saiu o `@media (pointer: coarse) and (min-width: 600px) { --spacing-control: 3rem }` (no `main`, `:33-37`). O WIP o devolve.

**Opt-in:** o comportamento antigo volta para os 7 via `suite:` (o marcador que eles já vestem). Exemplo: `UiFilterChip` com `class="min-h-control suite:rounded-full ..."`; o tema do `input`/`select` com `suite:h-control` nos slots `base` (tailwind-variants aceita classe com variante), e o `pointer: coarse` restrito a `[data-suite="v3"]` ou ao `<html>` marcado. O Gestor, sem `data-suite`, fica no compacto oficial.

### B.7 Hydration mismatch no shell

Não foi rodado navegador; o que segue é leitura. O laudo viu o aviso no Gestor em todas as páginas e larguras e no `/preorders` do PDV tanto no HEAD quanto no `main`, então a causa é antiga e comum.

| Fonte | Arquivo:linha | Risco | Correção |
|---|---|---|---|
| `useSuiteRailShown` usa `useMediaQuery(..., { ssrWidth: 1280 })`: no servidor é sempre "tem rail"; no celular e no tablet em pé o cliente diz "não tem" | `operator-kit/app/composables/useSuiteChrome.ts:19` | **alto** onde é usado fora de `ClientOnly`: `hub-nuxt/app/app.vue:607` (`<MoreBelow v-if="!railShown" />`). No kit ele está dentro de `ClientOnly` (`OperatorPageHeader.vue:159-167`, `OperatorSuiteRail.vue:212, :243`), e no PDV também (`pages/index.vue:1325-1327`) | decidir só por CSS (`rail:`/`norail:`, que já existem em `operator-suite.css:26-33`) o que é só mostrar/esconder; e onde precisa sair do DOM, `ClientOnly` ou um `mounted` (o mesmo truque do `OfflineBanner.vue:7-15`) |
| `useMediaQuery` sem `ssrWidth` | `OperatorSuiteSearch.vue:65` (`isPhone` em `:294` e `:389`), `OperatorStationSetup.vue:76` (`:84`) | baixo: os dois só pesam dentro do modal fechado ou depois do `onMounted` (`useStationProvision.load`) | `ssrWidth` explícito ou leitura só depois de montar |
| Hora formatada no SSR com o fuso do servidor | `orders-nuxt/app/pages/index.vue:118-124` (`toLocaleTimeString("pt-BR")` sem `timeZone`), passada ao `OperatorLiveStatus` | **alto em produção** (contêiner em UTC, tablet em `America/Sao_Paulo`): o "On 21:27" do servidor diverge do cliente. No ensaio do laudo servidor e navegador estavam na mesma máquina, então não explica o que ele viu | formatar com `timeZone` da loja (o kit já tem `todayIso(now, timeZone)` em `presentation/dates.ts:53`) ou só no cliente |
| Relógio vivo | `OperatorUrgentAlert.vue:25` (`useNow`) e `:61` (`Date.now()`) | nenhum hoje: está em `<ClientOnly>` (`OperatorSuiteShell.vue:274`). Passa a ser risco no dia em que for montado fora dele | manter o `ClientOnly` como contrato da peça (dizer no README) |
| `currentOrigin: import.meta.client ? window.location.origin : ""` no render | `useOperatorAppLink.ts:22` | nenhum hoje: `installed` é `false` no SSR e no primeiro render do cliente, e com `installed: false` a saída é a mesma (`presentation/appLaunch.ts:54-56`) | nada; registrar |
| `useOnline` | `OfflineBanner.vue` | resolvido: só mostra depois de `onMounted` (`:7-15`) | nada |

**Como fechar F5 com prova:** ligar `__VUE_PROD_HYDRATION_MISMATCH_DETAILS__: true` no `vite.define` do build do e2e (ou rodar `nuxt dev`, que já imprime o nó) e capturar o primeiro nó citado em `/` do Gestor e em `/preorders` do PDV a 390 e a 1280. Sem isso, qualquer correção é chute. A trava nova: e2e que reprova com "Hydration" no console, por app.

### B.8 OperatorUrgentAlert

- **Onde é montado:** só no `OperatorSuiteShell.vue:274`, dentro de `<ClientOnly>`. Logo, só no Gestor.
- **Depende de:**
  - `useOperatorInboxAlerts()` (`OperatorUrgentAlert.vue:23`), que lê o registro em `nuxtApp._operatorSuiteChrome` (`useSuiteChrome.ts:77-99`). Só tem dado se o app chamou `provideOperatorInboxAlerts`: hoje Gestor (`orders-nuxt/app/app.vue`), Produção e Marketing (A.3). E só aciona se o item tem `respondByIso` (`useSuiteChrome.ts:40-42`); a Produção já espelha `respond_by_iso` (commit `e6a377dfd`).
  - `useToast()` do Nuxt UI (`:24`) para o lembrete (`:75-91`): exige `UApp` (B.2).
  - `useNow` (`:25`), `navigateTo` (`:55`), `presentation/suiteChrome.ts` (`urgentAlerts`, `reminderIntervalMs`, `respondInLabel`).
  - **Som: nenhum.** O arquivo não chama `useAlertSound` (grep vazio). O som do Gestor é do app (`useAlertSound` 1 uso).
- **O que falta para montar em qualquer shell:** (1) trocar `useToast` pelo shim do kit (B.2); (2) exportá-lo como peça montável no `app.vue` de cada app ou dentro de `OperatorPwaRuntime` (que os 9 já montam), sempre em `ClientOnly`; (3) cada app que quer o aviso registra a fonte com `respondByIso`; (4) o modal usa `NuxtModal`, que nos 7 apps sem `UApp` funciona (o `OperatorLogin` e o `OperatorPhoneMenu` já usam `NuxtModal` neles), mas o portal fica fora do `[data-suite]`; (5) decidir se toca som (hoje não toca em lugar nenhum).

### B.9 Busca (OperatorSuiteSearch)

- **Diff main → HEAD:** no `main`, a variante `header` era um `<input>` de 22rem no cabeçalho (`main :331-338`) que filtrava a tela enquanto se digitava e abria um painel ancorado (`data-suite-search-panel`, `main :403`); só o celular e a variante `hotkey` iam para diálogo (`main :88`, `useDialog = hotkey || isPhone`). No HEAD é sempre `NuxtDashboardSearchButton` (`:280-290`) que abre `NuxtModal` (`:292-297`, `fullscreen` no celular), com `NuxtTabs` de alcance e `NuxtCommandPalette`. O `v-model` (filtro da tela) continua, mas só se escreve dentro do modal, que cobre a lista. Saíram `data-search-shortcut`, `data-suite-search-clear`, `-dialog-close`, `-dialog-input`, `-group` (nenhum app os usa, verificado pelo laudo).
- **Quem filtra a tela pelo `#search` com `v-model`** (perdem a leitura do resultado): KDS `[ref].vue:299`, Produção `ProductionHeader.vue:318`, `RecipeHeader.vue:41`, Marketing (`MarketingPageHeader.vue:42`, ex.: `campaigns.vue`), Compras `index.vue:1203, :1213`, B.I. `index.vue:233`, PDV `PosPreordersShell.vue:62`. Consumidores totais: hub 1, pos 2, kds 1, ord 4, prod 2, mkt 1, purch 2, bi 1, mais o padrão dentro de todo `OperatorPageHeader` (`:133`).
- **Opt-in:** uma prop `mode="inline" | "dialog"` no `OperatorSuiteSearch`. `inline` (padrão até cada app migrar) devolve o campo que filtra e o painel ancorado do `main`, mas montado com `NuxtInput` + `NuxtPopover` + `NuxtCommandPalette` (sem `<input>` cru). `dialog` é o de hoje. O Gestor passa `mode="dialog"` explícito (ou o `OperatorPageHeader` lê `operatorKit.search` do `app.config`). A trava `guardrails.suiteSearch.test.ts:91` ganha "o app declara o modo".

## C. Testes do kit que conferem cada peça, e o que muda

| Peça | Teste | O que confere hoje | O que muda |
|---|---|---|---|
| Rail/shell | `catalog.guardrails.test.ts:76-92` | strings do `OperatorOfficeShell` (`NuxtDashboardSidebarCollapse`, os dois `NuxtDashboardPanel`) e do `OperatorSuiteShell` (`data-suite-rail-footer`, `flex-col items-center`) | ganhar o caso do rail `NavigationMenu` opt-in, montado (não string): rótulo visível, chip, `aria-current` |
| Rail/shell | `guardrails.appBar.test.ts:82-139` ("migraram para o rail da suíte usam as duas peças da layer"), `:142` (um só Avisos), `:183` (ordem do pé), `:207`, `:217`, `:232` (`rail:` e não `md:`), `:244` | presença de `OperatorSuiteRail`/`OperatorSectionBar` nos `*Nav.vue` e a ordem do pé | aceitar a peça nova como alternativa por app; a ordem do pé vale para as duas |
| Rail | `tests/components/OperatorRail.test.ts`, `RailItem.test.ts`, `OperatorAppBar.test.ts`, `QueueColumn.test.ts`, `OperatorCapacityStatus.test.ts` | peças órfãs | apagar junto com as peças |
| Toast | `catalog.guardrails.test.ts:168-170` | `dedupe: ["reka-ui", "vue-sonner"]` | fica até o último app; depois inverte. Novo: teste do shim (as 4 cores, `description`, `action`, os dois destinos) |
| Toast | `tests/components/OperatorSonner.test.ts` | o Sonner | fica até o último app |
| PageHeader | `tests/components/SuiteChrome.test.ts` (`describe("OperatorPageHeader")`, `:503-606`) | slots e rail recolhido | novo teste do `#below` já veio no #1521. Novo guard geral: compilar o template de cada consumidor das peças do kit (`@vue/compiler-dom`, o mesmo que o `canonicalPilot` usa) e comparar os `<template #x>` com os `<slot name>` da peça |
| LiveStatus | `tests/components/SuiteChrome.test.ts:608-656`; `orders-nuxt/tests/canonicalPilot.guardrails.test.ts:386-389` | "On/Off" e `size="xl"` | exigir os 4 tons, texto pt-BR, proibir "On"/"Off"; `chipSizeOk` sem o caso especial ou com o novo tamanho decidido |
| Vocabulário | `guardrails.vocabulary.test.ts` | "aparelho", "fornada", "passo" | ganhar "On", "Off" (como texto visível) |
| Período | `tests/components/OperatorDatePickers.test.ts:123-200` (`input[type="date"]` em `:147`, `:194`) | o nativo | voltar a `findAllComponents(UiDateRangeField/UiDateField)`; o teste de `aria-label` "Próximos 7 dias" que a pilha apagou volta |
| Período | `kitOwnership.guardrails.test.ts:249-261` | `<input type=date>` só nos apps | casar `NuxtInput`/`UInput`/`UiInput` e varrer `operator-kit/app` |
| Toque | `catalog.guardrails.test.ts:119-127` | `pointer: coarse` ausente em **`operator-base.css`** (a regra morava em `operator-theme.css`) e nenhum `h-control` global | reescrever: a regra existe em `operator-theme.css`, restrita ao marcador de opt-in; nenhum `h-control` fora de `suite:` |
| FilterChip / FilterBar | `tests/components/UiToolbarPrimitives.test.ts:28-44` (`:36` exige **não** ter `min-h-control`), `:53`, `:66` (44 px dos outros); `tests/components/FilterBar.test.ts:70-135` | a pílula sem alvo | inverter `:36`; FilterBar com `touch` mede o envelope; o PDV (`preorders.test.ts:566, :858`) volta a passar |
| Busca | `tests/components/OperatorSuiteSearch.test.ts:105-219`; `guardrails.suiteSearch.test.ts:54-91` | o modal | casos para `mode="inline"` (digitar filtra sem abrir modal) e `dialog` |
| Card | `catalog.guardrails.test.ts:129-143` | a string exata do `body` do Card | trocar string por renderização (padding 0 com tabela única) |
| PWA | `catalog.guardrails.test.ts:101-112` | strings de classe do `OperatorPwaRuntime` | idem, por renderização |
| Ledger | `scripts/check_operator_component_ledger.py:35-39, :296-306` | estrutura canônica (`NuxtDashboard*`, `NuxtNavigationMenu`...) fora do kit | é o argumento para o rail e a barra do celular morarem no kit; registrar com motivo as 7 peças do Gestor ou subi-las |

## D. Mudanças de comportamento compartilhado sem opt-in (`git diff origin/main...HEAD -- surfaces/operator-kit`)

Diff: 73 arquivos, +5.327/-3.406. Abaixo, o que muda para quem não pediu. Linhas do HEAD.

| # | Mudança | Arquivo:linha (HEAD) | Apps afetados (além do Gestor) |
|---|---|---|---|
| D1 | `OperatorLiveStatus` binário "On/Off", inglês, `late`/`calm` verdes | `OperatorLiveStatus.vue:24-44, :48-61` | pos, kds, prod, mkt, purch, bi |
| D2 | `OperatorPeriodPicker` com data nativa; presets em Tabs sem `min-h-control` | `OperatorPeriodPicker.vue:204-235, :248, :259, :294` | pos, prod, bi |
| D3 | Tema: sem `h-control` em `input`/`select`/`selectMenu`/`textarea`; sem `alert` subtle padrão; Card/Table/PageCard/Chip 4xl/Kbd soft novos | `app.config.ts:25-36, :48-100, :101-165` | os 9 (campos Nuxt UI das peças do kit; `UiSelect` de mkt e purch; Alerts sem `variant` no Kitchen Sink saem sólidos) |
| D4 | Tablet de toque perde 48 px | `operator-theme.css` (regra do `main :33-37` apagada) | os 7 com `h-control`/`min-h-control` (pos 16, prod 11, purch 31, bi 18, mkt 6, kit 21 ocorrências, contagem do laudo) |
| D5 | `UiFilterChip` sem alvo de 44 px nem pílula | `UiFilterChip.vue:11-25` | kds, prod, mkt, purch, bi, pos |
| D6 | `FilterBar` em popover, `touch` sem envelope, `data-filter-backdrop` some | `FilterBar.vue:48-50, :151-300` | pos |
| D7 | `OperatorPageHeader`: `#phone-actions` no desktop, `#actions` sem rolagem, `#subtitle` na linha do título, 4 raízes, sem `bg-card`, altura fixa do `DashboardNavbar` | `OperatorPageHeader.vue:91-198` | pos, kds, prod, mkt, purch, bi |
| D8 | `OperatorSuiteSearch`: campo vira botão + modal | `OperatorSuiteSearch.vue:280-297` | os 8 que montam (hub, pos, kds, prod, mkt, purch, bi; ks não) |
| D9 | `OperatorSectionBar` vira `NuxtNavigationMenu` horizontal; selo vira "!" | `OperatorSectionBar.vue:40-51, :62-68` | pos, kds, prod, mkt, purch, bi |
| D10 | `OperatorInbox`: sem `RailSection` rotulado; sino `NuxtButton` neutro em Chip; some `data-operator-inbox-count`; o comentário "não interrompe" sai | `OperatorInbox.vue:116-140` | os 7 do `OperatorSuiteRail` (sino escuro sobre o bronze do rail) e hub/pos no cabeçalho |
| D11 | `OperatorPhoneMenu`: `reka-ui` Dialog/Popover → Nuxt UI; `data-active` novo | `OperatorPhoneMenu.vue` (todo o template) | hub (header) e os 6 da `OperatorSectionBar` (o "Mais") |
| D12 | `OperatorIdentify`: teclado `NuxtButton size="xl"` sem `touch-manipulation`, `NuxtPinInput :length="8"` | `OperatorIdentify.vue:225-234` | os 9 (via `OperatorLock`) e pos 6 (via `OperatorManagerAuth`) |
| D13 | `OperatorLock`: título vira `NuxtAlert` | `OperatorLock.vue:176, :215` | os 9 |
| D14 | `OperatorLogin`: `NuxtModal` + `OperatorLoginForm` novo | `OperatorLogin.vue:55-83, :87` | os 9 (quebrou `marketing-nuxt/tests/components/OperatorLogin.test.ts`, que o WIP apaga) |
| D15 | `OperatorManagerAuth` e `OperatorReasonDialog`: `UiDialog` (do app) → `NuxtModal` | `OperatorManagerAuth.vue`, `OperatorReasonDialog.vue` | pos (quebrou `sessionIndex.layout.test.ts:301`; o WIP devolve o `data-state`) |
| D16 | `OperatorStationSetup`: some `data-suite`, nova prop `mode` (padrão modal, compatível) | `OperatorStationSetup.vue:18-25, :80` | 8 (visual) |
| D17 | `OperatorPwaRuntime`/`UpdatePrompt`/`InstallInvite`/`PushInvite`/`ConfirmDialog`: Nuxt UI, pilha de avisos com `bottom-[calc(...)]` | `OperatorPwaRuntime.vue:56-70` | os 9 |
| D18 | `OperatorAppSeal`: Nuxt UI, prop `placement` | `OperatorAppSeal.vue:11-15, :35-60` | hub, pos e todo `OperatorPageHeader` |
| D19 | `OfflineBanner`: `NuxtBanner` (o título "Sem conexão, tentando reconectar" está escrito com travessão em `:27`, contra a regra de copy) | `OfflineBanner.vue:24-29` (título em `:27`) | os 9 |
| D20 | `OperatorOrderDetail` (+ Contact, Timeline, ProfileLines): Nuxt UI | `OperatorOrderDetail.vue` | pos |
| D21 | BFF: `Set-Cookie` sem `Domain=`/`Secure` quando o host é loopback | `server/utils/operatorCookies.ts:174-193`; `djangoProxy.ts` passa `getRequestURL(event)` | os 9 (efeito só em dev; segurança de sessão num PR de UI) |
| D22 | `OperatorSplitter`, `ColumnPicker`, `OperatorOfficeShell`, `queueColumns.ts` | vários | só Gestor/kit (sem efeito nos outros) |
| D23 | `useSuiteChrome.ts`/`presentation/suiteChrome.ts`: campos e funções novas (`respondByIso`, `urgentAlerts`...) | `useSuiteChrome.ts:40-48` | aditivo, sem efeito |

D1, D2 e D4 são regressões que se corrigem para todos. D3, D5 a D15 são as que pedem opt-in (o Gestor fica com o novo, os outros com o antigo, até migrar). D21 pede PR próprio.

## E. Sequência da ONDA 0 em PRs pequenos (seriais, um por vez no kit)

Regra de todos: base no WIP de F1 desta worktree depois de publicado; um PR por vez tocando `surfaces/operator-kit`; cada um roda o vitest do kit **e** o dos apps que ele toca (a CI do #1519 mostrou que o kit verde não prova nada); retrato só na sessão com o Chromium da CI.

| PR | O que muda | Toca / afeta | Trava nova | Risco |
|---|---|---|---|---|
| **0.0** F1 (o WIP de agora) | devolve `min-h-control` opt-in no `FilterBar touch` e no `UiFilterChip`, o `pointer: coarse` 48 px, `data-state` no `OperatorManagerAuth`, `--primary-ink` | kit; pos, kds, prod, mkt, purch, bi | inverter `UiToolbarPrimitives.test.ts:36`; `catalog.guardrails.test.ts:119-127` olhando o arquivo certo | baixo; é volta ao `main` |
| **0.1** Guard de slot | teste que compila cada consumidor de peça do kit e compara `<template #x>` com `<slot name>` | só testes | o próprio guard | nenhum; pega o próximo `#below` |
| **0.2** Marcador de opt-in | `app.config` do app com `operatorKit: { canon: boolean, toaster, search }` lido por um composable `useOperatorKitMode()`; o kit põe `data-operator-canon` (ou mantém `data-suite="v3"`) no `<html>` via `useHead` para os overlays teletransportados herdarem o `suite:` | kit; os 9 (só um atributo) | guard: todo app declara o modo | baixo; é a fundação dos seguintes |
| **0.3** LiveStatus | 4 tons e texto pt-BR (após o sim do Pablo ao texto) | kit; os 7 | `SuiteChrome.test.ts` e `canonicalPilot` com os 4 tons; vocabulário proíbe "On/Off" | médio: mexe no Gestor, que hoje é "On" |
| **0.4** Período | `OperatorPeriodPicker` volta a `UiDateRangeField`/`UiDateField`; `UiDateTimeField` com hora-limite | kit; pos, prod, bi, ord, mkt | `kitOwnership` varre o kit e o `NuxtInput type=date`; `OperatorDatePickers.test` volta ao componente | médio: Safari/Firefox do popover dentro do popover (não testado) |
| **0.5** Toast | `operatorToast` no kit com `description`/`action`, plugin opt-in por `toaster: "nuxt-ui"`; o Gestor tira o shim local; `OperatorUrgentAlert` usa o shim | kit; ord (troca); os outros não mudam | teste do shim nos dois destinos e com as 5 chamadas de 2 args | baixo |
| **0.6** Aviso urgente montável | `OperatorUrgentAlert` sai do `OperatorSuiteShell` para uma peça que o app monta (ou dentro do `OperatorPwaRuntime`, sob `ClientOnly`) | kit; ord; prod e mkt podem ligar (já registram a fonte) | teste: aviso com prazo abre o modal e lembra com Sonner e com Nuxt UI | médio: interrompe tela; decisão de quem liga é do dono |
| **0.7** Cabeçalho opt-in | `OperatorPageHeader` com `#phone-actions` em `md:hidden` e `#actions` rolável no celular quando `canon` é falso; `#subtitle` embaixo idem | kit; os 7 | guard 0.1 + teste dos dois modos | médio: o arquivo é o mais usado (29 consumidores) |
| **0.8** Busca opt-in | `OperatorSuiteSearch mode="inline"` (padrão até migrar) com `NuxtInput` + `NuxtPopover` + `NuxtCommandPalette`; `dialog` para o Gestor | kit; os 8 | teste "digitar filtra sem abrir modal" | médio |
| **0.9** Barra do celular e Avisos no rail | `OperatorSectionBar` e `OperatorInbox placement="rail"` voltam ao desenho rotulado quando `canon` é falso | kit; os 7 | matriz visual do rail de um app não migrado (PDV) | médio |
| **0.10** Rail canônico opt-in | `OperatorSuiteNavigation` (`NuxtNavigationMenu vertical collapsed` com rótulo e chip pelo tema); o `OperatorSuiteShell` passa a usá-lo | kit; ord | teste montado do rail (rótulo visível, chip, `aria-current`) | médio: tema global do `navigationMenu` vertical recolhido (hoje sem outro consumidor) |
| **0.11** Hydration | só depois da medição com `__VUE_PROD_HYDRATION_MISMATCH_DETAILS__`; `railShown` fora de `ClientOnly` no hub; hora com fuso da loja | kit; hub, ord, pos | e2e que reprova "Hydration" no console | baixo, se medido antes |
| **0.12** Faxina | apagar `OperatorAppBar`, `RailToggle`, `OperatorRail`, `RailItem`, `OperatorCapacityStatus`, `QueueColumnStrip`, `QueueColumnResizeHandle`, `UiSearchInput` e os testes deles | kit | nenhuma | nenhum (0 consumidores, verificado) |
| **0.13** BFF | D21 em PR próprio, com nome e teste | kit `server/` | `djangoProxy.test.ts` já cobre | baixo, mas é sessão |

Dependências: 0.0 → 0.1 → 0.2; 0.3 e 0.4 independem de 0.2; 0.5 → 0.6; 0.7, 0.8, 0.9 dependem de 0.2; 0.10 depois de 0.5 e 0.9. Fora da ordem e a qualquer momento: 0.12 e 0.13.

## O que não foi feito

- Nada rodado: nem vitest, nem build, nem navegador. As causas de hydration são leitura, com uma recomendação de medição.
- O repasse de `aria-label` pelos itens do `NuxtTabs` 4.11.3 e a fusão `hidden`/`block` do compound do `NavigationMenu` não foram verificados.
- A contagem por regex não pega `<component :is>`.
- O WIP não commitado desta worktree foi listado, não auditado.
