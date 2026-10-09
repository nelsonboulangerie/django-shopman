# operator-kit: Nuxt layer compartilhado das superfícies de operador

Fundação comum das oito superfícies de operador: `pos-nuxt`, `orders-nuxt`,
`kds-nuxt`, `production-nuxt`, `purchase-nuxt`, `marketing-nuxt`, `bi-nuxt` e a
Central (`hub-nuxt`). Centraliza BFF, segurança, resiliência, sessão e a base
do design system sem absorver regras específicas de cada domínio.

**Última verificação dos consumidores:** 2026-09-10, contra os oito
`nuxt.config.ts` do `HEAD`.

O **storefront-nuxt fica de fora** (superfície de cliente, branded, harness próprio).
O `kitchensink-nuxt` é o consumidor de referência e preview; não leva
implementação canônica para fora deste layer.

## UX transversal do WP-UX-13B

Layouts canônicos, matriz visual, scanner geométrico, Splitter, atalhos e catálogo vivo
estão documentados em
[`docs/reference/operator-ux-infrastructure.md`](../../docs/reference/operator-ux-infrastructure.md).

As peças estruturais novas são `<OperatorAppRoot>`, `<OperatorOfficeShell>`,
`<OperatorOperationalShell>`, `<OperatorPage>` e `<OperatorSplitter>`. Elas compõem as
famílias oficiais do Nuxt UI; não são uma anatomia paralela. O catálogo roda somente no
harness e na surface protegida `kitchensink-nuxt`:

```bash
npm run catalog:dev
npm run catalog:build
npm run test:visual
```

Nenhum app deve criar shell, Sidebar, NavigationMenu, Page ou Splitter local. Uma
necessidade operacional comprovada entra no ledger com responsável e teste.
O léxico, anatomias, matriz dos oito apps, exceções e guia de adoção ficam em
[`operator-kitchen-sink.md`](../../docs/reference/operator-kitchen-sink.md).

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
| `app/utils/api.ts` | `apiPath` | prefixa um caminho com o `baseURL` do app (no-op em `/`) |
| `app/composables/useApiPath.ts` | `useApiPath` | `apiPath` já amarrado ao `baseURL` do runtime config — a forma que o app consome |
| `app/utils/operatorSession.ts` | `operatorSessionOnError` | política comum de 401/403 no `useFetch`: reabre o gate com `refreshNuxtData("operator-session")`. O Marketing tem a própria (`marketingSessionOnError`), que distingue `station_locked` e guarda o intent de decisão pendente |
| `server/api/v1/[...path].ts` | — | o `/api/v1/**` do app: rota única do BFF para os oito, sobre `proxyDjangoApi` |
| `server/utils/djangoProxy.ts` | `proxyDjangoApi`, `proxyDjangoPath` | proxy BFF → Django (sessão de operador isolada, CSRF, redirects, X-API-Version) |
| `server/utils/operatorCookies.ts` | `operatorCookieHeaderForDjango`, `operatorSetCookieHeaderForBrowser` | fronteira de cookies entre browser e Django |
| `server/utils/djangoBaseUrl.ts` | `configuredDjangoBaseUrl`, `resolveDjangoBaseUrl` | fail-fast de upstream ausente/local/inseguro em produção |
| `server/plugins/upstream-guard.ts` | — | repete no boot o fail-fast dos apps opt-in, sem confiar no valor embutido no build |
| `server/middleware/operator-security.ts` | — | CSP/frame/nosniff/referrer/permissões, HSTS em HTTPS e cache privado |
| `server/utils/operatorSecurity.ts` | `operatorResponseHeaders`, `applyPrivateNoStore` | política testável de headers e preservação de `Vary` no BFF |
| `server/utils/eventStream.ts` | `proxyEventStream` | streaming SSE same-origin do eventstream do Django |
| `app/utils/resilientEventSource.ts` | `openResilientEventSource` | o lado do browser: EventSource que se recria com backoff (2 s → 60 s) depois de um não-200 na reconexão (502 de deploy) ou de um `stream-error` (canal recusado), e avisa a reabertura para o chamador refazer o fetch canônico |
| `server/routes/health/live.get.ts` | — | `/health/live`: processo/BFF vivo, sem chamar o Django — é o health check da plataforma |
| `server/routes/health/ready.get.ts` | — | `/health/ready`: BFF + `/health/ready/` do Django (smoke e diagnóstico, nunca health check da plataforma) |
| `server/utils/healthProbe.ts` | `ProbeRateLimiter`, `checkDjangoReadiness`, `respondHealthLive`, `respondHealthReady` | corpo pobre (`ok`/`fail`), `no-store` e limitador em memória dos probes |
| `server/utils/apiVersion.ts` | `warnOnApiVersionMismatch` | warning estruturado de major divergente do contrato |
| `app/composables/useConnectivity.ts` | `useConnectivity` | sinal offline + reconciliação no reconnect/foco |
| `app/components/OfflineBanner.vue` | `<OfflineBanner>` | aviso calmo de conexão (colocar no layout raiz) |
| `app/plugins/errorReporter.client.ts` | — | captura erro não-tratado → telemetria (inerte em dev) |
| `app/utils/deviceActivity.ts` | `deviceActivityClock`, `createDeviceActivityClock`, `deviceActivityCookieDomain` | relógio de atividade do DISPOSITIVO: cookie `shopman_operator_activity` (epoch ms) no domínio-pai (`<app>.<zona>` → `.<zona>`; localhost/IP/zona recusada pelo navegador → host-only), throttle de 5 s no próprio cookie, valor no futuro ignorado; o BFF não o repassa ao Django |
| `app/plugins/deviceActivity.client.ts` | — | todo toque real (pointerdown/keydown/wheel/touchstart/pointermove, na captura) em qualquer app marca o relógio; rota com `definePageMeta({ operatorActivity: false })` fica fora (tela do cliente do PDV). É o que faz a trava do PDV contar a ociosidade do dispositivo, não só a dele |
| `app/types/operator.ts` | `OperatorCard`, `OperatorSession`, … | espelho TS da API operator/session\|eligible\|unlock\|lock |
| `app/presentation/operatorLock.ts` | `isLocked`, `buildUnlockPayload`, … | transforms puros do lock (sem I/O) |
| `app/composables/useOperatorLock.ts` | `useOperatorLock` | read/write do lock de operador (PIN/crachá) via proxy |
| `app/components/OperatorLock.vue` | `<OperatorLock>` | overlay de lock (picker + PIN pad + crachá + troca forçada) |
| `app/components/OperatorPinChange.vue` | `<OperatorPinChange>` | numpad de troca de PIN (forçada e voluntária) |
| `app/components/OperatorNumpad.vue` | `<OperatorNumpad>` | numpad de quantidade (inteiro): POS e quiosque de QC |
| `app/components/OperatorDayPicker.vue` | `<OperatorDayPicker>` | Tipo 1 de data, "Escolha rápida de dia": Hoje, Amanhã, próxima data, Outra data (ver "Datas") |
| `app/components/OperatorPeriodPicker.vue` | `<OperatorPeriodPicker>` | Tipo 2 de data, "Período": botão que diz a janela, chips no popover, ‹ › (ver "Datas") |
| `app/components/OperatorMetric.vue` | `<OperatorMetric>` | métrica: `NuxtCard` com `title`/`description`, a figura e o delta pronto da presentation (`MetricDelta` em `presentation/metric.ts`) num `NuxtBadge`; `size="statement"` diz a resposta em uma frase (ver "Peças de leitura") |
| `app/components/ReadFreshness.vue` | `<ReadFreshness>` | frescor da leitura: "Última leitura útil: 15:36:22 · há 1 s", pelo relógio do servidor (`useNowTick`); `inline` para a linha de recortes (ver "Peças de leitura") |
| `app/composables/useNowTick.ts` | `useNowTick` | o relógio do servidor: um timer só para a tela, ancorado no `server_now_iso`/`generated_at` da projeção |
| `app/components/UiToolbar.vue` | `<UiToolbar>` | barra de trabalho sob o nav: slot padrão à esquerda, slot `end` à direita (com `flex-wrap`) |
| `app/components/UiSearchInput.vue` | `<UiSearchInput>` | busca da barra: ícone, limpar, expand-on-focus, `focus()` exposto para o atalho `/` |
| `app/components/UiFilterChip.vue` | `<UiFilterChip>` | pílula de filtro da barra, com contagem e slot de ícone — alvo de toque de 44 px (`min-h-control`) |
| `app/components/FilterBar.vue` | `<FilterBar>` | filtro universal: "+ Filtro" → campo → valores, chip removível que reabre a edição, painel de baixo no celular (ver "Filtro universal") |
| `app/composables/useRouteFilters.ts` | `useRouteFilters` | o recorte da `FilterBar` na URL (`filtersToQuery`/`filtersFromQuery` em `presentation/filterBar.ts`) |
| `app/components/UiIconButton.vue` | `<UiIconButton>` | ação quadrada de ícone da barra (44 px, `size-control`), com `active` e `spinning` |
| `app/presentation/windowTitle.ts` | `operatorAppName`, `windowTitle` | regra pura do nome e do título: `"<Casa> · <App> · <Página>"`, sempre com ponto médio — ver "Nome do app instalado" |
| `app/composables/useOperatorWindowTitle.ts` | `useOperatorWindowTitle`, `useOperatorAppName` | instala o `titleTemplate` no `app.vue` (e `error.vue`) e expõe o nome resolvido; as páginas passam só o próprio título |
| `app/presentation/nextFocus.ts` | `revealPlan`, `needsInitialReveal`, … | regra pura do próximo foco (alinhamento, movimento, quando rolar na montagem) |
| `app/composables/useNextFocus.ts` | `useNextFocus`, `measureBottomObstruction` | a página declara o foco (chave reativa); o bloco `data-focus-target` vai à linha de foco e recebe o foco de teclado — ver "Próximo foco" |
| `app/presentation/moreBelow.ts` | `hintOffset`, `hintMotionClass`, `shouldHint` | regra pura da dica "tem mais abaixo" |
| `app/composables/useMoreBelow.ts` | `useMoreBelow` | observa o fim do conteúdo (sentinela + IntersectionObserver) descontando o que flutua na base |
| `app/components/MoreBelow.vue` | `<MoreBelow>` | a dica em si: degradê + pílula com chevron, some ao chegar ao fim — ver "Tem mais abaixo" |
| `app/presentation/appLaunch.ts` | `crossAppLinkAttrs`, `sameOrigin`, `EXTERNAL_LINK_ATTRS` | regra pura de como um app manda o operador para OUTRO app — ver "Navegação entre apps instalados" |
| `app/composables/useOperatorAppLink.ts` | `useOperatorAppLink` | `attrsFor(href)` reativo ao modo de exibição (instalar com a tela aberta já muda o link) |
| `app/utils/displayMode.ts` | `isInstalledDisplay` | fonte única do "estou rodando como app instalado?" (standalone/fullscreen/minimal-ui + iOS) |
| `app/presentation/pwaRuntime.ts` | `idleReloadPathAllowed`, `shouldCheckForUpdate`, `idleUpdateBlocker`, `applyIdleUpdate` | regra pura da troca de versão: quando sondar, quando aplicar sozinho e QUAL razão impede |
| `app/composables/usePwaUpdate.ts` | `usePwaUpdate` | worker em espera + `update()` (skipWaiting + reload) + `checkForUpdate()` (sonda) |
| `app/composables/usePwaAutoUpdate.ts` | `usePwaAutoUpdate` | sonda periódica/no foco e aplicação automática em momento seguro — ver "Atualização do app instalado" |
| `app/composables/useOperatorReloadHold.ts` | `useOperatorReloadHold` | a TELA declara, pelo nome, o que impede recarregar agora (venda, comanda, pagamento) |
| `app/composables/useConfirm.ts` | `useConfirm` | a pergunta antes de descartar o que não foi salvo (ou de um ato normal, `tone: "primary"`), no diálogo da casa: devolve `Promise<boolean>` (ver "Pergunta antes de descartar") |
| `app/components/OperatorConfirmDialog.vue` | `<OperatorConfirmDialog>` | a caixa do `useConfirm`; montada UMA vez pelo `OperatorPwaRuntime`, nenhum app a monta |
| `app/utils/pwaUpdateReport.ts` | `markPwaUpdateApplied`, `reportPwaUpdateApplied` | marca a troca antes do reload e a relata no boot seguinte (→ `pwa.update_applied` no Django) |
| `app/presentation/orientationLock.ts` | `orientationFamily`, `orientationLockFailure`, `ORIENTATION_LOCK_COPY` | regra pura da trava de giro: família travada, motivo da recusa e cópia ao operador |
| `app/composables/useOrientationLock.ts` | `useOrientationLock` | trava de giro por dispositivo (Screen Orientation API): item "Travar giro" no `OperatorRail` só em dispositivo de toque; trava só com o navegador confirmando (Android/ChromeOS instalado), recusa vira aviso ("use o bloqueio de rotação do sistema") em iOS/Windows; preferência no `localStorage`, reaplicada pelo `OperatorPwaRuntime` no boot do app instalado |

Os testes também têm harness compartilhado: `tests/support/composableEnv.ts`
(`installNuxtGlobals()`, env `node` com Vue real + fronteira de dados mockada) é importado
pelos testes de composables que o adotam — os projetos `unit` desses apps
declaram `resolve.dedupe: ["vue"]` para garantir instância única do Vue.

As superfícies de operador compartilham SSO pelo domínio-pai usando
`shopman_operator_sessionid` e `shopman_operator_csrftoken`. O BFF traduz esses
nomes para `sessionid`/`csrftoken` somente na conexão interna com o Django e
descarta os cookies homônimos diretos do browser, que pertencem ao Admin. Assim,
unlock/lock troca ou encerra a sessão compartilhada dos apps de operador sem
invalidar uma sessão aberta no Admin; cookies de estação e demais cookies não
conflitantes continuam sendo repassados.

**Validade da sessão de operador (decisão de 17/09/2026): renova com o uso, expira
após 7 dias sem uso.** A sessão aberta pelas portas de operador (senha no app, PIN,
crachá) nasce marcada e com prazo de 7 dias; o uso empurra o prazo de volta para 7
dias, gravando no máximo uma vez por dia (quando restam menos de 6), e o Django
reemite o cookie com o novo `Max-Age`, que o BFF repassa como qualquer `Set-Cookie`.
O SSE não renova (o proxy de eventos não repassa cookies); a renovação vem das
requisições REST e dos polls. O Admin fica fora: segue os 14 dias fixos do Django,
com 2FA. Regra e motivo em `shopman/backstage/services/operator_session.py`;
constantes `SHOPMAN_OPERATOR_SESSION_IDLE_SECONDS` e
`SHOPMAN_OPERATOR_SESSION_RENEW_INTERVAL_SECONDS` em `config/settings.py`.

Apps que ativam `runtimeConfig.operatorSecurityHeaders` recebem documentos e APIs
privados (`private, no-store`, `Vary: Cookie`). Assets compilados mantêm o cache do
Nitro. HSTS só é emitido quando a requisição chega como HTTPS; o edge continua
responsável por preservar `X-Forwarded-Proto: https` e a verificação final deve ocorrer
no host publicado. Marketing usa ainda uma política CSP local mais estrita, com nonce e
branch de HMR limitado a desenvolvimento; essa necessidade não foi promovida ao kit
porque ainda não tem dois consumidores comprovados.

A CSP de base do kit só abre por app e por diretiva, em `runtimeConfig.operatorCspAllow`
(SEC-SURF-001, item 5). Aceitam exceção apenas `img-src`, `connect-src`, `font-src`,
`media-src` e `script-src`; `frame-ancestors`, `frame-src`, `default-src`, `style-src`,
`worker-src` e as demais nunca abrem. Nas quatro primeiras, a origem precisa ser `https:`,
um host `https://` explícito, um curinga de subdomínio sobre domínio fixo
(`https://*.googleapis.com`) ou a loopback do próprio dispositivo (`http://127.0.0.1:*`,
`http://localhost:*`). Em `script-src` o funil é mais estreito: só host `https://`
explícito com domínio (`https://maps.googleapis.com`) ou curinga de subdomínio sobre
domínio fixo; `https:`, loopback, `data:` e `blob:` são recusados ali. Em qualquer
diretiva, `*`, `https://*`, curinga sobre sufixo público (`https://*.com`,
`https://*.com.br`) e `'unsafe-*'` levantam erro. Sem a chave, a política é a de base.

