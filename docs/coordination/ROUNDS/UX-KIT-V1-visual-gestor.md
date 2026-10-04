# UX-KIT-V1: camada visual da suíte no kit, Gestor como piloto

- **id:** UX-KIT-V1
- **branch:** claude/ux-kit-v1-visual-gestor
- **PR:** #1448 (draft: o dono aprova as capturas antes do merge; sem auto-merge)
- **estado:** esperando o dono (capturas prévia | real)
- **início (UTC):** 2026-10-03

## Objetivo
O sistema real ganha o MESMO look & feel das prévias aprovadas (v3 e v4), que até aqui só
tinham entrado como função. SUITE-UX-FUNCTION-PLAN §12: "a camada visual da v3 (tokens,
rail, cabeçalho, busca) é o rosto das peças". A camada nasce no `surfaces/operator-kit`,
opt-in por app, e veste o Gestor (`surfaces/orders-nuxt`) como piloto. Os outros apps
virão um a um, o PDV por último.

## O que entrou
**Kit (opt-in, nada muda para quem não migrou):**
- `operator-suite.css`: papéis tipográficos de verdade (`op-*`), `tnum`, `live-dot`,
  `pill-*`, o selo âmbar e a variante `suite:` (casa só dentro de `data-suite="v3"`).
- `OperatorSuiteRail` + `RailSection`: o rail de 76px das prévias, com as seções do app.
- `OperatorSectionBar`: a barra do polegar no celular (a do Marketing virou peça da layer;
  o Marketing ainda usa a dele, migra na vez dele).
- `OperatorPageHeader` + `OperatorLiveStatus`: o cabeçalho de uma linha e o ao vivo
  discreto, com a barra de 56px no celular.
- `UiFilterChip`, `UiSearchInput` (tecla ensinada no campo), `UiIconButton`, `ColumnPicker`:
  visual novo atrás de `suite:`. `NotificationBell`: `placement="rail"`.
- `OperatorSection` ganhou `badge`/`badgeLabel` (opcionais).

**Gestor:** `data-suite="v3"`; seções no rail e na barra do polegar (`GestorNav`, que
substitui o `GestorTopBar`); cabeçalho de uma linha em todas as telas (Pedidos, Catálogo,
detalhe, Histórico, Canais, Clientes, Unificações, Postos, revisão de vínculos);
cartão do pedido no desenho `_ocard` (linha fina do canal com o relógio, código grande,
pílulas com ponto, ação larga); cabeça de coluna em versalete; posto Saída com grade de
cartões; celular com Entrada/Preparo/Saída em abas; painel do produto com o cabeçalho da
v4; alertas e avisos no pé do rail (no celular, na barra de 56px).

**Conserto de passagem:** os ícones que moram nas presentations (.ts) e os que chegam da
projeção (ícone do canal) não entravam no pacote do cliente; o navegador ia buscá-los no
api.iconify.design e a CSP do kit recusava (cabeças de coluna e ícones de canal em branco).
Agora a varredura lê .ts e os da projeção entram pelo gancho `icon:clientBundleIcons`.

## Função (não regride)
Nenhuma ação, atalho, permissão, estado ou SSE saiu. Exportar e imprimir foram para o ⋯ da
fila; Atualizar continua à vista. No celular, os controles descem para uma linha que rola.
Colunas recolhíveis (#1406), Saída (#1431), Postos (#1429), desfazer (#1423) e Vocação
(#1407) seguem iguais em comportamento.

## Evidência (saída de comando, 03/10/2026)
- `surfaces/operator-kit`: `npx vitest run` → 105 arquivos, 1140 testes, todos passando
  (inclui `SuiteChrome.test.ts`, 16 testes novos, e as travas de vocabulário e travessão).
- `surfaces/orders-nuxt`: `npx vitest run` → 54 arquivos, 558 testes passando;
  `npx nuxi typecheck` limpo; `npx eslint .` 0 erros (2 avisos de ordem de atributo que
  já existiam no trecho movido das coleções).
- `surfaces/bi-nuxt` (consumidor do kit, sem migrar): `nuxi typecheck` limpo, vitest 58/58.
- e2e do Gestor (Playwright com o Chromium desta máquina, mock backend): 8 de 9 passam
  (board, negociação iFood 375/1280, resiliência, alvos de toque desktop e touch). O
  `ifood.spec.ts` falha por um motivo que já existia no `main`: ele procura no cartão o
  resumo de operação do iFood ("Entrega por entregador iFood"), que o cartão não mostra
  desde que a evidência foi para o detalhe (`git grep ifood_operation_summary origin/main
  -- surfaces/orders-nuxt/app` só acha o detalhe). O passo novo do teste (tocar a lupa
  antes de buscar, no celular) é desta frente. O e2e do Gestor não roda na CI.

## Fora daqui (com nome e motivo)
- A fila "Precisa de você" e "o sistema fez" da v4, a Saída com progresso por estação e o
  nome do cliente no botão: mudam função (trilha de regra).
- Busca da suíte (Esta tela, Gestor, Toda a suíte): recurso novo.
- Detalhe em duas colunas: o corpo é o `OperatorOrderDetail`, compartilhado com o PDV.
- Deslizar o cartão no celular (Atender/Recusar) e o painel Filtros do celular: gesto e
  componente novos.
- Tablet em pé (820 px): as colunas seguem empilhadas (abas só abaixo de 768 px, porque o
  teste de alvos de toque roda a 768 px com as três colunas à vista).

## Prova visual
Página de comparação prévia | real (desktop, tablet deitado e em pé, celular 390 e 320,
claro e escuro): `scratchpad/ux/kit-v1/index.html` da sessão coordenadora, com as imagens
em `kit-v1/img/`. Baselines visuais do orders-nuxt: não existem (só Marketing e PDV têm,
e nenhum dos dois muda).
