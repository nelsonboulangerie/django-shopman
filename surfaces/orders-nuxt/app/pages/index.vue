<script setup lang="ts">
// Order board — the operator hub. Reads the two-zone queue projection + realtime
// (SSE + 30s poll) via useOrdersBoard; renders Entrada / Preparo / Saída columns of
// OrderCards; the gestures POST through the django proxy (CSRF handled there) and
// reconcile. Desktop-first (3 columns), responsive (stacks on tablet/phone).
import type { AffordanceRef, DispatchStep, SortKey, ZoneView } from "~/presentation/board";
import {
  bulkableRefs,
  cardAffordances,
  changeBackSuggestionQ,
  channelLabel,
  channelOptions,
  elapsedLabel,
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
  stripSummary,
  timerChip,
  timerTone,
  toneBadge,
  triageCards,
  waitingStripText,
  zoneEmptyText,
} from "~/presentation/board";
import type { OrderCardProjection } from "~/types/orders";
import type { SwipeAction } from "~/components/SwipeReveal.vue";
import type { CancellationReason } from "~/composables/useOrdersBoard";
import { BOARD_COLUMNS_QUERY, BOARD_ZONE_KEYS, useBoardLayout } from "~/composables/useBoardLayout";
import { QUEUE_FOCUS, QUEUE_SORT_OPTIONS, queueGesture, queueItems, queueScopeCounts, type QueueScope, type QueueSort } from "~/presentation/queue";
import { queueColumnForKey } from "../../../operator-kit/app/presentation/queueColumns";

const { readMetadata, queue, zones, deviceAgent, preorders, realtime, pending, error, refresh, isBusy, actionError, clearActionError, confirm, advance, reject, fetchCancellationReasons, settleCash, equipmentBack, courierBack, undoHandoff, undoReady, assign, unassign, confirmMany, advanceMany, markStationReady, recallStation, declareVolumes, soundOn, soundBlocked, attentionPending, toggleSound, activateAttentionSound, acknowledgeAttention } = useOrdersBoard();
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
const liveTone = computed(() => (error.value ? "off" : realtime.value === "live" ? "live" : realtime.value === "connecting" ? "late" : "calm"));
const readClock = computed(() => {
  const at = readMetadata.value?.generated_at;
  return at ? new Date(at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";
});

// Estação travada pelo servidor: não é falha de leitura, é falta de
// identificação. O board deixa de desenhar o aviso de erro nesse estado.
const { denied: stationLocked } = useStationLock();

// ── triage: search + channel filter + sort + view-mode (Arc 1) ──────────────
definePageMeta({ key: (route) => route.path });
const route = useRoute();
const router = useRouter();
const context = useOrdersContext();
const { query, channel, fulfillment, sort, viewMode, scope, queueSort, selected } = context;
// O recorte vive na URL; seleção/posição/foco ficam só na sessão e pessoa atual.
context.readLocation(route.query);
watch(() => route.query, (params) => { if (route.path === "/") context.readLocation(params); });
// A pessoa chega depois da primeira leitura (a sessão carrega no cliente): relê a URL
// antes de o recorte reescrevê-la, para "/?view=board" abrir na Supervisão.
watch(() => context.state.value.owner, (owner) => { if (owner && route.path === "/") context.readLocation(route.query); });
watch(context.location, (location) => {
  if (route.path === "/" && JSON.stringify(route.query) !== JSON.stringify(location.query)) void router.replace(location);
}, { deep: true });
const queueViewport = ref<HTMLElement | null>(null);
function rememberPosition(event: Event) {
  context.state.value.scrollTop = (event.currentTarget as HTMLElement).scrollTop;
}
function rememberFocus(event: MouseEvent) {
  const link = (event.target as HTMLElement).closest('a[aria-label^="Abrir pedido "]');
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
    const link = [...viewport.querySelectorAll<HTMLAnchorElement>("a[aria-label]")].find(item => item.getAttribute("aria-label") === label);
    link?.focus({ preventScroll: true });
    context.state.value.focusLabel = "";
  }
}
let restoreFrame = 0;
function scheduleRestore() {
  cancelAnimationFrame(restoreFrame);
  restoreFrame = requestAnimationFrame(() => { restoreFrame = requestAnimationFrame(() => { void restorePosition(); }); });
}
onMounted(scheduleRestore);
onBeforeUnmount(() => cancelAnimationFrame(restoreFrame));
watch(() => Boolean(queue.value), (available) => { if (available) scheduleRestore(); });

const negotiationCards = computed(() => (queue.value?.ifood_negotiation_orders ?? []) as OrderCardProjection[]);
const allCards = computed<OrderCardProjection[]>(() => zones.value.flatMap((z) => z.cards));
const channels = computed(() => channelOptions(allCards.value));
const fulfillment_ = computed(() => fulfillmentCounts(allCards.value));
const sortLabel = computed(() => SORT_OPTIONS.find((o) => o.key === sort.value)?.label ?? "Chegada");

function triaged(zone: ZoneView): OrderCardProjection[] {
  return triageCards(zone.cards, { query: query.value, channel: channel.value, sort: sort.value, fulfillment: fulfillment.value });
}
// flat rows for the dense table view, honouring the same triage + zone order.
const tableRows = computed(() =>
  flattenZones(zones.value.map((z) => ({ ...z, cards: triaged(z) }))),
);
// how many cards survive the current filters (for the "no results" affordance).
const visibleCount = computed(() => zones.value.reduce((n, z) => n + triaged(z).length, 0));
const hasFilter = computed(() => query.value.trim() !== "" || channel.value !== "all" || fulfillment.value !== "all");

// Encomendas (datas futuras) sob o mesmo triage do board (busca/canal/tipo);
// o sort não se aplica — a ordem canônica é a data combinada.
const triagedPreorders = computed(() =>
  preorders.value
    .map((group) => ({
      ...group,
      cards: triageCards(group.cards, { query: query.value, channel: channel.value, sort: "arrival", fulfillment: fulfillment.value }),
    }))
    .filter((group) => group.cards.length),
);
const preordersCount = computed(() => triagedPreorders.value.reduce((n, g) => n + g.cards.length, 0));

// ── bulk selection (Arc 4) ──────────────────────────────────────────────────
// Seleção em lote é um MODO (UX-KIT-V2, prévia v4): a caixa saiu do cartão; liga pelo ⋯
// do cabeçalho, pelo ⋯ do cartão ou pelo toque longo, e a barra de ação aparece em cima.
const selectingMode = ref(false);
const selecting = computed(() => selectingMode.value || selected.value.size > 0);
function startSelection(ref_?: string) {
  selectingMode.value = true;
  if (ref_ && !selected.value.has(ref_)) selected.value = new Set([...selected.value, ref_]);
}
function stopSelection() {
  selectingMode.value = false;
  selected.value = new Set();
}
const isSelected = (ref_: string) => selected.value.has(ref_);
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
const allVisibleSelected = computed(() => visibleRefs.value.length > 0 && visibleRefs.value.every((r) => selected.value.has(r)));
function toggleSelectAll() {
  selected.value = allVisibleSelected.value ? new Set() : new Set(visibleRefs.value);
}
const confirmableSel = computed(() => bulkableRefs(allCards.value, selected.value, "confirm"));
const advanceableSel = computed(() => bulkableRefs(allCards.value, selected.value, "advance"));
// Aceitar/Avançar em lote: o botão gira até o último pedido responder (clique nunca
// inerte). Antes ele não mudava nada enquanto a fila de N pedidos andava, e o segundo
// toque parecia o primeiro.
const { run: bulkConfirm, pending: bulkConfirming } = usePendingAction(async () => {
  const targets = confirmableSel.value.filter((ref) => !isBusy(ref));
  await confirmMany(targets);
  selected.value = new Set([...selected.value].filter((ref) => !targets.includes(ref) || actionError(ref)));
});
const { run: bulkAdvance, pending: bulkAdvancing } = usePendingAction(async () => {
  const targets = advanceableSel.value.filter((ref) => !isBusy(ref));
  await advanceMany(targets);
  selected.value = new Set([...selected.value].filter((ref) => !targets.includes(ref) || actionError(ref)));
});

// sort menu (house pattern: button + backdrop + absolute panel).
const sortOpen = ref(false);
// ⋯ da fila: atualizar, Ciente, seleção, exportar e imprimir (e, no posto Saída e no
// celular, também ordenar, a visão e o som).
const moreOpen = ref(false);
const channelOpen = ref(false);
function menuDo(fn: () => void, close = true) {
  if (close) moreOpen.value = false;
  fn();
}
// Celular (abaixo de md): as colunas viram abas.
const isPhone = useMediaQuery("(max-width: 767.98px)");
// Celular (prévia v3 `orders-phone3.html`): Entrada, Preparo e Saída viram abas, uma
// coluna por vez, com a contagem na aba. Abre na que tem pedido novo; sem pedido novo,
// na primeira que tem pedido. O toque do operador manda dali em diante.
const pickedZone = ref<string | null>(null);
const phoneZone = computed(() => {
  if (pickedZone.value && zones.value.some((z) => z.key === pickedZone.value)) return pickedZone.value;
  const intake = zones.value.find((z) => z.key === "intake");
  if (intake && triaged(intake).length) return intake.key;
  return zones.value.find((z) => triaged(z).length)?.key ?? zones.value[0]?.key ?? "intake";
});

