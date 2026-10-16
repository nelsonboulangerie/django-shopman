import { mockNuxtImport, mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";

import OperatorQuickFilters from "../../app/components/OperatorQuickFilters.vue";
import {
  collapsesOnPhone,
  QUICK_FILTERS_PHONE_MAX,
  nextQuickIndex,
  quickFiltersMode,
  routeActiveKey,
  toggleQuick,
  type QuickFilterItem,
} from "../../app/presentation/quickFilters";

// Os filtros rápidos da suíte (K4): o recorte de todo dia é UM toque, com a contagem.

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn() }));
mockNuxtImport("navigateTo", () => navigateToMock);

registerEndpoint("/api/v1/backstage/saved-views/", {
  method: "GET",
  handler: () => ({
    views: [
      { id: 3, surface: "pos", screen: "preorders", name: "Entregas a receber", query: { filters: { pay: ["to_receive"], fulfillment: ["delivery"] } }, pinned: true },
      { id: 4, surface: "pos", screen: "preorders", name: "Só no painel", query: { filters: { print: ["pending"] } }, pinned: false },
    ],
  }),
});

const RECORTES: QuickFilterItem[] = [
  { key: "to_receive", label: "A receber", count: 3 },
  { key: "unprinted", label: "Sem Via Pedido", count: 0 },
  { key: "pickup", label: "Retiradas", count: 5 },
  { key: "delivery", label: "Entregas", count: 2, disabled: false },
];

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

beforeEach(() => {
  vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn() });
  navigateToMock.mockReset();
});

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

describe("as decisões puras da faixa", () => {
  it("o modo sai dos itens: todos com `to` é sub-seção; senão, um ou vários", () => {
    expect(quickFiltersMode([{ key: "a", label: "A", to: "/a" }, { key: "b", label: "B", to: "/b" }])).toBe("route");
    expect(quickFiltersMode(RECORTES)).toBe("single");
    expect(quickFiltersMode(RECORTES, true)).toBe("multiple");
  });

  it("vários: liga e desliga na ordem dos itens; um: a chave tocada", () => {
    expect(toggleQuick([], "pickup", RECORTES, true)).toEqual(["pickup"]);
    expect(toggleQuick(["pickup"], "to_receive", RECORTES, true)).toEqual(["to_receive", "pickup"]);
    expect(toggleQuick(["to_receive", "pickup"], "to_receive", RECORTES, true)).toEqual(["pickup"]);
    expect(toggleQuick("pickup", "delivery", RECORTES, false)).toBe("delivery");
  });

  it("a sub-seção ativa é a da rota; o caminho mais longo e os parâmetros declarados decidem", () => {
    const items = [
      { key: "base", label: "Base", to: "/base" },
      { key: "items", label: "Itens", to: "/base/items" },
      { key: "late", label: "Atrasados", to: "/base?view=late" },
    ];
    expect(routeActiveKey(items, { path: "/base/items/12" })).toBe("items");
    expect(routeActiveKey(items, { path: "/base", query: { view: "late" } })).toBe("late");
    expect(routeActiveKey(items, { path: "/base" })).toBe("base");
    expect(routeActiveKey(items, { path: "/outra" })).toBe("");
  });

  it("as setas dão a volta e pulam o desligado; Home e End vão às pontas", () => {
    const items = [{ key: "a", label: "A" }, { key: "b", label: "B", disabled: true }, { key: "c", label: "C" }];
    expect(nextQuickIndex(items, 0, 1)).toBe(2);
    expect(nextQuickIndex(items, 2, 1)).toBe(0);
    expect(nextQuickIndex(items, 0, -1)).toBe(2);
    expect(nextQuickIndex(items, 2, -Infinity)).toBe(0);
    expect(nextQuickIndex(items, 0, Infinity)).toBe(2);
  });

  it("até 3 rolam no celular; mais que isso viram seletor (WP-FASE2 §11)", () => {
    expect(QUICK_FILTERS_PHONE_MAX).toBe(3);
    expect(collapsesOnPhone(RECORTES.slice(0, 3))).toBe(false);
    expect(collapsesOnPhone(RECORTES)).toBe(true);
  });
});

function host(initial: string | string[], props: Record<string, unknown> = {}) {
  const value = ref<string | string[]>(initial);
  const applied: unknown[] = [];
  const Host = defineComponent({
    setup: () => () =>
      h(OperatorQuickFilters, {
        items: RECORTES,
        label: "Recortes das encomendas",
        ...props,
        modelValue: value.value,
        "onUpdate:modelValue": (next: string | string[]) => {
          value.value = next;
        },
        onApply: (query: unknown) => applied.push(query),
      }),
  });
  return { Host, value, applied };
}

