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
// Pote de cookies do navegador: o relógio do aparelho que TODO app de operador
// alimenta (operator-kit/app/utils/deviceActivity.ts). Aqui é host-only (sem
// `location`), o mesmo pote que as abas e as portas do mesmo host compartilham.
let jar: Map<string, string>;
let write: ReturnType<typeof vi.fn>;
let page: { visibilityState: "visible" | "hidden" };
let pageListeners: Record<string, Array<() => void>>;
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-12T10:00:00Z"));
  listeners = {};
  jar = new Map();
  write = vi.fn((serialized: string) => {
    const [pair = ""] = serialized.split(";");
    const separator = pair.indexOf("=");
    jar.set(pair.slice(0, separator).trim(), pair.slice(separator + 1).trim());
  });
  vi.stubGlobal("window", {
    addEventListener: (event: string, fn: () => void) => (listeners[event] ||= []).push(fn),
    removeEventListener: () => {},
    setInterval, clearInterval,
  });
  vi.stubGlobal("navigator", {});
  pageListeners = {};
  page = { visibilityState: "visible" };
  vi.stubGlobal("document", {
    get cookie() { return [...jar].map(([name, value]) => `${name}=${value}`).join("; "); },
    set cookie(serialized: string) { write(serialized); },
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
  it("mantém auto-lock quando Web Locks rejeita ou o cookie está indisponível", async () => {
    vi.stubGlobal("navigator", { locks: { request: vi.fn().mockRejectedValue(new Error("unavailable")) } });
    write.mockImplementation(() => { throw new Error("cookies disabled"); });
    const lock = tab();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(lock).toHaveBeenCalledTimes(1);
  });
  it("não escreve o cookie a cada pointermove", () => {
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

// A decisão do Pablo (17/09/2026): a trava é pela ociosidade do APARELHO. PDV e
// Gestor lado a lado, operador trabalhando no Gestor → o PDV não pode travar,
// porque travar derruba a sessão do Gestor junto.
describe("auto-lock pela ociosidade do aparelho", () => {
  /** Outro app de operador (Gestor, KDS…) registrou um toque no relógio. */
  function touchInOtherApp() { jar.set("shopman_operator_activity", String(Date.now())); }

  it("atividade em OUTRO app dentro do prazo adia a trava", async () => {
    const lock = tab();
    for (let second = 0; second < 5 * 60; second += 20) {
      await vi.advanceTimersByTimeAsync(20_000);
      touchInOtherApp();
    }
    expect(lock).not.toHaveBeenCalled();
  });

  it("aparelho inteiro ocioso trava no prazo contado do último toque em qualquer app", async () => {
    const lock = tab();
    await vi.advanceTimersByTimeAsync(40_000);
    touchInOtherApp();
    await vi.advanceTimersByTimeAsync(55_000);
    expect(lock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(lock).toHaveBeenCalledTimes(1);
  });

  it("voltar à vista depois de trabalhar em outro app não trava", async () => {
    const lock = tab();
    page.visibilityState = "hidden";
    for (let second = 0; second < 3 * 60; second += 30) {
      await vi.advanceTimersByTimeAsync(30_000);
      touchInOtherApp();
    }
    page.visibilityState = "visible";
    pageListeners.visibilitychange?.forEach((fn) => fn());
    await vi.advanceTimersByTimeAsync(0);
    expect(lock).not.toHaveBeenCalled();
  });

  it("oculto continua não travando mesmo com o aparelho ocioso", async () => {
    const lock = tab();
    page.visibilityState = "hidden";
    await vi.advanceTimersByTimeAsync(10 * 60_000);
    expect(lock).not.toHaveBeenCalled();
  });

  it("relógio no futuro não desliga a trava", async () => {
    const lock = tab();
    jar.set("shopman_operator_activity", String(Date.now() + 365 * 24 * 60 * 60_000));
    await vi.advanceTimersByTimeAsync(60_000);
    expect(lock).toHaveBeenCalledTimes(1);
  });

  it("travar re-ancora o relógio do aparelho", async () => {
    const lock = tab();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(lock).toHaveBeenCalledTimes(1);
    expect(Number(jar.get("shopman_operator_activity"))).toBe(Date.now());
  });
});
