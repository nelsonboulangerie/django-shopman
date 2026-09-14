# WP-PWA-EXECUCAO — Plano de execução para agente externo: Storefront → PDV → backstage → Web Push

> Estado: **pronto para apreciação do dono (2026-09-14).** Este documento é o brief
> executável do [WP-PWA-CONFORMIDADE](WP-PWA-CONFORMIDADE.md): o "o quê e por quê"
> está lá; aqui está o "como, onde e com que prova". Quem executa é um agente
> externo, uma fase por PR, na ordem abaixo. Nenhuma fase começa sem os materiais
> do dono listados no Anexo A.
>
> Quando executar em relação ao go-live é decisão do dono; o plano não assume data.

## 0. Regras da casa que o executor tem que obedecer

Lidas de [CLAUDE.md](../../CLAUDE.md) e das ADRs. Violar qualquer uma reprova o PR.

1. **Worktree primeiro.** Nada de escrever no checkout principal. `git add` só de
   arquivo nomeado; nunca `-A`, `.`, `-u` ou diretório. Sem `git stash`.
2. **Node 22** para qualquer surface (`engines.node = 22.x`; node 26 deixa a suíte
   do storefront vermelha). Django sempre por `.venv/bin/python`.
3. **URL em inglês; texto de tela em português; identificador em inglês.** A copy
   que o cliente lê (tela offline, convite de instalação) é `OmotenashiCopy`
   quando for do Storefront, nunca literal em componente.
4. **Zero alias, zero nome antigo, zero "formerly".** Projeto pré-go-live.
5. **Nada de cache de API ou de HTML no service worker.** Regra dura deste WP: o
   SW não guarda nada sob `/api/`, `/events/`, `/admin/`, nem resposta de navegação.
   Um SW que serve o caixa de ontem é bug de segurança, não de UX.
6. **Envelope de segurança não afrouxa.** A CSP do `operator-kit` é nonce-only em
   `script-src`; a do Storefront tem allowlist própria. As duas já liberam
   `worker-src 'self' blob:` e `manifest-src 'self'`. Nenhuma diretiva nova por
   causa deste WP; se parecer necessário, parar e perguntar.
7. **Core intocado.** Nada em `packages/*`. O que é dado do tenant (nome, nome
   curto, cores) já mora em `shop.Shop`; o que é marca em arquivo (ícones) mora
   no `public/` da surface. Uploads em `Shop.logo` NÃO servem para ícone: a
   media da App Platform é efêmera ([ROADMAP](../ROADMAP.md), "Media persistente").
8. **Migração numerada sem colisão** (F3): `ls shopman/shop/migrations | sed 's/_.*//' | sort | uniq -d`
   vazio antes do PR. Chave nova em JSON documentada em
   [data-schemas](../reference/data-schemas.md) antes de usar.
9. **Cada PR entrega evidência**, não contagem: a saída dos comandos do gate e, nas
   fases com aparelho, a foto ou o registro descrito no runbook.

## 1. Estado de partida (medido em 2026-09-14)

| Fato | Onde |
|---|---|
| Nenhuma surface tem manifesto, service worker ou ícone além de `favicon.ico` | `surfaces/*/public` |
| Storefront: Nuxt 4.5, `@nuxtjs/color-mode`, `@nuxt/fonts`, `@nuxt/icon`; vitest (projetos `unit` e `component`), Playwright e2e, `scripts/ux-smoke.mjs`; CSP própria em `server/utils/storefrontSecurity.ts` com `worker-src 'self' blob:` e `manifest-src 'self'`; `theme-color` hoje `#85786c` (não é cor da marca viva); `apple-mobile-web-app-capable` já presente; fotos de produto imutáveis por convenção em `/img/products/**` com `routeRules` de um ano | `surfaces/storefront-nuxt` |
| BFF do Storefront responde `/api/**` com `private, no-store`; SSE em `server/utils/eventStream.ts` | idem |
| `Shop.brand_name`, `Shop.short_name` ("nome curto (PWA)"), `Shop.description`, `Shop.tagline`, `Shop.primary_color`; projeção pública da loja em `shopman/storefront/presentation/shop.py` | Django |
| Paleta da marca em código: `shopman/shop/brand_tokens.py` (navbar Burgundy `#7C3A40`, ink `#531D22`, canvas/cards creme, CTA Brass `#8B6B2E`, rodapé Deep Dark Moss `#30391E`); emitida como variáveis CSS na surface | Django + `app/utils/shopTheme.ts` |
| `operator-kit`: envelope de segurança opt-in (`server/utils/securityHeaders.ts`, `operatorSecurity.ts`), `useConnectivity`, SSE `notifications.ts`; Produção é o único app que optou pelo envelope; `board.vue` pede fullscreen à mão; nenhum Wake Lock | `surfaces/operator-kit`, `surfaces/production-nuxt` |
| Alerta pessoal: `UserNotification` + `UserNotificationEvent` com ciclo de vida, dedupe, escalação, retenção; `push_user_notification` emite só SSE `user-<id>` | `shopman/shop/models/user_notification.py`, `shopman/shop/services/user_notifications.py` |
| CI das surfaces: `.github/workflows/surfaces-gate.yml`, job `app-quality` por app (`npm ci`, `npm test`, `npm run typecheck`), Marketing com e2e/a11y/visual/security completos | GitHub |

