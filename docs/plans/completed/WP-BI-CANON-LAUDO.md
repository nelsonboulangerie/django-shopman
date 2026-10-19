# Laudo adversarial: por que o B.I. "ainda está bem cru"

Data: 08/10/2026. Revisor somente leitura (nada commitado, nada editado no repositório).

**Refs julgadas**
- B.I.: `claude/operador-nuxtui-bi-p2-conteudo` @ `212fb7508` (base `origin/claude/operador-nuxtui-onda0-periodo` @ `717ea7f70`). Caminhos abaixo relativos a `surfaces/bi-nuxt/app/`.
- Gestor e Kitchen Sink: `origin/claude/gestor-toolbar-calendario` @ `80ed58d54`. O `operator-kit` é **o mesmo** nas duas refs (diff só em `tests/kitOwnership.guardrails.test.ts`), então toda diferença de cara entre B.I. e Gestor é de composição do app, não do tema.
- Nuxt UI: lock do B.I. = `@nuxt/ui 4.11.3`; `npm latest` hoje = `4.11.3`. **Sem defasagem de versão.** Deltas que importam e que o B.I. não usa: `Card` com props `title`/`description` (4.7+), `Empty` com `loading` (4.10+), `Table` com linhas expansíveis (`expanded` + slot `#expanded`), `loading`, `sticky`, `meta.class`.
- Tela: capturas do próprio piloto (`onda0-bi-piloto/telas/*-1280.png` e `*-390.png`, build de produção contra o mock gravado) e do Gestor (`onda0-capturas/orders-nuxt__{board,history}__1440__light__depois.png`).

---

## (A) As razões estruturais do "cru"

A migração do B.I. trocou **peças** (botão, badge, select, tabs, alert viraram Nuxt UI), mas não trocou **composição**. O Gestor ficou canônico porque mudou a casca, o cabeçalho, a tabela e os estados; o B.I. ficou com a casca da suíte v3, gráficos de `div`, tabela de `div` e estados em parágrafo. O olho lê o conjunto, não a peça.

### A1. A casca é a da suíte v3, não a do Gestor
- B.I.: `app.vue:22` põe `data-suite="v3"`; `app.vue:29-36` monta `BiNav` → `OperatorSuiteRail` (rail latão cheio, rótulo + `Alt1..8` em cada item) e `OperatorSectionBar` no celular.
- Gestor: `orders-nuxt/app/app.vue:85-104` usa `OperatorSuiteShell` (→ `OperatorOfficeShell` → `NuxtDashboardGroup` / `NuxtDashboardSidebar` / `NuxtDashboardPanel`, rail neutro de ícones; no celular `NuxtDashboardToolbar` + `NuxtNavigationMenu`), com o comentário explícito "O Gestor não ativa mais a pele legada `suite:`".
- O `OperatorSuiteRail` é à mão: `operator-kit/app/components/OperatorSuiteRail.vue:147,159,184,275` (`w-[var(...)]`, `h-[52px] w-[68px]`, `text-[9px]`, `tracking-[0.09em]`, `<nav>` cru).
- Efeito colateral: `data-suite="v3"` liga o `suite-page:` do tema (`operator-kit/app/app.config.ts:154-176`), reservado aos "sete apps não migrados": inputs e selects do B.I. ficam em 44 px enquanto o Gestor está no compacto oficial. Por isso, na mesma régua de 1280 px, o B.I. parece mais pesado e "de outra época" (comparar `normal-explore-1280.png` com `orders-nuxt__board__1440__light__depois.png`).
- Doc: https://ui.nuxt.com/docs/components/dashboard-group , /dashboard-sidebar , /dashboard-panel.

### A2. Gráficos feitos de `div`, não de biblioteca
- B.I.: `components/chart/BarSeries.vue:57-118` (barras com `:style` de altura, sem eixo Y, sem escala, tooltip só em `group-hover` em `:92-100`, `role="img"` sem nome em `:60`); `chart/DivergingBars.vue:22-46`; `chart/HBarList.vue:16-30` (barra horizontal desenhada à mão, imitando `NuxtProgress`); mini-gráfico em `OverShortDetail.vue:90-103` (`h-[86px]`).
- Kitchen Sink: `operator-kit/app/components/OperatorKitchenSinkChart.client.vue:1-35` usa **Unovis** (`VisXYContainer`, `VisGroupedBar`, `VisAxis` x e y), dentro de `NuxtCard title/description`, com `<ClientOnly>` + `NuxtSkeleton` de fallback e a **mesma série numa `NuxtTable` SSR** (`OperatorKitchenSinkDashboard.vue:70-95`). O comentário do próprio catálogo: "Unovis, como no template oficial de dashboard. Nuxt UI não oferece Chart." A dependência já está no kit (`operator-kit/package.json:38-39`).
- Na tela: `normal-index-1280.png` mostra "Produção por dia" com um pico de 159.725.487 e o resto achatado em zero, sem eixo para o leitor perceber que a escala é absurda; `normal-cash-1280.png` mostra "Quebra de caixa por dia" com 300 px de vazio e uma barra vermelha sem valor no eixo.
- Doc/ref: https://ui.nuxt.com/templates (template Dashboard, Unovis).

