import { describe, expect, it, vi } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { ssePath } from "../../../operator-kit/app/utils/ssePath";
import { coalesceRefresh } from "../../app/utils/coalesceRefresh";
import { useBackstageEvents } from "../../app/composables/useBackstageEvents";

const env = installNuxtGlobals();

describe("invalidação SSE canônica", () => {
  it("reconexão e rajada compartilham uma leitura ativa e uma pendente; desmontar fecha transporte", async () => {
    env.reset();
    vi.useFakeTimers();
    let mounted!: () => void;
    let unmount!: () => void;
    vi.stubGlobal("onMounted", (fn: () => void) => { mounted = fn; });
    vi.stubGlobal("onBeforeUnmount", (fn: () => void) => { unmount = fn; });
    const listeners = { addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.stubGlobal("document", { ...listeners, visibilityState: "visible" });
    vi.stubGlobal("window", listeners);
    vi.stubGlobal("ssePath", ssePath);
    const events: Record<string, (event: { data: string }) => void> = {};
    const source = { addEventListener: (name: string, fn: typeof events[string]) => { events[name] = fn; }, close: vi.fn(), onopen: () => {}, onerror: () => {} };
    const factory = vi.fn(function () { return source; });
    vi.stubGlobal("EventSource", factory);
    let release!: () => void;
    const read = vi.fn().mockImplementationOnce(() => new Promise<void>(resolve => { release = resolve; })).mockResolvedValue(undefined);
    const refresh = coalesceRefresh(read);
    try {
      const status = useBackstageEvents("catalog", refresh);
      mounted();
      expect(factory).toHaveBeenCalledWith("/sse/catalog", { withCredentials: true });
      source.onopen();
      for (let i = 0; i < 30; i++) events["backstage-catalog-update"]!({ data: "{}" });
      expect(read).toHaveBeenCalledTimes(1);
      release();
      await refresh();
      expect(read).toHaveBeenCalledTimes(2);
      expect(status.realtime.value).toBe("live");
      source.onerror();
      expect(status.realtime.value).toBe("polling");
      await vi.advanceTimersByTimeAsync(30_000);
      expect(read).toHaveBeenCalledTimes(3);
      unmount();
      expect(source.close).toHaveBeenCalledOnce();
      await vi.advanceTimersByTimeAsync(30_000);
      expect(read).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });
});
