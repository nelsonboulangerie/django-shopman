> Anexo do [WP-OPERADOR-NUXTUI-ONDAS](../WP-OPERADOR-NUXTUI-ONDAS.md). Leitura de código em 08/10/2026 sobre `e79ed522d` (pilha do Gestor #1528 + #1521), sem build nem navegador. Vale como mapa de arquivo:linha; o que foi visto em tela está no corpo do plano e nos PRs.

# Onda 0: inventário de KDS (Cozinha), Central (hub) e Kitchen Sink

Auditor de leitura. Worktree `operador-nuxt-ui-migracao-16676a`, branch
`claude/operador-nuxtui-onda0-base` (pilha #1528 + #1521). Nada foi editado, nenhum build
ou teste rodou. Caminhos `arquivo:linha` são relativos ao diretório do app; peças do kit
aparecem como `kit/...` (= `surfaces/operator-kit/app/...`).

Fato de partida: `git diff origin/main...HEAD -- surfaces/kds-nuxt surfaces/hub-nuxt
surfaces/kitchensink-nuxt` é **vazio**. Os três apps não mudaram nesta pilha; tudo o que
mudou para eles chegou **por herança do kit** (P1-9 do laudo). O laudo
(`docs/plans/WP-GESTOR-CANON-LAUDO.md`) não existe nesta branch; li a versão do commit
`2ef7e958b` (branch `origin/claude/gestor-canon-laudo`).

---

## Números principais

| | KDS | Central | Kitchen Sink (app + 4 SFC do kit) |
|---|---|---|---|
| Arquivos `.vue` do app | 13 (2 páginas + pickup + app + 9 componentes) | 1 (`app.vue`, 638 linhas) | 2 (`app.vue` 51, `pages/index.vue` 3) + kit 2.009 linhas |
| Rotas | `/`, `/:ref`, `/pickup` (+3 redirects 301) | `/` + rota Nitro `/shortcuts/:surface` | `/` (`?state=`, `?mode=operational`) |
| Gestos do operador inventariados | 41 | 24 | 30 (exercícios do catálogo) |
| `<button>`/`<select>`/`<textarea>` crus | 24 (= teto do ledger, 24) | 3 (= teto, 3) | 0 no app; 0 nos SFC do kit (2 `<table>` crus, 1 `<label>`, 1 `<nav>`) |
| `:ui=` | 0 | 0 | 3 (Dashboard:66, Exercises:576, :608) |
| `type="date|time"` | 0 | 0 | 0 (usa `NuxtInputDate`/`NuxtInputTime`, Exercises:525, :533) |
| Valores arbitrários `[...]` | 28 | 19 | 13 |
| `Nuxt*` do Nuxt UI usados direto | 0 (só `NuxtLink`/`NuxtPage`) | 0 | 49 tipos, cerca de 190 instâncias |
| `Ui*` (ui-thing/kit legado) | 15 tags (`UiDialog` x3 conjuntos, `UiSheet` x1, `UiFilterChip` x3) | 0 | `UiFilterChip` x2 |
| Toaster | `OperatorSonner` (vue-sonner), 8 chamadas `useSonner` | `OperatorSonner`, 0 chamadas locais | **dois**: `OperatorAppRoot` (UApp) + `OperatorSonner` |
| `OperatorAppRoot` (UApp, locale pt-BR) | não | não | sim |
| Shell | nenhum do cânone: `div flex` + `KdsNav` (`OperatorSuiteRail`/`OperatorSectionBar`) | nenhum: `OperatorSuiteRail` + `<header>` feito à mão | `OperatorOfficeShell` / `OperatorOperationalShell` |
| Copy visível com travessão | 0 (2 em fixture de prévia) | 0 | 0 |
| SSE | 2 canais (`/sse/kds/:ref`, `/sse/orders`) | nenhum (poll 30 s) | nenhum |
| Mock e2e | sim (`tests/e2e/mockBackend.mjs`, :8798) com modo prévia | sim (:8797) | não há mock: harness `KITCHENSINK_VISUAL_MATRIX=1` no `nuxt dev` |
| e2e/visual na CI | **não** (só vitest, lint, typecheck, PWA build) | **não** | **sim**: `npm run test:visual` (vermelho no #1519) |

---

## 1. KDS (`surfaces/kds-nuxt`)

### 1.1 Telas, rotas, shell

| Rota | Arquivo | O que mostra | Shell |
|---|---|---|---|
| `/` | `app/pages/index.vue` (81) | Estações: lista de `KDSInstance` com tipo, nome, contagem; Saída leva ao Gestor | `OperatorPageHeader title="Estações"` (:34), sem `#search` (cai na busca padrão da suíte) |
| `/:ref` | `app/pages/[ref].vue` (740) | Quadro da estação: avisos (pedido novo, cancelamento), "A fazer", recortes, grade em foco (tablet/desktop) ou fila de celular, polegar, detalhe, toque longo, concluídos recentes | `OperatorPageHeader title="Preparo" :eyebrow` (:295) com `#status`, `#search`, `#actions` |
| `/pickup` | `app/pages/pickup.vue` (194) | Painel PÚBLICO de retirada (TV): "Pronto para retirar" e "Em preparo", relógio, cue ao vivo | nenhum: `<div class="dark grid ...">` próprio, fora do gate e do rail (`app.vue:31`) |
| `/estacao/**`, `/cliente`, `/retirada` | `nuxt.config.ts:22-26` | 301 legados | n/a |

Casca: `app/app.vue` (66). `data-suite="v3"` (:26); `OfflineBanner` (:29); `/pickup` sem rail
(:31); operador: `div.flex` com `KdsNav place="rail"` (:36-42), `NuxtPage` (:44), `KdsNav
place="bar"` (:45), `KdsSettingsDialog` (:47); `OperatorSessionUnavailable` (:51),
`OperatorLogin` (:52), `OperatorLock` (:53-56), `OperatorStationSetup` (:57-62),
`OperatorSonner` (:63), `OperatorPwaRuntime` (:64). Permissão `backstage.operate_kds` (:8).
Tema escuro por padrão (`nuxt.config.ts:73-80`). PWA `display: fullscreen`, `wakeLock: true`,
`kiosk: true`, `idleReloadPaths: ["*"]`, push `kitchen` (`nuxt.config.ts:29-38`).

### 1.2 Gestos (inventário de zero regressão)

| # | Gesto | Onde | Efeito / endpoint |
|---|---|---|---|
| 1 | Escolher estação | `index.vue:49-76` (NuxtLink-card) | `/:ref` ou, para `type=expedition`, link externo `ordersUrl/?columns=expedition` (`presentation/exitStation.ts:14-17`) |
| 2 | Iniciar preparo (botão do card) | `KdsTicketCard.vue:374-384` → `[ref].vue:578` | `useKdsBoard.ts:283-295` POST `/api/v1/backstage/kds/tickets/:pk/start/`, otimista, fila serial, reverte com toast |
| 3 | Armar o Pronto (anti-quique) | `KdsTicketCard.vue:91-107` | botão desabilitado `KDS_ARM_DELAY_MS` depois do Iniciar |
| 4 | Pronto (bump) com janela de 5 s | `KdsTicketCard.vue:117-125` → `[ref].vue:579` | `useKdsBoard.ts:360-366`; POST `/tickets/:pk/done/` só ao fechar a janela (`:331-346`) ou no `pagehide`/aba oculta (`:233-242`, keepalive) |
| 5 | Desfazer o Pronto (no card) | `KdsTicketCard.vue:353-372` | `useKdsBoard.ts:348-354` (local, cancela o timer) |
| 6 | Toque bloqueado por item cancelado | `KdsTicketCard.vue:122` → `[ref].vue:280-284` | toast `useSonner.error` com instrução |
| 7 | Toque no Pronto travado por pagamento | `KdsTicketCard.vue:123` → `[ref].vue:286-290` | toast `useSonner.warning` com `finish_block_label/reason` |
| 8 | Abrir detalhe (área de leitura do card) | `KdsTicketCard.vue:200-207` → `[ref].vue:577` | `KdsTicketModal` (`[ref].vue:622-628`) |
| 9 | Declarar volumes (−, +, Gravar, zero apaga) | `KdsTicketModal.vue:179-223` | `useKdsBoard.ts:382-405` POST `/api/v1/backstage/orders/:ref/volumes/` (`surface: "kds"`, `base_revision`, `idempotency_key`) |
| 10 | Fechar detalhe | `KdsTicketModal.vue:68` | `[ref].vue:246-248` |
| 11 | Visto (silencia o pedido novo na estação inteira) | `[ref].vue:416-425` | `useKdsBoard.ts:171-188` POST `/kds/:ref/seen/` `{ticket_pks}` |
| 12 | Recebi o cancelamento | `[ref].vue:448-456` | `useKdsBoard.ts:372-374` POST `/tickets/:pk/acknowledge/` |
| 13 | Som: ativar quando bloqueado / abrir Ajustes | `[ref].vue:312-330`, `:475-483` | `[ref].vue:87-93` (`activateSound` do kit ou abre Ajustes) |
| 14 | Reabrir (abre concluídos recentes) | `[ref].vue:331-346` | `recallOpen` |
| 15 | Recall de concluído | `[ref].vue:678-685` | `useKdsBoard.ts:368-370` POST `/tickets/:pk/recall/` |
| 16 | Volumes a partir de concluído recente | `[ref].vue:667-677` | `openFromRecent` (`:242-245`) |
| 17 | Fechar diálogo de concluídos | `[ref].vue:642` | `UiDialog` |
| 18 | Recorte Todos / Entrega / Atrasados | `[ref].vue:495-519` (`UiFilterChip` x3) | filtro local (`presentation/board.ts`) |
| 19 | Busca da tela (código, cliente, item) | `[ref].vue:300-307` | `OperatorSuiteSearch v-model="query"` (hoje abre MODAL, ver 1.4) |
| 20 | Atalho `/` foca a busca | `[ref].vue:204-210` | chama `searchInput.focus()` = `open` do modal (`kit/components/OperatorSuiteSearch.vue:265`) |
| 21 | Limpar busca e recorte | `[ref].vue:532-538` | local |
| 22 | Ver a fila inteira (+N) | `[ref].vue:588-598` | `expanded = true` |
| 23 | Voltar à fila em foco | `[ref].vue:599-607` | `expanded = false` |
| 24 | Celular: trazer linha para o foco | `KdsPhoneQueue.vue:97-126` | `chosenPk` |
| 25 | Celular: +N na fila | `KdsPhoneQueue.vue:128-138` | `showAll` |
| 26 | Celular: botão no polegar (Teleport) | `KdsTicketCard.vue:352` + `[ref].vue:614-619` (`#kds-thumb`, `data-focus-obstruction`) | o mesmo ato do card, rótulo "Pronto W07" |
| 27 | Toque longo no ticket em foco | `KdsTicketCard.vue:85,199` (`useLongPress`) | abre `KdsHoldSheet` |
| 28 | Toque longo numa linha | `KdsPhoneQueue.vue:65-72,105-111` | idem |
| 29 | Sheet: Ver o pedido | `KdsHoldSheet.vue:41-50` | abre detalhe |
| 30 | Sheet: Desfazer o pronto | `KdsHoldSheet.vue:51-60` | `undoFinish` |
| 31 | Sheet: Reabrir um concluído | `KdsHoldSheet.vue:61-71` | `recallOpen` |
| 32 | Ajustes: tamanho do ticket (3) | `KdsSettingsDialog.vue:39-55` | `useKdsShell.ts:78-110` PATCH `/kds/:ref/settings/` |
| 33 | Ajustes: som Ligado/Desligado | `KdsSettingsDialog.vue:60-87` | idem |
| 34 | Abrir Ajustes (rail/barra, item `settings`) | `KdsNav.vue:21-23` | `useKdsSettingsOpen` |
| 35 | Rail: Estações, Preparo, Saída (externa), Painel de retirada | `KdsNav.vue:27-37`, `presentation/sections.ts:22-49` | navegação; selos (Preparo, Saída) |
| 36 | Barra do polegar: Preparo, Saída, Estações, Mais | `KdsNav.vue:38-47` (`:max="3"`) | idem |
| 37 | Bloquear / menu do operador | `KdsNav.vue:36,46` → `app.vue:41,45` | `lock` de `useOperatorLock` |
| 38 | Voltar à Central (selo) | `OperatorSuiteRail :hub-url` (`app.vue:39`) | link |
| 39 | Seguir a estação no celular (push) | `[ref].vue:267-276` | POST `/kds/:ref/follow/` no mount, só no celular |
| 40 | Estação inexistente: Ver estações | `[ref].vue:362-368` | link `/` |
| 41 | Vincular dispositivo a posto | `app.vue:16,57-62` | `OperatorStationSetup` (kit) |

Leitura (sem gesto): `GET /api/v1/backstage/kds/` (`index.vue:9`, e de novo no rail a cada
30 s, `useKdsShell.ts:129-136`), `GET /kds/:ref/` (`useKdsBoard.ts:84-94`), `GET
/kds/pickup/` (`useKdsCustomerBoard.ts:14-17`). Sessão expirada no poll reabre o gate
(`operatorSessionOnError`, `useKdsBoard.ts:93`).

Diálogos/overlays: `KdsTicketModal` (UiDialog), `KdsSettingsDialog` (UiDialog), concluídos
recentes (UiDialog inline em `[ref].vue:642-690`), `KdsHoldSheet` (UiSheet bottom), modal da
busca (kit), `OperatorLock`, `OperatorLogin`, `OperatorStationSetup`,
`OperatorSessionUnavailable`.

### 1.3 Teclado, SSE, poll, som, tela

- Teclado: só `/` (`[ref].vue:204-210`), registrado como `legacy-command` em
  `docs/reference/operator-global-shortcut-exceptions.json` (último item, owner WP-UX-13I).
  Ao migrar, a entrada precisa sair do inventário (`scripts/check_operator_shortcuts.py:52`
  reprova exceção obsoleta). Herdados do kit: `Alt 1…9` das seções e ajuda de atalhos no
  `OperatorSuiteRail` (`kit/components/OperatorSuiteRail.vue:22,108-139`).
- SSE do quadro: `openResilientEventSource` em `/sse/kds/:ref` (`useKdsBoard.ts:201-220`),
  eventos `backstage-kds-update|created|status-changed|station-changed`; BFF
  `server/routes/sse/kds/[ref].ts` → `/events/kds/:ref/`.
- SSE do painel público: `/sse/orders` → `/events/orders/`, evento `backstage-orders-update`
  (`useKdsCustomerBoard.ts:28-47`, `server/routes/sse/orders.ts`).
- Poll: quadro 15 s (`useKdsBoard.ts:227`); painel 10 s (`useKdsCustomerBoard.ts:50`);
  índice 30 s pelo rail (`useKdsShell.ts:135`). Reconexão: `visibilitychange`/`online` →
  `refresh` + `reconnectNow` (`useKdsBoard.ts:233-247`).
- Estado ao vivo honesto: `realtime` `connecting|live|polling` (`useKdsBoard.ts:134`),
  `realtimeIndicator` (`presentation/board.ts:446-475`), tom para o kit em
  `[ref].vue:136-144`.
- Som: `useAlertSound("kds_sound_<ref>", KDS_ALERT)` do kit (`useKdsBoard.ts:114-123`), fanfarra
  escolhida pelo dono (`:18-51`, "não se mexe sem passar pelo mesmo teste"); toca por
  identidade de ticket não visto (`:55-77`), cala no Visto; vibração 400 ms no celular
  (`:147-155`); destravar autoplay pelo toque (`[ref].vue:87-93`). Som é da estação
  (`:138-145`).
- Tela sempre ligada: `wakeLock: true` na capability PWA (`nuxt.config.ts:32`), executada por
  `OperatorPwaRuntime` (`kit/composables/useWakeLock.ts`). Kiosk + recarga ociosa em qualquer
  rota.

### 1.4 Peças do operator-kit usadas

| Peça | Contagem | Onde | Estado herdado nesta pilha |
|---|---|---|---|
| `OperatorPageHeader` | 2 | `index.vue:34`; `[ref].vue:295` (slots `#status` :296, `#search` :299, `#actions` :311 com `v-if="!isPhone"`) | virou `NuxtDashboardNavbar` de altura fixa (laudo H6): `eyebrow` "Estação X" vira `NuxtBadge` ao lado do título; `#actions` (som, Reabrir, relógio) dentro do `#right`; sem `bg-card` |
| `OperatorLiveStatus` | 1 | `[ref].vue:297` (`tone` live/calm/off) | **P0-5/H2 vivo aqui**: `kit/components/OperatorLiveStatus.vue:24-26,36` pinta `calm` de verde "On HH:MM"; poll de 15 s (SSE caído) fica igual a ao vivo; o texto "Atualiza a cada 15 s" só vai para `aria-label`/`title` |
| `OperatorSuiteSearch` | 1 | `[ref].vue:300-307` (`v-model`, `screen-label="filtrando os tickets"`, `class="suite:md:w-[19rem]!"`) | **H7**: virou `NuxtDashboardSearchButton` + `NuxtModal` (`OperatorSuiteSearch.vue:268-297`); o filtro da grade acontece dentro de um modal que cobre a grade; o `/` abre o modal |
| `UiFilterChip` | 3 | `[ref].vue:495, 499, 509` (+ `class="suite:border-destructive/50! suite:text-destructive!"` :514) | **H5**: virou `NuxtButton soft/outline` + `NuxtBadge`, perdeu `min-h-control` (44 px) e a pílula; os overrides `suite:` do "Atrasados" não casam mais com a anatomia nova |
| `OperatorSuiteRail` | 1 | `KdsNav.vue:27-37` (`foot-order="inbox-first"`, `hub-url`) | **H9**: Avisos virou sino neutro sem rótulo sobre o bronze |
| `OperatorSectionBar` | 1 | `KdsNav.vue:38-47` (`:max="3"`) | **H8**: menu horizontal, rótulos truncam a 360 px |
| `OperatorSonner` + `useSonner` | 1 + 8 | `app.vue:63`; `useKdsBoard.ts:185,292,313,343,399`; `useKdsShell.ts:105`; `[ref].vue:281,289` | vue-sonner; o Gestor já usa `useToast` via shim `orders-nuxt/app/utils/operatorToast.ts` |
| `OperatorLogin`, `OperatorLock`, `OperatorSessionUnavailable`, `OperatorStationSetup`, `OperatorPwaRuntime`, `OfflineBanner` | 1 cada | `app.vue:52,53,51,57,64,29` | H11 (PIN menor), H12 (Alert como título), H4 (`NuxtSelect` do posto a cerca de 32 px) |
| `UiDialog*` / `UiSheet*` (biblioteca `kit/components/Ui/`) | 3 / 1 | `[ref].vue:642`, `KdsTicketModal.vue:68`, `KdsSettingsDialog.vue:21`; `KdsHoldSheet.vue:31` | primitiva paralela (laudo Anexo A) |
| Composables/utils | | `useOperatorLock` (app:9), `useStationSetupOffer` (app:16), `useOperatorWindowTitle` (app:20), `useAlertSound`, `openResilientEventSource` (import relativo `../../../operator-kit/...`, `useKdsBoard.ts:16`, `useKdsCustomerBoard.ts:10`), `ssePath`, `httpError`, `httpErrorMessage`, `operatorSessionOnError`, `useWebPush` (`[ref].vue:267`), `proxyEventStream` (server), tipo `OperatorSection` (`presentation/sections.ts:6`) | |
| **Não usa** | | `OperatorAppRoot`, `OperatorSuiteShell`, `OperatorOperationalShell`, `OperatorUrgentAlert`, `MoreBelow`, `useNextFocus` | sem `UApp`: os `Nuxt*` que o kit monta (modal da busca, badges) rodam sem locale pt-BR e sem toaster do Nuxt UI |

### 1.5 Componentes locais

| Componente | Linhas | Papel | Destino sugerido |
|---|---|---|---|
| `KdsTicketCard.vue` | 410 | ticket: identidade, relógio, pílula, itens, notas, bloqueio, botão, desfazer com dreno, Teleport ao polegar, toque longo | fica local (domínio), recomposto: `NuxtCard`/`NuxtPageCard highlight` no próximo, `NuxtBadge` (pílula, Adicional, relógio), `NuxtAlert` (bloqueio, notas), `NuxtProgress` (dreno) |
| `KdsCardButton.vue` | 54 | botão de largura total com 6 tons (`lead/invite/confirm/outline/blocked/locked`) | morre: `NuxtButton block size="xl"` com `color`/`variant`; o tom `locked` (listrado) precisa de decisão (variant não existe) |
| `KdsTicketModal.vue` | 262 | detalhe + volumes | `NuxtModal` (ou `NuxtSlideover`); stepper vira `NuxtInputNumber`; barra SLA vira `NuxtProgress` |
| `KdsPhoneQueue.vue` | 144 | celular: foco + linhas + "+N" | local; linhas como `NuxtButton block variant="outline"` ou lista; candidato a subir se a Produção tiver a mesma fila |
| `KdsHoldSheet.vue` | 76 | menu do toque longo | `NuxtDrawer` (bottom) com `NuxtButton`s, ou `NuxtContextMenu` |
| `KdsSettingsDialog.vue` | 96 | densidade e som da estação | `NuxtModal` + `NuxtRadioGroup variant="card"` (ou `NuxtTabs`) |
| `KdsAllDayStrip.vue` | 93 | "A fazer" numa linha, mede chips (`querySelectorAll`, :26) | local; chips viram `NuxtBadge size="lg"`; a régua invisível fica |
| `KdsNav.vue` | 48 | adaptador rail/barra | morre se o KDS adotar `OperatorSuiteShell` (seções num só array com `where`) |
| `KdsTestOrderBanner.vue` | 17 | aviso de pedido de teste iFood | `NuxtAlert color="warning" variant="subtle"` (ou `NuxtBadge`); morre |
| Composables `useKdsBoard` (437), `useKdsShell` (167), `useKdsCustomerBoard` (62), `useLongPress` (73), `useKdsDensity` (28) | | lógica | ficam; `useLongPress` é candidato ao kit (Gestor perdeu o deslizar/polegar, P0-6) |

### 1.6 Escapes do cânon

Contagens: (a) `:ui=` 0 · (b) HTML cru que imita componente: 24 botões + 11 blocos
alerta/pílula/vazio/carregando · (c) `type="date|time"` 0 · (d) classes que imitam
componente: 8 `pill-*` (`index.vue:67`, `[ref].vue:437`, `KdsTicketCard.vue:233`,
`presentation/board.ts:74-78`) + tons de botão em `KdsCardButton.vue:31-39` + 6 funções de
classe em `presentation/board.ts` (`toneBar` :21, `toneNextSurface` :35, `toneTimerChip` :46,
`pillClass` :81, `toneTimer` :86, `dotClass` :458-473) · (e) arbitrários 28 · (f) paralelas:
`UiDialog` x3, `UiSheet` x1, `UiFilterChip` x3, vue-sonner, `KdsCardButton` · (g) travessão 0 na
tela (2 nas fixtures de prévia: `previewFixtures.mjs` a nota "Alergia a castanhas" e
o item "Baguete tradicional", ambos com travessão).

Os 30 mais relevantes:

| # | Onde | O que é | Componente oficial |
|---|---|---|---|
| 1 | `KdsCardButton.vue:44-53` | botão do ato com tons próprios, usado em todo card | `NuxtButton block` (`color`/`variant`/`size`) |
| 2 | `KdsTicketCard.vue:191-196` | `<article>` com borda e fundo por estado (`surface` :157-163) | `NuxtCard` / `NuxtPageCard` `highlight` (receita "item da vez", kitchen-sink.md:222-224) |
| 3 | `presentation/board.ts:35-41` | halo `shadow-[0_0_0_4px_color-mix(...)]` no próximo | `NuxtPageCard highlight` |
| 4 | `KdsTicketCard.vue:249-259` | relógio como chip | `NuxtBadge` (cor do semáforo) |
| 5 | `KdsTicketCard.vue:260-267` | pílula de estado com ponto | `NuxtBadge variant="soft"` com `NuxtChip`/ícone leading |
| 6 | `KdsTicketCard.vue:231-236` | pílula "Adicional" | `NuxtBadge color="info"` |
| 7 | `KdsTicketCard.vue:336-346` | caixa do bloqueio de pagamento | `NuxtAlert color="error" variant="subtle"` (ou pílula + Popover, kitchen-sink.md:226-231) |
| 8 | `KdsTicketCard.vue:319-333` | notas do pedido em caixa âmbar | `NuxtAlert color="warning"` |
| 9 | `KdsTicketCard.vue:200-207` | `<button>` absoluto como área de leitura | `NuxtButton`/`NuxtLink` cobrindo, ou card clicável (`NuxtPageCard` com `@click`) |
| 10 | `KdsTicketCard.vue:360-362` | barra que escoa | `NuxtProgress` |
| 11 | `[ref].vue:399-426` | faixa "Pedido novo" com Visto | `NuxtAlert color="info"` com `actions` |
| 12 | `[ref].vue:428-457` | cartão vermelho de cancelamento com ação | `NuxtAlert color="error"` com `actions` |
| 13 | `[ref].vue:357-369` | "Esta estação não existe mais" + link | `NuxtEmpty` ou `NuxtAlert` com ação |
| 14 | `[ref].vue:372-383` | erro de carga / "Sem conexão" | `NuxtAlert` (error/warning) |
| 15 | `[ref].vue:388-395` | "Toca e vibra mesmo com a tela apagada" | `NuxtAlert color="success" variant="subtle"` ou `NuxtBadge` |
| 16 | `[ref].vue:466-484` | vazio "Tudo em dia" | `NuxtEmpty` com `actions` |
| 17 | `[ref].vue:524-539` | sem resultado de busca | `NuxtEmpty` |
| 18 | `[ref].vue:354`, `index.vue:39` | "Carregando…" em texto | `NuxtSkeleton` na geometria final |
| 19 | `[ref].vue:312-330` | botão de som com 3 estados | `NuxtButton` (`color="warning"` quando bloqueado) |
| 20 | `[ref].vue:331-346` | "Reabrir" com contador em `span` | `NuxtButton` + `NuxtBadge` (trailing) |
| 21 | `[ref].vue:642-690` | diálogo de concluídos com lista e botões crus | `NuxtModal` + lista + `NuxtButton` |
| 22 | `[ref].vue:495-519` | recortes como `UiFilterChip` | `NuxtTabs` (como o Gestor) ou `NuxtButton`s |
| 23 | `[ref].vue:588-607` | "+N · Ver a fila inteira" e voltar | `NuxtButton block variant="outline"` |
| 24 | `index.vue:49-76` | NuxtLink com classes de card | `NuxtPageCard to` (receita de navegação, kitchen-sink.md:238-239) |
| 25 | `index.vue:65-71` | contagem em `pill-primary` | `NuxtBadge` |
| 26 | `index.vue:40-45` | "Nenhuma estação configurada" tracejado | `NuxtEmpty` |
| 27 | `KdsTicketModal.vue:183-206` | stepper − N + e Gravar | `NuxtInputNumber` + `NuxtButton` |
| 28 | `KdsTicketModal.vue:147-153` | barra SLA `bg-white/5` | `NuxtProgress` |
| 29 | `KdsSettingsDialog.vue:39-87` | `role="radio"` feito à mão (5 botões) | `NuxtRadioGroup variant="card"` |
| 30 | `KdsHoldSheet.vue:31-75` + `KdsPhoneQueue.vue:97-138` | sheet e linhas com `<button>` | `NuxtDrawer` + `NuxtButton` |

Arbitrários (28): `KdsAllDayStrip.vue:56` `w-[86px]` (casado com `LABEL` :11, motivo
implícito); `KdsSettingsDialog.vue:22` `max-h-[85vh]`; `KdsCardButton.vue:38` gradiente
listrado; `:46` `active:scale-[0.99]`; `KdsTicketModal.vue:71` `max-h-[90vh]`, `:149`
`transition-[width]`; `pickup.vue:37` `grid-rows-[auto_1fr]`; `KdsHoldSheet.vue:32`
`pb-[env(safe-area-inset-bottom)]` (motivo: safe area); `board.ts:37-40` 3 halos (motivo
escrito em :31-33); `KdsTicketCard.vue:184` `leading-[1.375rem]`, `:289` `w-[2.5ch]`;
`[ref].vue:303` `suite:md:w-[19rem]!`, `:326,:340` `size-[18px]`, `:406,:431`
`min-h-[60px]`, `:406` `md:min-w-[18rem]`, `:412` `basis-[10rem]`, `:431`
`md:min-w-[22rem]`, `md:flex-[1.35]`, `:434` `basis-[14rem]`, `:450,:670,:680`
`active:scale-[0.98]`, `:643` `max-h-[85vh]`. Cores Tailwind fora do tema:
`board.ts:22-23` `bg-red-500/bg-amber-500`, `:87-90` `text-red-300/amber-300`,
`border-white/10`, `:458,:466` `bg-green-500/amber-500`; `pickup.vue:99`
`dark:text-lime-300`; `KdsTicketModal.vue:147` `bg-white/5`.

### 1.7 Testes e travas que vão quebrar ou mudar

- `tests/components/KdsTicketCard.test.ts` (400): seleciona `button[data-kds-action]`,
  `[data-kds-open]`, `[data-kds-undo]`, `[data-kds-pill]`, `[data-kds-finish-block]`,
  `[data-kds-test-order]`, `[data-kds-overline]`; afirma CLASSES: `h-11/h-14/h-16` por
  densidade (:249-261), `border-primary` e ausência de `ring` (:263-268), `bg-primary`,
  `border-foreground/80`, `bg-success` por tom (:347-356 aprox.), `rounded-lg` e `px-3.5`
  (:340-345 aprox.), `border-dashed` no travado, `text-xl`/`text-4xl` no código
  (:151-158), `.line-through` (:86). Trocar para `NuxtButton`/`NuxtBadge` reescreve a
  maior parte das asserções de classe.
- `tests/components/KdsTicketModal.test.ts` (96): stubs `UiDialog*` como passthrough (:48-55);
  migrar para `NuxtModal` exige stub novo (no Gestor isso virou o problema dos dublês, T5).
  O harness de componente roda `@vitejs/plugin-vue` sem runtime Nuxt (`vitest.config.ts`),
  igual ao Marketing que quebrou com `<NuxtModal>` inerte (P0-4).
- `tests/board.test.ts` (497) e `tests/composables/useKdsBoard.test.ts` (499): puros/composable;
  só quebram se `presentation/board.ts` perder as funções de classe (`toneNextSurface`,
  `pillClass` etc.).
- `tests/realtimeIndicator.test.ts` (23): crava `dotClass` verde/âmbar/neutro.
- `tests/sections.test.ts` (44): crava a ordem das seções por `place`; muda se o KDS passar
  para `OperatorSuiteShell` (um array, com `where`).
- `tests/prontoVocabulary.test.ts`, `tests/exitStation.test.ts`, `tests/securityConfig.test.ts`:
  estáveis.
- Kit: `guardrails.appBar.test.ts:82-109,118-125,218-224` exige que `kds-nuxt/app/components/KdsNav.vue`
  exista com `<OperatorSuiteRail` E `<OperatorSectionBar`, sem `<nav`, e com
  `:operator-name=` e `@lock="emit('lock')"` na barra; apagar o `KdsNav` reprova.
  `guardrails.test.ts:163` (escala tipográfica: proíbe `text-2xl`/`text-[..]`).
  `guardrails.suiteSearch`, `.vocabulary`, `.noEmDash`, `.pendingAction`, `.a11y` varrem o
  app pelo registro.
- Ledger: `docs/reference/operator-component-ledger.json` KDS `native_control_occurrences: 24`
  (teto que só desce); `scripts/check_operator_component_ledger.py:35-40,297-306` reprova
  `NuxtDashboard*`, `NuxtNavigationMenu`, `NuxtPage*` de layout no app: a migração tem de
  passar pelas peças do kit (`OperatorSuiteShell`/`OperatorOperationalShell`).
- Atalho `/`: `operator-global-shortcut-exceptions.json` (KDS `[ref].vue`); exceção obsoleta
  reprova.
- Omotenashi browser CI (`.github/workflows/omotenashi-gate.yml`,
  `scripts/run_omotenashi_browser_ci.sh:122,162`) builda e serve o KDS contra Django real;
  o check `tablet.kds.station` (`shopman/backstage/services/omotenashi_qa.py:255-272`) é
  por URL e expectativa, não por seletor.

### 1.8 Mock visual

- `tests/e2e/mockBackend.mjs` (91, porta 8798) ramifica pelo cookie `e2e_session=authed`;
  modo `KDS_MOCK_FIXTURE=preview` serve `tests/e2e/previewFixtures.mjs` (7 tickets na
  estação `bancada`, iniciar e Pronto mudam o quadro).
- Build de produção contra o mock: `playwright.config.ts:21-38`, `nuxt build && node
  .output/server/index.mjs` na :3103 com `NUXT_DJANGO_BASE_URL=http://127.0.0.1:8798`
  (o KDS não liga `operatorUpstreamFailFast`, então não precisa de
  `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM`). Prévia: `npm run preview:cards`
  (`tests/preview/serve.mjs`, mock :8799 + `nuxt dev` :3013); fotos em
  `tests/preview/capture.mjs`. Para ver o build de produção com a prévia:
  `KDS_MOCK_FIXTURE=preview MOCK_PORT=8798 node tests/e2e/mockBackend.mjs` + o mesmo
  comando do webServer.
- e2e existentes: `guards.spec.ts` (gate, rail, `/pickup` público), `resilience.spec.ts`
  (offline). **Nenhum job da CI roda o e2e do KDS** (`surfaces-gate.yml` só roda
  `test:e2e` para Marketing e Produção).
- Lacunas de fixture (por leitura):
  1. **Painel público sem fixture válida**: o mock casa `/kds/cliente/` (`mockBackend.mjs:67`),
     o app pede `/api/v1/backstage/kds/pickup/` (`useKdsCustomerBoard.ts:15`). Sem cookie
     cai no 403 (:74); com cookie ou prévia casa como estação (`:79-80`, `:83`) e devolve o
     quadro, não `{status}`. O `/pickup` sempre renderiza vazio. O guard e2e só olha o h1.
  2. Projection incompleta frente ao contrato (`app/generated/kdsContract.ts:15-66`): faltam
     `seen` (todo ticket da prévia vira "não visto" e dispara a fanfarra),
     `finish_block_label/reason`, `volumes*`, `started_by`, `started_at_display`,
     `is_preorder`, `due_time_display`, `density`, `sound_enabled`; sobram campos mortos
     (`service_date`, `today`, `available_dates`, `previewFixtures.mjs:134-137`).
  3. Telas sem fixture: cancelamentos (`cancelled_tickets: []`), concluídos recentes e
     recall (`recent_done: []`), bloqueio por pagamento (cadeado), volumes, estação 404,
     erro com cache, densidades compacta/ampla, som bloqueado, celular com push, Ajustes.
  4. POSTs `seen`, `acknowledge`, `recall`, `volumes`, `follow`, `settings` (PATCH) caem no
     `{}` genérico; `write()` só conhece `start|done` (`previewFixtures.mjs:155-165`).
  5. `capture.mjs` grava `localStorage kds.density` (prévia antiga); a densidade hoje vem da
     estação.

### 1.9 Riscos específicos

1. **Toque**: o card tem DOIS alvos (área de leitura abre detalhe; botão faz o ato) e um
   anti-quique de armar (`KdsTicketCard.vue:87-107`). `NuxtButton` com `loading`/`disabled`
   precisa manter o `disabled` durante o armar e o mesmo lugar do botão nos dois estados.
   Alturas `h-11/h-14/h-16` por densidade são contrato testado; o `md` do Nuxt UI tem cerca
   de 32 px e o kit tirou a regra coarse 48 px (H4).
2. **Polegar no celular**: `Teleport defer` para `#kds-thumb` (`KdsTicketCard.vue:352`,
   `[ref].vue:614-619`) e toque longo com engolir o clique (`useLongPress.ts:50-55`). Trocar
   `<button>` por `NuxtButton` muda o elemento que recebe `pointerdown`/`click.capture`.
3. **Posto e estação**: `useKdsStation` lembra a estação por dispositivo (`useKdsShell.ts:33-57`),
   Ajustes gravam na estação (PATCH) e o rail relê o índice a cada 30 s. Se o shell virar
   `OperatorSuiteShell`, falta nele `footOrder="inbox-first"` e `hub-url` (só o
   `OperatorSuiteRail` tem, `OperatorSuiteRail.vue:46,63`), e as seções de rail e barra
   têm ORDENS diferentes (`sections.ts:27-48`).
4. **Som**: a fanfarra e o Visto por estação são decisão do dono; não mexer em
   `KDS_ALERT`. O botão de destravar autoplay (`[ref].vue:87-93`) é o único caminho quando o
   navegador bloqueia; não pode sumir para o celular (no celular o `#actions` não
   renderiza: `[ref].vue:311`).
5. **Tela sempre ligada / kiosk**: depende de `OperatorPwaRuntime` montado; `OperatorAppRoot`
   precisa conviver com `display: fullscreen` e com o tema escuro forçado
   (`colorMode.preference: 'dark'`). O kit desliga o colorMode do Nuxt UI
   (`kit/nuxt.config.ts:35`).
6. **Ao vivo mentindo hoje** (P0-5): no KDS, SSE caído aparece igual a ao vivo. Corrigir
   antes de qualquer migração visual, ou o teste novo vai cristalizar o verde.
7. **Busca em modal** (H7): o cozinheiro filtra a grade e não vê a grade. Decisão de
   produto antes de migrar.
8. **Toaster**: migrar para `useToast` sem `OperatorAppRoot` faz os 8 avisos de falha
   sumirem em silêncio (H14). Os toasts do KDS são o único aviso de "não deu para marcar
   Pronto".
9. **Painel público** (`/pickup`): exceção funcional aceita pelo doc (kitchen-sink.md:339-341),
   mas **sem registro** em `operator-layout-exceptions.json`. Não pode herdar shell nem
   gate; tem `dark` forçado e paleta local (`lime-300`).
10. `OperatorUrgentAlert` (modal que interrompe) chega junto com o `OperatorSuiteShell`
    (`OperatorSuiteShell.vue:274`): decidir se a cozinha recebe modal de aviso com prazo.

---

## 2. Central (`surfaces/hub-nuxt`)

### 2.1 Telas, rotas, shell

Uma tela só, `app/app.vue` (638), sem `pages/`. Estados mutuamente exclusivos:
login (`:193-203`, `OperatorLogin mode="page"`), falha bloqueante (`:208-229`), dispositivo
travado (`:232`, `OperatorLock perm=""`), launcher (`:235-627`). Launcher:
`OperatorSuiteRail` com "Início" como única seção (`:239-245`, `HUB_SECTIONS`
`presentation/hub.ts:310`), `<header>` feito à mão de 56/76 px (`:253-306`) com saudação,
data, assinatura, busca hero e ações de celular; "Precisa de você" (`:324-458`, lista fina
no celular `:344-392`, lista com gesto no tablet+ `:394-454`); "Apps" (`:462-605`, linhas de
62 px no celular `:472-532`, grade de blocos `:533-604`); `MoreBelow` (`:607`); rodapé com
`OperatorPushSettings variant="line"` e versão (`:615-625`). Rota Nitro
`server/routes/shortcuts/[surface].get.ts` (302 para orders/pos/production, usada pelos
atalhos do manifesto PWA, `nuxt.config.ts:43-47`). Tema claro (`nuxt.config.ts:76-84`).

### 2.2 Gestos

| # | Gesto | Onde | Efeito |
|---|---|---|---|
| 1 | Entrar (usuário/senha) | `app.vue:193-203` | `OperatorLogin` POST `/api/v1/backstage/operator/login/` |
| 2 | Tentar de novo (falha transitória) | `app.vue:220-227` | `refresh()` do hub |
| 3 | Identificar-se no dispositivo travado | `app.vue:232` | `OperatorLock` (PIN/crachá) |
| 4 | Rail: Início | `app.vue:239-245` | `/` |
| 5 | Rail: Avisos | via `OperatorSuiteRail` (`OperatorInbox placement="rail"`) | caixa de Avisos |
| 6 | Rail: Bloquear o dispositivo | `app.vue:244` | `lockDevice` (`:121-128`) POST `/api/v1/backstage/operator/lock/` `{scope: "device"}` |
| 7 | Rail: menu do operador / atalhos / tema | `OperatorSuiteRail` | kit |
| 8 | Mostrar a barra (rail recolhido) | `app.vue:270-280` | `setRail('compact')` |
| 9 | Selo da Central (celular) | `app.vue:255-269` (span+img) e `:282` (`OperatorAppSeal home`) | identidade, sem link |
| 10 | Busca hero da suíte (+câmera) | `app.vue:295` | `OperatorSuiteSearch variant="hero"` (modal, `/` e `Meta+K`) |
| 11 | Avisos no celular | `app.vue:302` | `OperatorInbox placement="header"` |
| 12 | Menu do operador no celular (Bloquear) | `app.vue:303` | `OperatorPhoneMenu` → `lockDevice` |
| 13 | Item da fila no celular (linha inteira) | `app.vue:346-381` | link `item.url` (alvo pela instalação PWA, `:181-183`) |
| 14 | Ver mais N (celular) | `app.vue:384-392` | `phoneQueueOpen` |
| 15 | Gesto do item (tablet+) | `app.vue:440-452` | link `item.url`, largura fixa 164 px |
| 16 | App no celular (linha 62 px) | `app.vue:477-530` | link `tile.url`, `tileLinkAttrs` (instalada → janela própria; `external` → nova aba) |
| 17 | Bloco do app (tablet+) | `app.vue:535-602` | idem |
| 18 | Ícone real do app com queda para Lucide | `app.vue:159-170, 366, 416, 496, 566` | `@error` + varredura `querySelectorAll` no mount |
| 19 | Ativar push / dispositivos que recebem | `app.vue:617-623` | `OperatorPushSettings` (kit) |
| 20 | Vincular dispositivo a posto | `app.vue:78-82, 629-634` | `OperatorStationSetup` |
| 21 | Atalhos do PWA (Pedidos, Caixa, Produção) | `nuxt.config.ts:43-47` + `server/routes/shortcuts/[surface].get.ts` | 302 para a superfície |
| 22 | Reconectar | `app.vue:132-133` | `useConnectivity().onReconnect(refresh)` |
| 23 | Voltar à aba | `useOperatorHub.ts:34-41` | `visibilitychange` → refresh |
| 24 | Sessão expirada | `app.vue:136,152` | volta ao login |

### 2.3 Teclado, SSE, push

- Teclado: nenhum listener local. Herdados: `/` e `Meta+K` da busca hero
  (`OperatorSuiteSearch.vue` `kbds`), `Alt 1…9` e ajuda no rail.
- SSE: **nenhum** (decisão escrita em `useOperatorHub.ts:9-12`). Poll de 30 s só com a aba
  visível (`presentation/hub.ts:302`, `useOperatorHub.ts:29-41`). Relógio de 1 s pela hora do
  servidor (`app.vue:98-111`, `serverClockOffset`).
- `live-dot` verde fixo ao lado da assinatura (`app.vue:286`, utilitário em
  `kit/assets/css/operator-suite.css:119-127`): a Central não tem estado ao vivo e o ponto
  é sempre verde. Pela regra do próprio kit ("a cor nunca fala sozinha") é sinal sem
  significado; candidato a `OperatorLiveStatus` honesto ou a sair.
- Push: categorias `campaign, production, order, purchase, report, kitchen, sign_in, system`
  (`nuxt.config.ts:39-42`); clique da notificação abre `action_url` assinada
  (`tests/e2e/push.spec.ts`). Sem som.

### 2.4 Peças do operator-kit

| Peça | Contagem | Onde |
|---|---|---|
| `OperatorSuiteRail` | 1 | `app.vue:239` |
| `OperatorSuiteSearch` (`variant="hero"`) | 1 | `app.vue:295` |
| `OperatorInbox` (header) | 1 | `app.vue:302` (permitido por `guardrails.appBar.test.ts:149`) |
| `OperatorPhoneMenu` | 1 | `app.vue:303` |
| `OperatorAppSeal home` | 1 | `app.vue:282` |
| `OperatorPushSettings variant="line"` | 1 | `app.vue:617` (tem `:ui=` no kit, `OperatorPushSettings.vue:153`) |
| `MoreBelow` | 1 | `app.vue:607` |
| `OperatorLogin`, `OperatorLock`, `OfflineBanner`, `OperatorStationSetup`, `OperatorSonner`, `OperatorPwaRuntime` | 1 cada | `:193, :232, :190, :629, :635, :636` |
| Composables | | `useOperatorAppLink` :45, `useApiPath` :51, `useOperatorWindowTitle` :55, `useStationSetupOffer` :78, `useSuiteRailShown` :115, `usePendingAction` :121, `useRailState` :129, `useConnectivity` :132, `useOperatorSession` :136, `isUnauthenticatedError`/`isStationLockedError`/`isTransientError`/`httpError` :145-148, `operatorAppNamed`, `operatorShortcutIconSrc` (presentation) |
| **Não usa** | | `OperatorPageHeader`, `OperatorLiveStatus`, `OperatorAppRoot`, nenhum shell do cânone, nenhum `Ui*` |

Herança desta pilha: H9 (sino sem rótulo no rail), H7 (busca hero já era modal, sem
mudança de função), H4 (`NuxtSelect` do posto), H11/H12 (trava), H14 (dois contratos de
toast; a Central não chama `useSonner`).

### 2.5 Componentes locais

Nenhum componente; tudo em `app.vue`. Candidatos a extrair ou subir:
- cabeçalho de saudação + busca hero (`:253-306`): hoje viola "inventar cabeçalho local"
  (kitchen-sink.md:119); ou vira `OperatorPageHeader` com slot hero, ou exceção registrada;
- linha da fila "Precisa de você" (`:345-382`, `:395-453`): é a "attention list" da matriz
  (kitchen-sink.md:318); candidata ao kit (o Gestor tem lista equivalente de avisos);
- bloco de app (`:534-603`): `NuxtPageCard` com `to`, ícone e descrição
  (kitchen-sink.md:238-239, "metric tile");
- tela de falha (`:208-229`): `NuxtEmpty` com `actions`, ou `OperatorSessionUnavailable`.

Lógica pura que fica: `presentation/hub.ts` (326), `useOperatorHub.ts` (49).

### 2.6 Escapes do cânon

Contagens: (a) 0 · (b) 3 botões crus + 1 `<header>` + cartões/listas por classes (8 blocos)
· (c) 0 · (d) cards por classes `rounded-[14px] border bg-card` (5), listas `divide-y rounded-xl
border bg-card` (3), pontos de estado `size-[7px] rounded-full` (2) · (e) 19 · (f) vue-sonner,
`<img>` com fallback manual no lugar de `NuxtAvatar` · (g) 0 na tela.

| # | Onde | O que é | Oficial |
|---|---|---|---|
| 1 | `app.vue:253-306` | `<header>` local de 56/76 px | `OperatorPageHeader` (Navbar oficial via kit) |
| 2 | `app.vue:208-229` | cartão de falha + botão cru | `NuxtEmpty` com `actions` (ou `NuxtCard`) |
| 3 | `app.vue:220-227` | `<button>` "Tentar de novo" | `NuxtButton` |
| 4 | `app.vue:270-280` | `<button>` "Mostrar a barra" | `NuxtButton square variant="ghost"` (o `OperatorPageHeader` já tem, `kit/.../OperatorPageHeader.vue:99-110`) |
| 5 | `app.vue:384-392` | `<button>` "Ver mais N" | `NuxtButton block variant="ghost"` |
| 6 | `app.vue:255-269` | selo do celular `span`+`img` | `OperatorAppSeal` (já montado em `:282`; ver risco 2.9.3) |
| 7 | `app.vue:310-318` | vazio "Nenhum app liberado" tracejado | `NuxtEmpty` |
| 8 | `app.vue:333-339` | "Nada esperando" em caixa | `NuxtEmpty` (variant compacta) ou texto |
| 9 | `app.vue:344-383` | lista da fila no celular por classes | `NuxtCard` + lista, ou `NuxtPageCard`s |
| 10 | `app.vue:394-454` | lista da fila tablet+ por classes | `NuxtCard` com lista/`NuxtTable` |
| 11 | `app.vue:440-452` | `<a>` com classes de botão | `NuxtButton to` (`:target`) |
| 12 | `app.vue:472-532` | lista de apps no celular por classes | `NuxtPageCard`s ou lista em `NuxtCard` |
| 13 | `app.vue:533-604` | grade de blocos `rounded-[14px] border bg-card` | `NuxtPageGrid` + `NuxtPageCard to` |
| 14 | `app.vue:354-369, 404-418, 484-499, 554-569` | `<img>` com queda para `Icon` | `NuxtAvatar` (`src` + `icon`, como o `OperatorAppSeal`) |
| 15 | `app.vue:374-379, 503-511, 579-588` | ponto de tom `size-2/size-[7px] rounded-full` | `NuxtChip standalone` |
| 16 | `app.vue:286` | `live-dot` verde fixo | `OperatorLiveStatus` honesto, ou remover |
| 17 | `app.vue:326-329, 464-466` | contagem ao lado do título | `NuxtBadge` |
| 18 | `app.vue:166-170` | `document.querySelectorAll("img[data-app-icon]")` | `@error`/`NuxtAvatar` resolve sem varredura |
| 19 | `app.vue:209,310,539` `rounded-[14px]`; `:256,485,492,555,562` `rounded-[10px]` | raios locais | raio do tema |
| 20 | `app.vue:253` `md:h-[76px]`; `:309,616` `max-w-[1120px]`; `:420` `md:w-[76px]`; `:436` `w-[108px]`; `:446` `md:w-[164px]`; `:481` `min-h-[62px]`; `:504,580` `size-[7px]`; `:575` `min-h-[26px]`; `:580` `mt-[5.5px]` | medidas da prévia v4 (motivo nos comentários para 76, 62, 164) | `NuxtContainer`/`UPage` e escala do tema |

### 2.7 Testes e travas

- `tests/hub.test.ts` (239), `tests/hubQueue.test.ts` (194): presentation pura, estáveis.
- `tests/composables/useOperatorHub.test.ts` (48): env `nuxt` (`vitest.config.ts:25-32`).
- `tests/securityConfig.test.ts` (27): CSP `img-src https:` (`nuxt.config.ts:20-22`).
- e2e (não rodam na CI): `hub.spec.ts` (54) crava papel `link` com nome do app, `href`,
  `target="_self"`/`_blank`, alvo de 48 px do gesto (:35-37), larguras iguais dos gestos
  (`[data-hub-queue-action]`, :45-49), `[data-tile-tone]` (:53); `mobileTiles.spec.ts` (36)
  seleciona `ul > li > a` e lê `[data-tile-title]`/`[data-tile-description]` em todos: a
  lista de apps do celular (`app.vue:472-532`) **não tem esses atributos** e a grade
  desktop está `display:none` a 375 px; pela leitura o spec quebra hoje (null em
  `title.scrollHeight` e alturas 0 vs 62). `push.spec.ts`, `resilience.spec.ts` estáveis.
- Kit: `guardrails.appBar.test.ts:148-150` (Central pode montar `OperatorInbox`),
  `:225-227` (exige `<OperatorPhoneMenu` e `<OperatorSuiteRail` no `app.vue`);
  `guardrails.phoneBar.test.ts:98-112` (`data-hub-phone-actions` no `app.vue`);
  `guardrails.suiteSearch.test.ts:67-71` (`<OperatorSuiteSearch ... variant="hero"`);
  `guardrails.test.ts:163` (tipografia); `components/HubPushSettings.test.ts` (rodapé).
- Ledger: `native_control_occurrences: 3` (exato hoje); travas de layout canônico iguais
  às do KDS.

### 2.8 Mock visual

`tests/e2e/mockBackend.mjs` (88, :8797): devolve `{hub}` com 5 tiles e 2 itens de fila
(`total_count 4`, `more_count 2`; desde 10/10/2026 a fila só traz `total_count` e
`server_now`, e os itens vão em `tile.next_item`) e `{}` para todo o resto. Build de produção:
`playwright.config.ts:19-37` (`nuxt build && node .output/server/index.mjs` :3001,
`NUXT_DJANGO_BASE_URL` → :8797). Lacunas: `/operator/session/` responde `{}` (sem
operador, sem posto, sem trava: estados 2, 3, 20 sem fixture); nenhum estado de falha
(`login`, `station`, `forbidden`, `unavailable`); sem `tiles: []` (vazio); sem fila vazia;
sem mais de 3 itens (o "Ver mais N" do celular nunca aparece); sem item `attention: true`,
`due_style: countdown|clock`, `time_mode: until`; `shop_name` ausente; push sem
dispositivos. Não há `playwright.visual.config.ts` nem galeria.

### 2.9 Riscos específicos

1. **Links dos tiles**: o alvo depende de a Central estar instalada (`useOperatorAppLink`,
   `app.vue:45-49`): instalada abre a janela própria do app, aba comum abre em `_self`; a
   Loja abre em `_blank`. `NuxtPageCard to` + `target` precisa preservar isso e o `rel`.
2. **Ícone real do app**: PNG da origem do outro app com queda para Lucide; CSP
   `img-src https:` é exceção escrita do dono (29/09). `NuxtAvatar` resolve a queda sem a
   varredura de DOM.
3. **Selo duplicado no celular** (pré-existente, já no `main`): `span[data-hub-seal]`
   `md:hidden` (`:255`) e `OperatorAppSeal home` (`rail:hidden`, `kit/.../OperatorAppSeal.vue:39`)
   aparecem os dois abaixo de 768 px. Conferir em tela antes de migrar.
4. **Bloquear aqui trava o DISPOSITIVO** (`scope: "device"`, `:121-128`), não a sessão:
   qualquer shell novo precisa emitir `lock` para este handler, não o `lock` padrão.
5. **Push**: `OperatorPushSettings` no rodapé é o único lugar para ativar push do
   dispositivo da Central; não pode sumir num shell novo.
6. **Ao vivo falso**: o `live-dot` verde sem SSE (2.3).
7. A Central é a porta de entrada de dispositivo novo: `OperatorStationSetup` oferece
   todos os tipos de posto (`:71-82`).

---

## 3. Kitchen Sink (`surfaces/kitchensink-nuxt` + kit)

### 3.1 Telas e composição

- App: `app/app.vue` (51) monta `OperatorAppRoot` (:37) e, dentro, `OperatorSonner` (:48):
  **dois toasters** ao mesmo tempo (H14). Gate por `operatorSurfaceGate` (:22-31), permissão
  `backstage.view_operator_kitchen_sink` (:4); harness só no dev com
  `KITCHENSINK_VISUAL_MATRIX=1` (`nuxt.config.ts:18-20`); `operatorUpstreamFailFast: true`
  (:13). `NuxtEmpty` de acesso negado (:41), `NuxtSkeleton` de checagem (:42).
- Página: `app/pages/index.vue` = `<OperatorKitchenSink />`.
- `kit/components/OperatorKitchenSink.vue` (1.032): `OperatorOfficeShell` (:204-982) com
  sidebar (`NuxtDashboardSearchButton` :210, `NuxtNavigationMenu` seções :214 e
  "Referências" com popover click :220-242), cabeçalho da sidebar (:244-253), rodapé
  "Guia de composição" (:255-265), `NuxtDashboardSearch` (:266-273), ações da navbar
  (:275-279), toolbar com "Cenário" (`NuxtSelect` :288) e "Shell operacional" (:294);
  `OperatorPage` (:302) com seções `dashboard-exercises` (Dashboard), `visual-exercises`
  (Exercises), `#foundations` (:307), `#anatomies` (:364, `OperatorSplitter` :370 e
  sequência móvel :420), `#components` (:470, léxico em `<table>` :486 e formulário
  `NuxtForm` :509), `#recipes` (:583, cartão operacional :599, métricas `NuxtPageCard`
  :658, `NuxtTable` :675, `NuxtStepper` :693), `#states` (:707, 10 cenários), `#matrix`
  (:883, `<table>` :900), `#exceptions` (:922); rodapé com `<nav>` (:950).
  Modo `?mode=operational`: `OperatorOperationalShell` (:985-1029) com
  `NuxtDashboardNavbar` cru como cabeçalho (:991).
- `OperatorKitchenSinkDashboard.vue` (245): contagens, gráfico (`OperatorKitchenSinkChart.client.vue`,
  48), progresso, `NuxtTabs` Resumo/Fila/Equipe (:62-66), `NuxtSlideover` de detalhe
  (:220-242).
- `OperatorKitchenSinkExercises.vue` (684): tema, cards, ações, badges, escolhas e menus,
  calendários (`NuxtCalendar` :481, :487), entrada de dados (`NuxtInputDate` :525,
  `NuxtInputTime` :533, `NuxtInputNumber`, `NuxtFileUpload`, `NuxtDropdownMenu`), tabela com
  seleção/expansão/paginação (:576-640), reordenação por teclado (:641-680).

### 3.2 Gestos do catálogo (30)

Sidebar: abrir/recolher (oficial), 8 seções + Referências (2 filhos), busca `Meta+K`
(`NuxtDashboardSearch`), Guia de composição, alternar tema. Toolbar: Cenário (10 estados,
grava `?state=` :100-112), Shell operacional. Dashboard: Separar próximo, Reiniciar, Mostrar
em barras (switch), abas, Revisar NB-1048 (Slideover), Voltar à fila. Exercises: salvar com
pendente e concluir resposta simulada (:271, :277), alertas dispensáveis, filtro de pedidos,
seleção de linha, detalhes de linha, paginação, Subir/Descer (:668, :675). Formulário:
Salvar/Limpar com validação (:509-579). Estados: fechar alerta, Abrir confirmação
(`NuxtModal` :823), Abrir popover (:842), Abrir detalhe lateral (`NuxtSlideover` :852).
Rodapé: 3 links de seção. Operacional: Concluir etapa (:1019-1026), Voltar ao catálogo.

### 3.3 Teclado, SSE

Sem SSE. Teclado: `Meta+K`/`Escape` da busca oficial, `ArrowRight` nas abas, setas e Enter
na reordenação; `useScrollspy` e `getElementById` (:31, :51, :191) para seção ativa.

### 3.4 Peças do kit usadas pelo catálogo

`OperatorOfficeShell` 1, `OperatorOperationalShell` 1, `OperatorPage` 1, `OperatorSplitter` 1,
`UiFilterChip` 2 (:323, :327, rotulado "Pills canônicos de filtro" :337), `OperatorAppRoot` 1 e
`OperatorSonner` 1 (no app). **Não demonstra**: `OperatorSuiteShell` (só aparece como texto
no léxico :147, e é isso que satisfaz `catalog.guardrails.test.ts:46-66`), `OperatorPageHeader`
(só texto no léxico), `OperatorLiveStatus`, `OperatorSuiteSearch`, `OperatorUrgentAlert`,
`OperatorInbox`, `OperatorPeriodPicker`, `UiDate*`, `OrderCardMenu`. Ou seja: as peças que
o Gestor e os 7 herdeiros de fato montam não estão no catálogo.

### 3.5 Componentes locais

O app não tem componente. No kit: `OperatorKitchenSink` (1.032), `...Dashboard` (245),
`...Exercises` (684), `...Chart.client` (48), fixtures `kit/fixtures/operatorKitchenSink.ts`.
Ficam; o que muda é o conteúdo (3.6).

### 3.6 Escapes e contradições entre o catálogo/doc e o que o Gestor fez

Escapes no código do catálogo:
1. `<table>` crus como documentação: `OperatorKitchenSink.vue:486-503` (léxico) e `:900-918`
   (matriz) → `NuxtTable`.
2. `<label>` cru do Cenário (:287) → `NuxtFormField`.
3. `<li class="rounded-md border p-3">` que imita card dentro de `NuxtCard`/pane
   (:388-397, :425-433) → lista sem moldura ou `NuxtCard variant="soft"`.
4. `:ui=` 3: `Dashboard.vue:66`, `Exercises.vue:576`, `:608`.
5. 12 `NuxtAlert` sem `variant` (9 no catálogo, 1 no Dashboard :229, 2 no Exercises :223,
   :396): com o `defaultVariants: subtle` removido do `app.config.ts` (H13) saem `solid`.
6. Arbitrários 13: `:415,:448` `grid-cols-[auto_minmax(0,1fr)]`, `:487` `min-w-[44rem]`,
   `:901` `min-w-[48rem]`, `:557,:826` `gap-[var(--op-control-gap)]`, `:598,:656,:666`
   `gap-[var(--op-region-gap)]` (documentado), `:598` e `:666` grids, `:948`
   `px-[var(--op-page-inline-space)]`, `Exercises:373`.
7. **Bug de template**: `OperatorKitchenSink.vue:1027` `></template` depois de um `/>`
   deixa um `>` literal na barra de ação do shell operacional (já existe no `main`).
8. **Bug de dado**: o léxico tem uma linha sem nome (:151-154): `row[0]` vira a descrição
   "Título, busca, filtros e ações sobre Navbar e Toolbar oficiais" e a coluna "Use quando"
   fica vazia.
9. Copy: "Tente novamente" (:740) contra a trava de vocabulário planejada na F8 ("de
   novo"); "1 selecionados." (`Exercises.vue:625`, plural quebrado, e o spec crava o erro
   em `kitchen-sink.spec.ts:528-530`); "Geometria: alvos operacionais de 44 e 48 px" (:360)
   que o kit deixou de garantir.

Contradições doc/catálogo × Gestor (linhas do `docs/reference/operator-kitchen-sink.md`
desta branch; o laudo cita linhas antigas, que andaram 8 linhas):
1. **Card dentro de card**: `:260-261` "Não há Card dentro de Card" (o laudo cita `:253`)
   contra o "Em andamento" do Gestor (`QueueView.vue:603-714`) e a regra global do tema
   `kit/app.config.ts` (`card.slots.body` com `has-[>[data-slot=root]:only-child>[data-slot=item]]:py-0`).
2. **"Sem consumidor"**: `:440-444` lista `UiDateField`, `UiDateRangeField`,
   `UiDateTimeField`, `UiTimeField`, `UiTimeRangeField`, `UiStepper` como sem consumidor (o
   laudo cita `:432-436`): B.I. 3 e Marketing 9 usam. E `:436-439` diz que
   `OperatorOfficeShell`/`OperatorAppRoot` não são consumidos pelas oito apps: o Gestor já
   consome `OperatorAppRoot` e `OperatorSuiteShell` (que monta o `OperatorOfficeShell`).
3. **Alvo de toque**: `:67-72` "em ponteiro grosso uma regra compartilhada amplia o alvo
   para 44px (48px em tablet touch)": a regra coarse saiu de `operator-theme.css` e os
   overrides `md → h-control` de input/select/selectMenu saíram do `app.config.ts`. Só o
   alvo por pseudo-elemento de checkbox/switch/radio continua (`app.config.ts:5-18`).
4. **Alert subtle por padrão**: `:178` contra o `app.config.ts` sem `defaultVariants`.
5. **On/Off**: `:190-191` documenta o "estado compacto On/Off" que o laudo condena (P0-5).
6. **Busca**: `:246` "A busca usa DashboardSearch e DashboardSearchButton": o catálogo usa
   (`:266`), o kit/Gestor recompõem com `NuxtModal + NuxtTabs + NuxtCommandPalette`
   (`OperatorSuiteSearch.vue:268-297`).
7. **Contagem no NavigationMenu**: `:197-199` (chip no item do `NavigationMenu`): o rail do
   Gestor é `NuxtTooltip + NuxtChip + NuxtButton` à mão (`OperatorSuiteShell.vue:131-205`).
8. **Stepper**: `:158` "Fluxos com etapas usam `UiStepper`" contra `:38` e o catálogo
   (`NuxtStepper` direto, :693).
9. **Data/hora**: `:420-422` receitas `NuxtInputDate`/`NuxtInputTime` contra
   `OperatorPeriodPicker.vue:248,259,294` e `orders-nuxt/.../ChannelPeriodCalendar.vue:13-22`
   (`type="date|time"` nativo).
10. **Operação**: `:117` e `:140` (Cozinha usa `OperatorOperationalShell` +
    `OperatorPageHeader`) contra o molde real (Gestor em `OperatorSuiteShell`) e contra o
    próprio catálogo, cujo modo operacional usa `NuxtDashboardNavbar` cru (:991).
11. **Filtro em pílula**: catálogo mostra `UiFilterChip` como canônico (:323-337); o Gestor
    migrou para `NuxtTabs` e o próprio arquivo se chama "compatibilidade temporária"
    (`UiFilterChip.vue:2`).
12. **Toast**: `:180-182` "Toast usa `useToast` e o toaster do `OperatorAppRoot`... sem um
    segundo toaster": o app do catálogo monta `OperatorSonner` também
    (`kitchensink-nuxt/app/app.vue:48`).
13. **Contagens internas**: `:312` "60 telas e 241 variantes" contra `:433` "61 superfícies,
    254 variantes" (o ledger tem 61/254/60 pendentes).

### 3.7 Testes e o vermelho do job `kitchensink-nuxt` (#1519)

- Travas: `kitchensink-nuxt/tests/shell.test.ts` (52, strings do `app.vue`/`nuxt.config.ts`:
  `<OperatorAppRoot>`, `operatorSurfaceGate(`, `surface.show*`, sem `NuxtCard` na página);
  `operator-kit/tests/catalog.guardrails.test.ts` (strings no catálogo, no `app.config.ts`,
  `operator-base.css` e shells; :119-127 olha o arquivo errado para a regra coarse, T2);
  `operator-kit/tests/catalog/operator-kit-catalog.spec.ts` (mesmo catálogo no
  `/__operator_kit_catalog`, também vermelho no #1519).
- `tests/visual/kitchen-sink.spec.ts` (567): 13 testes x 9 viewports = 117; 69 são
  `test.skip` por viewport, 48 rodam. O laudo diz 14 passaram e 69 pularam, então **34
  falharam**.
- **Motivo provável (leitura, sem log)**: `captureOperatorEvidence(..., { allowedFindings:
  [] })` roda o scanner (`kit/visual/playwright.ts:99-108`) que, em viewport touch, exige
  alvo de 44 px (48 px a partir de 600 px de largura) em todo `button`, `a[href]`, `input`
  (`kit/visual/scanner.ts:35, 226-237`). Com a pilha #1518/#1519 o kit tirou a regra coarse
  (`operator-theme.css`) e os overrides de altura (`app.config.ts`), e `NuxtButton`/`NuxtInput`
  `md` voltaram a cerca de 32 px: todo teste com captura nos viewports touch acusa
  `touch-target` (captura canônica, shell operacional, tema escuro, consumer real, estados).
  Segundo motivo, determinístico no `desktop-common`: o teste "receitas interativas" exige
  opção de select com altura >= 44 px (`kitchen-sink.spec.ts:487-498`), e o
  `item: "min-h-control ..."` de `select`/`selectMenu` foi removido do `app.config.ts`.
  Terceiro candidato: os 12 `NuxtAlert` agora `solid` mudam contraste e geometria nas
  capturas (axe/scanner). O mesmo mecanismo explica o vermelho do passo Playwright do
  `operator-kit` (P0-4). Confirmação exige baixar o log do job.

### 3.8 Mock visual

Não há mock backend: o harness substitui o gate no `nuxt dev` (`app.vue:7-17`,
`playwright.visual.config.ts:6-12`, porta 33114) e as fixtures são estáticas no kit. Não há
build de produção visual: com `operatorUpstreamFailFast: true` o `node .output/server` aborta
sem `SHOPMAN_ENVIRONMENT`/upstream HTTPS (`kit/server/plugins/upstream-guard.ts:10-14`), e o
harness é desligado em `NODE_ENV=production`. Cenários cobertos: 10 estados + modo
operacional + modal + tema escuro. Browser pinado em `kit/visual/browser-lock.json`
(Playwright 1.63.0, Chromium 1243): baseline só regera quem tem o browser da CI.

### 3.9 Riscos

1. O catálogo é o "molde" que os 7 apps vão copiar e hoje ensina coisas que o Gestor não
   faz (3.6). Migrar KDS e Central pelo catálogo sem fechar 3.6 reproduz a divergência.
2. O spec crava o plural errado ("1 selecionados") e as travas cravam strings de
   classe (`catalog.guardrails.test.ts:129-143`).
3. Dois toasters: o mesmo aviso pode sair em dois lugares no app do catálogo.

---

## 4. O que não foi verificado

- Nada foi visto em tela (sem build, sem browser). Itens marcados "provável" saem de
  leitura: o seletor do `mobileTiles.spec.ts`, o selo duplicado da Central, a causa do
  vermelho do `kitchensink-nuxt`.
- Logs dos jobs da CI não foram baixados; `gh pr list` não respondeu nesta sessão, então
  não confirmei PRs abertos tocando os três apps (há branches remotas antigas com `kds-*`
  e `hub-*`, todas fora desta pilha).
- `OperatorStationSetup`, `OperatorLock`, `OperatorPushSettings` e `OperatorInbox` foram
  lidos só no que os três apps passam a eles.
