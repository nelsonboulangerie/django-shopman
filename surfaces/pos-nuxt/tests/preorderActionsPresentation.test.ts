// Os gestos do detalhe de uma encomenda: as frases dos botões e dos avisos. A
// régua (pode entregar? quanto falta?) é do servidor, e receber o saldo é a tela
// de Pagamento da venda (`balanceChargePresentation.test.ts`).
import { describe, expect, it } from "vitest";

import {
  handOverCta,
  handOverDoneMessage,
  paidOnlineNotice,
  redoNotice,
  rescheduleChanged,
  rescheduleConfirmLabel,
  rescheduleDoneMessage,
} from "../app/presentation/preorderActions";

const nbsp = (text: string) => text.replace(/\s/g, " ");

describe("receber e entregar — o cliente que acabou de pagar online", () => {
  it("só o código do servidor vira aviso, e o aviso diz para não cobrar", () => {
    expect(paidOnlineNotice("preorder_paid_online")).toBe(
      "O cliente acabou de pagar online. Não receba no balcão: só entregue a encomenda.",
    );
    expect(paidOnlineNotice("digital_charge_not_cancelled")).toBe("");
    expect(paidOnlineNotice("")).toBe("");
  });
});

describe("receber e entregar — as frases", () => {
  it("o botão diz o gesto inteiro", () => {
    expect(handOverCta({ needs_payment: true, amount_display: "R$ 36,00" })).toBe("Receber R$ 36,00 e entregar");
    expect(handOverCta({ needs_payment: false, amount_display: "R$ 0,00" })).toBe("Entregar");
  });

  it("o aviso de feito diz o que entrou e, com dinheiro a mais, o troco", () => {
    expect(nbsp(handOverDoneMessage(3600))).toBe("Recebido R$ 36,00. Encomenda entregue.");
    expect(nbsp(handOverDoneMessage(3600, 1400))).toBe("Recebido R$ 36,00, com troco de R$ 14,00. Encomenda entregue.");
    expect(handOverDoneMessage(0)).toBe("Encomenda entregue.");
  });
});

describe("reagendar — as frases", () => {
  it("só muda quando a data ou a janela mudou", () => {
    const current = { date: "2026-09-26", slot: "slot-09" };
    expect(rescheduleChanged(current, { date: "2026-09-26", slot: "slot-09" })).toBe(false);
    expect(rescheduleChanged(current, { date: "2026-09-27", slot: "" })).toBe(true);
    expect(rescheduleChanged(current, { date: "2026-09-26", slot: "slot-12" })).toBe(true);
    expect(rescheduleChanged(current, { date: "", slot: "" })).toBe(false);
  });

  it("o botão diz para onde vai; sem escolha, pede a data", () => {
    expect(rescheduleConfirmLabel("sáb, 27/09")).toBe("Mudar para sáb, 27/09");
    expect(rescheduleConfirmLabel("")).toBe("Escolha a nova data");
  });

  it("o aviso de feito diz se a encomenda já entrou no preparo de hoje", () => {
    expect(rescheduleDoneMessage(true, false)).toBe("Data trocada.");
    expect(rescheduleDoneMessage(true, true)).toContain("já entrou no preparo de hoje");
    expect(rescheduleDoneMessage(false, false)).toContain("Nada mudou");
  });
});

describe("redoNotice — o aviso diz o que aconteceu", () => {
  it("com caixa aberto, a venda abriu na comanda", () => {
    expect(redoNotice({ order_ref: "A17", schedule_dropped: "" })).toBe(
      'A venda nova abriu na comanda "Refazer A17", com os itens da encomenda cancelada: ajuste e feche a venda.',
    );
  });

  it("sem caixa aberto, a comanda espera no quadro e a tela manda abrir o caixa", () => {
    const notice = redoNotice({ order_ref: "A17", schedule_dropped: "" }, { needsOpenShift: true });
    expect(notice).toBe(
      'Comanda "Refazer A17" pronta no quadro, com os itens da encomenda cancelada. Abra o caixa para continuar a venda.',
    );
    expect(notice).not.toContain("abriu");
  });
});
