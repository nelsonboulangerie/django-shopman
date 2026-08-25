// Tela de resultado pós-venda — a decisão de avanço (auto-avanço e Enter), o
// título e o troco são presentation PURA: o comportamento da tela se prova aqui.
import { describe, expect, it } from "vitest";

import type { PaymentProofView } from "~/presentation/payment";
import {
  AUTO_ADVANCE_SECONDS,
  autoAdvanceSeconds,
  changeDisplay,
  enterAdvances,
  pixAwaiting,
  saleResultTitle,
} from "~/presentation/saleResult";
import { formatBRL } from "~/utils/posIntent";

function pixProof(overrides: Partial<PaymentProofView> = {}): PaymentProofView {
  return {
    method: "pix",
    icon: "lucide:qr-code",
    amountDisplay: "R$ 10,00",
    status: "pending",
    tone: "info",
    message: "",
    qrCodeSrc: "data:image/png;base64,abc",
    copyPaste: "000201...",
    checkoutUrl: "",
    isPix: true,
    isCard: false,
    hasProof: true,
    ...overrides,
  };
}

function cardProof(): PaymentProofView {
  return pixProof({
    method: "card",
    isPix: false,
    isCard: true,
    qrCodeSrc: "",
    copyPaste: "",
    checkoutUrl: "https://checkout.example/abc",
  });
}

describe("saleResultTitle — o obrigado é nominal quando há cliente", () => {
  it("com cliente vinculado, chama pelo primeiro nome (frase completa, com ponto)", () => {
    expect(saleResultTitle("Maria da Silva")).toBe("Venda concluída. Obrigado, Maria!");
  });
  it("sem cliente, a confirmação seca", () => {
    expect(saleResultTitle("")).toBe("Venda concluída");
    expect(saleResultTitle("   ")).toBe("Venda concluída");
  });
});

describe("changeDisplay — troco pronto para o palco", () => {
  it("formata quando há troco", () => {
    expect(changeDisplay(3370)).toBe(formatBRL(3370));
  });
  it("vazio quando não há", () => {
    expect(changeDisplay(0)).toBe("");
  });
});

describe("pixAwaiting — prova pendente na tela", () => {
  it("PIX com prova + polling = aguardando", () => {
    expect(pixAwaiting(pixProof(), "polling")).toBe(true);
  });
  it("confirmado, expirado ou sem prova não é aguardando", () => {
    expect(pixAwaiting(pixProof(), "paid")).toBe(false);
    expect(pixAwaiting(pixProof(), "expired")).toBe(false);
    expect(pixAwaiting(null, "polling")).toBe(false);
    expect(pixAwaiting(cardProof(), "polling")).toBe(false);
  });
});

describe("autoAdvanceSeconds — a tela nunca some sozinha em cima de um gesto", () => {
  const base = { changeQ: 0, payment: null, pixStatus: "idle" as const, reducedMotion: false };

  it("pagamento exato em dinheiro: contagem curta", () => {
    expect(autoAdvanceSeconds(base)).toBe(AUTO_ADVANCE_SECONDS);
  });
  it("cartão (link do checkout): contagem curta e cancelável", () => {
    expect(autoAdvanceSeconds({ ...base, payment: cardProof() })).toBe(AUTO_ADVANCE_SECONDS);
  });
  it("PIX confirmado avança", () => {
    expect(autoAdvanceSeconds({ ...base, payment: pixProof(), pixStatus: "paid" })).toBe(AUTO_ADVANCE_SECONDS);
  });
  it("troco a conferir NUNCA auto-avança", () => {
    expect(autoAdvanceSeconds({ ...base, changeQ: 500 })).toBe(0);
  });
  it("PIX aguardando NUNCA auto-avança (sair é gesto explícito)", () => {
    expect(autoAdvanceSeconds({ ...base, payment: pixProof(), pixStatus: "polling" })).toBe(0);
  });
  it("PIX expirado não some sozinho (prova não resolvida)", () => {
    expect(autoAdvanceSeconds({ ...base, payment: pixProof(), pixStatus: "expired" })).toBe(0);
  });
  it("prefers-reduced-motion desliga a contagem", () => {
    expect(autoAdvanceSeconds({ ...base, reducedMotion: true })).toBe(0);
  });
});

describe("enterAdvances — o Enter que validou não engole a tela do troco", () => {
  it("sem troco e sem PIX pendente, Enter avança", () => {
    expect(enterAdvances({ changeQ: 0, payment: null, pixStatus: "idle" })).toBe(true);
  });
  it("com troco, Enter não avança (confirmação explícita)", () => {
    expect(enterAdvances({ changeQ: 1000, payment: null, pixStatus: "idle" })).toBe(false);
  });
  it("PIX aguardando: só o toque deliberado sai", () => {
    expect(enterAdvances({ changeQ: 0, payment: pixProof(), pixStatus: "polling" })).toBe(false);
  });
  it("PIX confirmado libera o Enter", () => {
    expect(enterAdvances({ changeQ: 0, payment: pixProof(), pixStatus: "paid" })).toBe(true);
  });
});
