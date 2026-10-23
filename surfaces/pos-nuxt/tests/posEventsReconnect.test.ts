// U3 do laudo de 23/10: o PDV ficava só no poll de 60 s depois do 502 de deploy.
// Cada stream se recria com backoff e, ao reabrir, refaz o fetch canônico (ADR-016).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref, watch } from "vue";

import { FakeEventSource } from "../../operator-kit/tests/support/fakeEventSource";
import { ssePath } from "../../operator-kit/app/utils/ssePath";
import { POS_ORDER_CHANNELS, POS_TERMINAL_CHANNELS, usePosEvents } from "../app/composables/usePosEvents";

describe("usePosEvents: tempo real que reconecta", () => {
  let mounted!: () => void;
  let unmount!: () => void;
  let visibilityHandler: (() => void) | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    visibilityHandler = undefined;
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("ref", ref);
    vi.stubGlobal("watch", watch);
    vi.stubGlobal("ssePath", ssePath);
    vi.stubGlobal("useRuntimeConfig", () => ({ app: { baseURL: "/" } }));
    vi.stubGlobal("onMounted", (fn: () => void) => { mounted = fn; });
    vi.stubGlobal("onBeforeUnmount", (fn: () => void) => { unmount = fn; });
    vi.stubGlobal("document", {
      visibilityState: "visible",
      addEventListener: (name: string, fn: () => void) => { if (name === "visibilitychange") visibilityHandler = fn; },
      removeEventListener: vi.fn(),
    });
    vi.stubGlobal("window", { addEventListener: vi.fn(), removeEventListener: vi.fn() });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("depois do 502 recria cada stream com backoff e refaz o fetch do canal ao reabrir", async () => {
    const onPush = vi.fn();
    const { realtime } = usePosEvents(onPush);
    mounted();

    const [cash, tabs] = FakeEventSource.instances;
    expect(cash!.url).toBe("/sse/cash");
    expect(tabs!.url).toBe("/sse/tabs");
    cash!.open();
    tabs!.open();
    expect(realtime.value).toBe("live");
    expect(onPush).not.toHaveBeenCalled();

    cash!.emit("backstage-cash-update");
    expect(onPush).toHaveBeenLastCalledWith(POS_TERMINAL_CHANNELS[0]);

    // Um canal caído não devolve a tela ao poll enquanto o outro está de pé.
    cash!.failForGood();
    expect(realtime.value).toBe("live");
    tabs!.failForGood();
    expect(realtime.value).toBe("polling");

    await vi.advanceTimersByTimeAsync(2_000);
    expect(FakeEventSource.instances).toHaveLength(4);
    // A reabertura do caixa cai de novo com 502: a espera dele dobra.
    FakeEventSource.instances[2]!.failForGood();
    await vi.advanceTimersByTimeAsync(3_999);
    expect(FakeEventSource.instances).toHaveLength(4);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeEventSource.instances).toHaveLength(5);

    onPush.mockClear();
    FakeEventSource.instances[4]!.open();
    expect(realtime.value).toBe("live");
    expect(onPush).toHaveBeenCalledOnce();
    expect(onPush).toHaveBeenCalledWith(POS_TERMINAL_CHANNELS[0]);

    unmount();
    expect(FakeEventSource.alive()).toHaveLength(0);
  });

  it("sem push de pé, o poll calmo segura a tela; voltar à aba tenta o stream sem esperar o backoff", async () => {
    const onPush = vi.fn();
    const { realtime } = usePosEvents(onPush, { channels: POS_ORDER_CHANNELS, pollMs: 120_000 });
    mounted();

    const first = FakeEventSource.instances[0]!;
    expect(first.url).toBe("/sse/orders");
    first.open();
    // Com o stream vivo, o tick não refaz nada.
    await vi.advanceTimersByTimeAsync(120_000);
    expect(onPush).not.toHaveBeenCalled();

    first.failForGood();
    expect(realtime.value).toBe("polling");
    // Volta à aba antes do fim do backoff: relê e reconecta já.
    visibilityHandler!();
    expect(onPush).toHaveBeenCalledWith();
    expect(FakeEventSource.instances).toHaveLength(2);

    // A nova tentativa também cai: o poll é quem segura.
    FakeEventSource.instances[1]!.failForGood();
    onPush.mockClear();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(onPush).toHaveBeenCalledWith();

    unmount();
    expect(FakeEventSource.alive()).toHaveLength(0);
  });
});
