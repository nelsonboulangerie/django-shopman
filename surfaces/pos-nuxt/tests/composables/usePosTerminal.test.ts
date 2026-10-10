import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";

// Read-window do terminal: derivação das fatias (pos/shift/tabs/operators/actions) a
// partir da Projection serializada. Mockamos useFetch para controlar o payload.
const { fetchResult, fetchMock } = vi.hoisted(() => ({ fetchResult: { value: null as unknown }, fetchMock: vi.fn() }));

mockNuxtImport("useFetch", () => () => fetchResult.value);
mockNuxtImport("$fetch", () => fetchMock);
mockNuxtImport("useRequestHeaders", () => () => ({}));
mockNuxtImport("useRuntimeConfig", () => () => ({ app: { baseURL: "/" } }));

function asyncData(payload: unknown) {
  return { data: ref(payload), pending: ref(false), error: ref(null), refresh: vi.fn() };
}

describe("usePosTerminal", () => {
  beforeEach(() => {
    fetchResult.value = null;
    fetchMock.mockReset();
  });

  it("deriva as fatias da Projection", async () => {
    const pos = { actions: [{ ref: "fire" }], operators: [{ id: 1, name: "Ana" }] };
    fetchResult.value = asyncData({ pos, shift: { open: true }, tabs: [{ ref: "T1" }] });
    const t = await usePosTerminal();
    expect(t.pos.value).toEqual(pos);
    expect(t.shift.value).toEqual({ open: true });
    expect(t.tabs.value).toEqual([{ ref: "T1" }]);
    expect(t.operators.value).toEqual([{ id: 1, name: "Ana" }]);
    expect(t.actions.value).toEqual([{ ref: "fire" }]);
  });

  it("degrada para null/[] quando o payload vem vazio", async () => {
    fetchResult.value = asyncData(null);
    const t = await usePosTerminal();
    expect(t.pos.value).toBeNull();
    expect(t.shift.value).toBeNull();
    expect(t.tabs.value).toEqual([]);
    expect(t.operators.value).toEqual([]);
    expect(t.actions.value).toEqual([]);
  });

  it("o aviso de comanda relê só o quadro e o encaixa, sem reler a projeção inteira", async () => {
    const pos = { actions: [], operators: [] };
    const result = asyncData({ pos, shift: { open: true }, tabs: [{ ref: "T1" }] });
    fetchResult.value = result;
    fetchMock.mockResolvedValue({ tabs: [{ ref: "T1" }, { ref: "T2" }] });
    const t = await usePosTerminal();

    await t.refreshTabs();

    expect(String(fetchMock.mock.calls[0]![0])).toContain("/api/v1/backstage/pos/?only=tabs");
    expect(t.tabs.value).toEqual([{ ref: "T1" }, { ref: "T2" }]);
    expect(t.pos.value).toEqual(pos);
    expect(result.refresh).not.toHaveBeenCalled();
  });

  it("se o quadro não vem, relê a projeção inteira", async () => {
    const result = asyncData({ pos: { actions: [], operators: [] }, shift: null, tabs: [] });
    fetchResult.value = result;
    fetchMock.mockRejectedValue(new Error("rede"));
    const t = await usePosTerminal();

    await t.refreshTabs();

    expect(result.refresh).toHaveBeenCalledTimes(1);
  });
});
