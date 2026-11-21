import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

type Approval = { username?: string; pin?: string; badge?: string };

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
    const [[approval, done]] = w.emitted("checkManager") as [[Approval, (ok: boolean) => void]];
    expect(approval).toEqual({ username: "joyce", pin });
    return { w, dialog, done };
  }

  // O CRACHÁ (#2691): o diálogo "Autorizar a venda" convidava a passar o crachá, e a
  // tela não escutava o `authorize-badge`. Passar o crachá confere pela MESMA porta do
  // PIN (`checkManager`), com `{badge}`, e segue do mesmo jeito.
  async function passesBadge(badge: string) {
    const w = await mountSuspended(PosPaymentWorkspace, { props: props() });
    (w.vm as unknown as { $: { exposed: { validate: () => void } } }).$.exposed.validate();
    await w.vm.$nextTick();
    const dialog = w.findComponent({ name: "OperatorManagerAuth" });
    expect(dialog.props("open")).toBe(true);
    dialog.vm.$emit("authorizeBadge", badge);
    await w.vm.$nextTick();
    const emitted = w.emitted("checkManager") as [[Approval, (ok: boolean) => void]] | undefined;
    expect(emitted, "o crachá não chegou à conferência do gerente").toHaveLength(1);
    const [[approval, done]] = emitted!;
    expect(approval).toEqual({ badge });
    return { w, dialog, done };
  }

  it("crachá conferido: fecha e segue, como o PIN", async () => {
    const { w, dialog, done } = await passesBadge("4337f822b0e6");
    done(true);
    await w.vm.$nextTick();
    expect(dialog.props("open")).toBe(false);
    expect(w.emitted("submit")).toHaveLength(1);
  });

  it("crachá recusado: o diálogo fica aberto e a venda não anda", async () => {
    const { w, dialog, done } = await passesBadge("000000000000");
    done(false);
    await w.vm.$nextTick();
    expect(dialog.props("open")).toBe(true);
    expect(w.emitted("submit")).toBeUndefined();
  });

  it("PIN recusado: o diálogo fica aberto e a venda não anda", async () => {
    const { w, dialog, done } = await autorizar("0000");
    done(false);
    await w.vm.$nextTick();
    expect(dialog.props("open")).toBe(true);
    expect(w.emitted("submit")).toBeUndefined();
  });

  it("PIN conferido: fecha e segue, e o PIN não sobe para o carrinho", async () => {
    const { w, dialog, done } = await autorizar("4321");
    done(true);
    await w.vm.$nextTick();
    // Quem guarda a assinatura, presa ao retrato, é o `usePosSale` (WP-E1).
    expect(Object.keys(w.emitted()).filter((name) => name.startsWith("update:manager"))).toEqual([]);
    expect(dialog.props("open")).toBe(false);
    expect(w.emitted("submit")).toHaveLength(1);
  });

  it("o retrato mudou depois da assinatura: o aviso e 'Pedir autorização' voltam", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: { ...props(), managerApproved: true } });
    expect(w.text()).not.toContain("Esta venda precisa de um gerente.");
    expect(w.text()).toContain("Validar");
    await w.setProps({ managerApproved: false });
    expect(w.text()).toContain("Esta venda precisa de um gerente.");
    expect(w.text()).toContain("Pedir autorização");
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
