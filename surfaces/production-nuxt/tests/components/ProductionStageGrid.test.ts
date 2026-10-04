import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, reactive, ref, watch } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

import PlanReasonCard from "../../app/components/PlanReasonCard.vue";
import ProductionStageGrid from "../../app/components/ProductionStageGrid.vue";
import ShortageDialog from "../../app/components/ShortageDialog.vue";
import type {
  ProductionMatrixRowProjection,
  ProductionSuggestionProjection,
  WorkOrderCardProjection,
} from "../../app/types/production";
import {
  UiButtonStub,
  UiNativeSelectStub,
  UiTextareaStub,
} from "../support/nativeUiStubs";

// ProductionStageGrid é dirigido por composables (useProductionBoard/useProductionKds).
// Sem runtime Nuxt: reatividade Vue real como globais + os composables stubados com refs
// que controlamos. Os helpers de presentation (~/presentation) rodam de VERDADE
// (resolvidos pelo alias). O finish saiu do grid: fechar o lote é o Fechamento
// (quiosque de QC), que mira UMA WorkOrder por cartão: o bug do aproveitamento de
// 200% (pré-preencher o agregado contra a WO[0]) morreu por construção. Na Abertura a
// ação é uma só — Confirmar, o mesmo verbo do Planejamento (16/09/2026); a
// diferença para o planejado é
// rendimento e não pede motivo; o modal de etapas ("Avançar para Fermentação")
// não existe mais.

// ── Fixtures ────────────────────────────────────────────────────────────────
function wo(
  over: Partial<WorkOrderCardProjection> = {},
): WorkOrderCardProjection {
  return {
    pk: 1,
    ref: "WO-001",
    recipe_pk: 5,
    recipe_ref: "REC-5",
    recipe_name: "Pão",
    base_usages: [],
    output_sku: "PAO-001",
    rev: 2,
    status: "started",
    status_label: "Em processo",
    tone: "info",
    planned_qty: "30",
    started_qty: "30",
    finished_qty: "0",
    yield_rate: "",
    loss: "",
    operator_ref: "",
    position_ref: "",
    target_date_display: "",
    started_at_display: "",
    created_at_display: "",
    progress_pct: 0,
    committed_qty: "0",
    ...over,
  } as WorkOrderCardProjection;
}

function row(
  over: Partial<ProductionMatrixRowProjection> = {},
): ProductionMatrixRowProjection {
  return {
    recipe_pk: 5,
    output_sku: "PAO-001",
    recipe_name: "Pão",
    base_usages: [],
    suggestion: null,
    planned_orders: [],
    started_orders: [],
    finished_orders: [],
    planned_qty: "0",
    started_qty: "0",
    finished_qty: "0",
    loss_qty: "0",
    ...over,
  };
}

const FULL_ACCESS = {
  can_manage_all: true,
  can_view_suggested: true,
  can_edit_suggested: true,
  can_view_planned: true,
  can_edit_planned: true,
  can_view_started: true,
  can_edit_started: true,
  can_view_finished: true,
  can_edit_finished: true,
};

// ── Composable stubs (refs controláveis por teste) ──────────────────────────
const boardRows = ref<ProductionMatrixRowProjection[]>([]);
const voidSpy = vi.fn().mockResolvedValue({ ok: true });
const startSpy = vi.fn().mockResolvedValue({ ok: true });
const planSpy = vi.fn().mockResolvedValue({ ok: true });
const boardRefresh = vi.fn();
const boardInitialDateSpy = vi.fn();

function installGlobals() {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("reactive", reactive);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("useSonner", { success: vi.fn(), error: vi.fn() });
  vi.stubGlobal("useOperatorAppLink", () => ({
    attrsFor: () => ({ target: "_self" }),
  }));
  vi.stubGlobal("useRoute", () => ({ query: {} }));
  vi.stubGlobal("useProductionBoard", (initialDate: string) => {
    boardInitialDateSpy(initialDate);
    return {
      board: ref({
        access: FULL_ACCESS,
        base_recipes: [],
        selected_date: "2026-07-06",
        selected_position_ref: "",
        default_position_pk: 7,
        positions: [{ pk: 7, ref: "forno", name: "Forno", is_default: true }],
      }),
      rows: boardRows,
      counts: ref(null),
      selectedDate: ref("2026-07-06"),
      pending: ref(false),
      error: ref(null),
      refresh: boardRefresh,
      isBusy: () => false,
      plan: planSpy,
      start: startSpy,
    };
  });
  vi.stubGlobal("useProductionKds", () => ({
    cards: ref([]),
    totalCount: ref(0),
    lateCount: ref(0),
    pending: ref(false),
    error: ref(null),
    refresh: vi.fn(),
    isBusy: () => false,
    voidOrder: voidSpy,
  }));
  vi.stubGlobal("useOvenTimers", () => ({
    arm: vi.fn(),
    clear: vi.fn(),
    get: () => null,
    isRinging: () => false,
    remainingLabel: () => "",
  }));
}

