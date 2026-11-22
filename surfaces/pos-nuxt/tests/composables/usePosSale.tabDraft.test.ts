// A comanda não se perde quando a sessão cai (#3315). Medido na pilha viva: lançar,
// derrubar a sessão, entrar de novo, e o que foi lançado depois do último salvamento
// automático sumia (o `cart` é memória da página, e o login recarrega a página). Agora
// cada mudança ainda não salva fica no dispositivo e volta quando a comanda reabre.
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { toast } from "vue-sonner";

import type { POSCartItem } from "~/types/pos";
import { TAB_DRAFT_STORAGE_KEY, readTabDraft, writeTabDraft, type TabDraft } from "~/utils/tabDraft";
import { makeSale, makeTabPayload } from "./_posSaleHarness";

const { operatorId } = vi.hoisted(() => ({ operatorId: { value: 7 as number | string } }));
mockNuxtImport("useNuxtData", () => () => ({ data: ref({ operator: { id: operatorId.value } }) }));

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

const GERGELIM: POSCartItem = { sku: "PAO", name: "Pão", qty: 1, unit_price_q: 500, line_id: "L1" } as POSCartItem;
const LANCHE: POSCartItem = { sku: "CAFE", name: "Café", qty: 2, unit_price_q: 300, line_id: "L2" } as POSCartItem;

type Harness = ReturnType<typeof makeSale>;
let instances: Harness[] = [];

function draftFor(items: POSCartItem[], overrides: Partial<TabDraft> = {}): TabDraft {
  return {
    tabRef: "1009",
    tabSessionKey: "sess-1",
    baseRevision: "rev-1",
    operatorId: "7",
    savedAt: new Date().toISOString(),
    fields: {
      items, customerName: "", customerRef: "", customerPhone: "", customerTaxId: "", customerEmail: "",
      salesMode: "counter", fulfillmentConfirmed: true, fulfillmentType: "pickup",
      deliveryAddress: "", deliveryAddressStructured: {}, deliveryStreetNumber: "", deliveryNeighborhood: "",
      deliveryComplement: "", deliveryInstructions: "", deliveryDate: "", deliveryTimeSlot: "",
      deliveryFeeOverrideInput: "", deliveryFeeOverride: false, orderNotes: "",
    },
    ...overrides,
  };
}

/** O servidor da comanda: abrir devolve o que ele tem; salvar aceita. */
function serverWith(items: POSCartItem[], revision = "rev-1") {
  return vi.fn(async (path: string) => {
    if (String(path).includes("/open/")) {
      return makeTabPayload({ tab_ref: "1009", tab_display: "1009", session_key: "sess-1", tab_session_key: "sess-1", items, revision });
    }
    if (String(path).includes("/tabs/save/")) return { revision: "rev-2" };
    return {};
  });
}

function sale(actionCall: ReturnType<typeof vi.fn>) {
  const h = makeSale({ actionCall });
  instances.push(h);
  return h;
}

async function settle(ms = 0) {
  await nextTick();
  await vi.advanceTimersByTimeAsync(ms);
  await nextTick();
}

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
  operatorId.value = 7;
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.warning).mockReset();
});

afterEach(() => {
  for (const h of instances.splice(0)) h.handles.dispose();
  window.localStorage.clear();
  vi.useRealTimers();
});

describe("usePosSale: o rascunho da comanda no dispositivo", () => {
  it("o que ainda não foi salvo fica no dispositivo; o salvar aceito apaga", async () => {
    const actionCall = serverWith([GERGELIM]);
    const { sale: s } = sale(actionCall);
    await s.openTab("1009", { drawerChecked: true });
    await settle(50);
    expect(window.localStorage.getItem(TAB_DRAFT_STORAGE_KEY)).toBeNull();

    s.cart.items = [...s.cart.items, { ...LANCHE }];
    await settle();
    const draft = readTabDraft();
    expect(draft?.tabSessionKey).toBe("sess-1");
    expect(draft?.baseRevision).toBe("rev-1");
    expect(draft?.fields.items.map((item) => item.sku)).toEqual(["PAO", "CAFE"]);

    await settle(1300); // o salvamento automático
    expect(actionCall.mock.calls.some((call) => String(call[0]).includes("/tabs/save/"))).toBe(true);
    expect(window.localStorage.getItem(TAB_DRAFT_STORAGE_KEY)).toBeNull();
  });

  it("a comanda reabre com o rascunho e o salva, quando o servidor não mudou", async () => {
    writeTabDraft(draftFor([GERGELIM, LANCHE]));
    const actionCall = serverWith([GERGELIM]);
    const { sale: s } = sale(actionCall);

    await s.openTab("1009", { drawerChecked: true });
    await settle();

    expect(s.cart.items.map((item) => item.sku)).toEqual(["PAO", "CAFE"]);
    expect(s.unsaved.value).toBe(true);
    expect(toast.success).toHaveBeenCalledWith("O que foi lançado antes de a sessão cair voltou para a comanda.");
    await settle(1300);
    const saves = actionCall.mock.calls.filter((call) => String(call[0]).includes("/tabs/save/"));
    expect(saves.length).toBeGreaterThan(0);
    const body = saves.at(-1)![1]!.body as { items: POSCartItem[] };
    expect(body.items.map((item) => item.sku)).toEqual(["PAO", "CAFE"]);
  });

  it("depois de entrar de novo, a venda reabre sozinha na comanda do rascunho", async () => {
    writeTabDraft(draftFor([GERGELIM, LANCHE]));
    const actionCall = serverWith([GERGELIM]);
    const { sale: s } = sale(actionCall);
    await settle(10);

    expect(actionCall.mock.calls.some((call) => String(call[0]).includes("/tabs/1009/open/"))).toBe(true);
    expect(s.cart.tabRef).toBe("1009");
    expect(s.cart.items.map((item) => item.sku)).toEqual(["PAO", "CAFE"]);
  });

  it("outra estação mexeu na comanda: não reaplica por cima, e diz", async () => {
    writeTabDraft(draftFor([GERGELIM, LANCHE]));
    const { sale: s } = sale(serverWith([GERGELIM, { ...GERGELIM, line_id: "L9" }], "rev-9"));

    await s.openTab("1009", { drawerChecked: true });
    await settle();

    expect(s.cart.items.map((item) => item.line_id)).toEqual(["L1", "L9"]);
    expect(toast.warning).toHaveBeenCalled();
    expect(readTabDraft()).toBeNull();
  });

  it("a gravação chegou e só a resposta se perdeu: nada a reaplicar", async () => {
    writeTabDraft(draftFor([GERGELIM, LANCHE]));
    const { sale: s } = sale(serverWith([GERGELIM, LANCHE], "rev-2"));

    await s.openTab("1009", { drawerChecked: true });
    await settle();

    expect(s.unsaved.value).toBe(false);
    expect(toast.warning).not.toHaveBeenCalled();
    expect(readTabDraft()).toBeNull();
  });

  it("quem entrou é outra pessoa: o rascunho espera por quem lançou", async () => {
    writeTabDraft(draftFor([GERGELIM, LANCHE], { operatorId: "3" }));
    const actionCall = serverWith([GERGELIM]);
    const { sale: s } = sale(actionCall);
    await settle(10);

    expect(actionCall.mock.calls.some((call) => String(call[0]).includes("/open/"))).toBe(false);
    await s.openTab("1009", { drawerChecked: true });
    await settle();
    expect(s.cart.items.map((item) => item.sku)).toEqual(["PAO"]);
    expect(readTabDraft()?.operatorId).toBe("3");
  });
});
