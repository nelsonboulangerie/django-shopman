# Laudo — primeiro corte: shell + `orders-board` (`/`)

**Base:** `f650d01b2`. **Worktree:** `orders-canonical` / branch `codex/orders-canonical-shell`. **Data:** 2026-10-06.
**App:** Django `127.0.0.1:8001` (SQLite, `migrate` + `seed --flush`) + `surfaces/orders-nuxt` em `127.0.0.1:3004` (`NUXT_DJANGO_BASE_URL=http://127.0.0.1:8001`).
**Sessão:** login BFF `admin/admin` (superuser). **Estado do dispositivo:** sem posto provisionado → oferta de vínculo de posto na primeira visita (dismissida com "Usar sem vincular" para o board).
**Seed:** Nelson (10 pedidos: 8 retirada, 2 entrega; zonas Entrada 0, Preparo 8, Saída 2).
**Capturas:** `docs/plans/suite-ux-v2/orders/captures/` (8 viewports + 2 telas de login + 1 do modal de posto).

> Método WP-UX-13 §4: tela **realmente aberta** e inspecionada nos viewports; o que não foi possível fica vermelho com próximo passo. Este laudo **não** implementa anatomia e **não** regenera baseline.

## Correção de rumo do dono (06/10/2026) — prevalece sobre a primeira versão

O dono reavaliou a fonte e corrigiu a decisão. **Nada do que já existe no kit é intocável.**

1. **Rail é o DashboardSidebar**, não um rail novo. Tema renderizado: root relative hidden lg:flex, min-w-16 w-(--width), com a largura vindo de unit + defaultSize do DashboardGroup. Decisão: unit=px, default-size ~76–84, resizable=false, collapsible=false, ui.root tematizado para os tokens do rail (bg-rail / text-rail-foreground / altura) → rail fixo canônico. O que é Shopman é o **conteúdo**: seções, badge/atenção, Alt 1…9, selo/trocador — via NavigationMenu + composables do kit. **Nada** de OperatorSuiteRail novo. Abaixo de lg o DashboardSidebar é hidden; a barra de seções mobile entra como composição.
2. **Header é o do Dashboard**, não o PageHeader. OperatorOfficeShell = DashboardGroup/Sidebar/Panel/Navbar/Toolbar; o board é superfície de escritório → cabeçalho = DashboardNavbar (leading/title/right) + DashboardToolbar (filtros). PageHeader só dentro de composição Page (fluxo de leitura), **nunca** como chrome do board.
3. **Card de fila é o NuxtCard** (ou algo diretamente derivado dele: mesmos slots/tokens/raio). HTML semântico só **dentro** do card (badges, linhas, ações).
4. **MoreBelow / useNextFocus** devem ser reavaliados para harmonizar com o Nuxt UI: trocar bg-background/33, ring-border/40 e ring-ring pelas classes semânticas do tema (bg-default/bg-elevated, text-highlighted/text-muted, ring-default), mesmo raio/elevação de Card/Button/Slideover, e API/props no padrão Nuxt UI. Entregar um **mapa antes/depois** (pendente, no corte de anatomia).

## Viewports inspecionados

| viewport | dimensão | captura | resultado |
|---|---|---|---|
| desktop amplo | 1920×1080 | `desktop-wide__board.png` | board (Fila) renderiza, sem overflow |
| desktop comum | 1440×900 | `desktop-common__board.png` | board (Fila) renderiza; `desktop-common__station.png` = modal de posto cobrindo |
| desktop baixo | 1366×768 | `desktop-low__board.png` | renderiza |
| desktop compacto | 1280×800 | `desktop-compact__board.png` | renderiza |
| tablet paisagem | 1180×820 | `tablet-landscape__board.png` | renderiza |
| tablet retrato | 820×1180 | `tablet-portrait__board.png` | renderiza (zonas Entrada/Preparo/Saída) |
| celular padrão | 390×844 | `mobile-standard__board.png` | renderiza (barra de seções embaixo) |
| celular estreito | 320×568 | `mobile-narrow__board.png` | renderiza; chips rolam na horizontal |
| zoom 200% (1280×800@2×) | — | **não capturado** | **vermelho** (próximo passo) |
| tema escuro | — | **não capturado** | **vermelho** (o app não é dark-first) |

## Achados

