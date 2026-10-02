# R1 — Desencalhe do #1367 (comando import_recipe_versions)

- **id:** R1
- **sessão:** coordenacao-pedidos-4f89d4 (desencalhe; o PR é do coordenador noturno de 02/10)
- **branch:** claude/receitas-fx-import
- **PR:** #1367
- **estado final:** na fila #1367 (`gh-readonly-queue/main/pr-1367-…` existia às 16:55 UTC)
- **início / fim (UTC):** 2026-10-02 16:29 / 2026-10-02 16:55

## O que mudou
Rebase sobre `origin/main` (`bddd02693`) e um commit: `shopman/backstage/management/commands/import_recipe_versions.py:60`
importa de `shopman.craftsman.services.recipe_book` (a porta pública, que já reexporta `analyze`,
`classify_ingredient`, `item_grams` etc.; o `shopman/backstage/projections/recipe_book.py` do main
já importa dali) em vez de `shopman.craftsman.contrib.formula.percentages`.

## Prova
`pytest shopman/shop/tests/test_architecture.py shopman/shop/tests/test_import_boundaries.py shopman/backstage/tests/test_import_recipe_versions.py`
no worktree, com PYTHONPATH: `28 passed`. Ruff: `All checks passed!`. Na CI, às 16:55 UTC, o único
vermelho era "Marketing — cadeia completa" (node-forge, D-027, não obrigatório).

## O que ficou de fora
nada

## Perguntas ao dono
nada

## Armadilhas novas
O auto-merge aparece como desligado (`autoMergeRequest: null`) quando o PR já entrou na fila de merge;
`gh pr merge N --auto` responde "already queued to merge". Não é PR largado: confira
`git ls-remote origin 'refs/heads/gh-readonly-queue/*'`.

## Próximo passo
nada (a fila mergeia)
