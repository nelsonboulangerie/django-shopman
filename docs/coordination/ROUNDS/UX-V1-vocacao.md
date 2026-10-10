# UX-V1 — Vocação no painel do produto do Gestor

- **id:** UX-V1
- **sessão:** reforma SUITE-UX, onda 1 (Claude; executor em worktree próprio)
- **branch:** claude/ux-v1-vocacao
- **PR:** #1407
- **estado final:** na fila (#1407, auto-merge ligado)
- **plano:** `docs/plans/SUITE-UX-FUNCTION-PLAN.md` §13 e §17

## Objetivo
A etiqueta de consumo do produto (`ProductConsumptionTag`, modelo inalterado) ganha campo
"Vocação" na aba "Preço e config" do painel do produto do Gestor (`orders-nuxt`, Catálogo),
dentro do rascunho do painel, e a lista do Catálogo ganha um aviso discreto dos produtos à
venda sem vocação, com "Classificar". Serve ao B.I.; não muda a venda.

## O que mudou
- **Backend (backstage, nada no Core, sem migração):** `services/catalog.py` põe `vocation`
  (ref do papel, "" = sem) e `vocation_choices` (papéis ativos + o desativado ainda em uso)
  no detalhe do produto; o PATCH do painel aceita `vocation` com a mesma permissão
  (`shop.manage_catalog`) e a mesma revisão por campo. Cria a etiqueta `reviewed=True`;
  troca o papel zerando o peso próprio do SKU (volta a herdar do papel novo); "" apaga.
  Vocação sozinha não regrava nem revalida o produto; junto de outro campo, falha de um
  desfaz o outro (mesma transação). Erro: `{detail, field: "vocation"}` (400).
- **Matriz:** `has_vocation` por linha e `vocation_pending` (sku, nome) da loja inteira.
- **Nuxt:** linha "Vocação" (grupo de rádio do kit, escolhas do servidor, nota "só para o
  B.I.", "Deixar sem vocação") na aba Preço e config, no rascunho do "Salvar"; filtro
  "Com vocação"; aviso de uma linha "N produtos à venda sem vocação (nomes) · Classificar",
  que recorta à venda e sem vocação em todas as coleções e abre o primeiro na aba certa.

## Decisões registradas
- **"Sem vocação" = produto com `is_sellable` e sem `ProductConsumptionTag`.** O brief falava
  em "novos"; não há data de criação confiável no critério, e o aviso diz "à venda sem
  vocação" para não ter rótulo que mente. Na prática, com o cardápio curado, só produto novo
  cai aí.
- As escolhas são os **papéis** (`ConsumptionRole`, hoje cinco no seed: Bebida preparada,
  Bebida pronta, Consome aqui, Leva, Híbrido), não as três leituras: é o que a etiqueta grava.

## Prova
- `pytest shopman/backstage/tests/test_catalog_vocacao.py` → 13 passed.
- `pytest test_api_catalog_surface test_catalog_product_intentions test_catalog_patch_preservation
  test_catalog_social_intentions test_gtin_recusado_no_catalogo test_catalog_day1_audit
  test_bi_consumption` → 156 passed, 3 skipped (após ajustar as chaves fixadas do contrato).
- `pytest test_catalog_publication_intentions test_catalog_price_intentions
  test_catalog_cell_concurrency test_catalog_patch_preservation test_bi_room test_backup_api
  test_catalog_vocacao` → 71 passed, 3 skipped.
- `pytest shopman/backstage/tests/test_vocabulario_de_tela.py` → 2231 passed.
- `ruff check` nos .py tocados → All checks passed.
- `orders-nuxt`: `npx vitest run` → 49 files, 509 passed; `npx nuxi typecheck` → exit 0;
  `npx eslint app tests` → 0 erros (2 avisos antigos em `catalog.vue`, não deste PR).
- `operator-kit`: `vitest run tests/guardrails.vocabulary.test.ts` → 6 passed.

## Fora
- Peso por SKU (`eat_in_weight`), observação e o "revisada" de propostas seguem no Admin:
  o painel só escolhe o papel.
