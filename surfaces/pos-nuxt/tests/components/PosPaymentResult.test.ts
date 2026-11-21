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

// O Pix que venceu não é mais pagável: o QR e o copia-e-cola saem da tela (o
// cliente escanearia um código que o banco recusa), e o cartão diz só o fato.
// O aviso com o botão que resolve é da TELA, um só (auditoria do #2918).
describe("PosPaymentResult — o Pix vencido", () => {
  const pix = () => linkProof({ method: "pix", isPix: true, isLink: false, checkoutUrl: "", qrCodeSrc: "data:image/png;base64,abc", copyPaste: "000201..." });

  it("aguardando: QR e 'Copiar código Pix', com a grafia da casa", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, { props: { proof: pix(), status: "polling" } });
    expect(wrapper.find('img[alt="QR Code Pix"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Copiar código Pix");
    expect(wrapper.text()).toContain("Pagamento Pix");
    expect(wrapper.text()).not.toContain("PIX");
  });

  it("vencido: sem QR, sem código e sem botão de copiar; só o fato, sem repetir o aviso da tela", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, { props: { proof: pix(), status: "expired" } });
    const text = wrapper.text();
    expect(wrapper.find("img").exists()).toBe(false);
    expect(text).not.toContain("000201");
    expect(text).not.toContain("Copiar código");
    expect(text).toContain("Este Pix não pode mais ser pago.");
    expect(text).not.toContain("não foi confirmado");
    expect(text).not.toMatch(/Confira no gestor/i);
    expect(text).not.toContain("PIX");
    expect(wrapper.find("[data-payment-proof-expired]").exists()).toBe(true);
  });

  it("vencido: nem o envio ao cliente, nem o aviso do envio (o código morreu com o QR)", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: {
        proof: pix(),
        status: "expired",
        delivery: delivery({ template: "pix", status: "failed", notice: "O envio falhou em todos os canais disponíveis.", action: "resend", action_label: "Reenviar Pix" }),
      },
    });
    expect(wrapper.find("[data-payment-delivery]").exists()).toBe(false);
    expect(wrapper.find('[data-action="send-payment-notice"]').exists()).toBe(false);
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
          action_label: "Enviar Pix ao cliente",
        }),
      },
    });
    const botao = wrapper.find('[data-action="send-payment-notice"]');
    expect(botao.text()).toContain("Enviar Pix ao cliente");
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