## 2. Decisões de arquitetura (fechadas; não reabrir no PR)

| # | Decisão | Motivo |
|---|---|---|
| A1 | **Manifesto é rota Nitro** (`/manifest.webmanifest`), não arquivo estático: nome, nome curto, descrição e `lang` vêm da projeção pública do `Shop`; cores vêm dos tokens da marca; ícones apontam para `public/`. Cache `public, max-age=3600`. | Tenant = dado, zero código. O `short_name` já existe no `Shop` para isto |
| A2 | **Service worker via `@vite-pwa/nuxt`** com `manifest: false`, estratégia `generateSW`, `registerType: 'prompt'`, `navigateFallback` só para `offline.html` quando a rede falha (`NetworkOnly` + `catchHandler`). | Menos código próprio; Workbox testado; o manifesto fica com a A1 |
| A3 | **Precache**: build do Nuxt, `offline.html`, ícones, fontes. **Runtime**: `CacheFirst` só em `/img/products/**` e `/fonts/**` (imutáveis por convenção). **Nunca** `/api/**`, `/events/**`, `/admin/**`, navegação. | Regra 5 |
| A4 | **`/sw.js` com `cache-control: no-cache`**; assets do build seguem imutáveis. | Atualização precisa chegar |
| A5 | **Atualização**: o app detecta SW em espera e oferece "Atualizar" (Storefront e apps de mesa); kiosks (kds, production) aplicam sozinhos quando ociosos por 60 s. | Operador não pode rodar versão velha por dias |
| A6 | **Instalação**: Android por `beforeinstallprompt` capturado e botão próprio; iOS por tela guiada quando `display-mode: browser` e UA iOS, com "agora não" que silencia por 7 dias (localStorage). A permissão de notificação (F3) só por toque. | O que cada plataforma permite |
| A7 | **Ícones gerados de um único SVG mestre** por comando versionado (`npm run pwa:assets`), saída commitada em `public/`: `pwa-64`, `pwa-192`, `pwa-512`, `maskable-512` (zona segura 80 %), `apple-touch-icon-180` (fundo sólido), `favicon.ico` + `favicon.svg`, `monochrome-512` (badge/ícone temático Android). Splash iOS por `pwa-asset-generator` (`apple-touch-startup-image`, todos os tamanhos vigentes), commitados. | Uma fonte, saída reproduzível |
| A8 | **Capability do kit nasce na F1 por extração** do que o Storefront provou, não antes. | ADR-001: seam com dois consumidores reais |
| A9 | **Web Push** (F3): `PushSubscription` em `shop/models`, VAPID nos segredos, envio por Directive `notification.push` no worker, payload é ponteiro (`id`, `category`, `title`, `body` curto, `action_url`), categorias financeiras só título. | [WP-PWA-CONFORMIDADE](WP-PWA-CONFORMIDADE.md), seção Arquitetura |
| A10 | **Gate `make pwa`** próprio (script Node em `tools/pwa-gate/`), sem Lighthouse. | O Lighthouse aposentou a categoria PWA |

## 3. Fase F0 — Storefront (piloto)

**Pré-requisito:** Anexo A itens 1, 2, 3, 4 e 6 entregues pelo dono.

### Tarefas

