# 05 — PWA travado: app instalado, desatualizado e sem opção de atualizar

**Árvore:** `.dsh-worktrees/go-live-acceleration` (origin/main = `f0ffd02fd`, 2026-09-29)
**Superfície investigada:** `surfaces/storefront-nuxt`
**Método:** leitura estática + `git log`/`grep`/`du` read-only. Nada foi editado além deste arquivo.
**Legenda:** [FATO] verificado no código/saída · [INFERÊNCIA] dedução minha · [NÃO VERIFICADO] não consegui confirmar.

---

## 1. Resumo executivo

1. **Existe service worker** — `@vite-pwa/nuxt` 1.1.1, estratégia `generateSW` (Workbox), `registerType: 'prompt'` (`nuxt.config.ts:102,111,112`). Precache do build + `offline.html`; navegação `NetworkOnly` com fallback `offline.html`; `CacheFirst` só para `/img/products/**` e `/fonts/**` (`nuxt.config.ts:119-155`).
2. **Existe prompt de atualização** — toast vue-sonner "Nova versão disponível" com botão **Atualizar** (`app/components/PwaUpdateToast.vue:12-18`), montado no shell (`app/app.vue:150`). Ele é o **único** caminho para `skipWaiting` (`skipWaiting:false`, `clientsClaim:false` — `nuxt.config.ts:123-124`).
3. **O prompt é de tiro único e dispensável.** Dispara **uma vez por carregamento de página** (guard `shown`, `PwaUpdateToast.vue:7,9-11`) e o `Toaster` liga `close-button` (`app/components/Ui/Sonner.vue:5`). Num app instalado que não recarrega (iOS suspende em vez de fechar; `app.vue` não remonta entre navegações SPA), **não há segunda chance naquela sessão**.
4. **O storefront não sonda versão nova e nada avisa o cliente de que ele está velho.** `usePwaUpdate.ts` chama `useRegisterSW` e devolve só `needRefresh`/`update` (`app/composables/usePwaUpdate.ts:1-9`): não guarda a `registration` e nunca chama `registration.update()`. O módulo também desliga a sonda periódica (`periodicSyncForUpdates: 0`, `nuxt.config.ts:117`).
5. **O mesmo incidente já foi medido e resolvido no `operator-kit`, não no storefront.** O comentário do kit é literal: *"o worker novo fica em 'waiting' até TODAS as janelas do host fecharem, e o PDV instalado no desktop do dono ficou dias com o bundle antigo"* (`surfaces/operator-kit/app/presentation/pwaRuntime.ts:5-7`, medido 17/09/2026, commit `976152c7b`). O kit tem sonda de 30 min, banner persistente, auto-reload ocioso e telemetria da troca. **O storefront — a superfície do cliente final — ficou com a versão de 14/09/2026 (`b56c90925`) e nunca foi revisitada.**
6. **Nada identifica a versão do cliente.** Não existe `appVersion` no storefront (grep: zero ocorrências em `surfaces/storefront-nuxt`), o relatório de erro não manda `app_version` (`app/utils/clientErrorReport.ts:5-11`) embora o Django aceite o campo (`shopman/storefront/api/telemetry.py:30-31`). **Hoje é impossível saber quem está travado.**
7. **Não existe kill switch nem "forçar atualização"**: sem `version.json`, sem endpoint de versão no Nitro da loja (`server/routes/` só tem `health/live`, `sitemap.xml`, `robots.txt`, `manifest.webmanifest`, SSE), sem banner server-driven. O que existe é o inverso do necessário: **um cliente velho nunca é avisado de que é velho.**
8. **"Tela travada" no sentido literal também é possível, por outro motivo:** **nenhum fetch do storefront tem timeout** — nem o BFF→Django (`server/utils/djangoProxy.ts:202-207`), nem o shell aguardado em `app/app.vue:25` (`app/composables/useStorefrontShell.ts:20-31`). Rede ruim ou upstream pendurado = tela que nunca sai do estado pendente.
9. **Probabilidade:** [INFERÊNCIA] alta para o subconjunto que instala o app **e** mantém a instância viva atravessando um deploy — justamente o público mais fiel da loja. Severidade alta: cliente final, no meio do pedido, sem saída visível.
10. **Recomendação P0:** portar do `operator-kit` a sonda + **banner persistente** (não toast descartável) + identidade de versão; e colocar timeout nos dois fetches. Nada disso é invenção: tudo já existe no repositório, testado, no lado operador.

---

## 2. Achados

### A1 — O service worker: o que é e onde está [FATO]

