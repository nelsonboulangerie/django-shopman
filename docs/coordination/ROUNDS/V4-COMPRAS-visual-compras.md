# V4-COMPRAS: o app de Compras igual à v4

- **id:** V4-COMPRAS
- **branch:** claude/v4-compras
- **PR:** (a abrir)
- **estado:** em execução
- **início (UTC):** 2026-10-04

## Objetivo
Onda V4 (ordem do dono, 04/10: "quero tudo igual a v4"). O Compras
(`surfaces/purchase-nuxt`) veste a camada visual da suíte (`data-suite="v3"`, rail da
suíte, cabeçalho de uma linha, barra do polegar), no modelo do Gestor (#1448/#1451), e
as telas ficam iguais às prévias: `v4/compras-validade.jpg` (recebimento por exceção no
celular) e, onde a v4 não redesenhou, as v3 `purchase-base3.html`,
`purchase-receive-phone3.html` e `purchase-receive-tablet3.html`.

Função não regride. A regra do pedido de compra não muda (o PR #1418, de outra sessão,
mexe nela; este diff fica disjunto do dele onde dá).
