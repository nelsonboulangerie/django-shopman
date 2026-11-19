import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  ORDER_SETUP_ORDER,
  firstPendingStep,
  nextOrderSetupStep,
  orderSetupStepEnabled,
  orderSetupSteps,
} from "~/presentation/orderSetup";

const keys = (issue: Parameters<typeof orderSetupSteps>[0], delivery: boolean) =>
  orderSetupSteps(issue, delivery).map((s) => `${s.key}:${s.ready ? "pronta" : "pendente"}`);

describe("assistente da encomenda: etapas", () => {
  // A ordem do dono (19/11/2026, #2754): "pra quando" vem em SEGUNDO, logo depois
  // do cliente, porque diz respeito à disponibilidade.
  it("segue a ordem da regra: cliente, data, recebimento e endereço (só na entrega)", () => {
    expect(ORDER_SETUP_ORDER).toEqual(["customer", "schedule", "fulfillment", "address"]);
    expect(keys("customer", false)).toEqual(["customer:pendente", "schedule:pendente", "fulfillment:pendente"]);
    expect(keys("schedule", false)).toEqual(["customer:pronta", "schedule:pendente", "fulfillment:pendente"]);
    expect(keys("fulfillment", false)).toEqual(["customer:pronta", "schedule:pronta", "fulfillment:pendente"]);
    expect(keys("", false)).toEqual(["customer:pronta", "schedule:pronta", "fulfillment:pronta"]);
    expect(keys("address", true)).toEqual(["customer:pronta", "schedule:pronta", "fulfillment:pronta", "address:pendente"]);
    expect(keys("", true)).toEqual(["customer:pronta", "schedule:pronta", "fulfillment:pronta", "address:pronta"]);
  });

  it("o endereço pendente aparece mesmo sem a dica de entrega: quem manda é o issue", () => {
    expect(keys("address", false)).toEqual(["customer:pronta", "schedule:pronta", "fulfillment:pronta", "address:pendente"]);
  });

  it("uma etapa só abre com todas as anteriores prontas", () => {
    const steps = orderSetupSteps("schedule", true);
    expect(steps.map((_, i) => orderSetupStepEnabled(steps, i))).toEqual([true, true, false, false]);
    const done = orderSetupSteps("", true);
    expect(done.map((_, i) => orderSetupStepEnabled(done, i))).toEqual([true, true, true, true]);
  });

  it("a vez é a primeira pendente; com tudo pronto, a última", () => {
    expect(firstPendingStep(orderSetupSteps("customer", false))).toBe("customer");
    expect(firstPendingStep(orderSetupSteps("address", true))).toBe("address");
    expect(firstPendingStep(orderSetupSteps("", false))).toBe("fulfillment");
    expect(firstPendingStep(orderSetupSteps("", true))).toBe("address");
  });
});

describe("assistente da encomenda: para onde ir quando a regra muda", () => {
  it("a etapa aberta ficou pronta: segue para a próxima pendente", () => {
    // Identificou o cliente: a pergunta seguinte é "para quando".
    expect(nextOrderSetupStep({ steps: orderSetupSteps("schedule", false), current: "customer", wasReady: false })).toBe("schedule");
    // Escolheu entrega sem endereço: o assistente vai ao endereço.
    expect(nextOrderSetupStep({ steps: orderSetupSteps("address", true), current: "fulfillment", wasReady: false })).toBe("address");
    // Escolheu retirada: é a última etapa, e o assistente fica nela para montar.
    expect(nextOrderSetupStep({ steps: orderSetupSteps("", false), current: "fulfillment", wasReady: false })).toBe("fulfillment");
  });

  it("a data NÃO anda sozinha: escolhido o dia, a etapa ainda pergunta o horário", () => {
    expect(nextOrderSetupStep({ steps: orderSetupSteps("fulfillment", false), current: "schedule", wasReady: false })).toBe("schedule");
  });

  it("uma anterior voltou a pendente (o cliente saiu): volta a ela", () => {
    expect(nextOrderSetupStep({ steps: orderSetupSteps("customer", false), current: "fulfillment", wasReady: true })).toBe("customer");
    // O dia apagado devolve a data a quem já estava no recebimento.
    expect(nextOrderSetupStep({ steps: orderSetupSteps("schedule", false), current: "fulfillment", wasReady: true })).toBe("schedule");
  });

  it("o endereço saiu da entrega: quem estava nele continua nele, agora pendente", () => {
    expect(nextOrderSetupStep({ steps: orderSetupSteps("address", true), current: "address", wasReady: true })).toBe("address");
  });

  it("entrega virou retirada: a etapa do endereço some e o assistente não fica nela", () => {
    expect(nextOrderSetupStep({ steps: orderSetupSteps("", false), current: "address", wasReady: true })).toBe("fulfillment");
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