const passthrough = { template: "<div><slot /></div>" };
const stubs = {
  // O cabeçalho é dele mesmo (testado à parte); aqui ele só repassa os recortes
  // e os controles que a grade põe nele.
  ProductionHeader: {
    template: '<div><slot name="actions" /><slot name="filters" /></div>',
  },
  OperatorPeriodPicker: true,
  UiFilterChip: {
    props: ["active", "count"],
    template:
      '<button type="button" :data-active="active || undefined"><slot name="icon" /><slot /> {{ count }}</button>',
  },
  UiPopoverTrigger: passthrough,
  ShortageDialog: true,
  AlertsBell: true,
  Icon: true,
  NuxtLink: { template: "<a><slot /></a>" },
  // UiDialog renderiza o conteúdo inline quando aberto (sem teleport) → fácil de consultar.
  UiDialog: { props: ["open"], template: "<div v-if='open'><slot /></div>" },
  UiDialogContent: passthrough,
  UiDialogHeader: passthrough,
  UiDialogTitle: passthrough,
  UiDialogDescription: passthrough,
  UiDialogFooter: passthrough,
  UiBadge: passthrough,
  // O popover do "Por quê": o conteúdo só existe com a linha aberta (o v-if é
  // da grade), então o stub só precisa repassar o slot.
  UiPopover: { props: ["open"], template: "<div><slot /></div>" },
  UiPopoverAnchor: passthrough,
  UiPopoverContent: passthrough,
  OperatorKbd: { template: "<kbd><slot /></kbd>" },
  UiButton: UiButtonStub,
  UiNativeSelect: UiNativeSelectStub,
  UiTextarea: UiTextareaStub,
};

function mountGrid(stage: "plan" | "open" = "open") {
  return mount(ProductionStageGrid, {
    props: { stage, title: "Abertura" },
    global: { stubs, components: { PlanReasonCard } },
  });
}

function stubBoardAccess(access: Record<string, boolean>) {
  vi.stubGlobal("useProductionBoard", () => ({
    board: ref({
      access,
      base_recipes: [],
      selected_date: "2026-07-06",
      selected_position_ref: "",
      default_position_pk: 7,
      positions: [{ pk: 7, ref: "forno", name: "Forno", is_default: true }],
    }),
    rows: boardRows,
    counts: ref(null),
    selectedDate: ref("2026-07-06"),
    pending: ref(false),
    error: ref(null),
    refresh: boardRefresh,
    isBusy: () => false,
    plan: planSpy,
    start: startSpy,
  }));
}

const suggestion: ProductionSuggestionProjection = {
  recipe_pk: 5,
  recipe_ref: "REC-5",
  recipe_name: "Pão",
  base_usages: [],
  output_sku: "PAO-001",
  quantity: "8",
  committed: "0",
  avg_demand: "8",
  confidence: "Alta",
  sample_size: 7,
  high_demand_applied: false,
  projected: "7",
  margin: "1",
  safety_percent: 10,
  same_weekday: true,
  season_label: "",
  soldout_days: 0,
  waste_percent: 0,
  waste_discounted: false,
  material_shortages: [],
  fits_quantity: "",
};

const byText = (w: ReturnType<typeof mountGrid>, sel: string, txt: string) =>
  w.findAll(sel).find((el) => el.text().includes(txt));

