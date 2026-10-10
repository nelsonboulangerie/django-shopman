# UX-P1b — Produção > Qualidade: não somar gramas com peças

- **id:** UX-P1b
- **branch:** claude/ux-p1b-qualidade-unidades
- **PR:** #1426
- **estado final:** na fila #1426 (auto-merge ligado)
- **início / fim (UTC):** 2026-10-03 15:30 / 2026-10-03 16:05

## Objetivo
Conserto do #1408 visto com o seed Nelson: o cartão do conjunto limpo somava lotes de insumos medidos
em gramas (Yudane 3453.659, Pasta Autolizada 17073.914, Massa Tradição 18480) com produtos contados
em peças ("159648.487 peças"), e os chips mostravam decimal com ponto.

## O que mudou
- **Projeção** (`projections/production.py`): `QCOrderCardProjection.output_unit`, a unidade canônica
  do que o lote produz, pela mesma precedência da ficha (`_recipe_output_units`: Product, depois
  Material, depois `Recipe.meta.output_unit`), em duas consultas para o quiosque inteiro. Contrato
  regenerado (`export_production_schema`). Core intocado, sem migração.
- **`presentation/qualityGate.ts`**: `cleanPieces` (soma cega) morreu. `cleanSummary` agrupa por
  grandeza: "84 peças, todas no padrão" quando só há peças; "312 peças e 39 kg, tudo no padrão" quando
  há lote em peso (kg com 1 casa no total). `quantityMeasure`/`lotQuantityLabel` escrevem cada número
  na unidade do lote, em pt-BR (vírgula, sem milhar): g abaixo de 1000, kg a partir dele; ml/L igual;
  contagem sem unidade no texto corrido e "N peças" no chip. Selo, partição, referência ("Perda típica
  ...: 1,5 por lote", antes "1.5") e a linha dos confirmados (`reviewedSummary`, que saiu do .vue)
  usam a mesma regra.
- **`QualityGatePanel.vue`**: resumo e chips consomem as funções novas.
- Não havia formatador de quantidade com unidade no front da Produção para reaproveitar (o
  `projectedQuantityDisplay` da pesagem só reformata um texto "x kg" que já vem do servidor). A regra
  g→kg segue a do servidor (`_preparation_measure`/`_measure`: vírgula decimal, 3 casas).

## Prova
- `vitest run tests/presentation/qualityGate.test.ts` → `10 passed` (peças e gramas misturadas com o
  caso do seed, só gramas, kg+g+L+peças, singular, vírgula decimal, lote em gramas com perda).
- production-nuxt `vitest run` → `48 files, 394 passed`; `npm run typecheck` sem erro; `eslint .` → 0.
- operator-kit `vitest run tests/` → `101 files, 1095 passed` (inclui a trava de vocabulário).
- `pytest test_qc_quality_batch.py test_production_schema_export.py test_vocabulario_de_tela.py` →
  `2256 passed` (teste novo: cartão de pão vem `un`, de massa vem `g`).
- `pytest test_qc_kiosk test_qc_correction test_api_production_surface test_producao_adversarial_projecoes
  test_production_excellence_baseline test_producao_adversarial_quantidades test_production_operational`
  → `162 passed`. `ruff check` nos dois .py → limpo.

## O que ficou de fora
- **Insumos intermediários no portão** (massas, pré-fermentos, recheios): a regra do servidor inclui
  todo lote fechado do dia, sem filtro de tipo de receita, desde o quiosque de QC (antes do #1408). Não
  achei decisão escrita a favor nem contra (plano SUITE-UX, ADR-017). Como o fechamento do lote de
  preparo também passa pela Expedição, mantive. Se a Qualidade deve olhar só o que vai à vitrine, é
  decisão de produto: a projeção já distingue receita-base (`BaseRecipeOptionProjection`), então o
  filtro seria pequeno.
- Outras telas da Produção que mostram quantidade crua (Expedição/QcCloseScreen) não foram tocadas.
