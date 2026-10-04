import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  computed,
  defineComponent,
  h,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { mount, type VueWrapper } from "@vue/test-utils";

import ProductionHeader from "../../app/components/ProductionHeader.vue";
import { toolSections } from "../../app/presentation/productionSections";

// V4-PROD: o cabeçalho é o `OperatorPageHeader` da suíte (uma linha). As etapas saíram
// daqui para o rail e a barra do polegar (`ProductionNav`, testado em
// `ProductionNav.test.ts`); o cabeçalho continua dono das TECLAS (Alt+1 a Alt+5, "/",
// R e "?"), do progresso do dia e do ⋯ (Atualizar, Timers, Atalhos). A ajuda de atalhos
// e os Avisos são do kit (V6-KIT): a barra de 56px não tem Timers nem sino próprios.

const navigateSpy = vi.fn();
let wrapper: VueWrapper | null = null;

// O cabeçalho da suíte é do kit (testado lá): aqui ele só precisa render os slots.
const OperatorPageHeaderStub = defineComponent({
  props: { title: String, eyebrow: String },
  setup(props, { slots }) {
    return () =>
      h("header", [
        h("h1", props.title),
        slots.status?.(),
        slots.search?.(),
        h("div", { "data-phone": "" }, slots["phone-actions"]?.()),
        h("div", { "data-actions": "" }, slots.actions?.()),
        slots.filters?.(),
      ]);
  },
});

const UiSearchInputStub = defineComponent({
  inheritAttrs: false,
  props: { modelValue: { type: String, default: "" }, shortcut: String },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit, expose }) {
    const input = ref<HTMLInputElement | null>(null);
    expose({ focus: () => input.value?.focus() });
    return () =>
      h("input", {
        ...attrs,
        ref: input,
        type: "search",
        value: props.modelValue,
        "aria-keyshortcuts": props.shortcut,
        onInput: (event: Event) =>
          emit("update:modelValue", (event.target as HTMLInputElement).value),
      });
  },
});

const menuOpen = ref(false);
const stubs = {
  OperatorPageHeader: OperatorPageHeaderStub,
  OperatorLiveStatus: {
    props: ["tone", "time", "label"],
    template: '<span data-live :data-tone="tone">{{ label }}</span>',
  },
  UiSearchInput: UiSearchInputStub,
  Icon: true,
  NuxtLink: {
    props: ["to"],
    template: '<a :href="to"><slot /></a>',
  },
  // O ⋯ é um popover: o conteúdo existe enquanto está aberto.
  UiPopover: {
    props: ["open"],
    emits: ["update:open"],
    template: "<div><slot /></div>",
  },
  UiPopoverTrigger: { template: "<div><slot /></div>" },
  UiPopoverContent: { template: "<div data-menu><slot /></div>" },
};

const shortcutsOpen = ref(false);
const provideShortcuts = vi.fn();
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

function mountHeader(props: Record<string, unknown> = { title: "Planejamento" }) {
  return mount(ProductionHeader, {
    props,
    global: { stubs },
    attachTo: document.body,
  });
}

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useRoute", () => ({ path: "/plan" }));
  vi.stubGlobal("navigateTo", navigateSpy);
  vi.stubGlobal("useOperatorShortcuts", () => ({ open: shortcutsOpen }));
  vi.stubGlobal("provideOperatorShortcuts", provideShortcuts);
  vi.stubGlobal("useFloorTimers", () => ({
    activeCount: computed(() => timersActive.value),
    ringingCount: computed(() => timersRinging.value),
  }));
  vi.stubGlobal("useProductionSections", () => ({
    tools: computed(() =>
      toolSections({ canViewRecipes: true, canViewReports: false }),
    ),
  }));
  navigateSpy.mockClear();
  timersActive.value = 0;
  timersRinging.value = 0;
  menuOpen.value = false;
  shortcutsOpen.value = false;
  provideShortcuts.mockClear();
  wrapper = mountHeader();
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

  it("Alt+1 a Alt+5 percorrem o ciclo do lote, de Planejamento a Qualidade", () => {
    for (const digit of [1, 2, 3, 4, 5]) {
      press(String(digit), { altKey: true, code: `Digit${digit}` });
    }

    expect(navigateSpy.mock.calls.map(([to]) => to)).toEqual([
      "/plan",
      "/mise-en-place",
      "/",
      "/close",
      "/quality",
    ]);
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

    expect(shortcutsOpen.value).toBe(true);
    expect(
      wrapper!.find('input[type="search"]').attributes("aria-keyshortcuts"),
    ).toBe("/");
    expect(
      wrapper!.find("[data-header-refresh]").attributes("aria-keyshortcuts"),
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

describe("ProductionHeader — o ⋯ e o progresso do dia", () => {
  it("Atualizar mora no ⋯ e pede a releitura", async () => {
    await wrapper!.find("[data-header-refresh]").trigger("click");
    expect(wrapper!.emitted("refresh")).toHaveLength(1);
  });

  it("Atalhos desta tela abre a ajuda pelo ⋯", async () => {
    await wrapper!
      .find('button[aria-label="Ver atalhos do teclado"]')
      .trigger("click");
    expect(shortcutsOpen.value).toBe(true);
  });

  it("no celular, o ⋯ leva às ferramentas que no tablet moram no rail", () => {
    const links = wrapper!
      .findAll("[data-menu] a")
      .map((link) => link.attributes("href"));
    expect(links).toEqual(["/timers", "/recipes", "/board"]);
  });

  it("o contador fala 'N de M' com a barra junto", () => {
    wrapper?.unmount();
    wrapper = mountHeader({
      title: "Planejamento",
      count: 4,
      total: 28,
      countLabel: "planejados",
      progress: 14,
    });
    const progress = wrapper.find("[data-header-progress]");
    expect(progress.text().replace(/\s+/g, " ")).toBe("4 de 28 planejados");
    expect(progress.find('[role="progressbar"]').attributes("aria-valuenow")).toBe("14");
  });

  it("dado velho: o ao vivo fala por extenso", () => {
    wrapper?.unmount();
    wrapper = mountHeader({ title: "Abertura", stale: true });
    const live = wrapper.find("[data-live]");
    expect(live.attributes("data-tone")).toBe("late");
    expect(live.text()).toBe("Sem atualizar");
  });
});

// V6-KIT: a ajuda de atalhos é a do kit; a Produção entrega os grupos dela. A barra de
// 56px é a da v4 (selo, título, ao vivo, lupa, Avisos): Timers mora no "Mais" e no ⋯.
describe("ProductionHeader — peças do kit", () => {
  it("entrega os grupos de teclas da tela à ajuda do kit", () => {
    expect(provideShortcuts).toHaveBeenCalledOnce();
    const groups = provideShortcuts.mock.calls[0]![0] as Array<{ title: string }>;
    expect(groups.map((group) => group.title)).toContain("QC e timer");
  });

  it("a barra de 56px não leva Timers nem sino próprio", () => {
    expect(wrapper!.find("[data-phone]").text()).toBe("");
    expect(wrapper!.find('a[aria-label^="Timers"]').exists()).toBe(false);
  });
});
