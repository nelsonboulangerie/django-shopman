// O endereço da entrega no write-side (pedido do dono, 19/11/2026, #2754): ao
// escolher Entrega o padrão do cliente já vem; trocar de endereço substitui o
// anterior por inteiro; e dá para tirar o endereço DA ENTREGA sem tocar no
// cadastro do cliente.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";

import type { SavedAddressProjection } from "~/types/pos";
import { makeSale } from "./_posSaleHarness";

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

  it("tirar o endereço da entrega volta a 'sem endereço', avisa que o cadastro não mudou e deixa desfazer", () => {
    const { sale } = orderWaitingFulfillment();
    sale.chooseFulfillment("delivery");
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

    const [message, options] = vi.mocked(toast.info).mock.calls.at(-1) as unknown as
      [string, { description: string; action: { label: string; onClick: () => void } }];
    expect(message).toBe("Endereço tirado desta entrega.");
    expect(options.description).toBe("O cadastro do cliente não mudou.");
    expect(options.action.label).toBe("Desfazer");
    options.action.onClick();
    expect(sale.cart.deliveryAddress).toBe("Rua 1");
    expect(sale.cart.deliveryComplement).toBe("apto 12");
    expect(sale.cart.deliveryAddressStructured.postal_code).toBe("86010-000");
    expect(sale.orderSetupIssue.value).toBe("");
  });

  it("o Desfazer não passa por cima de um endereço posto depois", () => {
    const { sale } = orderWaitingFulfillment();
    sale.chooseFulfillment("delivery");
    sale.clearDeliveryAddress();
    const [, options] = vi.mocked(toast.info).mock.calls.at(-1) as unknown as [string, { action: { onClick: () => void } }];
    sale.applySavedAddress(OTHER);
    options.action.onClick();
    expect(sale.cart.deliveryAddress).toBe("Rua 2");
  });

  it("sem endereço na entrega, tirar não faz nada nem avisa", () => {
    const { sale } = orderWaitingFulfillment([]);
    sale.chooseFulfillment("delivery");
    sale.clearDeliveryAddress();
    expect(toast.info).not.toHaveBeenCalled();
  });
});
