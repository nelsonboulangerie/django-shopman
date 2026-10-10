# WP-GESTOR-CANON-LAUDO: auditoria adversarial da migração canônica do Gestor e do operator-kit

- **Data:** 07 e 08/10/2026.
- **O que foi auditado:** o head do #1519 (`700f6aa63`), que está empilhado sobre o #1518 (`bc6890171`).
- **Comparação:** o `main` `838ce00e6`, que é a versão antes da migração.
- **Correções P0 abertas:** #1520, #1521 e #1522. As três estão em rascunho, empilhadas sobre o #1519 e fora da fila.

## Como ler

**Nível de prova de cada achado:**

- **[tela]** visto no navegador: build de produção, mock `tests/visual/mockBackend.mjs` no cenário `gallery`, Chromium 1194.
  - Larguras: 390, 768, 1024, 1280 e 1440 px.
  - Temas: claro, e escuro pelo botão do app (o Gestor é claro por decisão em `nuxt.config.ts:120`).
- **[CI]** check vermelho no #1519.
- **[código]** leitura com arquivo:linha, sem ter visto rodando.

**Severidade:**

- **P0:** perde função ou mente ao operador.
- **P1:** fuga do cânon que se espalha para os outros 8 apps.
- **P2:** polimento.

Os anexos A a D trazem a leitura de código por eixo, com todos os arquivo:linha. O corpo traz só o que decide.

## Veredito

O Gestor ainda **não é molde**, por três motivos:

1. A migração derrubou o detalhe do pedido iFood com negociação. Esse detalhe é justo o destino do aviso urgente novo.
2. As mudanças no kit já quebram 4 apps na CI e apagaram as abas de Ajustes do PDV.
3. A pista do Pablo se confirma, e o caso é pior: o kit **regrediu** o período de `UiDateField` para `type="date"` nativo. Hoje ele aparece como `mm/dd/yyyy` e `12:00 AM`.

## Placar

