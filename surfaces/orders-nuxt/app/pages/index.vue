<script setup lang="ts">
import type { TabsItem } from "#ui/types";
// Order board — the operator hub. Reads the two-zone queue projection + realtime
// (SSE + 30s poll) via useOrdersBoard; renders Entrada / Preparo / Saída columns of
// OrderCards; the gestures POST through the django proxy (CSRF handled there) and
// reconcile. Desktop-first (3 columns), responsive (stacks on tablet/phone).
import type {
  AffordanceRef,
  DispatchStep,
  SortKey,
  ZoneView,
} from "~/presentation/board";
import {
  bulkableRefs,
  cardAffordances,
  changeBackSuggestionQ,
  channelOptions,
  elapsedLabel,
  EXIT_SELECTION_LABEL,
  flattenZones,
  fulfillmentCounts,
  lucideIcon,
  moneyInput,
  nextOutRef,
  nextSort,
  oneTapDispatch,
  realtimeIndicator,
  resolveShortcut,
  rowsToCsv,
  SORT_OPTIONS,
  splitRef,
  statusTone,
  timerTone,
  triageCards,
} from "~/presentation/board";
import type { OrderCardProjection } from "~/types/orders";
import type { SwipeAction } from "~/components/SwipeReveal.vue";
import type { CancellationReason } from "~/composables/useOrdersBoard";
import {
  BOARD_COLUMNS_QUERY,
  BOARD_ZONE_KEYS,
  useBoardLayout,
} from "~/composables/useBoardLayout";
import {
  QUEUE_FOCUS,
  QUEUE_SORT_OPTIONS,
  queueGesture,
  queueItems,
  queueScopeCounts,
  type QueueScope,
  type QueueSort,
} from "~/presentation/queue";
import { queueColumnForKey } from "../../../operator-kit/app/presentation/queueColumns";

const {
  readMetadata,
  queue,
  zones,
  deviceAgent,
  preorders,
  realtime,
  pending,
  error,
  refresh,
  isBusy,
  actionError,
  clearActionError,
  confirm,
  advance,
  reject,
  fetchCancellationReasons,
  settleCash,
  equipmentBack,
  courierBack,
  undoHandoff,
  undoReady,
  assign,
  unassign,
  confirmMany,
  advanceMany,
  markStationReady,
  recallStation,
  declareVolumes,
  soundOn,
  soundBlocked,
  attentionPending,
  toggleSound,
  activateAttentionSound,
  acknowledgeAttention,
} = useOrdersBoard();
// Quem só expede (SUITE-UX §15) opera a Saída daqui; o detalhe do pedido é de quem gerencia.
const { canManageOrders } = useGestorAccess();

// A DANFE da sacola sai sozinha pelo servidor; o card imprime ou reimprime à mão.
const danfePrint = useDanfePrint(deviceAgent, refresh);

function handleSoundAction() {
  if (!soundOn.value || soundBlocked.value) {
    void activateAttentionSound();
    return;
  }
  toggleSound();
}

// Sinal honesto de tempo-real vs poll (indicador de degradação do SSE).
const realtimeView = computed(() => realtimeIndicator(realtime.value));
// O ponto ao lado do título: verde só com o SSE vivo; leitura que falhou fala em
// vermelho e por extenso. A hora é a da última leitura útil (não a do relógio).
const liveTone = computed(() =>
  error.value
    ? "off"
    : realtime.value === "live"
      ? "live"
      : realtime.value === "connecting"
        ? "late"
        : "calm",
);
const readClock = computed(() => {
  const at = readMetadata.value?.generated_at;
  return at
    ? new Date(at).toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
});

// Estação travada pelo servidor: não é falha de leitura, é falta de
// identificação. O board deixa de desenhar o aviso de erro nesse estado.
const { denied: stationLocked } = useStationLock();

// ── triage: search + channel filter + sort + view-mode (Arc 1) ──────────────
definePageMeta({ key: (route) => route.path });
const route = useRoute();
const router = useRouter();
const context = useOrdersContext();
const {
  query,
  channel,
  fulfillment,
  sort,
  viewMode,
  scope,
  queueSort,
  selected,
} = context;
// O recorte vive na URL; seleção/posição/foco ficam só na sessão e pessoa atual.
context.readLocation(route.query);
watch(
  () => route.query,
  (params) => {
    if (route.path === "/") context.readLocation(params);
  },
);
// A pessoa chega depois da primeira leitura (a sessão carrega no cliente): relê a URL
// antes de o recorte reescrevê-la, para "/?view=board" abrir nas colunas.
watch(
  () => context.state.value.owner,
  (owner) => {
    if (owner && route.path === "/") context.readLocation(route.query);
  },
);
watch(
  context.location,
  (location) => {
    if (
      route.path === "/" &&
      JSON.stringify(route.query) !== JSON.stringify(location.query)
    )
      void router.replace(location);
  },
  { deep: true },
);
const queueViewport = ref<HTMLElement | null>(null);
function rememberPosition(event: Event) {
  context.state.value.scrollTop = (
    event.currentTarget as HTMLElement
  ).scrollTop;
}
function rememberFocus(event: MouseEvent) {
  const link = (event.target as HTMLElement).closest(
    'a[aria-label^="Abrir pedido "]',
  );
  if (link) {
    context.state.value.focusLabel = link.getAttribute("aria-label") || "";
    context.state.value.windowY = window.scrollY;
  }
}
async function restorePosition() {
  if (!queue.value) return;
  await nextTick();
  const viewport = queueViewport.value;
  if (!viewport) return;
  viewport.scrollTop = context.state.value.scrollTop;
  window.scrollTo({ top: context.state.value.windowY, behavior: "instant" });
  const label = context.state.value.focusLabel;
  if (label) {
    const link = [
      ...viewport.querySelectorAll<HTMLAnchorElement>("a[aria-label]"),
    ].find((item) => item.getAttribute("aria-label") === label);
    link?.focus({ preventScroll: true });
    context.state.value.focusLabel = "";
  }
}
let restoreFrame = 0;
function scheduleRestore() {
  cancelAnimationFrame(restoreFrame);
  restoreFrame = requestAnimationFrame(() => {
    restoreFrame = requestAnimationFrame(() => {
      void restorePosition();
    });
  });
}
onMounted(scheduleRestore);
onBeforeUnmount(() => cancelAnimationFrame(restoreFrame));
watch(
  () => Boolean(queue.value),
  (available) => {
    if (available) scheduleRestore();
  },
);

const negotiationCards = computed(
  () => (queue.value?.ifood_negotiation_orders ?? []) as OrderCardProjection[],
);
const allCards = computed<OrderCardProjection[]>(() =>
  zones.value.flatMap((z) => z.cards),
);
const channels = computed(() => channelOptions(allCards.value));
const fulfillment_ = computed(() => fulfillmentCounts(allCards.value));
const sortLabel = computed(
  () => SORT_OPTIONS.find((o) => o.key === sort.value)?.label ?? "Chegada",
);
const sortMenuItems = computed(() =>
  (view.value === "queue" ? QUEUE_SORT_OPTIONS : SORT_OPTIONS).map(
    (option) => ({
      label: option.label,
      description:
        "hint" in option && typeof option.hint === "string"
          ? option.hint
          : undefined,
      icon:
        (view.value === "queue" ? queueSort.value : sort.value) === option.key
          ? "i-lucide-check"
          : "i-lucide-arrow-up-down",
      onSelect: () =>
        view.value === "queue"
          ? pickQueueSort(option.key as QueueSort)
          : pickSort(option.key as SortKey),
    }),
  ),
);

function triaged(zone: ZoneView): OrderCardProjection[] {
  return triageCards(zone.cards, {
    query: query.value,
    channel: channel.value,
    sort: sort.value,
    fulfillment: fulfillment.value,
  });
}
// flat rows for the dense table view, honouring the same triage + zone order.
const tableRows = computed(() =>
  flattenZones(zones.value.map((z) => ({ ...z, cards: triaged(z) }))),
);
// A Lista (dono, 07/10/2026): linhas integradas num card branco; a linha principal tem
// só o gesto do momento e o ⋯; o resto (detalhes e todas as ações) abre na própria
// linha. A coluna de seleção fica sempre: marcar uma linha liga a barra de lote.
const supervisionColumns = computed(() => [
  { id: "expand", header: "" },
  { id: "select", header: "" },
  { id: "order", header: "Pedido" },
  { id: "stage", header: "Etapa" },
  { id: "items", header: "Itens" },
  { id: "total", header: "Total" },
  { id: "elapsed", header: "Tempo" },
  { id: "actions", header: "Próximo passo" },
]);
// Paginação só quando passa de uma página (dono, 07/10/2026).
const SUPERVISION_PAGE_SIZE = 25;
const supervisionPage = ref(1);
const supervisionRows = computed(() =>
  tableRows.value.slice(
    (supervisionPage.value - 1) * SUPERVISION_PAGE_SIZE,
    supervisionPage.value * SUPERVISION_PAGE_SIZE,
  ),
);
watch(
  () => tableRows.value.length,
  (total) => {
    const last = Math.max(1, Math.ceil(total / SUPERVISION_PAGE_SIZE));
    if (supervisionPage.value > last) supervisionPage.value = last;
  },
);
const supervisionExpanded = ref<Record<string, boolean>>({});
/** O gesto do momento numa linha da Lista: o primário (ou o travado, com o cadeado). */
function rowPrimary(card: OrderCardProjection) {
  return (
    cardAffordances(card).find(
      (aff) => aff.priority === "primary" || aff.disabled,
    ) ?? null
  );
}
/** Os outros gestos, que moram na linha aberta. */
function rowSecondary(card: OrderCardProjection) {
  const primary = rowPrimary(card);
  return cardAffordances(card).filter((aff) => aff.ref !== primary?.ref);
}
// how many cards survive the current filters (for the "no results" affordance).
const visibleCount = computed(() =>
  zones.value.reduce((n, z) => n + triaged(z).length, 0),
);
const hasFilter = computed(
  () =>
    query.value.trim() !== "" ||
    channel.value !== "all" ||
    fulfillment.value !== "all",
);

