# WP-FASE2-UX-OPERADOR: as atividades comuns do operador viram peças do kit

Pedido do dono (09/10/2026): redesenhar TODOS os apps de operador a partir das atividades
comuns, com o celular organizando também a mesa; filtros, busca, tabela, navegação entre
registros e barras como peças robustas e genéricas do `operator-kit`. O PDV tem carta branca
para ser mais específico.

Este documento consolida quatro laudos de leitura feitos sobre `origin/main` em `401485b83`
(#1559), com `nuxt dev` contra o mock de cada app, a 390 e 1440 px (o G2 também a 768):

| laudo | apps | onde estão as capturas |
|---|---|---|
| G1 | Gestor de pedidos, Central, Kitchen Sink | `fase2-capturas/{orders-nuxt,hub-nuxt,kitchensink-nuxt}/` |
| G2 | PDV, Cozinha, Produção | `fase2-capturas/{pos,kds,production}/` |
| G3 | Marketing, Compras, B.I. | `fase2-capturas/{marketing,compras,bi}/` |
| G4 | o kit como fornecedor de peças, a ação na base do Storefront, o Nuxt UI 4.11.3 oficial | `fase2-capturas/storefront/` |

As capturas ficaram no scratchpad da sessão coordenadora (não versionadas). Os achados
abaixo citam arquivo e linha do `main` medido; quem implementar confere de novo no ref atual.

A proposta visual mora no Kitchen Sink, em `/proposal/fase2`
(`surfaces/kitchensink-nuxt/app/pages/proposal/fase2/index.vue` e
`app/components/Fase2*.vue`): peças reais do Nuxt UI com o tema do kit, para o dono
decidir. Nada nela é contrato ainda; o que for aprovado nasce no kit pelos PRs da seção 8.

Decisões que este WP NÃO reabre: o conjunto mínimo de 08/10 (botão md/xl, selo `soft`,
cartão `outline`/`soft`, aviso `subtle`, `NuxtSelect`/`NuxtSelectMenu`, barra lateral em 3
estados, barra inferior de 3 a 5, barra do topo no celular = ☰ + título + 2 ícones + ⋯,
toolbar do celular em 1 linha com "Filtros (n)"); F7 (deslizar para entregar no celular:
sim); o aviso "sem vocação" como `NuxtAlert` (#1561); o "fez × vendeu" pelo gráfico do kit
(#1562).

## 1. Retrato em cinco linhas

1. **Só dois apps estão no shell da suíte** (Gestor e B.I.). PDV, Cozinha, Produção,
   Marketing e Compras seguem na barra antiga, com **zero componente Nuxt UI** (Compras 0,
   PDV 0, Cozinha 0, Produção 0; Marketing 2), 270+ `<button>` crus e 43 `UiNativeSelect`.
2. **A mesma atividade tem uma peça por app**: 8 barras de ação na base feitas à mão, 4
   padrões de ⋯, 3 cabeçalhos no PDV, 5 tabelas diferentes no Gestor, 22 `<table>` crus em
   PDV e Produção, 4 formas de "Atualizar" no Compras.
3. **O celular não tem regra para o que fica entre o topo e o conteúdo**: a toolbar ocupa
   até 4 linhas (Marketing), o topo da Base do Compras ocupa 362 px (43% da tela), e
   navegação secundária aparece desenhada como filtro (Compras, Marketing, B.I.).
4. **Faltam peças inteiras no kit**: tabela completa (ordenar, colunas, compacto), barra de
   seleção, anterior/próximo, favoritos de filtro, ação na base, estado de tela, lugar do
   aviso da tela. A base de cada uma já existe no Nuxt UI 4.11.3.
5. **Dois defeitos de hidratação quebram telas no celular** quando a rota abre direto
   (Gestor: fila em esqueleto eterno e toolbar sumida; Cozinha: barra inferior com os links
   trocados, #1563). A causa é a mesma: régua de largura decidida no servidor sem saber a
   largura.

## 2. Atividades comuns do operador

A tabela junta o que os quatro laudos mediram, pela frequência no app onde aparece mais.

| # | atividade | onde aparece | como é feita hoje |
|---|---|---|---|
| A1 | **Ver a fila e agir no próximo** | Gestor (fila), Cozinha (Preparo), Produção (etapas), Marketing (Decisões), Compras (Painel "Precisa de você"), Central (fila das filas), PDV (comandas) | cartões e colunas próprios por app; teclas só no Gestor (↑↓ Enter) |
| A2 | **Buscar** | todos | `OperatorSuiteSearch` já em níveis (Esta tela, App, Toda a suíte); o mesmo slot muda de nível sem sinal na Produção e na Cozinha; o PDV tem três buscas e mostra duas juntas a 390 |
| A3 | **Recortar rápido** (o "filtro rápido") | Gestor (escopo, Entrega/Retirada), Cozinha (Todos/Entrega/Atrasados), Produção (Todos/A planejar…), PDV Encomendas, Marketing (Campanhas, Enviados), Compras (Atenção), B.I. (veredito), Clientes do Gestor | `NuxtTabs` pill à mão (Gestor), `UiFilterChip` (5 apps), pílula sobre `<select>` invisível (Marketing), chips `<button>` (PDV no celular) |
| A4 | **Ir a uma sub-seção** (navegação secundária) | Compras (Base: Insumos, Fornecedores, Custos, Contagem), Marketing (Ajustes), B.I. (Sobrou ou faltou / Lotes no período), PDV (Ajustes), Gestor (abas Entrada/Preparo/Saída do Quadro), Produção (Qualidade) | 3 desenhos, quase sempre DENTRO da faixa de filtros e com o mesmo desenho deles |
| A5 | **Filtrar por completo** | Gestor (Histórico, Catálogo), PDV (Encomendas), Produção (Relatórios), Marketing (Enviados), B.I. (Explorar) | `FilterBar` em 3 telas; cartão com "Aplicar" na Produção; `<select>` nativos no Marketing; nada no Compras |
| A6 | **Escolher a data ou o período** | B.I. (todas), Gestor (Histórico), PDV (Encomendas), Produção (etapas, Relatórios), Marketing (Enviados "Criado em"), Compras (dia) | `OperatorPeriodPicker` em 4 apps; `<select>` nativo no Marketing |
| A7 | **Ler uma lista em tabela** (ordenar, escolher colunas, abrir a linha) | Gestor (Lista, Histórico, Catálogo, Clientes, Unificações), B.I. (21 tabelas), Compras (4), Marketing (Campanhas), Produção (14 `<table>`), PDV (8 `<table>`) | `NuxtTable` montada por tela sem contrato, ou `<table>` crua; nenhuma ordena pelo cabeçalho; colunas só no Catálogo; compacto em nenhuma |
| A8 | **Agir em vários de uma vez** | Gestor (Aceitar N, Avançar N; Catálogo), Compras (custos e mínimos), Produção (Plano) | barra no topo na fila, no pé no Catálogo, inexistente no resto |
| A9 | **Abrir o registro e ir ao próximo** | Gestor (pedido, cliente), PDV (encomenda), Produção (receita, lote), Compras (item da entrada, insumo), Marketing (Revisão), B.I. (dia) | só o Recebimento do Compras tem ‹ › e "Item N de M"; o B.I. anda de dia; o resto só "voltar" |
| A10 | **Fazer a ação do momento no celular** | Gestor (pedido), Cozinha (Pronto), PDV (Encomendas, Fim do dia), Compras (Receber, item), Marketing (Revisão), B.I. (Levar ao plano), Produção (painel encaixado) | 8 barras à mão (`fixed`, `sticky bottom-16`, `bottom-20`, `bottom-0`, números mágicos para a barra inferior) |
| A11 | **Deslizar para agir** | Gestor (Quadro; F7 decidido: entregar) | `SwipeReveal` mora no Gestor |
| A12 | **Ler um aviso da tela** | Gestor ("sem vocação"), Cozinha (Visto, cancelamento, push), Marketing (sessão, disparo), Compras (erro), B.I. (Perfis) | `NuxtAlert` só no B.I. e no Gestor; o resto `div role=alert` à mão |
| A13 | **Ver o estado da tela** (carregando, vazio, erro, sem conexão) | todos | `BiPageState` × `NuxtAlert` inline no B.I.; faixas à mão no Marketing e no Compras |
| A14 | **Mais ações** (o ⋯) | todos | Gestor 3 formas, Marketing 4 padrões (e some no celular), Compras e Produção `UiPopover` à mão, PDV `UiPopover` da comanda |
| A15 | **Atualizar** | todos | ícone, item do ⋯, botão de texto, tecla R, e às vezes na toolbar (Gestor) |

## 3. Divergências por gravidade

**Grave: quebra ou esconde o trabalho**

| # | divergência | onde | destino |
|---|---|---|---|
| D1 | Rota aberta direto a 390 quebra a tela: fila em esqueleto eterno (`emitsOptions`), toolbar some em Histórico, Clientes e Catálogo | Gestor (`pages/index.vue:1309` e as outras, `useMediaQuery` decide a árvore no servidor) | frente urgente lançada pelo coordenador (`claude/gestor-carga-direta-celular`); a régua única (K0) impede que volte |
| D2 | Barra inferior troca destino e rótulo quando `/bancada` abre direto | Cozinha (`useKdsShell.ts:120-165`) | #1563 |
| D3 | Fornecedores a 390 estoura a página (658 px) | Compras | onda do Compras (K1 resolve a tabela) |
| D4 | Topo da Base ocupa 362 px grudados (43% da tela de 844) | Compras (`index.vue:1182-1352`) | papéis das barras (seção 5) + K4 |
| D5 | `/settings/printers` sem barra inferior e sem selo | PDV (`PosSettingsShell` não monta a barra) | onda do PDV (navegação montada uma vez no layout) |
| D6 | Texto da casa cortado (nome do produto, do insumo, do cliente) | Gestor Catálogo, Compras Insumos, PDV grade semanal, Central | K1 (célula que quebra) e trava `copyNeverTruncates` por app |

**Alta: contradiz regra do kit em todas as telas de um app**

| # | divergência | onde |
|---|---|---|
| D7 | Cinco apps fora do shell da suíte (sem gaveta ☰, sem barra inferior 3 a 5, sem `phone-filters="drawer"`) | PDV, Cozinha, Produção, Marketing, Compras |
| D8 | Ação na base feita à mão, 8 vezes, sem `data-focus-obstruction`, adivinhando a altura da barra inferior | Cozinha `[ref].vue:617`; Marketing `AnnouncementCard.vue:929`; PDV `index.vue:1611`, `preorders/index.vue:764`, `session/closing.vue` (3×); Compras `index.vue:1954`, `:2248` |
| D9 | ⋯ em várias formas e que some no celular | Gestor (3), Marketing (4), Compras, Produção, PDV |
| D10 | Toolbar do celular em várias linhas | Marketing (até 4), Produção (chips em 2), B.I. (linha extra das abas), Gestor (2ª toolbar Entrada/Preparo/Saída) |
| D11 | Navegação secundária desenhada como filtro, dentro da faixa de filtros | Compras (pílulas que levam a Comprar e Custos), Marketing (Ajustes), B.I. (Sobrou/Lotes) |
| D12 | Ação na toolbar ("Atualizar", "Admin", "Unificações") | Gestor (7 telas), Kitchen Sink |
| D13 | Busca muda de nível no mesmo lugar sem dizer | Produção, Cozinha; PDV com duas buscas visíveis |
| D14 | Régua de largura redeclarada por página (10 telas do Gestor; a fila usa 4 réguas) | Gestor, e o mesmo padrão nos outros |
| D15 | Três cabeçalhos para o mesmo papel | PDV (`OperatorPageHeader`, `closing.vue`, `report.vue`) |

**Média: inconsistência entre telas**

| # | divergência | onde |
|---|---|---|
| D16 | Barra de seleção no topo numa tela e no pé noutra | Gestor (`index.vue:1579` × `catalog.vue:1846`) |
| D17 | Tabelas sem contrato comum (expandir, seleção, colunas, ordenar: cada uma tem um pedaço) | Gestor, B.I., Compras, Marketing |
| D18 | Estado de erro em 2 padrões; carregando ora `naked`, ora não | B.I., Marketing, Compras |
| D19 | "Filtro" e "Filtros" na mesma tela do celular | Gestor |
| D20 | Mestre-detalhe em 3 padrões, sem URL do registro | Compras |
| D21 | Ajustes em 3 padrões (abas em páginas, diálogo, página) | PDV, Cozinha, Produção |
| D22 | Largura do conteúdo em 4 medidas | Marketing |

**Baixa:** `>` solto no pé do modo operacional do Kitchen Sink; sino some do pé da lateral em
Catálogo e Canais; selo duplicado na Central no celular; Kitchen Sink com selo de `variant`
escrito e botão `lg`. Ficam com a onda de cada app.

**Fora desta fase, registrado:** o cartão de ação do Storefront cobre o rodapé da loja no
fim da sacola e do produto (a reserva mora só no `<main>`). A copy rejeitada pelo dono no
#1557 ("Atualiza a cada 30 s" e outras) segue no ar até ele escolher.

## 4. Mapa "atividade comum → peça do kit"

| atividade | peça | estado | base Nuxt UI 4.11.3 |
|---|---|---|---|
| A1 ver a fila | `QueueColumnStrip` (colunas), `OperatorSplitter` (lista + detalhe), `OperatorTable` (lista) | fila e splitter existem; tabela **a criar (K1)** | `UTable`, `UDashboardPanel` |
| A2 buscar | `OperatorSuiteSearch` com nível declarado (`scope="screen"` diz "filtrando…" no campo) | existe; o nível declarado **a criar (K6)** | `UCommandPalette` em `UModal` |
| A3 recortar rápido | `OperatorQuickFilters` na toolbar esquerda: abas com contagem, os favoritos fixados no fim | **a criar (K4)**; aposenta `UiFilterChip`/`UiToggleChip` | `UTabs` (`variant="pill"`), `UButton active` |
| A4 sub-seção | a mesma faixa de A3 (o dono: "filtros rápidos = navegação secundária"), com `to` em vez de `v-model`; e a sub-seção como filha na barra lateral | **a criar (K4)** | `UTabs` com `to`; `UNavigationMenu` com `children` |
| A5 filtrar completo | `FilterBar` refeita sobre `UCommandPalette` com `children` + `OperatorSavedFilters` (Favoritos) + `SavedView` no servidor | FilterBar existe; favoritos **a criar (K4)** | `UCommandPalette` em `UPopover`; `UDrawer` no celular; `UDropdownMenu` |
| A6 data e período | `OperatorPeriodPicker`; o `date-range` da `FilterBar` passa a usá-lo | existe | `UPopover` + `UTabs` + `UiDateField` (decisão do dono) |
| A7 tabela | `OperatorTable`: ordenar no cabeçalho, busca integrada, linha expansível, seleção, colunas (`column-visibility`), densidade, coluna fixada que cabe no celular, célula que quebra | **a criar (K1)**; aposenta o estado próprio do `ColumnPicker` | `UTable` (TanStack): `sorting`, `global-filter`, `expanded`, `row-selection`, `column-visibility`, `column-pinning`, `sticky` |
| A8 agir em vários | `OperatorBulkBar`: "N selecionados", ações, "Limpar seleção" | **a criar (K2)** | `UTable row-selection` + `OperatorToolbar` |
| A9 anterior/próximo | `OperatorRecordNav`: ‹ 3 de 18 ›, teclas J/K, segue a lista de onde a pessoa veio (com o recorte) | **a criar (K5)** | `UFieldGroup` + `UButton` + `UKbd` |
| A10 ação no celular | `OperatorActionBar`: contexto (rótulo + valor) + UMA ação `xl` + o motivo quando não pode | **a criar (K3)** | `UDashboardPanel #footer` + `UDashboardToolbar as="footer"` |
| A11 deslizar | `SwipeReveal` promovido ao kit | existe no Gestor; **promover (K8)** | composição própria |
| A12 aviso da tela | `alerts` do `OperatorPageHeader` (lugar declarado, `NuxtAlert subtle`) | **a criar (K6)** | `UAlert` |
| A13 estado da tela | `OperatorScreenState` (carregando, vazio, erro, sem conexão), uma redação por estado | **a criar (K7)**; aposenta `BiPageState` | `UEmpty`, `UAlert`, `USkeleton` |
| A14 mais ações | o ⋯ do `OperatorPageHeader` (`actions` como dados) e o MESMO formato no ⋯ da linha da tabela | existe no cabeçalho; **na linha (K1)** | `UDropdownMenu` |
| A15 atualizar | item "Atualizar" nas `actions` (tecla R), nunca na toolbar | regra (seção 5) | — |

## 5. Os papéis das barras

Uma barra, um papel. Vale para todo app; a ordem é de cima para baixo.

| faixa | papel | o que mora | o que nunca mora | celular (abaixo de `sm`) | mesa |
|---|---|---|---|---|---|
| **Barra superior primária** (`OperatorPageHeader`, navbar) | onde estou e o que faço com a tela inteira | ☰ (ou o ciclo da barra lateral), título, Busca, Avisos, ação primária da tela (`solid`), ⋯ Mais ações | filtros, abas, período, frescor | ☰ + título (até 2 linhas) + 2 ícones + ⋯; estado na 2ª linha | título, busca de 22 rem, ação primária, ⋯ |
| **Barra superior secundária** (toolbar do header) | o recorte da lista | esquerda: filtros rápidos e sub-seções (A3/A4), favoritos fixados; direita: período, Filtros (n), Favoritos, Colunas e densidade (só com tabela); fim: contagem e frescor | ação ("Atualizar", "Admin", "Exportar") | 1 linha: até 2 primários + "Filtros (n)"; chips ativos rolam abaixo | 1 linha; quebra antes de espremer, nunca 2ª toolbar |
| **Barra de seleção** (`OperatorBulkBar`) | agir nos marcados | "N selecionados", as ações em lote, "Limpar seleção" | filtros | vira a ação na base enquanto houver seleção | ocupa o lugar da toolbar enquanto houver seleção (pergunta 3) |
| **Aviso da tela** (`alerts`) | o que a tela precisa que a pessoa saiba agora | 1 `NuxtAlert subtle`; o 2º e seguintes dizem "e mais N" | erro de rede (é o `OfflineBanner`), aviso com prazo (é o `OperatorUrgentAlert`) | abaixo da toolbar, rola com o conteúdo | idem |
| **Conteúdo** | o trabalho | lista, tabela, cartões, detalhe | barras grudadas próprias | — | — |
| **Ação na base** (`OperatorActionBar`) | a ação do momento ao alcance do polegar | contexto + 1 ação `xl` + motivo | navegação, segunda ação de mesmo peso | em fluxo entre o conteúdo e a barra inferior; some com o teclado | não existe: a ação sobe para a barra primária |
| **Barra inferior** (`OperatorQuickBar`) | menu rápido do app | 3 a 5 seções | ação, filtro | sim | não existe (a barra lateral está na tela) |
| **Faixas do app** | o que vale para o app inteiro | `OfflineBanner` (topo), `OperatorUrgentAlert` (modal com prazo), Avisos (caixa) | aviso de uma tela só | — | — |

Regras que saem da tabela:

- **Nenhuma barra grudada fora destas.** "Barrinha extra" é sinal de papel sem dono:
  ou ela é aviso da tela, ou recorte (toolbar), ou ação (primária ou base).
- **Filtro rápido e sub-seção dividem a mesma faixa.** Com até 4 opções, rolam no celular;
  com mais, viram `NuxtSelect`. Uma sub-seção muda a URL (`to`); um recorte muda a query.
- **Busca em níveis, com o nível dito.** A busca da barra primária é sempre a da suíte. A
  tela que filtra a própria lista declara `scope="screen"`: o campo diz "Filtrando pedidos",
  e Tab troca para App e Toda a suíte. Nada de duas buscas visíveis juntas.
- **Uma régua de largura, a mesma no servidor e no cliente** (K0): estrutura que muda com a
  largura se resolve em CSS (`max-sm:hidden`, `lg:hidden`), não em `v-if` de media query. A
  régua em JS serve a comportamento (atalho, gesto), lida depois de montar, e recebe a
  largura do último acesso por cookie para o servidor desenhar certo.

## 6. As peças a construir

Cada peça nasce no `operator-kit`, entra no Kitchen Sink no MESMO PR, ganha teste de
componente montado com o Nuxt UI real e o `:ui` mora uma vez no tema ou na peça, nunca na tela.

| peça | contrato (resumo) | substitui |
|---|---|---|
| **K0 `useSuiteBreakpoints`** | réguas únicas `sm` 640 e `lg` 1024; `ssrWidth` do cookie `op-vw` (gravado pelo cliente); `mounted` antes de qualquer decisão de árvore | 10 `useMediaQuery` do Gestor e os dos outros apps; causa de D1 e D2 |
| **K1 `OperatorTable`** | `columns` com `sortable`, `hideable`, `pinned`; `v-model:sorting`, `v-model:selection`, `v-model:expanded`, `v-model:columns`; `density` (`comfortable`/`compact`, pergunta 1); `search` (o `global-filter`, ligado ao `#search` da tela); `row-actions` (o mesmo formato das `actions`); célula de texto da casa quebra, nunca corta; coluna fixada cabe no celular; `empty`/`loading` pelo `OperatorScreenState` | as tabelas montadas por tela, `<table>` crus, o estado próprio do `ColumnPicker` |
| **K2 `OperatorBulkBar`** | aparece com seleção; "N selecionados"; ações como dados (a primeira `solid`); "Limpar seleção"; Esc limpa; na mesa no lugar da toolbar, no celular como ação na base | as barras de lote do Gestor (topo e pé) |
| **K3 `OperatorActionBar`** | `context` (rótulo + valor), `action` (rótulo, `loading`, `disabled`, `reason`), `secondary` opcional (`ghost`); slot `#footer` do `OperatorSuiteShell`, em fluxo, `data-focus-obstruction`, área segura, some com o teclado, só abaixo de `lg` | as 8 barras à mão (D8) |
| **K4 Filtros** | `OperatorQuickFilters` (abas com contagem, `v-model` ou `to`, favoritos fixados no fim); `FilterBar` sobre `UCommandPalette` (busca e teclado de graça); `OperatorSavedFilters` ("Favoritos": salvar o recorte atual com nome, fixar como aba, renomear, apagar); `SavedView` no Django (generaliza o `BIView`: dono, superfície, tela, nome, `query`, fixado, e `shared` se a pergunta 2 for "2") | `UiFilterChip`, `UiToggleChip`, pílulas sobre `<select>`, chips `<button>` do PDV, o cartão "Aplicar" da Produção |
| **K5 `OperatorRecordNav`** | ‹ "3 de 18" ›, J/K; `useRecordTrail(key)` guarda a ordem e o recorte da lista de origem (sessão do navegador), e o detalhe sem trilha não mostra o par | só o "voltar" (Gestor, PDV, Produção, Marketing); o ‹ › do Recebimento do Compras |
| **K6 Cabeçalho** | `alerts` (lugar do aviso da tela); `search-scope`; variante `task` para tela de corredor (Fim do dia, Relatório X/Z, Letreiro: título, estado, "Sair") | faixas à mão; os 2 cabeçalhos extras do PDV |
| **K7 `OperatorScreenState`** | `loading`, `empty`, `error` (com "Tentar de novo"), `offline` ("Sem conexão. O que está na tela é de {hora}."); uma redação por estado | `BiPageState`, faixas à mão |
| **K8 `SwipeReveal`** | o do Gestor, sem mudança de gesto; ações como dados; só toque | a cópia que nasceria em cada app |

## 7. O que é legítimo do PDV (carta branca)

- A **barra de contexto da venda** (cliente, recebimento, Quando, F6/F7/F8) no lugar da
  toolbar enquanto a comanda está aberta.
- As **teclas de função** (F2, F6 a F8) e o toque crítico `xl` com campos de 48 px.
- A **comanda como folha de baixo** no celular e no tablet em pé.
- A **Tela do cliente** em shell próprio, sem barra lateral.
- O **corredor de Fim do dia** sem navegação (cabeçalho `task`, K6).
- A busca `hotkey` (o `/` é do campo do produto e do "cliente veio buscar").

O que não é carta branca e entra no padrão: três cabeçalhos (vira um, mais o `task`), ⋯ da
comanda em `UiPopover` (vira `actions`), `PosSearchField` (vira a busca da suíte), chips do
celular em `<button>` (viram `OperatorQuickFilters`), barras de base à mão (viram
`OperatorActionBar`), `UiNativeSelect` (viram `NuxtSelect`/`NuxtSelectMenu`), a navegação
remontada em cada página (vira layout).

## 8. Fatiamento em PRs

Regra herdada do WP-OPERADOR-NUXTUI-ONDAS: **PR de kit é serial** (uma sessão por vez em
`surfaces/operator-kit`); **PR de app é paralelo** (uma sessão por app). O app nunca copia a
peça: espera o PR de kit e empilha sobre ele.

**Kit (serial, nesta ordem)**

| PR | conteúdo | depende de | trava nova |
|---|---|---|---|
| K0 | `useSuiteBreakpoints` + cookie de largura; o Gestor troca as 10 réguas | a frente urgente do Gestor (D1) | e2e por app que reprova "Hydration" no console com carga direta a 390 |
| K1 | `OperatorTable` | K0; pergunta 1 | teste montado: ordenar, selecionar, expandir, esconder coluna, densidade; texto da casa não corta a 390 |
| K2 | `OperatorBulkBar` | K1, K3; pergunta 3 | a seleção nunca empurra a lista; Esc limpa |
| K3 | `OperatorActionBar` + `#footer` do shell | K0 | nenhuma barra grudada em `app/` dos apps (guard por regex de `sticky bottom`/`fixed bottom`, teto que só cai) |
| K4 | `OperatorQuickFilters`, `FilterBar` sobre CommandPalette, `OperatorSavedFilters`, `SavedView` (Django, migração no `backstage`) | K0; pergunta 2 | ida e volta da URL com favorito; teto de `UiFilterChip` que só cai |
| K5 | `OperatorRecordNav` + `useRecordTrail` | — | a trilha respeita o recorte; sem trilha, sem par |
| K6 | cabeçalho: `alerts`, `search-scope`, variante `task` | K7 | 1 aviso visível, os outros em "e mais N" |
| K7 | `OperatorScreenState` | — | uma redação por estado (vocabulário §2.3) |
| K8 | `SwipeReveal` no kit | — | o Gestor importa do kit; teste do gesto sobe junto |

K5, K7 e K8 independem e podem entrar em qualquer ordem entre os outros, ainda um por vez.

**Apps (paralelos entre si, cada um sobre os PRs de kit de que depende)**

| ordem | app | o que recebe | depende de |
|---|---|---|---|
| 1 | Gestor | K1 nas 5 tabelas, K2 (uma barra), K4 (Histórico, Catálogo, Clientes), K5 (pedido e cliente), K3 (pedido), K6 (aviso "sem vocação" no lugar), ações saem da toolbar | K0 a K6 |
| 2 | B.I. | K1 nas 21 tabelas (ordenar), K4 (veredito como recorte rápido; favoritos do Explorar migram de `BIView` para `SavedView`), K7, K3 ("Levar ao plano") | K1, K3, K4, K7 |
| 3 | Central e Kitchen Sink | a Central no shell (variante "início"); o Kitchen Sink mostra o shell de referência e as peças | K0, K6 |
| 4 | Compras | entra no shell; Base vira sub-seções com rota; K1 nas 4 tabelas; K3 (Receber); K5 (item, insumo); harness visual | K0 a K5 |
| 5 | Marketing | entra no shell; Ajustes como sub-seção; K1 (Campanhas); K4 (Enviados com período); K3 (Revisão); ⋯ único | K0 a K6 |
| 6 | Produção | entra no shell; K1 nas 14 tabelas (Plano agrupado); K4 (Relatórios sem "Aplicar"); K5 (receita, lote); busca com nível; harness visual | K0 a K7 |
| 7 | Cozinha | entra no shell; K3 ("Pronto"); avisos (Visto, cancelamento) no `alerts`; K8 (deslizar para Pronto, pela decisão F7); harness visual | K3, K6, K8 |
| 8 | PDV | por último, com tudo provado; a carta branca da seção 7 | todos |

Cada PR de app traz captura antes e depois a 390, 768 e 1440 (claro e escuro), a CI do app
e dos vizinhos, e diz o que não foi visto. A ordem dos apps segue a do WP-OPERADOR-NUXTUI-ONDAS
(risco, uso no balcão, dependência do kit), com o Gestor primeiro porque já está no shell e
é onde a dor da tabela e da seleção foi medida.

## 9. Perguntas ao dono (respondidas em 09/10)

Respostas do dono à rodada 1: **(1) densidade: a compacta é o padrão**, Confortável fica
como alternância guardada por dispositivo, e a linha expandida aberta não compacta;
**(2) favoritos: opção 2** (por pessoa, e o gerente publica para a equipe), podendo nascer
pela 1; **(3) barra de seleção: opção 1**. O texto original das perguntas segue abaixo
como registro; a rodada 2 (seção 10) já desenha as respostas.

1. **Densidade da tabela.** (1) Um botão "Compacta / Confortável" na tabela, guardado por
   dispositivo; (2) compacta sozinha do `lg` para cima, sem botão. Recomendo **1**: a mesma
   mesa serve ao gestor e ao balcão, e o tablet de toque precisa da confortável.
2. **Favoritos de filtro.** (1) Cada pessoa tem os seus; (2) cada pessoa tem os seus, e o
   gerente pode publicar um para a equipe. Recomendo **1** agora: o modelo já é por pessoa
   (o `BIView`), e o "publicar" entra depois sem refazer nada.
3. **Barra de seleção na mesa.** (1) Ocupa o lugar da toolbar enquanto houver marcados (o
   olho já está ali); (2) fica na base, como no celular. Recomendo **1**.

## 10. Rodada 2: o que mudou e por quê

O dono viu a rodada 1 (09/10), respondeu as perguntas, fez onze observações e pediu para
**estressar as peças juntas**. A página `/proposal/fase2` passou a mostrar as mudanças peça
a peça e leva a quatro telas compostas em `/proposal/fase2/<tela>` (`fila`, `historico`,
`compras`, `pdv`), em tela cheia, com o shell real da suíte (`OperatorSuiteShell`: barra
lateral na mesa, gaveta e barra inferior abaixo de `lg`). A mesma rota é o celular e a
mesa: o arranjo muda por CSS, como pede a régua única (K0). `?estado=` escolhe a situação
(`livre`, `filtros`, `busca`, `selecao`, `detalhe`, `vazio`, `erro`, `comanda`).

| # | observação do dono | o que mudou | peça |
|---|---|---|---|
| 1 | "Ao vivo · 10:42" no celular é SELO | `NuxtBadge` ao lado do título (verde ao vivo, âmbar reconectando, vermelho sem conexão); sem espaço, desce para a linha de baixo antes de espremer o título | K6 |
| 2 | botão de filtro só com ícone, com contagem | no celular, só o ícone, com o número no canto (`NuxtChip` `4xl`, o chip numerado do tema); na mesa, ícone + "Filtros" + o mesmo número | K4 |
| 3 | busca em níveis no canônico | `NuxtDashboardSearchButton` + `NuxtDashboardSearch` oficiais; os níveis são os GRUPOS da paleta em ordem fixa (`preserve-group-order`): Nesta tela, No app, Na suíte. "Filtrar a fila por …" vira um recorte (chip). Sem `NuxtTabs` nem `NuxtModal` próprios: o `OperatorSuiteSearch` passa a ser uma camada fina sobre o `DashboardSearch` | K6 |
| 4 | filtro repensado, igual no celular e na mesa, favoritos primeiro (Odoo) | UM painel sobre `NuxtCommandPalette`: **Favoritos** (os seus, depois os da equipe com o sufixo "Equipe") → **Filtros rápidos** (somam: OU) → **Data** → **Agrupar por** (só onde a tela agrupa) → **Filtros completos** (cada campo abre a lista dele, `children`; entre grupos, E) e no pé **Salvar como favorito**. Digitar oferece "Cliente contém …" (o "Search Customer for" do Odoo). Contêiner: `NuxtDrawer` de baixo no celular (pé: Limpar + "Ver 7 pedidos"), `NuxtPopover` na mesa (pé: Limpar + Salvar). O diálogo de salvar mora FORA do contêiner e já traz "Mostrar nos filtros rápidos da tela" e "Publicar para a equipe" (só gerente; pode nascer depois) | K4 |
| 5 | tabela compacta por padrão; a linha aberta não compacta | compacta é o padrão (`px-2 py-1`); Confortável e as colunas moram num botão só, **Exibir** (ícone), guardado no dispositivo (`localStorage`, lido depois de montar); o conteúdo aberto ganha o respiro da confortável (`px-4 py-3` no total) | K1 |
| 6 | campo de busca da tabela menor, com padding | o campo saiu da borda da tabela para a toolbar da tela (13 rem, com folga), com o rótulo "Filtrar estes pedidos"; a tabela entra no cartão sem barra própria | K1 |
| 7 | barra de seleção no lugar da barra de filtros | na mesa ela troca a toolbar inteira e diz em que recorte a seleção foi feita ("em iFood atrasados · R$ 171,50"); no celular ela é a ação flutuante | K2 |
| 8 | copy de estado | "Nenhum pedido precisa de você agora." · "Não foi possível carregar a fila" · "Sem conexão. O que está na tela é de 10:42." · "Nenhum pedido neste recorte." · "Carregando a fila." | K7 |
| 9 | ação na base com mais contraste, flutuante, escura | flutua 12 px acima da barra inferior, superfície invertida (a tinta do texto: escura no tema claro, creme no escuro), botão claro (`neutral` `solid` com os tokens redefinidos SÓ dentro da barra, o recurso do rail dourado); o conteúdo reserva a altura MEDIDA da barra | K3 |
| 10 | cartões sem destaque de cabeçalho e rodapé | cartão de pedido em bloco único, 12 px de respiro; cabeçalho e rodapé só onde separam algo de fato (a comanda do PDV tem título porque é uma coluna própria) | regra do kit |
| 11 | altura de campo = altura de botão | campo, lista de escolha e botão na altura `md` (32 px na mesa); o degrau `xl` (48 px) vale para os dois juntos, no toque crítico. A página da proposta deixou de vestir o marcador do catálogo (`data-operator-catalog`), que sobe campo e lista para 44 px: no kit, o `suite-page:h-control` do `input`/`select`/`selectMenu` `md` sai junto com a migração de cada app | tema do kit |

Duas mudanças que as telas compostas forçaram, além das observações:

- **O detalhe na mesa DIVIDE a tela, não cobre.** Na rodada 1 o anterior/próximo vivia
  num cartão; na tela composta, o primeiro desenho (um `Slideover` não modal) cobria as
  colunas da direita e os botões da barra de seleção. Agora o detalhe é uma coluna de
  24 rem ao lado da tabela, e a tabela solta Canal e Pagamento enquanto ele está aberto.
  Abaixo de `lg`, o detalhe é a tela inteira (`Slideover`).
- **Período nas listas mora no painel.** No Histórico a 1440 com a barra lateral aberta,
  campo + quatro abas + seletor de período + Filtros + Exibir + contagem não couberam numa
  linha (o último controle saía cortado). O seletor de período com setas fica para as
  telas de leitura por período (B.I., Fechamento); nas listas, a data é um grupo do
  painel e aparece como chip quando sai do padrão. A contagem de tabela foi para o pé
  da tabela.

## 11. Regras de precedência

O que as quatro telas compostas revelaram quando as peças disputam o mesmo espaço. Medido a
390×844 e 1440×900 (capturas `fase2-r2-*` no scratchpad da sessão, não versionadas).

**O que NUNCA fica coberto nem some**

1. O **título** da tela: quebra em linhas, nunca corta, nunca cede lugar a selo ou ícone.
2. O **fim do conteúdo**: a ação flutuante reserva a própria altura medida + 24 px; o
   último item fica visível acima dela (medido: 20 px livres na Fila e no Histórico, 40 no
   PDV).
3. O botão **Filtros** com o número de recortes: é o último a sair da toolbar, nunca sai.
4. O **recorte ativo**: se os chips não cabem, eles descem para uma faixa própria (celular
   e mesa estreita); a barra de seleção, quando toma a toolbar, escreve o recorte por
   extenso ("em …"); o detalhe do registro também ("em iFood atrasados", acima do "3 de 24").
5. A **barra inferior** do celular: nada flutua sobre ela; a ação flutua 12 px acima.
6. Na mesa, as **ações da seleção**: nenhum painel lateral as cobre (por isso o detalhe
   divide a tela).

**Quem cobre o quê (a pilha, de cima para baixo)**

1. Aviso com prazo (`OperatorUrgentAlert`, modal): o único que cobre tudo.
2. Diálogos e folhas pedidos pela pessoa (busca, painel de filtros, salvar favorito,
   comanda): cobrem a tela, e só enquanto abertos.
3. Ação flutuante: cobre o conteúdo que rola por baixo, nunca as barras e nunca o fim
   (regra 2 acima). Some com o teclado aberto e não existe do `lg` para cima.
4. Cabeçalho de grupo grudado (lista agrupada): gruda sob a toolbar, acima dos itens.

**Quem cede, em ordem, quando falta largura**

- *Barra superior primária, celular:* ☰ + título + selo + 2 ícones + ⋯. Cedem nesta ordem:
  o selo desce para a 2ª linha; a ação primária da tela vai para o ⋯ (entra no topo dele);
  a busca vira só a lupa; Avisos fica (é um dos 2 ícones). Nada mais entra na barra.
- *Barra superior primária, mesa:* título + selo, busca (14 rem, `/`), ação primária, ⋯.
  Avisos mora na barra lateral.
- *Toolbar, celular:* UMA linha: a faixa esquerda (recortes ou sub-seções) e o ícone de
  Filtros, fixo à direita. Os chips dos recortes ativos descem para uma faixa rolável
  logo abaixo. A contagem sai (o painel diz "Ver 7 pedidos"). Sub-seção (navegação) com
  mais de 3 opções vira `NuxtSelect` (medido: a 390 cabem 2 abas e meia com contagem ao
  lado do ícone); recorte rola. Favorito fixado não vira aba no celular quando já não
  cabem as abas: ele está no topo do painel.
- *Toolbar, mesa:* [campo "Filtrar estes …" só em tela de tabela] [abas] [chips] … [Filtros]
  [Exibir, só ícone] [contagem, só em tela sem tabela]. Cedem nesta ordem: a contagem (vai
  para o pé da tabela); os chips (descem para a faixa própria abaixo de `xl`); o rótulo de
  Exibir (já é só ícone); por fim a linha QUEBRA (`flex-wrap`), nunca corta e nunca vira
  segunda toolbar.
- *Tabela, celular:* ficam a seleção, a coluna-chave (Pedido), o texto da casa (Cliente,
  quebrando) e o valor; as colunas de apoio somem por CSS (`max-sm:hidden` no
  `meta.class` da coluna) e a seta de abrir dá lugar ao toque na linha.
- *Tabela, mesa com detalhe aberto:* a tabela encolhe e solta as colunas de apoio (Canal,
  Pagamento) antes de rolar na horizontal.

**Quem vai para o ⋯ e quem vai para o painel**

- ⋯ "Mais ações": tudo que AGE sobre a tela inteira e não é a ação primária: Atualizar (R),
  Exportar, Imprimir, a ação primária no celular, a busca da suíte no PDV.
- Painel de filtros: tudo que RECORTA: favoritos, filtros rápidos que não cabem como aba,
  data (nas listas), agrupar por, filtros completos, salvar favorito.
- Botão Exibir: o que muda a FORMA da tabela (densidade, colunas). Nunca no painel de
  filtros, porque não muda o que aparece, só como.

**Quem troca de lugar com quem (nunca os dois juntos)**

- Seleção ⇄ toolbar (mesa): com marcados, a barra de seleção ocupa a toolbar. Enquanto
  houver marcados o recorte não muda: mudar o recorte com marcados fora da vista seria agir
  no que não se vê. Limpar a seleção devolve a toolbar.
- Seleção ⇄ ação do momento (celular): a ação flutuante mostra a seleção quando há
  marcados ("Aceitar 3"); sem marcados, a ação do momento ("Aceitar o 1051").
- Aba de favorito fixado ⇄ chip do favorito: com a aba ativa, o chip não se repete.
- Aviso da tela: UM `NuxtAlert`; o 2º em diante vira "Mais N avisos" na própria ação do
  aviso (o resto mora na caixa de Avisos).

**Carta branca do PDV, confirmada na tela composta**

- A barra da venda (cliente, recebimento F6, quando F7, desconto F8) toma a toolbar
  enquanto há comanda; o campo de produto (`/`) ocupa uma 2ª linha da toolbar. É a única
  toolbar de duas linhas da suíte: no balcão a busca de produto é o gesto principal.
- Na mesa a comanda é uma coluna fixa à direita com "Receber R$ 49,70" `xl` e F2; a ação
  não sobe para a barra do topo.
- No celular a comanda é a ação flutuante (total + Receber) e abre como folha de baixo
  ("Ver comanda"). A busca da suíte vai para o ⋯.

## 12. O que não foi verificado

- O build de produção (os laudos mediram `nuxt dev`); D1 e D2 pedem confirmação lá.
- A venda do PDV cheia e o fechamento com dados (o mock devolve `tabs: []`).
- O Storefront com teclado aberto (o comportamento descrito vem do código).
- Captura com teclado físico e leitor de tela das peças propostas: a página da proposta é
  material de decisão, não peça pronta.
