import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import type { POSTabProjection } from "~/types/pos";

import { makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

// "Nova venda" (WP-E8, P2-3; D5 do dono): da tela de resultado direto para a GRADE
// da próxima comanda livre, sem passar pelo quadro. A comanda que ela abriu sozinha,
// se o operador sair sem lançar nada, volta a ser livre: o quadro não enche de
// comandas vazias (PDV2-13). Quem escolhe e reserva a comanda é o servidor
// (`tabs/next-free/`, #2443): duas estações nunca abrem a mesma. E toda comanda que
// ESTA estação pôs em uso (o abrir respondeu `created`), vazia, volta a ser livre.

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

const opened = { tab_ref: "2", tab_display: "2", session_key: "sess-2", tab_session_key: "sess-2", created: true };
const clears = (h: ReturnType<typeof makeSale>) =>
  h.handles.actionCall.mock.calls.filter((call) => String(call[0]).includes("/clear/"));

describe("usePosSale.openNextSale", () => {
  it("abre a próxima comanda livre, no balcão, e a venda fica na grade", async () => {
    const h = sale([tab("1", "in_use"), tab("2", "empty")], opened);

    expect(await h.sale.openNextSale()).toBe(true);

    expect(String(h.handles.actionCall.mock.calls[0]![0])).toContain("/tabs/next-free/");
    // A reserva leva a chave da tentativa: repetida, devolve a mesma comanda.
    expect(h.handles.actionCall.mock.calls[0]![1]).toMatchObject({ body: { client_request_id: expect.any(String) } });
    expect(h.sale.cart.tabRef).toBe("2");
    expect(h.sale.cart.salesMode).toBe("counter");
    expect(h.sale.inSaleView.value).toBe(true);
  });

  it("o servidor reservou outra que a do quadro (outra estação levou a 2): abre a dele", async () => {
    const h = sale([tab("2", "empty")], { ...opened, tab_ref: "3", tab_display: "3", session_key: "sess-3", tab_session_key: "sess-3" });

    expect(await h.sale.openNextSale()).toBe(true);

    expect(h.sale.cart.tabRef).toBe("3");
  });

  it("se a comanda não abre, responde não, e quem chama mostra o quadro", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("falhou"));
    const h = makeSale({ tabs: [tab("2", "empty")], actionCall });
    instances.push(h);

    expect(await h.sale.openNextSale()).toBe(false);
    expect(h.sale.cart.tabSessionKey).toBe("");
  });

  it("voltar ao quadro sem lançar nada libera a comanda que ela abriu", async () => {
    const h = sale([tab("2", "empty")], opened);
    await h.sale.openNextSale();
    await nextTick();

    h.sale.goToTabs();

    await vi.waitFor(() => expect(h.sale.cart.tabSessionKey).toBe(""));
    expect(clears(h)).toHaveLength(1);
    expect(String(clears(h)[0]![0])).toContain("/tabs/sess-2/clear/");
  });

  it("com item lançado, ou cliente escolhido, a comanda fica", async () => {
    const h = sale([tab("2", "empty")], opened);
    await h.sale.openNextSale();
    await nextTick();
    h.sale.cart.items.push({ line_id: "L-1", sku: "PAO", name: "Pão", qty: 1, price_q: 500, notes: "" } as never);
    await h.sale.releaseAbandonedTab();
    expect(clears(h)).toHaveLength(0);

    h.sale.cart.items.splice(0);
    h.sale.cart.customerName = "Maria";
    await h.sale.releaseAbandonedTab();
    expect(clears(h)).toHaveLength(0);
  });

  it("a comanda livre que o operador abriu pelo quadro, vazia, também volta a ser livre", async () => {
    const h = sale([tab("2", "empty")], opened);
    await h.sale.openTab("2");
    await nextTick();

    await h.sale.releaseAbandonedTab();

    expect(clears(h)).toHaveLength(1);
  });

  it("a comanda que já estava em uso quando ele a abriu é de quem a abriu: vazia, ela fica", async () => {
    const h = sale([tab("2", "in_use")], { ...opened, created: false });
    await h.sale.openTab("2");
    await nextTick();

    await h.sale.releaseAbandonedTab();

    expect(clears(h)).toHaveLength(0);
  });

  it("a Próxima livre do quadro pede a reserva ao servidor", async () => {
    const h = sale([tab("1", "in_use"), tab("2", "empty")], opened);

    await h.sale.openNextFreeTab();

    expect(String(h.handles.actionCall.mock.calls[0]![0])).toContain("/tabs/next-free/");
    expect(h.sale.cart.tabRef).toBe("2");
  });
});
