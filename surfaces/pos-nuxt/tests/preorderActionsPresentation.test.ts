// Os gestos do detalhe de uma encomenda: a forma de balcão, o troco, as frases
// dos botões e o corpo da rota. A régua (pode entregar? quanto falta?) é do
// servidor; aqui se prende o que a tela decide sozinha.
import { describe, expect, it } from "vitest";

import {
  COUNTER_METHODS,
  changeLine,
  checkReceive,
  handOverBody,
  handOverCta,
  handOverDoneMessage,
  initialMethod,
  paidOnlineNotice,
  receiveConfirmLabel,
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

describe("receber e entregar — a forma e o troco", () => {
  it("as formas do balcão: dinheiro, débito e crédito", () => {
    expect(COUNTER_METHODS.map((m) => [m.key, m.label])).toEqual([
      ["cash", "Dinheiro"], ["debit", "Débito"], ["credit", "Crédito"],
    ]);
  });

  it("abre na forma que o cliente combinou; sem combinado, dinheiro", () => {
    expect(initialMethod({ suggested_method: "debit" })).toBe("debit");
    expect(initialMethod({ suggested_method: "" })).toBe("cash");
  });

  it("dinheiro com campo vazio é o valor exato, sem troco", () => {
    expect(checkReceive("cash", 3600, "")).toEqual({ ok: true, tenderedQ: 3600, changeQ: 0, message: "" });
  });

  it("dinheiro a mais vira troco; a menos não deixa confirmar", () => {
    expect(checkReceive("cash", 3600, "50")).toMatchObject({ ok: true, tenderedQ: 5000, changeQ: 1400 });
    expect(checkReceive("cash", 3600, "50,00")).toMatchObject({ ok: true, changeQ: 1400 });
    const short = checkReceive("cash", 3600, "20");
    expect(short.ok).toBe(false);
    expect(nbsp(short.message)).toBe("O valor recebido não cobre R$ 36,00.");
    expect(checkReceive("cash", 3600, "abc").ok).toBe(false);
  });

  it("cartão não tem troco: a maquininha cobra o valor exato", () => {
    expect(checkReceive("debit", 3600, "999")).toEqual({ ok: true, tenderedQ: 0, changeQ: 0, message: "" });
  });

  it("troco por extenso, e zero é frase", () => {
    expect(nbsp(changeLine(1400))).toBe("Troco: R$ 14,00");
    expect(changeLine(0)).toBe("Sem troco");
  });
});

describe("receber e entregar — as frases e o corpo", () => {
  it("o botão diz o gesto inteiro", () => {
    expect(handOverCta({ needs_payment: true, amount_display: "R$ 36,00" })).toBe("Receber R$ 36,00 e entregar");
    expect(handOverCta({ needs_payment: false, amount_display: "R$ 0,00" })).toBe("Entregar");
  });

  it("a confirmação diz a forma", () => {
    expect(receiveConfirmLabel("cash", "R$ 36,00")).toBe("Receber R$ 36,00 em dinheiro e entregar");
    expect(receiveConfirmLabel("debit", "R$ 36,00")).toBe("Receber R$ 36,00 no débito e entregar");
    expect(receiveConfirmLabel("credit", "R$ 36,00")).toBe("Receber R$ 36,00 no crédito e entregar");
  });

  it("o corpo: a forma com o valor que falta, e a nota só no dinheiro", () => {
    const handOver = { needs_payment: true, amount_q: 3600 };
    expect(handOverBody(handOver, "cash", checkReceive("cash", 3600, "50"))).toEqual({
      tenders: [{ method: "cash", amount_q: 3600 }], cash_tendered_q: 5000,
    });
    expect(handOverBody(handOver, "credit", checkReceive("credit", 3600, ""))).toEqual({
      tenders: [{ method: "credit", amount_q: 3600 }],
    });
  });

  it("encomenda paga não manda forma nenhuma: só entrega", () => {
    expect(handOverBody({ needs_payment: false, amount_q: 0 }, "cash", checkReceive("cash", 0, ""))).toEqual({});
  });

  it("o aviso de feito diz o que entrou", () => {
    expect(nbsp(handOverDoneMessage(3600))).toBe("Recebido R$ 36,00. Encomenda entregue.");
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
