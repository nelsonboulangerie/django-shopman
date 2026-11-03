import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

// OS AVISOS DO PAGAMENTO EM TRÊS DEGRAUS (dono, 03/11/2026: "do jeito que está vai
// virar puro ruído"). O que trava é a única caixa; o que acontece é uma linha; a
// ressalva de item (estoque, cardápio, lote) sai do texto e vira o chip "N ressalvas
// nos itens", com o ⚠ no item da conta.

const remark = {
  code: "item_low_stock",
  field: "items",
  sku: "PAO",
  message: "Pão: pausado no cardápio do balcão. A venda vale; confira o cadastro.",
};

describe("PosPaymentWorkspace: a ressalva de item não é caixa", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("a frase não entra nos avisos; vira o chip, e o item da conta leva o ⚠ com a frase", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ review: review({ warnings: [remark] }) }),
    });
    const notices = wrapper.find('[aria-label="Avisos"]');
    expect(notices.exists() ? notices.text() : "").not.toContain("pausado no cardápio");
    expect(wrapper.find("[data-checkout-remarks]").text()).toBe("1 ressalva nos itens");
    expect(wrapper.find("[data-summary-remark]").attributes("aria-label")).toBe(remark.message);
  });

  it("o que trava segue a caixa em destaque; sem ressalva, nada de chip", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ paymentTenders: [] }),
    });
    expect(wrapper.find('[aria-label="Avisos"]').text()).toContain("Escolha a forma de pagamento.");
    expect(wrapper.find("[data-checkout-remarks]").exists()).toBe(false);
  });

  it("ressalva de pagamento (não de item) continua nos avisos", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({
        review: review({ warnings: [{ code: "cash_tendered_amount_too_low", field: "tendered", message: "Valor recebido em dinheiro menor que o total da venda." }] }),
      }),
    });
    expect(wrapper.find('[aria-label="Avisos"]').text()).toContain("Valor recebido em dinheiro menor");
    expect(wrapper.find("[data-checkout-remarks]").exists()).toBe(false);
  });
});

describe("PosPaymentWorkspace: a cozinha acionável no Pagamento (dono, 03/11/2026)", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  const fired = { sku: "CAFE", name: "Café", line_id: "L1", qty: 1, price_q: 500, fired: true, fired_qty: 1 };
  const pending = { sku: "PAO", name: "Pão", line_id: "L2", qty: 2, price_q: 300, fired: false };

  it("o Resumo leva o foguinho só no que já está na cozinha; sem ícone, vai ao finalizar", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ items: [fired, pending], canFireNow: true }),
    });
    const marks = wrapper.findAll("[data-summary-kitchen]").map((icon) => icon.attributes("aria-label"));
    expect(marks).toEqual(["Na cozinha"]);
  });

  it("com o que mandar agora, a linha da cozinha abre o MODAL, e 'Enviar agora' conta UNIDADES e dispara", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ items: [fired, pending], canFireNow: true }),
    });
    await wrapper.find("[data-checkout-kitchen]").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    const fire = document.body.querySelector<HTMLElement>("[data-checkout-fire-now]")!;
    expect(fire.textContent?.trim()).toBe("Enviar agora (2)");
    expect(document.body.querySelector("[data-checkout-kitchen-pending]")?.textContent).toContain("Pão");
    fire.click();
    expect(wrapper.emitted("fireNow")).toHaveLength(1);
  });

  it("sem a ação de mandar (ou tudo já foi), a cozinha é só a linha", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ items: [fired, pending], canFireNow: false }),
    });
    expect(wrapper.find("[data-checkout-kitchen]").exists()).toBe(false);
    expect(wrapper.find('[data-checkout-line="kitchen"]').exists()).toBe(true);
  });
});
