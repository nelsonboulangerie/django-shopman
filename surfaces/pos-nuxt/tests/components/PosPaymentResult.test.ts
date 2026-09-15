// Comprovante do LINK de pagamento — a URL para entregar, e até quando ela vale.
// O formato do prazo tem prova própria em presentation.test.ts; aqui se prova
// que a TELA o mostra para o link e só para o link.
import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentResult from "~/components/PosPaymentResult.vue";
import type { PaymentProofView } from "~/presentation/payment";
import type { POSPaymentDeliveryProjection } from "~/types/pos";

function linkProof(overrides: Partial<PaymentProofView> = {}): PaymentProofView {
  return {
    method: "link",
    icon: "lucide:wallet",
    amountDisplay: "R$ 63,00",
    status: "pending",
    tone: "info",
    message: "",
    qrCodeSrc: "",
    copyPaste: "",
    checkoutUrl: "https://pay.example.com/abc",
    isPix: false,
    isCard: false,
    isLink: true,
    hasProof: true,
    expiresDisplay: "amanhã às 9h",
    ...overrides,
  };
}

function delivery(overrides: Partial<POSPaymentDeliveryProjection> = {}): POSPaymentDeliveryProjection {
  return {
    template: "payment_link",
    status: "accepted",
    channel: "whatsapp",
    channel_label: "WhatsApp",
    notice: "Envio aceito pelo WhatsApp. Leitura não confirmada.",
    reason_code: "",
    can_send: false,
    can_resend: true,
    action: "resend",
    action_label: "Reenviar cobrança",
    ...overrides,
  };
}

describe("PosPaymentResult — o prazo do link", () => {
  it("diz até quando o link vale, sob a faixa da URL", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, { props: { proof: linkProof(), status: "idle" } });
    const text = wrapper.text();
    expect(text).toContain("https://pay.example.com/abc");
    expect(text).toContain("Pague até amanhã às 9h para garantir o pedido");
  });

  it("sem prazo, não inventa um", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: { proof: linkProof({ expiresDisplay: "" }), status: "idle" },
    });
    expect(wrapper.text()).not.toContain("Pague até");
  });

  it("o Pix não ganha a linha — o relógio dele é o polling", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: {
        proof: linkProof({
          method: "pix",
          isPix: true,
          isLink: false,
          checkoutUrl: "",
          copyPaste: "000201...",
          expiresDisplay: "hoje às 18h",
        }),
        status: "polling",
      },
    });
    expect(wrapper.text()).not.toContain("Pague até");
  });
});

describe("PosPaymentResult — entrega da cobrança", () => {
  it("mostra o canal realmente aceito e emite a ação do servidor", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: { proof: linkProof(), status: "idle", delivery: delivery() },
    });

    const botao = wrapper.find('[data-action="send-payment-notice"]');
    expect(botao.exists()).toBe(true);
    expect(botao.text()).toContain("Reenviar cobrança");
    expect(wrapper.text()).toContain("Copiar link");
    expect(wrapper.text()).toContain("Envio aceito pelo WhatsApp. Leitura não confirmada.");
    await botao.trigger("click");
    expect(wrapper.emitted("paymentNotice")).toEqual([["resend"]]);
  });

  it("em voo, o botão trava — clique duplo não vira dois reenvios", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: { proof: linkProof(), status: "idle", delivery: delivery(), resending: true },
    });

    const botao = wrapper.find('[data-action="send-payment-notice"]');
    expect(botao.attributes("disabled")).toBeDefined();
    await botao.trigger("click");
    expect(wrapper.emitted("paymentNotice")).toBeUndefined();
  });

  it("o Pix pode ser enviado quando o servidor expõe a ação", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: {
        proof: linkProof({ method: "pix", isPix: true, isLink: false, checkoutUrl: "", copyPaste: "000201..." }),
        status: "polling",
        delivery: delivery({
          template: "payment_requested",
          status: "not_sent",
          channel: "",
          channel_label: "",
          notice: "Cobrança pronta para envio.",
          can_send: true,
          can_resend: false,
          action: "send",
          action_label: "Enviar PIX ao cliente",
        }),
      },
    });
    const botao = wrapper.find('[data-action="send-payment-notice"]');
    expect(botao.text()).toContain("Enviar PIX ao cliente");
    await botao.trigger("click");
    expect(wrapper.emitted("paymentNotice")).toEqual([["send"]]);
  });

  it("não inventa ação ou canal quando o servidor não os informou", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: { proof: linkProof(), status: "idle", delivery: delivery({ status: "queued", channel: "", channel_label: "", action: "", action_label: "", notice: "Envio na fila." }) },
    });
    expect(wrapper.text()).toContain("Envio na fila.");
    expect(wrapper.text()).not.toContain("WhatsApp");
    expect(wrapper.find('[data-action="send-payment-notice"]').exists()).toBe(false);
  });
});
