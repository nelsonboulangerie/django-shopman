import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { workspaceProps } from "../support/paymentWorkspaceProps";

// ENCOMENDA PARA AMANHÃ não vai para a cozinha ao finalizar: o pedido espera a
// data combinada (`lifecycle._physical_work_deferred`). O pagamento dizia "Ao
// finalizar, o item vai para a cozinha." — promessa falsa ao operador.

const cash = { method: "cash", amount_q: 1000, collection: "terminal" as const };

function props(overrides: Record<string, unknown> = {}) {
  return workspaceProps({
    salesMode: "order",
    customerName: "Ana",
    customerPhone: "43999990001",
    paymentTenders: [cash],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentCovered: true,
    paymentRemainingQ: 0,
    scheduleToday: "2026-09-28",
    ...overrides,
  });
}

describe("PosPaymentWorkspace — a cozinha da encomenda", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("para amanhã: vai para a cozinha no dia da encomenda", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ deliveryDate: "2026-09-29", deliveryDateEffective: "2026-09-29" }),
    });
    const notices = wrapper.find('[aria-label="Avisos"]').text();
    expect(notices).toContain("O item vai para a cozinha no dia da encomenda.");
    expect(notices).not.toContain("Ao finalizar");
  });

  it("para hoje: vai ao finalizar", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ deliveryDate: "", deliveryDateEffective: "2026-09-28" }),
    });
    expect(wrapper.find('[aria-label="Avisos"]').text()).toContain("Ao finalizar, o item vai para a cozinha.");
  });
});
