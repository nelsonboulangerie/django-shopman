import { beforeEach, describe, expect, it } from "vitest";
import { ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useRecipeSheets } from "~/composables/useRecipeSheets";

const env = installNuxtGlobals();

const SHEET = {
  ref: "pao-tradicao",
  revision: "rev-1",
  name: "Pão Tradição",
  output_sku: "PAO-TRADICAO",
  output_unit: "kg",
  is_active: true,
  items: [],
  steps: [],
};

const CARD = {
  ref: "pao-tradicao",
  name: "Pão Tradição",
  output_sku: "PAO-TRADICAO",
  output_name: "Pão",
  batch_size: "1.7",
  item_count: 3,
  is_active: true,
  has_entry: false,
  updated_at_display: "14/10/2026",
};

describe("useRecipeSheets", () => {
  beforeEach(() => env.reset());

  it("derives the list, paging and access from the served projection", () => {
    env.fetchData.value = {
      sheets: { cards: [CARD], count: 1, page: 2, page_size: 24, total: 30, has_next: true, sort: "name" },
      access: { can_view: true, can_edit: true, capture_available: false },
    };
    const { cards, total, page, pageSize, canEdit, forbidden } = useRecipeSheets(ref("pao"));
    expect(cards.value).toHaveLength(1);
    expect(cards.value[0]?.ref).toBe("pao-tradicao");
    expect(total.value).toBe(30);
    expect(page.value).toBe(2);
    expect(pageSize.value).toBe(24);
    expect(canEdit.value).toBe(true);
    expect(forbidden.value).toBe(false);
  });

  it("sends the filters to the server instead of filtering in the client", () => {
    useRecipeSheets(ref("pao"), { active: ref("0"), sort: ref("output"), page: ref(3) });
    const options = env.useFetchMock.mock.calls[0]?.[1] as { query: { value: Record<string, string> } };
    expect(options.query.value).toEqual({ q: "pao", active: "0", sort: "output", page: "3" });
  });

  it("403 is forbidden, not a network failure", () => {
    env.fetchError.value = { status: 403 };
    expect(useRecipeSheets(ref("")).forbidden.value).toBe(true);
  });

  it("createSheet POSTs with an Idempotency-Key and returns the created sheet", async () => {
    env.fetchMock.mockResolvedValueOnce({ ok: true, outcome: "applied", sheet: SHEET, resource: { kind: "recipe-sheet", ref: "pao-tradicao" } });
    const { createSheet } = useRecipeSheets(ref(""));
    const payload = { name: "Pão", output_sku: "PAO-TRADICAO", batch_size: "1.7", items: [] };
    const result = await createSheet(payload);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/sheets/",
      expect.objectContaining({ method: "POST", headers: { "Idempotency-Key": expect.any(String) }, body: payload }),
    );
    expect(result.ok).toBe(true);
    expect(result.sheet?.ref).toBe("pao-tradicao");
    expect(env.refresh).toHaveBeenCalled();
  });

  it("reuses the create intention after an uncertain outcome and rotates it after a refusal", async () => {
    env.fetchMock
      .mockResolvedValueOnce({ outcome: "unknown" })
      .mockRejectedValueOnce({ status: 400, data: { detail: "SKU inválido.", field: "output_sku" } });
    const { createSheet } = useRecipeSheets(ref(""));
    const payload = { name: "Pão", output_sku: "X", batch_size: "1.7", items: [] };
    const first = await createSheet(payload);
    const second = await createSheet(payload);
    const firstKey = (env.fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>)["Idempotency-Key"];
    const secondKey = (env.fetchMock.mock.calls[1]?.[1]?.headers as Record<string, string>)["Idempotency-Key"];
    expect(first).toMatchObject({ ok: false, uncertain: true });
    expect(second).toMatchObject({ ok: false, field: "output_sku" });
    expect(secondKey).toBe(firstKey);
  });

  it("updateSheet PATCHes the sheet URL with the expected revision", async () => {
    env.fetchMock.mockResolvedValueOnce({ sheet: SHEET });
    const payload = { name: "Pão novo", output_sku: "PAO-TRADICAO", batch_size: "1.7", items: [], expectedRevision: "rev-1" };
    const result = await useRecipeSheets(ref("")).updateSheet("pao-tradicao", payload);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/sheets/pao-tradicao/",
      expect.objectContaining({ method: "PATCH", body: payload }),
    );
    expect(result.ok).toBe(true);
  });

  it("duplicateSheet POSTs to the duplicate URL with the given intention", async () => {
    env.fetchMock.mockResolvedValueOnce({ ok: true, outcome: "applied", sheet: SHEET, resource: { kind: "recipe-sheet", ref: "copia" } });
    const payload = { name: "Cópia", expectedRevision: "rev-1" };
    const result = await useRecipeSheets(ref("")).duplicateSheet("pao-tradicao", payload, "stable-key");
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/sheets/pao-tradicao/duplicate/",
      expect.objectContaining({ method: "POST", headers: { "Idempotency-Key": "stable-key" }, body: payload }),
    );
    expect(result.ok).toBe(true);
  });

  it("fetchSheet GETs the detail and toasts when it cannot open", async () => {
    env.fetchMock.mockResolvedValueOnce({ sheet: SHEET });
    const { fetchSheet } = useRecipeSheets(ref(""));
    expect((await fetchSheet("pao-tradicao"))?.ref).toBe("pao-tradicao");
    expect(env.fetchMock).toHaveBeenLastCalledWith("/api/v1/backstage/recipes/sheets/pao-tradicao/");

    env.fetchMock.mockRejectedValueOnce({ status: 404, data: { detail: "Não existe." } });
    expect(await fetchSheet("sumiu")).toBeNull();
    expect(env.sonner.error).toHaveBeenCalled();
  });
});