| Peça | Evidência |
| --- | --- |
| Módulo | `@vite-pwa/nuxt` `1.1.1` fixo — `surfaces/storefront-nuxt/package.json:32`; `tools/pwa-gate/check.mjs:93` |
| Estratégia | `strategies: 'generateSW'` (Workbox gera o SW) — `nuxt.config.ts:111` |
| Tipo de registro | `registerType: 'prompt'` — `nuxt.config.ts:112` |
| Registro automático | desligado: `injectRegister: false`, `client.registerPlugin: false` — `nuxt.config.ts:113-115` |
| Quem registra | **só** `useRegisterSW({ immediate: true })` dentro de `usePwaUpdate()` (`app/composables/usePwaUpdate.ts:4`), que só é chamado por `PwaUpdateToast` (`app/components/PwaUpdateToast.vue:6`) |
| Cache do próprio SW | `no-cache, no-store, must-revalidate` em `/sw.js` — `nuxt.config.ts:68-70` e `server/utils/storefrontSecurity.ts:57-59` |
| Gate | `tools/pwa-gate/check.mjs:118` exige que `skipWaiting` só obedeça mensagem explícita |

**Impacto:** se `PwaUpdateToast` não montar (por exemplo `app.vue` falha e o Nuxt renderiza `app/error.vue`, que **não** inclui o toast — `app/error.vue:77-123`), o SW não é registrado nessa carga. Numa PWA já instalada isso não desinstala o SW, mas significa que **o único componente que registra o SW é também o único que oferece a atualização**.

**Confiança:** [FATO] para todas as linhas acima.

---

### A2 — Precache e runtime cache: contrato estreito, bem feito [FATO]

- Precache: `globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}']` (`nuxt.config.ts:125`), com `globIgnores` para screenshots, splash do iOS e `documentos-legais/` (`nuxt.config.ts:131`).
- **Medição do peso estático** (`find` + `du -ch` sobre `public/` aplicando os `globIgnores`): **14 arquivos, 432 KB** — `offline.html`, 2 fontes, 9 ícones PWA, favicons, 1 padrão SVG. As 40 splash (5,0 MB) ficam fora, como o gate exige (`check.mjs:149-155`). O peso real do precache em produção é isso **mais os chunks `_nuxt/*.js|css` do build** (não mensurável aqui: sem `node_modules` e sem `.output`, não rodei build).
- Navegação: `NetworkOnly` com `precacheFallback: { fallbackURL: '/offline.html' }` (`nuxt.config.ts:133-140`); `navigateFallback: null` (`:120`). `public/offline.html` existe (30 linhas) e a CSP da loja permite `style-src 'unsafe-inline'`, então o casco offline sai estilizado (`server/utils/storefrontSecurity.ts:33`).
- Runtime: `CacheFirst` em `/img/products/**` e `/fonts/**` (`nuxt.config.ts:141-154`). API, SSE e HTML **nunca** entram — verificado pelo gate (`check.mjs:109,112,113,116,117`).
- **Consequência de desenho:** o app instalado **não navega offline**. Offline = casco genérico. É contrato declarado (`README.md:122-126`), não bug.

**Confiança:** [FATO].

---

### A3 — O caminho de atualização, linha por linha, e por que ele falha [FATO] + [INFERÊNCIA]

Cadeia verificada no código:

1. `registerType: 'prompt'`, `skipWaiting: false`, `clientsClaim: false` (`nuxt.config.ts:112,123,124`).
2. O único gradil para `skipWaiting` é a mensagem `SKIP_WAITING` (exigido pelo gate, `check.mjs:118`), disparada por `updateServiceWorker(true)` (`app/composables/usePwaUpdate.ts:8`).
3. O gatilho é `watch(needRefresh, ...)` — **sem `immediate`** — com `let shown = false` no escopo do setup (`app/components/PwaUpdateToast.vue:7,9-11`).
4. O toast é montado **uma vez** no shell (`app/app.vue:150`, dentro do `<ClientOnly>` de `:145-155`), e `app.vue` **não remonta** em navegação SPA.
5. O `Toaster` global usa `close-button` (`app/components/Ui/Sonner.vue:5`) — o aviso é descartável.

O que isso produz, em sequência:

