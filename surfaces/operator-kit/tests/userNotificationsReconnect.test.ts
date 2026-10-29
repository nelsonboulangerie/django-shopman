// O canal pessoal de notificações se recria depois do 502 de deploy e, ao
// reabrir, refaz o fetch canônico (ADR-016: o push é sinal sobre o fetch).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref, watch } from "vue";

import { useUserNotifications } from "../app/composables/useUserNotifications";
import { ssePath } from "../app/utils/ssePath";
import { FakeEventSource } from "./support/fakeEventSource";

describe("useUserNotifications: tempo real que reconecta", () => {
  let mounted!: () => void;
  let unmount!: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("ref", ref);
    vi.stubGlobal("watch", watch);
    vi.stubGlobal("ssePath", ssePath);
    vi.stubGlobal("useRuntimeConfig", () => ({ app: { baseURL: "/" } }));
    vi.stubGlobal("useNuxtData", () => ({ data: ref({ operator: { id: 7 } }) }));
    vi.stubGlobal("onMounted", (fn: () => void) => { mounted = fn; });
    vi.stubGlobal("onBeforeUnmount", (fn: () => void) => { unmount = fn; });
    const listeners = { addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.stubGlobal("document", { ...listeners, visibilityState: "visible" });
    vi.stubGlobal("window", listeners);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("depois do 502 recria o stream com backoff e refaz o fetch ao reabrir", async () => {
    const onPush = vi.fn();
    const { realtime } = useUserNotifications(onPush);
    mounted();

    const first = FakeEventSource.instances[0]!;
    expect(first.url).toBe("/sse/notifications");
    first.open();
    expect(realtime.value).toBe("live");
    // Primeira abertura: a tela acabou de ler; nada a refazer.
    expect(onPush).not.toHaveBeenCalled();

    first.emit("user-notification");
    expect(onPush).toHaveBeenCalledTimes(1);

    first.failForGood();
    expect(realtime.value).toBe("polling");
    await vi.advanceTimersByTimeAsync(1_999);
    expect(FakeEventSource.instances).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeEventSource.instances).toHaveLength(2);

    // A reabertura também cai com 502: a espera dobra.
    FakeEventSource.instances[1]!.failForGood();
    await vi.advanceTimersByTimeAsync(3_999);
    expect(FakeEventSource.instances).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeEventSource.instances).toHaveLength(3);

    FakeEventSource.instances[2]!.open();
    expect(realtime.value).toBe("live");
    expect(onPush).toHaveBeenCalledTimes(2);

    unmount();
    expect(FakeEventSource.alive()).toHaveLength(0);
  });
});
