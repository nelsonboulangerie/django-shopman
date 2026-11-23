import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { NEW_ORDER_ROUTE, wantsNewOrder } from "~/presentation/orderSetup";
import type { POSTabProjection } from "~/types/pos";

import { makeSale, makeTabPayload } from "./_posSaleHarness";

const { confirmNewOrder } = vi.hoisted(() => ({ confirmNewOrder: vi.fn() }));
vi.mock("../../../operator-kit/app/composables/useConfirm", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../../operator-kit/app/composables/useConfirm")>(),
  useConfirm: () => confirmNewOrder,
}));
beforeEach(() => confirmNewOrder.mockReset().mockResolvedValue(true));

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
  it("não abre comanda enquanto a confirmação está pendente nem ao desistir", async () => {
    let answer!: (confirmed: boolean) => void;
    confirmNewOrder.mockImplementationOnce(() => new Promise<boolean>((resolve) => { answer = resolve; }));
    const h = sale([tab("2", "empty")], { tab_ref: "2", session_key: "sess-2" });
    const opening = h.sale.openNewOrder();
    expect(confirmNewOrder).toHaveBeenCalledWith(expect.objectContaining({
      tone: "primary", confirmLabel: "Iniciar encomenda", cancelLabel: "Voltar sem iniciar",
    }));
    expect(h.handles.actionCall).not.toHaveBeenCalled();
    await h.sale.openNewOrder();
    expect(confirmNewOrder).toHaveBeenCalledTimes(1);
    answer(false);
    await opening;
    expect(h.handles.actionCall).not.toHaveBeenCalled();
    expect(h.sale.cart.tabSessionKey).toBe("");
    expect(h.sale.showTabs.value).toBe(true);
    // Desistir não trava uma nova tentativa. Só a confirmação abre a comanda.
    await h.sale.openNewOrder();
    expect(h.handles.actionCall.mock.calls.filter((call) => String(call[0]).includes("/next-free/"))).toHaveLength(1);
  });

  it("abre a próxima comanda livre, não a que tem venda em andamento, já no modo Encomendas", async () => {
    const h = sale([tab("1", "in_use"), tab("2", "empty")], {
      tab_ref: "2", tab_display: "2", session_key: "sess-2", tab_session_key: "sess-2",
    });

    await h.sale.openNewOrder();
    await nextTick();

    // Quem escolhe e reserva a comanda é o servidor (#2443).
    expect(String(h.handles.actionCall.mock.calls[0]![0])).toContain("/tabs/next-free/");
    expect(h.sale.cart.tabRef).toBe("2");
    expect(h.sale.cart.salesMode).toBe("order");
    // O assistente começa pela primeira etapa que falta: o cliente.
    expect(h.sale.orderSetupPending.value).toBe(true);
    expect(h.sale.orderSetupIssue.value).toBe("customer");
    expect(h.sale.inSaleView.value).toBe(true);
  });

  it("todas ocupadas: abre a que o servidor reservou (a seguinte à última)", async () => {
    const h = sale([tab("1", "in_use"), tab("2", "in_use")], {
      tab_ref: "3", tab_display: "3", session_key: "sess-3", tab_session_key: "sess-3",
    });
    expect(await h.sale.openNewOrder()).toBe(true);
    expect(String(h.handles.actionCall.mock.calls[0]![0])).toContain("/tabs/next-free/");
    expect(h.sale.cart.tabRef).toBe("3");
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

describe("Nova encomenda abandonada não prende a comanda", () => {
  // Beta test de 05/11/2026 (PDV2-13): a segunda "Nova" abriu #1009 e a #1008
  // ficou "Em uso" com 0 itens.
  const opened = { tab_ref: "2", tab_display: "2", session_key: "sess-2", tab_session_key: "sess-2" };

  it("a segunda Nova encomenda reaproveita a que segue vazia", async () => {
    const h = sale([tab("1", "in_use"), tab("2", "empty")], opened);
    await h.sale.openNewOrder();
    await nextTick();
    const opens = () => h.handles.actionCall.mock.calls.filter((call) => String(call[0]).includes("/next-free/")).length;
    expect(opens()).toBe(1);
    await h.sale.openNewOrder();
    expect(opens()).toBe(1);
    expect(h.sale.cart.tabRef).toBe("2");
  });

  it("sair com a encomenda vazia libera a comanda; com item, não", async () => {
    const h = sale([tab("2", "empty")], opened);
    await h.sale.openNewOrder();
    await nextTick();
    await h.sale.releaseAbandonedTab();
    const clears = h.handles.actionCall.mock.calls.filter((call) => String(call[0]).includes("/clear/"));
    expect(clears).toHaveLength(1);
    expect(String(clears[0]![0])).toContain("/tabs/sess-2/clear/");
    expect(clears[0]![1]).toMatchObject({ method: "DELETE" });

    h.handles.actionCall.mockClear();
    h.sale.cart.items.push({ line_id: "L-1", sku: "PAO", name: "Pão", qty: 1, price_q: 500, notes: "" } as never);
    await h.sale.releaseAbandonedTab();
    expect(h.handles.actionCall.mock.calls.filter((call) => String(call[0]).includes("/clear/"))).toHaveLength(0);
  });

  it("voltar ao quadro também libera a encomenda vazia, e a venda esquece a comanda", async () => {
    const h = sale([tab("2", "empty")], opened);
    await h.sale.openNewOrder();
    await nextTick();
    h.sale.goToTabs();
    await vi.waitFor(() => expect(h.sale.cart.tabSessionKey).toBe(""));
    const clears = h.handles.actionCall.mock.calls.filter((call) => String(call[0]).includes("/clear/"));
    expect(clears).toHaveLength(1);
    expect(h.sale.inSaleView.value).toBe(false);
  });

  it("com o cliente já escolhido a encomenda não é abandonada", async () => {
    const h = sale([tab("2", "empty")], opened);
    await h.sale.openNewOrder();
    await nextTick();
    h.sale.cart.customerName = "Maria";
    await h.sale.releaseAbandonedTab();
    expect(h.handles.actionCall.mock.calls.filter((call) => String(call[0]).includes("/clear/"))).toHaveLength(0);
  });

  it("Nova encomenda pedida do quadro reaproveita a vazia E volta para a tela dela", async () => {
    const h = sale([tab("2", "empty")], opened);
    await h.sale.openNewOrder();
    await nextTick();
    h.sale.showTabs.value = true;
    await h.sale.openNewOrder();
    expect(h.sale.showTabs.value).toBe(false);
    expect(h.sale.inSaleView.value).toBe(true);
  });
});

// A CHEGADA AO ASSISTENTE (#2824). O `openNewOrder` diz se a encomenda abriu; quem
// mostra o assistente (a tela de venda) leva o foco à etapa da vez, "Identificar
// cliente". Antes ninguém levava: o diálogo "Iniciar nova encomenda?" devolvia o foco
// à busca do quadro de comandas, o quadro saía da tela, e o foco morria no `body`.
describe("Nova encomenda: o foco chega à etapa da vez", () => {
  const opened = { tab_ref: "2", tab_display: "2", session_key: "sess-2", tab_session_key: "sess-2" };

  it("o sim não devolve o foco ao quadro, que sai da tela: quem abre a encomenda o leva", async () => {
    const h = sale([tab("2", "empty")], opened);
    await h.sale.openNewOrder();
    expect(confirmNewOrder).toHaveBeenCalledWith(expect.objectContaining({ returnFocusOnConfirm: false }));
  });

  it("diz que abriu, e só quando abriu", async () => {
    const h = sale([tab("2", "empty")], opened);
    confirmNewOrder.mockResolvedValueOnce(false);
    await expect(h.sale.openNewOrder()).resolves.toBe(false);
    await expect(h.sale.openNewOrder()).resolves.toBe(true);
    await nextTick();
    expect(h.sale.orderSetupPending.value).toBe(true);
    // A encomenda vazia reaproveitada também chega ao assistente.
    h.sale.showTabs.value = true;
    await expect(h.sale.openNewOrder()).resolves.toBe(true);
  });

  it("a comanda que não abriu não diz que abriu", async () => {
    const h = sale([tab("2", "empty")], opened);
    h.handles.actionCall.mockRejectedValueOnce(new Error("offline"));
    await expect(h.sale.openNewOrder()).resolves.toBe(false);
  });

  it("a tela de venda leva o foco ao assistente depois de abrir, pelos dois caminhos", () => {
    const page = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../../app/pages/index.vue"), "utf8");
    const after = (name: string) => page.slice(page.indexOf(`async function ${name}()`), page.indexOf(`async function ${name}()`) + 400);
    // A Nova encomenda das Encomendas (`/?new=order`) e a da tela de resultado.
    expect(after("startNewOrder")).toContain("if (await openNewOrder()) focusOrderEntry();");
    expect(after("startNextOrder")).toContain("if (await openNewOrder()) focusOrderEntry();");
  });
});