| # | Passo | Evidência | Status |
| --- | --- | --- | --- |
| 1 | Cliente instala o app. Passa a usar a janela instalada, que fica viva por dias. | `app/plugins/standalone-display.client.ts:6-10` | [FATO] |
| 2 | Um deploy publica build novo. O `sw.js` novo instala e fica em `waiting` porque as janelas antigas continuam abertas. | config `:123-124`; comportamento do Workbox | [FATO] na config, [INFERÊNCIA] no `waiting` |
| 3 | O app **continua servindo o build antigo** — HTML vem da rede (`NetworkOnly`), mas o JS em memória é o antigo. | `nuxt.config.ts:133-140` | [FATO]/[INFERÊNCIA] |
| 4 | O aviso aparece **uma vez**. Se o cliente estiver no meio de um pedido, rolar a tela, ou tocar no X, ele some. | `PwaUpdateToast.vue:9-18`; `Ui/Sonner.vue:5` | [FATO] |
| 5 | **Nada mais oferece atualização.** Não há segundo aviso, item de menu ou banner. | grep `usePwaUpdate`/`needRefresh`: só `PwaUpdateToast.vue` | [FATO] |
| 6 | Nada sonda o servidor: sem `registration.update()`, sem sonda periódica. O navegador só reconsulta o `sw.js` em navegação de documento. | `usePwaUpdate.ts:1-9`; `nuxt.config.ts:117` | [FATO] |
| 7 | A versão antiga persiste até o cliente fechar **todas** as janelas do host e reabrir. No iOS standalone isso pode levar dias, e o usuário não tem como forçar. | — | [INFERÊNCIA] |

**É exatamente a queixa**: *"PWA instalado, desatualizado, tela travada, sem opção de atualizar"*. O passo 5 responde literalmente a "nem dava opção de atualizar": o mecanismo existe, e **é de tiro único e descartável**.

**Confiança:** [FATO] para todo o mecanismo; [INFERÊNCIA] para a atribuição à queixa (não reproduzi em dispositivo — ver §6).

---

### A4 — O incidente já aconteceu aqui dentro e foi medido no lado operador [FATO]

`surfaces/operator-kit/runtime/plugins/pwaRegistration.client.ts:5-8`:

```
// `registerType: "prompt"` guarda o worker novo em "waiting" até todas as janelas
// do host fecharem. Num app instalado que fica dias aberto isso nunca acontece, e
// o aviso só aparece se o navegador chegar a buscar o `sw.js`. Guardar o registro
// aqui é o que dá a `usePwaAutoUpdate` como PERGUNTAR (`registration.update()`).
```

E `surfaces/operator-kit/app/presentation/pwaRuntime.ts:5-7`: *"medido em 17/09/2026, PRs #783/#789: o worker novo fica em 'waiting' até TODAS as janelas do host fecharem, e o PDV instalado no desktop do dono ficou dias com o bundle antigo"*. Commit: `976152c7b` (2026-09-17).

O kit resolveu com duas metades:

| Peça do kit | Arquivo | O que faz |
| --- | --- | --- |
| Sonda | `app/composables/usePwaUpdate.ts:6-12` + `pwaRuntime.ts:12,15` | `registration.update()` a cada 30 min, piso de 60 s entre sondas oportunistas |
| Disparos | `app/composables/usePwaAutoUpdate.ts:151-160` | intervalo + `visibilitychange` + `focus` + `online` |
| Aplicação segura | `app/presentation/pwaRuntime.ts:19,60-79` | só com o balcão ocioso, rota liberada e nenhum `hold` publicado; devolve a **razão nomeada** quando não aplica |
| Aviso | `app/components/OperatorPwaUpdatePrompt.vue:23-40` | **`<aside>` persistente** enquanto `needRefresh` for verdadeiro |
| Telemetria da troca | `app/utils/pwaUpdateReport.ts:1-20` | marca em `localStorage` antes do reload, envia no boot seguinte com `from_version`/`to_version` |
| Versão | `surfaces/operator-kit/pwa.config.ts:193` | `NUXT_PUBLIC_APP_VERSION | SOURCE_VERSION | "local"` |

**O storefront não tem nenhuma das seis.** `usePwaUpdate.ts` do storefront tem 10 linhas e não mudou desde `b56c90925` (2026-09-14; `git log` no arquivo: um único commit).

**Confiança:** [FATO].

---

### A5 — Nenhuma identidade de versão: o cliente não sabe que está velho, o suporte não sabe qual versão ele roda [FATO]

- grep por `app_version|appVersion|SOURCE_VERSION|NUXT_PUBLIC_APP_VERSION` em `surfaces/storefront-nuxt`: **zero ocorrências**.
- O payload de erro do cliente não tem campo de versão: `app/utils/clientErrorReport.ts:5-11` (`message, kind, source, url, stack`).
- **O backend já aceita esse campo** e o descarta por ausência: `shopman/storefront/api/telemetry.py:30-31` allow-lista `user_agent` e `app_version` (máx. 60). O custo de passar a receber a versão é **só no cliente**.
- Sentry está configurado sem `release=` (`config/settings.py:2276-2295`), então nem pelo caminho do Django dá para separar builds.
- O plano irmão que resolve isso está **aberto**: `docs/plans/WP-RELEASE-01-versoes-de-apps-sem-quebra.md:3` (`Estado: aberto`), Fase R1 (`:242-249`): `SHOPMAN_RELEASE_ID`/`SHOPMAN_BUILD_SHA` + *"endpoint barato de versão em Django e em cada Nitro, separado de liveness e readiness"*. Grep por `SHOPMAN_RELEASE_ID|SHOPMAN_BUILD_SHA`: **não existe no código**.

