import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { shallowMount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ClosePage from "../../app/pages/close.vue";
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

const ProductionHeaderStub = {
  name: "ProductionHeader",
  props: ["title", "count", "countLabel", "progress", "pending", "query"],
  template: "<header />",
};
const mountPage = () =>
  shallowMount(ClosePage, {
    global: { stubs: { ProductionHeader: ProductionHeaderStub } },
  });

describe("Fechamento", () => {
  it("mostra só os lotes abertos, sem a revisão de qualidade", () => {
    const wrapper = mountPage();

    expect(wrapper.text()).toContain("Baguete aberta");
    expect(wrapper.text()).not.toContain("Croissant aguardando QC");
    expect(wrapper.text()).not.toContain("Brioche revisado");
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false);
    expect(wrapper.findComponent({ name: "QualityGatePanel" }).exists()).toBe(
      false,
    );
  });

  it("o cabeçalho diz Fechamento e conta os lotes para finalizar", () => {
    const wrapper = mountPage();
    const header = wrapper.findComponent({ name: "ProductionHeader" });

    expect(header.props("title")).toBe("Fechamento");
    expect(header.props("count")).toBe(1);
    expect(header.props("countLabel")).toBe("lotes para finalizar");
  });

  it("o lote ainda não aberto diz isso, sem chamar de produzido", () => {
    const wrapper = mountPage();

    expect(wrapper.text()).toContain("ainda não aberto");
    expect(wrapper.text()).not.toMatch(/produzid/i);
  });
});
