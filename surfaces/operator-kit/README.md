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
| `server/routes/health/live.get.ts` | — | `/health/live`: processo/BFF vivo, sem chamar o Django — é o health check da plataforma |
| `server/routes/health/ready.get.ts` | — | `/health/ready`: BFF + `/health/ready/` do Django (smoke e diagnóstico, nunca health check da plataforma) |
| `server/utils/healthProbe.ts` | `ProbeRateLimiter`, `checkDjangoReadiness`, `respondHealthLive`, `respondHealthReady` | corpo pobre (`ok`/`fail`), `no-store` e limitador em memória dos probes |
| `server/utils/apiVersion.ts` | `warnOnApiVersionMismatch` | warning estruturado de major divergente do contrato |
| `app/composables/useConnectivity.ts` | `useConnectivity` | sinal offline + reconciliação no reconnect/foco |
| `app/components/OfflineBanner.vue` | `<OfflineBanner>` | aviso calmo de conexão (colocar no layout raiz) |
| `app/plugins/errorReporter.client.ts` | — | captura erro não-tratado → telemetria (inerte em dev) |
| `app/utils/deviceActivity.ts` | `deviceActivityClock`, `createDeviceActivityClock`, `deviceActivityCookieDomain` | relógio de atividade do APARELHO: cookie `shopman_operator_activity` (epoch ms) no domínio-pai (`<app>.<zona>` → `.<zona>`; localhost/IP/zona recusada pelo navegador → host-only), throttle de 5 s no próprio cookie, valor no futuro ignorado; o BFF não o repassa ao Django |
| `app/plugins/deviceActivity.client.ts` | — | todo toque real (pointerdown/keydown/wheel/touchstart/pointermove, na captura) em qualquer app marca o relógio; rota com `definePageMeta({ operatorActivity: false })` fica fora (tela do cliente do PDV). É o que faz a trava do PDV contar a ociosidade do aparelho, não só a dele |
| `app/types/operator.ts` | `OperatorCard`, `OperatorSession`, … | espelho TS da API operator/session\|eligible\|unlock\|lock |
| `app/presentation/operatorLock.ts` | `isLocked`, `buildUnlockPayload`, … | transforms puros do lock (sem I/O) |
| `app/composables/useOperatorLock.ts` | `useOperatorLock` | read/write do lock de operador (PIN/crachá) via proxy |
| `app/components/OperatorLock.vue` | `<OperatorLock>` | overlay de lock (picker + PIN pad + crachá + troca forçada) |
| `app/components/OperatorPinChange.vue` | `<OperatorPinChange>` | numpad de troca de PIN (forçada e voluntária) |
| `app/components/OperatorNumpad.vue` | `<OperatorNumpad>` | numpad de quantidade (inteiro): POS e quiosque de QC |
| `app/components/UiToolbar.vue` | `<UiToolbar>` | barra de trabalho sob o nav: slot padrão à esquerda, slot `end` à direita (com `flex-wrap`) |
| `app/components/UiSearchInput.vue` | `<UiSearchInput>` | busca da barra: ícone, limpar, expand-on-focus, `focus()` exposto para o atalho `/` |
| `app/components/UiFilterChip.vue` | `<UiFilterChip>` | pílula de filtro da barra, com contagem e slot de ícone — alvo de toque de 44 px (`min-h-control`) |
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
| `app/utils/pwaUpdateReport.ts` | `markPwaUpdateApplied`, `reportPwaUpdateApplied` | marca a troca antes do reload e a relata no boot seguinte (→ `pwa.update_applied` no Django) |
| `app/presentation/orientationLock.ts` | `orientationFamily`, `orientationLockFailure`, `ORIENTATION_LOCK_COPY` | regra pura da trava de giro: família travada, motivo da recusa e cópia ao operador |
| `app/composables/useOrientationLock.ts` | `useOrientationLock` | trava de giro por aparelho (Screen Orientation API): item "Travar giro" no `OperatorRail` só em aparelho de toque; trava só com o navegador confirmando (Android/ChromeOS instalado), recusa vira aviso ("use o bloqueio de rotação do sistema") em iOS/Windows; preferência no `localStorage`, reaplicada pelo `OperatorPwaRuntime` no boot do app instalado |

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

## Nome do app instalado (`"Nelson · PDV"`)

Todo app de operador instalado se chama `"<casa> · <App>"`: "Nelson · PDV", "Nelson ·
KDS", "Nelson · Central". A loja do cliente fica fora (é "Nelson Boulangerie").

- **A casa não mora no código.** A fonte única é `Shop.short_name` ("nome curto (PWA)",
  editável no Admin), servido por `GET /api/v1/backstage/operator/tenant/` (público,
  sem sessão: o navegador busca o manifesto sem cookie). O app declara só o rótulo em
  `definePwaCapability({ manifest: { label: "PDV", ... } })`.
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

A trava é `tests/appName.guardrails.test.ts`: varre os oito apps (rótulo sem casa, sem
`name`/`shortName` fixos, título começando pelo `name`, nenhum título com hífen de
separador, nenhum `document.title` cru).

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

Os dois lados do caminho usam a mesma peça: o ícone da Central no `OperatorRail` de cada
app, e os tiles da Central (`hub-nuxt`, `tileLinkAttrs`).

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
- A dica flutua logo acima do obstáculo, com degradê por baixo: sem ele a pílula boia
  sobre um texto qualquer e vira artefato.
- Decorativa: `aria-hidden`, sem captura de clique. **O que a impede de se ler como
  botão é a translucidez, não o tamanho**: fundo sólido com sombra vira chip clicável
  em qualquer medida. Com o fundo a 33% e sem sombra, o que sobra é o chevron, e o
  círculo só o separa do conteúdo — por isso ela pôde crescer de 28 para 48, encostando
  no alvo de toque sem se ler como controle. Sobre o degradê ela rende pouco (fundo da mesma
  cor); trabalha nas bordas e onde há contraste atrás, que é o caso do operador.
- `prefers-reduced-motion`: a dica fica **parada**, não some.

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
