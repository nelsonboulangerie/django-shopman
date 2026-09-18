import { mockNuxtImport, mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, ref } from "vue";

import SessionPage from "~/pages/session/index.vue";
import type { DayClosingProjection } from "~/types/closing";
import type {
  POSAccountBalanceProjection,
  POSChangeRequestProjection,
  POSPendingCashRefundProjection,
  POSProjection,
} from "~/types/pos";

import { makeProjection } from "../composables/_posSaleHarness";

// A ORGANIZAÇÃO da antesala com o turno aberto — e só ela. O que cada botão
// faz na rede é prova do `usePosCashSession`; aqui a pergunta é onde as coisas
// moram: o que precisa de gente fica em cima e só aparece quando existe, as
// ações da gaveta são tiles que abrem um diálogo, e o fim do expediente só
// aparece para quem pode. E a regra que não muda: o PIN do gerente sobe por
// cima do diálogo aberto sem fechar o formulário digitado.

// ── Os composables de rede viram estado dirigido pelo teste ────────────────
// Declarados como função (hoisted) e lidos na hora da montagem: a fábrica do
// mock não toca em nada quando o módulo carrega.
function makeCashSession() {
  return {
    busy: ref(false),
    movementKinds: computed(() => ["sangria", "suprimento"]),
    managerChallenge: ref<{ code: string; message: string } | null>(null),
    openCashShift: vi.fn().mockResolvedValue(true),
    closeCashShift: vi.fn().mockResolvedValue(true),
    registerCashMovement: vi.fn().mockResolvedValue(true),
    canOpenDrawer: ref(true),
    drawerUnavailableReason: ref(""),
    drawerProbing: ref(false),
    openDrawerWithoutSale: vi.fn().mockResolvedValue(true),
    probeDrawer: vi.fn().mockResolvedValue({ ok: true, message: "" }),
    pendingChangeRequests: ref<POSChangeRequestProjection[]>([]),
    pendingCashRefunds: ref<POSPendingCashRefundProjection[]>([]),
    refundCash: vi.fn().mockResolvedValue(true),
    accountBalances: ref<POSAccountBalanceProjection[]>([]),
    settleAccount: vi.fn().mockResolvedValue(true),
    requestChange: vi.fn().mockResolvedValue(true),
    serveChangeRequest: vi.fn().mockResolvedValue(true),
    cancelChangeRequest: vi.fn().mockResolvedValue(true),
  };
}
let cash: ReturnType<typeof makeCashSession>;
let projection: POSProjection | null;
let servedClosing: DayClosingProjection | null;

mockNuxtImport("usePosCashSession", () => () => cash);
mockNuxtImport("usePosTerminal", () => async () => ({
  pos: computed(() => projection),
  shift: ref({ count: 7 }),
  actions: computed(() => []),
  pending: ref(false),
  refresh: vi.fn().mockResolvedValue(undefined),
}));
mockNuxtImport("useOperatorLock", () => () => ({
  operator: ref({ name: "Ana" }),
  lock: vi.fn(),
}));
mockNuxtImport("usePosAction", () => () => ({ call: vi.fn() }));

registerEndpoint("/api/v1/backstage/closing/", () => ({ closing: servedClosing }));

function openShiftProjection(overrides: Partial<POSProjection["cash_runtime"]> = {}): POSProjection {
  return makeProjection({
    has_open_cash_session: true,
    cash_runtime: {
      has_open_shift: true,
      shift_id: 1,
      terminal_ref: "T1",
      terminal_label: "Caixa 1",
      operator_username: "ana",
      opened_at: "2026-09-16T08:00:00-03:00",
      can_audit_cash: false,
      ...overrides,
    } as POSProjection["cash_runtime"],
  });
}