### A3. A tabela principal do B.I. é uma grade de `div`
- B.I.: `pages/index.vue:103` (`COLUMNS` com sete colunas em px arbitrários: `104px`, `minmax(200px,230px)`, `92px`, `118px`, `168px`), `:363-379` (cabeçalho em `div` com `aria-hidden="true"`: o leitor de tela não recebe nome de coluna nenhum), `components/OverShortRow.vue:33-84` (linha + botão "Ver lotes e vendas" + detalhe abaixo).
- Gestor: `orders-nuxt/app/pages/history.vue:204-274` é `NuxtTable` dentro do card, com `#<col>-cell`, `on-select`, `caption`; o tema integra a tabela ao card sem padding (`app.config.ts:124-128`).
- O próprio B.I. já usa `NuxtTable` em Top produtos (`pages/sales.vue:327-345`), o que deixa a tela principal (Sobrou ou faltou) como a única "tabela" que não é tabela.
- Doc: https://ui.nuxt.com/docs/components/table (linhas expansíveis: prop `expanded`, slot `#expanded`, `row.toggleExpanded()`).

### A4. O cabeçalho de quadro e o número-herói são anatomia própria, não a do Card
- B.I.: `components/BiSection.vue:11-21` reescreve o cabeçalho do card (`h2.op-title` + `p.op-micro` + `#aside`); `components/StatTile.vue:38-58` e `components/BiAnswer.vue:9-12` montam rótulo/figura/legenda com `<p>` e utilitários `op-*`.
- Kitchen Sink: `OperatorKitchenSinkDashboard.vue:40-61` usa `NuxtCard title="…" description="…"` + `op-figure` + `NuxtBadge`/`NuxtProgress`; `OperatorKitchenSink.vue:657-663` usa `NuxtPageCard` para métricas; `OperatorKitchenSink.vue:648-654` escreve o contrato: "Texto solto serve apenas ao conteúdo, nunca para simular um componente."
- Doc: https://ui.nuxt.com/docs/components/card (props `title`, `description`, 4.7+), https://ui.nuxt.com/docs/components/page-card.

### A5. Cartão dentro de cartão
- B.I.: `pages/cash.vue:161-190` ("Contas na casa": três `StatTile`, cada um um `NuxtCard`, dentro de um `BiSection`, também `NuxtCard`, mais uma `<ul>` embaixo); `pages/profiles.vue:293-324` (três `StatTile` + um `NuxtCard` com `<ul>` dentro de `BiSection`). Visível em `normal-cash-1280.png`: borda dentro de borda, alturas desiguais.
- Gestor: nenhum card aninhado; seção de cartões é `QueueView.vue:236` (`NuxtPageCard`) ou lista dentro de um único card.
- Correção: a linha de números sai do quadro (grade de `NuxtCard`/`NuxtPageCard` no nível da página) ou vira `NuxtTable`/lista de definição dentro do único card.

### A6. Vazio e carregando não são componentes
- Vazio: 19 parágrafos `<p v-else class="op-body text-muted-foreground">` (`pages/index.vue:393,394,461,465`; `sales.vue:321,346`; `cash.vue:215,262,269,275`; `customers.vue:71,75`; `explore.vue:302`; `forecast.vue:152,182,257`; `profiles.vue:391`; `scenarios.vue:69,110`; `OverShortDetail.vue:110`). Em `normal-cash-1280.png` três quadros inteiros são só uma frase cinza.
- Gestor: `history.vue:276-282` usa `NuxtEmpty icon/title/description` (ver `orders-nuxt__history__1440__light__depois.png`); Kitchen Sink `OperatorKitchenSink.vue:727-731,788-792`.
- Carregando: `components/BiPageState.vue:20-25` é a mesma grade de 4 + 1 esqueletos em toda tela, sem a forma da tela que vem; Gestor `history.vue:195-202` desenha linhas no formato da tabela. Oficial: `NuxtTable :loading`, `NuxtEmpty :loading` (4.10+).
- Doc: https://ui.nuxt.com/docs/components/empty , /skeleton.

### A7. A linha de recortes é um varal, e o período mora no meio da página
- B.I.: `pages/index.vue:286-326` empilha `<label>` + `UiNativeSelect` + legenda de datas + `NuxtSeparator class="h-6 max-sm:hidden"` + `NuxtTabs` + separador + outro select + um espaçador + o texto cru `?day=2026-10-07` com ícone de link (`:322-325`). E o segundo controle de tempo da tela (`BiWindowPicker`) fica no corpo, em `index.vue:412-419`, abaixo da tabela: a página tem dois "quando" em dois lugares.
- Gestor: `history.vue:105-174` tem título + descrição no `#status`, uma busca, e uma linha só de recortes (`FilterBar` + `OperatorPeriodPicker` com ‹ › + Atualizar + total + `ReadFreshness`). Barra de bloco: `OperatorToolbar` (`operator-kit/app/components/OperatorToolbar.vue`, porta para `NuxtDashboardToolbar`), usado em `OrderBoardColumn.vue:53`, `catalog.vue:1816`, `[ref].vue:1028`. O B.I. não usa `OperatorToolbar` em lugar nenhum.
- Doc: https://ui.nuxt.com/docs/components/dashboard-toolbar.