function pendingResult<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  installGlobals();
  boardRows.value = [];
  voidSpy.mockClear().mockResolvedValue({ ok: true });
  startSpy.mockClear().mockResolvedValue({ ok: true });
  planSpy.mockClear().mockResolvedValue({ ok: true });
  boardRefresh.mockClear();
  boardInitialDateSpy.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe("ProductionStageGrid — planning authority", () => {
  it("opens the exact production date carried by an alert deep link", () => {
    vi.stubGlobal("useRoute", () => ({
      query: { date: "2026-07-05", q: "WO-001" },
    }));

    mountGrid("open");

    expect(boardInitialDateSpy).toHaveBeenCalledWith("2026-07-05");
  });

  // V4 (prévia `plano-porque4.html`): a linha decide. O stepper e "Planejar N" moram
  // na linha; a mesma autoridade de antes vale lá (a persona que só segue a sugestão
  // planeja o número exato, com origem "suggested"; quem planeja à mão, "manual").
  it("lets a suggestion-only persona submit only the exact suggestion", async () => {
    stubBoardAccess({
      ...FULL_ACCESS,
      can_manage_all: false,
      can_edit_planned: false,
      can_edit_suggested: true,
    });
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    const input = w.find('input[aria-label="Quantidade de Pão"]');
    expect(input.attributes("readonly")).toBeDefined();
    expect((input.element as HTMLInputElement).value).toBe("8");
    expect(
      w.find('button[aria-label="Aumentar Pão"]').attributes("disabled"),
    ).toBeDefined();
    await w.find("[data-plan-inline]").trigger("click");

    expect(planSpy).toHaveBeenCalledWith(
      "PAO-001",
      expect.objectContaining({
        quantity: "8",
        position_ref: "forno",
        source: "suggested",
      }),
    );
  });

  it("keeps an equal numeric value manual for a planned-only persona", async () => {
    stubBoardAccess({
      ...FULL_ACCESS,
      can_manage_all: false,
      can_edit_planned: true,
      can_edit_suggested: false,
    });
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    expect(w.find("[data-plan-inline]").text()).toBe("Planejar 8");
    await w.find("[data-plan-inline]").trigger("click");

    expect(planSpy).toHaveBeenCalledWith(
      "PAO-001",
      expect.objectContaining({
        quantity: "8",
        position_ref: "forno",
        source: "manual",
      }),
    );
    expect(w.text()).not.toContain("Planejar esta sugestão");
  });

  it("confirms planning on the first click and blocks repeats while pending", async () => {
    const request = pendingResult<{ ok: true }>();
    planSpy.mockImplementationOnce(() => request.promise);
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    const submit = w.find("[data-plan-inline]");
    await submit.trigger("click");

    expect(submit.text()).toBe("Planejando…");
    expect(submit.attributes("disabled")).toBeDefined();
    await submit.trigger("click");
    expect(planSpy).toHaveBeenCalledTimes(1);

    request.resolve({ ok: true });
    await request.promise;
  });

  it("confirms the planned quantity with Enter from its numeric field", async () => {
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    const input = w.find('input[aria-label="Quantidade de Pão"]');
    await input.setValue("12");
    expect(w.find("[data-plan-inline]").text()).toBe("Planejar 12");
    await input.trigger("keydown", { key: "Enter" });

    expect(planSpy).toHaveBeenCalledTimes(1);
    expect(planSpy).toHaveBeenCalledWith(
      "PAO-001",
      expect.objectContaining({ quantity: "12", source: "manual" }),
    );
  });

  it("mudou o número: a sugestão diz de onde veio, e voltar desfaz", async () => {
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    await w.find('button[aria-label="Aumentar Pão"]').trigger("click");
    await w.find('button[aria-label="Aumentar Pão"]').trigger("click");
    expect(w.find("[data-plan-changed]").text()).toContain("você mudou de 8");
    expect(w.find("[data-plan-inline]").text()).toBe("Planejar 10");

    await byText(w, "[data-plan-changed] button", "voltar")!.trigger("click");
    expect(w.find("[data-plan-changed]").exists()).toBe(false);
    expect(w.find("[data-plan-inline]").text()).toBe("Planejar 8");
  });

  it("zero não planeja: a linha não tem o que mandar", () => {
    boardRows.value = [row({ suggestion: { ...suggestion, quantity: "0" } })];
    const w = mountGrid("plan");

    expect(w.find("[data-plan-inline]").attributes("disabled")).toBeDefined();
  });

  it("o planejado vira estado, e corrigir abre o ajuste do lote pelo menu", async () => {
    boardRows.value = [
      row({
        suggestion,
        planned_qty: "20",
        planned_orders: [
          wo({
            pk: 9,
            ref: "WO-009",
            rev: 4,
            status: "planned",
            planned_qty: "20",
          }),
        ],
      }),
    ];
    const w = mountGrid("plan");

    expect(w.find("[data-plan-row]").exists()).toBe(false);
    const planned = w.find("[data-planned-line]");
    expect(planned.text()).toContain("Planejado");
    expect(w.find("[data-planned-row]").text()).toContain("Pão 20");

    await w.find("[data-planned-correct]").trigger("click");
    const input = w.find('input[aria-label="Quantidade planejada"]');
    expect((input.element as HTMLInputElement).value).toBe("20");
    await input.setValue("24");
    await input.trigger("keydown", { key: "Enter" });

    expect(planSpy).toHaveBeenCalledWith(
      "PAO-001",
      expect.objectContaining({
        quantity: "24",
        work_order_id: 9,
        expected_rev: 4,
        source: "manual",
      }),
    );
  });

  it("com a produção já assumida, o menu soma um lote novo, nunca em silêncio", async () => {
    boardRows.value = [
      row({
        suggestion,
        started_qty: "30",
        started_orders: [wo({ pk: 7, started_qty: "30" })],
      }),
    ];
    const w = mountGrid("plan");

    expect(w.find("[data-planned-row]").text()).toContain("(aberto)");
    expect(w.find("[data-planned-correct]").text()).toBe("Planejar novo lote");
    await w.find("[data-planned-correct]").trigger("click");
    expect(w.text()).toContain("Soma ao dia");
    const input = w.find('input[aria-label="Quantidade planejada"]');
    expect((input.element as HTMLInputElement).value).toBe("0");
  });
});