function pickPhoneZone(value: string | number) {
  pickedZone.value = String(value);
}
function pickSort(key: SortKey) {
  sort.value = key;
  sortOpen.value = false;
}
// A Saída no celular (G16, v4 `cozinha-celular` (a)): entrou pelo "Saída" da barra, as
// abas são "Prontos para sair" e "Em preparo" (com o ponto de atraso); pelo "Pedidos",
// as três colunas. Na aba da Saída, o mais antigo expandido e o resto em linhas.
const phoneExitMode = ref(false);
const phoneTabs = computed(() => {
  const byKey = new Map(zones.value.map((zone) => [zone.key, zone]));
  const tabs = phoneExitMode.value
    ? [{ key: "expedition", title: "Prontos para sair" }, { key: "prep", title: "Em preparo" }]
    : zones.value.map((zone) => ({ key: zone.key, title: zone.title }));
  return tabs.flatMap((tab) => {
    const zone = byKey.get(tab.key as ZoneView["key"]);
    return zone ? [{ ...tab, zone, late: lateCount(zone) }] : [];
  });
});
// Puxe para atualizar (celular) e o aviso dos gestos no fim da lista.
const { pull, refreshing: pullRefreshing, label: pullText } = usePullToRefresh(queueViewport, () => refresh(), isPhone);
// Deslizar o cartão para a esquerda (G17): Atender (quem gerencia) e Recusar (pedido novo).
function swipeActions(card: OrderCardProjection): SwipeAction[] {
  const actions: SwipeAction[] = [];
  if (canManageOrders.value) {
    actions.push({ key: "assign", label: card.assigned_operator ? "Liberar" : "Atender", icon: card.assigned_operator ? "lucide:user-minus" : "lucide:user-plus", tone: "info", disabled: isBusy(card.ref) });
  }
  const reject = cardAffordances(card).find((aff) => aff.ref === "reject");
  if (reject) actions.push({ key: "reject", label: "Recusar", icon: "lucide:circle-x", tone: "danger", disabled: isBusy(card.ref) || reject.disabled });
  return actions;
}
function onSwipe(card: OrderCardProjection, key: string) {
  if (key === "assign") onToggleAssign(card);
  else if (key === "reject") openReject(card.ref);
}

// ── colunas ajustáveis e recolhíveis, lembradas por posto (SUITE-UX §16) ──
// O tablet do passe fica só com a Saída: é o mesmo quadro, com Entrada e Preparo
// recolhidas numa faixa. Nenhuma ação muda; muda só o que cabe na tela.
const zoneTitles = computed<Record<string, string>>(() => Object.fromEntries(zones.value.map((z) => [z.key, z.title])));
const boardLayout = useBoardLayout(() => zoneTitles.value);
const mountedView = ref(false);
onMounted(() => { mountedView.value = true; });
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
watch(() => route.query[BOARD_COLUMNS_QUERY], () => { if (route.path === "/") applyColumnsQuery(); });
// O posto de saída é tablet de toque: todo alvo do cartão sobe para 48 px.
// A Fila "Precisa de você" (V4-G4) é a casa do desktop e do tablet deitado. O celular e
// o tablet em pé seguem com as colunas em abas, e o posto Saída com a Saída larga: lá a
// escolha "Fila" vira a Supervisão. Antes de montar (SSR), vale a escolha guardada.
const isWide = useMediaQuery("(min-width: 1024px)");
const queueAvailable = computed(() => !boardLayout.exitPost.value && (!mountedView.value || isWide.value));
const view = computed(() => (viewMode.value === "queue" && !queueAvailable.value ? "board" : viewMode.value));
const touchCards = computed(() => view.value === "board" && boardLayout.exitPost.value);
const exitPostView = computed(() => view.value === "board" && boardLayout.exitPost.value && !isPhone.value);
// Tablet em pé (e o posto Saída): a linha de cima fica com o essencial; ordenar e a
// visão entram no ⋯, para o cabeçalho não quebrar em duas linhas.
// Só depois de montar: o servidor não sabe a largura, e classe divergente na hidratação
// não é corrigida pelo Vue (o campo ficaria com a largura do servidor).
const isNarrow = useMediaQuery("(max-width: 1023.98px)");
const mounted = ref(false);
onMounted(() => { mounted.value = true; });
const compactHeader = computed(() => mounted.value && (exitPostView.value || (isNarrow.value && !isPhone.value)));
// Item 4: o header canônico consome este model; o estado e os efeitos ficam aqui (dono).
provideGestorBoardHeader({
  title: "Pedidos",
  eyebrow: computed(() => (exitPostView.value && boardLayout.station.value ? "Posto Saída · este dispositivo" : "")),
});

// O rail conta o que o quadro vê: pedidos novos em Pedidos e o que está na Saída, e
// acende "Saída" quando o posto está só com ela. Fora do quadro, a contagem leve do rail.
const rail = useGestorRail();
watch(
  () => ({
    exitPost: isPhone.value ? phoneExitMode.value || phoneZone.value === "expedition" : boardLayout.exitPost.value,
    intake: zones.value.find((z) => z.key === "intake")?.count ?? 0,
    exit: zones.value.find((z) => z.key === "expedition")?.count ?? 0,
  }),
  (next) => { rail.value = { onBoard: true, ...next }; },
  { immediate: true },
);
onBeforeUnmount(() => { rail.value = { ...rail.value, onBoard: false, exitPost: false }; });

// A Saída larga (posto do passe): uma grade de cartões de altura igual em duas linhas,
// como na v4; o que não cabe vira a faixa "+N esperando" e aparece quando um sair. A
// faixa abre todos (nunca paginação, nunca cartão inalcançável).
const exitGrid = ref<HTMLElement | null>(null);
function setExitGrid(el: unknown) {
  exitGrid.value = el instanceof HTMLElement ? el : null;
}
const EXIT_FILTERS = [
  { key: "all", label: "Todos", icon: "lucide:check" },
  { key: "pickup", label: "Retirada", icon: "lucide:store" },
  { key: "delivery", label: "Entrega", icon: "lucide:bike" },
] as const;
const { width: exitGridWidth } = useElementSize(exitGrid);
const exitShowAll = ref(false);
const exitCapacity = computed(() => {
  const width = exitGridWidth.value;
  if (!width) return 6;
  const columns = Math.max(1, Math.floor((width + 12) / (272 + 12)));
  return columns * 2;
});
function exitCards(zone: ZoneView) {
  const cards = triaged(zone);
  return exitShowAll.value ? cards : cards.slice(0, exitCapacity.value);
}
function exitOverflow(zone: ZoneView) {
  return exitShowAll.value ? [] : triaged(zone).slice(exitCapacity.value);
}
const nowMs = useNowTick(() => queue.value?.intake[0]?.server_now_iso ?? "");
function zoneNext(zone: ZoneView): string {
  return zone.key === "expedition" ? nextOutRef(triaged(zone)) : "";
}
// Onde a arrumação do posto mora (a frase curta da v4).
const layoutMemory = computed(() => {
  if (!boardLayout.station.value) return "vale até recarregar a tela";
  if (boardLayout.saveFailed.value) return "não deu para guardar neste posto";
  return "lembrada neste posto · salva no servidor";
});
// A coluna sozinha na tela (posto Saída) usa a largura: grade de cartões, não fila única.
function wideColumn(key: string): boolean {
  return !isPhone.value && key === "expedition" && boardLayout.exitPost.value;
}
function onStationReady(card: OrderCardProjection, stationRef: string) {
  if (card.kitchen) void markStationReady(card.ref, card.kitchen.order_pk, stationRef);
}
const columnEls = new Map<string, HTMLElement>();
function setColumnEl(key: string, el: unknown) {
  if (el instanceof HTMLElement) columnEls.set(key, el);
  else columnEls.delete(key);
}
function columnWidth(key: string | null): number {
  return key ? columnEls.get(key)?.getBoundingClientRect().width ?? 0 : 0;
}
function onResizeStart(key: string) {
  boardLayout.startResize(key, columnWidth(key), columnWidth(boardLayout.nextOpen(key)));
}
// Abrir a faixa da Entrada que pulsa é o "Ciente" do posto Saída (o som para).
function openColumn(key: string) {
  if (key === "intake" && attentionPending.value) acknowledgeAttention();
  boardLayout.open(key);
}
function lateCount(zone: ZoneView): number {
  return triaged(zone).filter((card) => timerTone(card.timer_class) === "late").length;
}
const shortcutHint = (key: string) => String(BOARD_ZONE_KEYS.indexOf(key as (typeof BOARD_ZONE_KEYS)[number]) + 1);

