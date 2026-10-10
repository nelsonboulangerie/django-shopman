// Regra do dono (09/10/2026): total que ainda pode mudar não aparece como
// definitivo. O botão do Pagamento (F4), o resumo da folha fechada e o "Pagar"
// da folha da mesa mostram o total da revisão do servidor; sem ela, o lugar do
// número diz "Calculando…" (ou "Não calculado") e NENHUM valor em reais.
import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";
import type { SaleTotalView } from "~/presentation/saleTotal";
import { formatBRL } from "~/utils/posIntent";

enableAutoUnmount(afterEach);

const fire: ActionAffordance = {
  ref: "fire_tab",
  present: true,
  label: "Enviar à cozinha",
  priority: "primary",
  enabled: true,
  reason: "",
  href: "/x",
};

function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { line_id: `L-${overrides.sku}`, price_q: 500, qty: 1, notes: "", ...overrides };
}

// Soma local 11,00; o servidor diz 9,90 (um desconto automático que a soma local não vê).
function props(total: SaleTotalView, overrides: Record<string, unknown> = {}) {
  return {
    items: [item({ sku: "PAO", name: "Pão" }), item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 })],
    total,
    requiresTab: false,
    hasOpenTab: true,
    loading: false,
    saving: false,
    fireAction: fire,
    unfireAction: { ...fire, ref: "unfire_tab", label: "Cancelar envio" },
    firing: false,
    ...overrides,
  };
}

const quickPayments = [
  { ref: "pix", label: "PIX", icon: "lucide:qr-code" },
  { ref: "card", label: "Maquininha", icon: "lucide:credit-card" },
];

describe("PosCartPanel — o total da comanda é o do servidor", () => {
  it("confirmado: o botão do Pagamento mostra o total da revisão, não a soma local", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ status: "confirmed", display: formatBRL(990) }),
    });
    const total = wrapper.find("[data-pos-primary-total]");
    expect(total.attributes("data-total-state")).toBe("confirmed");
    expect(total.text()).toContain(formatBRL(990));
    expect(wrapper.find("[data-pos-primary]").text()).not.toContain(formatBRL(1100));
  });

  it("calculando: o botão do Pagamento diz Calculando… e nenhum valor, e continua tocável", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ status: "calculating", display: "" }) });
    const primary = wrapper.find("[data-pos-primary]");
    expect(primary.find("[data-pos-primary-total]").text()).toContain("Calculando…");
    expect(primary.text()).not.toContain("R$");
    // Abrir o pagamento não espera: lá a revisão é refeita e as formas liberam quando ela chega.
    expect(primary.attributes("disabled")).toBeUndefined();
    await primary.trigger("click");
    expect(wrapper.emitted("prepare")).toHaveLength(1);
  });

  it("falhou: o botão diz Não calculado, sem número", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ status: "failed", display: "" }) });
    const total = wrapper.find("[data-pos-primary-total]");
    expect(total.attributes("data-total-state")).toBe("failed");
    expect(total.text()).toContain("Não calculado");
    expect(wrapper.find("[data-pos-primary]").text()).not.toContain("R$");
  });

  it("edição de encomenda: o botão não mostra total (a prévia do Salvar alterações mostra)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ status: "hidden", display: "" }, { primaryLabel: "Salvar alterações" }),
    });
    expect(wrapper.find("[data-pos-primary-total]").exists()).toBe(false);
    expect(wrapper.find("[data-pos-primary]").text()).not.toContain("R$");
  });

  it("folha fechada: a barra conta os itens e diz Calculando…, sem a soma local", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ status: "calculating", display: "" }, { sheet: true }),
    });
    const context = wrapper.find("[data-pos-sheet-bar] [data-operator-action-bar-context]");
    expect(context.text()).toContain("3 itens");
    expect(context.text()).toContain("Calculando…");
    expect(context.text()).not.toContain("R$");
    // "Calculando…" vai na linha de contexto, em texto comum: nunca no lugar do número.
    expect(context.find("span.font-semibold").exists()).toBe(false);
  });

  it("folha da mesa: o Pagar mostra Calculando… sem número, e o confirmado com o valor do servidor", async () => {
    const pending = await mountSuspended(PosCartPanel, {
      props: props({ status: "calculating", display: "" }, { sheet: true, quickPayments }),
    });
    await pending.find("[data-operator-action-bar-secondary]").trigger("click");
    await new Promise((resolve) => setTimeout(resolve, 0));
    const pay = document.body.querySelector("[data-pos-sheet-pay]");
    expect(pay?.querySelector("[data-pos-sheet-pay-total]")?.textContent?.trim()).toBe("Calculando…");
    expect(pay?.textContent).not.toContain("R$");
    pending.unmount();

    const confirmed = await mountSuspended(PosCartPanel, {
      props: props({ status: "confirmed", display: formatBRL(990) }, { sheet: true, quickPayments }),
    });
    await confirmed.find("[data-operator-action-bar-secondary]").trigger("click");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.body.querySelector("[data-pos-sheet-pay-total]")?.textContent?.trim()).toBe(formatBRL(990));
    expect(confirmed.find("[data-operator-action-bar-context]").text()).toContain(formatBRL(990));
  });
});
