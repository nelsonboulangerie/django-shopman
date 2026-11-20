// Receber o saldo da encomenda pela tela de Pagamento da venda (EXCELENCIA-PDV
// WP-E5): as formas que a rota aceita, a cobrança que a tela mostra e o corpo que
// vai para `pos/preorders/<ref>/hand-over/`. A rota não muda: o corpo tem de ser o
// que ela já aceita (formas somando o saldo; a nota inteira em `cash_tendered_q`).
import { describe, expect, it } from "vitest";

import { balanceCharge, handOverBody, handOverMethods } from "../app/presentation/balanceCharge";
import { paymentKeyIntent } from "../app/presentation/paymentKeys";
import type { POSPaymentTenderDraft } from "../app/types/pos";

const nbsp = (text: string) => text.replace(/\s/g, " ");
const line = (method: string, amount_q: number): POSPaymentTenderDraft => ({ method, amount_q, collection: "terminal" });

describe("as formas do saldo", () => {
  it("só dinheiro, débito e crédito, na ordem da loja: Pix e link a rota não recebe", () => {
    const methods = [
      { ref: "cash", label: "Dinheiro" },
      { ref: "pix", label: "Pix" },
      { ref: "credit", label: "Crédito" },
      { ref: "debit", label: "Débito" },
      { ref: "link", label: "Link de pagamento" },
    ];
    expect(handOverMethods(methods).map((method) => method.ref)).toEqual(["cash", "credit", "debit"]);
  });
});

describe("a cobrança na tela", () => {
  const base = {
    orderRef: "PDV-7",
    customerName: "Ana Souza",
    handOver: { amount_q: 9300, amount_display: "R$ 93,00", kitchen_notice: "", digital_charge_notice: "" },
    card: { total_q: 9300, total_display: "R$ 93,00" },
    items: [{ sku: "TRADI", name: "Baguette de Tradition", qty: "3", unit_price_display: "R$ 31,00", total_display: "R$ 93,00" }],
  };

  it("o saldo é o total, e os itens são os da encomenda", () => {
    const charge = balanceCharge(base);
    expect(charge).toMatchObject({ orderRef: "PDV-7", customerName: "Ana Souza", amountQ: 9300, amountDisplay: "R$ 93,00" });
    expect(charge.lines).toEqual([{ key: "TRADI-0", qtyLabel: "3x", name: "Baguette de Tradition", totalDisplay: "R$ 93,00" }]);
    expect(charge.paidDisplay).toBe("");
    expect(charge.notices).toEqual([]);
  });

  it("o desconto vem na própria linha: itens a preço de tabela, desconto e total fecham a conta", () => {
    const charge = balanceCharge({
      ...base,
      discountLines: [{ kind: "discount", label: "Desconto do grupo", amount_display: "−R$ 4,80" }],
    });
    expect(charge.adjustments).toEqual([{ key: "discount-0", label: "Desconto do grupo", amountDisplay: "−R$ 4,80" }]);
    expect(balanceCharge(base).adjustments).toEqual([]);
  });

  it("com parte paga antes, a conta fecha: total, já pago e o que falta", () => {
    const charge = balanceCharge({ ...base, handOver: { ...base.handOver, amount_q: 5300, amount_display: "R$ 53,00" } });
    expect(nbsp(charge.paidDisplay)).toBe("R$ 40,00");
    expect(charge.orderTotalDisplay).toBe("R$ 93,00");
  });

  it("as frases do servidor viram avisos: a cobrança cancelada primeiro, a cozinha depois", () => {
    const charge = balanceCharge({
      ...base,
      handOver: {
        ...base.handOver,
        kitchen_notice: "A cozinha ainda não marcou pronto. Ao entregar, a encomenda sai da tela da cozinha.",
        digital_charge_notice: "O Pix enviado ao cliente será cancelado.",
      },
    });
    expect(charge.notices.map((notice) => [notice.key, notice.tone ?? ""])).toEqual([["digital-charge", "warn"], ["kitchen", ""]]);
  });
});

describe("o corpo da rota", () => {
  it("dinheiro a mais: a forma paga o saldo e a nota vai inteira como recebido", () => {
    expect(handOverBody([line("cash", 10000)], 9300)).toEqual({
      tenders: [{ method: "cash", amount_q: 9300 }], cash_tendered_q: 10000,
    });
  });

  it("cédulas em duas linhas viram UMA forma de dinheiro", () => {
    expect(handOverBody([line("cash", 5000), line("cash", 5000)], 9300)).toEqual({
      tenders: [{ method: "cash", amount_q: 9300 }], cash_tendered_q: 10000,
    });
  });

  it("conta dividida: cartão como está, dinheiro com o resto, na ordem da tela", () => {
    expect(handOverBody([line("debit", 4650), line("cash", 5000)], 9300)).toEqual({
      tenders: [{ method: "debit", amount_q: 4650 }, { method: "cash", amount_q: 4650 }], cash_tendered_q: 5000,
    });
    expect(handOverBody([line("cash", 5000), line("credit", 4650)], 9300)).toEqual({
      tenders: [{ method: "cash", amount_q: 4650 }, { method: "credit", amount_q: 4650 }], cash_tendered_q: 5000,
    });
  });

  it("só cartão: sem nota", () => {
    expect(handOverBody([line("credit", 9300)], 9300)).toEqual({ tenders: [{ method: "credit", amount_q: 9300 }] });
  });

  it("encomenda paga não manda forma nenhuma: só entrega", () => {
    expect(handOverBody([], 0)).toEqual({});
  });
});

describe("o teclado da tela de Pagamento", () => {
  const key = (k: string, mods: Partial<KeyboardEvent> = {}) => ({ key: k, metaKey: false, ctrlKey: false, altKey: false, ...mods });

  it("com uma linha selecionada, dígito, vírgula, Backspace e = editam o valor", () => {
    expect(paymentKeyIntent(key("7"), true)).toEqual({ kind: "digit", digit: "7" });
    expect(paymentKeyIntent(key(","), true)).toEqual({ kind: "comma" });
    expect(paymentKeyIntent(key("."), true)).toEqual({ kind: "comma" });
    expect(paymentKeyIntent(key("Backspace"), true)).toEqual({ kind: "backspace" });
    expect(paymentKeyIntent(key("="), true)).toEqual({ kind: "exact" });
  });

  it("sem linha selecionada o valor não tem o que editar; a letra ainda lança a forma", () => {
    expect(paymentKeyIntent(key("7"), false)).toBeNull();
    expect(paymentKeyIntent(key("d"), false)).toEqual({ kind: "letter", letter: "D" });
  });

  it("com modificador a tecla não é desta tela (Ctrl K, Cmd R)", () => {
    expect(paymentKeyIntent(key("k", { ctrlKey: true }), true)).toBeNull();
    expect(paymentKeyIntent(key("7", { metaKey: true }), true)).toBeNull();
  });
});