A `Permissions-Policy` segue o mesmo desenho em `runtimeConfig.operatorPermissionsAllow`
(ex.: `{ camera: "self" }`): só recursos da lista de base (`browsing-topics`, `camera`,
`geolocation`, `microphone`, `payment`, `screen-wake-lock`, `usb`), e só com o valor
`"self"`; `*` ou outra origem levantam erro. Sem a chave, o header é byte a byte o de base.

Cada exceção leva no `nuxt.config` o comentário com a função que a exige, e a decisão do
dono que a autorizou. Hoje declaram exceções: Pedidos e Central (foto de produto e
ícone de app de host externo, agente de impressão do balcão), PDV (Google Maps do
autocompletar de endereço, ViaCEP, foto de produto, agente do balcão) e Compras (câmera
para ler a NF).

## Identidade do app (`app-identity.json`)

Rótulo, descrição, símbolo, cor e frase de instalação de cada app de operador vivem em
**`operator-kit/app-identity.json`**, e só ali. Um app declara em
`definePwaCapability({ app: "pos", ... })` apenas o que de facto varia: como a janela
abre, se a tela fica acesa, o que ele recebe por push e quais atalhos o SO oferece.

Estavam escritos em seis lugares (`nuxt.config`, `package.json`, `tools/pwa-gate`,
`app.vue` duas vezes, `PWA_ICONS.md`) e derivaram — a Central com ícone ardósia e barra
de título vinho, o Gestor com dois nomes, a Cozinha com três. Ver `PWA_ICONS.md` para a
tabela e para a regra "a barra de título é a cor do ícone".

O que a identidade passa a mandar, sem prop em nenhum call site: `theme_color` e
`background_color` do manifesto, `<title>` e `theme-color` do `<head>`, o rótulo e o
ícone do `<OperatorRail>` e do `<OperatorLogin>`, e o convite de instalação.

### Nome do app instalado (`"Nelson · PDV"`)

Todo app de operador instalado se chama `"<casa> · <App>"`: "Nelson · PDV", "Nelson ·
Cozinha", "Nelson · Gestor de pedidos". A loja do cliente fica fora (é "Nelson
Boulangerie").

- **A casa não mora no código.** A fonte única é `Shop.short_name` ("nome curto (PWA)",
  editável no Admin), servido por `GET /api/v1/backstage/operator/tenant/` (público,
  sem sessão: o navegador busca o manifesto sem cookie). O rótulo vem da identidade;
  nem ele nem a casa se escrevem num app.
- **Lido em runtime, não no build.** `server/utils/operatorTenant.ts` pergunta ao
  Django com cache de 5 min no processo Nitro; a mesma imagem serve todo deployment.
  Falha é macia: vale o último nome que o Django deu (nova tentativa em 30 s) e, sem
  nenhum desde o boot, o app mostra só o rótulo ("PDV"). Não há prefixo de reserva
  escrito no código ou no build — seria uma segunda fonte.
- **Manifesto e janela dizem o mesmo nome.** `/manifest.webmanifest` e
  `/_operator/app-name` usam o mesmo resolvedor. O plugin `runtime/plugins/operatorAppName.ts`
  resolve o nome no SSR (chamada local à rota Nitro), guarda no `useState` (viaja no
  payload) e instala o `titleTemplate` — também na página de erro padrão do Nuxt, que
  renderiza no lugar do `app.vue`.
- **O título começa com o `name` do manifesto.** Se não começar, o Chrome prefixa
  `"<name> - "` na barra da janela do PWA instalado. Por isso a home é `"Nelson · PDV"`,
  a página é `"Nelson · PDV · Filipetas"` e o título que pisca no Gestor também passa
  por `windowTitle`.
- **Nunca hífen na barra.** O separador é o ponto médio; `windowTitle` troca separador
  de hífen/barra que venha de título de página (a página 404 do Nuxt escreve
  "404 - Page not found | Nuxt"). `document.title` escrito à mão só passa montado por
  `windowTitle(...)` ou restaurando um valor guardado.
- **`short_name` é só o rótulo.** Ele aparece onde falta espaço (ícone no launcher
  Android), e lá a casa se repetiria em todo app e cortaria o que distingue um do outro
  ("Nelson · Pro…"). Desktop (macOS, Windows, ChromeOS) mostra o `name`. O
  `apple-mobile-web-app-title` leva o nome inteiro, que é o que o Safari propõe ao
  instalar.
- **Trocar o nome no Admin** chega ao BFF em até 5 min e ao app instalado quando o
  navegador rebusca o manifesto (`max-age=3600`, o contrato do gate estrutural de PWA); o Chrome atualiza o nome do app
  instalado na verificação periódica dele.

A trava é `tests/appName.guardrails.test.ts`: varre os oito apps (rótulo sem casa nem
separador, `nuxt.config` sem rótulo/cor/ícone reescritos, título começando pelo `name`,
nenhum título com hífen de separador, nenhum `document.title` cru, nenhum `app-label` nem
caminho de ícone escrito à mão, e a barra de título na cor do ícone). Do lado do Django,
`shopman/backstage/tests/test_hub_projection_identity.py` mantém os tiles da Central com
os mesmos nomes.

### Convite de instalação: o COMO é comum, o QUÊ é de cada app

