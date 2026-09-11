import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, type VueWrapper } from "vue";

import OperatorSonner from "../../app/components/OperatorSonner.vue";

const ToasterStub = defineComponent({
  name: "Toaster",
  props: {
    position: String,
    richColors: Boolean,
    visibleToasts: Number,
    closeButton: Boolean,
    duration: Number,
    theme: String,
    style: Object,
    toastOptions: Object,
  },
  template: '<div data-testid="toaster" />',
});

const mounted: VueWrapper[] = [];
beforeEach(() => {
  // O layer não instala @nuxtjs/color-mode sozinho; quem fornece o composable é
  // cada app hospedeiro. No teste da fonte, simulamos exatamente esse contrato.
  vi.stubGlobal("useColorMode", () => ({ value: "dark" }));
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
});

describe("OperatorSonner", () => {
  it("mantém o toast visível no topo e diferencia os tons semânticos", async () => {
    const wrapper = await mountSuspended(OperatorSonner, {
      global: { stubs: { Toaster: ToasterStub } },
    });
    mounted.push(wrapper as unknown as VueWrapper);

    const toaster = wrapper.getComponent(ToasterStub);
    expect(toaster.props()).toMatchObject({
      position: "top-center",
      richColors: true,
      visibleToasts: 3,
      closeButton: true,
      duration: 7000,
      theme: "dark",
    });
    expect(toaster.props("style")).toMatchObject({
      "--success-bg": "var(--success)",
      "--success-text": "var(--success-foreground)",
      "--error-bg": "var(--destructive)",
      "--error-text": "var(--destructive-foreground)",
      "--warning-bg": "var(--warning)",
      "--warning-text": "var(--warning-foreground)",
    });
  });
});
