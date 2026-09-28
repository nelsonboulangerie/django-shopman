import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosFulfillmentModal from "~/components/PosFulfillmentModal.vue";

// A TAXA DE ENTREGA diz a verdade. Queixa do dono (28/09/2026): com o endereço
// salvo "Casa" escolhido no F7 da venda, o bloco mostrava "R$ 0,00" e "Preencha
// o endereço para a loja calcular a taxa." — as duas coisas falsas. A taxa é
// resolvida pela review, e a review só roda no pagamento; fora dele não há
// número nenhum, e a tela tem de dizer isso.

function props(overrides: Record<string, unknown> = {}) {
  return {
    open: true,
    fulfillmentOptions: [
      { ref: "pickup", label: "Retirada", description: "", requires_address: false },
      { ref: "delivery", label: "Entrega", description: "", requires_address: true },
    ],
    fulfillmentType: "delivery" as const,
    fulfillmentConfirmed: true,
    savedAddresses: [],
    addressAutocomplete: null,
    deliveryAddress: "Rua Pará",
    deliveryStreetNumber: "86",
    deliveryNeighborhood: "Centro",
    deliveryComplement: "",
    deliveryInstructions: "",
    scheduleLabel: "Hoje",
    deliveryFeeOverride: false,
    deliveryFeeOverrideInput: "",
    deliveryFeeQ: 0,
    deliveryFeeSource: "",
    deliveryDistanceKm: null,
    orderNotes: "",
    ...overrides,
  };
}

const feeBlock = () => {
  const label = [...document.body.querySelectorAll("span")].find((el) => el.textContent?.trim() === "Taxa de entrega");
  return label?.closest("div")?.parentElement?.textContent ?? "";
};

describe("PosFulfillmentModal — a taxa de entrega", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("fora do pagamento, com endereço: não finge R$ 0,00 nem pede o endereço", async () => {
    await mountSuspended(PosFulfillmentModal, { props: props({ deliveryFeeStatus: "at_payment" }) });
    const block = feeBlock();
    expect(block).toContain("A taxa deste endereço é calculada no pagamento.");
    expect(block).not.toMatch(/R\$\s0,00/);
    expect(block).not.toContain("Preencha o endereço");
  });

  it("sem endereço, pede o endereço", async () => {
    await mountSuspended(PosFulfillmentModal, {
      props: props({ deliveryAddress: "", deliveryNeighborhood: "", deliveryFeeStatus: "resolved" }),
    });
    expect(feeBlock()).toContain("Preencha o endereço para a loja calcular a taxa.");
  });

  it("a review respondeu sem zona nem distância: diz que não calculou, e oferece combinar", async () => {
    await mountSuspended(PosFulfillmentModal, { props: props({ deliveryFeeStatus: "resolved", deliveryFeeSource: "" }) });
    const block = feeBlock();
    expect(block).toContain("Não deu para calcular a taxa deste endereço.");
    expect(block).toContain("Combinar outro valor");
    expect(block).not.toMatch(/R\$\s0,00/);
  });

  it("taxa resolvida pela tabela: mostra o valor e de onde veio", async () => {
    await mountSuspended(PosFulfillmentModal, {
      props: props({ deliveryFeeStatus: "resolved", deliveryFeeSource: "zone", deliveryFeeQ: 800 }),
    });
    const block = feeBlock();
    expect(block).toMatch(/R\$\s8,00/);
    expect(block).toContain("Tabela do bairro/CEP deste endereço.");
  });
});
