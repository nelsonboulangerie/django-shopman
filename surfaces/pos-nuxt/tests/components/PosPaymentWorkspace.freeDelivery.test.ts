import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import PosFulfillmentModal from "~/components/PosFulfillmentModal.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

// FRETE GRÁTIS NO BALCÃO (P2-21): a promoção de frete da loja vale no PDV pelo
// mesmo motor, e o operador vê que o frete saiu grátis e por qual regra. Antes,
// a linha "Taxa de entrega" simplesmente sumia do resumo, e no Recebimento
// aparecia "R$ 0,00" sem explicação.

const waiver = { reason: "promotion" as const, promotion_name: "Frete de verão", threshold_q: 0, base_fee_q: 800 };
const nbsp = (text: string) => text.replace(/\u00a0/g, " ");

describe("PosPaymentWorkspace — frete grátis pela promoção", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("o resumo diz Grátis e o nome da promoção", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({
        fulfillmentType: "delivery",
        review: review({ delivery_fee_q: 0, delivery_fee_waiver: waiver }),
      }),
    });
    const row = wrapper.find("[data-pos-delivery-fee-row]");
    expect(row.exists()).toBe(true);
    expect(row.text()).toContain("Taxa de entrega");
    expect(row.text()).toContain("Grátis");
    expect(row.text()).toContain("Promoção Frete de verão");
  });

  it("sem renúncia e sem taxa, a linha não aparece (retirada)", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ review: review({ delivery_fee_q: 0, delivery_fee_waiver: null }) }),
    });
    expect(wrapper.find("[data-pos-delivery-fee-row]").exists()).toBe(false);
  });
});

describe("PosFulfillmentModal — frete grátis pela promoção", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  const props = (overrides: Record<string, unknown> = {}) => ({
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
    deliveryFeeSource: "zone",
    deliveryFeeStatus: "resolved" as const,
    deliveryFeeWaiver: waiver,
    deliveryDistanceKm: null,
    orderNotes: "",
    ...overrides,
  });

  it("a taxa diz Grátis e qual promoção a levou", async () => {
    await mountSuspended(PosFulfillmentModal, { props: props() });
    expect(document.body.querySelector("[data-pos-delivery-fee-amount]")?.textContent).toBe("Grátis");
    expect(nbsp(document.body.querySelector("[data-pos-delivery-fee-waiver]")?.textContent ?? "")).toBe(
      "Frete grátis pela promoção Frete de verão (a taxa seria R$ 8,00).",
    );
  });

  it("com a taxa combinada à mão, a promoção não aparece", async () => {
    await mountSuspended(PosFulfillmentModal, {
      props: props({ deliveryFeeOverride: true, deliveryFeeOverrideInput: "3,00", deliveryFeeSource: "manual" }),
    });
    expect(document.body.querySelector("[data-pos-delivery-fee-waiver]")).toBeNull();
  });
});
