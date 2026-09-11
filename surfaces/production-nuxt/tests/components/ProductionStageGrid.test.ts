import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, reactive, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import ProductionStageGrid from "../../app/components/ProductionStageGrid.vue";
import type {
  ProductionMatrixRowProjection,
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
// (resolvidos pelo alias). O finish saiu do grid: fechar a fornada é a Expedição
// (quiosque de QC), que mira UMA WorkOrder por cartão — o bug do rendimento de 200%
// (pré-preencher o agregado contra a WO[0]) morreu por construção.

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
    advanceStep: vi.fn().mockResolvedValue({ ok: true }),
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
  ProductionHeader: true,
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
  UiButton: UiButtonStub,
  UiNativeSelect: UiNativeSelectStub,
  UiTextarea: UiTextareaStub,
};

function mountGrid(stage: "plan" | "produce" = "produce") {
  return mount(ProductionStageGrid, {
    props: { stage, title: "Produção" },
    global: { stubs },
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

const suggestion = {
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
  explanation_parts: [],
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

    mountGrid("produce");

    expect(boardInitialDateSpy).toHaveBeenCalledWith("2026-07-05");
  });

  it("lets a suggestion-only persona submit only the exact suggestion", async () => {
    stubBoardAccess({
      ...FULL_ACCESS,
      can_manage_all: false,
      can_edit_planned: false,
      can_edit_suggested: true,
    });
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    await byText(w, "button", "Confirmar")!.trigger("click");
    const input = w.find('input[aria-label="Quantidade planejada"]');
    expect(input.attributes("readonly")).toBeDefined();
    expect((input.element as HTMLInputElement).value).toBe("8");
    await w
      .findAll("button")
      .filter((button) => button.text().trim() === "Confirmar")
      .at(-1)!
      .trigger("click");

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

    await byText(w, "button", "Confirmar")!.trigger("click");
    await w
      .findAll("button")
      .filter((button) => button.text().trim() === "Confirmar")
      .at(-1)!
      .trigger("click");

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

    await byText(w, "button", "Confirmar")!.trigger("click");
    const submit = w
      .findAll("button")
      .filter((button) => button.text().trim() === "Confirmar")
      .at(-1)!;

    await submit.trigger("click");

    expect(submit.text()).toBe("Confirmando…");
    expect(submit.attributes("disabled")).toBeDefined();
    await submit.trigger("click");
    expect(planSpy).toHaveBeenCalledTimes(1);

    request.resolve({ ok: true });
    await request.promise;
  });

  it("confirms the planned quantity with Enter from its numeric field", async () => {
    boardRows.value = [row({ suggestion })];
    const w = mountGrid("plan");

    await byText(w, "button", "Confirmar")!.trigger("click");
    const input = w.find('input[aria-label="Quantidade planejada"]');
    await input.setValue("12");
    await input.trigger("keydown", { key: "Enter" });

    expect(planSpy).toHaveBeenCalledTimes(1);
    expect(planSpy).toHaveBeenCalledWith(
      "PAO-001",
      expect.objectContaining({ quantity: "12" }),
    );
  });
});

describe("ProductionStageGrid — produce render", () => {
  it("mostra Planejado → Produzido com uma ação Confirmar", () => {
    boardRows.value = [
      row({ planned_qty: "30", planned_orders: [wo({ status: "planned" })] }),
    ];
    const w = mountGrid();
    expect(w.text()).toContain("PAO-001");
    expect(w.text()).toContain("Planejado");
    expect(w.text()).toContain("Produzido");
    expect(byText(w, "button", "Confirmar")).toBeTruthy();
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
    const lines = w.findAll("tbody td")[0]!.findAll("p");
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
    const lines = w.findAll("tbody td")[0]!.findAll("p");
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

    await byText(w, "button", "Confirmar")!.trigger("click");
    expect(w.text()).toContain("Selecione a fornada exata");
    expect(startSpy).not.toHaveBeenCalled();

    await byText(w, "button", "WO-008")!.trigger("click");
    await w
      .findAll("button")
      .filter((button) => button.text().trim() === "Confirmar")
      .at(-1)!
      .trigger("click");

    expect(startSpy).toHaveBeenCalledWith("PAO-001", 8, 4, "30");
  });

  it("confirms produced quantity on the first click and blocks repeats while pending", async () => {
    const request = pendingResult<{ ok: true }>();
    startSpy.mockImplementationOnce(() => request.promise);
    boardRows.value = [
      row({
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountGrid();

    await byText(w, "button", "Confirmar")!.trigger("click");
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

  it("confirms the produced quantity with Enter from its numeric field", async () => {
    boardRows.value = [
      row({
        planned_qty: "30",
        planned_orders: [wo({ status: "planned" })],
      }),
    ];
    const w = mountGrid();

    await byText(w, "button", "Confirmar")!.trigger("click");
    const input = w.find('input[aria-label="Quantidade produzida"]');
    await input.setValue("27");
    await input.trigger("keydown", { key: "Enter" });

    expect(startSpy).toHaveBeenCalledTimes(1);
    expect(startSpy).toHaveBeenCalledWith("PAO-001", 1, 2, "27");
  });
});

describe("ProductionStageGrid — lote em processo (gestão)", () => {
  it("opens the management dialog for a started row and voids with a reason", async () => {
    boardRows.value = [
      row({
        started_qty: "30",
        started_orders: [wo({ pk: 7, ref: "WO-007", started_qty: "30" })],
      }),
    ];
    const w = mountGrid();

    // Com lote em processo a célula de ação mostra a quantidade (30), não o verbo.
    await byText(w, "button", "30")!.trigger("click");
    expect(w.text()).toContain("em processo");

    await byText(w, "button", "Estornar…")!.trigger("click");
    await w
      .find('textarea[aria-label="Motivo do estorno"]')
      .setValue("queimou");
    await byText(w, "button", "Confirmar estorno")!.trigger("click");
    expect(voidSpy).toHaveBeenCalledWith(7, 2, "queimou");
  });
});
