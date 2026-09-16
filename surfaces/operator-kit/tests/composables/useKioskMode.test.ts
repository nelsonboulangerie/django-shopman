import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { useKioskMode } from "../../app/composables/useKioskMode";

async function mountKiosk(options: Parameters<typeof useKioskMode>[0] = {}) {
  let state!: ReturnType<typeof useKioskMode>;
  const wrapper = await mountSuspended(defineComponent({
    setup() {
      state = useKioskMode(options);
      return () => h("span");
    },
  }));
  await nextTick();
  return { state, wrapper };
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useKioskMode", () => {
  it("degrada silenciosamente sem Fullscreen API", async () => {
    Object.defineProperty(document.documentElement, "requestFullscreen", { configurable: true, value: undefined });
    const { state, wrapper } = await mountKiosk();
    expect(state.supported.value).toBe(false);
    await expect(state.enter()).resolves.toBe(false);
    wrapper.unmount();
  });

  it("entra em fullscreen somente quando chamado explicitamente", async () => {
    const requestFullscreen = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(document.documentElement, "requestFullscreen", { configurable: true, value: requestFullscreen });
    const { state, wrapper } = await mountKiosk();

    expect(requestFullscreen).not.toHaveBeenCalled();
    await expect(state.enter()).resolves.toBe(true);
    expect(requestFullscreen).toHaveBeenCalledOnce();
    wrapper.unmount();
  });

  it("marca o kiosk ocioso após 60 s e atividade reinicia o prazo", async () => {
    const onIdle = vi.fn();
    const { state, wrapper } = await mountKiosk({ idleMs: 60_000, onIdle });
    // O mount do Nuxt usa timers próprios; congelar antes dele impede o Suspense de
    // concluir. A partir daqui, `markActive` troca o timer real por um controlado.
    vi.useFakeTimers();
    state.markActive();

    await vi.advanceTimersByTimeAsync(30_000);
    window.dispatchEvent(new Event("pointerdown"));
    await vi.advanceTimersByTimeAsync(59_999);
    expect(state.isIdle.value).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(state.isIdle.value).toBe(true);
    expect(onIdle).toHaveBeenCalledOnce();
    wrapper.unmount();
  });
});