describe("OperatorQuickFilters (vários recortes)", () => {
  it("desenha na ordem dos itens, com a contagem no chip da suíte e zero sem chip", async () => {
    const { Host } = host([], { multiple: true });
    mounted = await mountSuspended(Host);
    const buttons = mounted.findAll("[data-quick-filter-item]");
    expect(buttons.map((b) => b.attributes("data-quick-filter-item"))).toEqual(["to_receive", "unprinted", "pickup", "delivery"]);
    expect(buttons[0]!.text()).toContain("A receber");
    expect(buttons[0]!.find("[data-count-chip]").text()).toBe("3");
    expect(buttons[1]!.find("[data-count-chip]").exists()).toBe(false);
    expect(mounted.find("[role=toolbar]").attributes("aria-label")).toBe("Recortes das encomendas");
  });

  it("um toque liga (aria-pressed, ativo canônico) e outro desliga", async () => {
    const { Host, value } = host(["pickup"], { multiple: true });
    mounted = await mountSuspended(Host);
    const pickup = () => mounted!.find("[data-quick-filter-item=pickup]");
    expect(pickup().attributes("aria-pressed")).toBe("true");
    expect(pickup().attributes("data-quick-filter-active")).toBe("");
    // ligado é o ativo da suíte (solid primário); desligado, outline
    expect(pickup().classes()).toContain("bg-primary");
    expect(mounted.find("[data-quick-filter-item=to_receive]").classes()).not.toContain("bg-primary");
    expect(mounted.find("[data-quick-filter-item=to_receive]").classes().join(" ")).toContain("ring");
    await mounted.find("[data-quick-filter-item=to_receive]").trigger("click");
    expect(value.value).toEqual(["to_receive", "pickup"]);
    await pickup().trigger("click");
    expect(value.value).toEqual(["to_receive"]);
  });

  it("teclado: um só ponto de Tab, setas andam e Home/End vão às pontas", async () => {
    const { Host } = host([], { multiple: true });
    mounted = await mountSuspended(Host, { attachTo: document.body });
    const tabbable = mounted.findAll("[data-quick-filter-item]").filter((b) => b.attributes("tabindex") === "0");
    expect(tabbable.map((b) => b.attributes("data-quick-filter-item"))).toEqual(["to_receive"]);
    const toolbar = mounted.find("[role=toolbar]");
    (mounted.find("[data-quick-filter-item=to_receive]").element as HTMLElement).focus();
    await toolbar.trigger("keydown", { key: "ArrowRight" });
    expect(document.activeElement?.getAttribute("data-quick-filter-item")).toBe("unprinted");
    await toolbar.trigger("keydown", { key: "End" });
    expect(document.activeElement?.getAttribute("data-quick-filter-item")).toBe("delivery");
    await toolbar.trigger("keydown", { key: "ArrowRight" });
    expect(document.activeElement?.getAttribute("data-quick-filter-item")).toBe("to_receive");
  });

  it("favoritos fixados entram no fim e aplicam o recorte inteiro", async () => {
    const { Host, applied } = host([], {
      multiple: true,
      surface: "pos",
      screen: "preorders",
      query: { filters: { pay: ["to_receive"], fulfillment: ["delivery"] } },
    });
    mounted = await mountSuspended(Host);
    await vi.waitFor(() => expect(mounted!.find("[data-quick-filter-favorite]").exists()).toBe(true));
    const favorites = mounted.findAll("[data-quick-filter-favorite]");
    expect(favorites.map((f) => f.text())).toEqual(["Entregas a receber"]);
    expect(favorites[0]!.attributes("aria-pressed")).toBe("true");
    // Depois das opções, nunca antes.
    const all = mounted.findAll("[data-quick-filter-item], [data-quick-filter-favorite]");
    expect(all.at(-1)!.attributes("data-quick-filter-favorite")).toBe("3");
    await favorites[0]!.trigger("click");
    expect(applied).toEqual([{ filters: { pay: ["to_receive"], fulfillment: ["delivery"] } }]);
  });
});

describe("OperatorQuickFilters (um recorte, abas)", () => {
  it("as abas do Nuxt UI, com a ativa no v-model e a contagem no chip", async () => {
    const { Host, value } = host("pickup");
    mounted = await mountSuspended(Host, { attachTo: document.body });
    const tabs = mounted.findAll("[role=tab]");
    expect(tabs.map((t) => t.text().replace(/\d+$/, ""))).toEqual(["A receber", "Sem Via Pedido", "Retiradas", "Entregas"]);
    expect(tabs[2]!.attributes("data-state")).toBe("active");
    expect(tabs[2]!.find("[data-count-chip]").text()).toBe("5");
    await tabs[0]!.trigger("mousedown", { button: 0 });
    await nextTick();
    expect(value.value).toBe("to_receive");
  });
});

describe("OperatorQuickFilters (sub-seções)", () => {
  it("todo item com `to`: a aba navega, e a ativa é a da rota", async () => {
    const items = [
      { key: "index", label: "Início", to: "/" },
      { key: "other", label: "Outra", to: "/outra" },
    ];
    const Host = defineComponent({
      setup: () => () => h(OperatorQuickFilters, { items, label: "Seções" }),
    });
    mounted = await mountSuspended(Host, { attachTo: document.body });
    expect(mounted.find("[data-operator-quick-filters]").attributes("data-quick-filters-mode")).toBe("route");
    const tabs = mounted.findAll("[role=tab]");
    expect(tabs[0]!.attributes("data-state")).toBe("active");
    await tabs[1]!.trigger("mousedown", { button: 0 });
    await nextTick();
    expect(navigateToMock).toHaveBeenCalledWith("/outra");
  });
});

describe("OperatorQuickFilters (celular)", () => {
  it("com mais de 3 opções a faixa sai do celular e entra um seletor; com até 3, não", async () => {
    const many = host([], { multiple: true });
    mounted = await mountSuspended(many.Host);
    expect(mounted.find("[data-quick-filters-select]").exists()).toBe(true);
    expect(mounted.find("[data-quick-filters-strip]").element.parentElement?.className).toContain("max-sm:hidden");
    mounted.unmount();
    const few = host([], { multiple: true, items: RECORTES.slice(0, 3) });
    mounted = await mountSuspended(few.Host);
    expect(mounted.find("[data-quick-filters-select]").exists()).toBe(false);
    expect(mounted.find("[data-quick-filters-strip]").element.parentElement?.className).not.toContain("max-sm:hidden");
  });
});
