import { useReadMetadata } from "./useReadMetadata";
import { useBackstageEvents } from "./useBackstageEvents";
import { coalesceRefresh } from "../utils/coalesceRefresh";
import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useOrderIntention } from "./useOrderIntention";
import type {
  Action,
  CatalogPricePreview,
  CatalogPublicationPreview,
} from "~/generated/ordersContract";
// Catalog matrix read/write. Single source for the produto × superfície grid:
//   - useFetch the canonical matrix projection (GET /api/v1/backstage/catalog/);
//   - poll every 30s, coalescing wake and mutation refreshes;
//   - cell + bulk mutations POST through the django proxy (CSRF handled there),
//     then reconcile via refresh (the backend owns the availability rules).
import type {
  AiAssistResponse,
  AssistableField,
  BulkCell,
  BulkCellsResponse,
  CatalogMatrixProjection,
  CatalogMatrixResponse,
  CreateProductPayload,
  CreateProductResponse,
  DuplicatePayload,
  DuplicateSnapshot,
  ImportPreview,
  PhotoEnhanceResponse,
  ProductDetailPatch,
  ProductArchiveReceipt,
  ProductDetailProjection,
  ProductDetailResponse,
  ProductDraft,
  ProductEditConflict,
  ProductSocial,
} from "~/types/catalog";

export interface CellPatch {
  min_qty?: string;
  is_published?: boolean;
  is_sellable?: boolean;
  price_q?: number;
}

// Escrita PIM: um subconjunto dos campos sociais (merge parcial no backend).
export type SocialPatch = Partial<Omit<ProductSocial, "has_data">>;

export interface CatalogListOptions {
  /** Busca textual (nome/SKU) — filtrada no BANCO. */
  search?: Ref<string>;
  /** Página corrente (1-based). */
  page?: Ref<number>;
  /** Linhas por página (o servidor tem teto). */
  pageSize?: Ref<number>;
  /** Ordenação: name | sku | price | updated. */
  order?: Ref<string>;
  /** Facetas da FilterBar. As suportadas viram query do SERVIDOR. */
  filters?: Ref<Record<string, string[]>>;
}

