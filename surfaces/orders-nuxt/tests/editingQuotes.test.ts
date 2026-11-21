// A cotação de cada corrida em edição no sheet de chamar.
import { effectScope, nextTick, ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useEditingQuotes } from "../app/composables/useEditingQuotes";

const quoteFor = (refs: string[]) => ({
  estimate: {
    value_q: 1650,
    minutes: 24,
    km: 5.7,
    with_return: true,
    stops: refs,
    display: `cotação de ${refs.join("+")}`,
    route: refs.join(" → "),
  },
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("cotação das corridas em edição", () => {
  it("espera o operador parar de marcar e pergunta uma vez por corrida", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn(
      async (_url: string, options: { query: { refs: string[] } }) =>
        quoteFor(options.query.refs),
    );
    vi.stubGlobal("$fetch", fetch);
    const rides = ref([{ number: 1, refs: ["A"] }]);
    const scope = effectScope();
    const quotes = scope.run(() => useEditingQuotes(rides, 300))!;

    rides.value = [{ number: 1, refs: ["A", "B"] }];
    await nextTick();
    expect(quotes.value[1]?.pending).toBe(true);
    await vi.advanceTimersByTimeAsync(300);

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(quotes.value[1]?.quote?.display).toBe("cotação de A+B");
    expect(quotes.value[1]?.pending).toBe(false);
    scope.stop();
  });

  it("uma resposta velha não sobrescreve a escolha nova", async () => {
    vi.useFakeTimers();
    let release: (value: unknown) => void = () => {};
    const fetch = vi
      .fn()
      .mockImplementationOnce(() => new Promise((resolve) => (release = resolve)))
      .mockImplementationOnce(async () => quoteFor(["A", "C"]));
    vi.stubGlobal("$fetch", fetch);
    const rides = ref([{ number: 1, refs: ["A", "B"] }]);
    const scope = effectScope();
    const quotes = scope.run(() => useEditingQuotes(rides, 0))!;
    await vi.advanceTimersByTimeAsync(0);

    rides.value = [{ number: 1, refs: ["A", "C"] }];
    await nextTick();
    await vi.advanceTimersByTimeAsync(0);
    release(quoteFor(["A", "B"]));
    await vi.advanceTimersByTimeAsync(0);

    expect(quotes.value[1]?.quote?.display).toBe("cotação de A+C");
    scope.stop();
  });

  it("a corrida que sai da edição sai da lista, e a TaOn fora vira frase", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "$fetch",
      vi.fn(async () => ({ estimate: null, detail: "A TaOn não cotou." })),
    );
    const rides = ref([
      { number: 1, refs: ["A"] },
      { number: 2, refs: ["B"] },
    ]);
    const scope = effectScope();
    const quotes = scope.run(() => useEditingQuotes(rides, 0))!;
    await vi.advanceTimersByTimeAsync(0);
    expect(quotes.value[2]?.failure).toBe("A TaOn não cotou.");

    rides.value = [{ number: 1, refs: ["A"] }];
    await nextTick();
    expect(Object.keys(quotes.value)).toEqual(["1"]);
    scope.stop();
  });
});