**Impacto:** a pergunta "quantos clientes estão travados?" é hoje **irrespondível**. Nem por telemetria, nem por header, nem por log.

**Confiança:** [FATO].

---

### A6 — Detecção de versão obsoleta, kill switch e "forçar atualização": não existe [FATO]

Procurado e **não encontrado**:

| Mecanismo | Onde procurei | Resultado |
| --- | --- | --- |
| `version.json` / build id no cliente | grep em `surfaces/`, `app/`, `server/` | não encontrado |
| Endpoint de versão no Nitro da loja | `ls server/routes/` | só `health/live`, `sitemap.xml`, `robots.txt`, `manifest.webmanifest`, `sse/pedido/[ref]` |
| `/health` como kill switch | `server/routes/health/live.get.ts:11-19` | devolve `{status:'ok', checks:{bff:'ok'}}` — constante, sem versão, e o comentário diz que o health **não deve tirar a loja do ar** |
| Banner de atualização dirigido pelo servidor | `app/app.vue:145-155`; `shopman/storefront/presentation/home.py:157` | a única copy server-driven é `pwa_copy.update_title/update_cta` (`home.py:572-573`; `shopman/shop/omotenashi/copy.py`) — **texto**, não gatilho |
| Flag de "recarregar agora" | `runtimeConfig.public` (`nuxt.config.ts:47-51`) | só `continuumCatalogEnabled` |
| Auto-reload por ociosidade | `nuxt.config.ts:109-160` | ausente (o kit tem `idleReloadPaths`, `pwa.config.ts:68-78`) |

**A lacuna que dói:** o storefront **já** entrega copy vinda do servidor pelo shell. Um campo a mais na MESMA projection (`shell.pwa_release`) daria um banner **não descartável** para todo cliente cuja build difere da do servidor — o equivalente a um kill switch de cliente, sem deploy de app.

**Confiança:** [FATO].

---

### A7 — API muda, cliente velho chama endpoint removido: degradação silenciosa [FATO no código; INFERÊNCIA no efeito]

- O BFF lê `X-API-Version` do Django e **só loga um warning**, nunca bloqueia: `server/utils/apiVersion.ts:19-30`, chamado em `server/utils/djangoProxy.ts:209-212`.
- Esse warning é do **Nitro**, não do cliente: não chega ao navegador, não vira banner, não derruba nada.
- Endpoint removido → o Django devolve 404 no dialeto `{detail, field, errors}` (ou HTML, que o BFF saneia em `djangoProxy.ts:19-21,233-236`). A página mostra o erro dela; o cliente antigo segue instalado **sem saber que é antigo**.

**Impacto:** um major de API (`EXPECTED_API_MAJOR = 1`, `apiVersion.ts:10`) pode quebrar o app de todos os clientes instalados ao mesmo tempo, com a evidência existindo **apenas no log do servidor** e sem mecanismo algum de correção empurrada para o cliente.

**Confiança:** [FATO] no mecanismo; [INFERÊNCIA] no efeito observável (não há teste e2e desse cenário).

---

### A8 — "Tela travada" literal: nenhum fetch tem timeout [FATO no código]

Procurei `timeout|AbortSignal|AbortController|retry` em `app/` e `server/` do storefront. O que existe:

- `$fetch.raw(target, { method, headers, body, ignoreResponseError: true })` — **sem `timeout`, sem `signal`** (`server/utils/djangoProxy.ts:202-207`). É o único ponto por onde passa **toda** chamada da loja ao Django.
- `useStorefrontShell()` faz `$fetch` sem timeout (`app/composables/useStorefrontShell.ts:20-31`) e é **aguardado no topo do shell**: `await useStorefrontShell()` (`app/app.vue:25`). Ou seja, **todo carregamento de toda página depende de um fetch sem teto**.
- Timeout existe em exatamente dois lugares, e nenhum protege a loja: `AddressPicker.vue:471` (`timeout: 10000`) é da geolocalização do dispositivo; `server/middleware/sku-redirects.ts:10` (`timeout: 4000`) é de redirect de SKU.
- `retryWithBackoff` (2 retries, 200 ms→2 s; `app/utils/retryBackoff.ts:20-27`) existe mas é usado no **carrinho** (`useCartState.ts:296,352`), não na leitura de página.

**Impacto:** upstream pendurado (deploy, lock no banco, worker saturado) = requisição que nunca retorna. Para o cliente, **tela que nunca sai do estado pendente** — o outro sentido exato de "travada". O `Server-Timing` já é propagado do Django pelo BFF (`djangoProxy.ts:214-220`), então dá para medir o p95 antes de escolher o teto.

