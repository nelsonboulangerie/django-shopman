import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  firstPendingStep,
  nextOrderSetupStep,
  orderSetupStepEnabled,
  orderSetupSteps,
} from "~/presentation/orderSetup";

const keys = (issue: Parameters<typeof orderSetupSteps>[0], delivery: boolean) =>
  orderSetupSteps(issue, delivery).map((s) => `${s.key}:${s.ready ? "pronta" : "pendente"}`);

describe("assistente da encomenda: etapas", () => {
  it("segue a ordem da regra: cliente, recebimento, endereço (só na entrega) e data", () => {
    expect(keys("customer", false)).toEqual(["customer:pendente", "fulfillment:pendente", "schedule:pendente"]);
    expect(keys("fulfillment", false)).toEqual(["customer:pronta", "fulfillment:pendente", "schedule:pendente"]);
    expect(keys("schedule", false)).toEqual(["customer:pronta", "fulfillment:pronta", "schedule:pendente"]);
    expect(keys("", false)).toEqual(["customer:pronta", "fulfillment:pronta", "schedule:pronta"]);
    expect(keys("address", true)).toEqual(["customer:pronta", "fulfillment:pronta", "address:pendente", "schedule:pendente"]);
    expect(keys("schedule", true)).toEqual(["customer:pronta", "fulfillment:pronta", "address:pronta", "schedule:pendente"]);
  });

  it("o endereço pendente aparece mesmo sem a dica de entrega: quem manda é o issue", () => {
    expect(keys("address", false)).toEqual(["customer:pronta", "fulfillment:pronta", "address:pendente", "schedule:pendente"]);
  });

  it("uma etapa só abre com todas as anteriores prontas", () => {
    const steps = orderSetupSteps("fulfillment", true);
    expect(steps.map((_, i) => orderSetupStepEnabled(steps, i))).toEqual([true, true, false, false]);
    const done = orderSetupSteps("", true);
    expect(done.map((_, i) => orderSetupStepEnabled(done, i))).toEqual([true, true, true, true]);
  });

  it("a vez é a primeira pendente; com tudo pronto, a última", () => {
    expect(firstPendingStep(orderSetupSteps("customer", false))).toBe("customer");
    expect(firstPendingStep(orderSetupSteps("address", true))).toBe("address");
    expect(firstPendingStep(orderSetupSteps("", false))).toBe("schedule");
  });
});

describe("assistente da encomenda: para onde ir quando a regra muda", () => {
  it("a etapa aberta ficou pronta: segue para a próxima pendente", () => {
    expect(nextOrderSetupStep({ steps: orderSetupSteps("fulfillment", false), current: "customer", wasReady: false })).toBe("fulfillment");
    // Escolheu entrega sem endereço: o assistente vai ao endereço, não à data.
    expect(nextOrderSetupStep({ steps: orderSetupSteps("address", true), current: "fulfillment", wasReady: false })).toBe("address");
  });

  it("uma anterior voltou a pendente (o cliente saiu): volta a ela", () => {
    expect(nextOrderSetupStep({ steps: orderSetupSteps("customer", false), current: "schedule", wasReady: true })).toBe("customer");
  });

  it("retirada virou entrega sem endereço: quem revia a data volta ao endereço", () => {
    expect(nextOrderSetupStep({ steps: orderSetupSteps("address", true), current: "schedule", wasReady: true })).toBe("address");
  });

  it("entrega virou retirada: a etapa do endereço some e o assistente não fica nela", () => {
    expect(nextOrderSetupStep({ steps: orderSetupSteps("", false), current: "address", wasReady: true })).toBe("schedule");
  });

  it("revendo uma etapa feita que continua feita, fica onde o operador está", () => {
    expect(nextOrderSetupStep({ steps: orderSetupSteps("", false), current: "customer", wasReady: true })).toBe("customer");
  });
});

describe("a prontidão tem um dono só", () => {
  // A regra mora em `orderSetupIssue` (usePosSale) e no servidor. Se o
  // assistente começar a ler o carrinho, a regra passa a existir duas vezes.
  const CART_FIELDS = /\b(cart|customerRef|fulfillmentConfirmed|deliveryAddress|deliveryDate|deliveryTimeSlot)\b/;
  const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  it("nem a apresentação nem o componente leem o carrinho", () => {
    expect(read("../app/presentation/orderSetup.ts")).not.toMatch(CART_FIELDS);
    expect(read("../app/components/PosOrderEntry.vue")).not.toMatch(CART_FIELDS);
  });

  it("o tipo do issue é o mesmo que `orderSetupIssue` devolve", () => {
    expect(read("../app/composables/usePosSale.ts")).toMatch(/const orderSetupIssue = computed<OrderSetupIssue>/);
  });
});
