import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { usePosAutoLock } from "../app/composables/usePosAutoLock";

const lifecycle = vi.hoisted(() => ({ cleanup: [] as Array<() => void> }));
vi.mock("vue", async (original) => ({
  ...await original<typeof import("vue")>(),
  onMounted: (fn: () => void) => fn(),
  onBeforeUnmount: (fn: () => void) => lifecycle.cleanup.push(fn),
}));
let listeners: Record<string, Array<() => void>>;
let storage: Map<string, string>;
let write: ReturnType<typeof vi.fn>;
let page: { visibilityState: "visible" | "hidden" };
let pageListeners: Record<string, Array<() => void>>;
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-12T10:00:00Z"));
  listeners = {};
  storage = new Map();
  write = vi.fn((key: string, value: string) => storage.set(key, value));
  vi.stubGlobal("window", {
    localStorage: { getItem: (key: string) => storage.get(key) ?? null, setItem: write },
    addEventListener: (event: string, fn: () => void) => (listeners[event] ||= []).push(fn),
    removeEventListener: () => {},
    setInterval, clearInterval,
  });
  vi.stubGlobal("navigator", {});
  pageListeners = {};
  page = { visibilityState: "visible" };
  vi.stubGlobal("document", {
    get visibilityState() { return page.visibilityState; },
    addEventListener: (event: string, fn: () => void) => (pageListeners[event] ||= []).push(fn),
    removeEventListener: () => {},
  });
});
afterEach(() => {
  lifecycle.cleanup.splice(0).forEach((fn) => fn());
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
function tab(hold = () => false) {
  const lock = vi.fn();
  usePosAutoLock({ locked: ref(false), lock, autoLockSeconds: () => 60, holdWhen: hold });
  return lock;
}
describe("auto-lock coordenado entre abas PDV", () => {
  it("atividade somente na primeira aba impede a segunda ociosa de travar", async () => {
    const first = tab(); const second = tab();
    await vi.advanceTimersByTimeAsync(50_000);
    listeners.pointerdown![0]!();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(first).not.toHaveBeenCalled(); expect(second).not.toHaveBeenCalled();
  });
  it("ambas ociosas emitem um lock, inclusive sem Web Locks", async () => {
    const first = tab(); const second = tab();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(first.mock.calls.length + second.mock.calls.length).toBe(1);
  });
  it("pagamento na primeira aba protege ambas e devolve timeout completo ao encerrar", async () => {
    let paying = true;
    const first = tab(() => paying); const second = tab();
    await vi.advanceTimersByTimeAsync(90_000);
    expect(first).not.toHaveBeenCalled(); expect(second).not.toHaveBeenCalled();
    paying = false;
    await vi.advanceTimersByTimeAsync(55_000);
    expect(first).not.toHaveBeenCalled(); expect(second).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(first.mock.calls.length + second.mock.calls.length).toBe(1);
  });
  it("usa Web Locks quando disponível", async () => {
    const request = vi.fn(async (_name, _options, fn) => fn({ name: "lock" }));
    vi.stubGlobal("navigator", { locks: { request } });
    const lock = tab();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(request).toHaveBeenCalledTimes(1); expect(lock).toHaveBeenCalledTimes(1);
  });
  it("mantém auto-lock quando Web Locks rejeita ou storage está indisponível", async () => {
    vi.stubGlobal("navigator", { locks: { request: vi.fn().mockRejectedValue(new Error("unavailable")) } });
    write.mockImplementation(() => { throw new Error("storage disabled"); });
    const lock = tab();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(lock).toHaveBeenCalledTimes(1);
  });
  it("não escreve storage a cada pointermove", () => {
    tab();
    for (let i = 0; i < 100; i++) listeners.pointermove![0]!();
    expect(write).toHaveBeenCalledTimes(1);
  });
});

// Travar é `logout()` da sessão COMPARTILHADA por todos os apps de operador em
// `.boulangerie.com.br`. Uma aba do PDV esquecida em segundo plano (ou o PWA
// minimizado) media ociosidade só pelo que acontece NELA e derrubava o Gestor,
// o KDS e a Central em uso ativo no mesmo navegador, a cada 60 s.
describe("auto-lock com o PDV fora da vista", () => {
  function hide() { page.visibilityState = "hidden"; pageListeners.visibilitychange?.forEach((fn) => fn()); }
  function show() { page.visibilityState = "visible"; pageListeners.visibilitychange?.forEach((fn) => fn()); }

  it("aba oculta não derruba a sessão dos outros apps enquanto ninguém olha o PDV", async () => {
    const lock = tab();
    hide();
    await vi.advanceTimersByTimeAsync(10 * 60_000);
    expect(lock).not.toHaveBeenCalled();
  });

  it("ao voltar à vista depois do prazo, trava na hora, antes de qualquer toque", async () => {
    const lock = tab();
    hide();
    await vi.advanceTimersByTimeAsync(3 * 60_000);
    show();
    await vi.advanceTimersByTimeAsync(0);
    expect(lock).toHaveBeenCalledTimes(1);
  });

  it("voltar à vista dentro do prazo não trava", async () => {
    const lock = tab();
    hide();
    await vi.advanceTimersByTimeAsync(20_000);
    show();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(lock).not.toHaveBeenCalled();
  });
});
