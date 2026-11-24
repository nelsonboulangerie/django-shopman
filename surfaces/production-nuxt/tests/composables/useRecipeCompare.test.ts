import { computed, ref, type ComputedRef } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useRecipeCompare } from "~/composables/useRecipeCompare";

// A J-P9 (#3403) achou: com uma chave fixa, a receita e a tela de Comparar dividiam o
// estado e a tela de Comparar nunca pedia o par escolhido. Aqui: a chave é do par, e sem
// os dois lados nada sai para o servidor.

const request = vi.fn();
let key: ComputedRef<string>;
let handler: () => Promise<unknown>;

beforeEach(() => {
  request.mockReset();
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("useRequestFetch", () => request);
  vi.stubGlobal("useAsyncData", (k: ComputedRef<string>, h: () => Promise<unknown>) => {
    key = k;
    handler = h;
    return { data: ref(null), pending: ref(false), error: ref(null), refresh: vi.fn() };
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("useRecipeCompare", () => {
  it("does not ask the server until both sides are chosen", async () => {
    const a = ref("pao@1");
    const b = ref("");
    const { ready } = useRecipeCompare(a, b);
    expect(ready.value).toBe(false);
    expect(await handler()).toBeNull();
    expect(request).not.toHaveBeenCalled();
  });

  it("asks for the chosen pair, under a key of its own", async () => {
    const a = ref("pao@1");
    const b = ref("");
    useRecipeCompare(a, b);
    const before = key.value;
    b.value = "pao@2";
    expect(key.value).not.toBe(before);
    expect(key.value).toBe("recipe-compare:pao@1|pao@2");
    request.mockResolvedValueOnce({ compare: null });
    await handler();
    expect(request).toHaveBeenCalledWith("/api/v1/backstage/recipes/compare/", { query: { a: "pao@1", b: "pao@2" } });
  });

  it("two callers with different pairs never share a key", () => {
    useRecipeCompare(ref(""), ref(""));
    const publishDialog = key.value;
    useRecipeCompare(ref("pao@1"), ref("pao@2"));
    expect(key.value).not.toBe(publishDialog);
  });
});
