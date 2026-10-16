> Anexo do [WP-OPERADOR-NUXTUI-ONDAS](../WP-OPERADOR-NUXTUI-ONDAS.md). Leitura de código em 08/10/2026 sobre `e79ed522d` (pilha do Gestor #1528 + #1521), sem build nem navegador. Vale como mapa de arquivo:linha; o que foi visto em tela está no corpo do plano e nos PRs.

# Onda 0: inventário do PDV (`surfaces/pos-nuxt`) para a migração ao cânone Nuxt UI

Auditoria de LEITURA. Worktree `operador-nuxt-ui-migracao-16676a`, branch
`claude/operador-nuxtui-onda0-base`, HEAD `e79ed522d` (pilha do Gestor #1528 + #1521).
Nada foi editado, buildado ou testado. Todo `arquivo:linha` é relativo a
`surfaces/pos-nuxt/` salvo quando diz `operator-kit/` ou `docs/`.

Fonte do laudo lida: `docs/plans/WP-GESTOR-CANON-LAUDO.md` NÃO existe nesta worktree;
foi lido do commit `2ef7e958b` (seções P0, P1, Plano de fechamento, Anexo D).

## 0. Números de cabeça

| Medida | Valor |
|---|---|
| Páginas (`app/pages/**`) | 13, mais 4 rotas antigas em 301 (`nuxt.config.ts:83-88`) |
| Componentes locais (`app/components/**`) | 55 (`Pos*`), 2 órfãos (`PosPinPad`, `PosReceiptSaveOffer`) |
| Disparos de gesto no DOM (`@click`, `@keydown`, `@pointer*`, `@touch*`, `@submit`, drag/drop, `@change`) | 387 (381 vivos; 6 nos 2 órfãos) |
| Disparos via evento de componente (emits de `Pos*`/`Operator*`, `@update:open` etc.) | 306 |
| Ouvintes globais de teclado | 8 no app (mais o scanner de crachá/ficha) |
| Diálogos/folhas/popovers ui-thing (`UiDialog`/`UiSheet`/`UiPopover`) | 41 instâncias |
| Diálogos do kit montados | 6 `OperatorManagerAuth`, 1 `OperatorReasonDialog`, 1 `OperatorIdentify` embutido, mais os do shell |
| Tags `<Ui*>` no app | 474 (`UiButton` 187, `UiInput` 39, família `UiDialog*` 151) |
| Tags `Nuxt*` de Nuxt UI no app | 0 (só `NuxtLink`, `NuxtPage`, `NuxtRouteAnnouncer`) |
| `<button>` cru | 156 (146 com `@click`); teto do ledger = 157 (`docs/reference/operator-component-ledger.json`, app `pos`) |
| `:ui=` por instância | 0 |
| Campo nativo de data/hora no app | 0 (mas herda `type="date"` do kit pelo `OperatorPeriodPicker`) |
| Arbitrários Tailwind `[...]` | cerca de 100 ocorrências em 35 arquivos |
| Spinner à mão | 38 linhas em 18 arquivos (`line-md:loading-loop` 4, `lucide:loader-circle`/`animate-spin` 34) |
| Toast próprio (`vue-sonner`) | 21 arquivos importam `toast`, 102 chamadas; `<OperatorSonner>` no shell |
| Travessão visível | 3 (placeholder de ausência a string de um travessão (U+2014)) |
| Testes | 48 unit + 36 componente + 30 composable + 5 página + 3 e2e + 2 visual + 1 live |
| Mock visual | sim, parcial: só `/preorders` e `/preorders/NB-1042` |

---

## 1. Telas

O shell é decidido em `app/app.vue:29-31` pelo NOME da rota: `display` sobe no
`PosCustomerDisplayShell` (kiosk do cliente, sem identificação); o resto sobe no
`PosOperatorShell` (`components/PosOperatorShell.vue:91-132`), que monta, nesta ordem:
`OfflineBanner` (:94), `OperatorLock` (:97, PIN/crachá), `OperatorSessionUnavailable`
(:102), `OperatorLogin mode="page" large-fields` (:109), `OperatorStationSetup` (:122),
`NuxtPage` (:129) e `OperatorSonner` (:131). `OperatorPwaRuntime` em `app.vue:31`.

**Nenhuma página do PDV usa `OperatorOperationalShell`, `OperatorOfficeShell`,
`OperatorSuiteShell` nem `OperatorPage`.** Cada página monta à mão a moldura
`<main class="flex min-h-dvh ... md:flex-row">` + `PosFunctionRail` (que embrulha o
`OperatorSuiteRail` do kit no desktop e o `OperatorSectionBar` no celular) + cabeçalho.
O cabeçalho é `OperatorPageHeader` em 4 lugares e `<header>` feito à mão em 3.

| Rota | Arquivo (linhas) | O que mostra | Moldura e cabeçalho |
|---|---|---|---|
| `/` | `pages/index.vue` (1863) | A venda inteira: quadro de comandas (`PosTabBoard` :1539) quando não há comanda aberta; com comanda, grade de produtos (`PosProductGrid` :1587) + comanda (`PosCartPanel` :1615); assistente de encomenda (`PosOrderEntry` :1571); pagamento (`PosPaymentWorkspace` :1419); resultado (`PosSaleResult` :1386); recibo para impressão (`Teleport` :1822); edição de encomenda (`?edit=<ref>`) e refazer (`?redo=<ref>`) | `PosFunctionRail` :1090 e barra :1656; `<header data-pos-context-header>` à mão :1113, com `OperatorSuiteSearch` :1112, `OperatorAppSeal` :1127, `PosTabHeader` :1172, `OperatorLiveStatus` :1244, menu "⋮" em `UiPopover` :1277, `OperatorInbox` :1326 |
| `/display` | `pages/display.vue` (188) | Tela do cliente em segunda janela: ocioso, carrinho, pagamento, resultado. Só consome `BroadcastChannel` (`useCustomerDisplayConsumer`) | `PosCustomerDisplayShell`; `<main role="status" aria-live>` à mão; `definePageMeta({ operatorActivity: false })` :18 |
| `/preorders` | `pages/preorders/index.vue` (791) | Encomendas: semana em grade ou lista, dia, busca "cliente veio buscar", recortes (`UiFilterChip`), `FilterBar`, período (`OperatorPeriodPicker` :345), "Imprimir as que faltam", leitor de código, arrastar para reagendar | `PosPreordersShell` (`OperatorPageHeader title="Encomendas"` em `PosPreordersShell.vue:59`, slots `#search`, `#status`, `#actions`); `MoreBelow` :78 |
| `/preorders/:ref` | `pages/preorders/[ref].vue` (367) | Detalhe da encomenda (`OperatorOrderDetail` :319 contexto "pos") + ações: entregar/receber, reagendar, imprimir ficha, editar, cancelar e refazer, comentar, cancelar | `PosPreordersShell wide` :140 |
| `/session` | `pages/session/index.vue` (1281) | Antessala do caixa: cartões (`PosSessionTile`) para abrir caixa, continuar vendendo, devoluções, estornos, pedidos de troco, contas na casa, sangria/suprimento, abrir gaveta, fechar caixa, fim do dia, relatório; 9 diálogos | moldura à mão + `PosFunctionRail` :550/:675; `OperatorPageHeader title="Sessão de caixa"` :567 com `OperatorLiveStatus` :569 em `#status` e `#actions` |
| `/session/closing` | `pages/session/closing.vue` (825) | Fim do dia em corredor de 3 passos: vitrine (contagem cega), gaveta (por cédula ou total), revisão e selo; episódios de produção | SEM rail; `<header>` à mão :5 com ícone colorido e `OperatorLiveStatus` :243 |
| `/session/report` | `pages/session/report.vue` (187) | Relatório de caixa: Leitura X, Leituras Z, histórico do dia (`PosCashReadingCard`) | SEM rail; `<header>` à mão com botão voltar |
| `/settings/terminal` | `pages/settings/terminal.vue` (90) | Saúde do balcão e periféricos, testar o agente, atualizar | `PosSettingsShell` (`OperatorPageHeader :title` em `PosSettingsShell.vue:39`, slots `#lead`, `#status`, `#actions`, `#below` com `PosSettingsTabs`) |
| `/settings/printers` | `pages/settings/printers.vue` (87) | Largura do rolo e corte por impressora | `PosSettingsShell` |
| `/settings/card-machines` | `pages/settings/card-machines.vue` (93) | Maquininhas que vão com a entrega, ativar, editar (diálogo) | `PosSettingsShell` |
| `/settings/seating` | `pages/settings/seating.vue` (555) | Editor da planta do salão: paleta, planta com arrastar/zoom/pinça, lista, painel da mesa, histórico, desfazer/refazer, salvar | moldura própria + `OperatorPageHeader title="Salão"` :283 com `#below` (:369-371, `PosSettingsTabs`) |
| `/settings/kitchen` | `pages/settings/kitchen.vue` (61) | Estações e envio automático à cozinha | `PosSettingsShell` |
| `/settings/shortcuts` | `pages/settings/shortcuts.vue` (81) | Coleções favoritas e ordem dos chips | `PosSettingsShell` |
| 301 | `nuxt.config.ts:84-87` | `/tickets`, `/preorders/panel` → `/preorders?mode=week&print=pending`; `/preorders/today` → `?mode=day`; `/preorders/week` → `?mode=week` | (kiosk de parede tem bookmark) |

Seções do rail (`presentation/sections.ts:36-83`): Comandas, Encomendas (por permissão
`shop.manage_orders`, sondada), Caixa, Tela do cliente (abre janela), Fim do dia, Ajustes.

---

## 2. Gestos

A tabela COMPLETA, gerada por varredura dos templates (387 disparos de DOM e 306 de
emits), está nos Anexos A e B. Abaixo, o mapa por tela com o endpoint ou composable que
cada gesto chama. Todas as mutações passam por `usePosAction().call` (BFF
`/api/v1/**` do kit) ou `$fetch(apiPath(...))`.

### 2.1 Venda (`/`)

Estado e ações vêm de `usePosSale` (`composables/usePosSale.ts`, 3552 linhas; desestruturado
em `pages/index.vue:160-252`).

| Gesto | Disparo | Chama |
|---|---|---|
| Abrir comanda pelo número (campo F2 do quadro) | `PosTabBoard.vue:98` (form submit), tile `PosTabBoard.vue:185-192` | `openTab` → `POST /api/v1/backstage/pos/tabs/{tab_ref}/open/` (`usePosSale.ts:1603,1648`) |
| Escolher comanda no diálogo | `PosTabPickerDialog` (`index.vue:1736`, form `PosTabPickerDialog.vue:81`) | `openTabFromDialog` |
| Voltar para comandas / à comanda | `index.vue:1134` | `goToTabs` (autosave `POST .../tabs/save/` `usePosSale.ts:2583`) |
| Mostrar a barra (rail recolhido) | `index.vue:1122` | `setRail('compact')` (`useRailState` do kit) |
| Descartar minhas alterações (conflito) | `index.vue:1146` | `reloadConflictingTab` |
| Modo Balcão/Encomenda | `PosTabHeader.vue:205`; menu ⋮ `index.vue:1299` | `requestSalesMode` → diálogo `index.vue:1706` "Converter para balcão" (:1714 `convertToCounter`) |
| Mesa da comanda (escolher/tirar) | `PosTabHeader.vue:232`, `:240` | `renameTab(ref, spot)` → `POST .../tabs/rename/` (`usePosSale.ts:3286`) |
| Renomear comanda | `PosTabHeader.vue:264` | `renameTab` |
| Cliente (F6) | `PosTabHeader.vue:308` | abre `PosCustomerModal` (`PosTabHeader.vue:381`) |
| Recebimento (F7) | `PosTabHeader.vue:339`; menu ⋮ `index.vue:1304` | `openFulfillmentHere` → `PosFulfillmentModal` (`index.vue:1662`) |
| Quando (F8) | `PosTabHeader.vue:365`; menu ⋮ `index.vue:1308` | `openScheduleHere` → `PosScheduleModal` (`index.vue:1689`) → `GET /pos/schedule/` (`usePosSale.ts:828`) |
| Últimas vendas | `index.vue:1257`, `:1312`, `:1342` | `PosRecentSales` (folha `UiSheet`, `index.vue:1831`) |
| Liberar comanda | `index.vue:1269`, `:1316` | `tabHeaderRef.askRelease()` → diálogo `PosTabHeader.vue:415` → `clearCurrentTab` → `POST .../tabs/{session_key}/clear/` (`usePosSale.ts:3097`) |
| Liberar tentativa de fechamento incerto | `index.vue:1358` → diálogo `:1719` com `UiSwitch` :1726 → `:1731` | `acknowledgeUncertainClose` |
| Buscar produto (digitar letra, F3, `/`) | global `index.vue:958-963`; `PosSearchField` em `PosProductGrid.vue:199` | filtro local |
| Ler código pela câmera | `PosProductGrid.vue:216` | `PosCodeScanner` (`@zxing/browser`, `getUserMedia`, `navigator.vibrate`) |
| Densidade da grade | `PosProductGrid.vue:233` | `localStorage` |
| Coleções (Favoritos, Tudo, cada coleção) | `PosProductGrid.vue:280`, `:290`, `:302` | filtro local |
| Ocultar indisponíveis | `PosProductGrid.vue:321` | `localStorage` |
| Abrir comanda casada pela busca / buscar cliente pela busca | `PosProductGrid.vue:250`, `:262` | `openTab`, `searchCustomers` |
| Tocar produto | `PosProductTile.vue` (1 click), grupo `PosProductGroupTile.vue` (abre `UiDialog` :80) | `addProduct`; pesado → `PosWeighedEntryDialog` (`index.vue:1790`); com opções → `PosProductOptionsDialog` (`index.vue:1798`) |
| Linha: selecionar, editar, +, −, remover, observação, desconto, numérico, Pronto | `PosCartPanel.vue:1188-1581` (ver Anexo A) | `setQty`, `setLineNotes` (diálogo :1709), `setLineDiscount`, confirmação :1741 |
| Seleção múltipla (Alt S) e ações do lote | `PosCartPanel.vue:1018`, `:1089-1148` | transferir (`$emit('move')`), desconto, remover, enviar só as marcadas, cancelar envio |
| Enviar à cozinha (F9) | `PosCartPanel.vue:968`, `:1038`, `:1137` | `fireTab` → `POST .../tabs/fire/` (`usePosSale.ts:3219`) |
| Cancelar envio | `PosCartPanel.vue:1148`, `:1376`, `:1483` | `unfireTab` → `POST .../tabs/unfire/` (`:3239`) |
| Envio automático (ver/ajustar) | `PosCartPanel.vue:1059` | `$emit('autoFireSettings')` → `/settings/kitchen` |
| Na cozinha (ficha impressa) | `PosKitchenTicketDialog` (`PosCartPanel.vue:1778`) | `POST /api/v1/backstage/kds/printed-tickets/{pk}/done/` |
| Transferir linhas (F10) | `PosCartPanel.vue:1103`; `PosMoveLinesDialog` (`index.vue:1804`) | `submitMove` → `POST .../tabs/move-lines/` (`:3168`) |
| Folha da comanda (tablet/celular): abrir, recolher, scrim | `PosCartPanel.vue:924` (`UiScrim`), `:931`, `:941`, `:1072` | estado local |
| Pagar direto da folha (PIX, Maquininha, Outras formas) | `PosCartPanel.vue:1655`, `:1666`, `:1680` | `payOnSheet` (`index.vue:660`) |
| Ir ao pagamento (F4) | `PosCartPanel.vue:979`, `:991`, `:1696` | `prepareCheckout` → `POST .../sale/review/` (`usePosSale.ts:2694`) |
| Pagamento: forma (letras R P C D L), numérico, vírgula, apagar, Exato (=), Limpar, notas rápidas, editar linha | `PosPaymentWorkspace.vue:1429-1663` | `addTender`, `tenderDigit`, `tenderComma`, `tenderBackspace`, `tenderExact`, `tenderClear`, `tenderAdd`, `selectTender` (locais) |
| Desconto da venda (F9 no pagamento) | `PosPaymentWorkspace.vue:1321` → `UiDialog` :2179 | `OperatorManagerAuth` :2227 quando pede gerente |
| Dividir conta (F10; teclas 1 a 6) | `PosPaymentWorkspace.vue:1354` → `UiDialog` :2126 | `setSplitCount` |
| Cobrança (agora / na entrega) | `PosPaymentWorkspace.vue:1395` | `update:paymentCollection` |
| Passe na maquininha | `UiDialog` `PosPaymentWorkspace.vue:2085` | confirmação de maquininha |
| CPF na nota (F), Nota impressa (I), por e-mail (M) | `UiSwitch` `PosPaymentWorkspace.vue:1867`, `:1905`, `:1924` | `applyCustomerPreference` |
| Validar a venda (Enter) | `index.vue:1048-1052`; `PosPaymentWorkspace @submit` `index.vue:1504` | `submitSale` → `POST .../sale/close/` (`usePosSale.ts:2803`), sob trava de fechamento incerto |
| Resultado: Nova venda (F2/Enter), imprimir recibo, DANFE, reenviar aviso, cancelar contagem automática | `PosSaleResult.vue` (6 clicks; `pointerdown.capture` :115) | `startNextSale`; `printReceipt` (`index.vue:464`, `receipt-escpos` + agente); `printDanfe` (`danfe-escpos`); `sendPaymentNotice` → `POST /pos/orders/{ref}/send-payment-notice/` |
| PIX aguardando | poll `usePosSale.ts:461-476` | `GET /pos/payment/{ref}/status/` a cada ciclo |
| Gaveta aberta (trava) | `PosDrawerLockDialog` (`index.vue:1757`) + `OperatorManagerAuth` :1764 | `useDrawerLock`: `drawer-blind`, `drawer-unlock-attempt`, `drawer-unlock`, `drawer-block` (`useDrawerLock.ts:179-297`), poll do agente 400 ms |
| Dinheiro a levar à gaveta | `PosDrawerPulseCard` (`index.vue:1369`, `:1403`) | `POST /pos/cash/drawer-open/`, `GET /pos/cash/drawer-pulse/{ref}/` (`useDrawerOpening.ts:83,103`) |
| Cancelar venda recente | `PosCancelSaleDialog` (`index.vue:1776`, `PosRecentSales.vue:523`) com `OperatorIdentify` embutido (`PosCancelSaleDialog.vue:79`) | `POST /pos/sale/recent/cancel/` |
| Editar encomenda: Salvar (F4), Descartar | `index.vue:1167`; `PosOrderEditReview` :1834; `OperatorManagerAuth` :1849 | `usePosOrderEdit`: `GET .../edit-session/`, `POST /orders/{ref}/edit/preview/`, `POST /orders/{ref}/edit/` |
| Cliente (modal unificado) | `PosCustomerModal.vue` (21 clicks, 3 painéis `role="alertdialog"` inline :479, :495, :528) | `lookup`, `resolve`, `merge`, `contact/release`, `search` (`usePosSale.ts:1828-2449`), `PATCH /pos/customer/{ref}/profile/` (`PosCustomerModal.vue:114`) |
| Recebimento e endereço | `PosFulfillmentModal` + `PosAddressAutocomplete` | Google Places (`usePosGoogleMaps`), ViaCEP (`PosAddressAutocomplete.vue:142`) |
| Nova encomenda (assistente) | `PosOrderEntry` (`index.vue:1571`, 8 clicks) | `completeOrderSetup`, `useNextFocus` |
| Tela do cliente | rail "Tela do cliente" | `useCustomerDisplayWindow().open()`; publica por `PosDisplayPublisher` (`index.vue:1861`) |

Últimas vendas (`PosRecentSales.vue`, `UiSheet` :346, poll 5 s enquanto aberta :94): listar
(`GET /pos/recent-sales/` :71), reimprimir DANFE (:104), recibo (:142), reenviar NFC-e por
e-mail (:171), reenviar aviso de pagamento (:189), reprocessar fiscal (`/orders/{ref}/requeue-fiscal/` :207),
emitir fiscal (:242), cancelar com gerente (`OperatorManagerAuth` :536, endpoint :297).

### 2.2 Encomendas (`/preorders`)

| Gesto | Disparo | Chama |
|---|---|---|
| Grade ou lista | `UiIconButton` `preorders/index.vue:368` | `localStorage` |
| Imprimir as que faltam | `index.vue:378` | `usePosOrderTickets` → `POST /orders/tickets/escpos/` + agente |
| Buscar (`/` ou qualquer letra fora de campo; Enter abre a única) | `PosSearchField` :398/:406; global :187 | `GET /pos/preorders/search/` |
| Chips do celular | `<button>` :440 | filtro |
| Incluir concluídas | `UiSwitch` :410; botão :525 | refaz busca |
| Nova encomenda | :423 | `navigateTo(NEW_ORDER_ROUTE)` (venda com assistente) |
| Período (Dia/Semana/presets/Personalizado) | `OperatorPeriodPicker` :345 (`max-md:hidden`) | query da rota → `GET /pos/preorders/` |
| Recortes de todo dia | `UiFilterChip` `PosPreorderFilters.vue:65` | query `pay`, `print`, `kind` |
| Filtrar (FilterBar do kit, `touch`) | `PosPreorderFilters.vue:79` | query |
| "Mostrar só essas" (a conferir) | `PosPreorderFilters.vue` UiButton | query |
| Abrir o dia (coluna da semana) | `<button>` :714 | modo dia |
| Arrastar encomenda para outro dia | `dragstart` :735, `dragover`/`dragleave`/`drop` :697-699 | `usePosPreorderMove` (`GET /pos/preorders/{ref}/` + reagendar), confirmação `useConfirm` |
| Mover pelo menu (alternativa ao arrastar) | `PosPreorderMoveMenu` (`UiPopover` :35) :500/:662/:739 | idem |
| Ler código da encomenda | `<button>` :769 | `PosCodeScanner` :775 |
| Reagendar | `PosPreorderRescheduleDialog` :779 | `GET /pos/schedule/`, `POST /orders/{ref}/reschedule/` |
| Tentar de novo (erro) | :474, :629 | `refresh` |
| Abrir encomenda | `NuxtLink` `PosPreorderRow.vue:73` | rota `/preorders/:ref?back=` |

### 2.3 Detalhe da encomenda (`/preorders/:ref`)

| Gesto | Disparo | Chama (`usePosPreorderActions`) |
|---|---|---|
| Voltar | `[ref].vue:143` | `goBack` (respeita `?back=`) |
| Entregar / Receber e entregar | :217 → `PosPreorderHandOverDialog` :329 (`UiRadioGroup`, valor `inputmode=decimal`) | `POST /pos/preorders/{ref}/hand-over/` (`usePosPreorderActions.ts:66`) |
| Reagendar | :240 → `PosPreorderRescheduleDialog` :336 | `POST /orders/{ref}/reschedule/` (:160) |
| Imprimir ficha | :252 | `POST /orders/{ref}/ticket-escpos/` (`usePosOrderTickets.ts:99`) + agente |
| Editar encomenda | :265 | navega para `/?edit=<ref>` |
| Cancelar e refazer | :276 | cancelar + `POST /pos/preorders/{ref}/redo-tab/` (:142) |
| Comentar no histórico | :298, `OperatorOrderDetail @comment` :325 | `POST /orders/{ref}/comment/` (:186) |
| Cancelar encomenda | :311 → `PosPreorderCancelDialog` (`OperatorReasonDialog`) :345 | `POST /orders/{ref}/cancel/` (:103), `OperatorManagerAuth` :353 |

### 2.4 Caixa (`/session`, `/session/closing`, `/session/report`)

`/session` (`pages/session/index.vue`): `selectTile` (:170-183) despacha cada cartão.
Diálogos: Abrir caixa :684, Devoluções em dinheiro :745, Estornos na maquininha :780,
Pedidos de troco :815, Contas na casa :877, Pedido de troco :956, Movimento :1053,
Abrir gaveta :1138, Fechar caixa :1192; `OperatorManagerAuth` :1270 (PIN do gerente por
cima do diálogo aberto).

| Gesto | Disparo | Chama (`usePosCashSession`) |
|---|---|---|
| Abrir caixa (Enter no valor; "Está certo"; contar por cédulas) | :706, :719, :724, :735; `PosDenominationCounter` :729 | `POST /pos/cash/open/` (:140) |
| Devolver em dinheiro | :766 | `POST /pos/cash/refund/{ref}/` (:374) |
| Estornei na maquininha | :801 | `POST /pos/card-machine-refund/{ref}/` (:401) |
| Atender / cancelar pedido de troco | :839, :847, :855, :863 | `.../change-request/{ref}/serve/` (:345), `.../cancel/` (:428) |
| Receber acerto de conta | :942, :917, :931, :932 | `POST /pos/accounts/{ref}/settle/` (:415) |
| Pedir troco (cédulas/moedas, observação) | :1020, :982, :1031, :1036 | `POST /pos/cash/change-request/` (:323) |
| Sangria / suprimento / ajuste (tipo, motivo, valor) | :1073, :1111, :1129 | `POST /pos/cash/movement/` (:173); comprovante `.../entry/{id}/receipt/` (:206) |
| Abrir gaveta (motivos, testar) | :1156, :1162, :1163, :1173 | `POST /pos/cash/drawer-open/` (:294) + agente `/kick` |
| Fechar caixa (contar, conferir, fechar) | :1226, :1249, :1260, :1262 | `POST /pos/cash/close/` (:149) |
| Fim do dia / Relatório | cartões | rotas |

`/session/closing`: passos vitrine (Enter avança entre sobras `:639`), gaveta (Por cédula
:361, Só o total :368, Confirmar :401/:410), episódios de produção (:766, :775 →
`POST /closing/episodes/{id}/`), Fechar o dia (:799, :810 → `POST /closing/`). 21 disparos.

`/session/report`: voltar (:50, :81, :91), atualizar (:64 → `GET /pos/cash/report/`).

### 2.5 Ajustes

| Tela | Gestos | Chama |
|---|---|---|
| Terminal | Testar o agente (:72), Atualizar a tela (:76) | `useAgentHealth` (agente `/health`, sonda a cada 60 s), `refreshPos` |
| Impressoras | largura do rolo (:62), corte (:76), Gravar (:82) | `PATCH /pos/settings/` (`usePosSettings.ts:23`) |
| Maquininhas | Nova (:35), editar (:54), ativa (`UiSwitch` :60), form (:76), Cancelar (:86) | `usePosSettings` |
| Envio à cozinha | envio automático (`UiSwitch` :49) | `usePosSettings` |
| Atalhos de venda | subir/descer/tirar (:56-58), pôr (:72), Gravar (:38) | `usePosSettings` |
| Salão | desfazer/refazer (:301/:312 e Ctrl Z / Ctrl Shift Z / Ctrl Y), zoom ± (:319/:323), grade (:333), menu (:338: histórico :355, recarregar :362), arrastar mesa da paleta (`PosSeatingPalette.vue:79` pointerdown + `seating.vue:129-148` pointermove/up/cancel na janela), arrastar mesa e peça na planta (`PosSeatingPlan.vue:227-230`, `:284-287`), pinça e rolagem (`PosSeatingPlan.vue:189-192` touch*), setas movem (Shift = 1 px), Delete remove, Esc solta, Ctrl S salva, Descartar (:516), Salvar (:523) | `POST /pos/seating/` (`usePosSeating.ts:218`), `useConfirm` |

### 2.6 Gestos que não são toque

- Scanner de ficha da cozinha por teclado (leitor HID) em captura: `useKitchenTicketScanner.ts:176` → `POST /kds/printed-tickets/scan/`, com som (`useAlertSound`).
- Auto-lock por inatividade (`usePosAutoLock`, checa a cada 5 s, segura durante o pagamento via `useState("pos-payment-hold")`, `PosOperatorShell.vue:64-70`).
- Gaveta esquecida aberta (`useDrawerIdleWatch`, 60 s → `POST /pos/cash/drawer-left-open/`).
- Recuperação de fechamento incerto entre abas (`window` `storage`, `index.vue:1079`).
- Contagem regressiva do resultado (`PosSaleResult.vue:95`), cancelada por qualquer toque (`pointerdown.capture` :115).
- Não há deslizar (swipe) nem puxar para atualizar no PDV (grep sem resultado).

---

## 3. Teclado e tempo real

### 3.1 Atalhos

O PDV NÃO usa `useOperatorShortcutMap`. Usa listeners próprios e entrega o dicionário à
ajuda do kit por `provideOperatorShortcuts(POS_SHORTCUT_GROUPS, ...)` (`index.vue:820`;
dicionário em `presentation/shortcuts.ts`). A ajuda (`OperatorShortcutsHelp`) é montada
pelo `OperatorSuiteRail` do kit (`operator-kit/app/components/OperatorSuiteRail.vue:298`)
e aberta por "?" (`index.vue:888-890`, `:1058-1060`) via `useOperatorShortcuts().open`.

| Onde | Teclas | Arquivo:linha |
|---|---|---|
| Venda, global | F2 (comandas / nova venda no resultado), F3 e `/` (busca), F4 (pagamento / revisar / salvar edição), F6 (cliente), F7 (recebimento), F8 (quando), F9 (cozinha; desconto no pagamento), F10 (transferir; dividir no pagamento), Esc (sai do campo, depois do pagamento), Enter (valida; nova venda no resultado), `?` (ajuda), letra solta (vai à busca de produto) | `pages/index.vue:858-1068`, listener :1080 |
| Pagamento | 0-9, `,`/`.`, Backspace, `=` (exato), R P C D L (formas), F (CPF), I/M (nota impressa/e-mail) | `index.vue:898-943`; `PosPaymentWorkspace` `pressMethodKey`/`pressReceiptKey`/`toggleCpfOnInvoice` |
| Dividir conta | 2-6, 1 | `PosPaymentWorkspace.vue:2168` |
| Comanda | 0-9 e Backspace (linha ativa), Esc (fecha editor), Delete (remover com confirmação), ↑ ↓ | `PosCartPanel.vue:690-735`, listener :744 |
| Lista de itens | Alt S (entra na seleção), ↑ ↓, Espaço, Enter, → ←, + −, Delete, Esc | `PosCartPanel.vue:793-807` (listener :807), `navigateItems` :809 |
| Gaveta aberta | Esc capturado (não fecha se o PIN do gerente está aberto) | `PosDrawerLockDialog.vue:41-49` |
| Encomendas | letra solta foca a busca; Enter abre a única | `preorders/index.vue:187-192`, `:406` |
| Salão | Ctrl/Cmd S, Ctrl Z, Ctrl Shift Z, Ctrl Y, Esc, Delete, setas (Shift = fino) | `settings/seating.vue:221-261` |
| Fim do dia | Enter avança entre sobras | `session/closing.vue:639` |
| Caixa | Enter envia (abrir, acerto, troco, gaveta) | `session/index.vue:706, 917, 982, 1031, 1162` |
| PIN (órfão) | 0-9, Backspace, Enter | `PosPinPad.vue:39-53` |
| Leitor de ficha | sequência rápida de teclas (captura) | `useKitchenTicketScanner.ts:142, 176` |

**Trava que todos esses listeners compartilham:** `utils/keyboardGuard.ts:16`
`globalKeysBlocked()` pausa os atalhos quando existe `[data-operator-lock]`,
`[role="dialog"][data-state="open"]` ou `[role="alertdialog"][data-state="open"]`. Toda
troca de diálogo precisa manter `role` e `data-state="open"` no conteúdo, senão o
numérico do pagamento passa a digitar por baixo do modal. O mesmo vale para
`[data-drawer-manager-auth][data-state="open"]` (`PosDrawerLockDialog.vue:43`), que o kit
hoje põe no `content` do `NuxtModal` (`operator-kit/app/components/OperatorManagerAuth.vue:103-107`).

`kbd` some em toque: `assets/css/tailwind.css:17-21` (`pointer: coarse` + `hover: none`).
`OperatorKbd` aparece 23 vezes (variante `inverse` em `PosSaleResult.vue:233`,
`PosCartPanel.vue:1700`, `PosPaymentWorkspace.vue:1973`).

### 3.2 SSE e polls

| Canal | Quem | Arquivo:linha | Fallback |
|---|---|---|---|
| `/sse/cash` (evento `backstage-cash-update`) e `/sse/tabs` (`backstage-tabs-update`) | `PosOperatorShell`, refaz `usePosTerminal` | `usePosEvents.ts:16-17`; shell :41; BFF `server/routes/sse/cash.ts`, `tabs.ts` → `/events/cash/`, `/events/tabs/` | poll 60 s só sem stream (`usePosEvents.ts:96-98`), retoma em `visibilitychange` e `online` (:100-101) |
| `/sse/orders` (`backstage-orders-update`) | `usePosPreordersRail` (selo e telas das Encomendas, `refreshNuxtData(PREORDERS_LIVE_KEYS)`) | `usePosPreorders.ts:121-140`, montado por `PosFunctionRail.vue:49`; BFF `server/routes/sse/orders.ts` | poll 120 s |
| Estado ao vivo | `usePosLiveState` / `usePosLiveStatus` → `OperatorLiveStatus` (3 usos) | tons `live`/`calm`/`off` em `presentation/events.ts:30-46` | |
| `BroadcastChannel` (Tela do cliente) | publicador `PosDisplayPublisher`, consumidor `display.vue` | `useCustomerDisplay.ts:18-20` | |
| Polls próprios | PIX (`usePosSale.ts:461`), entrega do aviso de pagamento (:431), Últimas vendas 5 s (`PosRecentSales.vue:94`), gaveta 400 ms (`useDrawerLock.ts:23`), pulso da gaveta 1 s até 50 s (`useDrawerOpening.ts:33-34`), gaveta esquecida 60 s, agente 60 s, auto-lock 5 s | | |

**OperatorLiveStatus herdado:** o kit desenha hoje `tone === "off" ? "Off" : "On"`
(`operator-kit/app/components/OperatorLiveStatus.vue:25,36`). O PDV passa `calm`
("Atualiza a cada 60 s", sem stream) e ele sai verde "On", em inglês. É o P0-5 do laudo,
visível em `index.vue:1244`, `session/index.vue:569`, `session/closing.vue:243`.

---

## 4. Peças do operator-kit que o PDV usa

| Peça | Usos | Onde |
|---|---|---|
| `OperatorPageHeader` | 4 | `PosPreordersShell.vue:59` (`#search`, `#status`, `#actions`), `PosSettingsShell.vue:39` (`#lead`, `#status`, `#actions`, `#below`), `settings/seating.vue:283` (`#below` em :369-371 e outros), `session/index.vue:567` (`#status`, `#actions`) |
| Slots usados do header | `#lead`, `#status`, `#search`, `#actions`, `#below` | NÃO usa `#phone-actions`, `#subtitle`, `#filters`, `#feedback`. `#below` voltou com o #1521 (`operator-kit/app/components/OperatorPageHeader.vue:188`) |
| `OperatorLiveStatus` | 3 | tons `live`, `calm`, `off` (nunca `late`) |
| `OperatorSuiteSearch` | 2 | `variant="hotkey"` em `index.vue:1112` e `PosPreordersShell.vue:63` |
| `OperatorSuiteRail` | 1 (via `PosFunctionRail.vue:74`) | props `print-shortcuts`, `touch-label="none"`, `hub-url`, slot `#foot` com `PosTerminalHealth` |
| `OperatorSectionBar` | 1 (`PosFunctionRail.vue:99`) | slot `#more` com `PosTerminalHealth variant="sheet"` |
| `OperatorInbox` | 1 direto (`index.vue:1326`, `placement="header"` quando o rail está oculto) + o do rail | |
| `OperatorManagerAuth` | 6 | `index.vue:1764`, `:1849`; `preorders/[ref].vue:353`; `session/index.vue:1270`; `PosPaymentWorkspace.vue:2227`; `PosRecentSales.vue:536` |
| `OperatorIdentify` | 1 | `PosCancelSaleDialog.vue:79` |
| `OperatorReasonDialog` | 1 | `PosPreorderCancelDialog.vue:30` |
| `OperatorOrderDetail` | 1 | `preorders/[ref].vue:319` |
| `OperatorPeriodPicker` | 1 | `preorders/index.vue:345` (com `custom`: herda o `NuxtInput type="date"` do kit, P1-1) |
| `OperatorDayPicker` | 1 | `PosSchedulePicker.vue:77` |
| `FilterBar` | 1 | `PosPreorderFilters.vue:79` (`touch`) |
| `UiFilterChip` | 1 (em `v-for`) | `PosPreorderFilters.vue:65` |
| `OperatorKbd` | 23 | `PosCartPanel`, `PosPaymentWorkspace`, `PosTabHeader`, `PosCustomerSearch`, `PosSaleResult`, `PosSearchField`, `PosTabBoard` |
| `OperatorAppSeal` | 1 | `index.vue:1127` |
| `MoreBelow` | 1 | `PosPreordersShell.vue:78` |
| Shell: `OfflineBanner`, `OperatorLock`, `OperatorSessionUnavailable`, `OperatorLogin`, `OperatorStationSetup`, `OperatorSonner`, `OperatorPwaRuntime` | 1 cada | `PosOperatorShell.vue:94-131`, `app.vue:31` |
| `OperatorSonner` / `useSonner` | 1 / 3 chamadas | `PosOperatorShell.vue:131`; `useKitchenTicketScanner.ts:123-129`. O resto do app chama `toast` de `vue-sonner` direto (21 arquivos) |
| `UiNativeSelect` | 4 | `PosMoveLinesDialog.vue:160`, `PosCartPanel.vue:1521`, `PosSeatingSpotPanel.vue:194`, `session/index.vue:922` |
| `UiButton` | 187 | em 40 arquivos; é wrapper de `NuxtButton` no kit (`operator-kit/app/components/UiButton.vue:106`) |
| `UiDate*` / `UiTime*` | 0 | |
| Ui* ui-thing do kit (`operator-kit/app/components/Ui/**`) | `UiInput` 39, `UiDialog*` 151 (33 diálogos), `UiPopover*` 15, `UiSheet*` 10, `UiTextarea` 4, `UiBadge` 4, `UiAlert*` 6, `UiSeparator` 1 | reka-ui por baixo, não Nuxt UI |
| Ui* finos do kit | `UiSwitch` 11 (`NuxtSwitch`), `UiSkeleton` 5 (`NuxtSkeleton`), `UiCheckbox` 1, `UiRadioGroup` 1 (input cru dentro), `UiIconButton` 1 (`<button>` cru), `UiScrim` 1 (`<button>` cru) | |

Composables do kit: `useOperatorLock` (7), `useApiPath` (14), `useCustomerDisplayWindow`
é do app; do kit: `useConnectivity` (2), `useOperatorSession` (2), `useStationSetupOffer`
(1), `useNextFocus` (5: `PosProductOptionsDialog.vue:53`, `PosPaymentWorkspace.vue:748`,
`PosOrderEntry.vue:53`, `PosWeighedEntryDialog.vue:60`), `useConfirm` (2), `useAlertSound`
(2), `useRailState` (2), `useStationLock` (2), `useOperatorShortcuts`/`provideOperatorShortcuts`
(1 cada), `useOperatorWindowTitle`, `useOperatorReloadHold`, `usePwaUpdate`,
`useOperatorAppLink` (2), `useSuiteRailShown` (1). Não usa `useOperatorShortcutMap`,
`useRouteFilters`, `useKioskMode`, `useWakeLock`, `useOrientationLock`, `useMoreBelow`.

---

## 5. Componentes locais

Legenda do destino: **fica** (domínio do PDV), **kit** (outro app precisa da mesma
coisa), **morre** (vira componente oficial Nuxt UI direto), **órfão** (sem montagem).

| Componente | Linhas | Papel | Montado em | Destino |
|---|---|---|---|---|
| PosAddressAutocomplete | 268 | endereço com Places + ViaCEP, `role="listbox"` à mão :247 | `PosFulfillmentModal.vue:182` | kit candidato (Gestor e Storefront têm endereço); por baixo vira `NuxtInputMenu` |
| PosCancelSaleDialog | 95 | cancelar venda com identificação | `PosRecentSales.vue:523`, `index.vue:1776` | fica; casca vira `NuxtModal` |
| PosCartPanel | 1784 | comanda: lista, editor, numérico, lote, folha do tablet | `index.vue:1615` | fica; folha à mão (`UiScrim` :924) vira `NuxtDrawer`; 38 `<button>` |
| PosCashReadingCard | 135 | leitura X/Z com 2 `<table>` | `session/report.vue:96,115` | fica; tabelas viram `NuxtTable` |
| PosCodeScanner | 176 | câmera + zxing | `PosProductGrid.vue:373`, `preorders/index.vue:775` | kit candidato (Compras recebe por código) |
| PosCustomerDisplayShell | 27 | shell do kiosk do cliente | `app.vue:29` | fica |
| PosCustomerModal | 903 | cliente unificado: busca, cadastro, conflitos, preferências | `PosPaymentWorkspace.vue:2046`, `PosTabHeader.vue:381` | fica; 3 `role="alertdialog"` inline viram `NuxtAlert` com ações |
| PosCustomerSearch | 248 | busca com `role="listbox"` :197 | `PosCustomerModal.vue:736` | morre em `NuxtCommandPalette`/`NuxtInputMenu` |
| PosDenominationCounter | 244 | contagem por cédula/moeda, `<input>` cru :172 | `session/index.vue:729,1231`, `closing.vue:376` | fica (pode subir ao kit se o Compras contar caixa); input vira `NuxtInputNumber` |
| PosDisplayPublisher | 38 | publica no BroadcastChannel | `index.vue:1861` | fica |
| PosDrawerLockDialog | 111 | trava da gaveta aberta, `role="alertdialog"` | `index.vue:1757` | fica; `NuxtModal` sem fechar |
| PosDrawerPulseCard | 117 | dinheiro a levar à gaveta | `index.vue:1369,1403` | fica |
| PosFulfillmentModal | 275 | recebimento e entrega | `PosPaymentWorkspace.vue:1984`, `index.vue:1662` | fica |
| PosFunctionRail | 113 | adaptador para `OperatorSuiteRail`/`OperatorSectionBar` | 9 montagens | fica (morre se o shell do kit assumir) |
| PosHourlyShape | 37 | gráfico de barras por hora | `closing.vue:755` | morre se houver gráfico no kit |
| PosKitchenTicketDialog | 116 | ficha impressa da cozinha | `PosCartPanel.vue:1778` | fica |
| PosMoveLinesDialog | 178 | transferir linhas | `index.vue:1804` | fica |
| PosOperatorShell | 133 | shell do operador | `app.vue:30` | substituir pelo shell do kit (`OperatorSuiteShell` ou `OperatorOperationalShell`) |
| PosOrderEditReview | 160 | prévia de edição, `<form>` CPF | `index.vue:1834` | fica |
| PosOrderEntry | 150 | assistente de encomenda | `index.vue:1571` | fica |
| PosPaymentResult | 195 | aviso de pagamento (PIX/link) | `PosSaleResult.vue:214` | fica |
| PosPaymentWorkspace | 2238 | pagamento inteiro | `index.vue:1419` | fica; 13 `<button>`, numérico à mão |
| **PosPinPad** | 110 | teclado de PIN | NENHUM | **órfão**: apagar |
| PosPreorderCancelDialog | 42 | cancelar encomenda | `[ref].vue:345` | fica (casca do `OperatorReasonDialog`) |
| PosPreorderFilters | 109 | recortes + FilterBar | `preorders/index.vue:556` | fica; chips viram `NuxtTabs`/`NuxtButton` |
| PosPreorderHandOverDialog | 115 | entregar/receber | `[ref].vue:329` | fica |
| PosPreorderMoveMenu | 78 | mover para outro dia | 3 montagens | morre em `NuxtDropdownMenu` |
| PosPreorderRescheduleDialog | 147 | reagendar | `preorders/index.vue:779`, `[ref].vue:336` | fica |
| PosPreorderRow | 150 | cartão da encomenda | 4 montagens | fica |
| PosPreordersShell | 84 | moldura das Encomendas | 2 | substituir pelo shell do kit |
| PosProductGrid | 375 | grade de produtos | `index.vue:1587` | fica |
| PosProductGroupTile | 99 | grupo de produtos (abre diálogo) | `PosProductGrid.vue:355` | fica |
| PosProductOptionsDialog | 177 | opções do produto | `index.vue:1798` | fica |
| PosProductTile | 109 | tile do produto | 2 | fica |
| PosReceipt | 66 | recibo impresso, `<table>`, `text-[10-12px]` | `index.vue:1824` | fica (impressão; NÃO migrar para Nuxt UI) |
| **PosReceiptSaveOffer** | 90 | oferta inline de guardar contato | NENHUM; `tests/receiptOfferEntryPoints.test.ts` PROÍBE montá-lo | **órfão**: apagar com o teste de componente |
| PosRecentSales | 545 | últimas vendas | `index.vue:1831` | fica; `UiSheet` vira `NuxtSlideover` |
| PosSaleResult | 324 | venda concluída | `index.vue:1386` | fica |
| PosScheduleModal | 103 | quando | 2 | fica |
| PosSchedulePicker | 146 | dia + faixa | 2 | fica (usa `OperatorDayPicker`) |
| PosSearchField | 58 | campo de busca com `kbd` | 2 | morre em `NuxtInput` com `#trailing` + `NuxtKbd` |
| PosSeatingHistory | 35 | histórico do salão | `seating.vue:539` | fica; `NuxtSlideover` |
| PosSeatingList | 103 | lista de mesas | `seating.vue:388` | fica |
| PosSeatingPalette | 172 | paleta (arrastar), `<input>` cru :123 | 2 | fica |
| PosSeatingPlan | 363 | planta com arrastar/pinça | `seating.vue:442` | fica (canvas de domínio) |
| PosSeatingSpotPanel | 276 | painel da mesa; `role="radiogroup"` à mão :166; 3 `<input>` crus | 2 | fica; radiogroup vira `NuxtRadioGroup`/`NuxtTabs` |
| PosSessionTile | 66 | cartão da antessala | 4 | fica (ou `NuxtPageCard`) |
| PosSettingsShell | 62 | moldura dos Ajustes | 5 | substituir pelo shell do kit |
| PosSettingsTabs | 25 | abas de Ajustes (`NuxtLink` com sombra arbitrária) | 2 | morre em `NuxtTabs`/`NuxtNavigationMenu` |
| PosStoreNetworkNotice | 43 | aviso de rede da loja | `index.vue:1538` | morre em `NuxtAlert` |
| PosTabBoard | 227 | quadro de comandas | `index.vue:1539` | fica |
| PosTabHeader | 436 | barra da comanda (chips F6 F7 F8, mesa, nome) | `index.vue:1172` | fica |
| PosTabPickerDialog | 136 | escolher comanda | `index.vue:1736` | fica |
| PosTerminalHealth | 209 | saúde do terminal no rail (popover) e na folha; medidas `[68px]`, `[22px]` | `PosFunctionRail.vue:90,110` | kit candidato (KDS e Produção têm posto e impressora) |
| PosWeighedEntryDialog | 294 | pesagem; `role="radiogroup"` à mão :174, `<input>` :209 | `index.vue:1790` | fica |

---

## 6. Escapes do cânon

### 6.1 Contagem por categoria

| Cat. | O quê | Contagem | Componente oficial |
|---|---|---|---|
| a | `:ui=` por instância | **0** | n/a |
| b | `<button>` cru | **156** em 34 arquivos (`PosCartPanel` 38, `PosPaymentWorkspace` 13, `seating.vue` 10, `index.vue` 10, `closing.vue` 8, `PosSeatingSpotPanel` 8, `PosProductGrid` 8, `PosTabHeader` 7) | `NuxtButton` |
| b | `<input>` cru | **6** (`PosDenominationCounter.vue:172`, `PosSeatingSpotPanel.vue:184,239,250`, `PosSeatingPalette.vue:123`, `PosWeighedEntryDialog.vue:209`) | `NuxtInput` / `NuxtInputNumber` |
| b | `<select>`/`<textarea>` cru | 0 (há 4 `UiNativeSelect` e 4 `UiTextarea`) | `NuxtSelect` / `NuxtTextarea` |
| b | `<table>` cru | **8** (`PosCashReadingCard.vue:64,89`, `report.vue:157`, `closing.vue:466,516,549,570`, `PosReceipt.vue:40`) | `NuxtTable` (exceto `PosReceipt`, que é papel) |
| b | `<form>` cru | 8 | `NuxtForm` (opcional) |
| b | `role="alertdialog"` inline à mão | **4** vivos (`PosCustomerModal.vue:479,495,528`; `PosDrawerLockDialog.vue:57` é role no `UiDialogContent`) + 1 órfão (`PosReceiptSaveOffer.vue:66`) | `NuxtAlert` com `actions` / `NuxtModal` |
| b | `role="radiogroup"` à mão | 2 (`PosSeatingSpotPanel.vue:166`, `PosWeighedEntryDialog.vue:174`) | `NuxtRadioGroup` ou `NuxtTabs` |
| b | `role="listbox"` à mão | 2 (`PosCustomerSearch.vue:197`, `PosAddressAutocomplete.vue:247`) | `NuxtInputMenu` / `NuxtCommandPalette` |
| b | overlay à mão | 1 (folha da comanda com `UiScrim`, `PosCartPanel.vue:912-924`) | `NuxtDrawer` |
| b | `Teleport` | 1 (`index.vue:1822`, área de impressão; MANTER, é trava de `receiptPrint.test.ts:177`) | n/a |
| b | menu de ação feito com `<button>` dentro de `UiPopover` | 4 (`index.vue:1277-1320`, `settings/seating.vue:338-362`, `PosSeatingSpotPanel.vue:105`, `PosPreorderMoveMenu.vue:35`) | `NuxtDropdownMenu` |
| c | input nativo `type="date|time|datetime-local|month"` | **0** no app; 1 herdado (`OperatorPeriodPicker custom`) | `UiDateRangeField` do kit (F2 do laudo) |
| d | div com cara de card (`rounded-* border ... bg-card/muted/secondary`) | **32** (`closing.vue` 13, `report.vue` 6, `PosDenominationCounter` 3) | `NuxtCard` |
| d | span com cara de badge | **7+** (`PosCustomerModal.vue:793,807,810,813`, `closing.vue:458,541,730`, `PosCartPanel.vue:972`) | `NuxtBadge` |
| d | barra de aviso com classes (`rounded-md border border-warning/30 bg-warning/10 px-3 py-2`) | ver `PosPreorderFilters.vue:93` e similares | `NuxtAlert` |
| e | arbitrários `[...]` | **cerca de 100** em 35 arquivos (`session/index.vue` 12, `PosSeatingPlan` 11, `PosCartPanel` 11, `seating.vue` 9, `PosTerminalHealth` 9, `PosReceipt` 7) | tema / props |
| f | `Ui*` ui-thing (reka direto, fora do Nuxt UI) | `UiDialog*` 151 tags em 33 diálogos, `UiInput` 39, `UiPopover*` 15, `UiSheet*` 10, `UiTextarea` 4, `UiBadge` 4, `UiAlert*` 6, `UiSeparator` 1 | `NuxtModal`, `NuxtInput`, `NuxtPopover`, `NuxtSlideover`, `NuxtTextarea`, `NuxtBadge`, `NuxtAlert`, `NuxtSeparator` |
| f | `Ui*` paralelos finos do kit | `UiButton` 187, `UiSwitch` 11, `UiSkeleton` 5, `UiNativeSelect` 4, `UiIconButton` 1, `UiScrim` 1, `UiRadioGroup` 1, `UiCheckbox` 1, `UiFilterChip` 1 | `NuxtButton`, `NuxtSwitch`, `NuxtSkeleton`, `NuxtSelect`, `NuxtButton icon`, `NuxtDrawer`, `NuxtRadioGroup`, `NuxtCheckbox`, `NuxtTabs`/`NuxtButton` |
| f | spinner à mão | **38** linhas em 18 arquivos (`line-md:loading-loop` 4: `PosMoveLinesDialog.vue:133`, `PosOrderEditReview.vue:64`, `index.vue:1564`, `closing.vue:821`) | prop `loading` do `NuxtButton`, `NuxtSkeleton` |
| f | toast próprio | `vue-sonner` `toast` em 21 arquivos (102 chamadas) + `OperatorSonner` | `useToast` + `NuxtApp`/`NuxtToaster` |
| f | dependências ui-thing no `package.json` | `reka-ui`, `vue-sonner`, `tailwind-variants`, `tailwind-merge`, `motion-v`, `@tailwindcss/forms` (+ `ui-thing.config.ts`) | morrem quando o último `Ui*` sair |
| g | travessão visível | **3**: `PosFulfillmentModal.vue:218` (a string de um travessão (U+2014)), `PosTerminalHealth.vue:78` (`label` cai em U+2014), `presentation/cash.ts:106` (`return` de U+2014) | trocar por texto ("sem taxa", "desconhecido", "sem horário") |

### 6.2 Os 40 mais relevantes

Ordem: primeiro o que mexe em dinheiro, impressão e trava; depois o que se repete.

1. `PosPaymentWorkspace.vue:1453-1491`: numérico do pagamento em `<button>` cru (dígitos, vírgula, apagar, Exato, Limpar). `NuxtButton` em grade; manter alvo de toque e `aria-label`.
2. `PosPaymentWorkspace.vue:1429`: botões das formas de pagamento em `<button>` com motivo de bloqueio no `title`. `NuxtButton` + `NuxtTooltip`.
3. `PosPaymentWorkspace.vue:2085`: "Passe na maquininha" em `UiDialog`. `NuxtModal` (sem fechar por fora).
4. `PosPaymentWorkspace.vue:2126`, `:2179`: Dividir conta e Desconto em `UiDialog` com `max-h-[85vh]`. `NuxtModal`.
5. `PosPaymentWorkspace.vue:1867,1905,1924`: CPF/Nota impressa/E-mail em `UiSwitch` com `OperatorKbd`. `NuxtSwitch` + `NuxtKbd`.
6. `PosCartPanel.vue:912-941`: folha da comanda feita à mão (`max-h-[82dvh]`, `shadow-[...]`, `UiScrim`). `NuxtDrawer`.
7. `PosCartPanel.vue:1547`: numérico da linha em `<button>` com grade `grid-cols-[repeat(3,minmax(0,1fr))_minmax(0,1.6fr)]` (:1538). `NuxtButton`.
8. `PosCartPanel.vue:964,988,1663,1691`: botões primários com `shadow-[0_2px_0_color-mix(...)]` (relevo à mão). Tema (`app.config.ts` button `variants`).
9. `PosCartPanel.vue:1018-1148`: barra de seleção em lote com 7 `<button>`. `NuxtButton`/`NuxtFieldGroup`.
10. `PosCartPanel.vue:1709`, `:1741`: Observação e confirmação em `UiDialog`. `NuxtModal`.
11. `PosCartPanel.vue:1521`: `UiNativeSelect` (motivo do desconto). `NuxtSelect`.
12. `PosDrawerLockDialog.vue:54-87`: `UiDialog` com `role="alertdialog"`, `hide-close`, spinner `animate-spin`. `NuxtModal :dismissible="false"`.
13. `index.vue:1277-1320`: menu ⋮ do contexto feito com `<button class="flex h-11 ... hover:bg-accent">` dentro de `UiPopover`. `NuxtDropdownMenu`.
14. `index.vue:1113`: cabeçalho da venda à mão (`<header class="flex min-h-14 ...">`). `OperatorPageHeader` ou `NuxtDashboardNavbar` do shell.
15. `index.vue:1706`, `:1719`: dois `UiDialog` de confirmação. `useConfirm` do kit / `NuxtModal`.
16. `index.vue:1564`: `line-md:loading-loop` no "quadro indisponível". `NuxtEmpty` + `loading`.
17. `index.vue:1331`: `UiAlert` do fechamento incerto. `NuxtAlert` com `actions`.
18. `PosTabHeader.vue:205-365`: chips F6 F7 F8, mesa e renomear em 7 `<button>`; menu de mesas com `w-[min(22rem,80vw)]` (:217). `NuxtButton` + `NuxtPopover`.
19. `PosTabHeader.vue:415`: "Liberar comanda?" em `UiDialog`. `useConfirm`.
20. `PosCustomerModal.vue:421`: `UiDialogContent` com `max-h-[85vh] w-[calc(100%-2rem)] max-w-[360px]`. `NuxtModal`.
21. `PosCustomerModal.vue:479,495,528`: três painéis `role="alertdialog"` inline com borda `warning`. `NuxtAlert`.
22. `PosCustomerModal.vue:793-813`: 4 spans de selo (pedidos, restrição, aniversário). `NuxtBadge`.
23. `PosCustomerModal.vue:509-725`: 6 ícones com `animate-spin` à mão. `loading` do `NuxtButton`.
24. `PosCustomerSearch.vue:183,197`: spinner e `role="listbox"` à mão. `NuxtInputMenu`/`NuxtCommandPalette`.
25. `PosAddressAutocomplete.vue:242,247,257`: spinner, `role="listbox"`, `pointerenter`. `NuxtInputMenu`.
26. `PosRecentSales.vue:346`: `UiSheet`. `NuxtSlideover`.
27. `PosProductGrid.vue:216-321`: 8 `<button>` (câmera, densidade, coleções, ocultar). `NuxtButton`/`NuxtTabs`.
28. `PosProductTile.vue:46,54` e `PosProductGroupTile.vue:38,45`: `shadow-[4px_4px_0_-1px_var(--card),...]`, `h-[108px]`/`h-[92px]`. Tema ou variante de `NuxtCard`.
29. `PosWeighedEntryDialog.vue:142,167,174,209`: `UiDialog` com `h-[27.5rem]`, radiogroup à mão, `<input>` cru. `NuxtModal`, `NuxtRadioGroup`, `NuxtInputNumber`.
30. `PosDenominationCounter.vue:123,166,172`: grades arbitrárias e `<input>` cru. `NuxtInputNumber`.
31. `session/index.vue:684-1192`: 9 `UiDialog` com `max-h-[85vh]` cada. `NuxtModal`.
32. `session/index.vue:1000-1012`: cédula/moeda em `<button>` com classes de forma. `NuxtButton` (forma é informação: manter `rounded-full` por variante).
33. `session/index.vue:922`: `UiNativeSelect` "Método do acerto". `NuxtSelect`.
34. `session/closing.vue:5`: cabeçalho à mão, sem rail. Shell do kit.
35. `session/closing.vue:361,368`: alternância "Por cédula" / "Só o total" em `<button>`. `NuxtTabs`.
36. `session/closing.vue:466-570` e `report.vue:157`, `PosCashReadingCard.vue:64,89`: 7 `<table>` cruas. `NuxtTable`.
37. `session/closing.vue` (13) e `report.vue` (6): divs de card. `NuxtCard`.
38. `PosTerminalHealth.vue:83-104`: popover com medidas `w-[68px] gap-[3px] rounded-[10px] pt-[7px] leading-[13px] size-[22px] right-[17px] size-[9px]`. `NuxtPopover` + `NuxtChip`.
39. `settings/seating.vue:301-362`, `:516`, `:523`: 10 `<button>` (desfazer, refazer, zoom, grade, menu, descartar, salvar). `NuxtButton`, `NuxtDropdownMenu`.
40. `PosSettingsTabs.vue:13-19`: abas de Ajustes em `NuxtLink` com `shadow-[inset_0_-2px_0_var(--primary)]`. `NuxtTabs` ou `NuxtNavigationMenu` horizontal.

Fora da lista, mas com nome: `PosFulfillmentModal.vue:218` e mais 2 travessões visíveis
(g); `PosReceipt.vue:27-64` `text-[10-12px]` é papel térmico, fica; `preorders/index.vue:216,682`
grades `auto-fill` arbitrárias são layout de semana (motivo plausível, não escrito).

---

## 7. Testes e travas

### 7.1 Já vermelhos por herança do kit (fato de CI do laudo, conferido por leitura)

| Teste | Por quê | Estado por leitura nesta pilha |
|---|---|---|
| `tests/pages/preorders.test.ts:566` (`pickFilter`) | clica `[data-filter-trigger]` e procura `[data-filter-dimension]` com `wrapper.find`; o `FilterBar` do kit agora põe o painel num `NuxtPopover` (`operator-kit/app/components/FilterBar.vue:151-177`), que vai para o `body` | deve continuar falhando: o atributo existe, mas fora da árvore do wrapper |
| `tests/pages/preorders.test.ts:858` | espera `button` com `.tabular-nums` para a contagem; o `UiFilterChip` virou `NuxtButton` + `NuxtBadge` (`operator-kit/app/components/UiFilterChip.vue:11-25`) sem essa classe | deve continuar falhando |
| `tests/pages/sessionIndex.layout.test.ts:301` | espera `data-state="open"` em `[data-drawer-manager-auth]` | o kit agora põe o atributo no `content` do `NuxtModal` (`OperatorManagerAuth.vue:103-107`); pode ter voltado a passar, não dá para afirmar sem rodar |
| `tests/composables/usePosSale.sale.test.ts` | timeout de hook na CI (laudo, anexo D §0) | causa não identificada por leitura |
| `tests/pages/sessionIndex.layout.test.ts:329` | passa por vacuidade (a busca do kit não tem mais `input`) | registrar |

### 7.2 Travas que leem o FONTE e vão quebrar com a troca de componente

| Arquivo | O que exige |
|---|---|
| `tests/v6Conformidade.test.ts:86,91` | `cart` NÃO contém uma string exata de classe; `cart` casa `/Pronto<\/button>/` (vira `NuxtButton` → quebra) |
| `tests/receiptPrint.test.ts:177` | `index.vue` casa `/<Teleport to="body">\s*<div v-if="result" id="pos-print-area">/` |
| `tests/railPreorders.test.ts:78-91` | `PosPreordersShell` contém `<OperatorPageHeader`, não contém `<nav` nem `<NuxtLink ... to="/preorders"`, nem `TONE_CLASS` |
| `tests/railStatusOrder.test.ts:25-55` | lê `PosFunctionRail.vue` (`<PosTerminalHealth`, `variant="suite"`, `@refresh=...`) e o `OperatorSuiteRail.vue` do kit (`<slot name="foot" />`, `data-rail-foot-rule`, `<OperatorInbox v-if="railShown" placement="rail" />`) |
| `tests/customerDisplayAffordance.test.ts:28-40` | toda tela que monta o rail contém `<PosFunctionRail` |
| `tests/orderEditSaleScreen.test.ts:17-60` | strings exatas de `index.vue` (`@prepare="editing ? saveOrderEdit() : prepareCheckout()"`, `<PosOrderEditReview`, regex multilinha) |
| `tests/falhaComSaida.test.ts:188` | `GATILHOS = [/httpErrorMessage\(/, /toast\.error\(\s*"/, /toast\.warning\(\s*"/]`: se o toast virar `useToast().add(...)`, a trava passa a não ler nada (a guarda `:193` só conta arquivos, não gatilhos). Precisa mudar JUNTO |
| `tests/receiptOfferEntryPoints.test.ts:21` | nenhum `.vue` monta `<PosReceiptSaveOffer` (ok se o órfão for apagado) |
| `tests/seatingPresentation.test.ts:163-171`, `tests/drawerOpeningPresentation.test.ts:66`, `tests/orderSetupPresentation.test.ts:75-81`, `tests/pages/sessionOpenReturn.test.ts`, `tests/posIntent.test.ts`, `tests/securityConfig.test.ts` | leem fonte (copy, endpoint, nomes); baixo risco, conferir |

### 7.3 Testes de componente sensíveis ao markup

O harness é `environment: "nuxt"` com `mountSuspended` (`vitest.config.ts`), sem dublês
de Nuxt UI escritos à mão (`tests/support/componentSetup.ts` só mocka `localStorage` e
`navigator`). Bom: a troca para `Nuxt*` roda o componente real. Ruim: teleports e
`data-state` mudam de lugar.

- Consultam `button` cru: 23 arquivos (ex.: `PosCartPanel.test.ts`, `PosPaymentWorkspace*.test.ts` (9), `PosCustomerModal.*`, `PosTabHeader.test.ts`, `PosSaleResult.test.ts`, `PosScheduleModal.test.ts`, `preorders.test.ts`).
- Consultam `input` (`input[inputmode="decimal"]` etc.): 13 arquivos.
- Consultam `role="dialog"`/`[role=...]`: 10 arquivos; `data-state`: 4 (`PosPaymentWorkspace.splitKeys.test.ts:24` procura `[role="dialog"][data-state="open"]` no `body`).
- Consultam `document.body`: 6 arquivos (diálogos teleportados).
- `vi.mock("vue-sonner")`: 29 arquivos; todos mudam se o toast for para `useToast`.
- Montam peça do kit: `OperatorManagerAuth.test.ts`, `OperatorManagerAuth.badge.test.ts` (importam `../../../operator-kit/app/components/OperatorManagerAuth.vue`).
- Montam órfão: `PosReceiptSaveOffer.test.ts` (apagar junto).

### 7.4 Travas fora do app que olham o PDV

- `scripts/check_operator_component_ledger.py`: teto `native_control_occurrences: 157` para `pos` (conta `<button|select|textarea` em `.vue`; o "157" inclui um `<select>` dentro de comentário em `PosSeatingSpotPanel.vue:202`). Proíbe estrutura canônica Nuxt UI fora do kit (`CANONICAL_STRUCTURE`: `NuxtDashboard*`, `NuxtNavigationMenu`, `NuxtPage*`...): migrar o PDV para essas peças REPROVA a trava até registrar exceção ou subir ao kit (foi o que reprovou o Gestor, P0-4). O ledger lista 13 superfícies do `pos`, todas `pending`.
- `operator-kit/tests/kitOwnership.guardrails.test.ts`: por app, proíbe checkbox/rádio nativo, data/hora nativa, `role="switch"`, `role="tablist"`, Skeleton com `animate-pulse bg-muted`.
- `operator-kit/tests/guardrails.vocabulary.test.ts` ("aparelho", "fornada"), `guardrails.copyNeverTruncates.test.ts` (truncate em texto fixo): varrem o PDV.
- `tests/e2e/guards.spec.ts`: `getByLabel("Usuário")`, `getByLabel("Senha")`, botão "Entrar" desabilitado (é o `OperatorLogin` do kit).
- `tests/visual/baselines/*.png` (4 PNGs das Encomendas): toda mudança visual pede baseline nova, e só regera quem tem o Chromium da CI (CLAUDE.md).

---

## 8. Mock visual e e2e

Há DOIS mocks:

| | `tests/e2e/mockBackend.mjs` (37 linhas) | `tests/visual/mockBackend.mjs` (227 linhas) |
|---|---|---|
| Config | `playwright.config.ts` | `playwright.visual.config.ts` (`defineOperatorVisualConfig` do kit, `matrix: false`) |
| Como sobe | `npm run test:e2e`: `node tests/e2e/mockBackend.mjs` na 8798 + `nuxt build && node .output-e2e-<porta>/server/index.mjs` na 3002, `NUXT_DJANGO_BASE_URL` apontando ao mock, `NUXT_APP_BASE_URL=/`. Portas por `POS_E2E_PORT`/`POS_E2E_MOCK_PORT` | `npm run test:visual`: mock na 38792 + `npx nuxt dev` na 33012 com `POS_VISUAL_CLIENT_ONLY=1` (SSR desligado, `nuxt.config.ts:7`) e `bypassCSP: true` |
| Build de produção | sim | NÃO (é `nuxt dev`) |
| O que responde | `/backstage/operator/session/` 403, `/backstage/pos/` 401, resto `{}` | sessão autenticada (Ana, `CAIXA-1`), `/pos/` com projection VAZIA (sem produtos, coleções, formas de pagamento, tabs), `/pos/preorders/`, `/pos/preorders/search/`, `/pos/preorders/NB-1042/`, `/events/` 204, resto `{}` |
| Specs | `guards.spec.ts` (login), `resilience.spec.ts` (offline), `customer-display.spec.ts` (BroadcastChannel entre janelas) | `preorders.spec.ts` (semana em 390, 768, 1440; busca em 390), `preorderDetail.spec.ts` (detalhe em 5 tamanhos) |

Para olhar o build de PRODUÇÃO contra dados com cara de verdade não há receita pronta: o
mock do e2e só sabe dizer 401. O caminho mais curto é reaproveitar o
`tests/visual/mockBackend.mjs` com o `webServer` do `playwright.config.ts` (build +
`node .output/server/index.mjs`, `NUXT_DJANGO_BASE_URL=http://127.0.0.1:38792`).

**Telas sem fixture no mock visual (todas menos duas):** `/` (quadro, venda, comanda,
pagamento, resultado, edição), `/display`, `/session`, `/session/closing`,
`/session/report`, `/settings/terminal`, `/settings/printers`, `/settings/card-machines`,
`/settings/kitchen`, `/settings/shortcuts`, `/settings/seating` (o laudo viu `reading
'filter'` no console: o mock responde `{}` ao salão). Mesmo nas Encomendas, a projection
`pos` é vazia, então o rail não tem comandas e o cabeçalho da venda nunca aparece. A sonda
`tests/e2e-live/copy-overflow.live.spec.ts` cobre a venda, mas só contra Django semeado.

---

## 9. Riscos que a migração não pode quebrar

1. **Teclado inteiro pausa com diálogo aberto** (`utils/keyboardGuard.ts:16`). Todo `NuxtModal`/`NuxtSlideover`/`NuxtDrawer` novo precisa expor `role="dialog"` + `data-state="open"` no conteúdo. A folha da comanda (`PosCartPanel`) hoje NÃO é diálogo: se virar `NuxtDrawer` modal, os atalhos da venda passam a pausar com a comanda aberta no tablet. Decidir `modal: false` ou ajustar a trava.
2. **Esc da gaveta aberta** (`PosDrawerLockDialog.vue:41-49`) cede só ao `[data-drawer-manager-auth][data-state="open"]`. Mexer no `OperatorManagerAuth` sem manter esse atributo no `content` deixa o Esc fechar a trava da gaveta.
3. **PIN do gerente por cima do diálogo aberto**, com o valor digitado preservado (`sessionIndex.layout.test.ts:285-310`): ordem de teleport no `body` importa.
4. **Impressão**: `Teleport to="body"` + `#pos-print-area` (`index.vue:1822`) e o `@page` em `assets/css/tailwind.css:84-115` com variáveis de rolo (`receiptPrint.test.ts`). `PosReceipt` não migra. O agente do balcão (`useCounterAgent`: `http://127.0.0.1:47811` `/print`, `/kick`, `/drawer`, `/health`) e as exceções de CSP (`nuxt.config.ts` `operatorCspAllow`) não podem ser tocados.
5. **Gaveta e dinheiro**: trava da gaveta (poll 400 ms), pulso da gaveta, gaveta esquecida, fechamento incerto entre abas (`storage`), auto-lock que segura durante o pagamento. Nenhum desses é visual, mas todos dependem de diálogo e foco.
6. **Toque (tablet)**: `coarsePointer` em `PosProductGrid`, `PosCartPanel`, `PosTabHeader` (33 usos); `kbd` some em toque (`tailwind.css:17-21`); alvo de 48 px no tablet. O kit já perdeu o `--spacing-control: 3rem` em `pointer: coarse` e o `min-h-control` do `UiFilterChip` (laudo H4, H5): o PDV migrado herda o tamanho `md` do Nuxt UI (cerca de 32 px) se não houver variante de toque no tema. O `OperatorIdentify` (PIN) perdeu `touch-manipulation` e teclas de 52 px (laudo H11).
7. **Kiosk e posto**: `OperatorLock`, `OperatorStationSetup`, `useStationLock`, `OperatorLogin large-fields` (48 px deliberado, `PosOperatorShell.vue:108`). A Tela do cliente NUNCA identifica nem trava (`app.vue:1-22`, decisão pela rota nomeada `display`).
8. **Maquininha**: confirmação "Passe na maquininha" (`PosPaymentWorkspace.vue:2085`), estornos (`session/index.vue:780-801`), cadastro em Ajustes. Vocabulário: "maquininha" nunca vira "dispositivo".
9. **Scanner**: leitor HID de ficha em captura de teclado (`useKitchenTicketScanner.ts:176`) e câmera zxing (`PosCodeScanner`, com `navigator.vibrate`). Um `NuxtInput` com foco não pode engolir a leitura.
10. **Offline**: `OfflineBanner`, `useConnectivity().onReconnect` (`PosOperatorShell.vue:18-19`), SSE com poll de fallback e retomada no `online`; venda persistida (`usePosSale.persist`). O `OperatorLiveStatus` hoje mente "On" no modo `calm` (P0-5).
11. **SSR e hidratação**: o PDV é SSR em produção; o mock visual roda SEM SSR. Toda decisão por `localStorage` (densidade, grade/lista, ocultar indisponíveis) já é feita depois de montar para não divergir; o kit novo tem hydration mismatch em `/preorders` (laudo P1-3).
12. **Arrastar e pinça no Salão** (`PosSeatingPlan.vue:189-287`, `seating.vue:129-148`): eventos de ponteiro na janela; `select-none` e captura de ponteiro. Nenhum componente Nuxt UI substitui; só a moldura migra.
13. **Arrastar encomenda entre dias** (`preorders/index.vue:697-736`) com o menu como alternativa de toque.
14. **Duas réguas na mesma tela durante a transição**: cromo do kit em Nuxt UI e corpo em ui-thing (laudo anexo D §1). A migração deve ser por tela inteira, não por peça.
15. **`check_operator_component_ledger.py`** reprova estrutura canônica Nuxt UI montada no app (P0-4 do Gestor): decidir antes se o shell do PDV vem do kit.

---

## Anexo A. Todos os disparos de gesto no DOM (387)

Gerado por varredura dos `<template>` de `app/**/*.vue` (script `pos-gest2.py` neste diretório, saída crua em `pos-gestures.txt`). O rótulo é heurístico: `aria-label`/`title`/`label` da tag, senão o primeiro texto depois dela. Linhas de `PosPinPad.vue` e `PosReceiptSaveOffer.vue` são de componentes órfãos.

| arquivo:linha | elemento | evento | handler | rótulo (heurístico) |
|---|---|---|---|---|
| components/PosAddressAutocomplete.vue:239 | UiInput | keydown | `onKeydown` | Buscar endereço |
| components/PosAddressAutocomplete.vue:256 | button | click | `accept(suggestion)` | {{ suggestion.main }} |
| components/PosAddressAutocomplete.vue:257 | button | pointerenter | `highlighted = idx` | {{ suggestion.main }} |
| components/PosCartPanel.vue:904 | UiButton | click | `$emit('requestTab')` | Escolher comanda |
| components/PosCartPanel.vue:924 | UiScrim | click | `sheetOpen = false` | Recolher a comanda |
| components/PosCartPanel.vue:931 | button | click | `sheetOpen = !sheetOpen` | sheetOpen ? 'Recolher a comanda' : 'Abrir a comanda' |
| components/PosCartPanel.vue:941 | button | click | `sheetOpen = true` | Abrir a comanda |
| components/PosCartPanel.vue:968 | button | click | `$emit('fire')` | {{ fireBar.label }} |
| components/PosCartPanel.vue:979 | button | click | `$emit('prepare')` | {{ primaryText }} |
| components/PosCartPanel.vue:991 | button | click | `$emit('prepare')` | {{ primaryText }} |
| components/PosCartPanel.vue:1018 | button | click | `toggleBatchMode` | Selecionar linhas (Alt S): transferir, descontar e remover várias |
| components/PosCartPanel.vue:1038 | button | click | `$emit('fire')` | Enviar à cozinha as linhas novas (F9) |
| components/PosCartPanel.vue:1059 | button | click | `$emit('autoFireSettings')` | envio automático: {{ autoFire ? "ligado" : "desligado" }} |
| components/PosCartPanel.vue:1072 | button | click | `sheetOpen = false` | Recolher a comanda |
| components/PosCartPanel.vue:1089 | button | click | `toggleBatchMode` | Concluir seleção |
| components/PosCartPanel.vue:1103 | button | click | `$emit('move', selection.lineIds)` | Transferir as linhas marcadas para outra comanda (F10) |
| components/PosCartPanel.vue:1116 | button | click | `toggleDiscount` | Desconto |
| components/PosCartPanel.vue:1125 | button | click | `batchRemove` | Remover |
| components/PosCartPanel.vue:1137 | button | click | `batchFire` | 'Enviar à cozinha só as marcadas' |
| components/PosCartPanel.vue:1148 | button | click | `batchUnfire` | unfireAction.label ¦¦ 'Cancelar envio à cozinha' |
| components/PosCartPanel.vue:1160 | div | keydown | `navigateItems` | Escolha um produto para começar. |
| components/PosCartPanel.vue:1181 | li | click | `batchMode && toggleSelect(item.line_id)` |  |
| components/PosCartPanel.vue:1188 | button | click.stop | `toggleSelect(item.line_id)` | 'Selecionar ${item.name}' |
| components/PosCartPanel.vue:1216 | button | click | `selectLine(item.line_id)` | 'Editar ${item.name}' |
| components/PosCartPanel.vue:1256 | span | click.stop | `hasKitchenCard(item) && (kitchenLineId = item.line_id)` | hasKitchenCard(item) ? 'Ver ${item.name} na cozinha' : undefined |
| components/PosCartPanel.vue:1322 | UiButton | click.stop | `$emit('unfire', item.line_id)` | {{ unfireAction.label }} |
| components/PosCartPanel.vue:1328 | button | click | `selectLine(item.line_id); openNoteDialog();` | Observação |
| components/PosCartPanel.vue:1376 | button | click | `$emit('unfire', activeItem.line_id)` | {{ unfireAction.label }} |
| components/PosCartPanel.vue:1403 | button | click | `bump(activeItem.line_id, 'decrement')` | Diminuir |
| components/PosCartPanel.vue:1413 | button | click | `selectLine(activeItem.line_id); setMode('qty');` | 'Editar quantidade de ${activeItem.name}' |
| components/PosCartPanel.vue:1425 | button | click | `bump(activeItem.line_id, 'increment')` | Aumentar |
| components/PosCartPanel.vue:1436 | button | click | `askRemove(activeItem.line_id)` | Remover |
| components/PosCartPanel.vue:1447 | button | click | `closeEditor` | Fechar o editor |
| components/PosCartPanel.vue:1461 | button | click | `toggleDiscount` | {{ discountButtonLabel }} |
| components/PosCartPanel.vue:1470 | button | click | `chooseMode('note')` | Observação |
| components/PosCartPanel.vue:1483 | button | click | `$emit('unfire', activeItem.line_id)` | {{ unfireAction.label }} |
| components/PosCartPanel.vue:1501 | button | click | `chooseMode(mode.ref)` | {{ mode.label }} |
| components/PosCartPanel.vue:1526 | UiNativeSelect | change | `commitDiscount` | Motivo do desconto |
| components/PosCartPanel.vue:1547 | button | click | `typeof key === 'number' ? onDigit(String(key)) : key === 'back' ? onBackspace() : onComma()` | {{ key === "decimal" ? "," : key }} |
| components/PosCartPanel.vue:1560 | button | click | `toggleDiscount` | {{ discountOpen ? "Quantidade" : "Desconto" }} |
| components/PosCartPanel.vue:1567 | button | click | `chooseMode('note')` | Observação |
| components/PosCartPanel.vue:1574 | button | click | `askRemove(activeItem.line_id)` | Remover |
| components/PosCartPanel.vue:1581 | button | click | `closeEditor` | Pronto |
| components/PosCartPanel.vue:1606 | button | click | `typeof key === 'number' ? onDigit(String(key)) : key === 'back' ? onBackspace() : onComma()` | {{ typeof key === "number" ? key : key === "back" ? "⌫" : "," }} |
| components/PosCartPanel.vue:1655 | button | click | `$emit('prepare')` | Outras formas |
| components/PosCartPanel.vue:1666 | button | click | `$emit('pay', method.ref)` | {{ method.label }} |
| components/PosCartPanel.vue:1680 | button | click | `$emit('pay', method.ref)` | {{ method.label }} |
| components/PosCartPanel.vue:1696 | button | click | `$emit('prepare')` | '${primaryText} (F4)' |
| components/PosCartPanel.vue:1733 | UiButton | click | `noteDialog = null` | Cancelar |
| components/PosCartPanel.vue:1736 | UiButton | click | `saveNote` | Salvar observação |
| components/PosCartPanel.vue:1770 | UiButton | click | `cancelConfirm` | Cancelar |
| components/PosCartPanel.vue:1771 | UiButton | click | `runConfirm` | {{ confirmCta }} |
| components/PosCashReadingCard.vue:116 | UiButton | click | `emit('reprint', movement.entry_id)` | 'Imprimir segunda via do comprovante de ${movement.kind_label.toLowerCase()}' |
| components/PosCodeScanner.vue:145 | button | click | `close` | Fechar leitor |
| components/PosCodeScanner.vue:156 | button | click | `toggleTorch` | Lanterna |
| components/PosCodeScanner.vue:169 | button | click | `typeInstead` | Digite o código |
| components/PosCustomerModal.vue:421 | UiDialogContent | keydown.capture | `onReceiptKey` | {{ isReceiptDecision ? receiptTitle : "Cliente" }} |
| components/PosCustomerModal.vue:462 | UiButton | click | `activateReceiptAction(index)` | {{ action.label }} |
| components/PosCustomerModal.vue:470 | UiButton | click | `$emit('decisionConfirm', selectedReceiptOwner)` | Confirmar cliente |
| components/PosCustomerModal.vue:471 | UiButton | click | `confirmingAttend = false` | Voltar |
| components/PosCustomerModal.vue:504 | UiButton | click | `$emit('decisionRelease', confirmingRelease); confirmingRelease = null` | Sim, liberar |
| components/PosCustomerModal.vue:517 | UiButton | click | `confirmingRelease = null` | Não liberar |
| components/PosCustomerModal.vue:536 | UiButton | click | `confirmingAttend = false; $emit('decisionConfirm')` | Sim, tenho certeza |
| components/PosCustomerModal.vue:545 | UiButton | click | `confirmingAttend = false` | Voltar |
| components/PosCustomerModal.vue:587 | UiButton | click | `askRelease(candidateValue(row, customerDecision.field))` | {{ decisionCopy.release.label }} |
| components/PosCustomerModal.vue:607 | UiButton | click | `$emit('decisionMerge', row)` | É de {{ firstNameOf(customerDecision.current.name) }} |
| components/PosCustomerModal.vue:623 | UiButton | click | `$emit('decisionPick', row)` | Atender este |
| components/PosCustomerModal.vue:640 | UiButton | click | `askRelease(decisionReleaseValue)` | {{ decisionCopy.release.label }} |
| components/PosCustomerModal.vue:668 | UiButton | click | `$emit('decisionMerge')` | {{ decisionCopy.merge.label }} |
| components/PosCustomerModal.vue:689 | UiButton | click | `cancelDecision` | {{ decisionCopy.cancelLabel }} |
| components/PosCustomerModal.vue:700 | UiButton | click | `askConfirm()` | {{ decisionCopy.confirmLabel }} |
| components/PosCustomerModal.vue:705 | UiButton | click | `cancelDecision` | {{ decisionCopy.cancelLabel }} |
| components/PosCustomerModal.vue:720 | UiButton | click | `$emit('decisionMerge')` | {{ decisionCopy.merge.label }} |
| components/PosCustomerModal.vue:785 | UiButton | click | `$emit('clear')` | Remover cliente |
| components/PosCustomerModal.vue:796 | UiButton | click | `$emit('applyCustomerFavorite')` | Favorito |
| components/PosCustomerModal.vue:799 | UiButton | click | `$emit('repeatCustomerLastOrder')` | Último pedido |
| components/PosCustomerModal.vue:896 | UiButton | click | `onConclude` | {{ footerLabel }} |
| components/PosCustomerSearch.vue:179 | UiInput | keydown.enter | `onEnter` | Buscar cliente |
| components/PosCustomerSearch.vue:180 | UiInput | keydown.down | `onArrow($event, 1)` | Buscar cliente |
| components/PosCustomerSearch.vue:181 | UiInput | keydown.up | `onArrow($event, -1)` | Buscar cliente |
| components/PosCustomerSearch.vue:212 | button | click | `pick(result)` | {{ result.name ¦¦ "Sem nome" }} |
| components/PosCustomerSearch.vue:236 | UiButton | click | `run(pendingAction)` | {{ emptyStateLabel }} |
| components/PosDenominationCounter.vue:169 | div | click | `setActive(denom.q)` | {{ denomLabel(denom) }} |
| components/PosDenominationCounter.vue:182 | input | keydown.enter.prevent | `step(1)` | 'Quantidade de ${denom.shape === 'note' ? 'notas' : 'moedas'} de ${denom.label}' |
| components/PosDenominationCounter.vue:208 | button | click | `typeof key === 'number' ? digit(String(key)) : key === 'back' ? backspace() : plusOne()` | {{ key === "plus" ? "+1" : key }} |
| components/PosDenominationCounter.vue:218 | button | click | `step(-1)` | Anterior |
| components/PosDenominationCounter.vue:225 | button | click | `step(1)` | Próxima |
| components/PosDenominationCounter.vue:232 | button | click | `clear` | Limpar |
| components/PosDenominationCounter.vue:239 | button | click | `emit('note')` | Observação |
| components/PosDrawerLockDialog.vue:104 | button | click | `emit('manager')` | Mais opções |
| components/PosDrawerPulseCard.vue:75 | UiButton | click | `emit('open')` | {{ failed ? 'Tentar de novo: ${label}' : label }} |
| components/PosDrawerPulseCard.vue:112 | UiButton | click | `emit('dismiss')` | Abri com a chave |
| components/PosFulfillmentModal.vue:156 | UiButton | click | `$emit('update:fulfillmentType', option.ref as 'pickup' ¦ 'delivery'); $emit('update:fulfillmentConfi` | {{ option.label }} |
| components/PosFulfillmentModal.vue:175 | UiButton | click | `$emit('pickSavedAddress', address)` | {{ address.label ¦¦ address.formatted_address }} |
| components/PosFulfillmentModal.vue:224 | button | click | `$emit('update:deliveryFeeOverride', !deliveryFeeOverride)` | {{ deliveryFeeOverride ? "Usar a taxa da loja" : "Combinar outro valor" }} |
| components/PosFulfillmentModal.vue:248 | button | click | `$emit('openSchedule')` | Quando |
| components/PosFulfillmentModal.vue:271 | UiButton | click | `isOpen = false` | {{ !fulfillmentConfirmed ? "Escolha o recebimento" : fulfillmentType === "delive |
| components/PosKitchenTicketDialog.vue:104 | UiButton | click | `markReady(ticket)` | Pronto |
| components/PosMoveLinesDialog.vue:120 | UiButton | click | `mode = option.ref` | {{ option.label }} |
| components/PosMoveLinesDialog.vue:171 | UiButton | click | `$emit('update:open', false)` | Cancelar |
| components/PosMoveLinesDialog.vue:174 | UiButton | click | `submit` | {{ submitLabel }} |
| components/PosOrderEditReview.vue:89 | UiButton | click | `pickMethod(option.key)` | {{ option.label }} |
| components/PosOrderEditReview.vue:98 | form | submit.prevent | `taxIdReady && emit('retry')` | CPF ou CNPJ que sai na nota da entrega |
| components/PosOrderEditReview.vue:147 | UiButton | click | `emit('update:open', false)` | Voltar à edição |
| components/PosOrderEditReview.vue:153 | UiButton | click | `emit('confirm')` | Confirmar alterações |
| components/PosOrderEntry.vue:102 | button | click | `goToStep(index)` | '${index + 1}. ${step.label}${step.ready ? ', pronta' : ''}' |
| components/PosOrderEntry.vue:121 | UiButton | click | `act('customer')` | {{ isReady('customer') ? "Trocar cliente" : "Identificar cliente" }} |
| components/PosOrderEntry.vue:127 | UiButton | click | `act('fulfillment')` | {{ isReady('fulfillment') ? "Trocar entrega ou retirada" : "Escolher entrega ou |
| components/PosOrderEntry.vue:133 | UiButton | click | `act('address')` | {{ isReady('address') ? "Trocar endereço" : "Informar endereço" }} |
| components/PosOrderEntry.vue:140 | UiButton | click | `act('schedule')` | {{ isReady('schedule') ? "Trocar data e horário" : "Escolher data e horário" }} |
| components/PosOrderEntry.vue:144 | UiButton | click | `goToStep(currentIndex - 1)` | Voltar |
| components/PosOrderEntry.vue:146 | UiButton | click | `goToStep(currentIndex + 1)` | Continuar |
| components/PosOrderEntry.vue:147 | UiButton | click | `emit('complete')` | Montar encomenda |
| components/PosPaymentResult.vue:133 | UiButton | click | `copyCode` | Copiar código PIX |
| components/PosPaymentResult.vue:154 | UiButton | click | `copyLink` | Copiar link |
| components/PosPaymentResult.vue:169 | UiButton | click | `emit('paymentNotice', delivery.action)` | {{ delivery.action_label }} |
| components/PosPaymentWorkspace.vue:1321 | button | click | `discountSheetOpen = true` | !discountTypes.length ? 'Nenhum desconto disponível para esta loja' : undefined |
| components/PosPaymentWorkspace.vue:1354 | button | click | `splitSheetOpen = true` | Dividir conta |
| components/PosPaymentWorkspace.vue:1395 | button | click | `$emit('update:paymentCollection', collection.ref)` | {{ paymentCollectionLabel(collection, salesMode, fulfillmentType) }} |
| components/PosPaymentWorkspace.vue:1429 | button | click | `$emit('addTender', method.ref)` | paymentMethodBlockedReason(method.ref) |
| components/PosPaymentWorkspace.vue:1453 | button | click | `$emit('tenderDigit', digit)` | 'Dígito ${digit}' |
| components/PosPaymentWorkspace.vue:1457 | button | click | `$emit('tenderComma')` | Vírgula (centavos) |
| components/PosPaymentWorkspace.vue:1458 | button | click | `$emit('tenderDigit', '0')` | Dígito 0 |
| components/PosPaymentWorkspace.vue:1459 | button | click | `$emit('tenderBackspace')` | Apagar um dígito |
| components/PosPaymentWorkspace.vue:1480 | button | click | `$emit('tenderExact')` | Exato: a linha assume o restante |
| components/PosPaymentWorkspace.vue:1491 | button | click | `$emit('tenderClear')` | Limpar: zera o valor da linha |
| components/PosPaymentWorkspace.vue:1514 | button | click | `$emit('tenderAdd', note)` | '${onDelivery ? 'Cliente pagará com' : 'Recebi nota de'} ${formatBRL(note)}' |
| components/PosPaymentWorkspace.vue:1609 | UiButton | click | `action.run()` | {{ action.label }} |
| components/PosPaymentWorkspace.vue:1663 | button | click | `$emit('selectTender', idx)` | 'Editar ${tender.label} de ${tender.amountDisplay}' |
| components/PosPaymentWorkspace.vue:1676 | UiButton | click | `$emit('removeTender', idx)` | 'Remover ${tender.label} de ${tender.amountDisplay}' |
| components/PosPaymentWorkspace.vue:1970 | UiButton | click | `onCta` | {{ ctaLabel }} |
| components/PosPaymentWorkspace.vue:2110 | UiButton | click | `onMachineConfirmed` | OK, cobrei na maquininha |
| components/PosPaymentWorkspace.vue:2113 | UiButton | click | `machineConfirmOpen = false` | Voltar |
| components/PosPaymentWorkspace.vue:2127 | UiDialogContent | keydown | `onSplitKeydown` | Dividir conta |
| components/PosPaymentWorkspace.vue:2156 | UiButton | click | `$emit('setSplitCount', n); splitSheetOpen = false` | 'Dividir em ${n} pessoas, ${splitShareLabel(n)} cada' |
| components/PosPaymentWorkspace.vue:2166 | UiButton | click | `$emit('setSplitCount', 0); splitSheetOpen = false` | Não dividir |
| components/PosPaymentWorkspace.vue:2195 | UiButton | click | `$emit('update:discountType', option.ref === 'fixed' ? 'fixed' : 'percent')` | {{ option.label }} |
| components/PosPaymentWorkspace.vue:2211 | UiButton | click | `$emit('update:discountReason', reason.ref)` | {{ reason.label }} |
| components/PosPaymentWorkspace.vue:2221 | UiButton | click | `discountSheetOpen = false` | Voltar ao pagamento |
| components/PosPinPad.vue:76 | UiButton | click | `press(d)` | {{ d }} |
| components/PosPinPad.vue:86 | UiButton | click | `back` | Apagar |
| components/PosPinPad.vue:95 | UiButton | click | `press('0')` | 0 |
| components/PosPinPad.vue:104 | UiButton | click | `submit` | Confirmar |
| components/PosPreorderFilters.vue:72 | UiFilterChip | click | `press(chip)` | {{ chip.label }} |
| components/PosPreorderFilters.vue:103 | UiButton | click | `showOnlyCheck` | Mostrar só essas |
| components/PosPreorderHandOverDialog.vue:74 | form | submit.prevent | `confirm` | Forma de pagamento |
| components/PosPreorderHandOverDialog.vue:107 | UiButton | click | `emit('update:open', false)` | Voltar |
| components/PosPreorderMoveMenu.vue:59 | button | click | `pick(target.date)` | {{ target.label }} |
| components/PosPreorderMoveMenu.vue:71 | button | click | `other` | Outra data ou horário… |
| components/PosPreorderRescheduleDialog.vue:113 | form | submit.prevent | `confirm` |  |
| components/PosPreorderRescheduleDialog.vue:139 | UiButton | click | `emit('update:open', false)` | Voltar |
| components/PosProductGrid.vue:207 | PosSearchField | keydown.enter.prevent | `onSearchEnter` | Ler código |
| components/PosProductGrid.vue:208 | PosSearchField | keydown.esc.prevent | `onSearchEscape` | Ler código |
| components/PosProductGrid.vue:216 | button | click | `scannerOpen = true` | Ler código pela câmera |
| components/PosProductGrid.vue:233 | button | click | `setDensity(opt.key)` | 'Densidade ${opt.label}' |
| components/PosProductGrid.vue:250 | button | click | `openMatchedTab(tab.ref)` | Comanda {{ tab.display_ref }} |
| components/PosProductGrid.vue:262 | button | click | `findCustomer` | Buscar cliente “ |
| components/PosProductGrid.vue:280 | button | click | `activeCollection = FAVORITES_COLLECTION` | Favoritos |
| components/PosProductGrid.vue:290 | button | click | `activeCollection = ''` | Tudo |
| components/PosProductGrid.vue:302 | button | click | `activeCollection = collection.ref` | {{ collection.name }} |
| components/PosProductGrid.vue:321 | button | click | `setHideUnavailable(!hideUnavailable)` | hideUnavailableActionLabel |
| components/PosProductGrid.vue:345 | UiButton | click | `setHideUnavailable(false)` | Mostrar indisponíveis |
| components/PosProductGroupTile.vue:43 | button | click | `open = true` | '${group.name}: escolher entre ${group.options.length} opções' |
| components/PosProductOptionsDialog.vue:97 | UiDialogContent | keydown | `onKeydown` |  |
| components/PosProductOptionsDialog.vue:146 | button | click | `toggle(group.ref, option.ref)` | {{ option.label }} |
| components/PosProductOptionsDialog.vue:172 | UiButton | click | `emit('cancel')` | Voltar |
| components/PosProductOptionsDialog.vue:173 | UiButton | click | `confirm` | Lançar |
| components/PosProductTile.vue:52 | button | click | `$emit('add', product)` | opensChoice ? '${product.name}: abre as escolhas' : undefined |
| components/PosReceiptSaveOffer.vue:72 | UiButton | click | `emit('update:confirmed', true)` | Trocar CPF |
| components/PosReceiptSaveOffer.vue:79 | UiButton | click | `emit('update:checked', false)` | Manter CPF |
| components/PosRecentSales.vue:353 | UiButton | click | `load` | Atualizar as últimas vendas |
| components/PosRecentSales.vue:404 | UiButton | click | `printReceipt(sale)` | Recibo |
| components/PosRecentSales.vue:413 | UiButton | click | `printDanfe(sale)` | DANFE |
| components/PosRecentSales.vue:423 | UiButton | click | `sendPaymentNotice(sale)` | {{ sale.payment_delivery.action_label }} |
| components/PosRecentSales.vue:432 | UiButton | click | `openEmailPrompt(sale)` | {{ sale.email_sent ? "E-mail da nota (já enviada)" : "E-mail da nota" }} |
| components/PosRecentSales.vue:445 | UiButton | click | `requeueFiscal(sale)` | Reprocessar NFC-e |
| components/PosRecentSales.vue:460 | UiButton | click | `openEmitFiscal(sale)` | Estabelecer emissão… |
| components/PosRecentSales.vue:477 | UiButton | click | `openCancel(sale)` | Cancelar venda |
| components/PosRecentSales.vue:505 | UiInput | keydown.enter.prevent | `resendEmail(sale)` | Enviar |
| components/PosRecentSales.vue:510 | UiButton | click | `resendEmail(sale)` | Enviar |
| components/PosSaleResult.vue:115 | section | pointerdown.capture | `cancelCountdown` |  |
| components/PosSaleResult.vue:231 | UiButton | click | `onNewSale` | {{ pixPending ? "Nova venda mesmo assim" : "Nova venda" }} |
| components/PosSaleResult.vue:249 | UiButton | click | `emit('printReceipt')` | Via Recibo |
| components/PosSaleResult.vue:257 | UiButton | click | `emit('printTicket')` | {{ printingTicket ? "Imprimindo…" : "Via Pedido" }} |
| components/PosSaleResult.vue:271 | UiButton | click | `emit('printDanfe')` | {{ danfe.label }} |
| components/PosSaleResult.vue:316 | UiButton | click | `emit('cancelSale')` | Cancelar venda |
| components/PosScheduleModal.vue:98 | UiButton | click | `backToToday` | Sem agendamento · levar agora |
| components/PosScheduleModal.vue:99 | UiButton | click | `isOpen = false` | Confirmar dia e horário |
| components/PosSchedulePicker.vue:105 | button | click | `emit('update:timeSlot', '')` | A combinar |
| components/PosSchedulePicker.vue:127 | button | click | `emit('update:timeSlot', option.ref)` | option.reason ¦¦ '' |
| components/PosSeatingList.vue:44 | button | click | `emit('add', shape.value, activeArea === 'Sem área' ? '' : activeArea)` | {{ shape.label }} |
| components/PosSeatingList.vue:66 | button | click | `activeArea = group.area.name` | {{ group.area.name }} |
| components/PosSeatingList.vue:80 | button | click | `emit('select', spot.key)` | {{ shortLabelOf(spot) }} |
| components/PosSeatingPalette.vue:79 | button | pointerdown | `emit('grab', shape.value, $event)` | 'Pôr mesa ${shape.label.toLowerCase()} na planta' |
| components/PosSeatingPalette.vue:98 | button | click | `emit('addFixture', fixture.kind)` | 'Pôr ${fixture.label.toLowerCase()} na planta' |
| components/PosSeatingPalette.vue:117 | button | click | `startAdding` | Área |
| components/PosSeatingPalette.vue:122 | form | submit.prevent | `confirmArea` |  |
| components/PosSeatingPalette.vue:130 | input | keydown.esc.stop | `adding = false` | Nome da área nova |
| components/PosSeatingPalette.vue:144 | button | click | `emit('selectArea', area.name)` | areaAria(area) |
| components/PosSeatingPalette.vue:153 | button | click | `startAdding` | Área |
| components/PosSeatingPlan.vue:188 | div | pointerdown.self | `emit('select', null); selectedFixture = null` |  |
| components/PosSeatingPlan.vue:189 | div | touchstart.passive | `onTouchStart` |  |
| components/PosSeatingPlan.vue:190 | div | touchmove | `onTouchMove` |  |
| components/PosSeatingPlan.vue:191 | div | touchend.passive | `onTouchEnd` |  |
| components/PosSeatingPlan.vue:192 | div | touchcancel.passive | `onTouchEnd` |  |
| components/PosSeatingPlan.vue:194 | div | pointerdown.self | `emit('select', null)` |  |
| components/PosSeatingPlan.vue:198 | div | pointerdown.self | `emit('select', null)` |  |
| components/PosSeatingPlan.vue:227 | div | pointerdown | `onFixturePointerDown($event, fixture)` | fixture.label |
| components/PosSeatingPlan.vue:228 | div | pointermove | `onFixturePointerMove` | fixture.label |
| components/PosSeatingPlan.vue:229 | div | pointerup | `onFixturePointerUp` | fixture.label |
| components/PosSeatingPlan.vue:230 | div | pointercancel | `onFixturePointerUp` | fixture.label |
| components/PosSeatingPlan.vue:244 | button | click.stop | `emit('rotateFixture', fixture.kind)` | 'Girar ${fixture.label}' |
| components/PosSeatingPlan.vue:247 | button | click.stop | `emit('removeFixture', fixture.kind); selectedFixture = null` | 'Tirar ${fixture.label} da planta' |
| components/PosSeatingPlan.vue:284 | div | pointerdown | `onSpotPointerDown($event, spot)` | spotAria(spot) |
| components/PosSeatingPlan.vue:285 | div | pointermove | `onSpotPointerMove` | spotAria(spot) |
| components/PosSeatingPlan.vue:286 | div | pointerup | `onSpotPointerUp` | spotAria(spot) |
| components/PosSeatingPlan.vue:287 | div | pointercancel | `onSpotPointerUp` | spotAria(spot) |
| components/PosSeatingPlan.vue:335 | button | click.stop | `emit('rotate', spot.key)` | 'Girar ${spot.label} 90 graus' |
| components/PosSeatingSpotPanel.vue:117 | button | click | `menu('duplicate')` | Duplicar |
| components/PosSeatingSpotPanel.vue:120 | button | click | `menu('rotate')` | Girar 90° |
| components/PosSeatingSpotPanel.vue:123 | button | click | `menu('remove')` | Tirar do salão |
| components/PosSeatingSpotPanel.vue:141 | ? | click | `seats(-1)` | Um lugar a menos |
| components/PosSeatingSpotPanel.vue:152 | button | click | `seats(1)` | Um lugar a mais |
| components/PosSeatingSpotPanel.vue:176 | button | click | `emit('update', { shape: shape.value })` | {{ shape.label }} |
| components/PosSeatingSpotPanel.vue:183 | form | submit.prevent | `confirmNewArea` | Usar |
| components/PosSeatingSpotPanel.vue:244 | input | change | `commitNames` | Sigla |
| components/PosSeatingSpotPanel.vue:245 | input | keydown.enter | `($event.target as HTMLInputElement).blur()` | Sigla |
| components/PosSeatingSpotPanel.vue:256 | input | change | `commitNames` | {{ original ? "Tirar do salão a partir de hoje" : "Tirar esta mesa nova" }} |
| components/PosSeatingSpotPanel.vue:257 | input | keydown.enter | `($event.target as HTMLInputElement).blur()` | {{ original ? "Tirar do salão a partir de hoje" : "Tirar esta mesa nova" }} |
| components/PosSeatingSpotPanel.vue:269 | button | click | `emit('remove')` | {{ original ? "Tirar do salão a partir de hoje" : "Tirar esta mesa nova" }} |
| components/PosSessionTile.vue:48 | button | click | `$emit('select', tile)` | {{ tile.badge }} |
| components/PosStoreNetworkNotice.vue:24 | button | click | `open = !open` | Sem rede da loja |
| components/PosTabBoard.vue:98 | form | submit.prevent | `submitInput` |  |
| components/PosTabBoard.vue:124 | UiButton | click | `openNextFree` | 'Abrir a comanda ${nextFreeDisplay}' |
| components/PosTabBoard.vue:136 | UiButton | click | `tabFilter = 'all'` | Todas {{ tabs.length }} |
| components/PosTabBoard.vue:144 | UiButton | click | `tabFilter = 'in_use'` | Em uso {{ openCount }} |
| components/PosTabBoard.vue:156 | UiButton | click | `tabView = 'grid'` | Ver em grade |
| components/PosTabBoard.vue:166 | UiButton | click | `tabView = 'list'` | Ver em lista |
| components/PosTabBoard.vue:181 | button | click | `tabFilter = 'all'` | Ver todas |
| components/PosTabBoard.vue:194 | button | click | `activateTab(tab)` | {{ tabTitleView(view.displayRef, "").title }} |
| components/PosTabHeader.vue:205 | button | click | `$emit('salesModeChange', mode.ref)` | {{ mode.label }} |
| components/PosTabHeader.vue:232 | button | click | `pickSpot(spot)` | {{ spot.label }} |
| components/PosTabHeader.vue:240 | button | click | `clearSpot` | Tirar a mesa desta comanda |
| components/PosTabHeader.vue:248 | UiInput | keydown | `onRenameKeydown` |  |
| components/PosTabHeader.vue:250 | UiButton | click | `confirmRename` | Confirmar nome |
| components/PosTabHeader.vue:253 | UiButton | click | `cancelRename` | Cancelar |
| components/PosTabHeader.vue:264 | button | click | `startRename` | Renomear comanda |
| components/PosTabHeader.vue:308 | button | click | `readOnly ? $emit('openCustomer') : openCustomerSheet()` | {{ customerName ¦¦ customerLookup?.email ¦¦ customerLookup?.tax_id ¦¦ customerLo |
| components/PosTabHeader.vue:339 | button | click | `$emit('openFulfillment')` | isCounter ? 'Recebimento (F7): entregar vira encomenda' : 'Recebimento (F7)' |
| components/PosTabHeader.vue:365 | button | click | `$emit('openSchedule')` | {{ isCounter ? 'Agora' : scheduleLabel }} |
| components/PosTabHeader.vue:430 | UiButton | click | `confirmClear = false` | Cancelar |
| components/PosTabHeader.vue:431 | UiButton | click | `runClear` | Liberar comanda |
| components/PosTabPickerDialog.vue:81 | form | submit.prevent | `confirmTyped` | Referência da comanda |
| components/PosTabPickerDialog.vue:112 | button | click | `selectTab(tab)` | #{{ tab.display_ref }} |
| components/PosTerminalHealth.vue:176 | UiButton | click | `check` | Testar de novo |
| components/PosTerminalHealth.vue:201 | UiButton | click | `emit('refresh')` | Atualizar a tela |
| components/PosWeighedEntryDialog.vue:184 | button | click | `setKind('label')` | Valor da etiqueta |
| components/PosWeighedEntryDialog.vue:195 | button | click | `setKind('weight')` | Peso |
| components/PosWeighedEntryDialog.vue:217 | input | keydown | `onEntryKeydown` | kind === 'label' ? 'Valor da etiqueta, em reais' : 'Peso, em quilos' |
| components/PosWeighedEntryDialog.vue:235 | UiButton | click | `press(key)` | key === 'Backspace' ? 'Apagar' : key === ',' ? 'Vírgula' : key |
| components/PosWeighedEntryDialog.vue:279 | div | keydown | `onFooterKeydown` | Voltar |
| components/PosWeighedEntryDialog.vue:281 | UiButton | click | `back` | Voltar |
| components/PosWeighedEntryDialog.vue:287 | UiButton | click | `primary` | {{ step === "entry" ? "Continuar" : "Confirmar" }} |
| pages/index.vue:1122 | button | click | `setRail('compact')` | Mostrar a barra |
| pages/index.vue:1134 | button | click | `checkoutMode ? (checkoutMode = false) : goToTabs()` | checkoutMode ? 'Voltar à comanda' : 'Voltar para comandas' |
| pages/index.vue:1146 | UiButton | click | `reloadConflictingTab` | Descartar minhas alterações e atualizar |
| pages/index.vue:1167 | UiButton | click | `discardOrderEdit` | Descartar alterações |
| pages/index.vue:1257 | button | click | `recentSalesOpen = true` | Últimas vendas |
| pages/index.vue:1269 | button | click | `tabHeaderRef?.askRelease()` | Liberar comanda (pede confirmação) |
| pages/index.vue:1299 | button | click | `contextMoreOpen = false; requestSalesMode(mode.ref)` | {{ mode.label }} |
| pages/index.vue:1304 | button | click | `contextMoreOpen = false; openFulfillmentHere()` | {{ cart.salesMode === "order" ? 'Recebimento: ${fulfillmentChipLabel}' : "Consum |
| pages/index.vue:1308 | button | click | `contextMoreOpen = false; openScheduleHere()` | {{ cart.salesMode === "order" ? 'Quando: ${scheduleChipLabel}' : "Agendar (vira |
| pages/index.vue:1312 | button | click | `contextMoreOpen = false; recentSalesOpen = true` | Últimas vendas |
| pages/index.vue:1316 | button | click | `contextMoreOpen = false; tabHeaderRef?.askRelease()` | Liberar comanda |
| pages/index.vue:1342 | UiButton | click | `recentSalesOpen = true` | Conferir últimas vendas |
| pages/index.vue:1358 | UiButton | click | `openUncertainCloseRecovery` | Já conferi · liberar tentativa |
| pages/index.vue:1504 | PosPaymentWorkspace | submit | `submitSale` |  |
| pages/index.vue:1713 | UiButton | click | `confirmCounterMode = false` | Continuar encomenda |
| pages/index.vue:1714 | UiButton | click | `convertToCounter` | Converter para balcão |
| pages/index.vue:1730 | UiButton | click | `uncertainCloseRecoveryOpen = false` | Voltar e conferir |
| pages/index.vue:1731 | UiButton | click | `confirmUncertainCloseRecovery` | {{ uncertainCloseRecoveryBusy ? 'Verificando…' : 'Liberar tentativa' }} |
| pages/index.vue:1814 | PosMoveLinesDialog | submit | `submitMove` |  |
| pages/preorders/[ref].vue:143 | UiButton | click | `goBack` | Voltar |
| pages/preorders/[ref].vue:217 | UiButton | click | `handOverOpen = true` | {{ handOverCta(counter.hand_over) }} |
| pages/preorders/[ref].vue:240 | UiButton | click | `rescheduleOpen = true` | Reagendar |
| pages/preorders/[ref].vue:252 | UiButton | click | `printTicket` | {{ counter.ticket_printed ? "Imprimir 2ª via" : "Imprimir Via Pedido" }} |
| pages/preorders/[ref].vue:265 | UiButton | click | `editOrder` | Editar encomenda |
| pages/preorders/[ref].vue:276 | UiButton | click | `cancelAndRedo` | Cancelar e refazer |
| pages/preorders/[ref].vue:298 | UiButton | click | `goToComment` | Comentar no histórico |
| pages/preorders/[ref].vue:311 | UiButton | click | `redoAfterCancel = false; cancelOpen = true` | Cancelar encomenda |
| pages/preorders/index.vue:368 | UiIconButton | click | `setLayout(option.value)` | option.label |
| pages/preorders/index.vue:378 | UiButton | click | `printMissing` | {{ printCtaLabel(printCount, shownCount) }} |
| pages/preorders/index.vue:406 | PosSearchField | keydown.enter.prevent | `openSingle` | SEARCH_LABEL |
| pages/preorders/index.vue:423 | UiButton | click | `navigateTo(NEW_ORDER_ROUTE)` | Nova encomenda |
| pages/preorders/index.vue:440 | button | click | `pickPhoneChip(chip.key)` | {{ chip.label }} |
| pages/preorders/index.vue:474 | UiButton | click | `search.refresh()` | Tentar de novo |
| pages/preorders/index.vue:525 | UiButton | click | `includeCompleted = true` | Procurar nas concluídas |
| pages/preorders/index.vue:629 | UiButton | click | `period.refresh()` | Tentar de novo |
| pages/preorders/index.vue:697 | section | dragover | `onDragOver($event, weekDay.date)` |  |
| pages/preorders/index.vue:698 | section | dragleave | `onDragLeave($event, weekDay.date)` |  |
| pages/preorders/index.vue:699 | section | drop.prevent | `onDrop(weekDay.date)` |  |
| pages/preorders/index.vue:714 | button | click | `openDay(weekDay.date)` | 'Abrir o dia ${dayColumnTitle(weekDay)}' |
| pages/preorders/index.vue:735 | PosPreorderRow | dragstart | `onDragStart($event, card)` | move.moveTo(card, date)" @other="move.chooseOther(card)" |
| pages/preorders/index.vue:736 | PosPreorderRow | dragend | `endDrag` | move.moveTo(card, date)" @other="move.chooseOther(card)" |
| pages/preorders/index.vue:769 | button | click | `scannerOpen = true` | Ler código da encomenda |
| pages/session/closing.vue:266 | button | click | `goToCashSession` | Voltar à sessão de caixa |
| pages/session/closing.vue:312 | UiButton | click | `goToCashSession` | Voltar à sessão de caixa |
| pages/session/closing.vue:330 | UiButton | click | `goToCashReport` | Ver relatório de caixa |
| pages/session/closing.vue:334 | UiButton | click | `goToCashSession` | Voltar à sessão de caixa |
| pages/session/closing.vue:361 | button | click | `drawerMode = 'denominations'` | Por cédula |
| pages/session/closing.vue:368 | button | click | `drawerMode = 'total'` | Só o total |
| pages/session/closing.vue:401 | UiButton | click | `drawerConfirming = true` | Contei {{ drawerDisplay }} · Confirmar |
| pages/session/closing.vue:409 | UiButton | click | `drawerConfirming = false` | Voltar à contagem |
| pages/session/closing.vue:410 | UiButton | click | `confirmDrawer` | Fechar o caixa |
| pages/session/closing.vue:417 | button | click | `step = 'count'` | Contar a vitrine primeiro |
| pages/session/closing.vue:639 | UiInput | keydown.enter.prevent | `focusNextCount(index)` | 'Sobras de ${item.name}' |
| pages/session/closing.vue:657 | UiButton | click | `goToReview` | Contei {{ piecesLabel(summary.keep + summary.loss + summary.mixed) }} · Revisar |
| pages/session/closing.vue:694 | UiButton | click | `goToCloseCash` | Fechar caixa |
| pages/session/closing.vue:708 | button | click | `step = 'count'` | Maior sobra: {{ biggestLeftover.name }} ({{ biggestLeftover.qty }}) |
| pages/session/closing.vue:713 | button | click | `step = 'count'` | Voltar à contagem |
| pages/session/closing.vue:766 | button | click | `sendEpisode(episode.id, option.ref)` | option.hint ¦¦ undefined |
| pages/session/closing.vue:775 | button | click | `sendEpisode(episode.id, '')` | Não houve nada |
| pages/session/closing.vue:795 | UiButton | click | `step = 'count'` | Vitrine |
| pages/session/closing.vue:799 | UiButton | click | `confirming = true` | Fechar o dia {{ closing.today_display }} |
| pages/session/closing.vue:809 | UiButton | click | `confirming = false` | Cancelar |
| pages/session/closing.vue:810 | UiButton | click | `confirmSubmit` | Confirmar fechamento |
| pages/session/index.vue:706 | UiInput | keydown.enter | `submitOpen` | {{ openingError }} |
| pages/session/index.vue:719 | UiButton | click | `useFloatSuggestion` | Está certo: {{ floatSuggestionDisplay }} |
| pages/session/index.vue:724 | UiButton | click | `openingCounter = true` | Contar por cédulas e moedas |
| pages/session/index.vue:735 | UiButton | click | `submitOpen` | Abrir caixa e vender |
| pages/session/index.vue:766 | UiButton | click | `refundPending(refund.order_ref)` | Devolver |
| pages/session/index.vue:801 | UiButton | click | `recordMachineRefund(refund.order_ref)` | Estornei na maquininha |
| pages/session/index.vue:839 | UiButton | click | `serveChange(request.ref)` | Atender |
| pages/session/index.vue:847 | UiButton | click | `cancellingChangeRef = request.ref` | Cancelar pedido |
| pages/session/index.vue:855 | UiButton | click | `cancellingChangeRef = ''` | Voltar |
| pages/session/index.vue:863 | UiButton | click | `confirmCancelChange(request.ref)` | Confirmar |
| pages/session/index.vue:917 | UiInput | keydown.enter | `submitSettle` | Valor recebido no acerto |
| pages/session/index.vue:931 | UiButton | click | `settleCustomerRef = null` | Cancelar |
| pages/session/index.vue:932 | UiButton | click | `submitSettle` | Receber |
| pages/session/index.vue:942 | UiButton | click | `openSettle(account.customer_ref, account.balance_q)` | Receber acerto |
| pages/session/index.vue:982 | UiInput | keydown.enter | `submitChangeRequest` |  |
| pages/session/index.vue:1020 | button | click | `toggleDenomination(denom.q)` | '${denom.shape === 'note' ? 'Nota' : 'Moeda'} de ${denom.label}' |
| pages/session/index.vue:1031 | UiInput | keydown.enter | `submitChangeRequest` | Observação do pedido |
| pages/session/index.vue:1036 | UiButton | click | `submitChangeRequest` | Preciso de troco |
| pages/session/index.vue:1073 | UiButton | click | `pickMovementKind(kind)` | {{ movementLabel(kind) }} |
| pages/session/index.vue:1111 | UiButton | click | `pickMovementReason(reason)` | {{ reason }} |
| pages/session/index.vue:1129 | UiButton | click | `submitMovement()` | Registrar movimento |
| pages/session/index.vue:1156 | UiButton | click | `openDrawer(reason)` | {{ reason }} |
| pages/session/index.vue:1162 | UiInput | keydown.enter | `openDrawer(drawerReason)` | Abrir |
| pages/session/index.vue:1163 | UiButton | click | `openDrawer(drawerReason)` | Abrir |
| pages/session/index.vue:1173 | UiButton | click | `testDrawer` | Abrir para testar |
| pages/session/index.vue:1226 | UiButton | click | `closingCounter = true` | Contar por cédulas e moedas |
| pages/session/index.vue:1249 | UiButton | click | `confirmingClose = true` | Conferir e fechar |
| pages/session/index.vue:1260 | UiButton | click | `confirmingClose = false` | Cancelar |
| pages/session/index.vue:1262 | UiButton | click | `confirmClose` | Fechar o caixa |
| pages/session/report.vue:50 | UiButton | click | `goToCashSession` | Voltar à sessão de caixa |
| pages/session/report.vue:64 | UiButton | click | `refresh()` | Atualizar relatório |
| pages/session/report.vue:81 | UiButton | click | `goToCashSession` | Voltar à sessão de caixa |
| pages/session/report.vue:91 | UiButton | click | `goToCashSession` | Voltar à sessão de caixa |
| pages/settings/card-machines.vue:35 | UiButton | click | `addNew` | Nova maquininha |
| pages/settings/card-machines.vue:41 | UiButton | click | `settings.refresh()` | Tentar de novo |
| pages/settings/card-machines.vue:54 | button | click | `edit(machine)` | {{ machine.label }} |
| pages/settings/card-machines.vue:76 | form | submit.prevent | `submit` | Nome |
| pages/settings/card-machines.vue:86 | UiButton | click | `editing = null` | Cancelar |
| pages/settings/kitchen.vue:25 | UiButton | click | `settings.refresh()` | Tentar de novo |
| pages/settings/printers.vue:31 | UiButton | click | `settings.refresh()` | Tentar de novo |
| pages/settings/printers.vue:62 | button | click | `drafts[printer.terminal_ref]!.roll = width` | {{ width }} mm |
| pages/settings/printers.vue:76 | button | click | `drafts[printer.terminal_ref]!.cut = mode.value` | {{ mode.label }} |
| pages/settings/printers.vue:82 | UiButton | click | `save(printer)` | Gravar impressora |
| pages/settings/seating.vue:301 | button | click | `seating.undo()` | Desfazer (Ctrl Z) |
| pages/settings/seating.vue:312 | button | click | `seating.redo()` | Refazer (Ctrl Shift Z) |
| pages/settings/seating.vue:319 | button | click | `stepZoom(-1)` | Menos zoom |
| pages/settings/seating.vue:323 | button | click | `stepZoom(1)` | Mais zoom |
| pages/settings/seating.vue:333 | button | click | `snapEnabled = !snapEnabled` | Encaixar na grade |
| pages/settings/seating.vue:355 | button | click | `menuOpen = false; historyOpen = true` | Histórico do salão |
| pages/settings/seating.vue:362 | button | click | `menuOpen = false; seating.refresh()` | Recarregar o salão |
| pages/settings/seating.vue:378 | UiButton | click | `seating.refresh()` | Tentar de novo |
| pages/settings/seating.vue:516 | button | click | `discard` | Descartar |
| pages/settings/seating.vue:523 | button | click | `seating.save()` | Salvar salão |
| pages/settings/shortcuts.vue:38 | UiButton | click | `save` | Gravar atalhos |
| pages/settings/shortcuts.vue:42 | UiButton | click | `settings.refresh()` | Tentar de novo |
| pages/settings/shortcuts.vue:56 | button | click | `move(index, -1)` | 'Subir ${nameOf(ref)}' |
| pages/settings/shortcuts.vue:57 | button | click | `move(index, 1)` | 'Descer ${nameOf(ref)}' |
| pages/settings/shortcuts.vue:58 | button | click | `toggle(ref)` | 'Tirar ${nameOf(ref)}' |
| pages/settings/shortcuts.vue:72 | button | click | `toggle(collection.ref)` | {{ collection.name }} |
| pages/settings/terminal.vue:72 | UiButton | click | `check` | Testar o agente de novo |
| pages/settings/terminal.vue:76 | UiButton | click | `refreshScreen` | Atualizar a tela |

## Anexo B. Disparos por evento de componente (306)

Emits de `Pos*`/`Operator*`/`Ui*` com handler (exclui `update:model-value`, foco e blur). Cobre os diálogos e o que cada um devolve à página.

| arquivo:linha | componente | evento | handler |
|---|---|---|---|
| components/PosCancelSaleDialog.vue:52 | UiDialog | update:open | `(value) => emit('update:open', value)` |
| components/PosCancelSaleDialog.vue:89 | OperatorIdentify | pin | `onPin` |
| components/PosCancelSaleDialog.vue:90 | OperatorIdentify | badge | `onBadge` |
| components/PosCartPanel.vue:1711 | UiDialog | update:open | `(value) => { if (!value) noteDialog = null; }` |
| components/PosCartPanel.vue:1743 | UiDialog | update:open | `(value) => { if (!value) cancelConfirm(); }` |
| components/PosCartPanel.vue:1782 | PosKitchenTicketDialog | update:open | `(value) => { if (!value) kitchenLineId = ''; }` |
| components/PosCodeScanner.vue:135 | UiDialog | update:open | `(value) => { if (!value) close(); }` |
| components/PosCustomerModal.vue:419 | UiDialog | update:open | `$emit('update:open', Boolean($event))` |
| components/PosCustomerModal.vue:743 | PosCustomerSearch | search | `$emit('search', $event)` |
| components/PosCustomerModal.vue:744 | PosCustomerSearch | select | `onSelect` |
| components/PosCustomerModal.vue:745 | PosCustomerSearch | resolve-cpf | `onResolveCpf` |
| components/PosCustomerModal.vue:746 | PosCustomerSearch | transfer | `onTransfer` |
| components/PosCustomerModal.vue:747 | PosCustomerSearch | create-name-only | `onCreateNameOnly` |
| components/PosCustomerModal.vue:748 | PosCustomerSearch | conclude | `onConclude` |
| components/PosCustomerSearch.vue:211 | button | mousemove | `highlighted = index` |
| components/PosDrawerLockDialog.vue:54 | UiDialog | update:open | `(value) => emit('update:open', value)` |
| components/PosFulfillmentModal.vue:187 | PosAddressAutocomplete | selected | `onAddressSelected` |
| components/PosFunctionRail.vue:84 | OperatorSuiteRail | select | `onSelect` |
| components/PosFunctionRail.vue:85 | OperatorSuiteRail | lock | `emit('lock')` |
| components/PosFunctionRail.vue:95 | PosTerminalHealth | refresh | `emit('refresh')` |
| components/PosFunctionRail.vue:105 | OperatorSectionBar | select | `onSelect` |
| components/PosFunctionRail.vue:106 | OperatorSectionBar | lock | `emit('lock')` |
| components/PosFunctionRail.vue:110 | PosTerminalHealth | refresh | `emit('refresh')` |
| components/PosKitchenTicketDialog.vue:59 | UiDialog | update:open | `(value) => emit('update:open', value)` |
| components/PosMoveLinesDialog.vue:99 | UiDialog | update:open | `$emit('update:open', Boolean($event))` |
| components/PosOperatorShell.vue:105 | OperatorSessionUnavailable | retry | `refreshOperatorSession()` |
| components/PosOperatorShell.vue:124 | OperatorStationSetup | done | `stationSetup.done()` |
| components/PosOperatorShell.vue:125 | OperatorStationSetup | dismiss | `stationSetup.dismiss()` |
| components/PosOperatorShell.vue:126 | OperatorStationSetup | unavailable | `stationSetup.dismiss({ remember: false })` |
| components/PosOrderEditReview.vue:56 | UiDialog | update:open | `(value) => emit('update:open', value)` |
| components/PosPaymentWorkspace.vue:1990 | PosFulfillmentModal | update:fulfillment-confirmed | `$emit('update:fulfillmentConfirmed', $event)` |
| components/PosPaymentWorkspace.vue:2006 | PosFulfillmentModal | update:fulfillment-type | `$emit('update:fulfillmentType', $event)` |
| components/PosPaymentWorkspace.vue:2007 | PosFulfillmentModal | update:delivery-address | `$emit('update:deliveryAddress', $event)` |
| components/PosPaymentWorkspace.vue:2008 | PosFulfillmentModal | update:delivery-address-structured | `$emit('update:deliveryAddressStructured', $event)` |
| components/PosPaymentWorkspace.vue:2009 | PosFulfillmentModal | update:delivery-street-number | `$emit('update:deliveryStreetNumber', $event)` |
| components/PosPaymentWorkspace.vue:2010 | PosFulfillmentModal | update:delivery-neighborhood | `$emit('update:deliveryNeighborhood', $event)` |
| components/PosPaymentWorkspace.vue:2011 | PosFulfillmentModal | update:delivery-complement | `$emit('update:deliveryComplement', $event)` |
| components/PosPaymentWorkspace.vue:2012 | PosFulfillmentModal | update:delivery-instructions | `$emit('update:deliveryInstructions', $event)` |
| components/PosPaymentWorkspace.vue:2013 | PosFulfillmentModal | update:delivery-fee-override | `$emit('update:deliveryFeeOverride', $event)` |
| components/PosPaymentWorkspace.vue:2014 | PosFulfillmentModal | update:delivery-fee-override-input | `$emit('update:deliveryFeeOverrideInput', $event)` |
| components/PosPaymentWorkspace.vue:2015 | PosFulfillmentModal | update:order-notes | `$emit('update:orderNotes', $event)` |
| components/PosPaymentWorkspace.vue:2016 | PosFulfillmentModal | pick-saved-address | `$emit('pickSavedAddress', $event)` |
| components/PosPaymentWorkspace.vue:2017 | PosFulfillmentModal | open-schedule | `scheduleSheetOpen = true` |
| components/PosPaymentWorkspace.vue:2038 | PosScheduleModal | update:delivery-date | `$emit('update:deliveryDate', $event)` |
| components/PosPaymentWorkspace.vue:2039 | PosScheduleModal | update:delivery-time-slot | `$emit('update:deliveryTimeSlot', $event)` |
| components/PosPaymentWorkspace.vue:2061 | PosCustomerModal | update:customer-name | `$emit('update:customerName', $event)` |
| components/PosPaymentWorkspace.vue:2062 | PosCustomerModal | update:customer-phone | `$emit('update:customerPhone', $event)` |
| components/PosPaymentWorkspace.vue:2063 | PosCustomerModal | update:customer-tax-id | `$emit('update:customerTaxId', $event)` |
| components/PosPaymentWorkspace.vue:2064 | PosCustomerModal | update:customer-email | `$emit('update:customerEmail', $event)` |
| components/PosPaymentWorkspace.vue:2065 | PosCustomerModal | search | `$emit('search', $event)` |
| components/PosPaymentWorkspace.vue:2066 | PosCustomerModal | select-result | `onSelectResult` |
| components/PosPaymentWorkspace.vue:2067 | PosCustomerModal | clear | `$emit('clearCustomer')` |
| components/PosPaymentWorkspace.vue:2068 | PosCustomerModal | resolve-customer | `$emit('resolveCustomer', $event)` |
| components/PosPaymentWorkspace.vue:2069 | PosCustomerModal | decision-confirm | `$emit('decisionConfirm', $event)` |
| components/PosPaymentWorkspace.vue:2070 | PosCustomerModal | decision-cancel | `$emit('decisionCancel')` |
| components/PosPaymentWorkspace.vue:2071 | PosCustomerModal | decision-merge | `$emit('decisionMerge', $event)` |
| components/PosPaymentWorkspace.vue:2072 | PosCustomerModal | decision-release | `$emit('decisionRelease', $event)` |
| components/PosPaymentWorkspace.vue:2073 | PosCustomerModal | decision-pick | `$emit('decisionPick', $event)` |
| components/PosPaymentWorkspace.vue:2074 | PosCustomerModal | apply-customer-favorite | `$emit('applyCustomerFavorite')` |
| components/PosPaymentWorkspace.vue:2075 | PosCustomerModal | repeat-customer-last-order | `$emit('repeatCustomerLastOrder')` |
| components/PosPaymentWorkspace.vue:2076 | PosCustomerModal | apply-preference | `(key, value) => $emit('applyPreference', key, value)` |
| components/PosPaymentWorkspace.vue:2236 | OperatorManagerAuth | authorize | `onManagerAuthorize` |
| components/PosPreorderCancelDialog.vue:39 | OperatorReasonDialog | update:open | `(value: boolean) => emit('update:open', value)` |
| components/PosPreorderCancelDialog.vue:40 | OperatorReasonDialog | confirm | `(choice: ReasonChoice) => emit('confirm', choice.reason)` |
| components/PosPreorderHandOverDialog.vue:51 | UiDialog | update:open | `(value) => emit('update:open', value)` |
| components/PosPreorderRescheduleDialog.vue:106 | UiDialog | update:open | `(value) => emit('update:open', value)` |
| components/PosPreorderRescheduleDialog.vue:129 | PosSchedulePicker | update:date | `pickDate` |
| components/PosPreorderRescheduleDialog.vue:130 | PosSchedulePicker | update:time-slot | `slot = $event` |
| components/PosPreordersShell.vue:48 | PosFunctionRail | board | `navigateTo('/')` |
| components/PosPreordersShell.vue:49 | PosFunctionRail | cash | `navigateTo('/session')` |
| components/PosPreordersShell.vue:50 | PosFunctionRail | display | `openCustomerDisplay` |
| components/PosPreordersShell.vue:51 | PosFunctionRail | lock | `lock()` |
| components/PosPreordersShell.vue:52 | PosFunctionRail | refresh | `emit('refresh')` |
| components/PosPreordersShell.vue:81 | PosFunctionRail | board | `navigateTo('/')` |
| components/PosPreordersShell.vue:81 | PosFunctionRail | cash | `navigateTo('/session')` |
| components/PosPreordersShell.vue:81 | PosFunctionRail | display | `openCustomerDisplay` |
| components/PosPreordersShell.vue:81 | PosFunctionRail | lock | `lock()` |
| components/PosProductGrid.vue:360 | PosProductGroupTile | add | `emit('add', $event)` |
| components/PosProductGrid.vue:368 | PosProductTile | add | `emit('add', $event)` |
| components/PosProductGrid.vue:373 | PosCodeScanner | code | `onScanned` |
| components/PosProductGrid.vue:373 | PosCodeScanner | type | `focusSearch()` |
| components/PosProductGroupTile.vue:46 | img | error | `imageBroken = true` |
| components/PosProductGroupTile.vue:94 | PosProductTile | add | `choose` |
| components/PosProductOptionsDialog.vue:93 | UiDialog | update:open | `(value) => { if (!value) emit('cancel') }` |
| components/PosProductTile.vue:61 | img | error | `imageBroken = true` |
| components/PosRecentSales.vue:346 | UiSheet | update:open | `(v) => emit('update:open', v)` |
| components/PosRecentSales.vue:531 | PosCancelSaleDialog | confirm | `(username, pin) => submitCancel({ username, pin })` |
| components/PosRecentSales.vue:532 | PosCancelSaleDialog | confirm-badge | `(badge) => submitCancel({ badge })` |
| components/PosRecentSales.vue:542 | OperatorManagerAuth | authorize | `(username, pin) => submitEmitFiscal({ username, pin })` |
| components/PosRecentSales.vue:543 | OperatorManagerAuth | authorize-badge | `(badge) => submitEmitFiscal({ badge })` |
| components/PosSaleResult.vue:222 | PosPaymentResult | payment-notice | `emit('paymentNotice', $event)` |
| components/PosScheduleModal.vue:93 | PosSchedulePicker | update:date | `$emit('update:deliveryDate', $event)` |
| components/PosScheduleModal.vue:94 | PosSchedulePicker | update:time-slot | `$emit('update:deliveryTimeSlot', $event)` |
| components/PosSeatingHistory.vue:12 | UiSheet | update:open | `(value) => emit('update:open', value)` |
| components/PosSettingsShell.vue:32 | PosFunctionRail | board | `navigateTo('/')` |
| components/PosSettingsShell.vue:33 | PosFunctionRail | cash | `navigateTo('/session')` |
| components/PosSettingsShell.vue:34 | PosFunctionRail | display | `openCustomerDisplay` |
| components/PosSettingsShell.vue:35 | PosFunctionRail | lock | `lock()` |
| components/PosSettingsShell.vue:36 | PosFunctionRail | refresh | `refreshPos()` |
| components/PosTabHeader.vue:397 | PosCustomerModal | update:customer-name | `$emit('update:customerName', $event)` |
| components/PosTabHeader.vue:398 | PosCustomerModal | update:customer-phone | `$emit('update:customerPhone', $event)` |
| components/PosTabHeader.vue:399 | PosCustomerModal | update:customer-tax-id | `$emit('update:customerTaxId', $event)` |
| components/PosTabHeader.vue:400 | PosCustomerModal | update:customer-email | `$emit('update:customerEmail', $event)` |
| components/PosTabHeader.vue:401 | PosCustomerModal | search | `$emit('search', $event)` |
| components/PosTabHeader.vue:402 | PosCustomerModal | select-result | `$emit('selectResult', $event)` |
| components/PosTabHeader.vue:403 | PosCustomerModal | clear | `$emit('clearCustomer')` |
| components/PosTabHeader.vue:404 | PosCustomerModal | resolve-customer | `$emit('resolveCustomer', $event)` |
| components/PosTabHeader.vue:405 | PosCustomerModal | decision-confirm | `$emit('decisionConfirm', $event)` |
| components/PosTabHeader.vue:406 | PosCustomerModal | decision-cancel | `$emit('decisionCancel')` |
| components/PosTabHeader.vue:407 | PosCustomerModal | decision-merge | `$emit('decisionMerge', $event)` |
| components/PosTabHeader.vue:408 | PosCustomerModal | decision-release | `$emit('decisionRelease', $event)` |
| components/PosTabHeader.vue:409 | PosCustomerModal | decision-pick | `$emit('decisionPick', $event)` |
| components/PosTabHeader.vue:410 | PosCustomerModal | apply-customer-favorite | `$emit('applyCustomerFavorite')` |
| components/PosTabHeader.vue:411 | PosCustomerModal | repeat-customer-last-order | `$emit('repeatCustomerLastOrder')` |
| components/PosTabHeader.vue:412 | PosCustomerModal | apply-preference | `(key, value) => $emit('applyPreference', key, value)` |
| components/PosTabHeader.vue:415 | UiDialog | update:open | `(value) => { if (!value) confirmClear = false; }` |
| components/PosTabPickerDialog.vue:74 | UiDialog | update:open | `$emit('update:open', Boolean($event))` |
| components/PosWeighedEntryDialog.vue:142 | UiDialog | update:open | `(value) => { if (!value) emit('cancel') }` |
| pages/index.vue:1097 | PosFunctionRail | board | `goToTabs` |
| pages/index.vue:1098 | PosFunctionRail | cash | `goToCashSession` |
| pages/index.vue:1099 | PosFunctionRail | display | `openCustomerDisplay` |
| pages/index.vue:1100 | PosFunctionRail | lock | `lock()` |
| pages/index.vue:1101 | PosFunctionRail | refresh | `refresh()` |
| pages/index.vue:1209 | PosTabHeader | sales-mode-change | `requestSalesMode` |
| pages/index.vue:1210 | PosTabHeader | customer-closed | `focusOrderEntry` |
| pages/index.vue:1211 | PosTabHeader | customer-locked | `notifyCustomerLocked` |
| pages/index.vue:1212 | PosTabHeader | rename | `(ref: string, spot?: string) => { if (!editing) void renameTab(ref, spot); }` |
| pages/index.vue:1213 | PosTabHeader | clear | `clearOrDiscard` |
| pages/index.vue:1214 | PosTabHeader | clear-customer | `clearCustomer` |
| pages/index.vue:1215 | PosTabHeader | lookup-customer | `lookupCustomer` |
| pages/index.vue:1216 | PosTabHeader | resolve-customer | `(done) => { void resolveCustomer().then(done) }` |
| pages/index.vue:1217 | PosTabHeader | decision-confirm | `confirmCustomerDecision` |
| pages/index.vue:1218 | PosTabHeader | decision-cancel | `cancelCustomerDecision` |
| pages/index.vue:1219 | PosTabHeader | decision-merge | `mergeConflictCustomers` |
| pages/index.vue:1220 | PosTabHeader | decision-release | `releaseConflictContact` |
| pages/index.vue:1221 | PosTabHeader | decision-pick | `pickConflictCandidate` |
| pages/index.vue:1222 | PosTabHeader | search | `searchCustomers` |
| pages/index.vue:1223 | PosTabHeader | select-result | `selectCustomerResult` |
| pages/index.vue:1224 | PosTabHeader | apply-customer-favorite | `applyCustomerFavorite` |
| pages/index.vue:1225 | PosTabHeader | apply-preference | `applyCustomerPreference` |
| pages/index.vue:1226 | PosTabHeader | repeat-customer-last-order | `repeatCustomerLastOrder` |
| pages/index.vue:1227 | PosTabHeader | open-fulfillment | `openFulfillmentHere` |
| pages/index.vue:1228 | PosTabHeader | open-schedule | `openScheduleHere` |
| pages/index.vue:1229 | PosTabHeader | open-customer | `paymentWorkspaceRef?.openCustomer()` |
| pages/index.vue:1378 | PosDrawerPulseCard | open | `drawerOpening.open({ purpose: 'sale', orderRef: pending.orderRef })` |
| pages/index.vue:1379 | PosDrawerPulseCard | dismiss | `drawerOpening.dismissPendingCash(pending.orderRef)` |
| pages/index.vue:1395 | PosSaleResult | new-sale | `startNextSale` |
| pages/index.vue:1396 | PosSaleResult | print-ticket | `printOrderTicket(result.orderRef)` |
| pages/index.vue:1397 | PosSaleResult | print-receipt | `printReceipt` |
| pages/index.vue:1398 | PosSaleResult | print-danfe | `printDanfe` |
| pages/index.vue:1399 | PosSaleResult | cancel-sale | `openCancelSaleDialog` |
| pages/index.vue:1400 | PosSaleResult | payment-notice | `sendPaymentNotice` |
| pages/index.vue:1411 | PosDrawerPulseCard | open | `drawerOpening.open({ purpose: 'sale', orderRef: pending.orderRef })` |
| pages/index.vue:1412 | PosDrawerPulseCard | dismiss | `drawerOpening.dismissPendingCash(pending.orderRef)` |
| pages/index.vue:1503 | PosPaymentWorkspace | back | `checkoutMode = false` |
| pages/index.vue:1505 | PosPaymentWorkspace | add-tender | `addTender` |
| pages/index.vue:1506 | PosPaymentWorkspace | remove-tender | `removeTender` |
| pages/index.vue:1507 | PosPaymentWorkspace | select-tender | `selectTender` |
| pages/index.vue:1508 | PosPaymentWorkspace | set-split-count | `setSplitCount` |
| pages/index.vue:1509 | PosPaymentWorkspace | tender-digit | `tenderDigit` |
| pages/index.vue:1510 | PosPaymentWorkspace | tender-comma | `tenderComma` |
| pages/index.vue:1511 | PosPaymentWorkspace | tender-backspace | `tenderBackspace` |
| pages/index.vue:1512 | PosPaymentWorkspace | tender-clear | `tenderClear` |
| pages/index.vue:1513 | PosPaymentWorkspace | tender-add | `tenderAdd` |
| pages/index.vue:1514 | PosPaymentWorkspace | tender-exact | `tenderExact` |
| pages/index.vue:1515 | PosPaymentWorkspace | lookup-customer | `lookupCustomer` |
| pages/index.vue:1516 | PosPaymentWorkspace | resolve-customer | `(done) => { void resolveCustomer().then(done) }` |
| pages/index.vue:1517 | PosPaymentWorkspace | decision-confirm | `confirmCustomerDecision` |
| pages/index.vue:1518 | PosPaymentWorkspace | decision-cancel | `cancelCustomerDecision` |
| pages/index.vue:1519 | PosPaymentWorkspace | decision-merge | `mergeConflictCustomers` |
| pages/index.vue:1520 | PosPaymentWorkspace | decision-release | `releaseConflictContact` |
| pages/index.vue:1521 | PosPaymentWorkspace | decision-pick | `pickConflictCandidate` |
| pages/index.vue:1522 | PosPaymentWorkspace | search | `searchCustomers` |
| pages/index.vue:1523 | PosPaymentWorkspace | select-result | `selectCustomerResult` |
| pages/index.vue:1524 | PosPaymentWorkspace | clear-customer | `clearCustomer` |
| pages/index.vue:1525 | PosPaymentWorkspace | apply-customer-favorite | `applyCustomerFavorite` |
| pages/index.vue:1526 | PosPaymentWorkspace | apply-preference | `applyCustomerPreference` |
| pages/index.vue:1527 | PosPaymentWorkspace | repeat-customer-last-order | `repeatCustomerLastOrder` |
| pages/index.vue:1528 | PosPaymentWorkspace | pick-saved-address | `applySavedAddress` |
| pages/index.vue:1551 | PosTabBoard | open | `openTab` |
| pages/index.vue:1552 | PosTabBoard | request-association | `requestTabAssociation('start')` |
| pages/index.vue:1582 | PosOrderEntry | customer | `tabHeaderRef?.openCustomer()` |
| pages/index.vue:1583 | PosOrderEntry | fulfillment | `openFulfillmentHere` |
| pages/index.vue:1584 | PosOrderEntry | schedule | `openScheduleHere` |
| pages/index.vue:1585 | PosOrderEntry | complete | `completeOrderSetup` |
| pages/index.vue:1598 | PosProductGrid | add | `addProduct` |
| pages/index.vue:1599 | PosProductGrid | open-tab | `openTab` |
| pages/index.vue:1600 | PosProductGrid | find-customer | `(query: string) => tabHeaderRef?.openCustomer(query)` |
| pages/index.vue:1634 | PosCartPanel | increment | `(lineId) => setQty(lineId, lineQty(lineId) + 1)` |
| pages/index.vue:1635 | PosCartPanel | decrement | `(lineId) => setQty(lineId, lineQty(lineId) - 1)` |
| pages/index.vue:1636 | PosCartPanel | remove | `(lineId) => setQty(lineId, 0)` |
| pages/index.vue:1637 | PosCartPanel | restore | `restoreItem` |
| pages/index.vue:1638 | PosCartPanel | set-qty | `(lineId, qty) => setQty(lineId, qty)` |
| pages/index.vue:1639 | PosCartPanel | set-notes | `setLineNotes` |
| pages/index.vue:1640 | PosCartPanel | set-discount | `setLineDiscount` |
| pages/index.vue:1641 | PosCartPanel | prepare | `editing ? saveOrderEdit() : prepareCheckout()` |
| pages/index.vue:1642 | PosCartPanel | move | `openMoveWith` |
| pages/index.vue:1643 | PosCartPanel | fire | `fireTab` |
| pages/index.vue:1644 | PosCartPanel | pay | `payOnSheet` |
| pages/index.vue:1645 | PosCartPanel | auto-fire-settings | `navigateTo('/settings/kitchen')` |
| pages/index.vue:1646 | PosCartPanel | unfire | `unfireTab` |
| pages/index.vue:1647 | PosCartPanel | fire-lines | `(ids, complete) => fireTab(ids).then(complete)` |
| pages/index.vue:1648 | PosCartPanel | unfire-lines | `(ids, complete) => unfireSelected(ids).then(complete)` |
| pages/index.vue:1649 | PosCartPanel | request-tab | `requestTabAssociation('start')` |
| pages/index.vue:1656 | PosFunctionRail | board | `goToTabs` |
| pages/index.vue:1656 | PosFunctionRail | cash | `goToCashSession` |
| pages/index.vue:1656 | PosFunctionRail | display | `openCustomerDisplay` |
| pages/index.vue:1656 | PosFunctionRail | lock | `lock()` |
| pages/index.vue:1656 | PosFunctionRail | refresh | `refresh()` |
| pages/index.vue:1683 | PosFulfillmentModal | pick-saved-address | `applySavedAddress` |
| pages/index.vue:1684 | PosFulfillmentModal | open-schedule | `openScheduleHere` |
| pages/index.vue:1748 | PosTabPickerDialog | confirm | `openTabFromDialog` |
| pages/index.vue:1749 | PosTabPickerDialog | select | `openTabFromDialog` |
| pages/index.vue:1761 | PosDrawerLockDialog | update:open | `(value) => { if (!value) drawerLock.dismiss(); }` |
| pages/index.vue:1762 | PosDrawerLockDialog | manager | `drawerLock.askManager` |
| pages/index.vue:1771 | OperatorManagerAuth | update:open | `(value) => { if (!value) drawerLock.backToLock(); }` |
| pages/index.vue:1772 | OperatorManagerAuth | authorize | `drawerLock.unlock` |
| pages/index.vue:1773 | OperatorManagerAuth | authorize-badge | `drawerLock.unlockWithBadge` |
| pages/index.vue:1785 | PosCancelSaleDialog | confirm | `cancelRecentSale` |
| pages/index.vue:1786 | PosCancelSaleDialog | confirm-badge | `cancelRecentSaleWithBadge` |
| pages/index.vue:1793 | PosWeighedEntryDialog | confirm | `addWeighedProduct` |
| pages/index.vue:1794 | PosWeighedEntryDialog | cancel | `cancelWeighedPrompt` |
| pages/index.vue:1800 | PosProductOptionsDialog | confirm | `addOptionsProduct` |
| pages/index.vue:1801 | PosProductOptionsDialog | cancel | `cancelOptionsPrompt` |
| pages/index.vue:1831 | PosRecentSales | cancelled | `onExternalSaleCancelled` |
| pages/index.vue:1845 | PosOrderEditReview | update:open | `(isOpen: boolean) => { if (!isOpen) orderEdit.closeReview(); }` |
| pages/index.vue:1846 | PosOrderEditReview | retry | `saveOrderEdit` |
| pages/index.vue:1847 | PosOrderEditReview | confirm | `confirmOrderEdit()` |
| pages/index.vue:1857 | OperatorManagerAuth | update:open | `(isOpen: boolean) => { editManagerOpen = isOpen; }` |
| pages/index.vue:1858 | OperatorManagerAuth | authorize | `(username: string, pin: string) => confirmOrderEdit({ username, pin })` |
| pages/index.vue:1859 | OperatorManagerAuth | authorize-badge | `(badge: string) => confirmOrderEdit({ badge })` |
| pages/preorders/[ref].vue:140 | PosPreordersShell | refresh | `refreshPos(); refresh()` |
| pages/preorders/[ref].vue:325 | OperatorOrderDetail | comment | `submitComment` |
| pages/preorders/[ref].vue:334 | PosPreorderHandOverDialog | confirm | `confirmHandOver` |
| pages/preorders/[ref].vue:343 | PosPreorderRescheduleDialog | confirm | `confirmReschedule` |
| pages/preorders/[ref].vue:351 | PosPreorderCancelDialog | confirm | `(reason: string) => confirmCancel(reason)` |
| pages/preorders/[ref].vue:360 | OperatorManagerAuth | update:open | `(isOpen: boolean) => { if (!isOpen) actions.dismissManagerChallenge(); }` |
| pages/preorders/[ref].vue:361 | OperatorManagerAuth | authorize | `signWithPin` |
| pages/preorders/[ref].vue:362 | OperatorManagerAuth | authorize-badge | `signWithBadge` |
| pages/preorders/index.vue:341 | PosPreordersShell | refresh | `refreshAll` |
| pages/preorders/index.vue:504 | PosPreorderMoveMenu | other | `move.chooseOther(card)` |
| pages/preorders/index.vue:666 | PosPreorderMoveMenu | move | `(date) => move.moveTo(card, date)` |
| pages/preorders/index.vue:667 | PosPreorderMoveMenu | other | `move.chooseOther(card)` |
| pages/preorders/index.vue:743 | PosPreorderMoveMenu | move | `(date) => move.moveTo(card, date)` |
| pages/preorders/index.vue:744 | PosPreorderMoveMenu | other | `move.chooseOther(card)` |
| pages/preorders/index.vue:775 | PosCodeScanner | code | `onScannedOrder` |
| pages/preorders/index.vue:775 | PosCodeScanner | type | `searchField?.inputRef?.focus()` |
| pages/preorders/index.vue:788 | PosPreorderRescheduleDialog | confirm | `move.confirmDialog` |
| pages/session/closing.vue:382 | PosDenominationCounter | total-q | `drawerQ = $event` |
| pages/session/closing.vue:383 | PosDenominationCounter | progress | `(filled, total) => { drawerFilled = filled; drawerTotal = total; }` |
| pages/session/closing.vue:384 | PosDenominationCounter | note | `drawerNoteOpen = true` |
| pages/session/index.vue:557 | PosFunctionRail | board | `goToSaleBoard` |
| pages/session/index.vue:558 | PosFunctionRail | cash | `() => {}` |
| pages/session/index.vue:559 | PosFunctionRail | display | `openCustomerDisplay` |
| pages/session/index.vue:560 | PosFunctionRail | lock | `lock()` |
| pages/session/index.vue:561 | PosFunctionRail | refresh | `refresh()` |
| pages/session/index.vue:606 | PosSessionTile | select | `selectTile` |
| pages/session/index.vue:637 | PosSessionTile | select | `selectTile` |
| pages/session/index.vue:650 | PosSessionTile | select | `selectTile` |
| pages/session/index.vue:669 | PosSessionTile | select | `selectTile` |
| pages/session/index.vue:675 | PosFunctionRail | board | `goToSaleBoard` |
| pages/session/index.vue:675 | PosFunctionRail | display | `openCustomerDisplay` |
| pages/session/index.vue:675 | PosFunctionRail | lock | `lock()` |
| pages/session/index.vue:733 | PosDenominationCounter | total-q | `openingAmount = formatAmountInput($event)` |
| pages/session/index.vue:1235 | PosDenominationCounter | total-q | `closingAmount = formatAmountInput($event)` |
| pages/session/index.vue:1277 | OperatorManagerAuth | authorize | `onManagerAuthorize` |
| pages/session/index.vue:1278 | OperatorManagerAuth | authorize-badge | `onManagerBadge` |
| pages/session/report.vue:101 | PosCashReadingCard | reprint | `reprint` |
| pages/session/report.vue:121 | PosCashReadingCard | reprint | `reprint` |
| pages/settings/card-machines.vue:70 | UiDialog | update:open | `(value) => { if (!value) editing = null; }` |
| pages/settings/seating.vue:275 | PosFunctionRail | board | `navigateTo('/')` |
| pages/settings/seating.vue:276 | PosFunctionRail | cash | `navigateTo('/session')` |
| pages/settings/seating.vue:277 | PosFunctionRail | display | `openCustomerDisplay` |
| pages/settings/seating.vue:278 | PosFunctionRail | lock | `lock()` |
| pages/settings/seating.vue:279 | PosFunctionRail | refresh | `refreshPos()` |
| pages/settings/seating.vue:392 | PosSeatingList | select | `selectFromList` |
| pages/settings/seating.vue:393 | PosSeatingList | add | `addFromList` |
| pages/settings/seating.vue:395 | UiSheet | update:open | `(value) => (sheetOpen = value)` |
| pages/settings/seating.vue:411 | PosSeatingSpotPanel | update | `(patch) => seating.update(seating.selected.value!.key, patch)` |
| pages/settings/seating.vue:412 | PosSeatingSpotPanel | rotate | `seating.rotate(seating.selected.value!.key)` |
| pages/settings/seating.vue:413 | PosSeatingSpotPanel | duplicate | `seating.duplicate(seating.selected.value!.key)` |
| pages/settings/seating.vue:414 | PosSeatingSpotPanel | remove | `removeSelected` |
| pages/settings/seating.vue:427 | PosSeatingPalette | grab | `onGrab` |
| pages/settings/seating.vue:428 | PosSeatingPalette | select-area | `(name) => (activeArea = name)` |
| pages/settings/seating.vue:429 | PosSeatingPalette | add-area | `onAddArea` |
| pages/settings/seating.vue:437 | PosSeatingPalette | grab | `onGrab` |
| pages/settings/seating.vue:438 | PosSeatingPalette | select-area | `(name) => (activeArea = name)` |
| pages/settings/seating.vue:439 | PosSeatingPalette | add-area | `onAddArea` |
| pages/settings/seating.vue:440 | PosSeatingPalette | add-fixture | `onAddFixture` |
| pages/settings/seating.vue:450 | PosSeatingPlan | select | `(key) => (seating.selectedKey.value = key)` |
| pages/settings/seating.vue:451 | PosSeatingPlan | move-start | `seating.checkpoint()` |
| pages/settings/seating.vue:452 | PosSeatingPlan | move | `onMove` |
| pages/settings/seating.vue:453 | PosSeatingPlan | rotate | `seating.rotate` |
| pages/settings/seating.vue:454 | PosSeatingPlan | fixture-move-start | `seating.checkpoint()` |
| pages/settings/seating.vue:455 | PosSeatingPlan | move-fixture | `seating.moveFixture` |
| pages/settings/seating.vue:456 | PosSeatingPlan | rotate-fixture | `seating.rotateFixture` |
| pages/settings/seating.vue:457 | PosSeatingPlan | remove-fixture | `seating.removeFixture` |
| pages/settings/seating.vue:458 | PosSeatingPlan | pinch | `onPinch` |
| pages/settings/seating.vue:476 | PosSeatingSpotPanel | update | `(patch) => seating.update(seating.selected.value!.key, patch)` |
| pages/settings/seating.vue:477 | PosSeatingSpotPanel | rotate | `seating.rotate(seating.selected.value!.key)` |
| pages/settings/seating.vue:478 | PosSeatingSpotPanel | duplicate | `seating.duplicate(seating.selected.value!.key)` |
| pages/settings/seating.vue:479 | PosSeatingSpotPanel | remove | `removeSelected` |
| pages/settings/seating.vue:536 | PosFunctionRail | board | `navigateTo('/')` |
| pages/settings/seating.vue:536 | PosFunctionRail | cash | `navigateTo('/session')` |
| pages/settings/seating.vue:536 | PosFunctionRail | display | `openCustomerDisplay` |
| pages/settings/seating.vue:536 | PosFunctionRail | lock | `lock()` |
