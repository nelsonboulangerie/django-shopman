import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h as render, nextTick } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosOrderEntry from "~/components/PosOrderEntry.vue";
import { makeSale } from "./_posSaleHarness";

vi.mock("vue-sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("vue-sonner")>()),
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

// O assistente ligado à REGRA DE VERDADE: o `issue` sai de `orderSetupIssue`
// com o carrinho mexido como a tela mexe. Nenhuma prontidão é escrita aqui;
// se o assistente acertar, é porque obedece à regra, não porque a copiou.
type Harness = ReturnType<typeof makeSale>;
let instances: Harness[] = [];
beforeEach(() => { vi.useFakeTimers(); instances = []; });
afterEach(() => {
  instances.forEach((x) => x.handles.dispose());
  vi.clearAllTimers();
  vi.useRealTimers();
});

async function mountWizard() {
  const sale = makeSale();
  instances.push(sale);
  sale.sale.setSalesMode("order");
  const { cart, orderSetupIssue } = sale.sale;
  const Host = defineComponent({
    setup: () => () => render(PosOrderEntry, {
      issue: orderSetupIssue.value,
      delivery: cart.fulfillmentConfirmed && cart.fulfillmentType === "delivery",
      customerName: cart.customerName,
      fulfillmentLabel: cart.fulfillmentType,
      scheduleLabel: cart.deliveryDate,
      scheduleWindow: cart.deliveryTimeSlot,
      loading: false,
    }),
  });
  const w = await mountSuspended(Host);
  const step = () => w.find("[aria-current='step']").attributes("aria-label");
  const settle = async () => { await nextTick(); await nextTick(); };
  return { cart, w, step, settle };
}

describe("assistente da encomenda × orderSetupIssue", () => {
  it("anda na ordem da regra e volta quando a regra volta", async () => {
    const { cart, step, settle } = await mountWizard();
    expect(step()).toBe("1. Cliente");
    cart.customerRef = "CUST-A";
    cart.customerName = "Ana";
    await settle();
    expect(step()).toBe("2. Recebimento");
    cart.fulfillmentType = "delivery";
    cart.fulfillmentConfirmed = true;
    await settle();
    expect(step()).toBe("3. Endereço");
    cart.deliveryAddress = "Rua A, 100";
    await settle();
    expect(step()).toBe("4. Data e horário");
    cart.deliveryDate = "2099-09-12";
    cart.deliveryTimeSlot = "10:00";
    await settle();
    expect(step()).toBe("4. Data e horário, pronta");

    // Entrega vira retirada: a etapa do endereço deixa de existir.
    cart.fulfillmentType = "pickup";
    await settle();
    expect(step()).toBe("3. Data e horário, pronta");

    // Retirada vira entrega de novo, sem endereço: volta ao endereço.
    cart.deliveryAddress = "";
    cart.fulfillmentType = "delivery";
    await settle();
    expect(step()).toBe("3. Endereço");
    cart.deliveryAddress = "Rua A, 100";
    await settle();

    // O dia apagado devolve a data como pendente.
    cart.deliveryDate = "";
    await settle();
    expect(step()).toBe("4. Data e horário");
    cart.deliveryDate = "2099-09-13";
    await settle();

    // Agendar exige cliente: sem ele, volta à etapa 1.
    cart.customerRef = "";
    await settle();
    expect(step()).toBe("1. Cliente");
  });
});
