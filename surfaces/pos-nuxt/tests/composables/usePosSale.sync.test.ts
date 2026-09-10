import { describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { makeSale, makeTabPayload, makeProjection } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
const tick = async () => { await nextTick(); await new Promise(resolve => setTimeout(resolve, 0)); };

describe("comanda compartilhada", () => {
  it("atualiza uma tela sem edição local pelo fetch canônico", async () => {
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload({ revision: "v1:new", items: [
      { line_id: "L-shared", sku: "PAO", name: "Pão", qty: 3, price_q: 500, notes: "", authorship: { updated_by: "ana" } },
    ] }));
    const h = makeSale({ actionCall });
    Object.assign(h.sale.cart, { tabRef: "M1", tabSessionKey: "sess-1", expectedRevision: "v1:old" });
    await tick();
    h.sale.unsaved.value = false;
    h.handles.posValue.value = makeProjection();
    await tick();
    expect(actionCall.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(h.sale.cart.items[0]?.qty).toBe(3);
    expect(h.sale.cart.expectedRevision).toBe("v1:new");
    expect(h.sale.tabConflict.value).toBeNull();
    h.handles.dispose();
  });

  it("preserva a edição local e só a substitui após escolha explícita", async () => {
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload({ revision: "v1:new", items: [
      { line_id: "L-shared", sku: "PAO", name: "Pão", qty: 3, price_q: 500, notes: "" },
    ] }));
    const h = makeSale({ actionCall });
    Object.assign(h.sale.cart, { tabRef: "M1", tabSessionKey: "sess-1", expectedRevision: "v1:old", items: [
      { line_id: "L-shared", sku: "PAO", name: "Pão", qty: 2, price_q: 500, notes: "" },
    ] });
    await tick();
    h.sale.unsaved.value = true;
    h.handles.posValue.value = makeProjection();
    await tick();
    expect(h.sale.cart.items[0]?.qty).toBe(2);
    expect(h.sale.tabConflict.value?.items[0]?.qty).toBe(3);
    h.sale.adoptCurrentTab();
    expect(h.sale.cart.items[0]?.qty).toBe(3);
    expect(h.sale.cart.expectedRevision).toBe("v1:new");
    h.handles.dispose();
  });
});
