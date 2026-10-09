import { mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";

import OperatorFilterPanel from "../../app/components/OperatorFilterPanel.vue";
import type { PeriodSelection } from "../../app/presentation/dates";
import {
  activeRecortes,
  filterPanelLabel,
  panelDimensions,
  queryToSave,
  sameQuery,
} from "../../app/presentation/filterPanel";
import type { ActiveFilters, FilterDimension } from "../../app/types/filters";

const dimensions: FilterDimension[] = [
  {
    id: "status",
    label: "Situação",
    type: "multi-select",
    options: [
      { value: "done", label: "Concluído", count: 12 },
      { value: "cancelled", label: "Cancelado", count: 3 },
    ],
  },
  { id: "customer", label: "Cliente", type: "text", options: [] },
  { id: "total", label: "Total", type: "number-range", options: [] },
];
const DAY: PeriodSelection = { preset: "day", from: "", to: "" };

const posted: unknown[] = [];
registerEndpoint("/api/v1/backstage/saved-views/", {
  method: "GET",
  handler: () => ({
    views: [
      {
        id: 7,
        surface: "orders",
        screen: "history",
        name: "Cancelados da semana",
        query: { filters: { status: ["cancelled"] }, period: { preset: "7d", from: "", to: "" } },
        pinned: true,
      },
    ],
  }),
});
registerEndpoint("/api/v1/backstage/saved-views/", {
  method: "POST",
  handler: async (event: { node?: { req?: unknown } } & Record<string, unknown>) => {
    const { readBody } = await import("h3");
    const body = await readBody(event as never);
    posted.push(body);
    return { ok: true, view: { id: 8, ...(body as object), pinned: false } };
  },
});

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

// O toast é do app hospedeiro (o kit não o declara fora do catálogo).
beforeEach(() => {
  vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn() });
});

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

describe("as decisões puras do painel", () => {
  it("conta os recortes: dimensões com valor, período e agrupamento fora do padrão", () => {
    expect(activeRecortes(dimensions, { filters: {} }, { period: DAY })).toBe(0);
    expect(
      activeRecortes(
        dimensions,
        { filters: { status: ["done"], customer: ["ana"] }, period: { preset: "7d", from: "", to: "" }, group: "channel" },
        { period: DAY, group: "" },
      ),
    ).toBe(4);
    expect(filterPanelLabel(0)).toBe("Filtros");
    expect(filterPanelLabel(1)).toBe("Filtros: 1 recorte ativo");
    expect(filterPanelLabel(3)).toBe("Filtros: 3 recortes ativos");
  });

  it("o mesmo recorte, em qualquer ordem, é o mesmo favorito", () => {
    expect(
      sameQuery(
        { filters: { status: ["done", "cancelled"], x: [] }, period: DAY },
        { filters: { status: ["cancelled", "done"] }, period: DAY },
      ),
    ).toBe(true);
    expect(sameQuery({ filters: {} }, { filters: {}, group: "channel" })).toBe(false);
    expect(queryToSave({ filters: { status: ["done"], vazio: [""] }, period: DAY })).toEqual({
      filters: { status: ["done"] },
      period: DAY,
    });
  });

  it("o painel edita as listas e o texto; intervalo fica com o FilterBar", () => {
    expect(panelDimensions(dimensions).map((dimension) => dimension.id)).toEqual(["status", "customer"]);
  });
});

function host(initial: ActiveFilters = {}) {
  const filters = ref<ActiveFilters>(initial);
  const period = ref<PeriodSelection>(DAY);
  const Host = defineComponent({
    setup: () => () =>
      h(OperatorFilterPanel, {
        modelValue: filters.value,
        "onUpdate:modelValue": (next: ActiveFilters) => (filters.value = next),
        period: period.value,
        "onUpdate:period": (next: PeriodSelection) => (period.value = next),
        dimensions,
        quick: [{ dimension: "status", value: "cancelled", label: "Cancelados" }],
        periodPresets: ["day", "7d"],
        customPeriod: true,
        defaultPeriod: DAY,
        today: "2026-10-09",
        groups: [{ value: "channel", label: "Canal" }],
        surface: "orders",
        screen: "history",
      }),
  });
  return { Host, filters, period };
}

