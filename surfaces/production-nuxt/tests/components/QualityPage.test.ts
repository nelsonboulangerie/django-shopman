import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { flushPromises, shallowMount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import QualityPage from "../../app/pages/quality.vue";
import type { QCOrderCardProjection } from "../../app/types/production";

const orders = ref<QCOrderCardProjection[]>([]);
const reviewQuality = vi.fn(async () => ({ ok: true }));
const reviewQualityBatch = vi.fn(async () => ({ ok: true }));
const success = vi.fn();

function order(
  pk: number,
  name: string,
  overrides: Partial<QCOrderCardProjection> = {},
): QCOrderCardProjection {
  return {
    pk,
    ref: `WO-${pk}`,
    rev: 1,
    recipe_name: name,
    output_sku: `SKU-${pk}`,
    position_ref: "vitrine",
    status: "planned",
    planned_qty: "12",
    started_qty: "",
    started_at_display: "",
    elapsed_minutes: 0,
    can_close: true,
    closed: false,
    can_correct: false,
    quality_reviewed: false,
    partition: [],
    correction_count: 0,
    last_correction_at_display: "",
    committed_qty: "0",
    full_price_qty: "",
    discounted_qty: "",
    loss_qty: "",
    quality_exception: false,
    closed_by: "",
    closed_at_display: "",
    typical_loss_qty: "",
    alert_waiting_count: 0,
    ...overrides,
  };
}

// A rota é reativa como a do Nuxt; o `navigateTo` do teste a troca (só na /quality).
const route = reactive<{ path: string; query: Record<string, string>; hash: string }>({
  path: "/quality",
  query: {},
  hash: "",
});
const navigate = vi.fn(
  async (location: { path?: string; query?: Record<string, string> }, _options?: { replace?: boolean }) => {
    if (location.path === "/quality") route.query = { ...(location.query ?? {}) };
  },
);
const remember = vi.fn();
const correctQuality = vi.fn(async () => ({ ok: true }));

function installGlobals(hash = "") {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("onBeforeRouteUpdate", () => {});
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useHead", () => {});
  vi.stubGlobal("useProductionRail", () => productionRail);
  vi.stubGlobal("navigateTo", navigate);
  route.hash = hash;
  vi.stubGlobal("useRoute", () => route);
  vi.stubGlobal("useRecordTrail", () => ({
    remember,
    trail: computed(() => null),
    load: vi.fn(),
  }));
  vi.stubGlobal("useSonner", { success, error: vi.fn() });
  vi.stubGlobal("useQcKiosk", () => ({
    kiosk: computed(() => ({
      selected_date: "2026-09-28",
      selected_date_display: "Hoje",
      orders: orders.value,
      closed_count: orders.value.filter((item) => item.closed).length,
      total_count: orders.value.length,
      grades: [],
      defects: [],
      recipes: [],
      previous_open_count: 0,
      previous_open_date: "",
      access: {},
      actions: [
        ...orders.value
          .filter((item) => item.closed && !item.quality_reviewed)
          .map((item) => ({
            ref: `review_qc:${item.pk}`,
            kind: "review_qc",
            enabled: true,
          })),
        ...orders.value
          .filter((item) => item.closed && item.can_correct)
          .map((item) => ({
            ref: `correct_qc:${item.pk}`,
            kind: "correct_qc",
            enabled: true,
          })),
        { ref: "review_qc_batch:abc", kind: "review_qc_batch", enabled: true },
      ],
    })),
    selectedDate: ref(""),
    pending: ref(false),
    error: ref(null),
    submitting: ref(false),
    refresh: vi.fn(),
    finish: vi.fn(),
    quickFinish: vi.fn(),
    reviewQuality,
    reviewQualityBatch,
    correctQuality,
  }));
  vi.stubGlobal("useFloorTimers", () => ({
    lastMinutes: ref<number | null>(null),
    clear: vi.fn(),
    get: () => null,
    isRinging: () => false,
    isSeen: () => false,
    remainingLabel: () => "",
    extend: vi.fn(),
    arm: vi.fn(),
    seen: vi.fn(),
  }));
  vi.stubGlobal("useOvenFacts", () => ({
    isPending: () => false,
    errorFor: () => "",
    currentRev: (_pk: number, rev: number) => rev,
    armed: vi.fn(),
    concluded: vi.fn(),
  }));
}

beforeEach(() => {
  orders.value = [
    order(1, "Baguete aberta"),
    order(2, "Croissant aguardando QC", {
      status: "finished",
      closed: true,
      can_close: false,
      can_correct: true,
      full_price_qty: "12",
    }),
    order(3, "Brioche revisado", {
      status: "finished",
      closed: true,
      can_close: false,
      can_correct: true,
      quality_reviewed: true,
      full_price_qty: "8",
    }),
  ];
  route.query = {};
  navigate.mockClear();
  remember.mockClear();
  correctQuality.mockClear();
  installGlobals();
});

// Cada tela montada escuta a mesma rota: desmontar entre os testes.
const mounted: Array<{ unmount: () => void }> = [];
afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount());
  vi.unstubAllGlobals();
});

// O portão é componente auto-importado pelo Nuxt; aqui, um stub com nome e props.
const QualityGatePanelStub = {
  name: "QualityGatePanel",
  props: ["orders", "grades", "defects", "isToday", "batchAvailable", "submitting", "reviewAvailable", "correctionAvailable"],
  emits: ["confirm-batch", "confirm-one", "correct", "go-close"],
  template: "<div data-quality-gate-stub />",
};
// O selo da Qualidade no rail (V4-PROD): a tela conta ao rail os lotes à espera.
const productionRail = ref({ qualityPending: 0 });

