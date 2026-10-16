import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { flushPromises, shallowMount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ClosePage from "../../app/pages/close.vue";
import type { QCOrderCardProjection } from "../../app/types/production";
import { nuxtUiStubs } from "../support/nuxtUiStubs";

const orders = ref<QCOrderCardProjection[]>([]);
const previousOpen = ref({ count: 0, date: "" });
const reviewQuality = vi.fn(async () => ({ ok: true }));
const reviewQualityBatch = vi.fn(async () => ({ ok: true }));
const concluded = vi.fn(async () => true);
const ovenConcludeEnabled = ref(false);
const success = vi.fn();
const remember = vi.fn();
const selectedDate = ref("");

// A rota é reativa como a do Nuxt; o `navigateTo` do teste a troca.
const route = reactive<{ path: string; query: Record<string, string>; hash: string }>({
  path: "/close",
  query: {},
  hash: "",
});
const navigate = vi.fn(
  async (location: { query?: Record<string, string> }, _options?: { replace?: boolean }) => {
    route.query = { ...(location.query ?? {}) };
  },
);

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

function installGlobals() {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("onBeforeRouteUpdate", (guard: RouteGuard) => {
    routeGuard = guard;
  });
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useHead", () => {});
  vi.stubGlobal("useRoute", () => route);
  vi.stubGlobal("navigateTo", navigate);
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
      previous_open_count: previousOpen.value.count,
      previous_open_date: previousOpen.value.date,
      access: {},
      actions: [
        ...orders.value
          .filter((item) => !item.closed)
          .map((item) => ({ ref: `finish:${item.pk}`, kind: "finish", enabled: true })),
        ...(ovenConcludeEnabled.value
          ? [{ ref: "oven_conclude:1", kind: "oven_conclude", enabled: true }]
          : []),
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
    selectedDate,
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
    concluded,
  }));
}

beforeEach(() => {
  orders.value = [
    order(1, "Baguete aberta"),
    order(4, "Ciabatta aberta"),
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
  previousOpen.value = { count: 0, date: "" };
  ovenConcludeEnabled.value = false;
  selectedDate.value = "";
  route.query = {};
  navigate.mockClear();
  remember.mockClear();
  concluded.mockClear();
  installGlobals();
});

// Cada tela montada escuta a mesma rota: desmontar entre os testes.
const mounted: Array<{ unmount: () => void }> = [];
afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount());
  vi.unstubAllGlobals();
});

const ProductionHeaderStub = {
  name: "ProductionHeader",
  props: ["title", "count", "countLabel", "progress", "pending", "query", "alerts", "actions", "stale"],
  template: "<header><slot name='status' /><slot name='primary' /></header>",
};
const OperatorRecordNavStub = {
  name: "OperatorRecordNav",
  props: ["trail", "current", "to", "previousLabel", "nextLabel"],
  template: "<nav data-record-nav />",
};
// A tela de fechamento é auto-importada pelo Nuxt; aqui, um stub com nome e props, e
// a pergunta de descarte que a tela expõe para a página.
type RouteGuard = (to: { query: Record<string, string> }) => boolean | Promise<boolean>;
let routeGuard: RouteGuard | null = null;
const confirmDiscardChanges = vi.fn(async (_action: "leave" | "switch") => true);
const QcCloseScreenStub = {
  name: "QcCloseScreen",
  props: ["title", "subtitle", "planned", "started", "grades", "defects", "submitting"],
  emits: ["back", "confirm"],
  setup(_props: unknown, { expose }: { expose: (exposed: Record<string, unknown>) => void }) {
    expose({ confirmDiscardChanges });
  },
  template: "<section data-qc-screen />",
};
const mountPage = () => {
  const wrapper = shallowMount(ClosePage, {
    global: {
      stubs: {
        ...nuxtUiStubs,
        ProductionHeader: ProductionHeaderStub,
        OperatorRecordNav: OperatorRecordNavStub,
        QcCloseScreen: QcCloseScreenStub,
      },
    },
  });
  mounted.push(wrapper);
  return wrapper;
};

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
    expect(header.props("count")).toBe(2);
    expect(header.props("countLabel")).toBe("para finalizar");
  });

  it("o lote ainda não aberto diz isso, sem chamar de produzido", () => {
    const wrapper = mountPage();

    expect(wrapper.text()).toContain("ainda não aberto");
    expect(wrapper.text()).not.toMatch(/produzid/i);
  });

  it("lote esquecido de outro dia vira o aviso da tela, com a saída para o dia pendente", () => {
    previousOpen.value = { count: 2, date: "2026-09-27" };
    const wrapper = mountPage();
    const alerts = wrapper.findComponent({ name: "ProductionHeader" }).props("alerts");

    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toMatchObject({
      color: "warning",
      title: "2 lotes abertos de dias anteriores",
      action: { label: "Ver os lotes de 27/09" },
    });
    alerts[0].action.onSelect();
    expect(selectedDate.value).toBe("2026-09-27");
  });
});

