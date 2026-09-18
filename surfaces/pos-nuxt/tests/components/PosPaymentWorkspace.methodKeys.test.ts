import { afterEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { toast } from "vue-sonner";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { workspaceProps } from "../support/paymentWorkspaceProps";

// `importOriginal` mantém o `Toaster` (o shell o monta); só o `toast` é espionado.
vi.mock("vue-sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("vue-sonner")>()),
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

/**
 * A tecla da forma BLOQUEADA calava: o operador apertava P com "Na entrega"
 * marcado, nada acontecia, e apertava de novo achando que a tecla quebrou. O
 * dedo no botão já ouvia o motivo (`addTender` no composable); a tecla ouve o
 * mesmo texto.
 */
describe("PosPaymentWorkspace — a tecla da forma bloqueada avisa", () => {
  type Montado = Awaited<ReturnType<typeof mountSuspended>>;
  afterEach(() => { vi.mocked(toast.info).mockClear(); });
  const exposto = (w: Montado) =>
    (w.vm as unknown as { $: { exposed: { pressMethodKey: (letter: string) => boolean } } }).$.exposed;

  it("P (Pix) com cobrança na entrega: toast com o motivo, sem lançar linha, tecla consumida", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ fulfillmentType: "delivery", paymentCollection: "on_delivery" }),
    });
    expect(exposto(w).pressMethodKey("P")).toBe(true);
    expect(w.emitted("addTender")).toBeUndefined();
    expect(toast.info).toHaveBeenCalledWith("Na entrega, use dinheiro ou cartão na maquininha. PIX Efí exige confirmação automática.");
  });

  it("na retirada (encomenda), a frase nomeia a retirada", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ salesMode: "order", fulfillmentType: "pickup", paymentCollection: "on_delivery" }),
    });
    expect(exposto(w).pressMethodKey("P")).toBe(true);
    expect(w.emitted("addTender")).toBeUndefined();
    expect(toast.info).toHaveBeenCalledWith("Na retirada, use dinheiro ou cartão na maquininha. PIX Efí exige confirmação automática.");
  });

  it("R (dinheiro) na entrega lança a linha sem aviso; no caixa, P lança o Pix", async () => {
    const naEntrega = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ fulfillmentType: "delivery", paymentCollection: "on_delivery" }),
    });
    expect(exposto(naEntrega).pressMethodKey("R")).toBe(true);
    expect(naEntrega.emitted("addTender")).toEqual([["cash"]]);
    expect(toast.info).not.toHaveBeenCalled();
    naEntrega.unmount();

    const noCaixa = await mountSuspended(PosPaymentWorkspace, { props: workspaceProps() });
    expect(exposto(noCaixa).pressMethodKey("P")).toBe(true);
    expect(noCaixa.emitted("addTender")).toEqual([["pix"]]);
    expect(toast.info).not.toHaveBeenCalled();
  });
});
