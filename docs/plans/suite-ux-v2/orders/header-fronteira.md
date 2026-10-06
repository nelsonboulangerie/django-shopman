# Fronteira de estado do header do Gestor — item 4 do corte canônico

**Status:** entregável 1 (papel apenas). **Nada de código foi tocado.** Aguarda aprovação.

Objetivo: canonizar o header do board (`app/pages/index.vue`, bloco ~717–1020) como
`DashboardNavbar` + `DashboardToolbar`, sem quebrar board/mobile, definindo **quem é dono
de qual estado** antes de mover uma linha.

---

## 1. Inventário de refs do header

A coluna "dona" diz onde o estado nasce hoje; "compartilhada" diz se o **board** também lê.

### 1.1 Já singleton (via `useState`) — `useOrdersContext()`
`surfaces/orders-nuxt/app/composables/useOrdersContext.ts`

| ref | dona | compartilhada | papel |
|---|---|---|---|
| `query` | `useState("orders-board-context")` | **sim** (board tria + URL) | busca da tela |
| `channel` | idem | **sim** | recorte de canal |
| `fulfillment` | idem | **sim** | Entrega/Retirada |
| `sort` | idem | **sim** | ordenação do quadro/tabela |
| `viewMode` | idem | **sim** | Fila/Tabela/Quadro |
| `scope` | idem | **sim** | "Precisa de você"/Todos/Atrasados |
| `queueSort` | idem | **sim** | urgência/chegada (A3) |
| `selected` | idem | **sim** | seleção em lote |
| `state.owner` / `scrollTop` / `windowY` / `focusLabel` | idem | não (board) | sessão/posição |

**Conclusão:** o estado de **triagem já é singleton e compartilhado** — não precisa ser movido.

### 1.2 Derivado/efetivo — nascido no `index.vue` (não singleton)

| ref | origem | compartilhada | notas |
|---|---|---|---|
| `view` | computed (`viewMode` + `queueAvailable`) | **sim** | único ponto de verdade |
| `queueAvailable` | computed da queue | **sim** | |
| `exitPostView`, `compactHeader`, `isPhone`, `isNarrow` | computed/medida | **sim** | comportamento por dispositivo |
| `boardLayout` | `useBoardLayout()` — **refs locais + `$fetch`** | **sim** | station/viewLabel/allOpen/showAll/toggle |
| `scopeCounts` | `queueScopeCounts(...)` | derivado | contagens dos recortes |
| `fulfillment_`, `channels` | derivados de `allCards` | header | contagens dos filtros |
| `allCards`/`queueCards`/`preorders`/`zones`/`tableRows` | computeds do board | **sim** | |
| `readMetadata` | `useOrdersBoard` | **sim** | status/menu |
| `realtime`, `realtimeView`, `liveTone`, `readClock`, `error` | `useOrdersBoard` | **sim** | indicador ao vivo |
| `soundOn`, `soundBlocked`, `attentionPending` + ações | `useOrdersBoard` (`useAlertSound`) | **sim** | som/aviso |
| `selecting`, `selected.size`, start/stop, bulk* | computeds/ações locais | **sim** | lote |
| `sortOpen`, `moreOpen`, `channelOpen` | `ref` do header | **não** | UI efêmera |
| `searchInput` | `ref` de foco | **não** | UI efêmera |

**Conclusão:** o header **não tem estado próprio relevante**. Ele é uma **view** do estado do
board, mais três refs de popover e uma de foco. "Extrair estado do header" é, na prática,
**revelar** o que já é do board.

### 1.3 Chrome de kit usada pelo header (`OperatorPageHeader`, 165 linhas)
`useRailState` (`isCollapsed`/`setRail`), `useSuiteRailShown`, `useSuiteSearchRequest`
(`openSearch`), `hubUrl`, `OperatorAppSeal`, `OperatorSuiteSearch`, `OperatorInbox`.

---

## 2. O achado que muda a rota

