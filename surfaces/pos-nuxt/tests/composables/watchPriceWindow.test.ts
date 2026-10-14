// A grade relê a projeção quando a Hora da Xepa abre ou fecha, sem recarregar.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref } from "vue";

import { PRICE_WINDOW_REFRESH_GRACE_MS } from "~/presentation/catalog";
import { watchPriceWindow } from "~/composables/usePosTerminal";

describe("watchPriceWindow", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-10T17:59:00-03:00"));
  });
  afterEach(() => vi.useRealTimers());

  it("relê na virada e se arma de novo com a virada seguinte", async () => {
    const next = ref<string | null>("2026-10-10T18:00:00-03:00");
    const refresh = vi.fn(async () => {
      next.value = "2026-10-11T17:30:00-03:00";
    });
    const scope = effectScope();
    scope.run(() => watchPriceWindow(() => next.value, refresh));

    await vi.advanceTimersByTimeAsync(60_000 + PRICE_WINDOW_REFRESH_GRACE_MS - 1);
    expect(refresh).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(refresh).toHaveBeenCalledTimes(1);
    await nextTick();
    expect(vi.getTimerCount()).toBe(1);
    scope.stop();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("leitura que volta com a mesma virada tenta de novo com calma, sem martelar", async () => {
    const next = ref<string | null>("2026-10-10T18:00:00-03:00");
    const refresh = vi.fn(async () => {});
    const scope = effectScope();
    scope.run(() => watchPriceWindow(() => next.value, refresh));

    await vi.advanceTimersByTimeAsync(60_000 + PRICE_WINDOW_REFRESH_GRACE_MS);
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(29_000);
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(refresh).toHaveBeenCalledTimes(2);
    scope.stop();
  });

  it("sem janela não arma relógio", () => {
    const scope = effectScope();
    scope.run(() => watchPriceWindow(() => null, vi.fn()));
    expect(vi.getTimerCount()).toBe(0);
    scope.stop();
  });
});
