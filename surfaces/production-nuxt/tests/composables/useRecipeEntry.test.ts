import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useRecipeEntry } from "~/composables/useRecipeEntry";
import { emptyFormula } from "~/presentation/recipeBook";

const env = installNuxtGlobals();

const ENTRY = {
  ref: "pao-campanha",
  name: "Pão de campanha",
  kind: "bread",
  output_sku: "PAO-CAMP",
  current_version_number: 2,
  versions: [
    { id: 3, number: 3, status: "draft", formula: {}, steps: [] },
    { id: 2, number: 2, status: "published", formula: {}, steps: [] },
    { id: 1, number: 1, status: "superseded", formula: {}, steps: [] },
  ],
};

describe("useRecipeEntry", () => {
  beforeEach(() => env.reset());

  it("derives versions, the current one and the latest draft", () => {
    env.fetchData.value = { entry: ENTRY, access: { can_view: true, can_edit: true, capture_available: false } };
    const { entry, versions, currentVersion, latestDraft, canEdit, versionByNumber, notFound } = useRecipeEntry("pao-campanha");
    expect(entry.value?.name).toBe("Pão de campanha");
    expect(versions.value).toHaveLength(3);
    expect(currentVersion.value?.number).toBe(2);
    expect(latestDraft.value?.number).toBe(3);
    expect(canEdit.value).toBe(true);
    expect(versionByNumber(1)?.status).toBe("superseded");
    expect(versionByNumber(9)).toBeNull();
    expect(notFound.value).toBe(false);
  });

  it("404 is 'not found', 403 is 'forbidden' — neither is a network failure", () => {
    env.fetchError.value = { status: 404 };
    expect(useRecipeEntry("x").notFound.value).toBe(true);
    env.fetchError.value = { status: 403 };
    expect(useRecipeEntry("x").forbidden.value).toBe(true);
  });

  it("patchEntry PATCHes the entry URL and reconciles", async () => {
    env.fetchData.value = { entry: ENTRY };
    env.fetchMock.mockResolvedValueOnce({ entry: { ...ENTRY, output_sku: "PAO-NOVO" } });
    const result = await useRecipeEntry("pao-campanha").patchEntry({ output_sku: "PAO-NOVO" });
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/",
      expect.objectContaining({ method: "PATCH", body: { output_sku: "PAO-NOVO" } }),
    );
    expect(result.ok).toBe(true);
    expect(result.entry?.output_sku).toBe("PAO-NOVO");
    expect(env.refresh).toHaveBeenCalled();
  });

  it("createVersion / updateDraft / publish hit the version endpoints", async () => {
    env.fetchData.value = { entry: ENTRY };
    const { createVersion, updateDraft, publish } = useRecipeEntry("pao-campanha");

    env.fetchMock.mockResolvedValueOnce({ entry: ENTRY, version: { number: 4, status: "draft" } });
    const created = await createVersion({ from_version: 2, formula: emptyFormula(), yield_quantity: "2", yield_unit: "kg" });
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/versions/",
      expect.objectContaining({ method: "POST", body: expect.objectContaining({ from_version: 2 }) }),
    );
    expect(created.version?.number).toBe(4);

    env.fetchMock.mockResolvedValueOnce({ entry: ENTRY, version: { number: 4, status: "draft" } });
    await updateDraft(4, { label: "mais água" });
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/versions/4/",
      expect.objectContaining({ method: "PATCH", body: { label: "mais água" } }),
    );

    env.fetchMock.mockResolvedValueOnce({ entry: ENTRY });
    const published = await publish(4);
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/versions/4/publish/",
      expect.objectContaining({ method: "POST" }),
    );
    expect(published.ok).toBe(true);
  });

  it("a refused write toasts the server message and returns the field", async () => {
    env.fetchData.value = { entry: ENTRY };
    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "SKU desconhecido.", field: "output_sku" } });
    const result = await useRecipeEntry("pao-campanha").patchEntry({ output_sku: "NOPE" });
    expect(result.ok).toBe(false);
    expect(result.field).toBe("output_sku");
    expect(result.message).toBe("SKU desconhecido.");
    expect(env.sonner.error).toHaveBeenCalledWith("SKU desconhecido.");
  });

  it("encodes the ref in the URL", async () => {
    env.fetchData.value = { entry: ENTRY };
    env.fetchMock.mockResolvedValueOnce({ entry: ENTRY });
    await useRecipeEntry("pão/1").patchEntry({ notes: "x" });
    expect(env.fetchMock).toHaveBeenCalledWith("/api/v1/backstage/recipes/p%C3%A3o%2F1/", expect.anything());
  });
});
