<script setup lang="ts">
// Catalog matrix — produto × canal. The catalog side of the Gestor hub.
// Design: a glanceable availability heatmap (tinted cells) with one-click pause and
// inline reprice per cell; the collection axis (chips) scopes the view; selection +
// a floating bulk bar act on the active recorte. Desktop-first, horizontal scroll on
// narrow screens. The backend owns availability rules; this renders intent + reconciles.
import {
  catalogCsv,
  cellPrice,
  cellSyncView,
  cellView,
  filterRows,
  letterTile,
  rowStatus,
  surfaceDisplayIcon,
  syncBadge,
  syncErrorCount,
} from "~/presentation/catalog";
import {
  catalogDimensions,
  filterByDimensions,
  filtersFromQuery,
  vocationPendingFilters,
} from "~/presentation/catalogFilters";
import { vocationNotice } from "~/presentation/vocation";
import { realtimeIndicator } from "~/presentation/board";
import type {
  Action,
  CatalogPricePreview,
  CatalogPublicationPreview,
} from "~/generated/ordersContract";
import type { ActiveFilters } from "../../../operator-kit/app/types/filters";
import type { OperatorBulkItem } from "../../../operator-kit/app/presentation/bulkBar";
import { filterBarActiveFilters } from "../../../operator-kit/app/presentation/filterBar";
import type {
  AssistableField,
  CatalogRowProjection,
  CollectionProjection,
  ProductDetailPatch,
  ProductDetailProjection,
  SkuRoles,
  SurfaceCellProjection,
  SurfaceProjection,
} from "~/types/catalog";

const collectionRef = ref("");
const {
  readMetadata,
  realtime,
  matrix,
  pending,
  error,
  refresh,
  isBusy,
  cellKey,
  productKey,
  detailKey,
  setCell,
  setProduct,
  bulkSet,
  previewBulkSet,
  bulkPrice,
  previewBulkPrice,
  resync,
  fetchProductDetail,
  saveProductDetail,
  setPurchasable,
  productConflict,
  acknowledgeProductConflict,
  errorMsg,
  reorderCollections,
  reorderItems,
  curationAction,
  verifyOrder,
  bulkBusy,
  aiAssist,
  aiAssistKey,
} = useCatalogMatrix(collectionRef);

const surfaces = computed(() => matrix.value?.surfaces ?? []);
// Cabeçalho de uma linha (UX-KIT-V1): a hora da última leitura útil ao lado do título.
const readClock = computed(() => {
  const at = readMetadata.value?.generated_at;
  return at
    ? new Date(at).toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
});
// Collection navigation remains available while only the row resource changes.
const collections = shallowRef<CollectionProjection[]>(
  matrix.value?.collections ?? [],
);
watch(
  () => matrix.value?.collections,
  (value) => {
    if (value) collections.value = value;
  },
  { flush: "sync" },
);
// Superfícies = canais (transacionam) + feeds (só empurram dados). Índice p/ a
// célula saber o papel da coluna e onde começa a banda de feeds. No backend o model
// do feed chama-se ``Feed`` — daí os nomes internos aqui.
const surfaceByRef = computed(
  () => new Map(surfaces.value.map((s) => [s.ref, s])),
);
const isCellTransactional = (cell: SurfaceCellProjection) =>
  surfaceByRef.value.get(cell.surface_ref)?.transactional ?? true;

// ── colunas visíveis ("Exibir" da `OperatorTable`) ─────────────────────────────
// A escolha é do operador e vale por dispositivo (cookie da tabela, lido também no
// servidor: a matriz nasce com as colunas certas, sem piscar). A tabela guarda as
// OCULTAS: canal ou feed novo nasce visível. Todas as superfícies entram como coluna
// (para o Exibir listá-las); a tabela some com as ocultas.
const catalogView = useOperatorTableView("orders-catalog");
const surfaceColumnId = (ref: string) =>
  `surface_${ref.replace(/[^a-zA-Z0-9_]/g, "_")}`;
const visibleSurfaces = computed(() =>
  surfaces.value.filter(
    (s) => !catalogView.view.value.hidden.includes(surfaceColumnId(s.ref)),
  ),
);
// A divisória da banda de feeds acompanha o recorte: cai no primeiro feed VISÍVEL.
const firstFeedRef = computed(
  () => visibleSurfaces.value.find((s) => !s.transactional)?.ref ?? "",
);
const cellFor = (row: CatalogRowProjection, surfaceRef: string) =>
  row.cells.find((cell) => cell.surface_ref === surfaceRef)!;
const catalogColumns = computed(() => [
  {
    id: "product",
    header: "Produto",
    enableHiding: false,
    meta: {
      class: { th: "sm:min-w-[260px]", td: "sm:min-w-[260px] py-2" },
    },
  },
  ...surfaces.value.map((surface: SurfaceProjection) => ({
    id: surfaceColumnId(surface.ref),
    accessorFn: (row: CatalogRowProjection) => cellFor(row, surface.ref),
    header: surface.short_name,
    meta: {
      label: surface.name,
      class: {
        th: [
          "align-top",
          firstFeedRef.value === surface.ref ? "border-s border-s-default" : "",
        ].join(" "),
        td: [
          "py-2",
          firstFeedRef.value === surface.ref ? "border-s border-s-default" : "",
        ].join(" "),
      },
    },
  })),
  // O ⋯ da linha mora na última coluna, fixada à direita: perto do nome ele
  // ficava a meia tela do texto, e a coluna do produto esticava para guardá-lo.
  {
    id: "actions",
    header: "",
    enableHiding: false,
    meta: { class: { th: "w-px", td: "w-px py-2" } },
  },
]);
// A linha que se arrasta (e o alvo de soltar) é estado da tela: a tabela só aplica.
const catalogRowClass = (row: CatalogRowProjection) =>
  [
    "group transition-[opacity,box-shadow]",
    rowDragKey.value === row.sku ? "opacity-40" : "",
    rowDragKey.value &&
    rowOverKey.value === row.sku &&
    rowDragKey.value !== row.sku
      ? "shadow-[inset_0_2px_0_0_var(--color-primary)]"
      : "",
  ].join(" ");
const channelsCount = computed(
  () => surfaces.value.filter((s) => s.transactional).length,
);
const feedsCount = computed(
  () => surfaces.value.filter((s) => !s.transactional).length,
);
const syncColor = (
  status: string,
): "success" | "warning" | "error" | "neutral" =>
  status === "ok"
    ? "success"
    : status === "error"
      ? "error"
      : status === "never"
        ? "warning"
        : "neutral";
const catalogCountLine = computed(() => {
  const total = matrix.value?.rows?.length ?? 0;
  const shown = rows.value.length;
  const products =
    shown === total
      ? `${total} ${total === 1 ? "produto" : "produtos"}`
      : `${shown} de ${total} produtos`;
  const parts = [
    products,
    `${channelsCount.value} ${channelsCount.value === 1 ? "canal" : "canais"}`,
  ];
  if (feedsCount.value)
    parts.push(
      `${feedsCount.value} ${feedsCount.value === 1 ? "feed" : "feeds"}`,
    );
  return parts.join(" · ");
});
const query = ref("");
// Recorte por dimensões (envio, canal, publicação, venda, estoque, PIM). A coleção
// fica FORA: é o eixo primário, mora nas pills (que também reordenam) e recorta no
// servidor. Aqui é tudo client-side — a matriz já veio inteira.
// Chegando de um checklist de canal (`?surface=ifood&sync=error`), a tela já abre recortada.
const filters = ref<ActiveFilters>(filtersFromQuery(useRoute().query));
const searched = computed<CatalogRowProjection[]>(() =>
  filterRows(matrix.value?.rows ?? [], query.value),
);
// As contagens das opções são lidas sobre o resultado da BUSCA (antes dos filtros),
// senão marcar uma opção zeraria as contagens das outras.
const dimensions = computed(() =>
  catalogDimensions(surfaces.value, searched.value),
);
const rows = computed<CatalogRowProjection[]>(() =>
  filterByDimensions(searched.value, surfaces.value, filters.value),
);
// status por linha (esmaecer/foto P&B/selo) computado uma vez por refresh.
const rowStatuses = computed(() =>
  Object.fromEntries(rows.value.map((r) => [r.sku, rowStatus(r)])),
);
// há alguma superfície que projeta? (iFood/Meta/…) — gateia a UI de sync/PIM.
const hasProjectionTargets = computed(() =>
  surfaces.value.some((s) => s.is_projection_target),
);
const activeCollection = computed(
  () => collections.value.find((c) => c.ref === collectionRef.value) ?? null,
);

