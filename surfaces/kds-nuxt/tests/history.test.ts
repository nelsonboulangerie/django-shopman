import { describe, expect, it } from "vitest";

import { historyEmptyTitle, historyFootnote, historyRow } from "~/presentation/history";
import type { KDSHistoryEntryProjection, KDSTicketProjection } from "~/types/kds";

function entry(over: Partial<KDSHistoryEntryProjection> = {}, ticket: Partial<KDSTicketProjection> = {}) {
  return {
    ticket: {
      pk: 7,
      order_ref: "BAL-261013-0131",
      customer_name: "Ana",
      is_preorder: false,
      fulfillment_icon: "storefront",
      previous_tab_ref: "",
      ...ticket,
    } as KDSTicketProjection,
    state: "done",
    items_summary: "2x Croque, 1x Café",
    steps: ["recebido 21:40", "iniciado 21:42 Rafael", "Pronto 21:51 Rafael (tela)"],
    undone: [],
    prep_display: "9 min",
    can_reopen: true,
    reopen_block_reason: "",
    ...over,
  } as KDSHistoryEntryProjection;
}

describe("Histórico de hoje: a linha de cada pedido", () => {
  it("diz o código, os itens, a trilha e o preparo", () => {
    const row = historyRow(entry());
    expect(row.code).toBe("0131");
    expect(row.items).toBe("2x Croque, 1x Café");
    expect(row.trail).toBe("recebido 21:40 · iniciado 21:42 Rafael · Pronto 21:51 Rafael (tela)");
    expect(row.prep).toBe("preparo 9 min");
    expect(row.overline).toBe("");
    expect(row.canReopen).toBe(true);
  });

  it("na encomenda diz Encomenda e o cliente", () => {
    expect(historyRow(entry({}, { is_preorder: true })).overline).toBe("Encomenda · Ana");
  });

  it("o que já saiu da cozinha só se vê, com o motivo", () => {
    const reason = "Pedido despachado: não volta à cozinha. Para refazer, peça pelo PDV ou pelo Gestor.";
    const row = historyRow(entry({ can_reopen: false, reopen_block_reason: reason }));
    expect(row.canReopen).toBe(false);
    expect(row.blockedReason).toBe(reason);
  });

  it("o cancelado não tem preparo nem Reabrir", () => {
    const row = historyRow(
      entry({ state: "cancelled", prep_display: "", can_reopen: false, steps: ["recebido 21:40", "Cancelado 21:45"] }),
    );
    expect(row.cancelled).toBe(true);
    expect(row.prep).toBe("");
    expect(row.canReopen).toBe(false);
  });

  it("o rodapé só aparece quando a lista não mostra o dia inteiro", () => {
    const entries = [entry()];
    expect(historyFootnote({ entries, total: 1, query: "" })).toBe("");
    expect(historyFootnote({ entries, total: 140, query: "" })).toBe(
      "Mostrando os 1 mais recentes de 140. Busque pelo código para achar os outros.",
    );
  });

  it("o vazio diz se é o dia ou a busca", () => {
    expect(historyEmptyTitle("")).toBe("Nenhum pedido concluído ou cancelado hoje nesta estação.");
    expect(historyEmptyTitle(" 0131 ")).toBe("Nenhum pedido de hoje para “0131”.");
  });
});