// Encomendas (datas futuras) sob o mesmo triage do board (busca/canal/tipo);
// o sort não se aplica — a ordem canônica é a data combinada.
const triagedPreorders = computed(() =>
  preorders.value
    .map((group) => ({
      ...group,
      cards: triageCards(group.cards, {
        query: query.value,
        channel: channel.value,
        sort: "arrival",
        fulfillment: fulfillment.value,
      }),
    }))
    .filter((group) => group.cards.length),
);
const preordersCount = computed(() =>
  triagedPreorders.value.reduce((n, g) => n + g.cards.length, 0),
);

// ── bulk selection (Arc 4) ──────────────────────────────────────────────────
// Seleção em lote é um MODO (UX-KIT-V2, prévia v4): a caixa saiu do cartão; liga pelo ⋯
// do cabeçalho, pelo ⋯ do cartão ou pelo toque longo, e a barra de ação aparece em cima.
const selectingMode = ref(false);
const selecting = computed(
  () => selectingMode.value || selected.value.size > 0,
);
function startSelection(ref_?: string) {
  selectingMode.value = true;
  if (ref_ && !selected.value.has(ref_))
    selected.value = new Set([...selected.value, ref_]);
}
function stopSelection() {
  selectingMode.value = false;
  selected.value = new Set();
}
const isSelected = (ref_: string) => selected.value.has(ref_);
const supervisionRowSelection = computed<Record<string, boolean>>(() =>
  Object.fromEntries([...selected.value].map((ref_) => [ref_, true])),
);
function toggleSelect(ref_: string) {
  const next = new Set(selected.value);
  if (next.has(ref_)) next.delete(ref_);
  else next.add(ref_);
  selected.value = next;
}
function clearSelection() {
  selected.value = new Set();
}
// select-all over the currently visible (triaged) cards.
const visibleRefs = computed(() => tableRows.value.map((r) => r.card.ref));
const allVisibleSelected = computed(
  () =>
    visibleRefs.value.length > 0 &&
    visibleRefs.value.every((r) => selected.value.has(r)),
);
function toggleSelectAll() {
  selected.value = allVisibleSelected.value
    ? new Set()
    : new Set(visibleRefs.value);
}
const confirmableSel = computed(() =>
  bulkableRefs(allCards.value, selected.value, "confirm"),
);
const advanceableSel = computed(() =>
  bulkableRefs(allCards.value, selected.value, "advance"),
);
// Aceitar/Avançar em lote: o botão gira até o último pedido responder (clique nunca
// inerte). Antes ele não mudava nada enquanto a fila de N pedidos andava, e o segundo
// toque parecia o primeiro.
const { run: bulkConfirm, pending: bulkConfirming } = usePendingAction(
  async () => {
    const targets = confirmableSel.value.filter((ref) => !isBusy(ref));
    await confirmMany(targets);
    selected.value = new Set(
      [...selected.value].filter(
        (ref) => !targets.includes(ref) || actionError(ref),
      ),
    );
  },
);
const { run: bulkAdvance, pending: bulkAdvancing } = usePendingAction(
  async () => {
    const targets = advanceableSel.value.filter((ref) => !isBusy(ref));
    await advanceMany(targets);
    selected.value = new Set(
      [...selected.value].filter(
        (ref) => !targets.includes(ref) || actionError(ref),
      ),
    );
  },
);

// ⋯ da fila: atualizar, Ciente, seleção, exportar e imprimir (e, no posto Saída e no
// celular, também ordenar, a visão e o som).
const moreOpen = ref(false);
function menuDo(fn: () => void, close = true) {
  if (close) moreOpen.value = false;
  fn();
}
// Celular (abaixo de md): as colunas viram abas.
const isPhone = useMediaQuery("(max-width: 767.98px)");
// Tablet em pé: três colunas de ~240 px cortavam selo e prazo do cartão. Abaixo do
// lg, com mais de uma coluna aberta, o quadro usa as abas do celular.
const isNarrowTablet = useMediaQuery(
  "(min-width: 768px) and (max-width: 1023.98px)",
);
// Celular (prévia v3 `orders-phone3.html`): Entrada, Preparo e Saída viram abas, uma
// coluna por vez, com a contagem na aba. Abre na que tem pedido novo; sem pedido novo,
// na primeira que tem pedido. O toque do operador manda dali em diante.
const pickedZone = ref<string | null>(null);
const phoneZone = computed(() => {
  if (pickedZone.value && zones.value.some((z) => z.key === pickedZone.value))
    return pickedZone.value;
  const intake = zones.value.find((z) => z.key === "intake");
  if (intake && triaged(intake).length) return intake.key;
  return (
    zones.value.find((z) => triaged(z).length)?.key ??
    zones.value[0]?.key ??
    "intake"
  );
});

function pickPhoneZone(value: string | number) {
  pickedZone.value = String(value);
}
function pickSort(key: SortKey) {
  sort.value = key;
}
// A Saída no celular (G16, v4 `cozinha-celular` (a)): entrou pelo "Saída" da barra, as
// abas são "Prontos para sair" e "Em preparo" (com o ponto de atraso); pelo "Pedidos",
// as três colunas. Na aba da Saída, o mais antigo expandido e o resto em linhas.
const phoneExitMode = ref(false);
const phoneTabs = computed(() => {
  const byKey = new Map(zones.value.map((zone) => [zone.key, zone]));
  const tabs = phoneExitMode.value
    ? [
        { key: "expedition", title: "Prontos para sair" },
        { key: "prep", title: "Em preparo" },
      ]
    : (isPhone.value ? zones.value : desktopZones.value).map((zone) => ({
        key: zone.key,
        title: zone.title,
      }));
  return tabs.flatMap((tab) => {
    const zone = byKey.get(tab.key as ZoneView["key"]);
    return zone ? [{ ...tab, zone, late: lateCount(zone) }] : [];
  });
});
const phoneTabItems = computed(() =>
  phoneTabs.value.map((tab) => ({
    ...tab,
    value: tab.key,
    label: tab.title,
    badge: triaged(tab.zone).length,
  })),
);
// Puxe para atualizar (celular) e o aviso dos gestos no fim da lista.
const {
  pull,
  refreshing: pullRefreshing,
  label: pullText,
} = usePullToRefresh(queueViewport, () => refresh(), isPhone);
// Deslizar o cartão para a esquerda (G17): Atender (quem gerencia) e Recusar (pedido novo).
function swipeActions(card: OrderCardProjection): SwipeAction[] {
  const actions: SwipeAction[] = [];
  if (canManageOrders.value) {
    actions.push({
      key: "assign",
      label: card.assigned_operator ? "Liberar" : "Atender",
      icon: card.assigned_operator ? "lucide:user-minus" : "lucide:user-plus",
      tone: "info",
      disabled: isBusy(card.ref),
    });
  }
  const reject = cardAffordances(card).find((aff) => aff.ref === "reject");
  if (reject)
    actions.push({
      key: "reject",
      label: "Recusar",
      icon: "lucide:circle-x",
      tone: "danger",
      disabled: isBusy(card.ref) || reject.disabled,
    });
  return actions;
}
function onSwipe(card: OrderCardProjection, key: string) {
  if (key === "assign") onToggleAssign(card);
  else if (key === "reject") openReject(card.ref);
}