// ── a Fila "Precisa de você" (V4-G4) ────────────────────────────────────────
// Os mesmos recortes do quadro (busca, canal, Entrega/Retirada), mais as encomendas
// que ainda pedem aceite. O foco começa no mais urgente; ↑/↓ andam, Enter faz o gesto.
const queueCards = computed<OrderCardProjection[]>(() => [
  ...tableRows.value.map((row) => row.card),
  ...triagedPreorders.value.flatMap((group) => group.cards),
]);
// O que as setas alcançam: o que a Fila mostra (em "Precisa de você", os 4 em foco).
const queueOrder = computed(() => {
  const order = queueItems(queueCards.value, nowMs.value, { scope: scope.value, sort: queueSort.value }).map((item) => item.card);
  return scope.value === "attention" ? order.slice(0, QUEUE_FOCUS) : order;
});
const scopeCounts = computed(() => queueScopeCounts(queueCards.value, nowMs.value));
// A base da Fila é "Precisa de você". "Atrasados" saiu daqui e virou ORDENAÇÃO
// (QUEUE_SORT_OPTIONS); "Todos" deixou de ser recorte — o que muda o trabalho são
// o fluxo (Entrega/Retirada) e o canal.
const QUEUE_SCOPES: { key: QueueScope; label: string }[] = [
  { key: "attention", label: "Precisa de você" },
];
const queueSortLabel = computed(() => QUEUE_SORT_OPTIONS.find((o) => o.key === queueSort.value)?.label ?? "Urgência");
function pickQueueSort(key: QueueSort) {
  queueSort.value = key;
  sortOpen.value = false;
}
// A tecla A aceita o pedido novo em foco; sem ele, o pedido novo mais urgente da Fila.
const acceptRef = computed(() => {
  const confirmable = (card: OrderCardProjection) => card.attention === "confirm" && card.can_confirm;
  const focused = queueOrder.value.find((card) => card.ref === queueFocus.value);
  if (focused && confirmable(focused)) return focused.ref;
  return queueOrder.value.find(confirmable)?.ref ?? "";
});
const queueFocusPicked = ref("");
const queueFocus = computed(() => {
  const refs = queueOrder.value.map((card) => card.ref);
  return refs.includes(queueFocusPicked.value) ? queueFocusPicked.value : (refs[0] ?? "");
});
function queueKey(e: KeyboardEvent): boolean {
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (key === "f" && queueAvailable.value) {
    e.preventDefault();
    viewMode.value = "queue";
    return true;
  }
  if (key === "t") {
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
    const next = key === "ArrowDown" ? Math.min(order.length - 1, index + 1) : Math.max(0, index - 1);
    queueFocusPicked.value = order[next]!.ref;
    document.querySelector(`[data-queue-ref="${CSS.escape(order[next]!.ref)}"]`)?.scrollIntoView({ block: "nearest" });
    return true;
  }
  if (key === "a" && acceptRef.value && !isBusy(acceptRef.value)) {
    e.preventDefault();
    onAction(acceptRef.value, "confirm");
    return true;
  }
  const card = order[index];
  if (!card || isBusy(card.ref)) return false;
  if (key === "Enter" && !(e.target as HTMLElement | null)?.closest("button, a, input, textarea, select")) {
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
  // Esc fecha primeiro o painel aberto (⋯, ordenar, canal); só depois limpa os recortes.
  if (e.key === "Escape" && (moreOpen.value || sortOpen.value || channelOpen.value)) {
    moreOpen.value = false;
    sortOpen.value = false;
    channelOpen.value = false;
    return;
  }
  const el = e.target as HTMLElement | null;
  const typing = !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
  const column = view.value === "board" ? queueColumnForKey(e.key, boardLayout.keys) : null;
  if (column) {
    // Com um diálogo aberto a tecla é do diálogo, não do quadro atrás dele.
    if (typing || rejectRef.value || settleRef.value || dispatchRef.value || courierBackRef.value) return;
    e.preventDefault();
    boardLayout.toggle(column);
    return;
  }
  // A Fila: F e T trocam a visão; na Fila, ↑/↓ andam, Enter faz o gesto do item em
  // foco e A aceita o pedido novo em foco. O R continua sendo "atualizar".
  if (!typing && !rejectRef.value && !settleRef.value && !dispatchRef.value && !courierBackRef.value && queueKey(e)) return;
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
      viewMode.value = view.value === "board" ? (queueAvailable.value ? "queue" : "table") : "board";
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
const rejectDirty = computed(() => rejectRef.value !== null && Boolean(rejectReason.value.trim() || rejectCode.value));
const confirmDiscard = useConfirm();
async function closeReject() {
  if (rejectRef.value && isBusy(rejectRef.value)) return;
  if (rejectDirty.value && !(await confirmDiscard({
    title: "Descartar o motivo digitado?",
    description: "O motivo que você escreveu se perde, e o pedido não é recusado.",
    cancelLabel: "Continuar escrevendo",
  }))) return;
  rejectRef.value = null;
}
onBeforeRouteLeave(() => !rejectDirty.value || confirmDiscard({
  title: "Sair sem recusar o pedido?",
  description: "O motivo que você escreveu se perde, e o pedido não é recusado.",
  confirmLabel: "Descartar e sair",
  cancelLabel: "Continuar escrevendo",
}));
function beforeUnload(event: BeforeUnloadEvent) {
  if (!rejectDirty.value) return;
  event.preventDefault();
  event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload));
const rejectReasonsLoading = ref(false);
const rejectReasonsError = ref("");
const isMarketplaceReject = computed(() => allCards.value.find((c) => c.ref === rejectRef.value)?.channel_ref === "ifood");
const canConfirmReject = computed(() =>
  !rejectReasonsLoading.value && !rejectReasonsError.value && (isMarketplaceReject.value ? rejectReasons.value.some((r) => r.code === rejectCode.value) : rejectReason.value.trim() !== ""),
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
    if (request === rejectReasonsRequest && ref_ === rejectRef.value) rejectReasons.value = result;
  } catch {
    if (request === rejectReasonsRequest && ref_ === rejectRef.value) rejectReasonsError.value = "Não foi possível consultar os motivos. Nenhuma ação foi aplicada.";
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
  const ok = await reject(ref_, rejectReason.value.trim() || "Pedido recusado", rejectCode.value);
  if (ok) rejectRef.value = null;
}

// settle-cash dialog (needs an amount; and, when the courier took change from
// the drawer, how much of it came back — zero included; the server requires it).
const settleRef = ref<string | null>(null);
const cashDrafts = useOrderCashDrafts();
const settleCard = computed(() => allCards.value.find((c) => c.ref === settleRef.value) ?? null);
const settleAction = computed(() => settleCard.value?.actions.find((action) => action.ref === "settle-delivery-cash"));
const settlementDraft = computed(() => {
  const initial = { amount: "", changeBack: settleCard.value?.change_back_pending ? moneyInput(changeBackSuggestionQ(settleCard.value)) : "", equipmentBack: false,
    revision: String(settleAction.value?.payload_schema.base_revision || ""), custody: String(settleAction.value?.confirmation.description || "") };
  return (settleRef.value ? cashDrafts.settlements.value[settleRef.value] : null) ?? initial;
});
const settleAmount = computed({ get: () => settlementDraft.value.amount, set: (v: string) => { settlementDraft.value.amount = v; } });
const settleChangeBack = computed({ get: () => settlementDraft.value.changeBack, set: (v: string) => { settlementDraft.value.changeBack = v; } });
const settleEquipmentBack = computed({ get: () => settlementDraft.value.equipmentBack, set: (v: boolean) => { settlementDraft.value.equipmentBack = v; } });
const settleRevision = computed(() => settlementDraft.value.revision);
const settleCustody = computed(() => settlementDraft.value.custody);
const settleChanged = computed(() => settleRevision.value !== String(settleAction.value?.payload_schema.base_revision || ""));
function reviewSettleCustody() {
  settlementDraft.value.revision = String(settleAction.value?.payload_schema.base_revision || "");
  settlementDraft.value.custody = String(settleAction.value?.confirmation.description || "");
}
const settleAsksChangeBack = computed(() => Boolean(settleCard.value?.change_back_pending));
const settleAsksEquipment = computed(() => Boolean(settleCard.value?.equipment_back_pending));
function openSettle(ref_: string) {
  settleRef.value = ref_;
  cashDrafts.settlement(ref_, settlementDraft.value);
}
async function confirmSettle() {
  const ref_ = settleRef.value;
  if (!ref_) return;
  const changeBack = settleAsksChangeBack.value ? settleChangeBack.value.trim() || "0" : undefined;
  const ok = await settleCash(ref_, settleAmount.value.trim(), changeBack, settleAsksEquipment.value && settleEquipmentBack.value, settleRevision.value);
  if (ok) { cashDrafts.clear("settlement", ref_); settleRef.value = null; }
}

// Saída para entrega: um toque quando não há o que perguntar (a maquininha
// livre é escolhida sozinha); senão, o diálogo (troco, ir junto, qual maquininha,
// ou onde elas estão). Os passos saem em ordem: quem abre a saída primeiro.
const dispatchRef = ref<string | null>(null);
const dispatchCard = computed(() => allCards.value.find((c) => c.ref === dispatchRef.value) ?? null);
async function runDispatch(steps: DispatchStep[]) {
  for (const step of steps) {
    const ok = await advance(step.ref, step.changeOut, step.equipment, step.tripRef);
    if (!ok) return false;
  }
  return true;
}
async function onDispatch(steps: DispatchStep[]) {
  if (await runDispatch(steps)) dispatchRef.value = null;
}

// "Entregador voltou": confirma o que deve estar na mão e fecha a saída inteira.
const courierBackRef = ref<string | null>(null);
const courierBackCard = computed(() => allCards.value.find((c) => c.ref === courierBackRef.value) ?? null);
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
  }
  else if (action === "courier_back") courierBackRef.value = ref_;
  else if (action === "reject") openReject(ref_);
  else if (action === "settle_cash") openSettle(ref_);
  else if (action === "equipment_back") equipmentBack(ref_);
  else if (action === "undo_handoff") undoHandoff(ref_);
  else if (action === "undo_ready") undoReady(ref_);
}