### A1 — Oferta de vínculo de posto cobre o board no desktop (severidade **alta**, estado primeira visita)
- **Evidência:** `desktop-common__station.png` (board totalmente encoberto, fundo bege) × `desktop-common__board.png` (board após dismiss).
- **Contexto:** `OperatorStationSetup` é oferecido a quem gere operadores num dispositivo sem posto (`useStationSetupOffer`). Em produção o posto tende a existir; na primeira visita (e no dev) ele aparece. WP-UX-13 §4.3 exige o estado "primeira visita".
- **Problema:** o contrato de chrome (§3.3) quer o provisionamento no dispositivo, mas a forma atual **esconde o trabalho** — a fila é a casa (L6/L5) e não pode sumir atrás de um overlay opaco.
- **Solução proposta:** manter a oferta, mudar a forma: `OperatorStationSetup` como `Sheet`/painel não bloqueante (ou faixa), com o board visível; quando houver item pedindo atenção, a oferta não compete. Família **overlay** do kit.

### A2 — "Saída" tem duas portas (severidade **média**)
- **Evidência:** rail com `Saída Alt2` (badge 2) e, no tablet/celular, a zona `Saída 2`; no desktop, `EM ANDAMENTO`.
- **Contexto:** FUNCTION-PLAN §9 propõe **uma** fila de saída no posto `Saída` (hospedada no Gestor), puxando a Cozinha; é pedido de mudança de decisão, **aguardando o dono** (§13.3).
- **Problema:** o mesmo trabalho (L2) aparece em duas portas com desenhos diferentes.
- **Solução proposta:** **fora deste corte** (muda fronteira/rota). O laudo registra que a convergência depende dessa decisão; no corte, não duplicar ainda mais.

### A3 — Recortes sobrepostos na barra de filtros (severidade **média-baixa**)
- **Evidência:** `Precisa de você 8`, `Todos 10`, `Atrasados 6`, `Entrega 2`, `Retirada 8`, `+ Canal`.
- **Contexto:** §4.1 — filtro só com recortes que mudam o trabalho; `Todos` é o estado base, `Atrasados` é derivado do tempo (é a leitura de urgência).
- **Solução proposta:** consolidar: base `Precisa de você`; recortes `Entrega`/`Retirada`/`Canal`; `Atrasados` como alternância de atenção (ou a própria ordenação). Decisão de **forma**, não de estética.

### A4 — Busca local, sem alcance (severidade **média**, dependência)
- **Evidência:** `OperatorSuiteSearch` (placeholder "Buscar pedido, cliente ou item", kbd `/`).
- **Contexto:** v3 §2.2 quer uma busca só, com escopo `Esta tela · App · Suíte` e câmera no celular; isso é **WP-UX-11**.
- **Solução proposta:** manter a busca local no corte; registrar a lacuna e não construir uma segunda busca.

### A5 — Casca atual é Shopman (Operator*), não a casca canônica — correção do dono: convergir para Dashboard* (severidade **alta** para o objetivo)
- **Evidência:** GestorNav usa OperatorSuiteRail + OperatorSectionBar; header OperatorPageHeader; board usa UiFilterChip, UiIconButton, UiPopover, UiDialog*, UiSheet, UiTabs*, UiNativeSelect, UiCheckbox.
- **Contexto:** o app já se declara piloto visual (data-suite=v3), mas a casca canônica é DashboardGroup/Sidebar/Panel/Navbar/Toolbar. A leitura anterior (rail compacto como primitiva nova do kit) foi **corrigida pelo dono**: o rail compacto se obtém **configurando o DashboardSidebar** (unit=px, default-size ~76–84, sem resize/colapso, ui.root tematizado); a especificidade Shopman vive no conteúdo (seções, badge, Alt, selo), não num componente paralelo.
- **Solução proposta:** OperatorOfficeShell passa a ser o chrome canônico Dashboard*; conteúdo do rail via NavigationMenu + composables do kit; header via DashboardNavbar + DashboardToolbar. Sem OperatorSuiteRail, sem PageHeader como chrome, sem card cru.

### A6 — Card do pedido denso (severidade **baixa**)
- **Evidência:** capturas mobile/tablet/desktop: código, tempo/meta, cliente, canal, pills (Entrega/Retirada, N itens), itens, pagamento, valor, botão primário, `⋯`.
- **Contexto:** §4.1 pede "sem ícones decorativos, sem campos que não mudam a decisão". O bloqueio com motivo (H58/N88: `Pix expirado`, `gerado… · expira…`) já está **conforme L3**.
- **Solução proposta:** refinar densidade (pills redundantes, ícone de pagamento) mantendo o bloqueio antes do gesto e o gesto primário único.

