// Comprovante do LINK de pagamento — a URL para entregar, e até quando ela vale.
// O formato do prazo tem prova própria em presentation.test.ts; aqui se prova
// que a TELA o mostra para o link e só para o link.
import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentResult from "~/components/PosPaymentResult.vue";
import type { PaymentProofView } from "~/presentation/payment";

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

describe("PosPaymentResult — o prazo do link", () => {
  it("diz até quando o link vale, sob a faixa da URL", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, { props: { proof: linkProof(), status: "idle" } });
    const text = wrapper.text();
    expect(text).toContain("https://pay.example.com/abc");
    expect(text).toContain("Vale até amanhã às 9h");
  });

  it("sem prazo, não inventa um", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: { proof: linkProof({ expiresDisplay: "" }), status: "idle" },
    });
    expect(wrapper.text()).not.toContain("Vale até");
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
    expect(wrapper.text()).not.toContain("Vale até");
  });
});

describe("PosPaymentResult — reenviar o link", () => {
  it("o botão fica ao lado de Copiar link e emite resendLink", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, { props: { proof: linkProof(), status: "idle" } });

    const botao = wrapper.find('[data-action="resend-link"]');
    expect(botao.exists()).toBe(true);
    expect(botao.text()).toContain("Reenviar");
    expect(wrapper.text()).toContain("Copiar link");
    await botao.trigger("click");
    expect(wrapper.emitted("resendLink")).toHaveLength(1);
  });

  it("em voo, o botão trava — clique duplo não vira dois reenvios", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: { proof: linkProof(), status: "idle", resending: true },
    });

    const botao = wrapper.find('[data-action="resend-link"]');
    expect(botao.attributes("disabled")).toBeDefined();
    await botao.trigger("click");
    expect(wrapper.emitted("resendLink")).toBeUndefined();
  });

  it("o Pix não tem o que reenviar — o QR está na tela", async () => {
    const wrapper = await mountSuspended(PosPaymentResult, {
      props: {
        proof: linkProof({ method: "pix", isPix: true, isLink: false, checkoutUrl: "", copyPaste: "000201..." }),
        status: "polling",
      },
    });
    expect(wrapper.find('[data-action="resend-link"]').exists()).toBe(false);
  });
});