const mounted: VueWrapper[] = [];
async function openLobby() {
  clearNuxtData("day-closing-entry");
  const wrapper = await mountSuspended(SessionPage, {
    global: { stubs: { PosFunctionRail: true, RailToggle: true } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  await flushPromises();
  await flushPromises();
  return wrapper;
}

// Diálogos moram num portal (body), fora da árvore do wrapper.
const dialog = (key: string) => document.body.querySelector<HTMLElement>(`[data-session-dialog="${key}"]`);
const tile = (wrapper: VueWrapper, key: string) => wrapper.find(`[data-session-tile="${key}"]`);
const pickedKind = (key: string) =>
  dialog(key)?.querySelector('[aria-labelledby="movement-kind-label"] [aria-pressed="true"]')?.textContent?.trim();

describe("antesala — turno aberto, organização da tela", () => {
  beforeEach(() => {
    cash = makeCashSession();
    projection = openShiftProjection();
    servedClosing = null;
  });
  afterEach(() => {
    for (const wrapper of mounted.splice(0)) wrapper.unmount();
    document.body.innerHTML = "";
  });

  it("(a) sem pendência: nada de 'Precisa de você', tiles no lugar e NENHUM formulário aberto", async () => {
    const wrapper = await openLobby();
    const text = wrapper.text();

    expect(text).toContain("Continuar vendendo");
    expect(text).not.toContain("Precisa de você");
    expect(wrapper.find("[data-needs-you]").exists()).toBe(false);

    expect(text).toContain("Gaveta");
    const labels = wrapper.findAll("[data-session-tile]").map((t) => t.text());
    expect(labels.some((l) => l.includes("Pedir troco"))).toBe(true);
    expect(labels.some((l) => l.includes("Saída de caixa"))).toBe(true);
    expect(labels.some((l) => l.includes("Entrada de caixa"))).toBe(true);
    expect(labels.some((l) => l.includes("Abrir gaveta"))).toBe(true);
    expect(labels.some((l) => l.includes("Fechar caixa"))).toBe(true);

    // Os dois formulários que ficavam abertos o turno inteiro agora só existem
    // a um toque: nenhum diálogo no body, nenhum CTA de formulário na tela.
    expect(document.body.querySelector("[data-session-dialog]")).toBeNull();
    expect(text).not.toContain("Registrar movimento");
    expect(text).not.toContain("Preciso de troco");
    expect(text).not.toContain("Valor contado");
  });

  it("(b) com pendências: o bloco aparece com a contagem e os três grupos intactos", async () => {
    cash.pendingChangeRequests.value = [
      { ref: "cr-1", amount_q: 10000, amount_display: "R$ 100,00", denominations: [], note: "", requested_by: "Ana", requested_at: "" },
    ];
    cash.pendingCashRefunds.value = [
      { order_ref: "o-9", amount_q: 2500, amount_display: "R$ 25,00", customer_name: "Bia", cancelled_at: "" },
    ];
    cash.accountBalances.value = [
      { customer_ref: "c-1", customer_name: "Carlos", balance_q: 4200, balance_display: "R$ 42,00", intents: 2, oldest_at: "" },
    ];
    const wrapper = await openLobby();
    const block = wrapper.find("[data-needs-you]");

    expect(block.exists()).toBe(true);
    expect(block.text()).toContain("Precisa de você");
    expect(block.text()).toContain("3");
    expect(block.text()).toContain("Devoluções em dinheiro pendentes");
    expect(block.text()).toContain("Pedidos de troco pendentes");
    expect(block.text()).toContain("Contas na casa");
    // As ações de cada pendência continuam onde estavam.
    expect(block.text()).toContain("Devolver");
    expect(block.text()).toContain("Atender");
    expect(block.text()).toContain("Cancelar pedido");
    expect(block.text()).toContain("Receber acerto");
    expect(block.find("[data-house-accounts]").exists()).toBe(true);
    expect(block.find('[aria-label="Pedidos de troco pendentes"]').exists()).toBe(true);
    // O bloco vem ANTES da gaveta: pendência primeiro, ação rara depois.
    const html = wrapper.html();
    expect(html.indexOf("data-needs-you")).toBeLessThan(html.indexOf("data-session-tile"));
  });

  it("(c) o tile de saída abre o diálogo de movimento com 'sangria' já escolhido", async () => {
    const wrapper = await openLobby();
    await tile(wrapper, "movement:sangria").trigger("click");
    await flushPromises();

    const dlg = dialog("movement");
    expect(dlg).not.toBeNull();
    expect(dlg!.textContent).toContain("Saída de caixa");
    expect(pickedKind("movement")).toBe("Saída de caixa");
    // O seletor continua dentro, para trocar; o aviso do PIN é o da saída.
    expect(dlg!.textContent).toContain("Entrada de caixa");
    expect(dlg!.textContent).toContain("Tirar dinheiro da gaveta precisa da autorização de um gerente.");
    expect(dlg!.textContent).toContain("Registrar movimento");
  });

  it("(c') o tile de entrada abre o MESMO diálogo com 'suprimento'; troco e fechar têm o seu", async () => {
    const wrapper = await openLobby();
    await tile(wrapper, "movement:suprimento").trigger("click");
    await flushPromises();
    expect(pickedKind("movement")).toBe("Entrada de caixa");

    await tile(wrapper, "request_change").trigger("click");
    await flushPromises();
    expect(dialog("request_change")?.textContent).toContain("Preciso de troco");

    await tile(wrapper, "close_shift").trigger("click");
    await flushPromises();
    expect(dialog("close_shift")?.textContent).toContain("Valor contado");
    expect(dialog("close_shift")?.textContent).toContain("Contagem cega");
  });

  it("(d) sem caminho de software, o tile da gaveta fica desabilitado e DIZ o motivo", async () => {
    cash.canOpenDrawer.value = false;
    cash.drawerUnavailableReason.value = "Gaveta na impressora, sem agente nesta estação.";
    const wrapper = await openLobby();
    const drawerTile = tile(wrapper, "open_drawer");

    expect(drawerTile.exists()).toBe(true);
    expect((drawerTile.element as HTMLButtonElement).disabled).toBe(true);
    expect(drawerTile.text()).toContain("Gaveta na impressora, sem agente nesta estação.");

    await drawerTile.trigger("click");
    await flushPromises();
    expect(dialog("open_drawer")).toBeNull();
  });

  it("(e) relatório só para quem audita; fechamento do dia só quando a API deixou", async () => {
    let wrapper = await openLobby();
    expect(tile(wrapper, "cash_report").exists()).toBe(false);
    expect(tile(wrapper, "day_closing").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Fim do expediente");
    wrapper.unmount();
    mounted.splice(0);

    projection = openShiftProjection({ can_audit_cash: true });
    servedClosing = {
      today: "2026-09-16", today_display: "16/09/2026", items: [], has_items: false,
      already_closed: false, existing_closing_display: "", total_available: 0,
      production_summary: {}, reconciliation_errors: [], pending_production: [],
      has_pending_production: false, upcoming_preorders: [], has_upcoming_preorders: false,
    };
    wrapper = await openLobby();
    await flushPromises();
    expect(wrapper.text()).toContain("Fim do expediente");
    expect(tile(wrapper, "cash_report").text()).toContain("Relatório de caixa");
    expect(tile(wrapper, "day_closing").text()).toContain("Fazer o fechamento");
    expect(tile(wrapper, "day_closing").text()).toContain("16/09/2026");
  });

  it("o PIN do gerente sobe POR CIMA do diálogo aberto, e o formulário digitado fica", async () => {
    const wrapper = await openLobby();
    await tile(wrapper, "movement:sangria").trigger("click");
    await flushPromises();
    const amountInput = dialog("movement")!.querySelector<HTMLInputElement>('input[inputmode="decimal"]')!;
    amountInput.value = "50,00";
    amountInput.dispatchEvent(new Event("input", { bubbles: true }));
    await nextTick();

    // O servidor recusou com `manager_approval_required`: o desafio sobe.
    cash.managerChallenge.value = { code: "manager_approval_required", message: "Precisa do gerente." };
    await nextTick();
    await flushPromises();

    const pinDialog = document.body.querySelector<HTMLElement>("[data-drawer-manager-auth]");
    expect(pinDialog).not.toBeNull();
    expect(pinDialog!.getAttribute("data-state")).toBe("open");
    // O diálogo de movimento NÃO fechou, e o valor continua lá.
    const movementDialog = dialog("movement");
    expect(movementDialog).not.toBeNull();
    expect(movementDialog!.getAttribute("data-state")).toBe("open");
    expect(movementDialog!.querySelector<HTMLInputElement>('input[inputmode="decimal"]')!.value).toBe("50,00");
    // O PIN veio DEPOIS no body: é o que fica por cima.
    const stack = [...document.body.querySelectorAll("[data-session-dialog], [data-drawer-manager-auth]")];
    expect(stack.indexOf(movementDialog!)).toBeLessThan(stack.indexOf(pinDialog!));
  });
});
