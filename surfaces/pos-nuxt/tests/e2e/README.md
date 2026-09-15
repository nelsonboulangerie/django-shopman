# E2E do POS (Playwright)

E2E **backend-independentes**: sobem um mock backend leve (`mockBackend.mjs`) e o app
(build de produção servido em `baseURL '/'`) para exercitar comportamentos que **não
dependem de dados de negócio**.

```bash
npm run test:e2e          # sobe mock + build + serve + roda os specs
npm run test:e2e -- --ui  # modo interativo
# Para rodar em paralelo com outra sessão local:
POS_E2E_PORT=33002 POS_E2E_MOCK_PORT=38798 npm run test:e2e
```

O `playwright.config.ts` faz `nuxt build` e serve o Nitro a partir do
`.output-e2e-<porta>/server/index.mjs`, com
`NUXT_APP_BASE_URL=/` (produção usa `/pos/`) e aponta o BFF ao mock via
`NUXT_DJANGO_BASE_URL`. Cada execução sobe e encerra servidores próprios; as
variáveis `POS_E2E_PORT` e `POS_E2E_MOCK_PORT` isolam portas e também os
diretórios ignorados `.nuxt-e2e-<porta>` e `.output-e2e-<porta>`. Duas suítes
com pares de portas distintos podem rodar no mesmo checkout sem compartilhar
artefatos de build.

## Coberto aqui

- **`guards.spec.ts`** — gate de login: a leitura do terminal (`/backstage/pos/`) 401a
  (mock) → o app sobe a tela de login no próprio caixa, com credenciais e botão
  desabilitado até preencher.
- **`resilience.spec.ts`** — banner offline: `<OfflineBanner>` (global, do operator-kit)
  aparece ao cair a rede e some ao voltar.
- **`customer-display.spec.ts`** — transporte real por `BroadcastChannel` entre
  duas janelas e renderização das fases venda/resultado sem gate de operador.

## Fora daqui (precisa de Django real — reviewer local)

Fluxos que exigem uma Projeção de terminal com dados:

- **lock screen / re-gate de PIN** — precisa de operadores provisionados.
- **re-gate de 401 no meio da sessão** — precisa de um shell carregado + um comando
  que 401e (a versão de carga já está coberta no gate de login).
- **comanda → produto → pagamento → cozinha** — o fluxo de venda ponta-a-ponta.
- **404** — o POS é view única (sem `pages/`/router), então não há superfície de 404.

Rode-os contra um Django semeado (`make seed`) apontando `NUXT_DJANGO_BASE_URL` ao
backend real.