- `useOrdersBoard()` (`surfaces/orders-nuxt/app/composables/useOrdersBoard.ts:116`) abre
  `useFetch(..., { key: useOperatorResourceKey("orders-queue") })` — os **dados** deduplicam por
  chave, mas cria **refs e efeitos próprios**: `realtime` (SSE + poll), `useAlertSound` (beep) e
  `watch(error → flagIfStationLocked)`. **Chamar `useOrdersBoard()` uma segunda vez (ex.: no
  shell) liga um segundo SSE e um segundo som.** Não pode.
- `useBoardLayout()` (`useBoardLayout.ts:49`) é **ref local + `$fetch`** — não compartilha.
- `useOrdersContext()` é o **único** singleton de triagem (`useState`).

**Consequência:** a rota (b) "subir o estado do header para o shell" **não pode** ser feita
religando os controllers em `app.vue`. Ou o dono dos efeitos sobe inteiro (uma instância só),
ou o shell **não instancia nada** e apenas exibe o que a página entrega.

---

## 3. Forma proposta de `useGestorBoardHeader`

**Não é um segundo store.** É a **interface do dono** (view-model) sobre o que já existe, criada
**uma vez** no dono dos efeitos e consumida por injeção. Sem `useState` novo para dados que já
são singleton, e **nunca** re-criando `useOrdersBoard`/`useBoardLayout`.

```ts
// index.vue (dono) — cria uma vez e provê:
provide(GESTOR_HEADER_KEY, useGestorBoardHeader())
// GestorBoardHeader.vue (consumidor):
const header = inject(GESTOR_HEADER_KEY)!
```

Forma do retorno (leitura + comandos; nada de estado novo):

```ts
type GestorBoardHeader = {
  // identidade/status
  title: string; eyebrow: string;
  status: { tone: LiveTone; time: string; label: string; detail: string };
  // triagem (delegado a useOrdersContext)
  context: { query; channel; fulfillment; sort; viewMode; scope; queueSort };
  counts: { scopes; fulfillment; channels; total; allCards };
  // visão/layout (delegado a computeds + useBoardLayout)
  view: { current; queueAvailable; isPhone; compact; exitPost };
  layout: { station; viewLabel; memoryText; allOpen; showAll };
  // tempo real / aviso
  realtime: { soundOn; soundBlocked; attentionPending };
  // comandos
  commands: {
    setQuery; setChannel; setFulfillment; setSort; setQueueSort; setView; setScope;
    pickSort; pickQueueSort; refresh; exportCsv; printQueue;
    toggleSound; acknowledgeAttention; startSelection; stopSelection;
  };
  // efêmero do header (fica no componente, não aqui):
  // sortOpen / moreOpen / channelOpen / searchInput
};
```

Regra de ouro: **um dono dos efeitos**. `useOrdersBoard`/`useBoardLayout` são instanciados no
`index.vue`; o header só lê e chama comandos.

---

## 4. Mapeamento do template para `DashboardNavbar` / `DashboardToolbar`

