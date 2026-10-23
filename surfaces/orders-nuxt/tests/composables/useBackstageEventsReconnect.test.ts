// O stream do Gestor (pedidos, catálogo) se recria depois do 502 de deploy e,
// ao reabrir, refaz o fetch canônico (ADR-016).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { FakeEventSource } from "../../../operator-kit/tests/support/fakeEventSource";
import { ssePath } from "../../../operator-kit/app/utils/ssePath";
import { useBackstageEvents } from "../../app/composables/useBackstageEvents";

const env = installNuxtGlobals();

describe("useBackstageEvents: tempo real que reconecta", () => {
  let mounted!: () => void;
  let unmount!: () => void;

  beforeEach(() => {
    env.reset();
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("ssePath", ssePath);
    vi.stubGlobal("onMounted", (fn: () => void) => { mounted = fn; });
    vi.stubGlobal("onBeforeUnmount", (fn: () => void) => { unmount = fn; });
    const listeners = { addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.stubGlobal("document", { ...listeners, visibilityState: "visible" });
    vi.stubGlobal("window", listeners);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("depois do 502 recria o stream com backoff, refaz o fetch ao reabrir e mantém o poll", async () => {
    const onPush = vi.fn();
    const { realtime } = useBackstageEvents("orders", onPush, { orderRef: "WEB-1" });
    mounted();

    const first = FakeEventSource.instances[0]!;
    expect(first.url).toBe("/sse/orders");
    first.open();
    expect(realtime.value).toBe("live");
    expect(onPush).toHaveBeenCalledTimes(1);

    // O canal dos pedidos carrega todos: só o deste pedido refaz a leitura.
    first.emit("backstage-orders-update", JSON.stringify({ ref: "OUTRO" }));
    expect(onPush).toHaveBeenCalledTimes(1);
    first.emit("backstage-orders-update", JSON.stringify({ ref: "WEB-1" }));
    expect(onPush).toHaveBeenCalledTimes(2);

    first.failForGood();
    expect(realtime.value).toBe("polling");
    await vi.advanceTimersByTimeAsync(2_000);
    expect(FakeEventSource.instances).toHaveLength(2);

    // A reabertura também cai com 502: a espera dobra.
    FakeEventSource.instances[1]!.failForGood();
    await vi.advanceTimersByTimeAsync(3_999);
    expect(FakeEventSource.instances).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeEventSource.instances).toHaveLength(3);

    // O poll de fallback segue rodando enquanto o push está fora (30 s).
    onPush.mockClear();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(onPush).toHaveBeenCalled();

    onPush.mockClear();
    FakeEventSource.alive()[0]!.open();
    expect(realtime.value).toBe("live");
    expect(onPush).toHaveBeenCalledTimes(1);

    unmount();
    expect(FakeEventSource.alive()).toHaveLength(0);
  });
});
