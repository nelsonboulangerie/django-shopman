# UX-G1 — Gestor: colunas ajustáveis e recolhíveis, lembradas por posto

- **id:** UX-G1
- **branch:** claude/ux-g1-colunas-gestor
- **PR:** #1406
- **estado final:** pronto, na fila
- **início (UTC):** 2026-10-03

## Objetivo
SUITE-UX-FUNCTION-PLAN §16 e lei L7: as colunas Entrada, Preparo e Saída do quadro do Gestor
(`surfaces/orders-nuxt`) passam a ser ajustáveis (largura) e recolhíveis numa faixa estreita com
nome, contagem, ponto de urgência e gatilho para reabrir; teclas 1/2/3 no desktop; "Mostrar as 3
colunas"; a arrumação fica lembrada por posto/dispositivo no servidor. Regras de negócio de hoje,
nenhuma ação muda.

## O que mudou
- **Kit (forma FILA)**: `operator-kit/app/presentation/queueColumns.ts` (regras puras: peso por
  coluna aberta, faixa de 56 px, arrastar conserva a soma dos dois pesos, soltar abaixo de 140 px
  recolhe, nunca todas recolhidas, teclas 1 a 9, "Visão: Saída"), `QueueColumnStrip.vue` (faixa
  recolhida: um botão só, chevron de 48 px, contagem, ponto de atrasado/novo, "1 atrasado",
  pulso com `motion-safe`; barra baixa quando as colunas empilham) e `QueueColumnResizeHandle.vue`
  (alça `role=separator`, ponteiro e setas). Contrato no README do kit.
- **Gestor**: `useBoardLayout.ts` (GET/PUT `orders/board-layout/`, grava 600 ms depois do último
  gesto, gesto antes da leitura vence) e `pages/index.vue` (grid por `--board-columns` só no `lg`;
  botão "Recolher a coluna X" no cabeçalho, para o tablet sem teclado; faixa da Entrada pulsa com o
  aviso de pedido novo que já existia, o som continua; teclas 1/2/3 só no modo colunas, fora de
  campo de texto e de diálogo aberto; "Visão: Saída" e "Mostrar as 3 colunas" na barra quando há
  coluna recolhida). Abaixo do `lg` o quadro continua empilhado; a recolhida vira barra baixa.
- **Backstage**: `services/order_board_layout.py` + `OrderBoardLayoutView`
  (`/api/v1/backstage/orders/board-layout/`, `shop.manage_orders`, antes de `orders/<ref>/`).
  O posto é a estação confiável (`station_trust.station_ref`); a arrumação mora em
  `Terminal.metadata["gestor_board"]` (documentado em `data-schemas.md`), com `select_for_update`
  e sem tocar nas outras chaves. Nenhum modelo, nenhuma migração, nada novo no Core.

## Prova
- `pytest shopman/backstage/tests/test_order_board_layout.py` → 13 passed.
- `pytest test_url_language_gate test_api_perimeter test_station_trust test_vocabulario_de_tela` → 2265 passed.
- `pytest test_order_board_layout test_station_kinds test_saida_com_maquininha test_api_alerts_surface` → 68 passed.
- orders-nuxt: `npx vitest run` → 49 arquivos, 505 passed; `npx nuxi typecheck` exit 0; `eslint .` 0 erros (2 avisos antigos em `catalog.vue`).
- operator-kit: `npx vitest run` → 100 arquivos, 1071 passed (inclui guardrails de vocabulário, a11y, cópia que não se corta); `eslint .` limpo.
- `ruff check` limpo nos Python tocados.

## O que ficou de fora
- **Navegador que não é posto** (notebook do gestor sem estação confiável): sem chave no servidor,
  abre com as três colunas e a arrumação vale até recarregar (o título do selo "Visão" diz isso).
  Não criei fallback por pessoa nem `localStorage`: L7 manda o estado ser da casa, e o posto é quem
  decide. Se o dono quiser memória por operador nesse caso, é decisão de produto.
- A chave é por **posto** (`Terminal`), não por `TrustedDevice`: dois tablets no mesmo terminal
  dividem a arrumação, como dividem gaveta e turno (D-007).
- "Esc volta à visão salva" (nota 8 da prévia): o Esc já limpa os filtros no Gestor; não sobrepus.
- "aceita sozinho em 1:10" na faixa da Entrada (prévia): pede o prazo de auto-confirmação na
  projeção da coluna; ficou a contagem + "N atrasado(s)".
- E2E Playwright do Gestor não roda no CI e não foi rodado aqui (sem Chromium da CI).

## Próximo passo
Onda seguinte do piloto do Gestor (Saída única, "pronto" automático, desfazer de 5 s) consome o
mesmo `useBoardLayout` para o posto Saída.
