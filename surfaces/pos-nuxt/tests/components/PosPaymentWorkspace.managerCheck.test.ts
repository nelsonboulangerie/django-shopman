import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

/**
 * O PIN do gerente é conferido com o diálogo aberto (beta test de 05/11/2026).
 * Antes o diálogo guardava o PIN e fechava; o PIN errado só voltava no
 * fechamento, depois de o operador já ter confirmado "Recebi o Pix".
 */
describe("PosPaymentWorkspace: o PIN do gerente é conferido antes de seguir", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  const props = () => workspaceProps({
    review: review({ requires_manager_approval: true }),
    paymentTenders: [{ method: "cash", amount_q: 1000, collection: "terminal" }],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentTotalQ: 1000,
    paymentRemainingQ: 0,
    paymentCovered: true,
  });

  async function autorizar(pin: string) {
    const w = await mountSuspended(PosPaymentWorkspace, { props: props() });
    (w.vm as unknown as { $: { exposed: { validate: () => void } } }).$.exposed.validate();
    await w.vm.$nextTick();
    const dialog = w.findComponent({ name: "OperatorManagerAuth" });
    expect(dialog.props("open")).toBe(true);
    dialog.vm.$emit("authorize", "joyce", pin);
    await w.vm.$nextTick();
    const [[username, typed, done]] = w.emitted("checkManager") as [[string, string, (ok: boolean) => void]];
    expect([username, typed]).toEqual(["joyce", pin]);
    return { w, dialog, done };
  }

  it("PIN recusado: o diálogo fica aberto e a venda não anda", async () => {
    const { w, dialog, done } = await autorizar("0000");
    done(false);
    await w.vm.$nextTick();
    expect(dialog.props("open")).toBe(true);
    expect(w.emitted("submit")).toBeUndefined();
    expect(w.emitted("update:managerPin")).toBeUndefined();
  });

  it("PIN conferido: grava a assinatura, fecha e segue", async () => {
    const { w, dialog, done } = await autorizar("4321");
    done(true);
    await w.vm.$nextTick();
    expect(w.emitted("update:managerUsername")).toEqual([["joyce"]]);
    expect(w.emitted("update:managerPin")).toEqual([["4321"]]);
    expect(dialog.props("open")).toBe(false);
    expect(w.emitted("submit")).toHaveLength(1);
  });

  it("fechar o diálogo com erro na tela pede para limpar o erro", async () => {
    const { w, dialog, done } = await autorizar("0000");
    await w.setProps({ managerApprovalError: "Confira o gerente e digite o PIN de novo." });
    done(false);
    await w.vm.$nextTick();
    expect(dialog.props("open")).toBe(true);
    dialog.vm.$emit("update:open", false);
    await w.vm.$nextTick();
    expect(w.emitted("managerAuthDismissed")).toHaveLength(1);
  });
});
