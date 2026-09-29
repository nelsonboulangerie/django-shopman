import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { shallowMount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ExpeditePage from "../../app/pages/expedite.vue";
import type { QCOrderCardProjection } from "../../app/types/production";

const orders = ref<QCOrderCardProjection[]>([]);

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
  vi.stubGlobal("useSonner", { success: vi.fn(), error: vi.fn() });
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
      actions: orders.value
        .filter((item) => item.closed && !item.quality_reviewed)
        .map((item) => ({ ref: `review_qc:${item.pk}`, enabled: true })),
    })),
    selectedDate: ref(""),
    pending: ref(false),
    error: ref(null),
    submitting: ref(false),
    refresh: vi.fn(),
    finish: vi.fn(),
    quickFinish: vi.fn(),
    reviewQuality: vi.fn(),
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

describe("Expedição — fila própria de Qualidade", () => {
  it("remove lotes finalizados da expedição e acusa pendências na aba QC", async () => {
    const wrapper = shallowMount(ExpeditePage);

    expect(wrapper.text()).toContain("Baguete aberta");
    expect(wrapper.text()).not.toContain("Croissant aguardando QC");
    const qualityTab = wrapper
      .findAll('[role="tab"]')
      .find((tab) => tab.text().includes("Qualidade (QC)"));
    expect(qualityTab?.text()).toContain("1");
    expect(qualityTab?.attributes("aria-selected")).toBe("false");

    await qualityTab!.trigger("click");
    await nextTick();

    expect(wrapper.text()).not.toContain("Baguete aberta");
    expect(wrapper.text()).toContain("Croissant aguardando QC");
    expect(wrapper.text()).toContain("Aguardando revisão");
    expect(wrapper.text()).toContain("Brioche revisado");
    expect(wrapper.text()).toContain("Qualidade revisada");
    expect(qualityTab?.attributes("aria-selected")).toBe("true");
  });

  it("abre diretamente em QC quando veio da notificação do Gestor", () => {
    vi.unstubAllGlobals();
    installGlobals("#quality");

    const wrapper = shallowMount(ExpeditePage);

    expect(wrapper.text()).toContain("Croissant aguardando QC");
    expect(wrapper.text()).not.toContain("Baguete aberta");
    expect(
      wrapper
        .findAll('[role="tab"]')
        .find((tab) => tab.text().includes("Qualidade (QC)"))
        ?.attributes("aria-selected"),
    ).toBe("true");
  });
});
