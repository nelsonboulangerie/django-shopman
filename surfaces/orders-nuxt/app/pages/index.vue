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
import type { CancellationReason } from "~/composables/useOrdersBoard";
import { BOARD_COLUMNS_QUERY, BOARD_ZONE_KEYS, useBoardLayout } from "~/composables/useBoardLayout";
import { queueColumnForKey } from "../../../operator-kit/app/presentation/queueColumns";

const { readMetadata, queue, zones, deviceAgent, preorders, realtime, pending, error, refresh, isBusy, actionError, clearActionError, confirm, advance, reject, fetchCancellationReasons, settleCash, equipmentBack, courierBack, undoHandoff, undoReady, assign, unassign, confirmMany, advanceMany, markStationReady, recallStation, soundOn, soundBlocked, attentionPending, toggleSound, activateAttentionSound, acknowledgeAttention } = useOrdersBoard();
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
const { query, channel, fulfillment, sort, viewMode, selected } = context;
// O recorte vive na URL; seleção/posição/foco ficam só na sessão e pessoa atual.
context.readLocation(route.query);
watch(() => route.query, (params) => { if (route.path === "/") context.readLocation(params); });
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
function pickSort(key: SortKey) {
  sort.value = key;
  sortOpen.value = false;
}

// ── colunas ajustáveis e recolhíveis, lembradas por posto (SUITE-UX §16) ──
// O tablet do passe fica só com a Saída: é o mesmo quadro, com Entrada e Preparo
// recolhidas numa faixa. Nenhuma ação muda; muda só o que cabe na tela.
const zoneTitles = computed<Record<string, string>>(() => Object.fromEntries(zones.value.map((z) => [z.key, z.title])));
const boardLayout = useBoardLayout(() => zoneTitles.value);
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
  // No celular as colunas são abas: "Saída" abre a aba da Saída; "Pedidos", a da vez.
  pickedZone.value = wanted === "expedition" ? "expedition" : null;
  const { [BOARD_COLUMNS_QUERY]: _applied, ...rest } = route.query;
  void router.replace({ path: route.path, query: rest });
}
onMounted(applyColumnsQuery);
watch(() => route.query[BOARD_COLUMNS_QUERY], () => { if (route.path === "/") applyColumnsQuery(); });
// O posto de saída é tablet de toque: todo alvo do cartão sobe para 48 px.
const touchCards = computed(() => viewMode.value === "board" && boardLayout.exitPost.value);
const exitPostView = computed(() => viewMode.value === "board" && boardLayout.exitPost.value && !isPhone.value);
// Tablet em pé (e o posto Saída): a linha de cima fica com o essencial; ordenar e a
// visão entram no ⋯, para o cabeçalho não quebrar em duas linhas.
// Só depois de montar: o servidor não sabe a largura, e classe divergente na hidratação
// não é corrigida pelo Vue (o campo ficaria com a largura do servidor).
const isNarrow = useMediaQuery("(max-width: 1023.98px)");
const mounted = ref(false);
onMounted(() => { mounted.value = true; });
const compactHeader = computed(() => mounted.value && (exitPostView.value || (isNarrow.value && !isPhone.value)));

