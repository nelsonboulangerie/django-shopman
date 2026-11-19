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
      scheduleLabel: cart.deliveryDate,
      scheduleWindow: cart.deliveryTimeSlot,
      loading: false,
    }),
  });
  const w = await mountSuspended(Host);
  const step = () => w.find("[aria-current='step']").attributes("aria-label");
  const settle = async () => { await nextTick(); await nextTick(); };
  const next = async () => {
    await w.findAll("button").find((b) => b.text().includes("Continuar"))!.trigger("click");
    await settle();
  };
  return { cart, w, step, settle, next };
}

describe("assistente da encomenda × orderSetupIssue", () => {
  // A ordem do dono (19/11/2026, #2754): cliente, para quando, recebimento e,
  // na entrega, o endereço.
  it("anda na ordem da regra e volta quando a regra volta", async () => {
    const { cart, step, settle, next } = await mountWizard();
    expect(step()).toBe("1. Cliente");
    cart.customerRef = "CUST-A";
    cart.customerName = "Ana";
    await settle();
    expect(step()).toBe("2. Data e horário");
    // O dia deixa a data pronta, mas a etapa não anda sozinha: falta o horário.
    cart.deliveryDate = "2099-09-12";
    await settle();
    expect(step()).toBe("2. Data e horário, pronta");
    cart.deliveryTimeSlot = "10:00";
    await next();
    expect(step()).toBe("3. Recebimento");
    cart.fulfillmentType = "delivery";
    cart.fulfillmentConfirmed = true;
    await settle();
    expect(step()).toBe("4. Endereço");
    cart.deliveryAddress = "Rua A, 100";
    await settle();
    expect(step()).toBe("4. Endereço, pronta");

    // Entrega vira retirada: a etapa do endereço deixa de existir.
    cart.fulfillmentType = "pickup";
    await settle();
    expect(step()).toBe("3. Recebimento, pronta");

    // Retirada vira entrega de novo, sem endereço: vai ao endereço.
    cart.deliveryAddress = "";
    cart.fulfillmentType = "delivery";
    await settle();
    expect(step()).toBe("4. Endereço");
    cart.deliveryAddress = "Rua A, 100";
    await settle();

    // O dia apagado devolve a data como pendente, e ela vem antes do endereço.
    cart.deliveryDate = "";
    await settle();
    expect(step()).toBe("2. Data e horário");
    cart.deliveryDate = "2099-09-13";
    await settle();

    // Agendar exige cliente: sem ele, volta à etapa 1.
    cart.customerRef = "";
    await settle();
    expect(step()).toBe("1. Cliente");
  });
});

// JORNADA J5 (WP-E10, ordem do WP-E13): a Caixa cria a encomenda de outro dia
// escolhendo o dia e a Retirada NO PRÓPRIO CARTÃO, com o cartão ligado ao carrinho
// como a tela de venda o liga (`v-model:scheduleDate` e `pickFulfillment`). Nenhum
// diálogo no meio.
describe("jornada J5: dia e retirada escolhidos no cartão", () => {
  it("cliente, Amanhã no cartão, Retirada no cartão: a encomenda fica pronta para montar", async () => {
    const sale = makeSale();
    instances.push(sale);
    sale.sale.setSalesMode("order");
    const { cart, orderSetupIssue } = sale.sale;
    const Host = defineComponent({
      setup: () => () => render(PosOrderEntry, {
        issue: orderSetupIssue.value,
        delivery: cart.fulfillmentConfirmed && cart.fulfillmentType === "delivery",
        customerName: cart.customerName,
        scheduleLabel: cart.deliveryDate,
        scheduleWindow: cart.deliveryTimeSlot,
        loading: false,
        fulfillmentOptions: [
          { ref: "pickup", label: "Retirada", description: "No balcão", requires_address: false },
          { ref: "delivery", label: "Entrega", description: "No endereço", requires_address: true },
        ],
        chosenFulfillment: cart.fulfillmentConfirmed ? cart.fulfillmentType : "",
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
        onPickFulfillment: sale.sale.chooseFulfillment,
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
    expect(step()).toBe("2. Data e horário");

    await w.find("[data-order-step='schedule'] [data-day-option='tomorrow']").trigger("click");
    await settle();
    expect(cart.deliveryDate).toBe("2099-09-11");
    expect(orderSetupIssue.value).toBe("fulfillment");
    expect(step()).toBe("2. Data e horário, pronta");
    await w.findAll("button").find((b) => b.text().includes("Continuar"))!.trigger("click");
    await settle();
    expect(step()).toBe("3. Recebimento");

    await w.find("[data-order-fulfillment='pickup']").trigger("click");
    await settle();
    expect(cart.fulfillmentType).toBe("pickup");
    expect(cart.fulfillmentConfirmed).toBe(true);
    expect(orderSetupIssue.value).toBe("");
    expect(step()).toBe("3. Recebimento, pronta");
    const montar = w.findAll("button").find((b) => b.text().includes("Montar encomenda"))!;
    expect(montar.attributes("disabled")).toBeUndefined();
    // Nenhum diálogo foi aberto para chegar aqui.
    expect(document.querySelector("[role='dialog']")).toBeNull();
  });
});