// zoom da foto (clique na thumbnail amplia num lightbox)
const zoom = ref<{ url: string; name: string } | null>(null);
// A foto que não carregou vira a letra no quadrado colorido (G20, v3/v4): o texto
// alternativo do navegador ("Bague") nunca aparece no lugar da imagem.
const brokenImages = ref<Set<string>>(new Set());
function imageFailed(sku: string) {
  brokenImages.value = new Set(brokenImages.value).add(sku);
}
// A foto que já falhou antes de a tela hidratar (desenhada no servidor) não dispara
// mais o `error`: confere as que terminaram sem imagem, ao montar e a cada leitura.
function sweepBrokenImages() {
  for (const img of document.querySelectorAll<HTMLImageElement>(
    "img[data-catalog-thumb]",
  )) {
    if (img.complete && img.naturalWidth === 0 && img.dataset.catalogThumb)
      imageFailed(img.dataset.catalogThumb);
  }
}
onMounted(() => {
  nextTick(sweepBrokenImages);
});
watch(
  () => matrix.value?.rows,
  () => {
    if (import.meta.client) nextTick(sweepBrokenImages);
  },
);
// ⋯ do cabeçalho (v3): a última leitura útil, Atualizar e Exportar.
function exportCatalog() {
  const csv = catalogCsv(rows.value, visibleSurfaces.value);
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `catalogo-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── reordenar coleções (pills arrastáveis) ─────────────────────────────────────
// Override = null → ordem do servidor (determinístico p/ SSR); só é setado durante o
// drag otimista, e zerado após o POST+refresh (que já vem reordenado).
function reorderView<T extends { ref?: string; sku?: string }>(
  server: T[],
  override: string[] | null,
  key: (t: T) => string,
): T[] {
  if (!override) return server;
  const byKey = new Map(server.map((t) => [key(t), t]));
  const out = override.map((k) => byKey.get(k)).filter(Boolean) as T[];
  return out.length === server.length ? out : server;
}

const orderDraft = ref<{
  operation: "reorder-collections" | "reorder-items";
  ref: string;
  ordered: string[];
  action?: Action;
} | null>(null);
const orderSaving = ref(false);
const confirmDiscard = useConfirm();
onBeforeRouteLeave(() => {
  if (
    orderSaving.value ||
    bulkBusy.value ||
    (detailSku.value && isBusy(detailKey(detailSku.value))) ||
    (editing.value && isBusy(cellKey(editing.value.sku, editing.value.surface)))
  )
    return false;
  return (
    !hasUnsavedDraft.value ||
    confirmDiscard({
      title: "Sair sem salvar as alterações do catálogo?",
      description:
        "O que você alterou e ainda não salvou se perde (ordem, preço, publicação ou ficha do produto). O que já foi salvo continua salvo.",
      confirmLabel: "Descartar e sair",
    })
  );
});
let observedCollectionAction: Action | undefined;
let observedItemAction: Action | undefined;
let observedCollectionRef = "";
async function saveOrderDraft(useCurrent = false, checkOnly = false) {
  const draft = orderDraft.value;
  if (!draft || orderSaving.value) return;
  const action = useCurrent
    ? curationAction(draft.operation, draft.ref)
    : draft.action;
  if (useCurrent && !action) return;
  orderSaving.value = true;
  try {
    const ok = checkOnly
      ? await verifyOrder(draft.operation, draft.ref)
      : draft.operation === "reorder-items"
        ? await reorderItems(draft.ref, draft.ordered, action)
        : await reorderCollections(draft.ordered, action);
    if (ok && orderDraft.value === draft) orderDraft.value = null;
  } finally {
    orderSaving.value = false;
    collectionOverride.value = null;
    rowOverride.value = null;
  }
}
const currentOrder = computed(() =>
  orderDraft.value?.operation === "reorder-items"
    ? orderDraft.value.ref === collectionRef.value
      ? (matrix.value?.rows ?? []).map((row) => row.sku)
      : []
    : collections.value.map((group) => group.ref),
);
const canReviewOrder = computed(
  () =>
    !!orderDraft.value &&
    !!curationAction(orderDraft.value.operation, orderDraft.value.ref) &&
    currentOrder.value.length === orderDraft.value.ordered.length &&
    currentOrder.value.every((key) => orderDraft.value!.ordered.includes(key)),
);
function orderLabel(key: string) {
  return orderDraft.value?.operation === "reorder-items"
    ? matrix.value?.rows.find((row) => row.sku === key)?.name || key
    : collections.value.find((group) => group.ref === key)?.name || key;
}
const collectionOverride = ref<string[] | null>(null);
const orderedCollections = computed(() =>
  reorderView<CollectionProjection>(
    collections.value,
    collectionOverride.value,
    (c) => c.ref,
  ),
);
// Celular (abaixo de `sm`, a régua da toolbar do kit): a coleção é o primário da linha,
// numa lista (são mais de quatro e as pílulas rolavam para fora); os recortes e as
// colunas moram no painel "Filtros", com os ativos como chips removíveis. Lista no
// celular e pílulas na mesa decididas pelo CSS (`sm:hidden`/`max-sm:hidden`): o
// primeiro desenho do servidor já é o certo. O `NuxtSelect` não aceita valor vazio:
// "Todas" é `ALL_COLLECTIONS` só aqui.
const ALL_COLLECTIONS = "all";
const collectionSelectItems = computed(() =>
  collectionTabs.value.map((tab) => ({
    label: `${tab.label} (${tab.badge})`,
    value: tab.value || ALL_COLLECTIONS,
  })),
);
const activeFilters = computed(() =>
  filterBarActiveFilters(dimensions.value, filters.value, (next) => {
    filters.value = next;
  }),
);
const collectionTabs = computed(() => [
  {
    label: "Todas",
    value: "",
    badge: String(matrix.value?.rows?.length ?? rows.value.length),
  },
  ...orderedCollections.value.map((collection) => ({
    label: collection.name,
    value: collection.ref,
    icon: collection.is_smart ? "i-lucide-sparkles" : undefined,
    badge: String(collection.product_count),
  })),
]);
const {
  dragKey: _collDragKey,
  onPointerDown: collPointerDown,
  onKeyDown: collKeyDown,
} = useDragReorder(
  () => orderedCollections.value.map((c) => c.ref),
  (order) => {
    if (orderDraft.value) return;
    collectionOverride.value = order;
    orderDraft.value = {
      operation: "reorder-collections",
      ref: "",
      ordered: order,
      action: observedCollectionAction,
    };
    saveOrderDraft();
  },
  () => {
    observedCollectionAction = curationAction("reorder-collections");
  },
);

// ── reordenar produtos (handle na linha) — só numa coleção MANUAL, sem busca ────
// Arrastar só faz sentido sobre a coleção INTEIRA: com busca ou filtro ativo a lista
// é um recorte, e a ordem gravada sairia errada.
const canReorderRows = computed(
  () =>
    collectionRef.value !== "" &&
    !activeCollection.value?.is_smart &&
    query.value.trim() === "" &&
    Object.keys(filters.value).length === 0,
);
const rowOverride = ref<string[] | null>(null);
const orderedRows = computed(() =>
  reorderView<CatalogRowProjection>(
    rows.value,
    rowOverride.value,
    (r) => r.sku,
  ),
);
const displayRows = computed(() =>
  canReorderRows.value ? orderedRows.value : rows.value,
);
const {
  dragKey: rowDragKey,
  overKey: rowOverKey,
  onPointerDown: rowPointerDown,
  onKeyDown: rowKeyDown,
} = useDragReorder(
  () => displayRows.value.map((r) => r.sku),
  (order) => {
    if (orderDraft.value) return;
    rowOverride.value = order;
    orderDraft.value = {
      operation: "reorder-items",
      ref: observedCollectionRef,
      ordered: order,
      action: observedItemAction,
    };
    saveOrderDraft();
  },
  () => {
    observedCollectionRef = collectionRef.value;
    observedItemAction = curationAction("reorder-items", observedCollectionRef);
  },
);

// ── selection + floating bulk bar (acts on the active recorte) ─────────────────
const selected = ref<Set<string>>(new Set());
// A tabela da suíte marca (coluna de seleção e o "todos" no cabeçalho); o Set guarda,
// e a barra de lote lê dele.
const catalogRowSelection = computed<Record<string, boolean>>({
  get: () => Object.fromEntries([...selected.value].map((sku) => [sku, true])),
  set: (next) => {
    selected.value = new Set(Object.keys(next).filter((sku) => next[sku]));
  },
});
function clearSelection() {
  selected.value = new Set();
}
watch(collectionRef, clearSelection);

const bulkSurface = ref("");
watchEffect(() => {
  if (!bulkSurface.value && surfaces.value.length)
    bulkSurface.value = surfaces.value[0]!.ref;
});
// Feed só pausa/reativa em lote — sem publicar/reprecificar (não transaciona).
const bulkSurfaceIsFeed = computed(() => {
  const s = surfaceByRef.value.get(bulkSurface.value);
  return !!s && !s.transactional;
});
const channelSurfaces = computed(() =>
  surfaces.value.filter((s) => s.transactional),
);
const feedSurfaces = computed(() =>
  surfaces.value.filter((s) => !s.transactional),
);
const bulkSurfaceItems = computed(() => [
  { label: "Todos os canais", value: "*" },
  ...(channelSurfaces.value.length
    ? [
        { type: "label" as const, label: "Canais" },
        ...channelSurfaces.value.map((surface) => ({
          label: surface.name,
          value: surface.ref,
        })),
      ]
    : []),
  ...(feedSurfaces.value.length
    ? [
        { type: "label" as const, label: "Feeds" },
        ...feedSurfaces.value.map((surface) => ({
          label: surface.name,
          value: surface.ref,
        })),
      ]
    : []),
]);
type PublicationDraft = {
  surface: string;
  skus: string[];
  patch: { is_sellable?: boolean; is_published?: boolean };
  preview: CatalogPublicationPreview;
};
const publicationDraft = ref<PublicationDraft | null>(null);
async function bulk(patch: PublicationDraft["patch"]) {
  if (!bulkSurface.value || selected.value.size === 0 || publicationDraft.value)
    return;
  const surface = bulkSurface.value,
    skus = [...selected.value];
  const preview = await previewBulkSet(surface, { skus }, patch);
  if (preview) publicationDraft.value = { surface, skus, patch, preview };
}
async function reviewPublication() {
  const draft = publicationDraft.value;
  if (!draft) return;
  const preview = await previewBulkSet(
    draft.surface,
    { skus: draft.skus },
    draft.patch,
  );
  if (preview && publicationDraft.value === draft)
    publicationDraft.value = { ...draft, preview };
}
async function confirmPublication() {
  const draft = publicationDraft.value;
  if (!draft) return;
  const count = await bulkSet(
    draft.surface,
    { skus: draft.skus },
    draft.patch,
    draft.preview,
  );
  if (count !== null && publicationDraft.value === draft) {
    publicationDraft.value = null;
    selected.value = new Set(
      [...selected.value].filter((sku) => !draft.skus.includes(sku)),
    );
  }
}
function publicationState(value: Record<string, boolean>) {
  return [
    value.is_published === undefined
      ? ""
      : value.is_published
        ? "Exibido"
        : "Oculto",
    value.is_sellable ? "Habilitado nesta célula" : "Pausado nesta célula",
  ]
    .filter(Boolean)
    .join(" · ");
}

// ── reprecificação em lote (popover) ───────────────────────────────────────────
const priceOpen = ref(false);
// A barra de seleção (OperatorBulkBar): "N selecionados | Canal | Pausar/Ativar |
// Ocultar/Exibir | Preço | ×" (dono, 09/10/2026). Os pares opostos são um grupo só,
// com o mesmo peso. Feed só pausa e reativa (não transaciona): sem Ocultar/Exibir nem
// Preço. A barra existe em dois lugares (toolbar na mesa, base abaixo do `lg`); o
// painel do preço abre só no da largura da vez, senão abririam os dois.
const { belowLg: bulkAtBase } = useScreen();
const [DefineBulkPrice, ReuseBulkPrice] = createReusableTemplate();
const bulkScope = computed(() => activeCollection.value?.name ?? "");
function bulkItems(placement: "toolbar" | "base"): OperatorBulkItem[] {
  const busy = bulkBusy.value;
  return [
    [
      { label: "Pausar", icon: "i-lucide-pause", disabled: busy, onSelect: () => bulk({ is_sellable: false }) },
      { label: "Ativar", icon: "i-lucide-play", disabled: busy, onSelect: () => bulk({ is_sellable: true }) },
    ],
    ...(bulkSurfaceIsFeed.value
      ? []
      : [
          [
            { label: "Ocultar", icon: "i-lucide-eye-off", disabled: busy, onSelect: () => bulk({ is_published: false }) },
            { label: "Exibir", icon: "i-lucide-eye", disabled: busy, onSelect: () => bulk({ is_published: true }) },
          ],
          {
            label: "Preço…",
            icon: "i-lucide-tag",
            disabled: busy,
            panel: "price",
            open: priceOpen.value && (placement === "base") === bulkAtBase.value,
            onUpdateOpen: (open: boolean) => (priceOpen.value = open),
          },
        ]),
  ];
}
const priceOp = ref<"set" | "pct" | "delta">("pct");
const priceOps = [
  { k: "set", l: "Definir" },
  { k: "pct", l: "Ajustar %" },
  { k: "delta", l: "Ajustar R$" },
] as const;
const priceInputBulk = ref("");
const pricePreview = ref<CatalogPricePreview | null>(null);
let priceRequest = 0;
const priceBase = () =>
  JSON.stringify([
    priceOp.value,
    priceInputBulk.value,
    bulkSurface.value,
    [...selected.value].sort(),
  ]);
watch(
  priceBase,
  () => {
    priceRequest++;
    pricePreview.value = null;
  },
  { flush: "sync" },
);
const surfaceLabel = (ref_: string) =>
  ref_ === "*"
    ? "Todos os canais"
    : (surfaces.value.find((s) => s.ref === ref_)?.name ?? ref_);
// número digitado (aceita vírgula/percentual/negativo); em centavos p/ set/delta.
function parsedPriceValue(): number | null {
  const raw = priceInputBulk.value
    .replace(/[^0-9,.-]/g, "")
    .replace(/\./g, "")
    .replace(",", ".");
  const n = Number.parseFloat(raw);
  if (!Number.isFinite(n)) return null;
  return priceOp.value === "pct" ? Math.round(n) : Math.round(n * 100);
}
const priceValid = computed(() => {
  const v = parsedPriceValue();
  return v !== null && (priceOp.value !== "set" || v >= 0);
});
async function applyBulkPrice() {
  const value = parsedPriceValue();
  if (value === null || !bulkSurface.value || selected.value.size === 0) return;
  if (!pricePreview.value) {
    const request = ++priceRequest;
    const base = priceBase();
    const preview = await previewBulkPrice(
      bulkSurface.value,
      { skus: [...selected.value] },
      { op: priceOp.value, value },
    );
    if (request === priceRequest && base === priceBase() && priceOpen.value)
      pricePreview.value = preview;
    return;
  }
  const base = priceBase();
  const ok = await bulkPrice(
    bulkSurface.value,
    { skus: [...selected.value] },
    { op: priceOp.value, value },
    pricePreview.value,
  );
  if (ok === null || base !== priceBase()) return;
  priceOpen.value = false;
  priceInputBulk.value = "";
  clearSelection();
}

// ── product-level actions ("globalzinho" + publish) — via menu ⋯ da linha ───────
function toggleProduct(row: CatalogRowProjection) {
  setProduct(row.sku, { is_sellable: !row.is_sellable });
  menuOpen.value = null;
}
function toggleProductPublish(row: CatalogRowProjection) {
  setProduct(row.sku, { is_published: !row.is_published });
  menuOpen.value = null;
}

// row actions menu (⋯) — casa das ações menos corriqueiras (editar, pausar tudo,
// (des)publicar). Um menu por vez; keyed por sku.
const menuOpen = ref<string | null>(null);
const headerMenuItems = computed(() => [
  [
    {
      type: "label" as const,
      slot: "freshness",
      label: "Leitura do catálogo",
    },
  ],
  [
    {
      label: "Atualizar",
      icon: "i-lucide-refresh-cw",
      loading: pending.value,
      onSelect: () => refresh(),
    },
    {
      label: "Exportar CSV",
      icon: "i-lucide-download",
      onSelect: exportCatalog,
    },
  ],
]);
function rowMenuItems(row: CatalogRowProjection) {
  const primary = [
    {
      label: "Editar detalhes",
      icon: "i-lucide-pencil",
      onSelect: () => openDetail(row),
    },
    {
      label: row.is_sellable
        ? "Pausar em todos os canais"
        : "Ativar em todos os canais",
      icon: row.is_sellable ? "i-lucide-pause" : "i-lucide-play",
      disabled: isBusy(productKey(row.sku)) || !row.product_action?.enabled,
      onSelect: () => toggleProduct(row),
    },
    {
      label: row.is_published ? "Ocultar no catálogo" : "Exibir no catálogo",
      icon: row.is_published ? "i-lucide-eye-off" : "i-lucide-eye",
      disabled: isBusy(productKey(row.sku)) || !row.product_action?.enabled,
      onSelect: () => toggleProductPublish(row),
    },
  ];
  const projection = hasProjectionTargets.value
    ? [
        {
          label: "Dados para redes sociais",
          icon: "i-lucide-sparkles",
          badge: row.pim_complete ? undefined : "Incompleto",
          onSelect: () => openDetail(row, "social"),
        },
        {
          label: "Reenviar às plataformas",
          icon: "i-lucide-refresh-cw",
          disabled: isBusy(productKey(row.sku)) || !row.resync_action?.enabled,
          onSelect: () => resyncRow(row),
        },
      ]
    : [];
  return projection.length ? [primary, projection] : [primary];
}

// host do Django (não o do Gestor) — usado nos deep-links de saída dos feeds.
const djangoBase = useRuntimeConfig().public.djangoBaseUrl as string;

// ── cell pause/resume + inline reprice ─────────────────────────────────────────
// A pausa por célula vale para canal (vende) e feed (só exibe). No feed o backend
// grava em Feed.options[paused_skus]; aqui é o mesmo gesto.
const surfaceWord = (cell: SurfaceCellProjection) =>
  isCellTransactional(cell) ? "canal" : "feed";
function toggleCell(row: CatalogRowProjection, cell: SurfaceCellProjection) {
  if (!cell.in_listing) return;
  setCell(row.sku, cell.surface_ref, { is_sellable: !cell.is_sellable });
}
// O "Pausar" por canal do painel (G22): o MESMO interruptor da célula da tabela.
const adminBaseUrl = useRuntimeConfig().public.adminBaseUrl as string;
const detailChannelCells = computed(() => {
  const row = (matrix.value?.rows ?? []).find(
    (item) => item.sku === detailSku.value,
  );
  if (!row) return {};
  return Object.fromEntries(
    row.cells
      .filter((cell) => cell.in_listing)
      .map((cell) => [
        cell.surface_ref,
        {
          paused: !cell.is_sellable,
          enabled: Boolean(cell.action?.enabled ?? true),
          busy: isBusy(cellKey(row.sku, cell.surface_ref)),
        },
      ]),
  );
});
async function pauseDetailChannel(surface: string, pause: boolean) {
  const sku = detailSku.value;
  if (!sku) return;
  if (!(await setCell(sku, surface, { is_sellable: !pause }))) return;
  // Relê só a disponibilidade: o rascunho aberto no painel não se perde.
  const fresh = await fetchProductDetail(sku);
  if (fresh && detailSku.value === sku)
    detailAvailability.value = fresh.channel_availability ?? [];
}
const detailAvailability = ref<
  ProductDetailProjection["channel_availability"] | null
>(null);
const editing = ref<{
  sku: string;
  surface: string;
  action?: Action;
  original: string;
} | null>(null);
const priceInput = ref("");
async function startEdit(
  row: CatalogRowProjection,
  cell: SurfaceCellProjection,
) {
  if (!cell.in_listing) return;
  if (editing.value && !(await closePrice())) return;
  priceInput.value = ((cell.price_q ?? 0) / 100).toFixed(2).replace(".", ",");
  editing.value = {
    sku: row.sku,
    surface: cell.surface_ref,
    action: cell.action ?? undefined,
    original: priceInput.value,
  };
}
function priceConflict(cell: SurfaceCellProjection) {
  const before = editing.value?.action?.payload_schema.base_revisions as
    Record<string, string> | undefined;
  const current = cell.action?.payload_schema.base_revisions as
    Record<string, string> | undefined;
  return !!before && before.price_q !== current?.price_q;
}
async function closePrice() {
  if (
    editing.value &&
    isBusy(cellKey(editing.value.sku, editing.value.surface))
  )
    return false;
  if (
    editing.value &&
    priceInput.value !== editing.value.original &&
    !(await confirmDiscard({
      title: "Descartar o preço digitado?",
      description:
        "O novo preço não foi salvo. O produto continua com o preço atual.",
    }))
  )
    return false;
  editing.value = null;
  return true;
}
function keepPrice(cell: SurfaceCellProjection) {
  if (editing.value && cell.action) editing.value.action = cell.action;
}
const isEditing = (sku: string, surface: string) =>
  editing.value?.sku === sku && editing.value?.surface === surface;
function parseBrl(text: string): number | null {
  const cleaned = text
    .replace(/[^0-9,.-]/g, "")
    .replace(/\./g, "")
    .replace(",", ".");
  const value = Number.parseFloat(cleaned);
  return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : null;
}
async function commitPrice(
  row: CatalogRowProjection,
  cell: SurfaceCellProjection,
) {
  if (priceConflict(cell)) return;
  const price_q = parseBrl(priceInput.value);
  if (price_q === null) return;
  if (price_q === cell.price_q) {
    editing.value = null;
    return;
  }
  const originalEditor = editing.value;
  const ok = await setCell(
    row.sku,
    cell.surface_ref,
    { price_q },
    editing.value?.action,
  );
  if (ok && editing.value === originalEditor) editing.value = null;
}

// nome do canal (para o rótulo do popover de preço) + tooltip do valor no ícone $.
const surfaceName = (ref: string) =>
  surfaces.value.find((s) => s.ref === ref)?.name ?? ref;
function priceTitle(
  row: CatalogRowProjection,
  cell: SurfaceCellProjection,
): string {
  const p = cellPrice(row, cell);
  return p.differs
    ? `${cell.price_display} · ${p.delta === "up" ? "acima" : "abaixo"} do base`
    : cell.price_display;
}

// ── sync por célula + PIM (Arc H) ──────────────────────────────────────────────
// Selo de sync por (produto × plataforma): resolve a superfície p/ saber se projeta.
const cellSync = (cell: SurfaceCellProjection) =>
  cellSyncView(surfaceByRef.value.get(cell.surface_ref), cell);
const rowSyncErrors = (row: CatalogRowProjection) =>
  syncErrorCount(row, surfaces.value);
function resyncCell(row: CatalogRowProjection, cell: SurfaceCellProjection) {
  resync(row.sku, cell.surface_ref);
}
function resyncRow(row: CatalogRowProjection) {
  resync(row.sku);
  menuOpen.value = null;
}

// painel de produto (edição completa) — abre pelo menu ⋯ da linha. A matriz não
// carrega os campos longos: buscamos o detalhe sob demanda ao abrir. Os dados
// sociais (PIM) são uma ABA daqui: o produto é um só, e antes eram dois painéis
// que salvavam pedaços diferentes do mesmo registro.
const detailSku = ref<string | null>(null);
const detail = ref<ProductDetailProjection | null>(null);
const detailLoading = ref(false);
const detailTab = ref("geral");
const detailDirty = ref(false);
const hasUnsavedDraft = computed(
  () =>
    !!orderDraft.value ||
    !!publicationDraft.value ||
    detailDirty.value ||
    !!(editing.value && priceInput.value !== editing.value.original) ||
    !!(priceOpen.value && priceInputBulk.value.trim()),
);
function beforeUnload(event: BeforeUnloadEvent) {
  if (!hasUnsavedDraft.value) return;
  event.preventDefault();
  event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload));
async function selectCollection(next: string) {
  if (next === collectionRef.value) return;
  if (editing.value && !(await closePrice())) return;
  if (
    priceOpen.value &&
    priceInputBulk.value.trim() &&
    !(await confirmDiscard({
      title: "Trocar de coleção sem aplicar o preço em lote?",
      description:
        "O preço em lote que você digitou se perde, e nenhum preço muda.",
      confirmLabel: "Descartar e trocar",
    }))
  )
    return;
  priceOpen.value = false;
  collectionRef.value = next;
}
let detailRequest = 0;
const detailRoles = ref<SkuRoles | null>(null);
async function openDetail(row: CatalogRowProjection, tab = "geral") {
  const request = ++detailRequest;
  menuOpen.value = null;
  detailTab.value = tab;
  detailSku.value = row.sku;
  detail.value = null;
  detailAvailability.value = null;
  detailLoading.value = true;
  try {
    const result = await fetchProductDetail(row.sku);
    if (request === detailRequest && detailSku.value === row.sku) {
      detail.value = result;
      detailRoles.value = result?.roles ?? null;
    }
  } finally {
    if (request === detailRequest) detailLoading.value = false;
  }
}
// Chegando de um alerta (`?sku=AGUA-500&tab=social`, o GTIN que a SEFAZ recusou),
// a tela abre aquele produto já na aba certa. Espera a matriz ter a linha.
const route = useRoute();
const queryText = (value: unknown) => (typeof value === "string" ? value : "");
const skuFromLink = ref(queryText(route.query.sku));
watch(
  () => route.query.sku,
  (value) => {
    skuFromLink.value = queryText(value);
  },
);
watch(
  [skuFromLink, () => matrix.value?.rows],
  ([sku, rows]) => {
    if (import.meta.server || !sku || !rows) return;
    const row = rows.find((candidate) => candidate.sku === sku);
    if (!row) return;
    skuFromLink.value = "";
    void openDetail(row, queryText(route.query.tab) || "geral");
  },
  { immediate: true },
);
// Vocação (só para o B.I.): o aviso da lista conta os produtos à venda
// sem vocação, da loja inteira. "Classificar" recorta a lista neles (todas as
// coleções) e abre o primeiro já na aba "Preço e config", onde a vocação mora.
const vocation = computed(() => vocationNotice(matrix.value?.vocation_pending));
const skuToClassify = ref("");
async function classifyVocation() {
  const notice = vocation.value;
  if (!notice) return;
  filters.value = vocationPendingFilters();
  query.value = "";
  await selectCollection("");
  // Painel aberto com rascunho: recorta a lista, mas não troca o produto aberto.
  if (collectionRef.value !== "" || detailDirty.value) return;
  skuToClassify.value = notice.firstSku;
}
watch([skuToClassify, () => matrix.value?.rows], ([sku, rows]) => {
  if (!sku || !rows) return;
  const row = rows.find((candidate) => candidate.sku === sku);
  if (!row) return;
  skuToClassify.value = "";
  void openDetail(row, "config");
});
function closeDetail() {
  detailRequest++;
  detailRoles.value = null;
  detailSku.value = null;
  detail.value = null;
  detailDirty.value = false;
}
async function saveDetail(patch: ProductDetailPatch) {
  if (!detailSku.value) return;
  const sku = detailSku.value;
  const request = detailRequest;
  const ok = await saveProductDetail(sku, patch);
  if (ok && sku === detailSku.value && request === detailRequest) closeDetail();
}

async function togglePurchasable(enabled: boolean) {
  if (!detailSku.value) return;
  const sku = detailSku.value;
  const request = detailRequest;
  const product = await setPurchasable(sku, enabled);
  // Só os selos mudam, e moram fora de `detail`: trocar o detalhe reidrataria o
  // painel e apagaria o rascunho que o gestor ainda não salvou.
  if (product && sku === detailSku.value && request === detailRequest)
    detailRoles.value = product.roles ?? null;
}

function reviewProductConflict(keepDraft: boolean) {
  if (!detailSku.value) return;
  const current = acknowledgeProductConflict(detailSku.value);
  if (!keepDraft && current) detail.value = current;
}

// assist de IA — o painel é presentacional, então a página injeta a chamada e o
// predicado de ocupado.
function assistFor(sku: Ref<string | null>) {
  return {
    assist: (field: AssistableField, currentValue: string) =>
      sku.value
        ? aiAssist(sku.value, field, currentValue)
        : Promise.resolve(""),
    assistBusy: (field: AssistableField) =>
      sku.value ? isBusy(aiAssistKey(sku.value, field)) : false,
  };
}
const detailAssist = assistFor(detailSku);

useHead({ title: "Catálogo" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <!-- Cabeçalho de uma linha (UX-KIT-V1, prévia v3 `orders-catalog3.html`): título +
         ao vivo + busca e filtro + colunas; as coleções na segunda linha. -->
    <!-- O painel do preço em lote, escrito uma vez e usado pelas duas barras. -->
    <DefineBulkPrice>
      <div class="w-72 space-y-3 p-4">
        <p class="text-sm font-medium">
          <span class="tabular-nums">{{ selected.size }}</span>
          selecionado{{ selected.size === 1 ? "" : "s" }} em
          {{ surfaceLabel(bulkSurface) }}
        </p>
        <NuxtTabs
          v-model="priceOp"
          :items="
            priceOps.map((option) => ({
              label: option.l,
              value: option.k,
            }))
          "
          :content="false"
        />
        <div class="flex items-center gap-1.5">
          <span
            class="w-5 shrink-0 text-center text-sm text-muted-foreground"
            >{{ priceOp === "pct" ? "%" : "R$" }}</span
          >
          <NuxtInput
            v-model="priceInputBulk"
            type="text"
            inputmode="decimal"
            autofocus
            :placeholder="
              priceOp === 'set'
                ? '15,00'
                : priceOp === 'pct'
                  ? '+10 ou -20'
                  : '+1,00 ou -0,50'
            "
            @keyup.enter="applyBulkPrice"
          />
        </div>
        <p class="mt-1.5 text-xs leading-tight text-muted-foreground">
          {{
            priceOp === "set"
              ? "Define o preço de todos os selecionados."
              : priceOp === "pct"
                ? "Aumenta (+) ou reduz (−) por porcentagem."
                : "Soma (+) ou subtrai (−) do preço atual."
          }}
          A mudança é permanente. Para promoção, use as regras.
        </p>
        <NuxtCard v-if="pricePreview" variant="soft" aria-live="polite">
          <template #header
            ><p class="text-xs font-semibold">
              Revise {{ pricePreview.cells.length }} células antes de
              confirmar
            </p></template
          >
          <ul class="space-y-1 text-xs">
            <li v-for="cell in pricePreview.cells" :key="cell.id">
              {{ cell.sku }} · {{ surfaceLabel(cell.surface_ref) }} ·
              mínimo {{ cell.tier }}:
              {{
                (cell.before_q / 100).toLocaleString("pt-BR", {
                  style: "currency",
                  currency: "BRL",
                })
              }}
              →
              {{
                (cell.after_q / 100).toLocaleString("pt-BR", {
                  style: "currency",
                  currency: "BRL",
                })
              }}
            </li>
          </ul>
        </NuxtCard>
        <div class="mt-2.5 flex justify-end gap-1.5">
          <NuxtButton
            color="neutral"
            variant="ghost"
            label="Cancelar"
            @click="priceOpen = false"
          />
          <NuxtButton
            :label="
              pricePreview
                ? 'Confirmar alterações'
                : 'Revisar alterações'
            "
            :disabled="!priceValid || bulkBusy"
            @click="applyBulkPrice"
          />
        </div>
      </div>
    </DefineBulkPrice>

    <OperatorPageHeader
      title="Catálogo"
      :filters-wrap="false"
      :active-filters="activeFilters"
    >
      <template #status>
        <OperatorLiveStatus
          :tone="
            error
              ? 'off'
              : realtime === 'live'
                ? 'live'
                : realtime === 'connecting'
                  ? 'late'
                  : 'calm'
          "
          :time="readClock"
          :label="
            error ? 'Atualização falhou' : realtimeIndicator(realtime).label
          "
          :detail="realtimeIndicator(realtime).title"
        />
      </template>
      <template #search>
        <OperatorSuiteSearch
          v-model="query"
          screen-label="filtrando o catálogo"
          placeholder="Buscar produto ou SKU"
          aria-label="Buscar produto ou SKU"
        />
      </template>
      <template #actions>
        <!-- ⋯ (v3): a última leitura útil, Atualizar e Exportar moram aqui -->
        <OperatorMoreMenu
          :items="headerMenuItems"
          label="Mais ações do catálogo"
          data-catalog-more
        >
          <template #freshness>
            <ReadFreshness
              inline
              :metadata="readMetadata"
              :failed="Boolean(error)"
            />
          </template>
        </OperatorMoreMenu>
      </template>
      <template #filters>
        <!-- Recortes e escolha de colunas pertencem à DashboardToolbar, não à
             faixa de identidade da DashboardNavbar. -->
        <FilterBar v-model="filters" :dimensions="dimensions" touch />
        <OperatorTableView v-if="surfaces.length" table-key="orders-catalog" />
        <!-- No celular a coleção é o primário da linha (o `NuxtSelect` abaixo); aqui,
             só do `sm` para cima, pelo CSS. -->
        <span
          v-if="collections.length"
          class="me-1 shrink-0 op-eyebrow text-muted-foreground max-sm:hidden"
          >Coleção</span
        >
        <!-- coleções: arraste os chips para reordenar as seções da vitrine (Collection.sort_order) -->
        <NuxtTabs
          v-if="collections.length"
          class="max-sm:hidden"
          :model-value="collectionRef"
          :items="collectionTabs"
          :content="false"
          variant="pill"
          aria-label="Coleção do catálogo"
          data-collection-tabs
          @update:model-value="selectCollection(String($event))"
          @keydown.up.prevent.stop="
            collectionRef && collKeyDown(collectionRef, $event)
          "
          @keydown.down.prevent.stop="
            collectionRef && collKeyDown(collectionRef, $event)
          "
        >
          <template #default="{ item }">
            <span
              class="touch-none"
              :data-dragkey="item.value || undefined"
              :title="
                item.value
                  ? `${item.label}. Para reordenar, use as setas para cima ou para baixo.`
                  : item.label
              "
              @pointerdown="
                item.value && collPointerDown(String(item.value), $event)
              "
              >{{ item.label }}</span
            >
          </template>
        </NuxtTabs>
        <!-- "23 de 131 produtos · 4 canais · 4 feeds" no fim da linha das coleções (v3),
             inteiro: a frase não se corta na borda. -->
        <p
          class="hidden shrink-0 op-micro whitespace-nowrap text-muted-foreground lg:block"
          data-catalog-counts
        >
          <span class="tabular-nums">{{ catalogCountLine }}</span>
        </p>
      </template>
      <template v-if="collections.length" #filters-primary>
        <NuxtSelect
          :model-value="collectionRef || ALL_COLLECTIONS"
          :items="collectionSelectItems"
          aria-label="Coleção do catálogo"
          class="min-w-0 max-w-full sm:hidden"
          data-collection-select
          @update:model-value="
            selectCollection(
              String($event) === ALL_COLLECTIONS ? '' : String($event),
            )
          "
        />
      </template>
      <template v-if="selected.size" #selection>
        <OperatorBulkBar
          :count="selected.size"
          :scope="bulkScope"
          :items="bulkItems('toolbar')"
          data-catalog-bulk
          @clear="clearSelection"
        >
          <template #lead="{ size, block }">
            <NuxtSelect
              v-model="bulkSurface"
              :items="bulkSurfaceItems"
              :size="size"
              :class="block ? 'w-full' : 'min-w-56'"
              aria-label="Aplicar seleção em"
            />
          </template>
          <template #price><ReuseBulkPrice /></template>
        </OperatorBulkBar>
      </template>
    </OperatorPageHeader>

    <section class="flex min-h-0 flex-1 flex-col gap-4 p-4 sm:p-6">
      <NuxtAlert
        v-if="errorMsg"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :description="errorMsg"
      />
      <!-- Vocação: aviso padrão do conjunto mínimo, em `info` (serve só ao B.I.;
           não pede pressa). A ação repete a cor do aviso (PR #1545). -->
      <NuxtAlert
        v-if="vocation"
        color="info"
        variant="subtle"
        icon="i-lucide-tags"
        :title="vocation.headline"
        :description="vocation.names"
        :actions="[
          {
            label: 'Classificar',
            color: 'info',
            variant: 'outline',
            onClick: classifyVocation,
          },
        ]"
        data-testid="vocation-notice"
      />
      <NuxtAlert
        v-if="orderDraft"
        color="warning"
        variant="subtle"
        icon="i-lucide-list-restart"
        :title="
          orderSaving
            ? 'Confirmando a ordenação…'
            : 'A ordenação ainda precisa de conferência'
        "
      >
        <template #description
          ><div class="space-y-2">
            <p>
              {{
                orderSaving
                  ? "Confirmando a ordenação…"
                  : "A ordenação ainda precisa de conferência. Seu arraste foi preservado."
              }}
            </p>
            <p>
              Seu arraste: {{ orderDraft.ordered.map(orderLabel).join(" → ") }}
            </p>
            <p v-if="!orderSaving">
              Ordem atual:
              {{
                currentOrder.map(orderLabel).join(" → ") ||
                "Abra a coleção deste arraste para conferir."
              }}
            </p>
            <div v-if="!orderSaving" class="flex flex-wrap gap-2">
              <NuxtButton
                type="button"
                label="Verificar esta gravação"
                @click="saveOrderDraft(false, true)"
              />
              <NuxtButton
                v-if="canReviewOrder"
                type="button"
                label="Aplicar meu arraste à ordem atual"
                color="warning"
                variant="outline"
                @click="saveOrderDraft(true)"
              />
              <NuxtButton
                type="button"
                label="Descartar o rascunho de ordem"
                color="neutral"
                variant="ghost"
                @click="orderDraft = null"
              />
            </div></div
        ></template>
      </NuxtAlert>

      <NuxtCard
        v-if="publicationDraft"
        aria-label="Prévia de publicação"
      >
        <template #header
          ><h2 class="font-semibold">
            Confira {{ publicationDraft.preview.cells.length }} células em
            {{ surfaceLabel(publicationDraft.surface) }}
          </h2></template
        >
        <div class="space-y-3">
          <p class="text-sm text-muted-foreground">
            Esta prévia mostra o escopo da decisão. Após confirmar, acompanhe a
            sincronização das plataformas separadamente nas células.
          </p>
          <ul class="max-h-64 space-y-1 overflow-auto text-sm">
            <li
              v-for="cell in publicationDraft.preview.cells"
              :key="`${cell.sku}:${cell.surface_ref}:${cell.tier}`"
            >
              {{ cell.sku }} · {{ surfaceLabel(cell.surface_ref)
              }}<span v-if="cell.tier"> · mínimo {{ cell.tier }}</span
              >: {{ publicationState(cell.before) }} →
              {{ publicationState(cell.after) }}
            </li>
            <li
              v-for="cell in publicationDraft.preview.skipped"
              :key="`${cell.sku}:${cell.surface_ref}`"
            >
              {{ cell.sku }} · {{ surfaceLabel(cell.surface_ref) }}:
              {{ cell.reason }} Nenhuma alteração.
            </li>
          </ul>
        </div>
        <template #footer>
          <div class="flex flex-wrap gap-2">
            <NuxtButton
              type="button"
              label="Confirmar este lote"
              :disabled="bulkBusy"
              @click="confirmPublication"
            />
            <NuxtButton
              type="button"
              label="Atualizar esta prévia"
              color="neutral"
              variant="outline"
              :disabled="bulkBusy"
              @click="reviewPublication"
            />
            <NuxtButton
              type="button"
              label="Descartar esta prévia"
              color="neutral"
              variant="ghost"
              :disabled="bulkBusy"
              @click="publicationDraft = null"
            />
          </div>
        </template>
      </NuxtCard>

      <!-- A matriz é a tabela da suíte (`OperatorTable`, compacta por padrão): colunas
           dinâmicas, Produto fixado à esquerda e o ⋯ à direita, cabeçalho preso e a
           rolagem por dentro do cartão (`fill`). -->
      <OperatorTable
        v-model:row-selection="catalogRowSelection"
        :data="displayRows"
        :columns="catalogColumns"
        :row-key="(row: CatalogRowProjection) => row.sku"
        :row-label="(row: CatalogRowProjection) => row.name"
        :row-class="catalogRowClass"
        :loading="pending"
        :error="Boolean(error)"
        what="o catálogo"
        :error-description="matrix ? 'Exibindo a última leitura disponível.' : ''"
        empty-icon="i-lucide-package-search"
        :empty-title="
          Object.keys(filters).length || query.trim()
            ? 'Nenhum produto com esses filtros.'
            : `Nenhum produto ${activeCollection ? `na coleção ${activeCollection.name}` : 'no catálogo'}.`
        "
        selectable
        pinned="product"
        pinned-end="actions"
        fill
        view-key="orders-catalog"
        caption="Produtos e disponibilidade por canal"
        data-catalog-matrix
        @retry="refresh()"
      >
        <template v-if="Object.keys(filters).length" #empty-actions>
          <NuxtButton
            label="Limpar filtros"
            color="neutral"
            variant="outline"
            @click="filters = {}"
          />
        </template>

          <template
            v-for="surface in surfaces"
            :key="`head-${surface.ref}`"
            #[`${surfaceColumnId(surface.ref)}-header`]
          >
            <div class="flex flex-col gap-0.5">
              <span
                class="flex items-center gap-1 text-muted-foreground"
                :title="
                  surface.transactional
                    ? surface.name
                    : `${surface.name}: feed (só exibe, não vende)`
                "
                data-surface-head
              >
                <Icon
                  :name="surfaceDisplayIcon(surface)"
                  class="size-3.5 shrink-0"
                  :class="
                    surface.transactional
                      ? 'text-muted-foreground'
                      : 'text-primary/70'
                  "
                />
                <span class="op-eyebrow whitespace-nowrap">{{
                  surface.short_name
                }}</span>
                <NuxtButton
                  v-if="surface.output_path"
                  :to="`${djangoBase}${surface.output_path}`"
                  target="_blank"
                  icon="i-lucide-external-link"
                  color="neutral"
                  variant="ghost"
                  square
                  :aria-label="`Abrir ${surface.name}`"
                  :title="`Abrir ${surface.name}`"
                  @click.stop
                />
              </span>
              <NuxtBadge
                v-if="syncBadge(surface.sync_status)"
                :color="syncColor(surface.sync_status)"
                :label="syncBadge(surface.sync_status)!.label"
                :title="syncBadge(surface.sync_status)!.title"
              />
            </div>
          </template>

          <template #product-cell="{ row: tableRow }">
            <template v-for="row in [tableRow.original]" :key="row.sku">
              <div
                :data-dragkey="row.sku"
                class="flex items-center gap-3 sm:min-w-[260px]"
              >
                <!-- handle de arrastar (pointer events): aparece só quando a coleção ativa é reordenável -->
                <span v-if="canReorderRows" class="touch-none">
                  <NuxtButton
                    type="button"
                    icon="i-lucide-grip-vertical"
                    color="neutral"
                    variant="ghost"
                    square
                    aria-label="Arrastar para reordenar"
                    aria-keyshortcuts="ArrowUp ArrowDown"
                    aria-description="Use as setas para cima ou para baixo para mover este produto."
                    title="Arrastar ou usar as setas para reordenar nesta coleção"
                    @pointerdown="rowPointerDown(row.sku, $event)"
                    @keydown="rowKeyDown(row.sku, $event)"
                    @click.stop
                  />
                </span>
                <div class="flex min-w-0 flex-1 items-center gap-3">
                  <!-- UAvatar mantém foto e fallback na mesma geometria canônica. -->
                  <NuxtButton
                    v-if="row.image_url && !brokenImages.has(row.sku)"
                    color="neutral"
                    variant="ghost"
                    square
                    :aria-label="`Ampliar foto de ${row.name}`"
                    :data-catalog-thumb="row.sku"
                    @click.stop.prevent="
                      zoom = { url: row.image_url, name: row.name }
                    "
                  >
                    <NuxtAvatar
                      :src="row.image_url"
                      :alt="row.name"
                      size="md"
                      :class="
                        rowStatuses[row.sku]?.off ? 'opacity-50 grayscale' : ''
                      "
                      @error="imageFailed(row.sku)"
                    />
                  </NuxtButton>
                  <!-- Sem foto (ou foto quebrada), o fallback continua sendo UAvatar. -->
                  <span
                    v-else
                    class="inline-flex shrink-0 p-1.5"
                    aria-hidden="true"
                    data-letter-tile
                  >
                    <NuxtAvatar
                      :text="letterTile(row.name).letter"
                      color="primary"
                      size="md"
                      :class="
                        rowStatuses[row.sku]?.off ? 'opacity-50 grayscale' : ''
                      "
                    />
                  </span>
                  <div class="flex min-w-0 flex-col">
                    <span
                      class="flex flex-wrap items-center gap-1.5 font-medium"
                      :class="
                        rowStatuses[row.sku]?.off
                          ? 'text-muted-foreground'
                          : 'text-foreground'
                      "
                    >
                      <span>{{ row.name }}</span>
                      <NuxtBadge
                        v-if="rowStatuses[row.sku]?.label"
                        :color="
                          rowStatuses[row.sku]?.tone === 'danger'
                            ? 'error'
                            : rowStatuses[row.sku]?.tone === 'amber'
                              ? 'warning'
                              : 'neutral'
                        "
                        :label="rowStatuses[row.sku]?.label"
                        :title="rowStatuses[row.sku]?.hint || undefined"
                      />
                      <!-- esgotado que repõe por produção: o próximo lote reativa sozinho -->
                      <span
                        v-if="row.sold_out && row.replenish_qty"
                        class="shrink-0 text-xs font-normal text-muted-foreground"
                        >Repõe {{ row.replenish_qty }} no lote</span
                      >
                      <!-- estoque baixo (produto ainda ativo): aviso discreto -->
                      <NuxtBadge
                        v-else-if="!rowStatuses[row.sku]?.off && row.low_stock"
                        color="warning"
                        :label="`Resta ${row.stock_qty}`"
                      />
                      <!-- sync com erro em N plataforma(s): salta à vista + atalho p/ reenviar tudo -->
                      <NuxtButton
                        v-if="rowSyncErrors(row)"
                        type="button"
                        icon="i-lucide-triangle-alert"
                        :label="String(rowSyncErrors(row))"
                        color="error"
                        variant="ghost"
                        :disabled="
                          isBusy(productKey(row.sku)) ||
                          !row.resync_action?.enabled
                        "
                        :title="`Erro de sincronização em ${rowSyncErrors(row)} plataforma(s). Toque para reenviar tudo.`"
                        @click.stop="resyncRow(row)"
                      />
                    </span>
                    <!-- uma linha só: com a coluna em largura fixa, sem `nowrap` o SKU +
                         preço + coleção quebram e a linha da matriz cresce. -->
                    <span
                      class="flex items-center gap-1.5 overflow-hidden whitespace-nowrap text-xs text-muted-foreground"
                    >
                      <span class="shrink-0 font-mono">{{ row.sku }}</span>
                      <span class="shrink-0 text-muted-foreground/40">·</span>
                      <span class="shrink-0 tabular-nums">{{
                        row.base_price_display
                      }}</span>
                      <template v-if="row.primary_collection_name"
                        ><span class="shrink-0 text-muted-foreground/40">·</span
                        ><span class="truncate">{{
                          row.primary_collection_name
                        }}</span></template
                      >
                    </span>
                  </div>
                </div>
              </div>
            </template>
          </template>

          <!-- O cabeçalho da coluna do ⋯ é só para o leitor de tela. Um `header: ""`
               virava um texto vazio que o servidor não manda, e a hidratação acusava
               mismatch na carga direta. -->
          <template #actions-header>
            <span class="sr-only">Ações</span>
          </template>

          <!-- ⋯ da linha: as ações menos corriqueiras (editar, pausar tudo, publicar) -->
          <template #actions-cell="{ row: tableRow }">
            <OperatorMoreMenu
              :items="rowMenuItems(tableRow.original)"
              :label="`Mais ações de ${tableRow.original.name}`"
            />
          </template>

          <template
            v-for="surface in surfaces"
            :key="`cell-${surface.ref}`"
            #[`${surfaceColumnId(surface.ref)}-cell`]="{ row: tableRow }"
          >
            <template
              v-for="row in [tableRow.original]"
              :key="`${row.sku}-${surface.ref}`"
            >
              <template
                v-for="cell in [cellFor(row, surface.ref)]"
                :key="cell.surface_ref"
              >
                <div
                  v-if="cell.in_listing"
                  class="flex items-center justify-center gap-1"
                  :class="rowStatuses[row.sku]?.off ? 'opacity-50 grayscale' : ''"
                >
                  <!-- ÁREA 1 — toggle: verde=ligado&disponível · cinza=pausado (posição off).
                     Linha "fora" (esgotado/oculto) mantém a POSIÇÃO e esmaece a célula, como a
                     foto da linha: o `neutral` do Switch pinta escuro e gritava mais que o verde.
                     Vale para canal (vende) E feed (só exibe) — a mesma pausa por item. -->
                  <NuxtSwitch
                    color="success"
                    :model-value="cell.is_sellable"
                    :disabled="
                      isBusy(cellKey(row.sku, cell.surface_ref)) ||
                      !cell.action?.enabled
                    "
                    :aria-label="
                      cell.is_sellable
                        ? `${cellView(row, cell).label}. Toque para pausar neste ${surfaceWord(cell)}.`
                        : `Ativar neste ${surfaceWord(cell)}`
                    "
                    :title="
                      cell.is_sellable
                        ? `${cellView(row, cell).label}. Toque para pausar neste ${surfaceWord(cell)}.`
                        : `Pausado. Toque para ativar neste ${surfaceWord(cell)}.`
                    "
                    @update:model-value="toggleCell(row, cell)"
                  />

                  <span
                    v-if="cell.pause_audit"
                    class="max-w-40 text-xs text-muted-foreground"
                    >{{ cell.pause_audit }}</span
                  >

                  <!-- Feed não vende: sem divisória nem preço — só a pausa por item. -->
                  <template v-if="isCellTransactional(cell)">
                    <!-- divisória: deixa claro que toggle e preço são controles distintos -->
                    <NuxtSeparator orientation="vertical" class="h-5" />

                    <!-- ÁREA 2 — preço, ao lado do toggle: base = ícone $ apagado; ALTERADO =
                     seta ↑/↓ colorida + valor. title = valor; clique = popover. -->
                    <NuxtPopover
                      :open="isEditing(row.sku, cell.surface_ref)"
                      :content="{ align: 'center' }"
                      @update:open="
                        (v) => {
                          if (!v) void closePrice();
                        }
                      "
                    >
                      <NuxtButton
                        type="button"
                        color="neutral"
                        variant="ghost"
                        :disabled="
                          isBusy(cellKey(row.sku, cell.surface_ref)) ||
                          !cell.action?.enabled
                        "
                        :title="priceTitle(row, cell)"
                        :aria-label="`Preço em ${surfaceName(cell.surface_ref)}: ${cell.price_display}. Toque para editar.`"
                        @click="startEdit(row, cell)"
                      >
                        <span
                          v-if="cellPrice(row, cell).differs"
                          class="flex items-center gap-0.5"
                        >
                          <Icon
                            :name="
                              cellPrice(row, cell).delta === 'up'
                                ? 'lucide:arrow-up'
                                : 'lucide:arrow-down'
                            "
                            class="size-2.5 shrink-0"
                            :class="
                              rowStatuses[row.sku]?.off
                                ? 'text-muted-foreground/60'
                                : cellPrice(row, cell).delta === 'up'
                                  ? 'text-warning'
                                  : 'text-success'
                            "
                          />
                          <span
                            class="text-xs font-semibold tabular-nums"
                            :class="
                              cell.is_sellable
                                ? 'text-foreground'
                                : 'text-muted-foreground line-through'
                            "
                            >{{ cell.price_display.replace("R$ ", "") }}</span
                          >
                        </span>
                        <Icon
                          v-else
                          name="lucide:circle-dollar-sign"
                          class="size-3.5 text-muted-foreground/40"
                        />
                      </NuxtButton>
                      <template #content>
                        <div class="w-64 space-y-3 p-4">
                          <NuxtFormField
                            :label="`Preço · ${surfaceName(cell.surface_ref)}`"
                            :description="`Base do produto: ${row.base_price_display}`"
                          >
                            <NuxtInput
                              v-model="priceInput"
                              class="w-full"
                              type="text"
                              inputmode="decimal"
                              autofocus
                              @keyup.enter="commitPrice(row, cell)"
                              @keyup.esc="closePrice()"
                            />
                          </NuxtFormField>
                          <NuxtAlert
                            v-if="priceConflict(cell)"
                            color="warning"
                            variant="subtle"
                            title="O preço mudou"
                            :description="`Agora: ${cell.price_display}. Seu valor digitado foi mantido.`"
                            :actions="[
                              {
                                label: 'Conferir e manter meu preço',
                                color: 'warning',
                                variant: 'outline',
                                onClick: () => keepPrice(cell),
                              },
                            ]"
                          />
                          <div class="flex justify-end gap-2">
                            <NuxtButton
                              color="neutral"
                              variant="ghost"
                              label="Cancelar"
                              @click="closePrice()"
                            />
                            <NuxtButton
                              label="Salvar preço"
                              :disabled="
                                priceConflict(cell) ||
                                isBusy(cellKey(row.sku, cell.surface_ref))
                              "
                              @click="commitPrice(row, cell)"
                            />
                          </div>
                        </div>
                      </template>
                    </NuxtPopover>
                  </template>

                  <!-- ÁREA 3 — selo de SYNC (produto × plataforma), inline ao lado do preço,
                     só em superfície que projeta. Acionável (erro/sincronizando/nunca) =
                     botão "reenviar agora"; senão só informa. Vem por último para não
                     empurrar o toggle de lugar nas colunas em que não aparece. -->
                  <template v-if="cellSync(cell).show">
                    <NuxtButton
                      v-if="cellSync(cell).actionable"
                      type="button"
                      :icon="cellSync(cell).icon"
                      :color="cellSync(cell).color"
                      variant="ghost"
                      square
                      :disabled="
                        isBusy(cellKey(row.sku, cell.surface_ref)) ||
                        !row.resync_action?.enabled
                      "
                      :title="`${cellSync(cell).label}${cell.sync_error ? ' · ' + cell.sync_error : ''}. Toque para reenviar agora.`"
                      :aria-label="`${cellSync(cell).label} em ${surfaceName(cell.surface_ref)}. Toque para reenviar agora.`"
                      @click="resyncCell(row, cell)"
                    />
                    <Icon
                      v-else
                      :name="cellSync(cell).icon"
                      class="size-4 shrink-0"
                      :class="{
                        'text-success': cellSync(cell).color === 'success',
                        'text-warning': cellSync(cell).color === 'warning',
                        'text-error': cellSync(cell).color === 'error',
                        'text-muted-foreground':
                          cellSync(cell).color === 'neutral',
                      }"
                      :title="cellSync(cell).label"
                      :aria-label="`${cellSync(cell).label} em ${surfaceName(cell.surface_ref)}`"
                    />
                  </template>
                </div>
                <div
                  v-else
                  class="grid h-10 place-items-center rounded-md text-xs text-muted-foreground/30"
                >
                  —
                </div>
              </template>
            </template>
          </template>
      </OperatorTable>
    </section>

    <!-- A barra de seleção da suíte: abaixo do `lg`, na base (a do topo mora no
         `#selection` do cabeçalho e toma o lugar da toolbar). -->
    <OperatorBulkBar
      v-if="selected.size"
      placement="base"
      :count="selected.size"
      :scope="bulkScope"
      :items="bulkItems('base')"
      data-catalog-bulk
      @clear="clearSelection"
    >
      <template #lead="{ size, block }">
        <NuxtSelect
          v-model="bulkSurface"
          :items="bulkSurfaceItems"
          :size="size"
          :class="block ? 'w-full' : 'min-w-56'"
          aria-label="Aplicar seleção em"
        />
      </template>
      <template #price><ReuseBulkPrice /></template>
    </OperatorBulkBar>

    <!-- painel de produto (edição completa, incluindo dados sociais e fiscais) —
         slide-over à direita -->
    <CatalogProductPanel
      :open="detailSku !== null"
      :sku="detailSku"
      :detail="detail"
      :loading="detailLoading"
      :busy="detailSku !== null && isBusy(detailKey(detailSku))"
      :roles="detailRoles"
      :purchase-busy="detailSku !== null && isBusy(`purchase@${detailSku}`)"
      :assist="detailAssist.assist"
      :assist-busy="detailAssist.assistBusy"
      :initial-tab="detailTab"
      :conflict="detailSku ? productConflict(detailSku) : null"
      :error="errorMsg"
      :channel-cells="detailChannelCells"
      :live-availability="detailAvailability"
      :admin-base-url="adminBaseUrl"
      @review-conflict="reviewProductConflict"
      @dirty-change="detailDirty = $event"
      @update:open="
        (v) => {
          if (!v) closeDetail();
        }
      "
      @save="saveDetail"
      @set-purchasable="togglePurchasable"
      @pause-channel="pauseDetailChannel"
    />

    <!-- lightbox canônico: foco preso, Escape e retorno ao disparador são do Reka. -->
    <NuxtModal
      :open="Boolean(zoom)"
      fullscreen
      :title="zoom ? `Foto ampliada de ${zoom.name}` : 'Foto ampliada'"
      @update:open="
        (value) => {
          if (!value) zoom = null;
        }
      "
    >
      <template #body>
        <figure v-if="zoom" class="flex flex-col items-center gap-3">
          <img
            :src="zoom.url"
            :alt="zoom.name"
            class="max-h-[80vh] max-w-[85vw] rounded-lg object-contain"
          />
          <figcaption>{{ zoom.name }}</figcaption>
        </figure>
      </template>
    </NuxtModal>
  </main>
</template>
