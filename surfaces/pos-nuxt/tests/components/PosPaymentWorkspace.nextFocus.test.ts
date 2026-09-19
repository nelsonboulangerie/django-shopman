import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

// "Levar o foco ao campo que resolve" passa pelo mecanismo de próximo foco do
// kit (`useNextFocus().reveal`): a coluna de trabalho rola até o campo e o
// campo recebe o foco — o operador aperta F e já digita o CPF, em vez de os
// onze dígitos caírem no numpad. O `scrollIntoView` é a fronteira com o
// browser: espionado, não simulado.

type Montado = Awaited<ReturnType<typeof mountSuspended>>;
const exposto = (w: Montado) =>
  (w.vm as unknown as { $: { exposed: { toggleCpfOnInvoice: () => boolean } } }).$.exposed;

let scrolledSpy: ReturnType<typeof vi.fn>;
beforeEach(() => {
  scrolledSpy = vi.fn();
  Element.prototype.scrollIntoView = scrolledSpy as unknown as Element["scrollIntoView"];
});
afterEach(() => { document.body.innerHTML = ""; });

describe("PosPaymentWorkspace — o foco vai ao campo que resolve", () => {
  it("F liga o CPF na nota e o foco cai no campo assim que ele aparece", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, {
      attachTo: document.body,
      props: workspaceProps({
        checkoutContract: { capabilities: { supports_fiscal_document: true }, receipt_channels: [] },
        wantsCpfOnInvoice: false,
      }),
    });

    expect(exposto(w).toggleCpfOnInvoice()).toBe(true);
    expect(w.emitted("update:wantsCpfOnInvoice")?.[0]).toEqual([true]);
    // O shell grava a preferência e devolve a prop; o campo só existe depois.
    await w.setProps({ wantsCpfOnInvoice: true });

    await vi.waitFor(() => {
      const field = document.querySelector<HTMLElement>('[aria-label="CPF que sai na nota"]');
      expect(field).not.toBeNull();
      expect(document.activeElement).toBe(field);
    });
    expect(scrolledSpy).toHaveBeenCalledWith({ block: "center", behavior: expect.any(String) });
    // Input é focável por natureza: o mecanismo não o tira da ordem do Tab.
    expect(document.activeElement?.hasAttribute("tabindex")).toBe(false);
    w.unmount();
  });

  it("Trocar forma de pagamento (Pix acima do teto) leva o foco à primeira forma possível", async () => {
    const paymentConstraints = {
      pix: { provider: "efi", environment: "sandbox", mode: "provider_test", is_test: true, max_amount_q: 1000, max_amount_display: "R$ 10,00", message: "Pix de teste até R$ 10,00." },
    };
    const w = await mountSuspended(PosPaymentWorkspace, {
      attachTo: document.body,
      props: workspaceProps({
        paymentConstraints,
        review: review({ total_q: 1001, total_display: "R$ 10,01" }),
        paymentTotalQ: 1001,
        paymentTenders: [{ method: "pix", amount_q: 1001, collection: "terminal" as const }],
        selectedTenderIndex: 0,
        selectedTenderMethod: "pix",
        paymentCovered: true,
        paymentRemainingQ: 0,
      }),
    });

    const switchMethod = w.findAll("button").find((button) => button.text().includes("Trocar forma de pagamento"));
    await switchMethod!.trigger("click");
    expect(w.emitted("removeTender")?.[0]).toEqual([0]);
    // Enquanto o Pix de teste está na conta, as outras formas ficam bloqueadas;
    // o shell remove a linha e devolve as props, e só então há forma possível.
    // O reveal espera por ela (poucos quadros) em vez de desistir no ato.
    await w.setProps({
      paymentTenders: [],
      selectedTenderIndex: -1,
      selectedTenderMethod: "",
      paymentCovered: false,
      paymentRemainingQ: 1001,
    });

    await vi.waitFor(() => {
      expect(document.activeElement).toBe(document.querySelector('[data-payment-method="cash"]'));
    });
    expect(scrolledSpy).toHaveBeenCalled();
    w.unmount();
  });
});
