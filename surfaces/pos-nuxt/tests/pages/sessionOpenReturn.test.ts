import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { mockNuxtImport, mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, reactive, ref } from "vue";

import SessionPage from "~/pages/session/index.vue";
import { cashOpenReturnTarget, openShiftGate, SALE_HOME } from "~/presentation/cash";
import { wantsNewOrder } from "~/presentation/orderSetup";
import type { POSProjection } from "~/types/pos";

import { makeProjection } from "../composables/_posSaleHarness";

// SEM CAIXA ABERTO, O GESTO NÃO SE PERDE. A venda manda para a antesala e, aberto
// o caixa, a antesala volta para o que o operador veio fazer: "Nova encomenda"
// (`/?new=order`) termina no assistente, "Refazer" (`/?redo=<ref>`) na comanda
// refeita. O destino só vale dentro do PDV.

const read = (path: string) => readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), path), "utf8");
const salePage = read("../../app/pages/index.vue");

const openCashShift = vi.fn().mockResolvedValue(true);
let projection: POSProjection;

mockNuxtImport("usePosCashSession", () => () => ({
  busy: ref(false),
  movementKinds: computed(() => ["sangria", "suprimento"]),
  managerChallenge: ref(null),
  openCashShift,
  closeCashShift: vi.fn().mockResolvedValue(true),
  registerCashMovement: vi.fn().mockResolvedValue(true),
  canOpenDrawer: ref(true),
  drawerUnavailableReason: ref(""),
  drawerProbing: ref(false),
  openDrawerWithoutSale: vi.fn().mockResolvedValue(true),
  probeDrawer: vi.fn().mockResolvedValue({ ok: true, message: "" }),
  pendingChangeRequests: ref([]),
  pendingCashRefunds: ref([]),
  refundCash: vi.fn().mockResolvedValue(true),
  pendingCardMachineRefunds: ref([]),
  recordCardMachineRefund: vi.fn().mockResolvedValue(true),
  accountBalances: ref([]),
  settleAccount: vi.fn().mockResolvedValue(true),
  requestChange: vi.fn().mockResolvedValue(true),
  serveChangeRequest: vi.fn().mockResolvedValue(true),
  cancelChangeRequest: vi.fn().mockResolvedValue(true),
}));
mockNuxtImport("usePosTerminal", () => async () => ({
  pos: computed(() => projection),
  shift: ref({ count: 0 }),
  actions: computed(() => []),
  pending: ref(false),
  refresh: vi.fn().mockResolvedValue(undefined),
}));
mockNuxtImport("useOperatorLock", () => () => ({ operator: ref({ name: "Ana" }), lock: vi.fn() }));
mockNuxtImport("usePosAction", () => () => ({ call: vi.fn() }));
const navigate = vi.fn().mockResolvedValue(undefined);
mockNuxtImport("navigateTo", () => (...args: unknown[]) => navigate(...args));
const route = reactive({ path: "/session", query: {} as Record<string, string>, params: {} });
mockNuxtImport("useRoute", () => () => route);

registerEndpoint("/api/v1/backstage/closing/", () => ({ closing: null }));

const mounted: VueWrapper[] = [];
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.innerHTML = "";
});
beforeEach(() => {
  projection = makeProjection({ has_open_cash_session: false });
  navigate.mockClear();
  openCashShift.mockClear();
  route.query = {};
});

