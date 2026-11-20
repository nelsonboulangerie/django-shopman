import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import OrderNotificationReceipts from "../../app/components/OrderNotificationReceipts.vue";
import type { NotificationReceiptProjection } from "../../app/generated/ordersContract";

function receipt(overrides: Partial<NotificationReceiptProjection> = {}): NotificationReceiptProjection {
  return {
    template: "payment_link_sent",
    label: "Link de pagamento enviado",
    critical: true,
    state: "delivered",
    state_label: "Entregue com comprovante",
    tone: "ok",
    channel_label: "E-mail",
    time_display: "01/10 às 18:42",
    provider_id: "<abc@boulangerie.com.br>",
    detail: "O provedor registrou a mensagem e devolveu o identificador. Isso não confirma leitura.",
    attempts: [],
    fallback_whatsapp_url: "",
    ...overrides,
  };
}

describe("OrderNotificationReceipts", () => {
  it("mostra canal, hora e o identificador do provedor quando há comprovante", () => {
    const wrapper = mount(OrderNotificationReceipts, { props: { receipts: [receipt()] } });
    expect(wrapper.get("[data-receipt-label]").text()).toBe("Entregue com comprovante");
    expect(wrapper.text()).toContain("01/10 às 18:42 · E-mail");
    expect(wrapper.get("[data-receipt-provider-id]").text()).toContain("<abc@boulangerie.com.br>");
    // O aviso que precisava chegar diz isso em palavras, não "crítico".
    expect(wrapper.get("[data-receipt-critical]").text()).toBe("Precisava chegar");
  });

  it("aceite sem comprovante nunca aparece como entregue", () => {
    const wrapper = mount(OrderNotificationReceipts, {
      props: {
        receipts: [receipt({
          state: "accepted_no_receipt",
          state_label: "Aceito pelo provedor, sem comprovante",
          tone: "warning",
          channel_label: "WhatsApp",
          provider_id: "",
          attempts: [
            { channel_label: "WhatsApp", outcome: "no_receipt", outcome_label: "aceito, sem comprovante", time_display: "01/10 às 18:42", provider_id: "" },
            { channel_label: "SMS", outcome: "no_receipt", outcome_label: "aceito, sem comprovante", time_display: "01/10 às 18:42", provider_id: "" },
          ],
        })],
      },
    });
    expect(wrapper.get("[data-receipt-label]").text()).toBe("Aceito pelo provedor, sem comprovante");
    expect(wrapper.text()).not.toContain("Entregue");
    expect(wrapper.find("[data-receipt-provider-id]").exists()).toBe(false);
    expect(wrapper.findAll("[data-receipt-attempts] li").map((li) => li.text())).toEqual([
      "WhatsApp: aceito, sem comprovante, 01/10 às 18:42",
      "SMS: aceito, sem comprovante, 01/10 às 18:42",
    ]);
  });

  it("o aviso do Avisar o cliente que não saiu traz o WhatsApp com o mesmo texto", () => {
    const url = "https://wa.me/5543999990002?text=Oi%2C%20Ana!";
    const wrapper = mount(OrderNotificationReceipts, {
      props: {
        receipts: [
          receipt(),
          receipt({
            template: "order_item_missing",
            label: "Faltou um item",
            critical: false,
            state: "failed",
            state_label: "Falhou em todos os canais",
            tone: "danger",
            provider_id: "",
            fallback_whatsapp_url: url,
          }),
        ],
      },
    });
    const buttons = wrapper.findAll("[data-receipt-fallback]");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]!.attributes("href")).toBe(url);
    expect(buttons[0]!.text()).toBe("Chamar no WhatsApp");
  });

  it("não desenha bloco vazio quando o pedido não tem aviso", () => {
    const wrapper = mount(OrderNotificationReceipts, { props: { receipts: [] } });
    expect(wrapper.find("[data-notification-receipts]").exists()).toBe(false);
  });
});