### A7 — Tipografia de seção fora do token (severidade **baixa**)
- **Evidência:** cabeçalhos de zona usam `text-sm font-bold uppercase tracking-wide` em vez de `op-eyebrow`/`op-*`.
- **Solução proposta:** unificar na escala `op-*` (decisão de aparência).

### A8 — Automação anunciada, ainda não ligada (severidade **informativa**)
- **Evidência:** painel `O SISTEMA FEZ` → "Nada automático neste intervalo."; `EM ANDAMENTO` → `Na Cozinha 2`.
- **Contexto:** "pronto" automático quando a Cozinha conclui é **decisão do dono** (FUNCTION-PLAN §13, aprovada); a guarda está no §5.1.
- **Solução proposta:** não implementar regra no corte; a UI já reserva o lugar (L1).

## Decisão canônica por família (primeiro corte)

Dois eixos: **estrutura** (Nuxt UI / Reka / HTML) e **aparência** (manter / refinar / adotar adaptado).

| família | estrutura | aparência | motivo | alternativas rejeitadas |
|---|---|---|---|---|
| Rail (DashboardSidebar) | Nuxt UI **DashboardSidebar** com unit=px, default-size ~76–84, resizable=false, collapsible=false, ui.root tematizado; conteúdo por **NavigationMenu** + composables do kit | adotar adaptado | correção do dono: o rail é configuração do canônico, não componente paralelo | nova primitiva OperatorSuiteRail; DashboardSidebar em % (18%) |
| Header | Nuxt UI **DashboardNavbar** (leading/title/right) + **DashboardToolbar**, dentro do OperatorOfficeShell (DashboardGroup/Sidebar/Panel) | adotar adaptado | correção do dono: board é escritório; PageHeader só dentro de Page | OperatorPageHeader como chrome; PageHeader como chrome do board |
| Busca | `NuxtInput`/`InputMenu` sob `OperatorSuiteSearch` | manter | atalho `/`, alcance é WP-UX-11 | `input` nativo; segunda busca |
| Botão primário/secundário/ícone | Nuxt UI `Button` sob `UiButton` | refinar (44/48 px) | matriz WP-UX-8 §5 | `<button>` cru; variante nova |
| Chip de recorte | Nuxt UI `Button` `soft`/`outline` (ou `UiFilterChip`) | manter + consolidar recortes (A3) | padrão da suíte | `span` clicável |
| Segmentado (Fila/Supervisão) | Nuxt UI `Tabs` `variant="pill"` (ou `UiSegmentedControl` no kit) | adotar adaptado | v3 §2.4 | `div` + botões; dois segmentados |
| Menu (Urgência, ⋯) | Nuxt UI `DropdownMenu` (`BoardMenu` sobre ele) | adotar adaptado | portal/teclado/foco canônicos | `UiPopover` por controle |
| Card de fila | Nuxt UI **NuxtCard** (ou diretamente derivado: mesmos slots/tokens/raio); HTML semântico só dentro | adotar adaptado | correção do dono | HTML cru como card |
| Pílula de estado | Nuxt UI `Badge` / `UiStatusPill` no kit | adotar adaptado | 6 significados (§8); hoje há cor por canal | cor por canal como estado |
| Progresso de preparo | Nuxt UI `Progress` | adotar adaptado | "0 de 2 prontos" | barra `div` custom |
| Dialog / confirmação | Nuxt UI `Modal`/`AlertDialog` sobre Reka (`UiDialog*`) | manter | foco/portal/Escape | overlay manual |
| Sheet / painel lateral | Nuxt UI `Slideover`/`Drawer` (`UiSheet`) | manter | detalhe/edição | painel local |
| Switch | Nuxt UI `Switch` (`UiSwitch`) | manter | interruptor (L6) | toggle local |
| Checkbox | Nuxt UI `Checkbox` (`UiCheckbox`) | manter | seleção em lote | nativo pintado |
| Abas de zona | Nuxt UI `Tabs` | adotar adaptado | recorte nível 2 (v3 §4.2) | abas locais |
| Overlay de posto | Nuxt UI `Modal`/`Slideover` (família overlay) | **refinar** (A1: não cobrir o board) | contrato de chrome §3.3 | overlay opaco full-screen |
| MoreBelow / swipe | primitiva Shopman MoreBelow/useMoreBelow, com tokens e API harmonizados ao Nuxt UI (bg-default/bg-elevated, text-highlighted/text-muted, ring-default; mesmo raio/elevação de Card/Button/Slideover) | refinar (mapa antes/depois) | correção do dono | manter os tokens atuais; recriar por app |
| Próximo foco | primitiva Shopman useNextFocus, com API/props no padrão Nuxt UI e tokens semânticos | refinar (mapa antes/depois) | correção do dono | manter os tokens atuais; scroll manual por tela |
| Live status | `OperatorLiveStatus` (kit) sobre Nuxt UI | manter | v3 §2.3 | indicador local |
| Ícones | `@nuxt/icon` + Lucide (caminho canônico Nuxt UI) | manter | decisão do dono | SVG inline por app |
| Tipografia | tokens `op-*` sobre a escala Nuxt UI | refinar (A7) | uma escala, um significado (L3.3) | fonte menor para caber |

