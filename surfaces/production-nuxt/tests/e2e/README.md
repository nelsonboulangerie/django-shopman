# E2E do Produção (production-nuxt)

Playwright **backend-independente**: um mock backend (`mockBackend.mjs`) serve uma sessão
de operador autenticada + boards de produção vazios. O app é buildado com
`NUXT_APP_BASE_URL=/`, `SHOPMAN_ENVIRONMENT=test`,
`SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1` e apontado ao mock local via
`NUXT_DJANGO_BASE_URL`. Esse opt-in duplo é a única exceção ao fail-fast HTTPS.

```bash
npm run test:e2e
```

## O que cobre

- **guards.spec** — telas de operador atrás do gate; lock, expiração de sessão e
  atalhos das quatro etapas; `/menuboard` aposentado sem consulta ao storefront;
  headers defensivos, cache privado, `Vary` e cookie do BFF.
- **resilience.spec** — `OfflineBanner` aparece quando o contexto vai offline.
- **accessibility.spec** — axe/WCAG AA nas rotas críticas e no QC aberto, foco,
  reflow, alvos de toque, reduced motion, contraste forçado e copy longa. A
  viewport reduzida cobre apenas o **reflow equivalente** a zoom 200%, não o
  zoom real. Screenshots determinísticos são anexados como artefatos para revisão.

O gate executa Chromium nas viewports 1024×768, 768×1024, 1440×900,
1920×1080, 1366×768 e 390×844, além de WebKit em 768×1024. A matriz cobre
geometria e engines reais de browser; screenshots não são baselines aprovadas e
não substituem revisão humana, zoom real, tablet, TV, leitor de tela ou toque físicos.

## O que fica para o reviewer local (Django real)

Login efetivo, desbloqueio/troca de operador, planejar/iniciar/concluir contra
persistência real e o rollover de meia-noite exigem a stack completa + gateway.
D4 também exige refs/credenciais reais das TVs e a janela de corte.

## Como funciona a sessão (mock ramificado por cookie)

O `mockBackend.mjs` ramifica pelo cookie `e2e_session` que o BFF encaminha ao Django:
sem cookie → 403 nos endpoints de operador (aparece o gate de login); com
`e2e_session=authed` → sessão autenticada + estados vazios e uma WO sintética
isolada para abrir o QC; `e2e_session=locked` → lock sem autenticar ninguém. O
mock não oferece fixture de storefront: chamadas acidentais a `/storefront/` retornam 404.

## Portas

- App (build de produção do e2e): `127.0.0.1:3105` (distinta do dev server em `:3005`,
  para não reusar um dev server aberto que aponta ao Django real)
- Mock backend: `127.0.0.1:8797` (evita colidir com o mock do Gestor em `:8796`)