export function useCatalogMatrix(
  collectionRef?: Ref<string>,
  list: CatalogListOptions = {},
) {
  const intentions = useOrderIntention();
  const { data: operatorSession } = useNuxtData<{ operator?: { id: number } }>(
    "operator-session",
  );
  const detailActions = new Map<string, Action>();
  const productConflicts = ref<Record<string, ProductEditConflict>>({});
  const productConflict = (sku: string) => productConflicts.value[sku] ?? null;
  function acknowledgeProductConflict(
    sku: string,
  ): ProductDetailProjection | null {
    const conflict = productConflicts.value[sku];
    if (!conflict?.action) return null;
    detailActions.set(sku, conflict.action);
    Reflect.deleteProperty(productConflicts.value, sku);
    clearError();
    return conflict.product;
  }
  const path = "/api/v1/backstage/catalog/";
  // Recorte, busca, ordenação e página são do SERVIDOR: mudar qualquer um
  // refaz a consulta (a chave inclui todos).
  const collection = collectionRef ?? ref("");
  const search = list.search ?? ref("");
  const page = list.page ?? ref(1);
  const pageSize = list.pageSize ?? ref(50);
  const order = list.order ?? ref("name");
  const activeFilters = list.filters ?? ref<Record<string, string[]>>({});
  // TODAS as facetas da FilterBar viram parâmetro do servidor. As listas vão
  // separadas por vírgula ou vazias (vazio = sem recorte, o servidor ignora).
  const facet = (id: string) =>
    computed(() => activeFilters.value[id]?.[0] ?? "");
  const archived = facet("archived");
  const isPublished = facet("is_published");
  const isSellable = facet("is_sellable");
  const hasVocation = facet("has_vocation");
  const pimComplete = facet("pim_complete");
  const surfaceFilter = computed(() =>
    (activeFilters.value["surface"] ?? []).join(","),
  );
  const stockFilter = computed(() =>
    (activeFilters.value["stock"] ?? []).join(","),
  );
  const syncFilter = computed(() =>
    (activeFilters.value["sync_status"] ?? []).join(","),
  );
  const resourceKey = useOperatorResourceKey("catalog-matrix");
  const {
    data,
    pending,
    error,
    refresh: fetchMatrix,
  } = useFetch<CatalogMatrixResponse>(path, {
    key: computed(() =>
      [
        resourceKey,
        collection.value,
        search.value,
        order.value,
        page.value,
        pageSize.value,
        archived.value,
        isPublished.value,
        isSellable.value,
        hasVocation.value,
        pimComplete.value,
        surfaceFilter.value,
        stockFilter.value,
        syncFilter.value,
      ].join(":"),
    ),
    server: true,
    query: {
      collection,
      q: search,
      order,
      page,
      page_size: pageSize,
      archived,
      is_published: isPublished,
      is_sellable: isSellable,
      has_vocation: hasVocation,
      pim_complete: pimComplete,
      surface: surfaceFilter,
      stock: stockFilter,
      sync_status: syncFilter,
    },
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });

  const refresh = coalesceRefresh(() => fetchMatrix());
  const matchesScope = (value: CatalogMatrixResponse | null | undefined) =>
    (value?.collection_ref ?? "") === collection.value &&
    (value?.matrix?.query ?? "") === search.value &&
    (value?.matrix?.page ?? 1) === page.value &&
    (value?.matrix?.order ?? "name") === order.value;
  const readMetadata = useReadMetadata(
    computed(() => (matchesScope(data.value) ? data.value : null)),
    error,
    collection,
  );
  const lastConfirmed = shallowRef<CatalogMatrixProjection | null>(
    matchesScope(data.value) ? (data.value?.matrix ?? null) : null,
  );
  watch(
    collection,
    () => {
      lastConfirmed.value = null;
    },
    { flush: "sync" },
  );
  watch(
    [data, error],
    ([value, failure]) => {
      if (value?.matrix && !failure && matchesScope(value))
        lastConfirmed.value = value.matrix;
    },
    { flush: "sync" },
  );
  const matrix = computed<CatalogMatrixProjection | null>(() =>
    matchesScope(data.value)
      ? (data.value?.matrix ?? lastConfirmed.value)
      : lastConfirmed.value,
  );

  const { realtime } = useBackstageEvents("catalog", refresh);

  // Per-cell in-flight guard: a cell key is `${sku}@${surface}`.
  const busy = ref<Set<string>>(new Set());
  const isBusy = (key: string) => busy.value.has(key);
  const cellKey = (sku: string, surface: string) => `${sku}@${surface}`;

  const errorMsg = ref("");
  const clearError = () => (errorMsg.value = "");
  function canWrite() {
    if (!error.value && matchesScope(data.value)) return true;
    errorMsg.value =
      "A leitura do catálogo está desatualizada. Atualize antes de aplicar; seu rascunho foi mantido.";
    return false;
  }
  async function refreshAfterCommit() {
    try {
      await refresh();
    } catch {
      errorMsg.value =
        "Alteração confirmada. A leitura atualizada falhou; atualize antes de continuar.";
    }
    if (error.value)
      errorMsg.value =
        "Alteração confirmada. A leitura atualizada falhou; atualize antes de continuar.";
  }

  async function setCell(
    sku: string,
    surface: string,
    patch: CellPatch,
    observed?: Action,
  ): Promise<boolean> {
    const key = cellKey(sku, surface);
    if (busy.value.has(key) || !canWrite()) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      const action =
        observed ??
        matrix.value?.rows
          .find((row) => row.sku === sku)
          ?.cells.find((cell) => cell.surface_ref === surface)?.action;
      await intentions.executePath(
        `catalog:cell:${sku}:${surface}`,
        "/api/v1/backstage/catalog/cell/",
        action ?? undefined,
        { sku, surface_ref: surface, ...patch },
      );
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        error instanceof Error
          ? error.message
          : "Falha ao atualizar. Tente de novo.",
      );
      useSonner.error(errorMsg.value);
      if (httpError(error).status === 409) {
        try {
          await refresh();
        } catch {
          errorMsg.value += " A leitura atualizada também falhou.";
        }
      }
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // Product-level pause/publish ("globalzinho") — flips the produto-level switch,
  // which gates every channel at once. Busy key namespaced apart from cell keys.
  const productKey = (sku: string) => `product@${sku}`;
  async function setProduct(
    sku: string,
    patch: Pick<CellPatch, "is_published" | "is_sellable">,
  ): Promise<boolean> {
    const key = productKey(sku);
    if (busy.value.has(key) || !canWrite()) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      const action = matrix.value?.rows.find(
        (row) => row.sku === sku,
      )?.product_action;
      await intentions.executePath(
        `catalog:product:${sku}`,
        "/api/v1/backstage/catalog/product/",
        action ?? undefined,
        { sku, patch },
      );
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        error instanceof Error
          ? error.message
          : "Falha ao atualizar. Tente de novo.",
      );
      useSonner.error(errorMsg.value);
      if (httpError(error).status === 409) {
        try {
          await refresh();
        } catch {
          errorMsg.value += " A leitura atualizada também falhou.";
        }
      }
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // Bulk over a surface, scoped by collection ref OR an explicit sku list.
  const bulkBusy = ref(false);
  async function bulkSet(
    surface: string,
    scope: { collection_ref?: string; skus?: string[] },
    patch: Pick<CellPatch, "is_published" | "is_sellable">,
    preview: CatalogPublicationPreview,
  ): Promise<number | null> {
    if (bulkBusy.value || !canWrite()) return null;
    clearError();
    bulkBusy.value = true;
    try {
      const body = {
        surface_ref: surface,
        ...scope,
        ...patch,
        base_revision: preview.base_revision,
        expected_actor_id: preview.expected_actor_id,
      };
      const res = await intentions.executePath(
        "catalog:bulk-publication",
        "/api/v1/backstage/catalog/bulk/",
        {
          enabled: true,
          reason: "",
          payload_schema: body,
        },
        body,
      );
      await refreshAfterCommit();
      const count = res?.count ?? 0;
      useSonner.success(`${count} item(ns) atualizado(s).`);
      return count;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não deu para publicar as mudanças. Tente de novo.",
      );
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      bulkBusy.value = false;
    }
  }

  async function previewBulkSet(
    surface: string,
    scope: { collection_ref?: string; skus?: string[] },
    patch: Pick<CellPatch, "is_published" | "is_sellable">,
  ): Promise<CatalogPublicationPreview | null> {
    if (bulkBusy.value || !canWrite()) return null;
    clearError();
    bulkBusy.value = true;
    try {
      const result = await $fetch<{ preview: CatalogPublicationPreview }>(
        "/api/v1/backstage/catalog/bulk/",
        {
          method: "POST",
          body: { surface_ref: surface, ...scope, ...patch, preview: true },
        },
      );
      return result.preview;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não foi possível preparar a prévia de publicação.",
      );
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      bulkBusy.value = false;
    }
  }

  // Reprecificação em lote: op set|pct|delta, value em centavos (set/delta) ou
  // pontos percentuais (pct). Escopo por coleção OU lista de skus.
  async function previewBulkPrice(
    surface: string,
    scope: { collection_ref?: string; skus?: string[] },
    patch: { op: "set" | "pct" | "delta"; value: number },
  ): Promise<CatalogPricePreview | null> {
    if (bulkBusy.value) return null;
    bulkBusy.value = true;
    try {
      const response = await $fetch<{ preview: CatalogPricePreview }>(
        "/api/v1/backstage/catalog/bulk-price/",
        {
          method: "POST",
          body: { surface_ref: surface, ...scope, ...patch, preview: true },
        },
      );
      return response.preview;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não foi possível preparar a prévia.",
      );
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      bulkBusy.value = false;
    }
  }

  async function bulkPrice(
    surface: string,
    scope: { collection_ref?: string; skus?: string[] },
    patch: { op: "set" | "pct" | "delta"; value: number },
    preview: CatalogPricePreview,
  ): Promise<number | null> {
    if (bulkBusy.value || !canWrite()) return null;
    clearError();
    bulkBusy.value = true;
    try {
      const body = {
        surface_ref: surface,
        ...scope,
        ...patch,
        base_revision: preview.base_revision,
        expected_actor_id: preview.expected_actor_id,
      };
      const result = await intentions.executePath(
        "catalog:bulk-price",
        "/api/v1/backstage/catalog/bulk-price/",
        {
          enabled: true,
          reason: "",
          payload_schema: body,
        },
        body,
      );
      await refreshAfterCommit();
      const count = result.count ?? 0;
      useSonner.success(
        `${count} preço(s) atualizado(s). Acompanhe a sincronização nas células.`,
      );
      return count;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        error instanceof Error
          ? error.message
          : "Não foi possível confirmar a alteração de preços.",
      );
      useSonner.error(errorMsg.value);
      try {
        await refresh();
      } catch {
        errorMsg.value += " A leitura atualizada também falhou.";
      }
      return null;
    } finally {
      bulkBusy.value = false;
    }
  }

  // ── sync por plataforma (Arc H) ────────────────────────────────────────────
  // Re-enfileira a projeção de um SKU num canal (ou em todos, sem channelRef).
  // Otimista no selo? Não — o push é async (Directive); marca a célula como ocupada
  // e refaz o fetch canônico, que já traz o estado atualizado quando o worker roda.
  async function resync(sku: string, channelRef?: string): Promise<boolean> {
    const key = channelRef ? cellKey(sku, channelRef) : productKey(sku);
    if (busy.value.has(key) || !canWrite()) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      const action = matrix.value?.rows.find(
        (row) => row.sku === sku,
      )?.resync_action;
      await intentions.executePath(
        `catalog:resync:${sku}:${channelRef ?? "*"}`,
        "/api/v1/backstage/catalog/resync/",
        action ?? undefined,
        { sku, ...(channelRef ? { channel_ref: channelRef } : {}) },
      );
      useSonner.success(
        channelRef
          ? "Reenvio agendado."
          : "Reenvio agendado em todos os canais.",
      );
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Falha ao reenviar. Tente de novo.",
      );
      useSonner.error(errorMsg.value);
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // ── PIM social (Arc H) ─────────────────────────────────────────────────────
  // Salva atributos sociais (merge parcial); o backend valida (GTIN/categoria) e
  // re-projeta via o gatilho de Product.save. Retorna false com toast na validação.
  const socialKey = (sku: string) => `social@${sku}`;
  async function saveSocial(sku: string, patch: SocialPatch): Promise<boolean> {
    const key = socialKey(sku);
    if (busy.value.has(key) || !canWrite()) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      // The action must come from the product the person actually read. Fetching
      // a new base just before writing would hide a concurrent edit.
      return await saveProductDetail(sku, { social: patch });
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // ── detalhe do produto (painel de edição) ──────────────────────────────────
  // Busca sob demanda (só quando o painel abre — a matriz não carrega os campos
  // longos) e grava por merge parcial. O PATCH re-projeta no backend; refazemos o
  // fetch canônico da matriz para refletir nome/preço/publicação na linha.
  const detailKey = (sku: string) => `detail@${sku}`;

  async function fetchProductDetail(
    sku: string,
    revisionFields?: string[],
  ): Promise<ProductDetailProjection | null> {
    clearError();
    try {
      const res = await $fetch<ProductDetailResponse>(
        `/api/v1/backstage/catalog/product/${encodeURIComponent(sku)}/`,
      );
      if (res?.action) {
        const previous = detailActions.get(sku);
        if (revisionFields && previous) {
          const fresh = res.action.payload_schema.base_revisions as Record<
            string,
            string
          >;
          const prior = previous.payload_schema.base_revisions as Record<
            string,
            string
          >;
          detailActions.set(sku, {
            ...previous,
            payload_schema: {
              ...previous.payload_schema,
              base_revisions: {
                ...prior,
                ...Object.fromEntries(
                  revisionFields
                    .filter((field) => field in fresh)
                    .map((field) => [field, fresh[field]]),
                ),
              },
            },
          });
        } else detailActions.set(sku, res.action);
      }
      if (!revisionFields) Reflect.deleteProperty(productConflicts.value, sku);
      return res?.product ?? null;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao carregar o produto.");
      useSonner.error(errorMsg.value);
      return null;
    }
  }

  async function saveProductDetail(
    sku: string,
    patch: ProductDetailPatch,
  ): Promise<boolean> {
    const key = detailKey(sku);
    if (busy.value.has(key) || productConflicts.value[sku] || !canWrite())
      return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      await intentions.executePath(
        `catalog:${sku}:detail`,
        `/api/v1/backstage/catalog/product/${encodeURIComponent(sku)}/`,
        detailActions.get(sku),
        { patch },
      );
      useSonner.success("Produto salvo.");
      try {
        await refresh();
      } catch {
        errorMsg.value =
          "Produto salvo. A leitura do catálogo falhou; atualize antes de continuar.";
      }
      return true;
    } catch (error) {
      const failure = httpError(error);
      const data = failure.data as Partial<ProductEditConflict> | null;
      if (
        failure.status === 409 &&
        data?.product?.sku === sku &&
        data.action &&
        Array.isArray(data.conflicting_fields)
      ) {
        productConflicts.value[sku] = data as ProductEditConflict;
      }
      errorMsg.value = httpErrorMessage(
        error,
        "Falha ao salvar. Confira os campos.",
      );
      useSonner.error(errorMsg.value);
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // "Permitir compra": liga/desliga o cadastro de compra do MESMO SKU. Gesto
  // próprio, fora do rascunho do painel — vale na hora, como o interruptor que é.
  // Devolve o detalhe novo (com os selos) ou null na recusa ("é produzido aqui").
  async function setPurchasable(
    sku: string,
    enabled: boolean,
  ): Promise<ProductDetailProjection | null> {
    const key = `purchase@${sku}`;
    if (busy.value.has(key) || !canWrite()) return null;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      const res = await $fetch<{
        product: ProductDetailProjection;
        message: string;
      }>(
        `/api/v1/backstage/catalog/product/${encodeURIComponent(sku)}/purchase/`,
        { method: "POST", body: { enabled } },
      );
      useSonner.success(res.message);
      return res.product;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não foi possível mudar a compra deste produto.",
      );
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // ── assist de IA (sugestão por campo) ──────────────────────────────────────
  // Pede uma sugestão para UM campo e devolve o texto — não grava nada: quem
  // persiste é o salvar do painel, depois de o operador aceitar. Sem chave no
  // deployment o backend responde 503; aqui isso vira um aviso informativo, não
  // um erro: o assist é conveniência, e o operador segue escrevendo à mão.
  const aiAssistKey = (sku: string, field: AssistableField) =>
    `ai-assist-${sku}-${field}`;

  async function aiAssist(
    sku: string,
    field: AssistableField,
    currentValue: string,
  ): Promise<string> {
    const key = aiAssistKey(sku, field);
    if (busy.value.has(key)) return "";
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      const res = await $fetch<AiAssistResponse>(
        "/api/v1/backstage/catalog/ai-assist/",
        {
          method: "POST",
          body: { sku, field, current_value: currentValue, context: {} },
        },
      );
      return res?.suggestion ?? "";
    } catch (error) {
      const { status } = httpError(error);
      if (status === 503) {
        useSonner.info(
          httpErrorMessage(
            error,
            "Sugestão de IA não está configurada nesta loja.",
          ),
        );
      } else {
        errorMsg.value = httpErrorMessage(
          error,
          "Não consegui sugerir agora. Tente de novo.",
        );
        useSonner.error(errorMsg.value);
      }
      return "";
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // The action captured at pointer-down represents the order the person saw.
  function curationAction(operation: string, ref_ = "") {
    return data.value?.actions?.find(
      (action) =>
        action.ref === operation && action.payload_schema.ref === ref_,
    );
  }
  async function reorder(
    operation: string,
    ref_: string,
    ordered: string[],
    observed?: Action,
  ): Promise<boolean> {
    const key = `curation:${operation}:${ref_}`;
    if (!canWrite() || busy.value.has(key)) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      await intentions.executePath(
        key,
        `/api/v1/backstage/catalog/${operation}/`,
        observed ?? curationAction(operation, ref_),
        {
          ref: ref_,
          [operation === "reorder-items" ? "ordered_skus" : "ordered_refs"]:
            ordered,
        },
      );
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        error instanceof Error ? error.message : "Falha ao reordenar.",
      );
      useSonner.error(errorMsg.value);
      try {
        await refresh();
      } catch {
        errorMsg.value += " A leitura atualizada também falhou.";
      }
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }
  async function verifyOrder(
    operation: string,
    ref_: string,
  ): Promise<boolean> {
    try {
      const result = await intentions.checkPath(
        `curation:${operation}:${ref_}`,
        `/api/v1/backstage/catalog/${operation}/`,
      );
      if (result.outcome !== "applied") {
        errorMsg.value =
          "Resultado ainda desconhecido. O arraste foi mantido; consulte novamente.";
        return false;
      }
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        error instanceof Error
          ? error.message
          : "Falha ao consultar a ordenação.",
      );
      return false;
    }
  }
  const reorderCollections = (ordered: string[], action?: Action) =>
    reorder("reorder-collections", "", ordered, action);
  const reorderItems = (ref_: string, ordered: string[], action?: Action) =>
    reorder("reorder-items", ref_, ordered, action);

  // ── criar produto, duplicar e rascunho por GTIN (7.2, onda 1) ─────────────
  // Criar e duplicar passam pela MESMA intenção (revise + recibo) das outras
  // escritas. O rascunho do GTIN é leitura pura: nada é gravado até o aceite.
  const createKey = "catalog:create-product";

  function createAction() {
    return data.value?.actions?.find(
      (action) => action.ref === "create-product",
    );
  }

  async function createProduct(
    payload: CreateProductPayload,
  ): Promise<CreateProductResponse | null> {
    if (busy.value.has(createKey) || !canWrite()) return null;
    clearError();
    busy.value = new Set(busy.value).add(createKey);
    try {
      const result = await intentions.executePath(
        createKey,
        "/api/v1/backstage/catalog/product/create/",
        createAction(),
        payload as unknown as Record<string, unknown>,
      );
      await refreshAfterCommit();
      useSonner.success("Produto criado.");
      return result as unknown as CreateProductResponse;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não foi possível criar o produto. Confira os campos.",
      );
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      const next = new Set(busy.value);
      next.delete(createKey);
      busy.value = next;
    }
  }

  async function fetchProductDraft(gtin: string): Promise<ProductDraft | null> {
    clearError();
    try {
      const response = await $fetch<{ draft: ProductDraft }>(
        "/api/v1/backstage/catalog/product/draft/",
        { method: "POST", body: { gtin } },
      );
      return response.draft;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não foi possível buscar os dados deste código.",
      );
      useSonner.error(errorMsg.value);
      return null;
    }
  }

  async function fetchDuplicateSnapshot(
    sku: string,
  ): Promise<DuplicateSnapshot | null> {
    clearError();
    try {
      return await $fetch<DuplicateSnapshot>(
        "/api/v1/backstage/catalog/product/duplicate/",
        { query: { ref: sku } },
      );
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não foi possível preparar a cópia.",
      );
      useSonner.error(errorMsg.value);
      return null;
    }
  }

  async function duplicateProduct(
    snapshot: DuplicateSnapshot,
    payload: DuplicatePayload,
  ): Promise<CreateProductResponse | null> {
    const key = "catalog:duplicate:" + snapshot.source.sku;
    if (busy.value.has(key) || !canWrite()) return null;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      const result = await intentions.executePath(
        key,
        "/api/v1/backstage/catalog/product/duplicate/",
        snapshot.action,
        { ref: snapshot.source.sku, ...payload },
      );
      await refreshAfterCommit();
      useSonner.success("Produto duplicado. Ele nasce oculto e fora de venda.");
      return result as unknown as CreateProductResponse;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não foi possível duplicar o produto.",
      );
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // Melhoria DETERMINÍSTICA da foto. Sem provedor ligado o servidor responde 503
  // e a tela mostra o aviso: a capability é degradável, não caminho crítico.
  // Grava a foto no storage default e devolve a URL. Sem storage o servidor
  // responde 503 e o painel avisa: a capability é degradável.
  // ── tabelão: salvar o lote numa ida (fatia C) ──────────────────────────────
  // A intenção é a mesma das outras escritas; o lote inteiro vai num POST só.
  async function saveCells(
    cells: BulkCell[],
  ): Promise<BulkCellsResponse | null> {
    const key = "catalog:cells";
    if (!cells.length || busy.value.has(key) || !canWrite()) return null;
    clearError();
    busy.value = new Set(busy.value).add(key);
    const action = {
      ref: "edit-cells",
      kind: "mutation",
      label: "Salvar células",
      enabled: true,
      reason: "",
      method: "POST",
      idempotency: "required",
      payload_schema: {
        base_revision: `catalog-batch-${Date.now()}`,
        expected_actor_id: operatorSession.value?.operator?.id ?? null,
      },
    } as unknown as Action;
    try {
      const result = await intentions.executePath(
        key,
        "/api/v1/backstage/catalog/cells/",
        action,
        { cells } as unknown as Record<string, unknown>,
      );
      await refreshAfterCommit();
      const body = result as unknown as BulkCellsResponse;
      const changed = body.applied?.length ?? 0;
      if (body.conflicts?.length || body.errors?.length) {
        errorMsg.value =
          "Lote aplicado em parte. Confira as linhas marcadas antes de repetir.";
      } else {
        useSonner.success(`${changed} célula(s) atualizada(s).`);
      }
      return body;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não foi possível salvar o lote. Tente de novo.",
      );
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  async function setProductsActive(
    products: { sku: string; base_is_active: boolean }[],
    isActive: boolean,
  ): Promise<ProductArchiveReceipt | null> {
    const key = "catalog:products-active";
    if (!products.length || busy.value.has(key) || !canWrite()) return null;
    clearError();
    busy.value = new Set(busy.value).add(key);
    const action = {
      ref: isActive ? "unarchive-products" : "archive-products",
      kind: "mutation",
      label: isActive ? "Desarquivar" : "Arquivar",
      enabled: true,
      reason: "",
      method: "POST",
      idempotency: "required",
      payload_schema: {
        base_revision: products
          .map((product) => `${product.sku}:${Number(product.base_is_active)}`)
          .join("|"),
        expected_actor_id: operatorSession.value?.operator?.id ?? null,
      },
    } as unknown as Action;
    try {
      const result = await intentions.executePath(
        key,
        "/api/v1/backstage/catalog/products/archive/",
        action,
        { products, is_active: isActive },
      );
      await refreshAfterCommit();
      const receipt = result as unknown as ProductArchiveReceipt;
      if (receipt.conflicts.length || receipt.errors.length) {
        errorMsg.value =
          "Gesto aplicado em parte. Confira as linhas do recibo antes de repetir.";
      } else {
        const count = receipt.applied.filter((row) => row.changed).length;
        useSonner.success(
          isActive
            ? `${count} produto(s) desarquivado(s).`
            : `${count} produto(s) arquivado(s).`,
        );
      }
      return receipt;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        isActive
          ? "Não foi possível desarquivar os produtos."
          : "Não foi possível arquivar os produtos.",
      );
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }
  // ── import CSV: prévia sem gravar e apply com a revisão da prévia (fatia C3)
  async function previewImport(csv: string): Promise<ImportPreview | null> {
    clearError();
    try {
      const response = await $fetch<{ preview: ImportPreview }>(
        "/api/v1/backstage/catalog/product/import/",
        { method: "POST", body: { csv, preview: true } },
      );
      return response.preview;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Não foi possível ler o CSV.");
      useSonner.error(errorMsg.value);
      return null;
    }
  }

  async function applyImport(
    csv: string,
    preview: ImportPreview,
  ): Promise<ImportPreview | null> {
    const key = "catalog:product-import";
    if (busy.value.has(key) || !canWrite()) return null;
    clearError();
    busy.value = new Set(busy.value).add(key);
    const action = {
      ref: "import-products",
      kind: "mutation",
      label: "Importar produtos",
      enabled: true,
      reason: "",
      method: "POST",
      idempotency: "required",
      payload_schema: {
        base_revision: preview.base_revision,
        expected_actor_id: operatorSession.value?.operator?.id ?? null,
      },
    } as unknown as Action;
    try {
      await intentions.executePath(
        key,
        "/api/v1/backstage/catalog/product/import/",
        action,
        { csv } as unknown as Record<string, unknown>,
      );
      await refreshAfterCommit();
      useSonner.success("Importação aplicada.");
      return preview;
    } catch (error) {
      errorMsg.value = httpErrorMessage(
        error,
        "Não foi possível aplicar o CSV.",
      );
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }
  async function uploadPhoto(image: string, filename = ""): Promise<string> {
    const response = await $fetch<{ url: string; name: string }>(
      "/api/v1/backstage/catalog/product/photo/upload/",
      { method: "POST", body: { image, filename } },
    );
    return response.url;
  }
  async function enhancePhoto(image: string): Promise<string> {
    const response = await $fetch<PhotoEnhanceResponse>(
      "/api/v1/backstage/catalog/product/photo/",
      { method: "POST", body: { image } },
    );
    return response.image;
  }
  return {
    readMetadata,
    realtime,
    matrix,
    pending,
    error,
    refresh,
    isBusy,
    cellKey,
    productKey,
    socialKey,
    detailKey,
    errorMsg,
    clearError,
    setCell,
    setProduct,
    bulkSet,
    previewBulkSet,
    bulkPrice,
    previewBulkPrice,
    resync,
    saveSocial,
    fetchProductDetail,
    saveProductDetail,
    setPurchasable,
    reorderCollections,
    reorderItems,
    curationAction,
    verifyOrder,
    bulkBusy,
    aiAssist,
    aiAssistKey,
    productConflict,
    acknowledgeProductConflict,
    createAction,
    createProduct,
    fetchProductDraft,
    fetchDuplicateSnapshot,
    duplicateProduct,
    enhancePhoto,
    uploadPhoto,
    saveCells,
    setProductsActive,
    previewImport,
    applyImport,
  };
}