describe("ProductionStageGrid — Planejamento: conjunto sem ressalva e recortes", () => {
  function cleanRow(sku: string, name: string, quantity: string) {
    return row({
      recipe_pk: sku.length,
      output_sku: sku,
      recipe_name: name,
      suggestion: { ...suggestion, output_sku: sku, quantity },
    });
  }
  const flagged = row({
    output_sku: "CRO",
    recipe_name: "Croissant",
    suggestion: { ...suggestion, output_sku: "CRO", soldout_days: 7 },
  });
  const cleanRows = [
    cleanRow("PC", "Pain de Campagne", "34"),
    cleanRow("KP", "Kuro Pan", "12"),
    cleanRow("BG", "Baguete", "30"),
    cleanRow("FO", "Focaccia", "10"),
    cleanRow("SH", "Shokupan", "18"),
  ];
  const skus = (w: ReturnType<typeof mountGrid>, sel: string) =>
    w.findAll(sel).map((el) => el.attributes("data-sku"));

  it("o que não tem ressalva vira conjunto; o resto fica na linha", () => {
    boardRows.value = [flagged, ...cleanRows];
    const w = mountGrid("plan");

    expect(skus(w, "[data-plan-row]")).toEqual(["CRO"]);
    const set = w.find("[data-plan-clean]");
    expect(set.text()).toContain("+5 produtos sem ressalva");
    expect(set.text()).toContain(
      "Pain de Campagne 34, Kuro Pan 12, Baguete 30, Focaccia 10 e mais 1",
    );
    expect(w.find("[data-plan-clean-all]").text()).toBe(
      "Planejar os 5 como sugerido",
    );
  });

  it("Ver um a um abre o conjunto em linhas", async () => {
    boardRows.value = [flagged, ...cleanRows];
    const w = mountGrid("plan");

    await w.find("[data-plan-clean-expand]").trigger("click");
    expect(w.find("[data-plan-clean]").exists()).toBe(false);
    expect(w.findAll("[data-plan-row]")).toHaveLength(6);
  });

  it("um sim para o conjunto planeja cada um como sugerido, um a um", async () => {
    boardRows.value = [flagged, ...cleanRows];
    const w = mountGrid("plan");

    await w.find("[data-plan-clean-all]").trigger("click");
    await flushPromises();

    expect(planSpy).toHaveBeenCalledTimes(5);
    expect(
      planSpy.mock.calls.map(([sku, payload]) => [sku, payload.quantity]),
    ).toEqual([
      ["PC", "34"],
      ["KP", "12"],
      ["BG", "30"],
      ["FO", "10"],
      ["SH", "18"],
    ]);
  });

  it("o conjunto para na primeira recusa, e a recusa aparece", async () => {
    const refusal = { code: "material_shortage" };
    planSpy
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({ ok: false, shortage: refusal });
    boardRows.value = [flagged, ...cleanRows];
    const w = mount(ProductionStageGrid, {
      props: { stage: "plan", title: "Planejamento" },
      global: {
        stubs: {
          ...stubs,
          ShortageDialog: {
            props: ["shortage"],
            template: '<div v-if="shortage" data-shortage>{{ shortage.code }}</div>',
          },
        },
        components: { PlanReasonCard },
      },
    });

    await w.find("[data-plan-clean-all]").trigger("click");
    await flushPromises();

    expect(planSpy).toHaveBeenCalledTimes(2);
    expect(w.find("[data-shortage]").text()).toBe(refusal.code);
  });

  it("sem sugestão para o dia vira conjunto que se abre para planejar à mão", async () => {
    const manual = ["MOLHO", "RECHEIO", "CREME", "BASE"].map((sku) =>
      row({ recipe_pk: 9, output_sku: sku, recipe_name: sku }),
    );
    boardRows.value = [flagged, ...manual];
    const w = mountGrid("plan");

    expect(skus(w, "[data-plan-row]")).toEqual(["CRO"]);
    expect(w.find("[data-plan-manual]").text()).toContain(
      "+4 produtos sem sugestão para o dia",
    );
    await w.find("[data-plan-manual-expand]").trigger("click");
    expect(w.find("[data-plan-manual]").exists()).toBe(false);
    expect(skus(w, "[data-plan-row]")).toEqual(["CRO", "MOLHO", "RECHEIO", "CREME", "BASE"]);
  });

  it("os recortes contam e filtram: A planejar, Com ressalva, Planejados", async () => {
    const planned = row({
      output_sku: "BRI",
      recipe_name: "Brioche",
      planned_qty: "20",
      planned_orders: [wo({ status: "planned", planned_qty: "20" })],
    });
    boardRows.value = [flagged, ...cleanRows, planned];
    const w = mountGrid("plan");

    const chip = (key: string) => w.find(`[data-plan-filter="${key}"]`);
    expect(chip("all").text()).toContain("7");
    expect(chip("todo").text()).toContain("6");
    expect(chip("flagged").text()).toContain("1");
    expect(chip("done").text()).toContain("1");

    await chip("flagged").trigger("click");
    expect(skus(w, "[data-plan-row]")).toEqual(["CRO"]);
    expect(w.find("[data-planned-row]").exists()).toBe(false);

    await chip("done").trigger("click");
    expect(w.find("[data-plan-row]").exists()).toBe(false);
    expect(skus(w, "[data-planned-row]")).toEqual(["BRI"]);
  });
});