// ── colunas ajustáveis e recolhíveis, lembradas por posto (SUITE-UX §16) ──
// O tablet do passe fica só com a Saída: é o mesmo quadro, com Entrada e Preparo
// recolhidas numa faixa. Nenhuma ação muda; muda só o que cabe na tela.
const boardLayout = useBoardLayout();
// O sinal de canal decide se a segunda linha do cabeçalho existe. Montar sempre o
// slot #feedback e deixar só o filho vazio criava a faixa horizontal sem conteúdo que
// aparecia acima da toolbar da Saída.
const { attention: channelAttention } = useChannelAttention();
const hasChannelQueueSignal = computed(() =>
  Boolean(channelAttention.value?.queue?.length),
);
const desktopZones = computed(() =>
  zones.value.filter((zone) => boardLayout.isOpen(zone.key)),
);
const boardAsTabs = computed(
  () =>
    isPhone.value || (isNarrowTablet.value && desktopZones.value.length > 1),
);
const phoneZones = computed(() =>
  zones.value.filter((zone) => zone.key === phoneZone.value),
);
const boardSplitterItems = computed(() => {
  const open = desktopZones.value;
  const totalWeight = open.reduce(
    (total, zone) => total + (boardLayout.layout.value[zone.key]?.weight ?? 1),
    0,
  );
  return open.map((zone) => ({
    id: `orders-board-${zone.key}`,
    slot: zone.key,
    defaultSize:
      totalWeight > 0
        ? ((boardLayout.layout.value[zone.key]?.weight ?? 1) / totalWeight) *
          100
        : 100 / Math.max(1, open.length),
    minSize: open.length > 1 ? 18 : 100,
  }));
});
const boardSplitterPersistenceKey = computed(
  () =>
    `orders-board:${boardLayout.station.value || "device"}:${desktopZones.value.map((zone) => zone.key).join("-")}`,
);
const mountedView = ref(false);
onMounted(() => {
  mountedView.value = true;
});
// O índice de estações da Cozinha (estação de Saída) e o posto de saída chegam com
// `?columns=expedition`: o quadro abre só com a Saída, e a arrumação fica no posto.
// O parâmetro sai da URL depois de aplicado, para o operador poder abrir as outras.
// O rail usa o mesmo parâmetro: "Pedidos" abre as três colunas (`?columns=all`) e
// "Saída" abre o posto do passe, inclusive com o quadro já na tela.
function applyColumnsQuery() {
  const wanted = route.query[BOARD_COLUMNS_QUERY];
  if (wanted !== "expedition" && wanted !== "all") return;
  if (wanted === "expedition") boardLayout.showOnly("expedition");
  else boardLayout.showAll();
  // No celular as colunas são abas: "Saída" abre a Saída da v4 (abas "Prontos para
  // sair" e "Em preparo"); "Pedidos", as três abas na da vez.
  pickedZone.value = wanted === "expedition" ? "expedition" : null;
  phoneExitMode.value = wanted === "expedition";
  const { [BOARD_COLUMNS_QUERY]: _applied, ...rest } = route.query;
  void router.replace({ path: route.path, query: rest });
}
onMounted(applyColumnsQuery);
watch(
  () => route.query[BOARD_COLUMNS_QUERY],
  () => {
    if (route.path === "/") applyColumnsQuery();
  },
);
// O posto de saída é tablet de toque: todo alvo do cartão sobe para 48 px.
// A Fila "Precisa de você" (V4-G4) é a casa do desktop e do tablet deitado. O celular e
// o tablet em pé seguem com as colunas em abas, e o posto Saída com a Saída larga: lá a
// escolha "Grade" vira a Lista. Antes de montar (SSR), vale a escolha guardada.
const isWide = useMediaQuery("(min-width: 1024px)");
const queueAvailable = computed(
  () => !boardLayout.exitPost.value && (!mountedView.value || isWide.value),
);
const view = computed(() =>
  viewMode.value === "queue" && !queueAvailable.value
    ? "board"
    : viewMode.value,
);
const viewTabs = computed(() => [
  ...(queueAvailable.value
    ? [{ value: "queue", label: "Grade", icon: "i-lucide-layout-grid" }]
    : []),
  { value: "table", label: "Lista", icon: "i-lucide-list" },
]);
function pickView(value: string | number) {
  const next = String(value);
  if (next === "queue" || next === "table") viewMode.value = next;
}
const exitPostView = computed(
  () => view.value === "board" && boardLayout.exitPost.value && !isPhone.value,
);
// Tablet em pé (e o posto Saída): a linha de cima fica com o essencial; ordenar e a
// visão entram no ⋯, para o cabeçalho não quebrar em duas linhas.
// Só depois de montar: o servidor não sabe a largura, e classe divergente na hidratação
// não é corrigida pelo Vue (o campo ficaria com a largura do servidor).
// Abaixo do xl, título, busca e todos os controles não cabem numa linha (a 1024 px o
// título "Pedidos" virava "Pe…"): ordenar e a visão vão para o ⋯.
const isNarrow = useMediaQuery("(max-width: 1279.98px)");
const mounted = ref(false);
onMounted(() => {
  mounted.value = true;
});
const compactHeader = computed(
  () =>
    mounted.value && (exitPostView.value || (isNarrow.value && !isPhone.value)),
);

// O rail conta o que o quadro vê: pedidos novos em Pedidos e o que está na Saída, e
// acende "Saída" quando o posto está só com ela. Fora do quadro, a contagem leve do rail.
const rail = useGestorRail();
watch(
  () => ({
    exitPost: isPhone.value
      ? phoneExitMode.value || phoneZone.value === "expedition"
      : boardLayout.exitPost.value,
    intake: zones.value.find((z) => z.key === "intake")?.count ?? 0,
    exit: zones.value.find((z) => z.key === "expedition")?.count ?? 0,
  }),
  (next) => {
    rail.value = { onBoard: true, ...next };
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  rail.value = { ...rail.value, onBoard: false, exitPost: false };
});

const EXIT_FILTERS = [
  { key: "all", label: "Todos", icon: "lucide:check" },
  { key: "pickup", label: "Retirada", icon: "lucide:store" },
  { key: "delivery", label: "Entrega", icon: "lucide:bike" },
] as const;
const exitFilterTabs = EXIT_FILTERS.map((option) => ({
  value: option.key,
  label: option.label,
  icon: option.icon.replace("lucide:", "i-lucide-"),
}));
// A faixa de recortes do fluxo: na Saída, os três da expedição; no celular, a versão
// curta; no resto, com as contagens.
const fulfillmentFilterTabs = computed<TabsItem[]>(() =>
  exitPostView.value
    ? exitFilterTabs
    : isPhone.value
      ? fulfillmentCompactTabs.value
      : fulfillmentTabs.value,
);
const nowMs = useNowTick(() => queue.value?.intake[0]?.server_now_iso ?? "");
function zoneNext(zone: ZoneView): string {
  return zone.key === "expedition" ? nextOutRef(triaged(zone)) : "";
}
// A coluna sozinha na tela (posto Saída) usa a largura: grade de cartões, não fila única.
function wideColumn(key: string): boolean {
  return !isPhone.value && key === "expedition" && boardLayout.exitPost.value;
}
function onStationReady(card: OrderCardProjection, stationRef: string) {
  if (card.kitchen)
    void markStationReady(card.ref, card.kitchen.order_pk, stationRef);
}
function lateCount(zone: ZoneView): number {
  return triaged(zone).filter((card) => timerTone(card.timer_class) === "late")
    .length;
}
const shortcutHint = (key: string) =>
  String(BOARD_ZONE_KEYS.indexOf(key as (typeof BOARD_ZONE_KEYS)[number]) + 1);

// ── a Fila "Precisa de você" (V4-G4) ────────────────────────────────────────
// Os mesmos recortes do quadro (busca, canal, Entrega/Retirada), mais as encomendas
// que ainda pedem aceite. O foco começa no mais urgente; ↑/↓ andam, Enter faz o gesto.
// A Fila também recebe o pedido em negociação no iFood, inclusive o já entregue (o
// cliente reclama depois): ele espera uma resposta como qualquer outro (dono, 07/10).
const queueCards = computed<OrderCardProjection[]>(() => {
  const cards = [
    ...tableRows.value.map((row) => row.card),
    ...triagedPreorders.value.flatMap((group) => group.cards),
  ];
  const seen = new Set(cards.map((card) => card.ref));
  return [
    ...cards,
    ...negotiationCards.value.filter((card) => !seen.has(card.ref)),
  ];
});
// O que as setas alcançam: o que a Fila mostra (em "Precisa de você", os 4 em foco).
const queueOrder = computed(() => {
  const order = queueItems(queueCards.value, nowMs.value, {
    scope: scope.value,
    sort: queueSort.value,
  }).map((item) => item.card);
  return scope.value === "attention" ? order.slice(0, QUEUE_FOCUS) : order;
});
const scopeCounts = computed(() =>
  queueScopeCounts(queueCards.value, nowMs.value),
);
const QUEUE_SCOPES: { key: QueueScope; label: string }[] = [
  { key: "attention", label: "Precisa de você" },
  { key: "all", label: "Todos" },
  { key: "late", label: "Atrasados" },
];
const queueScopeTabs = computed(() =>
  QUEUE_SCOPES.map((option) => ({
    value: option.key,
    label: option.label,
    badge: scopeCounts.value[option.key],
  })),
);
const fulfillmentTabs = computed(() => [
  {
    value: "all",
    label: "Todos",
    icon: "i-lucide-layers-3",
    badge: allCards.value.length,
  },
  {
    value: "delivery",
    label: "Entrega",
    icon: "i-lucide-bike",
    badge: fulfillment_.value.delivery,
  },
  {
    value: "pickup",
    label: "Retirada",
    icon: "i-lucide-store",
    badge: fulfillment_.value.pickup,
  },
]);
const fulfillmentCompactTabs = computed(() =>
  fulfillmentTabs.value.map(({ icon: _icon, ...item }) => item),
);
const channelItems = computed(() => [
  { value: "all", label: "Todos os canais", icon: "i-lucide-layers" },
  ...channels.value.map((option) => ({
    value: option.ref,
    label: `${option.label} (${option.count})`,
    icon: `i-lucide-${lucideIcon(allCards.value.find((card) => card.channel_ref === option.ref)?.channel_icon || "")}`,
  })),
]);
function pickScope(value: string | number) {
  if (value === "attention" || value === "all" || value === "late")
    scope.value = value;
}
function pickFulfillment(value: string | number) {
  if (value === "all" || value === "delivery" || value === "pickup")
    fulfillment.value = value;
}
const queueSortLabel = computed(
  () =>
    QUEUE_SORT_OPTIONS.find((o) => o.key === queueSort.value)?.label ??
    "Urgência",
);
function pickQueueSort(key: QueueSort) {
  queueSort.value = key;
}
// A tecla A aceita o pedido novo em foco; sem ele, o pedido novo mais urgente da Fila.
const acceptRef = computed(() => {
  const confirmable = (card: OrderCardProjection) =>
    card.attention === "confirm" && card.can_confirm;
  const focused = queueOrder.value.find(
    (card) => card.ref === queueFocus.value,
  );
  if (focused && confirmable(focused)) return focused.ref;
  return queueOrder.value.find(confirmable)?.ref ?? "";
});
const queueFocusPicked = ref("");
const queueFocus = computed(() => {
  const refs = queueOrder.value.map((card) => card.ref);
  return refs.includes(queueFocusPicked.value)
    ? queueFocusPicked.value
    : (refs[0] ?? "");
});
function queueKey(e: KeyboardEvent): boolean {
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (key === "g" && queueAvailable.value) {
    e.preventDefault();
    viewMode.value = "queue";
    return true;
  }
  if (key === "l") {
    e.preventDefault();
    viewMode.value = "table";
    return true;
  }
  if (view.value !== "queue") return false;
  const order = queueOrder.value;
  const index = order.findIndex((card) => card.ref === queueFocus.value);
  if (key === "ArrowDown" || key === "ArrowUp") {
    if (!order.length) return false;
    e.preventDefault();
    const next =
      key === "ArrowDown"
        ? Math.min(order.length - 1, index + 1)
        : Math.max(0, index - 1);
    queueFocusPicked.value = order[next]!.ref;
    document
      .querySelector(`[data-queue-ref="${CSS.escape(order[next]!.ref)}"]`)
      ?.scrollIntoView({ block: "nearest" });
    return true;
  }
  if (key === "a" && acceptRef.value && !isBusy(acceptRef.value)) {
    e.preventDefault();
    onAction(acceptRef.value, "confirm");
    return true;
  }
  const card = order[index];
  if (!card || isBusy(card.ref)) return false;
  if (
    key === "Enter" &&
    !(e.target as HTMLElement | null)?.closest(
      "button, a, input, textarea, select",
    )
  ) {
    const item = queueItems([card], nowMs.value)[0];
    if (card.attention === "station") {
      const station = card.kitchen?.stations.find((s) => s.can_mark_ready);
      if (!station) return false;
      e.preventDefault();
      onStationReady(card, station.station_ref);
      return true;
    }
    const primary = item ? queueGesture(item).primary : null;
    if (!primary || primary.disabled) return false;
    e.preventDefault();
    onAction(card.ref, primary.ref);
    return true;
  }
  return false;
}

