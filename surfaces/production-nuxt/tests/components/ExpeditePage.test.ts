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

import ExpeditePage from "../../app/pages/expedite.vue";
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

function installGlobals(hash = "") {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useHead", () => {});
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
  emits: ["confirm-batch", "confirm-one", "correct", "go-expedition"],
  template: "<div data-quality-gate-stub />",
};
const mountPage = () =>
  shallowMount(ExpeditePage, {
    global: { stubs: { QualityGatePanel: QualityGatePanelStub } },
  });

describe("Expedição — fila própria de Qualidade", () => {
  const panel = (wrapper: ReturnType<typeof shallowMount>) =>
    wrapper.findComponent({ name: "QualityGatePanel" });

  it("remove lotes finalizados da expedição e acusa pendências na aba QC", async () => {
    const wrapper = mountPage();

    expect(wrapper.text()).toContain("Baguete aberta");
    expect(wrapper.text()).not.toContain("Croissant aguardando QC");
    expect(panel(wrapper).exists()).toBe(false);
    const qualityTab = wrapper
      .findAll('[role="tab"]')
      .find((tab) => tab.text().includes("Qualidade (QC)"));
    expect(qualityTab?.text()).toContain("1");
    expect(qualityTab?.attributes("aria-selected")).toBe("false");

    await qualityTab!.trigger("click");
    await nextTick();

    expect(wrapper.text()).not.toContain("Baguete aberta");
    expect(qualityTab?.attributes("aria-selected")).toBe("true");
    // O portão recebe os lotes do dia (abertos inclusive: ele os deixa fora).
    expect(panel(wrapper).props("orders")).toHaveLength(3);
    expect(panel(wrapper).props("batchAvailable")).toBe(true);
    expect(panel(wrapper).props("isToday")).toBe(true);
  });

  it("abre diretamente em QC quando veio da notificação do Gestor", () => {
    vi.unstubAllGlobals();
    installGlobals("#quality");

    const wrapper = mountPage();

    expect(panel(wrapper).exists()).toBe(true);
    expect(wrapper.text()).not.toContain("Baguete aberta");
    expect(
      wrapper
        .findAll('[role="tab"]')
        .find((tab) => tab.text().includes("Qualidade (QC)"))
        ?.attributes("aria-selected"),
    ).toBe("true");
  });

  it("confirma o conjunto sem exceção num ato só, sem caixa do navegador", async () => {
    vi.unstubAllGlobals();
    installGlobals("#quality");
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
    vi.unstubAllGlobals();
    installGlobals("#quality");
    const nativeConfirm = vi.fn(() => true);
    vi.stubGlobal("confirm", nativeConfirm);
    reviewQuality.mockClear();

    const wrapper = mountPage();
    panel(wrapper).vm.$emit("confirm-one", orders.value[1]);
    await flushPromises();

    expect(reviewQuality).toHaveBeenCalledWith(2, 1);
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it("o atalho dos lotes não fechados volta para a Expedição", async () => {
    vi.unstubAllGlobals();
    installGlobals("#quality");

    const wrapper = mountPage();
    panel(wrapper).vm.$emit("go-expedition");
    await nextTick();

    expect(wrapper.text()).toContain("Baguete aberta");
    expect(panel(wrapper).exists()).toBe(false);
  });
});
