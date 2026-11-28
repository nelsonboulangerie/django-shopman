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
// O fechar do lote: cada teste diz o que o servidor responde.
const finish = vi.fn(async (..._args: unknown[]): Promise<Record<string, unknown>> => ({ ok: true }));
const reviewQuality = vi.fn(async () => ({ ok: true }));
const reviewQualityBatch = vi.fn(async () => ({ ok: true }));
const concluded = vi.fn(async (..._args: unknown[]) => true);
const ovenError = ref("");
const sonnerError = vi.fn();
const clearTimer = vi.fn();
const ovenConcludeEnabled = ref(false);
const success = vi.fn();
const remember = vi.fn();
const selectedDate = ref("");
// WP-F15: a leitura que falha (Django parado) e o canal da Produção.
const readError = ref<unknown>(null);
const kioskGone = ref(false);
const realtime = ref<"connecting" | "live" | "polling">("live");
const refreshKiosk = vi.fn();

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
    oven_until_display: "",
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
  vi.stubGlobal("useSonner", { success, error: sonnerError });
  vi.stubGlobal("useQcKiosk", () => ({
    kiosk: computed(() => kioskGone.value ? null : ({
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
    error: readError,
    realtime,
    fallbackPollMs: computed(() => 30_000),
    submitting: ref(false),
    refresh: refreshKiosk,
    finish,
    quickFinish: vi.fn(),
    reviewQuality,
    reviewQualityBatch,
    correctQuality: vi.fn(),
  }));
  vi.stubGlobal("useFloorTimers", () => ({
    lastMinutes: ref<number | null>(null),
    clear: clearTimer,
    soundOff: ref(false),
    enableSound: vi.fn(),
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
    errorFor: () => ovenError.value,
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
  readError.value = null;
  kioskGone.value = false;
  realtime.value = "live";
  refreshKiosk.mockClear();
  ovenConcludeEnabled.value = false;
  selectedDate.value = "";
  route.query = {};
  navigate.mockClear();
  remember.mockClear();
  concluded.mockClear();
  concluded.mockResolvedValue(true);
  ovenError.value = "";
  sonnerError.mockClear();
  clearTimer.mockClear();
  success.mockClear();
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
  props: [
    "title", "count", "countLabel", "progress", "pending", "query", "alerts", "actions", "stale",
    "offline", "realtime", "pollMs",
  ],
  template: "<header><slot name='status' /><slot name='primary' /></header>",
};
const OperatorRecordNavStub = {
  name: "OperatorRecordNav",
  props: ["trail", "current", "to", "previousLabel", "nextLabel"],
  template: "<nav data-record-nav />",
};
// A tela de finalização é auto-importada pelo Nuxt; aqui, um stub com nome e props, e
// a pergunta de descarte que a tela expõe para a página.
type RouteGuard = (to: { query: Record<string, string> }) => boolean | Promise<boolean>;
let routeGuard: RouteGuard | null = null;
const confirmDiscardChanges = vi.fn(async (_action: "leave" | "switch") => true);
const QcCloseScreenStub = {
  name: "QcCloseScreen",
  props: ["title", "subtitle", "planned", "started", "unit", "grades", "defects", "submitting"],
  emits: ["back", "confirm"],
  setup(_props: unknown, { expose }: { expose: (exposed: Record<string, unknown>) => void }) {
    expose({ confirmDiscardChanges });
  },
  template: "<section data-qc-screen />",
};
const ShortageDialogStub = {
  name: "ShortageDialog",
  props: { shortage: { type: Object, default: null }, allowShortLot: Boolean },
  emits: ["update:open", "confirm", "close-short-lot", "review"],
  template: "<div data-shortage-dialog />",
};
const OperatorScreenStateStub = {
  name: "OperatorScreenState",
  props: ["state", "what", "description"],
  emits: ["retry"],
  template: "<div data-screen-state :data-state='state' />",
};
const mountPage = () => {
  const wrapper = shallowMount(ClosePage, {
    global: {
      stubs: {
        ...nuxtUiStubs,
        ProductionHeader: ProductionHeaderStub,
        OperatorRecordNav: OperatorRecordNavStub,
        QcCloseScreen: QcCloseScreenStub,
        ShortageDialog: ShortageDialogStub,
        OperatorScreenState: OperatorScreenStateStub,
      },
    },
  });
  mounted.push(wrapper);
  return wrapper;
};

describe("Finalização", () => {
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

  it("o cabeçalho diz Finalização e conta os lotes para finalizar", () => {
    const wrapper = mountPage();
    const header = wrapper.findComponent({ name: "ProductionHeader" });

    expect(header.props("title")).toBe("Finalização");
    expect(header.props("count")).toBe(2);
    expect(header.props("countLabel")).toBe("para finalizar");
  });

  it("a lista Para finalizar é uma coluna só, em todo tamanho (dono, 28/11)", () => {
    const wrapper = mountPage();
    const list = wrapper.find("[data-close-open-list]");

    expect(list.exists()).toBe(true);
    expect(list.classes().some((name) => /grid-cols-/.test(name))).toBe(false);
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

describe("Finalização — tempo real honesto (WP-F15)", () => {
  it("entrega ao cabeçalho o estado do canal e a cadência de reserva", () => {
    realtime.value = "polling";
    const header = mountPage().findComponent({ name: "ProductionHeader" });
    expect(header.props("realtime")).toBe("polling");
    expect(header.props("pollMs")).toBe(30_000);
    expect(header.props("offline")).toBe(false);
  });

  it("Django parado na primeira leitura: o erro com Tentar de novo, não a tela em branco", async () => {
    kioskGone.value = true;
    readError.value = new Error("502");
    const wrapper = mountPage();
    const header = wrapper.findComponent({ name: "ProductionHeader" });
    expect(header.props("offline")).toBe(true);
    const state = wrapper.findComponent({ name: "OperatorScreenState" });
    expect(state.exists()).toBe(true);
    expect(state.props("state")).toBe("error");
    state.vm.$emit("retry");
    expect(refreshKiosk).toHaveBeenCalledTimes(1);
  });

  it("dado velho vira o aviso do cabeçalho (com X, do kit), antes do lote esquecido", () => {
    readError.value = new Error("502");
    previousOpen.value = { count: 1, date: "2026-09-27" };
    const wrapper = mountPage();
    const header = wrapper.findComponent({ name: "ProductionHeader" });
    expect(header.props("stale")).toBe(true);
    const alerts = header.props("alerts");
    expect(alerts.map((alert: { id: string }) => alert.id)).toEqual(["stale-read", "previous-open"]);
    expect(alerts[0].action.label).toBe("Tentar de novo");
    alerts[0].action.onSelect();
    expect(refreshKiosk).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).not.toContain("Mostrando o último painel");
  });
});

describe("Finalização — a quantidade do cartão em pt-BR", () => {
  // Beta 05/11: "4200 un." aqui e "4.200" na Produção.
  it("escreve o milhar e a unidade como as outras telas", () => {
    orders.value = [order(1, "Croissant", { planned_qty: "4200", output_unit: "un" })];
    const wrapper = mountPage();
    expect(wrapper.find("[data-close-finish]").text()).toContain("4.200 un.");
  });
});

describe("Finalização — o lote mora na URL", () => {
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

  it("aberto pela URL, mostra a finalização do lote e o anterior/próximo no cabeçalho", async () => {
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

  it("lote de massa chega à finalização na unidade dele e sem arredondar (P1-22)", async () => {
    orders.value = [
      order(7, "Massa de croissant", {
        planned_qty: "2.5",
        started_qty: "2.35",
        output_unit: "kg",
      }),
    ];
    route.query = { lot: "7" };
    const wrapper = mountPage();
    await flushPromises();

    const screen = wrapper.findComponent({ name: "QcCloseScreen" });
    expect(screen.props()).toMatchObject({ planned: 2.5, started: 2.35, unit: "kg" });
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

  // WP-F12 (P1-10): ler não grava. Só o toque em Finalizar declara a retirada.
  it("abrir o lote pela URL ou pelo ‹ › não declara a retirada do forno", async () => {
    ovenConcludeEnabled.value = true;
    route.query = { lot: "1" };
    const wrapper = mountPage();
    await flushPromises();
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(true);

    route.query = { lot: "4" };
    await flushPromises();
    route.query = { lot: "1" };
    await flushPromises();

    expect(concluded).not.toHaveBeenCalled();
    expect(clearTimer).not.toHaveBeenCalled();
  });

  it("o toque em Finalizar declara a retirada e só então abre o lote", async () => {
    ovenConcludeEnabled.value = true;
    const wrapper = mountPage();

    await wrapper.find("[data-close-finish]").trigger("click");
    await flushPromises();

    expect(concluded).toHaveBeenCalledWith(1, 1);
    expect(clearTimer).toHaveBeenCalledWith("1");
    expect(navigate).toHaveBeenCalledWith({ path: "/close", query: { lot: "1" } });
  });

  it("a retirada recusada fica no painel e diz o porquê no cartão (P1-11)", async () => {
    ovenConcludeEnabled.value = true;
    concluded.mockImplementation(async () => {
      ovenError.value = "O lote mudou em outro dispositivo.";
      return false;
    });
    const wrapper = mountPage();

    await wrapper.find("[data-close-finish]").trigger("click");
    await flushPromises();

    expect(navigate).not.toHaveBeenCalled();
    const alert = wrapper.find("[data-close-oven-error]");
    expect(alert.exists()).toBe(true);
    expect(alert.attributes("role")).toBe("alert");
    expect(alert.text()).toBe("O lote mudou em outro dispositivo.");
  });

  it("o lote no forno por outro tablet diz isso no cartão, sem 'Iniciar timer'", () => {
    ovenConcludeEnabled.value = true;
    orders.value = [order(1, "Baguete aberta", { status: "started" })];
    const wrapper = mountPage();

    expect(wrapper.find("[data-close-in-oven]").text()).toBe("No forno");
  });

  it("com a hora do servidor, o cartão diz até quando fica no forno", () => {
    ovenConcludeEnabled.value = true;
    orders.value = [
      order(1, "Baguete aberta", { status: "started", oven_until_display: "5h40" }),
    ];
    const wrapper = mountPage();

    expect(wrapper.find("[data-close-in-oven]").text()).toBe("No forno até 5h40");
  });

  it("finalizado, volta à LISTA com o nome do lote, sem pular para o próximo (P2-11)", async () => {
    route.query = { lot: "1" };
    const wrapper = mountPage();
    await flushPromises();

    wrapper.findComponent({ name: "QcCloseScreen" }).vm.$emit("confirm", {
      quantity: "12",
      partition: [],
      yield_deviation_confirmed: false,
      yield_deviation_reason: "",
      reason: "",
    });
    await flushPromises();

    expect(success).toHaveBeenCalledWith("Lote de Baguete aberta finalizado.");
    expect(navigate).toHaveBeenLastCalledWith({ path: "/close", query: {} }, { replace: true });
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(false);
  });

  it("lote que não se fecha daqui (já fechado) devolve ao painel", async () => {
    route.query = { lot: "2" };
    const wrapper = mountPage();
    await flushPromises();

    expect(navigate).toHaveBeenCalledWith({ path: "/close", query: {} }, { replace: true });
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(false);
  });
});

// WP-F06 (decisão 1 do dono, 23/11/2026): rendeu menos que o encomendado, o lote
// fecha com a verdade, na MESMA tentativa, e os pedidos vão para o Gestor.
describe("Finalização — o lote curto fecha com a verdade", () => {
  const recusa = {
    code: "order_shortage",
    work_order_ref: "WO-4",
    idempotency_key: "k",
    possibilities: [
      { kind: "retry", label: "Revisar quantidade", enabled: true, proof: "" },
      { kind: "confirm", label: "Fechar com 4", enabled: true, proof: "assinada" },
    ],
    required: "6",
    requested: "4",
    order_refs: ["NB-1"],
    orders: [{ ref: "NB-1", qty: "6" }],
  };
  const payload = {
    quantity: "4",
    partition: [{ quantity: "4", quality_grade_ref: "standard" }],
    yield_deviation_confirmed: true,
    yield_deviation_reason: "Massa fraca",
    reason: "",
  };

  async function lotRefused() {
    route.query = { lot: "4" };
    finish.mockReset();
    finish.mockResolvedValueOnce({ ok: false, shortage: recusa });
    const wrapper = mountPage();
    await flushPromises();
    wrapper.findComponent({ name: "QcCloseScreen" }).vm.$emit("confirm", payload);
    await flushPromises();
    return wrapper;
  }

  it("a recusa abre o diálogo que sabe fechar o lote curto", async () => {
    const wrapper = await lotRefused();
    const dialog = wrapper.findComponent({ name: "ShortageDialog" });

    expect(dialog.props("shortage")).toEqual(recusa);
    expect(dialog.props("allowShortLot")).toBe(true);
  });

  it("fechar com o que rendeu manda de novo o mesmo lote com a prova da recusa", async () => {
    const wrapper = await lotRefused();
    finish.mockResolvedValueOnce({ ok: true });

    wrapper.findComponent({ name: "ShortageDialog" }).vm.$emit("close-short-lot", "assinada");
    await flushPromises();

    expect(finish).toHaveBeenCalledTimes(2);
    const [first, second] = finish.mock.calls;
    expect(second!.slice(0, 9)).toEqual(first!.slice(0, 9));
    expect(second![9]).toBe("assinada");
    expect(wrapper.findComponent({ name: "ShortageDialog" }).props("shortage")).toBeNull();
  });

  it("revisar quantidade fecha a recusa e devolve a contagem, sem fechar nada", async () => {
    const wrapper = await lotRefused();

    wrapper.findComponent({ name: "ShortageDialog" }).vm.$emit("review");
    await flushPromises();

    expect(finish).toHaveBeenCalledTimes(1);
    expect(wrapper.findComponent({ name: "ShortageDialog" }).props("shortage")).toBeNull();
    expect(wrapper.findComponent({ name: "QcCloseScreen" }).exists()).toBe(true);
  });
});
