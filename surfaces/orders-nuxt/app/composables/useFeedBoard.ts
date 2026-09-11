import { useBackstageEvents } from "./useBackstageEvents";
import { coalesceRefresh } from "../utils/coalesceRefresh";
import { useOrderIntention } from "./useOrderIntention";
import { useOperatorResourceKey } from "./useOperatorResourceKey";
// Feeds (menuboard/Google/Meta) — lê o board + liga/pausa + escolhe coleções.
import type { FeedBoardProjection, FeedBoardResponse } from "~/types/feeds";

export function useFeedBoard() {
  const path = "/api/v1/backstage/feeds/";
  const { data, pending, error, refresh: fetchBoard } = useFetch<FeedBoardResponse>(path, {
    key: useOperatorResourceKey("feed-board"),
    server: true,
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });
  const refresh = coalesceRefresh(() => fetchBoard());
  const { realtime } = useBackstageEvents("catalog", refresh);
  const lastConfirmed = shallowRef<FeedBoardProjection | null>(data.value?.board ?? null);
  watch([data, error], ([value, failure]) => {
    if (value?.board && !failure) lastConfirmed.value = value.board;
  }, { flush: "sync" });
  // Session ownership is provided by the page instance/resource cache key.
  // A transient failure is not a successful empty board.
  const board = computed<FeedBoardProjection | null>(() => data.value?.board ?? lastConfirmed.value);

  const intentions = useOrderIntention();
  const busy = ref<Set<string>>(new Set());
  const isBusy = (ref_: string) => busy.value.has(ref_);
  const errorMsg = ref("");

  async function run(ref_: string, body: Record<string, unknown>, url: string): Promise<boolean> {
    if (busy.value.has(ref_)) return false;
    if (error.value) {
      errorMsg.value = "A leitura está desatualizada. Atualize antes de aplicar; seu rascunho foi mantido.";
      return false;
    }
    errorMsg.value = "";
    busy.value = new Set(busy.value).add(ref_);
    try {
      const operation = url.split("/").filter(Boolean).at(-1)!;
      const action = board.value?.feeds.find((feed) => feed.ref === ref_)?.actions.find((item) => item.ref === operation);
      await intentions.executePath(`feed:${ref_}:${operation}`, url, action, body);
      try { await refresh(); }
      catch { errorMsg.value = "Alteração confirmada. A leitura atualizada falhou; atualize antes da próxima edição."; }
      if (error.value) errorMsg.value = "Alteração confirmada. A leitura atualizada falhou; atualize antes da próxima edição.";
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, error instanceof Error ? error.message : "Falha ao atualizar o feed.");
      useSonner.error(errorMsg.value);
      if (httpError(error).status === 409) {
        try { await refresh(); }
        catch { errorMsg.value += " A leitura atualizada também falhou; o rascunho foi mantido."; }
      }
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(ref_);
      busy.value = next;
    }
  }

  const setActive = (ref_: string, isActive: boolean) =>
    run(ref_, { ref: ref_, is_active: isActive }, "/api/v1/backstage/feeds/active/");
  const setCollections = (ref_: string, collections: string[], baseRevision?: string) =>
    run(ref_, { ref: ref_, collections, ...(baseRevision ? { base_revision: baseRevision } : {}) }, "/api/v1/backstage/feeds/collections/");
  const setRotation = (ref_: string, rotateSeconds: number, itemsPerPage: number, baseRevision?: string) =>
    run(
      ref_,
      { ref: ref_, rotate_seconds: rotateSeconds, items_per_page: itemsPerPage, ...(baseRevision ? { base_revision: baseRevision } : {}) },
      "/api/v1/backstage/feeds/rotation/",
    );

  return { realtime, board, pending, error, refresh, isBusy, errorMsg, setActive, setCollections, setRotation };
}