**Confiança:** [FATO] no código; [INFERÊNCIA] no efeito percebido.

---

### A9 — Offline e rede ruim: o que é tratado e o que escapa [FATO]

**Tratado:**
- Queda de rede em navegação → casco `offline.html` (contrato + e2e: `tests/e2e/pwa.spec.ts:26-35`, `tests/e2e/resilience.spec.ts:36-47`).
- Banner global "Sem conexão. Tentando reconectar…" pelo `navigator.onLine` (`app/components/OfflineBanner.vue:15-27`; `app/composables/useConnectivity.ts:11-33`), com reconexão reconciliando o carrinho (`app/app.vue:20`).
- SSR sem conteúdo → 503 com `Retry-After` em vez de parede bonita: `app/composables/useContentGuard.ts:30-43`.

**Escapa:**
- `precacheFallback` só cobre **falha de rede**. Um **502/503/504 do ingress** durante o deploy é resposta bem-sucedida: o cliente vê a página de erro da plataforma, **não** o casco offline. [INFERÊNCIA a partir do desenho do Workbox — não verificável aqui sem `node_modules`]
- `/health/live` do BFF não olha o Django (`server/routes/health/live.get.ts:3-10`), então o health check da plataforma **não** impede o tráfego de chegar numa instância cujo upstream está morto. Com `instance_count: 1` (`.do/app.subdomains.yaml:679-687`), o deploy é uma janela sem redundância.
- A própria `useContentGuard.ts:7-11` documenta o incidente real: **23/09/2026, durante o 504 do `api.` num reinício de deploy, toda PDP respondia 200 vazio**. "Tela vazia para quem visita" é medição no ar, não hipótese.

**Confiança:** [FATO] nas citações; [INFERÊNCIA] no comportamento 502→sem casco.

---

### A10 — Bônus: a regra de cache de foto de produto **nunca casa em produção** [FATO]

`nuxt.config.ts:141-147`:

```js
urlPattern: ({ url }) => url.origin === self.location.origin && url.pathname.startsWith('/img/products/')
```

Em produção as fotos saem de **outro host e outro caminho**:
- `.do/app.alpha-subdomains.yaml:66-73` — ingress `img.nelsonboulangerie.com.br` → service `storefront-nuxt` com `rewrite: /img/`;
- `config/management/commands/seed.py:1834-1837` — `SHOPMAN_PRODUCT_IMAGE_BASE` default `https://img.<domain>/products`, e `.do/app.subdomains.yaml:602-607` fixa `https://img.STORE_DOMAIN/products`;
- o seed grava `image_url` absoluta nesse host (testes de contrato: `shopman/backstage/tests/test_release_readiness.py:327,334`).

No documento servido em `www.<domain>`, a URL da foto é `https://img.<domain>/products/x.webp`:
- **origem diferente** → `url.origin === self.location.origin` é falso;
- **caminho diferente** → `/products/x.webp` não começa com `/img/products/`.

A regra `CacheFirst` (`cacheName: 'storefront-product-images'`) **é código morto no ar** — o cache vive vazio. Em dev/teste com URL relativa (`tests/continuumCatalog.test.ts:47` usa `/img/products/pao.webp`) a regra funciona — por isso o e2e não pega.

**Impacto:** nenhum "offline com foto"; e cada navegação nova no app instalado paga latência de rede para as fotos do cardápio (o `routeRules` `immutable` de `nuxt.config.ts:65-67` cobre só o cache HTTP do navegador).

**Confiança:** [FATO] nas URLs e na regra; [INFERÊNCIA] alta no casamento (não executei o SW).

---

### A11 — `CacheFirst` sem expiração: cache sem teto [FATO]

As duas regras de runtime (`nuxt.config.ts:141-154`) **não declaram `expiration`** (`maxEntries`/`maxAgeSeconds`). `/fonts/**` são 2 arquivos (100 KB) — irrelevante. Sem teto, o CacheStorage só cresce num app de uso diário. [INFERÊNCIA] com a regra de fotos morta (A10), o risco de estourar cota cai muito — mas ressuscitar a regra sem expiração reintroduz o risco. Não medi crescimento real.

**Confiança:** [FATO] na ausência de `expiration`; [NÃO VERIFICADO] o efeito de cota.

---

### A12 — Telemetria de cliente: existe, mas não enxerga app travado [FATO]

