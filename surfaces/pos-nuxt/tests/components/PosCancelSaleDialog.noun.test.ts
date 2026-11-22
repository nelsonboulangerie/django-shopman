// O cancelamento da tela de resultado diz o nome do que foi registrado (P2-7, #3192):
// a encomenda recém-registrada se cancela como "encomenda", não como "venda".
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";

import PosCancelSaleDialog from "~/components/PosCancelSaleDialog.vue";

afterEach(() => {
  document.body.innerHTML = "";
});

const base = {
  open: true,
  orderRef: "PDV-042",
  totalDisplay: "R$ 42,00",
  reason: "",
  maxAgeMinutes: 30,
  managers: [{ username: "joyce", name: "Joyce" }],
};

describe("PosCancelSaleDialog", () => {
  it("na encomenda o gerente lê 'Cancelar a encomenda de R$ 42,00'", async () => {
    const wrapper = await mountSuspended(PosCancelSaleDialog, { props: { ...base, noun: "encomenda" }, attachTo: document.body });
    const text = (document.body.textContent || "").replace(/\u00a0/g, " ");
    expect(text).toContain("Cancelar a encomenda de R$ 42,00");
    expect(text).toContain("minutos após a encomenda");
    expect(text).not.toContain("Cancelar a venda");
    wrapper.unmount();
  });

  it("sem dizer o objeto, segue sendo a venda", async () => {
    const wrapper = await mountSuspended(PosCancelSaleDialog, { props: base, attachTo: document.body });
    const text = (document.body.textContent || "").replace(/\u00a0/g, " ");
    expect(text).toContain("Cancelar a venda de R$ 42,00");
    wrapper.unmount();
  });
});
