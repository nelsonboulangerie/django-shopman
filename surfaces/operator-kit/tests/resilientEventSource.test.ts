// O SSE das superfícies de operador se recria depois de um não-200 na reconexão
// (o 502 de todo deploy) e não entra em laço quando o Django recusa o canal.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { openResilientEventSource } from "../app/utils/resilientEventSource";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, Array<(event: Event) => void>>();
  close = vi.fn(() => { this.readyState = 2; });
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(name: string, handler: (event: Event) => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), handler]);
  }
  emit(name: string) {
    for (const handler of this.listeners.get(name) ?? []) handler(new Event(name));
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  /** Reconexão recebeu 502: o navegador desiste e fica CLOSED. */
  failForGood() {
    this.readyState = 2;
    this.onerror?.();
  }
}

describe("openResilientEventSource", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("recria o stream depois que a reconexão recebe 502 e avisa que é reabertura", async () => {
    const onOpen = vi.fn();
    const onDown = vi.fn();
    openResilientEventSource({ url: "/sse/orders", events: ["x"], onEvent: vi.fn(), onOpen, onDown });
    const first = FakeEventSource.instances[0]!;
    first.open();
    expect(onOpen).toHaveBeenLastCalledWith(false);

    first.failForGood();
    expect(onDown).toHaveBeenCalled();
    expect(first.close).toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(2_000);
    expect(FakeEventSource.instances).toHaveLength(2);
    FakeEventSource.instances[1]!.open();
    expect(onOpen).toHaveBeenLastCalledWith(true);
  });

  it("canal recusado (stream-error) espera cada vez mais, até o teto, em vez de 3 s em laço", async () => {
    openResilientEventSource({ url: "/sse/orders", events: [], onEvent: vi.fn(), capMs: 16_000 });
    const waits: number[] = [];
    for (let round = 0; round < 6; round += 1) {
      const current = FakeEventSource.instances.at(-1)!;
      current.open();
      current.emit("stream-error");
      const before = FakeEventSource.instances.length;
      let waited = 0;
      while (FakeEventSource.instances.length === before) {
        await vi.advanceTimersByTimeAsync(1_000);
        waited += 1_000;
      }
      waits.push(waited);
    }
    expect(waits).toEqual([2_000, 4_000, 8_000, 16_000, 16_000, 16_000]);
  });

  it("queda no meio do stream fica com o navegador (sem stream duplicado)", async () => {
    const onDown = vi.fn();
    openResilientEventSource({ url: "/sse/kds/a", events: [], onEvent: vi.fn(), onDown });
    const first = FakeEventSource.instances[0]!;
    first.open();
    first.readyState = 0; // CONNECTING: o próprio EventSource reconecta
    first.onerror?.();
    expect(onDown).toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(first.close).not.toHaveBeenCalled();
  });

  it("reconnectNow pula a espera; close encerra de vez", async () => {
    const handle = openResilientEventSource({ url: "/sse/orders", events: [], onEvent: vi.fn() });
    FakeEventSource.instances[0]!.failForGood();
    handle.reconnectNow();
    expect(FakeEventSource.instances).toHaveLength(2);
    handle.reconnectNow(); // stream novo ainda conectando: não duplica
    expect(FakeEventSource.instances).toHaveLength(2);
    handle.close();
    expect(FakeEventSource.instances[1]!.close).toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(FakeEventSource.instances).toHaveLength(2);
  });

  it("entrega os eventos nomeados e o `message`", () => {
    const onEvent = vi.fn();
    openResilientEventSource({ url: "/sse/orders", events: ["backstage-orders-update"], onEvent });
    const source = FakeEventSource.instances[0]!;
    source.emit("message");
    source.emit("backstage-orders-update");
    expect(onEvent).toHaveBeenCalledTimes(2);
  });
});