**O que existe e funciona:**
- Plugin global que captura `vue:error`, `window.error` e `unhandledrejection` e faz POST fire-and-forget para `/api/v1/storefront/client-error/` (`app/plugins/errorReporter.client.ts:9,20,30,33-36`).
- Sanitização em casa (e-mail/telefone redigidos, query string removida, truncagem) — `app/utils/clientErrorReport.ts:22-56`, espelhando a allow-list do Django.
- Backend: `shopman/storefront/api/telemetry.py:93-115` (`logger.error` → Sentry via `LoggingIntegration` quando há DSN), rate-limit 30/m por IP; Sentry opt-in em `config/settings.py:2250-2295`.

**O que falta para o caso "cliente travado":**
1. sem `app_version` no payload (A5) — o Django **aceita** o campo (`telemetry.py:30`);
2. um app travado **não gera erro** — não há exceção, é silêncio; nada reporta "estou velho";
3. nenhuma telemetria de **troca de versão** (o kit tem `pwaUpdateReport.ts`: grava a marca antes do reload e envia `from_version`→`to_version` no boot seguinte);
4. `MAX_PER_SESSION = 20` e dedupe por chave (`errorReporter.client.ts:13-27`) — suficientes para erro em loop, irrelevantes aqui.

**Confiança:** [FATO].

---

### A13 — O gate de PWA valida estrutura, não o fluxo de atualização [FATO]

`tools/pwa-gate/check.mjs` (262 linhas) e `tests/e2e/pwa.spec.ts` foram lidos por inteiro:

- O gate confere precache, ausência de `/api|/events|/admin`, `offline.html` no precache, `NetworkOnly`+`PrecacheFallbackPlugin`, exatamente dois `CacheFirst`, `SKIP_WAITING` por mensagem, manifesto, ícones, dimensões, CSP, 40 splash, cache do `/sw.js` (`check.mjs:105-155,225-254`). **Nada sobre atualizar.**
- `tests/e2e/pwa.spec.ts` cobre manifesto, SW registrado + navegação offline, convite que não aparece no checkout, overlay/scroll. **Nenhum teste de "existe versão nova e o cliente consegue atualizar".** O `README.md:139-147` descreve o teste manual ("faça outro build, recarregue, toque em Atualizar") — o fluxo está **documentado como manual**, e fluxo manual não roda na CI.

**Impacto:** a regressão que produz o travamento é invisível para a esteira.

**Confiança:** [FATO].

---

## 3. O que já existe e funciona (não reinventar)

| Peça | Onde | Observação |
| --- | --- | --- |
| SW de casco com contrato estreito e verificado | `surfaces/storefront-nuxt/nuxt.config.ts:109-160`; `tools/pwa-gate/check.mjs` | API/SSE/HTML fora do cache, por gate, não por promessa |
| `offline.html` na voz da casa, pré-cacheado | `public/offline.html`; `check.mjs:111,113` | "A loja ficou sem conexão" + "Tentar de novo" (form GET, funciona sem JS) |
| `/sw.js` sempre revalidado | `nuxt.config.ts:68-70`; `server/utils/storefrontSecurity.ts:57-59` | sem isso, a sonda de versão nova responderia do disco para sempre |
| Banner de conexão perdida + reconexão que reconcilia o carrinho | `app/components/OfflineBanner.vue`; `app/composables/useConnectivity.ts`; `app/app.vue:20` | lugar natural para um banner de versão obsoleta |
| Copy do PWA server-driven | `shopman/storefront/presentation/home.py:561-573`; `shopman/shop/omotenashi/copy.py` (`PWA_UPDATE_TITLE`/`PWA_UPDATE_CTA`) | **o canal para um gatilho de atualização já existe** — é só campo novo na mesma projection |
| Telemetria de erro do cliente ponta a ponta | `app/plugins/errorReporter.client.ts`; `shopman/storefront/api/telemetry.py:93-115`; Sentry opt-in `config/settings.py:2250-2295` | falta só a versão no payload |
| **Todo o mecanismo de atualização do lado operador** | `surfaces/operator-kit/`: `pwaRegistration.client.ts`, `app/composables/usePwaUpdate.ts` (`checkForUpdate`), `usePwaAutoUpdate.ts`, `app/presentation/pwaRuntime.ts` (+ `tests/pwaRuntime.test.ts`), `app/utils/pwaUpdateReport.ts`, `app/components/OperatorPwaUpdatePrompt.vue`, `pwa.config.ts:193` (`appVersion`) | **sonda medida, holds nomeados, banner persistente, telemetria da troca, versão** — pronto para portar |
| Plano de identidade de release | `docs/plans/WP-RELEASE-01-...md:192-193,242-249` | invariante 9 já exige "service worker/cache inclui identidade de build" |
| Plano do PWA do storefront | `docs/plans/WP-PWA-EXECUCAO.md:66,67,89`; `docs/plans/WP-PWA-CONFORMIDADE.md:157` | F0.6 entregue em `b56c90925` (2026-09-14), como especificado; foi **subespecificado**, não mal implementado |