| # | Tarefa | Onde | Aceite |
|---|---|---|---|
| F0.1 | Adicionar `@vite-pwa/nuxt` (versão fixa) com `manifest: false`, `strategies: 'generateSW'`, `registerType: 'prompt'`, `workbox.navigateFallback: null`, `globPatterns` do build + `offline.html` + ícones + fontes, `runtimeCaching` conforme A3, `navigationPreload: false`. `devOptions.enabled: false`. | `surfaces/storefront-nuxt/nuxt.config.ts` | `nuxt build` gera `sw.js`; inspeção do precache (`workbox-*.js` manifest) sem `/api/`, `/events/`, `/admin/` |
| F0.2 | Rota Nitro do manifesto lendo a projeção pública da loja (via BFF já existente, mesma allowlist), com fallback estático se o Django estiver fora (nome da marca do build). Campos: `id: "/"`, `name`, `short_name`, `description`, `lang: "pt-BR"`, `dir`, `start_url: "/?source=pwa"`, `scope: "/"`, `display: "standalone"`, `display_override: ["standalone"]`, `orientation: "portrait"`, `theme_color`, `background_color`, `icons` (A7), `shortcuts` (Cardápio `/menu`, Sacola `/sacola`, Meus pedidos `/conta`), `categories: ["food","shopping"]`, `screenshots` (Anexo A item 5, `form_factor: narrow` e `wide`). | `surfaces/storefront-nuxt/server/routes/manifest.webmanifest.ts` | resposta `application/manifest+json`, `cache-control: public, max-age=3600`; teste unitário do builder com `Shop` sem `short_name` (cai para `brand_name` truncado a 12) |
| F0.3 | `head`: `<link rel="manifest">`, `theme-color` **da marca** (Anexo A item 3; hoje `#85786c` está errado), `apple-touch-icon`, `apple-mobile-web-app-title` = `short_name`, `apple-mobile-web-app-status-bar-style` coerente com a navbar, `apple-touch-startup-image` por media query (gerado). Rota `/sw.js` com `cache-control: no-cache` (A4). | `nuxt.config.ts`, `server/middleware/storefront-security.ts` | `curl -I /sw.js` mostra `no-cache`; `curl -I /manifest.webmanifest` mostra o tipo certo; CSP inalterada (`storefrontSecurity.test`) |
| F0.4 | `offline.html` estático, na voz da casa: título, uma frase honesta ("sem conexão agora"), botão "tentar de novo", fundo `background_color`, ícone. Nada de link externo: sem rede, nenhum link funciona. Copy via chave `OmotenashiCopy` `PWA_OFFLINE_*` resolvida no build da página (ou fallback fixo se a copy não existir). | `public/offline.html` + chaves em `shopman/shop/omotenashi/copy.py` | Playwright: com rede cortada, navegação para `/menu` mostra `offline.html`; `test_omotenashi_copy_keys` verde |
| F0.5 | Composable `usePwaInstall()`: captura `beforeinstallprompt`, expõe `canInstall`, `install()`, `isStandalone` (`display-mode`), `isIos`, `dismissedUntil`. Componente `PwaInstallInvite.vue` discreto (bottom sheet no padrão da loja), exibido no máximo uma vez por 7 dias, nunca no checkout nem no acompanhamento de pedido. Tela guiada iOS com dois passos em imagem (Anexo A item 7). Copy em `OmotenashiCopy` (`PWA_INSTALL_*`). | `app/composables/usePwaInstall.ts`, `app/components/PwaInstallInvite.vue`, `app/components/PwaIosGuide.vue` | vitest de composable (env do harness próprio do storefront): estados Android/iOS/standalone/dismissed; componente não renderiza em `/finalizar` e `/pedido/*` |
| F0.6 | Composable `usePwaUpdate()`: usa `useRegisterSW` do módulo; expõe `needRefresh`, `update()`. Toast "Nova versão disponível · Atualizar" no padrão da loja. `skipWaiting` só no toque. | `app/composables/usePwaUpdate.ts`, `app/app.vue` | vitest: `needRefresh` dispara o toast; `update()` chama `updateServiceWorker(true)` |
| F0.7 | Geração de ícones e splash: `npm run pwa:assets` (`@vite-pwa/assets-generator` com preset `minimal-2023` + `pwa-asset-generator` para splash), entrada `brand/nelson-mark.svg` (Anexo A item 1), saída em `public/pwa/`. Commitar a saída; script documentado no README da surface. | `surfaces/storefront-nuxt/package.json`, `public/pwa/` | os arquivos listados em A7 existem; `maskable-512` respeita zona segura (checagem visual no PR com a imagem anexada) |
| F0.8 | Gate `make pwa` (Node, sem dependência de navegador para os itens 1–4; Playwright para 5): manifesto válido e completo; `/sw.js` `no-cache`; precache sem caminhos proibidos; CSP com `worker-src`/`manifest-src`; meta iOS presentes; e2e: registro do SW conclui, `offline.html` com rede cortada, convite de instalação não aparece no checkout. Alvo `pwa` no Makefile com `app=storefront`. | `tools/pwa-gate/`, `Makefile` | `make pwa app=storefront` verde; documentado em [commands.md](../reference/commands.md) |
| F0.9 | Documentação: seção "PWA" no README do storefront (como gerar assets, como testar instalação no iPhone, como forçar atualização), entrada no [runbook de release](../runbooks/release-secrets-runbook.md) se algo virar env (não deve). | docs | revisão |

