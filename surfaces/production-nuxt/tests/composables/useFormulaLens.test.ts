import { nextTick, ref } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { LENS_DEBOUNCE_MS, useFormulaLens } from "~/composables/useFormulaLens";
import { addItem, emptyFormula, emptyItem } from "~/presentation/recipeBook";
import type { Formula } from "~/types/recipeBook";

const env = installNuxtGlobals();

// Sob fake timers um setTimeout(0) nunca dispara: o flush é de MICROTASKS.
async function flush() {
  for (let i = 0; i < 10; i++) await Promise.resolve();
}

async function settle() {
  await vi.advanceTimersByTimeAsync(LENS_DEBOUNCE_MS);
  await flush();
}

describe("useFormulaLens", () => {
  beforeEach(() => {
    env.reset();
    vi.useFakeTimers();
    env.fetchMock.mockResolvedValue({ lens: { anchor_kind: "flour", items: [], metrics: [], warnings: [] } });
  });
  afterEach(() => vi.useRealTimers());

  it("asks the server for the lens after the debounce, not before", async () => {
    const formula = ref<Formula>(emptyFormula());
    const { lens, pending } = useFormulaLens(formula, ref("bread"));
    await nextTick();
    expect(pending.value).toBe(true);
    expect(env.fetchMock).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(LENS_DEBOUNCE_MS - 1);
    expect(env.fetchMock).not.toHaveBeenCalled();

    await settle();
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/lens/",
      expect.objectContaining({ method: "POST", body: { formula: formula.value, kind: "bread" } }),
    );
    expect(lens.value?.anchor_kind).toBe("flour");
    expect(pending.value).toBe(false);
  });

  it("coalesces a burst of edits into one request", async () => {
    const formula = ref<Formula>(emptyFormula());
    useFormulaLens(formula, ref("bread"));
    await settle();
    env.fetchMock.mockClear();

    formula.value = addItem(formula.value, emptyItem({ name: "Farinha", role: "flour", quantity: 500 }));
    await nextTick();
    await vi.advanceTimersByTimeAsync(100);
    formula.value = addItem(formula.value, emptyItem({ name: "Água", role: "liquid", quantity: 350 }));
    await nextTick();
    await vi.advanceTimersByTimeAsync(100);
    formula.value = addItem(formula.value, emptyItem({ name: "Sal", role: "salt", quantity: 10 }));
    await nextTick();
    expect(env.fetchMock).not.toHaveBeenCalled();

    await settle();
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    const body = env.fetchMock.mock.calls[0]?.[1]?.body as { formula: Formula };
    expect(body.formula.items).toHaveLength(3);
  });

  it("recomputes when the kind changes (references depend on it)", async () => {
    const kind = ref("bread");
    useFormulaLens(ref<Formula>(emptyFormula()), kind);
    await settle();
    env.fetchMock.mockClear();
    kind.value = "viennoiserie";
    await nextTick();
    await settle();
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    expect(env.fetchMock.mock.calls[0]?.[1]?.body).toMatchObject({ kind: "viennoiserie" });
  });

  it("keeps the last lens and shows a calm message when the server fails", async () => {
    const formula = ref<Formula>(emptyFormula());
    const { lens, error, pending } = useFormulaLens(formula, ref("bread"));
    await settle();
    expect(lens.value).not.toBeNull();

    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "Fórmula inválida.", field: "items" } });
    formula.value = addItem(formula.value, emptyItem({ quantity: -1 }));
    await nextTick();
    await settle();
    expect(error.value).toBe("Fórmula inválida.");
    expect(lens.value).not.toBeNull();
    expect(pending.value).toBe(false);
  });

  it("standardize POSTs the formula with basis_g and returns the scaled formula", async () => {
    const formula = ref<Formula>(emptyFormula());
    const { standardize, lens } = useFormulaLens(formula, ref("bread"));
    await settle();
    const scaled = { ...emptyFormula(), basis_g: 1000, standardized: true };
    env.fetchMock.mockResolvedValueOnce({ formula: scaled, lens: { anchor_kind: "flour", standardized: true, items: [], metrics: [], warnings: [] } });

    const result = await standardize(1000);
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/standardize/",
      expect.objectContaining({ method: "POST", body: { formula: formula.value, basis_g: 1000 } }),
    );
    expect(result).toEqual(scaled);
    expect(lens.value?.standardized).toBe(true);
    // A tela decide substituir; o composable não mexe na fórmula em edição.
    expect(formula.value.standardized).toBe(false);
  });

  it("standardize toasts and returns null on failure", async () => {
    const { standardize } = useFormulaLens(ref<Formula>(emptyFormula()), ref("bread"));
    await settle();
    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "Sem farinha para padronizar." } });
    expect(await standardize()).toBeNull();
    expect(env.sonner.error).toHaveBeenCalledWith("Sem farinha para padronizar.");
  });
});