// O interruptor do canal na coluna da Fila (G09): o MESMO diálogo de Canais, com
// período, motivo e a aprovação do gerente; a leitura da Fila se refaz depois.
const menuChannels = computed(() => queue.value?.awareness?.menu_channels ?? []);
const switchRef = ref<string | null>(null);
const switchTarget = computed(() => menuChannels.value.find((row) => row.ref === switchRef.value)?.switch ?? null);
const { switchChannel, isSwitching } = useChannelSwitch((ref_) => menuChannels.value.find((row) => row.ref === ref_)?.switch, () => refresh());
const submitSwitch = (request: Parameters<typeof switchChannel>[1], approval?: Record<string, string>) => switchChannel(switchRef.value!, request, approval);

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
  const stamp = new Date().toISOString().slice(0, 16).replace("T", "-").replace(":", "h");
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
  <main class="flex min-h-0 flex-1 flex-col" :class="exitPostView ? 'h-dvh max-h-dvh' : ''">
    <!-- Cabeçalho de UMA linha (UX-KIT-V2, prévia v4 `gestor-fila4.html`): título, ao vivo,
         busca e poucos controles (som, ordenar, visão, ⋯). Atualizar, exportar, imprimir,
         a seleção em lote e a última leitura útil moram no ⋯; Ciente aparece aqui só
         enquanto há pedido novo esperando. No posto Saída (`gestor-colunas4.html`):
         "Visão: Saída", "Mostrar as 3 colunas" e o som; o resto no ⋯. -->
    <GestorBoardHeader>
      <template #status>
        <!-- No celular o título não se corta: o estado vai por extenso só na falha; o
             resto fica no ponto, na hora e no nome acessível. -->
        <OperatorLiveStatus
          :tone="liveTone"
          :time="readClock"
          :label="isPhone && !error ? '' : error ? 'Atualização falhou' : realtimeView.label"
          :detail="isPhone && !error ? `${realtimeView.label}. ${realtimeView.title}` : realtimeView.title"
        />
      </template>
      <template #search>
        <OperatorSuiteSearch
          ref="searchInput"
          :class="compactHeader ? 'suite:md:w-[15rem]!' : ''"
          :model-value="query"
          screen-label="filtrando o quadro"
          :placeholder="exitPostView ? 'Código ou cliente' : 'Buscar pedido, cliente ou item'"
          aria-label="Buscar por código, cliente ou item (atalho: /)"
          @update:model-value="(v) => (query = v)"
        />
      </template>
      <template v-if="!isPhone" #actions>
        <!-- No posto Saída a faixa da Entrada pulsa e o Ciente fica no ⋯ (a linha da v4
             não tem lugar para ele ao lado da busca, no tablet). -->
        <button
          v-if="attentionPending && !exitPostView && !isPhone"
          type="button"
          class="inline-flex h-control items-center gap-2 rounded-md border border-primary/50 bg-primary/10 px-3 text-sm font-semibold transition hover:bg-primary/15"
          aria-label="Reconhecer aviso de pedido novo"
          @click="acknowledgeAttention"
        >
          <Icon name="lucide:check" class="size-4" />
          Ciente
        </button>
        <!-- a visão deste posto e o caminho de volta às três colunas -->
        <template v-if="view === 'board' && !boardLayout.allOpen.value && !isPhone">
          <span
            class="hidden h-control items-center gap-2 rounded-md border border-primary/40 bg-primary/10 px-3.5 text-sm font-medium lg:inline-flex"
            :title="boardLayout.memoryText.value"
            data-board-view-label
          >
            <Icon name="lucide:panel-left-close" class="size-5 text-primary" aria-hidden="true" />
            <span class="text-muted-foreground">Visão:</span>
            <b class="font-semibold">{{ boardLayout.viewLabel.value.replace(/^Visão:\s*/, "") }}</b>
          </span>
          <button
            type="button"
            class="inline-flex h-control items-center gap-2 rounded-md border border-border bg-card px-4 text-sm font-semibold transition hover:bg-accent"
            title="Mostrar as 3 colunas (atalhos: 1, 2 e 3)"
            data-board-show-all
            @click="boardLayout.showAll()"
          >
            <Icon name="lucide:columns-3" class="size-5" aria-hidden="true" />
            Mostrar as 3 colunas
          </button>
        </template>
        <!-- som de pedido novo (mesmos 3 estados do KDS): ligado / desligado /
             ligado-mas-bloqueado pelo autoplay (ponto âmbar até o 1º gesto). -->
        <button
          v-if="!isPhone"
          type="button"
          class="relative grid size-control place-items-center rounded-md border border-border bg-card transition hover:bg-accent"
          :class="soundOn && soundBlocked ? 'border-warning/50 text-warning' : 'text-foreground'"
          :aria-label="soundOn && soundBlocked ? 'Som bloqueado: toque para ativar' : soundOn ? 'Som de pedido novo ativo' : 'Som de pedido novo desativado'"
          :title="soundOn && soundBlocked ? 'Som bloqueado: toque para ativar' : 'Som de pedido novo'"
          data-sound-toggle
          @click="handleSoundAction"
        >
          <Icon :name="soundOn ? 'lucide:volume-2' : 'lucide:volume-x'" class="size-5" />
          <span v-if="soundOn && soundBlocked" class="absolute -right-1 -top-1 size-2 rounded-full bg-warning" aria-hidden="true" />
        </button>

        <template v-if="!compactHeader && !isPhone">
          <!-- ordenar: na Fila, "Urgência ▾" (tempo contra a meta, chegada, mais recentes);
               no quadro e na tabela, a ordem deles -->
          <UiPopover v-model:open="sortOpen">
            <UiPopoverTrigger as-child>
              <button
                type="button"
                class="inline-flex h-control min-w-control items-center gap-2 rounded-md border border-border bg-card px-3 text-sm font-medium transition hover:bg-accent"
                :title="view === 'queue' ? 'Ordenar a Fila' : 'Ordenar (atalho: s)'"
                data-board-sort
              >
                <Icon name="lucide:arrow-up-down" class="size-4" />
                <span>{{ view === "queue" ? queueSortLabel : sortLabel }}</span>
                <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" aria-hidden="true" />
              </button>
            </UiPopoverTrigger>
            <UiPopoverContent v-if="sortOpen" align="end" :side-offset="6" class="w-64 overflow-hidden p-1" role="menu">
              <template v-if="view === 'queue'">
                <button
                  v-for="opt in QUEUE_SORT_OPTIONS"
                  :key="opt.key"
                  type="button"
                  role="menuitemradio"
                  :aria-checked="queueSort === opt.key"
                  class="flex min-h-control w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm transition hover:bg-accent"
                  @click="pickQueueSort(opt.key)"
                >
                  <span class="flex flex-col"><span>{{ opt.label }}</span><span class="text-xs text-muted-foreground">{{ opt.hint }}</span></span>
                  <Icon v-if="queueSort === opt.key" name="lucide:check" class="size-4 shrink-0 text-primary" />
                </button>
              </template>
              <template v-else>
                <button
                  v-for="opt in SORT_OPTIONS"
                  :key="opt.key"
                  type="button"
                  role="menuitemradio"
                  :aria-checked="sort === opt.key"
                  class="flex min-h-control w-full items-center justify-between px-3 py-1.5 text-left text-sm transition hover:bg-accent"
                  @click="pickSort(opt.key)"
                >
                  {{ opt.label }}
                  <Icon v-if="sort === opt.key" name="lucide:check" class="size-4 text-primary" />
                </button>
              </template>
            </UiPopoverContent>
          </UiPopover>

          <!-- visão (v4): dois segmentos, Fila F | Supervisão T. A Supervisão é a tabela
               densa com seleção em lote; as três colunas (Entrada, Preparo, Saída) moram
               no ⋯ e na tecla V, e o posto Saída abre nelas. -->
          <div class="inline-flex h-control items-center gap-0.5 rounded-md bg-secondary" data-view-switch>
            <button
              v-if="queueAvailable"
              type="button"
              class="inline-flex h-full min-w-control items-center justify-center gap-1.5 rounded-md px-2.5 text-sm font-medium transition"
              :class="view === 'queue' ? 'bg-card font-semibold text-foreground shadow-sm ring-1 ring-border' : 'text-muted-foreground hover:text-foreground'"
              aria-label="Fila: o que precisa de você"
              title="Fila: o que precisa de você (atalho: f)"
              :aria-pressed="view === 'queue'"
              @click="viewMode = 'queue'"
            >
              <Icon name="lucide:list-checks" class="size-4" />
              <span aria-hidden="true">Fila</span>
              <kbd class="ml-0.5 hidden font-mono text-xs text-muted-foreground pointer-fine:xl:inline" aria-hidden="true">F</kbd>
            </button>
            <button
              type="button"
              class="inline-flex h-full min-w-control items-center justify-center gap-1.5 rounded-md px-2.5 text-sm font-medium transition"
              :class="view === 'table' ? 'bg-card font-semibold text-foreground shadow-sm ring-1 ring-border' : 'text-muted-foreground hover:text-foreground'"
              aria-label="Supervisão: tabela densa, seleção em lote"
              title="Supervisão: tabela densa, seleção em lote (atalho: t)"
              :aria-pressed="view === 'table'"
              data-view-supervision
              @click="viewMode = 'table'"
            >
              <Icon name="lucide:table-2" class="size-4" />
              <span aria-hidden="true">Supervisão</span>
              <kbd class="ml-0.5 hidden font-mono text-xs text-muted-foreground pointer-fine:xl:inline" aria-hidden="true">T</kbd>
            </button>
          </div>
        </template>

        <!-- ⋯ da fila (do tablet para cima; no celular ele mora no fim dos recortes). O posto
             Saída (v4 `gestor-colunas`) não tem ⋯: a leitura se atualiza sozinha e o Ciente
             é tocar a faixa da Entrada que pulsa. -->
        <UiPopover v-if="!isPhone && !exitPostView" v-model:open="moreOpen">
          <UiPopoverTrigger as-child>
            <UiIconButton icon="lucide:ellipsis" label="Mais ações da fila" data-board-more />
          </UiPopoverTrigger>
          <UiPopoverContent v-if="moreOpen" align="end" :side-offset="6" class="max-h-[calc(100dvh-5rem)] w-72 overflow-y-auto rounded-lg p-0 shadow-lg">
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
              :full="compactHeader"
              @refresh="refresh()"
              @acknowledge="menuDo(acknowledgeAttention)"
              @select="menuDo(() => (selecting ? stopSelection() : startSelection()))"
              @sort="(key) => menuDo(() => pickSort(key))"
              @view="(mode) => menuDo(() => (viewMode = mode))"
              @sound="menuDo(handleSoundAction)"
              @export="menuDo(exportCsv)"
              @print="menuDo(printQueue)"
            />
          </UiPopoverContent>
        </UiPopover>
      </template>

      <!-- recortes (v4): Todos, o eixo do fluxo (Entrega, Retirada) e o canal num
           seletor só ("+ Canal"). No posto Saída os recortes do fluxo sobem para a
           cabeça da coluna, como na prévia. -->
      <!-- A Saída no celular (v4 `cozinha-celular` (a)) não tem a linha de recortes: a
           barra de cima, as duas abas e a lista. -->
      <template v-if="((allCards.length && !exitPostView) || isPhone) && !(isPhone && phoneExitMode)" #filters>
        <!-- na Fila (v4): "Precisa de você N · Todos N · ● Atrasados N", o recorte do que
             muda o trabalho; no quadro e na tabela, "Todos" tira os recortes. -->
        <template v-if="view === 'queue'">
          <UiFilterChip
            v-for="opt in QUEUE_SCOPES"
            :key="opt.key"
            :active="scope === opt.key"
            :count="scopeCounts[opt.key]"
            :data-queue-scope="opt.key"
            @click="scope = opt.key"
          >
            <template v-if="opt.key === 'late'" #icon>
              <span class="size-2 rounded-full bg-warning" aria-hidden="true" />
            </template>
            <template v-else-if="scope === opt.key" #icon>
              <Icon name="lucide:check" class="size-4 text-primary" />
            </template>
            {{ opt.label }}
          </UiFilterChip>
        </template>
        <UiFilterChip v-else :active="channel === 'all' && fulfillment === 'all'" :count="allCards.length" @click="channel = 'all'; fulfillment = 'all'">
          <template v-if="channel === 'all' && fulfillment === 'all'" #icon>
            <Icon name="lucide:check" class="size-4 text-primary" />
          </template>
          Todos
        </UiFilterChip>
        <span class="mx-1 h-6 w-px shrink-0 bg-border" aria-hidden="true" />
        <UiFilterChip :active="fulfillment === 'delivery'" :count="fulfillment_.delivery" @click="fulfillment = fulfillment === 'delivery' ? 'all' : 'delivery'">
          <template #icon><Icon name="lucide:bike" class="size-4" /></template>
          Entrega
        </UiFilterChip>
        <UiFilterChip :active="fulfillment === 'pickup'" :count="fulfillment_.pickup" @click="fulfillment = fulfillment === 'pickup' ? 'all' : 'pickup'">
          <template #icon><Icon name="lucide:store" class="size-4" /></template>
          Retirada
        </UiFilterChip>
        <!-- o canal: um seletor; o canal escolhido vira chip cheio, com o × de volta -->
        <UiPopover v-if="channels.length" v-model:open="channelOpen">
          <UiPopoverTrigger as-child>
            <button
              type="button"
              class="inline-flex h-control items-center gap-2 rounded-full border px-3 text-sm font-medium transition"
              :class="channel !== 'all' ? 'border-primary bg-primary/10 font-semibold' : 'border-dashed border-border text-muted-foreground hover:bg-accent'"
              data-channel-picker
            >
              <Icon :name="channel !== 'all' ? `lucide:${lucideIcon(allCards.find((c) => c.channel_ref === channel)?.channel_icon || '')}` : 'lucide:plus'" class="size-4" />
              {{ channel !== "all" ? channelLabel(channel) : "Canal" }}
              <span v-if="channel !== 'all'" class="tnum text-muted-foreground">{{ channels.find((o) => o.ref === channel)?.count ?? 0 }}</span>
            </button>
          </UiPopoverTrigger>
          <UiPopoverContent v-if="channelOpen" align="start" :side-offset="6" class="w-56 overflow-hidden p-1" role="menu">
            <button
              type="button"
              role="menuitemradio"
              :aria-checked="channel === 'all'"
              class="flex min-h-control w-full items-center gap-2.5 px-3 text-left text-sm transition hover:bg-accent"
              @click="channel = 'all'; channelOpen = false"
            >
              <Icon name="lucide:layers" class="size-4 text-muted-foreground" />
              <span class="flex-1">Todos os canais</span>
              <Icon v-if="channel === 'all'" name="lucide:check" class="size-4 text-primary" />
            </button>
            <button
              v-for="opt in channels"
              :key="opt.ref"
              type="button"
              role="menuitemradio"
              :aria-checked="channel === opt.ref"
              class="flex min-h-control w-full items-center gap-2.5 px-3 text-left text-sm transition hover:bg-accent"
              @click="channel = opt.ref; channelOpen = false"
            >
              <Icon :name="`lucide:${lucideIcon(allCards.find((c) => c.channel_ref === opt.ref)?.channel_icon || '')}`" class="size-4 text-muted-foreground" />
              <span class="flex-1">{{ opt.label }}</span>
              <span class="tnum text-muted-foreground">{{ opt.count }}</span>
              <Icon v-if="channel === opt.ref" name="lucide:check" class="size-4 text-primary" />
            </button>
          </UiPopoverContent>
        </UiPopover>
        <button
          v-if="channel !== 'all'"
          type="button"
          class="grid size-10 place-items-center rounded-full text-muted-foreground transition hover:bg-accent"
          :aria-label="`Tirar o recorte ${channelLabel(channel)}`"
          @click="channel = 'all'"
        >
          <Icon name="lucide:x" class="size-4" />
        </button>
        <!-- celular: os controles do quadro num painel só ("Filtros" da prévia v3), no começo
             da linha para nunca ficar fora da tela -->
        <span v-if="isPhone" class="order-first">
        <button
          type="button"
          class="inline-flex h-control items-center gap-2 rounded-full border border-border bg-card px-3 text-sm font-semibold"
          aria-haspopup="menu"
          :aria-expanded="moreOpen"
          aria-label="Mais ações da fila"
          data-board-more
          @click="moreOpen = !moreOpen"
        >
          <Icon name="lucide:sliders-horizontal" class="size-4" />
          Filtros
          <span v-if="attentionPending || (soundOn && soundBlocked)" class="size-2 rounded-full bg-warning" aria-hidden="true" />
        </button>
        </span>
      </template>
      <template #below>
        <!-- a loja no iFood: só o SINAL, e só quando muda o que entra na fila. -->
        <ChannelQueueSignal />
      </template>
    </GestorBoardHeader>

    <!-- celular: o painel dos controles sobe do pé, ao alcance do polegar -->
    <UiSheet v-if="isPhone" :open="moreOpen" @update:open="(value) => (moreOpen = value)">
      <UiSheetContent v-if="moreOpen" side="bottom" composition="bare" class="inset-x-2 bottom-2 h-auto max-h-[80dvh] w-auto overflow-y-auto rounded-xl border" data-board-menu-sheet>
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
          @select="menuDo(() => (selecting ? stopSelection() : startSelection()))"
          @sort="(key) => menuDo(() => pickSort(key))"
          @view="(mode) => menuDo(() => (viewMode = mode))"
          @sound="menuDo(handleSoundAction)"
          @export="menuDo(exportCsv)"
          @print="menuDo(printQueue)"
        />
      </UiSheetContent>
    </UiSheet>

    <!-- celular: as colunas viram abas -->
    <UiTabs
      v-if="isPhone && view === 'board' && zones.length"
      :model-value="phoneZone"
      class="shrink-0 print:hidden"
      data-board-zone-tabs
      @update:model-value="pickPhoneZone"
    >
      <UiTabsList class="flex w-full rounded-none border-x-0 border-t-0 bg-card px-2 py-0" aria-label="Colunas do quadro">
        <UiTabsTrigger
          v-for="tab in phoneTabs"
          :key="tab.key"
          :value="tab.key"
          class="h-12 flex-1 gap-1.5 rounded-none text-sm data-[state=active]:shadow-[inset_0_-3px_0_var(--primary)]"
          :data-phone-tab="tab.key"
        >
          {{ tab.title }}
          <span
            class="tnum"
            :class="phoneZone === tab.key && triaged(tab.zone).length ? 'grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1.5 text-xs text-primary-foreground' : ''"
          >{{ triaged(tab.zone).length }}</span>
          <span v-if="phoneExitMode && tab.late" class="size-2 rounded-full bg-warning" :aria-label="`${tab.late} passou da meta`" />
        </UiTabsTrigger>
      </UiTabsList>
    </UiTabs>

    <!-- barra da seleção em lote (o modo ligado) -->
    <div v-if="selecting" class="flex shrink-0 flex-wrap items-center gap-2 border-b bg-primary/10 px-4 py-2 text-sm print:hidden" data-bulk-bar>
      <Icon name="lucide:list-checks" class="size-4 text-primary" />
      <span class="font-semibold">{{ selected.size ? `${selected.size} selecionado${selected.size > 1 ? "s" : ""}` : "Toque nos pedidos para marcar" }}</span>
      <div class="ml-auto flex flex-wrap items-center gap-1.5">
        <button
          v-if="confirmableSel.length"
          type="button"
          class="min-h-action min-w-action inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:cursor-progress disabled:opacity-80"
          :disabled="bulkConfirming"
          :aria-busy="bulkConfirming || undefined"
          @click="bulkConfirm"
        >
          <Icon :name="bulkConfirming ? 'line-md:loading-loop' : 'lucide:check'" class="size-3.5" aria-hidden="true" /> Aceitar {{ confirmableSel.length }}
        </button>
        <button
          v-if="advanceableSel.length"
          type="button"
          class="min-h-control min-w-control inline-flex items-center gap-1.5 rounded-md border bg-card px-2.5 py-1.5 text-xs font-semibold transition hover:bg-accent disabled:cursor-progress disabled:opacity-80"
          :disabled="bulkAdvancing"
          :aria-busy="bulkAdvancing || undefined"
          @click="bulkAdvance"
        >
          <Icon :name="bulkAdvancing ? 'line-md:loading-loop' : 'lucide:arrow-right'" class="size-3.5" aria-hidden="true" /> Avançar {{ advanceableSel.length }}
        </button>
        <button type="button" class="min-h-control min-w-control rounded-md border bg-card px-2.5 py-1.5 text-xs font-medium transition hover:bg-accent" @click="toggleSelectAll">
          {{ allVisibleSelected ? "Desmarcar todos" : "Marcar todos" }}
        </button>
        <button v-if="selected.size" type="button" class="min-h-control min-w-control rounded-md border bg-card px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-accent" @click="clearSelection">
          Limpar
        </button>
        <button type="button" class="min-h-control min-w-control rounded-md border bg-card px-2.5 py-1.5 text-xs font-semibold transition hover:bg-accent" data-bulk-done @click="stopSelection">
          Concluir
        </button>
      </div>
    </div>

    <section ref="queueViewport" class="flex min-h-0 flex-1 flex-col overflow-auto p-3 md:p-4" @scroll.passive="rememberPosition" @click.capture="rememberFocus">
      <!-- puxe para atualizar (celular) -->
      <p
        v-if="isPhone && (pull > 0 || pullRefreshing)"
        class="flex shrink-0 items-center justify-center gap-2 overflow-hidden text-xs text-muted-foreground"
        :style="{ height: `${pullRefreshing ? 40 : pull}px` }"
        aria-live="polite"
        data-pull-refresh
      >
        <Icon name="lucide:refresh-cw" class="size-4" :class="pullRefreshing ? 'motion-safe:animate-spin' : ''" />{{ pullText }}
      </p>
      <p v-if="pending && !zones.length" class="text-sm text-muted-foreground">Carregando…</p>
      <!-- `!stationLocked`: antes do PIN toda leitura volta 403 `station_locked`; quem
           fala nesse estado é a identificação que sobe por cima (app.vue). -->
      <p v-else-if="error && !stationLocked" class="mb-3 rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive dark:text-orange-400" data-queue-error>
        Falha ao atualizar a fila. Mantivemos a última leitura; atualize antes de confirmar ações.
      </p>

      <template v-if="queue">
        <section v-if="negotiationCards.length" class="mb-6 space-y-3" data-ifood-negotiation-orders>
          <h2 class="text-sm font-bold uppercase tracking-wide">Negociações iFood pendentes</h2>
          <p class="text-sm text-muted-foreground">Confira solicitações e prazos, inclusive de pedidos já encerrados.</p>
          <div class="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <OrderCard v-for="card in negotiationCards" :key="`negotiation-${card.ref}`" :card="card" negotiation-only />
          </div>
        </section>
        <!-- no results across all zones for the active filters -->
        <p v-if="hasFilter && !visibleCount" class="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
          Nenhum pedido para os filtros atuais.
          <button type="button" class="min-h-control min-w-control ml-1 font-medium text-primary hover:underline" @click="query = ''; channel = 'all'; fulfillment = 'all'">Limpar filtros</button>
        </p>

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
          @switch="(ref_) => (switchRef = ref_)"
        />

        <!-- Supervisão: o quadro de três colunas -->
        <!-- colunas: a recolhida vira faixa (tocar devolve); a aberta tem alça para
             ajustar a largura com a vizinha. A arrumação é do posto (useBoardLayout). -->
        <div
          v-else-if="view === 'board'"
          class="grid gap-4 lg:[grid-template-columns:var(--board-columns)]"
          :class="exitPostView ? 'min-h-0 flex-1 lg:gap-2 lg:[grid-template-rows:minmax(0,1fr)]' : ''"
          :style="{ '--board-columns': boardLayout.gridTemplate.value }"
          data-board-columns
        >
          <section
            v-for="zone in zones"
            :key="zone.key"
            :ref="(el) => setColumnEl(zone.key, el)"
            class="relative min-h-0 min-w-0 flex-col gap-3"
            :class="isPhone && zone.key !== phoneZone ? 'hidden' : 'flex'"
            :data-zone="zone.key"
            :data-collapsed="(!isPhone && !boardLayout.isOpen(zone.key)) || undefined"
          >
            <QueueColumnStrip
              v-if="!isPhone && !boardLayout.isOpen(zone.key)"
              :title="zone.title"
              :icon="zone.icon"
              :count="triaged(zone).length"
              :late="lateCount(zone)"
              :summary="stripSummary(zone.key, triaged(zone), nowMs).text"
              :pulse="zone.key === 'intake' && attentionPending"
              @open="openColumn(zone.key)"
            />
            <template v-else>
            <!-- cabeça da coluna (v4): nome em versalete, contagem e a frase do que mora
                 aqui; no posto Saída, também os recortes do fluxo e onde a arrumação mora. -->
            <div v-if="!isPhone" class="flex min-h-11 items-center gap-2" :class="wideColumn(zone.key) ? '' : 'border-b border-border pb-2'">
              <Icon v-if="!wideColumn(zone.key)" :name="zone.icon" class="size-4 text-muted-foreground" />
              <h2 class="text-xs uppercase tracking-wider font-semibold">{{ zone.title }}</h2>
              <span class="text-sm tnum text-muted-foreground"><b class="font-semibold text-foreground">{{ triaged(zone).length }}</b><template v-if="wideColumn(zone.key)">{{ triaged(zone).length === 1 ? " pronto ou quase" : " prontos ou quase" }}</template></span>
              <span v-if="wideColumn(zone.key)" class="ml-3 hidden items-center gap-1.5 text-xs text-muted-foreground lg:inline-flex" :title="boardLayout.memoryText.value" data-board-layout-memory>
                <Icon name="lucide:cloud-check" class="size-4" aria-hidden="true" />{{ layoutMemory }}
              </span>
              <span v-else class="ml-auto hidden truncate text-xs text-muted-foreground sm:block" :title="zone.subtitle">{{ zone.subtitle }}</span>
              <template v-if="wideColumn(zone.key)">
                <span class="flex-1" />
                <button
                  v-for="opt in EXIT_FILTERS"
                  :key="opt.key"
                  type="button"
                  class="inline-flex h-11 items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium transition"
                  :class="fulfillment === opt.key ? 'border-primary bg-primary/10 font-semibold' : 'border-border bg-card hover:bg-accent'"
                  :aria-pressed="fulfillment === opt.key"
                  @click="fulfillment = opt.key"
                >
                  <Icon v-if="opt.key !== 'all' || fulfillment === 'all'" :name="opt.icon" class="size-4" :class="fulfillment === opt.key ? 'text-primary' : ''" />
                  {{ opt.label }}
                </button>
              </template>
              <UiIconButton
                v-if="boardLayout.canCollapse(zone.key)"
                class="-mr-2 ml-auto shrink-0 border-transparent !bg-transparent text-muted-foreground sm:ml-0"
                icon="lucide:chevrons-left"
                :label="`Recolher a coluna ${zone.title} (atalho: ${shortcutHint(zone.key)})`"
                data-board-collapse
                @click="boardLayout.toggle(zone.key)"
              />
            </div>

            <div v-if="!triaged(zone).length" class="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border bg-card/60 px-6 py-8 text-center">
              <span class="grid size-11 place-items-center rounded-full bg-success/10 text-success">
                <Icon name="lucide:circle-check" class="size-6" />
              </span>
              <p class="text-sm font-normal text-muted-foreground">{{ zoneEmptyText(zone.key) }}</p>
            </div>

            <!-- celular, a Saída da v4: o mais antigo expandido, o resto em linhas de
                 64px que se deslizam para entregar, e o gesto no polegar. -->
            <PhoneExitList
              v-else-if="isPhone && zone.key === 'expedition'"
              :cards="triaged(zone)"
              :now-ms="nowMs"
              :next-ref="zoneNext(zone)"
              :is-busy="isBusy"
              :action-error="actionError"
              :can-open="canManageOrders"
              @action="onAction"
              @dismiss-error="clearActionError"
            />

            <!-- posto Saída: a grade da v4 (cartões de altura igual, duas linhas que
                 enchem a tela; o excedente vira a faixa "+N esperando"). -->
            <template v-else-if="wideColumn(zone.key)">
              <div
                :ref="setExitGrid"
                class="-m-1 grid min-h-0 flex-1 gap-3 overflow-y-auto p-1 [grid-auto-rows:minmax(min-content,1fr)] [grid-template-columns:repeat(auto-fill,minmax(17rem,1fr))] [grid-template-rows:repeat(2,minmax(min-content,1fr))]"
                data-zone-cards
              >
                <OrderCard
                  v-for="card in exitCards(zone)"
                  :key="card.ref"
                  :card="card"
                  :busy="isBusy(card.ref)"
                  :error="actionError(card.ref)"
                  :selected="isSelected(card.ref)"
                  :selecting="selecting"
                  :next="card.ref === zoneNext(zone)"
                  fill
                  :danfe-printing="danfePrint.isPrinting(card.ref)"
                  :touch="touchCards"
                  :can-open="canManageOrders"
                  @action="(action) => onAction(card.ref, action)"
                  @dismiss-error="clearActionError(card.ref)"
                  @toggle-select="toggleSelect(card.ref)"
                  @toggle-assign="onToggleAssign(card)"
                  @select-mode="startSelection(card.ref)"
                  @print-danfe="danfePrint.printDanfe(card.ref)"
                  @station-ready="(stationRef) => onStationReady(card, stationRef)"
                  @station-recall="(ticketPk) => recallStation(card.ref, ticketPk)"
                  @volumes="(count) => declareVolumes(card.ref, count, 'exit')"
                />
              </div>
              <button
                v-if="exitOverflow(zone).length"
                type="button"
                class="flex min-h-11 shrink-0 flex-wrap items-center justify-center gap-x-2 rounded-lg border border-dashed border-border px-3 text-sm font-medium transition hover:bg-accent"
                data-exit-overflow
                @click="exitShowAll = true"
              >
                <b class="tnum">+{{ exitOverflow(zone).length }}</b>
                <span class="font-normal text-muted-foreground">{{ waitingStripText(exitOverflow(zone)) }} · aparecem aqui quando um destes sair</span>
                <span class="inline-flex items-center gap-1 font-semibold">Ver todos<Icon name="lucide:chevron-right" class="size-4" /></span>
              </button>
              <button
                v-else-if="exitShowAll && triaged(zone).length > exitCapacity"
                type="button"
                class="flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm font-medium text-muted-foreground transition hover:bg-accent"
                @click="exitShowAll = false"
              >
                Mostrar só os {{ exitCapacity }} primeiros
              </button>
            </template>

            <div v-else class="flex flex-col gap-3" data-zone-cards>
              <!-- no celular, deslizar o cartão para a esquerda revela Atender e Recusar -->
              <SwipeReveal
                v-for="card in triaged(zone)"
                :key="card.ref"
                :actions="isPhone ? swipeActions(card) : []"
                :label="`Pedido ${splitRef(card.ref).code}`"
                @pick="(key) => onSwipe(card, key)"
              >
              <OrderCard
                :card="card"
                :swipe-reject="isPhone"
                :busy="isBusy(card.ref)"
                :error="actionError(card.ref)"
                :selected="isSelected(card.ref)"
                :selecting="selecting"
                :next="card.ref === zoneNext(zone)"
                :danfe-printing="danfePrint.isPrinting(card.ref)"
                :touch="touchCards"
                :can-open="canManageOrders"
                @action="(action) => onAction(card.ref, action)"
                @dismiss-error="clearActionError(card.ref)"
                @toggle-select="toggleSelect(card.ref)"
                @toggle-assign="onToggleAssign(card)"
                @select-mode="startSelection(card.ref)"
                @print-danfe="danfePrint.printDanfe(card.ref)"
                @station-ready="(stationRef) => onStationReady(card, stationRef)"
                @station-recall="(ticketPk) => recallStation(card.ref, ticketPk)"
                @volumes="(count) => declareVolumes(card.ref, count, zone.key === 'expedition' ? 'exit' : 'orders')"
              />
              </SwipeReveal>
              <p v-if="isPhone && triaged(zone).length" class="flex items-center justify-center gap-1.5 py-1 text-xs text-muted-foreground" data-swipe-hint>
                <Icon name="lucide:hand" class="size-4" />{{ !canManageOrders ? "Puxe para atualizar" : zone.key === "intake" ? "Deslize para Atender ou Recusar · puxe para atualizar" : "Deslize para Atender · puxe para atualizar" }}
              </p>
            </div>
            <QueueColumnResizeHandle
              v-if="!isPhone && boardLayout.nextOpen(zone.key)"
              :label="`Ajustar a largura de ${zone.title} e ${zoneTitles[boardLayout.nextOpen(zone.key) || ''] || ''}`"
              @start="onResizeStart(zone.key)"
              @drag="boardLayout.dragResize"
              @end="boardLayout.endResize"
            />
            </template>
          </section>
        </div>

        <!-- dense table view (power-user) -->
        <div v-else class="overflow-x-auto rounded-lg border bg-card">
          <table class="w-full border-collapse text-sm">
            <thead>
              <tr class="text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground [&>th]:sticky [&>th]:top-0 [&>th]:z-20 [&>th]:border-b [&>th]:bg-card">
                <th class="w-9 px-3 py-2">
                  <button
                    type="button"
                    class="grid size-control place-items-center rounded transition hover:bg-accent"
                    :aria-label="allVisibleSelected ? 'Desmarcar todos' : 'Selecionar todos'"
                    :aria-pressed="allVisibleSelected"
                    @click="toggleSelectAll"
                  >
                    <span class="grid size-4 place-items-center rounded border" :class="allVisibleSelected ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/40 hover:border-primary'">
                      <Icon v-if="allVisibleSelected" name="lucide:check" class="size-3" />
                    </span>
                  </button>
                </th>
                <th class="px-3 py-2">Código</th>
                <th class="px-3 py-2">Etapa</th>
                <th class="px-3 py-2">Canal</th>
                <th class="px-3 py-2">Cliente</th>
                <th class="hidden px-3 py-2 lg:table-cell">Itens</th>
                <th class="px-3 py-2 text-right">Total</th>
                <th class="px-3 py-2 text-right">Tempo</th>
                <th class="px-3 py-2 text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="row in tableRows" :key="row.card.ref">
              <tr class="transition hover:bg-accent/40" :class="[actionError(row.card.ref) ? '' : 'border-b last:border-0', isSelected(row.card.ref) ? 'bg-primary/5' : '']">
                <td class="px-3 py-2">
                  <button
                    type="button"
                    class="grid size-control place-items-center rounded transition hover:bg-accent"
                    :aria-label="isSelected(row.card.ref) ? 'Desmarcar pedido' : 'Selecionar pedido'"
                    :aria-pressed="isSelected(row.card.ref)"
                    @click="toggleSelect(row.card.ref)"
                  >
                    <span class="grid size-4 place-items-center rounded border" :class="isSelected(row.card.ref) ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/40 hover:border-primary'">
                      <Icon v-if="isSelected(row.card.ref)" name="lucide:check" class="size-3" />
                    </span>
                  </button>
                </td>
                <td class="px-3 py-2">
                  <NuxtLink v-if="canManageOrders" :to="`/${row.card.ref}`" class="inline-flex min-h-control min-w-control items-center font-bold tabular-nums hover:underline" :aria-label="`Abrir pedido ${row.card.ref}`">
                    {{ splitRef(row.card.ref).code }}
                  </NuxtLink>
                  <span v-else class="inline-flex min-h-control items-center font-bold tabular-nums">{{ splitRef(row.card.ref).code }}</span>
                </td>
                <td class="px-3 py-2">
                  <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="toneBadge(statusTone(row.card.status))">
                    {{ row.card.status_label }}
                  </span>
                </td>
                <td class="px-3 py-2">
                  <span class="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <Icon :name="`lucide:${lucideIcon(row.card.channel_icon)}`" class="size-3.5" />
                    {{ channelLabel(row.card.channel_ref) }}
                  </span>
                </td>
                <td class="max-w-40 px-3 py-2">
                  <span class="block truncate">{{ row.card.customer_name }}</span>
                  <span v-if="row.card.assigned_operator" class="mt-0.5 inline-flex items-center gap-1 text-xs text-primary">
                    <Icon name="lucide:user-check" class="size-3" />{{ row.card.assigned_operator }}
                  </span>
                </td>
                <td class="hidden max-w-56 truncate px-3 py-2 text-muted-foreground lg:table-cell">{{ row.card.items_summary }}</td>
                <td class="whitespace-nowrap px-3 py-2 text-right font-semibold tabular-nums">{{ row.card.total_display }}</td>
                <td class="px-3 py-2 text-right">
                  <span class="inline-flex items-center rounded border px-1.5 py-0.5 text-xs tabular-nums" :class="timerChip(timerTone(row.card.timer_class))">
                    {{ elapsedLabel(row.card.elapsed_seconds) }}
                  </span>
                </td>
                <td class="px-3 py-2">
                  <div class="flex items-center justify-end gap-1">
                    <button
                      type="button"
                      :disabled="isBusy(row.card.ref)"
                      class="grid size-control place-items-center rounded border transition disabled:opacity-50"
                      :class="row.card.assigned_operator ? 'border-primary/40 bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'"
                      :aria-label="row.card.assigned_operator ? `Atendido por ${row.card.assigned_operator}. Toque para liberar` : 'Atender'"
                      :title="row.card.assigned_operator ? `${row.card.assigned_operator}: toque para liberar` : 'Atender'"
                      @click="onToggleAssign(row.card)"
                    >
                      <Icon :name="row.card.assigned_operator ? 'lucide:user-check' : 'lucide:user-plus'" class="size-3.5" />
                    </button>
                    <button
                      v-for="a in cardAffordances(row.card)"
                      :key="a.ref"
                      type="button"
                      :disabled="isBusy(row.card.ref) || a.disabled"
                      class="grid size-control place-items-center rounded border transition disabled:opacity-50"
                      :class="a.priority === 'primary' ? 'min-h-action min-w-action border-transparent bg-primary text-primary-foreground hover:bg-primary/90' : a.priority === 'danger' ? 'border-destructive/40 text-destructive hover:bg-destructive/10 dark:text-orange-300' : 'hover:bg-accent'"
                      :aria-label="a.label"
                      :title="a.reason || a.label"
                      @click="onAction(row.card.ref, a.ref)"
                    >
                      <Icon :name="a.icon" class="size-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
              <!-- action error sub-row: the backend's specific reason, inline -->
              <tr v-if="actionError(row.card.ref)" class="border-b last:border-0">
                <td colspan="9" class="px-3 pb-2">
                  <div class="flex items-start gap-1.5 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1.5 text-xs text-destructive dark:text-orange-300" role="alert">
                    <Icon name="lucide:alert-triangle" class="mt-px size-3.5 shrink-0" />
                    <span class="min-w-0 flex-1">{{ actionError(row.card.ref) }}</span>
                    <button type="button" class="min-h-control min-w-control shrink-0 rounded p-0.5 transition hover:bg-destructive/20" aria-label="Dispensar aviso" @click="clearActionError(row.card.ref)">
                      <Icon name="lucide:x" class="size-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
              </template>
            </tbody>
          </table>
        </div>

        <!-- Agendados: pedidos confirmados para datas futuras, fora das colunas
             do dia. Agrupados pela data combinada; no dia, o despertador devolve
             o pedido ao fluxo normal do board. -->
        <section v-if="preordersCount" class="mt-6" data-preorders-section>
          <div class="flex items-center gap-2 border-b pb-2">
            <Icon name="lucide:calendar-clock" class="size-4 text-muted-foreground" />
            <h2 class="text-sm font-bold uppercase tracking-wide">Agendados</h2>
            <span class="grid min-w-5 place-items-center rounded-full bg-muted px-1.5 text-xs font-bold tabular-nums">{{ preordersCount }}</span>
            <span class="ml-auto hidden text-right text-xs text-muted-foreground sm:block">Confirmados para os próximos dias</span>
          </div>
          <div class="mt-3 grid gap-4 lg:grid-cols-3">
            <div v-for="group in triagedPreorders" :key="group.date" class="flex min-w-0 flex-col gap-3">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{{ group.label }}</h3>
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
    <UiDialog :open="rejectRef != null" @update:open="(v) => { if (!v) closeReject() }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Recusar pedido {{ rejectRef }}</UiDialogTitle>
          <UiDialogDescription>
            {{ isMarketplaceReject ? "Escolha o motivo que o iFood exige. Ele é enviado ao iFood." : "Informe o motivo. O cliente recebe o aviso com ele." }}
          </UiDialogDescription>
        </UiDialogHeader>
        <p v-if="rejectReasonsLoading" class="text-sm text-muted-foreground">Carregando motivos do iFood…</p>
        <div v-else-if="rejectReasonsError" role="alert" class="text-sm text-destructive">
          <p>{{ rejectReasonsError }}</p>
          <button type="button" class="min-h-control min-w-control underline" @click="loadRejectReasons">Consultar novamente</button>
        </div>
        <p v-else-if="isMarketplaceReject && !rejectReasons.length" class="text-sm">O iFood não oferece motivos de cancelamento neste momento.</p>
        <!-- Marketplace (iFood): coded reason picker from the provider's live list -->
        <UiNativeSelect
          v-else-if="isMarketplaceReject"
          v-model="rejectCode"
          class="w-full"
          aria-label="Motivo do cancelamento (iFood)"
          @change="onRejectCodeChange"
        >
          <option value="" disabled>Selecione o motivo…</option>
          <option v-for="r in rejectReasons" :key="r.code" :value="r.code">{{ r.description }}</option>
        </UiNativeSelect>
        <!-- Other channels: free-text reason -->
        <textarea
          v-else
          v-model="rejectReason"
          rows="3"
          placeholder="Motivo da recusa…"
          class="min-h-control w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Motivo da recusa"
        />
        <UiDialogFooter>
          <button type="button" class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" :disabled="Boolean(rejectRef && isBusy(rejectRef))" @click="closeReject">Voltar</button>
          <button
            type="button"
            :disabled="!canConfirmReject || Boolean(rejectRef && isBusy(rejectRef))"
            class="min-h-action min-w-action rounded-md border border-transparent bg-destructive px-3 py-2 text-sm font-semibold text-white transition hover:bg-destructive/90 disabled:opacity-50"
            @click="confirmReject"
          >
            Recusar pedido
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- o interruptor do canal (coluna da Fila): o mesmo diálogo de Canais -->
    <ChannelSwitchDialog
      :open="Boolean(switchTarget)"
      :sw="switchTarget"
      :managers="queue?.awareness?.managers ?? []"
      :viewer-name="queue?.awareness?.viewer_name ?? ''"
      :busy="Boolean(switchRef && isSwitching(switchRef))"
      :submit="submitSwitch"
      @update:open="(value: boolean) => { if (!value) switchRef = null; }"
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
    <UiDialog :open="settleRef != null" @update:open="(v) => { if (!v) settleRef = null }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>{{ settleCard?.fulfillment_type === "pickup" ? "Pagamento na retirada" : "Acerto da entrega" }}</UiDialogTitle>
          <UiDialogDescription>{{ settleCard?.fulfillment_type === "pickup" ? "Valor recebido na retirada" : "Valor recebido na entrega" }} ({{ settleRef }}). Em branco usa o total de {{ settleCard?.total_display }}. {{ settleCustody }}</UiDialogDescription>
        </UiDialogHeader>
        <p v-if="settleChanged" role="alert" class="text-sm text-destructive">O pedido ou turno mudou. Confira o contexto atual: {{ settleAction?.confirmation.description }}
          <button type="button" class="min-h-control min-w-control underline" @click="reviewSettleCustody">Conferir e manter os valores digitados</button>
        </p>
        <input
          v-model="settleAmount"
          type="text"
          inputmode="decimal"
          placeholder="Ex.: 15,00"
          class="min-h-control w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Valor recebido"
        />
        <!-- o entregador levou troco da gaveta: quanto voltou (zero vale) -->
        <label v-if="settleAsksChangeBack" class="min-h-control flex flex-col gap-1 text-sm" data-change-back>
          <span class="text-muted-foreground">{{ settleCard?.change_label }}. Quanto voltou?</span>
          <input
            v-model="settleChangeBack"
            type="text"
            inputmode="decimal"
            placeholder="0,00"
            class="min-h-control w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
            aria-label="Troco que voltou"
          />
        </label>
        <UiCheckbox
          v-if="settleAsksEquipment"
          v-model="settleEquipmentBack"
          :label="`${settleCard?.equipment_label}. Voltou junto`"
          data-equipment-back
        />
        <UiDialogFooter>
          <button type="button" class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="settleRef = null">Voltar</button>
          <button type="button" class="min-h-action min-w-action rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50" :disabled="settleChanged || !settleAction?.enabled || (settleRef ? isBusy(settleRef) : false)" @click="confirmSettle">
            Confirmar acerto
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
