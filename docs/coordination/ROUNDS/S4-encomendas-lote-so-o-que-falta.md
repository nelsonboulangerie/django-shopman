# S4 — Encomendas: o lote imprime só as vias que faltam (P2)

- **id:** S4
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; subagente em worktree próprio)
- **branch:** claude/encomendas-lote-so-o-que-falta
- **PR:** #1391
- **estado final:** mergeado #1391 (02/10 19:47 UTC)
- **início / fim (UTC):** 2026-10-02 19:00 / 2026-10-02 19:47

## O que mudou
`surfaces/pos-nuxt/app/presentation/preorders.ts:455`: `printPlan` leva só as encomendas sem `ticket_printed`, dentro do visível. `presentation/orderTickets.ts:69`: `printCtaLabel` ("Imprimir 3 vias que faltam"; tudo impresso: desligado, "Todas as vias impressas"). `pages/preorders/index.vue:366`. Reimprimir segue no detalhe.

## Prova
Testes em `tests/pages/preorders.test.ts:591,602,616,189`, `preordersPresentation.test.ts:362`, `orderTickets.test.ts`: 5 reprovavam antes, todos passam depois. PDV 1480 passed; 3 retratos regerados com chromium-1243; CI obrigatória verde.

## O que ficou de fora
nada

## Perguntas ao dono
nada

## Armadilhas novas
nada

## Próximo passo
nada