### Prova humana da F0 (registrada no PR)

- Android (Chrome): botão "Instalar" aparece, instala, abre `standalone` com cor da
  barra da marca, atalhos funcionam, `offline.html` com modo avião.
- iPhone (Safari, iOS 16.4+): tela guiada aparece uma vez; após adicionar à Tela de
  Início abre `standalone`, splash da marca, barra de status coerente, sem barra do
  Safari; logado continua logado (cookie `.boulangerie`).
- Atualização: publicar um build novo, abrir o app, toast aparece, "Atualizar"
  recarrega na versão nova.
- Critério do dono: pessoa que nunca viu o sistema instala no iPhone em **menos de
  um minuto, sem manual**.

## 4. Fase F1 — capability do `operator-kit` + PDV

**Pré-requisito:** F0 no ar; Anexo A item 8 (ícones dos apps de operador).

| # | Tarefa | Onde | Aceite |
|---|---|---|---|
| F1.1 | Extrair do Storefront para o kit, como capability **opt-in** (mesma forma do envelope de segurança): `definePwaCapability({ app, manifest, display, wakeLock, kiosk })` que registra o módulo com a config A1–A6, a rota do manifesto (nome/cores por app, `short_name` por app), o middleware do `/sw.js`, `usePwaInstall`, `usePwaUpdate`, `useWakeLock`, `useKioskMode`. Nada implícito: app que não chama não ganha nada. | `surfaces/operator-kit/` (`server/utils/pwa.ts`, `app/composables/usePwa*.ts`, `app/components/Pwa*.vue`) | testes do kit (vitest) para cada composable com API ausente (Safari velho não quebra); `securityHeaders.test.ts` intacto; nonce presente no script de registro |
| F1.2 | `useWakeLock()`: pede `navigator.wakeLock.request('screen')` ao montar e re-pede em `visibilitychange`; nunca lança. | kit | teste com API ausente e com `release` |
| F1.3 | PDV liga: `display: standalone`, Wake Lock ligado, ícone próprio (Anexo A item 8), atalhos (Venda, Caixa), `theme-color` do tema neutro do PDV (`pos_neutral_design_system`). Sem push ainda. | `surfaces/pos-nuxt/nuxt.config.ts` | `make pwa app=pos`; suíte do PDV verde; Maps/ViaCEP continuam (CSP do PDV é específica, ver ADR-026 do envelope: não copiar a do Marketing) |
| F1.4 | Gate `make pwa` ganha `app=<qualquer>` e roda no CI `surfaces-gate` para os apps que optaram. | `tools/pwa-gate/`, workflow | CI verde |

## 5. Fase F2 — backstage inteiro

**Pré-requisito:** F1 no ar.

| App | `display` | Wake Lock | Kiosk (recarga ociosa) | Atalhos | Observação |
|---|---|---|---|---|---|
| hub | standalone | não | não | Pedidos, Caixa, Produção | recebe o feed de avisos e, na F3, as preferências de push |
| orders | standalone | não | não | Fila, Hoje | remover `new Notification()` de aba quando a F3 entrar |
| kds | fullscreen, landscape | sim | sim | nenhum | parede |
| production | fullscreen, landscape | sim | sim | Plano, Fornadas | trocar o `requestFullscreen` manual do `board.vue` pelo `useKioskMode`; `/display/` continua sem senha |
| marketing | standalone | não | não | Campanhas | envelope já ligado; conferir que o nonce cobre o registro |
| purchase | standalone | não | não | Recebimento | |
| bi | standalone | não | não | Vendas | |

Aceite: `make pwa app=<app>` verde para os sete; `surfaces-gate` verde; prova humana
em um tablet de parede (KDS ou Produção): tela não apaga em 30 minutos, versão nova
aplicada sozinha quando ocioso.

## 6. Fase F3 — Web Push

**Pré-requisito:** F2 no ar; chaves VAPID geradas e guardadas pelo dono (Anexo A item 9).

