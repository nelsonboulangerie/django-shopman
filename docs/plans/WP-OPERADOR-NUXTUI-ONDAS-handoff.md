# WP-OPERADOR-NUXTUI-ONDAS: handoff da sessão que abriu as ondas (08/10/2026)

O plano é o [WP-OPERADOR-NUXTUI-ONDAS.md](WP-OPERADOR-NUXTUI-ONDAS.md). O estado de cada PR está na seção 9, e os prompts das próximas sessões, no [-prompts.md](WP-OPERADOR-NUXTUI-ONDAS-prompts.md).

## Em voo
- **Pilha linear:** #1528 + #1521 → #1531 (0.1) → #1532 (0.1b) → #1534 (0.3) → #1535 (B.I. mock, rascunho) → #1536 (B.I. conteúdo, rascunho). O #1533, da sessão do Gestor, vai sobre o #1534.
- **Combinado com a sessão do Gestor:** mudança de kit é serial e passa por quem coordena a onda 0. A `ActionList` (`orders-nuxt/app/components/ActionList.vue`) sobe ao kit depois do 0.3. Tudo em `orders-nuxt` é dela.
- **Piloto B.I. em revisão, reprovado em tela pelo dono** ("ainda está bem cru"). O #1535 e o #1536 continuam em rascunho e NÃO estão prontos. A crítica e a correção vão para uma sessão nova, que começa olhando as telas, não o código.
- **Nada sai do rascunho sem o dono.** A pilha só entra no `main` depois do #1518 a #1528.

## Próxima peça de kit: 0.2 (guard de slot + marcador de opt-in)
- **Guard:** compilar com `@vue/compiler-dom` cada consumidor das peças do kit e comparar os `<template #x>` passados com os `<slot name>` declarados. O primeiro caso real que ele pega é o `BiDayStepper`, que passa `#trigger` ao `UiDateField`, que não declara esse slot.
- **Marcador:** `app.config` com `operatorKit: { canon, toaster, search }`; `useOperatorKitMode()`; `data-operator-canon` no `<html>`.
  - Hoje o opt-in é `data-suite="v3"`: os 7 apps vestem e o Gestor não. Ele é lido por `useSuiteMarker` (composable do kit) e pela variante CSS `suite-page:`, que alcança os portais.
  - Não ponha `suite:` nem `data-suite` em `.vue` que o Gestor monta: o `canonicalPilot` reprova, e com razão.

## Armadilhas medidas nesta sessão
1. **Builds simultâneos dividem cache.** O Kitchen Sink builda em `node_modules/.cache`. Com duas worktrees e `node_modules` por symlink, os builds se misturam e o retrato sai errado. Rode UM build por vez.
2. **`pkill` não casa caminho relativo.** Servidor subido como `node out/<app>/server/index.mjs` não morre com um padrão que contém o caminho absoluto. Use `pkill -f "node out/.*server/index.mjs"` e confira com `pgrep -fl "node out/"`.
3. **Captura que "mudou 99%" pode ser servidor que caiu.** Leia o JSON da captura (`capture-error: ERR_CONNECTION_REFUSED`) antes de concluir que é regressão.
4. **Capturas do B.I. e de qualquer app com superusuário:** a oferta "Vincular este dispositivo a um posto" cobre a tela. O harness grava `shopman.stationSetup.dismissed=1` no `localStorage`.
5. **Cada app tem a sua chave de tema:** `<app>-color-mode` (o PDV usa `nuxt-color-mode`). Sem isso, o "escuro" sai claro.
6. **Trava que recorta o `app.config` por posição.** A trava do Card lê do `card:` até "// Altura de controle". Bloco novo no meio dela é lido como pele de card.
7. **`heredoc` sem aspas no zsh executa crases.** Texto com `código` vira comando. Use `<<'EOF'`.
8. **Testes do PDV com "Hook timed out"** em máquina carregada: não é defeito. Rode sozinho com `--maxWorkers=2`.
9. **A porta 38794 é do mock de outra sessão do Gestor.** O B.I. usa 38995 e 38996 nas capturas.

## Comandos
```bash
# vitest de um projeto (kit ou app)
cd surfaces/<proj> && npx vitest run
# captura antes/depois (uma worktree por lado; a de "antes" com node_modules por symlink)
node surfaces/operator-kit/visual/capture-before-after.mjs <raiz-worktree> <app> <antes|depois> <porta-app> <porta-mock> <saída>
python3 surfaces/operator-kit/visual/capture-diff.py <saída>
# matriz do Kitchen Sink (Chromium 1243 = o da trava da CI)
cd surfaces/kitchensink-nuxt && npx playwright test -c playwright.visual.config.ts --reporter=line
# ledger e versões
python3 scripts/check_operator_component_ledger.py && python3 scripts/check_surface_versions.py
```

## Prévia local dos 9 apps com Django
- Banco local novo (`createdb <nome-único>`), `migrate` e `seed --flush`, com `DATABASE_URL`, `DJANGO_DEBUG=true` e `PYTHONPATH="<worktree>:<worktree>/packages/*"`. Depois `runserver 127.0.0.1:8899`.
- Cada app: `nuxt build` e `node .output/server/index.mjs` na porta de dev (3001 a 3009), com `NUXT_DJANGO_BASE_URL=http://127.0.0.1:8899`, `SHOPMAN_ENVIRONMENT=test` e `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1`.
- O login vale para todos os apps, porque o cookie de 127.0.0.1 não depende da porta. A Central lista os apps nas portas de dev (`projections/hub.py`).
- Copie os `.output` para uma pasta própria antes de servir: o próximo build sobrescreve.

## Gravar fixtures do seed (mock de app novo)
O molde é `surfaces/bi-nuxt/tests/visual/README.md` e `recordProxy.mjs`:
1. Crie um proxy entre o app e o Django, com a sessão de superusuário.
2. Percorra as telas com o Playwright.
3. Encerre com SIGTERM para gravar.

O mock casa por caminho com query e, sem ela, só pelo caminho.