// keyboard shortcuts (Arc 3): / search · r refresh · v view · s sort · Esc clear ·
// 1/2/3 recolhem ou abrem Entrada, Preparo e Saída.
// Pure mapping in resolveShortcut; here we run the effects and skip while typing.
const searchInput = ref<{ focus: () => void } | null>(null);
function onKeydown(e: KeyboardEvent) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  // Esc fecha primeiro o drawer móvel; menus canônicos cuidam do próprio Escape.
  if (e.key === "Escape" && moreOpen.value) {
    moreOpen.value = false;
    return;
  }
  const el = e.target as HTMLElement | null;
  const typing =
    !!el &&
    (el.tagName === "INPUT" ||
      el.tagName === "TEXTAREA" ||
      el.isContentEditable);
  const column =
    view.value === "board" ? queueColumnForKey(e.key, boardLayout.keys) : null;
  if (column) {
    // Com um diálogo aberto a tecla é do diálogo, não do quadro atrás dele.
    if (
      typing ||
      rejectRef.value ||
      settleRef.value ||
      dispatchRef.value ||
      courierBackRef.value
    )
      return;
    e.preventDefault();
    boardLayout.toggle(column);
    return;
  }
  // A Fila: F e T trocam a visão; na Fila, ↑/↓ andam, Enter faz o gesto do item em
  // foco e A aceita o pedido novo em foco. O R continua sendo "atualizar".
  if (
    !typing &&
    !rejectRef.value &&
    !settleRef.value &&
    !dispatchRef.value &&
    !courierBackRef.value &&
    queueKey(e)
  )
    return;
  const shortcut = resolveShortcut(e.key);
  if (!shortcut) return;
  // While typing, only Escape (clear-filters / blur) is honoured.
  if (typing && shortcut !== "clear-filters") return;
  switch (shortcut) {
    case "focus-search":
      e.preventDefault();
      searchInput.value?.focus();
      break;
    case "refresh":
      refresh();
      break;
    case "toggle-view":
      // V: as três colunas (Entrada, Preparo, Saída) e de volta à Fila.
      viewMode.value =
        view.value === "board"
          ? queueAvailable.value
            ? "queue"
            : "table"
          : "board";
      break;
    case "cycle-sort":
      sort.value = nextSort(sort.value);
      break;
    case "clear-filters":
      if (selecting.value && !typing) stopSelection();
      query.value = "";
      channel.value = "all";
      fulfillment.value = "all";
      if (typing) (el as HTMLElement).blur();
      break;
  }
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

// reject dialog (needs a reason). For marketplace (iFood) orders the reason is a
// coded pick from the provider's live list; other channels use free text.
const rejectRef = ref<string | null>(null);
const rejectReason = ref("");
const rejectReasons = ref<CancellationReason[]>([]);
const rejectCode = ref("");
const rejectDirty = computed(
  () =>
    rejectRef.value !== null &&
    Boolean(rejectReason.value.trim() || rejectCode.value),
);
const confirmDiscard = useConfirm();
async function closeReject() {
  if (rejectRef.value && isBusy(rejectRef.value)) return;
  if (
    rejectDirty.value &&
    !(await confirmDiscard({
      title: "Descartar o motivo digitado?",
      description:
        "O motivo que você escreveu se perde, e o pedido não é recusado.",
      cancelLabel: "Continuar escrevendo",
    }))
  )
    return;
  rejectRef.value = null;
}
onBeforeRouteLeave(
  () =>
    !rejectDirty.value ||
    confirmDiscard({
      title: "Sair sem recusar o pedido?",
      description:
        "O motivo que você escreveu se perde, e o pedido não é recusado.",
      confirmLabel: "Descartar e sair",
      cancelLabel: "Continuar escrevendo",
    }),
);
function beforeUnload(event: BeforeUnloadEvent) {
  if (!rejectDirty.value) return;
  event.preventDefault();
  event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload));
const rejectReasonsLoading = ref(false);
const rejectReasonsError = ref("");
const isMarketplaceReject = computed(
  () =>
    allCards.value.find((c) => c.ref === rejectRef.value)?.channel_ref ===
    "ifood",
);
const canConfirmReject = computed(
  () =>
    !rejectReasonsLoading.value &&
    !rejectReasonsError.value &&
    (isMarketplaceReject.value
      ? rejectReasons.value.some((r) => r.code === rejectCode.value)
      : rejectReason.value.trim() !== ""),
);
async function openReject(ref_: string) {
  rejectRef.value = ref_;
  rejectReason.value = "";
  rejectCode.value = "";
  rejectReasons.value = [];
  await loadRejectReasons();
}
let rejectReasonsRequest = 0;
async function loadRejectReasons() {
  const ref_ = rejectRef.value;
  if (!ref_) return;
  const request = ++rejectReasonsRequest;
  rejectReasonsLoading.value = true;
  rejectReasonsError.value = "";
  try {
    const result = await fetchCancellationReasons(ref_);
    if (request === rejectReasonsRequest && ref_ === rejectRef.value)
      rejectReasons.value = result;
  } catch {
    if (request === rejectReasonsRequest && ref_ === rejectRef.value)
      rejectReasonsError.value =
        "Não foi possível consultar os motivos. Nenhuma ação foi aplicada.";
  } finally {
    if (request === rejectReasonsRequest) rejectReasonsLoading.value = false;
  }
}

function onRejectCodeChange() {
  // Mirror the picked reason's text into the customer-facing reason.
  const picked = rejectReasons.value.find((r) => r.code === rejectCode.value);
  if (picked) rejectReason.value = picked.description;
}
async function confirmReject() {
  const ref_ = rejectRef.value;
  if (!ref_ || isBusy(ref_) || !canConfirmReject.value) return;
  const ok = await reject(
    ref_,
    rejectReason.value.trim() || "Pedido recusado",
    rejectCode.value,
  );
  if (ok) rejectRef.value = null;
}

// settle-cash dialog (needs an amount; and, when the courier took change from
// the drawer, how much of it came back — zero included; the server requires it).
const settleRef = ref<string | null>(null);
const cashDrafts = useOrderCashDrafts();
const settleCard = computed(
  () => allCards.value.find((c) => c.ref === settleRef.value) ?? null,
);
const settleAction = computed(() =>
  settleCard.value?.actions.find(
    (action) => action.ref === "settle-delivery-cash",
  ),
);
const settlementDraft = computed(() => {
  const initial = {
    amount: "",
    changeBack: settleCard.value?.change_back_pending
      ? moneyInput(changeBackSuggestionQ(settleCard.value))
      : "",
    equipmentBack: false,
    revision: String(settleAction.value?.payload_schema.base_revision || ""),
    custody: String(settleAction.value?.confirmation.description || ""),
  };
  return (
    (settleRef.value ? cashDrafts.settlements.value[settleRef.value] : null) ??
    initial
  );
});
const settleAmount = computed({
  get: () => settlementDraft.value.amount,
  set: (v: string) => {
    settlementDraft.value.amount = v;
  },
});
const settleChangeBack = computed({
  get: () => settlementDraft.value.changeBack,
  set: (v: string) => {
    settlementDraft.value.changeBack = v;
  },
});
const settleEquipmentBack = computed({
  get: () => settlementDraft.value.equipmentBack,
  set: (v: boolean) => {
    settlementDraft.value.equipmentBack = v;
  },
});
const settleRevision = computed(() => settlementDraft.value.revision);
const settleCustody = computed(() => settlementDraft.value.custody);
const settleChanged = computed(
  () =>
    settleRevision.value !==
    String(settleAction.value?.payload_schema.base_revision || ""),
);
function reviewSettleCustody() {
  settlementDraft.value.revision = String(
    settleAction.value?.payload_schema.base_revision || "",
  );
  settlementDraft.value.custody = String(
    settleAction.value?.confirmation.description || "",
  );
}
const settleAsksChangeBack = computed(() =>
  Boolean(settleCard.value?.change_back_pending),
);
const settleAsksEquipment = computed(() =>
  Boolean(settleCard.value?.equipment_back_pending),
);
function openSettle(ref_: string) {
  settleRef.value = ref_;
  cashDrafts.settlement(ref_, settlementDraft.value);
}
async function confirmSettle() {
  const ref_ = settleRef.value;
  if (!ref_) return;
  const changeBack = settleAsksChangeBack.value
    ? settleChangeBack.value.trim() || "0"
    : undefined;
  const ok = await settleCash(
    ref_,
    settleAmount.value.trim(),
    changeBack,
    settleAsksEquipment.value && settleEquipmentBack.value,
    settleRevision.value,
  );
  if (ok) {
    cashDrafts.clear("settlement", ref_);
    settleRef.value = null;
  }
}

