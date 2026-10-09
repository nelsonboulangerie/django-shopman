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
 * O "Exato" na mesma corrida das formas de pagamento. A linha já existe
 * (R$ 10,00 em dinheiro, lançada com a revisão anterior); o operador muda o
 * desconto DENTRO do checkout, a revisão zera, e o total da tela volta a ser o
 * interino. Tocar "Exato" (ou "=") nessa janela faria a linha assumir o total
 * antigo, e a revisão que chega com o desconto não a redimensiona. O Exato
 * espera a revisão, pela mesma regra das formas.
 */
describe("PosPaymentWorkspace: o Exato espera a revisão", () => {
  type Montado = Awaited<ReturnType<typeof mountSuspended>>;
  afterEach(() => { vi.mocked(toast.info).mockClear(); });
  const exposto = (w: Montado) =>
    (w.vm as unknown as { $: { exposed: { pressExact: () => boolean } } }).$.exposed;
  const exato = (w: Montado) => w.find('[aria-label="Exato: a linha assume o restante"]');

  // Linha lançada antes, desconto alterado no checkout, revisão em trânsito.
  const janela = () => workspaceProps({
    review: null,
    paymentTenders: [{ method: "cash", amount_q: 1000, collection: "terminal" }],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentTotalQ: 1000,
    paymentRemainingQ: 0,
    paymentCovered: true,
  });

  it("tocar Exato durante a janela não ajusta a linha", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: janela() });
    expect(exato(w).exists()).toBe(true);
    expect(exato(w).attributes("disabled")).toBeDefined();
    expect(exato(w).attributes("title")).toBe("Calculando o total. A forma libera assim que ele chegar.");
    await exato(w).trigger("click");
    expect(w.emitted("tenderExact")).toBeUndefined();
  });

  it("a tecla = também espera, e diz por quê", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: janela() });
    expect(exposto(w).pressExact()).toBe(true);
    expect(w.emitted("tenderExact")).toBeUndefined();
    expect(toast.info).toHaveBeenCalledWith("Calculando o total. A forma libera assim que ele chegar.");
  });

  it("a revisão chega com o desconto: o Exato libera e ajusta", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: janela() });
    await w.setProps({ review: review({ total_q: 850, total_display: "R$ 8,50" }), paymentTotalQ: 850, paymentChangeQ: 150 });
    expect(exato(w).attributes("disabled")).toBeUndefined();
    await exato(w).trigger("click");
    expect(w.emitted("tenderExact")).toEqual([[]]);
    expect(exposto(w).pressExact()).toBe(true);
    expect(w.emitted("tenderExact")).toEqual([[], []]);
  });
});
