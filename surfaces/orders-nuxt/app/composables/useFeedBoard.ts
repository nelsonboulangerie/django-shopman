// Feeds (menuboard/Google/Meta) — lê o board + liga/pausa + escolhe coleções.
import type { FeedBoardProjection, FeedBoardResponse } from "~/types/feeds";

export function useFeedBoard() {
  const path = "/api/v1/backstage/feeds/";
  const { data, pending, error, refresh } = useFetch<FeedBoardResponse>(path, {
    key: "feed-board",
    server: true,
  });
  const board = computed<FeedBoardProjection | null>(() => data.value?.board ?? null);

  const busy = ref<Set<string>>(new Set());
  const isBusy = (ref_: string) => busy.value.has(ref_);
  const errorMsg = ref("");

  async function run(ref_: string, body: Record<string, unknown>, url: string): Promise<boolean> {
    if (busy.value.has(ref_)) return false;
    errorMsg.value = "";
    busy.value = new Set(busy.value).add(ref_);
    try {
      await $fetch(url, { method: "POST", body });
      await refresh();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao atualizar o feed.");
      useSonner.error(errorMsg.value);
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(ref_);
      busy.value = next;
    }
  }

  const setActive = (ref_: string, isActive: boolean) =>
    run(ref_, { ref: ref_, is_active: isActive }, "/api/v1/backstage/feeds/active/");
  const setCollections = (ref_: string, collections: string[]) =>
    run(ref_, { ref: ref_, collections }, "/api/v1/backstage/feeds/collections/");
  const setRotation = (ref_: string, rotateSeconds: number, itemsPerPage: number) =>
    run(
      ref_,
      { ref: ref_, rotate_seconds: rotateSeconds, items_per_page: itemsPerPage },
      "/api/v1/backstage/feeds/rotation/",
    );

  return { board, pending, error, refresh, isBusy, errorMsg, setActive, setCollections, setRotation };
}
