// Tela de resultado pós-venda — a decisão de avanço (auto-avanço e Enter), o
// título e o troco são presentation PURA: o comportamento da tela se prova aqui.
import { describe, expect, it } from "vitest";

import type { PaymentProofView } from "~/presentation/payment";
import {
  AUTO_ADVANCE_SECONDS,
  autoAdvanceSeconds,
  changeDisplay,
  courierChangeLine,
  danfeOffer,
  enterAdvances,
  fiscalStateLabel,
  orderReadback,
  pixAwaiting,
  resolveFiscalState,
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

describe("a tela do LINK não some sozinha", () => {
  // ⚠️ Era este o defeito que fazia o fluxo do link "morrer": a venda fechava, a
  // URL aparecia — e cinco segundos depois a tela se fechava sozinha, antes de o
  // operador copiar. O pedido ficava aguardando um pagamento que ninguém pediu,
  // e recuperar a URL exigia ir ao gestor.
  const comLink = { isPix: false, isLink: true, hasProof: true } as never;

  it("o auto-avanço não conta com um link na tela", () => {
    expect(autoAdvanceSeconds({ changeQ: 0, payment: comLink, pixStatus: "idle", reducedMotion: false })).toBe(0);
  });

  it("nem o Enter engole a tela do link", () => {
    expect(enterAdvances({ changeQ: 0, payment: comLink, pixStatus: "idle" })).toBe(false);
  });

  it("sem prova para entregar, a venda comum continua avançando sozinha", () => {
    const semProva = { isPix: false, isLink: false, hasProof: false } as never;
    expect(autoAdvanceSeconds({ changeQ: 0, payment: semProva, pixStatus: "idle", reducedMotion: false }))
      .toBeGreaterThan(0);
    expect(enterAdvances({ changeQ: 0, payment: semProva, pixStatus: "idle" })).toBe(true);
  });
});

describe("cobrança que falhou não veste cara de venda concluída", () => {
  // ⚠️ O defeito real, reproduzido no balcão: o Pix voltou `403 Forbidden` do
  // gateway, a resposta trouxe `status: "error"` — e a tela mostrou o check
  // verde de "Venda concluída" e se fechou sozinha em 5 s. O pedido existia, a
  // linha do livro-caixa existia, e ninguém tinha cobrado R$ 12,00.
  const falhou = { isPix: true, isLink: false, hasProof: false, status: "error" } as never;
  const semDado = { isPix: true, isLink: false, hasProof: false, status: "unavailable" } as never;

  it("a tela não se fecha sozinha em cima de uma venda sem cobrança", () => {
    expect(autoAdvanceSeconds({ changeQ: 0, payment: falhou, pixStatus: "idle", reducedMotion: false })).toBe(0);
    expect(autoAdvanceSeconds({ changeQ: 0, payment: semDado, pixStatus: "idle", reducedMotion: false })).toBe(0);
  });

  it("nem o Enter que validou a venda passa por cima do aviso", () => {
    expect(enterAdvances({ changeQ: 0, payment: falhou, pixStatus: "idle" })).toBe(false);
  });

  it("o título diz o que aconteceu, e não agradece", () => {
    expect(saleResultTitle("Ana Maria", falhou)).toBe("Venda registrada, cobrança não criada");
    expect(saleResultTitle("Ana Maria", null)).toBe("Venda concluída. Obrigado, Ana!");
  });
});

describe("orderReadback — a leitura de volta da encomenda", () => {
  it("balcão não lê nada de volta: o pedido já foi entregue na mão", () => {
    expect(orderReadback({ salesMode: "counter", fulfillmentLabel: "Retirada", scheduleLabel: "Hoje" })).toBeNull();
    expect(orderReadback({ salesMode: undefined, fulfillmentLabel: "Retirada" })).toBeNull();
  });

  it("encomenda devolve como e quando, aparados", () => {
    expect(orderReadback({ salesMode: "order", fulfillmentLabel: " Entrega · Centro ", scheduleLabel: "sáb, 20/09, 10:00 às 10:30" }))
      .toEqual({ fulfillment: "Entrega · Centro", schedule: "sáb, 20/09, 10:00 às 10:30" });
  });

  it("encomenda sem nenhum dos dois não inventa bloco vazio", () => {
    expect(orderReadback({ salesMode: "order", fulfillmentLabel: "", scheduleLabel: "  " })).toBeNull();
  });
});

describe("enterAdvances — a encomenda não é dispensada por hábito", () => {
  it("no modo encomenda, Enter NÃO avança (a tela é a leitura de volta ao cliente)", () => {
    expect(enterAdvances({ changeQ: 0, payment: null, pixStatus: "idle", salesMode: "order" })).toBe(false);
  });
  it("no balcão, o mesmo estado avança", () => {
    expect(enterAdvances({ changeQ: 0, payment: null, pixStatus: "idle", salesMode: "counter" })).toBe(true);
    expect(enterAdvances({ changeQ: 0, payment: null, pixStatus: "idle" })).toBe(true);
  });
});

describe("courierChangeLine — o troco que sai com o entregador é linha, não herói", () => {
  it("formata quando há troco a separar", () => {
    expect(courierChangeLine(5800)).toBe(`Troco a separar: ${formatBRL(5800)}`);
  });
  it("vazio sem troco, zero ou ausente", () => {
    expect(courierChangeLine(0)).toBe("");
    expect(courierChangeLine(undefined)).toBe("");
  });
});

describe("resolveFiscalState — o estado do close, ou a derivação da previsão", () => {
  it("o `fiscal_state` do servidor vence a previsão", () => {
    expect(resolveFiscalState({ fiscal_state: "awaiting_payment", fiscal_expected: true })).toBe("awaiting_payment");
    expect(resolveFiscalState({ fiscal_state: "failed", fiscal_expected: false })).toBe("failed");
  });
  it("sem `fiscal_state`: esperada = na fila; não esperada = sem nota", () => {
    expect(resolveFiscalState({ fiscal_expected: true })).toBe("queued");
    expect(resolveFiscalState({ fiscal_expected: false })).toBe("not_expected");
    expect(resolveFiscalState({})).toBe("not_expected");
  });
});

describe("danfeOffer — a DANFE por existência da nota, não por previsão", () => {
  it("só `authorized` ganha o botão vivo", () => {
    expect(danfeOffer("authorized")).toEqual({ kind: "print", label: "Imprimir DANFE" });
  });
  it("na fila: botão desabilitado com a espera nomeada", () => {
    expect(danfeOffer("queued")).toEqual({ kind: "queued", label: "NFC-e na fila…" });
  });
  it("aguardando pagamento e falha dizem o próximo passo; sem nota, nada", () => {
    expect(danfeOffer("awaiting_payment")).toEqual({ kind: "awaiting_payment", label: "NFC-e sai quando o pagamento confirmar" });
    expect(danfeOffer("failed")).toEqual({ kind: "failed", label: "NFC-e falhou — veja Últimas vendas" });
    expect(danfeOffer("not_expected")).toBeNull();
  });
  it("o chip das Últimas vendas fala os mesmos estados", () => {
    expect(fiscalStateLabel("authorized")).toBe("NFC-e autorizada");
    expect(fiscalStateLabel("queued")).toBe("NFC-e na fila");
    expect(fiscalStateLabel("awaiting_payment")).toBe("NFC-e aguarda o pagamento");
    expect(fiscalStateLabel("failed")).toBe("NFC-e falhou");
    expect(fiscalStateLabel("not_expected")).toBe("Sem NFC-e");
  });
});
