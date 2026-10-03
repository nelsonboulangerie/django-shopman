# UX-C1b — Recebimento: consertos da conferência

- **id:** UX-C1b
- **sessão:** reforma SUITE-UX (Claude, subagente em worktree próprio), conserto do #1409 visto rodando
- **branch:** claude/ux-c1b-recebimento-consertos
- **estado:** em execução
- **início (UTC):** 2026-10-03

## Objetivo
Dois defeitos do recebimento por exceção (`surfaces/purchase-nuxt`):
1. Nota já na unidade base do insumo (ex.: 5 KG) recebia a conversão de embalagem padrão por cima
   ("5.000 × litros = 5.050.000 g").
2. "N de N conferidos" no cabeçalho dos itens com os itens ainda pendentes de validade.