### A8. Seletores nativos e rótulos que imitam o FormField
- B.I.: 11 `UiNativeSelect` (`index.vue:292,316`; `sales.vue:176`; `explore.vue:165,186,195,206`; `profiles.vue:203,213,366`; `scenarios.vue:57`). Em Explorar, os rótulos são `<label class="op-eyebrow">` em caixa alta (`explore.vue:163,184,193,204`), um `NuxtSeparator` vertical solto (`:183`) e o ⋯ caindo sozinho na segunda linha (`normal-explore-1280.png`). O seletor de Cenário tem `optgroup` de "Meus cenários" (lista que cresce): não é lista curta.
- Gestor: zero `UiNativeSelect`; `NuxtSelect` em `catalog.vue:1824`, `workstations.vue:158`, `channels/[ref]/catalog.vue:237`. Kitchen Sink `OperatorKitchenSinkExercises.vue:462-468` (`NuxtSelect`, `NuxtSelectMenu`).
- Conflito de regra a decidir: o README do kit (`operator-kit/README.md:809-810`) declara `UiNativeSelect` "a peça certa para lista curta e fixa" (roda do sistema no celular); a regra da migração diz "só componentes oficiais". O Gestor já escolheu `NuxtSelect`.
- Doc: https://ui.nuxt.com/docs/components/select , /select-menu , /form-field.

### A9. O selo "On" diz ao vivo numa leitura que não é ao vivo
- B.I.: `components/BiLiveStatus.vue:3-4` diz "leitura calma (sem poll)", mas renderiza `OperatorLiveStatus` (`:25-31`), cujo texto visível é `On`/`Off` (`operator-kit/app/components/OperatorLiveStatus.vue:36`). Na tela: "On 10:12" ao lado de "Quanto vendemos?".
- Gestor no Histórico (leitura sem SSE): `history.vue:168-172` usa `ReadFreshness` ("Última leitura útil: 15:36:22 · há 1 s"), que mora em `orders-nuxt/app/components/ReadFreshness.vue` e não no kit.
- Regra: omotenashi-copy, "rótulo que mente" e "jargão".

### A10. Hierarquia tipográfica achatada e listas sem fim
- Título de seção de página (`index.vue:415`, `profiles.vue:260`, `forecast.vue:89..303`) e título de card (`BiSection.vue:14`) são o mesmo `op-title` 16 px; a pergunta da seção ("Como foram os lotes no período?") pesa o mesmo que "Produção por dia".
- "Tempo de forno por receita" lista 26 receitas sem corte (`index.vue:457-462` + `HBarList`), 1.000 px de barras iguais (`normal-index-1280.png`), enquanto o Gestor corta com "+6: mais 4 … Ver todos" (board) e pagina (`history.vue:284-293`, `NuxtPagination`).

---

## (B) Achados

Severidade: P0 perde função ou mente ao operador; P1 fuga do canon que se espalha; P2 acabamento.