// Saída para entrega: um toque quando não há o que perguntar (a maquininha
// livre é escolhida sozinha); senão, o diálogo (troco, ir junto, qual maquininha,
// ou onde elas estão). Os passos saem em ordem: quem abre a saída primeiro.
const dispatchRef = ref<string | null>(null);
const dispatchCard = computed(
  () => allCards.value.find((c) => c.ref === dispatchRef.value) ?? null,
);
async function runDispatch(steps: DispatchStep[]) {
  for (const step of steps) {
    const ok = await advance(
      step.ref,
      step.changeOut,
      step.equipment,
      step.tripRef,
    );
    if (!ok) return false;
  }
  return true;
}
async function onDispatch(steps: DispatchStep[]) {
  if (await runDispatch(steps)) dispatchRef.value = null;
}

// "Entregador voltou": confirma o que deve estar na mão e fecha a saída inteira.
const courierBackRef = ref<string | null>(null);
const courierBackCard = computed(
  () => allCards.value.find((c) => c.ref === courierBackRef.value) ?? null,
);
async function confirmCourierBack() {
  const ref_ = courierBackRef.value;
  if (!ref_) return;
  if (await courierBack(ref_)) courierBackRef.value = null;
}
function courierBackDifferent() {
  const card = courierBackCard.value;
  courierBackRef.value = null;
  if (!card) return;
  if (card.can_settle_delivery_cash) openSettle(card.ref);
  else navigateTo(`/${card.ref}`);
}

function onAction(ref_: string, action: AffordanceRef) {
  if (action === "confirm") confirm(ref_);
  else if (action === "advance") {
    const card = allCards.value.find((c) => c.ref === ref_);
    if (card?.next_status !== "dispatched") advance(ref_);
    else {
      const steps = oneTapDispatch(card, allCards.value);
      if (steps) runDispatch(steps);
      else dispatchRef.value = card.ref;
    }
  } else if (action === "courier_back") courierBackRef.value = ref_;
  else if (action === "reject") openReject(ref_);
  else if (action === "settle_cash") openSettle(ref_);
  else if (action === "equipment_back") equipmentBack(ref_);
  else if (action === "undo_handoff") undoHandoff(ref_);
  else if (action === "undo_ready") undoReady(ref_);
}

// O interruptor do canal na coluna da Fila (G09): o MESMO diálogo de Canais, com
// período, motivo e a aprovação do gerente; a leitura da Fila se refaz depois.
const menuChannels = computed(
  () => queue.value?.awareness?.menu_channels ?? [],
);
const switchRef = ref<string | null>(null);
const switchTarget = computed(
  () =>
    menuChannels.value.find((row) => row.ref === switchRef.value)?.switch ??
    null,
);
const { switchChannel, isSwitching } = useChannelSwitch(
  (ref_) => menuChannels.value.find((row) => row.ref === ref_)?.switch,
  () => refresh(),
);
const submitSwitch = (
  request: Parameters<typeof switchChannel>[1],
  approval?: Record<string, string>,
) => switchChannel(switchRef.value!, request, approval);

// claim/release an order ("estou atendendo").
function onToggleAssign(card: OrderCardProjection) {
  if (card.assigned_operator) unassign(card.ref);
  else assign(card.ref);
}

