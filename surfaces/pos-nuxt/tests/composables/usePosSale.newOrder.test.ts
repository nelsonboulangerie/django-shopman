import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { NEW_ORDER_ROUTE, wantsNewOrder } from "~/presentation/orderSetup";
import type { POSTabProjection } from "~/types/pos";

import { makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

// "Nova encomenda" (seção Encomendas, S9): a venda abre na PRÓXIMA COMANDA LIVRE,
// já no modo Encomendas, com o assistente na primeira etapa. A comanda de uma
// venda em andamento nunca é tomada: ela fica no quadro, como estava.

function tab(ref: string, state: string): POSTabProjection {
  return {
    ref, display_ref: ref, session_key: state === "in_use" ? `sess-${ref}` : "", state,
    status_label: "", status_class: "", customer_name: "", customer_phone: "",
    item_count: state === "in_use" ? 2 : 0, line_count: 0, total_display: "",
    last_touched_display: "", items_preview: "",
  };
}

let instances: Array<ReturnType<typeof makeSale>> = [];
afterEach(() => {
  instances.forEach((h) => h.handles.dispose());
  instances = [];
});

function sale(tabs: POSTabProjection[], payload: Record<string, unknown>) {
  const actionCall = vi.fn().mockResolvedValue(makeTabPayload(payload));
  const h = makeSale({ tabs, actionCall });
  instances.push(h);
  return h;
}

describe("Nova encomenda: a URL da venda", () => {
  it("o sinal é de uma vez: `/?new=order`, e só ele abre a encomenda", () => {
    expect(NEW_ORDER_ROUTE).toEqual({ path: "/", query: { new: "order" } });
    expect(wantsNewOrder({ new: "order" })).toBe(true);
    expect(wantsNewOrder({})).toBe(false);
    expect(wantsNewOrder({ new: "1" })).toBe(false);
    expect(wantsNewOrder({ edit: "NB-7" })).toBe(false);
  });
});

describe("usePosSale.openNewOrder", () => {
  it("abre a próxima comanda livre, não a que tem venda em andamento, já no modo Encomendas", async () => {
    const h = sale([tab("1", "in_use"), tab("2", "empty")], {
      tab_ref: "2", tab_display: "2", session_key: "sess-2", tab_session_key: "sess-2",
    });

    await h.sale.openNewOrder();
    await nextTick();

    expect(String(h.handles.actionCall.mock.calls[0]![0])).toContain("/tabs/2/open/");
    expect(h.sale.cart.tabRef).toBe("2");
    expect(h.sale.cart.salesMode).toBe("order");
    // O assistente começa pela primeira etapa que falta: o cliente.
    expect(h.sale.orderSetupPending.value).toBe(true);
    expect(h.sale.orderSetupIssue.value).toBe("customer");
    expect(h.sale.inSaleView.value).toBe(true);
  });

  it("todas ocupadas: a próxima numeração depois da última", async () => {
    const h = sale([tab("1", "in_use"), tab("2", "in_use")], {
      tab_ref: "3", tab_display: "3", session_key: "sess-3", tab_session_key: "sess-3",
    });
    await h.sale.openNewOrder();
    expect(String(h.handles.actionCall.mock.calls[0]![0])).toContain("/tabs/3/open/");
    expect(h.sale.cart.salesMode).toBe("order");
  });

  it("se outra estação ocupou a comanda no caminho, ela abre como está e a venda dela não troca de modo", async () => {
    const h = sale([tab("2", "empty")], {
      tab_ref: "2", tab_display: "2", session_key: "sess-2", tab_session_key: "sess-2",
      sales_mode: "counter",
      items: [{ line_id: "L-1", sku: "PAO", name: "Pão", qty: 1, unit_price_q: 500 }],
    });
    await h.sale.openNewOrder();
    expect(h.sale.cart.tabRef).toBe("2");
    expect(h.sale.cart.items).toHaveLength(1);
    expect(h.sale.cart.salesMode).toBe("counter");
  });

  it("abrir comanda pelo quadro continua no modo que a comanda tem (o padrão é balcão)", async () => {
    const h = sale([tab("2", "empty")], {
      tab_ref: "2", tab_display: "2", session_key: "sess-2", tab_session_key: "sess-2",
    });
    await h.sale.openTab("2");
    expect(h.sale.cart.salesMode).toBe("counter");
  });
});