describe("ProductionStageGrid — Abertura", () => {
  it("mostra Planejado → Previsto com uma ação só: Confirmar", () => {
    boardRows.value = [
      row({ planned_qty: "30", planned_orders: [wo({ status: "planned" })] }),
    ];
    const w = mountGrid();
    expect(w.text()).toContain("PAO-001");
    expect(w.text()).toContain("Planejado");
    expect(w.text()).toContain("Previsto");
    // "Produzido" não rotula started nem finished (parecer do dono, 03/10/2026).
    expect(w.text()).not.toContain("Produzido");
    // O número mora na coluna Planejado, como no Planejamento — o botão é só o verbo.
    const cell = w.find('button[aria-label="Confirmar Pão"]');
    expect(cell.text().trim()).toBe("Confirmar");
    expect(w.text()).not.toContain("em processo");
  });

  it("nomeia a linha pelo produto e deixa o SKU na segunda linha", () => {
    boardRows.value = [
      row({
        recipe_name: "Pão de fermentação natural",
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountGrid();
    const lines = w.find("[data-row-product]").findAll("p");
    expect(lines[0]!.text()).toBe("Pão de fermentação natural");
    expect(lines[1]!.text()).toContain("PAO-001");
  });

  it("cai no SKU quando a ficha não tem nome — a linha não some", () => {
    boardRows.value = [
      row({
        recipe_name: "",
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountGrid();
    const lines = w.find("[data-row-product]").findAll("p");
    expect(lines[0]!.text()).toBe("PAO-001");
  });

  it("shows the welcoming empty state when nothing is planned", () => {
    boardRows.value = [];
    const w = mountGrid();
    expect(w.text()).toContain("Nada planejado para produzir");
  });

  it("requires an explicit planned work order when starting one of many", async () => {
    boardRows.value = [
      row({
        planned_qty: "50",
        planned_orders: [
          wo({
            pk: 7,
            ref: "WO-007",
            rev: 3,
            status: "planned",
            planned_qty: "20",
          }),
          wo({
            pk: 8,
            ref: "WO-008",
            rev: 4,
            status: "planned",
            planned_qty: "30",
          }),
        ],
      }),
    ];
    const w = mountGrid();

    await w.find('button[aria-label="Confirmar Pão"]').trigger("click");
    expect(w.text()).toContain("Selecione o lote");
    expect(startSpy).not.toHaveBeenCalled();

    await byText(w, "button", "WO-008")!.trigger("click");
    await w
      .findAll("button")
      .filter((button) => button.text().trim() === "Confirmar")
      .at(-1)!
      .trigger("click");

    expect(startSpy).toHaveBeenCalledWith("PAO-001", 8, 4, "30");
  });

  it("confirms the expected quantity on the first click and blocks repeats while pending", async () => {
    const request = pendingResult<{ ok: true }>();
    startSpy.mockImplementationOnce(() => request.promise);
    boardRows.value = [
      row({
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountGrid();

    await w.find('button[aria-label="Confirmar Pão"]').trigger("click");
    const submit = w
      .findAll("button")
      .filter((button) => button.text().trim() === "Confirmar")
      .at(-1)!;

    await submit.trigger("click");

    expect(submit.text()).toBe("Confirmando…");
    expect(submit.attributes("disabled")).toBeDefined();
    await submit.trigger("click");
    expect(startSpy).toHaveBeenCalledTimes(1);

    request.resolve({ ok: true });
    await request.promise;
  });

  it("confirms the planned quantity with Enter", async () => {
    boardRows.value = [
      row({
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountGrid();

    await w.find('button[aria-label="Confirmar Pão"]').trigger("click");
    const input = w.find('input[aria-label="Quantidade prevista"]');
    expect((input.element as HTMLInputElement).value).toBe("30");
    await input.trigger("keydown", { key: "Enter" });

    expect(startSpy).toHaveBeenCalledTimes(1);
    expect(startSpy).toHaveBeenCalledWith("PAO-001", 1, 2, "30");
  });

  it("a diferença para o planejado é rendimento: avisa, não pergunta, e segue", async () => {
    boardRows.value = [
      row({
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountGrid();

    await w.find('button[aria-label="Confirmar Pão"]').trigger("click");
    const input = w.find('input[aria-label="Quantidade prevista"]');
    await input.setValue("27");
    expect(w.text()).toContain("Diferente do planejado (30)");
    expect(w.find("textarea").exists()).toBe(false);
    const submit = w
      .findAll("button")
      .filter((button) => button.text().trim() === "Confirmar")
      .at(-1)!;
    expect(submit.attributes("disabled")).toBeUndefined();
    await input.trigger("keydown", { key: "Enter" });

    expect(startSpy).toHaveBeenCalledWith("PAO-001", 1, 2, "27");
  });

  it("zero não segue: não há o que confirmar", async () => {
    boardRows.value = [
      row({
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountGrid();

    await w.find('button[aria-label="Confirmar Pão"]').trigger("click");
    const input = w.find('input[aria-label="Quantidade prevista"]');
    await input.setValue("0");
    await input.trigger("keydown", { key: "Enter" });

    expect(startSpy).not.toHaveBeenCalled();
  });

  it("nunca oferece avanço de etapa nem gestão de lote", () => {
    boardRows.value = [
      row({
        started_qty: "30",
        started_orders: [wo({ pk: 7, ref: "WO-007", started_qty: "30" })],
      }),
    ];
    const w = mountGrid();
    expect(w.text()).not.toContain("Avançar");
    expect(w.text()).not.toContain("em processo");
  });

  it("com um lote aberto e outro planejado, mostra o número e Confirmar", () => {
    boardRows.value = [
      row({
        planned_qty: "20",
        started_qty: "30",
        planned_orders: [wo({ pk: 9, status: "planned", planned_qty: "20" })],
        started_orders: [wo({ pk: 7, ref: "WO-007", started_qty: "30" })],
      }),
    ];
    const w = mountGrid();
    expect(byText(w, "button", "30")).toBeTruthy();
    expect(w.find('button[aria-label="Confirmar Pão"]').text().trim()).toBe(
      "Confirmar",
    );
  });
});

describe("ProductionStageGrid — lote aberto (conferência e cancelamento)", () => {
  it("abre o lote aberto pelo número e cancela com motivo", async () => {
    boardRows.value = [
      row({
        started_qty: "30",
        started_orders: [wo({ pk: 7, ref: "WO-007", started_qty: "30" })],
      }),
    ];
    const w = mountGrid();

    // Sem planejado restante a célula mostra só o previsto (30), que abre a conferência.
    await byText(w, "button", "30")!.trigger("click");
    expect(w.text()).toContain("previstas seguem para o");
    expect(w.text()).toContain("Fechamento");
    expect(w.text()).not.toContain("Avançar");

    await byText(w, "button", "Cancelar lote…")!.trigger("click");
    await w
      .find('textarea[aria-label="Motivo do cancelamento"]')
      .setValue("queimou");
    await byText(w, "button", "Confirmar cancelamento")!.trigger("click");
    expect(voidSpy).toHaveBeenCalledWith(7, 2, "queimou");
  });
});

describe("ProductionStageGrid — Planejamento: o número na linha, o porquê por cima", () => {
  const butter = {
    sku: "MANTEIGA",
    name: "Manteiga",
    missing_display: "1200 g",
    fits_quantity: "5",
  };

  it("linha sem nada a notar mostra só o número e o Por quê, sem sinal nem conta", () => {
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    expect(w.find('[data-testid="suggestion-signal"]').exists()).toBe(false);
    const trigger = w.find("[data-plan-reason-trigger]");
    expect(trigger.text()).toContain("Por quê");
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(w.find('[data-testid="plan-reason"]').exists()).toBe(false);
    expect(w.text()).not.toContain("margem");
  });

  it("mostra um sinal só, o de maior prioridade", () => {
    boardRows.value = [
      row({
        suggestion: {
          ...suggestion,
          material_shortages: [butter],
          fits_quantity: "5",
          soldout_days: 7,
          waste_percent: 20,
          waste_discounted: true,
        },
      }),
    ];
    const w = mountGrid("plan");

    const signals = w.findAll('[data-testid="suggestion-signal"]');
    expect(signals).toHaveLength(1);
    expect(signals[0]!.text()).toBe("falta insumo");
  });

  it("acabou cedo e sobra aparecem quando são o único fato da linha", () => {
    boardRows.value = [
      row({ suggestion: { ...suggestion, soldout_days: 4 } }),
      row({
        output_sku: "BRIOCHE",
        recipe_name: "Brioche",
        suggestion: {
          ...suggestion,
          output_sku: "BRIOCHE",
          waste_percent: 20,
          waste_discounted: true,
        },
      }),
    ];
    const w = mountGrid("plan");

    expect(
      w.findAll('[data-testid="suggestion-signal"]').map((el) => el.text()),
    ).toEqual(["acabou cedo", "sobra"]);
  });

  it("o Por quê abre a conta ancorada na linha, marca a linha e fecha pelo mesmo gesto", async () => {
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");
    const trigger = w.find("[data-plan-reason-trigger]");

    await trigger.trigger("click");
    expect(trigger.attributes("aria-expanded")).toBe("true");
    expect(w.find("[data-plan-row]").classes()).toContain("bg-primary/5");
    expect(w.find('[data-testid="reason-math"]').text()).toContain("margem");

    await trigger.trigger("click");
    expect(w.find('[data-testid="plan-reason"]').exists()).toBe(false);
  });

  it("Fechar no detalhe fecha o detalhe", async () => {
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    await w.find("[data-plan-reason-trigger]").trigger("click");
    await w
      .findAll('[data-testid="plan-reason"] button')
      .find((button) => button.text().trim() === "Fechar")!
      .trigger("click");

    expect(w.find('[data-testid="plan-reason"]').exists()).toBe(false);
  });

  it("Planejar N no detalhe abre o planejamento com a sugestão", async () => {
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    await w.find("[data-plan-reason-trigger]").trigger("click");
    await byText(w, '[data-testid="plan-reason"] button', "Planejar 8")!.trigger(
      "click",
    );

    expect(w.find('[data-testid="plan-reason"]').exists()).toBe(false);
    const input = w.find('input[aria-label="Quantidade planejada"]');
    expect((input.element as HTMLInputElement).value).toBe("8");
    expect(input.attributes("readonly")).toBeDefined();
  });

  it("a alternativa que cabe no estoque abre o planejamento com o número dela", async () => {
    boardRows.value = [
      row({
        suggestion: {
          ...suggestion,
          material_shortages: [butter],
          fits_quantity: "5",
        },
      }),
    ];
    const w = mountGrid("plan");

    await w.find("[data-plan-reason-trigger]").trigger("click");
    await byText(
      w,
      '[data-testid="plan-reason"] button',
      "Planejar 5 (cabe no estoque)",
    )!.trigger("click");

    const input = w.find('input[aria-label="Quantidade planejada"]');
    expect((input.element as HTMLInputElement).value).toBe("5");
    expect(input.attributes("readonly")).toBeUndefined();
  });
});

describe("ProductionStageGrid — previsto abaixo das encomendas", () => {
  // A recusa `order_shortage` do start não pode deixar o diálogo parado em
  // silêncio: o operador vê quanto está encomendado, o que informou, e volta ao
  // número para corrigir. O servidor não oferece "force" aqui.
  const orderShortage = {
    code: "order_shortage" as const,
    work_order_ref: "WO-001",
    idempotency_key: "k",
    possibilities: [
      {
        kind: "retry",
        label: "Revisar quantidade",
        enabled: true,
        proof: "",
      },
    ],
    required: "12",
    requested: "8",
    order_refs: ["ORD-1", "ORD-2"],
  };

  function mountWithShortageDialog() {
    return mount(ProductionStageGrid, {
      props: { stage: "open", title: "Abertura" },
      global: {
        stubs: { ...stubs, ShortageDialog: false },
        components: { ShortageDialog },
      },
    });
  }

  it("mostra a falta e o caminho, e devolve o número digitado para corrigir", async () => {
    startSpy.mockResolvedValueOnce({ ok: false, shortage: orderShortage });
    boardRows.value = [
      row({
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountWithShortageDialog();

    await w.find('button[aria-label="Confirmar Pão"]').trigger("click");
    const input = w.find('input[aria-label="Quantidade prevista"]');
    await input.setValue("8");
    await input.trigger("keydown", { key: "Enter" });
    await flushPromises();

    expect(startSpy).toHaveBeenCalledWith("PAO-001", 1, 2, "8");
    // O diálogo de quantidade fecha; a recusa toma o lugar dele, com números e pedidos.
    expect(w.find('input[aria-label="Quantidade prevista"]').exists()).toBe(
      false,
    );
    expect(w.text()).toContain("Quantidade não cobre pedidos");
    expect(w.text()).toContain("Encomendado: 12 un.");
    expect(w.text()).toContain("informado: 8 un.");
    expect(w.text()).toContain("ORD-1, ORD-2");
    expect(w.text()).toContain("informe pelo menos 12 un.");
    // Nada de forçar: sem campo de motivo, sem botão de autorização.
    expect(w.find("textarea").exists()).toBe(false);
    expect(w.text()).not.toContain("Salvar com justificativa");

    await byText(w, "button", "Revisar quantidade")!.trigger("click");

    expect(w.text()).not.toContain("Quantidade não cobre pedidos");
    const back = w.find('input[aria-label="Quantidade prevista"]');
    expect((back.element as HTMLInputElement).value).toBe("8");
    await back.setValue("12");
    await back.trigger("keydown", { key: "Enter" });
    expect(startSpy).toHaveBeenLastCalledWith("PAO-001", 1, 2, "12");
  });

  it("Cancelar fecha a recusa sem reabrir o diálogo", async () => {
    startSpy.mockResolvedValueOnce({ ok: false, shortage: orderShortage });
    boardRows.value = [
      row({
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountWithShortageDialog();

    await w.find('button[aria-label="Confirmar Pão"]').trigger("click");
    await w
      .find('input[aria-label="Quantidade prevista"]')
      .trigger("keydown", { key: "Enter" });
    await flushPromises();

    await byText(w, "button", "Cancelar")!.trigger("click");

    expect(w.text()).not.toContain("Quantidade não cobre pedidos");
    expect(w.find('input[aria-label="Quantidade prevista"]').exists()).toBe(
      false,
    );
  });
});
