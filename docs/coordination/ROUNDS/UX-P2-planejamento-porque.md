# UX-P2 · Produção > Planejamento: o número na linha, o porquê por cima

- **id:** UX-P2
- **sessão:** SUITE-UX onda 1 (Claude; executor em worktree próprio)
- **branch:** claude/ux-p2-planejamento-porque
- **PR:** #1419
- **estado final:** na fila #1419 (auto-merge pedido)
- **início / fim (UTC):** 2026-10-03 13:55 / 2026-10-03 14:25

## Objetivo
Cada linha do Planejamento (`surfaces/production-nuxt`) mostra só o número sugerido e, no máximo, um
sinal. Um "Por quê" na linha abre o detalhe ancorado nela, só com dados que o sistema já calcula.
Prévia: `suite-ux-v2/v4/plano-porque.jpg`.

## O que mudou
- **Linha** (`ProductionStageGrid.vue`, lente `plan`): número + no máximo um sinal + "Por quê" (alvo de
  48 px). Nenhuma fórmula na linha. O diálogo antigo "Por que N?" (lista de frases) saiu.
- **Regra do sinal único** (`app/presentation/planningReason.ts`): falta insumo (âmbar, cadeado) >
  acabou cedo (vermelho) > sobra (âmbar). Falta insumo vence porque é o único que muda o que é
  possível (o fechamento recusa pela mesma régua). Acabou cedo = esgotou em metade ou mais dos dias da
  amostra. Sobra = passou do teto de 15% que a fórmula desconta (`SUGGESTION_WASTE_DISCOUNT_THRESHOLD`,
  espelho do passo 6 de `CraftQueries.suggest`).
- **Detalhe** (`PlanReasonCard.vue` dentro do `UiPopover` do app, ancorado na célula; Esc e fora
  fecham, o foco volta ao "Por quê"; a linha fica marcada): a conta `média dos sábados + encomendas +
  margem = sugestão` (a margem carrega segurança, reforço de sexta/sábado e arredondamento, e a nota
  diz quais), o histórico curto ("Acabou antes de fechar em 3 dos 4 sábados usados na conta", "Sobrou
  18% do que vendeu · a média já desconta essa sobra", estação), a falta de insumo ("Manteiga: dá para
  40; faltam 1200 g") com "Pedir no Compras" e a alternativa "Planejar 40 (cabe no estoque)". Sem
  alternativa, a ação é "Planejar N" (abre o planejamento com a sugestão, como antes).
- **Backstage** (Core intocado): `ProductionSuggestionProjection` troca `explanation_parts` (frases)
  pelo basis estruturado (`projected`, `margin`, `safety_percent`, `soldout_days`, `waste_percent`,
  `waste_discounted`, `same_weekday`, `season_label`); `soldout_days` já vinha no basis e não chegava.
  Falta de insumo da sugestão (`material_shortages`, `fits_quantity`) lida antes de planejar pelo mesmo
  `INVENTORY_BACKEND` do guardrail do fechamento, um saldo por insumo para a grade inteira, só em linha
  sem lote na data. `ProductionBoardProjection.purchase_url` (`hub.purchase_surface_url`, mesma
  pergunta do tile do Compras). Contrato regenerado (`export_production_schema`).

## Prova
- `pytest` backstage (vocabulário de tela, export do contrato, superfície da Produção, operacional,
  duas bancadas, adversarial de projeções, explicabilidade, baseline, hub, previsão, guardrail):
  `2397 passed`; depois do merge do `main`: `113 passed` (contrato, explicabilidade, hub, superfície).
- production-nuxt `vitest`: `Test Files 48 passed · Tests 398 passed`; `npm run typecheck` sem erro;
  `eslint .` limpo. operator-kit `vitest tests/` (travas de vocabulário, links entre apps, a11y):
  `Test Files 98 passed · Tests 1049 passed`. `ruff check shopman/backstage` limpo.

## O que ficou de fora (e por quê)
- **Os 4 pontos e a hora** ("acabou às 10:40", um ponto por sábado): o Core calcula o `soldout_at` por
  dia dentro do `suggest()` e descarta; o basis só leva a contagem (`soldout_days`). Expor exigiria
  mudar o basis no Core (`craftsman`), fora do que a frente pode tocar. Ficou a frase com a contagem.
- **"A projeção já soma o que deixou de vender"**: só é verdade quando a loja tem horário configurado
  (`selling_window_for`); a projection não sabe disso por linha. Omitido para não afirmar o que pode
  ser falso.
- **"Pedir no Compras" vai para a home do Compras**, não para o insumo: o `purchase-nuxt` não tem
  rota/consulta de entrada por insumo. "Entrega sex até 16h" (fornecedor/prazo) também não existe
  na leitura do planejamento.
- **Falta de insumo é por linha**: dois produtos que dividem a manteiga não somam (mesma régua do
  guardrail do fechamento e da coluna Saldo da Preparação).
- **Não criado, como o brief manda**: o grupo "+N sem ressalva · Planejar os N como sugerido", o
  stepper editável na linha com primária "Planejar N" e o "você mudou de X · voltar". Nada disso
  existia: a linha hoje planeja pela célula Planejado (diálogo com stepper). São da forma PLANEJAR do
  kit, outra frente. Também ficam para ela os filtros por estado e o cabeçalho com a ocasião e o clima.

## Perguntas ao dono
nada