| # | Tarefa | Onde | Aceite |
|---|---|---|---|
| F3.1 | Model `PushSubscription` (`user`, `endpoint` único, `p256dh`, `auth`, `surface_ref`, `device_label`, `categories` JSON, `created_at`, `last_success_at`, `failures`, `disabled_at`) com `verbose_name` em tudo (gate do Admin exige) e Admin somente leitura com ação "remover". Migração sem colisão de número. | `shopman/shop/models/push_subscription.py`, `shopman/shop/admin/` | `make admin` verde; `makemigrations --check` limpo |
| F3.2 | API `/api/v1/backstage/notifications/push/` (`POST` assinar, `DELETE` remover, `GET` listar aparelhos e categorias, `PATCH` categorias). Autenticada pelo `User` da sessão; endpoint de outro usuário é 404. Chave pública VAPID exposta em `runtimeConfig.public` (env `NUXT_PUBLIC_VAPID_PUBLIC_KEY`, nome derivado da chave, ver armadilha do Nuxt). | `shopman/backstage/api/notifications.py`, `urls.py` | testes de API: assinar, reassinar mesmo endpoint (idempotente), trocar de usuário revoga o anterior, 404 cruzado |
| F3.3 | Directive `notification.push` + handler: resolve assinaturas ativas do usuário que aceitam a categoria; `pywebpush` com `TTL` (1 h operacional, 24 h relatório) e `Urgency`; 404/410 desativa a assinatura; 5xx/timeout transitório; evidência por tentativa em log estruturado (`operational_event`). `push_user_notification` enfileira com `dedupe_key` (segunda perna, a primeira segue SSE). | `shopman/shop/handlers/notification_push.py`, `shopman/shop/services/user_notifications.py`, `apps.py` (registro) | testes com `pywebpush` falso; categoria financeira sem `body`; nenhum PII no payload (teste que serializa e procura telefone/valor) |
| F3.4 | SW: handlers `push` (mostra notificação com `tag = group_key`, `renotify` só para crítico, `data.action_url`), `notificationclick` (foca cliente existente na URL ou abre), `pushsubscriptionchange` (reassina via API). Badge: `navigator.setAppBadge(n)` com a contagem de avisos ativos vinda do feed; `clearAppBadge` ao zerar. | kit (`sw` custom via `injectManifest` só se `generateSW` não permitir os handlers; senão `workbox` `importScripts`) | Playwright: `notificationclick` abre a `action_url`; badge muda com o feed |
| F3.5 | Tela de avisos do Hub: seção "Avisos neste aparelho": botão "Ativar avisos" (pede permissão só no toque), lista de aparelhos, categorias com liga/desliga, versão do app. | `surfaces/hub-nuxt` | vitest do componente; prova humana |
| F3.6 | Segredos: `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIMS_EMAIL` no spec da DO (api e worker), documentados no [runbook de segredos](../runbooks/release-secrets-runbook.md) e na [conferência do spec](../runbooks/conferir-spec-digitalocean.md). Rotação = operação com runbook (invalida todas as assinaturas). | docs + spec | `check --deploy` verde |
| F3.7 | Gestor aposenta `new Notification()` de aba; Produção e PDV ligam push para as categorias da tabela do WP de conformidade. | `orders-nuxt`, `production-nuxt`, `pos-nuxt` | suítes verdes |

Prova humana da F3, registrada no runbook: Android e iPhone, tela desligada, um
aviso de cada categoria crítica chega e o toque abre a tela certa já logada.

## 7. Entrega por PR (formato obrigatório)

Cada PR (uma fase, ou uma metade de fase quando ficar grande) traz:

1. O diff só dos arquivos da fase (regra 1).
2. Saída dos gates: `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`,
   `npm run test:e2e` da surface; `make pwa app=<app>`; e nas fases Python
   `make test-framework` e `make admin`.
3. Evidência humana descrita na fase (foto de aparelho ou registro no runbook).
4. Lista do que ficou de fora e por quê.
5. Nenhum `TODO`, nenhum comentário "temporário", nenhuma diretiva de CSP nova.

## 8. O que NÃO fazer

- Não cachear API, SSE, Admin ou HTML no SW (regra 5).
- Não usar `Shop.logo` (upload) como ícone de manifesto (regra 7).
- Não instalar Firebase, OneSignal, Pusher ou SDK de push de terceiro.
- Não pedir permissão de notificação no carregamento da página.
- Não copiar a CSP do Marketing para o PDV nem para o Storefront.
- Não tocar em `packages/*`.
- Não colocar ícone, cor ou nome da Nelson em código Python ou do kit: é dado do
  `Shop` (nome, nome curto, descrição) ou arquivo em `public/` (ícone) por surface.