/** A venda sem caixa manda para a antesala; aqui o operador abre o caixa. */
async function arriveAndOpen(query: Record<string, string>) {
  route.query = query;
  const wrapper = await mountSuspended(SessionPage, {
    global: { stubs: { PosFunctionRail: true, RailToggle: true } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  await flushPromises();
  const dialog = document.body.querySelector<HTMLElement>('[data-session-dialog="open_shift"]');
  expect(dialog, "open=1 cai direto no diálogo de abertura").not.toBeNull();
  const input = dialog!.querySelector<HTMLInputElement>('input[inputmode="decimal"]')!;
  input.value = "100,00";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  await nextTick();
  const button = [...dialog!.querySelectorAll("button")].find((b) => b.textContent?.includes("Abrir caixa e vender"))!;
  button.click();
  await flushPromises();
  expect(openCashShift).toHaveBeenCalledTimes(1);
  return wrapper;
}

/** O destino em que a antesala terminou, como a venda vai lê-lo. */
function landedQuery(): Record<string, string> {
  const target = String(navigate.mock.calls.at(-1)?.[0]);
  return Object.fromEntries(new URL(target, "http://pdv.invalid").searchParams);
}

describe("caixa fechado: a ida leva o destino", () => {
  it("a venda manda para a antesala com o caminho e a query originais", () => {
    expect(salePage).toContain("await navigateTo(openShiftGate(useRoute().fullPath), { replace: true });");
    expect(openShiftGate("/?new=order")).toEqual({ path: "/session", query: { open: "1", next: "/?new=order" } });
    expect(openShiftGate("/?redo=NB-7")).toEqual({ path: "/session", query: { open: "1", next: "/?redo=NB-7" } });
    // A venda vazia não leva `next`: a volta sem destino já é ela.
    expect(openShiftGate("/")).toEqual({ path: "/session", query: { open: "1" } });
  });
});

describe("caixa fechado: aberto o caixa, a antesala volta para o gesto", () => {
  it("Nova encomenda termina no assistente", async () => {
    await arriveAndOpen(openShiftGate("/?new=order").query);
    expect(navigate).toHaveBeenLastCalledWith("/?new=order");
    expect(wantsNewOrder(landedQuery())).toBe(true);
  });

  it("Refazer termina na comanda refeita", async () => {
    await arriveAndOpen(openShiftGate("/?redo=NB-7").query);
    expect(navigate).toHaveBeenLastCalledWith("/?redo=NB-7");
    expect(landedQuery().redo).toBe("NB-7");
  });

  it("sem destino, volta para a venda", async () => {
    await arriveAndOpen({ open: "1" });
    expect(navigate).toHaveBeenLastCalledWith(SALE_HOME);
  });

  it.each(["https://x", "//x", "/\\x", "http:/x", "javascript:alert(1)"])(
    "destino de fora do PDV (%s) é ignorado e a volta é a venda",
    async (next) => {
      await arriveAndOpen({ open: "1", next });
      expect(navigate).toHaveBeenLastCalledWith(SALE_HOME);
    },
  );

  it("'Continuar vendendo' com o turno já aberto também leva ao gesto", async () => {
    projection = makeProjection({
      has_open_cash_session: true,
      cash_runtime: {
        has_open_shift: true, shift_id: 1, terminal_ref: "T1", terminal_label: "Caixa 1",
        operator_username: "ana", opened_at: "2026-10-03T08:00:00-03:00", can_audit_cash: false,
      } as POSProjection["cash_runtime"],
    });
    route.query = { next: "/?new=order" };
    const wrapper = await mountSuspended(SessionPage, {
      global: { stubs: { PosFunctionRail: true, RailToggle: true } },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    await flushPromises();
    await wrapper.find('[data-session-tile="continue_selling"]').trigger("click");
    await flushPromises();
    expect(navigate).toHaveBeenLastCalledWith("/?new=order");
  });
});

describe("cashOpenReturnTarget: só caminho interno do PDV", () => {
  it("aceita caminho com query", () => {
    expect(cashOpenReturnTarget("/?new=order")).toBe("/?new=order");
    expect(cashOpenReturnTarget(["/?redo=NB-7"])).toBe("/?redo=NB-7");
    expect(cashOpenReturnTarget("/preorders?mode=day")).toBe("/preorders?mode=day");
  });

  it("recusa esquema, host, barra dupla, barra invertida, quebra de linha e a própria antesala", () => {
    for (const raw of ["https://x", "//x", "/\\x", "\\\\x", "x", "", "/\n//x", "/session", "/session/report", undefined, 3]) {
      expect(cashOpenReturnTarget(raw)).toBe(SALE_HOME);
    }
  });
});
