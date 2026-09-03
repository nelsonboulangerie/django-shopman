// Inventário de receitas — read-side da página /recipes.
// GET /api/v1/backstage/recipes/ com `q`, `kind` e `archived=1`; o payload traz os
// cartões, as opções de `kind` (chips) e o acesso. Criar uma entry (as três portas
// de /recipes/new) é o único write daqui: POST recipes/ e navega para o editor.
import type { Ref } from "vue";
import type {
  EntryCreatePayload,
  RecipeBookListResponse,
  RecipeEntryDetailProjection,
  RecipeEntryResponse,
} from "~/types/recipeBook";
import { bookQuery, errorField } from "~/presentation/recipeBook";

export interface CreateEntryResult {
  ok: boolean;
  entry?: RecipeEntryDetailProjection;
  field?: string;
  message?: string;
}

export function useRecipeBook(query: Ref<string>, kind: Ref<string>, archived: Ref<boolean>) {
  const { data, pending, error, refresh } = useFetch<RecipeBookListResponse>("/api/v1/backstage/recipes/", {
    key: "recipe-book",
    server: true,
    query: computed(() => bookQuery(query.value, kind.value, archived.value)),
  });

  const book = computed(() => data.value?.book ?? null);
  const entries = computed(() => book.value?.entries ?? []);
  const kinds = computed(() => book.value?.kinds ?? []);
  const count = computed(() => book.value?.count ?? 0);
  const access = computed(() => data.value?.access ?? null);
  const canEdit = computed(() => !!access.value?.can_edit);
  const forbidden = computed(() => httpError(error.value).status === 403);

  const creating = ref(false);

  async function createEntry(payload: EntryCreatePayload): Promise<CreateEntryResult> {
    if (creating.value) return { ok: false };
    creating.value = true;
    try {
      const response = await $fetch<RecipeEntryResponse>("/api/v1/backstage/recipes/", {
        method: "POST",
        body: payload,
      });
      await refresh();
      return { ok: true, entry: response.entry };
    } catch (err) {
      const message = httpErrorMessage(err, "Não foi possível criar a receita.");
      const field = errorField(httpError(err).data);
      useSonner.error(message);
      return { ok: false, field, message };
    } finally {
      creating.value = false;
    }
  }

  return { book, entries, kinds, count, access, canEdit, forbidden, pending, error, refresh, creating, createEntry };
}
