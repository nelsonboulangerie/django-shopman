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
- **`resilience.spec.ts`** — `<OfflineBanner>` (kit) aparece ao cair a rede e some ao voltar.

## Fora daqui (Django real — reviewer local)

- **Login efetivo** + sessão cross-subdomínio `.boulangerie`.
- **Trava do operador** — PIN/crachá na antessala de uma estação provisionada.
- **Ações** (confirmar/avançar/recusar/atribuir) + SSE realtime + catálogo/expositores.
