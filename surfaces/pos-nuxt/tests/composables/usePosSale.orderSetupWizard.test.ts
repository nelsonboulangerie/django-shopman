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

// JORNADA J5 (WP-E10): a Caixa cria a encomenda de outro dia escolhendo Retirada e
// o dia NO PRÓPRIO CARTÃO, com o cartão ligado ao carrinho como a tela de venda o
// liga (`pickFulfillment` e `v-model:scheduleDate`). Nenhum diálogo no meio.
describe("jornada J5: retirada e dia escolhidos no cartão", () => {
  it("cliente, Retirada no cartão, Amanhã no cartão: a encomenda fica pronta para montar", async () => {
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
        fulfillmentOptions: [
          { ref: "pickup", label: "Retirada", description: "No balcão", requires_address: false },
          { ref: "delivery", label: "Entrega", description: "No endereço", requires_address: true },
        ],
        fulfillmentType: cart.fulfillmentType,
        fulfillmentConfirmed: cart.fulfillmentConfirmed,
        scheduleDate: cart.deliveryDate,
        scheduleTimeSlot: cart.deliveryTimeSlot,
        schedule: {
          today: "2099-09-10",
          availableDates: ["2099-09-10", "2099-09-11", "2099-09-12"],
          maxDate: "2099-10-10",
          windows: [],
          bottleneckName: "",
          readyAt: "",
          pending: false,
          failed: false,
        },
        onPickFulfillment: (type: "pickup" | "delivery") => {
          cart.fulfillmentType = type;
          cart.fulfillmentConfirmed = true;
        },
        "onUpdate:scheduleDate": (iso: string) => { cart.deliveryDate = iso; },
        "onUpdate:scheduleTimeSlot": (slot: string) => { cart.deliveryTimeSlot = slot; },
      }),
    });
    const w = await mountSuspended(Host);
    const settle = async () => { await nextTick(); await nextTick(); };
    const step = () => w.find("[aria-current='step']").attributes("aria-label");

    cart.customerRef = "CUST-A";
    cart.customerName = "Ana";
    await settle();
    expect(step()).toBe("2. Recebimento");

    await w.find("[data-order-fulfillment='pickup']").trigger("click");
    await settle();
    expect(cart.fulfillmentType).toBe("pickup");
    expect(cart.fulfillmentConfirmed).toBe(true);
    expect(step()).toBe("3. Data e horário");

    await w.find("[data-order-step='schedule'] [data-day-option='tomorrow']").trigger("click");
    await settle();
    expect(cart.deliveryDate).toBe("2099-09-11");
    expect(orderSetupIssue.value).toBe("");
    expect(step()).toBe("3. Data e horário, pronta");
    const montar = w.findAll("button").find((b) => b.text().includes("Montar encomenda"))!;
    expect(montar.attributes("disabled")).toBeUndefined();
    // Nenhum diálogo foi aberto para chegar aqui.
    expect(document.querySelector("[role='dialog']")).toBeNull();
  });
});