| id | sev | arquivo:linha (B.I.) | regra violada | correção (componente/prop oficial) |
|---|---|---|---|---|
| F01 | **P0** | `components/chart/BarSeries.vue:92-100`, `:60`; legenda que promete o detalhe em `pages/index.vue:447` ("o detalhe traz previsto e perda") | função perdida: o detalhe só existe em `:hover`; no toque e no teclado não há como ver previsto/perda/comparação; `role="img"` sem nome. Anterior à migração (o diretório `chart/` não está no diff), mas o piloto não o resolveu | gráfico do kit sobre Unovis com tooltip por foco/toque + `NuxtTable` SSR com a mesma série (padrão `OperatorKitchenSinkDashboard.vue:82-95`) |
| F02 | P1 | `app.vue:22,29-36`; `components/BiNav.vue:23-37` | casca legada (`data-suite="v3"`, `OperatorSuiteRail` à mão); liga o `suite-page:` de 44 px | `OperatorSuiteShell` (→ `NuxtDashboardGroup/Sidebar/Panel`), como `orders-nuxt/app/app.vue:94` |
| F03 | P1 | `components/chart/BarSeries.vue`, `DivergingBars.vue`, `HBarList.vue`; `OverShortDetail.vue:90-103` | primitivo paralelo (gráfico de `div` com `:style`) | peça de gráfico do kit (Unovis: `VisGroupedBar`, `VisAxis`, `VisLine` para o traço de comparação); barra horizontal → `NuxtProgress`/`NuxtProgressGroup` |
| F04 | P1 | `pages/index.vue:103,363-379`; `components/OverShortRow.vue:33-84` | tabela crua em `div`, cabeçalho `aria-hidden`, larguras px sem motivo de produto | `NuxtTable` com `v-model:expanded` + slot `#expanded` (detalhe `OverShortDetail`), colunas com `meta.class`, `#verdict-cell` com `NuxtBadge` |
| F05 | P1 | `components/BiSection.vue:11-21` | classes imitando o cabeçalho do Card | `NuxtCard :title :description` (4.7+); o ⋯ do quadro entra na peça do kit (C) |
| F06 | P1 | `pages/cash.vue:161-190`; `pages/profiles.vue:293-324` | card dentro de card | números no nível da página (grade de `NuxtCard`/`NuxtPageCard`); dentro do quadro, `NuxtTable` |
| F07 | P1 | 19 `<p v-else>` (lista em A6) | vazio imitado com texto | `NuxtEmpty icon/title/description` (variante `naked` dentro do card) |
| F08 | P1 | `pages/index.vue:286-326,412-419`; `pages/sales.vue:170-192` | composição do cabeçalho fora do padrão do Gestor; dois controles de tempo em dois lugares; separadores com classe de ajuste | `OperatorPageHeader` `#filters` com uma linha (`NuxtSelect` + `NuxtTabs`), período no `#actions`; o bloco "lotes no período" vira aba (`NuxtTabs`) ou rota própria com o próprio cabeçalho |
| F09 | P1 | 11 `UiNativeSelect` (lista em A8); `explore.vue:163-215` | controle fora do oficial; rótulo imitando FormField | `NuxtFormField label` + `NuxtSelect`; Cenário com grupos → `NuxtSelectMenu :items` agrupados. **Depende de decisão** (README do kit x regra da migração) |
| F10 | P1 | `components/BiLiveStatus.vue:24-31` | copy que mente ("On" numa leitura sem poll) | `ReadFreshness` (subir ao kit) com "Leitura das HH:MM" |
| F11 | P1 | `pages/sales.vue:303-320`; `cash.vue:180-189`; `profiles.vue:314-321,331-341,348-355` | listas e `<dl>` imitando tabela/progresso | `NuxtTable` (com rodapé via `column.footer` na Conciliação), `NuxtProgress` na célula |
| F12 | P1 | `components/BiPeriodChip.vue:6-14` | primitivo paralelo declarado (segundo seletor de período) + import relativo para dentro do kit (`../../../operator-kit/app/presentation/dates`) | variante compacta do `OperatorPeriodPicker` no kit; apagar `BiPeriodChip` |
| F13 | P2 | `components/BiPageState.vue:20-25` | carregando genérico, sem a forma da tela | `NuxtTable :loading` / `NuxtEmpty :loading` / esqueleto no formato do quadro (como `history.vue:195-202`) |
| F14 | P2 | `pages/index.vue:322-325` | omotenashi: "nota de rodapé do engenheiro" (`?day=2026-10-07` na tela) | apagar; o "Copiar link desta leitura" já está no ⋯ (`BiPageMenu.vue:19-22`) |
| F15 | P2 | `pages/sales.vue:268-272` | legenda de gráfico à mão (bolinhas e traço em `span`) | legenda da peça de gráfico (Unovis `VisBulletLegend`) |
| F16 | P2 | `OverShortDetail.vue:61,90`; `OverShortBar.vue:14`; `BiPeriodChip.vue:61` | valor arbitrário sem motivo escrito (`h-[86px]`, `max-w-[200px]`, `grid-cols-[1.1fr_1fr_1.25fr]`) | some com F03/F04/F12; o que restar ganha comentário |
| F17 | P2 | `components/StatTile.vue:38-58`; `BiAnswer.vue:9-12` | anatomia própria de métrica; "A RESPOSTA" em eyebrow solto | `NuxtCard title description` + `op-figure` + `NuxtBadge` (receita do Kitchen Sink) |
| F18 | P2 | `pages/index.vue:300-312` (capturado em `normal-index-390.png`) | no celular as abas de veredito cortam ("Na me…") sem pista de rolagem | `filters-wrap` do `OperatorPageHeader` ou `NuxtSelect` abaixo de `sm` |
| F19 | P2 | `pages/index.vue:415`; `profiles.vue:260`; `forecast.vue:89-303` vs `BiSection.vue:14` | hierarquia achatada (seção = card = 16 px) | seção com `op-heading`/eyebrow como `OperatorKitchenSink.vue:714-717`, ou cada pergunta numa aba |
| F20 | P2 | `pages/index.vue:457-462` | lista sem corte (26 linhas) | `NuxtTable` com ordenação + "Ver todas" (padrão "+N" do Gestor) |
| F21 | P2 | dado/projeção (capturas) | rótulo de forno "producao" (slug sem acento) e pico 159.725.487 em "Produção por dia" | conferir projeção `bi_*`/fixture gravada; ver (E) |
| F22 | P2 | `operator-kit/app/components/OperatorKitchenSinkDashboard.vue:66` | o catálogo usa `:ui` por instância em `NuxtTabs` | levar ao `app.config.ts` ou justificar no catálogo |

**Contagem:** P0 = 1 · P1 = 11 · P2 = 10.

O que o piloto acertou e deve ficar: `NuxtDropdownMenu` no ⋯ da página e do quadro (`BiPageMenu.vue`, `BiChartMenu.vue`); `NuxtAlert` com ação no erro (`BiPageState.vue:26-36`); `NuxtTabs variant="pill"` com `badge` nos recortes; `NuxtTable` em Top produtos, Perfis e Caixa; `NuxtFieldGroup` + `UiDateField` no dia; zero `:ui` por instância no app.

---

## (C) O que sobe ao kit (B.I. e Gestor, e os próximos: Central, Marketing, Compras)

1. **Gráfico de leitura** (Unovis, já dependência do kit): barras, barras com traço de comparação, divergente (sobrou/faltou), linha/área; eixo, tooltip por foco e toque, legenda, `ClientOnly` + `NuxtSkeleton`, e a tabela SSR equivalente. Nasce do `OperatorKitchenSinkChart.client.vue` (hoje fixture). Mata `chart/*` do B.I.
2. **Quadro de leitura**: `NuxtCard` com `title`/`description` e o ⋯ de ações do quadro (exportar CSV). O ⋯ com "Exportar CSV deste quadro" (`BiChartMenu.vue`) e o "Copiar link desta leitura" (`BiPageMenu.vue`) servem Gestor (histórico, catálogo), Compras e Marketing.
3. **Métrica**: a receita do Kitchen Sink (`NuxtCard title/description` + figura + `NuxtBadge` de delta) como peça, com o delta pronto da presentation (`DeltaBadge`). Mata `StatTile`/`BiAnswer`.
4. **Frescor da leitura**: `ReadFreshness` sai de `orders-nuxt/app/components/` para o kit; o B.I. troca o "On" por ele.
5. **Período compacto no celular**: variante de gatilho curto do `OperatorPeriodPicker`; e o modo "um dia com ‹ ›" que o Gestor já usa no Histórico substitui `BiDayStepper`.
6. **Decisão de seletor**: o kit precisa dizer uma vez se `UiNativeSelect` continua canônico (README:809) ou se morre em favor de `NuxtSelect`. Hoje Gestor e B.I. divergem.

