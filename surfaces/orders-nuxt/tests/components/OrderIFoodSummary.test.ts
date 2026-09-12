import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import OrderIFoodSummary from "../../app/components/OrderIFoodSummary.vue";

const pendingNotice = "Cancelamento solicitado ao iFood. Aguardando confirmação.";

describe("OrderIFoodSummary", () => {
  it("mantém a solicitação como pendente sem afirmar cancelamento concluído", () => {
    const wrapper = mount(OrderIFoodSummary, { props: { cancellationNotice: pendingNotice } });
    expect(wrapper.get('[role="status"]').text()).toBe(pendingNotice);
    expect(wrapper.findAll("[data-ifood-payment]")).toHaveLength(0);
  });

  it("exibe parcelas pagas e valores a cobrar exatamente como projetados", () => {
    const lines = ["Pago no iFood: R$ 20,00", "Cobrar na entrega: R$ 15,00", "Troco para: R$ 20,00"];
    const wrapper = mount(OrderIFoodSummary, { props: { paymentSummary: lines } });
    expect(wrapper.findAll("[data-ifood-payment]").map((line) => line.text())).toEqual(lines);
    expect(wrapper.find("[data-ifood-cancellation]").exists()).toBe(false);
  });

  it("atualiza o aviso conforme a decisão recebida do servidor", async () => {
    const wrapper = mount(OrderIFoodSummary, { props: { cancellationNotice: pendingNotice } });
    const failed = "O iFood não aceitou a solicitação. Consulte os motivos e tente novamente.";
    await wrapper.setProps({ cancellationNotice: failed });
    expect(wrapper.get('[role="status"]').text()).toBe(failed);
    await wrapper.setProps({ cancellationNotice: "" });
    expect(wrapper.find("[data-ifood-summary]").exists()).toBe(false);
  });

  it("não adiciona bloco vazio a pedidos sem dados iFood", () => {
    const wrapper = mount(OrderIFoodSummary);
    expect(wrapper.find("[data-ifood-summary]").exists()).toBe(false);
  });
});
