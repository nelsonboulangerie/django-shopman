import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { OFFLINE_SALE_OFF_REASON } from "~/presentation/offlineSales";
import type { ActionAffordance } from "~/presentation/actions";
import { formatBRL } from "~/utils/posIntent";
import { workspaceProps } from "../support/paymentWorkspaceProps";

// A VENDA SEM CONEXÃO DESLIGADA NA LOJA (dono, 03/11/2026): sem rede, o balcão não
// cobra. O Pagamento (F4) e o Validar ficam apagados, com a razão escrita abaixo.

enableAutoUnmount(afterEach);

function affordance(overrides: Partial<ActionAffordance> = {}): ActionAffordance {
  return { ref: "fire_tab", present: true, label: "Enviar à cozinha", priority: "primary", enabled: true, reason: "", href: "/x", ...overrides };
}

function cartProps(overrides: Record<string, unknown> = {}) {
  return {
    items: [{ line_id: "L-PAO", sku: "PAO", name: "Pão", price_q: 500, qty: 1, notes: "" }],
    total: { status: "offline", display: formatBRL(500) },
    requiresTab: false,
    hasOpenTab: false,
    loading: false,
    saving: false,
    offline: true,
    fireAction: affordance(),
    unfireAction: affordance({ ref: "unfire_tab", label: "Cancelar envio" }),
    firing: false,
    ...overrides,
  };
}

const cash = { method: "cash", amount_q: 1000, collection: "terminal" as const };

describe("venda sem conexão desligada: a comanda", () => {
  it("o Pagamento fica apagado, com a razão escrita abaixo", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: cartProps({ saleBlockedReason: OFFLINE_SALE_OFF_REASON }) });

    expect(wrapper.find("[data-pos-primary]").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-pos-sale-blocked-reason]").text()).toBe("Sem conexão. A venda espera a rede voltar.");
  });

  it("com a chave ligada (sem razão), o Pagamento segue clicável sem conexão", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: cartProps() });

    expect(wrapper.find("[data-pos-primary]").attributes("disabled")).toBeUndefined();
    expect(wrapper.find("[data-pos-sale-blocked-reason]").exists()).toBe(false);
  });
});

describe("venda sem conexão desligada: o Pagamento", () => {
  function paymentProps(overrides: Record<string, unknown> = {}) {
    return workspaceProps({
      paymentTenders: [cash],
      selectedTenderIndex: 0,
      selectedTenderMethod: "cash",
      paymentCovered: true,
      paymentRemainingQ: 0,
      ...overrides,
    });
  }

  it("Validar fica travado e o aviso diz por quê", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: paymentProps({ saleBlockedReason: OFFLINE_SALE_OFF_REASON }),
    });

    const notices = wrapper.find('[aria-label="Avisos"]').text();
    expect(notices).toContain("Sem conexão. A venda espera a rede voltar.");
    expect(notices).toContain("Esta loja não vende sem conexão. Os itens ficam na comanda até a rede voltar.");
    const cta = wrapper.findAll("button").find((button) => button.text().includes("Enter"));
    expect(cta?.attributes("disabled")).toBeDefined();
  });

  it("sem razão, Validar segue liberado", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: paymentProps() });

    expect(wrapper.find('[aria-label="Avisos"]').exists() ? wrapper.find('[aria-label="Avisos"]').text() : "")
      .not.toContain("A venda espera a rede voltar.");
    const cta = wrapper.findAll("button").find((button) => button.text().includes("Enter"));
    expect(cta?.attributes("disabled")).toBeUndefined();
  });
});