describe("Fechamento — o lote mora na URL", () => {
  it("o painel grava a trilha dos lotes que se fecham daqui, na ordem dele", () => {
    mountPage();

    expect(remember).toHaveBeenLastCalledWith(["1", "4"], {
      from: "/close",
      label: "Lotes para finalizar",
    });
  });

  it("Finalizar leva ao lote pela URL, com o dia e a busca", async () => {
    selectedDate.value = "2026-09-27";
    route.query = { date: "2026-09-27", q: "bag" };
    const wrapper = mountPage();

    await wrapper.find("[data-close-finish]").trigger("click");

    expect(navigate).toHaveBeenCalledWith({
      path: "/close",
      query: { date: "2026-09-27", q: "bag", lot: "1" },
    });
  });

  it("aberto pela URL, mostra o fechamento do lote e o anterior/próximo no cabeçalho", async () => {
    route.query = { lot: "4" };
    const wrapper = mountPage();
    await flushPromises();

    const screen = wrapper.findComponent({ name: "QcCloseScreen" });
    expect(screen.exists()).toBe(true);
    expect(screen.props("title")).toBe("Ciabatta aberta");
    const nav = wrapper.findComponent({ name: "OperatorRecordNav" });
    expect(nav.props()).toMatchObject({
      trail: "production-close-lots",
      current: "4",
      previousLabel: "Lote anterior",
      nextLabel: "Próximo lote",
    });
    expect(nav.props("to")("1")).toEqual({ path: "/close", query: { lot: "1" } });
    // No lote, a trilha não é regravada: ela é a lista de onde a pessoa veio.
    remember.mockClear();
    orders.value = [...orders.value, order(5, "Pão de forma")];
    await flushPromises();
    expect(remember).not.toHaveBeenCalled();
  });

  it("o ‹ › para outro lote pergunta antes de descartar o que foi digitado", async () => {
    route.query = { lot: "1" };
    mountPage();
    await flushPromises();
    expect(routeGuard).not.toBeNull();

    confirmDiscardChanges.mockResolvedValueOnce(false);
    await expect(routeGuard!({ query: { lot: "4" } })).resolves.toBe(false);
    expect(confirmDiscardChanges).toHaveBeenLastCalledWith("switch");

    // Sair para o painel (sem lote) não pergunta aqui: o voltar já perguntou na tela.
    confirmDiscardChanges.mockClear();
    expect(await routeGuard!({ query: {} })).toBe(true);
    expect(confirmDiscardChanges).not.toHaveBeenCalled();
  });

  it("voltar sai do lote substituindo a entrada dele no histórico", async () => {
    route.query = { lot: "1" };
    const wrapper = mountPage();
    await flushPromises();

    wrapper.findComponent({ name: "QcCloseScreen" }).vm.$emit("back");
    await flushPromises();

    expect(navigate).toHaveBeenLastCalledWith({ path: "/close", query: {} }, { replace: true });
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(false);
    expect(wrapper.text()).toContain("Baguete aberta");
  });

  it("o voltar do navegador (a URL sem lote) volta ao painel", async () => {
    route.query = { lot: "1" };
    const wrapper = mountPage();
    await flushPromises();
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(true);

    route.query = {};
    await flushPromises();

    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(false);
    expect(wrapper.findComponent({ name: "OperatorRecordNav" }).exists()).toBe(false);
  });

  it("abrir o lote declara a retirada do forno antes do fechamento", async () => {
    ovenConcludeEnabled.value = true;
    route.query = { lot: "1" };
    const wrapper = mountPage();
    await flushPromises();

    expect(concluded).toHaveBeenCalledWith(1, 1);
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(true);
  });

  it("lote que não se fecha daqui (já fechado) devolve ao painel", async () => {
    route.query = { lot: "2" };
    const wrapper = mountPage();
    await flushPromises();

    expect(navigate).toHaveBeenCalledWith({ path: "/close", query: {} }, { replace: true });
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(false);
  });
});