// ── export / print (Arc 5) ───────────────────────────────────────────────
// CSV of the current (triaged) queue for a shift handover; print uses the
// browser dialog (the print stylesheet hides the chrome and shows the table).
function exportCsv() {
  const csv = rowsToCsv(tableRows.value);
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const stamp = new Date()
    .toISOString()
    .slice(0, 16)
    .replace("T", "-")
    .replace(":", "h");
  const a = document.createElement("a");
  a.href = url;
  a.download = `pedidos-${stamp}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
function printQueue() {
  window.print();
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <!-- Cabeçalho de UMA linha (UX-KIT-V2, prévia v4 `gestor-fila4.html`): título, ao vivo,
         busca e poucos controles (som, ordenar, visão, ⋯). Atualizar, exportar, imprimir,
         a seleção em lote e a última leitura útil moram no ⋯; Ciente aparece aqui só
         enquanto há pedido novo esperando. No posto Saída (`gestor-colunas4.html`):
         "Visão: Saída", "Mostrar as 3 colunas" e o som; o resto no ⋯. -->
    <OperatorPageHeader
      :title="exitPostView ? 'Saída' : 'Pedidos'"
      :filters-wrap="false"
    >
      <template #status>
        <!-- No celular o título não se corta: o estado vai por extenso só na falha; o
             resto fica no ponto, na hora e no nome acessível. -->
        <OperatorLiveStatus
          :tone="liveTone"
          :time="readClock"
          :label="
            isPhone && !error
              ? ''
              : error
                ? isPhone
                  ? 'Falhou'
                  : 'Atualização falhou'
                : realtimeView.label
          "
          :detail="
            isPhone
              ? `${error ? 'Atualização falhou. ' : `${realtimeView.label}. `}${realtimeView.title}`
              : realtimeView.title
          "
        />
      </template>
      <template #search>
        <OperatorSuiteSearch
          ref="searchInput"
          :model-value="query"
          screen-label="filtrando o quadro"
          :placeholder="
            exitPostView
              ? 'Código ou cliente'
              : 'Buscar pedido, cliente ou item'
          "
          aria-label="Buscar por código, cliente ou item (atalho: /)"
          @update:model-value="(v) => (query = v)"
        />
      </template>
      <template v-if="!isPhone" #actions>
        <!-- a visão deste posto e o caminho de volta às três colunas -->
        <template
          v-if="view === 'board' && !boardLayout.allOpen.value && !isPhone"
        >
          <NuxtButton
            icon="i-lucide-columns-3"
            label="Mostrar as 3 colunas"
            color="neutral"
            variant="outline"
            title="Mostrar as 3 colunas (atalhos: 1, 2 e 3)"
            data-board-show-all
            @click="boardLayout.showAll()"
          />
        </template>
        <!-- O som de pedido novo e o "Ciente" que o cala formam um grupo só: o Ciente
             aparece enquanto há pedido novo tocando e, reconhecido, some, deixando o
             botão do som sozinho. No posto Saída o Ciente fica no ⋯. O som tem os
             mesmos 3 estados do KDS: ligado, desligado e ligado-mas-bloqueado pelo
             autoplay (ponto âmbar até o 1º gesto). -->
        <NuxtFieldGroup v-if="!isPhone" data-sound-group>
          <!-- Filhos diretos do FieldGroup, sem Chip no meio: o grupo arredonda só as
               pontas e cola as bordas pelo primeiro e último filho. "Som bloqueado
               pelo navegador" é a cor do próprio botão (warning) até o 1º gesto. -->
          <NuxtButton
            :icon="soundOn ? 'i-lucide-volume-2' : 'i-lucide-volume-x'"
            :color="soundOn && soundBlocked ? 'warning' : 'neutral'"
            variant="outline"
            square
            :aria-label="
              soundOn && soundBlocked
                ? 'Som bloqueado: toque para ativar'
                : soundOn
                  ? 'Som de pedido novo ativo'
                  : 'Som de pedido novo desativado'
            "
            :title="
              soundOn && soundBlocked
                ? 'Som bloqueado: toque para ativar'
                : 'Som de pedido novo'
            "
            data-sound-toggle
            @click="handleSoundAction"
          />
          <NuxtButton
            v-if="attentionPending && !exitPostView"
            icon="i-lucide-check"
            label="Ciente"
            color="neutral"
            variant="outline"
            aria-label="Reconhecer aviso de pedido novo"
            @click="acknowledgeAttention"
          />
        </NuxtFieldGroup>

        <template v-if="!compactHeader && !isPhone">
          <!-- ordenar: na Fila, "Urgência ▾" (tempo contra a meta, chegada, mais recentes);
               no quadro e na tabela, a ordem deles -->
          <NuxtDropdownMenu :items="sortMenuItems" :content="{ align: 'end' }">
            <NuxtButton
              icon="i-lucide-arrow-up-down"
              trailing-icon="i-lucide-chevron-down"
              :label="view === 'queue' ? queueSortLabel : sortLabel"
              color="neutral"
              variant="outline"
              :title="
                view === 'queue' ? 'Ordenar a Fila' : 'Ordenar (atalho: s)'
              "
              data-board-sort
            />
          </NuxtDropdownMenu>

          <!-- visão: dois segmentos genéricos, Grade G (os cartões da Fila) | Lista L (a
               tabela densa, com seleção em lote), nomes que servem a qualquer tela com
               muitos registros (dono, 07/10/2026). As três colunas (Entrada, Preparo,
               Saída) moram no ⋯ e na tecla V, e o posto Saída abre nelas. -->
          <NuxtTabs
            :model-value="view"
            :items="viewTabs"
            :content="false"
            variant="pill"
            aria-label="Visão do Gestor"
            data-view-switch
            @update:model-value="pickView"
          />
        </template>

        <!-- ⋯ da fila (do tablet para cima; no celular ele mora no fim dos recortes). O posto
             Saída (v4 `gestor-colunas`) não tem ⋯: a leitura se atualiza sozinha e o Ciente
             é tocar a faixa da Entrada que pulsa. -->
        <BoardMenu
          v-if="!isPhone && !exitPostView"
          mode="dropdown"
          :metadata="readMetadata"
          :failed="Boolean(error)"
          :pending="pending"
          :sort="sort"
          :view-mode="view"
          :queue-available="queueAvailable"
          :sound-on="soundOn"
          :sound-blocked="soundBlocked"
          :attention-pending="attentionPending"
          :selecting="selecting"
          :full="compactHeader"
          @refresh="refresh()"
          @acknowledge="acknowledgeAttention"
          @select="selecting ? stopSelection() : startSelection()"
          @sort="pickSort"
          @view="(mode) => (viewMode = mode)"
          @sound="handleSoundAction"
          @export="exportCsv"
          @print="printQueue"
        />
      </template>

      <!-- recortes (v4): Todos, o eixo do fluxo (Entrega, Retirada) e o canal num
           seletor só. O posto Saída usa a mesma faixa: o título já diz a visão. -->
      <!-- A Saída no celular (v4 `cozinha-celular` (a)) não tem a linha de recortes: a
           barra de cima, as duas abas e a lista. -->
      <template
        v-if="
          ((exitPostView && desktopZones.length) ||
            (allCards.length && !exitPostView) ||
            isPhone) &&
          !(isPhone && phoneExitMode)
        "
        #filters
      >
        <!-- na Fila (v4): "Precisa de você N · Todos N · ● Atrasados N", o recorte do que
             muda o trabalho; no quadro e na tabela, "Todos" tira os recortes. -->
        <NuxtTabs
          v-if="view === 'queue'"
          :model-value="scope"
          :items="queueScopeTabs"
          :content="false"
          variant="pill"
          data-queue-scopes
          @update:model-value="pickScope"
        />
        <NuxtTabs
          :model-value="fulfillment"
          :items="fulfillmentFilterTabs"
          :content="false"
          variant="pill"
          aria-label="Tipo de entrega"
          @update:model-value="pickFulfillment"
        />
        <NuxtSelect
          v-if="channels.length"
          v-model="channel"
          :items="channelItems"
          aria-label="Canal"
          data-channel-picker
        />
        <!-- celular: os controles do quadro num painel só ("Filtros" da prévia v3), no começo
             da linha para nunca ficar fora da tela -->
        <NuxtChip
          v-if="isPhone"
          :show="attentionPending || (soundOn && soundBlocked)"
          color="warning"
          size="2xl"
          inset
        >
          <NuxtButton
            icon="i-lucide-sliders-horizontal"
            label="Filtros"
            color="neutral"
            variant="outline"
            aria-haspopup="dialog"
            :aria-expanded="moreOpen"
            data-board-more
            @click="moreOpen = true"
          />
        </NuxtChip>
      </template>
      <template v-if="hasChannelQueueSignal" #feedback>
        <!-- a loja no iFood: só o SINAL, e só quando muda o que entra na fila. -->
        <ChannelQueueSignal :attention="channelAttention" />
      </template>
    </OperatorPageHeader>

    <!-- celular: o painel dos controles sobe do pé, ao alcance do polegar -->
    <NuxtDrawer
      v-if="isPhone"
      :open="moreOpen"
      title="Filtros e ações da fila"
      description="Ordenação, visão, atualização e ações auxiliares."
      @update:open="(value) => (moreOpen = value)"
    >
      <template #body>
        <BoardMenu
          :metadata="readMetadata"
          :failed="Boolean(error)"
          :pending="pending"
          :sort="sort"
          :view-mode="view"
          :queue-available="queueAvailable"
          :sound-on="soundOn"
          :sound-blocked="soundBlocked"
          :attention-pending="attentionPending"
          :selecting="selecting"
          full
          @refresh="refresh()"
          @acknowledge="menuDo(acknowledgeAttention)"
          @select="
            menuDo(() => (selecting ? stopSelection() : startSelection()))
          "
          @sort="(key) => menuDo(() => pickSort(key))"
          @view="(mode) => menuDo(() => (viewMode = mode))"
          @sound="menuDo(handleSoundAction)"
          @export="menuDo(exportCsv)"
          @print="menuDo(printQueue)"
        />
      </template>
    </NuxtDrawer>

    <!-- celular: as colunas viram abas dentro da segunda faixa canônica do header. -->
    <OperatorToolbar
      v-if="boardAsTabs && view === 'board' && zones.length"
      class="py-2"
    >
      <NuxtTabs
        :model-value="phoneZone"
        :items="phoneTabItems"
        :content="false"
        variant="link"
        data-board-zone-tabs
        @update:model-value="pickPhoneZone"
      />
    </OperatorToolbar>

    <!-- barra da seleção em lote (o modo ligado) -->
    <OperatorToolbar v-if="selecting" data-bulk-bar>
      <template #left>
        <NuxtBadge
          color="primary"
          icon="i-lucide-list-checks"
          :label="
            selected.size
              ? `${selected.size} selecionado${selected.size > 1 ? 's' : ''}`
              : 'Toque nos pedidos para marcar'
          "
        />
      </template>
      <template #right>
        <div class="ms-auto flex flex-wrap items-center gap-1.5">
          <NuxtButton
            v-if="confirmableSel.length"
            :icon="bulkConfirming ? 'i-line-md-loading-loop' : 'i-lucide-check'"
            :label="`Aceitar ${confirmableSel.length}`"
            color="primary"
            :disabled="bulkConfirming"
            :loading="bulkConfirming"
            :aria-busy="bulkConfirming || undefined"
            @click="bulkConfirm"
          />
          <NuxtButton
            v-if="advanceableSel.length"
            :icon="
              bulkAdvancing ? 'i-line-md-loading-loop' : 'i-lucide-arrow-right'
            "
            :label="`Avançar ${advanceableSel.length}`"
            color="neutral"
            variant="outline"
            :disabled="bulkAdvancing"
            :loading="bulkAdvancing"
            :aria-busy="bulkAdvancing || undefined"
            @click="bulkAdvance"
          />
          <NuxtButton
            :label="allVisibleSelected ? 'Desmarcar todos' : 'Marcar todos'"
            color="neutral"
            variant="outline"
            @click="toggleSelectAll"
          />
          <NuxtButton
            v-if="selected.size"
            label="Limpar"
            color="neutral"
            variant="ghost"
            @click="clearSelection"
          />
          <NuxtButton
            :label="EXIT_SELECTION_LABEL"
            color="neutral"
            variant="outline"
            data-bulk-done
            @click="stopSelection"
          />
        </div>
      </template>
    </OperatorToolbar>

    <section
      ref="queueViewport"
      class="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 *:shrink-0 sm:p-6"
      @scroll.passive="rememberPosition"
      @click.capture="rememberFocus"
    >
      <!-- puxe para atualizar (celular) -->
      <p
        v-if="isPhone && (pull > 0 || pullRefreshing)"
        class="flex shrink-0 items-center justify-center gap-2 overflow-hidden op-micro text-muted-foreground"
        :style="{ height: `${pullRefreshing ? 40 : pull}px` }"
        aria-live="polite"
        data-pull-refresh
      >
        <Icon
          name="lucide:refresh-cw"
          class="size-4"
          :class="pullRefreshing ? 'motion-safe:animate-spin' : ''"
        />{{ pullText }}
      </p>
      <div
        v-if="pending && !zones.length"
        class="grid gap-3 md:grid-cols-2 lg:grid-cols-3"
        aria-label="Carregando fila"
      >
        <NuxtSkeleton v-for="i in 3" :key="i" class="h-40 w-full" />
      </div>
      <!-- `!stationLocked`: antes do PIN toda leitura volta 403 `station_locked`; quem
           fala nesse estado é a identificação que sobe por cima (app.vue). -->
      <NuxtAlert
        v-else-if="error && !stationLocked"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Falha ao atualizar a fila"
        description="Mantivemos a última leitura; atualize antes de confirmar ações."
        data-queue-error
      />

      <template v-if="queue">
        <!-- no results across all zones for the active filters -->
        <NuxtEmpty
          v-if="hasFilter && !visibleCount"
          icon="i-lucide-search-x"
          title="Nenhum pedido para os filtros atuais"
          :actions="[
            {
              label: 'Limpar filtros',
              onClick: () => {
                query = '';
                channel = 'all';
                fulfillment = 'all';
              },
            },
          ]"
        />

        <!-- a Fila "Precisa de você" (v4): só o fato humano é botão -->
        <QueueView
          v-else-if="view === 'queue'"
          :cards="queueCards"
          :awareness="queue.awareness"
          :now-ms="nowMs"
          :focus-ref="queueFocus"
          :accept-ref="acceptRef"
          :scope="scope"
          :sort="queueSort"
          :is-busy="isBusy"
          :action-error="actionError"
          :can-open="canManageOrders"
          :switching="isSwitching"
          @action="onAction"
          @station-ready="onStationReady"
          @focus="(ref_) => (queueFocusPicked = ref_)"
          @dismiss-error="clearActionError"
          @scope="(next) => (scope = next)"
          @toggle-assign="onToggleAssign"
          @select-mode="
            (ref_) => {
              startSelection(ref_);
              viewMode = 'table';
            }
          "
          @volumes="(ref_, count) => declareVolumes(ref_, count, 'orders')"
          @station-recall="recallStation"
          @switch="(ref_) => (switchRef = ref_)"
        />

        <!-- O quadro usa o Splitter oficial do kit no desktop. No celular, as tabs
             mantêm uma coluna por vez: nenhuma alça ou faixa paralela ao Nuxt UI. -->
        <template v-else-if="view === 'board'">
          <OperatorSplitter
            v-if="!boardAsTabs"
            id="orders-board-columns"
            :persistence-key="boardSplitterPersistenceKey"
            :items="boardSplitterItems"
            class="min-h-full flex-1"
            handle-label="Ajustar largura das colunas"
            data-board-columns
            @layout="boardLayout.applySizes"
          >
            <template v-for="zone in desktopZones" :key="zone.key" #[zone.key]>
              <OrderBoardColumn
                :zone="zone"
                :cards="triaged(zone)"
                :now-ms="nowMs"
                :next-ref="zoneNext(zone)"
                :phone="false"
                :wide="wideColumn(zone.key)"
                :can-open="canManageOrders"
                :selecting="selecting"
                :can-collapse="boardLayout.canCollapse(zone.key)"
                :shortcut="shortcutHint(zone.key)"
                :is-busy="isBusy"
                :action-error="actionError"
                :is-selected="isSelected"
                :danfe-printing="danfePrint.isPrinting"
                :swipe-actions="swipeActions"
                :heading="!exitPostView"
                @collapse="boardLayout.toggle(zone.key)"
                @action="onAction"
                @dismiss-error="clearActionError"
                @toggle-select="toggleSelect"
                @toggle-assign="onToggleAssign"
                @select-mode="startSelection"
                @print-danfe="danfePrint.printDanfe"
                @station-ready="onStationReady"
                @station-recall="recallStation"
                @volumes="declareVolumes"
                @swipe="onSwipe"
              />
            </template>
          </OperatorSplitter>

          <OrderBoardColumn
            v-for="zone in phoneZones"
            v-else
            :key="zone.key"
            :zone="zone"
            :cards="triaged(zone)"
            :now-ms="nowMs"
            :next-ref="zoneNext(zone)"
            phone
            :wide="false"
            :can-open="canManageOrders"
            :selecting="selecting"
            :can-collapse="false"
            :shortcut="shortcutHint(zone.key)"
            :is-busy="isBusy"
            :action-error="actionError"
            :is-selected="isSelected"
            :danfe-printing="danfePrint.isPrinting"
            :swipe-actions="swipeActions"
            @action="onAction"
            @dismiss-error="clearActionError"
            @toggle-select="toggleSelect"
            @toggle-assign="onToggleAssign"
            @select-mode="startSelection"
            @print-danfe="danfePrint.printDanfe"
            @station-ready="onStationReady"
            @station-recall="recallStation"
            @volumes="declareVolumes"
            @swipe="onSwipe"
          />
        </template>

        <!-- A Lista: a NuxtTable canônica dentro de um card branco (receita do Kitchen
             Sink), com linha expansível para os detalhes e as outras ações. -->
        <NuxtCard v-else class="min-w-0" data-supervision-card>
          <NuxtTable
            v-model:expanded="supervisionExpanded"
            :data="supervisionRows"
            :columns="supervisionColumns"
            :get-row-id="(row) => row.card.ref"
            :row-selection="supervisionRowSelection"
            caption="Lista dos pedidos em andamento"
            data-supervision-table
          >
            <template #expand-cell="{ row }">
              <NuxtButton
                :icon="
                  row.getIsExpanded()
                    ? 'i-lucide-chevron-up'
                    : 'i-lucide-chevron-down'
                "
                color="neutral"
                variant="ghost"
                square
                :aria-label="`Detalhes do pedido ${row.original.card.ref}`"
                :aria-expanded="row.getIsExpanded()"
                data-supervision-expand
                @click="row.toggleExpanded()"
              />
            </template>
            <template #select-header>
              <NuxtCheckbox
                :model-value="
                  allVisibleSelected
                    ? true
                    : selected.size
                      ? 'indeterminate'
                      : false
                "
                aria-label="Selecionar todos os pedidos da lista"
                @update:model-value="toggleSelectAll"
              />
            </template>
            <template #select-cell="{ row }">
              <NuxtCheckbox
                :model-value="isSelected(row.original.card.ref)"
                :aria-label="`Selecionar o pedido ${row.original.card.ref}`"
                @update:model-value="toggleSelect(row.original.card.ref)"
              />
            </template>
            <template #order-cell="{ row }">
              <div class="flex min-w-0 flex-col">
                <NuxtLink
                  v-if="canManageOrders"
                  :to="`/${row.original.card.ref}`"
                  class="font-semibold tabular-nums hover:underline"
                  :aria-label="`Abrir pedido ${row.original.card.ref}`"
                  >{{ splitRef(row.original.card.ref).code }}</NuxtLink
                >
                <span v-else class="font-semibold tabular-nums">{{
                  splitRef(row.original.card.ref).code
                }}</span>
                <span
                  class="inline-flex max-w-48 items-center gap-1 text-xs text-muted-foreground"
                >
                  <Icon
                    :name="`lucide:${lucideIcon(row.original.card.channel_icon)}`"
                    class="size-3.5 shrink-0"
                  />
                  <span class="truncate">{{
                    row.original.card.customer_name || "Sem cliente"
                  }}</span>
                </span>
              </div>
            </template>
            <template #stage-cell="{ row }">
              <NuxtBadge
                :color="
                  statusTone(row.original.card.status) === 'danger'
                    ? 'error'
                    : statusTone(row.original.card.status) === 'success'
                      ? 'success'
                      : statusTone(row.original.card.status) === 'warning'
                        ? 'warning'
                        : 'neutral'
                "
                :label="row.original.card.status_label"
              />
            </template>
            <template #items-cell="{ row }">
              <span
                class="block max-w-40 truncate text-muted-foreground xl:max-w-64"
                :title="row.original.card.items_summary"
                >{{ row.original.card.items_summary }}</span
              >
            </template>
            <template #total-cell="{ row }">
              <span class="whitespace-nowrap font-semibold tabular-nums">{{
                row.original.card.total_display
              }}</span>
            </template>
            <template #elapsed-cell="{ row }">
              <NuxtBadge
                :color="
                  timerTone(row.original.card.timer_class) === 'late'
                    ? 'warning'
                    : timerTone(row.original.card.timer_class) === 'warning'
                      ? 'warning'
                      : 'neutral'
                "
                :label="elapsedLabel(row.original.card.elapsed_seconds)"
              />
            </template>
            <template #actions-cell="{ row }">
              <div class="flex min-w-max items-center justify-end gap-1.5">
                <NuxtButton
                  v-if="rowPrimary(row.original.card)"
                  :icon="
                    rowPrimary(row.original.card)!.disabled
                      ? 'i-lucide-lock'
                      : rowPrimary(row.original.card)!.icon.replace(
                          'lucide:',
                          'i-lucide-',
                        )
                  "
                  :label="rowPrimary(row.original.card)!.label"
                  :color="
                    rowPrimary(row.original.card)!.disabled
                      ? 'neutral'
                      : 'primary'
                  "
                  :variant="
                    rowPrimary(row.original.card)!.disabled
                      ? 'outline'
                      : 'solid'
                  "
                  :disabled="
                    isBusy(row.original.card.ref) ||
                    rowPrimary(row.original.card)!.disabled
                  "
                  :title="rowPrimary(row.original.card)!.reason || undefined"
                  data-supervision-primary
                  @click="
                    onAction(
                      row.original.card.ref,
                      rowPrimary(row.original.card)!.ref,
                    )
                  "
                />
                <OrderCardMenu
                  :card="row.original.card"
                  :busy="isBusy(row.original.card.ref)"
                  :can-open="canManageOrders"
                  :selecting="selecting"
                  :selected="isSelected(row.original.card.ref)"
                  @toggle-assign="onToggleAssign(row.original.card)"
                  @toggle-select="toggleSelect(row.original.card.ref)"
                  @select-mode="startSelection(row.original.card.ref)"
                  @volumes="
                    (count) => declareVolumes(row.original.card.ref, count)
                  "
                  @station-recall="
                    (pk) => recallStation(row.original.card.ref, pk)
                  "
                />
              </div>
              <NuxtAlert
                v-if="actionError(row.original.card.ref)"
                class="mt-2"
                color="error"
                variant="subtle"
                icon="i-lucide-triangle-alert"
                :description="actionError(row.original.card.ref)"
                :actions="[
                  {
                    label: 'Dispensar',
                    color: 'error',
                    variant: 'outline',
                    onClick: () => clearActionError(row.original.card.ref),
                  },
                ]"
              />
            </template>
            <!-- a linha aberta: os detalhes do pedido e todas as outras ações -->
            <template #expanded="{ row }">
              <div
                class="grid gap-4 whitespace-normal lg:grid-cols-[minmax(0,1fr)_auto]"
                data-supervision-detail
              >
                <dl
                  class="grid gap-x-6 gap-y-2 op-body sm:grid-cols-[auto_minmax(0,1fr)]"
                >
                  <dt class="text-muted-foreground">Itens</dt>
                  <dd>{{ row.original.card.items_summary }}</dd>
                  <dt class="text-muted-foreground">Recebimento</dt>
                  <dd>
                    {{ row.original.card.fulfillment_label
                    }}<template v-if="row.original.card.delivery_address">
                      · {{ row.original.card.delivery_address }}</template
                    >
                  </dd>
                  <template v-if="row.original.card.payment_method_label">
                    <dt class="text-muted-foreground">Pagamento</dt>
                    <dd>
                      {{ row.original.card.payment_method_label
                      }}<template v-if="row.original.card.change_label">
                        · {{ row.original.card.change_label }}</template
                      >
                    </dd>
                  </template>
                  <template v-if="row.original.card.equipment_label">
                    <dt class="text-muted-foreground">Maquininha</dt>
                    <dd>{{ row.original.card.equipment_label }}</dd>
                  </template>
                  <template v-if="row.original.card.assigned_operator">
                    <dt class="text-muted-foreground">Atende</dt>
                    <dd>{{ row.original.card.assigned_operator }}</dd>
                  </template>
                  <template v-if="row.original.card.advance_block_reason">
                    <dt class="text-muted-foreground">Por que espera</dt>
                    <dd>{{ row.original.card.advance_block_reason }}</dd>
                  </template>
                </dl>
                <div
                  class="flex flex-wrap content-start items-start justify-end gap-2"
                >
                  <NuxtButton
                    v-for="aff in rowSecondary(row.original.card)"
                    :key="aff.ref"
                    :icon="aff.icon.replace('lucide:', 'i-lucide-')"
                    :label="aff.label"
                    :color="aff.priority === 'danger' ? 'error' : 'neutral'"
                    variant="outline"
                    :disabled="isBusy(row.original.card.ref) || aff.disabled"
                    :title="aff.reason || undefined"
                    @click="onAction(row.original.card.ref, aff.ref)"
                  />
                  <NuxtButton
                    v-if="canManageOrders"
                    :to="`/${row.original.card.ref}`"
                    icon="i-lucide-file-text"
                    label="Abrir o pedido"
                    color="neutral"
                    variant="outline"
                  />
                </div>
              </div>
            </template>
          </NuxtTable>
          <template v-if="tableRows.length > SUPERVISION_PAGE_SIZE" #footer>
            <div class="flex items-center justify-between gap-3">
              <span class="op-micro text-muted-foreground tnum"
                >{{ tableRows.length }} pedidos</span
              >
              <NuxtPagination
                v-model:page="supervisionPage"
                :total="tableRows.length"
                :items-per-page="SUPERVISION_PAGE_SIZE"
              />
            </div>
          </template>
        </NuxtCard>

        <!-- Agendados: pedidos confirmados para datas futuras, fora das colunas
             do dia. Agrupados pela data combinada; no dia, o despertador devolve
             o pedido ao fluxo normal do board. -->
        <section v-if="preordersCount" class="mt-6" data-preorders-section>
          <div class="flex items-center gap-2 border-b pb-2">
            <Icon
              name="lucide:calendar-clock"
              class="size-4 text-muted-foreground"
            />
            <h2 class="text-sm font-bold uppercase tracking-wide">Agendados</h2>
            <NuxtBadge
              color="neutral"
              :label="String(preordersCount)"
            />
            <span
              class="ms-auto hidden text-end text-xs text-muted-foreground sm:block"
              >Confirmados para os próximos dias</span
            >
          </div>
          <div class="mt-3 grid gap-4 lg:grid-cols-3">
            <div
              v-for="group in triagedPreorders"
              :key="group.date"
              class="flex min-w-0 flex-col gap-3"
            >
              <h3
                class="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              >
                {{ group.label }}
              </h3>
              <OrderCard
                v-for="card in group.cards"
                :key="card.ref"
                :card="card"
                :busy="isBusy(card.ref)"
                :error="actionError(card.ref)"
                :selected="isSelected(card.ref)"
                :selecting="selecting"
                :danfe-printing="danfePrint.isPrinting(card.ref)"
                :can-open="canManageOrders"
                @action="(action) => onAction(card.ref, action)"
                @dismiss-error="clearActionError(card.ref)"
                @toggle-select="toggleSelect(card.ref)"
                @toggle-assign="onToggleAssign(card)"
                @select-mode="startSelection(card.ref)"
                @print-danfe="danfePrint.printDanfe(card.ref)"
              />
            </div>
          </div>
        </section>
      </template>
    </section>

    <!-- reject dialog -->
    <NuxtModal
      :open="rejectRef != null"
      :title="`Recusar pedido ${rejectRef ?? ''}`"
      :description="
        isMarketplaceReject
          ? 'Escolha o motivo que o iFood exige. Ele é enviado ao iFood.'
          : 'Informe o motivo. O cliente recebe o aviso com ele.'
      "
      @update:open="
        (v) => {
          if (!v) closeReject();
        }
      "
    >
      <template #body>
        <div class="grid gap-4">
          <NuxtEmpty
            v-if="rejectReasonsLoading"
            icon="i-line-md-loading-loop"
            title="Carregando motivos do iFood…"
          />
          <NuxtAlert
            v-else-if="rejectReasonsError"
            color="error"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :description="rejectReasonsError"
            :actions="[
              {
                label: 'Consultar novamente',
                color: 'error',
                variant: 'outline',
                onClick: () => loadRejectReasons(),
              },
            ]"
          />
          <NuxtEmpty
            v-else-if="isMarketplaceReject && !rejectReasons.length"
            icon="i-lucide-circle-slash"
            title="Nenhum motivo disponível"
            description="O iFood não oferece motivos de cancelamento neste momento."
          />
          <!-- Marketplace (iFood): coded reason picker from the provider's live list -->
          <NuxtSelect
            v-else-if="isMarketplaceReject"
            v-model="rejectCode"
            class="w-full"
            :items="
              rejectReasons.map((reason) => ({
                label: reason.description,
                value: reason.code,
              }))
            "
            placeholder="Selecione o motivo…"
            aria-label="Motivo do cancelamento (iFood)"
            @update:model-value="onRejectCodeChange"
          />
          <!-- Other channels: free-text reason -->
          <NuxtTextarea
            v-else
            v-model="rejectReason"
            class="w-full"
            :rows="3"
            placeholder="Motivo da recusa…"
            aria-label="Motivo da recusa"
          />
        </div>
      </template>
      <template #footer>
        <NuxtButton
          label="Voltar"
          color="neutral"
          variant="outline"
          :disabled="Boolean(rejectRef && isBusy(rejectRef))"
          @click="closeReject"
        />
        <NuxtButton
          label="Recusar pedido"
          color="error"
          :disabled="
            !canConfirmReject || Boolean(rejectRef && isBusy(rejectRef))
          "
          @click="confirmReject"
        />
      </template>
    </NuxtModal>

    <!-- o interruptor do canal (coluna da Fila): o mesmo diálogo de Canais -->
    <ChannelSwitchDialog
      :open="Boolean(switchTarget)"
      :sw="switchTarget"
      :managers="queue?.awareness?.managers ?? []"
      :viewer-name="queue?.awareness?.viewer_name ?? ''"
      :busy="Boolean(switchRef && isSwitching(switchRef))"
      :submit="submitSwitch"
      @update:open="
        (value: boolean) => {
          if (!value) switchRef = null;
        }
      "
    />

    <!-- saída para entrega (só quando há o que perguntar) -->
    <DispatchDialog
      :card="dispatchCard"
      :cards="allCards"
      :busy="dispatchRef != null && isBusy(dispatchRef)"
      @dispatch="onDispatch"
      @courier-back="(ref_) => (courierBackRef = ref_)"
      @close="dispatchRef = null"
    />

    <!-- entregador voltou: confere e fecha a saída inteira -->
    <CourierBackDialog
      :card="courierBackCard"
      :busy="courierBackRef != null && isBusy(courierBackRef)"
      @confirm="confirmCourierBack"
      @different="courierBackDifferent"
      @close="courierBackRef = null"
    />

    <!-- settle-cash dialog -->
    <NuxtModal
      :open="settleRef != null"
      :title="
        settleCard?.fulfillment_type === 'pickup'
          ? 'Pagamento na retirada'
          : 'Acerto da entrega'
      "
      :description="`${settleCard?.fulfillment_type === 'pickup' ? 'Valor recebido na retirada' : 'Valor recebido na entrega'} (${settleRef}). Em branco usa o total de ${settleCard?.total_display}. ${settleCustody}`"
      @update:open="
        (v) => {
          if (!v) settleRef = null;
        }
      "
    >
      <template #body>
        <div class="grid gap-4">
          <NuxtAlert
            v-if="settleChanged"
            color="warning"
            variant="subtle"
            title="O pedido ou turno mudou"
            :description="`Confira o contexto atual: ${settleAction?.confirmation.description || ''}`"
            :actions="[
              {
                label: 'Conferir e manter os valores digitados',
                color: 'warning',
                variant: 'outline',
                onClick: () => reviewSettleCustody(),
              },
            ]"
          />
          <NuxtFormField label="Valor recebido">
            <NuxtInput
              v-model="settleAmount"
              class="w-full"
              type="text"
              inputmode="decimal"
              placeholder="Ex.: 15,00"
            />
          </NuxtFormField>
          <!-- o entregador levou troco da gaveta: quanto voltou (zero vale) -->
          <NuxtFormField
            v-if="settleAsksChangeBack"
            :label="`${settleCard?.change_label}. Quanto voltou?`"
            data-change-back
          >
            <NuxtInput
              v-model="settleChangeBack"
              class="w-full"
              type="text"
              inputmode="decimal"
              placeholder="0,00"
              aria-label="Troco que voltou"
            />
          </NuxtFormField>
          <NuxtCheckbox
            v-if="settleAsksEquipment"
            v-model="settleEquipmentBack"
            :label="`${settleCard?.equipment_label}. Voltou junto`"
            data-equipment-back
          />
        </div>
      </template>
      <template #footer>
        <NuxtButton
          label="Voltar"
          color="neutral"
          variant="outline"
          @click="settleRef = null"
        />
        <NuxtButton
          label="Confirmar acerto"
          color="primary"
          :disabled="
            settleChanged ||
            !settleAction?.enabled ||
            (settleRef ? isBusy(settleRef) : false)
          "
          @click="confirmSettle"
        />
      </template>
    </NuxtModal>
  </main>
</template>
