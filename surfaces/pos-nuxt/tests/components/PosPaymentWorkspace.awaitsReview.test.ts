import { afterEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { toast } from "vue-sonner";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

vi.mock("vue-sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("vue-sonner")>()),
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

/**
 * A CORRIDA DO DESCONTO. Abrir o checkout ou mexer no desconto zera a revisão
 * antes de o servidor responder; nessa janela o total do pagamento é o
 * interino (a última revisão vencida, ou o líquido do carrinho), e o primeiro
 * lançamento nasce dimensionado por ele. Quando a revisão volta com o desconto,
 * ninguém redimensiona o que o operador já escolheu: a tela cobra o total
 * antigo.
 *
 * O "Validar" já se trava sozinho ("Calculando o total…"), por isso clicar nele não
 * reproduz nada. O teste clica na FORMA DE PAGAMENTO, que é por onde o valor
 * errado entra.
 */
describe("PosPaymentWorkspace: as formas de pagamento esperam a revisão", () => {
  type Montado = Awaited<ReturnType<typeof mountSuspended>>;
  afterEach(() => { vi.mocked(toast.info).mockClear(); });
  const exposto = (w: Montado) =>
    (w.vm as unknown as { $: { exposed: { pressMethodKey: (letter: string) => boolean } } }).$.exposed;

  // Janela da corrida: desconto pedido, revisão em trânsito, total interino
  // ainda sem o desconto (R$ 10,00 em vez de R$ 8,50).
  const janela = () => workspaceProps({ review: null, paymentTotalQ: 1000, paymentRemainingQ: 1000 });

  it("tocar numa forma durante a janela não lança nada", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: janela() });
    const dinheiro = w.find('[data-payment-method="cash"]');
    expect(dinheiro.exists()).toBe(true);
    expect(dinheiro.attributes("disabled")).toBeDefined();
    expect(dinheiro.attributes("title")).toBe("Calculando o total. A forma libera assim que ele chegar.");
    await dinheiro.trigger("click");
    expect(w.emitted("addTender")).toBeUndefined();
  });

  it("a tecla da forma também espera, e diz por quê", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: janela() });
    expect(exposto(w).pressMethodKey("R")).toBe(true);
    expect(w.emitted("addTender")).toBeUndefined();
    expect(toast.info).toHaveBeenCalledWith("Calculando o total. A forma libera assim que ele chegar.");
  });

  it("revisão que falhou: a forma aponta para o Tentar de novo", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: { ...janela(), reviewFailed: true } });
    const dinheiro = w.find('[data-payment-method="cash"]');
    expect(dinheiro.attributes("disabled")).toBeDefined();
    expect(dinheiro.attributes("title")).toBe("O total não foi calculado. Toque em Tentar de novo.");
  });

  it("a revisão chega com o desconto: a forma libera e lança", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: janela() });
    await w.setProps({ review: review({ total_q: 850, total_display: "R$ 8,50" }), paymentTotalQ: 850, paymentRemainingQ: 850 });
    const dinheiro = w.find('[data-payment-method="cash"]');
    expect(dinheiro.attributes("disabled")).toBeUndefined();
    await dinheiro.trigger("click");
    expect(w.emitted("addTender")).toEqual([["cash"]]);
  });
});