const ProductionHeaderStub = {
  name: "ProductionHeader",
  props: ["title", "count", "countLabel", "progress", "pending", "query", "eyebrow", "stale", "searchable"],
  template: "<header><slot name='status' /></header>",
};
const OperatorRecordNavStub = {
  name: "OperatorRecordNav",
  props: ["trail", "current", "to", "previousLabel", "nextLabel"],
  template: "<nav data-record-nav />",
};
const QcCloseScreenStub = {
  name: "QcCloseScreen",
  props: ["title", "subtitle", "planned", "started", "grades", "defects", "submitting", "mode", "initialPartition"],
  emits: ["back", "confirm"],
  template: "<section data-qc-screen />",
};
const mountPage = () => {
  const wrapper = shallowMount(QualityPage, {
    global: {
      stubs: {
        QualityGatePanel: QualityGatePanelStub,
        ProductionHeader: ProductionHeaderStub,
        OperatorRecordNav: OperatorRecordNavStub,
        QcCloseScreen: QcCloseScreenStub,
        NuxtTabs: true,
      },
    },
  });
  mounted.push(wrapper);
  return wrapper;
};

describe("Qualidade — aba própria", () => {
  const panel = (wrapper: ReturnType<typeof shallowMount>) =>
    wrapper.findComponent({ name: "QualityGatePanel" });

  it("entrega ao portão os lotes do dia e conta os que aguardam revisão", () => {
    const wrapper = mountPage();

    // O portão recebe os lotes do dia (abertos inclusive: ele os deixa fora).
    expect(panel(wrapper).props("orders")).toHaveLength(3);
    expect(panel(wrapper).props("batchAvailable")).toBe(true);
    expect(panel(wrapper).props("isToday")).toBe(true);
    const header = wrapper.findComponent({ name: "ProductionHeader" });
    expect(header.props("title")).toBe("Qualidade");
    // A contagem dos que aguardam revisão vai para o selo da Qualidade no rail.
    expect(productionRail.value.qualityPending).toBe(1);
  });

  it("confirma o conjunto sem exceção num ato só, sem caixa do navegador", async () => {
    const nativeConfirm = vi.fn(() => true);
    vi.stubGlobal("confirm", nativeConfirm);
    reviewQualityBatch.mockClear();
    success.mockClear();

    const wrapper = mountPage();
    panel(wrapper).vm.$emit("confirm-batch");
    await flushPromises();

    expect(reviewQualityBatch).toHaveBeenCalledTimes(1);
    expect(success).toHaveBeenCalledWith("1 lote confirmado.");
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it("confirma uma exceção assim, sem window.confirm", async () => {
    const nativeConfirm = vi.fn(() => true);
    vi.stubGlobal("confirm", nativeConfirm);
    reviewQuality.mockClear();

    const wrapper = mountPage();
    panel(wrapper).vm.$emit("confirm-one", orders.value[1]);
    await flushPromises();

    expect(reviewQuality).toHaveBeenCalledWith(2, 1);
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it("o atalho dos lotes não fechados leva ao Fechamento", async () => {
    navigate.mockClear();

    const wrapper = mountPage();
    panel(wrapper).vm.$emit("go-close");
    await nextTick();

    expect(navigate).toHaveBeenCalledWith({ path: "/close", query: {} });
  });
});

describe("Qualidade — a correção do lote mora na URL", () => {
  const panel = (wrapper: ReturnType<typeof shallowMount>) =>
    wrapper.findComponent({ name: "QualityGatePanel" });

  it("o portão grava a trilha dos lotes que ele mostra com Corrigir", () => {
    orders.value = orders.value.map((item) =>
      item.pk === 2 ? { ...item, quality_exception: true, loss_qty: "2" } : item,
    );
    mountPage();

    // Na vista "Para confirmar", as exceções (o lote limpo não tem Corrigir na tela).
    expect(remember).toHaveBeenLastCalledWith(["2"], {
      from: "/quality",
      label: "Exceções para olhar",
    });
  });

  it("Corrigir leva ao lote pela URL; aberto, mostra a correção e o anterior/próximo", async () => {
    const wrapper = mountPage();
    panel(wrapper).vm.$emit("correct", orders.value[1]);
    await flushPromises();

    expect(navigate).toHaveBeenCalledWith({ path: "/quality", query: { lot: "2" } });
    const screen = wrapper.findComponent({ name: "QcCloseScreen" });
    expect(screen.exists()).toBe(true);
    expect(screen.props("mode")).toBe("correct");
    expect(screen.props("title")).toBe("Croissant aguardando QC");
    const nav = wrapper.findComponent({ name: "OperatorRecordNav" });
    expect(nav.props()).toMatchObject({
      trail: "production-quality-lots",
      current: "2",
      previousLabel: "Lote anterior",
      nextLabel: "Próximo lote",
    });
    expect(nav.props("to")("3")).toEqual({ path: "/quality", query: { lot: "3" } });
  });

  it("salvar a correção volta ao portão substituindo a entrada do lote", async () => {
    route.query = { lot: "2" };
    const wrapper = mountPage();
    await flushPromises();

    wrapper
      .findComponent({ name: "QcCloseScreen" })
      .vm.$emit("confirm", { partition: [], reason: "Contagem errada no fechamento" });
    await flushPromises();

    expect(correctQuality).toHaveBeenCalledWith(2, 1, [], "Contagem errada no fechamento");
    expect(navigate).toHaveBeenLastCalledWith({ path: "/quality", query: {} }, { replace: true });
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(false);
  });

  it("lote sem correção possível, aberto por link, volta ao portão", async () => {
    route.query = { lot: "1" };
    const wrapper = mountPage();
    await flushPromises();

    expect(navigate).toHaveBeenCalledWith({ path: "/quality", query: {} }, { replace: true });
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(false);
  });
});