- Não ligar push para cliente no Storefront.

## Anexo A — Materiais que o dono entrega antes de cada fase

| # | Material | Formato | Para quê | Fase |
|---|---|---|---|---|
| 1 | **Símbolo da marca** (a marca sozinha, sem texto, como aparece no ícone do app) | SVG vetorial, quadrado, fundo transparente, sem texto rasterizado; cor em `currentColor` ou cor fixa da marca | fonte única de todos os ícones (A7) | F0 |
| 2 | **Logotipo completo** (símbolo + wordmark) | SVG, versão horizontal; versão sobre fundo escuro se existir | splash iOS, `offline.html`, convite de instalação | F0 |
| 3 | **Duas cores do manifesto**: `theme_color` (barra do sistema) e `background_color` (fundo da splash e do casco). Recomendação: navbar Burgundy `#7C3A40` e creme dos cards `#FCF7EE`; alternativa: Faubourg `#F5E7DD` | hex | manifesto, meta `theme-color`, splash | F0 |
| 4 | **Nomes**: `name` (até 45 caracteres, ex. "Nelson Boulangerie") e `short_name` (até 12, o que aparece sob o ícone, ex. "Nelson"); descrição curta (até 140) | texto, gravados no Admin em `Shop` (`brand_name`, `short_name`, `description`) | manifesto | F0 |
| 5 | **Capturas para o diálogo de instalação** do Android: 2 verticais (mobile, 1080×1920 ou proporção equivalente) e 1 horizontal (1280×720 ou maior); podem ser feitas pelo executor no alpha e aprovadas pelo dono | PNG | manifesto `screenshots` (instalação rica) | F0 |
| 6 | **Copy** da tela offline e do convite de instalação (ou "use a voz da casa e me mostre") | texto pt-BR, uma frase cada | `OmotenashiCopy` `PWA_*` | F0 |
| 7 | Aprovação das **duas imagens do passo a passo iOS** (Compartilhar → Adicionar à Tela de Início), produzidas pelo executor no aparelho | aprovação | tela guiada iOS | F0 |
| 8 | **Ícones dos apps de operador**: decisão entre (a) um único símbolo da marca com uma cor de fundo por app, ou (b) um glifo por app (PDV, KDS, Produção, Gestor, Hub, Marketing, Compras, B.I.). Recomendação: (a), símbolo em creme sobre fundo Burgundy, com a inicial/glifo pequeno no canto para diferenciar na tela inicial | decisão + SVG se (b) | manifestos dos apps | F1/F2 |
| 9 | **Chaves VAPID** geradas e guardadas no cofre do dono (comando fornecido pelo executor: `npx web-push generate-vapid-keys`) e um e-mail de contato para o `sub` do VAPID | segredos no spec da DO | Web Push | F3 |
| 10 | **Aparelhos de prova**: um Android e um iPhone (iOS 16.4+) com acesso ao alpha, e um tablet de parede para o kiosk | acesso | provas humanas | F0, F2, F3 |

O que o executor gera sozinho a partir dos itens 1 a 3: `favicon.ico`, `favicon.svg`,
`pwa-64/192/512`, `maskable-512`, `apple-touch-icon-180`, `monochrome-512`, todos os
`apple-touch-startup-image` (tamanhos vigentes de iPhone e iPad, retrato e paisagem),
e a `theme-color` para light e dark do `color-mode`.

## Anexo B — Referências

- [WP-PWA-CONFORMIDADE](WP-PWA-CONFORMIDADE.md): o que entra, o que fica de fora, por surface.
- [ADR-026, envelope de segurança das surfaces](../decisions/adr-026-operator-surface-security-envelope.md)
- [ADR-016, SSE first](../decisions/adr-016-sse-first-realtime.md) · [ADR-003, directives](../decisions/adr-003-directives-sem-celery.md)
- Armadilhas conhecidas: env `NUXT_PUBLIC_*` deriva da chave; fallback de `runtimeConfig.public` é assado no build; node 26 quebra o storefront; `stat` não prova existência sob sandbox.
- `shopman/shop/brand_tokens.py` (cores), `shopman/storefront/presentation/shop.py` (projeção da loja), `shopman/shop/services/user_notifications.py` (avisos).
