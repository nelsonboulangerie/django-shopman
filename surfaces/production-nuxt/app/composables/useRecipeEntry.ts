// A receita — read-side + ações de /recipes/[ref] e do editor.
// GET /api/v1/backstage/recipes/<ref>/ traz a entry com TODAS as versões (mais nova
// primeiro), cada uma já com a lente calculada. As escritas vão pelo BFF (CSRF no
// proxy) e reconciliam por refresh: PATCH da entry (nome/kind/SKU/notas/arquivar),
// POST de versão (cópia em rascunho), PATCH do rascunho e POST publish. Erro no
// dialeto canônico: a mensagem vai ao toast e o `field` volta para a tela acender.
import type {
  DraftPatch,
  EntryPatch,
  RecipeEntryDetailProjection,
  RecipeEntryResponse,
  RecipeVersionProjection,
  RecipeVersionResponse,
  VersionPayload,
} from "~/types/recipeBook";
import { errorField } from "~/presentation/recipeBook";

export interface EntryActionResult {
  ok: boolean;
  entry?: RecipeEntryDetailProjection;
  version?: RecipeVersionProjection;
  field?: string;
  message?: string;
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
      return { ok: false, field: errorField(httpError(err).data), message };
    } finally {
      busy.value = false;
    }
  }

  const patchEntry = (patch: EntryPatch) =>
    act(
      () => $fetch<RecipeEntryResponse>(base, { method: "PATCH", body: patch }),
      "Não foi possível salvar a receita.",
    );

  const createVersion = (payload: VersionPayload) =>
    act(
      () => $fetch<RecipeVersionResponse>(`${base}versions/`, { method: "POST", body: payload }),
      "Não foi possível criar a versão.",
    );

  const updateDraft = (number: number, patch: DraftPatch) =>
    act(
      () => $fetch<RecipeVersionResponse>(`${base}versions/${number}/`, { method: "PATCH", body: patch }),
      "Não foi possível salvar o rascunho.",
    );

  const publish = (number: number) =>
    act(
      () => $fetch<RecipeEntryResponse>(`${base}versions/${number}/publish/`, { method: "POST", body: {} }),
      "Não foi possível publicar a versão.",
    );

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
    createVersion,
    updateDraft,
    publish,
  };
}