// O rail conta o que o quadro vê: pedidos novos em Pedidos e o que está na Saída, e
// acende "Saída" quando o posto está só com ela. Fora do quadro os selos somem.
const rail = useGestorRail();
watch(
  () => ({
    exitPost: isPhone.value ? phoneZone.value === "expedition" : boardLayout.exitPost.value,
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
function lateCount(zone: ZoneView): number {
  return triaged(zone).filter((card) => timerTone(card.timer_class) === "late").length;
}
const shortcutHint = (key: string) => String(BOARD_ZONE_KEYS.indexOf(key as (typeof BOARD_ZONE_KEYS)[number]) + 1);

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
  const column = viewMode.value === "board" ? queueColumnForKey(e.key, boardLayout.keys) : null;
  if (column) {
    // Com um diálogo aberto a tecla é do diálogo, não do quadro atrás dele.
    if (typing || rejectRef.value || settleRef.value || dispatchRef.value || courierBackRef.value) return;
    e.preventDefault();
    boardLayout.toggle(column);
    return;
  }
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
      viewMode.value = viewMode.value === "board" ? "table" : "board";
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
    <OperatorPageHeader title="Pedidos" :eyebrow="exitPostView && boardLayout.station.value ? 'Posto Saída · este dispositivo' : ''">
      <template #status>
        <OperatorLiveStatus
          :tone="liveTone"
          :time="readClock"
          :label="error ? 'Atualização falhou' : realtimeView.label"
          :detail="realtimeView.title"
        />
      </template>
      <template #search>
        <UiSearchInput
          ref="searchInput"
          :class="compactHeader ? 'suite:md:w-[15rem]!' : ''"
          :model-value="query"
          :placeholder="exitPostView ? 'Código ou cliente' : 'Buscar pedido, cliente ou item'"
          aria-label="Buscar por código, cliente ou item (atalho: /)"
          shortcut="/"
          @update:model-value="(v) => (query = v)"
        />
      </template>
      <template #phone-actions>
        <GestorPhoneBells />
      </template>
      <template v-if="!isPhone" #actions>
        <!-- No posto Saída a faixa da Entrada pulsa e o Ciente fica no ⋯ (a linha da v4
             não tem lugar para ele ao lado da busca, no tablet). -->
        <button
          v-if="attentionPending && !exitPostView && !isPhone"
          type="button"
          class="inline-flex h-control items-center gap-2 rounded-md border border-primary/50 bg-primary/10 px-3 op-label font-semibold transition hover:bg-primary/15"
          aria-label="Reconhecer aviso de pedido novo"
          @click="acknowledgeAttention"
        >
          <Icon name="lucide:check" class="size-4" />
          Ciente
        </button>
        <!-- a visão deste posto e o caminho de volta às três colunas -->
        <template v-if="viewMode === 'board' && !boardLayout.allOpen.value && !isPhone">
          <span
            class="hidden h-control items-center gap-2 rounded-md border border-primary/40 bg-primary/10 px-3.5 op-label lg:inline-flex"
            :title="boardLayout.memoryText.value"
            data-board-view-label
          >
            <Icon name="lucide:panel-left-close" class="size-5 text-primary" aria-hidden="true" />
            <span class="text-muted-foreground">Visão:</span>
            <b class="font-semibold">{{ boardLayout.viewLabel.value.replace(/^Visão:\s*/, "") }}</b>
          </span>
          <button
            type="button"
            class="inline-flex h-control items-center gap-2 rounded-md border border-border bg-card px-4 op-label font-semibold transition hover:bg-accent"
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
          <!-- ordenar -->
          <div class="relative">
            <button
              type="button"
              class="inline-flex h-control min-w-control items-center gap-2 rounded-md border border-border bg-card px-3 op-label transition hover:bg-accent"
              aria-haspopup="menu"
              :aria-expanded="sortOpen"
              title="Ordenar (atalho: s)"
              @click="sortOpen = !sortOpen"
            >
              <Icon name="lucide:arrow-up-down" class="size-4" />
              <span>{{ sortLabel }}</span>
              <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" aria-hidden="true" />
            </button>
            <div v-if="sortOpen" class="fixed inset-0 z-40" @click="sortOpen = false" />
            <div v-if="sortOpen" class="absolute right-0 z-50 mt-1 w-48 overflow-hidden rounded-md border bg-card py-1 shadow-lg" role="menu">
              <button
                v-for="opt in SORT_OPTIONS"
                :key="opt.key"
                type="button"
                role="menuitemradio"
                :aria-checked="sort === opt.key"
                class="flex min-h-control w-full items-center justify-between px-3 py-1.5 text-left op-body transition hover:bg-accent"
                @click="pickSort(opt.key)"
              >
                {{ opt.label }}
                <Icon v-if="sort === opt.key" name="lucide:check" class="size-4 text-primary" />
              </button>
            </div>
          </div>

          <!-- visão: quadro ou tabela (o alternador segmentado da v4, com a tecla) -->
          <!-- os dois botões têm 44px cada (alvo da casa): o trilho não tem respiro
               interno, e o ativo se destaca pelo cartão com contorno. -->
          <div class="inline-flex h-control items-center gap-0.5 rounded-md bg-secondary">
            <button
              type="button"
              class="inline-flex h-full min-w-control items-center justify-center gap-1.5 rounded-md px-2.5 op-label transition"
              :class="viewMode === 'board' ? 'bg-card font-semibold text-foreground shadow-sm ring-1 ring-border' : 'text-muted-foreground hover:text-foreground'"
              aria-label="Ver em colunas"
              title="Colunas (atalho: v)"
              :aria-pressed="viewMode === 'board'"
              @click="viewMode = 'board'"
            >
              <Icon name="lucide:columns-3" class="size-4" />
              <span class="hidden xl:inline" aria-hidden="true">Quadro</span>
              <kbd v-if="viewMode !== 'board'" class="ml-0.5 hidden font-mono op-micro text-muted-foreground pointer-fine:xl:inline" aria-hidden="true">V</kbd>
            </button>
            <button
              type="button"
              class="inline-flex h-full min-w-control items-center justify-center gap-1.5 rounded-md px-2.5 op-label transition"
              :class="viewMode === 'table' ? 'bg-card font-semibold text-foreground shadow-sm ring-1 ring-border' : 'text-muted-foreground hover:text-foreground'"
              aria-label="Ver em tabela"
              title="Tabela (atalho: v)"
              :aria-pressed="viewMode === 'table'"
              @click="viewMode = 'table'"
            >
              <Icon name="lucide:table-2" class="size-4" />
              <span class="hidden xl:inline" aria-hidden="true">Tabela</span>
              <kbd v-if="viewMode !== 'table'" class="ml-0.5 hidden font-mono op-micro text-muted-foreground pointer-fine:xl:inline" aria-hidden="true">V</kbd>
            </button>
          </div>
        </template>

        <!-- ⋯ da fila (do tablet para cima; no celular ele mora no fim dos recortes) -->
        <div v-if="!isPhone" class="relative">
          <UiIconButton
            icon="lucide:ellipsis"
            label="Mais ações da fila"
            aria-haspopup="menu"
            :aria-expanded="moreOpen"
            data-board-more
            @click="moreOpen = !moreOpen"
          />
          <div v-if="moreOpen" class="fixed inset-0 z-40" @click="moreOpen = false" />
          <div v-if="moreOpen" class="absolute right-0 z-50 mt-1 max-h-[calc(100dvh-5rem)] w-72 overflow-y-auto rounded-lg border bg-popover text-popover-foreground shadow-lg">
            <BoardMenu
              :metadata="readMetadata"
              :failed="Boolean(error)"
              :pending="pending"
              :sort="sort"
              :view-mode="viewMode"
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
          </div>
        </div>
      </template>

      <!-- recortes (v4): Todos, o eixo do fluxo (Entrega, Retirada) e o canal num
           seletor só ("+ Canal"). No posto Saída os recortes do fluxo sobem para a
           cabeça da coluna, como na prévia. -->
      <template v-if="(allCards.length && !exitPostView) || isPhone" #filters>
        <UiFilterChip :active="channel === 'all' && fulfillment === 'all'" :count="allCards.length" @click="channel = 'all'; fulfillment = 'all'">
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
        <div v-if="channels.length" class="relative">
          <button
            type="button"
            class="inline-flex h-10 items-center gap-2 rounded-full border px-3 op-label transition"
            :class="channel !== 'all' ? 'border-primary bg-primary/10 font-semibold' : 'border-dashed border-border text-muted-foreground hover:bg-accent'"
            aria-haspopup="menu"
            :aria-expanded="channelOpen"
            data-channel-picker
            @click="channelOpen = !channelOpen"
          >
            <Icon :name="channel !== 'all' ? `lucide:${lucideIcon(allCards.find((c) => c.channel_ref === channel)?.channel_icon || '')}` : 'lucide:plus'" class="size-4" />
            {{ channel !== "all" ? channelLabel(channel) : "Canal" }}
            <span v-if="channel !== 'all'" class="tnum text-muted-foreground">{{ channels.find((o) => o.ref === channel)?.count ?? 0 }}</span>
          </button>
          <div v-if="channelOpen" class="fixed inset-0 z-40" @click="channelOpen = false" />
          <div v-if="channelOpen" class="absolute left-0 z-50 mt-1 w-56 overflow-hidden rounded-md border bg-popover py-1 text-popover-foreground shadow-lg" role="menu">
            <button
              type="button"
              role="menuitemradio"
              :aria-checked="channel === 'all'"
              class="flex min-h-control w-full items-center gap-2.5 px-3 text-left op-body transition hover:bg-accent"
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
              class="flex min-h-control w-full items-center gap-2.5 px-3 text-left op-body transition hover:bg-accent"
              @click="channel = opt.ref; channelOpen = false"
            >
              <Icon :name="`lucide:${lucideIcon(allCards.find((c) => c.channel_ref === opt.ref)?.channel_icon || '')}`" class="size-4 text-muted-foreground" />
              <span class="flex-1">{{ opt.label }}</span>
              <span class="tnum text-muted-foreground">{{ opt.count }}</span>
              <Icon v-if="channel === opt.ref" name="lucide:check" class="size-4 text-primary" />
            </button>
          </div>
        </div>
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
          class="inline-flex h-10 items-center gap-2 rounded-full border border-border bg-card px-3 op-label font-semibold"
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
    </OperatorPageHeader>

    <!-- celular: o painel dos controles sobe do pé, ao alcance do polegar -->
    <template v-if="isPhone && moreOpen">
      <div class="fixed inset-0 z-40 bg-black/30" @click="moreOpen = false" />
      <div class="fixed inset-x-2 bottom-2 z-50 max-h-[80dvh] overflow-y-auto rounded-xl border bg-popover text-popover-foreground shadow-xl" data-board-menu-sheet>
        <BoardMenu
          :metadata="readMetadata"
          :failed="Boolean(error)"
          :pending="pending"
          :sort="sort"
          :view-mode="viewMode"
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
      </div>
    </template>

    <!-- celular: as colunas viram abas -->
    <div
      v-if="isPhone && viewMode === 'board' && zones.length"
      class="flex shrink-0 border-b border-border bg-card px-2 print:hidden"
      role="tablist"
      aria-label="Colunas do quadro"
      data-board-zone-tabs
    >
      <button
        v-for="zone in zones"
        :key="zone.key"
        type="button"
        role="tab"
        :aria-selected="phoneZone === zone.key"
        class="flex h-12 flex-1 items-center justify-center gap-1.5 op-body"
        :class="phoneZone === zone.key ? 'font-semibold text-foreground shadow-[inset_0_-3px_0_var(--primary)]' : 'text-muted-foreground'"
        @click="pickedZone = zone.key"
      >
        {{ zone.title }}
        <span
          class="tnum"
          :class="phoneZone === zone.key && triaged(zone).length ? 'grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1.5 text-xs text-primary-foreground' : ''"
        >{{ triaged(zone).length }}</span>
      </button>
    </div>

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

        <!-- board view (clean, default) -->
        <!-- colunas: a recolhida vira faixa (tocar devolve); a aberta tem alça para
             ajustar a largura com a vizinha. A arrumação é do posto (useBoardLayout). -->
        <div
          v-else-if="viewMode === 'board'"
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
              @open="boardLayout.open(zone.key)"
            />
            <template v-else>
            <!-- cabeça da coluna (v4): nome em versalete, contagem e a frase do que mora
                 aqui; no posto Saída, também os recortes do fluxo e onde a arrumação mora. -->
            <div v-if="!isPhone" class="flex min-h-11 items-center gap-2" :class="wideColumn(zone.key) ? '' : 'border-b border-border pb-2'">
              <Icon v-if="!wideColumn(zone.key)" :name="zone.icon" class="size-4 text-muted-foreground" />
              <h2 class="op-eyebrow">{{ zone.title }}</h2>
              <span class="op-label tnum text-muted-foreground"><b class="font-semibold text-foreground">{{ triaged(zone).length }}</b><template v-if="wideColumn(zone.key)">{{ triaged(zone).length === 1 ? " pedido" : " pedidos" }}</template></span>
              <span v-if="wideColumn(zone.key)" class="ml-3 hidden items-center gap-1.5 op-micro text-muted-foreground xl:inline-flex" :title="boardLayout.memoryText.value" data-board-layout-memory>
                <Icon name="lucide:cloud-check" class="size-4" aria-hidden="true" />{{ layoutMemory }}
              </span>
              <span v-else class="ml-auto hidden truncate op-micro text-muted-foreground sm:block" :title="zone.subtitle">{{ zone.subtitle }}</span>
              <template v-if="wideColumn(zone.key)">
                <span class="flex-1" />
                <button
                  v-for="opt in EXIT_FILTERS"
                  :key="opt.key"
                  type="button"
                  class="inline-flex h-11 items-center gap-1.5 rounded-full border px-3.5 op-label transition"
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
              <p class="op-label font-normal text-muted-foreground">{{ zoneEmptyText(zone.key) }}</p>
            </div>

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
                />
              </div>
              <button
                v-if="exitOverflow(zone).length"
                type="button"
                class="flex min-h-11 shrink-0 flex-wrap items-center justify-center gap-x-2 rounded-lg border border-dashed border-border px-3 op-label transition hover:bg-accent"
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
                class="flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-dashed border-border op-label text-muted-foreground transition hover:bg-accent"
                @click="exitShowAll = false"
              >
                Mostrar só os {{ exitCapacity }} primeiros
              </button>
            </template>

            <div v-else class="flex flex-col gap-3" data-zone-cards>
              <OrderCard
                v-for="card in triaged(zone)"
                :key="card.ref"
                :card="card"
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
              />
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
        <label v-if="settleAsksEquipment" class="min-h-control flex items-center gap-2 text-sm" data-equipment-back>
          <input v-model="settleEquipmentBack" type="checkbox" />
          <span>{{ settleCard?.equipment_label }}. Voltou junto</span>
        </label>
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
