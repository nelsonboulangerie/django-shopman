// A aba Encomendas abre com a próxima ação (WP-E10, P1-11 do laudo de 16/11): a
// pronta primeiro, a entregue no fim do dia. A ordem do servidor (a janela)
// continua sendo o eixo; o que muda é quem abre cada janela.
import { describe, expect, it } from "vitest";

import { DELIVERED_GROUP_LABEL, NO_WINDOW_LABEL, checkPaymentNotice, groupByWindow, nextActionFirst } from "~/presentation/preorders";
import type { PreorderCard, PreorderSituation } from "~/types/preorders";

function card(ref: string, situation: PreorderSituation, window_label = "", window_start = ""): PreorderCard {
  return {
    ref,
    channel_display_id: "",
    customer_name: ref,
    channel_ref: "pdv",
    channel_label: "Balcão",
    fulfillment_type: "pickup",
    fulfillment_label: "Retirada",
    commitment_date: "2026-11-16",
    commitment_date_display: "hoje",
    window_label,
    window_start,
    status: "accepted",
    situation,
    situation_label: situation,
    payment_state: "to_receive",
    total_q: 1000,
    total_display: "R$ 10,00",
    balance_q: 1000,
    balance_display: "R$ 10,00",
    items_summary: "1x Pão",
    items_count: 1,
    ticket_printed: false,
  } as PreorderCard;
}

const refs = (cards: readonly PreorderCard[]) => cards.map((c) => c.ref);

describe("a próxima ação no topo", () => {
  it("o caso do laudo: dez entregues e a única pronta, todas a combinar; a pronta abre a lista", () => {
    const delivered = Array.from({ length: 10 }, (_, i) => card(`E${i}`, "delivered"));
    const open = [card("P1", "to_pay"), card("P2", "paid"), card("PRONTA", "ready"), card("P3", "to_pay")];
    const sorted = nextActionFirst([...delivered, ...open]);
    expect(sorted[0]!.ref).toBe("PRONTA");
    expect(refs(sorted.slice(0, 4))).toEqual(["PRONTA", "P1", "P2", "P3"]);
    expect(sorted.slice(4).every((c) => c.situation === "delivered")).toBe(true);
  });

  it("a janela continua sendo o eixo: dentro dela, pronta, depois a espera, depois a que saiu", () => {
    const sorted = nextActionFirst([
      card("A9", "to_pay", "9h às 10h", "09:00"),
      card("S9", "out_for_delivery", "9h às 10h", "09:00"),
      card("R9", "ready", "9h às 10h", "09:00"),
      card("E9", "delivered", "9h às 10h", "09:00"),
      card("R14", "ready", "14h às 15h", "14:00"),
      card("N", "check_payment"),
    ]);
    expect(refs(sorted)).toEqual(["R9", "A9", "S9", "R14", "N", "E9"]);
  });

  it("empate fica na ordem do servidor e a lista de entrada não é alterada", () => {
    const input = [card("B", "to_pay"), card("A", "to_pay"), card("C", "ready")];
    expect(refs(nextActionFirst(input))).toEqual(["C", "B", "A"]);
    expect(refs(input)).toEqual(["B", "A", "C"]);
  });

  it("no modo Dia, as entregues formam um grupo só, no fim", () => {
    const groups = groupByWindow([
      card("E1", "delivered", "9h às 10h", "09:00"),
      card("A", "to_pay", "9h às 10h", "09:00"),
      card("R", "ready", "9h às 10h", "09:00"),
      card("E2", "delivered"),
      card("N", "paid"),
    ]);
    expect(groups.map((g) => [g.label, refs(g.orders)])).toEqual([
      ["9h às 10h", ["R", "A"]],
      [NO_WINDOW_LABEL, ["N"]],
      [DELIVERED_GROUP_LABEL, ["E1", "E2"]],
    ]);
  });
});

describe("o aviso do pagamento a conferir concorda com o número (P2-7)", () => {
  it("uma encomenda: ela não entra; várias: elas não entram", () => {
    expect(checkPaymentNotice(1)).toBe(
      "1 encomenda está com o pagamento a conferir: o sistema não conseguiu ler o que foi pago, e ela não entra em A receber nem em Pagas.",
    );
    expect(checkPaymentNotice(3)).toContain("3 encomendas estão");
    expect(checkPaymentNotice(3)).toContain("e elas não entram");
  });
});
