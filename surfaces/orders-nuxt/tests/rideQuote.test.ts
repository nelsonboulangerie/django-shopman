// A cotação da corrida com várias paradas enquanto o operador marca quem vai junto.
import { effectScope, nextTick, ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRideQuote } from "../app/composables/useRideQuote";

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

describe("cotação da corrida com várias paradas", () => {
  it("espera o operador parar de marcar e pergunta uma vez", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn(
      async (_url: string, options: { query: { refs: string[] } }) =>
        quoteFor(options.query.refs),
    );
    vi.stubGlobal("$fetch", fetch);
    const refs = ref<string[]>([]);
    const scope = effectScope();
    const quote = scope.run(() => useRideQuote(refs, 300))!;

    refs.value = ["A", "B"];
    await nextTick();
    refs.value = ["A", "B", "C"];
    await nextTick();
    expect(quote.pending.value).toBe(true);
    await vi.advanceTimersByTimeAsync(300);

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(quote.quote.value?.display).toBe("cotação de A+B+C");
    expect(quote.pending.value).toBe(false);
    scope.stop();
  });

  it("uma resposta velha não sobrescreve a escolha nova", async () => {
    vi.useFakeTimers();
    let release: (value: unknown) => void = () => {};
    const fetch = vi
      .fn()
      .mockImplementationOnce(
        () => new Promise((resolve) => (release = resolve)),
      )
      .mockImplementationOnce(async () => quoteFor(["A", "C"]));
    vi.stubGlobal("$fetch", fetch);
    const refs = ref<string[]>(["A", "B"]);
    const scope = effectScope();
    const quote = scope.run(() => useRideQuote(refs, 0))!;
    refs.value = ["A", "B"];
    await nextTick();
    await vi.advanceTimersByTimeAsync(0);

    refs.value = ["A", "C"];
    await nextTick();
    await vi.advanceTimersByTimeAsync(0);
    release(quoteFor(["A", "B"]));
    await vi.advanceTimersByTimeAsync(0);

    expect(quote.quote.value?.display).toBe("cotação de A+C");
    scope.stop();
  });

  it("com menos de duas entregas não cota, e a TaOn fora vira frase", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "$fetch",
      vi.fn(async () => ({ estimate: null, detail: "A TaOn não cotou." })),
    );
    const refs = ref<string[]>([]);
    const scope = effectScope();
    const quote = scope.run(() => useRideQuote(refs, 0))!;
    refs.value = ["A"];
    await nextTick();
    expect(quote.pending.value).toBe(false);
    refs.value = ["A", "B"];
    await nextTick();
    await vi.advanceTimersByTimeAsync(0);
    expect(quote.quote.value).toBeNull();
    expect(quote.failure.value).toBe("A TaOn não cotou.");
    scope.stop();
  });
});
