import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { usePwaInstall } from "../../app/composables/usePwaInstall";

const NOW = Date.UTC(2026, 8, 16);
const DAY = 24 * 60 * 60 * 1_000;

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
  Object.defineProperty(navigator, "userAgent", { configurable: true, value: "Mozilla/5.0 (Linux; Android 15) Chrome/126.0.0.0 Mobile Safari/537.36" });
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
    expect(state.plan.value.kind).toBe("prompt");
    expect(prompt).not.toHaveBeenCalled();
    await expect(state.install()).resolves.toBe(true);
    expect(prompt).toHaveBeenCalledOnce();
    wrapper.unmount();
  });

  it("sem prompt no Android ensina o menu do navegador, e não o Safari", async () => {
    const { state, wrapper } = await mountInstall();
    expect(state.plan.value.kind).toBe("steps");
    expect(state.canInvite.value).toBe(true);
    const texto = state.plan.value.steps.map((step) => step.text).join(" ");
    expect(texto).toContain("⋮");
    expect(texto).not.toContain("Safari");
    wrapper.unmount();
  });

  it("no iPhone ensina o gesto do iOS e silencia por sete dias mesmo sem storage", async () => {
    Object.defineProperty(navigator, "userAgent", { configurable: true, value: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1" });
    Object.defineProperty(navigator, "platform", { configurable: true, value: "iPhone" });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
    const { state, wrapper } = await mountInstall();

    expect(state.plan.value.os).toBe("ios");
    expect(state.plan.value.steps[0]?.text).toContain("Compartilhar");
    expect(() => state.dismiss()).not.toThrow();
    expect(state.dismissedUntil.value).toBe(NOW + 7 * DAY);
    expect(state.isDismissed.value).toBe(true);
    expect(state.canInvite.value).toBe(false);
    wrapper.unmount();
  });

  it("'já instalei' encerra o convite de vez, e não por uma semana", async () => {
    // Quem seguiu os passos não tem como ser detectado daqui — o iOS não avisa. Quem
    // sabe é ela, e repetir o convite na semana seguinte gasta a paciência dela.
    const { state, wrapper } = await mountInstall();
    state.dismissAsDone();
    expect(state.dismissedUntil.value).toBe(NOW + 365 * DAY);
    wrapper.unmount();
  });

  it("no computador sem prompt o convite não sobe sozinho", async () => {
    Object.defineProperty(navigator, "userAgent", { configurable: true, value: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36" });
    Object.defineProperty(navigator, "platform", { configurable: true, value: "Win32" });
    const { state, wrapper } = await mountInstall();
    expect(state.plan.value.kind).toBe("steps");
    expect(state.canInvite.value).toBe(false);
    wrapper.unmount();
  });
});
