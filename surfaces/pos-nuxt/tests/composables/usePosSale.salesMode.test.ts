import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { makeProjection, makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

type Harness = ReturnType<typeof makeSale>;
let instances: Harness[] = [];

function createSale(actionCall = vi.fn().mockImplementation(async (path: string) => {
  if (path.includes("/sale/review/")) return { review: { total_q: 500, subtotal_q: 500, total_display: "R$ 5,00" } };
  if (path.includes("/sale/close/")) return { ok: true, order_ref: "PED-MODE", payment: null };
  return {};
})) {
  const h = makeSale({
    actionCall,
    projection: makeProjection({ checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"] }),
  });
  instances.push(h);
  return h;
}

function identifyAndSchedule(h: Harness) {
  h.sale.cart.customerRef = "CUST-A";
  h.sale.cart.customerName = "Ana";
  h.sale.cart.fulfillmentType = "pickup";
  h.sale.cart.fulfillmentConfirmed = true;
  h.sale.cart.deliveryDate = "2026-09-12";
}

beforeEach(() => { vi.useFakeTimers(); instances = []; });
afterEach(() => {
  instances.forEach((h) => h.handles.dispose());
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe("usePosSale — balcão e encomenda", () => {
  it("balcão permite item e checkout sem cadastrar cliente nem informar data", async () => {
    const h = createSale();
    expect(h.sale.cart.salesMode).toBe("counter");
    expect(h.sale.orderSetupPending.value).toBe(false);
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    await nextTick();
    await h.sale.prepareCheckout();
    expect(h.sale.cart.items).toHaveLength(1);
    expect(h.sale.checkoutMode.value).toBe(true);
    expect(h.sale.cart.customerRef).toBe("");
    expect(h.sale.cart.deliveryDate).toBe("");
    expect(h.handles.actionCall.mock.calls.some(([path]) => String(path).includes("/sale/review/"))).toBe(true);
  });

  it("encomenda só libera itens após cliente selecionado, recebimento, data e conclusão", async () => {
    const h = createSale();
    const product = h.handles.posValue.value!.products[0]!;
    h.sale.setSalesMode("order");
    const blocked = async () => {
      h.sale.completeOrderSetup();
      h.sale.addProduct(product);
      await h.sale.prepareCheckout();
      expect(h.sale.cart.items).toHaveLength(0);
      expect(h.sale.checkoutMode.value).toBe(false);
      expect(h.handles.actionCall).not.toHaveBeenCalled();
    };
    h.sale.cart.customerName = "Ana digitada";
    h.sale.cart.customerPhone = "43999990022";
    expect(h.sale.orderSetupIssue.value).toBe("customer");
    await blocked();
    h.sale.cart.customerRef = "CUST-A";
    expect(h.sale.orderSetupIssue.value).toBe("fulfillment");
    await blocked();
    h.sale.cart.fulfillmentConfirmed = true;
    expect(h.sale.orderSetupIssue.value).toBe("schedule");
    await blocked();
    h.sale.cart.deliveryDate = "2026-09-12";
    expect(h.sale.orderSetupIssue.value).toBe("");
    h.sale.addProduct(product);
    expect(h.sale.cart.items).toHaveLength(0);
    h.sale.completeOrderSetup();
    h.sale.addProduct(product);
    await nextTick();
    await h.sale.prepareCheckout();
    expect(h.sale.cart.items).toHaveLength(1);
    expect(h.sale.checkoutMode.value).toBe(true);
  });

  it("entrega também exige endereço antes de concluir os dados", () => {
    const h = createSale();
    h.sale.setSalesMode("order");
    identifyAndSchedule(h);
    h.sale.cart.fulfillmentType = "delivery";
    h.sale.completeOrderSetup();
    expect(h.sale.orderSetupIssue.value).toBe("address");
    expect(h.sale.orderSetupPending.value).toBe(true);
    h.sale.cart.deliveryAddress = "Rua A, 100";
    h.sale.completeOrderSetup();
    expect(h.sale.orderSetupPending.value).toBe(false);
  });

  it("trocar modo preserva itens e cliente, bloqueia checkout incompleto e limpa entrega ao voltar", async () => {
    const h = createSale();
    h.sale.cart.customerRef = "CUST-A";
    h.sale.cart.customerName = "Ana";
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    const line = { ...h.sale.cart.items[0]! };
    h.sale.setSalesMode("order");
    await h.sale.prepareCheckout();
    expect(h.sale.checkoutMode.value).toBe(false);
    expect(h.sale.cart.items).toEqual([line]);
    expect(h.sale.cart.customerRef).toBe("CUST-A");
    h.sale.cart.deliveryDate = "2026-09-12";
    h.sale.cart.deliveryTimeSlot = "15:00";
    h.sale.cart.fulfillmentType = "delivery";
    h.sale.cart.deliveryAddress = "Rua A, 100";
    h.sale.cart.paymentCollection = "on_delivery";
    h.sale.cart.changeForInput = "100,00";
    h.sale.setSalesMode("counter");
    expect(h.sale.cart.items).toEqual([line]);
    expect(h.sale.cart.customerName).toBe("Ana");
    expect(h.sale.cart.customerRef).toBe("CUST-A");
    expect(h.sale.cart.fulfillmentType).toBe("pickup");
    expect(h.sale.cart.fulfillmentConfirmed).toBe(true);
    expect(h.sale.cart.deliveryDate).toBe("");
    expect(h.sale.cart.deliveryTimeSlot).toBe("");
    expect(h.sale.cart.deliveryAddress).toBe("");
    expect(h.sale.cart.paymentCollection).toBe("terminal");
    expect(h.sale.cart.changeForInput).toBe("");
  });

  it("resultado preserva modo encomenda depois de limpar carrinho para balcão", async () => {
    const h = createSale();
    h.sale.setSalesMode("order");
    identifyAndSchedule(h);
    h.sale.completeOrderSetup();
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    await nextTick();
    await h.sale.prepareCheckout();
    await h.sale.submitSale();
    expect(h.sale.result.value?.salesMode).toBe("order");
    expect(h.sale.result.value?.receipt.customerName).toBe("Ana");
    expect(h.sale.cart.salesMode).toBe("counter");
    expect(h.sale.cart.items).toHaveLength(0);
  });

  it.each(["order", undefined])("reabrir comanda recompõe encomenda por modo %s ou fatos salvos", async (mode) => {
    const payload = makeTabPayload({
      sales_mode: mode,
      customer_ref: "CUST-A", customer_name: "Ana",
      fulfillment_type: "delivery", delivery_date: "2026-09-12", delivery_address: "Rua A, 100",
      items: [{ line_id: "L1", sku: "PAO", name: "Pão", qty: 1, price_q: 500, notes: "" }],
    });
    const h = createSale(vi.fn().mockResolvedValue(payload));
    // Memória já carregada: o teste cobre os fatos da comanda, sem outro transporte.
    h.sale.customerLookup.value = { ref: "CUST-A" } as never;
    await h.sale.openTab("M1", { drawerChecked: true });
    expect(h.sale.cart.salesMode).toBe("order");
    expect(h.sale.cart.customerRef).toBe("CUST-A");
    expect(h.sale.cart.deliveryDate).toBe("2026-09-12");
    expect(h.sale.cart.fulfillmentType).toBe("delivery");
    expect(h.sale.orderSetupPending.value).toBe(false);
    expect(h.sale.cart.items).toHaveLength(1);
  });

  it("corrigir duplicidade mantém todos os dados do cadastro em rascunho", async () => {
    const h = createSale();
    const draft = { customerName: "Outra Pessoa", customerPhone: "43999990022", customerTaxId: "52998224725", customerEmail: "nova@example.com" };
    Object.assign(h.sale.cart, draft);
    h.sale.customerDecision.value = {
      kind: "existing_customer", field: "phone", typed: draft.customerPhone, current: null,
      other: { ref: "CUST-B", name: "Bruno", value: draft.customerPhone },
    };
    await h.sale.cancelCustomerDecision();
    expect(h.sale.customerDecision.value).toBeNull();
    expect(h.sale.cart).toMatchObject(draft);
    expect(h.sale.cart.customerRef).toBe("");
    expect(h.handles.actionCall).not.toHaveBeenCalled();
  });
});
