// O endereço da entrega no write-side (pedido do dono, 19/11/2026, #2754): ao
// escolher Entrega o padrão do cliente já vem; trocar de endereço substitui o
// anterior por inteiro; e dá para tirar o endereço DA ENTREGA sem tocar no
// cadastro do cliente.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { toast } from "vue-sonner";

import type { SavedAddressProjection } from "~/types/pos";
import { makeProjection, makeSale } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

function saved(id: number, extra: Partial<SavedAddressProjection> = {}): SavedAddressProjection {
  return {
    id,
    label: "Entrega",
    label_key: "other",
    label_custom: "Entrega",
    formatted_address: `Rua ${id}, ${id}00 - Centro - Londrina/PR`,
    route: `Rua ${id}`,
    street_number: `${id}00`,
    neighborhood: "Centro",
    city: "Londrina",
    state_code: "PR",
    postal_code: "86010-000",
    complement: "",
    delivery_instructions: "",
    is_default: id === 1,
    ...extra,
  };
}
const HOME = saved(1, { label: "Casa", label_key: "home", label_custom: "", complement: "apto 12", delivery_instructions: "Portaria" });
const OTHER = saved(2);

type Harness = ReturnType<typeof makeSale>;
let instances: Harness[] = [];

/** Encomenda com cliente e data: o que falta é o recebimento. */
function orderWaitingFulfillment(addresses: SavedAddressProjection[] = [HOME, OTHER]) {
  const h = makeSale();
  instances.push(h);
  const { sale } = h;
  sale.setSalesMode("order");
  sale.cart.customerRef = "CUST-A";
  sale.cart.customerName = "Ana";
  sale.cart.deliveryDate = "2099-09-12";
  sale.customerLookup.value = {
    ref: "CUST-A",
    name: "Ana",
    default_address: addresses[0] ?? null,
    saved_addresses: addresses,
  } as unknown as NonNullable<typeof sale.customerLookup.value>;
  return h;
}