**Leitura da decisão (corrigida pelo dono):** o chrome converge para o canônico do Dashboard (Sidebar configurado como rail em px, Navbar/Toolbar), o conteúdo do rail é Shopman via NavigationMenu + composables do kit, e o card de fila é NuxtCard. Nenhuma família exige Reka/HTML direto. MoreBelow/useNextFocus continuam primitivas Shopman, mas com tokens e API harmonizados ao Nuxt UI.

## O que **não** foi possível abrir/rodar (vermelho explícito)

- **zoom 200% (1280×800@2×)** — não capturado nesta rodada; próximo passo: incluir no script de captura e no runner do app.
- **tema escuro** — não capturado; o app não é dark-first. Confirmar se a matriz escura se aplica.
- **sessão expirada / permissão negada (não-superuser)** — o login do superuser torna `authorized` sempre verdadeiro; exige um operador sem `shop.manage_orders`/`backstage.operate_kds` e um sem `shop.manage_customers`.
- **conflito de revisão em tempo real**, **scanner/câmera**, **giro de dispositivo**, **`forced-colors` / reduced-motion** — não reproduzidos.
- **`make operator-visual app=orders`** — **não roda**: nenhuma superfície do orders tem `runner` no ledger (11 `pending`). As capturas vieram de script dedicado (`surfaces/orders-nuxt/tests/e2e/_capture_orders.mjs`, temporário, não commitado).
- **Baseline pixel a pixel** — não existe para o orders; não foi regenerada.

## Próximo passo proposto (implementação do primeiro corte)

1. **Validar este laudo e a decisão por família com o dono** (é a prévia antes da anatomia, WP-UX-13 §2.5).
2. Abrir PR do primeiro corte (shell + /) com OperatorOfficeShell = DashboardGroup/Sidebar/Panel/Navbar/Toolbar (DashboardSidebar em px como rail; conteúdo por NavigationMenu), header DashboardNavbar + DashboardToolbar, card de fila NuxtCard e MoreBelow/useNextFocus harmonizados; **sem** mudar rota, regra, permissão ou contrato de backend.
3. Corrigir A1 (overlay de posto não cobre o board) e A3 (recortes) junto, se aprovado.
4. Adicionar `runner` das superfícies do orders ao ledger e gerar a matriz com o Chromium da CI (baseline oficial).
5. Artefatos do WP-UX-13 §8: inventário (feito), laudo (este), decisão canônica (acima), contact sheet antes/depois, estados, teclado/toque, a11y, desempenho, exceções, comandos.

## Segunda passada — implementação e de-para (06/10/2026)

O corte visível foi implementado e verificado; a matriz do board roda **claro + escuro** no harness oficial e passa. Esta seção é o **de-para** "função anterior → novo lugar" e a revisão estrutural/semântica.

### De-para por achado/família