---

## (D) Fatiamento em PRs (no máximo um grupo de telas cada), em ordem

1. **PR-K1 kit: gráfico de leitura + quadro** (itens C1 e C2). Kitchen Sink troca a fixture pela peça real; teste de acessibilidade do tooltip por teclado. Sem tocar app.
2. **PR-K2 kit: métrica, frescor, período compacto** (C3, C4, C5). `ReadFreshness` sobe e o Gestor passa a importá-lo do kit no mesmo PR (troca mecânica, captura antes/depois do Histórico).
3. **PR-B1 B.I. casca**: tira `data-suite="v3"`, adota `OperatorSuiteShell`; decide o destino do `BiSwipeHint` (gesto próprio do B.I.). Captura das 8 telas a 390/768/1440, porque as alturas de controle mudam em todas (sai do `suite-page:`).
4. **PR-B2 Produção (Sobrou ou faltou)**: `index.vue` + `OverShortRow/Detail/Bar`. `NuxtTable` com linha expansível, cabeçalho numa linha, "lotes no período" em aba ou rota, `NuxtEmpty`, fim do `?day=`. Resolve F01 nesta tela.
5. **PR-B3 Vendas**: `sales.vue` com os gráficos do kit, Por canal em `NuxtTable`, frescor no lugar do "On".
6. **PR-B4 Caixa**: `cash.vue` sem card dentro de card, listas em tabela, vazios.
7. **PR-B5 Clientes + Perfis**: `customers.vue`, `profiles.vue` (Conciliação com rodapé de tabela, faixa honesta, matriz).
8. **PR-B6 Explorar + Cenários**: `explore.vue`, `scenarios.vue` (`NuxtFormField` + `NuxtSelect/SelectMenu`, `NuxtEmpty`).
9. **PR-B7 Projeção**: `forecast.vue`.

PR-B2 a PR-B7 dependem de PR-K1/K2 e de PR-B1; entre si são independentes. A pergunta do seletor (C6) precisa de resposta antes de PR-B2.

---

## (E) O que não deu para verificar, e por quê

- **Tela ao vivo:** os servidores respondem (`127.0.0.1:3001/3004/3007/3009` = 200, `node out/<app>/server/index.mjs`), mas não sei de qual commit é cada build, e não entrei (exige login no hub). Julguei pelas capturas do piloto (`onda0-bi-piloto/telas`, 10:12, anteriores ao último commit `212fb7508` de 10:13, que só mexe no separador e na tabela do celular) e pelas do Gestor (`onda0-capturas`, 09:59). A captura do Kitchen Sink em `onda0-capturas` é só a tela de login; o catálogo foi julgado pelo código.
- **Capturas de página inteira:** o rail e a barra de seções aparecem cortados ou no meio da página porque são `sticky`/fixos; não contei isso como defeito.
- **Pico 159.725.487 e o forno "producao" (F21):** podem ser da fixture gravada (`tests/visual/fixtures/recorded-django.json`) ou da projeção; não abri a fixture nem a projeção.
- **Docs do Nuxt UI:** li, via fetch, Card, Table, Empty e DashboardToolbar. Não li PageCard, Tabs, DropdownMenu, Badge, Alert, Skeleton, Progress, Select/SelectMenu nem a página do template de dashboard. A afirmação "Nuxt UI não tem Chart, o template usa Unovis" vem do comentário do Kitchen Sink, sem conferência independente.
- **Omotenashi:** sem travessão na copy visível do B.I. (os três `—` de `presentation/bi.ts` são comentários). Não fiz a varredura completa dos oito defeitos de `docs/reference/omotenashi-copy.md` tela a tela.
- **Regressão funcional:** não rodei teste nem gesto; a tabela de gestos antes/depois do piloto (`onda0-bi-piloto/gestos-antes-depois.md`) diz "sim" em todos, com vários "não exercido" (CSV, POST de levar ao plano, salvar cenário).

---

## (F) Minimalismo na suíte inteira: o que está em uso, o conjunto reduzido e onde a doc é mais simples que o kit

**Escopo e método.** Ref `origin/claude/gestor-toolbar-calendario` @ `80ed58d54`, todos os `surfaces/*-nuxt/app/**/*.vue` mais `operator-kit/app` (o storefront fica fora). A contagem é por regex sobre as tags (`<NuxtButton …>` etc.). Prop ausente conta como default do tema; prop ligada (`:color="…"`) entra como "dinâmica" e fica fora das combinações. Nesta ref o `bi-nuxt` ainda é o pré-migração; os números do B.I. migrado estão em (A) e (B). **Tudo aqui é proposta para o dono aprovar. Nada foi mudado.**

### F1. O que está em uso hoje

