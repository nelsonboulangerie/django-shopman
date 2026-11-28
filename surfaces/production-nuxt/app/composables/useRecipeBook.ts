// Inventário de receitas — read-side da página /recipes.
// GET /api/v1/backstage/recipes/ com `q`, `kind` e `archived=1`; o payload traz os
// cartões, as opções de `kind` (chips) e o acesso. Criar uma entry (as três portas
// de /recipes/new) é o write daqui: POST recipes/ e navega para o editor. A estrela
// (useRecipeFavorite) acende o cartão no lugar, sem buscar a lista de novo.
import type { Ref } from "vue";
import type {
  EntryCreatePayload,
  RecipeBookListResponse,
  RecipeCreateResponse,
  RecipeEntryDetailProjection,
} from "~/types/recipeBook";
import { bookQuery, errorField } from "~/presentation/recipeBook";
import { useRecipeFavorite } from "~/composables/useRecipeFavorite";

export interface CreateEntryResult {
  ok: boolean;
  entry?: RecipeEntryDetailProjection;
  field?: string;
  message?: string;
}

function newMutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export interface RecipeBookServerFilters {
  withoutSku?: Ref<boolean>;
  withDraft?: Ref<boolean>;
  favorites?: Ref<boolean>;
  unreviewed?: Ref<boolean>;
  mode?: Ref<string>;
  sort?: Ref<string>;
  page?: Ref<number>;
  pageSize?: Ref<number>;
}

export function useRecipeBook(
  query: Ref<string>,
  kind: Ref<string>,
  archived: Ref<boolean>,
  filters: RecipeBookServerFilters = {},
) {
  const { data, pending, error, refresh } = useFetch<RecipeBookListResponse>("/api/v1/backstage/recipes/", {
    key: "recipe-book",
    server: true,
    query: computed(() => bookQuery(query.value, kind.value, archived.value, {
      withoutSku: filters.withoutSku?.value,
      withDraft: filters.withDraft?.value,
      favorites: filters.favorites?.value,
      unreviewed: filters.unreviewed?.value,
      mode: filters.mode?.value,
      sort: filters.sort?.value,
      page: filters.page?.value,
      pageSize: filters.pageSize?.value,
    })),
  });

  const book = computed(() => data.value?.book ?? null);
  const entries = computed(() => book.value?.entries ?? []);
  const kinds = computed(() => book.value?.kinds ?? []);
  const count = computed(() => book.value?.count ?? 0);
  const total = computed(() => book.value?.total ?? count.value);
  const page = computed(() => book.value?.page ?? 1);
  const pageSize = computed(() => book.value?.page_size ?? 48);
  const hasNext = computed(() => book.value?.has_next ?? false);
  const access = computed(() => data.value?.access ?? null);
  const canEdit = computed(() => !!access.value?.can_edit);
  const forbidden = computed(() => httpError(error.value).status === 403);

  const { setFavorite, isFavoriteBusy } = useRecipeFavorite();

  /** Marca/desmarca e acende o cartão com o estado que o servidor devolveu. */
  async function toggleFavorite(entryRef: string, next: boolean): Promise<boolean> {
    const state = await setFavorite(entryRef, next);
    if (state === null) return false;
    const current = data.value;
    if (current?.book) {
      data.value = {
        ...current,
        book: {
          ...current.book,
          entries: current.book.entries.map((entry) =>
            entry.ref === entryRef ? { ...entry, is_favorite: state } : entry,
          ),
        },
      };
    }
    return true;
  }

  const creating = ref(false);
  const createKey = ref(newMutationKey());

  async function createEntry(payload: EntryCreatePayload): Promise<CreateEntryResult> {
    if (creating.value) return { ok: false };
    creating.value = true;
    try {
      const response = await $fetch<RecipeCreateResponse>("/api/v1/backstage/recipes/", {
        method: "POST",
        headers: { "Idempotency-Key": createKey.value },
        body: payload,
      });
      if (response.outcome !== "applied") return { ok: false, message: "Cadastro ainda em processamento." };
      createKey.value = newMutationKey();
      await refresh();
      return { ok: true, entry: response.entry };
    } catch (err) {
      const message = httpErrorMessage(err, "Não foi possível criar a receita.");
      const field = errorField(httpError(err).data);
      useSonner.error(message);
      // Uma recusa definitiva já foi memorizada pelo servidor; a próxima
      // intenção recebe outra chave. Em falha de rede, preservamos a chave.
      if (httpError(err).status >= 400) createKey.value = newMutationKey();
      return { ok: false, field, message };
    } finally {
      creating.value = false;
    }
  }

  return {
    book,
    entries,
    kinds,
    count,
    total,
    page,
    pageSize,
    hasNext,
    access,
    canEdit,
    forbidden,
    pending,
    error,
    refresh,
    creating,
    createEntry,
    toggleFavorite,
    isFavoriteBusy,
  };
}
