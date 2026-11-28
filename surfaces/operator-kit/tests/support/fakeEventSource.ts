import { vi } from "vitest";

/**
 * EventSource de teste com o ciclo de vida que importa para o tempo real dos
 * operadores: abrir, receber evento nomeado e, sobretudo, a reconexão que recebe
 * 502 e fica CLOSED para sempre (`failForGood`), que é o caso do deploy.
 * Instale com `vi.stubGlobal("EventSource", FakeEventSource)` e zere
 * `FakeEventSource.instances` no `beforeEach`.
 */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, Array<(event: Event) => void>>();
  close = vi.fn(() => {
    this.readyState = 2;
  });
  constructor(
    public url: string,
    public init?: { withCredentials?: boolean },
  ) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(name: string, handler: (event: Event) => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), handler]);
  }
  emit(name: string, data = "{}") {
    for (const handler of this.listeners.get(name) ?? []) handler(new MessageEvent(name, { data }));
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  /** A reconexão recebeu 502: o navegador desiste e o stream fica CLOSED. */
  failForGood() {
    this.readyState = 2;
    this.onerror?.();
  }
  /** Os streams ainda vivos (não fechados por quem os abriu). */
  static alive(): FakeEventSource[] {
    return FakeEventSource.instances.filter((source) => source.close.mock.calls.length === 0);
  }
}
