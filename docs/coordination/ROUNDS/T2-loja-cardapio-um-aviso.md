# T2 — Loja: um só aviso no cardápio

- **id:** T2
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; frentes T1 a T5 executadas por subagentes em worktree próprio)
- **branch:** claude/loja-cardapio-um-aviso
- **PR:** #1381
- **estado final:** na fila #1381 (`gh-readonly-queue/main/pr-1381-…` às 16:55 UTC)
- **início / fim (UTC):** 2026-10-02 16:33 / 2026-10-02 16:40

## O que mudou
`surfaces/storefront-nuxt/app/pages/menu.vue:66-73` declara ao NavigationFeedback a espera inteira pelo
`usePageContentPending` do #1357 (`pending || (continuumPending && !continuumFailed)`); o card azul
"Confirmando o cardápio" saiu (`menu.vue:571` só mostra a falha, warning + "Tentar de novo").
`usePageContentPending.ts:30,44` ganhou a frase da fase; `NavigationFeedback.vue:18,27,185` mostra
"Confirmando preços e disponibilidade…" no mesmo overlay. `lazy` e limiar de 200 ms intocados.

## Prova
`tests/pages/menuOneNarrator.test.ts` com `continuumCatalogEnabled = true` (como no vivo): contra o
`menu.vue` do main `1 failed | 1 passed` (`data-continuum-catalog-status` existia); com a mudança, junto do
`navigationFeedback.test.ts`, `12 passed`. Typecheck 0, eslint 0. NÃO VERIFICADO no navegador.

## O que ficou de fora
Quem abre o /menu direto pelo endereço (sem navegação interna) não vê mais aviso de confirmação: o overlay
só existe na navegação. Fica o estado pendente de cada produto e a frase para leitor de tela.

## Perguntas ao dono
nada

## Armadilhas novas
O defeito só aparece com `NUXT_PUBLIC_CONTINUUM_CATALOG_ENABLED=true` (vivo); o repositório nasce `false`.

## Próximo passo
Conferir no alpha depois do deploy (desta sessão ou do coordenador).
