import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import { useOperatorAppLink } from "../../app/composables/useOperatorAppLink";

const CENTRAL = "https://central.boulangerie/";

/** `matchMedia` controlável: `installed` liga os display-modes de app. */
function stubDisplayMode(installed: boolean) {
  const listeners = new Set<() => void>();
  let current = installed;
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() {
      return current && /standalone|fullscreen|minimal-ui/.test(query);
    },
    addEventListener: (_: string, fn: () => void) => void listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => void listeners.delete(fn),
  }));
  return {
    /** O operador instalou o app com a tela aberta. */
    install() {
      current = true;
      for (const fn of listeners) fn();
    },
    get listenerCount() {
      return listeners.size;
    },
  };
}

async function mountLink() {
  let state!: ReturnType<typeof useOperatorAppLink>;
  const wrapper = await mountSuspended(defineComponent({
    setup() {
      state = useOperatorAppLink();
      return () => h("span");
    },
  }));
  await nextTick();
  return { state, wrapper };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useOperatorAppLink", () => {
  it("em aba de navegador, trocar de app segue na mesma aba", async () => {
    stubDisplayMode(false);
    const { state, wrapper } = await mountLink();
    expect(state.installed.value).toBe(false);
    expect(state.attrsFor(CENTRAL)).toEqual({ target: "_self" });
    wrapper.unmount();
  });

  it("instalado, o outro app ganha a janela dele", async () => {
    stubDisplayMode(true);
    const { state, wrapper } = await mountLink();
    expect(state.installed.value).toBe(true);
    expect(state.attrsFor(CENTRAL)).toEqual({ target: "_blank", rel: "noopener" });
    wrapper.unmount();
  });

  it("instalar com a tela ABERTA já muda o link, sem recarregar", async () => {
    const media = stubDisplayMode(false);
    const { state, wrapper } = await mountLink();
    expect(state.attrsFor(CENTRAL)).toEqual({ target: "_self" });

    media.install();
    await nextTick();

    expect(state.attrsFor(CENTRAL)).toEqual({ target: "_blank", rel: "noopener" });
    wrapper.unmount();
  });

  it("solta os ouvintes ao desmontar", async () => {
    const media = stubDisplayMode(true);
    const { wrapper } = await mountLink();
    expect(media.listenerCount).toBeGreaterThan(0);
    wrapper.unmount();
    expect(media.listenerCount).toBe(0);
  });
});
