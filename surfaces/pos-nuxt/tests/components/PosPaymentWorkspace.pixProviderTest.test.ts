import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { review, workspaceProps } from "../support/paymentWorkspaceProps";

const paymentConstraints = {
  pix: {
    provider: "efi",
    environment: "sandbox",
    mode: "provider_test",
    is_test: true,
    max_amount_q: 1000,
    max_amount_display: "R$ 10,00",
    message: "Ambiente de testes: a Efí simula a confirmação de Pix de até R$ 10,00. Para continuar, troque a forma de pagamento ou ajuste os itens do pedido.",
  },
};
const pix = (amount_q: number) => ({ method: "pix", amount_q, collection: "terminal" as const });
const cta = (wrapper: Awaited<ReturnType<typeof mountSuspended>>) =>
  wrapper.findAll("button").find((button) => /Validar|Autorizar|Atualizando/.test(button.text()));

describe("PosPaymentWorkspace — limite Pix do provedor", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("avisa durante todo o Pix de teste e mantém R$ 10,00 permitido", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({
        paymentConstraints,
        paymentTenders: [pix(1000)],
        selectedTenderIndex: 0,
        selectedTenderMethod: "pix",
        paymentCovered: true,
        paymentRemainingQ: 0,
      }),
    });

    const notices = wrapper.find('[aria-label="Avisos"]').text();
    expect(notices).toContain("a Efí simula a confirmação de Pix de até R$ 10,00");
    expect(notices).toContain("está dentro do limite");
    // Dentro do limite o aviso não manda trocar nada: instrução que a venda não
    // precisa seguir, ao lado de "está dentro do limite", obriga a escolher.
    expect(notices).not.toContain("troque a forma de pagamento");
    expect(wrapper.findAll("button").some((button) => button.text().includes("Trocar forma de pagamento"))).toBe(false);
    expect(cta(wrapper)?.attributes("disabled")).toBeUndefined();
  });

  it("sem a constraint (produção ou Pix simulado) nada aparece, mesmo acima de R$ 10,00", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({
        review: review({ total_q: 1500, total_display: "R$ 15,00" }),
        paymentTotalQ: 1500,
        paymentTenders: [pix(1500)],
        selectedTenderIndex: 0,
        selectedTenderMethod: "pix",
        paymentCovered: true,
        paymentRemainingQ: 0,
      }),
    });

    expect(wrapper.text()).not.toContain("Efí");
    expect(wrapper.findAll("button").some((button) => button.text().includes("Trocar forma de pagamento"))).toBe(false);
    expect(cta(wrapper)?.attributes("disabled")).toBeUndefined();
  });

  it("bloqueia acima do teto e oferece as duas saídas reais", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      attachTo: document.body,
      props: workspaceProps({
        paymentConstraints,
        review: review({ total_q: 1001, total_display: "R$ 10,01" }),
        paymentTotalQ: 1001,
        paymentTenders: [pix(1001)],
        selectedTenderIndex: 0,
        selectedTenderMethod: "pix",
        paymentCovered: true,
        paymentRemainingQ: 0,
      }),
    });

    const notices = wrapper.find('[aria-label="Avisos"]');
    expect(notices.text()).toContain(paymentConstraints.pix.message);
    expect(cta(wrapper)?.attributes("disabled")).toBeDefined();

    const switchMethod = wrapper.findAll("button").find((button) => button.text().includes("Trocar forma de pagamento"));
    await switchMethod!.trigger("click");
    expect(wrapper.emitted("removeTender")?.[0]).toEqual([0]);

    const adjustItems = wrapper.findAll("button").find((button) => button.text().includes("Ajustar itens"));
    await adjustItems!.trigger("click");
    expect(wrapper.emitted("back")).toHaveLength(1);
  });

  it("compara o teto com o total efetivo, não com a parcela Pix digitada", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({
        paymentConstraints,
        review: review({ total_q: 1500, total_display: "R$ 15,00" }),
        paymentTotalQ: 1500,
        paymentTenders: [pix(500)],
        selectedTenderIndex: 0,
        selectedTenderMethod: "pix",
        paymentCovered: false,
        paymentRemainingQ: 1000,
      }),
    });

    const notices = wrapper.find('[aria-label="Avisos"]');
    expect(notices.text()).toContain(paymentConstraints.pix.message);
    expect(notices.text()).not.toContain("está dentro do limite");
    expect(cta(wrapper)?.attributes("disabled")).toBeDefined();
  });

  it("impede Pix misto ou dividido antes do avanço", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({
        paymentConstraints,
        paymentTenders: [pix(500), { method: "cash", amount_q: 500, collection: "terminal" }],
        selectedTenderIndex: 0,
        selectedTenderMethod: "pix",
        paymentCovered: true,
        paymentRemainingQ: 0,
      }),
    });

    const mixedNotice = wrapper.find('[aria-label="Avisos"]').text();
    expect(mixedNotice).toContain("Pix não pode ser combinado nem dividido");
    // Sem divisão armada, "esta divisão" não existe; e ajustar itens não desfaz a combinação.
    expect(mixedNotice).not.toContain("divisão.");
    expect(mixedNotice).toContain("Use Pix sozinho no total");
    expect(wrapper.findAll("button").some((button) => button.text().includes("Ajustar itens"))).toBe(false);
    expect(cta(wrapper)?.attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-payment-method="cash"]').attributes("disabled")).toBeDefined();

    const switchMethod = wrapper.findAll("button").find((button) => button.text().includes("Trocar forma de pagamento"));
    await switchMethod!.trigger("click");
    expect(wrapper.emitted("removeTender")?.[0]).toEqual([0]);

    const splitFirst = await mountSuspended(PosPaymentWorkspace, {
      props: workspaceProps({ paymentConstraints, splitCount: 2 }),
    });
    expect(splitFirst.find('[data-payment-method="pix"]').attributes("disabled")).toBeDefined();
  });
});
