import { useBackstageEvents } from "./useBackstageEvents";
import { useOrderIntention } from "./useOrderIntention";
import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useReadMetadata } from "./useReadMetadata";
import { coalesceRefresh } from "../utils/coalesceRefresh";
import type { CatalogBindingReviewProjection, CatalogReviewItem } from "~/generated/ordersContract";

type ReviewResponse = import("~/types/readMetadata").ReadMetadata & { board: CatalogBindingReviewProjection };

export function useCatalogBindings(channel: string) {
  const base = `/api/v1/backstage/catalog/channels/${encodeURIComponent(channel)}`;
  const selected = ref("");
  const { data, pending, error, refresh: fetchReview } = useFetch<ReviewResponse>(`${base}/review/`, {
    key: useOperatorResourceKey(`catalog-bindings:${channel}`),
    query: computed(() => selected.value ? { snapshot_id: selected.value } : {}), dedupe: "defer", onResponseError: operatorSessionOnError,
  });
  const refresh = coalesceRefresh(() => fetchReview());
  const { realtime } = useBackstageEvents("catalog", refresh);
  const readMetadata = useReadMetadata(data, error);
  const lastConfirmed = shallowRef<ReviewResponse | null>(data.value ?? null);
  watch([data, error], ([value, failure]) => {
    if (value && !failure && (!selected.value || String(value.board.selected_snapshot?.id ?? "") === selected.value)) {
      lastConfirmed.value = value;
      if (!selected.value && value.board.selected_snapshot) selected.value = String(value.board.selected_snapshot.id);
    }
  }, { immediate: true, flush: "sync" });
  const board = computed(() => lastConfirmed.value?.board ?? null);
  const stale = computed(() => Boolean(error.value) || pending.value || Boolean(selected.value && String(board.value?.selected_snapshot?.id ?? "") !== selected.value));
  const busy = ref(false);
  const message = ref("");
  const intentions = useOrderIntention();

  async function execute(resource: string, path: string, action: CatalogBindingReviewProjection["import_action"] | undefined, body: Record<string, unknown>) {
    if (busy.value || stale.value || !board.value) return false;
    busy.value = true;
    message.value = "";
    try {
      const result = await intentions.executePath(resource, path, action, body);
      const snapshotId = (result as { snapshot_id?: unknown }).snapshot_id;
      if (resource === `catalog-snapshot:${channel}` && typeof snapshotId === "number") selected.value = String(snapshotId);
      message.value = "Gravação local confirmada. Nenhuma alteração enviada à plataforma.";
      try { await refresh(); }
      catch { message.value += " A leitura atualizada falhou; atualize antes de continuar."; }
      return true;
    } catch (failure) {
      message.value = httpErrorMessage(failure, failure instanceof Error ? failure.message : "Não foi possível confirmar a gravação local.");
      if (httpError(failure).status === 409) {
        try { await refresh(); }
        catch { message.value += " Não foi possível reler o vínculo; sua seleção foi mantida."; }
      }
      return false;
    } finally { busy.value = false; }
  }

  function importSnapshot(rawJson: string) {
    return execute(`catalog-snapshot:${channel}`, `${base}/snapshots/`, board.value?.import_action,
      { raw_json: rawJson });
  }

  function bind(item: CatalogReviewItem, sku: string, revision: string) {
    return execute(`catalog-binding:${channel}:${item.item_id}`, `${base}/bindings/`, item.binding_action,
      { snapshot_id: board.value?.selected_snapshot?.id, item_id: item.item_id, sku, base_revision: revision });
  }
  return { board, pending, error, stale, refresh, readMetadata, realtime, selected, busy, message, importSnapshot, bind };
}
