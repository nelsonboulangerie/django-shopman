import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useKdsCustomerBoard } from "~/composables/useKdsCustomerBoard";

const env = installNuxtGlobals();

describe("useKdsCustomerBoard — public pickup board", () => {
  beforeEach(() => env.reset());

  it("derives the preparing/ready status from the public payload", () => {
    env.fetchData.value = {
      status: {
        preparing: [
          {
            ref: "WEB-0007",
            status: "preparing",
            status_label: "Preparando",
            updated_at_display: "08:00",
          },
        ],
        ready: [
          {
            ref: "WEB-0006",
            status: "ready",
            status_label: "Pronto",
            updated_at_display: "07:58",
          },
        ],
        updated_at_display: "08:00",
      },
    };
    const { status } = useKdsCustomerBoard();
    expect(status.value?.preparing).toHaveLength(1);
    expect(status.value?.ready).toHaveLength(1);
  });

  it("degrades to null when there is no payload (never throws on the public TV)", () => {
    env.fetchData.value = null;
    expect(useKdsCustomerBoard().status.value).toBeNull();
  });

  it("starts in 'polling' — a bolinha verde 'ao vivo' só acende quando o SSE conecta", () => {
    env.fetchData.value = null;
    // Sem onMounted/EventSource no harness, o default honesto é 'polling' (não 'live').
    expect(useKdsCustomerBoard().realtime.value).toBe("polling");
  });
});

/** EventSource de mentira: `failForGood` é a reconexão que recebeu 502 (CLOSED). */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, Array<() => void>>();
  close = vi.fn(() => { this.readyState = 2; });
  constructor(public url: string) { FakeEventSource.instances.push(this); }
  addEventListener(name: string, handler: () => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), handler]);
  }
  emit(name: string) { for (const handler of this.listeners.get(name) ?? []) handler(); }
  open() { this.readyState = 1; this.onopen?.(); }
  failForGood() { this.readyState = 2; this.onerror?.(); }
}

/** Monta o composable com lifecycle e browser mínimos, e devolve o desmontar. */
async function withMountedBrowser<T>(build: () => T): Promise<{ value: T; unmount: () => void }> {
  const mounts: Array<() => void> = [];
  const unmounts: Array<() => void> = [];
  FakeEventSource.instances = [];
  vi.stubGlobal("onMounted", (callback: () => void) => { mounts.push(callback); });
  vi.stubGlobal("onBeforeUnmount", (callback: () => void) => { unmounts.push(callback); });
  const listeners = { addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.stubGlobal("document", { ...listeners, title: "", visibilityState: "visible" });
  vi.stubGlobal("window", listeners);
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("ssePath", (await import("../../../operator-kit/app/utils/ssePath")).ssePath);
  const value = build();
  mounts.forEach((callback) => callback());
  return { value, unmount: () => unmounts.forEach((callback) => callback()) };
}

describe("useKdsCustomerBoard — SSE da TV de retirada", () => {
  beforeEach(() => { env.reset(); vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("volta a ouvir depois do 502 de deploy, sem precisar recarregar a TV", async () => {
    const { value, unmount } = await withMountedBrowser(() => useKdsCustomerBoard());
    try {
      FakeEventSource.instances[0]!.open();
      expect(value.realtime.value).toBe("live");
      FakeEventSource.instances[0]!.failForGood();
      expect(value.realtime.value).toBe("polling");
      await vi.advanceTimersByTimeAsync(2_000);
      expect(FakeEventSource.instances).toHaveLength(2);
      env.refresh.mockClear();
      FakeEventSource.instances[1]!.open();
      expect(value.realtime.value).toBe("live");
      expect(env.refresh).toHaveBeenCalledTimes(1); // cobre o que passou no meio
    } finally { unmount(); }
  });

  it("canal recusado ao convidado (stream-error) não vira laço de reconexão", async () => {
    const { value, unmount } = await withMountedBrowser(() => useKdsCustomerBoard());
    try {
      const first = FakeEventSource.instances[0]!;
      first.open();
      first.emit("stream-error");
      expect(first.close).toHaveBeenCalled();
      expect(value.realtime.value).toBe("polling");
      await vi.advanceTimersByTimeAsync(1_999);
      expect(FakeEventSource.instances).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(1);
      expect(FakeEventSource.instances).toHaveLength(2);
    } finally { unmount(); }
  });
});
