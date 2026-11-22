import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

/**
 * WP-E2 (D-041): a encomenda acima da fornada planejada da data trava o Validar
 * com os dois números, e o gerente os vê no diálogo antes de assinar. A K16
 * prometeu 200 baguetes contra 22 planejadas com uma ressalva recolhida.
 */
describe("PosPaymentWorkspace: encomenda acima do plano pede o gerente com os números", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  const k16 = { sku: "BF", name: "Baguette de Tradition", date: "2026-11-17", requested_qty: 200, planned_qty: 22, unclaimed_qty: 22 };
  const props = (overrides: Record<string, unknown> = {}) => workspaceProps({
    review: review({
      requires_manager_approval: true,
      approval_reasons: ["preorder_over_plan"],
      preorder_over_plan: [k16],
      warnings: [{
        code: "item_low_stock",
        field: "items",
        sku: "BF",
        message: "Baguette de Tradition: 200 pedidas, 22 planejadas para 17/11. O que passa do plano fica para a Produção planejar.",
      }],
    }),
    salesMode: "order",
    customerName: "Maria Santos",
    customerPhone: "43999990001",
    deliveryDate: "2026-11-17",
    deliveryDateEffective: "2026-11-17",
    scheduleToday: "2026-11-16",
    paymentTenders: [{ method: "cash", amount_q: 1000, collection: "terminal" }],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
    paymentTotalQ: 1000,
    paymentRemainingQ: 0,
    paymentCovered: true,
    ...overrides,
  });

  it("o aviso que trava diz o produto e os dois números, e o botão pede a autorização", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: props() });
    expect(w.text()).toContain("A encomenda passa do plano. Só o gerente libera.");
    expect(w.text()).toContain("Baguette de Tradition: 200 pedidas, 22 planejadas para 17/11.");
    expect(w.text()).toContain("Pedir autorização");
    // A ressalva da mesma linha não se repete no chip.
    expect(w.text()).not.toContain("1 ressalva");
  });

  it("o gerente vê os dois números no diálogo, e sem a assinatura nada fecha", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: props() });
    (w.vm as unknown as { $: { exposed: { validate: () => void } } }).$.exposed.validate();
    await w.vm.$nextTick();
    const dialog = w.findComponent({ name: "OperatorManagerAuth" });
    expect(dialog.props("open")).toBe(true);
    // O motivo do plano tem nome na descrição (#2676) e os números no contexto.
    expect(dialog.props("reasons")).toEqual(["preorder_over_plan"]);
    expect(document.body.textContent).toContain("Encomenda acima do plano da data.");
    const context = document.body.querySelector("[data-over-plan-context]");
    expect(context?.textContent).toContain("200 pedidas, 22 planejadas para 17/11");
    expect(w.emitted("submit")).toBeUndefined();
    dialog.vm.$emit("authorize", "joyce", "1234");
    await w.vm.$nextTick();
    const [[, done]] = w.emitted("checkManager") as [[{ username?: string; pin?: string; badge?: string }, (ok: boolean) => void]];
    done(false);
    await w.vm.$nextTick();
    expect(w.emitted("submit")).toBeUndefined();
  });

  it("assinado: o Validar volta", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: props({ managerApproved: true }) });
    expect(w.text()).not.toContain("Só o gerente libera");
    expect(w.text()).toContain("Validar");
  });

  it("encomenda de outro dia não mostra 'Na retirada'", async () => {
    const collections = [
      { ref: "terminal", label: "Receber no caixa", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: ["cash"] },
      { ref: "on_delivery", label: "Receber ao entregar", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: ["cash"] },
    ];
    const outroDia = await mountSuspended(PosPaymentWorkspace, { props: props({ paymentCollections: collections }) });
    expect(outroDia.text()).not.toContain("Na retirada");
    const hoje = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentCollections: collections, deliveryDate: "2026-11-16", deliveryDateEffective: "2026-11-16" }),
    });
    expect(hoje.text()).toContain("Na retirada");
  });
});