A shell (`OperatorOfficeShell.vue`) já expõe, com `navbar=true`:
`DashboardNavbar` (#leading, #title, #right) + `DashboardToolbar` (default).

| hoje (`OperatorPageHeader`) | destino canônico |
|---|---|
| selo do app (`OperatorAppSeal`) | **#leading** da navbar (identidade já vive em `app.vue`; sai da página) |
| botão "mostrar a barra" (`isCollapsed`/`setRail`) | **não se aplica** com `rail=true` (rail não colapsa) — remover |
| eyebrow ("Posto Saída · este dispositivo") | conteúdo do **#title** |
| `h1` "Pedidos" | **#title** (ou prop `title` da shell) |
| `#status` (`OperatorLiveStatus`) | **#title** (ao lado do h1) |
| `#search` (`OperatorSuiteSearch`) | **#right** — a navbar não tem slot de busca oficial; é necessidade transversal (candidata a primitiva categoria 2) |
| `Ciente` | **#right** |
| alternador Fila/Supervisão | **#right** |
| ordenar (`UiPopover` sort) | **#right** |
| som (`sound-toggle`) | **#right** |
| ⋯ (`BoardMenu`) | **#right** |
| barra mobile: lupa, `#phone-actions` | **#right** (com `md:hidden`), reproduzindo o comportamento |
| inbox mobile/tablet | **#right** — e, canonicamente, **dono = shell** (rail no desktop, navbar no mobile) |
| recortes (`#filters`: chips + canal) | **`DashboardToolbar`** (slot default) |
| `ChannelQueueSignal` (`#below`) | **`DashboardToolbar`** (a toolbar não tem "below") |

---

## 5. O que **não** cabe no canônico (e por quê)

1. **Barra mobile de 56px** (selo + lupa-tela-cheia + phone-actions + inbox). `DashboardNavbar`
   não tem contrato mobile próprio; o comportamento por dispositivo terá de ser reproduzido
   dentro dos slots. É o principal atrito e a razão de o passo 2 não ser mecânico.
2. **Eyebrow de posto.** Não é conceito do `DashboardNavbar`; vira conteúdo do `#title`.
3. **Toggle do rail.** Com `rail=true` o rail é fixo; o controle perde função e sai.
4. **Selo do app e inbox.** Canonicamente são **chrome da shell**, não da página — devem subir
   para `app.vue` (a identidade e a sessão já estão lá).
5. **Rótulo/botão de layout do quadro** ("Visão: …", "Mostrar as 3 colunas"). É controle de
   board, não de navbar genérica; cabe no `#right`, mas é candidato a **toolbar**.
6. **Busca da suíte na navbar.** O Nuxt UI não oferece slot de busca no `DashboardNavbar`. Como
   é necessidade de **toda** tela operadora, é caso legítimo de **primitiva Shopman categoria 2**
   (o canônico cresce com prova), não de gambiarra local.

---

## 6. Recomendação de rota

**(a) agora, (b) depois — com teleporte, não com hoisting de efeitos.**

- **Passo 1 — estado sem mudança visual.** Criar `useGestorBoardHeader` como a interface da
  seção 3, **provida pelo `index.vue`** (dono dos efeitos). Nada visível muda.
- **Passo 2 — `GestorBoardHeader.vue` canônico.** O componente renderiza
  `NuxtDashboardNavbar` + `NuxtDashboardToolbar` e injeta o header; segue **dentro do
  `index.vue`** (`navbar=false`). Já entrega **aparência e léxico canônicos**, com risco baixo:
  o estado e os efeitos continuam na página.
- **Passo 3 — shell dono do DOM, via `<Teleport>`.** A página **teleporta** seus controles para
  alvos dentro da navbar/toolbar da shell; o estado permanece na página. **Não** subir
  `useOrdersBoard`/`useBoardLayout` para `app.vue` — seria segunda instância de SSE/som.

Se o dono exigir que a shell também **possua** o estado (não só o DOM), isso é um WP próprio:
singletonizar os controllers com garantia de instância única (sem duplo SSE/som) — maior risco,
fora deste corte.

---

## 7. Riscos e verificações para o passo 1

- [ ] `useAlertSound` é singleton ou instância por chamada? (define se o beep duplica)
- [ ] `useBoardLayout` hoje é recriado a cada navegação? (hoje é do `index.vue`)
- [ ] `useOrdersContext` cobre 100% da triagem? (sim, pela seção 1.1)
- [ ] `queueAvailable`, `view`, `exitPostView` têm um único ponto de verdade? (sim)
- [ ] O harness cobre desktop **e** mobile a cada passo.

---

## 8. Próximo passo

Aguardando aprovação do dono/pai para: **(a) passo 1+2 agora** e **(b) passo 3 em sessão
dedicada**. Nada de código até o aval.
