import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { mount, type VueWrapper } from "@vue/test-utils";

import ProductionHeader from "../../app/components/ProductionHeader.vue";
import { UiButtonStub, UiInputStub } from "../support/nativeUiStubs";

const navigateSpy = vi.fn();
let wrapper: VueWrapper | null = null;

const stubs = {
  RailToggle: true,
  AlertsBell: true,
  Icon: true,
  OperatorKbd: true,
  UiButton: UiButtonStub,
  UiInput: UiInputStub,
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

const timersActive = ref(0);
const timersRinging = ref(0);

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
  vi.stubGlobal("useFloorTimers", () => ({
    activeCount: computed(() => timersActive.value),
    ringingCount: computed(() => timersRinging.value),
  }));
  navigateSpy.mockClear();
  timersActive.value = 0;
  timersRinging.value = 0;
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
  it("navega pelas etapas com Alt+número e preserva as teclas de função", () => {
    press("€", { altKey: true, code: "Digit2" });
    press("F1");

    expect(navigateSpy).toHaveBeenCalledOnce();
    expect(navigateSpy).toHaveBeenCalledWith("/mise-en-place");
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

    press("#", { altKey: true, code: "Digit3" });

    expect(navigateSpy).not.toHaveBeenCalled();
  });
});

// O botão de timers LEVA à página /timers (o diálogo morreu em 18/09/2026);
// o que o cabeçalho ainda prova é o contador e o link.
describe("ProductionHeader — timers da bancada", () => {
  it("o botão Timers mostra os ativos depois de montar e leva a /timers", async () => {
    timersActive.value = 2;
    wrapper?.unmount();
    wrapper = mount(ProductionHeader, {
      props: { title: "Produção" },
      global: { stubs },
      attachTo: document.body,
    });
    await nextTick();

    const link = wrapper.find('a[aria-label="Timers (2 ativos)"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("href")).toBe("/timers");
    expect(link.text()).toContain("2");
  });

  it("sem timer ativo não há badge — e o link continua lá", () => {
    const link = wrapper!.find('a[aria-label="Timers (0 ativos)"]');
    expect(link.exists()).toBe(true);
    expect(link.text()).not.toMatch(/\d/);
  });
});
