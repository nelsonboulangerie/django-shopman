import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  computed,
  defineComponent,
  h,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
  type PropType,
} from "vue";
import { mount, type VueWrapper } from "@vue/test-utils";

import ProductionHeader from "../../app/components/ProductionHeader.vue";
import type { OperatorHeaderAction } from "../../../operator-kit/app/presentation/pageHeader";

// Fase 2: o cabeçalho é o `OperatorPageHeader` do kit, dentro do shell da suíte. As
// etapas (Alt+1 a Alt+5), a busca "/" e a ajuda "?" são do shell e da busca da suíte;
// aqui ficam o R (Atualizar), o ⋯ como DADOS (as ações da tela e Atualizar), o dia na
// toolbar (`#primary`) e o progresso no fim dela.

let wrapper: VueWrapper | null = null;
let headerActions: OperatorHeaderAction[] = [];

// O cabeçalho da suíte é do kit (testado lá): aqui ele só expõe props e slots.
const OperatorPageHeaderStub = defineComponent({
  props: {
    title: String,
    eyebrow: String,
    actions: { type: Array as PropType<OperatorHeaderAction[]>, default: () => [] },
    alerts: { type: Array, default: () => [] },
  },
  setup(props, { slots }) {
    return () => {
      headerActions = props.actions;
      return h("header", [
        h("h1", props.title),
        h("div", { "data-status": "" }, slots.status?.()),
        slots.search?.(),
        h("div", { "data-primary": "" }, slots["filters-primary"]?.()),
        h("div", { "data-filters": "" }, slots.filters?.()),
        h("div", { "data-end": "" }, slots["filters-end"]?.()),
        h("div", { "data-alerts": props.alerts.length }),
      ]);
    };
  },
});

const stubs = {
  OperatorPageHeader: OperatorPageHeaderStub,
  OperatorLiveStatus: {
    props: ["tone", "time", "label"],
    template: '<span data-live :data-tone="tone">{{ label }}</span>',
  },
  OperatorSuiteSearch: {
    props: ["modelValue", "screenLabel"],
    template: '<input type="search" :data-screen-label="screenLabel" />',
  },
  NuxtProgress: {
    props: ["modelValue"],
    template: '<div role="progressbar" :aria-valuenow="modelValue" />',
  },
};

const provideShortcuts = vi.fn();

function press(key: string, overrides: KeyboardEventInit = {}, target: HTMLElement | Window = window) {
  target.dispatchEvent(
    new KeyboardEvent("keydown", { key, code: overrides.code ?? key, bubbles: true, cancelable: true, ...overrides }),
  );
}

function mountHeader(props: Record<string, unknown> = { title: "Planejamento" }, slots = {}) {
  return mount(ProductionHeader, { props, slots, global: { stubs }, attachTo: document.body });
}

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("provideOperatorShortcuts", provideShortcuts);
  provideShortcuts.mockClear();
  wrapper = mountHeader();
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
  vi.unstubAllGlobals();
  document.querySelector("[data-production-shortcut-scope]")?.remove();
});

describe("ProductionHeader — teclas", () => {
  it("R relê fora de campo; dentro de um campo, R é letra", () => {
    const input = wrapper!.find('input[type="search"]');
    press("r", {}, input.element as HTMLInputElement);
    expect(wrapper!.emitted("refresh")).toBeUndefined();
    press("r");
    expect(wrapper!.emitted("refresh")).toHaveLength(1);
  });

  it("Alt+número é do shell: o cabeçalho não navega nem relê", () => {
    press("€", { altKey: true, code: "Digit2" });
    expect(wrapper!.emitted("refresh")).toBeUndefined();
  });

  it("não relê por baixo de um fluxo exclusivo", () => {
    const blocker = document.createElement("div");
    blocker.dataset.productionShortcutScope = "exclusive";
    document.body.append(blocker);
    press("r");
    expect(wrapper!.emitted("refresh")).toBeUndefined();
  });

  it("entrega os grupos de teclas da Produção à ajuda do kit", () => {
    expect(provideShortcuts).toHaveBeenCalledOnce();
    const groups = provideShortcuts.mock.calls[0]![0] as Array<{ title: string }>;
    expect(groups.map((group) => group.title)).toContain("QC e timer");
  });
});

describe("ProductionHeader — o ⋯ como dados", () => {
  it("as ações da tela vêm antes de Atualizar, que leva a tecla R", () => {
    wrapper?.unmount();
    const onSelect = vi.fn();
    wrapper = mountHeader({ title: "Fechamento", actions: [{ label: "Lote avulso", icon: "i-lucide-plus", onSelect }] });
    expect(headerActions.map((action) => action.label)).toEqual(["Lote avulso", "Atualizar"]);
    expect(headerActions[1]!.kbds).toEqual(["R"]);
    headerActions[1]!.onSelect?.();
    expect(wrapper.emitted("refresh")).toHaveLength(1);
  });

  it("a busca declara o que filtra nesta tela", () => {
    wrapper?.unmount();
    wrapper = mountHeader({ title: "Qualidade", searchLabel: "filtrando os lotes" });
    expect(wrapper.find('input[type="search"]').attributes("data-screen-label")).toBe("filtrando os lotes");
  });
});

describe("ProductionHeader — toolbar e estado", () => {
  it("o dia vai para o começo da toolbar; o progresso, para o fim", () => {
    wrapper?.unmount();
    wrapper = mountHeader(
      { title: "Planejamento", count: 4, total: 28, countLabel: "planejados", progress: 14 },
      { primary: '<span data-day>Hoje</span>' },
    );
    expect(wrapper.find("[data-primary] [data-day]").exists()).toBe(true);
    const progress = wrapper.find("[data-end] [data-header-progress]");
    expect(progress.text().replace(/\s+/g, " ")).toBe("4 de 28 planejados");
    expect(progress.find('[role="progressbar"]').attributes("aria-valuenow")).toBe("14");
  });

  it("dado velho: o ao vivo fala por extenso", () => {
    wrapper?.unmount();
    wrapper = mountHeader({ title: "Abertura", stale: true });
    const live = wrapper.find("[data-status] [data-live]");
    expect(live.attributes("data-tone")).toBe("late");
    expect(live.text()).toBe("Sem atualizar");
  });
});
