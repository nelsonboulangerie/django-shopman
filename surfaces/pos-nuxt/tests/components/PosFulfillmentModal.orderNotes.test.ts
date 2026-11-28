import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosFulfillmentModal from "~/components/PosFulfillmentModal.vue";

// Beta test de 05/11/2026 (PDV2-08): a observação era cortada em silêncio no
// servidor. O campo para no mesmo limite e diz quanto já foi.
function props(orderNotes: string) {
  return {
    open: true,
    fulfillmentOptions: [{ ref: "pickup", label: "Retirada", description: "", requires_address: false }],
    fulfillmentType: "pickup" as const,
    fulfillmentConfirmed: true,
    savedAddresses: [],
    addressAutocomplete: null,
    deliveryAddress: "",
    deliveryStreetNumber: "",
    deliveryNeighborhood: "",
    deliveryComplement: "",
    deliveryInstructions: "",
    scheduleLabel: "Hoje",
    deliveryFeeOverride: false,
    deliveryFeeOverrideInput: "",
    deliveryFeeQ: 0,
    deliveryFeeSource: "",
    deliveryDistanceKm: null,
    orderNotes,
  };
}

describe("PosFulfillmentModal — observação do pedido", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("o campo para no limite do servidor e conta os caracteres", async () => {
    await mountSuspended(PosFulfillmentModal, { props: props("Sem cebola") });
    const textarea = document.body.querySelector("[data-pos-order-notes]") as HTMLTextAreaElement | null;
    const field = textarea?.tagName === "TEXTAREA" ? textarea : textarea?.querySelector("textarea");
    expect(field?.getAttribute("maxlength")).toBe("500");
    expect(document.body.querySelector("[data-pos-order-notes-count]")?.textContent).toBe("10/500");
  });
});
