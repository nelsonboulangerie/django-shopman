import { ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useRecipeBook } from "~/composables/useRecipeBook";

const env = installNuxtGlobals();

function book() {
  return useRecipeBook(ref(""), ref(""), ref(false));
}

describe("useRecipeBook", () => {
  beforeEach(() => env.reset());

  it("derives entries, kinds, count and the write flag from the payload", () => {
    env.fetchData.value = {
      book: {
        entries: [{ ref: "pao" }, { ref: "brioche" }],
        kinds: [{ value: "bread", label: "Pão" }],
        count: 2,
      },
      access: { can_view: true, can_edit: true, capture_available: false },
    };
    const { entries, kinds, count, canEdit, forbidden } = book();
    expect(entries.value).toHaveLength(2);
    expect(kinds.value[0]?.label).toBe("Pão");
    expect(count.value).toBe(2);
    expect(canEdit.value).toBe(true);
    expect(forbidden.value).toBe(false);
  });

  it("degrades to empty lists when the payload is null", () => {
    env.fetchData.value = null;
    const { entries, kinds, count, canEdit } = book();
    expect(entries.value).toEqual([]);
    expect(kinds.value).toEqual([]);
    expect(count.value).toBe(0);
    expect(canEdit.value).toBe(false);
  });

  it("recognises the 403 as a permission state, not a network failure", () => {
    env.fetchData.value = null;
    env.fetchError.value = { status: 403, data: { detail: "sem permissão" } };
    expect(book().forbidden.value).toBe(true);
  });

  it("createEntry POSTs to recipes/, reconciles and returns the entry", async () => {
    env.fetchData.value = { book: { entries: [], kinds: [], count: 0 }, access: {} };
    env.fetchMock.mockResolvedValueOnce({ entry: { ref: "pao-campanha", name: "Pão de campanha" } });
    const result = await book().createEntry({ name: "Pão de campanha", kind: "bread", output_sku: "", notes: "" });
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/",
      expect.objectContaining({ method: "POST", body: expect.objectContaining({ name: "Pão de campanha", kind: "bread" }) }),
    );
    expect(result.ok).toBe(true);
    expect(result.entry?.ref).toBe("pao-campanha");
    expect(env.refresh).toHaveBeenCalled();
  });

  it("createEntry surfaces the server message and the field of the canonical dialect", async () => {
    env.fetchData.value = { book: { entries: [], kinds: [], count: 0 }, access: {} };
    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "Nome obrigatório.", field: "name" } });
    const result = await book().createEntry({ name: "", kind: "bread", output_sku: "", notes: "" });
    expect(result.ok).toBe(false);
    expect(result.field).toBe("name");
    expect(result.message).toBe("Nome obrigatório.");
    expect(env.sonner.error).toHaveBeenCalledWith("Nome obrigatório.");
  });
});
