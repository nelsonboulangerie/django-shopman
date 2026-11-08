# E2E do Gestor (Playwright)

Backend-independentes: mock backend leve (`mockBackend.mjs`, sessão autenticada **e
autorizada** + uma fila + o detalhe de cada pedido dela) + o app (build de produção em
`baseURL '/'`). `npm run test:e2e`; roda no `surfaces-gate.yml` (job `orders-nuxt`).
Portas: `ORDERS_E2E_PORT` (app, padrão 3004) e `MOCK_PORT` (mock, padrão 8796).

A sessão do mock precisa de `authorized: true`: sem ele o app abre em "Seu acesso não
inclui o Gestor de pedidos" e nenhum teste daqui alcança o Gestor (o `board.spec.ts`
confere que a recusa NÃO aparece).

## Coberto

- **`board.spec.ts`** — o mock devolve sessão de operador autenticada (sem lock) + uma
  fila com um card; o Gestor passa dos gates (login/lock) e renderiza o card com cliente,
  itens e total.
- **`overlap.spec.ts`**: a trava da sobreposição (dono, 07/11/2026). Todas as telas do
  Gestor, e o detalhe do pedido aberto da fila (com anterior e próximo), em 1440, 1360,
  1280, 1024, 768 e 390 px: nada visível se desenha por cima de outra coisa visível
  (`expectNoOperatorOverlap` do kit). Os refs do mock têm a forma real (`WEB-20260625-0008`,
  `IFOOD-260914-1515`): o "BLOCKED" de antes passava da coluna de 80 px da fila.
- **`resilience.spec.ts`** — `<OfflineBanner>` (kit) aparece ao cair a rede e some ao voltar.

## Fora daqui (Django real — reviewer local)

- **Login efetivo** + sessão cross-subdomínio `.boulangerie`.
- **Trava do operador** — PIN/crachá na antessala de uma estação provisionada.
- **Ações** (confirmar/avançar/recusar/atribuir) + SSE realtime + catálogo/expositores.
