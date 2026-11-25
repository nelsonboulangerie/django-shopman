import { afterEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { nextTick } from "vue";

import OperatorLoadingFeedback from "../../app/components/OperatorLoadingFeedback.vue";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

// Monta sob timers REAIS e só então liga os falsos: o `mountSuspended` do kit
// (env `nuxt`) depende de timers reais internos e trava se os fake ligam antes.
function advanceToNextPaint() {
  vi.advanceTimersByTime(17);
}

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("OperatorLoadingFeedback", () => {
  it("fica silencioso até 200ms e então mostra o aviso de espera", async () => {
    mounted = await mountSuspended(OperatorLoadingFeedback);
    const nuxtApp = useNuxtApp();
    vi.useFakeTimers();

    await nuxtApp.callHook("page:start");
    await nextTick();

    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(false);
    expect(mounted.get("[role=\"status\"]").text()).toBe("");

    vi.advanceTimersByTime(199);
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(false);

    vi.advanceTimersByTime(1);
    advanceToNextPaint();
    await nextTick();

    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(true);
    expect(mounted.get("[data-operator-loading-card]").text()).toContain("Carregando…");
    expect(mounted.get("[data-operator-loading-card]").text()).toContain("Só um instante.");
    expect(mounted.get("[role=\"status\"]").text()).toContain("Carregando…");
  });

  // DEV-2026-094: a espera começa no início da navegação (antes do middleware) e o
  // link tocado fica marcado no mesmo instante, até a página chegar.
  it("começa no page:loading:start e marca o link tocado até o fim", async () => {
    mounted = await mountSuspended(OperatorLoadingFeedback);
    const nuxtApp = useNuxtApp();
    const link = document.createElement("a");
    link.href = "/outra-tela";
    link.addEventListener("click", (event) => event.preventDefault());
    document.body.append(link);
    vi.useFakeTimers();

    link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
    expect(link.getAttribute("aria-busy")).toBe("true");
    expect(link.hasAttribute("data-navigation-pending")).toBe(true);

    await nuxtApp.callHook("page:loading:start");
    vi.advanceTimersByTime(200);
    advanceToNextPaint();
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(true);

    await nuxtApp.callHook("page:loading:end");
    vi.advanceTimersByTime(400);
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(false);
    expect(link.hasAttribute("aria-busy")).toBe(false);
    expect(link.hasAttribute("data-navigation-pending")).toBe(false);
  });

  it("o atalho para outro app começa a espera no toque", async () => {
    mounted = await mountSuspended(OperatorLoadingFeedback);
    const link = document.createElement("a");
    link.href = "https://pdv.exemplo.test/";
    link.addEventListener("click", (event) => event.preventDefault());
    document.body.append(link);
    vi.useFakeTimers();

    link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
    expect(link.getAttribute("aria-busy")).toBe("true");
    vi.advanceTimersByTime(200);
    advanceToNextPaint();
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(true);
  });

  it("não mostra nada numa navegação que termina em até 200ms", async () => {
    mounted = await mountSuspended(OperatorLoadingFeedback);
    const nuxtApp = useNuxtApp();
    vi.useFakeTimers();

    await nuxtApp.callHook("page:start");
    vi.advanceTimersByTime(200);
    await nuxtApp.callHook("page:finish");
    advanceToNextPaint();
    await nextTick();

    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(false);
    expect(mounted.get("[role=\"status\"]").text()).toBe("");
  });

  it("evita um clarão curto depois que o aviso já apareceu", async () => {
    mounted = await mountSuspended(OperatorLoadingFeedback);
    const nuxtApp = useNuxtApp();
    vi.useFakeTimers();

    await nuxtApp.callHook("page:start");
    vi.advanceTimersByTime(200);
    advanceToNextPaint();
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(true);

    await nuxtApp.callHook("page:finish");
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(true);

    vi.advanceTimersByTime(300);
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(true);

    vi.advanceTimersByTime(20);
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(false);
  });

  it("o watchdog solta o aviso se a navegação não terminar", async () => {
    mounted = await mountSuspended(OperatorLoadingFeedback);
    const nuxtApp = useNuxtApp();
    vi.useFakeTimers();

    await nuxtApp.callHook("page:start");
    vi.advanceTimersByTime(200);
    advanceToNextPaint();
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(true);

    vi.advanceTimersByTime(15_000);
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(false);
  });

  it("o erro do app e o retorno do bfcache soltam o aviso na hora", async () => {
    mounted = await mountSuspended(OperatorLoadingFeedback);
    const nuxtApp = useNuxtApp();
    vi.useFakeTimers();

    await nuxtApp.callHook("page:start");
    vi.advanceTimersByTime(200);
    advanceToNextPaint();
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(true);

    window.dispatchEvent(new Event("pageshow"));
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(false);

    // O mesmo vale para erro não tratado do app.
    await nuxtApp.callHook("page:start");
    vi.advanceTimersByTime(200);
    advanceToNextPaint();
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(true);

    await nuxtApp.callHook("app:error");
    await nextTick();
    expect(mounted.find("[data-operator-loading-overlay]").exists()).toBe(false);
  });
});