`<OperatorPwaInstallInvite>` diz `"Instale {artigo} {rótulo}"` e, embaixo, a frase
`install` do próprio app ("Abra a fila de pedidos direto da tela inicial deste
dispositivo."). O caminho do iOS (Compartilhar → Adicionar à Tela de Início) é o mesmo em
todo app e fica no componente. Os oito diziam **"Instale Shopman"** — o componente lia
`manifest.name`, chave que o manifesto resolvido não tem, e caía no nome da marca — com
"Abra o caixa direto da tela inicial" embaixo, no B.I., na Cozinha e no Marketing.

## Navegação entre apps instalados

Com os oito apps instaláveis, sair de um para outro produzia dois sintomas ao mesmo
tempo (relatado em 17/09/2026): **uma tarja grande no topo**, como se o navegador
tivesse entrado em outro site, e **o título e a cor da barra da janela continuavam
sendo os do primeiro app aberto**, qualquer que fosse ele.

Não é estilo, é o contrato do PWA instalado. Cada app é um **host** próprio (`pdv.`,
`central.`, `cozinha.`…) e o `scope` do manifesto é por origem. Navegar no MESMO frame
para outra origem é sair do escopo: o Chrome preserva a janela — que pertence ao app
que a abriu, com o `name` e o `theme_color` DELE — e desenha por cima a barra de "você
saiu do app". Um sintoma só, visto de dois ângulos.

A saída não é esconder a barra; é **não fazer essa navegação**. O app de destino tem
janela própria, e é nela que ele deve abrir:

| contexto | como o link abre |
|---|---|
| aba de navegador | `_self` — mesma aba, como antes (`_blank` ali empilharia aba a cada troca) |
| app instalado, outra origem | `_blank` + `rel="noopener"` |
| mesma origem | `_self`, sempre |
| loja do cliente (`external`) | `_blank` + `rel="noopener"`, sempre |

⚠️ **O `noopener` aqui não é só higiene de segurança — é a condição de o link abrir no
app certo.** A captura de navegação do Chrome (ligada por padrão desde o Chrome 139) só
age sobre navegações "capturáveis": as que criam um frame novo e **não** abrem num
contexto auxiliar. Um `_blank` comum guarda `opener` e é auxiliar; com `noopener` o
contexto nasce sem opener, é capturável, e o Chrome o entrega à janela do app de
destino. Sem `noopener`, abriria uma janela solta do navegador.

E o manifesto de todo app de operador declara `launch_handler: { client_mode:
"focus-existing" }`: chegar num app que **já está aberto** traz a janela dele para a
frente e descarta o URL. `navigate-existing` recarregaria o PDV com venda na mão só
porque alguém tocou no atalho da Central — a mesma regra do `useOperatorReloadHold`.

Os dois lados do caminho usam a mesma peça: o ícone da Central no `OperatorRail` de
cada app, e os tiles da Central (`hub-nuxt`, `tileLinkAttrs`).

**O que foi recusado:** `scope_extensions` (declarar as origens irmãs como extensão do
escopo) tira a tarja, mas pelo motivo errado — passaria a rodar a Central *dentro* da
janela do PDV, e o título e a cor continuariam sendo os do PDV. É exatamente o sintoma
que se quer eliminar.

## Atualização do app instalado (`usePwaAutoUpdate`)

Medido em 17/09/2026: depois dos deploys das PRs #783 e #789 o contêiner do grupo
`operator-floor` reiniciou com a imagem nova, e o PDV instalado como PWA no desktop
seguiu rodando o bundle antigo — nenhuma chamada de capacidade veio dele depois do
restart, o cliente velho continuava ativo. A causa não foi o deploy: com
`registerType: "prompt"`, `skipWaiting: false` e `clientsClaim: false`, o worker novo
fica em **waiting** até TODAS as janelas do host fecharem, e o aviso só aparece se o
navegador chegar a buscar o `sw.js`. Kiosk e PDV instalado não fecham nunca.

O contrato tem três peças, e nenhuma delas interrompe operação:

**1. Sondar.** `usePwaAutoUpdate` chama `registration.update()` a cada 30 min e ao
voltar do segundo plano, ganhar foco ou reconectar (com piso de 60 s entre sondas,
porque esses gatilhos chegam em rajada ao acordar). Sem a sonda, o navegador só procura
`sw.js` novo em navegação de documento.

**2. Aplicar.** Havendo versão em espera, o aviso ao operador (`OperatorPwaUpdatePrompt`)
continua exatamente como antes. Em paralelo, a versão entra **sozinha** quando as três
condições valem juntas: a rota está em `idleReloadPaths`, a superfície está ociosa
(60 s sem toque) e **nenhuma razão de `useOperatorReloadHold` está de pé**. Faltando
qualquer uma, `blocker` diz qual.

```ts
// Na tela que tem rascunho na mão (PDV, pages/index.vue):
const { hold } = useOperatorReloadHold();
watchEffect(() => {
  hold("tab_open", Boolean(cart.tabRef));
  hold("payment_open", checkoutMode.value || pixStatus.value === "polling");
});
```

Quem declara a rota segura é o app, em `definePwaCapability({ idleReloadPaths })`:
`"*"` no KDS (nenhuma tela dele tem rascunho), `"/board"` na Produção (preserva os
editores de receita), `"/"` no PDV (**só a raiz** — `/session` tem contagem digitada e
`/display` nunca é tocada, então seria "ociosa" para sempre). Lista vazia (Central,
Gestor, Compras, B.I., Marketing) mantém só o aviso.

⚠️ **`skipWaiting` vale para a ORIGEM inteira.** Quem aplica não recarrega só a si: o
`vite-plugin-pwa` registra, em **toda** janela que viu o worker em espera, um listener de
`controlling` que chama `location.reload()`. Duas consequências: (a) janelas irmãs do
mesmo host entram na versão nova juntas, de graça; (b) uma janela que nunca é tocada —
a tela do cliente do PDV — não pode estar em `idleReloadPaths`, porque ela seria
considerada ociosa sempre e quem recarregaria no meio da venda seria a janela do
operador. Apps diferentes são hosts diferentes (`pdv.` × `cozinha.`), então nada disso
atravessa de um app para outro.

ℹ️ **Abrir uma janela nova já traz a versão nova**, mesmo com o worker velho ativo:
a navegação é `NetworkOnly`, o HTML fresco aponta para arquivos com hash novo, e o
precache do worker velho não tem esses nomes — deixa passar para a rede (conferido no
build do PDV: o manifesto de precache não tem nenhuma entrada de navegação, só
`offline.html`). Quem fica preso numa versão é a janela que **não recarrega**, não a que
abre. É por isso que abrir a tela do cliente no PDV leva junto um `checkForUpdate()`:
a janela nova não precisa de ajuda, a do operador precisa.

**3. Provar.** A troca termina em `location.reload()`, e nada que fique na memória
sobrevive para contar o que houve. Então a marca vai ao `localStorage` **antes** do
reload e é relatada no boot seguinte, quando as duas versões são conhecidas:
`POST /api/v1/backstage/client-pwa-update/` → `pwa.update_applied` nos logs do Django,
com `app`, `trigger` (`prompt` | `idle`), `from_version` e `to_version`.

**Cabeçalhos.** `/sw.js` e `/operator-push-sw.js` saem com
`cache-control: no-cache, no-store, must-revalidate` (route rule da capability e handler
do push); `/manifest.webmanifest` com `public, max-age=3600` — ele não decide versão de
código. O roteador por Host (`surfaces/operator-router`) repassa tudo intacto, e cada
host serve o SEU worker; a trava está em `operator-router/test/router.test.mjs`.

## Barra de seções (`<OperatorAppBar>`)

O cabeçalho que fica no topo do CONTEÚDO — não é o rail. Ele carrega o `RailToggle`, a
navegação de seções do app e um cluster de ações à direita.

```vue
<OperatorAppBar :sections="sections" label="Seções do Gestor">
  <template #end><UiIconButton icon="lucide:refresh-cw" label="Atualizar" /></template>
</OperatorAppBar>
```

`sections` é uma lista de `OperatorSection` (`app/presentation/appBar.ts`):

| campo | serve para |
|---|---|
| `key` | identidade da seção — é o que o app compara e o que o teste nomeia |
| `label` · `icon` | o que aparece na aba (ícone `lucide:*`) |
| `to` | rota da seção. **Sem `to`, a aba vira botão** e a barra emite `select` — é como o Compras funciona, porque a seção dele é estado (`useState`), não rota |
| `match` | outras rotas que PERTENCEM à seção (`/channels` dentro de Canais, `/templates` dentro de Campanhas) |
| `attention` | aviso curto ao lado do rótulo ("1 desligado"). Ausente = estado normal, sem ruído |
| `shortcut` | a tecla que leva à seção, ENSINADA na própria aba e anunciada em `aria-keyshortcuts` |

A seção ativa sai da rota por `activeSectionKey()`, que é pura e tem teste: vence o
prefixo mais longo, `/` não é prefixo de ninguém, barra final e query não mudam nada, e
rota desconhecida cai na seção raiz — a barra nunca fica sem nenhuma aba acesa, porque
"nenhuma acesa" é a tela dizendo que o operador está em lugar nenhum.

**Por que isto virou peça da layer.** Quatro apps desenhavam a mesma barra à mão e, na
medição de 22/09/2026, "a mesma" já não era a mesma: `min-h-control` (44px) no Gestor,
`h-11` no Marketing e **`h-8`** no B.I. e no Compras — metade do alvo de toque que o
token `--spacing-control` define para a casa, numa barra usada com a mão ocupada. O
`chipClass(active)` do B.I. e o do Compras eram cópia byte a byte. E a aba ativa só era
trazida para dentro da área visível no Marketing — onde o defeito tinha aparecido de
verdade: a 390px cabem duas abas e meia, e em `/platforms` a seção ativa nascia fora da
tela, então o gestor lia a barra e concluía que estava no Painel. Agora isso vale para
todos, junto com o `aria-current="page"` e a remedida depois de `document.fonts.ready`.

**Cabeçalhos ainda não convertidos** — PDV, Cozinha, Produção e Hub — carregam estado
próprio (comanda editável, relógio e dia operacional, progresso do dia, saudação). Não
são deriva: são cabeçalhos ricos, e a conversão é WP próprio.
`tests/guardrails.appBar.test.ts` guarda a lista deles e impede que ela CRESÇA em
silêncio — arquivo novo com `<header>` + `<RailToggle>` reprova até alguém adicioná-lo
de propósito, escrevendo por quê.

## Camada visual da suíte (UX-KIT-V1: rail, cabeçalho, busca, tokens)

O rosto das prévias aprovadas (SUITE-UX-FUNCTION-PLAN §12: "a camada visual da v3,
tokens, rail, cabeçalho, busca, é o rosto das peças"). **É opt-in, por app**: quem não
migrou não muda um pixel. O Gestor é o piloto; os outros apps entram um a um, o PDV por
último.

Como um app migra:

1. Põe `data-suite="v3"` no elemento raiz do `app.vue`. Os primitivos do kit
   (`UiFilterChip`, `UiSearchInput`, `UiIconButton`) trazem o visual novo
   atrás da variante `suite:` e só a vestem dentro desse atributo.
2. Troca `OperatorRail` + `<OperatorAppBar>` por `<OperatorSuiteRail>` (as mesmas
   `OperatorSection`, agora dentro do rail, do tablet para cima) e monta
   `<OperatorSectionBar>` no fim da coluna de conteúdo (as mesmas seções embaixo, no
   celular e no tablet em pé, com o "Mais"; passe `operator-name` e `@lock`). O pé do
   rail é do kit (Avisos, Atalhos, Bloquear, iniciais); o slot `#foot` é só para o que
   é do app antes do traço (o Terminal do PDV). Alertas da operação entram na caixa de
   Avisos por `provideOperatorInboxAlerts`; teclas da tela, na ajuda de atalhos, por
   `provideOperatorShortcuts`.
3. Cada tela abre com `<OperatorPageHeader title="…">`: `#status` (o
   `<OperatorLiveStatus>` e pílulas), `#search` (a busca da suíte, uma vez só; ver abaixo),
   `#actions` (controles), `#filters` (recortes na segunda linha), `#lead` (o voltar),
   `#phone-actions` (ações de polegar da tela na barra de 56px; Avisos o kit já põe).

| peça | o que é | medida da prévia |
|---|---|---|
| `operator-suite.css` | papéis tipográficos `op-display/op-heading/op-figure/op-title/op-body/op-label/op-micro/op-eyebrow`, `tnum`, `live-dot`, `pill-*`, o selo âmbar (`suite-badge`) e a variante `suite:` | `_shared.css` |
| `OperatorSuiteRail` | rail de 76px no tablet deitado e no desktop (variante `rail:`): selo do app na cor dele (volta à Central), seções com ícone, nome, tecla Alt 1…9, selo e ponto; pé da v4 (seções do pé, traço, Avisos, Atalhos, Bloquear, iniciais; `foot-order="inbox-first"` para a Cozinha); "?" e Alt+N | `_rail3top.html`, `_rail3bottom.html` |
| `RailSection` | o item do rail (64px de largura, ≥ 44px de altura, inativo a 80%, ativo com fundo na cor do texto do rail; no toque, `shortLabel` ou só o ícone) | `.rail-item` |
| `OperatorSectionBar` | barra de baixo no celular e no tablet em pé: até 4 seções + "Mais" (o resto, o slot `#more` e o menu do operador) | `orders-phone3.html`, `cozinha-celular4.html` |
| `OperatorPageHeader` | cabeçalho de uma linha; sem rail, barra de 56px com selo, título, ponto ao vivo, lupa, ações de polegar e Avisos; o posto do dispositivo no eyebrow; controles e recortes descem para linhas que rolam | `orders-board3.html` |
| `OperatorToolbar` | a barra de trabalho que o app monta sem tocar a estrutura do Nuxt UI (o ledger proíbe `NuxtDashboardToolbar` direto nos apps): camada fina sobre o `NuxtDashboardToolbar`, slots `#left`, `#right` e o padrão (que ocupa a barra inteira, como no oficial), `as` = `div` (padrão), `header` ou `footer`; `class`, `data-*` e `aria-*` chegam ao elemento. Sem pele própria: o fundo vem do tema (`dashboardToolbar.slots.root` em `app.config.ts`) | DashboardToolbar do Nuxt UI |
| `OperatorLiveStatus` | o ponto ao vivo com a hora; fora do ao vivo o estado se escreve por extenso | `.live-dot` |
| `OperatorInbox` | "Avisos": UM item no rail e UM sino na barra de 56px; um painel (portal) com duas abas, a operação (alertas do app, capacidade acima do limite) e a caixa pessoal (avisos, Meus acessos); um selo somado | `_rail3bottom.html` |
| `OperatorShortcutsHelp` | a ajuda de atalhos de todo app: "Em todo o app" (Alt 1…9, "?") e os grupos da tela | "Atalhos (?)" de `_rail3bottom.html` |
| `OperatorPhoneMenu` | o menu do operador sem o rail: o "Mais" da barra de baixo (`variant="bar"`) ou as iniciais na barra de 56px (`variant="header"`, a Central) | menu de `_rail3bottom.html` |
| `OperatorMenuItems` | o conteúdo do menu do operador (posto, Bloquear no celular, tema, giro, capacidade do serviço escrita) | menu de `_rail3bottom.html` |
| `OperatorAppSeal` | o selo do app na barra de 56px dos cabeçalhos próprios (PDV, Central) | `_rail3top.html` |
| `OperatorSwipeRow` | deslizar uma linha no toque (F7, 09/10/2026): à esquerda revela `actions` (gaveta que fica aberta depois da metade); à direita faz `commit` depois do ponto de compromisso, com o verbo e o alvo atrás da linha. Mouse não desliza; o eixo se decide no começo (rolar nunca vira deslize); `motion-safe:` na volta. Nunca a única porta: o mesmo ato existe num botão visível, e a camada de trás é `aria-hidden` | `cozinha-celular` (a), v4 |
| `OperatorThumbAction` | o polegar do celular: o gesto principal da tela num botão `xl` largo, preso na base da área que rola (`data-focus-obstruction`), com o verbo e o alvo ("Entregar U13 a Ana"). Um por tela, só abaixo de `md` | `cozinha-celular` (a), v4 |

**O título da barra do topo não se corta** (PR-K5, achado do B.I. a 390 px: "Quem compra
no balc…"). O `NuxtDashboardNavbar` oficial leva `truncate` no título; o tema do kit
(`dashboardNavbar` em `app/app.config.ts`) o troca por quebra de linha (`text-clip
whitespace-normal`, sem `line-clamp`) e a barra passa de `h-(--ui-header-height)` a
`min-h-(--ui-header-height)`: com título de uma linha ela segue com 56 px; com título
longo, cresce e mostra o título inteiro. A coluna da direita é `shrink-0` no oficial: o
título quebra antes de empurrar a lupa, as ações e Avisos para fora. Vale para toda barra
do topo (o `OperatorPageHeader`, o `OperatorOfficeShell`, a do Kitchen Sink operacional,
em `?mode=operational`). Não há `short-title`: o título é o mesmo `h1` para quem enxerga
e para o leitor de tela, e uma tela que precise de título curto o escolhe curto.

Opções do rail e da barra (todas opcionais): `print-shortcuts` (padrão ligado) imprime
a tecla de cada seção sob o nome ("Alt1"), só com ponteiro fino; `dense-labels` usa
rótulos de 10px para nomes longos ("Planejamento"); `OperatorSection.shortLabel` encurta
o rótulo na barra e no rail de toque ("Plano"); `where: "rail" | "bar"` põe a seção num
lugar só; `divider` desenha um traço acima dela no rail.

Onde mora a navegação (V6-KIT, `depois-navegacao.jpg`): rail no tablet deitado e em
qualquer tela de 1024px para cima; no celular e no tablet em pé, barra de 56px em cima e
seções embaixo. A régua é uma só: a variante `rail:` no CSS e `useSuiteRailShown()` no
script. Alvos ≥ 44px em tudo (as prévias tinham chips de
40px: aqui ficaram com 44). `prefers-reduced-motion` desliga as transições dentro de
`data-suite`. Contrato em `tests/components/SuiteChrome.test.ts`;
`tests/guardrails.appBar.test.ts` lista quem migrou.

## Conjunto mínimo da suíte (dono, 08/10/2026)

Aprovado no PR #1539, sobre o laudo `docs/plans/WP-BI-CANON-LAUDO.md` (seção F). A
referência viva é a página `/proposal` do Kitchen Sink. O tema do kit (`app/app.config.ts`
e o módulo em `nuxt.config.ts`) fixa o default de cada peça, e a trava
`tests/guardrails.minimalSet.test.ts` conta o que ainda foge do conjunto: o número só
cai. Uso novo fora do conjunto reprova; migrar um uso antigo baixa o teto.

| peça | conjunto | como se escreve |
|---|---|---|
| Botão | tamanho `md` (todo lugar) e `xl` (toque crítico: PDV, Cozinha, quiosque, teclado numérico); variante `solid` (o gesto principal, um por região), `outline` (secundário) e `ghost` (terciário, ícone, menu); cor `primary`, `neutral` e `error` | estado ativo por `active` + `active-variant`/`active-color`, nunca `:variant="ativo ? … : …"`. Botão só de ícone é `square`. Aviso, informação e sucesso moram no selo ou no aviso, não na cor do botão; a exceção é a ação de aviso (abaixo). O default continua o do Nuxt UI (`primary` `solid` `md`): trocá-lo repintaria em silêncio todo botão sem cor escrita |
| Selo (Badge) | uma variante, `soft` (sem borda), nas 6 cores `neutral`, `primary`, `info`, `success`, `warning`, `error` | o tema dá `soft` (`badge.defaultVariants`); ninguém escreve `variant` num selo. O `primary` usa a tinta `--primary-ink` (AA) |
| Cartão (Card) | `outline` no topo; `soft` para cartão dentro de outro cartão (só fundo, sem borda dupla) | `outline` é o default; o aninhado escreve `variant="soft"` na chamada. `subtle` e `solid` não entram. Destaque navegável é `NuxtPageCard` |
| Aviso (Alert) | `subtle` × `info`, `success`, `warning`, `error` | fundo opaco pré-composto no tema (compoundVariants). `primary` e `neutral` ainda têm uso e morrem com a migração deles; `secondary` saiu |
| Cores geradas | `primary`, `info`, `success`, `warning`, `error` (e o `neutral`, que o Nuxt UI sempre gera) | `theme.colors` no módulo: cor que não é gerada não existe no tipo do `color` |
| Escolha numa lista | `NuxtSelect` (lista curta e fixa) e `NuxtSelectMenu` (longa, buscável ou que cresce) | ver abaixo. `UiNativeSelect` está aposentado |
| Texto | 5 tamanhos: `text-xs` 12 (rótulo e meta), `text-sm` 14 (texto corrido e controles), `text-base` 16 (título de cartão), `text-xl` (título de tela), `text-2xl` (figura); 2 pesos: `font-medium` e `font-semibold` | nenhum tamanho arbitrário novo (`text-[13px]`, `text-[0.625rem]`); a trava conta os que existem. Os papéis `op-*` de `operator-suite.css` ainda não foram reduzidos a esses cinco |
| Chip | ponto (estado) e número (contagem) com anel de 2 px (`chip.slots.base: 'ring-2'`, o traço dos ícones Lucide), na cor do fundo onde o chip está (`ring-bg`) | exceção declarada: o tamanho `4xl` numerado (16 px, texto 12 px), porque o `3xl` oficial não lê dois dígitos. Número acima de 99 escreve "99+" |
| Rail | dourado pelo tema: `ui.dashboardSidebar.slots` (`root` e `content`) redefine os tokens do Nuxt UI só dentro do rail (`--ui-text*`, `--ui-primary`, `--primary-ink`, `--ui-bg` = `--rail`, `--ui-border`) | nenhuma tela passa `:ui` ao rail. Três estados e sinais no `OperatorSuiteShell` (PR-K4): ver "Barra lateral em três estados" abaixo |
| Raio | ainda o do kit (`--radius` e `--radius-sm/md/lg/xl` em `operator-base.css`) | `--ui-radius` não entrou: nenhum valor único reproduz os raios de hoje (ver o PR-K3) |

**Exceção declarada: a ação de aviso repete a cor do aviso** (dono, 08/10/2026, PR #1545).
O botão de ação dentro de um `NuxtAlert` (no slot `#actions`, no `#description`, ou
declarado em objeto no prop `actions`) usa a cor do próprio aviso: `warning`, `info`,
`success` ou `error`. É a saída daquele aviso; neutro, ele se descola do estado que o
chamou. Fora de um aviso, a cor do botão continua `primary`, `neutral` ou `error`. A
trava `guardrails.minimalSet` não conta em `buttonColor` o botão dentro de um aviso cuja
cor é a do aviso (com a cor do aviso ligada, qualquer cor de aviso passa).

### Rail da suíte em três estados (`OperatorSuiteShell`)

### Barra lateral em três estados (`OperatorSuiteShell`)

Na tela, a peça se chama **barra lateral** (dono, 08/10/2026, PR #1544): nenhum texto
visível nem `aria-label` diz "rail". No código, `rail` continua sendo o nome
(`SUITE_RAIL_*`, `data-suite-rail`, `useSuiteRail`).

Aprovado pelo dono em 08/10/2026 (PR #1539; referência viva em
`kitchensink-nuxt/app/pages/proposal/rail.vue` do branch da proposta). Montado só com
peças oficiais: `NuxtDashboardGroup` (`unit="rem"`), `NuxtDashboardSidebar`
(`collapsible`, `resizable`, 12 a 20 rem aberto, `collapsed-size` 4) e
`NuxtNavigationMenu` vertical com `tooltip` e `popover`. Nenhum `:ui` por instância; o
dourado mora no `ui.dashboardSidebar` deste `app.config`.

| Estado | O que é | Onde mora |
| --- | --- | --- |
| aberto | ícone e nome; a borda redimensiona de 12 a 20 rem | cookie do DashboardGroup (`<storage-key>-sidebar-suite`: `{ size, collapsed }`) |
| compacto | só ícone; o nome (com o sinal) vira tooltip | o mesmo cookie |
| oculto | o sidebar não é montado (só desktop) | cookie do kit `<storage-key>-rail-hidden` |

- **Um botão só** na barra do topo (`OperatorPageHeader`, `data-rail-cycle`, a partir de
  `lg`) percorre aberto → compacto → oculto → aberto; o ícone e o `aria-label` dizem o
  PRÓXIMO estado ("Compactar a barra lateral", "Ocultar a barra lateral", "Mostrar a
  barra lateral"). A tecla
  **C** faz o mesmo (`SUITE_RAIL_SHORTCUT`, listada na ajuda de atalhos). O shell
  entrega o controle à barra por `provideSuiteRail`/`useSuiteRail`; fora do shell a
  barra segue como era.
- Ao voltar do oculto, o sidebar remonta e relê o cookie (compacto): o shell reafirma
  o aberto depois da montagem.
- Arrastar alterna aberto e compacto (canônico); ocultar não é por arrasto. Abaixo de
  `lg`, o comportamento oficial: a barra lateral abre como slideover (a gaveta) pelo ☰
  da barra do topo, e a barra inferior fica embaixo (ver "Barra lateral e barra
  inferior").
- Sem o rail na tela (oculto ou abaixo de `lg`), Avisos sobe para a barra do topo.
- **Sinais** (`sectionRailSignal`, `railSignalChip`, `railSignalLabel` em
  `presentation/suiteChrome.ts`): `badge` numérico maior que zero vira número (`4xl`
  do kit, `inset: false`, "99+" acima de 99); `attention` vira ponto (tamanho padrão do
  NavigationMenu). A cor é `tone` da seção (`success`, `warning` padrão, `error`).
  Compacto: chip no canto do ícone (`chip` do item). Aberto: o MESMO chip na ponta
  direita da linha (slot `item-trailing`, `standalone`). Tooltip e `aria-label`:
  `sectionDescription(section)`, "Seção · estado" ou "Seção · N pendências"
  ("1 pendência").
- O pé: seções do pé do app, Atalhos (só ponteiro fino), Bloquear, Avisos e o menu do
  operador (o "Ocultar a barra lateral" do menu leva ao estado oculto).

Contrato em `tests/components/OperatorSuiteShell.test.ts` e `tests/suiteChrome.test.ts`.

### Barra lateral e barra inferior

Regra única para todo app do shell, inclusive app novo (dono, 08/10/2026, PR #1544):

- **Gaveta** (a barra lateral pelo ☰, abaixo de `lg`) = o menu **completo** do app.
  Sempre disponível.
- **Barra inferior** (`OperatorQuickBar`, só abaixo de `lg`) = o menu **rápido**, de
  **3 a 5 vagas**, escolhidas por importância de uso.

O contrato (`quickBarLayout` e `quickBarProblems` em `presentation/suiteChrome.ts`):

| O app declara | A barra mostra |
| --- | --- |
| nada | as primeiras seções, até 4, e "Mais" quando sobra seção |
| `quick: true` em 1 a 4 seções | essas, na ordem da lista, e "Mais" se alguma ficou de fora |
| `quick: true` em 5 seções | as cinco, **sem** "Mais" (o ☰ já leva ao completo) |
| `quick: true` em mais de 5 | o kit corta em 5, e `quickBarProblems` acusa |

- "Mais" abre a gaveta; só existe quando sobra seção.
- Menos de 3 vagas (seções + "Mais") é erro de configuração, que o teste das seções do
  app acusa com `expect(quickBarProblems(sections)).toEqual([])`. App com menos de 3
  seções ao todo mostra todas, sem erro.
- **Exceção** só declarada com motivo: `quickBarProblems(sections, "motivo")` dispensa o
  mínimo (nunca o máximo). Hoje não há nenhuma.
- Seção com `where: "rail"` não entra na barra inferior.
- **Desenho**: o exemplo oficial "With bottom tab bar" do `NavigationMenu`
  (<https://ui.nuxt.com/docs/components/navigation-menu#with-bottom-tab-bar>):
  horizontal, `class="w-full"`, ícone em cima e rótulo embaixo, ativo pelo `active` do
  item. O `:ui` do exemplo mora UMA vez no `OperatorQuickBar`, nunca nas telas; o
  `text-[10px]/3` do rótulo é o valor da documentação, exceção declarada no teto da
  trava do conjunto mínimo. O kit soma a fixação embaixo, a área segura
  (`pb-[env(safe-area-inset-bottom)]`) e o alvo de toque (`min-h-control` no link).
- **Sinal**: o mesmo chip da barra lateral (`chip` do item: ponto, ou número `4xl` com
  `inset: false`), e a mesma descrição.

**Descrição de contagem única.** Barra lateral, gaveta e barra inferior dizem a mesma
coisa da mesma seção, por `sectionDescription`: "Seção · N pendências" ("1 pendência")
ou "Seção · estado". A seção não traz contagem por extenso própria (o antigo
`badgeLabel` saiu: a Saída era "2 pedidos na Saída" embaixo e "2 pendências" ao lado).
A barra lateral e a barra do polegar dos apps ainda fora do shell
(`OperatorSuiteRail`, `OperatorSectionBar`) usam a mesma descrição.

Os apps ainda fora do shell seguem com a barra do polegar antiga (`OperatorSectionBar`:
até 4 + "Mais", com o "Mais" guardando também o menu do operador, porque lá não há
gaveta) até a onda de cada um.

Contrato em `tests/suiteChrome.test.ts` (máximo 5, mínimo 3, "Mais" só quando sobra) e
`tests/components/OperatorSuiteShell.test.ts`.

**O desenho das duas barras de baixo é um só** (`TAB_BAR_UI` em
`presentation/tabBar.ts`): a barra inferior do shell (`OperatorQuickBar`) e a barra do
polegar dos apps ainda fora do shell (`OperatorSectionBar`, com o "Mais" como item da
mesma barra). Ícone em cima, nome **inteiro** embaixo: o rótulo quebra em vez de cortar
(o oficial leva `truncate`, e a 320 px o Marketing dizia "De…", "Age…", "En…").

### Régua de tela (`useScreen`)

Uma régua só, a do CSS: `useScreen()` devolve `belowSm`, `belowMd`, `belowLg` e
`belowXl`, as mesmas bordas do `max-sm:`/`max-md:`/`max-lg:`/`max-xl:` do Tailwind
(`presentation/screen.ts`). O servidor não sabe a largura, então **até a hidratação
terminar toda leitura responde "mesa"** (falso), no servidor e no cliente; depois, a
largura real entra como reatividade comum. Tela montada depois da hidratação (navegação
interna) já nasce com a largura real.

- O que é **só apresentação** decide no CSS (`max-sm:hidden`, `hidden md:inline-flex`):
  o servidor já desenha certo e nada troca.
- O que **muda a árvore** (slot, `v-if`, prop de componente, ações da barra) lê
  `useScreen()`. Nunca `useMediaQuery` de largura na tela, nunca `ssrWidth`: a árvore
  hidratada tem de ser a que o servidor mandou.
- Dado lido só no cliente (`useFetch` com `server: false`) segue a mesma regra: o
  esqueleto aparece também antes de hidratar (`pending || !screen.ready`), senão o
  cliente hidrata um nó que o servidor não mandou.

Por quê (alpha, 09/10/2026): o Gestor tinha a régua redeclarada em dez telas (`isNarrow`
valia 639 px em nove e 1279 px na fila) e decidia `v-if` com ela. Na carga direta no
celular (recarregar, PWA, link) a Fila ficava no esqueleto para sempre (`Cannot read
properties of null (reading 'emitsOptions')`) e a toolbar do Histórico, dos Clientes e do
Catálogo sumia. Travas: `tests/guardrails.screen.test.ts` (só a régua e o rail usam
`useMediaQuery` no kit; Gestor e Cozinha são zero; os apps não migrados têm teto que só cai) e
`orders-nuxt/tests/ssr/directLoadPhone.spec.ts` (build de produção, 390 e 1440 px, toda
rota aberta direto: nenhum mismatch, nenhum erro de página).

### Barra do topo no celular

Regra única para todo app (dono, 08/10/2026: "no mobile tem muitas opções na navbar
superior que estão se sobrepondo"). Abaixo de `sm`, a barra do topo
(`OperatorPageHeader`) mostra no máximo:

- **☰** (a gaveta, no shell);
- **o título**, que quebra em até 2 linhas e nunca se corta (a coluna da esquerda ocupa
  a sobra: `dashboardNavbar.slots.left`/`title` em `app.config.ts`);
- **até 2 ícones fixos**: Avisos (onde a barra lateral não está) e a Busca, ou a ação da
  tela de `priority` menor que a da Busca (`SEARCH_PRIORITY`);
- **um ⋯ "Mais ações"** (o `OperatorMoreMenu`, ver "Peças de tela") com todo o resto,
  na ordem declarada. A
  Busca que perde a vaga vira "Buscar" no ⋯.

O que **não** fica na barra: o estado (`#status`, o selo ao vivo) e o posto do
dispositivo descem para uma segunda linha da barra (`data-page-header-status`), em vez de
se espremer por cima do título. O selo do app sai da barra no shell (a gaveta o mostra no
topo). Controles de leitura (período, frescor, recortes) moram na toolbar, nunca na barra.

A tela declara as ações como **dados**, e o kit decide o que transborda
(`phoneHeaderLayout` em `presentation/pageHeader.ts`):

```vue
<OperatorPageHeader
  title="Pedidos"
  :actions="[
    { label: 'Visto', icon: 'i-lucide-check', priority: 1, onSelect: ack },
    { label: 'Atualizar', icon: 'i-lucide-refresh-cw', onSelect: refresh },
    { label: 'Exportar CSV', icon: 'i-lucide-download', onSelect: exportCsv },
  ]"
  actions-label="Mais ações da fila"
/>
```

- Com `actions`, o `#actions` some abaixo de `sm` (o que importa ao polegar está nos
  dados); do `sm` para cima, nada muda: o `#actions` segue como está e as ações
  declaradas aparecem num ⋯ ao lado dele. Quem tem as mesmas ações no `#actions` passa
  `actions` só no celular (`isNarrow ? [...] : undefined`), como o Gestor.
- Página de leitura: `useReadingPageActions(items)` dá "Copiar link desta leitura" mais
  as da página, e o nome do ⋯ (`actions-label`).
- `#phone-actions` é para o ⋯ PRÓPRIO da tela, quando o menu é um painel e não uma lista
  (o pedido do Gestor): conta como o ⋯.

Trava: `tests/pageHeader.test.ts` (quem ganha a vaga, nada se perde) e
`tests/catalog/phone-header.spec.ts` (no navegador, a 320 e a 390 px, na bancada
`/__operator_kit_catalog/phone-header`: nenhuma caixa se cruza ou sai da largura, título
inteiro em até 2 linhas, no máximo 3 controles à direita, todas as ações no ⋯).

### Toolbar no celular

Abaixo de `sm`, no shell (`phone-filters="drawer"`, o padrão com `OperatorSuiteShell`),
a toolbar do cabeçalho é **uma linha só, de altura fixa**:

| slot | do `sm` para cima | abaixo do `sm` |
| --- | --- | --- |
| `#filters-primary` | começo da linha | na linha (até 2 controles; o período em `compact`) |
| `#filters` | a linha de sempre | no painel "Filtros" (`NuxtDrawer` de baixo), inteiros e rotulados, com "Limpar" e "Ver resultados" |
| `#filters-end` | fim da linha (o frescor, a contagem) | faixa de texto logo abaixo da linha (ou na linha, se não há primário) |
| `active-filters` | (a própria barra mostra) | número no "Filtros" e chips removíveis numa faixa que rola, só quando há algum |

- O botão "Filtros" só existe se há `#filters`; abaixo de 360 px ele fica só com o
  ícone (o nome segue no `aria-label` e no `title`).
- `clear-filters` faz o "Limpar"; sem ele, o kit remove cada recorte ativo.
  `filterBarActiveFilters(dimensions, filtros, atualizar)` converte os campos da
  `FilterBar` em recortes ativos.
- Aba ou segmentado com mais de 4 opções vira `NuxtSelect` no celular (a Coleção do
  Catálogo); com até 4, rola na horizontal, sem cortar rótulo.
- Ação não é filtro: "Atualizar", "Exportar", "Admin" vão para as `actions` da barra,
  nunca para o painel "Filtros".
- Os apps ainda fora do shell seguem com a linha de sempre (`row`) até a onda de cada um;
  `phone-filters="drawer"` os traz antes.

Trava: `tests/catalog/phone-header.spec.ts` (linha de no máximo 64 px, primário sem
rolagem escondida, o painel abre, o recorte vira chip e sai pelo ×).

### Escolha numa lista: `NuxtSelect` e `NuxtSelectMenu`

`UiNativeSelect` **está aposentado** (dono, 08/10/2026): nada de lista do sistema, em
nenhum dispositivo. Os usos de hoje (43, nos apps ainda não migrados) são teto no ledger
(`ui_native_select_occurrences` em `docs/reference/operator-component-ledger.json`,
conferido por `scripts/check_operator_component_ledger.py`): o número só cai, e nenhum
uso novo passa. Escolha nova nasce em Nuxt UI:

- **Lista curta e fixa:** `NuxtSelect`.
- **Lista longa ou que cresce:** `NuxtSelectMenu` com busca. A busca recebe o foco ao
  abrir só onde há teclado físico; no toque, o teclado virtual sobe quando a pessoa toca
  na busca:

```vue
<script setup lang="ts">
import { useMediaQuery } from "@vueuse/core";
const touch = useMediaQuery("(pointer: coarse)");
</script>

<template>
  <NuxtSelectMenu v-model="product" :items="products" :search-input="{ autofocus: !touch }" />
</template>
```

O `UiSelect` também fica fora do conjunto: escolha nova não nasce nele.

### Cartão dentro de cartão

O cartão de topo é `outline` (borda e fundo do cartão). Um cartão dentro dele (o lote
dentro do plano, o item dentro do pedido) é `variant="soft"`: só o fundo, sem a segunda
borda. A regra mora na chamada, não no CSS: um seletor que adivinhasse o aninhamento
pintaria errado o cartão que só está dentro de uma coluna.

## Peças de tela (fase 2)

As atividades comuns do operador, uma peça para cada uma
(`docs/plans/WP-FASE2-UX-OPERADOR.md`). Cada peça nasce aqui com teste, entra no
catálogo do kit (Kitchen Sink, seção "Peças de tela",
`OperatorKitchenSinkScreenPieces.vue`) no mesmo PR, e o `:ui` mora uma vez na peça.

### Mais ações: o ⋯ único (`OperatorMoreMenu`)

Um ⋯ só na suíte, o mesmo no cabeçalho, no cartão, na linha da tabela e no quadro de
leitura, no celular e na mesa. A tela declara as ações como **dados**; a peça desenha o
botão e o menu:

```vue
<OperatorMoreMenu
  label="Mais ações do pedido 1048"
  :items="[
    [
      { label: 'Atender este pedido', icon: 'i-lucide-user-plus', onSelect: assign },
      {
        label: 'Voltar para a Cozinha',
        icon: 'i-lucide-rotate-ccw',
        disabled: true,
        reason: 'A Cozinha já fechou o pedido 1048.',
      },
    ],
    [{ type: 'label', label: 'Leitura' }, { label: 'Atualizar', icon: 'i-lucide-refresh-cw', kbds: ['R'], onSelect: refresh }],
    [{ label: 'Cancelar pedido', icon: 'i-lucide-x', color: 'error', onSelect: cancel }],
  ]"
/>
```

- **Os itens** têm o formato do `NuxtDropdownMenu` (`OperatorMoreMenuItem`,
  `presentation/moreMenu.ts`): lista simples ou lista de grupos, o rótulo de grupo é um
  item `type: "label"`, a destrutiva é `color: "error"`, atalho em `kbds`, link em `to`.
  Grupo vazio, ou só com o rótulo, some.
- **`reason`**: o motivo de uma ação desabilitada, escrito sob o rótulo (no toque não há
  dica de ponteiro). Ação desabilitada por regra do negócio leva motivo; a desabilitada
  só enquanto um pedido anda dispensa.
- **`label`**: o nome do ⋯, o que ele guarda ("Mais ações do pedido 1048", "Mais ações de
  Pão francês"). Vira `aria-label` e `title`. Padrão: "Mais ações".
- **O botão** é sempre o mesmo: reticências deitadas, `ghost`, `neutral`, quadrado. Nada
  de `outline`, nada de reticências de pé, nada de botão rotulado.
- **Texto da casa não se corta**: o rótulo e o motivo quebram linha, e o menu não passa
  da largura que sobra na tela.
- Atributos (`class`, `data-*`) chegam ao botão; `v-model:open` controla o menu; slot de
  item (`slot: "freshness"` → `#freshness`) passa direto.
- **As ações da barra do topo são o mesmo formato**: o ⋯ do `OperatorPageHeader` (as
  `actions`) é esta peça, e `OperatorHeaderAction` aceita `reason`. O quadro de leitura
  (`OperatorReadingCard`) e o ⋯ da página de leitura (`OperatorReadingPageMenu`) também.

O que **não** é este ⋯: o "Mais" da barra inferior e o menu do operador (navegação, não
ação), e o ⋯ que abre um **painel** (o pedido do Gestor, com o pedido inteiro; o
cenário do B.I., com campo de nome).

Trava: `tests/guardrails.moreMenu.test.ts` reprova o ícone de reticências fora da peça,
com as exceções acima listadas com motivo e teto (o número só cai), e o ⋯ de pé em
qualquer lugar. Os apps ainda fora do shell (Marketing, Compras, Produção, PDV) desenham o
⋯ com `UiPopover`: trocam pela peça na onda de cada um. Contrato em
`tests/components/OperatorMoreMenu.test.ts` e `tests/moreMenu.test.ts`.

### Anterior e próximo (`OperatorRecordNav` + `useRecordTrail`)

"‹ 3 de 18 ›" no detalhe de um registro: anda DENTRO da lista de onde a pessoa veio, com
o recorte dela (a busca, o escopo, a ordenação). "18" são os que ela via.

```ts
// Na lista: grava a ordem que a tela mostra (a cada mudança).
const { remember } = useRecordTrail("orders-queue");
watch(visibleRefs, (refs) => remember(refs, { from: route.fullPath, label: "Pedidos" }), { immediate: true });
```

```vue
<!-- No detalhe, no #status do OperatorPageHeader (a barra do topo; no celular, a 2ª linha). -->
<OperatorRecordNav
  trail="orders-queue"
  :current="orderRef"
  :to="(ref) => `/${ref}`"
  previous-label="Pedido anterior"
  next-label="Próximo pedido"
/>
```

- **A trilha** (`presentation/recordTrail.ts`) mora na sessão do navegador, por chave:
  o detalhe recarregado ainda sabe de que lista veio; outra aba começa sem trilha. Duas
  listas que abrem o mesmo detalhe usam chaves diferentes (a fila e o histórico do
  Gestor), e o detalhe lê a da lista por onde a pessoa chegou.
- **Sem trilha, sem par**: aberto por link, por outro app, ou com o registro fora da
  lista (que já mudou), o par não aparece. Sozinho na lista, também não.
- **Cada lado é um link** (`to`): a URL é a do registro, abre em outra aba, e o voltar do
  navegador volta ao registro anterior. Na ponta, o lado que falta fica desabilitado.
- **Teclas** J (próximo) e K (anterior), e as setas → e ← (`RECORD_NAV_SHORTCUTS`, pela
  infraestrutura de atalhos do kit). Não agem com o foco num campo, com diálogo aberto
  nem onde as setas já têm dono (abas, rádio, menu, lista, divisor:
  `ignoreWithin` do comando de atalho).
- **O lugar** é a barra do topo, o papel "onde estou": o `#status` do `OperatorPageHeader`.
  No celular ele é a segunda linha da barra; nunca uma barra própria.
- No servidor não há trilha: o par aparece depois de montar e nunca diverge na
  hidratação.

Contrato em `tests/components/OperatorRecordNav.test.ts` e `tests/recordTrail.test.ts`.
Primeiro uso: o pedido do Gestor (`orders-nuxt/app/pages/[ref].vue`), com a trilha da
fila (`pages/index.vue`) e a do histórico (`pages/history.vue`).

### Ação na base (`OperatorActionBar`)

A ação do momento no celular e no tablet: a estrutura de sucesso do Storefront
(`.shop-action-dock` da sacola) como regra, não como classe. A linha de contexto (o que a
ação mexe), UMA ação larga e o motivo escrito quando ela não pode, num cartão
**flutuante em superfície invertida** (dono, 09/10/2026): escura no tema claro, creme no
escuro (`bg-inverted`/`text-inverted`, os tokens do tema), com sombra, como a sacola do
Storefront. Contraste AA dos dois botões sobre ela, nos dois temas, travado em
`tests/actionBarContrast.test.ts`.

```vue
<OperatorActionBar
  :action="{ label: 'Iniciar preparo', icon: 'i-lucide-lock', disabled: true,
             reason: 'O Pix ainda não caiu. O pedido libera sozinho quando cair.' }"
  :secondary="{ label: 'Recusar', onSelect: reject }"
  context-label="Pedido 1049 · Pix"
  context-value="R$ 93,20"
/>
```

- **Em fluxo**: a tela a põe como irmã do conteúdo que rola, DEPOIS dele (o rodapé do
  painel, a posição do `#footer` do `NuxtDashboardPanel`). Nada de `fixed`, nada de
  `bottom-16` adivinhando a altura da barra inferior.
- **A ação** (`OperatorActionBarAction`, `presentation/actionBar.ts`) leva verbo e alvo
  ("Pronto para retirar"), `xl`. A PRINCIPAL é `primary` `solid` (o dourado); a segunda
  (`secondary`), se houver, é SECUNDÁRIA (`outline`), nunca discreta (`ghost`) (dono,
  09/10/2026). Sobre a superfície invertida as duas ganham contorno na cor do texto
  invertido: o dourado sozinho não separa da superfície (2,8:1 no claro, 1,8:1 no
  escuro). A cor de cada uma é da peça, não da tela.
- **`reason`**: com `disabled`, o motivo aparece escrito sob a ação (`role="status"`, e o
  botão aponta para ele com `aria-describedby`).
- **Só abaixo de `lg`**: na mesa, a ação sobe para a barra superior primária.
- **Some com o teclado aberto** (`data-keyboard="open"` no `<html>`, do
  `plugins/visualViewport.client.ts`): o campo que a pessoa digita fica com a tela.
- Marca `data-focus-obstruction`: o próximo foco e o "Tem mais abaixo" descontam a altura.

**Convivência na base do celular**, de baixo para cima:

1. a **barra inferior** (`OperatorQuickBar`, 3 a 5 vagas, do shell), sempre visível;
2. a **ação na base**, uma por tela, colada em cima dela;
3. o **conteúdo**, que rola acima das duas e nunca fica coberto.

Enquanto houver seleção numa lista, a barra de seleção (`OperatorBulkBar`, por vir)
ocupa o lugar da ação na base. **Ponto de encontro com o `OperatorThumbAction`** (o
polegar da Saída do Gestor, #1564): é o mesmo papel (a ação do momento ao alcance do
polegar, `xl`, `data-focus-obstruction`), hoje `sticky` dentro da área que rola e só
abaixo de `md`. Próximo passo: o polegar vira um `OperatorActionBar` sem linha de
contexto (a Saída passa a ação para o rodapé do painel), e as duas peças viram uma. A
trava abaixo declara o teto dele (1, que só cai).

Trava: `tests/guardrails.actionBar.test.ts` conta, por arquivo, o texto de classe com
`sticky`/`fixed` e `bottom-*` nos templates dos apps de operador e do kit: uso novo
reprova, e o teto das barras feitas à mão (Cozinha, Marketing, PDV, Compras) só cai.
Contrato em `tests/components/OperatorActionBar.test.ts`. Primeiro uso: o pedido do
Gestor no celular (`orders-nuxt/app/pages/[ref].vue`: a ação primária, "Recusar" como
segunda, o motivo do bloqueio escrito).

### Estado da tela (`OperatorScreenState`)

Carregando, vazio, erro e sem conexão, com UMA frase por estado
(`presentation/screenState.ts`). A tela diz o que mostra, com artigo, e a peça escreve:

| estado | peça | frase |
| --- | --- | --- |
| `loading` | `NuxtEmpty loading` | "Carregando a fila" |
| `empty` | `NuxtEmpty` com ícone | o título da tela, no presente e sobre a pessoa ("Nenhum pedido precisa de você agora."); sem título, "Nada para mostrar agora." |
| `error` | `NuxtAlert subtle error` + "Tentar de novo" | "Não foi possível carregar a fila" (o tom é do dono, 09/10/2026) |
| `offline` | `NuxtAlert subtle warning` | "Sem conexão." + "O que está na tela é de 10:42." |

```vue
<OperatorScreenState v-if="error" state="error" what="os lotes do período" @retry="refresh()" />
<OperatorScreenState v-else-if="pending && !report" state="loading" what="os lotes do período" in-card />
```

- **"Tentar de novo" na cor do aviso** (a exceção declarada do conjunto mínimo), `outline`,
  tamanho `md` como o resto da suíte: o `xs` que o `NuxtAlert` dá por padrão às ações
  fica fora do conjunto. Vale para toda ação dentro de aviso montada pelo kit.
- **`in-card`**: dentro de um cartão o vazio e o carregando perdem a moldura própria
  (`naked`); no corpo da página, ficam com ela. Uma regra, em vez de cada tela escolher.
- `description` acrescenta a segunda linha (no B.I., "Os números na tela são os da
  leitura anterior."); `#actions` dá a saída do vazio.
- Substituiu o `BiPageState` (3 usos) e os cinco avisos de erro escritos à mão no B.I.

### Aviso da tela (`alerts` do `OperatorPageHeader`)

O que a tela precisa que a pessoa saiba agora tem **um lugar só**: as `alerts` do
cabeçalho, logo abaixo da toolbar.

```vue
<OperatorPageHeader
  title="Pedidos"
  :alerts="[{ id: 'late', color: 'warning', title: '2 pedidos passaram do horário',
              description: 'O 1049 e o 1053 já deveriam ter saído.',
              action: { label: 'Ver os atrasados', onSelect: showLate } }]"
/>
```

- `NuxtAlert subtle` nas 4 cores do conjunto (`info`, `success`, `warning`, `error`); o
  ícone vem da cor se a tela não escolher. A saída (`action`) repete a cor do aviso, `md`.
- **Um aviso inteiro**; os outros ficam atrás de "e mais N avisos", que abre todos. A
  ordem é a da tela: o mais importante primeiro.
- O aviso fica fixo com o cabeçalho (não rola com o conteúdo): o "um inteiro, o resto em
  e mais N" é o que impede que ele coma a tela do celular.

**Onde cada aviso mora** (a regra; nenhuma tela monta faixa própria):

| o que é | onde mora |
| --- | --- |
| aviso de uma tela ("33 produtos sem vocação", "2 pedidos atrasados") | `alerts` do `OperatorPageHeader` |
| o conteúdo não veio (erro ao carregar, vazio, carregando) | `OperatorScreenState`, no lugar do conteúdo |
| sem rede no app inteiro | `OfflineBanner` (do app) |
| prazo correndo que interrompe ("o pedido cancela em 2 min") | `OperatorUrgentAlert` (modal) |
| resultado de uma ação ("Pedido aceito", "Não deu para aceitar") | toast (`useSonner`/`useToast`), ou o erro escrito junto do controle |
| alerta da operação que fica (capacidade, canal parado) | caixa de Avisos (`provideOperatorInboxAlerts`) |

O `#feedback` do cabeçalho segue para sinal que não é aviso (o `ChannelQueueSignal` do
Gestor).

Trava: `tests/components/OperatorScreenState.test.ts` (as frases, sem travessão; a saída
do erro; um aviso inteiro e "e mais N") e `tests/catalog/phone-header.spec.ts` (no
navegador, a 320, 390 e 1440 px: um aviso visível, "e mais 2 avisos" abre os três, a saída
do aviso no tamanho da suíte e sem rolagem lateral). Primeiro uso do estado: o B.I. (oito
erros de leitura, em sete telas); do aviso: a bancada do catálogo.

### Tabela (`OperatorTable` + `OperatorTableView`)

A `NuxtTable` oficial dentro do cartão branco, com o que toda tabela de operador repete.
Decisões do dono (09/10/2026): **compacta é o padrão**; Confortável é a alternância,
guardada por dispositivo; **a linha aberta não compacta** (o conteúdo de `#expanded`
ganha o respiro da confortável).

```vue
<!-- toolbar da tela (só na mesa; no celular as colunas já são as que cabem) -->
<OperatorTableView table-key="orders-history" />

<OperatorTable
  :data="items"
  :columns="[
    { id: 'order', header: 'Pedido', enableHiding: false },
    { accessorKey: 'customer', header: 'Cliente', enableSorting: true },
    { id: 'payment', header: 'Pagamento', meta: { supporting: true } },
  ]"
  :row-key="(row) => row.ref"
  :row-label="(row) => `o pedido ${row.ref}`"
  :on-select="(row) => open(row.ref)"
  :loading="pending" :error="Boolean(error)" what="o histórico" @retry="refresh()"
  empty-title="Nenhum pedido neste recorte."
  pinned="order" view-key="orders-history" selectable
  v-model:row-selection="selection" v-model:expanded="expanded"
  caption="Pedidos concluídos e cancelados"
>
  <template #order-cell="{ row }">…</template>
  <template #expanded="{ row }">…</template>
  <template #footer><NuxtPagination … /></template>
</OperatorTable>
```

- **Exibir** (`OperatorTableView`, só o ícone): Linhas (Compacta, Confortável) e as colunas
  visíveis, num menu só. Muda a FORMA da tabela, por isso nunca mora no painel de
  filtros. A lista de colunas vem da própria tabela com a mesma chave; ficam de fora a
  que diz `enableHiding: false` e as fixadas.
- **Por dispositivo, sem piscar**: cookie `op-table-<chave>` (lido no servidor, que já
  desenha a densidade e as colunas certas). Guarda as OCULTAS: coluna nova nasce visível.
- **Ordenação pelo cabeçalho**: a coluna que diz `enableSorting: true` ganha o botão com
  a seta e o nome acessível ("Ordenar por total"). Tabela paginada no servidor não liga
  ordenação local (ordenaria só a página da vez).
- **Seleção múltipla** (`selectable`, `v-model:row-selection`): caixa em cada linha e o
  "todos" no cabeçalho; marcar não abre a linha.
- **Linha expansível**: basta o slot `#expanded`; a seta entra sozinha.
- **Coluna fixada** (`pinned`, e `pinned-end` para o ⋯ de uma matriz larga): presa ao
  rolar de lado e, no celular, com largura máxima (o texto dela quebra).
- **Colunas de apoio** (`meta.supporting`): somem no celular por CSS (`max-sm:hidden`),
  nunca por media query em JS.
- **Estado** pelo `OperatorScreenState`: carregando sem linhas, vazio (título da tela,
  `#empty-actions` para a saída) e erro com "Tentar de novo" (as linhas da leitura
  anterior continuam abaixo).
- `fill`: a tabela ocupa a altura que sobra e rola por dentro, com o cabeçalho preso (a
  matriz do Catálogo). `row-class` dá à tela a classe da linha (arrastar); `active-key`
  marca o registro aberto ao lado.
- **A célula quebra** (`whitespace-normal`): texto da casa nunca é cortado. Número e ação
  que não devem quebrar dizem isso na própria célula (`whitespace-nowrap`, `min-w-max`).
- **Sem `:ui` na tela**: a densidade é o único `:ui` da tabela e mora no componente
  (`presentation/operatorTable.ts`).
- Substituiu as cinco tabelas do Gestor (Lista da fila, Histórico, Clientes, Unificações e a
  matriz do Catálogo) e aposentou o `ColumnPicker`.

## Busca da suíte (`OperatorSuiteSearch`)

Uma busca, uma tecla (SUITE-UX-V2 §2.2, FUNCTION §7; prévias v3 `depois-gestor-busca`,
`depois-hub-celular` e o campo do cabeçalho das v4). O `OperatorPageHeader` já a traz
(`search = true`): toda tela tem o campo de 22rem do tablet para cima e a lupa na barra de
56px do celular, que abre a busca em tela cheia (com a câmera onde o navegador lê código).

- **Esta tela**: a tela que filtra a própria lista passa a sua no `#search`, com `v-model`
  (e `screen-label="filtrando o quadro"`, `screen-count` se souber contar). Digitar filtra a
  tela, como antes; Esc fecha o painel e mantém o filtro.
- **App** e **Toda a suíte**: `GET /api/v1/backstage/search/?q=` (projeção
  `shopman/backstage/projections/suite_search.py`): pedidos, encomendas, clientes, produtos,
  insumos, fornecedores, lotes, receitas, campanhas e telas que o operador abre, agrupados por
  tipo, cada um com o link profundo para o app de destino. "App" recorta pelo app atual
  (`operatorPwa.app`; o Gestor é `orders` no kit e `gestor` no Django).
- Teclas: `/` fora de campo e Ctrl K (⌘K) em qualquer lugar abrem; ↑↓ anda, Enter abre, Tab
  troca o alcance. Impressas só com ponteiro fino.
- Variantes: `header` (padrão), `hero` (a barra grande da Central, 34rem, "/" e Ctrl K) e
  `hotkey` (sem campo na tela: a Venda e as Encomendas do PDV, onde o `/` é do campo do
  produto e do "cliente veio buscar"; só Ctrl K e a lupa abrem a suíte).

Contrato em `tests/components/OperatorSuiteSearch.test.ts` e `tests/suiteSearch.test.ts`;
`tests/guardrails.suiteSearch.test.ts` trava que os oito apps e a Central a têm e que o
`#search` do cabeçalho é sempre ela, e uma só.

## Próximo foco (`useNextFocus`)

Toda tela com sequência de blocos (etapas, campos, cartões que se abrem um após o
outro) usa o mesmo mecanismo para deixar a página **sempre posicionada no que se faz
agora**. A tela diz qual é o foco; o mecanismo leva a página até ele.

```ts
// A página nomeia o foco do momento — um estado, não um evento.
const focusKey = computed(() => (customerEditing.value ? "customer" : activeStep.value));
const { reveal } = useNextFocus(focusKey);
```

```html
<!-- Cada bloco candidato se marca com a chave. `scroll-mt-*` declara a folga
     sob o chrome fixo (o scrollIntoView nativo respeita scroll-margin-top). -->
<section data-focus-target="payment" class="scroll-mt-20 outline-none" tabindex="-1">
  <!-- Se a próxima ação é digitar, o controle recebe o foco no lugar do bloco. -->
  <input data-focus-control />
</section>
```

Contrato:

- **Linha de foco** = topo da área visível, abaixo do chrome fixo. Acima, o feito; na
  linha, o agora; abaixo, o depois. Sempre a mesma posição, o olho não procura.
- Quando a chave muda, o bloco vai à linha (`scrollIntoView` nativo, funciona em
  container aninhado) e recebe o foco de teclado: o controle `data-focus-control` se
  houver, senão o próprio bloco (`tabindex=-1`, para o leitor de tela anunciar).
- `reveal(alvo, { align: "center", focus: false })` para o foco fora do fluxo (um
  erro, um item que chegou). Aceita chave, elemento ou função que resolve o elemento.
- O pedido mais novo vence: trocas rápidas não disputam, e o foco automático da
  renderização passa na frente de um `reveal` do mesmo handler.
- Na montagem só rola se o foco estiver fora da área visível (estado restaurado lá
  embaixo). Respeita `prefers-reduced-motion`. Nunca roda no servidor.

## Tem mais abaixo (`<MoreBelow />`)

A outra metade do contrato com a área visível. O próximo foco responde "onde eu devo
estar agora"; esta responde "ainda há coisa que você não viu". As duas convivem, e
devem: com a ação fixa num card e sem a dica, dá para avançar sem nunca ver as opções
que ficaram abaixo da dobra.

```html
<!-- No fim do CONTEÚDO — antes de qualquer card/barra flutuante, que é chrome. -->
<MoreBelow />
```

Contrato:

- Um sentinela de 1px marca o fim do conteúdo; enquanto ele não aparece, a dica existe.
  IntersectionObserver em vez de contas de rolagem, então redimensionamento, teclado
  virtual e conteúdo que cresce funcionam de graça.
- **O fim só conta ACIMA do obstáculo.** O observador encolhe a área pelo que flutua na
  base (`data-focus-obstruction`, o mesmo fato que o próximo foco lê). Sem isso a dica
  some com conteúdo ainda escondido atrás do card.
- **O degradê ENCOSTA no obstáculo; quem recua é o chevron.** A base da dica se apoia
  no topo do que flutua, e a folga de `HINT_GAP` (12px) mora no recuo interno do
  desenho. Enquanto ela morava no posicionamento, a lavagem parava 12px acima do card
  e sobrava uma faixa de conteúdo cru entre os dois — a dica prometia dissolver e
  largava o texto legível justo na borda. A pílula não se mexeu; só o degradê desceu.
- **O chevron LEVA ATÉ O FIM.** Era decorativo e inerte; virou botão por decisão do
  Pablo, porque já parecia tocável e não era — quem tentava não recebia nada, que é
  pior do que não convidar. O destino é o próprio sentinela, alinhado pela borda de
  baixo, e é o `scroll-margin-bottom` dele (igual ao obstáculo) que faz o fim parar
  ACIMA do card em vez de atrás — o mesmo truque do `scroll-margin-top` do próximo
  foco, do outro lado da tela.
- **Só o chevron captura o toque.** A faixa teleportada cobre a largura inteira da
  tela: `pointer-events-none` nela, `pointer-events-auto` no botão. O degradê continua
  `aria-hidden` — ele é desenho.
- **O que a impede de se ler como botão gordo é a translucidez, não o tamanho**: fundo
  sólido com sombra vira chip pesado em qualquer medida. Com o fundo a 33% e sem
  sombra, o que sobra é o chevron, e o círculo só o separa do conteúdo — por isso ela
  pôde crescer de 28 para 48, que é o alvo de toque. Sobre o degradê ela rende pouco
  (fundo da mesma cor); trabalha nas bordas e onde há contraste atrás, que é o caso do
  operador.
- `prefers-reduced-motion`: a dica fica **parada**, não some — e o toque salta para o
  fim de uma vez, sem deslizar.

⚠️ O `BottomSheet` do storefront ainda tem a versão antiga inline. Migrá-lo pede um
tom de degradê por superfície (`card`/`muted`) e marcar o rodapé do sheet como
obstáculo; é o próximo consumidor natural.

Tela cujo foco de teclado é todo explícito (o PDV, com o shell capturando dígitos e
letras fora de input) chama `useNextFocus()` sem fonte e usa só o `reveal` — é o caso
de "levar o foco ao campo que resolve" (`PosPaymentWorkspace`: CPF/e-mail da nota,
forma alternativa ao Pix). O que NÃO é próximo foco: o realce de uma listbox seguindo
as setas (`scrollIntoView({ block: "nearest" })` em `PosCartPanel`/`PosCustomerSearch`)
— isso é manter a opção realçada visível dentro da lista, e fica como está.

O storefront tem cópia espelhada (`storefront-nuxt/app/composables/useNextFocus.ts`);
o checkout (`pages/finalizar.vue`) é o primeiro consumidor; o PDV, o segundo; o login
do storefront (`pages/entrar.vue`: telefone, código, nome — um bloco por passo), o terceiro.

## Clique nunca inerte (`usePendingAction`)

Regra da casa: "cliquei e não aconteceu nada" não pode existir. Todo botão que dispara
uma ação assíncrona (`$fetch`, fila de pedidos, navegação que carrega rota) diz que
está em andamento do toque até a resposta.

```ts
const { run: bulkConfirm, pending: bulkConfirming } = usePendingAction(async () => {
  await confirmMany(targets);
});
// Por linha: remover A não trava B.
const { run: removeLine, isPending: removing } = usePendingAction(removeLineNow, { key: (line) => line.sku });
```

```html
<button :disabled="bulkConfirming" :aria-busy="bulkConfirming || undefined" @click="bulkConfirm">
  <Icon :name="bulkConfirming ? 'line-md:loading-loop' : 'lucide:check'" aria-hidden="true" /> Aceitar
</button>
```

Contrato:

- **Pendente do toque até a promessa assentar**, com sucesso ou erro. O botão mostra
  (`aria-busy` + spinner) e fica desabilitado **só durante** o pendente; nunca nasce
  desabilitado "até ficar pronto".
- **Toque repetido enquanto pende é ignorado**, não enfileira uma segunda ação. Com
  `key`, a trava é por chave.
- **O erro sobe para quem chamou.** O composable não engole nem avisa: o aviso de
  erro continua sendo da ação.
- **Spinner empacotado**: `line-md:loading-loop` (coleção instalada na layer, #1316).
  Ícone buscado pela rede no meio do gesto é a mesma inércia por outro caminho.
- A trava `tests/guardrails.pendingAction.test.ts` varre a layer e os apps de operador
  do `registry.json`: botão com `@click` numa função `async` do próprio componente
  precisa declarar o pendente (`:loading`, `:aria-busy` ou `:disabled` no mesmo
  elemento). O que já existia sem isso está numa lista que **só encolhe**: corrigir um
  item obriga a tirá-lo da lista, e item novo reprova.

A loja tem cópia espelhada (`storefront-nuxt/app/composables/usePendingAction.ts`) e,
além dela, o **toque antes da hidratação** (`storefront-nuxt/app/utils/earlyTap.ts`):
o "Adicionar" nasce ativo no HTML do servidor, um script inline no `<head>` guarda o
toque que chega antes do app e o mostra girando, e o componente o executa uma vez ao
montar.

## Diálogo de motivo (`OperatorReasonDialog`)

O gesto destrutivo que o cliente vai ler (cancelar, recusar) pergunta o motivo, diz a
consequência e confirma num diálogo só. Consumidores: o cancelar da encomenda no PDV
(`PosPreorderCancelDialog`) e o recusar/cancelar do Gestor (`OrderReasonDialog`).

```html
<OperatorReasonDialog
  :open="open" title="Cancelar pedido" :description="consequence"
  confirm-label="Confirmar" :presets="cancellation_presets" :busy="busy"
  @update:open="open = $event" @confirm="({ reason, code }) => cancelOrder(reason, code)" />
```

Contrato:

- **A consequência é obrigatória** (`description`): reembolso, para onde vai o motivo.
- **Motivos prontos** (`presets`, os grupos cadastrados no Admin) são um toque; com
  eles vem o "Outros", que exige texto. "Outros" nunca é o motivo enviado.
- **Motivo codificado** (`coded` + `codedReasons`): o iFood exige um código da lista
  dele; a descrição escolhida vira o texto que o cliente lê.
- `required` diz se confirmar em branco é permitido (recusar exige; cancelar não).
- **Fechar com texto digitado pergunta dentro do diálogo**, nunca por
  `window.confirm`. Ocupado (`busy`), o diálogo não fecha nem confirma de novo.
- A autorização do gerente fica **fora**: o `OperatorManagerAuth` sobe por cima, e o
  motivo digitado continua embaixo.
- ⚠️ Usa `UiDialog`, `UiButton` e `UiTextarea` do app hospedeiro, o mesmo limite do
  `OperatorManagerAuth`.

## Pergunta antes de descartar (`useConfirm`)

Descartar o que o operador digitou e não salvou pergunta antes, no diálogo da casa,
nunca no `window.confirm` do navegador (fonte do sistema, "OK"/"Cancelar" que não dizem
o ato, e no app instalado uma caixa estranha sobre a tela).

```ts
const confirmDiscard = useConfirm();

async function closePrice() {
  if (dirty.value && !(await confirmDiscard({
    title: "Descartar o preço digitado?",
    description: "O novo preço não foi salvo. O produto continua com o preço atual.",
  }))) return false;
  editing.value = null;
  return true;
}

// Guarda de rota: o Vue Router 4 espera a Promise (false = fica na tela).
onBeforeRouteLeave(() => !dirty.value || confirmDiscard({
  title: "Sair sem salvar as alterações do catálogo?",
  description: "O que você alterou e ainda não salvou se perde. O que já foi salvo continua salvo.",
  confirmLabel: "Descartar e sair",
}));
```

Contrato:

- **Nada a montar.** O `<OperatorConfirmDialog>` vive dentro do `OperatorPwaRuntime`, que
  todo app de operador já monta; o app só chama `useConfirm()`.
- **`title` é a pergunta com o ato** ("Descartar o motivo digitado?", "Sair sem salvar…?").
  **`description` é obrigatória e diz o que se perde** (e, quando ajuda, o que fica: "O
  que já foi salvo continua salvo"). Régua da copy: `docs/reference/omotenashi-copy.md`.
- **Dois botões, com o nome do ato.** O destrutivo: `confirmLabel`, padrão "Descartar"
  ("Descartar e sair", "Descartar e trocar" quando o gesto continua). O que fica:
  `cancelLabel`, padrão "Continuar editando" ("Continuar escrevendo" para um motivo, o
  mesmo par do `OperatorReasonDialog`; "Continuar revisando" numa revisão).
- **O tom diz o que o ato é (`tone`).** `"danger"` é o padrão: botão vermelho, para
  descartar ou perder. `"primary"` é o ato normal que só merece confirmação (mudar a
  encomenda de dia, enviar): botão da cor da casa, e aí `confirmLabel` e `cancelLabel`
  são obrigatórios no tipo, porque os padrões falam de perda. Vermelho num ato normal é
  rótulo que mente. Consumidor: o arrastar de dia das Encomendas do PDV
  (`usePosPreorderMove`: "Mudar para qui, 01/10" / "Manter a data").
- **Ficar é o padrão seguro.** O foco nasce em "Continuar editando"; Esc responde ficar;
  toque fora não responde nada (é `AlertDialog`). Só o botão destrutivo descarta.
- **Uma pergunta por vez.** Com uma aberta, a seguinte responde `false` sem abrir: dois
  gatilhos do mesmo gesto (o Esc do campo e o Esc do popover) não empilham caixas.
- **Abre sobre o diálogo do app.** O kit faz `dedupe` do `reka-ui` (`nuxt.config.ts`), para
  que a pergunta e o `UiDialog` do app dividam a mesma pilha de camadas: o toque dentro
  da pergunta não fecha o diálogo de baixo.
- **A função que só espera a pergunta não é clique inerte.** A trava do "Clique nunca
  inerte" reconhece o `async function` cujos `await` são todos o `useConfirm` (o toque
  abre o diálogo no mesmo instante); a que espera rede depois da pergunta continua
  precisando declarar o pendente.
- ⚠️ **O `beforeunload` continua nativo.** Fechar a aba ou recarregar não deixa página
  nenhuma desenhar a própria caixa; ali o gesto possível segue sendo
  `event.preventDefault()`.
- A trava `tests/guardrails.nativeConfirm.test.ts` varre `app/` de todas as superfícies
  Nuxt e da layer e reprova `window.confirm(` (e o `confirm(` solto). O que ainda existe
  está declarado com motivo numa lista que **só encolhe** (hoje: dois pontos da Produção).

## Filtro universal (`FilterBar` + `useRouteFilters`)

Uma barra só para recortar qualquer lista, a do plano SUITE-UX ("Filtrar"). Os 3 a 6
recortes mais usados podem continuar como `UiFilterChip` com contagem na linha; o resto
entra pelo "+ Filtro". Consumidores: Histórico e Catálogo do Gestor, Encomendas do PDV.

```html
<FilterBar v-model="filters" :dimensions="dimensions" touch />
```

```ts
const dimensions = computed<FilterDimension[]>(() => [
  { id: "payment", label: "Pagamento", type: "multi-select", options: [{ value: "pix", label: "Pix", count: 12 }] },
  { id: "customer", label: "Cliente", type: "text", options: [], placeholder: "Nome ou telefone" },
  { id: "total", label: "Total", type: "number-range", options: [], formatValue: (q) => brl(q) },
  { id: "closed", label: "Fechado em", type: "date-range", options: [] },
]);
const filters = useRouteFilters(dimensions, { resetKeys: ["page"] });
```

- **Dois passos no mesmo popover**: "+ Filtro" lista os campos; escolher um abre os
  valores dele, com "‹ voltar". Nada de modal: o operador não perde a lista de vista.
- **Campo de lista** (`multi-select`, `single-select`, `boolean`): marca valores; multi
  fica aberto para marcar vários de uma vez. `count` aparece à direita de cada valor.
  A partir de 8 opções (`SEARCH_THRESHOLD`) aparece a busca, sem acento e sem caixa;
  `searchable` força ligar ou desligar.
- **Campo digitado** (`text`, `number-range`, `date-range`): o valor (ou De/Até, qualquer
  lado aberto) e "Aplicar". Valor vazio remove o recorte.
- **Chip** por campo aplicado: "Pagamento: Pix, Cartão", "Total: até R$ 50,00",
  "Fechado em: 01/10 a 03/10". Tocar no chip reabre a edição daquele campo; o × remove;
  "Limpar filtros" tira todos.
- **Celular** (abaixo de `sm`): a linha de chips rola na horizontal e o popover vira
  painel de baixo com fundo escurecido e botão "Pronto".
- **Valor**: `ActiveFilters = Record<id, string[]>`. Lista guarda os valores; texto,
  `[texto]`; intervalo, `[de, até]`. A barra não interpreta nada: quem filtra é o app
  (ou o servidor).
- **URL**: uma chave por campo, com o `id`. Lista → `?payment=pix,card` (valor de opção
  não leva vírgula); texto → `?customer=maria`; intervalo → `?total=1000..5000`,
  `?closed=2026-10-01..` (lado aberto vazio). `filtersFromQuery` descarta valor
  malformado em vez de virar filtro que não casa nada, e NÃO confere opção contra
  `options` (elas podem chegar depois, do servidor). `useRouteFilters` troca só as
  chaves dos campos (período, busca e aba ficam), por `router.replace`, e apaga as
  `resetKeys` a cada troca.
- **Contagem por valor** é do servidor quando a lista é paginada: conte cada recorte com
  os OUTROS aplicados e o próprio solto (marcar Pix não zera Cartão). Referência:
  `shopman/backstage/projections/order_history.py`.
- Testes: `tests/filterBar.test.ts`, `tests/filterBarUrl.test.ts` (ida e volta da URL,
  vários campos e valores) e `tests/components/FilterBar.test.ts` (DOM).

## Primitivos de escolha (`UiCheckbox`, `UiRadioGroup`/`UiRadio`, `UiSelect`)

Até 18/09/2026 **todo** checkbox e **todo** rádio das nove superfícies era o controle
nativo do browser com uma tinta do Tailwind por cima (`size-4 rounded border-border`,
às vezes um `accent-color`): o desenho vinha do sistema operacional, mudava de dispositivo
para dispositivo no meio do desenho da casa, e não tinha estado **indeterminado** — que é
o que falta para um "marcar todos" honesto. O select com busca existia UMA vez,
escondido no Compras como `MaterialPicker`.

Agora os três vivem aqui, com nome global `Ui<Nome>`, e o `MaterialPicker` foi
**promovido** (não reescrito) a `UiSelect`.

```html
<UiCheckbox v-model="birthday" label="Aniversariantes de hoje"
            description="Só quem tem data cadastrada." />

<!-- "marcar todos" honesto: `mixed` quando só parte das linhas está marcada -->
<UiCheckbox :model-value="allSelected" :indeterminate="someSelected && !allSelected"
            aria-label="Selecionar todos" @update:model-value="toggleAll" />

<UiRadioGroup v-model="useSaved" label="Para quem">
  <UiRadio :value="true" label="O público da campanha" description="…" />
  <UiRadio :value="false" label="Escolher agora" variant="inline" />
</UiRadioGroup>
<!-- ou, sem escrever um filho por item -->
<UiRadioGroup v-model="format" :options="formatOptions" label="Formato" />

<UiSelect :options="templateOptions" :model-value="current"
          labelled-by="rotulo-do-campo" placeholder="Sem modelo"
          @update:model-value="choose" />
```

Contrato:

- **Alvo de toque de 44 px pelo token** (`min-h-control`/`h-control`/`size-control`),
  nunca literal. `UiCheckbox` sem rótulo vira um quadrado de 44 px; com rótulo, a linha
  inteira é o alvo. Quem atende balcão está com uma mão só e o celular na outra.
- **ARIA de verdade, não `<input>` pintado**: `role="checkbox"` com
  `aria-checked="true|false|mixed"`, `role="radiogroup"`/`role="radio"`,
  `aria-haspopup="listbox"` + `role="listbox"` + `aria-activedescendant`.
- **Uma parada de tabulação por grupo de rádio** (a escolhida, ou a primeira
  utilizável). A seta anda, pula opção desabilitada e dá a volta; Home/End vão às
  pontas. Sem isso o Tab passearia por cada opção, que é o erro clássico.
- **Foco por `outline`, não por `ring`.** Anel de foco feito de `box-shadow` some no
  modo de alto contraste do sistema, e quem depende dele fica sem foco visível.
- **Clicar num checkbox indeterminado MARCA tudo.** Sair de "alguns" para "nenhum"
  desfaria o que o operador já escolheu; ele clica o mestre para alcançar o todo.

Do `UiSelect`, três coisas que valem a leitura:

- **Limiar de busca: `SEARCH_THRESHOLD = 12`** (`app/presentation/choice.ts`). Acima
  dele a lista ganha campo de busca; abaixo, degrada para lista simples. O número é
  medido, não chutado: o maior vocabulário FIXO da casa tem 10 itens (`ROLE_OPTIONS` do
  Produção, filtro de desfecho do Histórico), e busca em cima de dez opções escritas no
  código é obstáculo; do outro lado estão as listas reclamadas — os modelos aprovados
  da Meta, os 41 exemplos do Explorar no B.I., os 56 insumos do Compras. O app pode
  forçar (`:searchable="true|false"`) ou mover o limiar (`:search-threshold`).
- **A busca ignora acento** e casa por rótulo, detalhe (`hint`) e palavras-chave
  invisíveis (`keywords` — o `ns` do fluxo, o SKU da etiqueta), com termos soltos em
  qualquer ordem. A contagem vai para uma região viva (`role="status"`).
- ⚠️ **Nunca envolva o `UiSelect` num `<label>`.** Um `<label>` sem `for` adota o botão
  que abre e reencaminha para ele todo clique que caia em parte não interativa —
  inclusive o véu de fechar. O painel fechava e reabria no mesmo gesto. Rotule com um
  `<span id>` e passe `labelledBy`. Isto é memória de um defeito pago no recebimento do
  Compras; o teste que a prende vive em `tests/components/UiChoicePrimitives.test.ts`.

O `UiNativeSelect` **está aposentado** e o `UiSelect` saiu do conjunto (dono,
08/10/2026): escolha nova é `NuxtSelect` ou `NuxtSelectMenu`. Ver "Conjunto mínimo da
suíte", acima.

### `UiToggleChip` — escolha múltipla desenhada como pílula

```html
<UiToggleChip v-model="semGluten" label="Sem glúten" />

<!-- com ícone e estado ao lado do nome, via slot -->
<UiToggleChip
  :model-value="platforms.includes('whatsapp')"
  @update:model-value="togglePlatform('whatsapp')"
>
  <Icon name="lucide:message-circle" class="size-3.5" />
  WhatsApp <span class="text-xs">· limitada</span>
</UiToggleChip>
```

⚠️ **Não é apelido do `UiCheckbox` e não é o `UiFilterChip`.** As três se parecem e
fazem trabalhos diferentes:

| Peça | Ofício | Como acende |
|---|---|---|
| `UiCheckbox` | marcar item numa lista vertical | quadrado que enche de `primary` |
| `UiToggleChip` | marcar item onde cabem vários na linha | contorno `primary` + tint |
| `UiFilterChip` | **filtrar** uma lista (chrome, sem valor de formulário) | `bg-primary` sólido |

O chip é `role="checkbox"` com `aria-checked`, como o `UiCheckbox` — escolher plataforma
é marcar item, não apertar um botão que fica apertado. Um grupo de chips mora dentro de
um `<fieldset>` com `<legend>` ou de um `role="group"` com nome.

**Não há degrau denso, e é de propósito.** O alvo de 44 px (`min-h-control`) é o piso do
kit, e o `h-9` de 36 px é justamente a dívida que a cópia do Marketing carregava —
`kitOwnership.guardrails.test.ts` recusa altura literal em primitivo. Grade que não cabe
a 44 px não vira exceção aqui: ela **reflui**. Os sete dias da semana do Marketing eram o
caso difícil e viraram quatro colunas no celular, sete a partir do `sm`.

### ⚠️ `aria-pressed` não é sinal de chip — e quase nunca é

Ao procurar consumidores para este primitivo, varri as 30 ocorrências de `aria-pressed`
nas superfícies de operador esperando encontrar chips escritos à mão. **Nenhuma era.** O
que existe, medido:

- **~17 são escolha EXCLUSIVA** vestida de `aria-pressed` — modo do numpad, tipo de
  entrega, modo de venda, coleção de pagamento, data (hoje/amanhã), paginação, filtro de
  tipo, aba de modo. São controles segmentados: o leitor de tela diz *"pressionado"* onde
  a pessoa está **escolhendo um entre N**. Pedem um `UiSegmentedControl` ou um
  `UiRadioGroup` com variante inline — nenhum dos dois existe hoje, e o conserto atravessa
  três apps. **É WP próprio, não conversão de passagem.**
- **~6 são seleção de LINHA ou CARTÃO** (comanda em lote, pedidos): o alvo é a linha
  inteira, não uma pílula. Alguns pedem `UiCheckbox`; chip não serve.
- **2 são botão booleano solto** (desconto ligado, dividir conta ativo): não estão num
  grupo de escolha.
- **1 parecia chip e não é**: as cédulas e moedas do troco no PDV. A forma É a informação
  — cédula retangular, moeda redonda — e o marcado é um **anel**, não um tom, "porque sob
  a luz do balcão dois tons da mesma cor viram um só". Converter apagaria três decisões
  deliberadas.

Moral: `aria-pressed` num `<button>` é o que se escreve quando não há primitivo, seja
qual for o gesto. **Contar ocorrências superestima o trabalho**; ler uma a uma é o que
diz o que existe.

`tests/kitOwnership.guardrails.test.ts` recusa que qualquer app volte a ter cópia
própria de `Ui/Checkbox.vue`, `Ui/Radio.vue`, `Ui/RadioGroup.vue`, `Ui/Select.vue`,
`Ui/ToggleChip.vue` ou um `MaterialPicker` — duas implementações vivas é como uma garantia se perde em silêncio.
`tests/guardrails.a11y.test.ts` varre as nove superfícies e recusa botão de ícone puro
sem nome acessível (a peça canônica é o `UiIconButton`, que EXIGE `label`).

O inventário do que ainda falta converter, app por app, está em
[`docs/primitivos-de-escolha-inventario.md`](docs/primitivos-de-escolha-inventario.md).

## Datas: dois controles, e só dois (`OperatorDayPicker`, `OperatorPeriodPicker`)

Decisão do dono (02/10/2026): todo controle de data das superfícies de operador é de um
destes dois tipos. A aritmética que eles dividem (datas LOCAIS, nunca `toISOString`, que é
UTC e virava o dia depois das 21h) mora em `app/presentation/dates.ts`, pura e testada em
`tests/dates.test.ts`; os componentes em `tests/components/OperatorDatePickers.test.ts`.

### Tipo 1: "Escolha rápida de dia" (`OperatorDayPicker`)

Passo de wizard e campo de formulário (PDV agendar e reagendar; Compras recebimento).

```html
<OperatorDayPicker v-model="date" :today="storeToday" :min="storeToday"
                   :max="maxDate" :available-dates="openDates" label="Dia da retirada" />
```

- **Quatro botões de 44 px** (`min-h-control`), um toque escolhe: `Hoje / Qui 01/10`,
  `Amanhã / Sex 02/10`, `<dia da semana por extenso> / 03/10` e `Outra data`.
- O terceiro é a **próxima data depois de amanhã que o contexto permite**: pula dia
  fechado (`availableDates`) e respeita `min`/`max`.
- Hoje e amanhã **aparecem sempre**; se o contexto não deixa, ficam apagados com o
  motivo curto no próprio botão (`fechado`, `fora do prazo`, `indisponível`).
- `availableDates` é a lista de dias em que a casa abre. Dia dentro da lista que não
  está nela é fechado; depois da última data, quem decide é o servidor.
- **Outra data** mostra logo abaixo o campo canônico de data (`UiDateField`, com
  `min`/`max`): os segmentos dia/mês/ano e o calendário do Nuxt UI no gatilho do
  campo. Nunca o seletor nativo. Dia fechado escolhido ali é recusado com a frase do
  motivo. A data escolhida por lá vira a legenda do botão.
- `today` é o hoje da LOJA (vem do servidor), não o do dispositivo.
- ARIA: `role="radiogroup"` + `role="radio"`/`aria-checked`, uma parada de tabulação,
  setas andam entre as opções.

### Tipo 2: "Período" (`OperatorPeriodPicker`)

Quadros e análise (B.I., Encomendas, Produção, KDS, Gestor). O desenho é o do B.I.
(promovido de `BiTopBar.vue`): UM botão que DIZ a janela ativa, os chips e o personalizado
no popover dele. Acrescido de ‹ › e de "Voltar para hoje". É o controle universal de
período: o popover tem até quatro grupos, sempre nesta ordem, e cada consumidor liga os
que fazem sentido para ele.

| Grupo | Chips (chave) | O que é |
|---|---|---|
| Período | Dia, Semana, Mês, Ano (`day`, `week`, `month`, `year`) | o período do calendário que contém a âncora; Ontem, Mês passado etc. são ‹ a partir dele |
| Próximos | 7D, 14D, 28D (`next7d`, `next14d`, `next28d`) | os N dias começando hoje (quem trabalha com o que está por vir) |
| Últimos | 7D, 28D, 3M, 6M, 1A, 5A, Máx (`7d` … `max`) | os N dias terminando hoje |
| Personalizado | De/Até (`custom`) | o intervalo escolhido; `max-span-days` recusa o que passa do teto do servidor |

**Os campos de data do popover são os canônicos** (decisão do dono, não se reabre):
De e Até são dois `UiDateField`, um por linha, com o `min`/`max` do consumidor; sem
personalizado, "Ir para o dia" é um `UiDateField`. Nunca `type="date"`, nem pelo
`NuxtInput`: a trava `kitOwnership.guardrails.test.ts` varre o kit e os apps atrás de
`input`, `NuxtInput`, `UInput` e `UiInput` com tipo temporal, literal ou no `:type`.
Por que dois `UiDateField` e não o `UiDateRangeField`: o intervalo oferece "Sem início"
e "Sem fim", e o período precisa das duas pontas; o motivo de recusa (`max-span-days`,
fora de `min`/`max`) aparece num `NuxtAlert` sob os campos depois que as duas datas
existem. Os chips são `NuxtTabs` com `activation-mode="manual"`: o popover põe o foco
no primeiro chip ao abrir, e no modo automático esse foco escolhia "Dia" e fechava o
popover de quem estava em 28D. O nome por extenso do chip ("Próximos 7 dias") vai
escrito para o leitor de tela no conteúdo do gatilho, porque o `NuxtTabs` não repassa
atributo do item.

```html
<!-- B.I.: todo o passado, personalizado, calendário até hoje -->
<OperatorPeriodPicker v-model="selection" :presets="PAST_PERIOD_PRESETS"
                      custom :max="today" :epoch="DATA_EPOCH" label="Período de análise" />
<!-- Encomendas: o calendário, os próximos e os últimos dias, personalizado até 62 dias -->
<OperatorPeriodPicker v-model="period" :presets="PREORDERS_PERIOD_PRESETS" custom
                      :max-span-days="62" label="Período das encomendas" />
<!-- Produção e KDS: só ['day'] -->
```

- **O consumidor declara as granularidades** (`presets`, chaves de `PERIOD_PRESETS`) e se
  aceita `custom`. Sem personalizado, o popover oferece "Ir para o dia".
- **O período mora na URL** (plano SUITE-UX): `periodFromQuery(route.query, { presets,
  custom, fallback })` e `periodToQuery(seleção, fallback)` usam as chaves `period`, `from`
  e `to`; o padrão do consumidor não ocupa a URL, e valor ilegível cai no padrão. O B.I.
  usa assim (`useBiWindow`, e as abas levam a query); as Encomendas mantêm o vocabulário
  próprio (`mode`, `date`, `to`) por causa dos favoritos de kiosk já gravados.
- **O hoje da loja**: `todayIso(agora, STORE_TIME_ZONE)` dá o dia de Londrina
  (`America/Sao_Paulo`) qualquer que seja o fuso do dispositivo.
- **O valor** é `{ preset, from, to }`. No calendário (`day`/`week`/`month`/`year`), `from`
  é a âncora e `""` é "o período que contém hoje" (acompanha a virada do dia); na janela
  móvel do passado (`7d`…`5y`), `to` é o último dia e `""` é "termina hoje"; na do futuro
  (`next7d`…), `from` é o primeiro dia e `""` é "começa hoje"; em `custom`, o intervalo.
  O estado é do consumidor: quem guarda na URL guarda na URL. Quadro que guarda UM dia
  (Abertura, Fechamento, Qualidade, TV, Encomendas) usa a ponte `periodOfDay(preset, dia, hoje)` /
  `periodAnchor(seleção, hoje)` num `computed` com setter.
- **Consumidores hoje**: B.I. (barra e Projeção), Encomendas (Dia a Mês, Próximos, 7D e 28D, personalizado), Produção
  (grade, Fechamento, Qualidade, quadro da TV, Preparação, Relatórios) e Gestor (Histórico). O KDS não
  tem seletor de dia.

### Celular e leitura de um dia (`compact`, `prev-day`/`next-day`)

- **`compact`**: abaixo de `sm`, o botão diz a forma curta da janela (`periodShortLabel`:
  "Ontem", "Ter 29/09", "28D · 04/09 a 01/10"); do `sm` para cima, a frase inteira. O nome
  acessível é sempre a frase inteira. Para a barra do celular, onde a frase longa empurra
  as setas para a segunda linha.
- **Um dia com ‹ ›**: `presets` só com `day` (o padrão). As setas andam um dia de calendário;
  quem sabe que nem todo dia existe na leitura (dia fechado não tem venda) passa
  `prev-day`/`next-day` com o dia aberto anterior/seguinte que o servidor informou, e
  `""` desliga a seta. É o que substitui o `BiDayStepper` do B.I.

```html
<OperatorPeriodPicker v-model="day" compact :max="yesterday"
                      :prev-day="reading.previous" :next-day="reading.next" label="Dia da leitura" />
```

### Campos de data e hora (`UiDateField`, `UiDateRangeField`, `UiTimeField`, `UiTimeRangeField`, `UiDateTimeField`)

Camadas finas sobre `NuxtInputDate`, `NuxtInputTime` e `NuxtCalendar`, com valor ISO no
contrato (`YYYY-MM-DD`, `HH:mm`, `YYYY-MM-DDTHH:mm`). São a única forma de pedir data ou
hora nos apps de operador. Consumidores: os dois tipos acima, B.I. (`UiDateField`) e
Marketing (`UiDateRangeField`, `UiTimeField`, `UiTimeRangeField`, `UiDateTimeField`).

- `UiDateTimeField` divide o instante em data e hora. `min`/`max` são instantes: a data
  recebe o dia, e a hora recebe o limite **só no dia-limite** (no dia de `min`, a hora
  mínima; no de `max`, a máxima; nos outros dias, toda hora vale).
- **‹ › andam um período igual**: dia → dia anterior; semana (segunda a domingo) → semana
  anterior; mês → mês anterior; janela de N dias (7D, 28D, personalizado) → os N dias
  antes; próximos N dias → os N dias depois, e ‹ para em hoje. "Máx" não anda. A seta
  que sairia de `min`/`max` fica desabilitada.
- **`max` muda o que é "o período"**: com `max` = hoje (B.I.), a semana corre de segunda até
  hoje; sem `max` (quadros), é segunda a domingo inteira.
- **Trocar de granularidade guarda a âncora** (quem olhava a quinta passada e toca
  "Semana" vê a semana daquela quinta). Janela móvel recomeça terminando hoje.
- **Rótulo**: dia diz sempre o dia da semana (`Hoje, qui 01/10`, `Ontem, qua 30/09`,
  `Ter 29/09`); o resto diz o nome por extenso e o intervalo (`Semana · 28/09 a 04/10`,
  `Últimos 28 dias · 04/09 a 01/10`, `Próximos 7 dias · 01/10 a 07/10`). O chip diz `7D`
  porque o grupo diz para que lado; o botão não tem grupo. Sem travessão.

## Peças de leitura (`OperatorMetric`, `ReadFreshness`)

Subiram no PR-K2 do WP-BI-CANON-LAUDO, para o B.I., a Central, o Marketing e o Compras
não reescreverem número-herói nem selo de atualização. O Kitchen Sink mostra as duas
(seção "Peças de leitura") junto do período compacto.

- **`OperatorMetric`** é a receita do Kitchen Sink virada peça: `NuxtCard` com `title` e
  `description` (a anatomia do Card, nunca rótulo escrito à mão em `<p>`), a figura
  (`op-figure`; `hero` maior; `statement` para uma frase), a unidade na mesma linha, o
  veredito em `tone` (`error`/`warning`/`success`) e a comparação. **A peça não calcula**:
  o delta chega pronto da presentation como `MetricDelta` (`text` inteiro para o leitor
  de tela, `tone` por melhorou/piorou e não por sinal, `percent` da pílula, `direction`
  da seta, `caption` com o "contra o quê"). Sem base de comparação, `percent` vazio: a
  pílula some e a frase fica.
- **`ReadFreshness`** diz quando o servidor gerou o que está na tela e há quanto tempo,
  pelo relógio do servidor (o dispositivo com hora errada não muda a idade). É a frase
  das leituras sem tempo real, onde um selo "ao vivo" seria rótulo que mente; `failed`
  acrescenta "atualização falhou"; `realtime-label` diz o estado do transporte com o
  vocabulário do app ("Conexão: Ao vivo"), porque conexão e leitura são estados distintos.
  `inline` é a mesma frase sem faixa própria, no fim da linha de recortes. Nasceu no
  Gestor e subiu sem mudar de comportamento.

## Colunas de fila ajustáveis e recolhíveis (`QueueColumnStrip`, `QueueColumnResizeHandle`)

Forma FILA (SUITE-UX §16): uma fila em colunas deixa cada posto arrumar a tela para o
trabalho dele. A coluna aberta tem um **peso** (fração da largura entre as abertas); a
recolhida vira uma **faixa** de 56 px. Primeiro consumidor: o quadro do Gestor (Entrada,
Preparo, Saída), onde o tablet do passe fica só com a Saída.

- **Regras puras** em `app/presentation/queueColumns.ts`: `defaultQueueLayout`,
  `normalizeQueueLayout` (higiene do que veio guardado; nunca devolve todas recolhidas),
  `toggleQueueColumn` (recolher a última aberta não faz nada), `openQueueColumn`,
  `showAllQueueColumns`, `resizeQueueColumns` (a soma dos dois pesos não muda; durante o
  arraste nada fica abaixo de `QUEUE_COLUMN_MIN_PX`; ao soltar abaixo de
  `QUEUE_COLLAPSE_PX`, a coluna recolhe), `nextOpenQueueKey` (com quem a alça divide),
  `queueGridTemplate` (o `grid-template-columns`), `queueColumnForKey` (teclas 1 a 9),
  `queueViewLabel` ("Visão: Saída") e `queueStripLabel` (nome acessível da faixa).
- **`<QueueColumnStrip>`**: a coluna recolhida. Um `<button>` só, a faixa inteira é o
  gancho (`@open`), com chevron de 48 px (`size-action`). Props: `title`, `count`,
  `late` (vira o ponto vermelho e a frase "1 atrasado"), `pulse` (novidade esperando
  alguém olhar: a faixa pulsa, com `motion-safe`), `icon`, `noun` (singular e plural do
  que se conta; padrão pedido/pedidos). No `lg` é faixa vertical com o nome em pé; abaixo,
  barra baixa de largura inteira (as colunas empilham).
- **`<QueueColumnResizeHandle>`**: a alça na borda direita de uma coluna aberta que tem
  vizinha aberta (o pai põe a coluna em `relative`). Não mede nem guarda: `start` (o pai
  mede as duas colunas), `drag(deltaPx)` a cada movimento (prévia), `end(deltaPx)` uma vez
  ao soltar (o pai grava). Setas do teclado andam `QUEUE_KEYBOARD_STEP_PX`. Só aparece no
  `lg`.

**Quem guarda é o app**, e a lei L7 manda guardar no servidor, por posto: o Gestor usa
`orders/board-layout/` (`Terminal.metadata["gestor_board"]`, ver
`docs/reference/data-schemas.md`). Sem servidor, a arrumação padrão (todas abertas).

## Base de CSS (`operator-base.css`)

O núcleo de CSS dos oito apps de operador vive em
`app/assets/css/operator-base.css`, que puxa o `operator-theme.css` (tokens) ao
lado. Cobre: o `@source` do kit, a variante `dark`, fontes, animações e keyframes,
os aliases de `@theme inline`, o bloco-doc da escala de design, o `@layer base`
(reset, scrollbar, `color-scheme`, cursor de botão) e o utilitário `no-scrollbar`.

O `tailwind.css` de cada app fica com três coisas, e só elas:

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "../../../../operator-kit/app/assets/css/operator-base.css";
@plugin "@tailwindcss/forms" { strategy: "class"; }
/* e o tail do app */
```

**Por que `@import "tailwindcss"` e o `@plugin` não sobem para a base:** eles
resolvem por especificador nu, a partir do diretório do arquivo que os declara. O
kit é uma layer do Nuxt, não um app — não tem `node_modules` com o Tailwind, e não
há `node_modules` acima de `surfaces/`. Na base eles não resolveriam.

**Tail legítimo** é o que pertence a um app só: impressão térmica de 80 mm e
`.pos-tile-fallback` no POS; `.date-input-hit-area` e `forced-colors` no Produção;
`@font-face` self-hosted, alvos de toque de 44 px e `prefers-reduced-motion` no
Marketing (piloto do ADR-026). Os outros cinco apps não têm tail.

⚠️ **A armadilha do `@source`:** o caminho é relativo ao arquivo que o declara. Na
base, `../..` é a raiz `operator-kit/app`. Errar não quebra o build — o CSS compila
e as classes usadas só nos componentes do kit (`OperatorRail`, `RailItem`,
`RailToggle`, `OfflineBanner`, `UiNativeSelect`) somem do bundle em silêncio.
Medido: um `@source` errado derrubou 14 KB do CSS do `production-nuxt` com exit 0 e
zero avisos. `tests/guardrails.test.ts` resolve o caminho declarado e exige que ele
ainda alcance esses componentes; o mesmo arquivo recusa que qualquer app volte a
copiar o núcleo.

## Gráfico e quadro de leitura (`OperatorReadingChart`, `OperatorReadingCard`, `OperatorReadingPageMenu`)

PR-K1 do `docs/plans/WP-BI-CANON-LAUDO.md` (itens C1 e C2). Servem B.I., Gestor, Compras,
Marketing e Central. A parte pura (frase do ponto, legenda, tabela, CSV, teclado, eixo,
domínio) mora em `app/presentation/readingChart.ts`, testada em `tests/readingChart.test.ts`;
os componentes em `tests/components/OperatorReadingChart.test.ts`.

```html
<OperatorReadingPageMenu />  <!-- no cabeçalho da página: "Copiar link desta leitura" -->

<OperatorReadingCard title="Faturamento por dia" description="Esta semana contra a anterior"
                     :csv="readingChartCsv('Dia', series, points, { money: true })" :heading-level="3">
  <OperatorReadingChart title="Faturamento por dia" kind="comparison" axis-label="Dia"
                        :series="series" :points="points" :format="readingMoneyFormat" />
</OperatorReadingCard>
```

- **Cinco formas, e só cinco** (`kind`): `bars` (séries lado a lado), `stacked` (séries
  que são PARTES de um todo, numa barra só: "vendeu" mais "sobrou" é o que a casa fez),
  `comparison` (barras da primeira série e o traço tracejado da segunda, o período de
  comparação), `diverging` (uma série com sinal; `diverging` dá o nome de cada lado,
  "Sobrou" e "Faltou", e do zero) e `line` (linha com área). O desenho é Unovis (o Nuxt
  UI não tem Chart; o template oficial de dashboard usa Unovis), dentro de `<ClientOnly>`
  com `NuxtSkeleton` da mesma altura. Cores só do tema (`READING_TONE_COLOR`), nunca
  hexadecimal.
- **Preenchimento é a segunda codificação** (`fill` da série, nas barras): `solid` (o
  padrão), `tint` (o mesmo tom a 30%, a parte que completa o todo) e `hatch` (listrado,
  a estimativa). Os tons do tema são quentes e vizinhos (latão, âmbar, tijolo): medidos
  com o validador de paleta, latão × âmbar e latão × tijolo não se separam para quem não
  distingue vermelho de verde, e âmbar × latão nem para quem distingue. Dois segmentos
  vizinhos se diferenciam pelo preenchimento, não pela cor. A legenda desenha o mesmo
  preenchimento.
- **Deitado** (`horizontal`, só nas formas de barra): quando o eixo é de NOMES (produto,
  receita), não de datas. As categorias descem pelo eixo vertical, a primeira no topo,
  TODAS com rótulo (até 120 px, quebrando em duas linhas), e a altura cresce com elas
  (`readingHorizontalHeight`: 40 px por faixa mais a régua; `height` não vale). Cada
  faixa tem um trilho discreto que é a régua e o alvo do ponteiro (a barra curta não
  encolhe o alvo); a faixa lida fica cheia e as outras esmaecem. Sem linha de grade: ela
  cruzava as barras por cima.
- **O ponto em leitura é um só** para mouse, toque e teclado: a frase dele fica acima do
  gráfico e o traço vertical marca onde ele está. A área do gráfico é uma parada de
  tabulação (`role="group"`, nome = `title`); setas andam, Home e End vão às pontas,
  Escape solta, e o leitor de tela ouve a frase a cada seta (`role="status"`, que o passar
  do mouse não aciona). O teclado força o traço (`forceShowAt`); o ponteiro não, porque
  forçar travava o traço no primeiro ponto tocado.
- **A tabela equivalente sai no SSR** (`NuxtTable` com `caption`), com os mesmos números já
  formatados; ponto sem dado diz "sem dado", nunca zero. Ela existe sempre para o leitor de
  tela; `table-visible` a mostra também a quem enxerga.
- **O eixo tem formato próprio** (`axis-format`, PR-K5). O eixo vertical é régua e é
  estreito no celular: o dinheiro por extenso quebrava ("R$ 15." numa linha, "000,00" na
  outra). `format` vale para a frase do ponto e para a tabela; `axis-format`, só para o
  eixo. Sem `axis-format`, o eixo usa `format`, com uma exceção: com `readingMoneyFormat`
  (reais por extenso, "R$ 15.000,00"), o eixo vira `readingMoneyAxisFormat` ("R$ 15 mil",
  "R$ 1,2 mi"). O gráfico recebe reais; quem tem centavos (`_q`) divide por 100 ao montar
  os pontos. O rótulo do eixo tem 96 px antes de quebrar.
- **Buraco na série** (`null`): a linha quebra, e na forma `line` a área quebra junto. O
  Unovis lê o ponto ausente como zero, e a área descia até a base no buraco; ela agora sai
  trecho a trecho (`readingRuns`), e ponto isolado não vira área.
- **Sem pontos**, o gráfico é o `NuxtEmpty` (`empty-title`, `empty-description`).
- **O quadro** é o `NuxtCard` com `title`/`description` (Nuxt UI 4.7+). O título vira
  cabeçalho (`heading-level`, padrão 2) e nomeia a região. Com `csv`, o ⋯ oferece
  "Exportar CSV deste quadro" (ponto e vírgula, UTF-8 com marca de ordem de bytes, nome do
  arquivo saído do título); `items` acrescenta ações ao mesmo ⋯. O número sai como a
  planilha em português o lê: vírgula decimal e nenhum separador de milhar ("1234,5";
  `readingCsvNumber`), porque "1.2" ela lia como milhar ou texto. Com `{ money: true }` no
  `readingChartCsv`, os valores (em reais) saem com duas casas e sem "R$" ("1500,50";
  `readingCsvMoney`), e o cabeçalho ganha a unidade ("Esta semana (R$)").
- ⚠️ O `VisCrosshair` do `@unovis/vue` 1.7 não declara props e repassa os atributos como
  vieram: atributo hifenizado não vira config. No `OperatorReadingChartPlot.client.vue` ele
  é escrito em camelCase, com o `eslint-disable` da hifenização só em volta dele.

## O que ainda NÃO vive aqui (roadmap — ver docs/plans/completed/BACKSTAGE-EXCELLENCE-HARDENING-PLAN.md)

- **Lock do POS** — o POS mantém deliberadamente a própria variante
  (`usePosOperatorLock` + `PosLockScreen`/`PosPinChange`): auto-lock por inatividade,
  transporte via `usePosAction` e lock local-first. A família canônica
  (`useOperatorLock`/`OperatorLock`/`OperatorPinChange`) vive aqui e serve
  kds/orders/production.
- **Interceptor global de 401/403** (reabre o gate de operador) — plugin compartilhado.
- **Tooling base** (Prettier + vitest 2-projects + Playwright) — configs
  compartilhadas adotadas por cada app no seu WP. O ESLint flat já saiu do roadmap:
  ver "Lint do kit" abaixo.

## Testes do kit

```bash
npm test   # vitest: utils puros + guardrails de design system (paridade de tokens)
npm run lint   # eslint: app/, server/, runtime/, scripts/, tests/ e os configs da raiz
```

Os guardrails (`tests/guardrails.test.ts`) verificam a fonte única de tokens e os
consumidores já incorporados a cada regra. A cobertura cresce por app; a ausência de
um app numa regra específica não deve ser documentada como cobertura existente.

## Lint do kit

O kit se linta a si mesmo por `eslint.config.mjs` (raiz do layer). Ele NÃO nasce de
`./.nuxt/eslint.config.mjs` como os nove apps irmãos, e a diferença é estrutural:
esse arquivo é gerado pelo módulo `@nuxt/eslint`, e o `nuxt.config.ts` do layer não
registra módulo nenhum de propósito — módulo declarado aqui vaza por `extends` para
todas as superfícies hospedeiras. `nuxt prepare` roda no layer (gera tipos), mas
não produz config de ESLint. Então o preset é montado à mão: `@eslint/js` +
`typescript-eslint` + `eslint-plugin-vue`, a MESMA `eslint.config.base.mjs` que os
apps aplicam, e `eslint-config-prettier` por último.

Duas consequências que valem a leitura:

- **`no-undef` fica desligado** no kit. Sem `@nuxt/eslint` para declarar os
  auto-imports (`ref`, `computed`, `defineEventHandler`, `useRuntimeConfig`, …), a
  regra acusaria cada um deles. É o mesmo que o preset do Nuxt faz nos apps.
- **`Ui*.vue` do kit NÃO herda o afrouxamento de `any`.** O bloco
  `app/components/Ui/**` da base existe para as primitivas VENDADAS do ui-thing/reka-ui;
  no kit os `Ui*.vue` são planos (`app/components/UiNativeSelect.vue`) e escritos aqui.
  O glob da base não os alcança, e isso é deliberado: `@typescript-eslint/no-explicit-any`
  continua **erro** neles.

## Versões: o kit segue os irmãos, com UMA exceção declarada

A regra do ecossistema (decisão do dono, 18/09/2026) é **a mesma versão em todos os
apps, e a mais recente estável**. O `scripts/check_surface_versions.py` cobra isso em
todo PR, conferindo faixa (`package.json`) **e** versão travada (`package-lock.json`)
de cada pacote declarado por dois ou mais apps de `surfaces/`.

O kit tem **uma** divergência autorizada, e ela está escrita no `EXCEPTIONS` do próprio
guard — não vale como exceção o que não estiver lá:

- **`@iconify-json/lucide` com pino EXATO (`1.2.133`, sem `^`).** O kit define o
  conjunto de ícones que os nove apps herdam por `extends`. Faixa aberta na layer
  deixaria o mesmo nome de ícone resolver para arquivos diferentes em apps diferentes
  na mesma leva — o kit não é um consumidor a mais, é a origem do conjunto.

⚠️ **O pino exato tem um preço, e ele está medido.** Pino sem `^` tira o kit dos grupos
do Dependabot: eles passam a cobrir 9 diretórios em vez de 10, e é daí que saem os PRs
parciais (o #723 é o caso). Duas consequências práticas:

1. **Subir o `@iconify-json/lucide` do kit é passo MANUAL.** Ninguém vai abrir esse PR
   por você.
2. **A versão do kit nunca pode ficar ABAIXO da dos apps.** O guard trata isso como
   falha, de propósito: exceção autoriza *divergir*, não *ficar para trás*. Um app
   excetuado que envelhece atrás dos irmãos é a deriva usando a exceção como
   esconderijo.

Qualquer outra divergência do kit é deriva, não decisão — alinhe pelo
`python scripts/check_surface_versions.py --fix` seguido de `npm install`.
