<script setup lang="ts">
import { useAlertDismissals } from "../../../operator-kit/app/composables/useAlertDismissals";
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
  EXIT_SELECTION_LABEL,
  exitGesture,
  flattenZones,
  fulfillmentCounts,
  lucideIcon,
  negotiationZoneView,
  nextOutRef,
  nextSort,
  oneTapDispatch,
  realtimeIndicator,
  resolveShortcut,
  rideChoices,
  rowsToCsv,
  SORT_OPTIONS,
  splitRef,
  statusTone,
  timerTone,
  triageCards,
} from "~/presentation/board";
import { moneyInput } from "../../../operator-kit/app/presentation/custody";
import type { OrderCardProjection } from "~/types/orders";
import { ORDERS_QUEUE_TRAIL } from "~/presentation/orderTrails";
import { boardStrip, type BoardStrip } from "~/presentation/boardStrip";
import { provideOrderTicketPrinter } from "~/composables/useOrderTicketPrint";
import type { OperatorActionBarAction } from "../../../operator-kit/app/presentation/actionBar";
import type { OperatorBulkItem } from "../../../operator-kit/app/presentation/bulkBar";
import type { ActiveFilters, FilterDimension } from "../../../operator-kit/app/types/filters";
import type { OperatorSwipeAction } from "../../../operator-kit/app/components/OperatorSwipeRow.vue";
import {
  BOARD_COLUMNS_QUERY,
  BOARD_ZONE_KEYS,
  useBoardLayout,
} from "~/composables/useBoardLayout";
import {
  QUEUE_FOCUS,
  QUEUE_SORT_OPTIONS,
  liveAge,
  queueGesture,
  queueItems,
  queueCode,
  queueScopeCounts,
  type QueueScope,
  type QueueSort,
} from "~/presentation/queue";
import { queueColumnForKey } from "../../../operator-kit/app/presentation/queueColumns";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

const {
  readMetadata,
  queue,
  cancelReasons,
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
  settleCash,
  equipmentBack,
  courierBack,
  undoHandoff,
  undoReady,
  dismissCourierReminder,
  retryIFoodAccept,
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
  attentionRef,
  toggleSound,
  activateAttentionSound,
  acknowledgeAttention,
} = useOrdersBoard();
// Quem só expede (SUITE-UX §15) opera a Saída daqui; o detalhe do pedido é de quem gerencia.
const { canManageOrders } = useGestorAccess();

