# WP-OPERADOR-NUXTUI-ONDAS: a migração dos 8 apps de operador para Nuxt UI, em ondas

- **Data:** 08/10/2026.
- **Molde:** o Gestor (`surfaces/orders-nuxt`), Nuxt UI 4.11.3 tematizado uma vez em `surfaces/operator-kit/app/app.config.ts`. Pilha #1518 a #1528, em rascunho.
- **Base medida:** `e79ed522d` = #1528 (`claude/gestor-avisos-com-prazo`) + #1521 (`#below`). O `main` ainda não tem a pilha.
- **Brief:** `docs/plans/WP-OPERADOR-NUXTUI-ONDAS-brief.md` (#1529). **Laudo do Gestor:** `docs/plans/WP-GESTOR-CANON-LAUDO.md` (#1523).
- **Anexos (inventário por leitura de código, com arquivo:linha):** [PDV](WP-OPERADOR-NUXTUI-ONDAS/inventario-pos-nuxt.md) · [Produção](WP-OPERADOR-NUXTUI-ONDAS/inventario-production-nuxt.md) · [Marketing](WP-OPERADOR-NUXTUI-ONDAS/inventario-marketing-nuxt.md) · [Compras e B.I.](WP-OPERADOR-NUXTUI-ONDAS/inventario-purchase-bi.md) · [Cozinha, Central e Kitchen Sink](WP-OPERADOR-NUXTUI-ONDAS/inventario-kds-hub-kitchensink.md) · [Grafo do kit e onda 0](WP-OPERADOR-NUXTUI-ONDAS/inventario-kit-grafo.md).
- **Prompts das próximas sessões:** [WP-OPERADOR-NUXTUI-ONDAS-prompts.md](WP-OPERADOR-NUXTUI-ONDAS-prompts.md).

## Como ler

**Nível de prova:** **[tela]** visto no navegador (build de produção contra o mock do app, Chromium 1243, o mesmo da trava da CI); **[teste]** saída de vitest ou Playwright rodada na sessão; **[CI]** check do GitHub; **[código]** leitura com arquivo:linha, sem rodar.

**Severidade:** P0 perde função ou mente ao operador; P1 fuga do cânon que se espalha; P2 polimento.

## 1. O que já está decidido e não se reabre

- **Data, hora e período:** `UiDateField`, `UiDateRangeField`, `UiTimeField`, `UiTimeRangeField`, `UiDateTimeField` (camada fina sobre `InputDate`, `InputTime`, `Calendar`). Nunca `type="date|time"`.
- **Menu ⋯:** `DropdownMenu`. **Aviso com prazo:** `OperatorUrgentAlert`. **Toast:** `useToast` no kit; o `OperatorSonner` morre quando o último app migrar.
- **Destaque do item da vez:** `PageCard highlight` ou `data-highlight` no `NuxtCard`. Cartão com a altura do próprio conteúdo. Tabela integrada ao card.
- **Live Status:** o contrato escrito é o do `operator-kit/README.md:422`: "o ponto ao vivo com a hora; fora do ao vivo o estado se escreve por extenso". O "On/Off" verde da pilha não tem decisão escrita (P0-5 do laudo). A volta ao contrato está na pergunta 2 da seção 8, só para confirmar.
- **Lista curta:** `UiNativeSelect`, por decisão escrita do dono em 10/09 (`README.md:808`), até ele responder a pergunta 1 da seção 8. O Gestor usou `NuxtSelect`; nenhum outro app troca antes da resposta.
- **O kit muda por opt-in.** Peça ou variante nova até cada app migrar. Mudança de comportamento compartilhado só no PR que também migra ou confere os 9 consumidores. Isto fecha a pergunta 3 do laudo (o brief a respondeu).
- **Quem recebe aviso é a pessoa logada, pelas permissões.** O financeiro panorâmico (caixa, contagem, totais do dia) só o dono vê.

## 2. Inventário por app (resumo; o detalhe está nos anexos)

| App | Telas | Gestos | Atalhos · tempo real | Peças do kit (mais usadas) | Locais | Escapes do cânon (principais) | Travas que quebram | Mock |
|---|---|---|---|---|---|---|---|---|
| **B.I.** `bi-nuxt` | 8 rotas (81 a 467 linhas) | ~30; 1 POST de negócio (levar ao plano) e o CRUD de cenários | `[` `]` `/`; sem SSE nem poll | `OperatorPageHeader` 8, `OperatorPeriodPicker` 2 (6 telas), `UiDateField` 3, `UiNativeSelect` 8, `UiFilterChip` 4 | 19 (os gráficos em CSS ficam) | 21 `<button>`, 8 `<table>`, 5 menus à mão, 1 overlay à mão, 20+ cartões por classe | nenhuma trava de template; `guardrails.appBar` (lista "migrados"); ledger com variantes fictícias | **não**; a frente P.1 grava as fixtures do seed |
| **Compras** `purchase-nuxt` | 1 rota, 4 vistas por estado, página de 2.868 linhas | 13 POSTs, câmera/QR, foto, chave da NF | `?view=receive`; sem SSE | `UiNativeSelect` 9, `UiFilterChip` 5, `UiSheet` 4, `OperatorDayPicker` 2 | 9 | 132 controles crus (teto do ledger), 4 `<table>`, 47 arbitrários | `v6-conformidade` (17 `it` de string), `camada-visual-da-suite` | **não**; precisa de mock com estado e de `export_purchase_schema` |
| **Marketing** `marketing-nuxt` | 9 rotas + 2 da matriz | 124; 10 famílias de diálogo | R em 5 telas, N em Campanhas; poll | `UiButton` 82, `UiDialog` 8, `UiDateTimeField` 4, `UiCheckboxGroup` 14 | 20 | 14 `:ui=` (todos no `UiCheckboxGroup`), 28 crus, 121 arbitrários, 8 campos numéricos sem `InputNumber` | 82 baselines (só a CI regera); `sectionBar.test` exige `data-suite`; harness sem runtime Nuxt (`uiPrimitives.ts`, 550 linhas de dublê) | sim (`mock_backend.py`, matriz visual) |
| **Central** `hub-nuxt` | 1 (`app.vue`, 640 linhas) | 24 | poll de 30 s; push | `OperatorSuiteRail`, `OperatorPhoneMenu`, `OperatorAppSeal` | 0 | cabeçalho à mão, 3 `<button>` (teto), 19 arbitrários; ponto verde "ao vivo" fixo sem SSE | `guardrails.appBar` exige `OperatorSuiteRail` no `app.vue`; `mobileTiles.spec` (provável vermelho: sem `data-tile-title`) | sim (tiles fixos) |
| **Kitchen Sink** `kitchensink-nuxt` | 1 (o catálogo do kit) | 30 | nenhum | monta o kit inteiro | 0 | 13 contradições entre doc e código; `>` literal na barra de ação (já no `main`); dois toasters | matriz SSR, a11y e geometria | não precisa de backend |
| **Produção** `production-nuxt` | 14 rotas | dezenas; toque longo de 550 ms, duplo toque de 600 ms, 3 numpads, timers locais | Alt+1..5, `/`, R, `?`; **sem SSE por decisão (WP-PE4)**, 8 polls | `UiButton` 96, `UiNativeSelect` 18, `UiDialog` 14, `OperatorPeriodPicker` 6 | 18 (`ProductionStageGrid` com 2.442 linhas) | 90 `<button>`, 14 `<table>`, 2 menus e 1 listbox à mão, 74 arbitrários | `v6Conformity`, `QcCloseScreen` (13 classes), `nativeUiStubs.ts`, `KNOWN_INERT` | sim, parcial: receitas, timers e diálogos da grade sem fixture |
| **Cozinha** `kds-nuxt` | 3 rotas (inclui o painel público `/pickup`) | 41 | `/`; SSE, som, fanfarra; tela sempre ligada | `OperatorPageHeader`, `UiFilterChip` 3, `OperatorSuiteSearch` | 9 | 24 `<button>` (teto), 28 arbitrários | `KdsTicketCard.test` crava classes; `KdsTicketModal.test` com dublê de `UiDialog`; exceção do `/` em `operator-global-shortcut-exceptions.json` | sim, mas o `/pickup` pede `/kds/pickup/` e o mock responde `/kds/cliente/` |
| **PDV** `pos-nuxt` | 13 + 4 redirecionamentos | 381 disparos vivos + 306 por evento; 41 diálogos | 8 ouvintes próprios; SSE `/sse/cash`, `/sse/tabs`, `/sse/orders` + `BroadcastChannel` (Tela do cliente) | `UiButton` 187, família `UiDialog*` 151, `OperatorManagerAuth` 6 | 55 (2 órfãos) | 156 `<button>`, 8 `<table>`, 4 `alertdialog` inline, 38 spinners à mão, `vue-sonner` em 21 arquivos | ~10 travas de fonte (`v6Conformidade`, `receiptPrint`, `railPreorders`…); `falhaComSaida` só reconhece `toast.error` | parcial: só `/preorders` (visual) e o login (e2e); 11 telas sem fixture |

**Defeitos achados no inventário, fora do cânon, para o dono da frente de cada app:**

- **Marketing:** o "Reagendar" dos Agendados manda `?action=reschedule_announcement`, que o `assertRecoveryAction` não aceita (lança `unsupported_marketing_recovery_action`), e nenhum teste cobre. [código]
- **Marketing:** no celular, Decisões e Agendados não mostram o ⋯ com "Atualizar"; só a tecla R. [código]
- **B.I.:** "Apagar" cenário salvo sem confirmação (`explore.vue:233-238`). [código]
- **Cozinha:** o painel público `/pickup` sempre renderiza vazio no mock. [código]
- **Kit:** o título do `OfflineBanner.vue:27` tem travessão, contra a regra de copy. [código]

## 3. Grafo de dependência kit → app

Cada app só migra quando as peças do kit que ele usa já são canônicas **e opt-in**. A tabela diz que PR da onda 0 cada app espera.

| PR da onda 0 | B.I. | Compras | Marketing | Central | Kitchen Sink | Produção | Cozinha | PDV |
|---|---|---|---|---|---|---|---|---|
| 0.1 Herança verde | herda | herda | herda | herda | herda | herda | herda | herda |
| 0.2 Guard de slot + marcador de opt-in | precisa | precisa | precisa | precisa | precisa | precisa | precisa | precisa |
| 0.3 Período e data (`Ui*`) | **precisa** (6 telas) | | precisa (`UiDateTimeField` com limite) | | precisa | **precisa** (6 usos) | | precisa (1) |
| 0.4 Toast no kit | precisa (1 ação) | precisa | precisa (31) | | precisa | precisa (ação "Atualizar") | precisa | precisa (102 chamadas) |
| 0.5 Live Status | precisa | precisa | precisa | precisa | precisa | **precisa** (`late`) | **precisa** (`calm`) | precisa |
| 0.6 Aviso urgente montável | | | pode ligar | | precisa | pode ligar | **decisão**: interromper a cozinha? | |
| 0.7 Cabeçalho opt-in | **precisa** (dois seletores de período no desktop) | precisa (`#below`) | precisa (`#below`) | | precisa | precisa | precisa | precisa |
| 0.8 Busca opt-in (`inline`) | precisa | precisa | precisa | precisa | | **precisa** (lupa com 2 toques) | **precisa** (`/` cobre a grade) | precisa |
| 0.9 Barra e Avisos rotulados | herda | herda | herda | herda | | herda | herda | herda |
| 0.10 Rail com `NavigationMenu` | troca o shell | troca | troca | troca | demonstra | troca | troca | troca |
| 0.11 Hydration | precisa (SSR) | | | **precisa** (`railShown` fora de `ClientOnly`) | precisa | | | precisa |

"Precisa" = a migração do app não fecha sem o PR. "Herda" = o PR devolve ao app o que a pilha tirou. "Troca" = o app sai de `*Nav.vue` + `OperatorSuiteRail` para o shell canônico quando o PR existir; antes disso, o app migra o **conteúdo** e mantém o shell.

## 4. As ondas

### Onda 0: só kit, serial

Regra: **um PR por vez tocando `surfaces/operator-kit`**. Cada um roda o vitest do kit e dos 9 apps (a CI do #1519 provou que o kit verde não prova nada) e traz captura antes e depois de cada app tocado, nas 5 larguras, claro e escuro, pelo harness da seção 7.

| PR | O que muda | Opt-in? | Trava nova | Estado |
|---|---|---|---|---|
| **0.1 Herança verde** | Login (o erro descreve os dois campos e o `aria-invalid` volta a ser real), PIN do gerente (o marcador volta ao `DialogContent`; a trava da gaveta do PDV volta a vê-lo), `FilterBar` e `UiFilterChip` com alvo de 44 px e contagem à parte, degrau de 48 px no tablet (só no token opt-in), `--primary-ink` (AA do latão `soft`), `alt=""` no selo, envelope de toque do catálogo | volta ao `main` | os testes do Login sobem do Marketing para o kit, contra o Nuxt UI real; duas travas reescritas com o motivo | seção 9 |
| **0.2 Guard de slot + marcador** | teste que compila cada consumidor e compara `<template #x>` com `<slot name>` da peça (pega o próximo `#below`); `app.config` do app com `operatorKit: { canon, toaster, search }` e `data-operator-canon` no `<html>`, para os overlays em portal herdarem o modo | é a fundação do opt-in | o guard; "todo app declara o modo" | a fazer |
| **0.3 Período e data** | `OperatorPeriodPicker` volta a `UiDateRangeField`/`UiDateField` (mantém o `NuxtPopover` e as `NuxtTabs` da pilha); `UiDateTimeField` com a hora-limite; `FilterBar date-range` sem nativo | correção (decidido no brief) | `kitOwnership` varre `operator-kit/app` e casa `NuxtInput`/`UInput`/`UiInput` com `type="date\|time\|datetime-local\|month\|week"`; `OperatorDatePickers.test` volta ao componente | seção 9 |
| **0.4 Toast no kit** | `operatorToast` (o shim do Gestor sobe) com `description` e `action`; destino por `operatorKit.toaster` (`nuxt-ui` ou `sonner`); `OperatorUrgentAlert` passa a usá-lo | sim | teste do shim nos dois destinos e nas 5 chamadas de dois argumentos (Produção 3, Compras 1, B.I. 1) | a fazer |
| **0.5 Live Status** | volta ao contrato do README:422: `live` ponto e hora, `calm` neutro, `late` âmbar, `off` vermelho, estado por extenso em pt-BR; o `NuxtBadge` fica | correção, depois do "sim" do dono (pergunta 2) | `SuiteChrome.test` e `canonicalPilot` exigem os 4 tons; o vocabulário proíbe "On"/"Off" visíveis | espera o dono |
| **0.6 Aviso urgente montável** | `OperatorUrgentAlert` sai do `OperatorSuiteShell` para uma peça que o app monta (em `ClientOnly`); o som é decisão do dono | sim (o app liga) | o aviso com prazo abre o modal e lembra, nos dois toasters | depois de 0.4 |
| **0.7 Cabeçalho opt-in** | sem `canon`: `#phone-actions` só no celular, `#actions` rolável no celular, `#subtitle` embaixo do título | sim | guard 0.2 + teste dos dois modos | depois de 0.2 |
| **0.8 Busca opt-in** | `OperatorSuiteSearch mode="inline"` (padrão até migrar) com `NuxtInput` + `NuxtPopover` + `NuxtCommandPalette`; `dialog` para o Gestor | sim | "digitar filtra sem abrir modal" | depois de 0.2 |
| **0.9 Barra e Avisos rotulados** | `OperatorSectionBar` e `OperatorInbox` no rail com rótulo para quem não é `canon` (P1-5: "Avisos" virou sino sem rótulo) | sim | matriz visual do rail do PDV | depois de 0.2 |
| **0.10 Rail canônico** | `OperatorSuiteNavigation`: `NuxtNavigationMenu vertical collapsed` com rótulo e chip pelo **tema** (`compoundVariant`, nunca `:ui=`); o `OperatorSuiteShell` passa a usá-lo; os 7 trocam um por vez | sim | teste montado do rail (rótulo visível, chip, `aria-current`) | depois de 0.4 e 0.9 |
| **0.11 Hydration** | medir antes com `__VUE_PROD_HYDRATION_MISMATCH_DETAILS__`; candidatos: `useSuiteRailShown` fora de `ClientOnly` (Central `app.vue:607`), hora do SSR sem fuso (`orders-nuxt/.../index.vue:118`) | correção | e2e que reprova "Hydration" no console, por app | a fazer |
| **0.12 Faxina** | apagar as órfãs: `OperatorAppBar`, `RailToggle`, `OperatorRail`, `RailItem`, `OperatorCapacityStatus`, `QueueColumnStrip`, `QueueColumnResizeHandle`, `UiSearchInput` e os testes delas | n/a | nenhuma | a qualquer momento |
| **0.13 BFF** | o `Set-Cookie` sem `Domain`/`Secure` em loopback (D21 do anexo do kit) entrou num PR de UI; vai para PR próprio, com nome e teste | n/a | `djangoProxy.test` | a qualquer momento |

Dependências: 0.1 → 0.2; 0.3 e 0.12 independem; 0.4 → 0.6; 0.7, 0.8 e 0.9 dependem de 0.2; 0.10 vem depois de 0.4 e 0.9; 0.5 espera o sim do dono. O Kitchen Sink (o catálogo) muda **no mesmo PR** que muda a peça: a doc do cânon não pode atrasar.

### Ondas 1 a 6: os apps

A ordem segue três critérios: risco (o app escreve dinheiro ou estoque, ou interrompe o chão?), uso no balcão (quantas pessoas tocam por hora) e dependência do kit (quanto da onda 0 o app precisa).

| Onda | App | Por quê | Depende de | Paralelo com |
|---|---|---|---|---|
| **1** | **B.I.** (piloto) | escritório; leitura pura; 8 telas pequenas, um PR por grupo de telas; maior consumidor de período (prova 0.3 e 0.7 em tela); mock barato e com contrato (schema exportado) | 0.1, 0.3, 0.7; o shell troca em 0.10 | a onda 0 (o piloto migra o conteúdo enquanto o kit anda) |
| **2a** | **Compras** | escritório, mas escreve estoque, custo e preço; antes, quebrar a página de 2.868 linhas sem mudar markup | 0.2, 0.4, 0.7 | 2b |
| **2b** | **Marketing** | escritório; contrato factual próprio (`marketing-surface-contract.md`), CSP opt-in, 82 baselines que só a CI regera (uma sessão só) | 0.3, 0.4, 0.7 | 2a |
| **3** | **Central** + **Kitchen Sink** | a Central é uma tela e a porta da suíte; prova o rail e o cabeçalho canônicos num app sem domínio. O Kitchen Sink anda junto com a onda 0; aqui fecha as 13 contradições | 0.10, 0.11 | entre si |
| **4** | **Produção** | chão, tablet, kiosk, timers locais, toque longo; 14 telas; a grade de 2.442 linhas é fatiada antes | 0.3, 0.4, 0.5 (`late`), 0.8 | a onda 5, depois do PR de shell da Produção |
| **5** | **Cozinha** | chão, posto, som, fanfarra, tela sempre ligada; pequeno (3 telas), mas não pode errar; usa as peças de chão já provadas na Produção | 0.5 (`calm`), 0.8 e a decisão do aviso urgente | a Produção, depois do shell |
| **6** | **PDV** | o maior (381 disparos), dinheiro, impressão, maquininha, PIN e gaveta; por último, com todas as peças provadas | todas | nenhuma |

### Por app

| App | O que muda | O que sobe para o kit | Trava nova | Pronto em tela | Frentes (PRs) |
|---|---|---|---|---|---|
| B.I. | `Ui*` e HTML → `NuxtCard`, `NuxtTable`, `NuxtBadge`, `NuxtButton`, `NuxtDropdownMenu`, `NuxtAccordion`, `NuxtAlert`, `NuxtSkeleton`; listas curtas pela pergunta 1; `BiPeriodChip` morre (variante do `OperatorPeriodPicker`); os gráficos em CSS ficam | `StatTile`, `BiShareButton`, o menu de exportar CSV, `BiDayStepper` (como `OperatorDayStepper`) | guard de template do B.I. (sem `<button>`, `<table>` ou `role="menu"` cru) e o ledger com as variantes reais | 8 telas, 5 larguras, claro e escuro, ⋯ e período abertos, vazio e erro | 5: mock, 3 de telas, shell |
| Compras | quebrar `index.vue` (sem mudar markup, com retrato antes); migrar Base → Comprar → Painel → Receber | o menu do pedido (DropdownMenu), `useCodeScanner` (duplicado com a Produção) | `export_purchase_schema` + teste de deriva; o `v6-conformidade` vira guard de componente | 4 vistas, câmera simulada, recebimento com divergência | 6 |
| Marketing | `UiCheckboxGroup` sem `:ui=`; 8 `InputNumber`; 3 segmentados à mão → `NuxtTabs`/`RadioGroup`; `MarketingPageMenu` → `DropdownMenu`; decidir o `MarketingBoard` antes | `MarketingSettingsNav`, `MarketingWorkspaceDialog` | harness com `mountSuspended` no lugar dos dublês; CSP medida, não `bypassCSP` | as 9 rotas + `/second-control`; baselines regeradas pela sessão da CI | 6 |
| Central | cabeçalho à mão → `OperatorPageHeader`; ponto verde fixo → Live Status real (o poll de 30 s é `calm`) | nada | `mobileTiles.spec` volta a medir com `data-tile-title` | tiles a 390 em duas colunas iguais; offline | 2 |
| Kitchen Sink | fechar as 13 contradições; demonstrar `OperatorSuiteShell`, `OperatorPageHeader`, `OperatorLiveStatus`, `OperatorSuiteSearch` e `UiDate*` montados (hoje o guard passa porque o nome aparece no léxico) | é o próprio catálogo | `catalog.guardrails` por renderização, não por string | matriz verde no Chromium da CI | 2 |
| Produção | fatiar `ProductionStageGrid`; `ProductionHeader` + `RecipeHeader` num cabeçalho só; 2 menus e 1 listbox à mão → `DropdownMenu`/`SelectMenu`; `IngredientPicker` → `InputMenu`; progresso → `NuxtProgress` | `useCodeScanner` + `LotLabelScanner`, `useAdaptivePoll` | os gestos frágeis viram e2e (toque longo, duplo toque, o `[role=dialog][data-state=open]` que pausa atalhos, `data-production-timer-dialog`) | 14 telas, tablet deitado de toque, Letreiro escuro, impressão de etiqueta | 8 |
| Cozinha | card de 2 toques mantido; `/` inline; `calm` neutro; Teleport do botão para o polegar; fanfarra | nada | `KdsTicketCard`/`KdsTicketModal` contra o Nuxt UI real; `/pickup` com a fixture certa | estação, pickup público, som bloqueado, offline | 3 |
| PDV | por último; fixtures das 11 telas primeiro; a comanda vira `NuxtDrawer` só se os atalhos continuarem pausando | `PosAddressAutocomplete`, `PosCodeScanner`, `PosTerminalHealth`, `PosDenominationCounter` | `falhaComSaida` reconhece `useToast`; as ~10 travas de fonte viram guard de componente | venda, caixa, fim do dia, Ajustes, Tela do cliente, impressão | 10 |

## 5. Coordenação

- **Mudança de kit é serial.** Só uma sessão por vez tem PR aberto tocando `surfaces/operator-kit`. Ela se declara no título (`(onda 0.N)`) e o próximo PR de kit empilha sobre ele.
- **Migração de app é paralela.** Uma frente = um app = um branch = um PR por grupo de telas. Uma sessão por app. Apps diferentes rodam ao mesmo tempo; o mesmo app, nunca.
- **O app não edita o kit.** Precisou de peça nova: abre o PR de kit (serial) e empilha o app sobre ele. Copiar a peça para o app é proibido (herança).
- **Empilhamento:** enquanto a pilha do Gestor (#1518 a #1528) não entra no `main`, a onda 0 empilha sobre `#1528 + #1521`; depois, sobre o `main`. O título diz sobre o que está empilhado. O PR de app empilha sobre o último PR de kit de que depende.
- **Retratos e baselines:** só a sessão com o Chromium da CI regera. Nenhuma frente de app regera baseline de outro app.
- **Gestor:** `surfaces/orders-nuxt` é da sessão dona do Gestor. O que a onda 0 pede dele (o ledger reprova 7 arquivos com `NuxtDashboardToolbar`/`NuxtNavigationMenu` diretos; o ⋯ em `NavigationMenu`) vai como mensagem para ela e no PR dela, não como commit daqui.
- **Relatório de cada sessão** (no PR e no chat do dono, em elevator pitch): o que mudou; os gestos conferidos (antes e depois, com arquivo:linha); as capturas (5 larguras, claro e escuro, diálogos abertos); a CI do app **e dos vizinhos**; o que não foi verificado, com nome e motivo; o estado do PR (mergeado, na fila, vermelho com a causa, rascunho esperando decisão).

## 6. Critério de pronto de cada app

1. Só componente oficial do Nuxt UI, tematizado no `app.config.ts` do kit. Nada de `:ui=` por instância, HTML cru, input nativo de data ou hora, classe que imita componente, arbitrário sem motivo escrito ou primitiva paralela.
2. Omotenashi: a tela diz o que fazer e já traz a ação (`omotenashi-copy.md`, `suite-vocabulary.md`).
3. Herança: o que serve a outro sobe para o kit.
4. Zero regressão: o inventário do anexo, conferido gesto a gesto depois, com arquivo:linha dos dois lados.
5. Visto em tela: antes e depois em 390, 768, 1024, 1280 e 1440, claro e escuro, diálogos e overlays abertos, estados carregando, vazio, erro, offline e sessão expirada, teclado e foco.
6. CI verde do app e dos vizinhos. Mudança no kit só sai com a CI dos 9 verde.

## 7. Método de prova

- **Harness de captura** (o mesmo para os 9 apps): build de produção (`nuxt build` com `SHOPMAN_ENVIRONMENT=test`, `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1` e `NUXT_DJANGO_BASE_URL` apontando para o mock) e `node .output/server/index.mjs`; Playwright puro com o Chromium 1243 (o da trava da CI); 5 larguras × claro e escuro (a chave `<app>-color-mode` no `localStorage`); cenários com passos (abrir o popover, o diálogo); relatório JSON com o console de cada captura (hydration, 500, 403). Antes e depois saem de duas worktrees (a base e o branch), com os `node_modules` ligados por symlink. O script está no PR 0.1 (`surfaces/operator-kit/visual/capture-before-after.mjs`).
- **Mock incompleto esconde defeito** (foi o 500 do Gestor): cada app ganha mock com fixtures gravadas do seed antes da migração (Django local, banco novo com `seed`, leitura pelo cliente de teste com operador autenticado).
- **Dublê fiel ou componente real.** O teste de componente monta com `mountSuspended` (Nuxt UI real). Dublê escrito à mão só se lançar onde o real lança.

## 8. Decisões que são do dono

1. **Lista curta:** (1) `UiNativeSelect` nativo, como decidido em 10/09; (2) `NuxtSelect` em tudo, como o Gestor fez.
2. **Live Status:** volta ao contrato do README (ponto e hora quando ao vivo; "Atualiza a cada 60 s" ou "Sem conexão" por extenso; âmbar quando atrasado)? (sim/não)
3. **Aviso urgente na Cozinha:** o modal com prazo interrompe a tela da cozinha? (sim/não)
4. **Gráficos do B.I.:** (1) os gráficos em CSS ficam (leves, acessíveis, testados); (2) passam a `@unovis/vue` por peça do kit.
5. **`MarketingBoard`** (597 linhas, só em `/__visual_board`, sustenta 12 baselines): morre? (sim/não)

## 9. Estado da execução

Em 08/10/2026, ao fechar a sessão que escreveu este plano. A pilha é linear, cada PR sobre o anterior: #1528 + #1521 → **#1531** → **#1532** → **#1534** → **#1535** → **#1536**. O #1533, do Gestor, empilha sobre o #1534.

| Frente | PR | Estado | O que falta |
|---|---|---|---|
| 0.1 Herança verde | #1531 | aberto, empilhado sobre o #1528 (base `claude/gestor-avisos-com-prazo`) | sair da pilha quando o dono tirar o #1518 a #1528 do rascunho; a CI do PR é a primeira prova remota |
| 0.1b `OperatorToolbar` | #1532 | aberto, sobre o #1531 | o Gestor já troca os 5 usos no #1533 |
| 0.3 Período e data | #1534 | aberto, sobre o #1532 | o período aberto no PDV e na Produção não foi visto em tela |
| Gestor: toolbar + `ChannelPeriodCalendar` | #1533 | da sessão do Gestor, sobre o #1534 | ledger sem erro no orders (dito pela sessão do Gestor) |
| Piloto B.I. P.1, mock | #1535 | rascunho, sobre o #1534 | rodar o `bi.spec.ts` |
| Piloto B.I. P.2, conteúdo | #1536 | rascunho, sobre o #1535 | ver o PR: gestos não exercidos e pedidos ao kit |
| 0.2, 0.4 a 0.13 | nenhum | a fazer | a próxima peça é a **0.2**; ver o handoff |
| Ondas 2 a 6 | nenhum | a fazer | prompts em `WP-OPERADOR-NUXTUI-ONDAS-prompts.md` |
| `ActionList` do Gestor para o kit | nenhum | combinado com a sessão do Gestor, na fila depois do 0.3 | entra como PR de kit serial |

Achados desta sessão que viraram correção:
- o Login perdia o `aria-invalid` e a descrição do erro;
- o marcador do PIN do gerente saiu do diálogo, e o Esc da gaveta do PDV passava a roubar a tecla;
- as Tabs do período ativavam no foco e escolhiam "Dia" sozinhas;
- o `UiDateRangeField` quebrava o "mm" em duas linhas a 390 px;
- o foco da tabela integrada era cortado pelo card.

Um achado anterior à pilha ficou registrado e não foi corrigido: o `BiDayStepper` passava um slot `#trigger` que o `UiDateField` não declara. É a mesma classe do `#below`, e o guard de slot do 0.2 o pega.

## 10. O que não foi verificado

- **CI remota dos #1531, #1532 e #1534:** não acompanhada até o fim nesta sessão. A prova é local:
  - vitest dos 10 projetos;
  - matriz do Kitchen Sink com 48 passando e 0 falhando, no Chromium 1243;
  - 160 pares de captura antes e depois.
- **Matriz Playwright AA da Produção:** não rodada local. As duas causas novas da pilha (o contraste do "Mais" e o `alt` do selo) foram corrigidas no #1531. As 14 falhas de `showPicker` já existiam no `main`.
- **Safari e Firefox:** não abertos. O risco é o popover dentro de popover do período.
- **Leitor de tela real:** não usado. A acessibilidade foi conferida pelo DOM e pelo axe da matriz.
- **Offline e sessão expirada:** não simulados em nenhum app.
- **PDV fora de /preorders e do login:** sem fixture no mock. Venda, caixa, Ajustes e Tela do cliente não foram vistos.
- **Compras, além do login:** o app não tem mock.
- **Hydration mismatch:** aparece na Central, no Gestor e no B.I., igual antes e depois. O nó não foi medido; fica para o PR 0.11.
- **Gestos do B.I. não exercidos:** download do CSV, Web Share, o POST de levar ao plano, salvar, favoritar e apagar cenário, e Tentar de novo. O detalhe está no #1536.
