// Cadastro direto da ficha de execução — read-side de /recipes/sheets e as
// escritas (criar, editar, duplicar) pelo BFF. GET /recipes/sheets/ traz os
// cartões, a paginação e o acesso; o detalhe (itens e operação) é buscado ao
// abrir o painel. Toda recusa volta no dialeto canônico: a mensagem vai ao
// toast e o field acende o campo.
import type { Ref } from "vue";
import type {
  RecipeSheetDetailProjection,
  RecipeSheetDuplicatePayload,
  RecipeSheetListResponse,
  RecipeSheetMutationResponse,
  RecipeSheetPayload,
  RecipeSheetResponse,
} from "~/types/recipeBook";
import { errorField } from "~/presentation/recipeBook";
import { sheetQuery } from "~/presentation/recipeSheet";

const LIST_URL = "/api/v1/backstage/recipes/sheets/";

export interface SheetActionResult {
  ok: boolean;
  sheet?: RecipeSheetDetailProjection;
  field?: string;
  message?: string;
  uncertain?: boolean;
}

function newMutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? Date.now() + "-" + Math.random().toString(16).slice(2);
}

function sheetUrl(ref: string): string {
  return LIST_URL + encodeURIComponent(ref) + "/";
}

export interface SheetServerFilters {
  active?: Ref<string>;
  mode?: Ref<string>;
  sort?: Ref<string>;
  page?: Ref<number>;
  pageSize?: Ref<number>;
}

export function useRecipeSheets(query: Ref<string>, filters: SheetServerFilters = {}) {
  const { data, pending, error, refresh } = useFetch<RecipeSheetListResponse>(LIST_URL, {
    key: "recipe-sheets",
    server: true,
    query: computed(() =>
      sheetQuery(
        query.value,
        filters.active?.value ?? "",
        filters.sort?.value ?? "updated",
        filters.page?.value ?? 1,
        filters.pageSize?.value ?? 48,
        filters.mode?.value ?? "",
      ),
    ),
  });

  const list = computed(() => data.value?.sheets ?? null);
  const cards = computed(() => list.value?.cards ?? []);
  const total = computed(() => list.value?.total ?? 0);
  const page = computed(() => list.value?.page ?? 1);
  const pageSize = computed(() => list.value?.page_size ?? 48);
  const access = computed(() => data.value?.access ?? null);
  const canEdit = computed(() => !!access.value?.can_edit);
  const forbidden = computed(() => httpError(error.value).status === 403);

  const busy = ref(false);
  const createKey = ref(newMutationKey());

  async function act<T extends { sheet?: RecipeSheetDetailProjection }>(
    request: () => Promise<T>,
    fallback: string,
  ): Promise<SheetActionResult> {
    if (busy.value) return { ok: false };
    busy.value = true;
    try {
      const response = await request();
      await refresh();
      return { ok: true, sheet: response.sheet };
    } catch (err) {
      const message = httpErrorMessage(err, fallback);
      useSonner.error(message);
      const parsed = httpError(err);
      return { ok: false, field: errorField(parsed.data), message, uncertain: !parsed.status };
    } finally {
      busy.value = false;
    }
  }

  async function createSheet(payload: RecipeSheetPayload): Promise<SheetActionResult> {
    const result = await act(
      async () => {
        const response = await $fetch<RecipeSheetMutationResponse>(LIST_URL, {
          method: "POST",
          headers: { "Idempotency-Key": createKey.value },
          body: payload,
        });
        if (response.outcome !== "applied") throw new Error(response.outcome);
        return response;
      },
      "Não foi possível criar a ficha.",
    );
    if (result.ok || !result.uncertain) createKey.value = newMutationKey();
    return result;
  }

  async function updateSheet(ref: string, payload: RecipeSheetPayload): Promise<SheetActionResult> {
    return act(
      () => $fetch<RecipeSheetResponse>(sheetUrl(ref), { method: "PATCH", body: payload }),
      "Não foi possível salvar a ficha.",
    );
  }

  async function duplicateSheet(
    ref: string,
    payload: RecipeSheetDuplicatePayload,
    idempotencyKey: string,
  ): Promise<SheetActionResult> {
    return act(
      async () => {
        const response = await $fetch<RecipeSheetMutationResponse>(sheetUrl(ref) + "duplicate/", {
          method: "POST",
          headers: { "Idempotency-Key": idempotencyKey },
          body: payload,
        });
        if (response.outcome !== "applied") throw new Error(response.outcome);
        return response;
      },
      "Não foi possível duplicar a ficha.",
    );
  }

  async function fetchSheet(ref: string): Promise<RecipeSheetDetailProjection | null> {
    try {
      const response = await $fetch<RecipeSheetResponse>(sheetUrl(ref));
      return response.sheet;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível abrir a ficha."));
      return null;
    }
  }

  return {
    list,
    cards,
    total,
    page,
    pageSize,
    access,
    canEdit,
    forbidden,
    pending,
    error,
    refresh,
    busy,
    createSheet,
    updateSheet,
    duplicateSheet,
    fetchSheet,
  };
}