// A DANFE da sacola sai sozinha pelo servidor; o card imprime ou reimprime à mão.
const danfePrint = useDanfePrint(deviceAgent, refresh);
// A Via Pedido no ⋯ de cada pedido (cartão e Fila), pela impressora desta estação.
provideOrderTicketPrinter(deviceAgent);

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
// Conferência das sacolas (P1-13): o leitor do posto Saída bipa o QR da Via
// Pedido em qualquer ponto do quadro. Só avisa; a saída segue no cartão.
const volumeCheck = useVolumeCheck({
  enabled: () => !stationLocked.value,
  onChecked: () => refresh(),
});
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
// As entregas prontas que podem ir juntas numa corrida, como cards (ordem da fila).
// A corrida junta pedido pronto e em preparo: o card de cada um vem da Saída
// ou do Preparo.
const rideCandidates = computed(() =>
  rideChoices(queue.value?.ride_candidates ?? [], [
    ...(queue.value?.expedition_delivery ?? []),
    ...(queue.value?.prep ?? []),
  ]),
);
const allCards = computed<OrderCardProjection[]>(() =>
  zones.value.flatMap((z) => z.cards),
);
const channels = computed(() => channelOptions(allCards.value));
const fulfillment_ = computed(() => fulfillmentCounts(allCards.value));
const sortLabel = computed(
  () => SORT_OPTIONS.find((o) => o.key === sort.value)?.label ?? "Chegada",
);
const boardOrderHint = computed(() => {
  const by: Record<string, string> = {
    arrival: "Por chegada",
    urgency: "Mais urgente primeiro",
    recent: "Mais recentes primeiro",
  };
  return `${by[sort.value] ?? sortLabel.value}, em cada coluna`;
});
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
  const cards = triageCards(zone.cards, {
    query: query.value,
    channel: channel.value,
    sort: sort.value,
    fulfillment: fulfillment.value,
  });
  return view.value === "board" ? inBoardScope(cards) : cards;
}
// Os recortes do Quadro (D, prévia `gestor-d`): Todos · Precisa de você · Atrasados,
// com a régua da Fila, em cada coluna. O Quadro abre em Todos; a Fila tem o seu.
const boardScope = ref<QueueScope>("all");
function inBoardScope(cards: OrderCardProjection[]): OrderCardProjection[] {
  if (boardScope.value === "all") return cards;
  const keep = new Set(
    queueItems(cards, nowMs.value, { scope: boardScope.value }).map((item) => item.card.ref),
  );
  return cards.filter((card) => keep.has(card.ref));
}
// flat rows for the dense table view, honouring the same triage + zone order.
const tableRows = computed(() =>
  flattenZones(zones.value.map((z) => ({ ...z, cards: triaged(z) }))),
);
// A Tabela (dono, 07/10/2026): linhas integradas num card branco; a linha principal tem
// só o gesto do momento e o ⋯; o resto (detalhes e todas as ações) abre na própria
// linha. A coluna de seleção fica sempre: marcar uma linha liga a barra de lote.
// A seleção e a seta de abrir são da `OperatorTable`; Pedido é a chave (fixada) e
// Situação, Itens e Tempo são de apoio (somem no celular, onde o cartão aberto diz tudo).
const supervisionColumns = [
  { id: "order", header: "Pedido", enableHiding: false },
  { id: "stage", header: "Situação", meta: { supporting: true } },
  { id: "items", header: "Itens", meta: { supporting: true } },
  { id: "total", header: "Total" },
  { id: "elapsed", header: "Tempo", meta: { supporting: true } },
  { id: "actions", header: "Próximo passo", enableHiding: false },
];
type SupervisionRow = (typeof tableRows.value)[number];
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
/** O gesto do momento numa linha da Tabela: o primário (ou o travado, com o cadeado). */
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
// A seleção da Tabela é a mesma da barra de lote: a tabela marca, o Set guarda.
const supervisionRowSelection = computed<Record<string, boolean>>({
  get: () => Object.fromEntries([...selected.value].map((ref_) => [ref_, true])),
  set: (next) => {
    selected.value = new Set(Object.keys(next).filter((ref_) => next[ref_]));
  },
});
function toggleSelect(ref_: string) {
  const next = new Set(selected.value);
  if (next.has(ref_)) next.delete(ref_);
  else next.add(ref_);
  selected.value = next;
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
// A barra de seleção (OperatorBulkBar): a ação principal (Aceitar) e o resto no mesmo
// peso; o × sai do modo de seleção. O recorte vai por extenso ("em Entrega · iFood").
const bulkScope = computed(() =>
  [
    fulfillment.value !== "all"
      ? FULFILLMENT_LABELS[fulfillment.value] ?? ""
      : "",
    channel.value !== "all"
      ? channelLabel(channel.value)
      : "",
  ]
    .filter(Boolean)
    .join(" · "),
);
const bulkItems = computed<OperatorBulkItem[]>(() => [
  ...(confirmableSel.value.length
    ? [{
        label: `Aceitar ${confirmableSel.value.length}`,
        icon: "i-lucide-check",
        primary: true,
        loading: bulkConfirming.value,
        disabled: bulkConfirming.value,
        onSelect: () => void bulkConfirm(),
      }]
    : []),
  ...(advanceableSel.value.length
    ? [{
        label: `Avançar ${advanceableSel.value.length}`,
        icon: "i-lucide-arrow-right",
        loading: bulkAdvancing.value,
        disabled: bulkAdvancing.value,
        onSelect: () => void bulkAdvance(),
      }]
    : []),
  {
    label: allVisibleSelected.value ? "Desmarcar todos" : "Marcar todos",
    icon: allVisibleSelected.value ? "i-lucide-square" : "i-lucide-check-check",
    onSelect: toggleSelectAll,
  },
]);
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

// A régua da suíte (`useScreen` do kit): mesa no servidor e na hidratação, a largura
// real depois. Decidir a árvore com `useMediaQuery` cru fazia o celular hidratar outra
// árvore na carga direta: a Fila ficava no esqueleto para sempre.
// Ela responde "mesa" até montar, então a barra do topo e a toolbar NÃO decidem por ela
// (o celular desenhava a barra da mesa encavalada até hidratar): `phone-actions`,
// `actions-from="md"` e as classes `max-lg:`/`md:` fazem isso pelo CSS. Daqui só o que
// muda a árvore depois de montar: as colunas que viram abas, a Fila só do `lg` e o
// puxar para atualizar.
const screen = useScreen();
// Celular (abaixo de md): as colunas viram abas.
const isPhone = screen.belowMd;
const hydrated = screen.ready;
// Tablet em pé: três colunas de ~240 px cortavam selo e prazo do cartão. Abaixo do
// lg, com mais de uma coluna aberta, o quadro usa as abas do celular.
const isNarrowTablet = computed(
  () => screen.belowLg.value && !screen.belowMd.value,
);
// A aba "Negociação" (só quando há): o pedido do iFood já fora das etapas com
// negociação aberta. É ação pendente do gerente; a Fila do desktop o mostra, e no
// quadro em abas ele ficava sem lugar. A Saída do celular é do posto, não do gerente.
const negotiationZone = computed(() =>
  queue.value ? negotiationZoneView(queue.value) : null,
);
const tabZones = computed<ZoneView[]>(() => [
  ...zones.value,
  ...(negotiationZone.value ? [negotiationZone.value] : []),
]);
// Celular (prévia v3 `orders-phone3.html`): Entrada, Preparo e Saída viram abas, uma
// coluna por vez, com a contagem na aba. Abre na que tem pedido novo; sem pedido novo,
// na primeira que tem pedido. O toque do operador manda dali em diante.
const pickedZone = ref<string | null>(null);
const phoneZone = computed(() => {
  if (pickedZone.value && tabZones.value.some((z) => z.key === pickedZone.value))
    return pickedZone.value;
  const intake = zones.value.find((z) => z.key === "intake");
  if (intake && triaged(intake).length) return intake.key;
  return (
    tabZones.value.find((z) => triaged(z).length)?.key ??
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
  const byKey = new Map(tabZones.value.map((zone) => [zone.key, zone]));
  const tabs = phoneExitMode.value
    ? [
        { key: "expedition", title: "Prontos para sair" },
        { key: "prep", title: "Em preparo" },
      ]
    : [
        // Em abas, as três etapas aparecem sempre: recolher é gesto das colunas, e a
        // aba do Preparo não pode sumir do tablet porque ele abre recolhido na mesa.
        ...zones.value,
        ...(negotiationZone.value ? [negotiationZone.value] : []),
      ].map((zone) => ({
        key: zone.key,
        title: zone.title,
      }));
  return tabs.flatMap((tab) => {
    const zone = byKey.get(tab.key as ZoneView["key"]);
    return zone ? [{ ...tab, zone, late: lateCount(zone) }] : [];
  });
});
// A aba "Negociação" tem ícone, e no celular fica só com ele e a contagem (o nome
// segue para o leitor de tela): com o nome inteiro, a quarta aba passava da largura.
const phoneTabItems = computed(() =>
  phoneTabs.value.map((tab) => ({
    ...tab,
    value: tab.key,
    label: tab.title,
    icon: tab.key === "negotiation" ? "i-lucide-message-square-warning" : undefined,
    iconOnlyOnPhone: tab.key === "negotiation",
    count: triaged(tab.zone).length,
  })),
);
// Puxe para atualizar (celular) e o aviso dos gestos no fim da lista.
const {
  pull,
  refreshing: pullRefreshing,
  label: pullText,
} = usePullToRefresh(queueViewport, () => refresh(), isPhone);
// Deslizar o cartão para a esquerda (G17): Atender (quem gerencia) e Recusar (pedido novo).
function swipeActions(card: OrderCardProjection): OperatorSwipeAction[] {
  const actions: OperatorSwipeAction[] = [];
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
// As tiras das colunas recolhidas, presas à coluna aberta seguinte (ou, no fim, à
// última): a ordem Entrada · Preparo · Saída não muda quando uma recolhe.
const boardStrips = computed(() => {
  const out: Record<string, { before: BoardStrip[]; after: BoardStrip[] }> = {};
  let pending: BoardStrip[] = [];
  let last = "";
  for (const zone of zones.value) {
    if (boardLayout.isOpen(zone.key)) {
      out[zone.key] = { before: pending, after: [] };
      pending = [];
      last = zone.key;
    } else pending.push(boardStrip(zone, triaged(zone), nowMs.value));
  }
  if (last && pending.length) out[last]!.after = pending;
  return out;
});
const boardAsTabs = computed(
  () =>
    isPhone.value || (isNarrowTablet.value && desktopZones.value.length > 1),
);
const phoneZones = computed(() =>
  tabZones.value.filter((zone) => zone.key === phoneZone.value),
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
// Abriu ou recolheu uma coluna: a largura guardada no navegador para esse conjunto
// sai antes de o Splitter montar, e as abertas voltam a dividir o espaço por igual.
const boardSplitter = ref<{ reset: () => void } | null>(null);
watch(
  boardSplitterPersistenceKey,
  () => boardSplitter.value?.reset(),
  { flush: "pre" },
);
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
// A Fila "Precisa de você" (V4-G4) segue no desktop e no tablet deitado; a casa é o
// Quadro. O celular e
// o tablet em pé seguem com as colunas em abas, e o posto Saída com a Saída larga: lá a
// escolha "Fila" vira o Quadro. Antes de montar (SSR), vale a escolha guardada.
const queueAvailable = computed(
  () => !boardLayout.exitPost.value && !screen.belowLg.value,
);
const view = computed(() =>
  viewMode.value === "queue" && !queueAvailable.value
    ? "board"
    : viewMode.value,
);
// Três modos de ver o MESMO trabalho, num controle só (dono, 13/11/2026: "mantermos
// os dois modos, acionáveis por um toggle", para decidir no uso e fundir depois):
// Fila (urgência, um pedido por linha), Quadro (as três colunas, a do Preparo
// recolhida) e Tabela (densa, com seleção em lote). Nenhum gesto muda de modo a modo.
const viewTabs = computed(() => [
  ...(queueAvailable.value
    ? [{ value: "queue", label: "Fila" }]
    : []),
  { value: "board", label: "Quadro" },
  { value: "table", label: "Tabela" },
]);
function pickView(value: string | number) {
  const next = String(value);
  if (next === "queue" || next === "board" || next === "table")
    viewMode.value = next;
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
const compactHeader = computed(
  () =>
    screen.ready.value &&
    (exitPostView.value || (screen.belowXl.value && !isPhone.value)),
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

// O nome do recebimento no recorte ativo ("Recebimento: Entrega") e no escopo da seleção.
const FULFILLMENT_LABELS: Record<string, string> = { delivery: "Entrega", pickup: "Retirada" };
const channelLabel = (ref: string) => channels.value.find((option) => option.ref === ref)?.label ?? ref;
const nowMs = useNowTick(() => queue.value?.intake[0]?.server_now_iso ?? "");
function zoneNext(zone: ZoneView): string {
  return zone.key === "expedition" ? nextOutRef(triaged(zone)) : "";
}
// A Saída do celular: o ato do "Próximo" ao alcance do polegar, na ação da base da
// suíte (`OperatorActionBar`, no rodapé do painel, depois da área que rola). É o mesmo
// botão largo do cartão e o mesmo deslize à direita, por outro caminho: o mesmo
// `onAction`. Com a seleção ligada, a base é da barra de seleção.
const exitBaseAction = computed<OperatorActionBarAction | null>(() => {
  if (!isPhone.value || view.value !== "board" || selecting.value) return null;
  const zone = zones.value.find((z) => z.key === "expedition");
  if (!zone || phoneZone.value !== "expedition") return null;
  const nextRef = zoneNext(zone);
  const card = triaged(zone).find((c) => c.ref === nextRef);
  const gesture = card ? exitGesture(card) : null;
  if (!card || !gesture) return null;
  return {
    label: gesture.label,
    icon: "i-lucide-hand-platter",
    loading: isBusy(card.ref),
    onSelect: () => {
      if (!isBusy(card.ref)) onAction(card.ref, gesture.action);
    },
  };
});
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
// A trilha do anterior/próximo do pedido (fase 2, `OperatorRecordNav`): a ordem que
// esta tela mostra, com o recorte (escopo, busca, canal, ordenação). Na Fila, todos
// do escopo, não só os em foco: "3 de 18" conta o que o escopo tem.
const { remember: rememberTrail } = useRecordTrail(ORDERS_QUEUE_TRAIL);
const trailRefs = computed(() =>
  (view.value === "queue"
    ? queueItems(queueCards.value, nowMs.value, {
        scope: scope.value,
        sort: queueSort.value,
      }).map((item) => item.card.ref)
    : tableRows.value.map((row) => row.card.ref)
  ).join("\n"),
);
watch(
  trailRefs,
  (refs) =>
    rememberTrail(refs ? refs.split("\n") : [], {
      from: route.fullPath,
      label: "Pedidos",
    }),
  { immediate: true },
);
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
    key: option.key,
    label: option.label,
    count: scopeCounts.value[option.key],
  })),
);
const boardScopeCounts = computed(() =>
  queueScopeCounts(
    zones.value.flatMap((zone) => zone.cards),
    nowMs.value,
  ),
);
const boardScopeTabs = computed(() =>
  (["all", "attention", "late"] as const).map((key) => ({
    key,
    label: QUEUE_SCOPES.find((option) => option.key === key)!.label,
    count: boardScopeCounts.value[key],
  })),
);
function pickBoardScope(value: string | number) {
  if (value === "attention" || value === "all" || value === "late")
    boardScope.value = value;
}
// O que a Saída do sistema fez sozinho e ainda se desfaz: a faixa abaixo do cabeçalho.
const systemUndoLines = computed(() =>
  (queue.value?.awareness?.system_actions ?? []).filter(
    (line) => Boolean(line.undo_action) && Date.parse(line.undo_until_iso) > nowMs.value,
  ),
);
const boardDesk = computed(() => view.value === "board" && !boardAsTabs.value);
const showSystemBand = computed(() => boardDesk.value && systemUndoLines.value.length > 0);
function pickScope(value: string | number) {
  if (value === "attention" || value === "all" || value === "late")
    scope.value = value;
}
function pickFulfillment(value: string | number) {
  if (value === "all" || value === "delivery" || value === "pickup")
    fulfillment.value = value;
}
// O filtro único da suíte (dono, 04/11/2026): o recebimento e o canal como campos de
// escolha única, e os favoritos da pessoa. É o ÚNICO lugar desses recortes, na mesa e no
// celular: não há abas nem seletor de canal paralelos.
const panelDimensions = computed<FilterDimension[]>(() => [
  {
    id: "fulfillment",
    label: "Recebimento",
    type: "single-select",
    options: [
      { value: "delivery", label: "Entrega", count: fulfillment_.value.delivery },
      { value: "pickup", label: "Retirada", count: fulfillment_.value.pickup },
    ],
  },
  {
    id: "channel",
    label: "Canal",
    type: "single-select",
    options: channels.value.map((option) => ({ value: option.ref, label: option.label, count: option.count })),
  },
]);
const panelFilters = computed<ActiveFilters>({
  get: () => ({
    ...(fulfillment.value !== "all" ? { fulfillment: [fulfillment.value] } : {}),
    ...(channel.value !== "all" ? { channel: [channel.value] } : {}),
  }),
  set: (next) => {
    pickFulfillment(next.fulfillment?.[0] ?? "all");
    channel.value = next.channel?.[0] ?? "all";
  },
});
// As ações da fila no celular, em dados para o kit: o "Visto" (e o som bloqueado)
// disputam a vaga de ícone com a Busca e vencem enquanto valem; o resto vai para o ⋯.
// Declaradas sempre (`phone-actions`): o kit as mostra só abaixo de `sm`, pelo CSS, e o
// servidor já desenha a barra do celular (sem o flash da mesa antes de montar).
const phoneHeaderActions = computed(() => {
  return [
    ...(attentionPending.value && !exitPostView.value
      ? [{ label: "Visto", icon: "i-lucide-check", priority: 1, onSelect: () => acknowledgeAttention() }]
      : []),
    {
      label:
        soundOn.value && soundBlocked.value
          ? "Som bloqueado: ativar"
          : soundOn.value
            ? "Som ligado: desligar"
            : "Som desligado: ligar",
      icon: soundOn.value && !soundBlocked.value ? "i-lucide-volume-2" : "i-lucide-volume-x",
      ...(soundOn.value && soundBlocked.value ? { priority: 2 } : {}),
      onSelect: () => handleSoundAction(),
    },
    { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
    {
      label: selecting.value ? EXIT_SELECTION_LABEL : "Selecionar pedidos",
      icon: "i-lucide-list-checks",
      onSelect: () => (selecting.value ? stopSelection() : startSelection()),
    },
    { label: "Exportar CSV", icon: "i-lucide-download", onSelect: () => exportCsv() },
    { label: "Imprimir fila", icon: "i-lucide-printer", onSelect: () => printQueue() },
  ];
});
// Os recortes ativos (chips removíveis abaixo da linha e o número no "Filtros").
const activeFilters = computed(() => [
  ...(fulfillment.value !== "all"
    ? [{
        key: "fulfillment",
        label: `Recebimento: ${FULFILLMENT_LABELS[fulfillment.value] ?? fulfillment.value}`,
        remove: () => pickFulfillment("all"),
      }]
    : []),
  ...(channel.value !== "all"
    ? [{
        key: "channel",
        label: `Canal: ${channelLabel(channel.value)}`,
        remove: () => (channel.value = "all"),
      }]
    : []),
]);
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

// reject dialog: o MESMO `OrderReasonDialog` do detalhe (beta 06/11: o quadro tinha
// um diálogo próprio, com texto livre). Uma lista de motivos em qualquer canal; no
// iFood o diálogo esconde o que o iFood não oferece.
const rejectRef = ref<string | null>(null);
// O diálogo diz quando há motivo escolhido ou texto; ele mesmo pede confirmação ao
// fechar, e a página guarda só a saída por rota e por recarga.
const rejectDirty = ref(false);
const confirmDiscard = useConfirm();
function closeReject() {
  if (rejectRef.value && isBusy(rejectRef.value)) return;
  rejectRef.value = null;
  rejectDirty.value = false;
}
onBeforeRouteLeave(
  () =>
    !rejectDirty.value ||
    confirmDiscard({
      title: "Sair sem recusar o pedido?",
      description:
        "O motivo que você escolheu se perde, e o pedido não é recusado.",
      confirmLabel: "Descartar e sair",
      cancelLabel: "Continuar escolhendo",
    }),
);
function beforeUnload(event: BeforeUnloadEvent) {
  if (!rejectDirty.value) return;
  event.preventDefault();
  event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload));
const isMarketplaceReject = computed(
  () =>
    allCards.value.find((c) => c.ref === rejectRef.value)?.channel_ref ===
    "ifood",
);
function openReject(ref_: string) {
  rejectRef.value = ref_;
}
async function confirmReject(payload: { reasonKey: string; internalNote: string }) {
  const ref_ = rejectRef.value;
  if (!ref_ || isBusy(ref_)) return;
  if (await reject(ref_, payload)) closeReject();
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

function onAdvanceAction(ref_: string) {
  const card = allCards.value.find((c) => c.ref === ref_);
  if (card?.next_status !== "dispatched") advance(ref_);
  else {
    const steps = oneTapDispatch(card, allCards.value);
    if (steps) runDispatch(steps);
    else dispatchRef.value = card.ref;
  }
}

function onAction(ref_: string, action: AffordanceRef) {
  if (action === "confirm") confirm(ref_);
  else if (action === "advance") onAdvanceAction(ref_);
  else if (action === "courier_back") courierBackRef.value = ref_;
  else if (action === "reject") openReject(ref_);
  else if (action === "settle_cash") openSettle(ref_);
  else if (action === "equipment_back") equipmentBack(ref_);
  else if (action === "undo_handoff") undoHandoff(ref_);
  else if (action === "undo_ready") undoReady(ref_);
  else if (action === "dismiss_courier_reminder")
    void dismissCourierReminder(ref_);
  else if (action === "ifood_accept_retry") retryIFoodAccept(ref_);
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
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
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
// A linha do chão no celular (modelo de navegação, 31/10/2026): o ⋮ dela leva as MESMAS
// ações do ⋯ do celular (som, atualizar, selecionar, exportar, imprimir).
// O aviso não é só de pedido novo: toca para o pedido que acabou de ter algo a fazer, em
// qualquer zona. A pílula diz qual é, com o mesmo status que o cartão mostra (a zona
// mentia: um pedido já na rua aparecia como "pronto para sair"), e Ver leva à zona dele.
const attention = computed(() => {
  const zone = zones.value.find((z) => z.cards.some((c) => c.ref === attentionRef.value));
  const card = zone?.cards.find((c) => c.ref === attentionRef.value);
  return {
    zone: zone?.key ?? "intake",
    code: card ? queueCode(card) : "",
    what: card?.status_label || "Pedido para tratar",
  };
});
// O navegador só deixa tocar som depois do primeiro toque na tela, e qualquer toque já
// liga. Em vez de "Som bloqueado" pendurado no aviso, a tela pede o toque uma vez.
const startDismissed = ref(false);
function startTap() {
  startDismissed.value = true;
  handleSoundAction();
}
// Ver: abre a zona do pedido. Na Saída, fica nela se o pedido é da Saída ou do preparo;
// senão sai do posto e abre Pedidos (o selo muda junto).
function seeAttention() {
  const zone = attention.value.zone;
  if (phoneExitMode.value && zone !== "expedition" && zone !== "prep") phoneExitMode.value = false;
  pickPhoneZone(zone);
}
// O X da pílula dispensa o aviso só nesta montagem (a regra do kit, `useAlertDismissals`):
// o próximo pedido que pedir atenção traz a pílula de volta. Visto continua sendo o "eu vi,
// pode parar de avisar".
const notices = useAlertDismissals();
// "Falha ao atualizar a fila" fecha e volta na próxima leitura que falhar: cada falha nova
// (outro erro) é outra chave.
const queueFailures = ref(0);
watch(error, (now, before) => {
  if (now && now !== before) queueFailures.value += 1;
});
// O ⋮ da linha do chão: as ações da fila e, em grupos próprios, Ordenar e Ver como (não
// são filtro: ficam fora do painel). No celular a Fila não existe: Quadro ou Tabela.
const compactOptions = computed(() => [
  phoneHeaderActions.value.map(({ priority: _p, ...item }) => item),
  ...(phoneExitMode.value
    ? []
    : [
        [
          { type: "label" as const, label: "Ordenar" },
          ...sortMenuItems.value,
        ],
        [
          { type: "label" as const, label: "Ver como" },
          ...(
            [
              { key: "board", label: "Quadro", icon: "i-lucide-columns-3" },
              { key: "table", label: "Tabela", icon: "i-lucide-table" },
            ] as const
          ).map((option) => ({
            label: option.label,
            icon: view.value === option.key ? "i-lucide-check" : option.icon,
            onSelect: () => (viewMode.value = option.key),
          })),
        ],
      ]),
]);
const compactTotal = computed(() => zones.value.reduce((n, z) => n + z.cards.length, 0));
const compactFilterLabel = computed(() => activeFilters.value.map((f) => f.label).join(', '));
function compactClear() {
  query.value = "";
  channel.value = "all";
  fulfillment.value = "all";
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-compact-page>
    <!-- Cabeçalho de UMA linha (UX-KIT-V2, prévia v4 `gestor-fila4.html`): título, ao vivo,
         busca e poucos controles (som, ordenar, visão, ⋯). Atualizar, exportar, imprimir,
         a seleção em lote e a última leitura útil moram no ⋯; Visto aparece aqui só
         enquanto há pedido novo esperando. No posto Saída (`gestor-colunas4.html`):
         "Visão: Saída", "Mostrar as 3 colunas" e o som; o resto no ⋯. -->
    <OperatorCompactBar
      title="Pedidos"
      :tone="liveTone"
      :time="readClock"
      :conn-label="error ? 'Atualização falhou' : realtimeView.label"
      :query="query"
      search-button-label="Buscar por código, cliente ou item"
      :filter-active="channel !== 'all' || fulfillment !== 'all'"
      :filter-label="compactFilterLabel"
      :summary="visibleCount + ' de ' + compactTotal + ' pedidos no quadro.'"
      :options="compactOptions"
      @clear="compactClear"
    >
      <!-- O filtro único da suíte (dono, 04/11/2026): o ícone na linha, antes da busca, com
           o número no canto, como o sino. Ordenar e Ver como moram no ⋮. -->
      <template v-if="!phoneExitMode" #filter-panel>
        <OperatorFilterPanel
          v-model="panelFilters"
          :dimensions="panelDimensions"
          trigger="icon"
          :chips="false"
          surface="orders"
          screen="queue"
          data-queue-filters-compact
        />
      </template>
    </OperatorCompactBar>
    <!-- Sem conexão segue EXPLÍCITO (cor + texto), não só o chip do selo. Com a
         leitura falhada o conteúdo já diz "Falha ao atualizar a fila"; aqui não repete. -->
    <p v-if="liveTone === 'off' && !error" class="flex items-center gap-2 border-b border-default bg-error/10 px-3 py-2 text-sm text-error md:hidden" role="status" data-compact-offline>
      <NuxtIcon name="i-lucide-wifi-off" class="size-4 shrink-0" /><span>Sem conexão.<template v-if="readClock"> Última leitura às {{ readClock }}.</template></span>
    </p>
    <!-- O aviso no polegar, sem empurrar a fila: qual pedido, o status do cartão dele, Ver
         e Visto. Na Saída fica acima do "Entregar", a ação do momento ali. Sobe pela altura da
         barra de baixo do shell (`--operator-quick-bar-inset`, do kit): nunca a cobre. -->
    <div v-if="attentionPending && !exitPostView && notices.isOpen(`attention:${attentionRef}`)" :class="phoneExitMode ? 'bottom-[calc(var(--operator-quick-bar-inset,0px)+6rem)]' : 'bottom-[calc(var(--operator-quick-bar-inset,0px)+1rem)]'" class="fixed inset-x-3 z-40 md:hidden" role="status" data-attention-pill>
      <div class="flex items-center gap-2 rounded-2xl bg-inverted py-1.5 pl-4 pr-1.5 text-inverted shadow-lg">
        <NuxtIcon name="i-lucide-bell-ring" class="size-5 shrink-0" />
        <p class="min-w-0 flex-1 leading-tight"><strong class="block truncate">{{ attention.code || attention.what }}</strong><span v-if="attention.code" class="block truncate text-xs opacity-80">{{ attention.what }}</span></p>
        <NuxtButton label="Ver" color="neutral" variant="ghost" class="min-h-11 text-inverted" data-attention-see @click="seeAttention" />
        <NuxtButton icon="i-lucide-check" label="Visto" color="neutral" variant="outline" class="min-h-11" data-attention-seen @click="acknowledgeAttention" />
        <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square class="size-11 justify-center text-inverted" aria-label="Fechar o aviso" data-attention-close @click="notices.close(`attention:${attentionRef}`)" />
      </div>
    </div>
    <!-- O som pede um toque do navegador uma vez; a tela pede, ao abrir (celular). Qualquer
         toque já libera o som (o kit escuta o primeiro gesto); o botão é a porta para quem
         chega pelo teclado. -->
    <NuxtModal
      :open="isPhone && soundOn && soundBlocked && !startDismissed"
      fullscreen
      :close="false"
      title="Toque para começar"
      description="O som dos avisos de pedido liga junto."
      data-sound-start
      @update:open="(v) => { if (!v) startTap(); }"
    >
      <template #content>
        <div class="flex h-full flex-col items-center justify-center gap-4 p-6 text-center" @pointerdown="startTap">
          <p class="text-xl font-semibold text-highlighted">Toque para começar</p>
          <p class="text-muted">O som dos avisos de pedido liga junto.</p>
          <NuxtButton label="Começar" class="min-h-11" data-sound-start-button @click="startTap" />
        </div>
      </template>
    </NuxtModal>
    <OperatorPageHeader
      title="Pedidos"
      :filters-wrap="false"
      :phone-actions="phoneHeaderActions"
      actions-from="md"
      actions-label="Mais ações da fila"
      :active-filters="activeFilters"
    >
      <template #status>
        <!-- O texto visível é do selo (a hora, a cadência, "Última leitura às…",
             "Sem conexão"); o rótulo do estado e o detalhe vão ao nome acessível. -->
        <OperatorLiveStatus
          :tone="liveTone"
          :time="readClock"
          :label="error ? 'Atualização falhou' : realtimeView.label"
          :short-label="realtimeView.shortLabel"
          :detail="realtimeView.title"
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
      <!-- Os controles da mesa (do `md` para cima) escolhidos pelo CSS, não pela régua
           do JS: ela responde "mesa" até montar, e o celular desenhava esta linha
           encavalada sobre o título até a hidratação terminar. -->
      <template #actions>
        <!-- a visão deste posto e o caminho de volta às três colunas -->
        <template
          v-if="view === 'board' && boardAsTabs && !boardLayout.allOpen.value"
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
        <!-- Uma corrida da TaOn para várias entregas prontas: some com menos de duas. -->
        <CourierRideMenu
          v-if="!(view === 'board' && !boardAsTabs && boardLayout.isOpen('expedition'))"
          :choices="rideCandidates"
          @done="refresh()"
        />
        <!-- Onde está a maquininha: some quando todas estão na loja (no Quadro, mora na
             linha de baixo). -->
        <EquipmentOutMenu
          v-if="!boardDesk"
          :items="queue?.equipment_out ?? []"
          :is-busy="isBusy"
          @back="equipmentBack"
        />
        <!-- O som de pedido novo e o "Visto" que o cala formam um grupo só: o Visto
             aparece enquanto há pedido novo tocando e, reconhecido, some, deixando o
             botão do som sozinho. No posto Saída o Visto fica no ⋯. O som tem os
             mesmos 3 estados do KDS: ligado, desligado e ligado-mas-bloqueado pelo
             autoplay (ponto âmbar até o 1º gesto). -->
        <NuxtFieldGroup data-sound-group>
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
            label="Visto"
            color="neutral"
            variant="outline"
            aria-label="Visto: parar o som de pedido novo"
            @click="acknowledgeAttention"
          />
        </NuxtFieldGroup>
        <template v-if="!compactHeader">
          <!-- ordenar (no Quadro, mora no ⋮ e a ordem em vigor aparece na linha de baixo): na Fila, "Urgência ▾" (tempo contra a meta, chegada, mais recentes);
               no quadro e na tabela, a ordem deles -->
          <NuxtDropdownMenu
            v-if="!boardDesk"
            :items="sortMenuItems"
            :content="{ align: 'end' }"
          >
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

          <!-- visão: Fila · Quadro · Tabela, um controle só (dono, 13/11/2026). A Fila
               some abaixo do lg (não cabe); o dispositivo lembra a escolha. Só o nome, sem
               ícone: com os três ícones, o selo de atualização não cabia na linha a
               1280 px. -->
          <NuxtTabs
            :model-value="view"
            :items="viewTabs"
            :content="false"
            variant="pill"
            aria-label="Visão do Gestor"
            data-view-switch
            @update:model-value="pickView"
          />
          <!-- Exibir (linhas e colunas) só existe com a Tabela na tela. -->
          <OperatorTableView v-if="view === 'table'" table-key="orders-queue" />
        </template>
      </template>
      <template #more>
        <!-- ⋮ da fila (do tablet para cima; no celular ele mora no fim dos recortes), no
             canto do cabeçalho, depois do sino (`#more` do kit). O posto
             Saída (v4 `gestor-colunas`) não tem ⋯: a leitura se atualiza sozinha e o Visto
             é tocar a faixa da Entrada que pulsa. -->
        <BoardMenu
          v-if="!exitPostView"
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
          :sort-in-menu="boardDesk"
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

      <!-- O filtro único da suíte (dono, 04/11/2026): na mesa, "Filtros (n)" no começo da
           linha de baixo e os recortes ativos ao lado, cada um com ×. O recebimento e o
           canal só existem aqui (nada de abas ou seletor repetindo o mesmo recorte); o
           posto Saída usa o mesmo painel. Abaixo do `md` a linha do chão (acima) leva o
           mesmo painel pelo ícone. -->
      <template #filter-panel>
        <OperatorFilterPanel
          v-model="panelFilters"
          :dimensions="panelDimensions"
          surface="orders"
          screen="queue"
          data-queue-filters
        />
      </template>
      <!-- na Fila (v4): "Precisa de você N · Todos N · ● Atrasados N", o recorte do que
           muda o trabalho; no quadro e na tabela, "Todos" tira os recortes. É o primário
           da toolbar: no celular fica na linha, ao lado do "Filtros". -->
      <template
        v-if="(view === 'queue' && !(isPhone && phoneExitMode)) || boardDesk"
        #filters-primary
      >
        <!-- Um controle só para os recortes (o da Fila e o do Quadro, cada um com o seu
             estado). A Fila só existe do `lg` para cima (`queueAvailable`): o CSS diz o
             mesmo, e o celular não desenha os escopos antes de montar. -->
        <OperatorQuickFilters
          :class="view === 'queue' ? 'max-lg:hidden' : undefined"
          :model-value="view === 'queue' ? scope : boardScope"
          :items="view === 'queue' ? queueScopeTabs : boardScopeTabs"
          :label="view === 'queue' ? 'Recortes da fila' : 'Recortes do quadro'"
          :data-queue-scopes="view === 'queue' ? '' : undefined"
          :data-board-scopes="view === 'queue' ? undefined : ''"
          @update:model-value="
            view === 'queue'
              ? pickScope(String($event))
              : pickBoardScope(String($event))
          "
        />
      </template>
      <!-- À direita da linha de baixo, no Quadro: a ordem em vigor (trocar fica no ⋮) e
           a maquininha na rua, que só aparece enquanto alguma está fora. -->
      <template v-if="boardDesk" #filters-end>
        <div class="flex items-center gap-2">
          <EquipmentOutMenu
            :items="queue?.equipment_out ?? []"
            :is-busy="isBusy"
            @back="equipmentBack"
          />
          <span class="op-micro text-muted-foreground" data-board-order-hint>
            {{ boardOrderHint }}
          </span>
        </div>
      </template>
      <template v-if="hasChannelQueueSignal || showSystemBand" #feedback>
        <div class="flex flex-col gap-2">
          <!-- a loja no iFood: só o SINAL, e só quando muda o que entra na fila. -->
          <ChannelQueueSignal v-if="hasChannelQueueSignal" :attention="channelAttention" />
          <OrderSystemBand
            v-if="showSystemBand"
            :lines="systemUndoLines"
            :busy="isBusy"
            :server-now="queue?.intake[0]?.server_now_iso"
            @undo="(ref_) => onAction(ref_, 'undo_ready')"
          />
        </div>
      </template>
      <!-- Com o modo de seleção ligado, a barra de seleção toma o lugar da toolbar. -->
      <template v-if="selecting" #selection>
        <OperatorBulkBar
          :escape="false"
          :count="selected.size"
          :scope="bulkScope"
          empty="Toque nos pedidos para marcar"
          :items="bulkItems"
          :clear-label="EXIT_SELECTION_LABEL"
          data-bulk-bar
          @clear="stopSelection"
        />
      </template>
    </OperatorPageHeader>

    <!-- celular: as colunas viram abas dentro da segunda faixa canônica do header. O
         traço da aba ativa assenta na borda da faixa, sem vão nem segunda linha (dono,
         02/11/2026): a faixa não tem respiro embaixo, e a aba dentro da faixa não
         desenha linha própria (tema do kit, `tabs` link). -->
    <OperatorToolbar
      v-if="boardAsTabs && view === 'board' && zones.length"
      class="items-end pt-2 pb-0"
      data-board-zone-bar
    >
      <NuxtTabs
        :model-value="phoneZone"
        :items="phoneTabItems"
        :content="false"
        variant="link"
        data-board-zone-tabs
        @update:model-value="pickPhoneZone"
      >
        <template #default="{ item }"><span :class="item.iconOnlyOnPhone ? 'max-sm:sr-only' : undefined">{{ item.label }}</span></template>
        <template #trailing="{ item }"><OperatorCountChip :count="item.count" /></template>
      </NuxtTabs>
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
      <VolumeCheckBar
        :state="volumeCheck.state.value"
        @switch="volumeCheck.switchTo"
        @dismiss-alarm="volumeCheck.dismissAlarm"
        @end="volumeCheck.end"
      />
      <!-- A fila é lida só no cliente (`server: false`): o servidor e a hidratação
           desenham o esqueleto também, senão o cliente hidratava um nó que o servidor
           não mandou. -->
      <div
        v-if="(pending || !hydrated) && !zones.length"
        class="grid gap-3 md:grid-cols-2 lg:grid-cols-3"
        aria-label="Carregando fila"
      >
        <NuxtSkeleton v-for="i in 3" :key="i" class="h-40 w-full" />
      </div>
      <!-- `!stationLocked`: antes do PIN toda leitura volta 403 `station_locked`; quem
           fala nesse estado é a identificação que sobe por cima (app.vue). -->
      <NuxtAlert
        v-else-if="error && !stationLocked && notices.isOpen(`queue-error:${queueFailures}`)"
        v-bind="notices.closeProps"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Falha ao atualizar a fila"
        description="Mantivemos a última leitura; atualize antes de confirmar ações."
        data-queue-error
        @update:open="notices.onOpen(`queue-error:${queueFailures}`, $event)"
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
            ref="boardSplitter"
            :persistence-key="boardSplitterPersistenceKey"
            :items="boardSplitterItems"
            class="min-h-full flex-1"
            handle-label="Ajustar largura das colunas"
            quiet
            data-board-columns
            @layout="boardLayout.applySizes"
          >
            <template v-for="zone in desktopZones" :key="zone.key" #[zone.key]>
              <!-- As colunas recolhidas ficam no lugar delas, como tira: as que vêm
                   antes desta coluna aberta (e, na última, as que vêm depois). -->
              <div class="flex h-full min-h-0 w-full min-w-0 gap-2.5 px-1">
              <OrderBoardStrip
                v-for="closed in boardStrips[zone.key]?.before ?? []"
                :key="closed.key"
                :strip="closed"
                :shortcut="shortcutHint(closed.key)"
                @open="boardLayout.open(closed.key)"
              />
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
              >
                <!-- Uma corrida da TaOn para várias entregas prontas, na coluna delas:
                     some com menos de duas. -->
                <template v-if="zone.key === 'expedition'" #heading-actions>
                  <CourierRideMenu :choices="rideCandidates" @done="refresh()" />
                </template>
              </OrderBoardColumn>
              <OrderBoardStrip
                v-for="closed in boardStrips[zone.key]?.after ?? []"
                :key="closed.key"
                :strip="closed"
                :shortcut="shortcutHint(closed.key)"
                @open="boardLayout.open(closed.key)"
              />
              </div>
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

        <!-- A Tabela: a tabela da suíte (`OperatorTable`, compacta por padrão), com a
             linha que abre os detalhes e as outras ações. -->
        <OperatorTable
          v-else
          v-model:expanded="supervisionExpanded"
          v-model:row-selection="supervisionRowSelection"
          :data="supervisionRows"
          :columns="supervisionColumns"
          :row-key="(row: SupervisionRow) => row.card.ref"
          :row-label="(row: SupervisionRow) => `o pedido ${row.card.ref}`"
          selectable
          pinned="order"
          view-key="orders-queue"
          empty-icon="i-lucide-inbox"
          empty-title="Nenhum pedido precisa de você agora."
          caption="Tabela dos pedidos em andamento"
          data-supervision-table
        >
          <template #order-cell="{ row }">
            <div class="flex min-w-36 flex-col">
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
                class="inline-flex items-start gap-1 text-xs text-muted-foreground"
              >
                <Icon
                  :name="`lucide:${lucideIcon(row.original.card.channel_icon)}`"
                  class="size-3.5 shrink-0"
                />
                <span>{{
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
            <span class="block min-w-40 text-muted-foreground">{{
              row.original.card.items_summary
            }}</span>
          </template>
          <template #total-cell="{ row }">
            <span class="whitespace-nowrap font-semibold tabular-nums">{{
              row.original.card.total_display
            }}</span>
          </template>
          <template #elapsed-cell="{ row }">
            <!-- O relógio vivo do kit (useNowTick), como a Grade: P1-8. -->
            <NuxtBadge
              :color="
                liveAge(row.original.card, nowMs).tone === 'neutral'
                  ? 'neutral'
                  : 'warning'
              "
              :label="liveAge(row.original.card, nowMs).label"
              class="tabular-nums"
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
              :actions="alertActions('error', [
                {
                  label: 'Dispensar',
                  onClick: () => clearActionError(row.original.card.ref),
                },
              ])"
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
          <template v-if="tableRows.length > SUPERVISION_PAGE_SIZE" #footer>
            <div class="flex flex-wrap items-center justify-between gap-3">
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
        </OperatorTable>

        <!-- Encomendas: os pedidos dos próximos dias, fora das colunas do dia, numa lista
             simples (dono, 13/11/2026). No dia, o despertador devolve o pedido ao
             fluxo normal do quadro. -->
        <OrderPreorderList
          v-if="preordersCount"
          :groups="triagedPreorders"
          :count="preordersCount"
        />
      </template>
    </section>

    <!-- A barra de seleção da suíte, abaixo do `lg`: na base (a da mesa toma o lugar
         da toolbar, no `#selection` do cabeçalho). -->
    <OperatorBulkBar
      v-if="selecting"
      placement="base"
      :count="selected.size"
      :scope="bulkScope"
      empty="Toque nos pedidos para marcar"
      :items="bulkItems"
      :clear-label="EXIT_SELECTION_LABEL"
      data-bulk-bar
      @clear="stopSelection"
    />
    <!-- A Saída do celular: o "Próximo" na ação da base (F7). -->
    <OperatorActionBar
      v-else-if="exitBaseAction"
      :action="exitBaseAction"
      label="Saída do próximo pedido"
      data-exit-base-action
    />

    <!-- reject dialog: o mesmo diálogo de motivo do detalhe do pedido -->
    <OrderReasonDialog
      :open="rejectRef != null"
      mode="reject"
      :marketplace="isMarketplaceReject"
      :cancel-reasons="cancelReasons"
      :busy="Boolean(rejectRef && isBusy(rejectRef))"
      @dirty-change="rejectDirty = $event"
      @update:open="
        (v) => {
          if (!v) closeReject();
        }
      "
      @confirm="confirmReject"
    />

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
            :actions="alertActions('warning', [
              {
                label: 'Conferir e manter os valores digitados',
                onClick: () => reviewSettleCustody(),
              },
            ])"
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