---

## 4. Lacunas / riscos

| # | Risco | Provável? | Severidade | Evidência |
| --- | --- | --- | --- | --- |
| R1 | Cliente instalado preso em build antigo **sem opção de atualizar** | Alta no subconjunto instalado que atravessa deploy | **Crítica** (cliente final, sem saída) | A3, A4 |
| R2 | Nenhuma identidade de versão: não sei quantos estão travados nem qual build | Certo | Alta (incidente às cegas) | A5 |
| R3 | Sem force-update/kill switch: não há como empurrar correção ao cliente | Certo | Alta | A6 |
| R4 | Fetch sem timeout (BFF e shell) → página pendurada para sempre | Média, e **certa** em deploy com upstream lento | Alta | A8 |
| R5 | Deploy reinicia instância única; 502/504 não caem no casco offline | Média | Média-alta | A9; `.do/app.subdomains.yaml:679-687` |
| R6 | Major de API quebra clientes antigos em silêncio (warning só no Nitro) | Baixa no curto prazo | Alta se acontecer | A7 |
| R7 | Fluxo de atualização sem teste automatizado | Certo | Média (regressão invisível) | A13 |
| R8 | Cache `CacheFirst` de foto de produto morto em produção | Certo | Baixa | A10 |
| R9 | `CacheFirst` sem expiração | Baixa hoje | Baixa | A11 |

---

## 5. Recomendações, por impacto/esforço

### P0 — antes do go-live (bloqueiam a queixa)

**1. Portar a sonda + banner persistente do `operator-kit` para o storefront.**
- O quê: guardar a `registration` (`onRegisteredSW`) e expor `checkForUpdate()` no `usePwaUpdate` do storefront (espelho de `operator-kit/app/composables/usePwaUpdate.ts:3-20`); sondar no boot, a cada 30 min, no `focus`/`visibilitychange`/`online` (espelho de `usePwaAutoUpdate.ts:151-160`); trocar o toast por um aviso **que volta** enquanto houver versão nova.
- Custo: **~1 dia** (a lógica pura e os testes já existem: `app/presentation/pwaRuntime.ts` + `tests/pwaRuntime.test.ts`).
- Risco: **baixo**. Precisa ser mais conservador que o kit: **nada de auto-reload ocioso no storefront** (o cliente pode estar digitando endereço ou pagando). Só avisar e atualizar no toque.
- Detalhe de UX que resolve a queixa: aviso **persistente** (padrão `<aside>` do kit, `OperatorPwaUpdatePrompt.vue:23-40`) ou reexibição a cada `visibilitychange`, nunca "uma vez e some".

**2. Identidade de versão ponta a ponta.**
- O quê: `appVersion` em `runtimeConfig.public` (`NUXT_PUBLIC_APP_VERSION || SOURCE_VERSION`, como `operator-kit/pwa.config.ts:193`); `app_version` no payload de `clientErrorReport` (o Django já aceita: `telemetry.py:30-31`); rota `/health/version` no Nitro da loja (barata, sem Django).
- Custo: **~2-4 h**. Risco: nenhum.

**3. Timeout nos dois fetches que sustentam a loja.**
- O quê: `timeout` (ou `AbortSignal.timeout`) no `$fetch.raw` do `djangoProxy.ts:202` e no `$fetch` do `useStorefrontShell.ts:22`; erro tratado → estado de erro com "Tentar de novo" (o padrão do `error.vue:96-98` já existe).
- Custo: **~4-6 h** com teste. Risco: **médio** — teto curto derruba página legítima lenta. Medir o p95 com o `Server-Timing` que o BFF já propaga (`djangoProxy.ts:214-220`) antes de fixar (sugestão inicial: 15 s no BFF, 20 s no shell).

### P1 — logo depois (tornam o problema gerenciável)

**4. Kill switch de cliente via a projection que já existe.**
- O quê: campo `shell.pwa_release` (build id do servidor) na mesma projection que já leva `pwa_copy` (`shopman/storefront/presentation/home.py:240,360,390`); o cliente compara com o seu `appVersion` e, se diferir, mostra aviso **não descartável** — "nova versão, toque para atualizar agora".
- Custo: **~1 dia**. Risco: baixo; o aviso tem de ser silencioso no checkout.
- Bônus: é o único mecanismo que funciona **mesmo quando a sonda não funciona** (iOS teimoso), porque o gatilho vem no dado que o cliente já busca.

