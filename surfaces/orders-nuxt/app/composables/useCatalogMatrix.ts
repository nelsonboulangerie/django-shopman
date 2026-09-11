import { coalesceRefresh } from "../utils/coalesceRefresh";
import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useOrderIntention } from "./useOrderIntention";
import type { Action, CatalogPricePreview } from "~/generated/ordersContract";
// Catalog matrix read/write. Single source for the produto × superfície grid:
//   - useFetch the canonical matrix projection (GET /api/v1/backstage/catalog/);
//   - poll every 30s, coalescing wake and mutation refreshes;
//   - cell + bulk mutations POST through the django proxy (CSRF handled there),
//     then reconcile via refresh (the backend owns the availability rules).
import type {
  AiAssistResponse,
  AssistableField,
  CatalogMatrixProjection,
  CatalogMatrixResponse,
  ProductDetailPatch,
  ProductDetailProjection,
  ProductDetailResponse,
  ProductEditConflict,
  ProductSocial,
} from "~/types/catalog";

export interface CellPatch {
  is_published?: boolean;
  is_sellable?: boolean;
  price_q?: number;
}

// Escrita PIM: um subconjunto dos campos sociais (merge parcial no backend).
export type SocialPatch = Partial<Omit<ProductSocial, "has_data">>;

export function useCatalogMatrix(collectionRef?: Ref<string>) {
  const intentions = useOrderIntention();
  const detailActions = new Map<string, Action>();
  const productConflicts = ref<Record<string, ProductEditConflict>>({});
  const productConflict = (sku: string) => productConflicts.value[sku] ?? null;
  function acknowledgeProductConflict(sku: string): ProductDetailProjection | null {
    const conflict = productConflicts.value[sku];
    if (!conflict?.action) return null;
    detailActions.set(sku, conflict.action);
    delete productConflicts.value[sku];
    clearError();
    return conflict.product;
  }
  const path = "/api/v1/backstage/catalog/";
  // Reactive collection filter → server-side row scoping (smart-aware via
  // product_queryset). Changing the ref refetches the matrix.
  const collection = collectionRef ?? ref("");
  const resourceKey = useOperatorResourceKey("catalog-matrix");
  const { data, pending, error, refresh: fetchMatrix } = useFetch<CatalogMatrixResponse>(path, {
    key: computed(() => `${resourceKey}:${collection.value}`),
    server: true,
    query: { collection },
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });

  const refresh = coalesceRefresh(() => fetchMatrix());
  const matchesScope = (value: CatalogMatrixResponse | null | undefined) => (value?.collection_ref ?? "") === collection.value;
  const lastConfirmed = shallowRef<CatalogMatrixProjection | null>(matchesScope(data.value) ? data.value?.matrix ?? null : null);
  watch(collection, () => { lastConfirmed.value = null; }, { flush: "sync" });
  watch([data, error], ([value, failure]) => {
    if (value?.matrix && !failure && matchesScope(value)) lastConfirmed.value = value.matrix;
  }, { flush: "sync" });
  const matrix = computed<CatalogMatrixProjection | null>(() => matchesScope(data.value) ? data.value?.matrix ?? lastConfirmed.value : lastConfirmed.value);

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  const onVisible = () => { if (document.visibilityState === "visible") refresh(); };
  onMounted(() => {
    pollTimer = setInterval(() => refresh(), 30_000);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  // Per-cell in-flight guard: a cell key is `${sku}@${surface}`.
  const busy = ref<Set<string>>(new Set());
  const isBusy = (key: string) => busy.value.has(key);
  const cellKey = (sku: string, surface: string) => `${sku}@${surface}`;

  const errorMsg = ref("");
  const clearError = () => (errorMsg.value = "");
  function canWrite() {
    if (!error.value && matchesScope(data.value)) return true;
    errorMsg.value = "A leitura do catálogo está desatualizada. Atualize antes de aplicar; seu rascunho foi mantido.";
    return false;
  }
  async function refreshAfterCommit() {
    try { await refresh(); }
    catch { errorMsg.value = "Alteração confirmada. A leitura atualizada falhou; atualize antes de continuar."; }
    if (error.value) errorMsg.value = "Alteração confirmada. A leitura atualizada falhou; atualize antes de continuar.";
  }

  async function setCell(sku: string, surface: string, patch: CellPatch, observed?: Action): Promise<boolean> {
    const key = cellKey(sku, surface);
    if (busy.value.has(key) || !canWrite()) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      const action = observed ?? matrix.value?.rows.find(row => row.sku === sku)?.cells.find(cell => cell.surface_ref === surface)?.action;
      await intentions.executePath(`catalog:cell:${sku}:${surface}`, "/api/v1/backstage/catalog/cell/", action ?? undefined,
        { sku, surface_ref: surface, ...patch });
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, error instanceof Error ? error.message : "Falha ao atualizar. Tente de novo.");
      useSonner.error(errorMsg.value);
      if (httpError(error).status === 409) {
        try { await refresh(); } catch { errorMsg.value += " A leitura atualizada também falhou."; }
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
      const action = matrix.value?.rows.find(row => row.sku === sku)?.product_action;
      await intentions.executePath(`catalog:product:${sku}`, "/api/v1/backstage/catalog/product/", action ?? undefined, { sku, patch });
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, error instanceof Error ? error.message : "Falha ao atualizar. Tente de novo.");
      useSonner.error(errorMsg.value);
      if (httpError(error).status === 409) {
        try { await refresh(); } catch { errorMsg.value += " A leitura atualizada também falhou."; }
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
  ): Promise<number | null> {
    if (bulkBusy.value || !canWrite()) return null;
    clearError();
    bulkBusy.value = true;
    try {
      const res = await $fetch<{ count: number }>("/api/v1/backstage/catalog/bulk/", {
        method: "POST",
        body: { surface_ref: surface, ...scope, ...patch },
      });
      await refreshAfterCommit();
      const count = res?.count ?? 0;
      useSonner.success(`${count} item(ns) atualizado(s).`);
      return count;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha na ação em lote.");
      useSonner.error(errorMsg.value);
      return null;
    } finally {
      bulkBusy.value = false;
    }
  }

  // Reprecificação em lote: op set|pct|delta, value em centavos (set/delta) ou
  // pontos percentuais (pct). Escopo por coleção OU lista de skus.
  async function previewBulkPrice(surface: string, scope: { collection_ref?: string; skus?: string[] }, patch: { op: "set" | "pct" | "delta"; value: number }): Promise<CatalogPricePreview | null> {
    if (bulkBusy.value) return null;
    bulkBusy.value = true;
    try {
      const response = await $fetch<{ preview: CatalogPricePreview }>("/api/v1/backstage/catalog/bulk-price/", { method: "POST", body: { surface_ref: surface, ...scope, ...patch, preview: true } });
      return response.preview;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Não foi possível preparar a prévia.");
      useSonner.error(errorMsg.value);
      return null;
    } finally { bulkBusy.value = false; }
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
      const body = { surface_ref: surface, ...scope, ...patch, base_revision: preview.base_revision, expected_actor_id: preview.expected_actor_id };
      const result = await intentions.executePath("catalog:bulk-price", "/api/v1/backstage/catalog/bulk-price/", {
        enabled: true, reason: "", payload_schema: body,
      }, body);
      await refreshAfterCommit();
      const count = result.count ?? 0;
      useSonner.success(`${count} preço(s) atualizado(s). Acompanhe a sincronização nas células.`);
      return count;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, error instanceof Error ? error.message : "Não foi possível confirmar a alteração de preços.");
      useSonner.error(errorMsg.value);
      try { await refresh(); } catch { errorMsg.value += " A leitura atualizada também falhou."; }
      return null;
    } finally { bulkBusy.value = false; }
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
      await $fetch("/api/v1/backstage/catalog/resync/", {
        method: "POST",
        body: channelRef ? { sku, channel_ref: channelRef } : { sku },
      });
      useSonner.success(channelRef ? "Reenvio agendado." : "Reenvio agendado em todos os canais.");
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao reenviar. Tente de novo.");
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
      await $fetch("/api/v1/backstage/catalog/social/", {
        method: "POST",
        body: { sku, ...patch },
      });
      useSonner.success("Dados do produto salvos.");
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao salvar. Confira os campos.");
      useSonner.error(errorMsg.value);
      return false;
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

  async function fetchProductDetail(sku: string): Promise<ProductDetailProjection | null> {
    clearError();
    try {
      const res = await $fetch<ProductDetailResponse>(`/api/v1/backstage/catalog/product/${encodeURIComponent(sku)}/`);
      if (res?.action) detailActions.set(sku, res.action);
      delete productConflicts.value[sku];
      return res?.product ?? null;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao carregar o produto.");
      useSonner.error(errorMsg.value);
      return null;
    }
  }

  async function saveProductDetail(sku: string, patch: ProductDetailPatch): Promise<boolean> {
    const key = detailKey(sku);
    if (busy.value.has(key) || productConflicts.value[sku] || !canWrite()) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      await intentions.executePath(`catalog:${sku}:detail`, `/api/v1/backstage/catalog/product/${encodeURIComponent(sku)}/`,
        detailActions.get(sku), { patch });
      useSonner.success("Produto salvo.");
      try { await refresh(); }
      catch { errorMsg.value = "Produto salvo. A leitura do catálogo falhou; atualize antes de continuar."; }
      return true;
    } catch (error) {
      const failure = httpError(error);
      const data = failure.data as Partial<ProductEditConflict> | null;
      if (failure.status === 409 && data?.product?.sku === sku && data.action && Array.isArray(data.conflicting_fields)) {
        productConflicts.value[sku] = data as ProductEditConflict;
      }
      errorMsg.value = httpErrorMessage(error, "Falha ao salvar. Confira os campos.");
      useSonner.error(errorMsg.value);
      return false;
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
  const aiAssistKey = (sku: string, field: AssistableField) => `ai-assist-${sku}-${field}`;

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
      const res = await $fetch<AiAssistResponse>("/api/v1/backstage/catalog/ai-assist/", {
        method: "POST",
        body: { sku, field, current_value: currentValue, context: {} },
      });
      return res?.suggestion ?? "";
    } catch (error) {
      const { status } = httpError(error);
      if (status === 503) {
        useSonner.info(httpErrorMessage(error, "Sugestão de IA não está configurada nesta loja."));
      } else {
        errorMsg.value = httpErrorMessage(error, "Não consegui sugerir agora. Tente de novo.");
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
    return data.value?.actions?.find(action => action.ref === operation && action.payload_schema.ref === ref_);
  }
  async function reorder(operation: string, ref_: string, ordered: string[], observed?: Action): Promise<boolean> {
    const key = `curation:${operation}:${ref_}`;
    if (!canWrite() || busy.value.has(key)) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      await intentions.executePath(key, `/api/v1/backstage/catalog/${operation}/`, observed ?? curationAction(operation, ref_),
        { ref: ref_, [operation === "reorder-items" ? "ordered_skus" : "ordered_refs"]: ordered });
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, error instanceof Error ? error.message : "Falha ao reordenar.");
      useSonner.error(errorMsg.value);
      try { await refresh(); } catch { errorMsg.value += " A leitura atualizada também falhou."; }
      return false;
    } finally {
      const next = new Set(busy.value); next.delete(key); busy.value = next;
    }
  }
  async function verifyOrder(operation: string, ref_: string): Promise<boolean> {
    try {
      const result = await intentions.checkPath(`curation:${operation}:${ref_}`, `/api/v1/backstage/catalog/${operation}/`);
      if (result.outcome !== "applied") { errorMsg.value = "Resultado ainda desconhecido. O arraste foi mantido; consulte novamente."; return false; }
      await refreshAfterCommit();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, error instanceof Error ? error.message : "Falha ao consultar a ordenação.");
      return false;
    }
  }
  const reorderCollections = (ordered: string[], action?: Action) => reorder("reorder-collections", "", ordered, action);
  const reorderItems = (ref_: string, ordered: string[], action?: Action) => reorder("reorder-items", ref_, ordered, action);

  return {
    matrix, pending, error, refresh, isBusy, cellKey, productKey, socialKey, detailKey, errorMsg, clearError,
    setCell, setProduct, bulkSet, bulkPrice, previewBulkPrice, resync, saveSocial, fetchProductDetail, saveProductDetail,
    reorderCollections, reorderItems, curationAction, verifyOrder, bulkBusy, aiAssist, aiAssistKey, productConflict, acknowledgeProductConflict,
  };
}