**Botões: duas famílias paralelas**
- `NuxtButton`: 287 usos, todos no kit (130) e no Gestor (157). São **35 combinações** fixas, mais 27 dinâmicas.
  - Tamanhos: `md`, `xs`, `sm`, `lg`, `xl` (os 5 da doc).
  - Cores: `primary`, `neutral`, `error`, `warning`, `info`, `success` (6).
  - Variantes: `solid`, `outline`, `ghost`, `link`, `soft` (5).
  - Topo: `neutral outline` 85 · `neutral ghost` 59 · `primary solid` 53 · `neutral link` 12 · `error outline` 7 · `xl neutral outline` 7 · `xs neutral outline` 7.
- `UiButton` (camada própria do kit, shadcn-like): 368 usos no PDV (187), na Produção (96), no Marketing (82) e no B.I. (3). São **23 combinações**.
  - Tamanhos: `default`, `sm`, `xs`, `lg`, `icon`, `icon-sm`.
  - Variantes: `default`, `outline`, `ghost`, `link`, `destructive`, `secondary`.
  - Usa `:ui` interno (`operator-kit/app/components/UiButton.vue:125`).
- `UiIconButton`: 10 usos.
- **Resultado:** a suíte tem duas escalas de tamanho e dois vocabulários de variante para o mesmo botão.

**Badge**
- `NuxtBadge`: 78 usos, 18 combinações; tamanho praticamente único (`md`).
- Variantes `soft`, `subtle`, `outline` e `solid`, nas cores `neutral`, `warning`, `error`, `success`, `primary` e `info`.
- O mesmo sentido ("neutro informativo") aparece em `soft` 14× e `subtle` 13×, às vezes **no mesmo componente**:
  - `orders-nuxt/app/components/QueueView.vue:319,395` (`soft`) contra `:406,607,654,720` (`subtle`);
  - `OrderCard.vue:504-663` (`soft`) contra `:761` (`subtle`).

**Card**
- `NuxtCard`: 90 usos, 3 estilos: `outline` (default do tema, 75), `soft` (9) e `subtle` (3).
  - `soft`: `CatalogProductPanel.vue:1132,1208,1242,1300`, `catalog.vue:1909`, `channels/[ref]/catalog.vue:188,258`, `OperatorSuiteSearch.vue:330`.
  - `subtle`: `CatalogProductPanel.vue:817`, `catalog.vue:1252`.
- `NuxtPageCard`: 4 usos.
- Um só padding (16 px, `app.config.ts:124-128`). Isso está bom.

**Alert**
- `NuxtAlert`: 117 usos, 16 combinações; 3 variantes (`subtle` 95 %, `solid`, `soft`) × 6 cores.
- O tema reescreve o fundo do `subtle` em **7 compoundVariants** com `color-mix` (`app.config.ts:61-113`). Um deles é `secondary`, e nenhuma tela usa `color="secondary"` (0 ocorrências).

**Seleção: quatro peças para um gesto só**
- `UiNativeSelect` 43 (Produção 18, Compras 9, B.I. 8, PDV 4, Marketing 4).
- `NuxtSelect` 19 (Gestor e kit).
- `UiSelect` 10 (Marketing, Compras).
- `NuxtSelectMenu` 2 (kit; um deles com `size="lg"` e `:ui`).

**Tipografia: duas escalas sobrepostas**
- Nos migrados (kit + Gestor + Kitchen Sink):
  - Tailwind `text-xs` 108 e `text-sm` 112, mais `lg`, `base`, `xl` e `2xl`;
  - **9 tamanhos arbitrários** (`text-[9px]`, `[9.5px]`, `[10px]`, `[11px]`, `[12px]`, `[13px]`, `[15px]`, `[16px]`, `[0.625rem]`);
  - **mais** 8 papéis `op-*` de outra escala: `op-body` 15 px e `op-label` 13 px (`operator-kit/app/assets/css/operator-suite.css`), que caem **entre** o 14 e o 12 px que os componentes Nuxt UI usam.
  - Total: **15 tamanhos de texto distintos**.
- Nos legados: 29 tamanhos (até `text-8xl`).
- Pesos: 4 (`normal`, `medium`, `semibold`, `bold`).

**Raio: dois sistemas sobrepostos**
- `--radius: 0.625rem` mais `--radius-sm/md/lg/xl` próprios (`operator-base.css:44-47`, `operator-theme.css:52`).
- `--ui-radius` (o token de raio do Nuxt UI, default `0.25rem`) **não é definido**.
- Valores em uso:
  - migrados: 9 (`md` 43, `full` 16, `lg` 8, `rounded` 5, `xl` 4, `none`, `sm`, `[10px]`, `[inherit]`);
  - legados: 16 (inclui `[14px]`, `[10px]`, `2xl`, `3xl`).

**Ajustes do tema em `app.config.ts`, somados**
- 14 componentes ajustados.
- 3 `compoundVariants` de tinta (button, badge e alert ×7).
- Hacks de área de toque com `after:` em checkbox, switch e radio (`:5-21`).
- Variante inventada `chip.size.4xl` com `text-[12px]` (`:25-31`).
- Seletor `has-[…]` para a tabela integrada ao card (`:126`).
- Altura de toque por `suite-page:` (`:154-176`).

### F2. Conjunto canônico reduzido (proposta)