**5. Gate: teste e2e do fluxo de atualização.**
- O quê: em `tools/pwa-gate/check.mjs` ou `tests/e2e/pwa.spec.ts`, subir o preview, publicar um `sw.js` novo (build com byte diferente), esperar `needRefresh` e provar que o aviso aparece **e reaparece**; e provar que o app não recarrega sozinho no checkout.
- Custo: **~1 dia**. Risco: baixo. Sem isso, a regressão que gerou a queixa volta em silêncio (A13).

**6. Tornar visível a divergência de contrato.**
- O quê: hoje o major errado de `X-API-Version` só vira `console.warn` no Nitro (`apiVersion.ts:19-30`). Propagar ao cliente como estado degradado + contador de métrica.
- Custo: **~4 h**. Risco: baixo.

### P2 — higiene

**7. Foto de produto no cache do SW (A10):** decidir entre tirar a regra morta (`nuxt.config.ts:141-147`) ou fazê-la casar (host de imagem na allowlist, ou servir foto same-origin). Custo: 2-4 h. Ganho: cardápio mais rápido no app instalado.

**8. `expiration` nos `CacheFirst`** (`nuxt.config.ts:141-154`): `maxEntries`/`maxAgeSeconds`. Custo: 1 h.

**9. Runbook de suporte para cliente travado.** Custo: 1 h. Enquanto 1-3 não estiverem no ar, é a **única** saída: app instalado não se atualiza sozinho; reinstalar (remover da tela de início e adicionar de novo) resolve. Escrever isso onde o atendimento lê.

### Matriz de decisão para o dono

| Opção | Custo | Cobre | Risco |
| --- | --- | --- | --- |
| Só o runbook (P2-9) | 1 h | nada estrutural | cliente continua travando |
| Sonda + banner (P0-1) + versão (P0-2) | ~1,5 dia | a queixa principal, e dá visibilidade | baixo |
| P0 + timeouts (P0-3) | ~2 dias | também a "tela pendurada" | médio (calibrar teto) |
| P0 + `shell.pwa_release` (P1-4) | ~3 dias | tudo acima, **com** empurrão server-side | baixo |
| Migrar o storefront para a capability do kit | 1-2 semanas | o kit inteiro, com holds e auto-update ocioso | alto: o storefront é cliente, não operador; auto-reload ocioso é inaceitável no checkout |

---

## 6. Perguntas abertas / o que não consegui verificar

1. **Não reproduzi em dispositivo.** A cadeia de A3 é [FATO] no código; o passo "o worker fica em waiting e a página nunca o ativa" é comportamento do Workbox/browser que **não** pude ler aqui: `node_modules` está **vazio** na worktree e no checkout principal (`ls` retorna 0 entradas), e não rodei build (sem `.output`). **É o item nº 1 a confirmar** — teste manual de 20 minutos: `npm run build && npm run preview`, abrir, `navigator.serviceWorker.ready`, novo build, recarregar, observar `needRefresh` → toast → tocar em Atualizar (roteiro já escrito em `README.md:139-147`).
2. **Web search indisponível** nesta sessão (duas tentativas, timeout de 60 s). Todo comportamento de plataforma (iOS standalone, `updateViaCache`, ativação do worker em espera) está marcado [INFERÊNCIA] e merece confirmação em documentação oficial.
3. **Proporção de clientes que instalam o app** — não há analytics de instalação nem de versão (A5). Nenhuma priorização pode ser calibrada com dado hoje.
4. **Peso real do precache em produção** — medi 432 KB estáticos (14 arquivos) já com os `globIgnores`; o total inclui os chunks `_nuxt/*` do build, que **não medi** (sem build). Se o precache passar de alguns MB, o risco de instalação falhar em aparelho com pouco espaço entra na conta (não entrei nele).
5. **Se há Cloudflare/CDN na frente da loja.** `nuxt.config.ts:59-61` cita o Email Obfuscation da Cloudflare e `docs/plans/CATALOG-IMAGES-OFF-GITHUB-PLAN.md:61` cita "o CDN da DO", mas o spec versionado (`.do/app.subdomains.yaml`, `.do/app.alpha-subdomains.yaml`) **não** declara `cdn:` nem purge de cache no deploy. Isso muda a retenção dos chunks antigos após um deploy — e portanto a severidade do cenário de chunk 404, que pela leitura do Workbox só deve morder quando o worker novo ativa com página antiga em memória.
6. **`experimental.emitRouteChunkError`** (reload automático do Nuxt em falha de chunk): não está configurado no `nuxt.config.ts`, então vale o default do Nuxt 4.5 — que **não verifiquei** sem `node_modules`. Se o default for `'automatic'`, parte do cenário de tela branca por chunk é mitigada pelo próprio framework; se for `false`, não é.
7. **Quantas versões atrás os clientes costumam estar.** Sem os itens 2/A5 não há resposta — e é a pergunta que decide se o problema é "um cliente reclamou" ou "metade da base instalada está velha".
