# Laudo — primeiro corte: shell + `orders-board` (`/`)

**Base:** `f650d01b2`. **Worktree:** `orders-canonical` / branch `codex/orders-canonical-shell`. **Data:** 2026-10-06.
**App:** Django `127.0.0.1:8001` (SQLite, `migrate` + `seed --flush`) + `surfaces/orders-nuxt` em `127.0.0.1:3004` (`NUXT_DJANGO_BASE_URL=http://127.0.0.1:8001`).
**Sessão:** login BFF `admin/admin` (superuser). **Estado do dispositivo:** sem posto provisionado → oferta de vínculo de posto na primeira visita (dismissida com "Usar sem vincular" para o board).
**Seed:** Nelson (10 pedidos: 8 retirada, 2 entrega; zonas Entrada 0, Preparo 8, Saída 2).
**Capturas:** `docs/plans/suite-ux-v2/orders/captures/` (8 viewports + 2 telas de login + 1 do modal de posto).

> Método WP-UX-13 §4: tela **realmente aberta** e inspecionada nos viewports; o que não foi possível fica vermelho com próximo passo. Este laudo **não** implementa anatomia e **não** regenera baseline.

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

### A5 — Casca atual é Shopman (`Operator*`), não a casca canônica do kit (severidade **alta** para o objetivo)
- **Evidência:** `GestorNav` usa `OperatorSuiteRail` + `OperatorSectionBar`; header `OperatorPageHeader`; board usa `UiFilterChip`, `UiIconButton`, `UiPopover`, `UiDialog*`, `UiSheet`, `UiTabs*`, `UiNativeSelect`, `UiCheckbox`.
- **Contexto:** o app já se declara piloto visual (`data-suite="v3"`), mas a casca canônica entregue no kitchen sink é `DashboardGroup/Sidebar/Panel/Navbar/Toolbar`. Há **tensão de anatomia**: a v3 quer um rail compacto de 76 px (seções do app + trocador no selo), que o Nuxt UI não oferece como componente.
- **Solução proposta:** o rail compacto é **primitiva Shopman de primeira classe** (categoria 2), construída sobre Nuxt UI/Reka com contrato, tema e testes — não é `DashboardSidebar`. O resto do chrome (header, busca, menus, overlays) converge para os componentes Nuxt UI. Ver decisão por família abaixo.

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
| Rail de suíte + seções | Reka `NavigationMenu` (ou Nuxt UI `NavigationMenu`) sob wrapper Shopman `OperatorSuiteRail`; **não** `DashboardSidebar` | manter (tokens) + refinar | v3: rail 76 px com seções, contagem, atenção e tecla; Nuxt UI não tem rail de suíte | `DashboardSidebar` (18% de largura); sidebar offcanvas; segundo menu |
| Header de página | Nuxt UI `PageHeader` + slots (`OperatorPageHeader` fino) | refinar | cabeçalho único v3; hoje há header + linha de filtros | cabeçalho local novo |
| Busca | `NuxtInput`/`InputMenu` sob `OperatorSuiteSearch` | manter | atalho `/`, alcance é WP-UX-11 | `input` nativo; segunda busca |
| Botão primário/secundário/ícone | Nuxt UI `Button` sob `UiButton` | refinar (44/48 px) | matriz WP-UX-8 §5 | `<button>` cru; variante nova |
| Chip de recorte | Nuxt UI `Button` `soft`/`outline` (ou `UiFilterChip`) | manter + consolidar recortes (A3) | padrão da suíte | `span` clicável |
| Segmentado (Fila/Supervisão) | Nuxt UI `Tabs` `variant="pill"` (ou `UiSegmentedControl` no kit) | adotar adaptado | v3 §2.4 | `div` + botões; dois segmentados |
| Menu (Urgência, ⋯) | Nuxt UI `DropdownMenu` (`BoardMenu` sobre ele) | adotar adaptado | portal/teclado/foco canônicos | `UiPopover` por controle |
| Card de item de fila | HTML semântico (`li`/`article`) + tokens; **não** `NuxtCard` | manter + refinar (A6) | unidade de fila, densidade pela atenção | `NuxtCard`; grade de card |
| Pílula de estado | Nuxt UI `Badge` / `UiStatusPill` no kit | adotar adaptado | 6 significados (§8); hoje há cor por canal | cor por canal como estado |
| Progresso de preparo | Nuxt UI `Progress` | adotar adaptado | "0 de 2 prontos" | barra `div` custom |
| Dialog / confirmação | Nuxt UI `Modal`/`AlertDialog` sobre Reka (`UiDialog*`) | manter | foco/portal/Escape | overlay manual |
| Sheet / painel lateral | Nuxt UI `Slideover`/`Drawer` (`UiSheet`) | manter | detalhe/edição | painel local |
| Switch | Nuxt UI `Switch` (`UiSwitch`) | manter | interruptor (L6) | toggle local |
| Checkbox | Nuxt UI `Checkbox` (`UiCheckbox`) | manter | seleção em lote | nativo pintado |
| Abas de zona | Nuxt UI `Tabs` | adotar adaptado | recorte nível 2 (v3 §4.2) | abas locais |
| Overlay de posto | Nuxt UI `Modal`/`Slideover` (família overlay) | **refinar** (A1: não cobrir o board) | contrato de chrome §3.3 | overlay opaco full-screen |
| MoreBelow / swipe | primitiva Shopman `MoreBelow`/`useMoreBelow` (kit) | manter | necessidade transversal Omotenashi | recriar por app |
| Próximo foco | primitiva Shopman `useNextFocus` (kit) | manter | Omotenashi mobile, pixel-perfect | scroll manual por tela |
| Live status | `OperatorLiveStatus` (kit) sobre Nuxt UI | manter | v3 §2.3 | indicador local |
| Ícones | `@nuxt/icon` + Lucide (caminho canônico Nuxt UI) | manter | decisão do dono | SVG inline por app |
| Tipografia | tokens `op-*` sobre a escala Nuxt UI | refinar (A7) | uma escala, um significado (L3.3) | fonte menor para caber |

