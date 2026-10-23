// A fila do padeiro (/recipes/review, WP-RECEITAS-DA-CASA F2): as receitas cuja
// versão em uso ninguém da casa conferiu, do que mais sai para o que menos sai.
// GET /api/v1/backstage/recipes/review/; a conferência é POST em
// recipes/<ref>/versions/<n>/review/ e tira a receita da fila no lugar.
import type { RecipeReviewQueueResponse } from "~/types/recipeBook";

export function useRecipeReview() {
  const { data, pending, error, refresh } = useFetch<RecipeReviewQueueResponse>(
    "/api/v1/backstage/recipes/review/",
    { key: "recipe-review", server: true },
  );

  const queue = computed(() => data.value?.queue ?? null);
  const items = computed(() => queue.value?.items ?? []);
  const canEdit = computed(() => !!data.value?.access?.can_edit);
  const forbidden = computed(() => httpError(error.value).status === 403);
  const busyRef = ref("");

  async function confirm(ref: string, versionNumber: number): Promise<boolean> {
    if (busyRef.value) return false;
    busyRef.value = ref;
    try {
      await $fetch(`/api/v1/backstage/recipes/${encodeURIComponent(ref)}/versions/${versionNumber}/review/`, {
        method: "POST",
      });
      const current = data.value;
      if (current?.queue) {
        const remaining = current.queue.items.filter((item) => item.ref !== ref);
        data.value = {
          ...current,
          queue: {
            ...current.queue,
            items: remaining,
            total: remaining.length,
            confirmed_total: current.queue.confirmed_total + (remaining.length < current.queue.items.length ? 1 : 0),
          },
        };
      }
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível registrar a conferência."));
      return false;
    } finally {
      busyRef.value = "";
    }
  }

  return { queue, items, canEdit, forbidden, pending, error, refresh, confirm, busyRef };
}