| Severidade | Quantos | Situação |
|---|---|---|
| P0 | 6 | 3 corrigidos em PR empilhado (#1520, #1521, #1522); 3 viram plano (F1, F3, F7) |
| P1 | 24 | plano F1 a F9 |
| P2 | cerca de 40 | anexos; entram nas frentes que tocam o arquivo |

## P0

### P0-1. O detalhe do pedido iFood com negociação aberta cai com 500 [tela] → **#1520**

- **Onde:** `OrderIFoodNegotiations.vue:263-290` e `CatalogBindingReview.vue:190-200`.
- **O defeito:** o `NuxtSelect` recebia `{ label: "Selecione…", value: "" }`. O `SelectItem` do reka-ui lança erro com valor vazio, e a página inteira vira "500 · A <SelectItem /> must have a value prop…".
- **Por que é grave:** é a página para onde leva o "Responder no pedido" do aviso urgente. No `main` era um `<select>` nativo, que aceita valor vazio, então é regressão da migração.
- **Por que nenhum teste pegou:** o dublê do `NuxtSelect` em `tests/support/uiPrimitives.ts` aceitava `value: ""`. Os testes de componente do Gestor rodam contra 25 dublês de Nuxt UI escritos à mão. A galeria do mock também não pegava: a negociação do I15 vinha sem `items`, e o detalhe caía antes, com `reading 'length'`.
- **Correção (#1520):**
  - `placeholder` no lugar do item vazio.
  - O dublê passa a lançar como o real: 14 testes caem no código antigo.
  - Trava de template, no Gestor e no kit.
  - Galeria com a projection completa.
  - Antes: 500. Depois: o formulário de resposta aparece, a 1440 e a 390 px.

### P0-2. O cabeçalho do kit apagou o slot `#below` [tela] → **#1521**

- **O defeito:** `OperatorPageHeader.vue` perdeu o `<slot name="below" />`, e Vue descarta slot não declarado sem aviso.
- **Na tela:** no PDV, em `/settings/terminal` a 1280 px, as seis abas de Ajustes aparecem no `main` e somem no #1519 (Terminal, Impressoras, Maquininhas, Salão, Envio à cozinha, Atalhos de venda). Com o #1521 elas voltam.
- **Pela leitura de código, também perdem o slot:**
  - o prazo do anúncio no Marketing (`announcements/[id].vue:441`);
  - o bloco da Produção (`ProductionHeader.vue:375`);
  - a seção do Compras no celular (`purchase-nuxt/.../index.vue:1332`).

### P0-3. "Concluir" da barra de lote só sai da seleção [tela] → **#1522**

- **Onde:** `index.vue:1550`. O defeito já existia no `main`.
- **Por que mente:** "Concluir" é o rótulo do servidor para concluir o pedido entregue (`order_queue.py:85`).
- **Correção:** "Sair da seleção", numa constante única com o ⋯ do quadro.

### P0-4. A herança do kit já quebra 4 apps [CI] → frente F1

- **Jobs vermelhos no #1519:**
  - `pos-nuxt`;
  - `marketing-nuxt`;
  - `kitchensink-nuxt`;
  - `operator-kit`;
  - "Produção · matriz Playwright AA";
  - "Marketing · cadeia completa";
  - "Versões das superfícies".
- **O autor declarou** o Gestor verde e não abriu os outros apps.
- **O que a leitura explica:**
  - **PDV:** 3 testes caem em peças do kit (`preorders.test.ts:566` FilterBar, `:858` UiFilterChip, `sessionIndex.layout.test.ts:301` Modal do PIN).
  - **Marketing:** `OperatorLogin.test.ts` cai porque `<NuxtModal>` fica inerte no harness sem o runtime do Nuxt.
  - **Versões das superfícies:** o `check_operator_component_ledger.py` reprova "layout Nuxt UI canônico usado fora do operator-kit" em 7 arquivos do Gestor.
  - **Kit:** o vitest passa (1.368 testes); o vermelho é do passo Playwright.
- **O que não foi feito:** os logs dos jobs Playwright não foram baixados.

### P0-5. `OperatorLiveStatus` virou binário verde "On/Off", em inglês [tela + código] → frente F3

- **Na tela:** todo cabeçalho do Gestor mostra "On 21:27". É inglês, e "On" não diz o quê.
- **Nos outros apps:**
  - o tom `late` da Produção (`ProductionHeader.vue:102`) e o `calm` do KDS saem verdes;
  - isso quebra o contrato do `operator-kit/README.md:422` e o `marketing liveStatus.ts`.
- **A trava protege o defeito:** `canonicalPilot.guardrails.test.ts` exige o "On/Off xl" e cristaliza a decisão errada.
- **Ordem da correção:** primeiro decidir o texto e os tons, depois corrigir o teste.

### P0-6. A Saída do celular perdeu o deslizar para entregar e o polegar [código] → frente F7

- **O que sumiu:** o `PhoneExitList.vue`, apagado no snapshot `7e6bb83de`, sem decisão escrita. Com ele foram:
  - o deslize da linha para a direita que entregava;
  - o botão fixo "Entregar U13 a Ana";
  - o mais antigo em foco;
  - o `Enter` na linha.
- **O teste foi junto:** `gestorV6Gestures.test.ts:28` também foi apagado.
- **Situação agora:** a aba Saída usa `OrderBoardColumn.vue:100-155` e só desliza para a esquerda (Atender/Recusar). Entregar segue possível pelo botão de cada cartão.

## P1 que mais importam

### P1-1. Data, hora e período: a pista do Pablo [tela + código]

**Na tela:**

- **Canais, "Escolher período…":** quatro `NuxtInput type="date|time"` aparecem como `mm/dd/yyyy` e `12:00 AM`. A hora começa à meia-noite, e o rodapé diz "Escolha no calendário…" (`presentation/channelSwitch.ts:48`), mas o calendário não existe mais.
- **Histórico, "Personalizado":** "De 10/07/2026" ao lado de "Hoje, qua 07/10". É a mesma data em dois formatos, e 10/07 se lê 10 de julho. O formato é do sistema do dispositivo, não da casa.

**No código:**

- `OperatorPeriodPicker.vue:248, 259, 294`: o #1518 trocou `UiDateField` por `NuxtInput type="date"`.
  - São 10 usos em 5 apps: B.I. 2, PDV 1, Produção 6, Gestor 1.
- `ChannelPeriodCalendar.vue:13-22`: era calendário de intervalo com `UiTimeField`, com motivo escrito ("o nativo não mostra o INTERVALO"). Virou quatro campos nativos. Ficaram restos:
  - `:today` em `ChannelSwitchDialog.vue:153`, uma prop que o componente não declara mais;
  - `monthWeeks`, `pickDay` e `monthLabel`, usados só por teste.
- A trava `kitOwnership.guardrails.test.ts:254` só procura `<input` cru e não varre `operator-kit/app`. Foi assim que o `<NuxtInput type="date">` passou.

**Os `Ui*` de data e hora são camada fina, não primitiva paralela.** Não têm markup próprio: compõem `NuxtInputDate`, `NuxtCalendar` e `NuxtInputTime` com o locale, o passo e os limites da casa. B.I. e Marketing já usam 12 vezes. O `operator-kitchen-sink.md:432-436` diz que eles não têm consumidor, e está errado.

**O componente da suíte:**

| Precisa de | Componente da suíte | Por baixo (Nuxt UI 4.11.3) |
|---|---|---|
| uma data | `UiDateField` | `InputDate` + `Calendar` em `Popover` |
| intervalo de datas | `UiDateRangeField` | `InputDate range` + `Calendar range` |
| uma hora | `UiTimeField` (passo 15 min em agenda) | `InputTime` |
| intervalo de horas | `UiTimeRangeField` | `InputTime range` |
| data e hora | `UiDateTimeField` | `InputDate` + `InputTime` |
| período com atalhos (Dia/Semana/Mês, 7D…) | `OperatorPeriodPicker` com `UiDateRangeField` no "Personalizado" | Popover + Tabs + o de cima |

Há um defeito a corrigir junto: no `UiDateTimeField.vue:58-71`, `min` e `max` aplicam só a data e perdem a hora-limite. O Marketing usa esse campo 4 vezes.

**A mesma classe de defeito em outras peças:**

| Peça | No Gestor | Veredito |
|---|---|---|
| busca | `NuxtCommandPalette` e `NuxtInput` com ícone | canônico; `UiSearchInput` não tem consumidor: apagar |
| filtro | `NuxtTabs` + `NuxtSelect` | canônico; o `FilterBar`/`UiFilterChip` do kit (PDV) quebrou na CI, e o tipo `date-range` do `FilterBar` não tem consumidor |
| seleção em lote | `NuxtTable` `row-selection` | canônico |
| paginação | `NuxtPagination` | canônico |
| ⋯ | dois desenhos: `NuxtPopover` + `NavigationMenu` vertical no pedido (`OrderCardMenu.vue:119, 159`), com ações em semântica de navegação; e `NuxtDropdownMenu` com ⋮ vertical no Catálogo (`catalog.vue:1566`) | um só: `DropdownMenu`, com ⋯ |
| vazio | `NuxtEmpty` | canônico |
| carregando | `NuxtSkeleton`, mas há spinner à mão (`i-line-md-loading-loop`) em 6 lugares: `index.vue:1515, 1526, 2062`, `CustomerMergeDialog.vue:287`, `OperatorReasonDialog.vue:183`, `OperatorSuiteSearch.vue:426` | prop `loading` |
| lista curta | `NuxtSelect` | `UiNativeSelect` tem 43 usos e o README (`:808`) manda manter: contradição, decisão do Pablo |

### P1-2. O aviso urgente leva ao pedido, mas não à resposta [tela]

A 390 px, "Responder no pedido" abre `/WEB-261007-I15#ifood-negotiations`, mas a tela para no topo. Antes do formulário de resposta vêm, nesta ordem:

- o banner de localização;
- "Pix · Pago", duas vezes;
- o card "Cliente", com uma palavra só;
- os itens.

O formulário fica três telas abaixo, logo depois de o modal dizer "faltam 6 min". Isso fere a regra do próximo foco. **Correção:** `data-focus-target` no bloco da negociação e `useNextFocus` ao chegar com o hash.

### P1-3. Hydration mismatch em toda página e em toda largura [tela]

"Hydration completed but contains mismatches" aparece no console em `/`, `/history`, `/catalog`, `/customers`, `/workstations`, `/feeds` e no detalhe, de 390 a 1440 px. Também aparece em `/preorders` do PDV, no kit novo e no `main`, então o defeito é anterior à migração e está no shell. O #1519 diz que ele acontece "na Grade e na Lista"; na verdade é em todo lugar.

### P1-4. A barra do celular ainda corta os rótulos [tela]

A 390 px aparecem "Pedid…", "Saí…" e "Ajust…", embora o #1518 declare isso corrigido. A faixa de filtros corta "Todo(s os canais)"; esse corte o #1518 admite.

### P1-5. Dois rails, dois toasters, rail sem "Avisos" [tela + código]

- **Rail:**
  - o rail do `OperatorSuiteShell.vue:131-166` é montado à mão, quando a receita é `NavigationMenu` vertical `collapsed`;
  - os outros 7 apps têm um segundo rail, também feito à mão (`OperatorSuiteRail` + `RailSection`);
  - no PDV em tela, o "Avisos" do rail perdeu o rótulo e virou um sino solto.
- **Toaster:** o Gestor usa `useToast` por um shim local (`utils/operatorToast.ts`); os outros 8 apps montam `OperatorSonner`. O lembrete do aviso urgente não chega a eles.

### P1-6. Vocabulário [tela + código]

- **"Ciente" e "Ciente de todos":** violam a decisão §2.1, que é "Visto"; o próprio aviso urgente usa "Visto".
- **"Agendados":** o nome fechado é "Encomendas".
- **"Etapa":** na Lista e no CSV mostra a situação; o Histórico chama a mesma coisa de "Situação".
- **O mesmo ato com vários nomes:**
  - despachar: "Saiu", "Despachar" e "Marcar saída para entrega";
  - retirar: "Retirou", "Entregar a Ana" e "Marcar como retirado";
  - acerto: quatro nomes;
  - despacho: dois diálogos diferentes (`[ref].vue:1164-1228` e `DispatchDialog.vue`).
- **"Falha na ação. Tente de novo."** aparece duas vezes ao mesmo tempo (no toast e no Alert do cartão) e não diz qual ação falhou.

### P1-7. "+9: mais 8 pedem você · em andamento: 1 na cozinha" [tela]

O "+9" soma duas grandezas diferentes. **Reescrita:** "Mais 8 pedem você · Ver todos".

### P1-8. Lista: o "Tempo" fica congelado [tela; o defeito já existia no `main`]

A Grade mostra "7 min" e "25 min"; a Lista mostra "10m" para todos. O cartão usa o relógio vivo (`useNowTick`), e a Lista usa o `elapsed_seconds` estático, com outra base e outro formato (`index.vue:1836`).

### P1-9. O kit mudou comportamento sem opt-in [código]

Mudanças que chegaram aos outros apps sem eles pedirem (detalhe no anexo D):

- a altura de toque de 48 px (`pointer: coarse`) saiu de input, select e textarea;
- o `UiFilterChip` perdeu o alvo de 44 px;
- o `#phone-actions` aparece no desktop;
- a busca inline virou modal no KDS, na Produção, no Marketing, no Compras e no B.I.

O README do kit e o ADR-026 pedem capability **opt-in**.

### P1-10. Card dentro de card sem decisão registrada [tela + código]

O "Em andamento" desenha um `NuxtCard` por grupo, dentro do card do painel (`QueueView.vue:603-714`). Isso contraria o `operator-kitchen-sink.md:253`. A decisão de 07/10 está só em comentário e numa regra global do tema (`app.config.ts:109`).

## Inventário "gesto antigo → onde mora agora"

Conferências mecânicas: as 11 páginas são as mesmas; os 51 endpoints `/api/v1` são os mesmos, com a mesma contagem; toda ação dos composables segue chamada; SSE e som estão intactos. A tabela completa, com arquivo:linha dos dois lados, está no anexo B.

| Gesto | Antes (main) | Agora | Status |
|---|---|---|---|
| Aceitar, avançar, pronto | `index.vue:657-667` | `index.vue:1152-1161` | mantido |
| Volumes | etiqueta abria num toque, `OrderCard.vue:296-303` | só pelo ⋯, `OrderCardMenu.vue:83-160` | alterado (2 toques) |
| Voltar para estação | `OrderCard.vue:653-666` | `OrderCardMenu.vue:101-107`, `QueueView.vue:575` | mantido |
| Recusa (iFood com motivo codificado) | `index.vue:520-588` | `index.vue:922-1020, 2044-2129` | mantido |
| Despacho (um toque ou `DispatchDialog`) | `index.vue:630-639` | `index.vue:1118-1132, 2147` | mantido; dois diálogos (P1-6) |
| Entregador voltou, acerto, maquininha | `index.vue:592-671` | `index.vue:1024-1165` | mantido |
| Troca de canal | `QueueView.vue:316`, `feeds` | `QueueView.vue:837`, `feeds.vue:840` | mantido [tela]; período nativo (P1-1) |
| Unificação de clientes | `customers/[ref].vue` | `customers/[ref].vue:357` | mantido [código] |
| NFC-e: reprocessar | link à vista | Popover da pílula, `OrderCard.vue:271-291` | alterado (+1 toque) |
| DANFE | botão à vista | à vista; Popover se não foi impressa | alterado |
| Negociação iFood | bloco no topo, em todas as visões | aviso urgente + Grade + detalhe | movido (decisão do dono); detalhe corrigido no #1520 |
| Atalhos | F/T, 1/2/3, S, R, V, A, ↑↓, Enter, `/`, ⌘K, Tab | F→G, T→L, o resto mantido | **Tab/Shift+Tab da busca: AUSENTE** |
| Puxar para atualizar | `index.vue:1113-1121` | `index.vue:1567-1579` | incerto (a rolagem agora é da coluna) |
| Deslizar o cartão (Atender/Recusar) | `SwipeReveal` | `OrderBoardColumn.vue:105-155` | mantido |
| Deslizar para entregar, polegar fixo (Saída do celular) | `PhoneExitList.vue` | apagado | **AUSENTE (P0-6)** |
| Faixa da coluna recolhida (abre UMA coluna; pulso da Entrada) | `QueueColumnStrip` | a coluna some | alterado (perde sinal) |
| Alvos de 48 px no posto Saída | prop `touch` | removida | alterado (perde ergonomia) |
| Sair da seleção | "Concluir" | "Sair da seleção" | corrigido no #1522 |
| SSE | `/sse/orders`, `useBackstageEvents`, `useAlerts` | iguais | mantido |

## Herança vista em tela

| App | Tela | `main` | #1519 | Com correção |
|---|---|---|---|---|
| PDV | `/settings/terminal` 1280 | seis abas de Ajustes; rail com "Avisos" rotulado | **sem abas**; "Avisos" vira sino sem rótulo | abas de volta (#1521); sino sem rótulo continua (P1-5) |
| PDV | `/settings/seating` 1280 | erro `reading 'filter'` no console | o mesmo erro | erro do mock, que não tem os dados do salão; não é regressão |
| PDV | `/preorders` 1280 | hydration mismatch | hydration mismatch | defeito anterior (P1-3) |

A Produção não foi aberta: o build exige `NUXT_DJANGO_BASE_URL` no build ("Shopman environment is not configured"), e não sobrou tempo para montar o mock dela. Os outros 6 apps também não foram abertos. O que se espera deles está no anexo D, pela leitura.

## Plano de fechamento

Frentes pequenas e independentes. Cada uma é um PR empilhado sobre o #1519 enquanto ele não entra; depois, contra o `main`.

| # | Frente | O que muda | Kit ou app | Herdam | Trava nova | Pronto em tela | Paralelo com |
|---|---|---|---|---|---|---|---|
| F0 | Select vazio, `#below`, "Sair da seleção" | feito: **#1520, #1521, #1522** | Gestor + kit | PDV, Marketing, Produção, Compras | dublê fiel + guard de template; teste do `#below`; constante do rótulo | visto (acima) | todas |
| F1 | CI verde dos herdeiros | corrigir os 3 testes do PDV e o `OperatorLogin` do Marketing contra o kit; ledger (registrar com motivo as 7 peças do Gestor ou subi-las ao kit); ler os logs Playwright e corrigir | kit | PDV, Marketing, Kitchen Sink, Produção | guard "slot passado e não declarado": compilar o template do consumidor contra os slots do kit | os 7 jobs verdes | F2, F3, F5 |
| F2 | Data, hora e período | `OperatorPeriodPicker` volta a `UiDateRangeField`/`UiDateField`; `ChannelPeriodCalendar` vira `UiDateRangeField` + `UiTimeRangeField` (passo 15); tirar os restos; `min`/`max` com hora no `UiDateTimeField`; corrigir a doc | kit + Gestor | B.I., PDV, Produção, Gestor, Marketing | `kitOwnership` varre `operator-kit/app` e pega `type="date\|time\|datetime-local\|month"` em qualquer tag | Canais e Histórico em `dd/mm/aaaa` 24 h, no calendário, a 390 e a 1440 | F1, F3 |
| F3 | Live Status | texto em pt-BR e os tons `ok/late/calm/offline` do README:422 | kit | os 9 | o guard do piloto passa a exigir os 4 tons, não o "On/Off" (decisão antes do teste) | Produção atrasada em âmbar | F1, F2 |
| F4 | Aviso leva à resposta | `data-focus-target` + `useNextFocus` com o hash | Gestor | modelo para os 9 | teste: chegada com `#ifood-negotiations` foca o bloco | a 390 o destino é o formulário | todas |
| F5 | Hydration | relógios e media queries só no cliente, no shell | kit | os 9 | e2e que reprova com "Hydration … mismatches" no console | console limpo nas 6 páginas | F1, F2 |
| F6 | Um ⋯, um rail, um toaster | ⋯ = `DropdownMenu`; rail = `NavigationMenu` `collapsed` com rótulos; `useToast` no kit (o shim sobe, o `OperatorSonner` morre); apagar órfãos (`UiSearchInput`, `OperatorRail`, `RailItem`, `OperatorAppBar`, `RailToggle`, `QueueColumnStrip`, `QueueColumnResizeHandle`) | kit + Gestor | os 9 | ledger proíbe Popover+NavigationMenu como menu de ação e proíbe montar Sonner | ⋯ igual nas duas telas; toast do aviso no PDV | depois de F1 |
| F7 | Gestos perdidos | Saída do celular: deslizar para entregar + polegar; Tab na busca; 48 px no posto Saída | Gestor + kit | — | o teste `gestorV6Gestures` volta | a 390, deslizar entrega | F2, F3 |
| F8 | Vocabulário | "Visto", "Encomendas", "Situação", um verbo por ato, um diálogo de despacho, falha com o nome do ato e num lugar só, "+N" sem soma | Gestor + rótulos do servidor | — | `guardrails.vocabulary` ganha "Ciente", "Agendado", "(s)", "novamente", "leitura" | varredura nas 6 páginas | todas |
| F9 | Kit opt-in | toque coarse, alvo do FilterChip, `#phone-actions` só no celular, busca inline atrás de prop | kit | os 7 não migrados | matriz de toque por consumidor | PDV e KDS em tablet com 48 px | depois de F1 |

**Ordem:** primeiro F1, que destrava a CI. Depois F2, F3, F4 e F5 em paralelo. Por último F6 a F9.

## Decisões que são do Pablo

1. **Lista curta:** (1) `UiNativeSelect` nativo, como você pediu em 10/09 (README:808); (2) `NuxtSelect` em tudo, como o Gestor fez.
2. **Saída do celular:** o deslizar para entregar e o polegar fixo voltam? (sim/não)
3. **Kit:** (1) as mudanças de comportamento ficam atrás de peça ou variante que só o Gestor usa, até cada app migrar; (2) migrar os 7 apps já.
4. **"Em andamento" com card dentro de card:** registrar como exceção no kitchen sink? (sim/não)
5. **#1516 ou #1518:** os dois seguem abordagens diferentes, e este laudo só auditou o #1518/#1519. (1) #1518; (2) #1516.

## O que NÃO foi verificado, e por quê

- **Django real:** o container não tem `.venv` nem banco. As telas são do mock, com fixtures gravadas do seed. Nenhum POST foi exercido de ponta a ponta.
- **Diálogos que não abri:**
  - **unificação de clientes:** o botão não foi achado pelo nome;
  - **despacho no detalhe:** o mock não oferece a ação;
  - **painel de produto do Catálogo:** clicar a linha não abre;
  - **recusa iFood:** o mock devolve `{}` em `cancellation-reasons` e o diálogo não desenha. O defeito é do mock; o servidor devolve `{reasons}`. Isso entra em F1.
- **Gestos de toque e teclado:** puxar para atualizar, deslizar e o teclado no Splitter não foram exercidos.
- **Offline e sessão expirada:** não foram simulados.
- **Navegadores:** só Chromium. Se o `type="date"` dentro de popover fechar o popover no Safari ou no Firefox, o P1-1 sobe para P0.
- **Herança:** a Produção não foi aberta, e os outros 6 apps também não. Os logs Playwright da CI não foram baixados.
- **Retratos e baselines:** não foram regerados. Só a sessão com o browser da CI regera.

---

Os anexos a seguir foram produzidos por quatro auditores de leitura de código, em paralelo, sem rodar nada. Valem como mapa de arquivo:linha. Onde um anexo diverge do corpo, vale o corpo, porque o corpo foi visto em tela.

## Anexo A. Primitivas e fuga do cânon (eixos 1 e 2)

### Laudo adversarial do Gestor (orders-nuxt) contra o cânone Nuxt UI: eixos 1 e 2 (mais a varredura do eixo 3)

Worktree: `/home/user/django-shopman/.claude/worktrees/gestor-canon-laudo`, HEAD `700f6aa63` (PR #1519, empilhado sobre #1518).
Base de comparação: `origin/main`. Auditoria só de leitura: nada foi editado, commitado ou trocado de branch.

Atribuição de commit (verificada com `git merge-base --is-ancestor` e `git log`): `origin/claude/orders-nuxt-ui-migration-b4c49c` = `bc6890171` é ancestral de HEAD, então os commits até `bc6890171` (o primeiro é `7e6bb83de WIP: migração canônica do Gestor...`) são da #1518, e de `a6a223f74` até `700f6aa63` são da #1519. Nas tabelas, **NOVO** = linha adicionada na pilha #1518/#1519 (`git diff -U0 origin/main...HEAD`), **pré** = já existia no `main`.

Versão: `@nuxt/ui` `^4.11.3` em `surfaces/operator-kit/package.json:46`; travada em `4.11.3` (`surfaces/operator-kit/package-lock.json:4172`). Prefixo dos componentes: `Nuxt` (`surfaces/operator-kit/nuxt.config.ts:33`), então `UInputDate` aparece no código como `NuxtInputDate`.
Tema: `surfaces/operator-kit/app/app.config.ts` (167 linhas). `surfaces/orders-nuxt/app/app.config.ts` só liga `operatorHeader.workstationBadge: false` (sem tema). O `app.config` do kit **não** define `ui.icons`, então os ícones internos do Nuxt UI usam o padrão `i-lucide-*`.

Como separar o que li do que inferi: tudo que tem `arquivo:linha` foi lido ou saiu de um comando. O que está marcado **(inferido)** não foi executado nem testado no navegador.

---

#### Resumo dos achados por severidade

| # | Sev. | Achado | Onde | Origem |
|---|---|---|---|---|
| 1 | **P1** | Kit trocou o campo de data canônico (`UiDateField`, que é `NuxtInputDate` + `NuxtCalendar`) por `NuxtInput type="date"` nativo no seletor de período. Isso vale para os 10 consumidores em 5 apps | `operator-kit/app/components/OperatorPeriodPicker.vue:248, 259, 294` | NOVO (#1518, `7e6bb83de`). No `main` eram `<UiDateField>` (linhas 264, 274, 300 do arquivo no main) |
| 2 | **P1** | O Gestor trocou o calendário de intervalo (que tinha motivo escrito: "o seletor nativo não mostra o INTERVALO") e dois `UiTimeField` por quatro campos nativos `type=date/time` | `orders-nuxt/app/components/ChannelPeriodCalendar.vue:13, 16, 19, 22` | NOVO (#1518) |
| 3 | **P1** | A trava `kitOwnership.guardrails.test.ts:250-262` só pega `<input type=...>` em minúsculas e só varre os apps, nunca o `operator-kit/app`. `<NuxtInput type="date">` passa, e um campo nativo dentro do kit também. Os achados 1 e 2 entraram sem acusar nada | `operator-kit/tests/kitOwnership.guardrails.test.ts:254` (regex `/<input(?=...)/i`) | pré |
| 4 | **P1** | O ⋯ do pedido é `NuxtPopover` + `NuxtNavigationMenu` vertical, não `NuxtDropdownMenu`. As ações caem na semântica de navegação (landmark/links), não na de menu. O ⋯ da linha do Catálogo usa `NuxtDropdownMenu` (`pages/catalog.vue:1566`), então são dois desenhos de ⋯ no mesmo app | `orders-nuxt/app/components/OrderCardMenu.vue:119, 159` | NOVO (#1519, `b0223fafb`) |
| 5 | **P1** | O rail do Gestor é um `<nav>` feito à mão com `NuxtTooltip`+`NuxtChip`+`NuxtButton` por item, e não `NuxtNavigationMenu orientation="vertical" collapsed`, que é a receita do próprio Kitchen Sink (contagem "mora no `chip` do item do `NavigationMenu`"). Os outros 7 apps usam um terceiro rail (`OperatorSuiteRail` + `RailSection`, feitos à mão). Resultado: dois rails paralelos na suíte | `operator-kit/app/components/OperatorSuiteShell.vue:131-166, 175-205` | NOVO (#1518) |
| 6 | **P1** | Dois sistemas de toast na suíte. O Gestor usa `useToast` do Nuxt UI por meio de um shim local, que apelida `useSonner` (`orders-nuxt/app/utils/operatorToast.ts`, `nuxt.config.ts:116`). Os outros 8 apps montam o `OperatorSonner` (vue-sonner) 9 vezes. O shim mora no app, não no kit, e cada app que migrar vai copiá-lo | `orders-nuxt/app/utils/operatorToast.ts:1-35`, `plugins/operator-toast.client.ts` | NOVO (#1518, `6fdbb5f29`) |
| 7 | **P1** | `UiDateTimeField` passa só a parte de data de `min`/`max` (`.slice(0,10)`) e não passa `min`/`max` ao `UiTimeField`. A hora-limite não é aplicada | `operator-kit/app/components/UiDateTimeField.vue:58-59, 64-71` | pré (consumido pelo Marketing, 4 usos) |
| 8 | **P1** | Documentação contradiz o código: o Kitchen Sink diz que `UiDateField`, `UiDateRangeField`, `UiDateTimeField`, `UiTimeField`, `UiTimeRangeField` e `UiStepper` não têm consumidor de produção. Têm: B.I. 3 e Marketing 9 (tabela abaixo). O README do kit diz que o "Outra data" do `OperatorDayPicker` abre o seletor nativo, mas ele usa `UiDateField` | `docs/reference/operator-kitchen-sink.md:432-436`; `operator-kit/README.md:903`; `OperatorDayPicker.vue:172` | doc: NOVO/pré misto |
| 9 | P2 | Ícone de carregamento fora do conjunto do tema (`i-line-md-loading-loop`) em vez da prop `loading` / `ui.icons.loading`. Em `index.vue:1515` o botão já tem `:loading`, então o ícone manual é redundante | `orders-nuxt/app/pages/index.vue:1515, 1526, 2062`; `components/CustomerMergeDialog.vue:287`; `operator-kit/app/components/OperatorReasonDialog.vue:183`; `OperatorSuiteSearch.vue:426` | NOVO (6) |
| 10 | P2 | `scrollIntoView` ad hoc por `document.querySelector`, contra a regra "Próximo foco" do CLAUDE.md | `orders-nuxt/app/pages/index.vue:805-807` | NOVO |
| 11 | P2 | Prop órfã: `ChannelSwitchDialog` passa `:today="clock"`, mas o novo `ChannelPeriodCalendar` não declara a prop. Ela cai como atributo HTML na `<div>` raiz. `monthWeeks`, `pickDay` e `monthLabel` (`presentation/channelSwitch.ts`) ficaram vivos só nos testes | `orders-nuxt/app/components/ChannelSwitchDialog.vue:153`; `presentation/channelSwitch.ts:106, 138, 161`; `tests/channelSwitch.test.ts:7-8` | NOVO (efeito do #1518) |
| 12 | P2 | Copy que não bate mais com a tela: "Escolha no calendário quando começa e quando termina.", e já não há calendário | `orders-nuxt/app/presentation/channelSwitch.ts:48` | pré; ficou falsa com o #1518 |
| 13 | P2 | Override de padding por instância no `DashboardToolbar` (`class="py-2"`) | `orders-nuxt/app/pages/index.vue:1483`; `operator-kit/app/components/OperatorPageHeader.vue:171` | NOVO |
| 14 | P2 | Valores arbitrários de grade sem motivo escrito | `orders-nuxt/app/components/QueueView.vue:249` (`80px`/`92px`/`240px`); `pages/catalog.vue:150, 1425` (`min-w-[260px]` repetido); `pages/catalog.vue:2029` (`max-h-[80vh] max-w-[85vw]`); `pages/workstations.vue:145` | NOVO |
| 15 | P2 | Vocabulário de token misto. `text-muted-foreground` (shadcn) aparece 180 vezes em `orders-nuxt/app`, e `text-muted` do Nuxt UI 0 vezes (só aparece como prefixo da forma shadcn). O tema mapeia um no outro (`operator-theme.css:116`), então o visual coincide, mas o Gestor ensina aos outros 8 apps a forma não-Nuxt UI | `orders-nuxt/app/**/*.vue` | majoritariamente NOVO |
| 16 | P2 | Duas grafias de ícone: `i-lucide-*` (252) e `"lucide:*"` (82, 52 NOVOS) em `orders-nuxt/app`. Mais 32 `<Icon>` do `@nuxt/icon` em vez de `NuxtIcon` | ver eixo 3 | misto |
| 17 | P2 | Componentes órfãos depois da migração: `QueueColumnStrip` e `QueueColumnResizeHandle` (o Gestor era o único consumidor no `main`); `OperatorRail`+`RailItem`, `OperatorAppBar`+`RailToggle`+`OperatorKbd` (este no AppBar) e `UiSearchInput`, todos com 0 consumidores | `operator-kit/app/components/*` | órfão: NOVO (efeito); código: pré |

**P0 confirmado: nenhum.** Candidato a P0 **(inferido, não testado)**: o `type="date"` nativo dentro do `NuxtPopover` do `OperatorPeriodPicker` (achado 1). Em Safari e Firefox, a janela do seletor nativo pode registrar o toque como "fora do popover", fechar o popover e perder o rascunho De/Até. Antes de fechar a severidade, isso tem que ser exercido num dispositivo real.

---

#### Eixo 1: data, hora e período

### 1.1 Os cinco `Ui*` temporais do kit: camada fina ou primitiva paralela?

Os cinco foram lidos por inteiro.

| Componente | Composição (lida) | Veredito | `:ui` por instância |
|---|---|---|---|
| `UiDateField.vue` (120 l.) | `NuxtInputDate` + `NuxtPopover` + `NuxtButton` + `NuxtCalendar`. Converte ISO `YYYY-MM-DD` ↔ `CalendarDate` | **Camada fina**: a anatomia é toda do Nuxt UI | `:89` `:ui="{ content: 'z-[60]' }"` (valor arbitrário de z, sem motivo escrito) |
| `UiDateRangeField.vue` (217 l.) | `NuxtInputDate range` + `NuxtPopover` + `NuxtCalendar range` (2 meses no desktop) + botões "Sem início / Sem fim / Limpar" | **Camada fina** com um acréscimo de domínio (limpar uma ponta) | `:140` `:ui="inputUi"` (largura dos segmentos no celular, com motivo no comentário `:89-95` do script); `:146` `z-[60]` |
| `UiTimeField.vue` (71 l.) | `NuxtInputTime` 24h, `step.minute`, `step-snapping`. ISO `HH:mm` | **Camada fina** | nenhum |
| `UiTimeRangeField.vue` (97 l.) | `NuxtInputTime range` | **Camada fina** | nenhum |
| `UiDateTimeField.vue` (74 l.) | `UiDateField` + `UiTimeField` lado a lado, numa `grid-cols-[minmax(0,1fr)_minmax(7rem,0.55fr)]` | **Composição** de dois finos. O motivo está escrito (`:2-3`: "evita o datetime-local estreito"). **Defeito** (achado 7): `min`/`max` de hora se perdem | nenhum (mas usa grade arbitrária em `:49`) |

Nenhum dos cinco tem markup próprio de calendário ou de segmentos. Os cinco são a forma ISO-string dos componentes oficiais.

### 1.2 Quem consome cada um (contagem por app, `app/` sem testes)

Comando: `consumers.py` (varre `surfaces/*/app/**/*.vue|ts`, ignora o próprio arquivo e `node_modules/.nuxt/.output`).

| Componente | bi | marketing | pos | production | purchase | orders | operator-kit | total |
|---|---|---|---|---|---|---|---|---|
| `UiDateField` | 3 | 0 | 0 | 0 | 0 | 0 | 2 (`UiDateTimeField`, `OperatorDayPicker`) | 5 |
| `UiDateRangeField` | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| `UiTimeField` | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 2 |
| `UiTimeRangeField` | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| `UiDateTimeField` | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 4 |
| `OperatorPeriodPicker` | 2 | 0 | 1 | 6 | 0 | 1 (`pages/history.vue:146`) | 0 | 10 |
| `OperatorDayPicker` | 0 | 0 | 1 | 0 | 2 | 0 | 0 | 3 |
| `ChannelPeriodCalendar` | | | | | | 1 (`ChannelSwitchDialog.vue:150`) | | 1 |

Locais: `bi-nuxt/app/components/BiPeriodChip.vue:89, 92`, `BiDayStepper.vue:40`; `marketing-nuxt/app/components/MarketingOfferForm.vue:287, 305`, `CampaignForm.vue:944, 1016, 1058`, `GoogleBusinessPostOptions.vue:101, 115`, `AnnouncementCard.vue:880`; `production-nuxt/app/components/ProductionStageGrid.vue:1001`, `pages/board.vue:127`, `mise-en-place.vue:178`, `reports.vue:160, 355`, `close.vue:423`; `pos-nuxt/app/pages/preorders/index.vue:345`, `components/PosSchedulePicker.vue:77`; `purchase-nuxt/app/components/ReceiptExceptionFlow.vue:335`, `ReceiptLineSheet.vue:402`.

### 1.3 Todo campo temporal nativo nas superfícies

Comando: `grep -rn` por `type="(date|time|datetime-local|month|week)"` e `:type=` em `surfaces/` (sem `node_modules`, `.output`, `.nuxt`, `tests`).

| Local | Campo | Origem |
|---|---|---|
| `orders-nuxt/app/components/ChannelPeriodCalendar.vue:13` | `NuxtInput type="date"` (início) | NOVO #1518 |
| `orders-nuxt/app/components/ChannelPeriodCalendar.vue:16` | `NuxtInput type="time" :step="900"` | NOVO #1518 (no main era `UiTimeField :minute-step="15"`) |
| `orders-nuxt/app/components/ChannelPeriodCalendar.vue:19` | `NuxtInput type="date"` (término) | NOVO #1518 |
| `orders-nuxt/app/components/ChannelPeriodCalendar.vue:22` | `NuxtInput type="time" :step="900"` | NOVO #1518 (no main era `UiTimeField`) |
| `operator-kit/app/components/OperatorPeriodPicker.vue:248` | `NuxtInput type="date"` (De) | NOVO #1518 (no main era `UiDateField`) |
| `operator-kit/app/components/OperatorPeriodPicker.vue:259` | `NuxtInput type="date"` (Até) | NOVO #1518 (no main era `UiDateField`) |
| `operator-kit/app/components/OperatorPeriodPicker.vue:294` | `NuxtInput type="date"` (Ir para o dia) | NOVO #1518 (no main era `UiDateField`) |
| `operator-kit/app/components/FilterBar.vue:272, 285` | `NuxtInput :type="date-range ? 'date' : 'number'"` | lógica pré (no main era `<input>` cru, linha 304 do main). O PR só trocou a casca. **Latente**: nenhum consumidor declara dimensão `date-range` (grep sem resultado fora do kit) |
| `storefront-nuxt/app/pages/conta/perfil.vue:261` | `UiInput type="date"` (aniversário) | fora do escopo: o Storefront tem biblioteca própria e não estende o kit |

Total de operador: **9 campos nativos** (4 no Gestor e 5 no kit). Os 9 vieram da pilha #1518/#1519. Os 7 do Gestor e do `OperatorPeriodPicker` **substituíram** componentes canônicos que já existiam. Ou seja, nessa parte a migração andou para trás.

Detalhe do `ChannelPeriodCalendar` no `main` (lido via `git show origin/main:...`): era um calendário de mês feito à mão, com `<button>` cru e classes copiadas, portanto também fora do cânone. Mas o comentário dava o motivo funcional: "o seletor nativo não mostra o INTERVALO; férias de duas semanas se conferem de olho". Ele também bloqueava dias passados (`:disabled="day.past"`). O substituto certo era `NuxtCalendar range`, que mostra o intervalo, e não `type="date"`. O que sobrou do intervalo é a frase do `NuxtAlert` (`:25-32`). A validação de "fim no passado" continua em `missingStep` (`channelSwitch.ts:53-54`).

### 1.4 Recomendação: o componente da suíte por tipo

O critério é o do próprio Kitchen Sink (`operator-kitchen-sink.md:412-414`: receitas com `NuxtInputDate` e `NuxtInputTime`), mais o fato de que as APIs da suíte falam ISO-string. Os `Ui*` temporais já são essa borda ISO fina sobre o oficial e têm consumidores reais, então devem ser **adotados como o cânone** em vez de apagados. A alternativa (`NuxtInputDate` direto em todo app) espalharia `parseDate`/`toString` por 8 apps.

| Tipo | Componente oficial Nuxt UI 4.11.3 | Peça da suíte | Migram para ela |
|---|---|---|---|
| Data | `InputDate` (+ `Popover` + `Calendar` no trailing) | `UiDateField` | `OperatorPeriodPicker.vue:294` |
| Intervalo de datas | `InputDate range` + `Calendar range` | `UiDateRangeField` | `OperatorPeriodPicker.vue:245-264` (De/Até, com `min`/`max`); `ChannelPeriodCalendar.vue:13, 19` (com `min` = hoje da loja); `FilterBar.vue:268-289` quando `step.type === 'date-range'` |
| Hora | `InputTime` | `UiTimeField` | `ChannelPeriodCalendar.vue:16, 22` (`:minute-step="15"`, como era no main) |
| Intervalo de horas | `InputTime range` | `UiTimeRangeField` | nenhum pendente (Marketing já usa) |
| Data e hora | `InputDate granularity="minute"` (um campo só, com `CalendarDateTime`) **(inferido: a API Reka/Nuxt UI aceita, mas não foi testado aqui)**, ou a composição atual | `UiDateTimeField` | Antes de qualquer migração, corrigir o achado 7 (passar `min`/`max` de hora ao `UiTimeField`, ou trocar por `InputDate granularity="minute"`). Alternativa para o `ChannelPeriodCalendar`: dois `UiDateTimeField` (início e término) |

O que morre:
- os 4 nativos do Gestor e os 5 do kit;
- `monthWeeks`, `pickDay`, `monthLabel` e `isoDay` (`orders-nuxt/app/presentation/channelSwitch.ts:102-163`), com os testes correspondentes, se ninguém mais os usar (hoje só `tests/channelSwitch.test.ts`);
- a prop `:today` em `ChannelSwitchDialog.vue:153`, ou ela vira `min` do `UiDateRangeField`.

O que precisa mudar junto:
- a trava `kitOwnership.guardrails.test.ts:250-262` passa a casar `<(input|NuxtInput|UiInput)` e a varrer também `operator-kit/app`;
- a copy de `channelSwitch.ts:48`.

`OperatorDayPicker` (Tipo 1, decisão do dono de 02/10/2026) e `OperatorPeriodPicker` (Tipo 2, decisão do dono de 02/10/2026) ficam como **decisões fechadas** de desenho. O que se aponta é só a anatomia por dentro:
- `OperatorDayPicker.vue:129-166` são `<button role="radio">` crus com `tileClass` copiado (`:112-119`). O equivalente oficial é `NuxtRadioGroup variant="card"`. O "Outra data" já é `UiDateField` (`:172`), que está certo.
- `OperatorPeriodPicker` usa `NuxtTabs variant="pill"` como seletor de preset (`:208-237`). É aceitável como segmentado. O defeito está só nos campos de data.

---

#### Eixo 2: as outras classes de primitiva

Composição lida com `anat.py` (conta `<Nuxt*>`, elementos crus e `:ui=` por arquivo) e consumidores com `consumers.py`. Colunas: bi / hub / kds / mkt / pos / prod / purch / **orders** / kit.

**Constatação central (verificada):** o `orders-nuxt/app` não consome **nenhum** `Ui*` do kit. Todas as contagens da coluna orders são 0. Ele usa 40 componentes Nuxt UI diretamente (`NuxtButton` 155, `NuxtAlert` 71, `NuxtFormField` 61, `NuxtBadge` 54, `NuxtInput` 45, `NuxtCard` 30, `NuxtEmpty` 18, `NuxtSkeleton` 16, `NuxtSelect` 13, `NuxtCheckbox` 13, `NuxtModal` 10, `NuxtDropdownMenu` 5, `NuxtTable` 5, `NuxtPagination` 3, `NuxtKbd` 2 etc.). No `main`, ele consumia `UiCheckbox` 11, `UiIconButton` 11, `UiNativeSelect` 8, `UiSkeleton` 9, `UiSwitch` 5, `UiFilterChip` 5, `UiTimeField` 2, `QueueColumnStrip`, `QueueColumnResizeHandle`, `OperatorSuiteRail`, `OperatorSectionBar` e `OperatorSonner` (contagem por `git grep` em `origin/main`; só pega a primeira linha da tag, então pode estar subestimada).

| Peça | Fina ou paralela (lido) | Consumidores | Canônico | Quem migra / o que morre |
|---|---|---|---|---|
| **Busca** `UiSearchInput` | **Paralela**: `<input>` + `<kbd>` + `<button>` crus, classes copiadas, `suite:text-[15px]` (`UiSearchInput.vue:31-58`) | **0** em todos | `NuxtInput icon` / `DashboardSearchButton` + `CommandPalette` | Morre (código morto). O Gestor usa `OperatorSuiteSearch` (4 telas), que é `NuxtDashboardSearchButton` + `NuxtModal` + `NuxtTabs` + `NuxtCommandPalette` (`OperatorSuiteSearch.vue:274-300`). É fino, mas recompõe o `DashboardSearch` oficial em vez de usá-lo, o que contradiz `operator-kitchen-sink.md` ("A busca usa `DashboardSearch` e `DashboardSearchButton`"). Os dois campos de busca locais do Gestor (`CustomerMergeDialog.vue:206`, `CatalogBindingReview.vue:80`) são `NuxtInput type="search"` sem ícone, aceitáveis |
| **Filtros** `FilterBar` | **Composição fina**: `NuxtFieldGroup`, `NuxtPopover`, `NuxtButton` ×9, `NuxtInput` ×4, `NuxtForm`, `NuxtEmpty`, sem elementos crus. O Nuxt UI não tem FilterBar, então é composição legítima | kit 1, orders 2, pos 1 | idem | Só o `date-range` nativo (eixo 1) |
| `UiFilterChip` | **Fina**: `NuxtButton` + `NuxtBadge` (`UiFilterChip.vue:11-25`), marcada no próprio arquivo como "compatibilidade temporária" | bi 4, kds 3, mkt 3, pos 1, prod 2, purch 5, kit 2 (20); orders 0 (migrou para `NuxtTabs`) | `NuxtTabs` (segmentado) ou `NuxtButton` | Os 7 apps migram para `NuxtTabs`; depois o arquivo morre |
| `UiToggleChip` | **Paralela**: `<button role="checkbox">` cru com classes de seleção copiadas (`:54-74`) | mkt 1 (`CampaignForm.vue:1036`) | `NuxtCheckboxGroup variant="card"` / `NuxtButton` com `active` | Marketing; depois morre |
| **Seleção em lote** `UiCheckbox` / `UiCheckboxGroup` | **Finas**: `NuxtCheckbox` / `NuxtCheckboxGroup` + `:ui` por instância (`UiCheckbox.vue:73`, `UiCheckboxGroup.vue:105`) | UiCheckbox: mkt 9, pos 1, prod 7, purch 1 (18). UiCheckboxGroup: mkt 14, kit 1 | `NuxtCheckbox` / `NuxtCheckboxGroup` direto; tabela com `row-selection` | O Gestor já faz o canônico: `NuxtTable :row-selection` (`pages/index.vue:1734`, `pages/catalog.vue:1329`) + `NuxtCheckbox` nos slots. O `:ui` dos wrappers deve subir para o `app.config` (o alvo de toque já está lá, `app.config.ts:5-10`), e depois os wrappers morrem |
| **Paginação** | não há wrapper | orders: `NuxtPagination` ×3 (`customers/index.vue:230`, `index.vue:1980`, `history.vue:284`) | `NuxtPagination` | Canônico |
| **⋯ menu** | O Gestor tem **dois desenhos**: `OrderCardMenu.vue:119-162` (`NuxtPopover` + `NuxtNavigationMenu vertical`, com um editor `NuxtInputNumber` embutido) e `NuxtDropdownMenu` (`BoardMenu.vue:178`, `CatalogProductPanel.vue:700`, `index.vue:1324`, `catalog.vue:1076, 1566`) | orders | `NuxtDropdownMenu`. O editor de volumes vai num `NuxtPopover` ou `NuxtModal` aberto a partir de um item do menu | Gestor (achado 4, NOVO #1519) |
| **Vazio** | não há wrapper | orders `NuxtEmpty` ×18 | `NuxtEmpty` | Canônico. Observação: `index.vue:2062` usa `NuxtEmpty` com ícone de spinner como estado de carregamento, mistura de papéis (P2) |
| **Carregando** `UiSkeleton` | **Fina**: `NuxtSkeleton` + `aria-label` em pt-BR (`UiSkeleton.vue:13-15`) | mkt 10, pos 5; orders usa `NuxtSkeleton` ×16 direto | `NuxtSkeleton`. O rótulo pt-BR deveria vir do locale do `OperatorAppRoot` **(inferido: não verifiquei se o Skeleton 4.11.3 lê o locale)** | Marketing e PDV migram; morre quando o rótulo vier do locale |
| `UiSelect` | **Fina**: `NuxtSelectMenu` + `:ui` (`:163`) com `z-[60]` (`:126`) | mkt 9, purch 1 | `NuxtSelectMenu` | Subir o `z-[60]` para o `app.config` e depois migrar |
| `UiNativeSelect` | **Paralela**: `<select>` cru (`:59`) + CSS global de chevron (`operator-theme.css:197-212`, "pedido Pablo 2026-09-10") | bi 8, mkt 4, pos 4, prod 18, purch 9 (**43**); orders 0 (migrou para `NuxtSelect` ×13) | `NuxtSelect` | **Contradição com decisão anterior**: `operator-kit/README.md:808` diz que ele "continua sendo a peça certa" para lista curta. Não tratado como defeito a desfazer. Fica registrado que o Gestor já não segue essa regra |
| `UiRadio` / `UiRadioGroup` | **Paralela**: `<button role="radio">` cru, teclado reimplementado (`UiRadio.vue:78-81`, `UiRadioGroup.vue:77`) | UiRadio mkt 4, kit 1; UiRadioGroup mkt 6, pos 1, purch 1 (8) | `NuxtRadioGroup` (o Gestor usa ×3) | A trava `kitOwnership.guardrails.test.ts:246` **manda usar** `<UiRadioGroup>`, então empurra para a primitiva paralela. Trocar a mensagem |
| `UiSwitch` | **Fina**: `NuxtSwitch` + `:ui` (`:29-40`). Duplica a ampliação de alvo que o `app.config.ts:11-15` já faz globalmente **(inferido: as duas regras `after:` somam; não medido)** | mkt 4, pos 11 (15); orders usa `NuxtSwitch` ×5 | `NuxtSwitch` | Migram; o wrapper morre |
| `UiStepper` | **Fina**: `NuxtStepper` + `:ui` responsivo com `calc(50%+36px)` (`:40`, `:57`) | mkt 1 | `NuxtStepper` | Kitchen Sink `:155` manda "fluxos com etapas usam `UiStepper`", enquanto `:432` o lista como sem consumidor e o laudo de 06/10 diz que o exemplo usa `NuxtStepper` direto. Contradição interna do doc |
| `UiButton` | **Fina com API paralela**: traduz variantes shadcn (`default`/`destructive`/`ghost`, `icon-sm`...) para `NuxtButton` + `:ui` (`:125`) + `loadingIcon: "line-md:loading-loop"` (`:42`) | bi 3, mkt 82, pos 187, prod 96 (**368**) | `NuxtButton` | O doc (`operator-kitchen-sink.md:124-126`) aceita como "tradução legada". É a maior dívida em volume; o Gestor já está fora dela |
| `UiIconButton` | **Paralela**: `<button>` cru (`:17-25`) | bi 2, mkt 5, pos 1, prod 1, purch 1 (10); orders 0 (no main eram 11) | `NuxtButton square icon` | 5 apps; depois morre |
| `UiScrim` | **Paralela**: `<button>` fixo, `backdrop-blur-[1px]` (`:15, :21`) | pos 1 (`PosCartPanel.vue:924`) | overlay de `NuxtSlideover` / `NuxtDrawer` | PDV; depois morre |
| `OperatorSonner` | **Paralela** (vue-sonner, não Nuxt UI), com CSS vars inline (`:15-28`) | bi, hub, kds, kitchensink, mkt, prod, purch 1 cada; pos 2 (9); orders 0 | `useToast` + toaster do `OperatorAppRoot` | Subir o shim `orders-nuxt/app/utils/operatorToast.ts` para o kit, migrar os 8 apps, apagar `OperatorSonner` e o pacote (achado 6) |
| `OperatorConfirmDialog` | **Fina**: `NuxtModal` + `NuxtButton` (`:28-48`) | kit 1 (montado pelo `OperatorPwaRuntime`) | `NuxtModal` | Canônico |
| `OperatorReasonDialog` | **Fina**: `NuxtModal`, `NuxtSelect`, `NuxtTextarea`, `NuxtAlert` ×3, `NuxtEmpty`. Nenhum elemento cru | orders 1, pos 1 | `NuxtModal` | Canônico, exceto o spinner `i-line-md` em `:183` (NOVO) |
| `OperatorKbd` | **Paralela**: `<kbd>` cru com classes (`:15-27`) | pos 23, prod 1, kit 1 (no `OperatorAppBar`, que está morto); orders usa `NuxtKbd` ×2 | `NuxtKbd` (variante `soft` já é o padrão no `app.config.ts:34-36`) | PDV e Produção; depois morre |
| `OperatorNumpad` | **Paralela**: 4 `<button>` crus (`:36-65`) | prod 2 | O Nuxt UI não tem numpad; o certo é compor com `NuxtButton` | Produção (P2) |
| `OperatorDayPicker` | **Paralela** (ver eixo 1) | pos 1, purch 2 | `NuxtRadioGroup variant="card"` + `UiDateField` | PDV e Compras; a decisão de desenho do dono fica |
| `ColumnPicker` | **Composição fina**: `NuxtPopover` + `NuxtCheckbox` + `NuxtButton` | orders 1 | Na doc do `Table` do Nuxt UI, a visibilidade de colunas é `NuxtDropdownMenu` com itens `type: 'checkbox'` | Gestor (P2) |
| `QueueColumnStrip` / `QueueColumnResizeHandle` | **Paralelas** (`<button>` cru, `suite:` com `shadow-[...]`, `dark:text-orange-300`) | **0** (órfãos depois da #1518; no main, o único consumidor era o Gestor) | | Morrem |
| `RailItem` / `OperatorRail` | Paralelas | `RailItem` só no `OperatorRail`; **`OperatorRail` tem 0** | `NuxtNavigationMenu vertical` | Morrem |
| `RailToggle` / `OperatorAppBar` | Paralelas | `RailToggle` só no `OperatorAppBar`; **`OperatorAppBar` tem 0** | | Morrem |
| `RailSection` / `OperatorSuiteRail` | **Paralelas**: `<kbd>` cru, `text-[9.5px]`, `size-[22px]`, `w-[68px]` etc. (`RailSection.vue:68-102`), e o `OperatorSuiteRail` importa `reka-ui` direto (`PopoverRoot...`) | OperatorSuiteRail: bi, hub, kds, mkt, pos, prod, purch (7); orders 0 | `NuxtDashboardSidebar` + `NuxtNavigationMenu orientation="vertical" collapsed` com `chip` no item | Os 7 apps migram para `OperatorSuiteShell`, **depois** que o rail do `OperatorSuiteShell` virar `NuxtNavigationMenu` (achado 5). Aí morrem `OperatorSuiteRail` e `RailSection` |
| `OperatorSectionBar` | **Fina**: `NuxtNavigationMenu` | bi, kds, mkt, pos, prod, purch (6); orders 0 (o `OperatorSuiteShell:252-271` tem a própria barra com `NuxtNavigationMenu`) | idem | Duas barras de celular; unificar no `OperatorSuiteShell` |
| Biblioteca `components/Ui/` (estilo shadcn sobre Reka: `Dialog`, `Sheet`, `Popover`, `Tooltip`, `Tabs`, `Card`, `Alert`, `Badge`, `Input`, `Textarea`) | **Paralela inteira** ao Nuxt UI (ex.: `Ui/Input.vue:3` `<input>`, `Ui/Popover/X.vue:29` `heroicons:x-mark`) | UiDialog 60 (kds 3, mkt 8, pos 33, prod 14, purch 2), UiInput 78, UiBadge 23, UiPopover 15, UiSheet 11, UiTextarea 21 (fora do storefront, que tem biblioteca própria); orders 0 | `NuxtModal`, `NuxtSlideover`/`NuxtDrawer`, `NuxtPopover`, `NuxtTooltip`, `NuxtTabs`, `NuxtCard`, `NuxtAlert`, `NuxtBadge`, `NuxtInput`, `NuxtTextarea` | Fora do escopo do Gestor, mas é a maior primitiva paralela que sobra para os outros 8 apps |

---

#### Eixo 3: fuga do cânone em `orders-nuxt/app` e `operator-kit/app` (varredura)

Comando: `scan.py` (regex por linha, sem linhas de comentário), cruzado com as linhas adicionadas de `git diff -U0 origin/main...HEAD`.

### orders-nuxt/app

| Categoria | Total | NOVO | Notas |
|---|---|---|---|
| `:ui=` / `ui="` | **0** | 0 | limpo |
| `<button>`, `<input>`, `<select>`, `<table>`, `<textarea>`, `<kbd>` crus | **0** | 0 | limpo |
| Temporal nativo | 4 | 4 | `ChannelPeriodCalendar.vue:13, 16, 19, 22` (P1) |
| Valor arbitrário de Tailwind (reais; os acertos em `arr[0]` foram descartados à mão) | 8 | 8 | `CustomerMergeDialog.vue:241` (motivo no comentário `:240`, ok); `QueueView.vue:249` (sem motivo, P2); `catalog.vue:150, 1425` `min-w-[260px]` (sem motivo, P2); `catalog.vue:1319` (motivo em `:1314-1317`, ok); `catalog.vue:1349` `max-w-[40%]` (skeleton, P2); `catalog.vue:2029` `max-h-[80vh] max-w-[85vw]` (P2); `settings.vue:36` `gap-[var(--op-region-gap)]` (documentado no Kitchen Sink, ok); `workstations.vue:145` (P2) |
| Cor fixa (`text-red-*`, hex etc.) | **0** | 0 | limpo |
| `onclick` / `onchange` | 0 | 0 | |
| `document.querySelector` / `getElementById` | 1 | 1 | `pages/index.vue:806` → `scrollIntoView` ad hoc (P2) |
| `:style` inline | 3 | 1 | `SwipeReveal.vue:92` (NOVO), `:116` (pré), `index.vue:1570` (pré). Os três são geometria de gesto (largura/translate/altura do puxar para atualizar), aceitáveis |
| Ícone fora do Lucide | 5 | 4 | `i-line-md-loading-loop`: `CustomerMergeDialog.vue:287`, `index.vue:1515, 1526, 2062` (NOVOS); `catalog.vue:1819` `line-md:loading-loop` (pré) |
| Grafia `"lucide:x"` em vez de `i-lucide-x` | 82 | 52 | maiores: `OrderCard.vue` 15, `presentation/board.ts` 11, `presentation/catalog.ts` 10, `index.vue` 10 |
| `<Icon>` (@nuxt/icon) em vez de `NuxtIcon` | 32 | n/d | `OrderCard.vue` 6, `QueueView.vue` 5, `catalog.vue` 5, ... |
| `class` visual em componente Nuxt | 24 | n/d | 14 em `NuxtSkeleton` (formato da tela, legítimo); `NuxtDashboardToolbar class="py-2"` em `index.vue:1483` (P2); `NuxtLink` com `hover:underline` ×6 (imita `ULink`; P2. Atenção: com `prefix: "Nuxt"`, o `ULink` do Nuxt UI teria o mesmo nome do `NuxtLink` do Nuxt, **(inferido)** conflito de nome não verificado) |

### operator-kit/app

| Categoria | Total | NOVO | Notas |
|---|---|---|---|
| `:ui=` por instância | 14 | 0 | todos pré: `UiButton.vue:125`, `UiCheckbox.vue:73`, `UiCheckboxGroup.vue:105`, `UiDateField.vue:89`, `UiDateRangeField.vue:140, 146`, `UiSelect.vue:163`, `UiStepper.vue:57`, `UiSwitch.vue:50`, `OperatorPage.vue:16`, `OperatorPushSettings.vue:153`, `OperatorKitchenSinkDashboard.vue:66`, `OperatorKitchenSinkExercises.vue:576, 608` |
| `<button>` cru | 20 | 0 | `MoreBelow.vue:82`, `OperatorCapacityStatus.vue:44`, `OperatorDayPicker.vue:130, 151`, `OperatorNumpad.vue:36, 47, 56, 65`, `OperatorPushSettings.vue:78, 88, 118, 170`, `OperatorSuiteRail.vue:273`, `QueueColumnStrip.vue:49`, `RailToggle.vue:24`, `UiIconButton.vue:17`, `UiRadio.vue:78`, `UiScrim.vue:21`, `UiSearchInput.vue:50`, `UiToggleChip.vue:54` |
| `<input>` / `<select>` / `<textarea>` / `<table>` / `<kbd>` crus | 2 / 1 / 1 / 2 / 3 | 0 | `Ui/Input.vue:3`, `UiSearchInput.vue:33`; `UiNativeSelect.vue:59`; `Ui/Textarea.vue:2`; `OperatorKitchenSink.vue:486, 900` (tabela de documentação); `OperatorKbd.vue:19`, `RailSection.vue:87`, `UiSearchInput.vue:44` |
| Temporal nativo | 5 | 5 | `OperatorPeriodPicker.vue:248, 259, 294` (P1); `FilterBar.vue:272, 285` (lógica pré) |
| Valor arbitrário (reais) | ~55 | 14 | NOVOS com motivo escrito: `app.config.ts:28` (Chip `4xl`), `:54-96` (`color-mix` dos Alerts). NOVOS sem motivo: `FilterBar.vue:164`, `OfflineBanner.vue:21` (`z-[100]`), `OperatorInbox.vue:143`, `OperatorKitchenSink.vue:598`, `OperatorPeriodPicker.vue:200`, `OperatorPwaRuntime.vue:61` (`bottom-[calc(...)] z-[60] w-[28rem]`), `OperatorSuiteSearch.vue:272, 337`. Pré e concentrados em peças paralelas: `RailSection.vue:68-102` (8), `QueueColumnStrip.vue:52-78`, `OperatorSuiteRail.vue:147-275`, `Ui/*` |
| Cor fixa | 84 | 0 | 81 em `assets/css/operator-theme.css` (definição de token, legítimo), 2 em `operator-suite.css:42-43` (`--suite-badge` em hex, token), 1 em `QueueColumnStrip.vue:79` (`dark:text-orange-300`, componente morto) |
| `getElementById` / `querySelector` | 5 | 0 | `OperatorKitchenSink.vue:31, 51, 191`; `UiSelect.vue:81`; `utils/operatorShortcuts.ts:66` |
| `:style` inline | 6 | 1 | `OperatorAppSeal.vue:52` (NOVO, cor do app vinda do registro, legítimo); `OperatorSonner.vue:15` (pré, CSS vars do sonner) |
| Ícone fora do Lucide | 4 | 2 | `OperatorReasonDialog.vue:183`, `OperatorSuiteSearch.vue:426` (`i-line-md`, NOVOS); `Ui/Popover/X.vue:29` (`heroicons:x-mark`), `UiButton.vue:42` (`line-md`) |
| Grafia `"lucide:x"` | 57 | 17 | `OperatorOrderDetail.vue` 13, `presentation/workstation.ts` 7 |

**Ícones (verificado):** o kit instala quatro coleções (`@iconify-json/lucide`, `heroicons`, `line-md`, `tabler`; `operator-kit/package.json:40-43`). O `app.config.ts` não define `ui.icons`, então o Nuxt UI usa os Lucide padrão. Se o spinner `line-md` for uma decisão de marca, o lugar dele é `ui.icons.loading` no `app.config` do kit, junto com a prop `loading` nos botões. Não é ícone por instância.

---

#### Contradições entre documentação e código (registro, não defeito a desfazer)

1. `operator-kitchen-sink.md:432-436`: lista `UiDateField`, `UiDateRangeField`, `UiDateTimeField`, `UiTimeField`, `UiTimeRangeField` e `UiStepper` como "sem consumidor de produção". Falso: B.I. 3, Marketing 9, mais 1 `UiStepper` no Marketing.
2. `operator-kitchen-sink.md:412-414`: a receita canônica é `NuxtInputDate` e `NuxtInputTime`. A #1518 pôs `type="date"` nativo no kit e no Gestor, o contrário da receita.
3. `operator-kitchen-sink.md:155`: "Fluxos com etapas usam `UiStepper`". A seção de 06/10 diz que o exemplo usa `NuxtStepper` direto e que o wrapper ainda espera decisão.
4. `operator-kit/README.md:903`: o "Outra data" do `OperatorDayPicker` "abre o seletor nativo". O código usa `UiDateField` (`OperatorDayPicker.vue:172`).
5. `kitOwnership.guardrails.test.ts:246, 260`: as mensagens da trava mandam usar `UiCheckbox`, `UiRadioGroup` e `UiDateField`/`UiTimeField`/`UiDateTimeField`. O `UiRadioGroup` é primitiva paralela, e o Gestor (já canônico) usa `NuxtRadioGroup`/`NuxtCheckbox`.
6. `operator-kit/README.md:808` e `operator-theme.css:197` (pedido do dono, 10/09/2026): `UiNativeSelect` "continua sendo a peça certa" para lista curta. O Gestor migrou para `NuxtSelect`. As duas regras não podem valer juntas nos 9 apps; a decisão é do dono.
7. `operator-kitchen-sink.md` ("A contagem de uma seção mora no `chip` do item do `NavigationMenu`"): vale para a barra do celular (`OperatorSuiteShell.vue:259`), mas não para o rail (`:131-166`, Button+Chip à mão).

---

#### O que não foi feito ou verificado

- Nenhum teste, build ou navegador foi rodado. Severidades de comportamento marcadas "(inferido)" pedem teste em dispositivo real: popover com data nativa, soma do `after:` no `UiSwitch`, locale do `NuxtSkeleton`, `InputDate granularity="minute"`, colisão de `NuxtLink`.
- Os PRs não foram consultados no `gh` (o comando falhou nesta sessão). A atribuição #1518/#1519 saiu da ancestralidade dos branches remotos `origin/claude/orders-nuxt-ui-migration-b4c49c` (`bc6890171`) e `origin/claude/gestor-aviso-critico` (= HEAD).
- A contagem de consumidores por regex conta tags `<Nome` seguidas de espaço, `/`, `>` ou fim de linha. Usos dinâmicos (`<component :is>`) não entram.
- O Storefront foi excluído: tem biblioteca `Ui` própria e não estende o kit.


## Anexo B. Regressão, gesto por gesto (eixo 5)

### Laudo do Gestor canônico, eixo 5: regressão funcional (gesto por gesto)

Auditoria somente leitura. Antes = `origin/main` (838ce00e6, igual ao merge-base). Depois = HEAD da worktree `gestor-canon-laudo` (700f6aa63, PR #1519 empilhada sobre #1518), 18 commits.

Convenção dos caminhos: `ON/` = `surfaces/orders-nuxt/app/` e `KIT/` = `surfaces/operator-kit/app/`. A coluna "Antes" lê `origin/main`; a coluna "Agora" lê o HEAD.

Status: **mantido** (mesmo lugar) · **movido** (outro lugar, mesmo gesto) · **alterado** (o gesto existe, mas mudou de forma ou custa mais toques) · **AUSENTE** (o gesto não existe mais) · **incerto** (só o navegador decide).

#### 1. Método e verificações mecânicas

| Verificação | Resultado |
|---|---|
| Arquivos em `pages/` | Os mesmos 11 dos dois lados: `index`, `[ref]`, `history`, `catalog`, `channels/[ref]/catalog`, `customers/index`, `customers/[ref]`, `customers/merges`, `feeds`, `settings`, `workstations`. Nenhuma página nasceu ou morreu. |
| Componentes apagados | `ON/components/GestorNav.vue` e `ON/components/PhoneExitList.vue`. Novos: `OrderBoardColumn.vue`, `OrderBoardHeading.vue`, `OrderCardMenu.vue`; no kit, `OperatorSuiteShell.vue`, `OperatorUrgentAlert.vue`, `OperatorLoginForm.vue`. |
| `server/` do Gestor | Sem mudança no diff (BFF intacto). |
| Endpoints `/api/v1/...` citados em `orders-nuxt/app` + `operator-kit/app` | 51 caminhos distintos antes, os mesmos 51 depois, com a mesma contagem de ocorrências por caminho (diff vazio). Nenhum endpoint deixou de ser chamado. |
| Chamadas `$fetch`/`useFetch`/`fetch(` por arquivo de `ON/` | Mesma contagem em todos os 18 arquivos. |
| Ações devolvidas pelos composables (`useOrdersBoard`, `useOrderDetail`, `useOrderIntention`, `useCustomers`, `useCatalogMatrix`, `useFeedBoard`, `useWorkstations`...) | Todas as ações continuam devolvidas **e** consumidas por alguma página ou componente. Única perda de API: `useBoardLayout` perdeu `memoryText`/`viewLabel` e trocou `startResize/dragResize/endResize/gridTemplate/nextOpen` por `applySizes` (Splitter). |
| SSE | Mesmas assinaturas: `/sse/orders` resiliente (`useOrdersBoard.ts:437`), `useBackstageEvents("orders"|"catalog")`, `useAlerts` (EventSource próprio), `useUserNotifications`. `useOrderEvents` continua no detalhe (`[ref].vue:72`). |
| Som | `useAlertSound("gestor_sound", GESTOR_ALERT)` intacto (`useOrdersBoard.ts:223`), com `acknowledgeOnGesture` em `pointerdown`/`keydown` (`useOrdersBoard.ts:376-379, 486-487`). |

#### 2. Quadro, Grade, Lista e cabeçalho (`ON/pages/index.vue`)

| Gesto antigo | Antes (origin/main) | Agora (HEAD) | Status |
|---|---|---|---|
| Aceitar pedido (confirm) | `index.vue:657-658` via `onAction`; botão primário do cartão `OrderCard.vue:547-564` | `index.vue:1152-1153`; `OrderCard.vue:876-896` | mantido |
| Avançar etapa / marcar pronto (advance) | `index.vue:659-667` | `index.vue:1154-1161` | mantido |
| Despacho com um toque (`oneTapDispatch`) ou DispatchDialog | `index.vue:630-639, 663-665, 1567-1574` | `index.vue:1118-1132, 1158-1160, 2147-2154` | mantido |
| Entregador voltou (CourierBackDialog), "deu diferente" abre o acerto | `index.vue:642-655, 668, 1577-1583` | `index.vue:1135-1150, 1162, 2157-2163` | mantido |
| Acerto em dinheiro (valor, troco que voltou, maquininha voltou, revisão de custódia) | `index.vue:592-623, 1586-1628` | `index.vue:1024-1109, 2166-2247` | mantido |
| Maquininha voltou (equipment_back) | `index.vue:671` | `index.vue:1165` | mantido |
| Desfazer entrega (undo_handoff) e desfazer pronto (undo_ready) | `index.vue:672-673`; `OrderCard.vue:416-430, 521-532` | `index.vue:1166-1167`; `OrderCard.vue:658-687, 835-847` | mantido |
| Recusar com motivo (texto livre; iFood com motivo codificado, "Consultar novamente", descarte protegido, `beforeunload`) | `index.vue:520-588, 1507-1553` | `index.vue:922-1020, 2044-2129` | mantido |
| Atender / Liberar (assign/unassign) no cartão | `OrderCard.vue:594-606` (⋯) | `OrderCardMenu.vue:57-70` (⋯) | movido (componente próprio) |
| Atender na linha da tabela | botão direto na linha, `index.vue:1426-1436` | só no ⋯ da linha, `index.vue:1875-1883` → `OrderCardMenu.vue:57-70` | alterado (1 toque a mais) |
| Ações secundárias na linha da tabela | todos os botões inline, `index.vue:1437-1449` | primário inline `index.vue:1841-1874`; resto na linha aberta `index.vue:1910-1972` | alterado (abrir a linha antes) |
| Abrir o pedido | código `OrderCard.vue:229-240`, ⋯ `OrderCard.vue:667-677`, tabela `index.vue:1395` | `OrderCard.vue:377-388`, `OrderCardMenu.vue:108-117`, tabela `index.vue:1776-1781` e `1963-1970` | mantido |
| Volumes: tocar a etiqueta abre o editor num toque | `OrderCard.vue:296-303` (`openVolumesMenu`, `OrderCard.vue:81-84`) | etiqueta virou `NuxtBadge` só de leitura `OrderCard.vue:514-523`; editor só pelo ⋯ | alterado (2 toques; teste `OrderCard.test.ts:356` "a etiqueta abre o editor num toque" removido) |
| Volumes: editor no ⋯ (−/+/Gravar, 0 apaga) | `OrderCard.vue:618-652` | `OrderCardMenu.vue:83-100, 136-160` (`NuxtInputNumber`) | mantido |
| Volumes na Grade (Fila) | não existia | `QueueView.vue:574`, `index.vue:1643` | novo |
| Voltar para a estação (station recall) | `OrderCard.vue:653-666` | `OrderCardMenu.vue:101-107`; também na Grade `QueueView.vue:575-576` | mantido |
| Pronto de uma estação sem tela | botão à vista no cartão `OrderCard.vue:397-409` | ação dentro do Popover da pílula da estação `OrderCard.vue:217-244, 727-752` | alterado (1 toque a mais) |
| Imprimir / reimprimir DANFE | botão à vista `OrderCard.vue:432-448` | DANFE em ordem: botão à vista `OrderCard.vue:691-718`; DANFE não impressa: dentro do Popover `OrderCard.vue:245-270` | alterado no caso de atenção (1 toque a mais) |
| NFC-e não autorizada: abrir e reprocessar | link à vista `OrderCard.vue:450-458` | pílula + Popover com a ação `OrderCard.vue:271-291` | alterado (1 toque a mais) |
| Negociação iFood no cartão | link à vista `OrderCard.vue:461-463` | pílula + Popover "Abrir solicitação" `OrderCard.vue:292-312` | alterado (1 toque a mais) |
| Motivo do bloqueio ("por que espera") | texto à vista `OrderCard.vue:484-493` | pílula "Por que espera" + Popover `OrderCard.vue:208-216` | alterado (teste `OrderCard.test.ts:339` "a frase inteira fica à vista" removido) |
| Bloco "Negociações iFood pendentes" no topo do quadro | `index.vue:1130-1136` (todas as visões, inclusive celular) | entra na Grade `index.vue:684-694` + aviso com prazo `KIT/components/OperatorUrgentAlert.vue` (montado em `OperatorSuiteShell.vue:274`) | movido, decisão escrita do dono (commit a6a223f74). Ver P1 abaixo sobre celular e tablet em pé |
| Dispensar erro da ação | `OrderCard.vue:503`, tabela `index.vue:1459` | `OrderCard.vue:802-811`, tabela `index.vue:1892-1907` | mantido |
| Seleção em lote: ligar pelo ⋯ do cabeçalho, pelo ⋯ do cartão, por toque longo | `BoardMenu.vue` "Selecionar pedidos"; `OrderCard.vue:607-617`; `OrderCard.vue:151-164` | `BoardMenu.vue:103-107`; `OrderCardMenu.vue:71-82`; `OrderCard.vue:148-164` | mantido |
| Toque longo no cartão da Saída larga abria o ⋯ | `OrderCard.vue:158` (`fill`) | sempre liga a seleção `OrderCard.vue:155-158`; o ⋯ agora está sempre à vista | alterado |
| Barra de lote: Aceitar N, Avançar N, Marcar/Desmarcar todos, Limpar, Concluir | `index.vue:1075-1109` | `index.vue:1498-1558` | mantido |
| Marcar todos na tabela | `index.vue:1356-1366` | checkbox de cabeçalho `index.vue:1754-1766` | mantido |
| Seleção pela Grade | não existia | `QueueView.vue:573`, `index.vue:1637-1642` (vai para a Lista) | novo |
| Busca no quadro (`/`) | `index.vue:727-737, 492-495` | `index.vue:1252-1265, 889-892` | mantido |
| Ordenar (botão, menu e tecla S) | `index.vue:792-835, 503-505` | `index.vue:233-251, 1324-1336, 905-907` | mantido |
| Ordenar a Grade (Urgência...) | `index.vue:397-400, 806-819` | `index.vue:762-764`, via `sortMenuItems` | mantido |
| Trocar visão Fila/Supervisão | segmentos `index.vue:840-869` | `NuxtTabs` Grade/Lista `index.vue:592-601, 1342-1350` | alterado (renomeado: Fila→Grade, Supervisão→Lista, decisão do dono 07/10) |
| Recortes da Fila: Precisa de você / Todos / Atrasados | `index.vue:913-930` | `index.vue:711-717, 1396-1404` | mantido |
| Recorte Entrega / Retirada | `index.vue:938-945` (toque de novo desliga) | `NuxtTabs` `index.vue:718-737, 1405-1412` | alterado (abas exclusivas; "Todos" em vez de tocar de novo) |
| Chip "Todos" zera canal **e** fluxo | `index.vue:931-936` | "Todos" da aba só zera o fluxo; canal tem o próprio "Todos os canais" `index.vue:741-748, 1413-1419` | alterado |
| Escolher canal; "×" tira o recorte do canal | `index.vue:947-996` | `NuxtSelect` `index.vue:1413-1419` (opção "Todos os canais") | alterado (sem o "×") |
| Limpar filtros (sem resultados) | `index.vue:1138-1141` | `index.vue:1601-1615` | mantido |
| Ciente (cabeçalho) | `index.vue:741-750` | `index.vue:1310-1318` (agrupado com o som) | mantido |
| Ciente de todos (⋯) | `BoardMenu.vue` | `BoardMenu.vue:50-58` | mantido |
| Som: ligar/desligar/destravar autoplay | `index.vue:49-55, 775-787` | `index.vue:96-102, 1290-1309` | mantido |
| ⋯ do quadro: Atualizar, Ciente, Som, Mostrar 3 colunas, Ver em colunas/voltar, Selecionar, Ordenar, Ver como, Exportar CSV, Imprimir fila | `BoardMenu.vue:44-115` | `BoardMenu.vue:41-165` | mantido (rótulos "Voltar à Fila"→"Voltar à grade/lista", "Supervisão"→"Lista") |
| Exportar CSV | `index.vue:693-703` | `index.vue:1199-1213` | mantido |
| Imprimir fila | `index.vue:704-706`; `print:hidden` nas abas e na barra de lote `index.vue:1052, 1075`; rail com `print:hidden` | `index.vue:1214-1216`; abas `index.vue:1483` e barra de lote `index.vue:1498` sem `print:hidden`; rail do `OperatorOfficeShell` sem `print:hidden` | incerto (impressão pode levar o chrome) |
| Celular: painel "Filtros" de baixo | `index.vue:999-1013, 1022-1046` | `index.vue:1422-1439, 1448-1480` (`NuxtDrawer`) | mantido |
| Celular: colunas em abas (com contagem) | `index.vue:1049-1072` | `index.vue:1483-1495`; também no tablet em pé `index.vue:422-424, 523-526` | mantido (ampliado) |
| Celular: ponto de atraso na aba "Em preparo" da Saída | `index.vue:1069` | `phoneTabItems` carrega `late` (`index.vue:464-473`) mas o `NuxtTabs` não o desenha | alterado (sinal perdido) |
| Puxar para atualizar (celular) | `index.vue:239, 1113-1121` | `index.vue:476-480, 1567-1579`; `usePullToRefresh.ts` só reformatado | mantido; incerto: no celular a lista agora rola dentro da coluna (`OrderBoardColumn.vue:105` `overflow-y-auto`), e o puxar olha o `scrollTop` de `queueViewport`. Conferir no navegador |
| Deslizar o cartão para a esquerda: Atender / Recusar (SwipeReveal) | `index.vue:241-253, 1306-1334`; `SwipeReveal.vue` | `index.vue:482-507`; `OrderBoardColumn.vue:105-155`; `SwipeReveal.vue` (só markup) | mantido |
| **Saída no celular (PhoneExitList): mais antigo expandido, linhas de 64 px, tocar a linha traz para o foco, deslizar a linha para a DIREITA entrega, botão do polegar fixo "Entregar U13 a Ana"** | `index.vue:1239-1249`; `PhoneExitList.vue:1-186` (deslize `:72-88`, polegar `:170-184`, dica `:163-165`) | componente apagado; a aba Saída do celular desenha os cartões comuns em `SwipeReveal` (só Atender/Recusar para a esquerda) `OrderBoardColumn.vue:100-155` | **AUSENTE** (a ação ainda existe pelo botão primário de cada cartão; somem o deslize-para-entregar, o polegar fixo e o "mais antigo em foco"; teste `gestorV6Gestures.test.ts:28` removido; sem decisão escrita, entrou no snapshot WIP 7e6bb83de) |
| Recolher coluna (botão e teclas 1/2/3) | `index.vue:1220-1227, 476-483` | `OrderBoardHeading.vue:27-37`; `index.vue:857-871` | mantido |
| **Faixa da coluna recolhida: contagem, atrasados, resumo, pulso da Entrada; tocar abre SÓ aquela coluna; tocar a Entrada pulsante = Ciente no posto Saída** | `index.vue:1184-1193, 368-372` (`QueueColumnStrip`) | coluna recolhida some (`index.vue:520-522` filtra só as abertas); volta por "Mostrar as 3 colunas" `index.vue:1268-1280` (todas de uma vez) ou pela tecla 1/2/3; Ciente no posto Saída só pelo reconhecimento por gesto depois do som `useOrdersBoard.ts:376-379` | alterado, deliberado pela trava (`canonicalPilot.guardrails.test.ts:490` proíbe `<QueueColumnStrip`). Perde-se: abrir UMA coluna pelo toque, e o sinal visual de pedido novo no posto Saída |
| Ajustar largura das colunas (alça arrastável, teclado) | `index.vue:357-367, 1339-1345` (`QueueColumnResizeHandle`) | `OperatorSplitter` `index.vue:1651-1692` + `boardLayout.applySizes` | movido; incerto: teclado na alça do Splitter |
| Arrumação lembrada no posto, com aviso "dispositivo não é posto" e "não deu para guardar" | `index.vue:345-349, 752-761, 1201-1203`; `useBoardLayout.ts` `memoryText`/`viewLabel` | falha vira toast `useBoardLayout.ts:78-85`; aviso "não é posto" e selo "Visão: …" removidos | alterado, deliberado (commit 6def2f922; teste `useBoardLayout.test.ts:80` removido) |
| Posto Saída: recortes Todos/Retirada/Entrega na cabeça da coluna | `index.vue:1205-1219` | na faixa de recortes do cabeçalho `index.vue:641-659, 1385-1412` | movido |
| Posto Saída: grade em 2 linhas + faixa "+N esperando · Ver todos" / "Mostrar só os N primeiros" | `index.vue:313-339, 1253-1302` | grade rolável sem limite `OrderBoardColumn.vue:67-98` | alterado (todos os cartões alcançáveis por rolagem; o gesto "Ver todos" deixa de ser necessário) |
| Posto Saída: alvos de 48 px (`touch`) | `index.vue:288, 1270`; `OrderCard.vue:96, 167` | prop `touch` removida de `OrderCard`; nenhum alvo maior no posto | alterado (testes `OrderCardKitchen.test.ts:135` e `kitOwnership.guardrails.test.ts:321` removidos) |
| Interruptor do canal na coluna da Fila (ChannelSwitchDialog) | `QueueView.vue:316`; `index.vue:678-682, 1556-1564` | `QueueView.vue:837`; `index.vue:1172-1188, 2132-2144` | mantido |
| Grade: "+N · Ver todos" abre o recorte Todos | `QueueView.vue:228-238` | `QueueView.vue:584-592` | mantido |
| Grade: Pronto da estação, Responder negociação | `QueueView.vue:193` | `QueueView.vue:442, 458-460` | mantido (Responder é novo) |
| Sinal da loja iFood no cabeçalho | `index.vue:1015-1018` | `index.vue:1441-1444` | mantido |
| Agendados (encomendas) com os mesmos gestos do cartão | `index.vue:1473-1502` | `index.vue:1992-2039` | mantido |
| Restaurar rolagem/foco ao voltar do detalhe | `index.vue:86-118` | `index.vue:173-220` | mantido |

#### 3. Atalhos de teclado (lista completa)

| Tecla | Antes | Agora | Status |
|---|---|---|---|
| `/` focar a busca do quadro | `presentation/board.ts:515`, `index.vue:492` | `presentation/board.ts:652`, `index.vue:889` | mantido |
| `R` atualizar | `board.ts:517-519` | `board.ts:654-656` | mantido |
| `V` colunas ↔ Fila/Lista | `board.ts:520-522`, `index.vue:499-502` | `board.ts:657-659`, `index.vue:896-904` | mantido |
| `S` ciclar ordenação | `board.ts:523-525` | `board.ts:660-662` | mantido |
| `Esc` fecha painel, sai da seleção, limpa recortes, tira foco do campo | `index.vue:468-473, 506-512` | `index.vue:847-850, 908-914` (só o drawer móvel; menus do Nuxt UI tratam o próprio Esc) | mantido |
| `1` `2` `3` recolher/abrir Entrada, Preparo, Saída | `index.vue:476-483` + `KIT/presentation/queueColumns.ts` | `index.vue:857-871` | mantido |
| `F` abrir a Fila | `index.vue:415-419` | trocou para `G` (Grade) `index.vue:784-788` | alterado (decisão do dono, commit a6a223f74) |
| `T` abrir a Supervisão | `index.vue:420-424` | trocou para `L` (Lista) `index.vue:789-793` | alterado (idem) |
| `↑` `↓` andar na Fila | `index.vue:428-435` | `index.vue:797-809` | mantido |
| `Enter` gesto do item em foco | `index.vue:443-457` | `index.vue:817-836` | mantido |
| `A` aceitar o pedido novo em foco | `index.vue:436-440` | `index.vue:810-814` | mantido |
| Qualquer tecla/toque depois de o aviso soar = Ciente | `useOrdersBoard.ts:330, 427-428` | `useOrdersBoard.ts:376-379, 486-487` | mantido |
| `Ctrl/⌘ K` e `/` busca da suíte | `KIT/presentation/suiteSearch.ts:204-206`, `KIT/shortcuts/suiteShortcuts.ts` | `KIT/shortcuts/suiteShortcuts.ts:11-29`, `OperatorSuiteSearch.vue:128-143` | mantido |
| `Tab` / `Shift+Tab` troca o alcance da busca (App ↔ Suíte) | `KIT/components/OperatorSuiteSearch.vue:197`, dica `:491` | sem tecla; alcance por `NuxtTabs` `OperatorSuiteSearch.vue:302-307` | **AUSENTE** (atalho; o alcance continua por clique; teste `OperatorSuiteSearch.test.ts:113` removido) |
| `↑` `↓` nos resultados da busca, `Esc` fecha | `OperatorSuiteSearch.vue:358, 530` (`onKeydown`) | `NuxtCommandPalette` `OperatorSuiteSearch.vue:384-436` | movido (navegação nativa do CommandPalette); incerto (teste `:127` removido) |
| `Alt+1..9` abrir seção, `?` ajuda de atalhos | `KIT/components/OperatorSuiteRail.vue:131-133` | `KIT/components/OperatorSuiteShell.vue:48-69` | mantido |
| `⌘ Enter` enviar comentário | `KIT/components/OperatorOrderTimeline.vue:52` | `OperatorOrderTimeline.vue:73` | mantido |
| `↑` `↓` reordenar coleção (Catálogo) | na aba focada `ON/pages/catalog.vue:630` | na aba **ativa** `catalog.vue:1118-1123` | alterado |
| `↑` `↓` reordenar linha (Catálogo) | `catalog.vue:795` | `catalog.vue:1440` | mantido |
| `Enter`/`Esc` no preço inline; `Enter` no reajuste em lote | `catalog.vue:992, 1102` | `catalog.vue:1704-1705, 1896` | mantido |
| `Enter` numa linha da Saída do celular | `PhoneExitList.vue:153` | componente apagado | AUSENTE (junto com o PhoneExitList) |
| `Esc` no FilterBar / ColumnPicker | `KIT/components/FilterBar.vue:142`, `ColumnPicker.vue:54` | Popover/DropdownMenu do Nuxt UI | movido (nativo) |

#### 4. Detalhe do pedido (`ON/pages/[ref].vue`)

| Gesto antigo | Antes | Agora | Status |
|---|---|---|---|
| Voltar para a fila / histórico | `[ref].vue:342-350` | `[ref].vue:627-638` | mantido |
| Bilhete de volta (veio de outro app) | `[ref].vue:378-386` | `[ref].vue:682-689` | mantido |
| Ação primária (aceitar, avançar, acertar, despachar) | `[ref].vue:400-411`, polegar `:605-612` | `[ref].vue:710-722`, `:1043-1051` | mantido |
| Recusar | `[ref].vue:392-399`, `:598-603` | `[ref].vue:699-708`, `:1036-1041` | mantido |
| ⋯ do pedido: Atualizar, Avançar fora de ordem, Acerto, Maquininha voltou, Reprocessar NFC-e, Reenviar link de pagamento, Cancelar | `[ref].vue:416-450` (UiSheet) | `[ref].vue:414-500, 728-745` (NuxtDrawer) | mantido |
| Cancelar / recusar com motivo (OrderReasonDialog) | `[ref].vue:620-633` | `[ref].vue:1059-1076` | mantido |
| Acerto (valor, troco, maquininha, revisão) | `[ref].vue:636-680` | `[ref].vue:1085-1162` | mantido |
| Despacho: maquininhas, troco, "Saiu sem troco", "Levou o troco" | `[ref].vue:686-727` | `[ref].vue:1168-1230` | mantido (a legenda "O que sai com o entregador" do grupo de maquininhas sumiu; é título, não gesto) |
| Desfazer (pronto automático ou entrega) | `[ref].vue:516` | `[ref].vue:900-910` | mantido |
| Segunda assinatura do gerente (PIN/crachá) | `[ref].vue:736-744` | `[ref].vue:1236-1253` | mantido |
| Entregador por app: cotar, chamar, cancelar (OrderCourierPanel) | `[ref].vue:529-538` | `[ref].vue:934-949` | mantido |
| Nota para a cozinha: etiquetas rápidas, gravar, conflito (manter meu texto / usar do servidor) | `[ref].vue:550-585` | `[ref].vue:960-1020` | mantido |
| Comentário (timeline) | `[ref].vue:43-48, 478-485`; `KIT/OperatorOrderDetail.vue:233` | `[ref].vue:75-80, 818-827`; `KIT/OperatorOrderDetail.vue:368-373, 665-672` | mantido |
| Contato do cliente (WhatsApp, telefone, Admin) | `KIT/OperatorOrderDetail.vue:141, 353-358`; `OperatorOrderContact.vue:23-29` | `KIT/OperatorOrderDetail.vue:263, 618-646`; `OperatorOrderContact.vue:21` | mantido |
| iFood: resumo e negociação (decisão, motivo, detalhe, confirmar consequência, enviar, "Verificar mesmo envio") | `[ref].vue:489-490`; `OrderIFoodNegotiations.vue:58-134` | `[ref].vue:831-845`; `OrderIFoodNegotiations.vue:150-359` | mantido |
| Recibos de notificação | `[ref].vue:541` | `[ref].vue:952` | mantido |
| Banner de fora da loja: Permitir / Agora não / Ver tudo | `[ref].vue:455-464` | `[ref].vue:758-790` | mantido |
| Proteção de texto não salvo ao sair | `[ref].vue:116` | `[ref].vue:162` | mantido |

#### 5. Canais, clientes, fiscal e iFood loja

| Gesto antigo | Antes | Agora | Status |
|---|---|---|---|
| Pausar/ligar canal (ChannelSwitchDialog), com período, motivo e gerente | `ChannelSwitchDialog.vue` (187 linhas) | `ChannelSwitchDialog.vue:113-243` | mantido |
| Motivo pré-definido: tocar de novo desmarca | `ChannelSwitchDialog.vue:56-58, 127-135` | `NuxtRadioGroup` `ChannelSwitchDialog.vue:167-172` | alterado (sem desmarcar; o campo de texto continua) |
| Período personalizado: calendário de mês com o INTERVALO marcado, dias passados travados, setas de mês | `ChannelPeriodCalendar.vue:1-83` (o comentário `:2-4` diz por que não usar o seletor nativo) | 4 campos nativos `date`/`time` `ChannelPeriodCalendar.vue:1-34`; `monthWeeks`/`pickDay` (`presentation/channelSwitch.ts:106-145`) ficaram sem uso na tela; a prop `today` passada em `ChannelSwitchDialog.vue:153` não é declarada | alterado. A validação "fim depois do início" e "fim no passado" continua em `missingStep` (`channelSwitch.ts:40-58`); some a trava visual de dia passado e a leitura do intervalo no calendário |
| Unificar clientes (CustomerMergeDialog) | `CustomerMergeDialog.vue` | `CustomerMergeDialog.vue` (mesmos manipuladores) | mantido |
| Desfazer unificação (merges) | `customers/merges.vue` | `customers/merges.vue` (mesmos manipuladores) | mantido |
| Lista/ficha de clientes | `customers/index.vue`, `customers/[ref].vue` | idem, mesmos manipuladores | mantido |
| Canais e feeds: liga/desliga, automático, coleções, rotação, mensagens do descanso com conflito | `feeds.vue` | `feeds.vue:574-666, 750` | mantido |
| Loja iFood (abrir/fechar, interrupções) | `IFoodChannelStore.vue` | idem | mantido |
| Checklist de saúde do canal | `ChannelHealthChecklist.vue` | idem | mantido |
| Catálogo do canal (`channels/[ref]/catalog.vue`) | mesmo conjunto de manipuladores | idem | mantido |
| Catálogo: editar, pausar em todos, ocultar, dados sociais, reenviar, célula, preço inline, preço em lote, IA, colunas, filtros, reordenar | `catalog.vue` (menu da linha `:865-940`) | `catalog.vue:696-735` (menu), `:1097-1098`, `:1704-1705`, `:1870-1896` | mantido |
| Postos (workstations) | `workstations.vue` | idem (+ `setNewKind`) | mantido |
| Histórico: período, filtros, recorte por produto com "×" | `history.vue:64, 80-90` | `history.vue:121-146` | mantido |

#### 6. Navegação, avisos e shell

| Gesto antigo | Antes | Agora | Status |
|---|---|---|---|
| Rail com seções e contagens (Pedidos, Saída, Ajustes...) | `GestorNav.vue:40-48` → `KIT/OperatorSuiteRail.vue` | `app.vue:69, 94-101` → `KIT/OperatorSuiteShell.vue:132-169` | movido |
| Ponto âmbar de canal desligado em Ajustes/Canais | `GestorNav.vue` + `useGestorSections` | `useGestorSections.ts:62-64` + chip `OperatorSuiteShell.vue:146-152` | movido (testes `ChannelQueueSignal.test.ts:97, 101` removidos junto com o GestorNav, sem substituto equivalente no app) |
| Barra do polegar (celular) com "Mais" | `GestorNav.vue:49-56` → `OperatorSectionBar` | `OperatorSuiteShell.vue:250-270` | movido |
| Avisos (caixa da operação + pessoal), Ciente do alerta | `GestorNav.vue:24-36`; `OperatorInbox.vue:163, 175` | `app.vue:70-81`; `OperatorInbox.vue:158-214` | mantido ("Da operação" virou "Gerais") |
| Aviso com prazo que interrompe a tela (Visto / ir ao lugar) | não existia | `KIT/OperatorUrgentAlert.vue:127, 137` | novo |
| Bloquear / trocar operador, menu do operador, Atalhos | `OperatorSuiteRail.vue` | `OperatorSuiteShell.vue:207-237` | mantido |
| Selo do app volta à Central | `OperatorSuiteRail.vue:153-158` (via `hubUrl`) | `OperatorAppSeal.vue:23-57` (lê `operatorHubUrl`) | mantido |
| Vincular dispositivo a um posto | modal `app.vue` antigo `OperatorStationSetup` | inline `app.vue:103-110` | alterado (inline) |
| Toasts | `OperatorSonner` | toast do Nuxt UI `ON/utils/operatorToast.ts`, `ON/plugins/operator-toast.client.ts` | movido |

#### 7. Testes removidos entre origin/main e HEAD

Nenhum arquivo de teste foi apagado (o diff só tem `A` e `M`). Por nome de `it(`/`test(` (normalizado para aspas e espaços): orders-nuxt 647 → 669 (15 removidos, 37 novos); operator-kit 981 → 993 (11 removidos, 23 novos).

Removidos que escondem gesto perdido ou alterado:

- `orders-nuxt/tests/gestorV6Gestures.test.ts:28` "a Saída do celular é a da v4: linhas, dica de deslizar e o polegar" → PhoneExitList AUSENTE.
- `orders-nuxt/tests/components/OrderCard.test.ts:356` "a etiqueta abre o editor num toque" e `:366` "sem o gesto liberado, a etiqueta é só leitura" → volumes por um toque, alterado.
- `orders-nuxt/tests/components/OrderCardKitchen.test.ts:135` "posto de saída: alvos de 48 px" e `operator-kit/tests/kitOwnership.guardrails.test.ts:321` → alvos de toque do posto, alterado.
- `orders-nuxt/tests/components/OrderCard.test.ts:339` "a frase inteira fica à vista" → bloqueio dentro do Popover.
- `orders-nuxt/tests/components/OrderCard.test.ts:262` "links negotiations on a completed order..." → modo `negotiationOnly` removido (decisão a6a223f74).
- `orders-nuxt/tests/composables/useBoardLayout.test.ts:80` "dispositivo que não é posto: ... e diz por quê" → aviso removido (6def2f922).
- `orders-nuxt/tests/e2e/queue.spec.ts:26` "Ver todos e T abrem a Supervisão; F volta para a Fila" → reescrito como G/L; o clique em `[data-queue-rest]` perdeu cobertura e2e.
- `orders-nuxt/tests/components/ChannelQueueSignal.test.ts:97, 101` → ponto âmbar de Ajustes (mudou de lugar, ficou sem teste no app).
- `operator-kit/tests/components/OperatorSuiteSearch.test.ts:113` (Tab troca o alcance), `:127` (↑↓ e Esc), `:161` (`/` e Ctrl K de qualquer lugar), `:175` (tecla não impressa no toque) → atalhos da busca sem cobertura; Tab AUSENTE.
- `operator-kit/tests/queueColumns.test.ts:75` → nome da visão com colunas recolhidas (o selo "Visão: …" saiu).

Removidos sem gesto por trás (estilo ou cópia): `cardV4.test.ts:51`, `OrderCard.test.ts:113, 165, 247`, `queueV6.test.ts:59`, `OperatorLogin.test.ts:137`, `SuiteChrome.test.ts:404, 412, 419`, `UiToolbarPrimitives.test.ts:29`.

#### 8. Achados, por gravidade

**AUSENTE**

1. Saída do celular (PhoneExitList): deslizar a linha para a direita entrega, o botão fixo do polegar ("Entregar U13 a Ana"), tocar a linha traz para o foco, `Enter` na linha. Antes `ON/components/PhoneExitList.vue:72-88, 153, 170-184`; ligado em `index.vue:1239-1249`. Agora não existe; a aba Saída do celular usa `OrderBoardColumn.vue:100-155` com o deslize para a esquerda (só Atender/Recusar). A entrega continua possível pelo botão do cartão, então a operação não trava, mas o gesto de polegar do passe sumiu sem decisão escrita (entrou no snapshot WIP 7e6bb83de) e o teste que o protegia foi apagado.
2. `Tab`/`Shift+Tab` troca o alcance da busca da suíte. Antes `KIT/components/OperatorSuiteSearch.vue:197` (e a dica `:491`). Agora só por clique nas abas `OperatorSuiteSearch.vue:302-307`.

**alterado com perda real (P1)**

3. Faixa da coluna recolhida (`QueueColumnStrip`): some a contagem/atrasados/pulso de uma coluna recolhida, e não dá para reabrir só uma por toque (só "Mostrar as 3 colunas" ou a tecla). No posto Saída, o pedido novo deixa de ter sinal visual na tela. Deliberado pela trava `canonicalPilot.guardrails.test.ts:490`, mas é perda funcional para o tablet do passe.
4. Negociação iFood de pedido já encerrado: antes visível em todas as visões (`index.vue:1130-1136`); agora só na Grade (`index.vue:684-694`), que não existe no celular, no tablet em pé nem no posto Saída (`index.vue:584-586`). Nesses dispositivos o único caminho é o aviso com prazo (`OperatorUrgentAlert`) e a caixa de Avisos. Decisão do dono (a6a223f74); conferir no navegador que o aviso aparece no celular.
5. Posto Saída sem alvos de 48 px (prop `touch` removida).
6. Período personalizado do canal: calendário de intervalo trocado por 4 campos nativos, contrariando o motivo escrito no componente antigo; funções `monthWeeks`/`pickDay` ficaram mortas e a mensagem "Escolha no calendário…" (`channelSwitch.ts:49`) ficou desatualizada.

**alterado (mais toques ou forma diferente, P2)**

7. Volumes: a etiqueta deixou de abrir o editor (2 toques pelo ⋯).
8. Pronto da estação, DANFE não impressa, NFC-e falha, negociação iFood e motivo do bloqueio passaram para Popover de pílula (1 toque a mais cada).
9. Lista: Atender e ações secundárias saíram da linha (⋯ e linha aberta).
10. Recortes: "Todos" não zera mais o canal; o canal perdeu o "×".
11. Teclas F/T viraram G/L (decisão do dono).
12. Celular: o ponto de atraso na aba "Em preparo" da Saída não é desenhado.
13. Reordenar coleção pelo teclado atua na aba ativa, não na focada.
14. Motivo pré-definido do canal não se desmarca com novo toque.

**incerto (precisa de navegador)**

15. Puxar para atualizar no celular: a rolagem passou para dentro da coluna (`OrderBoardColumn.vue:105`), e o gesto lê o `scrollTop` de `queueViewport` (`index.vue:480`).
16. Imprimir fila: abas, barra de lote e rail novos sem `print:hidden`.
17. Ajuste de largura das colunas pelo teclado no `OperatorSplitter`.
18. Navegação ↑↓/Esc nos resultados da busca (agora do `NuxtCommandPalette`), sem teste.

## Anexo C. Copy e minimalismo (eixos 3 e 4)

### Laudo adversarial do Gestor: eixo 3 (copy) e eixo 4 (minimalismo)

**Árvore auditada:** worktree `gestor-canon-laudo` (HEAD `700f6aa63`, PR #1519 empilhado
sobre #1518). Leitura apenas; nada editado.
**Régua:** `CLAUDE.md` (travessão, dispositivo/maquininha), `docs/reference/omotenashi-copy.md`
(D1 a D8), `docs/reference/suite-vocabulary.md` (decisões fechadas, §2.1 Visto, §2.2 Tentar
de novo, §2.3 forma do dado velho), `docs/reference/operator-kitchen-sink.md` (contrato de Card,
slots, Grade/Lista, aviso urgente).
**Severidade:** P0 = mente ao operador ou perde função; P1 = vai se espalhar (kit ou padrão)
ou viola decisão escrita; P2 = polimento.

Convenção: `arquivo:linha` relativo a `surfaces/` salvo indicação. Linha envelhece; a string
citada é a âncora.

---

#### Parte A. Eixo 3: copy

### A.1 P0

| # | Onde | Texto real | Defeito | Reescrita |
|---|---|---|---|---|
| A1 | `orders-nuxt/app/pages/index.vue:1550` (barra de seleção em lote) | botão `"Concluir"` que só **sai do modo de seleção** | D1 + D7b. No mesmo app, `"Concluir"` é o rótulo do servidor para o ato de concluir o pedido entregue (`shopman/backstage/projections/order_queue.py:85`, `NEXT_ACTION_LABELS["delivered"] = "Concluir"`). Quem seleciona pedidos entregues e toca "Concluir" sai da tela achando que concluiu. É o defeito "acabar de agir achando que agiu". Além disso o mesmo gesto já se chama `"Sair da seleção"` no ⋯ (`BoardMenu.vue:105`) | `"Sair da seleção"` (o nome que o ⋯ já usa) |
| A2 | `orders-nuxt/app/composables/useOrdersBoard.ts:742` (toast do lote) | `` `${failures} pedido(s) não puderam ser atualizados.` `` | D3 + D2 + plural "(s)". Não diz quais pedidos nem qual ato falhou (Aceitar ou Avançar); a barra de lote some e o operador não tem como achar os que ficaram para trás. Perde a função de recuperar o erro | `"2 pedidos não foram aceitos: K44 e T18. Eles continuam marcados."` (ato pelo nome, códigos, e manter a seleção dos que falharam) |

### A.2 P1: decisões escritas violadas e o que se espalha

| # | Onde | Texto real | Defeito / regra | Reescrita |
|---|---|---|---|---|
| A3 | `orders-nuxt/app/pages/index.vue:1313` · `components/BoardMenu.vue:52` | `"Ciente"` · `"Ciente de todos"` (aria `"Reconhecer aviso de pedido novo"`) | §2.1 de `suite-vocabulary.md`: reconhecer um aviso **é "Visto"**, decisão fechada. No mesmo app o `OperatorUrgentAlert` e a caixa de Avisos já dizem `"Visto"`; o Gestor ensina duas palavras para um gesto, e ainda dois rótulos para o mesmo `acknowledgeAttention` (com e sem "de todos") | `"Visto"` nos dois lugares; aria `"Visto: parar o som de pedido novo"` |
| A4 | `orders-nuxt/app/presentation/queue.ts:320-324` (Grade) · `presentation/board.ts:1043-1055` (Colunas) · servidor `order_queue.py:83,88` (detalhe e `title`) | Despachar: `"Saiu"` (Grade) · `"Despachar M09"` (Colunas) · `"Marcar saída para entrega"` (detalhe) · `"Saiu para entrega"` (diálogo). Retirar: `"Retirou"` · `"Entregar a Ana"` · `"Marcar como retirado"` | D7c, lei 1 ("um nome por conceito, qualquer que seja a porta"). O mesmo ato tem três nomes conforme a visão; quem aprende na Grade não reconhece nas Colunas. Mistura ainda tempo verbal (fato no passado vs ordem) | Escolher **um** verbo por ato e usar nas três portas e no servidor: `"Despachar M09"` / `"Entregar a Ana"` (verbo + quem; o `title` fica com o mesmo verbo). Decisão do dono se preferir o fato no passado; o que não pode é três |
| A5 | `orders-nuxt/app/pages/index.vue:2166-2245` (diálogo do acerto no quadro) vs `pages/[ref].vue:1079-1160` (mesmo diálogo no detalhe) vs `presentation/board.ts:339-340` | Botão do cartão `"Receber na retirada"` → título `"Pagamento na retirada"` → confirmação `"Confirmar acerto"` (quadro) ou `"Confirmar"` (detalhe); descrições diferentes nas duas portas | D7c: o mesmo gesto com quatro nomes e dois textos de diálogo, um por porta | Retirada: título `"Receber na retirada"`, botão `"Registrar recebimento"`. Entrega: título `"Acertar entrega"`, botão `"Confirmar acerto"`. Um componente só para as duas portas |
| A6 | `orders-nuxt/app/pages/index.vue:2173` | `"… Em branco usa o total de R$ 45,00. …"` | D5 (vazio como código secreto) num campo de **dinheiro**. O operador precisa lembrar que vazio vale o total | Pré-preencher o campo com o total e descrever `"Confira o valor recebido."` |
| A7 | `orders-nuxt/app/pages/[ref].vue:1164-1228` vs `components/DispatchDialog.vue:113-201` | Detalhe: título `"Troco para o entregador"` / `"Saída para entrega"`, botões `"Saiu sem troco"` / `"Levou o troco"`. Quadro: título `"Saída para entrega"`, botão `"Saiu para entrega"` / `"Saiu com a maquininha Azul"` | D7c: dois diálogos para o mesmo despacho, com copy e capacidades diferentes (o do quadro oferece "vai junto" e maquininha; o do detalhe não) | Usar o `DispatchDialog` também no detalhe |
| A8 | `orders-nuxt/app/pages/index.vue:272` · `presentation/board.ts:612` (CSV) vs `presentation/history.ts:35` | Coluna da Lista `"Etapa"` (mostra `status_label`); no Histórico a mesma coluna é `"Situação"` | D7c dentro do app e D7b entre apps: **etapa** é palavra fechada para a etapa de receita (`suite-vocabulary.md` §1, 01/10) | `"Situação"` na Lista e no CSV |
| A9 | `orders-nuxt/app/pages/index.vue:1998,2006` · `components/OrderCard.vue:529` | Seção `"Agendados"`, selo `"Agendado · sáb 19/07"` | D7c entre superfícies: o pedido para data futura é **encomenda** no PDV e na loja (`suite-vocabulary.md` §3 e §5). O próprio código chama de "Encomendas" (`board.ts:227`) | `"Encomendas"` / `"Encomenda · sáb 19/07"` |
| A10 | `orders-nuxt/app/pages/catalog.vue:1291` vs `catalog.vue:1515` (mesma tela) | `"Confirmar este lote"` (lote = conjunto de mudanças de publicação) ao lado de `"Repõe 12 no lote"` (lote da Produção) | D7b dentro da mesma tela, e **lote** é palavra fechada da Produção (22/09) | `"Publicar estas mudanças"` |
| A11 | `orders-nuxt/app/components/OrderCard.vue:276-282` | pílula `"NFC-e não autorizada"` · descrição `"O pedido tem o Reprocessar NFC-e."` · ação `"Abrir e reprocessar"` | D1: a ação só abre o pedido, não reprocessa. D3: a descrição obriga a completar sentido | descrição `"A Sefaz recusou a nota. Reprocesse no pedido."` · ação `"Abrir o pedido"` |
| A12 | `orders-nuxt/app/composables/useOrderDetail.ts:271,279` | `"Pedido de entregador enviado à central."` · `"Cancelamento da corrida pedido. Falta a central confirmar."` | D7b: num app de **pedidos**, "pedido" como "solicitação" se lê como o pedido do cliente | `"Entregador chamado. A central confirma em instantes."` · `"Cancelamento da corrida solicitado. Falta a central confirmar."` |
| A13 | Forma do "dado velho" (§2.3) em 6 redações no mesmo app: `pages/index.vue:1595` `"Mantivemos a última leitura; atualize antes de confirmar ações."` · `pages/[ref].vue:812` `"Mantivemos a última leitura e seu rascunho; …"` · `pages/feeds.vue:343` e `pages/catalog.vue:1184` `"Exibindo a última leitura disponível."` · `pages/channels/[ref]/catalog.vue:162` `"Exibindo a última leitura disponível; a gravação está bloqueada."` · `components/ReadFreshness.vue:39,43` `"Última leitura útil: 14:02:11 · há 37 s"` / `"Horário da leitura indisponível"` · `BoardMenu.vue:152` `"Leitura da fila"` | §2.3 manda uma forma; "leitura" é um dos sete substantivos que a régua aposentou (D7a). `"há 3600 s"` é o mesmo número sem unidade legível | `"Não deu para atualizar. O que está na tela é de 14:02."`; ReadFreshness: `"Atualizado às 14:02 (há 37 s)"`, sem horário: `"Sem horário da última atualização."`; rótulo do grupo: `"Atualização"` |
| A14 | `operator-kit/app/components/OperatorOrderTimeline.vue:19,58,66` + `OperatorOrderDetail.vue:671` | `"Histórico"` (coluna única) e `"Linha do tempo"` (duas colunas, o Gestor); vazio `"Ainda não há nada no histórico deste pedido."`; campo `"Comentar no histórico"` | D7c no kit: o mesmo bloco com dois nomes conforme o layout, e no Gestor o título diz "Linha do tempo" e o corpo diz "histórico". E "Histórico" é também uma **seção** do Gestor (`gestorSections.ts:107`) | Um nome só no kit: `"Linha do tempo"`; vazio `"Nada aconteceu com este pedido ainda."`; campo `"Comentar"` |
| A15 | `operator-kit/app/presentation/suiteSearch.ts:57-66` · `OperatorSuiteSearch.vue:296,389` | `"Toda a suíte"`, `"Na suíte"`, `"Buscando na suíte…"`, `"A busca da suíte não respondeu."`, `"Busque nesta tela, neste app ou em toda a suíte."` | D7a: "suíte" é palavra de engenharia; o operador conhece "os apps" | `"Todos os apps"`, `"Nos outros apps"`, `"Buscando em todos os apps…"` |
| A16 | `operator-kit/app/components/OfflineBanner.vue:27` | `title="Sem conexão — tentando reconectar…"` | Travessão em texto de tela (CLAUDE.md). A exceção em `guardrails.noEmDash.test.ts` é **mecânica** (o retrato do Marketing), não decisão; e o componente está nos nove apps | `"Sem conexão. Tentando reconectar…"` e regerar o retrato na sessão que tem o Chromium da CI |
| A17 | `operator-kit/app/components/OperatorInbox.vue:212,221` · `orders-nuxt/app/app.vue:74` · `composables/useAlerts.ts:111,118` | A caixa se chama `"Avisos"` e o botão `"Visto"`, mas: `"O alerta sai quando o problema for resolvido."`, `"Nenhum alerta agora"`, `"Nenhum alerta de pedido agora."`, `"Os alertas mudaram…"`, `"Não deu para marcar o alerta como visto."` | D7c: aviso e alerta para o mesmo objeto, no kit | `"aviso"` em todos: `"Nenhum aviso de pedido agora."`, `"O aviso some quando o problema for resolvido."` |
| A18 | `orders-nuxt/app/pages/index.vue:2080-2085` · `components/OrderReasonDialog.vue:57` | `"Nenhum motivo disponível"` / `"O iFood não oferece motivos de cancelamento neste momento."` e o botão "Recusar pedido" fica desabilitado | D3 + "erro terminal nomeia a saída" (kitchen sink). Sem a lista, a recusa do iFood é impossível e a tela não diz o que fazer; e o título é "Recusar", o texto diz "cancelamento" | `"O iFood não mandou a lista de motivos. Sem um motivo da lista, ele não aceita a recusa. Tente de novo em instantes."` + ação `"Tentar de novo"` |
| A19 | `operator-kit/app/app.config.ts:109-110` (tema) vs `docs/reference/operator-kitchen-sink.md:253` | O tema do kit passou a tratar "Accordion como conteúdo inteiro" de um Card para servir o Card dentro do Card do "Em andamento" | Decisão do dono (07/10) registrada só em comentário; o documento canônico ainda diz "Não há Card dentro de Card". Ver também B4 | Registrar a decisão no kitchen sink (seção "Contrato compacto de Cards") ou trocar por `NuxtCard` `soft`/lista sem moldura |

### A.3 P2: polimento, mas com nome

**Vocabulário e colisão (D7)**

| # | Onde | Texto real | Reescrita |
|---|---|---|---|
| A20 | `presentation/board.ts:479` | `"Sem tempo real; o board atualiza sozinho a cada 30s"` (e `:472`). "board" saiu do vocabulário de tela (24/09) | `"Sem tempo real; a tela atualiza sozinha a cada 30 s"` |
| A21 | `pages/feeds.vue:361,737` | `"Carregando feed"`, `"Ver feed"` | `"Carregando a vitrine"`, `"Abrir a vitrine"` (ou o nome que o domínio fechar) |
| A22 | `components/CatalogProductPanel.vue:149,1002` | aba `"Preço e config"`; `"Usadas em busca e SEO."` | `"Preço e venda"`; `"Usadas na busca do site e do Google."` |
| A23 | `pages/[ref].vue:974` · `operator-kit/.../OperatorOrderDetail.vue:544` | `"Aparece no ticket da cozinha (KDS)."`; o editor diz `"Nota para a cozinha"`, a leitura diz `"Nota da cozinha"` | `"Aparece no pedido, na tela da Cozinha."`; um nome: `"Nota da cozinha"` |
| A24 | `pages/[ref].vue:989,998` · `pages/feeds.vue:494,573,665` · `CatalogProductPanel.vue:739` · `catalog.vue:1716` | `"No servidor: …"`, `"Usar texto do servidor"`, `"As coleções mudaram no servidor"`, `"Usar valor atual"`, `"Usar valores atuais"` | D7a + D7c: `"Alguém salvou antes de você: …"` · um gesto só: `"Usar o que foi salvo"` |
| A25 | `components/OrderCard.vue:327` | pílula `"iFood à frente"` | D7a. `"iFood já avançou o pedido"` |
| A26 | `components/QueueView.vue:399` | `"Café no papel"` | D7a/D3. `"Café sem tela: marque o pronto"` |
| A27 | `components/QueueView.vue:349` | `"no prazo, o iFood decide sem a loja"` | D3 (qual prazo?). `"se a loja não responder até 14:20, o iFood decide sozinho"` |
| A28 | `components/OrderCard.vue:297-303` · `QueueView.vue:345,442` · `OrderIFoodNegotiations.vue:202,271` | `"Negociação iFood"` → `"Abrir solicitação"` → `"Aceitar solicitação"` | D7c. Um nome: `"Negociação iFood"` → `"Responder"` → `"Aceitar"`/`"Recusar"` |
| A29 | `components/OrderIFoodNegotiations.vue:329,342` | `"… Confirmo esta consequência."`, `"Verificar mesmo envio"` | "consequência" é exemplo nominal de D7a na régua. `"Entendi o que acontece."`, `"Conferir se a resposta chegou"` |
| A30 | `components/OrderCard.vue:230` · `QueueView.vue:467` vs `pages/[ref].vue` menu (`"Marcar pronto"`) e `QueueView.vue:763` | `"Pronto de Café"` vs `"Marcar pronto"` | D7c. `"Marcar Café pronto"` |
| A31 | `pages/index.vue:487` · `OrderCardMenu.vue:60` | `"Liberar"` (desatribuir) | D7b com o PDV, onde **liberar** é devolver a comanda (§3). `"Deixar de atender"` |
| A32 | `pages/index.vue:1920` · `presentation/history.ts:38` | `"Recebimento"` para retirada/entrega | D7b com Compras (recebimento de mercadoria) e com "Receber na retirada" (dinheiro). `"Entrega ou retirada"` |
| A33 | `pages/index.vue:707-709,720-735` (mesma faixa de recortes) | Duas abas `"Todos"` lado a lado: uma do recorte (Precisa de você · **Todos** · Atrasados) e outra da entrega (**Todos** · Entrega · Retirada) | D7b. Na segunda: `"Entrega e retirada"` |
| A34 | `BoardMenu.vue:105` · `OrderCardMenu.vue:71-75` · `OrderCard.vue:372` · `index.vue:1537,1544,1763` | Seleção: `"Selecionar pedidos"`, `"Selecionar vários"`, `"Marcar este pedido"`, `"Selecionar pedido"` (aria), `"Marcar todos"`/`"Desmarcar todos"` e **também** `"Limpar"` (que faz o mesmo que "Desmarcar todos" quando tudo está marcado) | D7c. Um verbo (`"Selecionar"`/`"Desmarcar"`); tirar "Limpar" ou "Desmarcar todos" |
| A35 | `pages/index.vue:1276` | `title="Mostrar as 3 colunas (atalhos: 1, 2 e 3)"` | D1: 1, 2 e 3 recolhem cada coluna (`OrderBoardHeading.vue:36`), não "mostram as 3". `"Mostrar as 3 colunas"` sem o parêntese |
| A36 | `pages/index.vue:1332` | `title="Ordenar a Fila"` | "Fila" é o nome interno; na tela a visão é **Grade** e o título é "Precisa de você". `"Ordenar"` |
| A37 | `pages/index.vue:1256` · `history.vue:114` · `catalog.vue:1069` · `customers/index.vue:82` | `screen-label="filtrando o quadro"` (inclusive quando a visão é Grade ou Lista) | D1 leve. `"Os pedidos desta tela estão filtrados."` |
| A38 | `pages/workstations.vue:184` | `aria-label="Carregando estação"` numa página chamada **Postos** | `"Carregando postos"` |
| A39 | `CatalogProductPanel.vue:630` vs `:1280`; `:623` vs `:1122`; `:626` vs `:1127` | `"Rendimento"` (aviso de conflito) para o campo `"Serve"`; `"Produção em lote"` vs `"Produzido em lote"`; `"Venda no dia seguinte"` vs `"Pode ser vendido no dia seguinte"` | D7c entre o formulário e o aviso de conflito do mesmo campo; e "rendimento" é da ficha (§1) |
| A40 | `catalog.vue:1833,1841` vs `CatalogProductPanel.vue:934` | `"Pausar"`/`"Ativar"` vs `"Pausar"`/`"Retomar"` | Um par só |
| A41 | `CatalogProductPanel.vue:1173,186-187` | `"Vocação"` (`"só para o B.I."`); `"Aceita planejado"`, `"Aceita demanda"` | D7a. Explicar em linguagem de venda (ex.: `"Vende o que ainda vai ser produzido"`) |
| A42 | `pages/catalog.vue:1256-1263`; `useCatalogMatrix.ts:353` | `"Confira 12 células em …"`, `"acompanhe a sincronização das plataformas separadamente nas células"` | D7a ("células" é a grade técnica). `"Confira 12 preços no iFood"`; `"O envio a cada canal aparece no próprio preço."` |
| A43 | `pages/catalog.vue:1230-1243` | `"Verificar esta gravação"`, `"Aplicar meu arraste à ordem atual"`, `"Descartar o rascunho de ordem"` | D7a. `"Conferir se a ordem foi salva"`, `"Salvar a minha ordem"`, `"Descartar a minha ordem"` |
| A44 | `pages/channels/[ref]/catalog.vue:142-146,190-193,265` | `"… Este fluxo não envia alterações à plataforma."`, `"nenhum produto será alterado ou vinculado automaticamente"`, `sha256` sob `"Identificação única do arquivo"` | D6 (abre/fecha dizendo o que o sistema não faz) + V4 (código interno na tela) |
| A45 | `components/OrderNotificationReceipts.vue:48,67` | selo `"crítico"`; `"Comprovante: <id do provedor em mono>"` | D7a/V4 |

**Frase incompleta, verbo genérico, zero como código (D2, D3, D5)**

| # | Onde | Texto real | Reescrita |
|---|---|---|---|
| A46 | `presentation/board.ts:147` | `"aviso ao cliente sai em 0:24"` | D2. `"o cliente é avisado em 0:24"` |
| A47 | `components/QueueView.vue:763-764` | rodapé `"Aviso ao cliente só sai depois da janela de desfazer. “Marcar pronto” à mão continua no menu do pedido."` | D6 + D2 + rodapé de cerimônia (ver B7). Apagar; o "desfazer" já mostra o prazo |
| A48 | `presentation/danfe.ts:43,50` · `useDanfePrint.ts:69` | `"DANFE saindo na impressora"`, `"A DANFE sai sozinha quando a entrega sair"`, `"A DANFE do pedido … não saiu"` | D2. `"Imprimindo a DANFE"`, `"A DANFE é impressa sozinha no despacho"`, `"A DANFE do pedido K44 não foi impressa"` |
| A49 | `components/OrderCardMenu.vue:138` | `"Zero apaga: o cartão volta a contar itens."` | D5. Botão `"Apagar volumes"` ao lado do campo |
| A50 | `pages/feeds.vue:602` | `"Zere os dois campos para mostrar tudo sem rotação."` | D5 (é o exemplo canônico). Interruptor `"Trocar de página sozinho"` |
| A51 | `components/CatalogProductPanel.vue:1086` | placeholder `"Vazio = não perece"` | D5. Interruptor `"Perecível"` com o campo de dias revelado |
| A52 | `components/QueueView.vue:723,730` | badge `"15 min"` ao lado de `"O sistema fez"`; vazio `"Nada automático neste intervalo."` | D3. Título `"O sistema fez nos últimos 15 min"`, sem o badge |
| A53 | `presentation/board.ts:1137-1142` | `"prontos esperando (K44, T18)"` / `"esperando (K44, T18)"` | D3 (esperando o quê?). `"2 prontos para sair: K44, T18"` / `"2 na Saída: K44, T18"` |
| A54 | `pages/[ref].vue:813` | `"Pedido não encontrado ou falha ao carregar."` | D3 (duas leituras). Separar pelo status HTTP |
| A55 | `components/CourierBackDialog.vue:16,29` | descrição `"{Fecha a saída dos pedidos …} Confira:"` (com um pedido só, sobra `" Confira:"`) + Alert `"Conferir no retorno"` | D3 + D8. Descrição `"Confira o que o entregador trouxe:"` e lista sem Alert |
| A56 | `pages/index.vue:2049` · `OrderReasonDialog.vue:39` | `"Escolha o motivo que o iFood exige. Ele é enviado ao iFood."` | D8. `"O iFood exige um motivo da lista dele."` |
| A57 | `pages/index.vue:2187,2190` · `pages/[ref].vue:1105,1108` | `"Confira o contexto atual: …"`, `"Conferir e manter os valores digitados"` | D7a/D8. `"O pedido ou o turno mudou: …"`, `"Manter o que digitei"` |
| A58 | `useOrderDetail.ts:257` | `"Notas salvas."` (salva-se uma nota) | `"Nota da cozinha salva."` |
| A59 | `pages/history.vue:108` vs `presentation/gestorSections.ts:110` | `"Pedidos concluídos e cancelados"` vs `"Pedidos concluídos, cancelados e devolvidos"` | D1 leve: uma das duas promete o que não mostra |

**Plurais "(s)", "novamente", inglês, travessão**

- `(s)`: `composables/useCatalogMatrix.ts:253` `"N item(ns) atualizado(s)."`; `:353` `"N preço(s) atualizado(s). …"`; `useOrdersBoard.ts:742` (A2); `pages/catalog.vue:1537` `"… em N plataforma(s)."`. Reescrever com plural resolvido (como `board.ts:1021-1023` já faz).
- `novamente` (§2.2 manda `Tentar de novo`/`Tente de novo.`): `pages/index.vue:2073` `"Consultar novamente"`; `pages/channels/[ref]/catalog.vue:163` `"Tente novamente para consultar os inventários."`; `useCatalogMatrix.ts:651` `"consulte novamente"`; `OrderIFoodNegotiations.vue:177,324`; `CatalogBindingReview.vue:178`; `app.vue:122` `"Entrar novamente não concede…"`; kit `OperatorLogin.vue:47` `"Entre novamente."`. Também `pages/feeds.vue:344` e `catalog.vue:1185` `"Tente atualizar para consultar…"` ao lado de um botão `"Tentar de novo"` (dois verbos para o mesmo gesto).
- Inglês na tela: `"board"` (A20), `"feed"` (A21), `"config"`, `"SEO"` (A22), `"KDS"` (A23), `"Exportar CSV"` (`BoardMenu.vue:157`, sugerido `"Baixar planilha (CSV)"`).
- Travessão como valor vazio: `presentation/board.ts:403` (`channelLabel` devolve `"—"`) e `pages/catalog.vue:1784`. A trava aceita (`dropPlaceholders`), mas o canal sem nome vira um traço no cartão ao lado de "·". Preferir `"Canal sem nome"`.
- `aparelho`: zero ocorrências em `orders-nuxt` e nos componentes do kit lidos. Bom.

**Doc que mente (kit)**

- `docs/reference/operator-kitchen-sink.md:206-207` diz que o aviso urgente já visto volta "a cada `URGENT_REMINDER_MINUTES` (5)"; o código diz `1` (`operator-kit/app/presentation/suiteChrome.ts:201`, commit `700f6aa63`). Com toast de 15 s a cada minuto, o documento esconde o custo de ruído.
- Os atalhos do Gestor (`/`, `R`, `V`, `S`, `G`, `L`, `A`, `Enter`, `1/2/3`, `Esc`) não são registrados em `provideOperatorShortcuts`: o painel "Atalhos do teclado" (`OperatorShortcutsHelp`) do Gestor lista só os comuns. Os `title` dos botões prometem atalhos que a ajuda não mostra.

### A.4 Bom (onde não mexer)

- `zoneEmptyText` (`board.ts:180-189`): um vazio por coluna, nomeando a zona.
- `machinesOutSentence` / `machinePhrase` (`board.ts:799-823`): maquininha com nome, sem "dispositivo".
- `OperatorUrgentAlert`: "Visto" + lugar exato em 1/3 + 2/3, título "Precisa de resposta", toast com hora-limite.
- `packLabel` resolve plural e não deduz volume.
- `ChannelSwitchDialog` / `presentation/channelSwitch.ts`: verbo do botão é o gesto (`"Desligar"`, `"Agendar o desligamento"`) e as pendências são frases inteiras.

---

#### Parte B. Eixo 4: minimalismo

| # | Sev. | Onde | O que se repete / sobra | Proposta |
|---|---|---|---|---|
| B1 | P2 | `components/OrderCard.vue:396-400` + `:467-470` + `:817-824` (com `payment_method_label = "iFood"` em `order_queue.py:927`) | Pedido do iFood diz **iFood três vezes** no mesmo cartão: `"iFood #1234"` na linha 1, `"· iFood"` na linha 2, selo de pagamento `"iFood"`. E o selo de pagamento "iFood" não diz se o pagamento é online ou na porta (verificar `ifood_payment_summary`; se houver cobrança na entrega, isto é P1) | Linha 2: `"Ana · iFood #1234"`; selo de pagamento com o meio real |
| B2 | P2 | `OrderCard.vue:406-455` + `presentation/board.ts:926-938` | **Estado duas vezes**: selo (`"Bloqueado"`, `"Próximo"`, `"Novo"`) e, no segundo selo, `status_label · relógio` quando difere. No bloqueado, o motivo aparece quatro vezes: selo "Bloqueado", pílula "Por que espera", botão desabilitado com cadeado e `title` do motivo | Um selo de estado; o bloqueio vira só o botão desabilitado + pílula |
| B3 | P2 | `OrderCard.vue:645-653` + `:897-905` | A estação que falta aparece **duas vezes**: `"1 de 2 prontos · falta Café"` no corpo e `NuxtAlert` `"Aguardando Café"` no rodapé | Manter só a linha do corpo; o rodapé fica vazio ou com o ⋯ |
| B4 | P1 | `components/QueueView.vue:603-714` (`NuxtCard` "Em andamento" contendo um `NuxtCard` por grupo, `:636`) | **Card dentro de Card**, contra `operator-kitchen-sink.md:253`. A decisão do dono (07/10) está só em comentário e num ajuste global de tema (`app.config.ts:109`), o que a faz espalhar para todo Card com Accordion | Registrar a exceção no kitchen sink ou trocar o card interno por lista com separador |
| B5 | P2 | `QueueView.vue:585-593` + `:603-713` + `pages/index.vue:1396-1404` + `QueueView.vue:216-219` | Na Grade, **as mesmas contagens três vezes**: abas `"Precisa de você 4 · Todos 11 · Atrasados 1"`; cabeçalho da seção `"Precisa de você 4"`; botão `"+7: em andamento, nada pede você: 5 na cozinha, 2 na rua · Ver todos"`; aside `"Em andamento 7 pedidos / Na Cozinha 5 / Na rua 2"` | Tirar a contagem do cabeçalho da seção e reduzir o botão a `"Ver todos (11)"` |
| B6 | P2 | `pages/index.vue:1992-2038` + `OrderCard.vue:524-531` | Encomendas: grupo pela data (`"sáb, 19/07"`) e cada cartão repete `"Agendado · sáb 19/07"`; e usa o **OrderCard inteiro** (alto, com rodapé de gesto) para o que só precisa de quem, quanto e quando | Linha compacta (código · cliente · total · ⋯) dentro do grupo; sem o selo de data |
| B7 | P2 | `QueueView.vue:761-766` (rodapé com nota), `OrderCard.vue:897-905` (rodapé com Alert informativo) | **Slot footer como cerimônia**: o contrato de Card diz "footer somente para ações" | Rodapé só com gesto; a nota sai (A47) |
| B8 | P2 | `pages/catalog.vue:1200-1215` | Alert do rascunho de ordem repete **título = descrição** (`"A ordenação ainda precisa de conferência"` duas vezes; `"Confirmando a ordenação…"` duas vezes) | Título só; descrição com as duas ordens |
| B9 | P2 | `pages/[ref].vue:641-649` + `OperatorOrderDetail.vue:396-409`; `[ref].vue:861-875` + `OperatorOrderDetail.vue:468-474` | No celular, **canal duas vezes** (status do cabeçalho e linha de meta) e **pagamento duas vezes** (pílula e linha do resumo) | Deixar só a linha do resumo |
| B10 | P2 | `pages/index.vue:592-597,1342-1350` | Alternador de visão com um segmento só (`"Lista"`) quando a Grade não existe; e na visão Colunas (que mora no ⋯) nenhum segmento fica marcado | Esconder o alternador com uma opção; marcar estado "Colunas" no ⋯ |
| B11 | P2 | `pages/index.vue:1451-1452`, `pages/[ref].vue:730-731`, `OperatorPhoneMenu.vue:84` | Descrições de gaveta de cerimônia: `"Ordenação, visão, atualização e ações auxiliares."`, `"Atualização e ações auxiliares deste pedido."` (e o botão do celular se chama `"Filtros"` mas abre ações) | Sem descrição, ou `description` só para leitor de tela; botão `"Filtros e ações"` |
| B12 | P2 | `OrderCard.vue:740-751` + `:249-251` | Pílula `"DANFE não impressa"` abre Alert cujo título é o mesmo texto; idem `"NFC-e não autorizada"` (`:276-277`) e `"Negociação iFood"` (`:297-298`) | No Popover, título = o que fazer, não o nome repetido |
| B13 | P2 | `OrderCard.vue:457-460` (handoff) | No estado "entregue, desfazer", o cabeçalho troca os selos por `fulfillment · volume` e o corpo repete o fato (`handoff.label`) e o detalhe | Manter só o corpo |
| B14 | P2 | `OperatorOrderDetail.vue:557-581` | Fiscal num `NuxtCard` inteiro para uma linha (rótulo + link) | Linha dentro do card do resumo |

O que está certo e não se mexe: Lista como `NuxtTable` dentro de `NuxtCard` com linha expansível
(é a receita do kitchen sink); pílula + Popover para avisos longos no cartão (decisão de 07/10);
OrderCard com cabeçalho em duas linhas.

---

#### Parte C. As travas de vocabulário

**`surfaces/operator-kit/tests/guardrails.vocabulary.test.ts`**

- **Cobre os arquivos novos do Gestor, sim.** A lista de apps vem de `surfaces/registry.json`
  (`orders-nuxt` é `kind: operator`), a varredura é recursiva em disco e não pula `tests/`;
  `OrderBoardColumn.vue`, `OrderCardMenu.vue`, `OrderBoardHeading.vue`,
  `OperatorSuiteShell.vue`, `OperatorUrgentAlert.vue`, `OperatorLoginForm.vue` e
  `tests/visual/mockBackend.mjs` estão no alcance. Não lê `.json`: a fixture nova
  `orders-nuxt/tests/visual/fixtures/recorded-django.json` (49.906 linhas de copy do
  servidor) fica de fora (hoje sem `aparelh`, conferido por grep).
- **Não checa só string, e checa só três palavras.** `aparelh` vale para a linha inteira
  (código, comentário, template); `fornada` e `passo` descontam comentário. Nenhuma regra
  cobre o que este laudo achou: `Ciente` (§2.1, com baseline proposto em
  `suite-vocabulary.md` §6 e nunca escrito), `novamente` (§2.2), as 14 redações do dado
  velho (§2.3), `(s)`, `board`, `suíte`, `etapa` fora da Produção, `lote` fora da
  Produção. E nada mede D7c (o mesmo gesto com N nomes): é exatamente o V6 da
  `omotenashi-copy.md` §5.3 (baseline que só encolhe), que não existe.
- Proposta: acrescentar `Ciente` e `novamente` como baseline que só desce (o mecanismo de
  `guardrails.identifiers.test.ts`), e incluir `.json` de fixture na varredura.

**`shopman/backstage/tests/test_vocabulario_de_tela.py`**

- Só `.py` de `shopman`, `packages` e `config`, só `aparelh`. Não alcança `orders-nuxt` por
  desenho. Mas é o lado que escreve as palavras que o Gestor mostra sem traduzir
  (`"Marcar como retirado"`, `"Marcar saída para entrega"`, `"Concluir"`,
  `"Pronto · automático"`, `"Aceitar"`): A1 e A4 nascem em parte no servidor, e nenhuma
  trava Python olha vocabulário além de `aparelh` (há `test_copy_sem_travessao.py` para o
  travessão).

**`guardrails.noEmDash.test.ts`** (a terceira, que cuida do travessão): cobre `orders-nuxt/app`
incluindo `.json`, pula `tests/`, aceita `"—"` sozinho como vazio e tem a exceção do
`OfflineBanner` justificada por retrato, não por decisão (A16).

## Anexo D. Herança e travas (eixos 6 e 7)

### Laudo Gestor canônico: Eixo 6 (herança) e Eixo 7 (travas)

Auditor adversarial, somente leitura. Worktree `gestor-canon-laudo`, HEAD `700f6aa63` (PR #1519, empilhado no #1518, `claude/orders-nuxt-ui-migration-b4c49c`). Base de comparação: `origin/main` = `838ce00e6` (merge-base). O diff `origin/main...HEAD` cobre os dois PRs: 229 arquivos, +76.274/-10.260; só no `surfaces/operator-kit`, 73 arquivos, +5.192/-3.406.

Severidade: **P0** perde função ou mente; **P1** fuga do cânone que se espalha; **P2** acabamento.

---

#### 0. Fatos de CI (saída de comando, não previsão)

Checks do SHA `700f6aa6` (#1519) e do `bc689017` (#1518, head do PR de baixo): **os dois têm o MESMO conjunto vermelho.**

| Check | Causa (log do job) |
|---|---|
| `pos-nuxt` | 3 testes quebrados por peça do kit: `tests/pages/preorders.test.ts:566` (`[data-filter-dimension]` some, FilterBar), `preorders.test.ts:858` (`[data-preorders-shortcuts]` vazio, UiFilterChip), `tests/pages/sessionIndex.layout.test.ts:301` (diálogo do PIN do gerente sem `data-state="open"`, OperatorManagerAuth). Mais 1 suíte com timeout de hook (`usePosSale.sale.test.ts`). |
| `marketing-nuxt` | `tests/components/OperatorLogin.test.ts` (3 testes): o harness monta o SFC do kit sem runtime Nuxt e o `<NuxtModal>` vira `<nuxtmodal>` inerte, sem campos. |
| `operator-kit` | vitest local passa (118 arquivos, 1.367 testes, rodado nesta auditoria); a falha é no passo Playwright do catálogo (`tests/catalog/operator-kit-catalog.spec.ts`). |
| `kitchensink-nuxt` | passo Playwright `tests/visual/kitchen-sink.spec.ts` (só 14 passaram, 69 pulados). |
| `Versões das superfícies` | não é versão: é `scripts/check_operator_component_ledger.py`: `[ERRO] orders: layout Nuxt UI canônico usado fora do operator-kit: BoardMenu.vue, CustomerMergeDialog.vue, OrderBoardColumn.vue, OrderCardMenu.vue, pages/[ref].vue, catalog.vue, index.vue`. A trava que o próprio projeto tem contra "layout canônico fora do kit" reprova o Gestor. |
| `Produção — matriz Playwright AA`, `Marketing — cadeia completa` | vermelhos, causa não extraída nesta auditoria (provável herança visual do kit; ver §1). |

`mergeable_state`: #1518 `blocked`, #1519 `unstable`.

Sobre o `test_hub_queue::test_uma_fonte_que_quebra_nao_derruba_a_central` (`shopman/backstage/tests/test_hub_queue.py:350`): o PR diz que "falha na base também". Na CI, `Testes (test-backstage)` está **verde** nos dois SHAs. A falha é local (o teste depende de `caplog`, sensível a configuração de logging do ambiente). **P2**: o corpo do PR deve dizer "falha local, verde na CI", não "falha na base", senão vira desculpa permanente.

---

#### 1. Eixo 6: herança

### 1.1 Como os 8 apps recebem a mudança

- Todos os 9 apps de operador fazem `extends: ["../operator-kit"]` por **caminho relativo** (`surfaces/*/nuxt.config.ts`). Não há pacote versionado: nenhum `package.json` de app declara `@shopman/operator-kit`. **Toda mudança do kit chega a todos os apps no mesmo merge, sem opt-in.**
- `@nuxt/ui` só existe no `operator-kit/package.json` (`^4.11.3`) e no lock do kit (`4.11.3`). Nenhum app tem `@nuxt/ui` no próprio lock; resolvem pelo `operator-kit/node_modules` (comentário em `operator-kit/nuxt.config.ts:91`, `dedupe: ["reka-ui","vue-sonner"]` na linha 96). `reka-ui 2.10.5` e `vue-sonner 2.0.9` iguais em todos os locks. **Não há divergência de versão de Nuxt UI.** A exceção do `scripts/check_surface_versions.py:91` é só o pino exato de `@iconify-json/lucide` no kit; nada a ver com Nuxt UI.
- Os outros 7 apps **ainda estão em ui-thing** (`UiButton`: pos 187, production 96, marketing 82; `UiInput`: pos 39, production 23, marketing 16) e **não usam `Nuxt*` diretamente**. O Nuxt UI entra neles só através das peças do kit. Resultado: cada tela dos 7 apps passa a ter cromo em Nuxt UI (cabeçalho, busca, login, trava, posto, status, rail) e corpo em ui-thing, com duas escalas de altura (ver 1.3). É a pior forma de transição: o app fica com dois sistemas visíveis sem ninguém ter decidido migrar o app.

### 1.2 Mapa de consumo (peça alterada do kit, quem usa)

Varredura de `app/`, `server/`, `tests/` de cada app (sem `node_modules/.nuxt/.output`):

| Peça do kit | hub | pos | kds | prod | mkt | purch | bi | ks |
|---|---|---|---|---|---|---|---|---|
| `app.config.ts` / `operator-theme.css` (tema) | todos, global | | | | | | | |
| `OperatorPageHeader` | | 4 | 2 | 2 | 1 | 1 | 8 | |
| `OperatorSuiteSearch` | 1 | 2 | 1 | 2 | 1 | 2 | 1 | |
| `OperatorLiveStatus` | | 3 | 1 | 1 | 3 | 1 | 1 | |
| `OperatorSectionBar` (barra do celular) | | 1 | 1 | 1 | 1 | 1 | 1 | |
| `OperatorInbox` (via `OperatorSuiteRail`, inalterado) | 1 | 1 | 1 | 1 | 1 | 1 | 1 | |
| `UiFilterChip` | | 1 | 1 | 1 | 1 | 1 | 2 | |
| `OperatorPeriodPicker` | | 1 | | 6 | | | 2 | |
| `OperatorLogin`, `OperatorLock`, `OperatorPwaRuntime`, `OfflineBanner` | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| `OperatorStationSetup` | 1 | 1 | 1 | 1 | 1 | 1 | 1 | |
| `OperatorSessionUnavailable` | | 1 | 1 | 1 | | 1 | 1 | 1 |
| `OperatorManagerAuth`/`OperatorIdentify` | | 6 | | | | | | |
| `OperatorOrderDetail`, `OperatorReasonDialog`, `FilterBar` | | 1 cada | | | | | | |
| `OperatorAppSeal` / `OperatorPhoneMenu` | 1/1 | 1/0 | | | | | | |
| `server/utils/djangoProxy.ts`, `operatorCookies.ts` (BFF) | todos | | | | | | | |

`OperatorSuiteShell`, `OperatorUrgentAlert`, `OperatorLoginForm` são novos e só o Gestor monta o shell (`orders-nuxt/app/app.vue:94`).

### 1.3 Achados de herança

**H1. P0. `OperatorPageHeader` apagou o slot `#below`; as abas de Ajustes do PDV somem.**
`surfaces/operator-kit/app/components/OperatorPageHeader.vue` (base tinha `<slot name="below" />`; HEAD troca por `#feedback`). Consumidores: `pos-nuxt/app/components/PosSettingsShell.vue:51-53` e `pos-nuxt/app/pages/settings/seating.vue:369-371` passam `<PosSettingsTabs />` em `#below`. Vue descarta slot não declarado sem aviso: **toda a navegação entre seções de Ajustes do PDV desaparece**, e nenhuma trava acusa (slot fantasma não quebra teste nem typecheck).

**H2. P0. `OperatorLiveStatus` mente: dado velho aparece como verde "On".**
`surfaces/operator-kit/app/components/OperatorLiveStatus.vue:24-44`. Novo: `badgeColor = tone === "off" ? error : success`, texto visível `"On HH:MM"`; o `label` ("Atualiza a cada 15 s", "Atrasado", etc.) só vai para `aria-label`/`title`. Consequências:
- Produção: `production-nuxt/app/components/ProductionHeader.vue:102` manda `tone="late"` quando `props.stale`; a tela agora mostra **verde "On"** para leitura vencida.
- KDS: `kds-nuxt/app/pages/[ref].vue:137-143`, SSE caído vira `calm` com "Atualiza a cada 15 s"; agora "On", indistinguível do ao vivo.
- Marketing: `marketing-nuxt/app/presentation/liveStatus.ts:1-3` documenta o contrato "fora do ao vivo o estado se escreve por extenso, porque a cor nunca fala sozinha"; o README do kit (`surfaces/operator-kit/README.md:422`) diz o mesmo. O kit quebrou o próprio contrato.
- "On"/"Off" em inglês numa tela em português (a trava de vocabulário não pega).
Pior: `orders-nuxt/tests/canonicalPilot.guardrails.test.ts` (função `chipSizeOk`, "o On/Off é xl") **cristaliza** esse desenho.

**H3. P0. Testes de outros apps vermelhos por herança (fato de CI, §0).** pos 3, marketing 3. A migração do kit foi entregue sem rodar a matriz dos irmãos; o que a CI mostra já é a herança cobrando.

**H4. P1. Tema: alturas de campo voltam ao compacto do Nuxt UI e o tablet perde os 48 px.**
`surfaces/operator-kit/app/app.config.ts`: removidos os overrides `input/select/selectMenu/textarea` `md → h-control` (44 px). `surfaces/operator-kit/app/assets/css/operator-theme.css`: removido `@media (pointer: coarse) and (min-width: 600px) { --spacing-control: 3rem }` (o 48 px "como pede a v4").
- Nos 7 apps, todo `h-control/min-h-control/size-control` (pos 16, production 11, purchase 31, bi 18, marketing 6, kit 21 ocorrências) cai de 48 para 44 px no tablet de toque (KDS, PDV, Produção são tablet).
- Os campos Nuxt UI das peças do kit que esses apps montam (`OperatorStationSetup` NuxtSelect, `OperatorReasonDialog` Select/Textarea no PDV, `FilterBar` Input no PDV, `OperatorPeriodPicker` inputs) caem para a altura `md` padrão do Nuxt UI (cerca de 32 px), ao lado de `UiInput`/`UiButton` do próprio app a 44 px: duas réguas na mesma tela.
- O README do kit ainda promete 44 px (`README.md:88` para `UiFilterChip`, `:776` "Alvo de toque de 44 px pelo token").

**H5. P1. `UiFilterChip` perdeu o alvo de toque e o desenho de pílula.**
`surfaces/operator-kit/app/components/UiFilterChip.vue`: de `<button class="min-h-control rounded-full ...">` para `<NuxtButton :variant="active ? 'soft' : 'outline'">` com `NuxtBadge` de contagem. O comentário removido dizia literalmente "`min-h-control` (44 px) é alvo de toque, não estética" e contava uma regressão anterior idêntica no Marketing. Consumidores: pos (Encomendas), kds `[ref].vue`, production `ProductionStageGrid`, marketing `campaigns`, purchase, bi `index`/`sales`. Já quebrou `pos-nuxt/tests/pages/preorders.test.ts:858`. O novo comentário chama a peça de "Compatibilidade temporária" sem prazo nem trava.

**H6. P1. `OperatorPageHeader` virou `NuxtDashboardNavbar` de altura fixa; `#phone-actions` aparece no desktop.**
- `#phone-actions` agora é renderizado no `#right` sem `md:hidden`. B.I. (`bi-nuxt/app/pages/cash.vue:93-100` e as outras 6 páginas) põe `BiWindowPicker`+`BiPageMenu` em `#actions` e `BiPeriodChip`+`BiShareButton` em `#phone-actions`: **no desktop aparecem os dois seletores de período**. Purchase (`purchase-nuxt/app/pages/index.vue:1222`) idem.
- A linha de ações rolável do celular (`overflow-x-auto`, "nenhuma função fica só no desktop") foi trocada por `flex items-center gap-2` dentro de uma barra de altura fixa: ações em excesso estouram ou cortam no celular.
- O componente agora tem 3 raízes (Navbar, Toolbar, div feedback): `class`/attrs passados pelo consumidor deixam de cair no header.
- Eyebrow virou `NuxtBadge` ao lado do título; `#subtitle` saiu de baixo do título para `#trailing` na mesma linha. Produção (`ProductionHeader.vue`) usa `#subtitle` para a linha de hora/contagem das prévias v4.
- O cabeçalho perdeu `bg-card`; fica sobre o bege da página.
- `#icon` usado por purchase e bi não existe nem na base: slot morto pré-existente, não é deste PR (P2, registrar).

**H7. P1. `OperatorSuiteSearch`: o campo que filtra a tela virou botão que abre modal.**
`surfaces/operator-kit/app/components/OperatorSuiteSearch.vue:268-297`: `NuxtDashboardSearchButton` + `NuxtModal`. KDS (`[ref].vue:300`), Produção (`RecipeHeader.vue:42`, `ProductionHeader.vue:329`), Marketing (`campaigns.vue:476`), Compras (`index.vue:1204,1214`), B.I. (`index.vue:234`) usam `v-model` + `screen-label` para filtrar a lista **enquanto a vê**. Agora o filtro acontece dentro de um modal que cobre a lista. A função existe, a leitura do resultado não. Atributos removidos (`data-suite-search-clear`, `-dialog-input`, `-group`, `data-search-shortcut`) não são usados por outros apps (verificado).

**H8. P1. `OperatorSectionBar` (barra inferior do celular) virou `NuxtNavigationMenu` horizontal.**
`surfaces/operator-kit/app/components/OperatorSectionBar.vue`: antes, cada item era coluna de `min-h-16` (ícone de 22 px sobre rótulo, pílula no ativo, selo numérico). Agora é menu horizontal (ícone ao lado do rótulo) com "!" no lugar do ponto de atenção. Em 360 px, 4 ou 5 seções mais o "Mais" não cabem lado a lado: rótulos truncam. Afeta pos, kds, production, marketing, purchase, bi no celular. O `aria-current` deixa de ser explícito.

**H9. P1. Avisos no rail dos 7 apps: sino escuro, sem rótulo, sobre o bronze.**
`OperatorSuiteRail.vue:212,243` (inalterado) monta `<OperatorInbox placement="rail">`. O Inbox (`OperatorInbox.vue`) trocou o `RailSection` rotulado "Avisos" por `NuxtButton color="neutral" variant="ghost"` com `NuxtChip`. No rail (`bg-rail` `#8b6b2e`, `text-rail-foreground` branco), o botão neutro pinta o ícone na cor de texto padrão (escura) sobre bronze e o hover em bege: baixo contraste, sem o rótulo que todos os outros itens do rail têm. O Gestor escapa porque usa o `OperatorSuiteShell` novo; os 7 irmãos não. No celular/tablet em pé (hub e todos via `OperatorPageHeader`), o sino caiu de `size-11/md:size-12` para o `md` do Nuxt UI.
O comentário apagado no topo do Inbox também dizia "**Não interrompe.** sem modal, sem som, sem roubo de foco". O `OperatorUrgentAlert` novo é exatamente um modal que interrompe. A decisão do dono (07/10) muda a regra; o certo era reescrever o comentário com a exceção, não apagá-lo.

**H10. P1. `OperatorPeriodPicker` regrediu de `UiDateField` para `<NuxtInput type="date">` nativo.**
`surfaces/operator-kit/app/components/OperatorPeriodPicker.vue:245-298` (base: `UiDateField` nas linhas 264, 274, 300). Consumidores: pos (Encomendas), production (6 telas), bi (2), orders. É exatamente o que `kitOwnership.guardrails.test.ts:250` proíbe nos apps ("não devolve data ou hora ao seletor nativo"), só que feito no kit, onde a trava não olha (ver T3). Os presets viraram `NuxtTabs` (Tabs para escolha de valor, não para troca de painel); "Próximos 7D" e "Últimos 7D" têm o mesmo texto visível "7D", e o teste que verificava `aria-label` "Próximos 7 dias"/"Últimos 7 dias" foi removido.

**H11. P1. PIN do PDV: teclado menor e sem `touch-manipulation`.**
`OperatorIdentify.vue`: teclas de `py-3 text-lg` (cerca de 52 px) com `touch-manipulation select-none` para `NuxtButton size="xl"` (cerca de 40 px) sem essas classes; `NuxtPinInput :length="8"` desenha sempre 8 caixas, mesmo para PIN de 4 dígitos (sugere um tamanho que não existe). Usado por `OperatorLock` (todos os apps) e `OperatorManagerAuth` (6 pontos do PDV). O teste do PDV `sessionIndex.layout.test.ts:301` já quebrou no diálogo de PIN.

**H12. P1. `OperatorLock` usa `NuxtAlert` como título.**
"Identifique-se para operar" e "Perdi meu crachá" viraram `NuxtAlert color="neutral"/"warning"` no lugar do `<h2>`. A tela de trava, montada por todos os apps, fica sem heading e com um aviso que não é aviso. Mesmo padrão em `OperatorIdentify` (erro como Alert, aceitável) e em `OfflineBanner` (ok, Banner é a peça certa).

**H13. P2. Tema global (Card, Table, PageCard, Alert, Kbd, Chip).**
- `alert`: removido `defaultVariants: { variant: "subtle" }` e o override de `title/description: text-default`. Default do Nuxt UI volta a `solid`/`primary`. Os 7 apps não usam `NuxtAlert` direto, mas o kit sim: 12 `NuxtAlert` sem `variant` no Kitchen Sink (`OperatorKitchenSinkDashboard.vue:229` e outros) agora saem sólidos cor primária. O catálogo que documenta o contrato mudou de aparência sem decisão.
- `alert.compoundVariants` subtle pré-misturado com `--card`: correto como intenção (opaco), mas sobre o bege da página o "subtle" ganha um retângulo branco-tingido.
- `card.slots.body` com seletores `has-[>[data-slot=root]:only-child>table]:p-0` e `...>[data-slot=item]]:py-0`: depende do markup interno de `UTable`/`UAccordion` (`data-slot`); mudança de versão do Nuxt UI quebra em silêncio. Hoje só o Gestor e o Kitchen Sink usam `NuxtCard`.
- `table.pinned/sticky` com `bg-card`, `pageCard outline bg-card`, `kbd soft`, `chip 4xl`: sem efeito nos 7 apps (não usam essas peças diretamente).
- Variáveis removidas `--op-splitter-handle`, `--op-layer-resize`: nenhum app usa (verificado).

**H14. P2. Toast: dois mundos, e o novo só funciona onde há `UApp`.**
`OperatorUrgentAlert.vue:20` chama `useToast()` (Nuxt UI). Só `orders-nuxt` e `kitchensink-nuxt` montam `OperatorAppRoot` (`<NuxtApp>`); os outros 7 montam `OperatorSonner` (vue-sonner) e nenhum `UApp`. Hoje o Urgent só existe dentro do `OperatorSuiteShell` (só Gestor), então não quebra. Mas o kit agora tem dois contratos de aviso: peças do kit chamam `useSonner` (`OperatorLock.vue:111,124,135`, `OperatorMenuItems.vue:52`, `OperatorRail.vue:83`, `useOperatorLock.ts:133`), que no Gestor é reapontado para `useToast` (`orders-nuxt/nuxt.config.ts:116`, `app/utils/operatorToast.ts`) e nos outros vai para vue-sonner; o Urgent chama `useToast` direto. O dia em que outro app adotar o `OperatorSuiteShell` sem `OperatorAppRoot`, o lembrete de "Ainda sem resposta" some sem erro. O Kitchen Sink monta os dois toasters ao mesmo tempo. A trava `catalog.guardrails.test.ts:168` congela `dedupe: ["reka-ui", "vue-sonner"]`, ou seja, cristaliza o Sonner como runtime global.

**H15. P2. BFF dos 9 apps mudou dentro de um PR de UI.**
`surfaces/operator-kit/server/utils/operatorCookies.ts`: `operatorSetCookieHeaderForBrowser` ganhou `target` e, quando o host da requisição é loopback, remove `Domain=` e (em http) `Secure` do Set-Cookie. `djangoProxy.ts` passa `getRequestURL(event)` (derivado do `Host` da requisição). Em produção o Host é o público, então o efeito é só dev; mas é mudança de segurança de sessão de todos os apps escondida num PR de 52 mil linhas sobre Gestor. Merece PR próprio com nome.

**H16. P2. Comentários de decisão apagados no kit.** `OperatorInbox.vue` (18 linhas de rationale: "um item só", "não interrompe", "realce, nunca silo", portal), `UiFilterChip.vue` (régua de 44 px e o histórico da regressão), `OperatorPageHeader.vue` (medidas da prévia, "nenhuma função fica só no desktop"), `OperatorSuiteSearch.vue` (o contrato do campo que filtra). O código novo contradiz o que os comentários garantiam e eles sumiram junto, em vez de serem revistos.

### 1.4 Testes de outros apps

- Só `orders-nuxt` e `operator-kit` têm `node_modules` neste worktree; os outros 7 não, então não rodei vitest neles (regra da tarefa). A CI responde por eles (§0): **pos e marketing vermelhos por herança**; hub, kds, production, purchase, bi verdes no vitest (o que só prova que os testes deles não montam essas peças, não que a tela está certa: H2, H6, H8, H9 passam por todas as travas).
- Testes de outros apps que leem ou montam código do kit: `pos-nuxt/tests/components/OperatorManagerAuth*.test.ts` (as strings "Trocar gerente", "Quem autoriza?" etc. continuam no kit; passam), `marketing-nuxt/tests/components/OperatorLogin.test.ts` (quebra), `pos-nuxt/tests/pages/sessionIndex.layout.test.ts:329` (passa por vacuidade: a busca não tem mais `input`), `purchase-nuxt/tests/camada-visual-da-suite.test.ts` e `marketing-nuxt/tests/sectionBar.test.ts` (só checam `data-suite="v3"` no shell do app, que o Gestor proíbe e os outros ainda exigem: duas travas com verdades opostas na mesma suíte).

---

#### 2. Eixo 7: travas

### 2.1 Inventário

| Trava | O que checa de fato | O que deixa passar |
|---|---|---|
| `operator-kit/tests/catalog.guardrails.test.ts` (novo, +74) | `toContain` de strings em `OperatorKitchenSink.vue`, `OperatorOfficeShell.vue`, `OperatorSuiteShell.vue`, `app.config.ts`, `operator-base.css`, `nuxt.config.ts` | Qualquer comportamento. Ver T1, T2. |
| `operator-kit/tests/kitOwnership.guardrails.test.ts` | Regex sobre `app/` **de cada app**, sem o kit: `<input type=checkbox/radio>`, `<input type=date/time/...>`, cópias de primitivas | `<NuxtInput type="date">` (regex exige `<input`); tudo que está dentro do kit (T3). |
| `guardrails.appBar.test.ts` (+71) | Presença de peças do kit nos shells, "um só item de Avisos", ordem do pé do rail | Aparência e contraste do item (H9 passa). |
| `guardrails.suiteSearch.test.ts` | A busca existe no cabeçalho, uma só | Se ela filtra inline ou em modal (H7 passa). |
| `guardrails.pendingAction.test.ts` (+100) | Botão com `@click` async declara pendente (regex) | Ok como lista que encolhe; é string. |
| `guardrails.test.ts`, `.vocabulary`, `.noEmDash`, `.copyNeverTruncates`, `.a11y`, `.nativeConfirm`, `.phoneBar`, `.identifiers` | Varreduras de texto por app | "On"/"Off" em inglês (H2) passa no vocabulário; slot inexistente passa em todas. |
| `sessionUnavailable.guardrails`, `appLaunch.guardrails`, `iconCollections.guardrails`, `appName.guardrails` | Contratos específicos, por texto | Fora do escopo das regressões acima. |
| `orders-nuxt/tests/canonicalPilot.guardrails.test.ts` (novo, 839 linhas) | Regex e AST (`@vue/compiler-dom`) sobre o Gestor **e** sobre as peças do kit alcançáveis a partir dele (grafo `reachableShared`): sem `<button|input|select|textarea|form|table>` cru, sem `<Ui*>`, sem `:ui=`, sem `reka-ui`, sem `role=` manual, sem skin em controles Nuxt, Badge só soft/subtle, Button sem `size` (exceto `xs`), Alert sempre com `variant`, ações de Alert outline e da mesma cor, Card sem classes de borda/fundo, sem `suite:` | `type="date"` em `NuxtInput`; Card dentro de Card fora dos casos que o teste conhece; tudo nos 7 outros apps (o grafo parte só do Gestor). |
| `orders-nuxt/tests/support/uiPrimitives.ts` (+896) | Não é trava: são **25 dublês** escritos à mão de `NuxtButton`, `NuxtModal`, `NuxtTable`, `NuxtInput`, `NuxtSelect`, `NuxtTabs`, `NuxtPopover`, `NuxtDropdownMenu`... registrados globalmente no projeto `component` | Ver T5. |
| `scripts/check_operator_component_ledger.py` | Contagens com teto por app (`native_control_occurrences` = regex `<(?:button|select|textarea)`), import direto de `@nuxt/ui`, estrutura canônica (`NuxtDashboard*`, `NuxtNavigationMenu`...) fora do kit | `<input>` cru não conta; `type="date"` não conta. **Hoje reprova o próprio Gestor** (§0). |
| `scripts/check_operator_layout_guardrails.py` | Arquivo local com nome `*Shell|Layout|Sidebar|Splitter|Dashboard.vue` e declaração de tokens `--op-*` fora do kit | Layout feito com outro nome. |
| `scripts/check_surface_versions.py`, `check_surface_registry.py` | Versões e registro | Nada de UI; ambos verdes. |
| `scripts/run_operator_visual.py` (+9) | Aceita `--scenario <estado de auditoria>` | Mudança de runner, não trava. |

### 2.2 Achados de trava

**T1. P1. Trava que cristaliza decisão errada: o Live Status binário.**
`orders-nuxt/tests/canonicalPilot.guardrails.test.ts` (`chipSizeOk`: `if (file.endsWith("OperatorLiveStatus.vue")) return /\bsize="xl"/.test(tag)`, comentário "o On/Off é xl"). Congela o desenho que esconde "atrasado" (H2). Quem consertar H2 encontra um teste dizendo que On/Off é a regra.

**T2. P1. Travas que afirmam string de classe ou arquivo errado.**
- `catalog.guardrails.test.ts:129-143` exige a string exata `'body: "p-4 sm:p-4 has-[>[data-slot=root]:only-child>table]:p-0 has-[>[data-slot=root]:only-child>[data-slot=item]]:py-0"'`. Qualquer refactor equivalente reprova; nenhuma regressão visual real é detectada (o que importa é o padding renderizado da tabela no card).
- `catalog.guardrails.test.ts:101-112` exige strings de classe do `OperatorPwaRuntime` (`bottom-[calc(var(--ui-header-height)+1rem+env(...))]`).
- `canonicalPilot.guardrails.test.ts` exige `'"4xl": "h-4 min-w-4 px-1 text-[12px]/none"'` no `app.config.ts` e `size="4xl"` no `OperatorInbox.vue`.
- `catalog.guardrails.test.ts:119-127` ("sem inflar controles globalmente") verifica `@media (pointer: coarse)` em **`operator-base.css`**, mas a regra removida morava em **`operator-theme.css`**. A trava crava a remoção dos 48 px do tablet (H4) e ainda assim olha o arquivo errado: a regra pode voltar no lugar onde sempre esteve e a trava não vê. Também cristaliza a decisão de "não inflar" sem registro do dono revogando a régua de toque de 44/48 px.

**T3. P1. A trava contra data nativa não alcança o kit nem o `NuxtInput`.**
`kitOwnership.guardrails.test.ts:250-262` itera `OPERATOR_APPS` (sem o kit) e procura `<input ... type="date">`. Resultado: `OperatorPeriodPicker.vue:248,259,294` (kit, consumido por 4 apps) e `orders-nuxt/app/components/ChannelPeriodCalendar.vue:13,16,19,22` (`<NuxtInput type="date|time">`) passam. Pior: `operator-kit/tests/components/OperatorDatePickers.test.ts` foi reescrito para consultar `input[type="date"]` (era `findAllComponents(UiDateField)`): o teste agora **exige** o seletor nativo.

**T4. P1. Regras do cânone sem trava nenhuma (ou só no Gestor).**
- Slot passado que o componente não declara (H1): nenhuma trava, nenhum typecheck. Sugestão: teste que lista `<template #x>` de cada consumidor de peça do kit e confere contra os `<slot name>` dela.
- `type="date|time"` em `NuxtInput`/`UInput`: sem trava em lugar nenhum (T3).
- `:ui=` por instância: só proibido no grafo do Gestor; o kit tem 14 (`OperatorPushSettings`, `OperatorPage`, `UiButton`, `UiSelect`, `UiCheckbox*`, `UiDate*`, `UiSwitch`, `OperatorKitchenSinkDashboard`) e o Marketing 14 (`MarketingOfferForm.vue`, `CampaignForm.vue`, `FireCampaignPanel.vue`).
- `<button>` cru: no Gestor, proibido; nos outros apps, só teto de contagem (`check_operator_component_ledger.py`: pos 157, purchase 132, production 91...), e `<input>` cru nem é contado.
- Card dentro de Card: só os casos "divisor" do Gestor (`canonicalPilot...:626`); nenhuma trava geral.
- Alert usado como título (H12): nenhuma.
- Texto de estado em inglês ("On"/"Off"): a trava de vocabulário só conhece "aparelho", "fornada", "passo".
- Altura mínima de alvo de toque em tablet: nenhuma trava de comportamento (só strings).
- Contraste do item no rail (H9): a matriz visual existe, mas o Gestor não usa o `OperatorSuiteRail`, então nenhuma matriz cobre o rail dos irmãos com o Inbox novo.

**T5. P1. Os testes de componente do Gestor testam dublês, não o Nuxt UI.**
`orders-nuxt/tests/support/uiPrimitives.ts` (+896 linhas, 25 dublês). Asserções sobre foco, abrir/fechar, `data-state`, tabela, menu, popover passam contra a implementação escrita no teste. É o mesmo problema que derrubou o PDV (`sessionIndex.layout.test.ts:301` espera `data-state="open"` do Modal real): no Gestor, o dublê decide o que é verdade. O kit, por contraste, monta Nuxt UI real com `mountSuspended`. A divergência de harness entre apps (marketing: `@vitejs/plugin-vue` sem runtime; pos: `environment: "nuxt"`; orders: dublês) explica por que a mesma peça do kit passa num app e quebra no outro.

**T6. P2. A trava do ledger reprova o Gestor e o PR segue.** `check_operator_component_ledger.py:296-306` acusa "layout Nuxt UI canônico usado fora do operator-kit" em 7 arquivos do Gestor. Ou o Gestor está errado (estrutura deveria estar numa peça do kit) ou a trava está desatualizada para o piloto; nenhum dos dois foi decidido, e o check está vermelho nos dois PRs.

### 2.3 Os +52 mil linhas do #1519

`git diff --stat` ordenado (diff total dos dois PRs):

| Arquivo | Linhas | Natureza |
|---|---|---|
| `surfaces/orders-nuxt/tests/visual/fixtures/recorded-django.json` | +49.906 (1.544.736 bytes) | fixture gravada do Django (seed Nelson) para o mock da matriz visual |
| `surfaces/orders-nuxt/app/pages/index.vue` | 2.443 | código |
| `surfaces/orders-nuxt/tests/visual/fixtures/orders-board.json` | +2.212 (75.960 bytes) | fixture |
| `surfaces/orders-nuxt/app/pages/catalog.vue` | 2.124 | código |
| `surfaces/orders-nuxt/app/components/CatalogProductPanel.vue` | 1.855 | código |
| `surfaces/orders-nuxt/tests/visual/fixtures/alerts.json` | +408 | fixture |

O #1519 tem +52.450 linhas em 51 arquivos; 96 % é o `recorded-django.json`.

**F1. P2. Não é artefato acidental (não é screenshot, trace nem relatório): é fixture usada** por `orders-nuxt/tests/visual/mockBackend.mjs:23` (`recordedFor(url)`). Mas:
- 1.092.676 bytes (70 %) são **uma** resposta: `/api/v1/backstage/catalog/?collection`. O mock casa só pelo caminho quando a query difere (`mockBackend.mjs:24-28`), então uma fatia do catálogo bastaria.
- Sem PII: 0 CPF, 0 telefone `+55`, 0 e-mail, 0 cookie/sessão/Authorization (`token` aparece 46 vezes, todas `token_required`).
- **Não é hermética**: 44 URLs `https://images.unsplash.com` e 50 `https://img.nelsonboulangerie.com.br` dentro das respostas; `orders-board.spec.ts` não intercepta imagem (nenhum `page.route`/`abort`). A matriz visual depende de rede e de imagem externa estável: candidato a retrato que muda sozinho.
- Contrato congelado sem verificação: nada compara essas respostas gravadas ao contrato gerado; quando a API mudar, a matriz continua verde com o formato antigo.
Recomendação: cortar para os campos e linhas renderizados, trocar `image_url` por asset local ou interceptar imagens, e validar a fixture contra o contrato/OpenAPI no teste.

---

#### 3. Resumo por severidade

- **P0 (4)**: H1 slot `#below` some e o PDV perde as abas de Ajustes; H2 Live Status mostra verde "On" para dado vencido (Produção, KDS, Marketing, PDV, B.I., Compras); H3 pos e marketing vermelhos na CI por herança do kit (6 testes); CI vermelha nos dois PRs, incluindo a trava de ledger contra o próprio Gestor.
- **P1 (14)**: H4 alturas e 48 px do tablet; H5 FilterChip sem alvo de toque; H6 cabeçalho (phone-actions no desktop, overflow no celular); H7 busca virou modal; H8 barra do celular horizontal; H9 Avisos no rail escuro e sem rótulo; H10 data nativa no PeriodPicker; H11 PIN menor; H12 Alert como título; T1 trava cristaliza On/Off; T2 travas de string e arquivo errado (pointer coarse); T3 trava de data cega ao kit e teste que exige nativo; T4 regras sem trava; T5 dublês no lugar do Nuxt UI.
- **P2 (8)**: H13 tema (Alert solid no catálogo, seletor `data-slot` frágil); H14 dois toasters; H15 mudança de cookie do BFF dentro de PR de UI; H16 comentários de decisão apagados; T6 ledger reprovando sem decisão; F1 fixture de 1,5 MB não hermética; slot `#icon` morto pré-existente em purchase/bi; frase "falha na base" do hub_queue (verde na CI).

**Recomendação de corte**: o kit não pode mudar para o Gestor e para os outros 7 apps no mesmo merge sem opt-in. Ou (a) as mudanças de comportamento do kit (PageHeader, SuiteSearch, LiveStatus, SectionBar, Inbox, FilterChip, PeriodPicker, Identify, tema de altura) ficam atrás de uma variante/peça nova usada só pelo Gestor (`OperatorSuiteShell` já é esse caminho), ou (b) o PR migra os 7 consumidores junto e prova com a matriz deles. Hoje é (c): os 7 recebem a mudança sem saber, e a CI já mostra.