**Leitura da decisão:** nenhuma família exige Reka/HTML direto além do **rail compacto** (que é o candidato a primitiva Shopman de primeira classe) e do **card de fila** (HTML semântico por densidade). O resto converge para componentes Nuxt UI já existentes, tematizados — exatamente a regra "o canônico cobre; o app cede".

## O que **não** foi possível abrir/rodar (vermelho explícito)

- **zoom 200% (1280×800@2×)** — não capturado nesta rodada; próximo passo: incluir no script de captura e no runner do app.
- **tema escuro** — não capturado; o app não é dark-first. Confirmar se a matriz escura se aplica.
- **sessão expirada / permissão negada (não-superuser)** — o login do superuser torna `authorized` sempre verdadeiro; exige um operador sem `shop.manage_orders`/`backstage.operate_kds` e um sem `shop.manage_customers`.
- **conflito de revisão em tempo real**, **scanner/câmera**, **giro de dispositivo**, **`forced-colors` / reduced-motion** — não reproduzidos.
- **`make operator-visual app=orders`** — **não roda**: nenhuma superfície do orders tem `runner` no ledger (11 `pending`). As capturas vieram de script dedicado (`surfaces/orders-nuxt/tests/e2e/_capture_orders.mjs`, temporário, não commitado).
- **Baseline pixel a pixel** — não existe para o orders; não foi regenerada.

## Próximo passo proposto (implementação do primeiro corte)

1. **Validar este laudo e a decisão por família com o dono** (é a prévia antes da anatomia, WP-UX-13 §2.5).
2. Abrir PR do primeiro corte (shell + `/`) com: rail compacto como primitiva do kit (contrato/tema/testes) e convergência do header/board aos canônicos; **sem** mudar rota, regra, permissão ou contrato de backend.
3. Corrigir A1 (overlay de posto não cobre o board) e A3 (recortes) junto, se aprovado.
4. Adicionar `runner` das superfícies do orders ao ledger e gerar a matriz com o Chromium da CI (baseline oficial).
5. Artefatos do WP-UX-13 §8: inventário (feito), laudo (este), decisão canônica (acima), contact sheet antes/depois, estados, teclado/toque, a11y, desempenho, exceções, comandos.