| peça | hoje | proposta | justificativa |
|---|---|---|---|
| Botão: tamanhos | 5 no Nuxt + 6 no UiButton | **2**: `md` (todo lugar) e `xl` (opt-in de toque crítico: PDV, KDS, kiosk, numpad) | `xs`/`sm` existem para caber em linha de tabela: use `square` + `ghost` no `md`. O `lg` some no `xl` ou no `md`. O `UiButton` `icon`/`icon-sm` vira `square`. Uma régua de altura só por contexto |
| Botão: variantes | 5 + 6 | **3**: `solid` (o gesto principal, 1 por região), `outline` (secundário), `ghost` (terciário, ícone, menus) | `link` vira `ghost` ou `NuxtLink`; `soft` só aparece como **estado ativo**, via `active-variant` (F3.2); `destructive`/`secondary` do UiButton viram cor |
| Botão: cores | 6 | **3**: `primary`, `neutral`, `error` | estado (aviso, info, sucesso) mora em Badge ou Alert, não no botão. Os 4 `warning outline` e o `info`/`success` viram `neutral` |
| Badge | 4 variantes × 6 cores | **1 variante** (`subtle`, que tem borda e se lê sobre o card branco) × 5 cores (`neutral`, `primary`, `success`, `warning`, `error`), fixada em `defaultVariants` | acaba a dupla `soft`/`subtle` para o mesmo sentido; `info` vira `neutral` |
| Card | 3 estilos | **1**: `outline`. Destaque navegável = `NuxtPageCard` | `soft`/`subtle` foram usados como "caixa dentro do painel", o mesmo cheiro de card-em-card de (A5) |
| Alert | 3 variantes | **1**: `subtle` × 4 cores (`info`, `success`, `warning`, `error`) | apaga 3 dos 7 compoundVariants (`primary`, `secondary`, `neutral`) |
| Seleção | 4 peças | **2 oficiais**: `NuxtSelect` (lista curta e fixa) e `NuxtSelectMenu` (longa, buscável, agrupada ou que cresce) | ver F4 |
| Texto | 15 tamanhos (migrados) | **5**: `text-xs` 12, `text-sm` 14, `text-base` 16, `text-xl` (título de tela), `text-2xl` (figura) | os `op-*` passam a ser só aliases desses 5 (ou morrem). O texto corrido fica no mesmo 14 px dos controles. Zero arbitrários |
| Peso | 4 | **2**: `medium` e `semibold` | `bold` só no `op-code` do Gestor, se o dono quiser manter |
| Raio | 9 / 16 valores | **1 token** (`--ui-radius`) e **3 usos**: componente (o do tema), `rounded-full` (avatar, ponto), `rounded-none` | Nuxt UI deriva `xs…3xl` de `--ui-radius` |

### F3. Onde a doc atual é mais simples ou mais robusta que o kit, o Gestor ou o Kitchen Sink

