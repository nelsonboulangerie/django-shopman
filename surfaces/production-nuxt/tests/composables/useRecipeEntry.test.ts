import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useRecipeEntry } from "~/composables/useRecipeEntry";
import { emptyFormula } from "~/presentation/recipeBook";

const env = installNuxtGlobals();

const ENTRY = {
  ref: "pao-campanha",
  revision: "2026-10-14T02:03:04+00:00",
  name: "Pão de campanha",
  kind: "bread",
  output_sku: "PAO-CAMP",
  current_version_number: 2,
  versions: [
    { id: 3, number: 3, status: "draft", revision: "rev-3", formula: {}, steps: [] },
    { id: 2, number: 2, status: "published", revision: "rev-2", formula: {}, steps: [] },
    { id: 1, number: 1, status: "superseded", revision: "rev-1", formula: {}, steps: [] },
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

    env.fetchMock.mockResolvedValueOnce({
      ok: true,
      outcome: "applied",
      resource: { kind: "recipe-version", ref: "pao-campanha@4" },
      entry: ENTRY,
      version: { number: 4, status: "draft" },
    });
    const created = await createVersion({ from_version: 2, formula: emptyFormula(), yield_quantity: "2", yield_unit: "kg" });
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/versions/",
      expect.objectContaining({
        method: "POST",
        headers: { "Idempotency-Key": expect.any(String) },
        body: expect.objectContaining({ from_version: 2 }),
      }),
    );
    expect(created.version?.number).toBe(4);

    env.fetchMock.mockResolvedValueOnce({ entry: ENTRY, version: { number: 3, status: "draft" } });
    await updateDraft(3, { label: "mais água" });
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/versions/3/",
      expect.objectContaining({ method: "PATCH", body: { label: "mais água", expectedRevision: "rev-3" } }),
    );

    env.fetchMock.mockResolvedValueOnce({
      ok: true,
      outcome: "applied",
      resource: { kind: "recipe-version", ref: "pao-campanha@3" },
      entry: ENTRY,
    });
    const published = await publish(3);
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/versions/3/publish/",
      expect.objectContaining({
        method: "POST",
        headers: { "Idempotency-Key": expect.any(String) },
        body: { expectedRevision: "rev-3", expectedEntryRevision: ENTRY.revision },
      }),
    );
    expect(published.ok).toBe(true);
  });

  it("reuses a create-version intention after an uncertain outcome", async () => {
    env.fetchData.value = { entry: ENTRY };
    const { createVersion } = useRecipeEntry("pao-campanha");
    env.fetchMock
      .mockResolvedValueOnce({ outcome: "unknown" })
      .mockResolvedValueOnce({
        ok: true,
        outcome: "applied",
        resource: { kind: "recipe-version", ref: "pao-campanha@4" },
        entry: ENTRY,
        version: { number: 4, status: "draft" },
      });

    const first = await createVersion({ from_version: 2 });
    const second = await createVersion({ from_version: 2 });
    const firstHeaders = env.fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>;
    const secondHeaders = env.fetchMock.mock.calls[1]?.[1]?.headers as Record<string, string>;

    expect(first).toMatchObject({ ok: false, uncertain: true });
    expect(second.ok).toBe(true);
    expect(secondHeaders["Idempotency-Key"]).toBe(firstHeaders["Idempotency-Key"]);
  });

  it("rotates a publish intention after a definitive refusal", async () => {
    env.fetchData.value = { entry: ENTRY };
    const { publish } = useRecipeEntry("pao-campanha");
    env.fetchMock
      .mockRejectedValueOnce({ status: 409, data: { detail: "A receita mudou." } })
      .mockResolvedValueOnce({
        ok: true,
        outcome: "applied",
        resource: { kind: "recipe-version", ref: "pao-campanha@3" },
        entry: ENTRY,
      });

    const first = await publish(3);
    const second = await publish(3);
    const firstHeaders = env.fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>;
    const secondHeaders = env.fetchMock.mock.calls[1]?.[1]?.headers as Record<string, string>;

    expect(first).toMatchObject({ ok: false, uncertain: false });
    expect(second.ok).toBe(true);
    expect(secondHeaders["Idempotency-Key"]).not.toBe(firstHeaders["Idempotency-Key"]);
  });

  it("saves execution with the revision and reconciles the served projection", async () => {
    env.fetchData.value = { entry: ENTRY };
    env.fetchMock.mockResolvedValueOnce({ entry: ENTRY });
    const payload = {
      expectedRevision: "2026-10-14T02:03:04+00:00",
      maxStartedMinutes: 90,
      capacityPerDay: "24",
      requiresBatchTracking: true,
      shelfLifeDays: 3,
      shelfLifeReviewed: true,
      productionLifecycle: "standard",
    };

    const result = await useRecipeEntry("pao-campanha").saveExecution(payload);

    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/execution/",
      expect.objectContaining({ method: "PATCH", body: payload }),
    );
    expect(result.ok).toBe(true);
    expect(env.refresh).toHaveBeenCalled();
  });

  it("duplicates with a stable key and returns the exact created recipe", async () => {
    env.fetchData.value = { entry: ENTRY };
    env.fetchMock.mockResolvedValueOnce({
      ok: true,
      outcome: "applied",
      resource: { kind: "recipe", ref: "pao-campanha-copia" },
      entry: { ...ENTRY, ref: "pao-campanha-copia", name: "Pão de campanha (cópia)" },
    });
    const payload = {
      name: "Pão de campanha (cópia)",
      expectedRevision: "2026-10-14T02:03:04+00:00",
    };

    const result = await useRecipeEntry("pao-campanha").duplicate(payload, "stable-key");

    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/duplicate/",
      expect.objectContaining({
        method: "POST",
        headers: { "Idempotency-Key": "stable-key" },
        body: payload,
      }),
    );
    expect(result.ok).toBe(true);
    expect(result.entry?.ref).toBe("pao-campanha-copia");
  });

  it("does not treat an uncertain duplicate outcome as a successful creation", async () => {
    env.fetchData.value = { entry: ENTRY };
    env.fetchMock.mockResolvedValueOnce({
      ok: false,
      outcome: "unknown",
      resource: { kind: "recipe", ref: "" },
    });

    const result = await useRecipeEntry("pao-campanha").duplicate(
      { name: "Cópia", expectedRevision: ENTRY.revision },
      "same-key-on-retry",
    );

    expect(result.ok).toBe(false);
    expect(env.sonner.error).toHaveBeenCalled();
    expect(env.refresh).not.toHaveBeenCalled();
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

  it("saveReferences PATCHes the whole list; rateVersion PUTs the scores of a version", async () => {
    env.fetchData.value = { entry: ENTRY };
    const { saveReferences, rateVersion } = useRecipeEntry("pao-campanha");

    env.fetchMock.mockResolvedValueOnce({ entry: ENTRY });
    const saved = await saveReferences([{ title: "Tartine Bread", note: "p. 48" }]);
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/",
      expect.objectContaining({
        method: "PATCH",
        body: {
          external_references: [{ title: "Tartine Bread", note: "p. 48" }],
          expectedRevision: ENTRY.revision,
        },
      }),
    );
    expect(saved.ok).toBe(true);

    env.fetchMock.mockResolvedValueOnce({ entry: ENTRY });
    const rated = await rateVersion(2, { "1": 5, "2": 4 });
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao-campanha/versions/2/rating/",
      expect.objectContaining({ method: "PUT", body: { scores: { "1": 5, "2": 4 } } }),
    );
    expect(rated.ok).toBe(true);
    expect(env.refresh).toHaveBeenCalled();
  });

  it("a refused rating toasts the server message", async () => {
    env.fetchData.value = { entry: ENTRY };
    env.fetchMock.mockRejectedValueOnce({ status: 409, data: { detail: "Nenhum critério de nota ativo. Ative um no Admin." } });
    const result = await useRecipeEntry("pao-campanha").rateVersion(3, { "1": 5 });
    expect(result.ok).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("Nenhum critério de nota ativo. Ative um no Admin.");
  });

  it("encodes the ref in the URL", async () => {
    env.fetchData.value = { entry: ENTRY };
    env.fetchMock.mockResolvedValueOnce({ entry: ENTRY });
    await useRecipeEntry("pão/1").patchEntry({ notes: "x" });
    expect(env.fetchMock).toHaveBeenCalledWith("/api/v1/backstage/recipes/p%C3%A3o%2F1/", expect.anything());
  });
});
