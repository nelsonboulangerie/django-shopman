import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { mount, type VueWrapper } from "@vue/test-utils";

import ProductionHeader from "../../app/components/ProductionHeader.vue";

const navigateSpy = vi.fn();
let wrapper: VueWrapper | null = null;

const stubs = {
  RailToggle: true,
  AlertsBell: true,
  Icon: true,
  NuxtLink: {
    props: ["to"],
    template: '<a :href="to"><slot /></a>',
  },
  ProductionShortcutsHelp: {
    props: ["open"],
    emits: ["update:open"],
    template: '<div v-if="open" data-shortcuts-help />',
  },
};

function press(
  key: string,
  overrides: KeyboardEventInit = {},
  target: HTMLElement | Window = window,
) {
  target.dispatchEvent(
    new KeyboardEvent("keydown", {
      key,
      code: overrides.code ?? key,
      bubbles: true,
      cancelable: true,
      ...overrides,
    }),
  );
}

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useRoute", () => ({ path: "/plan" }));
  vi.stubGlobal("navigateTo", navigateSpy);
  navigateSpy.mockClear();
  wrapper = mount(ProductionHeader, {
    props: { title: "Planejamento" },
    global: { stubs },
    attachTo: document.body,
  });
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
  vi.unstubAllGlobals();
  document.querySelector("[data-production-shortcut-scope]")?.remove();
});

describe("ProductionHeader — atalhos descobríveis", () => {
  it("navega pelas etapas com função ou Alt+número", () => {
    press("F4");
    press("€", { altKey: true, code: "Digit2" });

    expect(navigateSpy).toHaveBeenNthCalledWith(1, "/expedite");
    expect(navigateSpy).toHaveBeenNthCalledWith(2, "/mise-en-place");
  });

  it("foca a busca com / e não sequestra R enquanto o campo é editado", async () => {
    const input = wrapper!.find('input[type="search"]');
    press("/");
    await nextTick();
    expect(document.activeElement).toBe(input.element);

    press("r", {}, input.element as HTMLInputElement);
    expect(wrapper!.emitted("refresh")).toBeUndefined();

    (input.element as HTMLInputElement).blur();
    press("r");
    expect(wrapper!.emitted("refresh")).toHaveLength(1);
  });

  it("abre a ajuda por ? e anuncia os atalhos nos controles", async () => {
    press("?");
    await nextTick();

    expect(wrapper!.find("[data-shortcuts-help]").exists()).toBe(true);
    expect(
      wrapper!.find('input[type="search"]').attributes("aria-keyshortcuts"),
    ).toBe("/");
    expect(
      wrapper!
        .find('button[aria-label="Atualizar"]')
        .attributes("aria-keyshortcuts"),
    ).toBe("R");
  });

  it("não navega por baixo de um fluxo exclusivo", () => {
    const blocker = document.createElement("div");
    blocker.dataset.productionShortcutScope = "exclusive";
    document.body.append(blocker);

    press("F3");

    expect(navigateSpy).not.toHaveBeenCalled();
  });
});