/** O corpo do último salvamento da comanda (o que o servidor recebe). */
async function savedBody(addresses: SavedAddressProjection[], act: (sale: Harness["sale"]) => void) {
  const actionCall = vi.fn().mockResolvedValue({});
  const h = makeSale({
    actionCall,
    projection: makeProjection({ checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"] }),
  });
  instances.push(h);
  Object.assign(h.sale.cart, { tabRef: "M1", tabSessionKey: "sess-1", customerRef: "CUST-A", customerName: "Ana" });
  h.sale.customerLookup.value = {
    ref: "CUST-A", name: "Ana", default_address: addresses[0] ?? null, saved_addresses: addresses,
  } as unknown as NonNullable<typeof h.sale.customerLookup.value>;
  h.sale.setSalesMode("order");
  h.sale.cart.deliveryDate = "2099-09-12";
  act(h.sale);
  await h.sale.saveTab();
  const call = actionCall.mock.calls.find((c) => String(c[0]).includes("/tabs/save/"))!;
  return call[1]!.body as Record<string, any>;
}

beforeEach(() => { vi.useFakeTimers(); vi.mocked(toast.info).mockClear(); instances = []; });
afterEach(() => {
  instances.forEach((h) => h.handles.dispose());
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe("usePosSale: o endereço da entrega", () => {
  it("ao escolher Entrega, o endereço padrão do cliente já vem e a encomenda fica pronta", () => {
    const { sale } = orderWaitingFulfillment();
    expect(sale.orderSetupIssue.value).toBe("fulfillment");
    sale.chooseFulfillment("delivery");
    expect(sale.cart.fulfillmentType).toBe("delivery");
    expect(sale.cart.fulfillmentConfirmed).toBe(true);
    expect(sale.cart.deliveryAddress).toBe("Rua 1");
    expect(sale.cart.deliveryStreetNumber).toBe("100");
    expect(sale.cart.deliveryNeighborhood).toBe("Centro");
    expect(sale.cart.deliveryComplement).toBe("apto 12");
    expect(sale.cart.deliveryInstructions).toBe("Portaria");
    expect(sale.cart.deliveryAddressStructured.postal_code).toBe("86010-000");
    expect(sale.orderSetupIssue.value).toBe("");
  });

  it("cliente sem endereço cadastrado: Entrega pede o endereço, que é a última etapa", () => {
    const { sale } = orderWaitingFulfillment([]);
    sale.chooseFulfillment("delivery");
    expect(sale.cart.deliveryAddress).toBe("");
    expect(sale.orderSetupIssue.value).toBe("address");
  });

  it("Retirada não mexe em endereço nenhum", () => {
    const { sale } = orderWaitingFulfillment();
    sale.chooseFulfillment("pickup");
    expect(sale.cart.fulfillmentType).toBe("pickup");
    expect(sale.cart.deliveryAddress).toBe("");
    expect(sale.orderSetupIssue.value).toBe("");
  });

  it("escolher Entrega de novo não troca o endereço que o operador já pôs", () => {
    const { sale } = orderWaitingFulfillment();
    sale.chooseFulfillment("delivery");
    sale.applySavedAddress(OTHER);
    sale.chooseFulfillment("delivery");
    expect(sale.cart.deliveryAddress).toBe("Rua 2");
  });

  it("trocar de endereço substitui o anterior por inteiro: complemento e instruções não grudam", () => {
    const { sale } = orderWaitingFulfillment();
    sale.chooseFulfillment("delivery");
    sale.applySavedAddress(OTHER);
    expect(sale.cart.deliveryAddress).toBe("Rua 2");
    expect(sale.cart.deliveryStreetNumber).toBe("200");
    expect(sale.cart.deliveryComplement).toBe("");
    expect(sale.cart.deliveryInstructions).toBe("");
    expect(sale.cart.deliveryAddressStructured.complement).toBe("");
    expect(sale.cart.deliveryAddressStructured.delivery_instructions).toBe("");
  });

  it("tirar o endereço da entrega volta a 'sem endereço', não toca no cadastro e deixa desfazer", () => {
    const { sale } = orderWaitingFulfillment();
    sale.chooseFulfillment("delivery");
    expect(sale.canRestoreDeliveryAddress.value).toBe(false);
    sale.clearDeliveryAddress();
    expect(sale.cart.deliveryAddress).toBe("");
    expect(sale.cart.deliveryStreetNumber).toBe("");
    expect(sale.cart.deliveryNeighborhood).toBe("");
    expect(sale.cart.deliveryComplement).toBe("");
    expect(sale.cart.deliveryInstructions).toBe("");
    expect(sale.cart.deliveryAddressStructured).toEqual({});
    // A entrega continua sendo entrega: o funil volta a pedir o endereço.
    expect(sale.cart.fulfillmentType).toBe("delivery");
    expect(sale.orderSetupIssue.value).toBe("address");
    // O cadastro do cliente não foi tocado: os dois endereços seguem na lista.
    expect(sale.customerLookup.value?.saved_addresses).toEqual([HOME, OTHER]);

    // O Desfazer mora na tela (no assistente e no diálogo de Recebimento), não
    // num aviso passageiro: por cima de um diálogo o aviso não recebe toque.
    expect(toast.info).not.toHaveBeenCalled();
    expect(sale.canRestoreDeliveryAddress.value).toBe(true);
    sale.restoreDeliveryAddress();
    expect(sale.cart.deliveryAddress).toBe("Rua 1");
    expect(sale.cart.deliveryStreetNumber).toBe("100");
    expect(sale.cart.deliveryComplement).toBe("apto 12");
    expect(sale.cart.deliveryInstructions).toBe("Portaria");
    expect(sale.cart.deliveryAddressStructured.postal_code).toBe("86010-000");
    expect(sale.orderSetupIssue.value).toBe("");
    expect(sale.canRestoreDeliveryAddress.value).toBe(false);
  });

  it("o endereço digitado na hora também volta no Desfazer", () => {
    const { sale } = orderWaitingFulfillment([]);
    sale.chooseFulfillment("delivery");
    sale.cart.deliveryAddress = "Rua Nova";
    sale.cart.deliveryStreetNumber = "9";
    sale.cart.deliveryAddressStructured = { route: "Rua Nova", postal_code: "86015-000" };
    sale.clearDeliveryAddress();
    expect(sale.orderSetupIssue.value).toBe("address");
    sale.restoreDeliveryAddress();
    expect(sale.cart.deliveryAddress).toBe("Rua Nova");
    expect(sale.cart.deliveryStreetNumber).toBe("9");
    expect(sale.cart.deliveryAddressStructured.postal_code).toBe("86015-000");
  });

  it("o Desfazer não passa por cima de um endereço posto depois", async () => {
    const { sale } = orderWaitingFulfillment();
    sale.chooseFulfillment("delivery");
    sale.clearDeliveryAddress();
    sale.applySavedAddress(OTHER);
    expect(sale.canRestoreDeliveryAddress.value).toBe(false);
    sale.restoreDeliveryAddress();
    expect(sale.cart.deliveryAddress).toBe("Rua 2");
    // E o que saiu antes deixa de ser "o último": tirar o novo devolve o novo.
    await nextTick();
    sale.clearDeliveryAddress();
    sale.restoreDeliveryAddress();
    expect(sale.cart.deliveryAddress).toBe("Rua 2");
  });

  it("o Desfazer é da entrega: virou retirada, não há o que devolver", () => {
    const { sale } = orderWaitingFulfillment();
    sale.chooseFulfillment("delivery");
    sale.clearDeliveryAddress();
    sale.chooseFulfillment("pickup");
    expect(sale.canRestoreDeliveryAddress.value).toBe(false);
    sale.restoreDeliveryAddress();
    expect(sale.cart.deliveryAddress).toBe("");
  });

  // O servidor reconhece o endereço do cliente pela LINHA do cadastro. A linha
  // recomposta pelo PDV é escrita de outro jeito, e cada comanda salva gravava o
  // mesmo endereço de novo no cadastro, como "Casa" (medido na jornada J11).
  it("o endereço escolhido do cadastro viaja com a linha do cadastro, para não ser gravado de novo", async () => {
    const fromStore = saved(3, { formatted_address: "Rua 3, 300 - Centro, Londrina - PR, 86010-000" });
    const body = await savedBody([fromStore], (sale) => sale.chooseFulfillment("delivery"));
    expect(body.fulfillment_type).toBe("delivery");
    expect(body.delivery_address).toBe("Rua 3, 300 - Centro, Londrina - PR, 86010-000");
    expect(body.delivery_address_structured.formatted_address).toBe("Rua 3, 300 - Centro, Londrina - PR, 86010-000");
  });

  it("o operador corrigiu o número: já não é o endereço do cadastro, e a linha é recomposta", async () => {
    const fromStore = saved(3, { formatted_address: "Rua 3, 300 - Centro, Londrina - PR, 86010-000" });
    const body = await savedBody([fromStore], (sale) => {
      sale.chooseFulfillment("delivery");
      sale.cart.deliveryStreetNumber = "302";
    });
    expect(body.delivery_address).toBe("Rua 3, 302 - Centro - Londrina/PR");
  });

  it("endereço digitado na hora segue com a linha recomposta dos campos", async () => {
    const body = await savedBody([], (sale) => {
      sale.chooseFulfillment("delivery");
      sale.cart.deliveryAddress = "Rua Nova";
      sale.cart.deliveryStreetNumber = "9";
      sale.cart.deliveryNeighborhood = "Centro";
      sale.cart.deliveryAddressStructured = { city: "Londrina", state_code: "PR", postal_code: "86015-000" };
    });
    expect(body.delivery_address).toBe("Rua Nova, 9 - Centro - Londrina/PR");
  });

  it("sem endereço na entrega, tirar não faz nada", () => {
    const { sale } = orderWaitingFulfillment([]);
    sale.chooseFulfillment("delivery");
    sale.clearDeliveryAddress();
    expect(sale.canRestoreDeliveryAddress.value).toBe(false);
  });
});
