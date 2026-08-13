import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, reactive, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import ProductionStageGrid from "../../app/components/ProductionStageGrid.vue";
import type {
  ProductionMatrixRowProjection,
  WorkOrderCardProjection,
} from "../../app/types/production";

// ProductionStageGrid é dirigido por composables (useProductionBoard/useProductionKds).
// Sem runtime Nuxt: reatividade Vue real como globais + os composables stubados com refs
// que controlamos. Os helpers de presentation (~/presentation) rodam de VERDADE
// (resolvidos pelo alias). O finish saiu do grid: fechar a fornada é a Expedição
// (quiosque de QC), que mira UMA WorkOrder por cartão — o bug do rendimento de 200%
// (pré-preencher o agregado contra a WO[0]) morreu por construção.

// ── Fixtures ────────────────────────────────────────────────────────────────
function wo(over: Partial<WorkOrderCardProjection> = {}): WorkOrderCardProjection {
  return {
    pk: 1,
    ref: "WO-001",
    recipe_pk: 5,
    recipe_ref: "REC-5",
    recipe_name: "Pão",
    base_usages: [],
    output_sku: "PAO-001",
    status: "started",
    status_label: "Em processo",
    status_color: "",
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

function row(over: Partial<ProductionMatrixRowProjection> = {}): ProductionMatrixRowProjection {
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
const boardRefresh = vi.fn();

function installGlobals() {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("reactive", reactive);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("useSonner", { success: vi.fn(), error: vi.fn() });
  vi.stubGlobal("useRoute", () => ({ query: {} }));
  vi.stubGlobal("useProductionBoard", () => ({
    board: ref({
      access: FULL_ACCESS,
      base_recipes: [],
      selected_date: "2026-07-06",
      selected_position_ref: "",
    }),
    rows: boardRows,
    counts: ref(null),
    selectedDate: ref("2026-07-06"),
    pending: ref(false),
    error: ref(null),
    refresh: boardRefresh,
    isBusy: () => false,
    plan: vi.fn().mockResolvedValue({ ok: true }),
    start: vi.fn().mockResolvedValue({ ok: true }),
  }));
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
};

function mountGrid(stage: "plan" | "produce" = "produce") {
  return mount(ProductionStageGrid, {
    props: { stage, title: "Produção" },
    global: { stubs },
  });
}

const byText = (w: ReturnType<typeof mountGrid>, sel: string, txt: string) =>
  w.findAll(sel).find((el) => el.text().includes(txt));

beforeEach(() => {
  installGlobals();
  boardRows.value = [];
  voidSpy.mockClear().mockResolvedValue({ ok: true });
  boardRefresh.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe("ProductionStageGrid — produce render", () => {
  it("lists a planned row with a 'Processar' affordance", () => {
    boardRows.value = [row({ planned_qty: "30", planned_orders: [wo({ status: "planned" })] })];
    const w = mountGrid();
    expect(w.text()).toContain("PAO-001");
    expect(byText(w, "button", "Processar")).toBeTruthy();
  });

  it("shows the welcoming empty state when nothing is planned", () => {
    boardRows.value = [];
    const w = mountGrid();
    expect(w.text()).toContain("Nada planejado para processar");
  });
});

describe("ProductionStageGrid — lote em processo (gestão)", () => {
  it("opens the management dialog for a started row and voids with a reason", async () => {
    boardRows.value = [
      row({ started_qty: "30", started_orders: [wo({ pk: 7, ref: "WO-007", started_qty: "30" })] }),
    ];
    const w = mountGrid();

    // Com lote em processo a célula de ação mostra a quantidade (30), não o verbo.
    await byText(w, "button", "30")!.trigger("click");
    expect(w.text()).toContain("em processo");

    await byText(w, "button", "Estornar…")!.trigger("click");
    await w.find('textarea[aria-label="Motivo do estorno"]').setValue("queimou");
    await byText(w, "button", "Confirmar estorno")!.trigger("click");
    expect(voidSpy).toHaveBeenCalledWith(7, "queimou");
  });
});
