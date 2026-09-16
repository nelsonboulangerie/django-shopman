import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { useWakeLock } from "../../app/composables/useWakeLock";

function visibleDocument() {
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
}

async function mountWakeLock() {
  let state!: ReturnType<typeof useWakeLock>;
  const wrapper = await mountSuspended(defineComponent({
    setup() {
      state = useWakeLock();
      return () => h("span");
    },
  }));
  await nextTick();
  return { state, wrapper };
}

beforeEach(visibleDocument);
afterEach(() => vi.restoreAllMocks());

describe("useWakeLock", () => {
  it("degrada silenciosamente quando a API não existe", async () => {
    Object.defineProperty(navigator, "wakeLock", { configurable: true, value: undefined });
    const { state, wrapper } = await mountWakeLock();

    expect(state.supported.value).toBe(false);
    await expect(state.request()).resolves.toBe(false);
    expect(state.active.value).toBe(false);
    wrapper.unmount();
  });

  it("pede screen lock, libera e pede novamente ao voltar visível", async () => {
    const listeners = new Map<string, EventListener>();
    const sentinel = {
      released: false,
      release: vi.fn().mockResolvedValue(undefined),
      addEventListener: vi.fn((name: string, listener: EventListener) => listeners.set(name, listener)),
    };
    const request = vi.fn().mockResolvedValue(sentinel);
    Object.defineProperty(navigator, "wakeLock", { configurable: true, value: { request } });
    const { state, wrapper } = await mountWakeLock();

    await vi.waitFor(() => expect(request).toHaveBeenCalledWith("screen"));
    expect(state.active.value).toBe(true);

    sentinel.released = true;
    listeners.get("release")?.(new Event("release"));
    await nextTick();
    expect(state.active.value).toBe(false);

    sentinel.released = false;
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2));

    wrapper.unmount();
    await vi.waitFor(() => expect(sentinel.release).toHaveBeenCalledOnce());
  });

  it("nunca propaga uma recusa do navegador", async () => {
    Object.defineProperty(navigator, "wakeLock", {
      configurable: true,
      value: { request: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")) },
    });
    const { state, wrapper } = await mountWakeLock();

    await expect(state.request()).resolves.toBe(false);
    expect(state.active.value).toBe(false);
    expect(state.lastError.value).toBeInstanceOf(DOMException);
    wrapper.unmount();
  });
});
