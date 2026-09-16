import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { usePwaInstall } from "../../app/composables/usePwaInstall";

const NOW = Date.UTC(2026, 8, 16);

async function mountInstall() {
  let state!: ReturnType<typeof usePwaInstall>;
  const wrapper = await mountSuspended(defineComponent({
    setup() {
      state = usePwaInstall({ app: "pos", now: () => NOW });
      return () => h("span");
    },
  }));
  await nextTick();
  return { state, wrapper };
}

beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(navigator, "userAgent", { configurable: true, value: "Mozilla/5.0 (Linux; Android 15) Chrome" });
  Object.defineProperty(navigator, "platform", { configurable: true, value: "Linux armv8l" });
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("usePwaInstall", () => {
  it("captura o prompt sem dispará-lo antes do gesto", async () => {
    const { state, wrapper } = await mountInstall();
    const prompt = vi.fn().mockResolvedValue(undefined);
    const event = new Event("beforeinstallprompt", { cancelable: true }) as Event & {
      prompt: () => Promise<void>;
      userChoice: Promise<{ outcome: "accepted"; platform: string }>;
    };
    event.prompt = prompt;
    event.userChoice = Promise.resolve({ outcome: "accepted", platform: "web" });

    window.dispatchEvent(event);
    await nextTick();
    expect(state.canInstall.value).toBe(true);
    expect(prompt).not.toHaveBeenCalled();
    await expect(state.install()).resolves.toBe(true);
    expect(prompt).toHaveBeenCalledOnce();
    wrapper.unmount();
  });

  it("reconhece iOS e silencia por sete dias mesmo sem storage", async () => {
    Object.defineProperty(navigator, "userAgent", { configurable: true, value: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari" });
    Object.defineProperty(navigator, "platform", { configurable: true, value: "iPhone" });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
    const { state, wrapper } = await mountInstall();

    expect(state.isIos.value).toBe(true);
    expect(() => state.dismiss()).not.toThrow();
    expect(state.dismissedUntil.value).toBe(NOW + 7 * 24 * 60 * 60 * 1_000);
    expect(state.isDismissed.value).toBe(true);
    wrapper.unmount();
  });
});
