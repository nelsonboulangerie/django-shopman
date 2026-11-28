import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { isImplausibleChange } from "~/presentation/payment";
import { formatBRL } from "~/utils/posIntent";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

/**
 * Beta 07/11: "recebido R$ 10.000,00" numa venda de R$ 48,60 validou direto e
 * mandou dar R$ 9.951,40 de troco. Troco a partir de R$ 200 (a maior cédula)
 * pede uma conferência; a conta certa passa com um toque.
 */
describe("PosPaymentWorkspace: troco implausível pede conferência", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  const props = (changeQ: number) => workspaceProps({
    review: review(),
    paymentTenders: [{ method: "cash", amount_q: 4860 + changeQ, collection: "terminal" }],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentTotalQ: 4860,
    paymentRemainingQ: 0,
    paymentChangeQ: changeQ,
    paymentCovered: true,
  });
  const validar = (w: Awaited<ReturnType<typeof mountSuspended>>) =>
    (w.vm as unknown as { $: { exposed: { validate: () => void } } }).$.exposed.validate();

  it("R$ 199,99 de troco é normal; R$ 200,00 já é conferência", () => {
    expect(isImplausibleChange(19999)).toBe(false);
    expect(isImplausibleChange(20000)).toBe(true);
  });

  it("troco normal valida direto", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: props(140) });
    validar(w);
    await w.vm.$nextTick();
    expect(w.emitted("submit")).toHaveLength(1);
  });

  it("troco grande segura o Validar com o valor e o toque que confirma", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: props(995140) });
    expect(w.text()).toContain(`Troco de ${formatBRL(995140)}.`);
    validar(w);
    await w.vm.$nextTick();
    expect(w.emitted("submit")).toBeUndefined();

    const confirm = w.findAll("button").find((b) => b.text().trim() === "O troco está certo");
    expect(confirm).toBeTruthy();
    await confirm!.trigger("click");
    validar(w);
    await w.vm.$nextTick();
    expect(w.emitted("submit")).toHaveLength(1);
  });

  it("mudar o recebido depois de confirmar pede a conferência de novo", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: props(995140) });
    await w.findAll("button").find((b) => b.text().trim() === "O troco está certo")!.trigger("click");
    await w.setProps(props(95140));
    expect(w.text()).toContain(`Troco de ${formatBRL(95140)}.`);
    validar(w);
    await w.vm.$nextTick();
    expect(w.emitted("submit")).toBeUndefined();
  });
});

describe("PosPaymentWorkspace: o gerente vê quanto de desconto assina", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("o diálogo recebe o desconto manual (linha + venda)", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({
        review: review({
          requires_manager_approval: true,
          approval_reasons: ["discount_over_threshold"],
          manager_approval_threshold_q: 500,
          line_discount_q: 1200,
          order_discount_q: 300,
        }),
        paymentTenders: [{ method: "cash", amount_q: 1000, collection: "terminal" }],
        selectedTenderIndex: 0,
        selectedTenderMethod: "cash",
        paymentTotalQ: 1000,
        paymentRemainingQ: 0,
        paymentCovered: true,
      }),
    });
    expect(w.findComponent({ name: "OperatorManagerAuth" }).props("discountQ")).toBe(1500);
    expect(w.text()).toContain(`Desconto de ${formatBRL(1500)}, acima de ${formatBRL(500)}.`);
  });
});