1. **Defaults no tema em vez de prop em cada chamada.**
   - Hoje: 85 `color="neutral" variant="outline"` escritos à mão em `NuxtButton`, e 27 badges com `variant` repetido.
   - Doc: `ui.<comp>.defaultVariants` no `app.config` e `theme.defaultVariants` no módulo (https://ui.nuxt.com/docs/getting-started/theme/components, https://ui.nuxt.com/docs/getting-started/installation/nuxt).
   - Por quê: fixa a escolha num lugar, as chamadas encolhem e a regra vira trava. Ex.: `badge.defaultVariants.variant = 'subtle'`.
2. **Estado ativo do botão pela API oficial.**
   - Hoje: ternários `:variant="active ? 'soft' : 'outline'"` em `UiFilterChip.vue:20`, `ColumnPicker.vue:47`, `OperatorReasonDialog.vue:245,256`, `OperatorPhoneMenu.vue:98`.
   - Doc: props `active`, `active-color`, `active-variant` (https://ui.nuxt.com/docs/components/button).
   - Por quê: o rail do kit já faz certo (`OperatorSuiteShell.vue:150-159`). Um padrão só, e o "pressionado" fica igual em toda a suíte.
3. **Restringir as cores geradas.**
   - Hoje: o módulo gera as 6 cores default (`operator-kit/nuxt.config.ts:30-42`), e `secondary` tem compoundVariant de Alert sem nenhum uso.
   - Doc: `theme.colors` (default `['primary','secondary','success','info','warning','error']`, https://ui.nuxt.com/docs/getting-started/installation/nuxt).
   - Proposta: `['primary','success','warning','error']` (o `neutral` é sempre gerado). Cor que não existe não pode ser usada; menos CSS gerado.
4. **Raio pelo token do Nuxt UI.**
   - Hoje: `--radius` + `--radius-sm/md/lg/xl` próprios (`operator-base.css:44-47`); `--ui-radius` não definido.
   - Doc: `--ui-radius`, de onde saem `--radius-xs…3xl` (https://ui.nuxt.com/docs/getting-started/theme/css-variables).
   - Proposta: `--ui-radius: 0.3125rem` (dá `md` ≈ 7,5 px e `lg` = 10 px, o atual) e apagar as quatro sobrescritas. Hoje dois sistemas disputam `--radius-md`. Não conferi qual vence em runtime (ver E).
5. **Rail de navegação.**
   - Hoje: `NuxtTooltip` > `NuxtChip` > `NuxtButton`, montados à mão por item (`OperatorSuiteShell.vue:137-204`), mais a variante inventada `chip.size.4xl` (`app.config.ts:25-31`).
   - Doc: `NuxtNavigationMenu orientation="vertical" collapsed tooltip` com `badge` no item, que é o exemplo de DashboardSidebar recolhida (https://ui.nuxt.com/docs/components/navigation-menu).
   - Por quê: some o laço manual, a variante `4xl` e o `text-[12px]`; `aria-current` e teclado vêm do Reka. É navegação, não menu de ação, então a regra do ledger que tirou o NavigationMenu dos menus de ação não se aplica.
   - **Ressalva:** o selo numérico do rail (contagem "9+") precisa caber no `badge` do item; a provar no Kitchen Sink.
6. **Loading do botão.**
   - Hoje: 43 `:loading="…"` ligados a refs de pendência, e 8 `usePendingAction`.
   - Doc: `loading-auto`, que mostra o loading enquanto a promise do `@click` não resolve (https://ui.nuxt.com/docs/components/button).
   - Por quê: menos estado à mão e nenhum botão "esquecido" sem loading. O `usePendingAction` continua só onde há guarda de duplo envio entre botões diferentes.
7. **Vazio com carregando.**
   - Hoje: esqueletos à mão por tela (`history.vue:195-202`, `BiPageState.vue:20-25`).
   - Doc: `NuxtEmpty :loading` (4.10+) e `NuxtTable :loading` (https://ui.nuxt.com/docs/components/empty, /table).
   - Por quê: uma peça só para "não tem" e "ainda não chegou", sem pular o layout.
8. **Card com `title`/`description`.**
   - Hoje: o Kitchen Sink usa as props (`OperatorKitchenSinkDashboard.vue:40-73`), mas o próprio Kitchen Sink e o Gestor ainda escrevem `<template #header><h3 class="op-title">` (`OperatorKitchenSink.vue:430,445,507,669,691`).
   - Doc: https://ui.nuxt.com/docs/components/card (4.7+).
   - Por quê: um cabeçalho de card só na suíte.
9. **`:ui` por instância no próprio catálogo.**
   - Hoje: `OperatorKitchenSinkDashboard.vue:66`, `OperatorKitchenSinkExercises.vue:576,608`, `OperatorPage.vue:16`, `OperatorPushSettings.vue:153`, `UiButton.vue:125`.
   - Proposta: o catálogo é a referência, então tem que obedecer à regra que ensina. Levar ao `app.config` ou escrever a exceção com motivo.
10. **Aposentar `UiButton`, `UiIconButton`, `UiSelect` e `UiNativeSelect`.**
    - Camada paralela com 431 usos nos apps legados. Com F2 aprovado, a migração de cada app vira troca 1:1 para `NuxtButton`/`NuxtSelect`/`NuxtSelectMenu`, com o mapa fixo: `destructive` → `error`, `icon` → `square`, `lg` → `xl`.

### F4. A pergunta do `UiNativeSelect`: recomendação

**Recomendo aposentar.** Lista curta e fixa vai para `NuxtSelect`; lista longa, buscável, agrupada ou que cresce vai para `NuxtSelectMenu`. **No toque e no kiosk**, o `NuxtSelectMenu` vai com `:search-input="{ autofocus: false }"`, que é exatamente o que a doc indica "to avoid opening the virtual keyboard on touch devices" (https://ui.nuxt.com/docs/components/select-menu). Pede a palavra do dono, porque reabre o que está escrito em `operator-kit/README.md:809-810`.

Fundamento:
- **O que a doc oferece:**
  - o `NuxtSelect` (Reka Listbox) suporta grupos (array de arrays) e itens `type: 'label' | 'separator'` (https://ui.nuxt.com/docs/components/select);
  - o `NuxtSelectMenu` acrescenta busca, `virtualize` e `create-item`, e trata o teclado virtual no toque (link acima);
  - a doc não oferece select nativo como alternativa.
- **O que o nativo custa:**
  - a lista de opções é do sistema operacional, então não segue o tema, não mostra ícone nem badge e muda de um SO para outro;
  - grupo com rótulo só existe como `optgroup` sem estilo;
  - é a única peça de escolha que o `app.config` não alcança.
- **A altura de toque já está resolvida** para `select` e `selectMenu` no tema (`app.config.ts:161-176`, `suite-page:min-h-control`). O argumento "a roda do sistema é ótima no celular" perde força contra um painel de 44 px por item, igual em iOS, Android e desktop.
- **A suíte já se dividiu:** o Gestor tem 0 `UiNativeSelect` e 19 `NuxtSelect`; Produção, Compras e B.I. têm 35 `UiNativeSelect`. Manter os dois é manter duas aparências para o mesmo gesto.
- **Risco a medir antes de aprovar:** a roda nativa do iOS é um gesto que o operador do PDV e da Produção já conhece. Proposta de prova: uma tela da Produção com `NuxtSelect`, num iPad, antes de migrar as outras 42.

### Limites de (F)
- A contagem é por regex. Props montadas em objeto (`v-bind`) e componentes renderizados por `h()` não entram. Os números são piso, não censo.
- Não medi em runtime qual definição de `--radius-md` vence (a do kit ou a do Nuxt UI).
- Não provei que o `badge` do item do `NavigationMenu` comporta o selo "9+" do rail.
- As páginas da doc foram lidas por fetch com resumo: Select, SelectMenu, Button, NavigationMenu, css-variables, theme/components e installation/nuxt.
