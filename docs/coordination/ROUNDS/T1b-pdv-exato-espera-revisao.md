# T1b — PDV: o "Exato" espera a revisão do total

- **id:** T1b
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; subagente da T1, em worktree próprio)
- **branch:** claude/pdv-exato-espera-revisao
- **PR:** #1385
- **estado final:** na fila #1385 (auto-merge ligado; CI rodando às 17:40 UTC)
- **início / fim (UTC):** 2026-10-02 16:58 / 2026-10-02 17:35

## O que mudou
O botão "Exato" e a tecla `=` tinham a mesma corrida da T1: ajustavam a linha pelo total antigo
quando o desconto mudava dentro do checkout. `surfaces/pos-nuxt/app/components/PosPaymentWorkspace.vue:1478-1479`
desabilita o "Exato" com o motivo de `awaitingReviewReason()`; `pressExact()` (:1195) é a porta única,
e `pages/index.vue:798` manda a tecla `=` por ela.

## Prova
`tests/components/PosPaymentWorkspace.exactAwaitsReview.test.ts`, sobre o main com o #1380: sem a mudança
`Tests 3 failed (3)` (os dois primeiros pelo defeito; o terceiro só porque `pressExact` não existia); com a
mudança `3 passed`. pos-nuxt inteiro `Tests 1424 passed`; typecheck 0; eslint 0 erros.

## O que ficou de fora
nada

## Perguntas ao dono
nada (o passo 2 é a D42)

## Armadilhas novas
nada

## Próximo passo
nada