const openButton = () => document.querySelector<HTMLElement>("[data-operator-filter-panel-open]")!;
const panel = () => document.querySelector<HTMLElement>("[data-operator-filter-panel]");
async function settle() {
  for (let i = 0; i < 4; i++) {
    await nextTick();
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}
function itemByText(text: string): HTMLElement {
  const item = [...panel()!.querySelectorAll<HTMLElement>("[data-slot='item']")].find((el) =>
    el.textContent?.includes(text),
  );
  expect(item, `item ${text}`).toBeDefined();
  return item!;
}

describe("OperatorFilterPanel", () => {
  it("o botão diz quantos recortes; o painel segue a ordem do dono", async () => {
    const { Host } = host({ status: ["done"] });
    mounted = await mountSuspended(Host, { attachTo: document.body });
    await settle();
    expect(openButton().getAttribute("aria-label")).toBe("Filtros: 1 recorte ativo");
    expect(document.querySelector("[data-operator-filter-panel-count]")?.textContent).toBe("1");
    expect(document.querySelector("[data-operator-filter-chip]")?.textContent).toContain("Situação: Concluído");

    openButton().click();
    await settle();
    const labels = [...panel()!.querySelectorAll("[data-slot='group'] > [data-slot='label']")].map((el) =>
      el.textContent?.trim(),
    );
    expect(labels).toEqual(["Favoritos", "Filtros rápidos", "Data", "Agrupar por", "Filtros completos"]);
    // O favorito fixado mora nos filtros rápidos, não se repete em Favoritos.
    expect(panel()!.querySelectorAll("[data-operator-filter-favorite]")).toHaveLength(0);
  });

  it("filtro rápido, data e favorito mudam o recorte da tela", async () => {
    const { Host, filters, period } = host();
    mounted = await mountSuspended(Host, { attachTo: document.body });
    await settle();
    openButton().click();
    await settle();

    itemByText("Cancelados").click();
    await settle();
    expect(filters.value).toEqual({ status: ["cancelled"] });

    itemByText("Últimos 7 dias").click();
    await settle();
    expect(period.value.preset).toBe("7d");

    // O favorito devolve o recorte inteiro que ele guardou.
    filters.value = {};
    period.value = DAY;
    await settle();
    itemByText("Cancelados da semana").click();
    await settle();
    expect(filters.value).toEqual({ status: ["cancelled"] });
    expect(period.value).toEqual({ preset: "7d", from: "", to: "" });
  });

  it("salvar como favorito manda o recorte com o nome e o fixado", async () => {
    posted.length = 0;
    const { Host } = host({ status: ["done"] });
    mounted = await mountSuspended(Host, { attachTo: document.body });
    await settle();
    openButton().click();
    await settle();
    document.querySelector<HTMLElement>("[data-operator-filter-panel-save]")!.click();
    await settle();
    const input = document.querySelector<HTMLInputElement>("[data-operator-filter-save-name] input, input[data-operator-filter-save-name]")!;
    input.value = "Concluídos de hoje";
    input.dispatchEvent(new Event("input"));
    await settle();
    const confirm = document.querySelector<HTMLButtonElement>("[data-operator-filter-save-confirm]")!;
    expect(confirm.disabled).toBe(false);
    confirm.click();
    await vi.waitFor(() => expect(posted).toHaveLength(1), { timeout: 3000 });
    expect(posted).toEqual([
      {
        surface: "orders",
        screen: "history",
        name: "Concluídos de hoje",
        query: { filters: { status: ["done"] }, period: DAY },
        pinned: false,
      },
    ]);
  });
});
