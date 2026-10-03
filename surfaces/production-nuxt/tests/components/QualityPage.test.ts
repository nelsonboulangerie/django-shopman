import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
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

const navigate = vi.fn();

function installGlobals(hash = "") {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useHead", () => {});
  vi.stubGlobal("navigateTo", navigate);
  vi.stubGlobal("useRoute", () => ({ query: {}, hash }));
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
    correctQuality: vi.fn(),
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
  installGlobals();
});

afterEach(() => vi.unstubAllGlobals());

// O portão é componente auto-importado pelo Nuxt; aqui, um stub com nome e props.
const QualityGatePanelStub = {
  name: "QualityGatePanel",
  props: ["orders", "grades", "defects", "isToday", "batchAvailable", "submitting", "reviewAvailable", "correctionAvailable"],
  emits: ["confirm-batch", "confirm-one", "correct", "go-close"],
  template: "<div data-quality-gate-stub />",
};
const ProductionHeaderStub = {
  name: "ProductionHeader",
  props: ["title", "count", "countLabel", "progress", "pending", "query"],
  template: "<header />",
};
const mountPage = () =>
  shallowMount(QualityPage, {
    global: {
      stubs: {
        QualityGatePanel: QualityGatePanelStub,
        ProductionHeader: ProductionHeaderStub,
      },
    },
  });

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
    expect(header.props("count")).toBe(1);
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