| antes (achado) | depois (novo lugar) | evidência |
|---|---|---|
| **A1** oferta de posto em overlay opaco cobrindo o board | `OperatorStationSetup` (kit) = `NuxtBanner` **no fluxo** + `NuxtSlideover` com os passos; board operável atrás. A chamada vai no slot `#title` (Banner não tem prop `description`). | `650c67be6`, `9abb84b13`; `corte-a1-banner.png` |
| **A3** "Precisa de você / Todos / Atrasados / Entrega / Retirada / +Canal" | base **"Precisa de você"**; `Todos` sai; **"Atrasados" vira ordenação** (`QueueSort "late"`); ficam fluxo (Entrega/Retirada) + canal | `96e318073` |
| **A5** casca `OperatorSuiteRail` + `OperatorSectionBar` + `OperatorPageHeader` | `OperatorOfficeShell` modo **rail** (`unit=px`, **64 px**, sem resize/colapso, `ui.root` `bg-rail`/`text-rail-foreground`) + **bottom tab bar**; rail e tab viram primitivas do kit (`OperatorSuiteRailMenu`, `OperatorSuiteTabBar`); `app.vue` só passa items/ui | `6b2a6e482`, `75731882a`; `corte-rail-card.png` |
| **header** `OperatorPageHeader` (chrome) | `GestorBoardHeader` (orders) + `OperatorCanonicalHeader` (**kit**, categoria 2) sobre `NuxtDashboardNavbar` + `NuxtDashboardToolbar`; estado pelo view-model `useGestorBoardHeader` (provide/inject; **um** dono de SSE/som) | `75731882a`; `corte-header-desktop.png`, `corte-header-mobile.png` |
| **A6** card HTML denso | card veste `NuxtCard` (`variant="outline"`, bordas condicionais por `ui.root`); resumo vira `NuxtPopover`; pagamento/canal de relance; **uma** ação primária + ⋯ | `d266b6282` |
| **A7** cabeçalhos fora do token | **purga de `op-*`** da superfície → escala canônica do Nuxt UI/Tailwind (ver mapa abaixo); zero `op-*` no app | este commit |
| **altura de controle** campos 44 × botões 32 | fonte única: base = **padrão Nuxt UI** no ponteiro fino; **44 (celular) / 48 (tablet)** só no `@media (pointer: coarse)` — regra **compartilhada** no kit (`operator-base.css`), não escopada no catálogo | `584f5ced0`, `df06368c6` |
| **gate de geometria** | harness passa a emular o ponteiro do viewport (`hasTouch`/`isMobile`) e o piso de toque virou regra do kit; scanner verde sem allowlist | `e725c003f` |

### Purga de `op-*` → escala canônica (188 trocas, 16 arquivos)

| token | classes canônicas | delta |
|---|---|---|
| `op-micro` | `text-xs` | 12/16 → 12/16 (perde `letter-spacing .02em`) |
| `op-label` | `text-sm` (+ `font-medium` se a marcação não tiver peso) | 13 → 14 |
| `op-body` | `text-sm` | 15 → 14 |
| `op-title` | `text-base` (+ `font-semibold`) | 16/24 → 16/24 (exato) |
| `op-eyebrow` | `text-xs uppercase tracking-wider` (+ `font-semibold`) | 11 → 12 |
| `op-action` | `text-base` (+ `font-semibold`) | 17 → 16 |
| `op-code` | `text-4xl tabular-nums` (+ `font-bold`) | 35,2 → 36 |
| `op-figure` | `text-2xl tabular-nums` (+ `font-semibold`) | 24/28 → 24/32 |

Regra do peso: o peso do utilitário só é emitido quando a marcação **não** tem `font-*` explícito — o explícito sempre venceu. `op-*` segue no **kit** (os outros apps usam); saiu só da superfície orders.

### Dark (obrigatório)

A matriz agora roda **claro e escuro** para cada viewport/estado. O Gestor é **light-first** (`colorMode.preference: "light"`), então o dark não vem do `prefers-color-scheme`: a spec crava a preferência no storage do color-mode (`orders-nuxt-color-mode`) por `addInitScript` antes do boot e passa `theme` à evidência. Contraste AA no escuro: os tokens do tema já são cobertos pelo guardrail (`guardrails.test.ts`, claro **e** escuro); a captura dark fica em `captures/`.

### Revisão estrutural/semântica

- **Navegação primária** = rail `DashboardSidebar` (desktop) / bottom tab bar (mobile) — as mesmas seções nas duas formas; **secundária** = `DashboardToolbar` (recortes de fluxo/canal). Não há duas navegações competindo.
- **Card**: uma ação primária; o resto em expansão/detalhe. Pagamento e canal aparecem de relance, sem decorar.
- **Copy**: os avisos de estado (bloqueio, "o sistema fez", meta de tempo) mantêm a frase que muda a decisão; hints decorativos saíram junto da densidade do card.

### Continua vermelho (fora deste corte)

- **A2** — "Saída" com duas portas: muda fronteira/rota, **aguarda decisão do dono** (FUNCTION-PLAN §9/§13.3).
- **A4** — busca com escopo `Esta tela · App · Suíte` + câmera: **WP-UX-11**.
- **A8** — automação "pronto quando a Cozinha conclui": decisão do dono (a UI reserva o lugar).
- **MoreBelow / useNextFocus** — mapa antes/depois de tokens/API (família "refinar").
- **Passo 3 do header** — shell dona do DOM via `<Teleport>` (refactor invisível, sessão dedicada).

