// A receita — read-side + ações de /recipes/[ref] e do editor.
// GET /api/v1/backstage/recipes/<ref>/ traz a entry com TODAS as versões (mais nova
// primeiro), cada uma já com a lente calculada. As escritas vão pelo BFF (CSRF no
// proxy) e reconciliam por refresh: PATCH da entry (nome/kind/SKU/notas/arquivar),
// POST de versão (cópia em rascunho), PATCH do rascunho e POST publish. A estrela
// do operador (useRecipeFavorite) acende no lugar, sem refazer a lente. As
// fontes (`external_references`: livros, vídeos, artigos) vão no PATCH da entry com a lista
// inteira; a nota da versão (0 a 5 por critério) é um PUT em versions/<n>/rating/.
// Erro no dialeto canônico: a mensagem vai ao toast e o `field` volta para a tela acender.
import type {
  DraftPatch,
  EntryPatch,
  ExecutionPatch,
  ExternalReferenceInput,
  RecipeDuplicatePayload,
  RecipeDuplicateResponse,
  RecipeEntryDetailProjection,
  RecipeEntryResponse,
  RecipeVersionProjection,
  RecipeVersionMutationResponse,
  RecipeVersionResponse,
  VersionPayload,
} from "~/types/recipeBook";
import { errorField } from "~/presentation/recipeBook";
import { useRecipeFavorite } from "~/composables/useRecipeFavorite";

export interface EntryActionResult {
  ok: boolean;
  entry?: RecipeEntryDetailProjection;
  version?: RecipeVersionProjection;
  field?: string;
  message?: string;
  uncertain?: boolean;
}

function newMutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useRecipeEntry(entryRef: string) {
  const base = `/api/v1/backstage/recipes/${encodeURIComponent(entryRef)}/`;

  const { data, pending, error, refresh } = useFetch<RecipeEntryResponse>(base, {
    key: `recipe-entry-${entryRef}`,
    server: true,
  });

  const entry = computed(() => data.value?.entry ?? null);
  const access = computed(() => data.value?.access ?? null);
  const canEdit = computed(() => !!access.value?.can_edit);
  const versions = computed<RecipeVersionProjection[]>(() => entry.value?.versions ?? []);
  const currentVersion = computed(
    () => versions.value.find((version) => version.number === entry.value?.current_version_number) ?? null,
  );
  const latestDraft = computed(() => versions.value.find((version) => version.status === "draft") ?? null);
  const notFound = computed(() => httpError(error.value).status === 404);
  const forbidden = computed(() => httpError(error.value).status === 403);

  function versionByNumber(number: number | null | undefined): RecipeVersionProjection | null {
    if (!number) return null;
    return versions.value.find((version) => version.number === number) ?? null;
  }

  // Uma escrita em voo por vez: a receita é uma só, e duas gravações cruzadas
  // sobre o mesmo rascunho não têm ordem certa.
  const busy = ref(false);

  async function act<T extends { entry?: RecipeEntryDetailProjection; version?: RecipeVersionProjection }>(
    request: () => Promise<T>,
    fallback: string,
  ): Promise<EntryActionResult> {
    if (busy.value) return { ok: false };
    busy.value = true;
    try {
      const response = await request();
      await refresh();
      return { ok: true, entry: response.entry, version: response.version };
    } catch (err) {
      const message = httpErrorMessage(err, fallback);
      useSonner.error(message);
      const parsed = httpError(err);
      return { ok: false, field: errorField(parsed.data), message, uncertain: !parsed.status };
    } finally {
      busy.value = false;
    }
  }

  const patchEntry = (patch: EntryPatch) =>
    act(
      () => $fetch<RecipeEntryResponse>(base, { method: "PATCH", body: patch }),
      "Não foi possível salvar a receita.",
    );

  const saveExecution = (patch: ExecutionPatch) =>
    act(
      () => $fetch<RecipeEntryResponse>(`${base}execution/`, { method: "PATCH", body: patch }),
      "Não foi possível salvar a operação da ficha.",
    );

  async function duplicate(payload: RecipeDuplicatePayload, idempotencyKey: string): Promise<EntryActionResult> {
    return act(
      async () => {
        const response = await $fetch<RecipeDuplicateResponse>(`${base}duplicate/`, {
          method: "POST",
          headers: { "Idempotency-Key": idempotencyKey },
          body: payload,
        });
        if (response.outcome !== "applied") throw new Error(response.outcome);
        return response;
      },
      "Não foi possível duplicar a receita.",
    );
  }

  const createVersionKey = ref(newMutationKey());
  async function createVersion(payload: VersionPayload) {
    const result = await act(
      async () => {
        const response = await $fetch<RecipeVersionMutationResponse>(`${base}versions/`, {
          method: "POST",
          headers: { "Idempotency-Key": createVersionKey.value },
          body: payload,
        });
        if (response.outcome !== "applied") throw new Error(response.outcome);
        return response;
      },
      "Não foi possível criar a versão.",
    );
    if (result.ok || !result.uncertain) createVersionKey.value = newMutationKey();
    return result;
  }

  const updateDraft = (number: number, patch: DraftPatch) =>
    act(
      () => $fetch<RecipeVersionResponse>(`${base}versions/${number}/`, {
        method: "PATCH",
        body: {
          ...patch,
          ...(versionByNumber(number)?.revision ? { expectedRevision: versionByNumber(number)?.revision } : {}),
        },
      }),
      "Não foi possível salvar o rascunho.",
    );

  const { setFavorite, isFavoriteBusy } = useRecipeFavorite();
  const favoriteBusy = computed(() => isFavoriteBusy(entryRef));

  /** Marca/desmarca esta receita e acende a estrela com o estado do servidor. */
  async function toggleFavorite(next: boolean): Promise<boolean> {
    const state = await setFavorite(entryRef, next);
    if (state === null) return false;
    const current = data.value;
    if (current?.entry) data.value = { ...current, entry: { ...current.entry, is_favorite: state } };
    return true;
  }

  const saveReferences = (references: ExternalReferenceInput[]) =>
    act(
      () => $fetch<RecipeEntryResponse>(base, {
        method: "PATCH",
        body: {
          external_references: references,
          ...(entry.value?.revision ? { expectedRevision: entry.value.revision } : {}),
        },
      }),
      "Não foi possível salvar as fontes.",
    );

  const rateVersion = (number: number, scores: Record<string, number>) =>
    act(
      () => $fetch<RecipeEntryResponse>(`${base}versions/${number}/rating/`, { method: "PUT", body: { scores } }),
      "Não foi possível salvar a nota.",
    );

  /** "Está certa": assina a conferência da versão em uso (WP-RECEITAS-DA-CASA F1). */
  const confirmVersion = (number: number) =>
    act(
      () => $fetch<RecipeEntryResponse>(`${base}versions/${number}/review/`, { method: "POST" }),
      "Não foi possível registrar a conferência.",
    );

  const publishKeys = new Map<number, string>();
  async function publish(number: number) {
    const key = publishKeys.get(number) ?? newMutationKey();
    publishKeys.set(number, key);
    const version = versionByNumber(number);
    const result = await act(
      async () => {
        const response = await $fetch<RecipeVersionMutationResponse>(`${base}versions/${number}/publish/`, {
          method: "POST",
          headers: { "Idempotency-Key": key },
          body: {
            ...(version?.revision ? { expectedRevision: version.revision } : {}),
            ...(entry.value?.revision ? { expectedEntryRevision: entry.value.revision } : {}),
          },
        });
        if (response.outcome !== "applied") throw new Error(response.outcome);
        return response;
      },
      "Não foi possível publicar a versão.",
    );
    if (result.ok || !result.uncertain) publishKeys.delete(number);
    return result;
  }

  return {
    entry,
    access,
    canEdit,
    versions,
    currentVersion,
    latestDraft,
    versionByNumber,
    notFound,
    forbidden,
    pending,
    error,
    refresh,
    busy,
    patchEntry,
    saveExecution,
    duplicate,
    createVersion,
    updateDraft,
    publish,
    saveReferences,
    rateVersion,
    confirmVersion,
    toggleFavorite,
    favoriteBusy,
  };
}
