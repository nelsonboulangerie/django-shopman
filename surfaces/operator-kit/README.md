# operator-kit — Nuxt layer compartilhado das superfícies de operador

Fundação comum das oito superfícies de operador: `pos-nuxt`, `orders-nuxt`,
`kds-nuxt`, `production-nuxt`, `purchase-nuxt`, `marketing-nuxt`, `bi-nuxt` e a
Central de Apps (`hub-nuxt`). Centraliza BFF, segurança, resiliência, sessão e a base
do design system sem absorver regras específicas de cada domínio.

**Última verificação dos consumidores:** 2026-09-10, contra os oito
`nuxt.config.ts` do `HEAD`.

O **storefront-nuxt fica de fora** (superfície de cliente, branded, harness próprio).

## Como um app consome

No `nuxt.config.ts` do app:

```ts
export default defineNuxtConfig({
  extends: ["../operator-kit"],
  // ... config do app (color-mode, css, app.head, etc.)
});
```

O layer contribui, via auto-import do Nuxt:

| Área | Símbolo | Papel |
|---|---|---|
| `app/utils/httpError.ts` | `httpError`, `isTransientError` | narrowing tipado de erro de rede |
| `app/utils/retryBackoff.ts` | `retryWithBackoff` | backoff exponencial + jitter + teto |
| `app/utils/clientErrorReport.ts` | `reportClientError`, `buildClientErrorReport` | telemetria → `backstage/client-error/` |
| `app/utils/tw-helper.ts` | `tw` | identidade para strings de classes Tailwind (DX/lint) |
| `app/utils/translucent.ts` | `getTranslucentFloatingPanelClasses`, … | classes canônicas de painel flutuante translúcido |
| `server/utils/djangoProxy.ts` | `proxyDjangoApi`, `proxyDjangoPath` | proxy BFF → Django (cookie, CSRF, redirects, X-API-Version) |
| `server/utils/djangoBaseUrl.ts` | `configuredDjangoBaseUrl`, `resolveDjangoBaseUrl` | fail-fast de upstream ausente/local/inseguro em produção |
| `server/plugins/upstream-guard.ts` | — | repete no boot o fail-fast dos apps opt-in, sem confiar no valor embutido no build |
| `server/middleware/operator-security.ts` | — | CSP/frame/nosniff/referrer/permissões, HSTS em HTTPS e cache privado |
| `server/utils/operatorSecurity.ts` | `operatorResponseHeaders`, `applyPrivateNoStore` | política testável de headers e preservação de `Vary` no BFF |
| `server/utils/eventStream.ts` | `proxyEventStream` | streaming SSE same-origin do eventstream do Django |
| `server/utils/apiVersion.ts` | `warnOnApiVersionMismatch` | warning estruturado de major divergente do contrato |
| `app/composables/useConnectivity.ts` | `useConnectivity` | sinal offline + reconciliação no reconnect/foco |
| `app/components/OfflineBanner.vue` | `<OfflineBanner>` | aviso calmo de conexão (colocar no layout raiz) |
| `app/plugins/errorReporter.client.ts` | — | captura erro não-tratado → telemetria (inerte em dev) |
| `app/types/operator.ts` | `OperatorCard`, `OperatorSession`, … | espelho TS da API operator/session\|eligible\|unlock\|lock |
| `app/presentation/operatorLock.ts` | `isLocked`, `buildUnlockPayload`, … | transforms puros do lock (sem I/O) |
| `app/composables/useOperatorLock.ts` | `useOperatorLock` | read/write do lock de operador (PIN/crachá) via proxy |
| `app/components/OperatorLock.vue` | `<OperatorLock>` | overlay de lock (picker + PIN pad + crachá + troca forçada) |
| `app/components/OperatorPinChange.vue` | `<OperatorPinChange>` | numpad de troca de PIN (forçada e voluntária) |
| `app/components/OperatorNumpad.vue` | `<OperatorNumpad>` | numpad de quantidade (inteiro): POS e quiosque de QC |

Os testes também têm harness compartilhado: `tests/support/composableEnv.ts`
(`installNuxtGlobals()`, env `node` com Vue real + fronteira de dados mockada) é importado
pelos testes de composables que o adotam — os projetos `unit` desses apps
declaram `resolve.dedupe: ["vue"]` para garantir instância única do Vue.

Apps que ativam `runtimeConfig.operatorSecurityHeaders` recebem documentos e APIs
privados (`private, no-store`, `Vary: Cookie`). Assets compilados mantêm o cache do
Nitro. HSTS só é emitido quando a requisição chega como HTTPS; o edge continua
responsável por preservar `X-Forwarded-Proto: https` e a verificação final deve ocorrer
no host publicado. Marketing usa ainda uma política CSP local mais estrita, com nonce e
branch de HMR limitado a desenvolvimento; essa necessidade não foi promovida ao kit
porque ainda não tem dois consumidores comprovados.

## O que ainda NÃO vive aqui (roadmap — ver docs/plans/completed/BACKSTAGE-EXCELLENCE-HARDENING-PLAN.md)

- **Lock do POS** — o POS mantém deliberadamente a própria variante
  (`usePosOperatorLock` + `PosLockScreen`/`PosPinChange`): auto-lock por inatividade,
  transporte via `usePosAction` e lock local-first. A família canônica
  (`useOperatorLock`/`OperatorLock`/`OperatorPinChange`) vive aqui e serve
  kds/orders/production.
- **DS tokens canônicos** (`tailwind.css`) — hoje idênticos por app; extrair o bloco
  canônico para cá (com split das partes app-específicas: print no POS, dark no KDS).
- **Interceptor global de 401/403** (reabre o gate de operador) — plugin compartilhado.
- **Tooling base** (ESLint flat + Prettier + vitest 2-projects + Playwright) — configs
  compartilhadas adotadas por cada app no seu WP.

## Testes do kit

```bash
npm test   # vitest: utils puros + guardrails de design system (paridade de tokens)
```

Os guardrails (`tests/guardrails.test.ts`) verificam a fonte única de tokens e os
consumidores já incorporados a cada regra. A cobertura cresce por app; a ausência de
um app numa regra específica não deve ser documentada como cobertura existente.
